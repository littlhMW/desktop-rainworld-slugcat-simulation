# -*- coding: utf-8 -*-
"""投掷物 ⨯ 目标的统一命中几何（文档「追加审计」第 4 / 6 / 7 条）。

之前「AI 预演弹道」和「真实命中」各有一套：

* 蜥蜴：逐 chunk 扫掠，返回**真实接触点**，矛尖对齐它；
* 蛞蝓猫：只做 chunk0/chunk1 的点到线段距离，只知道「碰到了」，没有接触点；
* 拾荒者：直接比中心点，40px/帧 的矛一帧跨过去就打空；
* 蝠蝇 / 蝉乌贼这类没链节的：返回这一帧的**终点**当命中点。

于是「AI 说能中、实际插在空气里」、「可命中点不对」。这里收成唯一一套：
目标 → 可命中点列表 → 扫掠求最早接触点 → 把矛**尖**摆上去。
AI 预演（fsm._shot_hits_target）和真实物理（items._step_spear_hit）都只调这几个。
轻量：不引用任何游戏对象，只看字段，所以 AI 预演可以直接拿真实对象跑同一个函数。
"""
from __future__ import annotations

import math


def sweep_circle(ax, ay, bx, by, cx, cy, r):
    """线段 AB 首次穿进圆 (c, r) 的接触点；返回 (t, x, y)，没穿进返回 None。

    t 是这一帧位移上的参数（0=起点、1=终点），取最早的一个才是「真实接触点」。
    """
    dx, dy = bx - ax, by - ay
    fx, fy = ax - cx, ay - cy
    a = dx * dx + dy * dy
    if a <= 1e-9:
        return (0.0, ax, ay) if fx * fx + fy * fy <= r * r else None
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None
    sq = math.sqrt(disc)
    t = (-b - sq) / (2.0 * a)
    if t < 0.0:
        if c > 0.0:
            return None                      # 圆整段都在前方：这一帧没碰到
        t = 0.0                              # 起点已经在圆里
    elif t > 1.0:
        return None
    return (t, ax + dx * t, ay + dy * t)


def seg_dist(ax, ay, bx, by, x, y) -> float:
    """点 (x,y) 到线段 AB 的最短距离。投掷物 40px/帧，逐帧位置判定会穿过链节。"""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-9:
        return math.hypot(x - ax, y - ay)
    t = ((x - ax) * dx + (y - ay) * dy) / L2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(x - (ax + dx * t), y - (ay + dy * t))


def target_chunks(t):
    """目标身上所有可命中点 ``[(owner, x, y, rad), ...]``（全局唯一口径）。

    优先用对象自己声明的 ``hit_chunks()``（面条蝇那种吻部要收细的）；
    没有就按「双 chunk 躯干（蛞蝓猫）→ 头 + 各链节（蜥蜴）→ 单圆（拾荒者 /
    蝠蝇）」逐级降级 —— 旧代码这里每处各写一套，才是「可命中点不对」的来源。
    """
    # 正式接口 CombatTarget.chunks()（文档 §6）：目标自己声明可命中点。
    # hit_chunks() 是旧名字，保留兼容；两者都没有才走下面的降级链。
    for name in ("chunks", "hit_chunks"):
        hc = getattr(t, name, None)
        if not callable(hc):
            continue
        try:
            got = [(t, float(cx), float(cy), float(cr)) for (cx, cy, cr) in hc()]
        except Exception:
            got = []
        if got:
            return got
    c0, c1 = getattr(t, "chunk0", None), getattr(t, "chunk1", None)
    if c0 is not None:
        out = []
        for c in (c0, c1):
            if c is None:
                continue
            out.append((t, float(c.x), float(c.y),
                        float(getattr(c, "rad", 0.0) or 0.0)))
        if out:
            return out
    p0, p1 = getattr(t, "p0", None), getattr(t, "p1", None)
    if (p0 is not None and p1 is not None
            and isinstance(p0, (tuple, list)) and isinstance(p1, (tuple, list))):
        # 双 chunk 物件（爆米花荚：p0/p1 两个悬挂点）。旧 items._cob_hit 就是
        # 拿这两个点各判一次；统一到 target_chunks 才不丢第二种 chunk。
        rad = float(getattr(t, "rad", 0.0) or 0.0)
        return [(t, float(p0[0]), float(p0[1]), rad),
                (t, float(p1[0]), float(p1[1]), rad)]
    out = []
    x, y = getattr(t, "x", None), getattr(t, "y", None)
    if (isinstance(x, (int, float)) and not isinstance(x, bool)
            and isinstance(y, (int, float)) and not isinstance(y, bool)):
        rad = getattr(t, "head_rad", None)
        if rad is None:
            rad = getattr(t, "rad", 0.0)
        out.append((t, float(x), float(y), float(rad or 0.0)))
    for s in (getattr(t, "seg", None) or ()):
        out.append((s, float(s.x), float(s.y), float(getattr(s, "rad", 0.0) or 0.0)))
    return out


def preferred_point(t):
    """目标身上「最该瞄准的那个点」``(x, y)``（文档 §6 CombatTarget）。

    目标可以自己实现 ``preferred_point()``（头甲、盾牌、软肋各不相同）；
    没实现就退回 :func:`target_chunks` 的第一个点。所有瞄准都读这一份，
    别再「AI 瞄 chunk0、判定判 chunk1」。
    """
    fn = getattr(t, "preferred_point", None)
    if callable(fn):
        try:
            px, py = fn()
            return (float(px), float(py))
        except Exception:
            pass
    ch = target_chunks(t)
    if not ch:
        x, y = getattr(t, "x", None), getattr(t, "y", None)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return (float(x), float(y))
        return None
    _o, cx, cy, _r = ch[0]
    return (cx, cy)


def hit_radius(t) -> float:
    """目标的命中半径（文档 §6 CombatTarget）：优先自报，否则取所有 chunk 最大值。"""
    fn = getattr(t, "hit_radius", None)
    if callable(fn):
        try:
            return float(fn())
        except Exception:
            pass
    ch = target_chunks(t)
    if not ch:
        return float(getattr(t, "rad", 0.0) or 0.0)
    return max(float(cr) for (_o, _x, _y, cr) in ch)


class HitResult:
    """一次命中的统一结果（文档 §6）。

    * ``owner``  ／ 命中的 chunk 或子对象（头部甲、尾巴、荚……）
    * ``point``  ／ 真实接触点 (x, y)，插矛要贴的就是它
    * ``t``      ／ 沿这一帧扫掠线段的参数 0..1
    * ``tick``   ／ 预演时是第几帧扫到的
    * ``normal`` ／ 接触法线（= 扫掠线段方向的垂线）
    * ``impact_angle`` ／ 命中瞬间的**飞行角**：矛身朝向可能已经和它不同，
      插墙 / 插生物改用它，不再拿 ``sp.angle_deg`` 冒充（文档 §6）。

    兼容旧的 ``owner, point, t = hit`` 解包与 ``hit[1][0]`` 下标。
    """
    __slots__ = ("owner", "point", "t", "tick", "normal", "impact_angle")

    def __init__(self, owner, point, t, tick=0.0, normal=(0.0, 0.0), impact_angle=None):
        self.owner = owner
        self.point = (float(point[0]), float(point[1]))
        self.t = float(t)
        self.tick = float(tick)
        self.normal = (float(normal[0]), float(normal[1]))
        self.impact_angle = impact_angle

    def __iter__(self):
        return iter((self.owner, self.point, self.t))

    def __getitem__(self, i):
        return (self.owner, self.point, self.t)[i]

    def __len__(self):
        return 3

    def __repr__(self):
        return "HitResult(%r, %r, t=%.3f)" % (self.owner, self.point, self.t)


def _impact_angle(ax, ay, bx, by):
    """扫掠方向 → 飞行角（0 = 上，顺时针为正，y↓），和 Spear.tip() 同口径。"""
    dx, dy = bx - ax, by - ay
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def _normal_of(ax, ay, bx, by):
    """扫掠方向 → 接触法线（单位向量，垂直于飞行方向）。"""
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L <= 1e-9:
        return (0.0, 0.0)
    return (-dy / L, dx / L)


def sweep_hit(target, ball, pad: float = 0.0):
    """飞行中的投掷物 vs 目标：返回 (命中点, 真实接触点 (x, y), t)，没中 None。

    ball 需要 last_x/last_y 与 x/y/rad（有 _seg_x/_seg_y 时优先，同 items._seg_end）。
    """
    ax = float(getattr(ball, "last_x", ball.x))
    ay = float(getattr(ball, "last_y", ball.y))
    bx = float(getattr(ball, "_seg_x", ball.x))
    by = float(getattr(ball, "_seg_y", ball.y))
    brad = float(getattr(ball, "rad", 0.0) or 0.0)
    best = None
    for owner, cx, cy, cr in target_chunks(target):
        got = sweep_circle(ax, ay, bx, by, cx, cy, brad + cr + pad)
        if got is None:
            continue
        if best is None or got[0] < best[0]:
            best = (got[0], owner, got[1], got[2])
    if best is None:
        return None
    return HitResult(best[1], (best[2], best[3]), best[0],
                     normal=_normal_of(ax, ay, bx, by),
                     impact_angle=_impact_angle(ax, ay, bx, by))


def sweep_hit_predicted(target, ax, ay, bx, by, brad, pad: float = 0.0,
                        tick: float = 0.0):
    """飞行线段 AB vs 目标：把每个可命中点按**它自己的速度**推进 tick 帧再判。

    AI 预演专用（真实命中走 :func:`sweep_hit`）。同伴/猎物也在动，逐 chunk 拿各自
    的 ``vx/vy`` 平移才是「这一 tick 它会在哪」；旧实现各写一套，才出现
    「AI 算的命中点」和「真实命中点」对不上。
    """
    best = None
    for owner, cx, cy, cr in target_chunks(target):
        cx += float(getattr(owner, "vx", 0.0) or 0.0) * float(tick)
        cy += float(getattr(owner, "vy", 0.0) or 0.0) * float(tick)
        got = sweep_circle(ax, ay, bx, by, cx, cy, brad + cr + pad)
        if got is None:
            continue
        if best is None or got[0] < best[0]:
            best = (got[0], owner, got[1], got[2])
    if best is None:
        return None
    return HitResult(best[1], (best[2], best[3]), best[0], tick=tick,
                     normal=_normal_of(ax, ay, bx, by),
                     impact_angle=_impact_angle(ax, ay, bx, by))


def tip_align(ball, hx: float, hy: float, length: float, angle_deg=None) -> None:
    """把投掷物的**尖**摆到接触点上（中心沿自身轴线回退 length/2）。

    和 Spear.tip() 同一套几何：angle=0 向上、顺时针为正、y 向下。
    """
    if angle_deg is None:
        angle_deg = getattr(ball, "angle_deg", 90.0)
    ang = math.radians(float(angle_deg))
    ball.x = float(hx) - math.sin(ang) * float(length) * 0.5
    ball.y = float(hy) + math.cos(ang) * float(length) * 0.5
