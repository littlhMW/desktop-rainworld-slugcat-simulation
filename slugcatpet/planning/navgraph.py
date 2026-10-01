# -*- coding: utf-8 -*-
"""统一的导航边与图：蜥蜴与蛞蝓猫共用的 MovementConnection 层。

反编译口径：原版生物移动 = 一条 MovementConnection（Room / AImap），
「这条路这只生物能不能走」由 CreatureTemplate 的能力位 +
ConnectionResistance 决定，寻路是 A*（PathFinder）。桌宠原本两套边：

    world/terrain.py     蜥蜴：tuple (to_node, mode, cost, extra)
    planning/surface.py  蛞蝓猫：SurfaceEdge(kind, src, dst, time, energy, risk, …)

同一件事（走过去 / 跳过去 / 爬上去）在两边是两种数据结构、两套代价。本模块
把它们收成一条 NavigationEdge，并给两边同一套 A* / 可达性 / 卡住检测 / 路线缓存。
"""
from __future__ import annotations

import heapq
import math

# ── 连接类型（原版 MovementConnection 的种类）──
WALK = "walk"                # 同一块面上走过去 / 跨小缝
STEP = "step"                # 台阶（小高差）
JUMP = "jump"                # 起跳够到更高 / 更远的锚点
DROP = "drop"                # 落下去
CLIMB_WALL = "climb_wall"                    # 沿**实体墙**爬（WallClimber）
CLIMB_POLE = "climb_pole"                    # 沿竖杆爬
CLIMB_BACKGROUND = "climb_background"        # 沿**背景区域**爬（原版背景墙攀爬）
CLIMB_EDGE = "climb_edge"                    # 已废弃（旧窗口竖边）
POLE_HOP = "pole_hop"        # 杆间跳跃
WALL_HOP = "wall_hop"        # 墙面之间挪
DOOR = "door"                # 穿过庇护所门洞
ATTACK = "attack_reach"      # 到位后直接攻击
FINISH = "finish"            # 收尾（伸手 / 起跳弧够到目标点）

LANDS = frozenset((JUMP, DROP, POLE_HOP, WALL_HOP))
CLIMBS = frozenset((CLIMB_WALL, CLIMB_POLE, CLIMB_BACKGROUND, CLIMB_EDGE))


class NavigationEdge:
    """一条导航边（文档口径）：带类型、耗时、风险、体力、可逆性与执行计划。"""

    __slots__ = ("src", "dst", "type", "time", "energy", "risk", "noise",
                 "reversible", "capability", "plan", "extra")

    def __init__(self, type, src, dst, time=1.0, energy=0.0, risk=0.0,
                 noise=0.0, reversible=True, capability=None, plan=None,
                 extra=None):
        self.type = type
        self.src = src
        self.dst = dst
        self.time = float(time)
        self.energy = float(energy)
        self.risk = float(risk)
        self.noise = float(noise)
        self.reversible = bool(reversible)
        self.capability = capability
        self.plan = plan
        self.extra = extra

    @property
    def lands(self):
        return self.type in LANDS

    def __repr__(self):
        return "<%s -> %s %.1ft>" % (self.type, self.dst, self.time)


class Capabilities:
    """能力表（文档 §13）：一位 = 会不会用某种连接。默认**全关**。"""

    __slots__ = ("walk", "step", "jump", "drop", "climb_pole", "climb_wall",
                 "climb_background", "climb_edge", "wall_jump", "pole_hop",
                 "wall_hop", "door",
                 "swim", "hpole_walk", "can_enter_shelter",
                 "walk_speed", "climb_speed", "jump_up", "jump_dx", "drop_max",
                 "drop_dx", "hop_dx", "climb_reach")

    def __init__(self, walk=True, step=True, jump=False, drop=True,
                 climb_pole=False, climb_wall=False, climb_background=None,
                 climb_edge=None,
                 wall_jump=False, pole_hop=False, wall_hop=False, door=True,
                 swim=False, hpole_walk=True, can_enter_shelter=True,
                 walk_speed=4.1, climb_speed=2.6, jump_up=0.0, jump_dx=0.0,
                 drop_max=420.0, drop_dx=70.0, hop_dx=90.0,
                 climb_reach=220.0):
        self.walk = bool(walk)
        self.step = bool(step)
        self.jump = bool(jump)
        self.drop = bool(drop)
        self.climb_pole = bool(climb_pole)
        self.climb_wall = bool(climb_wall)
        # 背景区域（Background Climb）：原版就是 WallClimber 干的活，所以不写
        # 就跟爬墙能力走；显式给值以品种表为准。
        self.climb_background = bool(
            self.climb_wall if climb_background is None else climb_background)
        # 窗口竖边已废弃：只留名字，不再有地形产出，恒 False。
        self.climb_edge = bool(False if climb_edge is None else climb_edge)
        self.wall_jump = bool(wall_jump)
        self.pole_hop = bool(pole_hop)
        self.wall_hop = bool(wall_hop)
        self.door = bool(door)
        self.swim = bool(swim)
        self.hpole_walk = bool(hpole_walk)
        self.can_enter_shelter = bool(can_enter_shelter)
        self.walk_speed = float(walk_speed)
        self.climb_speed = float(climb_speed)
        self.jump_up = float(jump_up)
        self.jump_dx = float(jump_dx)
        self.drop_max = float(drop_max)
        self.drop_dx = float(drop_dx)
        self.hop_dx = float(hop_dx)
        self.climb_reach = float(climb_reach)

    def allows_climb(self, kind):
        """这个能力表允许爬 Surface.climb 这一类竖线吗。"""
        if kind is None:
            return False
        if kind == "pole":
            return self.climb_pole
        if kind == "wall":
            return self.climb_wall
        if kind == "background":
            return self.climb_background
        if kind == "edge":
            return self.climb_edge
        return False

    def allows(self, type_):
        """这个能力表允许走 type_ 这一类连接吗。"""
        if type_ == WALK:
            return self.walk
        if type_ == STEP:
            return self.step
        if type_ == JUMP:
            return self.jump
        if type_ == DROP:
            return self.drop
        if type_ == CLIMB_POLE:
            return self.climb_pole
        if type_ == CLIMB_WALL:
            return self.climb_wall
        if type_ == CLIMB_BACKGROUND:
            return self.climb_background
        if type_ == CLIMB_EDGE:
            return self.climb_edge
        if type_ == POLE_HOP:
            return self.pole_hop or self.climb_pole
        if type_ == WALL_HOP:
            return self.wall_hop or self.climb_wall or self.wall_jump
        if type_ == DOOR:
            return self.door
        return True

    def key(self):
        return (self.walk, self.step, self.jump, self.drop, self.climb_pole,
                self.climb_wall, self.climb_background, self.climb_edge,
                self.wall_jump, self.pole_hop,
                self.wall_hop, self.door, self.swim, self.hpole_walk,
                self.can_enter_shelter, round(self.climb_reach, 1),
                round(self.walk_speed, 2), round(self.climb_speed, 2),
                round(self.jump_up, 1), round(self.jump_dx, 1),
                round(self.drop_max, 1), round(self.drop_dx, 1),
                round(self.hop_dx, 1))

    def __repr__(self):
        return "Capabilities(walk=%s jump=%s pole=%s wall=%s bg=%s)" % (
            self.walk, self.jump, self.climb_pole, self.climb_wall,
            self.climb_background)


class Preferences:
    """性格权重（文档 §13）：同一张图，不同生物算出不同最短路。

    目标选择时用 estimated travel time 而不是欧氏距离 —— 这份权重就是
    travel time 之外「愿意绕多远 / 愿不愿意冒险 / 多想要垂直机动」的表达。
    """

    __slots__ = ("time", "energy", "risk", "noise", "directness", "aggression",
                 "caution", "ambush", "persistence", "risk_tolerance",
                 "verticality", "pack_dependence")

    def __init__(self, time=1.0, energy=0.25, risk=1.0, noise=0.2, directness=1.0,
                 aggression=0.5, caution=0.5, ambush=0.15, persistence=0.5,
                 risk_tolerance=0.3, verticality=0.5, pack_dependence=0.2):
        self.time = float(time)
        self.energy = float(energy)
        self.risk = float(risk)
        self.noise = float(noise)
        self.directness = float(directness)
        self.aggression = float(aggression)
        self.caution = float(caution)
        self.ambush = float(ambush)
        self.persistence = float(persistence)
        self.risk_tolerance = float(risk_tolerance)
        self.verticality = float(verticality)
        self.pack_dependence = float(pack_dependence)

    @classmethod
    def from_prefs(cls, d):
        """旧 APPROACH_PREFS 字典 → 连续性格（迁移用，保留既有品种差异）。"""
        if not d:
            return cls()
        g = d.get
        return cls(time=1.0,
                   energy=g("travel", 0.8) * 0.3,
                   risk=g("wall", 1.5) * 0.5,
                   noise=0.2,
                   directness=1.0 / max(0.2, g("travel", 0.8) + 0.6),
                   aggression=g("lurk", 0.15) * -1.0 + 0.6,
                   caution=g("wall", 1.5) * 0.3,
                   ambush=g("lurk", 0.15),
                   persistence=0.5,
                   risk_tolerance=g("jump", 0.55),
                   verticality=g("angle", 0.7),
                   pack_dependence=0.2)

    def key(self):
        return (round(self.time, 3), round(self.energy, 3), round(self.risk, 3),
                round(self.noise, 3))


def edge_cost(edge, pers=None):
    """统一代价（文档 §39）：time*P + energy*P + risk*P + noise*P。"""
    if pers is None:
        return edge.time
    return (edge.time * pers.time + edge.energy * pers.energy
            + edge.risk * pers.risk + edge.noise * pers.noise)


class ReachResult:
    """可达性的四种结论（文档 §5）——不要把 UNKNOWN / UNREACHABLE 都当成 direct。"""

    REACHABLE = "reachable"
    TEMPORARILY_BLOCKED = "temporarily_blocked"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


STUCK_PHYSICS = "physics"          # 路线对，位移被墙 / 碰撞吞掉
STUCK_NAVIGATION = "navigation"    # 路线本身反复把人带到同一个死点
ANCHOR_BUCKET = 24.0               # 锚点量化桶（黑名单 / 插桩 / 图缓存共用一个键）
BLACKLIST_TTL = 240              # 导航黑名单保留 tick（约 4s）


def anchor_key(x, y, bucket=ANCHOR_BUCKET):
    """锚点量化成 24px 桶。黑名单与按需插桩必须用同一个键，别各算一套。"""
    return (int(round(float(x) / bucket)), int(round(float(y) / bucket)))


class StuckDetector:
    """卡住检测（文档 §13/§28）：不是「重规划几次」，是「这段时间有没有位移」。

    升级阶梯：1 次卡住 → 当前边重试；2 次 → 换边；3 次 → 换面；4 次 → 放弃目标。

    并且区分两种卡住 —— 这是「丢掉路线重新问图」之外真正需要的一层：

      STUCK_PHYSICS     这条路线是对的，位移被墙 / 碰撞 / 脚支撑吞掉了。
                        该做的是原地小跳、反向蹭出来，**不是**丢掉路线。
      STUCK_NAVIGATION  同一条边反复被选中、每次都到同一个死点。
                        该做的是把它的落点记进黑名单，让下一次寻路绕开它 ——
                        否则「A→B 失败 → 重规划 → 又给 A→B → 又卡」会一直转。
    """

    __slots__ = ("window", "min_px", "owner", "_x", "_y", "_tick", "level",
                 "kind", "_tries", "_blocked")

    def __init__(self, window=24, min_px=8.0, tick=0):
        self.window = int(window)
        self.min_px = float(min_px)
        self.owner = None
        self._x = None
        self._y = None
        self._tick = int(tick)
        self.level = 0
        self.kind = ""
        self._tries = {}                # 边签名 → 已经卡过几次
        self._blocked = {}              # 黑名单桶键 → 过期 tick

    def reset(self, x, y, tick=0):
        """重新开始计时。**不清黑名单** —— 那是世界知识，不是当前目标的进度。"""
        self._x, self._y = float(x), float(y)
        self._tick = int(tick)
        self.owner = None
        self.level = 0
        self.kind = ""

    # ── 导航黑名单（文档 §13：Navigation stuck 要 blacklist 当前 edge）──
    def block(self, x, y, tick, ttl=BLACKLIST_TTL):
        self._blocked[anchor_key(x, y)] = int(tick) + int(ttl)

    def blocked(self, x, y, tick) -> bool:
        k = anchor_key(x, y)
        until = self._blocked.get(k)
        if until is None:
            return False
        if int(tick) > until:
            del self._blocked[k]
            return False
        return True

    def blocked_keys(self, tick):
        """还没过期的黑名单桶键（直接喂 TerrainQuery.route(avoid=...)）。"""
        out = set()
        for k, until in list(self._blocked.items()):
            if int(tick) > until:
                del self._blocked[k]
            else:
                out.add(k)
        return out

    def update(self, x, y, tick, owner=None, edge=None) -> int:
        """返回当前卡住等级（0 = 没卡住）。

        owner 变了（换了目标）就重新计时；``edge`` 是这条边的签名（一般是它的
        落点）。同一签名卡第二次起判为 STUCK_NAVIGATION。
        """
        if self._x is None or owner != self.owner:
            self.reset(x, y, tick)
            self.owner = owner
            return 0
        if (int(tick) - self._tick) < self.window:
            return 0
        moved = math.hypot(x - self._x, y - self._y)
        self._x, self._y, self._tick = float(x), float(y), int(tick)
        if moved < self.min_px:
            self.level = min(4, self.level + 1)
            key = edge if edge is not None else owner
            try:
                self._tries[key] = self._tries.get(key, 0) + 1
                n = self._tries[key]
            except TypeError:
                n = 1
            if len(self._tries) > 48:
                self._tries.clear()
            self.kind = STUCK_NAVIGATION if n >= 2 else STUCK_PHYSICS
        else:
            self.level = 0
            self.kind = ""
        return self.level


def edge_dst(e):
    """边的终点（文档 §39 的收口）：蜥蜴侧直接是节点下标，蛞蝓猫侧是节点对象。

    两边的边对象形状不同（TerrainQuery 用 NavigationEdge，SurfaceGraph 用
    SurfaceEdge，还带实测轨迹 plan / 落点 land_x），但**图算法只该有一套** ——
    这里把「怎么拿到终点下标」收成一个入口，于是 radj / SCC / Dijkstra / A*
    全部可以直接复用同一份实现。
    """
    d = e.dst
    return d if isinstance(d, int) else d.nid


class NavGraph:
    """统一移动图：节点 + NavigationEdge。Dijkstra / A* 都用 heapq。

    旧实现（文档 §3）名义 Dijkstra、实际 O(V^2) 双重循环：节点多时每只蜥蜴
    每帧都在做几千次比较。这里改成 O((V+E) log V)。
    """

    __slots__ = ("nodes", "adj", "radj", "comp", "_dist", "_prev", "_src",
                 "_avoid", "_ret_src", "_ret_set", "version", "_pos")

    def __init__(self, nodes, adj, version=0, pos=None):
        self.nodes = nodes
        self.adj = adj
        self.version = int(version)
        self._pos = pos
        radj = [[] for _ in nodes]
        for u in range(len(nodes)):
            for e in self.edges(u):
                radj[edge_dst(e)].append(u)
        self.radj = radj
        self.comp = _scc(len(nodes), self) if nodes else []
        self._dist = None
        self._prev = None
        self._src = None
        self._avoid = None
        self._ret_src = None
        self._ret_set = None

    def edges(self, u):
        """u 的出边。adj 既可以是 list[list]（蜥蜴）也可以是 dict（蛞蝓猫图的历史形状）。"""
        if type(self.adj) is dict:
            return self.adj.get(u, ())
        return self.adj[u]

    # ── 节点坐标 ──
    def xy(self, i):
        if self._pos is not None:
            return self._pos(i)
        n = self.nodes[i]
        return (getattr(n, "x", getattr(n, "anchor", 0.0)), n.y)

    def heuristic(self, a, b, scale=1.0):
        ax, ay = self.xy(a)
        bx, by = self.xy(b)
        return math.hypot(bx - ax, by - ay) * scale

    # ── Dijkstra（单源，heapq）──
    def _run(self, src, avoid=None):
        """单源最短路。``avoid`` 里的节点不可进入（导航级黑名单，文档 §13）。

        「A→B 走不通 → 重规划 → 又给 A→B」的死循环只能靠把那条边记下来解决：
        StuckDetector 判定 STUCK_NAVIGATION 后把落点塞进 avoid，下一次寻路
        自然绕开它，而不是原样再给一遍。
        """
        n = len(self.nodes)
        dist = [float("inf")] * n
        prev = [None] * n
        dist[src] = 0.0
        heap = [(0.0, src)]
        pop = heapq.heappop
        push = heapq.heappush
        while heap:
            d, u = pop(heap)
            if d > dist[u]:
                continue
            for e in self.edges(u):
                if avoid is not None:
                    v = edge_dst(e)
                    if v in avoid and v != src:
                        continue
                nd = d + e.time
                if nd < dist[e.dst]:
                    dist[e.dst] = nd
                    prev[e.dst] = (u, e)
                    push(heap, (nd, e.dst))
        self._dist, self._prev, self._src, self._avoid = dist, prev, src, avoid

    def _ensure(self, src, avoid=None):
        if src is None:
            return False
        if self._dist is None or self._src != src or self._avoid != avoid:
            self._run(src, avoid)
        return True

    def path(self, src, dst, avoid=None):
        """返回 [NavigationEdge, ...]；不可达 None。"""
        if src is None or dst is None or not self._ensure(src, avoid):
            return None
        if self._dist[dst] == float("inf"):
            return None
        out = []
        cur = dst
        while self._prev[cur] is not None:
            u, e = self._prev[cur]
            out.append(e)
            cur = u
        out.reverse()
        return out

    # ── A*（目标明确时用；蜥蜴追猎恒有目标）──
    def astar(self, src, dst, max_speed=20.0, avoid=None):
        if src is None or dst is None:
            return None
        if src == dst:
            return []
        n = len(self.nodes)
        g = {src: 0.0}
        prev = {}
        heap = [(self.heuristic(src, dst) / max_speed, 0.0, src)]
        pop, push = heapq.heappop, heapq.heappush
        closed = set()
        while heap:
            _f, gc, u = pop(heap)
            if u == dst:
                out = []
                cur = u
                while cur in prev:
                    p, e = prev[cur]
                    out.append(e)
                    cur = p
                out.reverse()
                return out
            if u in closed:
                continue
            closed.add(u)
            for e in self.edges(u):
                if avoid is not None:
                    v = edge_dst(e)
                    if v in avoid and v != src:
                        continue
                ng = gc + e.time
                if ng < g.get(e.dst, float("inf")) - 1e-9:
                    g[e.dst] = ng
                    prev[e.dst] = (u, e)
                    push(heap, (ng + self.heuristic(e.dst, dst) / max_speed, ng,
                                e.dst))
        return None

    def reachable(self, src, dst):
        if src is None or dst is None or not self._ensure(src):
            return False
        return self._dist[dst] != float("inf")

    def _reachers(self, src):
        if self._ret_src == src and self._ret_set is not None:
            return self._ret_set
        seen = {src}
        stack = [src]
        while stack:
            u = stack.pop()
            for w in self.radj[u]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        self._ret_src, self._ret_set = src, seen
        return seen

    def back_reachable(self, dst, src):
        if dst is None or src is None:
            return False
        if dst == src:
            return True
        return dst in self._reachers(src)

    def can_return(self, src, dst):
        if src is None or dst is None:
            return False
        if src == dst:
            return True
        return self.back_reachable(dst, src)


def _scc(n, g):
    """迭代 Tarjan：强连通分量（可达性 / 可返回性）。

    g 是 NavGraph（或任何有 edge_dst 形状边的图对象）——
    于是蜥蜴的 list 邻接表和蛞蝓猫的 dict 邻接表跑的是同一份实现。
    """
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
            edges = g.edges(v)
            i = pi
            while i < len(edges):
                w = edge_dst(edges[i])
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


class RouteCache:
    """路线缓存（文档 §24/§26）：按**导航版本** + 分桶后的起终点缓存。

    旧键含 world_version 且 round(x, 1) —— 猫每移动 0.1px 就换一次键、
    加一只飞虫就整张图重建。这里只依赖导航版本，并且按 16px / 24px 分桶。
    """

    __slots__ = ("bucket", "limit", "_data", "_nav", "_tick")

    def __init__(self, bucket=16.0, limit=64):
        self.bucket = float(bucket)
        self.limit = int(limit)
        self._data = {}
        self._nav = None
        self._tick = None

    def key(self, nav_version, sx, sy, gx, gy, extra=None):
        b = self.bucket
        return (int(nav_version), int(sx // b), int(sy // b),
                int(gx // b), int(gy // b), extra)

    def get(self, key):
        return self._data.get(key)

    def put(self, key, value):
        if len(self._data) >= self.limit:
            self._data.clear()
        self._data[key] = value

    def note_version(self, nav_version):
        if self._nav != nav_version:
            self._nav = nav_version
            self._data.clear()
