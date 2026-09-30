# -*- coding: utf-8 -*-
"""表面图寻路：Goal → SurfaceGraph(锚点图) → RoutePlan → RouteExecutor。

旧版只有「地板 → 一块窗口顶边 → 目标」这条定长两段路，于是「先爬杆、再跳平台、
再够到目标」这类目标永远没人去拿 —— 不是参数问题，是导航拓扑没成形。
原版是「房间 tile 图 + A*」（Room.CreateTileGraph / PathFinder）；桌宠没有 tile 图，
但有等价的东西：地板段、窗口顶边（单向平台）、竖杆顶、横杆面，都是可站立的支撑面。

导航节点不是「一整块面」，而是 **面 × 锚点**（NavNode = surf_id + x_anchor）：

    A 面 [100..500] → A@116 / A@280 / A@420 …（同面相邻锚点用 walk 边相连）
    Edge = 一次位移，带类型与代价：
           walk        同一面上相邻锚点走过去（含小缝隙 STEP_X）
           jump / drop 从一个锚点跳到另一块面的锚点上（实测轨迹族 jump/jumpfall/drop/flip）
           climb_pole  沿竖杆爬到杆顶
           pole_beam   杆间跳跃（空中抓另一根杆）
           finish      从该锚点伸手 / 起跳弧够到目标点
    每条边带：耗时 / 体力 / 风险 / 是否落地 / 终点姿态 / 起终锚点。
    代价 = route.edge 的六轴模型（时间 / 体力 / 风险 / 噪音 / 精度 / 后摇）× 性格。

为什么必须带锚点：代价里的「走到起跳点」必须用**真实起点**。旧版用
`abs(launch_x - a.clamp(launch_x))`，而 launch_x 本来就采在 a 的区间内 → 恒等于 0，
于是规划器认为「走到起跳位置不花时间」，路线看着聪明、走起来不对。

寻路：Dijkstra（节点数是个位数～几十，无需启发式）；终点（finish）当普通 terminal
边参与比较，不再「一弹出就返回」。可达性：只有「去得了、还能回来」的锚点才允许收尾
（原版 accessibility mapping 的等价物），免得猫跳进一个回不来的角落。

执行：RouteExecutor 按当前 leg 建既有控制器（HopReach / PoleJumpReach），落地后
**重新规划**接着走下一段；只有原目标（original_goal）被满足才算结束 —— 不会把
「第一段落点」当成终点，于是不会再出现「跳上平台就发呆」。
"""
from __future__ import annotations

from ..behavior import tuning
from ..core import chunkphys
from ..core.units import clampf
from .ability import (DONE, GIVEUP, HOLD, HOLDING, MODE_TOUCH, RUNNING,
                      walk_band)
from .backflip_reach import takeoff_c0_h
from .goal import point_goal
from .hop_reach import HopReach, HopReachController, surface_under
from .jump_arc import get_arc, sweep_hit
from .pole_hop import hop_plan, land_sweep, pole_hit
from .pole_reach import PoleJumpReach
from .route import edge_for, landing_safe, route_cost
from .walk_reach import WalkReach

OPTIMISM = 1.30          # 多段路线的代价保守系数（宁可低估直连、不高估两段）
ANCHOR_STEP = 120.0      # 同一块面上锚点间距（NavNode 的位置分辨率）
ANCHOR_INSET = 16.0      # 锚点离面两端至少这么远（landing_safe 边距之外）
HAND_UP = 12.0           # 站在面上时手离脚面的高度（手在身侧偏下）
WALK_Y_EPS = 6.0         # 同一块面：纵向容差（像素）
STEP_X = 14.0            # 走过去能跨过的横向缝隙上限
POLE_TIP_PAD = 10.0      # 杆顶可站立的横向范围
POLE_CLIMB_SPEED = 0.55  # 爬杆速度（px/tick，整条腿留给执行器）
BEAM_PENALTY = 1.25      # 杆上位移的保守系数（比走地面更容易失败）
LAND_PAD = tuning.PLAN_WALK_X_PAD

_ENV = {}


def _anchors(lo, hi):
    """一块面上的锚点 x 列表（面 × 锚点 = 导航节点）。"""
    lo, hi = min(lo, hi), max(lo, hi)
    if hi - lo <= 2.0 * ANCHOR_INSET:
        return [0.5 * (lo + hi)]
    a, b = lo + ANCHOR_INSET, hi - ANCHOR_INSET
    n = max(2, int((b - a) // ANCHOR_STEP) + 1)
    if n <= 2:
        return [a, b]
    step = (b - a) / (n - 1)
    return [a + i * step for i in range(n)]


def _dedupe(xs):
    out = []
    for x in xs:
        if not out or x - out[-1] > 0.5:
            out.append(x)
    return out


def _envelope(stats):
    """本猫的跳跃包线 (最高升高, 最远横距)：够不到的面就别扫掠（空间粗筛）。"""
    v = _ENV.get(stats)
    if v is None:
        rise, dx = 0.0, 0.0
        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            for md in (0, 1, -1):
                arc = get_arc(stats, hold, md)
                rise = max(rise, max(-p[1] for p in arc.points))
                dx = max(dx, max(abs(p[0]) for p in arc.points))
        v = (rise, dx)
        _ENV[stats] = v
    return v


def _arc_grab(stats, lx, ly, pole, r):
    """从地面起跳，飞行轨迹上够到某根杆就抓住：返回第几 tick 抓到，无解 None。"""
    for hold in tuning.PLAN_JUMP_HOLD_GEARS:
        for md in (1, -1):
            for i, (px, py) in enumerate(get_arc(stats, hold, md).points):
                if i < 1:
                    continue
                if pole_hit(pole, lx + px, ly + py, r):
                    return i + 1
    return None


def _hop_controller(pet, leg):
    '''按边自带的实测轨迹建 HopReachController（先走到起跳锚点再起跳）。'''
    if leg.plan is None:
        return None
    k, hold, md, land_x, _ly, ticks, launch_x = leg.plan
    return HopReachController(pet, leg.goal(), (k, hold, md, launch_x, land_x, ticks))


def _point_in_solids(x, y, shrink=1.0):
    """点是不是落在庇护所墙体 / 关上的门里面（各边向内收，避免贴着面误判）。"""
    for (a0, b0, a1, b1) in chunkphys.cat_solids():
        if a0 + shrink < x < a1 - shrink and b0 + shrink < y < b1 - shrink:
            return True
    return False


def _walk_blocked(x0, x1, y):
    """同一块面上从一个锚点走到另一个：中间会不会被庇护所墙体挡住。

    把猫看成 [x0..x1] × [y-WALK_BODY_H, y] 一条扫掠带：高过脚面一步以上的
    实心块算墙，矮的（庇护所底墙 5.6px）只是台阶，底边高过猫头的（门口上方
    那段外墙 / 走廊层的缺口）也放行 —— 于是「屋外 → 门洞 → 屋内」这一条正通。
    """
    lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
    for (a0, b0, a1, b1) in chunkphys.cat_solids():
        if a1 <= a0 or b1 <= b0:
            continue
        if a1 <= lo or a0 >= hi:
            continue
        if b1 <= y - tuning.WALK_BODY_H:
            continue
        if b0 >= y - tuning.WALK_STEP_UP:
            continue
        return True
    return False


def _merge_spans(spans):
    """把 x 区间合并成互不相邻的几段（走带切分用）。"""
    out = []
    for a, b in sorted(spans):
        if a > b:
            a, b = b, a
        if out and a <= out[-1][1] + 0.5:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _roof_under(pet, x, y):
    """(x,y) 站在哪间庇护所的屋顶上；不是则 None。返回 (x0, x1)。"""
    for sh in getattr(pet, "shelters", ()) or ():
        if abs(y - sh.y) <= 3.0 and sh.x <= x <= sh.x + sh.w:
            return (sh.x, sh.x + sh.w)
    return None


def _reach_from_surface(stats, y0, lo, hi, start_x, gx, gy):
    """站在支撑面 y0（可走区间 [lo,hi]）的锚点 start_x 上能不能够到 (gx,gy)。

    返回 (耗时, 体力)；够不到 None。纯几何（不读实时 body），所以可测试、
    也可以拿去问「我落在那块面上以后够不够得到」。start_x 是真实起点（锚点），
    所以「走过去伸手」那段是真实耗时，不再恒等于 0。
    """
    if hi < lo:
        lo, hi = hi, lo
    best = None
    wx = min(max(gx, lo), hi)
    hand_y = y0 - HAND_UP
    # ① 走过去伸手
    if (abs(gy - hand_y) <= tuning.GRAB_REACH + 6.0
            and abs(gx - wx) <= tuning.GRAB_REACH):
        t = abs(wx - start_x) / tuning.PLAN_WALK_SPEED
        best = (t, t * tuning.PLAN_EN_RATE_LIGHT)
    # ② 面上起跳（土狼跳那套弧线族）：起跳点取锚点附近几档
    launch_y = y0 - takeoff_c0_h(stats)
    xs = _dedupe(sorted(clampf(start_x + k * tuning.PLAN_WALK_X_PAD, lo, hi)
                        for k in (0.0, -1.0, 1.0)))
    for hold in tuning.PLAN_JUMP_HOLD_GEARS:
        for md in (0, 1, -1):
            arc = get_arc(stats, hold, md)
            for lx in xs:
                hit = sweep_hit(arc, gx - lx, gy - launch_y, tuning.GRAB_REACH)
                if hit is None:
                    continue
                t = (abs(lx - start_x) / tuning.PLAN_WALK_SPEED + hit
                     + tuning.PLAN_STARTUP_TICKS)
                e = (t * tuning.PLAN_EN_RATE_LIGHT
                     + hit * tuning.PLAN_EN_RATE_VIGOROUS)
                if best is None or t < best[0]:
                    best = (t, e)
    return best


# ══════════════════════════ 节点与边 ══════════════════════════

class SurfaceNode:
    """一个导航节点：某块支撑面上的一个锚点（NavNode = surf_id + x_anchor）。"""

    __slots__ = ("kind", "y", "lo", "hi", "pole", "here", "anchor", "sid")

    def __init__(self, kind, y, lo, hi, pole=None, here=False, anchor=None, sid=""):
        self.kind = kind          # floor / deck / pole_tip / pole_h
        self.y = float(y)
        self.lo = float(min(lo, hi))
        self.hi = float(max(lo, hi))
        self.pole = pole
        self.here = here          # 猫此刻站在这个锚点上
        self.sid = sid            # 所属支撑面 id（同 id = 同一块面）
        self.anchor = float(clampf((self.lo + self.hi) * 0.5
                                   if anchor is None else anchor, self.lo, self.hi))

    @property
    def width(self):
        return self.hi - self.lo

    def clamp(self, x):
        return clampf(x, self.lo, self.hi)

    def near(self, x, pad=0.0):
        return self.lo - pad <= x <= self.hi + pad

    def key(self):
        return (self.kind, round(self.y, 1), round(self.lo, 1),
                round(self.hi, 1), round(self.anchor, 1))

    def __repr__(self):
        return "<%s y=%.0f [%.0f..%.0f] @%.0f>" % (self.kind, self.y, self.lo,
                                                   self.hi, self.anchor)


class SurfaceEdge:
    """一次位移。字段就是文档里要求的那几项。"""

    __slots__ = ("kind", "src", "dst", "time", "energy", "risk", "lands", "pose",
                 "plan", "land_x")

    def __init__(self, kind, src, dst, time, energy, land_x, pose, plan=None, risk=0.0):
        self.kind = kind          # walk / jump / drop / climb_pole / pole_beam / finish
        self.src = src
        self.dst = dst            # None＝终点是目标点（finish）
        self.time = float(time)
        self.energy = float(energy)
        self.risk = float(risk)   # 0..1 失败倾向
        self.lands = kind in ("jump", "drop", "pole_beam")
        self.pose = pose          # 终点姿态：stand / crouch / hang / tip
        self.plan = plan          # 执行器要的原始轨迹（land_sweep 的返回值等）
        self.land_x = float(land_x)

    def goal(self):
        """这条边跑完之后猫应该把哪个点当目标（执行器用）。"""
        if self.dst is None:
            return None
        return point_goal(self.land_x, self.dst.y, contact="travel")

    def __repr__(self):
        return "<%s→%s %.1ft>" % (self.kind, self.dst, self.time)


class SurfaceGraph:
    """锚点图：节点 + 有向边。懒构建，按几何版本缓存。"""

    def __init__(self):
        self.nodes = []
        self.adj = {}             # index → [SurfaceEdge]
        self.start = None
        self._here_sid = None
        self._surf = {}           # sid → dict(kind,y,lo,hi,pole,idx[])
        self._returnable = set()

    def add_node(self, node):
        self.nodes.append(node)
        self.adj[len(self.nodes) - 1] = []
        return len(self.nodes) - 1

    def add_edge(self, i, edge):
        self.adj[i].append(edge)

    def idx(self, node):
        return self.nodes.index(node)

    # ── 构建 ──
    def _add_surface(self, sid, kind, y, lo, hi, pole=None):
        """一块面 → 一串锚点节点（相互之间用 walk 边连成链）。"""
        lo, hi = min(lo, hi), max(lo, hi)
        xs = _anchors(lo, hi)
        idxs = []
        for x in xs:
            idxs.append(self.add_node(SurfaceNode(kind, y, lo, hi, pole=pole,
                                                  anchor=x, sid=sid)))
        # 同面相邻锚点：走过去
        for a, b in zip(idxs, idxs[1:]):
            d = abs(self.nodes[b].anchor - self.nodes[a].anchor)
            if d < 0.5:
                continue
            t = d / tuning.PLAN_WALK_SPEED
            self.add_edge(a, SurfaceEdge("walk", self.nodes[a], self.nodes[b], t,
                                         t * tuning.PLAN_EN_RATE_LIGHT,
                                         self.nodes[b].anchor, "stand"))
            self.add_edge(b, SurfaceEdge("walk", self.nodes[b], self.nodes[a], t,
                                         t * tuning.PLAN_EN_RATE_LIGHT,
                                         self.nodes[a].anchor, "stand"))
        self._surf[sid] = dict(kind=kind, y=float(y), lo=lo, hi=hi, pole=pole,
                               idx=idxs)
        return idxs

    def _add_shelter(self, k, sh, start_node, WL):
        """庇护所 = 矩形障碍 + 一个门洞（不给它塞 chamber / tunnel）。

        - 屋顶（deck）：跳上去、横穿、再从另一侧落下 —— 多段路里的「绕」；
        - 屋里地面（shelter）：底墙顶边，只能**从门洞走进来**（jump 落点不给它）；
        - 屋外两侧的走带（floor）：只有这间屋子确实挡住猫脚下这条走道时才加，
          于是「屋外 → 门洞 → 屋内」由 _link_gaps 的避墙检查连成一条 walk 链。
        """
        lo, hi = sh.interior_span()
        if hi - lo >= 2.0:
            self._add_surface("shell:%d" % k, "shelter", sh.interior_floor_y(),
                              lo, hi)
        rx0, rx1 = sh.roof_span()
        if rx1 - rx0 >= 2.0 and sh.y > 4.0:
            self._add_surface("sroof:%d" % k, "deck", sh.y, rx0, rx1)
        gy = start_node.y
        cuts = _merge_spans(sh.cut_span(gy))
        if not cuts:
            return                        # 猫脚下这条走道没被挡：屋里屋外本来就通
        seg, cur = [], 0.0
        for a, b in cuts:
            if a - cur >= 4.0:
                seg.append((cur, a))
            cur = max(cur, b)
        if WL - cur >= 4.0:
            seg.append((cur, WL))
        for j, (a, b) in enumerate(seg):
            self._add_surface("sground:%d:%d" % (k, j), "floor", gy,
                              max(a, 0.0), min(b, WL))

    def start_at(self, x):
        """把「起点」指向猫脚下这块面上离它最近的锚点。

        图本身不因猫移动而重建（锚点是固定的）；猫到该锚点之间那一小段走路
        由调用方按真实起点补进总代价里 —— 于是「走到起跳点」既不恒等于 0，
        也不用每帧重建整张图。
        """
        idxs = self._surf[self._here_sid]["idx"] if self._here_sid else []
        if not idxs:
            return self.start
        k = min(idxs, key=lambda i: abs(self.nodes[i].anchor - x))
        for i in idxs:
            self.nodes[i].here = (i == k)
        self.start = k
        return k

    @classmethod
    def build(cls, pet, start_node):
        g = cls()
        WL = pet._WL
        body = pet.body
        sx = clampf(getattr(body.chunk1, "x", 0.0), start_node.lo, start_node.hi)
        g._here_sid = "here"
        g._add_surface("here", start_node.kind, start_node.y,
                       start_node.lo, start_node.hi)
        g.start = 0

        for k, (x0, y0, x1) in enumerate(chunkphys.platforms()):
            lo, hi = max(min(x0, x1), 0.0), min(max(x0, x1), WL)
            if hi - lo < 2.0:
                continue
            if (abs(y0 - start_node.y) <= WALK_Y_EPS
                    and lo >= start_node.lo - 1.0 and hi <= start_node.hi + 1.0):
                continue                  # 就是猫脚下那块面，已经在图里了
            g._add_surface("deck:%d" % k, "deck", y0, lo, hi)

        for k, sh in enumerate(getattr(pet, "shelters", ()) or ()):
            g._add_shelter(k, sh, start_node, WL)

        for k, p in enumerate(getattr(pet, "poles", ())):
            if getattr(p, "virtual", False):
                continue                  # 光标虚杆不进表面图（它自己一套）
            if getattr(p, "kind", None) == "vertical":
                top = min(p.ay, p.by)
                if top <= 0.0:
                    continue
                g._add_surface("vpole:%d" % k, "pole_tip", top,
                               p.bx - POLE_TIP_PAD, p.bx + POLE_TIP_PAD, pole=p)
            else:
                lo, hi = max(min(p.ax, p.bx), 0.0), min(max(p.ax, p.bx), WL)
                if hi - lo < 2.0:
                    continue
                g._add_surface("hpole:%d" % k, "pole_h", p.ay, lo, hi, pole=p)

        g._link_gaps()
        g._link_jumps(pet)
        g._link_poles(pet)
        g._link_beams(pet)
        g.start_at(sx)
        g._compute_returnable()
        return g

    def _link_gaps(self):
        """两块面同高、缝 ≤ STEP_X：走过去（旧版要求真重叠，8px 小缝直接判不连通）。"""
        flat = ("floor", "deck", "pole_h", "shelter")
        sids = list(self._surf)
        for ii, sa in enumerate(sids):
            a = self._surf[sa]
            if a["kind"] not in flat:
                continue
            for sb in sids[ii + 1:]:
                b = self._surf[sb]
                if b["kind"] not in flat or abs(a["y"] - b["y"]) > WALK_Y_EPS:
                    continue
                if a["hi"] < b["lo"]:
                    if b["lo"] - a["hi"] > STEP_X:
                        continue
                elif b["hi"] < a["lo"]:
                    if a["lo"] - b["hi"] > STEP_X:
                        continue
                # 重叠也算同一块面（屋外走带 / 屋里地面会叠在一起）
                best = None
                for ka in a["idx"]:
                    for kb in b["idx"]:
                        d = abs(self.nodes[kb].anchor - self.nodes[ka].anchor)
                        if best is None or d < best[0]:
                            best = (d, ka, kb)
                if best is None:
                    continue
                d, ka, kb = best
                if _walk_blocked(self.nodes[ka].anchor, self.nodes[kb].anchor,
                                 a["y"]):
                    continue              # 中间隔着庇护所墙 / 关上的门：走不过去
                t = d / tuning.PLAN_WALK_SPEED
                self.add_edge(ka, SurfaceEdge("walk", self.nodes[ka], self.nodes[kb], t,
                                              t * tuning.PLAN_EN_RATE_LIGHT,
                                              self.nodes[kb].anchor, "stand"))
                self.add_edge(kb, SurfaceEdge("walk", self.nodes[kb], self.nodes[ka], t,
                                              t * tuning.PLAN_EN_RATE_LIGHT,
                                              self.nodes[ka].anchor, "stand"))

    def _link_jumps(self, pet):
        """锚点 → 另一块面（或更低的面）的锚点：交给实测轨迹族 land_sweep。"""
        stats = pet.cat.stats
        off = takeoff_c0_h(stats)
        rise_max, dx_max = _envelope(stats)
        kinds = ("floor", "deck", "pole_h", "pole_tip")
        span_pad = dx_max + 4.0 * tuning.PLAN_WALK_X_PAD
        for i, a in enumerate(self.nodes):
            if a.kind not in kinds:
                continue
            launch_y = a.y - off
            for j, b in enumerate(self.nodes):
                if i == j or b.kind not in kinds or a.sid == b.sid:
                    continue
                up = a.y - b.y                 # >0：目标更高
                if abs(up) <= 2.0:
                    continue                   # 同高：walk 那条边在管
                if up > rise_max + tuning.GRAB_REACH:
                    continue                   # 高过一个跳跃的极限（空间粗筛）
                if abs(b.anchor - a.anchor) > span_pad + abs(up):
                    continue                   # 横向太远（空间粗筛）
                launches = self._launches(a, b.anchor, launch_y)
                r = land_sweep(stats, [(b.lo, b.y, b.hi)], launches,
                               want=(b.anchor, b.y), land_off=off)
                if r is None:
                    continue
                kind, hold, md, land_x, _ly, ticks, launch_x = r
                if not landing_safe(land_x, b.lo, b.hi):
                    continue                   # 落点贴着平台边：这只猫不愿意赌
                if abs(land_x - b.anchor) > max(LAND_PAD, ANCHOR_STEP):
                    continue                   # 落到别的锚点去了：那条边在管
                t = (abs(launch_x - a.anchor) / tuning.PLAN_WALK_SPEED
                     + ticks + tuning.PLAN_STARTUP_TICKS)
                e = t * tuning.PLAN_EN_RATE_LIGHT + ticks * tuning.PLAN_EN_RATE_VIGOROUS
                risk = 0.15 if kind == "flip" else 0.05
                ekind = "jump" if up > 0.0 else "drop"
                self.add_edge(i, SurfaceEdge(ekind, a, b, t, e, land_x, "crouch",
                                             plan=r, risk=risk))

    def _link_poles(self, pet):
        """沿竖杆爬上杆顶（climb_pole）。"""
        for i, a in enumerate(self.nodes):
            for j, b in enumerate(self.nodes):
                if a.sid == b.sid or b.kind != "pole_tip" or b.pole is None:
                    continue
                pole = b.pole
                if b.y >= a.y - 2.0:
                    continue
                lo, hi = min(pole.ay, pole.by), max(pole.ay, pole.by)
                if not (lo - tuning.POLE_AIRGRAB_PAD <= a.y <= hi + tuning.POLE_AIRGRAB_PAD):
                    continue
                if abs(pole.bx - a.anchor) > tuning.POLE_TRANSPORT_NEAR:
                    continue
                rise = a.y - b.y
                t = (abs(pole.bx - a.anchor) / tuning.PLAN_WALK_SPEED
                     + rise / POLE_CLIMB_SPEED + tuning.PLAN_STARTUP_TICKS)
                self.add_edge(i, SurfaceEdge("climb_pole", a, b, t * BEAM_PENALTY,
                                             t * tuning.PLAN_EN_RATE_VIGOROUS,
                                             pole.bx, "tip"))

    def _link_beams(self, pet):
        """杆间跳跃 / 地面起跳抓杆：空中贴到另一根杆就抓住（pole_beam）。"""
        stats = pet.cat.stats
        r = tuning.POLE_AIRGRAB_R
        off = takeoff_c0_h(stats)
        for i, a in enumerate(self.nodes):
            for j, b in enumerate(self.nodes):
                if a.sid == b.sid or b.kind not in ("pole_tip", "pole_h") or b.pole is None:
                    continue
                if a.pole is not None and a.pole is b.pole:
                    continue
                if a.kind in ("pole_tip", "pole_h"):
                    plan = hop_plan(stats, [b.pole], a.anchor, a.y,
                                    grab=r, want=(b.anchor, b.y))
                    if plan is None:
                        continue
                    hit = plan[2]
                else:
                    hit = _arc_grab(stats, a.anchor, a.y - off, b.pole, r)
                    if hit is None:
                        continue
                t = hit + tuning.PLAN_STARTUP_TICKS
                self.add_edge(i, SurfaceEdge("pole_beam", a, b, t * BEAM_PENALTY,
                                             t * tuning.PLAN_EN_RATE_VIGOROUS,
                                             b.anchor, "hang", risk=0.5))

    @staticmethod
    def _launches(a, want, launch_y):
        xs = []
        for k in (-2, -1, 0, 1, 2):
            x = a.clamp(want + k * 24.0)
            if x not in xs:
                xs.append(x)
        return [(x, launch_y) for x in xs[:5]]

    def _compute_returnable(self):
        """反向可达：从哪些节点能走回起点（原版 accessibility 的「能不能再回来」）。"""
        rev = {}
        for i, edges in self.adj.items():
            for e in edges:
                if e.dst is None:
                    continue
                j = self.idx(e.dst)
                rev.setdefault(j, []).append(i)
        seen = {self.start}
        stack = [self.start]
        while stack:
            cur = stack.pop()
            for k in rev.get(cur, ()):
                if k not in seen:
                    seen.add(k)
                    stack.append(k)
        self._returnable = seen

    # ── 寻路 ──
    def route_to(self, goal_point, stats, pers=None):
        """Dijkstra：起面 → 目标点。返回 (legs, time, energy)；到不了 None。

        finish 是一条普通的 terminal 边：所有可能路径按代价比较完才收尾，
        不再「一弹出就返回」（那样只保证看见了，不保证整条路最便宜）。
        """
        gx, gy = goal_point
        best = {self.start: (0.0, 0.0, 0.0, [])}      # idx → (cost, time, energy, path)
        seen = set()
        fin = None
        while True:
            cur = None
            for idx, rec in best.items():
                if idx in seen:
                    continue
                if cur is None or rec[0] < best[cur][0]:
                    cur = idx
            if cur is None:
                break
            c0 = best[cur][0]
            if fin is not None and fin[0] <= c0 + 1e-9:
                break                            # 剩下的都比已知收尾贵
            seen.add(cur)
            _c, t0, e0, path = best[cur]
            node = self.nodes[cur]
            fin_est = _reach_from_surface(stats, node.y, node.lo, node.hi,
                                          node.anchor, gx, gy)
            if fin_est is not None and cur in self._returnable:
                legs = path + [SurfaceEdge("finish", node, None, fin_est[0],
                                           fin_est[1], node.anchor, "reach")]
                fcost = c0 + route_cost(edge_for("finish", fin_est[0], fin_est[1]), pers)
                if fin is None or fcost < fin[0]:
                    fin = (fcost, legs, (t0 + fin_est[0]) * OPTIMISM,
                           (e0 + fin_est[1]) * OPTIMISM)
            for e in self.adj[cur]:
                if e.dst is None:
                    continue
                j = self.idx(e.dst)
                if j in seen:
                    continue
                nc = c0 + route_cost(edge_for(e.kind, e.time, e.energy), pers)
                old = best.get(j)
                if old is None or nc < old[0] - 1e-9:
                    best[j] = (nc, t0 + e.time, e0 + e.energy, path + [e])
        if fin is None:
            return None
        return (fin[1], fin[2], fin[3])


class RoutePlan:
    """一条多段路线：original_goal + legs + current_leg。

    执行器只跑当前 leg，跑完 current_leg += 1；**只有 original_goal 被满足才算结束**
    （旧版把 legs[0] 的落点当终点，跳上去就发呆）。
    """

    __slots__ = ("original_goal", "legs", "current_leg", "time", "energy")

    def __init__(self, original_goal, legs, time, energy):
        self.original_goal = original_goal
        self.legs = list(legs)
        self.current_leg = 0
        self.time = float(time)
        self.energy = float(energy)

    def leg(self):
        if 0 <= self.current_leg < len(self.legs):
            return self.legs[self.current_leg]
        return None

    def advance(self):
        self.current_leg += 1
        return self.leg()

    def kinds(self):
        return [e.kind for e in self.legs]

    # ── 旧调用兼容：第一段的落点即「眼下的执行目标」 ──
    @property
    def goal(self):
        return self.legs[0].goal()

    @property
    def land_x(self):
        return float(self.legs[0].land_x)

    @property
    def y(self):
        e = self.legs[0]
        return float(e.land_x if e.dst is None else e.dst.y)

    @property
    def deck(self):
        e = self.legs[0]
        return None if e.dst is None else (e.dst.lo, e.dst.y, e.dst.hi)

    def __repr__(self):
        return "<RoutePlan %s>" % (self.kinds(),)


class SurfaceRoute:
    """表面图寻路：Goal → SurfaceGraph → 最优多段路线。"""

    key = "route"

    def __init__(self, pet):
        self.pet = pet
        self._cache = {}
        self._cache_key = None
        self._graph = None            # 锚点图缓存（平台/杆没变就不重建）
        self._gkey = None

    # ── 当前支撑面 ──
    def _here(self):
        """猫此刻的支撑面 (y, lo, hi)。"""
        pet = self.pet
        y = pet.stand_h()
        lo, hi = walk_band(pet)
        bx = pet.body.chunk1.x
        s = surface_under(bx, y)
        if s is not None:                     # 站在窗口顶边上：只能在这块面的范围内走
            lo = max(lo, min(s[1], s[2]))
            hi = min(hi, max(s[1], s[2]))
        else:
            r = _roof_under(pet, bx, y)       # 站在庇护所屋顶上：同理
            if r is not None:
                lo = max(lo, r[0])
                hi = min(hi, r[1])
        return (y, lo, hi)

    def _pers(self):
        beh = getattr(self.pet, "behavior", None)
        pers = getattr(beh, "pers", None)
        if pers is None:
            pers = getattr(getattr(self.pet, "cat", None), "personality", None)
        return pers

    def plan(self, goal):
        pet = self.pet
        body = pet.body
        if getattr(body, "swimming", False) or getattr(body, "zerog", False):
            return None
        if getattr(body, "on_pole", False):
            return None                       # 杆上另有杆间跳/落平台的路
        gx, gy = goal.pos()
        stats = pet.cat.stats
        hy, hlo, hhi = self._here()
        if surface_under(gx, gy) is not None:
            return None                       # 目标就在某块顶边上：HopReach 直连即可
        if _reach_from_surface(stats, hy, hlo, hhi, body.chunk1.x, gx, gy) is not None:
            return None                       # 此刻就够得到：交给直连能力，别绕
        if (not chunkphys.platforms() and not getattr(pet, "poles", ())
                and not getattr(pet, "shelters", ())):
            return None                       # 世界只有一块地板：没有别的面可去

        # 缓存必须含**起点 x**：同一几何下从不同位置问同一目标，路线并不一样。
        ck = (getattr(pet, "geometry_version", 0), getattr(pet, "world_version", 0),
              round(hy, 1), round(body.chunk1.x, 1), round(gx, 1), round(gy, 1))
        if ck != self._cache_key:
            self._cache = {}
            self._cache_key = ck
        hit = self._cache.get("r")
        if hit is not None:
            return hit                      # 同一几何同一起点同一目标只解一次

        start = SurfaceNode("floor", hy, hlo, hhi, here=True,
                            anchor=body.chunk1.x, sid="here")
        # 图缓存：只有「平台 / 杆 / 站在哪块面」变了才重建（猫移动不算）
        gkey = (getattr(pet, "geometry_version", 0), getattr(pet, "world_version", 0),
                stats, round(hy, 1), round(hlo, 1), round(hhi, 1))
        if gkey != self._gkey:
            self._graph = None
            self._gkey = gkey
        if self._graph is None:
            self._graph = SurfaceGraph.build(pet, start)
        graph = self._graph
        graph.start_at(body.chunk1.x)
        got = graph.route_to((gx, gy), stats, self._pers())
        out = None
        if got is not None:
            legs, t, e = got
            # 真实起点到「起始锚点」那一小段走路（锚点是固定的，误差 ≤ 半个锚点间距）
            walk0 = (abs(body.chunk1.x - graph.nodes[graph.start].anchor)
                     / tuning.PLAN_WALK_SPEED)
            t += walk0 * OPTIMISM
            e += walk0 * tuning.PLAN_EN_RATE_LIGHT
            if legs[0].kind not in ("finish",) and len(legs) >= 2:
                out = RoutePlan(goal, legs, t, e)
        self._cache["r"] = out
        return out

    def make_controller(self, plan):
        """按**当前 leg** 建既有控制器；落地后由 RouteExecutor 重新规划接下一段。"""
        leg = plan.leg()
        if leg is None or leg.kind == "finish":
            return None
        if leg.kind == "walk":
            return WalkReach(self.pet).make_controller(leg.goal())
        if leg.kind == "climb_pole":
            return PoleJumpReach(self.pet).make_controller(leg.goal())
        if leg.kind == "pole_beam":
            return PoleJumpReach(self.pet).make_controller(leg.goal())
        return _hop_controller(self.pet, leg)


class RouteExecutor:
    """多段路线执行器：跑当前 leg → 落地后重新规划 → 直到原目标被满足。

    与 PlanExecutor 的关系：直连能力给不出方案时，PlanExecutor 会把「route」当
    一个候选，控制器就是本类。本类在「没有多段路可走 / 只剩最后一伸」时转交给
    PlanExecutor（allow_route=False，防递归），于是原目标始终是同一个。
    """

    MAX_REPLANS = 8

    def __init__(self, pet, planner, goal, mode=MODE_TOUCH):
        self.pet = pet
        self.planner = planner
        self.goal = goal
        self.mode = mode
        self.plan = planner.surface_route(goal)
        self._ctrl = None
        self._direct = None
        self._replans = 0
        self._cancelled = False

    def update(self):
        if self._cancelled:
            return GIVEUP
        if not self.goal.valid():
            return GIVEUP
        body = self.pet.body
        if (getattr(body, "swimming", False) or getattr(body, "zerog", False)
                or getattr(body, "on_pole", False)):
            return GIVEUP
        leg = self.plan.leg() if self.plan is not None else None
        if leg is None or leg.kind == "finish":
            return self._direct_tick()
        if self._ctrl is None:
            self._ctrl = self._build(leg)
            if self._ctrl is None:
                self.plan = None
                return self._direct_tick()
        status = self._ctrl.update()
        if status == RUNNING:
            return RUNNING
        ctrl, self._ctrl = self._ctrl, None
        if hasattr(ctrl, "cancel"):
            ctrl.cancel()
        # DONE（落地）或 GIVEUP（这一段没走通）：都重新规划，接着朝原目辵走
        return self._replan()

    def _direct_tick(self):
        if self._direct is None:
            from .executor import PlanExecutor
            self._direct = PlanExecutor(self.pet, self.planner, self.goal,
                                        mode=self.mode, allow_route=False)
        st = self._direct.update()
        if st == HOLDING:
            return HOLD
        if st == GIVEUP:
            self._cancelled = True
            return GIVEUP
        return RUNNING

    def _replan(self):
        self._replans += 1
        if self._replans > self.MAX_REPLANS:
            self._cancelled = True
            return GIVEUP
        self.plan = self.planner.surface_route(self.goal)
        leg = self.plan.leg() if self.plan is not None else None
        if leg is None or leg.kind == "finish":
            return self._direct_tick()
        return RUNNING

    def _build(self, leg):
        if leg.kind == "walk":
            return WalkReach(self.pet).make_controller(leg.goal())
        if leg.kind == "climb_pole":
            return PoleJumpReach(self.pet).make_controller(leg.goal())
        if leg.kind == "pole_beam":
            return PoleJumpReach(self.pet).make_controller(leg.goal())
        return _hop_controller(self.pet, leg)

    def cancel(self):
        self._cancelled = True
        if self._ctrl is not None and hasattr(self._ctrl, "cancel"):
            self._ctrl.cancel()
        self._ctrl = None
        if self._direct is not None:
            self._direct.cancel()