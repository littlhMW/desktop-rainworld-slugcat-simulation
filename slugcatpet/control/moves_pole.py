"""玩家控制的杆上移动（Player.cs:7631-7998；屏幕坐标 y 向下）。"""
from __future__ import annotations

from ..world.pole import VERTICAL

GRAB_R = 13.0
REGRAB_TICKS = 12
VERT_SPEED = 2.4
HORIZ_SPEED = 2.7


def try_grab(body, inp) -> bool:
    """靠近杆并向上操作时抓杆；空中经过杆也可抓。"""
    if body._ctrl_pole_cd > 0 or body.on_pole or body.swimming:
        return False
    if inp.y <= 0 and body.on_floor():
        return False
    win = body._ctrl_win
    if win is None:
        return False
    c0, c1 = body.chunk0, body.chunk1
    for pole in getattr(win, "poles", ()):
        if pole.kind == VERTICAL:
            top, bottom = pole.span_y()
            if abs(c0.x - pole.x) > GRAB_R or not top - GRAB_R <= c0.y <= bottom + GRAB_R:
                continue
            axis = min(max(c1.y, top + body._conn_stand), bottom)
            c1.x, c1.y = pole.x, axis
            c0.x, c0.y = pole.x + body.facing * 5.0, axis - body._conn_stand
            body.animation = "ClimbOnBeam"
        else:
            lo, hi = pole.span_x()
            if not lo - GRAB_R <= c0.x <= hi + GRAB_R or abs(c0.y - pole.ay) > GRAB_R:
                continue
            axis = min(max(c1.x, lo), hi)
            c1.x, c1.y = axis, pole.ay - c1.rad
            c0.x, c0.y = axis, c1.y - body._conn_stand
            body.animation = "StandOnBeam"
        body._ctrl_pole = pole
        body.on_pole = True
        body.standing = True
        body.pole_x, body.pole_y = pole.nearest_point(c0.x, c0.y)
        body.feet_stuck = None
        body.crawl_anchor = None
        body.crawl_pose = 0.0
        body.jump_boost = 0.0
        c0.vx = c0.vy = c1.vx = c1.vy = 0.0
        c0.pinned = c1.pinned = True
        return True
    return False


def update(body) -> None:
    """Player.cs:7836-7885：竖杆 W/S 上下，横杆 A/D 左右；跳键离杆。"""
    pole = body._ctrl_pole
    win = body._ctrl_win
    if pole is None or win is None or pole not in getattr(win, "poles", ()):
        release(body)
        return
    inp = body._ctrl_input[0]
    from .moves_throw import ctl_throw_update
    ctl_throw_update(body)
    if inp.jmp:
        release(body)
        body.pole_jump(body.facing if inp.x == 0 else inp.x,
                       move_dir=inp.x if inp.x else body.facing)
        return
    if pole.kind == VERTICAL:
        top, bottom = pole.span_y()
        if inp.x:
            body.facing = inp.x
        y = min(max(body.chunk1.y - inp.y * VERT_SPEED * body.stats.pole_fac,
                    top + body._conn_stand), bottom)
        body.chunk1.x, body.chunk1.y = pole.x, y
        body.chunk0.x, body.chunk0.y = pole.x + body.facing * 5.0, y - body._conn_stand
        body.animation = "BeamTip" if y <= top + body._conn_stand + 1.0 else "ClimbOnBeam"
        if inp.y < 0 and y >= bottom - 1.0:
            release(body)
            return
    else:
        lo, hi = pole.span_x()
        x = min(max(body.chunk1.x + inp.x * HORIZ_SPEED * body.stats.pole_fac, lo), hi)
        if inp.x:
            body.facing = inp.x
        body.chunk1.x, body.chunk1.y = x, pole.ay - body.chunk1.rad
        body.chunk0.x, body.chunk0.y = x, body.chunk1.y - body._conn_stand
        body.animation = "StandOnBeam"
        if inp.y < 0:
            release(body)
            return
    body.bodyMode = "ClimbingOnBeam"
    body.pole_x, body.pole_y = pole.nearest_point(body.chunk0.x, body.chunk0.y)
    body.chunk0.vx = body.chunk0.vy = 0.0
    body.chunk1.vx = body.chunk1.vy = 0.0
    body.chunk0.pinned = body.chunk1.pinned = True


def release(body) -> None:
    body.chunk0.pinned = body.chunk1.pinned = False
    body.on_pole = False
    body._ctrl_pole = None
    body._ctrl_pole_cd = REGRAB_TICKS
    body.animation = None
