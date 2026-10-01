"""挡路几何纯函数：判 blocker 是否挡在 walker 通往目标的路上，及被顶方顺向让路点。无副作用、可脱离 Qt 单测。"""
from __future__ import annotations

from ..core.creature import WALK_STOP_EPS

# 竖杆上「在同一条线上」的横向容差（杆径很窄，隔壁杆上的猫不算挡路）
POLE_LANE_EPS = 10.0
# 两只都蹲在杆头：杆头只许一只猫，摇摆出的横向偏移不能把对方判成「不在一条线上」
POLE_TIP_LANE_EPS = 24.0


def on_same_pole(a, b) -> bool:
    """两只都在杆上且是同一根杆（竖杆比 pole_x、横杆比 pole_y）。"""
    if not (getattr(a, "on_pole", False) and getattr(b, "on_pole", False)):
        return False
    a_beam = is_beam(a)
    if a_beam != is_beam(b):
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
    if is_beam(a):
        return (abs(a.chunk1.x - b.chunk1.x) < dist
                and abs(a.chunk0.y - b.chunk0.y) < dist)
    lane = POLE_TIP_LANE_EPS if (at_beam_tip(a) and at_beam_tip(b)) else POLE_LANE_EPS
    return (abs(a.chunk0.y - b.chunk0.y) < dist
            and abs(a.chunk0.x - b.chunk0.x) < lane)


# ── 杆上冲突：谁在挤谁（原版 Player：杆上一格一猫、贴身硬挤）──
POLE_ALONG_EPS = 3.0


def is_beam(body) -> bool:
    """横杆位姿 → True；其余 on_pole 位姿按竖杆算。

    统一问身体自己的战斗站位查询（``creature.combat_position``，文档 §7/§11：
    站位状态的定义归 Creature，FSM / blocking 都不再知道 ClimbOnBeam /
    StandOnBeam / HangFromBeam 这些 animation 名字 —— 旧实现还留着一层
    animation 字符串 fallback，等于状态定义有两处）。
    """
    return bool(body.combat_position() == "horizontal")


def pole_along(body) -> float:
    """沿杆位置：竖杆=y（越小越靠杆头），横杆=x。"""
    return body.chunk1.x if is_beam(body) else body.chunk0.y


def pole_along_dir(body) -> float:
    """沿杆运动意图方向：竖杆恒向上(-1)；横杆看行走速度（站着不动=0）。"""
    if not is_beam(body):
        return -1.0
    vx = getattr(body.chunk1, "vx", 0.0)
    if abs(vx) <= 0.5:
        return 0.0
    return 1.0 if vx > 0.0 else -1.0


def pole_push_role(me, other) -> int:
    """我对 other 的杆上角色。+1=我在后面挤它、-1=它在挤我（我在前面）、
    2=互相挤、0=不相干。"""
    if not on_same_pole(me, other):
        return 0
    a_me, a_ot = pole_along(me), pole_along(other)
    if abs(a_me - a_ot) <= POLE_ALONG_EPS:
        return 0
    mine = (a_ot - a_me) * pole_along_dir(me) > POLE_ALONG_EPS
    theirs = (a_me - a_ot) * pole_along_dir(other) > POLE_ALONG_EPS
    if mine and theirs:
        return 2
    if mine:
        return 1
    return -1 if theirs else 0


def pole_rivals(bodies, me, dist) -> list:
    """同一根杆上贴着 me 的其它身体（挤位赛的候选）。"""
    return [b for b in bodies
            if b is not me and pole_in_the_way(me, b, dist)]


def at_beam_tip(body) -> bool:
    """是否蹲在竖杆杆头上（原版 BeamTip）——问身体自己的查询。"""
    return bool(body.on_beam_tip())


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
