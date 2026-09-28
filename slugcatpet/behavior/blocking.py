"""挡路几何纯函数：判 blocker 是否挡在 walker 通往目标的路上，及被顶方顺向让路点。无副作用、可脱离 Qt 单测。"""
from __future__ import annotations

from ..core.creature import WALK_STOP_EPS

# 横杆位姿（HangFromBeam/GetUpOnBeam/StandOnBeam）；其余 on_pole 位姿按竖杆算
BEAM_ANIMS = ("HangFromBeam", "GetUpOnBeam", "StandOnBeam")
# 竖杆上「在同一条线上」的横向容差（杆径很窄，隔壁杆上的猫不算挡路）
POLE_LANE_EPS = 10.0


def on_same_pole(a, b) -> bool:
    """两只都在杆上且是同一根杆（竖杆比 pole_x、横杆比 pole_y）。"""
    if not (getattr(a, "on_pole", False) and getattr(b, "on_pole", False)):
        return False
    a_beam = getattr(a, "animation", None) in BEAM_ANIMS
    if a_beam != (getattr(b, "animation", None) in BEAM_ANIMS):
        return False
    if a_beam:
        pa, pb = getattr(a, "pole_y", None), getattr(b, "pole_y", None)
        return pa is not None and pb is not None and abs(pa - pb) < 8.0
    pa, pb = getattr(a, "pole_x", None), getattr(b, "pole_x", None)
    return pa is not None and pb is not None and abs(pa - pb) < 6.0


def pole_in_the_way(a, b, dist) -> bool:
    """同杆上贴得够近 → 互相挡路（竖杆看纵向、横杆看横向）。"""
    if not on_same_pole(a, b):
        return False
    if getattr(a, "animation", None) in BEAM_ANIMS:
        return (abs(a.chunk1.x - b.chunk1.x) < dist
                and abs(a.chunk0.y - b.chunk0.y) < dist)
    return (abs(a.chunk0.y - b.chunk0.y) < dist
            and abs(a.chunk0.x - b.chunk0.x) < POLE_LANE_EPS)


def _sign(v: float) -> float:
    return 1.0 if v > 0.0 else (-1.0 if v < 0.0 else 0.0)


def blocks_path(blocker_x, walker_x, walker_target_x, contact_dist) -> bool:
    """blocker 是否正挡在 walker 前进方向上且已接触。"""
    if walker_target_x is None:
        return False
    d = walker_target_x - walker_x
    if abs(d) <= WALK_STOP_EPS:
        return False
    rel = (blocker_x - walker_x) * _sign(d)
    return 0.0 < rel <= contact_dist


def yield_target_x(walker_x, walker_target_x, lo, hi, clear_pad) -> float:
    """被顶方顺向让路目标：让到对方目标点外 clear_pad，clamp 到走带内（对方抵墙时只让到墙边）。"""
    s = _sign(walker_target_x - walker_x)
    return min(max(walker_target_x + s * clear_pad, lo), hi)
