"""飞虫够取规划：走到飞行轨迹下方 → 起跳滞空伸手抓住（原版 Player 上手抓 Fly/Cicada）。

和 jump_reach 同一套跳跃弧模型（枚举档位×左右，逐点扫掠），只是把命中半径换成
抓取半径抓活虫。喂给 _nearest_catchable / FlyCatcher._candidates 当认距闸，
于是「空中抓蝙蝠/蝉乌贼/幼面条蝇」也是正经寻路，而不是只看直线距离。
"""
from __future__ import annotations

import math

from ..behavior import tuning
from .ability import walk_band
from .jump_arc import get_arc, sweep_hit


def fly_reach_plan(pet, obj, radius=None):
    """返回 (walk_x, hold, move_dir, hit_ticks)；够不到则 None。"""
    body = getattr(pet, "body", None)
    if body is None or obj is None:
        return None
    r = tuning.CATCH_REACH if radius is None else radius
    ox, oy = obj.x, obj.y
    c0 = body.chunk0
    side = "r" if ox >= c0.x else "l"
    hx, hy = body._carry_pos(side)
    if not body.on_floor() and math.hypot(hx - ox, hy - oy) <= r:
        return (c0.x, 0, 0, 0)          # 已经在空中且贴到手边：本 tick 就抓
    if getattr(body, "on_pole", False):
        return None
    if getattr(body, "carried_fruit", None) is not None or getattr(body, "zerog", False):
        return None
    stats = getattr(getattr(pet, "cat", None), "stats", None)
    if stats is None:
        return None
    xmin, xmax = walk_band(pet)
    floor = getattr(pet, "_HL", None)
    if floor is None:
        return None
    hipx = body.chunk1.x
    best = None
    for hold in tuning.PLAN_JUMP_HOLD_GEARS:
        arc0 = get_arc(stats, hold, 0)
        if xmin <= ox <= xmax:
            dy = oy - (floor - arc0.takeoff_h)
            hit = sweep_hit(arc0, 0.0, dy, r)
            if hit is not None:
                t = abs(hipx - ox) / tuning.PLAN_WALK_SPEED + hit
                if best is None or t < best[0]:
                    best = (t, ox, hold, 0, hit)
        for md in (1, -1):
            arc = get_arc(stats, hold, md)
            ty = floor - arc.takeoff_h
            for i, (px, py) in enumerate(arc.points):
                lx = ox - px
                if not (xmin <= lx <= xmax):
                    continue
                if abs((ty + py) - oy) <= r:
                    t = abs(hipx - lx) / tuning.PLAN_WALK_SPEED + i + 1
                    if best is None or t < best[0]:
                        best = (t, lx, hold, md, i + 1)
                    break
    if best is None:
        return None
    return best[1:]


def in_reach(pet, obj, radius=None):
    """认距闸：直线够近，或者一跳就能抓住。"""
    body = getattr(pet, "body", None)
    if body is None or obj is None:
        return False
    c0 = body.chunk0
    d = math.hypot(obj.x - c0.x, obj.y - c0.y)
    if d <= tuning.CATCH_SEEK_R:
        return True
    if d > tuning.CATCH_PLAN_R:
        return False
    return fly_reach_plan(pet, obj, radius) is not None
