# -*- coding: utf-8 -*-
"""表面图寻路：Goal → SurfaceGraph → Route → 第一条边的控制器。

旧版只有「地板 → 一块窗口顶边 → 目标」这条定长两段路，于是「先爬杆、再跳平台、
再够到目标」这类目标永远没人去拿 —— 不是参数问题，是导航拓扑没成形。
原版是「房间 tile 图 + A*」（Room.CreateTileGraph / PathFinder）；桌宠没有 tile 图，
但有等价的东西：地板段、窗口顶边（单向平台）、竖杆顶、横杆面，都是可站立的支撑面。

现在把它们放进一张真图：

    Node = 支撑面（floor / deck(窗口顶边) / pole_tip / pole_h(横杆面)）
    Edge = 一次位移，带类型与代价：
           walk        同一面上走过去（含小缝隙）
           jump        跳到更高的支撑面（轨迹族实测：jump/jumpfall/drop/flip）
           drop        落到更低的支撑面
           climb_pole  沿竖杆爬到杆顶
           pole_beam   杆间跳跃（beam jump）
           finish      从该面伸手 / 起跳弧够到目标点
    每条边带：耗时 / 体力 / 风险 / 是否落地 / 终点姿态 / 起终支撑面。
    代价 = route.edge 的六轴模型（时间 / 体力 / 风险 / 噪音 / 精度 / 后摇）× 性格，
    与单能力候选（WalkReach / JumpReach / …）共用同一套打分，不会各算各的。

寻路：Dijkstra（节点数是个位数，无需启发式），代价不可行（≥∞）直接剪掉。
执行：make_controller(route) 按**第一条边**建既有控制器（HopReach / PoleJumpReach），
落地后执行器重新规划 —— 此时「从这块面直接够」已经是第一段，于是自动接上第二段，
多段路线自然衔接，不需要额外的「路线记忆」。
"""
from __future__ import annotations

import math

from ..behavior import tuning
from ..core import chunkphys
from ..core.units import clampf
from .ability import walk_band
from .backflip_reach import takeoff_c0_h
from .goal import point_goal
from .hop_reach import HopReach, surface_under
from .jump_arc import get_arc, sweep_hit
from .pole_hop import land_sweep
from .pole_reach import PoleJumpReach
from .route import landing_safe

OPTIMISM = 1.30          # 多段路线的代价保守系数（宁可低估直连、不高估两段）
DECK_SAMPLES = 4         # 每块平台上试几个落点
HAND_UP = 12.0           # 站在平台上时手离脚面的高度（手在身侧偏下）
JUMP_X_TRIES = 3         # 平台上起跳点候选个数
WALK_Y_EPS = 6.0         # 同一块面：纵向容差（像素）
STEP_X = 14.0            # 走过去能跨过的横向缝隙上限
POLE_TIP_PAD = 10.0      # 杆顶可站立的横向范围
POLE_CLIMB_SPEED = 0.55  # 爬杆速度（px/tick，整条腿留给执行器）
BEAM_PENALTY = 1.25      # 杆上位移的保守系数（比走地面更容易失败）
DROP_MAX = 260.0         # 超过这个高度就不指望「正好落在那张面上」
INF = float("inf")


def _reach_from_surface(stats, y0, lo, hi, start_x, gx, gy):
    """站在支撑面 y0（可走区间 [lo,hi]）上能不能够到 (gx,gy)：走+伸手 / 起跳弧。

    返回 (耗时, 体力)；够不到 None。纯几何（不读实时 body），所以可测试、
    也可以拿去问「我落在那块面上以后够不够得到」。
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
    # ② 平台上起跳（士狼跳那套弧线族）：起跳点取目标附近几档
    launch_y = y0 - takeoff_c0_h(stats)
    xs = []
    for k in (0.0, -1.0, 1.0):
        x = clampf(wx + k * tuning.PLAN_WALK_X_PAD, lo, hi)
        if x not in xs:
            xs.append(x)
    xs = xs[:JUMP_X_TRIES]
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
    """一张可站立的支撑面。"""

    __slots__ = ("kind", "y", "lo", "hi", "pole", "here")

    def __init__(self, kind, y, lo, hi, pole=None, here=False):
        self.kind = kind          # floor / deck / pole_tip / pole_h
        self.y = float(y)
        self.lo = float(min(lo, hi))
        self.hi = float(max(lo, hi))
        self.pole = pole
        self.here = here          # 猫此刻站的就是这张面

    @property
    def width(self):
        return self.hi - self.lo

    def clamp(self, x):
        return clampf(x, self.lo, self.hi)

    def near(self, x, pad=0.0):
        return self.lo - pad <= x <= self.hi + pad

    def key(self):
        return (self.kind, round(self.y, 1), round(self.lo, 1), round(self.hi, 1))

    def __repr__(self):
        return "<%s y=%.0f [%.0f..%.0f]>" % (self.kind, self.y, self.lo, self.hi)


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
    """支撑面图：节点 + 有向边。懒构建，按几何版本缓存。"""

    def __init__(self):
        self.nodes = []
        self.adj = {}             # index → [SurfaceEdge]
        self.start = None

    def add_node(self, node):
        self.nodes.append(node)
        self.adj[len(self.nodes) - 1] = []
        return len(self.nodes) - 1

    def add_edge(self, i, edge):
        self.adj[i].append(edge)

    def idx(self, node):
        return self.nodes.index(node)

    # ── 构建 ──
    @classmethod
    def build(cls, pet, start_node):
        g = cls()
        g.start = g.add_node(start_node)
        WL = pet._WL

        for (x0, y0, x1) in chunkphys.platforms():
            lo, hi = max(min(x0, x1), 0.0), min(max(x0, x1), WL)
            if hi - lo < 2.0:
                continue
            g.add_node(SurfaceNode("deck", y0, lo, hi))

        for p in getattr(pet, "poles", ()):
            if getattr(p, "virtual", False):
                continue                    # 光标虚杆不进表面图（它自己一套）
            kind = getattr(p, "kind", None)
            if kind == "vertical":
                top = min(p.ay, p.by)
                if top <= 0.0:
                    continue
                g.add_node(SurfaceNode("pole_tip", top, p.bx - POLE_TIP_PAD,
                                       p.bx + POLE_TIP_PAD, pole=p))
            else:
                lo, hi = max(min(p.ax, p.bx), 0.0), min(max(p.ax, p.bx), WL)
                if hi - lo < 2.0:
                    continue
                g.add_node(SurfaceNode("pole_h", p.ay, lo, hi, pole=p))

        g._link_walks(pet)
        g._link_jumps(pet)
        g._link_poles(pet)
        return g

    def _link_walks(self, pet):
        """同一高度、够得着就直连（走 / 跨缝隙 / 上横杆面）。"""
        flat = ("floor", "deck")
        for i, a in enumerate(self.nodes):
            if a.kind not in flat:
                continue
            for j, b in enumerate(self.nodes):
                if b.kind not in flat or i == j or abs(a.y - b.y) > WALK_Y_EPS:
                    continue
                if a.hi < b.lo or b.hi < a.lo:
                    continue                  # 有缝就是洞：走过去会掉下去，不走这条
                gap = 0.0
                x0 = a.clamp((a.lo + a.hi) * 0.5)
                x1 = b.clamp(x0)
                d = abs(x1 - x0) + gap
                t = d / tuning.PLAN_WALK_SPEED + tuning.PLAN_STARTUP_TICKS
                self.add_edge(i, SurfaceEdge("walk", a, b, t, t * tuning.PLAN_EN_RATE_LIGHT,
                                             x1, "stand"))

    def _link_jumps(self, pet):
        """任一面 → 更高的面（或更低的面）：交给实测轨迹族 land_sweep。"""
        stats = pet.cat.stats
        off = takeoff_c0_h(stats)
        for i, a in enumerate(self.nodes):
            if a.kind not in ("floor", "deck"):
                continue                  # 从杆上出发另有杆间跳
            launch_y = a.y - off
            for j, b in enumerate(self.nodes):
                if i == j or b.kind not in ("floor", "deck"):
                    continue
                dy = a.y - b.y
                if dy < -2.0:
                    continue                  # b 比 a 高：只有落下去，见下
                want = b.clamp((b.lo + b.hi) * 0.5)
                launches = self._launches(a, want, launch_y)
                if not launches:
                    continue
                if dy <= 2.0:
                    continue                  # 同高：走路那条边已经在管
                r = land_sweep(stats, [(b.lo, b.y, b.hi)], launches,
                               want=(want, b.y), land_off=off)
                if r is None:
                    continue
                kind, hold, md, land_x, _ly, ticks, launch_x = r
                if not landing_safe(land_x, b.lo, b.hi):
                    continue                  # 落点贴着平台边：这只猫不愿意赌
                t = (abs(launch_x - a.clamp(launch_x)) / tuning.PLAN_WALK_SPEED
                     + ticks + tuning.PLAN_STARTUP_TICKS)
                e = t * tuning.PLAN_EN_RATE_LIGHT + ticks * tuning.PLAN_EN_RATE_VIGOROUS
                risk = 0.15 if kind == "flip" else 0.05
                self.add_edge(i, SurfaceEdge("jump", a, b, t, e, land_x, "crouch",
                                             plan=r, risk=risk))
            # 落到更低的面：自由落体（原版 drop）
        # 落到更低的面：自由落体。源必须比目标高（y 越大越低），否则这不是「落」。
        for i, a in enumerate(self.nodes):
            if a.kind not in ("floor", "deck"):
                continue
            for j, b in enumerate(self.nodes):
                if i == j or b.kind not in ("floor", "deck"):
                    continue
                dy = b.y - a.y                # >0：目标更低，可以落下去
                if dy <= 2.0 or dy > DROP_MAX:
                    continue                  # 同高走走路；太高落不到点上
                lx = b.clamp((a.lo + a.hi) * 0.5)
                dx = lx - a.clamp(lx)
                fall = math.sqrt(2.0 * dy / chunkphys.GRAVITY)
                t = (abs(dx) / tuning.PLAN_WALK_SPEED + fall
                     + tuning.PLAN_STARTUP_TICKS)
                self.add_edge(i, SurfaceEdge("drop", a, b, t * BEAM_PENALTY,
                                             t * tuning.PLAN_EN_RATE_LIGHT, lx, "crouch"))

    def _link_poles(self, pet):
        """沿竖杆爬上杆顶 / 杆间 beam jump。"""
        for i, a in enumerate(self.nodes):
            if a.kind not in ("floor", "deck"):
                continue                  # 杆上 → 杆：走 beam jump（pole_hop）
            for j, b in enumerate(self.nodes):
                if i == j or b.kind != "pole_tip" or b.y >= a.y - 2.0:
                    continue
                pole = b.pole
                if pole is None:
                    continue
                lo, hi = min(pole.ay, pole.by), max(pole.ay, pole.by)
                if not (lo - tuning.POLE_AIRGRAB_PAD <= a.y <= hi + tuning.POLE_AIRGRAB_PAD):
                    continue
                if abs(pole.bx - a.clamp(pole.bx)) > tuning.POLE_TRANSPORT_NEAR:
                    continue
                rise = a.y - b.y
                t = (abs(a.clamp(pole.bx) - a.clamp((a.lo + a.hi) * 0.5))
                     / tuning.PLAN_WALK_SPEED
                     + rise / POLE_CLIMB_SPEED + tuning.PLAN_STARTUP_TICKS)
                self.add_edge(i, SurfaceEdge("climb_pole", a, b, t * BEAM_PENALTY,
                                             t * tuning.PLAN_EN_RATE_VIGOROUS,
                                             pole.bx, "tip"))

    @staticmethod
    def _launches(a, want, launch_y):
        xs = []
        for k in (-2, -1, 0, 1, 2):
            x = a.clamp(want + k * 24.0)
            if x not in xs:
                xs.append(x)
        return [(x, launch_y) for x in xs[:JUMP_X_TRIES + 2]]

    # ── 寻路 ──
    def route_to(self, goal_point, stats):
        """Dijkstra：起面 → 目标点。返回 (legs, time, energy)；到不了 None。"""
        gx, gy = goal_point
        best = {self.start: (0.0, 0.0, [])}
        seen = set()
        while True:
            cur = None
            for idx, (t, _e, _p) in best.items():
                if idx in seen:
                    continue
                if cur is None or t < best[cur][0]:
                    cur = idx
            if cur is None:
                return None
            seen.add(cur)
            t0, e0, path = best[cur]
            node = self.nodes[cur]
            # 走到这条边上再伸手 / 起跳够目标
            fin = _reach_from_surface(stats, node.y, node.lo, node.hi,
                                      node.clamp(gx), gx, gy)
            if fin is not None:
                tt = (t0 + fin[0]) * OPTIMISM
                ee = (e0 + fin[1]) * OPTIMISM
                legs = path + [SurfaceEdge("finish", node, None, fin[0], fin[1],
                                           node.clamp(gx), "reach")]
                return (legs, tt, ee)
            for e in self.adj[cur]:
                if e.dst is None:
                    continue
                j = self.idx(e.dst)
                nt = t0 + e.time * (1.0 + e.risk)
                ne = e0 + e.energy
                old = best.get(j)
                if old is None or nt < old[0] - 1e-9:
                    best[j] = (nt, ne, path + [e])
        return None


class SurfaceHop:
    """一条表面图路线：可以只当「第一段」用（兼容旧调用），也带完整 legs。"""

    __slots__ = ("deck", "y", "land_x", "time", "energy", "goal", "legs")

    def __init__(self, edge, legs, time, energy):
        self.deck = (edge.dst.lo, edge.dst.y, edge.dst.hi) if edge.dst is not None else None
        self.y = float(edge.land_x if edge.dst is None else edge.dst.y)
        self.land_x = float(edge.land_x)
        self.time = float(time)
        self.energy = float(energy)
        self.goal = point_goal(edge.land_x, self.y, contact="travel")
        self.legs = list(legs)


class SurfaceRoute:
    """表面图寻路：Goal → SurfaceGraph → 最优路线。"""

    key = "route"

    def __init__(self, pet):
        self.pet = pet
        self._cache = {}
        self._cache_key = None

    # ── 当前支撑面 ──
    def _here(self):
        """猫此刻的支撑面 (y, lo, hi)。"""
        pet = self.pet
        y = pet.stand_h()
        lo, hi = walk_band(pet)
        s = surface_under(pet.body.chunk1.x, y)
        if s is not None:                     # 站在窗口顶边上：只能在这块面的范围内走
            lo = max(lo, min(s[1], s[2]))
            hi = min(hi, max(s[1], s[2]))
        return (y, lo, hi)

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
        if not chunkphys.platforms() and not getattr(pet, "poles", ()):
            return None                       # 世界只有一块地板：没有别的面可去

        ck = (getattr(pet, "geometry_version", 0), getattr(pet, "world_version", 0),
              round(hy, 1), round(gx, 1), round(gy, 1))
        if ck != self._cache_key:
            self._cache = {}
            self._cache_key = ck
        hit = self._cache.get("r")
        if hit is not None:
            return hit                      # 同一几何同一目标只解一次

        start = SurfaceNode("floor", hy, hlo, hhi, here=True)
        graph = SurfaceGraph.build(pet, start)
        got = graph.route_to((gx, gy), stats)
        out = None
        if got is not None:
            legs, t, e = got
            first = legs[0]
            if first.kind in ("jump", "drop", "climb_pole") and len(legs) >= 2:
                out = SurfaceHop(first, legs, t, e)
        self._cache["r"] = out
        return out

    def make_controller(self, hop):
        """按第一条边的类型建既有控制器；落地后执行器重新规划接下一段。"""
        first = hop.legs[0]
        if first.kind == "climb_pole":
            return PoleJumpReach(self.pet).make_controller(hop.goal)
        return HopReach(self.pet).make_controller(hop.goal)
