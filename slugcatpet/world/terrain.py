# -*- coding: utf-8 -*-
"""所有生物共用的地形查询：地面 / 平台顶 / 竖杆 / 横杆 / 背景墙 / 窗口竖边。

反编译口径：原版一张地图的地形就是 AImap / AItile —— Floor / Wall / Ceiling /
Climb（verticalBeam 竖杆、horizontalBeam 横杆）都在同一张连通图里；
「这条路这只生物能不能走」由 CreatureTemplate.AccessibilityResistance /
ConnectionResistance（AImap.cs:59-77）决定，蜥蜴读的是 LizardPather 给出的
MovementConnection，而不是动作层临时去找一根竖线。

**本文件现在是 planning/navgeom.py + planning/navgraph.py 之上的适配层**：
几何（哪些面、哪些竖线、哪些实心体）只由 NavGeometry 说一次，边（走 / 跳 /
掉 / 爬 / 换杆）统一用 NavigationEdge，寻路统一用 NavGraph 的 heapq A*。
这一层只回答三个问题：**我周围有哪些地形 / 这块地形怎么上去 / 我的能力表
允不允许用**。真正的位移仍归各自的物理（蜥蜴走 _step_wall，蛞蝓猫走
PoleClimb / HPole）。
"""
from __future__ import annotations

import bisect
import math

from ..planning import navgeom
from ..planning.navgeom import (CLIMB_EDGE, CLIMB_POLE, CLIMB_WALL, FLOOR,
                                HPOLE, PLATFORM, SHELTER_FLOOR, SHELTER_ROOF,
                                SHELTER_WALL, VPOLE, WALL, WINDOW_EDGE,
                                NavGeometry)
from ..planning.navgraph import (ATTACK, CLIMB_EDGE as E_CLIMB_EDGE,
                                 CLIMB_POLE as E_CLIMB_POLE,
                                 CLIMB_WALL as E_CLIMB_WALL, DROP, FINISH,
                                 JUMP, POLE_HOP, STEP, WALK as E_WALK,
                                 Capabilities, NavGraph, NavigationEdge,
                                 ReachResult, WALL_HOP, anchor_key, edge_cost)

FLOOR_TOL = 18.0        # 「这块地形的落脚点在我这一层」的容差
ATTACH_TOL = 30.0       # 上墙点离我多近算「走过去就能抓」
GRIP_R = 30.0           # 直接抓线的半径
REACH_PENALTY = 120.0   # 线太远：算上绕路代价
CLIMB_REACH_DEFAULT = 220.0
FLOOR_SNAP = 2.0        # 面比身体高这么点就不算「脚下的地」
SINK_TOL = 40.0         # 身体已经陷进面里这么多，仍然算踩在这块面上

# ── 移动图（MovementConnection）的几何常量 ──
STEP_X = 14.0           # 两块面之间能直接跨过的横向缝隙（与 SurfaceGraph 同一口径）
STEP_DY = 24.0          # 走过去的台阶高差上限
ANCHOR_STEP = 70.0      # 面上每隔这么远放一个导航锚点
ATTACH_DY = 34.0        # 面 ↔ 竖线端点 的纵向容差（走过去抓线）
ATTACH_COST = 6.0       # 上/下线的固定代价（tick）
CLIMB_COST = 2.0        # 爬一整条竖线的起步代价
DROP_MIN = 30.0         # 低于这个高度不算「跳下」，只是台阶
DROP_DX = 70.0          # 跳下时的横向容差
HOP_DX = 90.0           # 竖线之间挪过去的横向上限
HOP_DY = 70.0           # 竖线之间挪过去的纵向上限
ABOVE_PENALTY = 240.0   # 起点选锚点时：面在身体上方这么远的惩罚（不能往上瞬移）
CLIMB_RISK = 0.06       # 爬一整条竖线的失败倾向（保守，巡逻够用）
HOP_RISK = 0.30         # 杆间 / 墙间跳跃更容易失手
JUMP_RISK = 0.10
DROP_RISK = 0.04

WALK, CLIMB, JUMP, DROP, HOP = "walk", "climb", "jump", "drop", "hop"

# ── 路线类型（文档 §4：returnable 不该一刀切）──
ROUTE_SAFE = "safe"                # 去得了 + 回得来 + 没有高危边
ROUTE_RETURNABLE = "returnable"    # 去得了 + 回得来
ROUTE_ONE_WAY = "one_way"          # 只要去得了（追即将掉落的猫 / 单向猎物）
ROUTE_RISKY = "risky"              # 允许高危边（红蜥跳危险位置）
ROUTE_DEAD_END = "dead_end"        # 允许走进死角（追目标进死路）

_EDGE_RISK_LIMIT = 0.25            # SAFE 路线允许的单边风险上限
SNAP_FAR = 90.0                 # 目标离最近地形节点超过这么远：它此刻不在任何面上


class Caps(Capabilities):
    """一只生物的地形能力表（原版 CreatureTemplate / LizardBreedParams）。

    直接复用统一能力表 Capabilities；这里补上旧调用点的关键字名，
    让蜥蜴侧的构造参数一个都不用改。
    """

    __slots__ = ()

    def __init__(self, walk=True, jump=True, wall_climb=False, pole_climb=False,
                 wall_jump=False, climb_reach=CLIMB_REACH_DEFAULT,
                 hpole_walk=True, walk_speed=4.1, climb_speed=2.6,
                 jump_up=60.0, jump_dx=95.0, drop_max=420.0, drop_dx=DROP_DX,
                 hop_dx=HOP_DX, climb_edge=None, can_enter_shelter=False,
                 pole_hop=None, wall_hop=None):
        super().__init__(
            walk=walk, step=True, jump=jump, drop=True,
            climb_pole=pole_climb, climb_wall=wall_climb, climb_edge=climb_edge,
            wall_jump=wall_jump, pole_hop=pole_climb if pole_hop is None else pole_hop,
            wall_hop=wall_climb if wall_hop is None else wall_hop,
            door=True, swim=False, hpole_walk=hpole_walk,
            can_enter_shelter=can_enter_shelter, walk_speed=walk_speed,
            climb_speed=climb_speed, jump_up=jump_up, jump_dx=jump_dx,
            drop_max=drop_max, drop_dx=drop_dx, hop_dx=hop_dx,
            climb_reach=climb_reach)

    # 旧调用点 / 旧测试读的是 wall_climb / pole_climb 这两个名字
    @property
    def wall_climb(self):
        return self.climb_wall

    @property
    def pole_climb(self):
        return self.climb_pole

    def __repr__(self):
        return "Caps(walk=%s jump=%s wall=%s pole=%s)" % (
            self.walk, self.jump, self.climb_wall, self.climb_pole)


class Leg:
    """一段路线（RoutePlan 的一条腿）：动作层只负责执行这一段。"""

    __slots__ = ("mode", "x", "y", "tx", "ty", "top", "bot", "up", "risk")

    def __init__(self, mode, x, y, tx=None, ty=None, top=None, bot=None, up=0,
                 risk=0.0):
        self.mode = mode          # walk / climb_wall / climb_pole / climb_edge / jump / drop / hop
        self.x, self.y = float(x), float(y)   # 这一段先去哪（上墙点 / 起跳点 / 落点）
        self.tx, self.ty = tx, ty             # 段末落点（jump / drop / hop 用）
        self.top, self.bot = top, bot         # 竖线上下端（climb 用）
        self.up = int(up)                      # climb 方向：+1 上 / -1 下
        self.risk = float(risk)

    def __repr__(self):
        return "Leg(%s, %.0f,%.0f)" % (self.mode, self.x, self.y)


class NavNode:
    """导航节点 = 地形（一块面 / 一条竖线）+ 锚点 x。"""

    __slots__ = ("nid", "x", "y", "line", "top", "bot", "stand", "sid")

    def __init__(self, nid, x, y, stand=True, line=None, top=None, bot=None,
                 sid=None):
        self.nid = nid
        self.x, self.y = float(x), float(y)
        self.stand = bool(stand)   # 能不能站在这（地板 / 横杆面 / 竖线两端）
        self.line = line           # None / "pole" / "wall" / "edge"：这条竖线属于哪一族
        self.top, self.bot = top, bot
        self.sid = sid

    def __repr__(self):
        return "Nav#%d(%s, %.0f,%.0f)" % (self.nid, self.line or "floor",
                                          self.x, self.y)


class TerrainRoute:
    """一次寻路结果：多段 legs + 可达性 / 可返回性。"""

    __slots__ = ("legs", "reachable", "returnable", "cost", "kind", "risk")

    def __init__(self, legs, reachable, returnable, cost, kind=ROUTE_RETURNABLE,
                 risk=0.0):
        self.legs = tuple(legs)
        self.reachable = bool(reachable)
        self.returnable = bool(returnable)
        self.cost = float(cost)
        self.kind = kind
        self.risk = float(risk)

    def __repr__(self):
        return "TerrainRoute(%d legs, cost=%.1f, back=%s, %s)" % (
            len(self.legs), self.cost, self.returnable, self.kind)


def _attach_key(attach):
    """插桩点量化成 24px 桶，再进图缓存键（文档 §20）。

    「按需插桩」只在基础图给不出答案时才发生，量化只是别让同一只蜥蜴每挪 1px
    就重建一张图。
    """
    if not attach:
        return ()
    return tuple(sorted({(int(round(ax / 24.0)), int(round(ay / 24.0)))
                         for (ax, ay) in attach}))


def _anchors(lo, hi):
    """一块面 [lo, hi] 上的导航锚点（含两端，等距）。"""
    lo, hi = float(lo), float(hi)
    if hi - lo <= 1.0:
        return ()
    n = max(1, int((hi - lo) / ANCHOR_STEP) + 1)
    step = (hi - lo) / n
    return tuple(lo + step * i for i in range(n + 1))


_CLIMB_EDGE_TYPE = {"pole": E_CLIMB_POLE, "wall": E_CLIMB_WALL,
                    "edge": E_CLIMB_EDGE}
_CLIMB_FROM_TYPE = {E_CLIMB_POLE: "climb_pole", E_CLIMB_WALL: "climb_wall",
                    E_CLIMB_EDGE: "climb_edge"}


class TerrainGraph(NavGraph):
    """一次世界快照 + 一张能力表编译出来的 MovementConnection 图（可缓存）。

    寻路一律走 NavGraph 的 heapq Dijkstra / A*（文档 §3：旧的 O(V^2) 双重循环
    在节点多时是每只蜥蜴每帧的最大开销之一）。
    """

    __slots__ = ()

    def nearest(self, x, y, stand_only=True, allow_above=True):
        best, bd = None, None
        for n in self.nodes:
            if stand_only and not n.stand:
                continue
            d = math.hypot(n.x - x, n.y - y)
            if not allow_above and n.y < y - 20.0:
                d += ABOVE_PENALTY
            if bd is None or d < bd:
                best, bd = n.nid, d
        return best

    def path_edges(self, src, dst, max_speed=20.0, avoid=None):
        """目标明确时优先 A*（采样启发式可采纳：不超过最快连接的耗时下限）。

        ``avoid``（节点下标集合）是导航级黑名单：文档 §13 的 Navigation stuck
        要靠它断掉「同一条边反复被选中」的循环。
        """
        got = self.astar(src, dst, max_speed=max_speed, avoid=avoid)
        if got is None:
            got = self.path(src, dst, avoid=avoid)
        return got

    def legs(self, path):
        """把节点路径折成动作层能执行的 legs（同面连续的 walk 合并成一段）。"""
        out = []
        for e in path:
            a, b = self.nodes[e.src], self.nodes[e.dst]
            if e.type in _CLIMB_FROM_TYPE:
                extra = e.extra or (None, None, 0, a.x)
                out.append(Leg(_CLIMB_FROM_TYPE[e.type], extra[3], b.y,
                               top=extra[0], bot=extra[1], up=extra[2],
                               risk=e.risk))
            elif e.type in (JUMP, POLE_HOP, WALL_HOP):
                out.append(Leg("jump", a.x, a.y, tx=b.x, ty=b.y, risk=e.risk))
            elif e.type == DROP:
                out.append(Leg("drop", a.x, a.y, tx=b.x, ty=b.y, risk=e.risk))
            else:
                out.append(Leg("walk", b.x, b.y, risk=e.risk))
        return _merge_legs(out)

    # 兼容：旧调用点还会直接喊 _run
    def _run(self, src, avoid=None):
        NavGraph._run(self, src, avoid)


def _merge_legs(legs):
    """同一块面上的连续 walk 合并成一段（否则一路走过去会拆成十几段）。"""
    out = []
    for leg in legs:
        if (out and leg.mode == "walk" and out[-1].mode == "walk"
                and abs(out[-1].y - leg.y) < 2.0):
            out[-1].x = leg.x
            out[-1].y = leg.y
            out[-1].risk = max(out[-1].risk, leg.risk)
            continue
        out.append(leg)
    return tuple(out)


def _graph_cache(win):
    c = getattr(win, "_terrain_graphs", None)
    if c is None:
        c = {}
        try:
            win._terrain_graphs = c
        except Exception:
            return {}
    return c


class TerrainQuery:
    """一次世界快照上的地形查询。每 tick 建一次，全场生物共用同一份。

    几何来自 planning.navgeom.NavGeometry（与蛞蝓猫同一份），
    移动图来自 planning.navgraph.NavGraph。
    """

    __slots__ = ("win", "_geom")

    def __init__(self, win):
        self.win = win
        self._geom = None

    # ── 统一几何 ──
    @property
    def geom(self) -> NavGeometry:
        if self._geom is None:
            self._geom = navgeom.nav_geometry(self.win)
        return self._geom

    def nav_version(self) -> int:
        return self.geom.version

    # ── 原始地形（元组视图，历史调用方还在用）──
    def platforms(self):
        """窗口顶边（可站的平台）：(x0, y, x1)。"""
        from ..core import chunkphys
        return tuple(chunkphys.platforms() or ())

    def surfaces(self):
        return self.geom.surfaces

    def vpoles(self):
        """**真正的竖杆**：(x, top, bot)。

        窗口左右边缘**不再**混进这里（文档 §34/§35：它同时是碰撞体、可攀爬竖线、
        顶端可站面，语义和普通竖杆不同）。要窗口竖边请查 window_edges()。
        """
        return self.geom.vpoles()

    def window_edges(self):
        """本窗口左右竖边：(x, top, bot)。"""
        return tuple((s.x, s.top, s.bot) for s in self.geom.surfaces
                     if s.kind == WINDOW_EDGE)

    def hpoles(self):
        """横杆：(x0, y, x1) —— 杆面可以踩。"""
        return self.geom.hpoles()

    def walls(self):
        """竖直墙面：(x, top, bot)。庇护所墙条 + 背景墙。只有 WallClimber 能当楼梯。"""
        return self.geom.walls()

    def climb_surfaces(self, caps=None):
        """可攀爬的竖线：(x, top, bot, kind)，kind ∈ {"pole","wall","edge"}。

        横杆不在这里 —— 它不是竖线，是脚下的地形（见 walk_floors）。
        """
        return self.geom.climb_surfaces(caps)

    # ── 可站的面 ──
    def walk_floors(self, caps=None):
        """能站在上面的面：屏幕地板 + 窗口顶边 + 横杆杆面 + 庇护所地面/屋顶。

        caps.hpole_walk 为假（不会用杆的品种，如绿蜥）时不把横杆杆面当地面；
        caps.can_enter_shelter 为假（蜥蜴）时不把庇护所**屋里地面**当地面，
        但屋顶仍然可站。
        """
        return self.geom.walk_floors(caps)

    def support_contact(self, x, y, caps=None, default=None):
        return self.geom.support_contact(x, y, caps, default)

    def floor_under(self, x, y, caps=None):
        """x 处、y 之下最近的可站面（没有就退回屏幕地板）。"""
        return self.geom.floor_under(x, y, caps)

    def support(self, x, y, default, caps=None):
        """脚下的支撑面 y：屏幕地板 / 窗台 / 横杆杆面 / 庇护所屋顶里最近的一块。

        生物物理用它当「地面」，这样蜥蜴能站在别的窗口顶上和横杆上，而不是只认
        屏幕底边（原版 Floor tile 本来就不止一种）。
        """
        return self.geom.support_contact(x, y, caps, default).y

    # ── 视线（与蛞蝓猫共用同一份几何）──
    def los_blocked(self, x0, y0, x1, y1):
        return self.geom.los_blocked(x0, y0, x1, y1)

    # ── 单段地形提示（地形图给不出整条路线时的兜底）──
    def route_hint(self, x, y, tx, ty, caps):
        """够不着目标时先问地形：有没有一条「走 → 上墙 / 上杆 / 上窗边」的路线。

        返回 (mode, sx, top, bot, dir, reason)；没有可用地形就 None。mode ∈
        {"climb_wall", "climb_pole", "climb_edge"}，sx 是上墙点（线所在的 x），
        (top, bot) 是这条线的上下端，dir = +1 向上 / -1 向下。
        """
        if caps is None or ty >= y - FLOOR_TOL:
            return None                       # 目标不比我高：直冲 / 跳跃那套
        best = None
        for sx, top, bot, kind in self.climb_surfaces():
            if not caps.allows_climb(kind):
                continue                  # 这个品种用不了这一类竖线
            if top > ty + 12.0:
                continue                      # 线顶还够不着目标那一层
            on_line = top - 12.0 <= y <= bot + 12.0
            foot_here = (bot >= y - ATTACH_TOL) and (bot <= y + ATTACH_TOL)
            if not (on_line or foot_here):
                continue                      # 线底不在我这一层，也还没爬上去
            d = abs(x - sx)
            if d > caps.climb_reach:
                continue
            score = d + (0.0 if d <= GRIP_R else REACH_PENALTY)
            if best is None or score < best[0]:
                best = (score, sx, kind, top, bot)
        if best is None:
            return None
        return ("climb_" + best[2], best[1], best[3], best[4], 1,
                "terrain:%s" % best[2])

    # ── 移动图 ──
    def graph(self, caps, attach=()):
        """把这一帧的地形编译成 MovementConnection 图（按**导航版本** + 能力表缓存）。

        文档 §24：旧键用 world_version，新增生物 / 物品状态会让整张图重建。
        现在只依赖 navgeom 的导航版本（只在 platform / pole / wall / shelter 变化时 +1）。

        `attach` 是「按需插桩」的高度集合 [(line_x, y), ...]（文档 §20）：竖线只
        在 top / bot 有节点，所以「我挂在墙中间」「目标在杆中间」在图上没有落点。
        这里**不预先离散化所有高度**，只在真的需要的那一两个高度上给对应竖线补
        节点；没有 `attach` 时就是原来那张端点图（缓存键也不变）。
        """
        if caps is None:
            caps = Caps()
        wl = float(getattr(self.win, "_WL", 0.0) or 0.0)
        hl = float(getattr(self.win, "_HL", 0.0) or 0.0)
        key = (self.geom.version, int(wl), int(hl), caps.key(),
               _attach_key(attach))
        cache = _graph_cache(self.win)
        hit = cache.get(key)
        if hit is not None:
            return hit
        g = self._build_graph(caps, wl, hl, attach)
        if len(cache) > 8:
            cache.clear()
        cache[key] = g
        return g

    def attach_points(self, caps, x, y, tx, ty):
        """「按需插桩」要补的高度：我的当前高度 + 目标的当前高度（文档 §20）。

        参数化搜索的口径不是「把每条竖线按 ANCHOR_STEP 离散成很多层」，而是
        「只在需要时算 current vertical position → target vertical position」。
        所以这里只挑「离自己 / 目标够近、且高度落在竖线中段」的那几条竖线。
        """
        out, seen = [], set()
        for (px, py) in ((x, y), (tx, ty)):
            for s in self.geom.verticals(caps):
                if abs(s.x - px) > caps.climb_reach:
                    continue
                if py <= s.top + 8.0 or py >= s.bot - 8.0:
                    continue                     # 端点已经盖住这个高度
                key = (round(s.x, 1), round(py, 1))
                if key in seen:
                    continue
                seen.add(key)
                out.append((s.x, py))
        return tuple(out)

    def _graphs(self, caps, x, y, tx, ty):
        """候选移动图：先缓存的基础图，给不出答案时才用「按需插桩」的图兜底。"""
        base = self.graph(caps)
        yield base
        attach = self.attach_points(caps, x, y, tx, ty)
        if attach:
            yield self.graph(caps, attach=attach)

    def _build_graph(self, caps, wl, hl, attach=()):
        nodes = []
        adj = []

        def add_node(x, y, stand=True, line=None, top=None, bot=None, sid=None):
            nodes.append(NavNode(len(nodes), x, y, stand=stand, line=line,
                                 top=top, bot=bot, sid=sid))
            adj.append([])
            return len(nodes) - 1

        def link(a, b, type_, cost, extra=None, both=True, risk=0.0):
            if a == b:
                return
            adj[a].append(NavigationEdge(type_, a, b, cost, risk=risk, extra=extra,
                                         reversible=bool(both)))
            if both:
                adj[b].append(NavigationEdge(type_, b, a, cost, risk=risk,
                                             extra=extra, reversible=True))

        # ① 可站的面：屏幕地板 / 窗台 / 横杆杆面 / 庇护所地面与屋顶
        spans = []
        for s in self.geom.floors(caps):
            lo, hi = max(0.0, s.lo), min(wl, s.hi)
            if hi - lo > 1.0:
                spans.append((lo, s.y, hi, s))
        spans.sort(key=lambda t: (t[1], t[0]))
        span_anchors = []          # [ [(node_i, x), ...], ... ]
        for (lo, y, hi, s) in spans:
            anchors = _anchors(lo, hi) or (0.5 * (lo + hi),)
            row = [(add_node(ax, y, sid=s.sid), ax) for ax in anchors]
            span_anchors.append(row)
            for k in range(len(row) - 1):        # 同面相邻锚点：走过去
                (a, ax), (b, bx) = row[k], row[k + 1]
                d = abs(bx - ax)
                link(a, b, E_WALK, d / max(0.5, caps.walk_speed))
        # 面与面之间：x 范围挨着（缝隙 <= STEP_X）且高差 <= STEP_DY 就走过去。
        # 面已按 y 排序，内层一超标就 break（文档 §36 的「边候选空间筛选」）。
        for i in range(len(spans)):
            lo_a, y_a, hi_a, _sa = spans[i]
            for j in range(i + 1, len(spans)):
                lo_b, y_b, hi_b, _sb = spans[j]
                dy = y_b - y_a
                if dy > STEP_DY:
                    break
                gap = max(lo_a - hi_b, lo_b - hi_a)
                if gap > STEP_X:
                    continue
                best = None
                for (a, ax) in span_anchors[i]:
                    for (b, bx) in span_anchors[j]:
                        d = abs(ax - bx)
                        if best is None or d < best[0]:
                            best = (d, a, b)
                if best is not None:
                    link(best[1], best[2], E_WALK,
                         best[0] / max(0.5, caps.walk_speed))

        node_y = {}
        for row in span_anchors:
            for (n, _x) in row:
                node_y[n] = nodes[n].y

        # ② 竖线：竖杆 / 背景墙 / 窗口竖边 —— 底端 + 顶端两个节点
        vnodes = []        # [(node_i, x, y, usable)]
        vlines = []        # [(surface, nf, nh, can)]：②b 插桩要用
        vline_of = {}      # 节点 → (kind, x)：同一条竖线上的两点之间不建跳跃 / 跳下
        for s in self.geom.verticals(None):
            if s.bot - s.top < 8.0:
                continue
            kind = s.climb
            can = caps.allows_climb(kind)
            # 竖线不是地板：只有「能抓住这条竖线」的品种才把它当可站面
            # （原版竖杆 / 墙 tile 是 Climb / Wall accessibility，不是 Floor）。
            nf = add_node(s.x, s.bot, stand=bool(s.stand and can), line=kind,
                          top=s.top, bot=s.bot, sid=s.sid)
            nh = add_node(s.x, s.top, stand=bool(s.stand and can), line=kind,
                          top=s.top, bot=s.bot, sid=s.sid)
            vnodes.append((nf, s.x, s.bot, can))
            vnodes.append((nh, s.x, s.top, can))
            vlines.append((s, nf, nh, can))
            vline_of[nf] = vline_of[nh] = (kind, round(s.x, 1))
            if can:
                c = (s.bot - s.top) / max(0.5, caps.climb_speed) + CLIMB_COST
                et = _CLIMB_EDGE_TYPE[kind]
                link(nf, nh, et, c, (s.top, s.bot, 1, s.x), risk=CLIMB_RISK)
                link(nh, nf, et, c, (s.top, s.bot, -1, s.x), risk=CLIMB_RISK)

        # ②b 按需插桩（文档 §20）：竖线中间也要能进出。只在 `attach` 给的高度上
        #     补节点 —— 「我挂在墙中间想从这跳出去 / 另一根杆在这一层」于是有了
        #     落点；不预先离散化所有高度，也不改变没有 attach 时的端点图。
        placed = set()
        for (ax, ay) in attach:
            ay = float(ay)
            for (s, nf, nh, can) in vlines:
                if abs(s.x - ax) > caps.climb_reach:
                    continue
                if ay <= s.top + 8.0 or ay >= s.bot - 8.0:
                    continue                    # 端点已经盖住这个高度
                key = (round(s.x, 1), round(ay, 1))
                if key in placed:
                    continue
                placed.add(key)
                kind = s.climb
                nm = add_node(s.x, ay, stand=bool(s.stand and can), line=kind,
                              top=s.top, bot=s.bot, sid=s.sid)
                vnodes.append((nm, s.x, ay, can))
                vline_of[nm] = (kind, round(s.x, 1))
                if not can:
                    continue
                et = _CLIMB_EDGE_TYPE[kind]
                cu = (ay - s.top) / max(0.5, caps.climb_speed) + CLIMB_COST
                cd = (s.bot - ay) / max(0.5, caps.climb_speed) + CLIMB_COST
                # 插桩点把原线切成上 / 下两段：extra = (段顶, 段底, 方向, x)，
                # 这样动作层拿到的是「这一段爬到哪里为止」，而不是整条线。
                link(nh, nm, et, cu, (s.top, ay, -1, s.x), both=False,
                     risk=CLIMB_RISK)
                link(nm, nh, et, cu, (s.top, ay, 1, s.x), both=False,
                     risk=CLIMB_RISK)
                link(nm, nf, et, cd, (ay, s.bot, -1, s.x), both=False,
                     risk=CLIMB_RISK)
                link(nf, nm, et, cd, (ay, s.bot, 1, s.x), both=False,
                     risk=CLIMB_RISK)

        # ③ 面 ↔ 竖线端点：走过去就能抓（原版 Floor→Wall 那条连接）
        for (nv, vx, vy, vcan) in vnodes:
            if not vcan:
                continue          # 不会爬这条竖线的品种：走不到「杆上 / 墙上」去
            for row in span_anchors:
                for (na, ax) in row:
                    if abs(ax - vx) > caps.climb_reach:
                        continue
                    if abs(node_y[na] - vy) > ATTACH_DY:
                        continue
                    link(na, nv, E_WALK,
                         abs(ax - vx) / max(0.5, caps.walk_speed) + ATTACH_COST)

        # ④ 能站的节点集合（跳跃 / 跳下的两端）
        stand = []
        for row in span_anchors:
            stand.extend(row)
        stand.extend((n, x) for (n, x, _y, vcan) in vnodes if vcan)
        sy = dict(node_y)
        for (n, _x, _y, _c) in vnodes:
            sy[n] = nodes[n].y

        # 粗筛（原版 MovementConnection 也是按 tile 层找，不是全场两两比）：
        # 把能站的节点按 y 排好，跳跃 / 跳下只在自己的高度带里取候选。
        band = sorted(stand, key=lambda p: sy[p[0]])
        band_y = [sy[n] for (n, _x) in band]

        def _slice(lo, hi):
            return band[bisect.bisect_left(band_y, lo):
                        bisect.bisect_right(band_y, hi)]

        def _same_line(a, b) -> bool:
            """两个节点在同一条竖线上（同 kind 同 x）—— 它们之间只该有爬，没有跳。"""
            ka = vline_of.get(a)
            return ka is not None and ka == vline_of.get(b)

        # ⑤ 跳跃：往上够得着的锚点（原版 jump MovementConnection）
        if caps.jump:
            for (a, ax) in stand:
                ay = sy[a]
                for (b, bx) in _slice(ay - caps.jump_up, ay):
                    if a == b or _same_line(a, b):
                        continue
                    up = ay - sy[b]
                    if up <= 0.0 or up > caps.jump_up:
                        continue
                    d = abs(bx - ax)
                    if d > caps.jump_dx:
                        continue
                    link(a, b, JUMP, 1.0 + d / max(1.0, caps.jump_dx),
                         (None, None, 1, None), both=False, risk=JUMP_RISK)

        # ⑥ 跳下：往下的落差（走路掉下去，不需要能力）
        for (a, ax) in stand:
            ay = sy[a]
            for (b, bx) in _slice(ay + DROP_MIN, ay + caps.drop_max):
                if a == b or _same_line(a, b):
                    continue
                down = sy[b] - ay
                if down < DROP_MIN or down > caps.drop_max:
                    continue
                d = abs(bx - ax)
                if d > caps.drop_dx:
                    continue
                link(a, b, DROP, 0.6 + down / max(1.0, caps.drop_max),
                     (None, None, -1, None), both=False, risk=DROP_RISK)

        # ⑦ 竖线之间：杆↔杆 / 杆↔墙 / 墙↔窗边 的横向挪动（原版 beam 之间的小跳）
        # 按 x 排序后只扫横向窗口内的邻居（原来是无条件 N^2 全比）。
        if caps.pole_hop or caps.wall_hop or caps.wall_jump:
            vx_sorted = sorted(vnodes, key=lambda p: p[1])
            for i in range(len(vx_sorted)):
                a, ax, ay = vx_sorted[i][0], vx_sorted[i][1], vx_sorted[i][2]
                for j in range(i + 1, len(vx_sorted)):
                    b, bx, by = vx_sorted[j][0], vx_sorted[j][1], vx_sorted[j][2]
                    d = bx - ax
                    if d > caps.hop_dx:
                        break                     # 再往后只会更远
                    if d < 1.0 or abs(by - ay) > HOP_DY:
                        continue
                    if not (vx_sorted[i][3] and vx_sorted[j][3]):
                        continue          # 用不了的竖线不参与「挪过去」的连接
                    link(a, b, POLE_HOP, 1.2, (None, None, 1, None),
                         both=False, risk=HOP_RISK)
                    link(b, a, POLE_HOP, 1.2, (None, None, -1, None),
                         both=False, risk=HOP_RISK)

        return TerrainGraph(nodes, adj, version=self.geom.version)

    # ── 寻路 ──
    def route(self, x, y, tx, ty, caps, must_return=True, stand_only=True,
              kind=None, avoid=None):
        """多段地形路线。

        路线类型（文档 §4）：SAFE / RETURNABLE 要求「能去也能回」；ONE_WAY /
        RISKY / DEAD_END 只要求去得了。追即将掉落的猫、红蜥跳危险位置、
        追进死角的猎物本来就可以单向 —— 旧实现一律 must_return，于是这些情况
        全被判无路线，上层只能 fallback 成 direct 直冲，最后撞墙 / 原地跳。

        ``kind`` 还可以给**一串**类型（文档 §5：行为先指定路线哲学）：
        从严到松依次尝试，取第一个成立的，于是「我要 SAFE，但只有 RETURN 可用」
        会降级成 RETURN 而不是直接判无路线。

        ``avoid`` 是 StuckDetector 的导航黑名单（量化锚点键的集合）：里面的
        落点不进图，寻路自然绕开。
        """
        if kind is None:
            kind = ROUTE_RETURNABLE if must_return else ROUTE_ONE_WAY
        kinds = (kind,) if isinstance(kind, str) else tuple(kind)
        speed = max(caps.walk_speed, caps.climb_speed, caps.jump_dx,
                    caps.hop_dx, 40.0)
        for g in self._graphs(caps, x, y, tx, ty):
            if not g.nodes:
                continue
            src = g.nearest(x, y, stand_only=stand_only, allow_above=False)
            dst = g.nearest(tx, ty, stand_only=stand_only)
            if src is None or dst is None:
                continue
            ban = self._avoid_ids(g, avoid, src)
            path = g.path_edges(src, dst, max_speed=speed, avoid=ban)
            if not path:
                continue
            back = g.can_return(src, dst)
            risk = max((e.risk for e in path), default=0.0)
            legs = g.legs(path)
            if not legs:
                continue
            cost = sum(e.time for e in path)
            for k in kinds:
                if k in (ROUTE_SAFE, ROUTE_RETURNABLE) and not back:
                    continue
                if k == ROUTE_SAFE and risk > _EDGE_RISK_LIMIT:
                    continue
                return TerrainRoute(legs, True, back, cost, kind=k, risk=risk)
        return None

    @staticmethod
    def _avoid_ids(g, avoid, src):
        """黑名单桶键 → 这张图的节点下标（源点永远不封，否则自己出不去）。"""
        if not avoid:
            return None
        ban = set()
        for n in g.nodes:
            if n.nid == src:
                continue
            if anchor_key(n.x, n.y) in avoid:
                ban.add(n.nid)
        return ban or None

    def reach_result(self, x, y, tx, ty, caps):
        """可达性的四种结论（文档 §5）。

        旧实现里「图里没路线」和「目标根本到不了」是同一件事，都 fallback 成
        direct 直冲 —— 于是蜥蜴会一直朝穿不过去的墙走。现在分开：
        REACHABLE 追；TEMPORARILY_BLOCKED 等 / 换路线；UNREACHABLE 放弃。
        """
        last = None
        for g in self._graphs(caps, x, y, tx, ty):
            last = g
            if not g.nodes:
                continue
            src = g.nearest(x, y, stand_only=False, allow_above=False)
            dst = g.nearest(tx, ty, stand_only=False)
            if src is None or dst is None:
                continue
            if g.reachable(src, dst):
                return ReachResult.REACHABLE
        if last is None or not last.nodes:
            return ReachResult.UNKNOWN
        dst = last.nearest(tx, ty, stand_only=False)
        if dst is None:
            return ReachResult.UNKNOWN
        n = last.nodes[dst]
        if math.hypot(n.x - tx, n.y - ty) > SNAP_FAR:
            return ReachResult.TEMPORARILY_BLOCKED   # 目标此刻不在任何地形上
        return ReachResult.UNREACHABLE

    def reachable(self, x, y, tx, ty, caps):
        """从 (x, y) 到得了 (tx, ty) 附近的地形吗。"""
        for g in self._graphs(caps, x, y, tx, ty):
            src = g.nearest(x, y, allow_above=False)
            dst = g.nearest(tx, ty)
            if src is None or dst is None:
                continue
            if g.reachable(src, dst):
                return True
        return False

    def returnable(self, x, y, tx, ty, caps):
        """到了 (tx, ty) 之后还回得来吗（可达性映射的第二问）。"""
        for g in self._graphs(caps, x, y, tx, ty):
            src = g.nearest(x, y, allow_above=False)
            dst = g.nearest(tx, ty)
            if src is None or dst is None:
                continue
            if g.can_return(src, dst):
                return True
        return False

    def __repr__(self):
        return "<Terrain floors=%d vpoles=%d wedges=%d hpoles=%d walls=%d>" % (
            len(self.walk_floors()), len(self.vpoles()),
            len(self.window_edges()), len(self.hpoles()), len(self.walls()))
