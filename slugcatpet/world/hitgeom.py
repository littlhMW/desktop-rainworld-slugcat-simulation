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
    hc = getattr(t, "hit_chunks", None)
    if callable(hc):
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
    return (best[1], (best[2], best[3]), best[0])


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
    return (best[1], (best[2], best[3]), best[0])


def tip_align(ball, hx: float, hy: float, length: float) -> None:
    """把投掷物的**尖**摆到接触点上（中心沿自身轴线回退 length/2）。

    和 Spear.tip() 同一套几何：angle=0 向上、顺时针为正、y 向下。
    """
    ang = math.radians(float(getattr(ball, "angle_deg", 90.0)))
    ball.x = float(hx) - math.sin(ang) * float(length) * 0.5
    ball.y = float(hy) + math.cos(ang) * float(length) * 0.5
