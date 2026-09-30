# -*- coding: utf-8 -*-
"""所有生物共用的地形查询：地面 / 平台顶 / 竖杆 / 横杆 / 背景墙。

反编译口径：原版一张地图的地形就是 AImap / AItile —— Floor / Wall / Ceiling /
Climb（``verticalBeam`` 竖杆、``horizontalBeam`` 横杆）都在同一张连通图里；
「这条路这只生物能不能走」由 ``CreatureTemplate.AccessibilityResistance`` /
``ConnectionResistance``（AImap.cs:59-77）决定，蜥蜴读的是 LizardPather 给出的
MovementConnection，而不是动作层临时去找一根竖线。

桌宠映射（与蛞蝓猫侧 planning/surface.py 读的是同一批几何）：

===========  ==========================================================
Floor        屏幕地板 + 别的窗口顶边（``chunkphys.platforms()``）
Climb(竖)    ``poles`` 里的竖杆 + 窗口左右竖边露出来的墙段（``world.walls``）
Climb(横)    ``poles`` 里的横杆：能踩在杆面上走
Wall         同上；只有 WallClimber 品种（蓝 / 白 / 鳗鱼蜥）能把它当楼梯
===========  ==========================================================

这一层只回答三个问题：**我周围有哪些地形 / 这块地形怎么上去 / 我的能力表
允不允许用**。真正的位移仍归各自的物理（蜥蜴走 ``_step_wall``，蛞蝓猫走
PoleClimb / HPole）。
"""
from __future__ import annotations

import bisect
import math

from .enums import ItemState
from .pole import VERTICAL, HORIZONTAL

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

WALK, CLIMB, JUMP, DROP, HOP = "walk", "climb", "jump", "drop", "hop"


class Caps:
    """一只生物的地形能力表（原版 CreatureTemplate / LizardBreedParams）。

    前半是「能不能用某种连接」，后半是「这种连接跑多快 / 跳多高」—— 原版这些
    数值分散在 CreatureTemplate（bodySize / runspeed）与 LizardBreedParams
    （jumpForce / climbSpeed / dropSpeed）里，这里收成一张表交给移动图算代价。
    """

    __slots__ = ("walk", "jump", "wall_climb", "pole_climb", "wall_jump",
                 "climb_reach", "hpole_walk", "walk_speed", "climb_speed",
                 "jump_up", "jump_dx", "drop_max", "drop_dx", "hop_dx")

    def __init__(self, walk=True, jump=True, wall_climb=False, pole_climb=False,
                 wall_jump=False, climb_reach=CLIMB_REACH_DEFAULT,
                 hpole_walk=True, walk_speed=4.1, climb_speed=2.6,
                 jump_up=60.0, jump_dx=95.0, drop_max=420.0, drop_dx=DROP_DX,
                 hop_dx=HOP_DX):
        self.walk = bool(walk)
        self.jump = bool(jump)
        self.wall_climb = bool(wall_climb)
        self.pole_climb = bool(pole_climb)
        self.wall_jump = bool(wall_jump)
        self.climb_reach = float(climb_reach)
        self.hpole_walk = bool(hpole_walk)
        self.walk_speed = float(walk_speed)
        self.climb_speed = float(climb_speed)
        self.jump_up = float(jump_up)
        self.jump_dx = float(jump_dx)
        self.drop_max = float(drop_max)
        self.drop_dx = float(drop_dx)
        self.hop_dx = float(hop_dx)

    def key(self):
        """缓存键：只有影响图结构的字段进来。"""
        return (self.walk, self.jump, self.wall_climb, self.pole_climb,
                self.wall_jump, self.hpole_walk, round(self.climb_reach, 1),
                round(self.walk_speed, 2), round(self.climb_speed, 2),
                round(self.jump_up, 1), round(self.jump_dx, 1),
                round(self.drop_max, 1), round(self.drop_dx, 1),
                round(self.hop_dx, 1))

    def __repr__(self):
        return "Caps(walk=%s jump=%s wall=%s pole=%s)" % (
            self.walk, self.jump, self.wall_climb, self.pole_climb)


# ══════════════════════════════════════════════════════════════════════
# 移动图：NavNode = Surface + AnchorX；MoveLink = MovementConnection
#
# 反编译口径（原版 Room / AImap / Creature）：
#   * 地图不是「平台列表」，而是 Floor / Wall / Climb / Ceiling 的连通图
#     （AImap + AItile，每个 tile 有 TerrainType 与 Accessibility）。
#   * 生物移动 = 走一条 MovementConnection（walk / climb / jump / drop / beam）。
#   * 「这条路这只生物能不能走」= CreatureTemplate 的能力位 + ConnectionResistance。
#   * 寻路还会做 accessibility mapping —— 不光算「能不能到达」，还算
#     「能不能从那里回来」，免得生物走进一个出不来的坑。
#
# 桌宠映射：
#   Floor      -> 屏幕地板 + 别的窗口顶边（chunkphys.platforms）
#   Climb(竖)  -> 竖杆 + 背景墙露出来的竖段（world.walls / WallSurface）
#   Climb(横)  -> 横杆的杆面：能踩在上面走
#   节点        -> NavNode(surface, anchor_x)：一块面上每隔 ANCHOR_STEP 一个锚点，
#                  这样图里能表达「走到哪一段，再从那里跳」，而不是「这块面反正
#                  能跳过去」。
# ══════════════════════════════════════════════════════════════════════


class Leg:
    """一段路线（RoutePlan 的一条腿）：动作层只负责执行这一段。"""

    __slots__ = ("mode", "x", "y", "tx", "ty", "top", "bot", "up")

    def __init__(self, mode, x, y, tx=None, ty=None, top=None, bot=None, up=0):
        self.mode = mode          # walk / climb_wall / climb_pole / jump / drop / hop
        self.x, self.y = float(x), float(y)   # 这一段先去哪（上墙点 / 起跳点 / 落点）
        self.tx, self.ty = tx, ty             # 段末落点（jump / drop / hop 用）
        self.top, self.bot = top, bot         # 竖线上下端（climb 用）
        self.up = int(up)                      # climb 方向：+1 上 / -1 下

    def __repr__(self):
        return "Leg(%s, %.0f,%.0f)" % (self.mode, self.x, self.y)


class NavNode:
    """导航节点 = 地形（一块面 / 一条竖线）+ 锚点 x。"""

    __slots__ = ("nid", "x", "y", "line", "top", "bot", "stand")

    def __init__(self, nid, x, y, stand=True, line=None, top=None, bot=None):
        self.nid = nid
        self.x, self.y = float(x), float(y)
        self.stand = bool(stand)   # 能不能站在这（地板 / 横杆面 / 竖线两端）
        self.line = line           # None / "wall" / "pole"：这条竖线属于哪一族
        self.top, self.bot = top, bot

    def __repr__(self):
        return "Nav#%d(%s, %.0f,%.0f)" % (self.nid, self.line or "floor",
                                          self.x, self.y)


class TerrainRoute:
    """一次寻路结果：多段 legs + 可达性 / 可返回性。"""

    __slots__ = ("legs", "reachable", "returnable", "cost")

    def __init__(self, legs, reachable, returnable, cost):
        self.legs = tuple(legs)
        self.reachable = bool(reachable)
        self.returnable = bool(returnable)
        self.cost = float(cost)

    def __repr__(self):
        return "TerrainRoute(%d legs, cost=%.1f, back=%s)" % (
            len(self.legs), self.cost, self.returnable)


def _anchors(lo, hi):
    """一块面 [lo, hi] 上的导航锚点（含两端，等距）。"""
    lo, hi = float(lo), float(hi)
    if hi - lo <= 1.0:
        return ()
    n = max(1, int((hi - lo) / ANCHOR_STEP) + 1)
    step = (hi - lo) / n
    return tuple(lo + step * i for i in range(n + 1))


def _scc(n, adj):
    """迭代 Tarjan：每个节点属于哪个强连通分量（可达性 / 可返回性用）。"""
    index = [0] * n
    low = [0] * n
    on = [False] * n
    comp = [-1] * n
    stack = []
    counter = 0
    ncomp = 0
    for root in range(n):
        if index[root]:
            continue
        work = [(root, 0)]
        while work:
            v, pi = work.pop()
            if pi == 0:
                counter += 1
                index[v] = low[v] = counter
                stack.append(v)
                on[v] = True
            recurse = False
            edges = adj[v]
            i = pi
            while i < len(edges):
                w = edges[i][0]
                if not index[w]:
                    work.append((v, i + 1))
                    work.append((w, 0))
                    recurse = True
                    break
                if on[w] and index[w] < low[v]:
                    low[v] = index[w]
                i += 1
            if recurse:
                continue
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on[w] = False
                    comp[w] = ncomp
                    if w == v:
                        break
                ncomp += 1
            if work:
                par = work[-1][0]
                if low[v] < low[par]:
                    low[par] = low[v]
    return comp


class TerrainGraph:
    """一次世界快照 + 一张能力表编译出来的 MovementConnection 图（可缓存）。"""

    __slots__ = ("nodes", "adj", "radj", "comp", "_dist", "_prev", "_src",
                 "_ret_src", "_ret_set")

    def __init__(self, nodes, adj):
        self.nodes = nodes
        self.adj = adj
        # 反图：回答「到了那里还回得来吗」要沿连接反向搜一次
        radj = [[] for _ in nodes]
        for u in range(len(nodes)):
            for (v, mode, cost, extra) in adj[u]:
                radj[v].append((u, mode, cost, extra))
        self.radj = radj
        self.comp = _scc(len(nodes), adj) if nodes else []
        self._dist = None
        self._prev = None
        self._src = None
        self._ret_src = None      # 「回得来」的 BFS 缓存：起点
        self._ret_set = None      # 起点对应的「能回到它」的节点集合

    # ── 起点 / 终点落点 ──
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

    # ── Dijkstra（单源，全图）──
    def _run(self, src):
        n = len(self.nodes)
        dist = [float("inf")] * n
        prev = [None] * n
        dist[src] = 0.0
        done = [False] * n
        for _ in range(n):
            u, ud = -1, float("inf")
            for i in range(n):
                if not done[i] and dist[i] < ud:
                    u, ud = i, dist[i]
            if u < 0:
                break
            done[u] = True
            for (w, mode, cost, extra) in self.adj[u]:
                nd = ud + cost
                if nd < dist[w]:
                    dist[w] = nd
                    prev[w] = (u, mode, extra)
        self._dist, self._prev, self._src = dist, prev, src

    def _ensure(self, src):
        if src is None:
            return False
        if self._dist is None or self._src != src:
            self._run(src)
        return True

    def path(self, src, dst):
        """返回 [(to_node, mode, extra, from_node), ...]；不可达返回 None。"""
        if src is None or dst is None:
            return None
        if not self._ensure(src):
            return None
        if self._dist[dst] == float("inf"):
            return None
        out = []
        cur = dst
        while self._prev[cur] is not None:
            u, mode, extra = self._prev[cur]
            out.append((cur, mode, extra, u))
            cur = u
        out.reverse()
        return out

    # ── 可达性 / 可返回性 ──
    def reachable(self, src, dst):
        if src is None or dst is None or not self._ensure(src):
            return False
        return self._dist[dst] != float("inf")

    def _reachers(self, src):
        """「能回到 src 的节点」集合：radj 上从 src 搜一次（BFS，按 src 缓存）。

        沿 radj 从 src 走到 dst ⇔ 在 adj 里有一条 dst → … → src 的连接链，
        也就是「站在 dst 上还回得来回 src」。
        """
        if self._ret_src == src and self._ret_set is not None:
            return self._ret_set
        seen = {src}
        stack = [src]
        while stack:
            u = stack.pop()
            for (w, _mode, _cost, _extra) in self.radj[u]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        # 小图直接全缓存；大图也只留最近一份（蜥蜴的起点很少变）
        self._ret_src, self._ret_set = src, seen
        return seen

    def back_reachable(self, dst, src):
        """从 dst 出发能不能回到 src（adj 里 dst → … → src 有连接链）。"""
        if dst is None or src is None:
            return False
        if dst == src:
            return True
        return dst in self._reachers(src)

    def can_return(self, src, dst):
        """原版 accessibility mapping 的第二问：到了 dst 还回得来吗。

        注意口径：只问「有没有一条从 dst 回到 src 的连接链」，不要求同强连通
        分量 —— 从窗台掉回地面是单向连接，但那是**回得来**，不能算困住。
        """
        if src is None or dst is None:
            return False
        if src == dst:
            return True
        return self.back_reachable(dst, src)   # dst → … → src 有连接链

    def legs(self, path):
        """把节点路径折成动作层能执行的 legs（同面连续的 walk 合并成一段）。"""
        out = []
        for (to_i, mode, extra, from_i) in path:
            a, b = self.nodes[from_i], self.nodes[to_i]
            if mode.startswith("climb_"):
                out.append(Leg(mode, extra[3], b.y, top=extra[0], bot=extra[1],
                               up=extra[2]))
            elif mode == JUMP:
                out.append(Leg("jump", a.x, a.y, tx=b.x, ty=b.y))
            elif mode == DROP:
                out.append(Leg("drop", a.x, a.y, tx=b.x, ty=b.y))
            elif mode == HOP:
                out.append(Leg("hop", a.x, a.y, tx=b.x, ty=b.y))
            else:
                out.append(Leg("walk", b.x, b.y))
        return _merge_legs(out)


def _merge_legs(legs):
    """同一块面上的连续 walk 合并成一段（否则一路走过去会拆成十几段）。"""
    out = []
    for leg in legs:
        if (out and leg.mode == "walk" and out[-1].mode == "walk"
                and abs(out[-1].y - leg.y) < 2.0):
            out[-1].x = leg.x
            out[-1].y = leg.y
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
    """一次世界快照上的地形查询。每 tick 建一次，全场生物共用同一份。"""

    __slots__ = ("win", "_floors")

    def __init__(self, win):
        self.win = win
        self._floors = None

    # ── 原始地形 ──
    def platforms(self):
        """窗口顶边（可站的平台）：``(x0, y, x1)``。"""
        from ..core import chunkphys
        return tuple(chunkphys.platforms() or ())

    def _poles(self):
        out = []
        for pl in getattr(self.win, "poles", ()) or ():
            if getattr(pl, "state", None) != ItemState.FREE:
                continue                      # 被拿起 / 已消失的杆不是地形
            if getattr(pl, "virtual", False):
                continue                      # 鼠标那截虚杆：不是地形
            out.append(pl)
        return out

    def vpoles(self):
        """竖杆：``(x, top, bot)``（top < bot）。"""
        out = []
        for pl in self._poles():
            if getattr(pl, "kind", None) != VERTICAL:
                continue
            out.append((float(pl.x), min(pl.ay, pl.by), max(pl.ay, pl.by)))
        return tuple(out)

    def hpoles(self):
        """横杆：``(x0, y, x1)`` —— 杆面可以踩。"""
        out = []
        for pl in self._poles():
            if getattr(pl, "kind", None) != HORIZONTAL:
                continue
            out.append((min(pl.ax, pl.bx), float(pl.ay), max(pl.ax, pl.bx)))
        return tuple(out)

    def walls(self):
        """背景墙的**可见**竖段：``(x, top, bot)``。"""
        out = []
        for ws in getattr(self.win, "wall_surfaces", ()) or ():
            for top, bot in ws.segments:
                out.append((float(ws.x), float(top), float(bot)))
        if out:
            return tuple(out)
        for rect in getattr(self.win, "walls", ()) or ():     # 兜底：还没建 surface
            x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
            top, bot = min(y0, y1), max(y0, y1)
            out.append((float(x0), top, bot))
            out.append((float(x1), top, bot))
        return tuple(out)

    def climb_surfaces(self):
        """可攀爬的**竖线**：``(x, top, bot, kind)``，kind ∈ {"pole", "wall"}。

        横杆不在这里 —— 它不是竖线，是脚下的地形（见 walk_floors）。
        """
        out = [(x, t, b, "pole") for x, t, b in self.vpoles()]
        out += [(x, t, b, "wall") for x, t, b in self.walls()]
        return tuple(out)

    # ── 可站的面 ──
    def walk_floors(self):
        """能站在上面的面：屏幕地板 + 窗口顶边 + 横杆杆面 -> ``(x0, y, x1)``。"""
        wl = float(getattr(self.win, "_WL", 0.0) or 0.0)
        hl = float(getattr(self.win, "_HL", 0.0) or 0.0)
        out = [(0.0, hl, wl)]
        for x0, y, x1 in self.platforms():
            out.append((float(x0), float(y), float(x1)))
        for x0, y, x1 in self.hpoles():
            out.append((x0, y, x1))
        return tuple(out)

    def floor_under(self, x, y):
        """x 处、y 之下最近的可站面（没有就退回屏幕地板）。"""
        hl = float(getattr(self.win, "_HL", 0.0) or 0.0)
        best = hl
        for x0, fy, x1 in self.walk_floors():
            if fy < y - FLOOR_SNAP:
                continue                      # 面在我上面：踩不到
            if not (x0 - 4.0 <= x <= x1 + 4.0):
                continue
            if fy < best:
                best = fy
        return best

    # ── 路线 ──
    def route_hint(self, x, y, tx, ty, caps):
        """够不着目标时先问地形：有没有一条「走 → 上墙 / 上杆」的路线。

        返回 ``(mode, sx, top, bot, dir, reason)``；没有可用地形就 None。mode ∈
        ``{"climb_wall", "climb_pole"}``，sx 是上墙点（线所在的 x），(top, bot)
        是这条线的上下端，dir = +1 向上 / -1 向下。
        """
        if caps is None or ty >= y - FLOOR_TOL:
            return None                       # 目标不比我高：直冲 / 跳跃那套
        best = None
        for sx, top, bot, kind in self.climb_surfaces():
            if kind == "wall":
                if not caps.wall_climb:
                    continue                  # 不会爬墙的品种：背景墙不是它的地形
            elif not caps.pole_climb:
                continue
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
    def graph(self, caps):
        """把这一帧的地形编译成 MovementConnection 图（按几何版本 + 能力表缓存）。"""
        if caps is None:
            caps = Caps()
        wl = float(getattr(self.win, "_WL", 0.0) or 0.0)
        hl = float(getattr(self.win, "_HL", 0.0) or 0.0)
        key = (int(getattr(self.win, "geometry_version", 0) or 0),
               int(wl), int(hl), caps.key())
        cache = _graph_cache(self.win)
        hit = cache.get(key)
        if hit is not None:
            return hit
        g = self._build_graph(caps, wl, hl)
        if len(cache) > 8:
            cache.clear()
        cache[key] = g
        return g

    def _build_graph(self, caps, wl, hl):
        nodes = []
        adj = []

        def add_node(x, y, stand=True, line=None, top=None, bot=None):
            nodes.append(NavNode(len(nodes), x, y, stand=stand, line=line,
                                 top=top, bot=bot))
            adj.append([])
            return len(nodes) - 1

        def link(a, b, mode, cost, extra=(None, None, 0, None), both=True):
            if a == b:
                return
            adj[a].append((b, mode, float(cost), extra))
            if both:
                adj[b].append((a, mode, float(cost), extra))

        # ① 可站的面：屏幕地板 / 窗台 / 横杆杆面
        spans = []
        for x0, y, x1 in self.walk_floors():
            lo, hi = max(0.0, float(x0)), min(wl, float(x1))
            if hi - lo > 1.0:
                spans.append((lo, float(y), hi))
        span_anchors = []          # [ [(node_i, x), ...], ... ]
        for (lo, y, hi) in spans:
            row = [(add_node(ax, y), ax) for ax in _anchors(lo, hi)]
            span_anchors.append(row)
            for k in range(len(row) - 1):        # 同面相邻锚点：走过去
                (a, ax), (b, bx) = row[k], row[k + 1]
                d = abs(bx - ax)
                link(a, b, WALK, d / max(0.5, caps.walk_speed))
        # 面与面之间：x 范围挨着（缝隙 ≤ STEP_X）且高差 ≤ STEP_DY 就走过去
        for i in range(len(spans)):
            lo_a, y_a, hi_a = spans[i]
            for j in range(i + 1, len(spans)):
                lo_b, y_b, hi_b = spans[j]
                if abs(y_a - y_b) > STEP_DY:
                    continue
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
                    link(best[1], best[2], WALK,
                         best[0] / max(0.5, caps.walk_speed))

        node_y = {}
        for row in span_anchors:
            for (n, _x) in row:
                node_y[n] = nodes[n].y

        # ② 竖线：竖杆 / 背景墙露出来的竖段 —— 底端 + 顶端两个节点
        vnodes = []        # [(node_i, x, y)]
        for (x, top, bot, kind) in self.climb_surfaces():
            top, bot = float(top), float(bot)
            if bot - top < 8.0:
                continue
            can = (caps.wall_climb if kind == "wall" else caps.pole_climb)
            nf = add_node(x, bot, stand=True, line=kind, top=top, bot=bot)
            nh = add_node(x, top, stand=True, line=kind, top=top, bot=bot)
            vnodes.append((nf, x, bot))
            vnodes.append((nh, x, top))
            if can:
                c = (bot - top) / max(0.5, caps.climb_speed) + CLIMB_COST
                link(nf, nh, "climb_" + kind, c, (top, bot, 1, x))
                link(nh, nf, "climb_" + kind, c, (top, bot, -1, x))

        # ③ 面 ↔ 竖线端点：走过去就能抓（原版 Floor→Wall 那条连接）
        for (nv, vx, vy) in vnodes:
            for row in span_anchors:
                for (na, ax) in row:
                    if abs(ax - vx) > caps.climb_reach:
                        continue
                    if abs(node_y[na] - vy) > ATTACH_DY:
                        continue
                    link(na, nv, WALK,
                         abs(ax - vx) / max(0.5, caps.walk_speed) + ATTACH_COST)

        # ④ 能站的节点集合（跳跃 / 跳下的两端）
        stand = []
        for row in span_anchors:
            stand.extend(row)
        stand.extend((n, x) for (n, x, _y) in vnodes)
        sy = dict(node_y)
        for (n, _x, _y) in vnodes:
            sy[n] = nodes[n].y

        # 粗筛（原版 MovementConnection 也是按 tile 层找，不是全场两两比）：
        # 把能站的节点按 y 排好，跳跃 / 跳下只在自己的高度带里取候选。
        band = sorted(stand, key=lambda p: sy[p[0]])
        band_y = [sy[n] for (n, _x) in band]

        def _slice(lo, hi):
            return band[bisect.bisect_left(band_y, lo):
                        bisect.bisect_right(band_y, hi)]

        # ⑤ 跳跃：往上够得着的锚点（原版 jump MovementConnection）
        if caps.jump:
            for (a, ax) in stand:
                ay = sy[a]
                for (b, bx) in _slice(ay - caps.jump_up, ay):
                    if a == b:
                        continue
                    up = ay - sy[b]
                    if up <= 0.0 or up > caps.jump_up:
                        continue
                    d = abs(bx - ax)
                    if d > caps.jump_dx:
                        continue
                    link(a, b, JUMP, 1.0 + d / max(1.0, caps.jump_dx),
                         (None, None, 1, None), both=False)

        # ⑥ 跳下：往下的落差（走路掉下去，不需要能力）
        for (a, ax) in stand:
            ay = sy[a]
            for (b, bx) in _slice(ay + DROP_MIN, ay + caps.drop_max):
                if a == b:
                    continue
                down = sy[b] - ay
                if down < DROP_MIN or down > caps.drop_max:
                    continue
                d = abs(bx - ax)
                if d > caps.drop_dx:
                    continue
                link(a, b, DROP, 0.6 + down / max(1.0, caps.drop_max),
                     (None, None, -1, None), both=False)

        # ⑦ 竖线之间：杆↔杆 / 杆↔墙 的横向挪动（原版 beam 之间的小跳）
        # 按 x 排序后只扫横向窗口内的邻居（原来是无条件 N² 全比）。
        if caps.pole_climb or caps.wall_climb or caps.wall_jump:
            vx_sorted = sorted(vnodes, key=lambda p: p[1])
            for i in range(len(vx_sorted)):
                a, ax, ay = vx_sorted[i]
                for j in range(i + 1, len(vx_sorted)):
                    b, bx, by = vx_sorted[j]
                    d = bx - ax
                    if d > caps.hop_dx:
                        break                     # 再往后只会更远
                    if d < 1.0 or abs(by - ay) > HOP_DY:
                        continue
                    link(a, b, HOP, 1.2, (None, None, 1, None), both=False)
                    link(b, a, HOP, 1.2, (None, None, -1, None), both=False)

        return TerrainGraph(nodes, adj)

    # ── 寻路 ──
    def route(self, x, y, tx, ty, caps, must_return=True, stand_only=True):
        """多段地形路线。

        must_return=True 时只给「能去也能回」的路线（原版 accessibility mapping
        的第二问）；返回 None 表示地形层给不出方案，让上层退回自己的兜底逻辑。
        """
        g = self.graph(caps)
        if not g.nodes:
            return None
        src = g.nearest(x, y, stand_only=stand_only, allow_above=False)
        dst = g.nearest(tx, ty, stand_only=stand_only)
        path = g.path(src, dst)
        if path is None:
            return None
        back = g.can_return(src, dst)
        if must_return and not back:
            return None
        legs = g.legs(path)
        if not legs:
            return None
        return TerrainRoute(legs, True, back, g._dist[dst])

    def reachable(self, x, y, tx, ty, caps):
        """从 (x, y) 到得了 (tx, ty) 附近的地形吗。"""
        g = self.graph(caps)
        src = g.nearest(x, y, allow_above=False)
        dst = g.nearest(tx, ty)
        return g.reachable(src, dst)

    def returnable(self, x, y, tx, ty, caps):
        """到了 (tx, ty) 之后还回得来吗（可达性映射的第二问）。"""
        g = self.graph(caps)
        src = g.nearest(x, y, allow_above=False)
        dst = g.nearest(tx, ty)
        return g.can_return(src, dst)

    def support(self, x, y, default):
        """脚下的支撑面 y：屏幕地板 / 窗台 / 横杆杆面里，离身体最近的下面那一块。

        生物物理用它当「地面」，这样蜥蜴能站在别的窗口顶上和横杆上，而不是只认
        屏幕底边（原版 Floor tile 本来就不止一种）。
        """
        best = default
        for x0, fy, x1 in self.walk_floors():
            if fy < y - SINK_TOL:
                continue                      # 面在身体上方：这一脚踩不到
            if not (x0 - 2.0 <= x <= x1 + 2.0):
                continue
            if fy < best:
                best = fy
        return best

    def __repr__(self):
        return "<Terrain floors=%d vpoles=%d hpoles=%d walls=%d>" % (
            len(self.walk_floors()), len(self.vpoles()), len(self.hpoles()),
            len(self.walls()))
