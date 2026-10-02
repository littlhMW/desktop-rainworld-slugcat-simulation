"""玩家控制的杆上移动（Player.cs:7631-7998；屏幕坐标 y 向下）。"""
from __future__ import annotations

from ..world.pole import VERTICAL, cross_point

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
        body._ctrl_pole_hang = False
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
        # 原版在竖杆底端不会立刻松手：下压后会进入
        # HangUnderVerticalBeam，身体挂在杆下，向上才重新爬回杆身。
        # 旧实现把到达 bottom 直接 release，导致玩家只能一直上爬/掉杆，
        # 也没有“停在杆下”的过渡姿态。
        if getattr(body, "_ctrl_pole_hang", False):
            _update_vertical_hang(body, pole, inp)
            return
        # Player.cs:7900：竖杆交叉处按横向，换成横杆下方吊挂。
        if inp.x:
            for other in win.poles:
                if other.kind == VERTICAL or cross_point(pole, other) is None:
                    continue
                if abs(body.chunk0.y - other.ay) <= GRAB_R:
                    _switch_to_horizontal(body, other)
                    return
        top, bottom = pole.span_y()
        if inp.x:
            body.facing = inp.x
        y = min(max(body.chunk1.y - inp.y * VERT_SPEED * body.stats.pole_fac,
                    top + body._conn_stand), bottom)
        body.chunk1.x, body.chunk1.y = pole.x, y
        body.chunk0.x, body.chunk0.y = pole.x + body.facing * 5.0, y - body._conn_stand
        body.animation = "BeamTip" if y <= top + body._conn_stand + 1.0 else "ClimbOnBeam"
        if inp.y < 0 and y >= bottom - 1.0:
            # 只在向下输入的上升沿进入吊挂；保持按住下键时让吊挂状态
            # 自己接管，避免下一帧被当成“松杆”。
            _begin_vertical_hang(body, pole)
            return
    else:
        # Player.cs:7660-7670：横杆交叉处按上，转竖杆。
        if inp.y > 0:
            for other in win.poles:
                if other.kind != VERTICAL or cross_point(pole, other) is None:
                    continue
                if abs(body.chunk0.x - other.x) <= GRAB_R:
                    _switch_to_vertical(body, other)
                    return
        lo, hi = pole.span_x()
        if body.animation == "HangFromBeam":
            x = min(max(body.chunk0.x + inp.x * HORIZ_SPEED * body.stats.pole_fac,
                        lo), hi)
            if inp.x:
                body.facing = inp.x
            body.chunk0.x, body.chunk0.y = x, pole.ay
            body.chunk1.x, body.chunk1.y = x, pole.ay + body._conn_stand
            body.chunk0.pinned = body.chunk1.pinned = True
            body.chunk0.vx = body.chunk0.vy = 0.0
            body.chunk1.vx = body.chunk1.vy = 0.0
            body.bodyMode = "ClimbingOnBeam"
            body.standing = False
            body.pole_x, body.pole_y = x, pole.ay
            body.pole_move = inp.x
            if inp.y < 0:
                release(body)
            return
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


def _switch_to_horizontal(body, pole) -> None:
    c0, c1 = body.chunk0, body.chunk1
    body._ctrl_pole = pole
    body._ctrl_pole_hang = False
    body.on_pole = True
    body.standing = False
    body.bodyMode = "ClimbingOnBeam"
    body.animation = "HangFromBeam"
    body.pole_x, body.pole_y = pole.nearest_point(c0.x, pole.ay)
    c0.pinned = True
    c0.x, c0.y = body.pole_x, pole.ay
    c0.vx = c0.vy = 0.0
    c1.pinned = False
    c1.x, c1.y = c0.x, c0.y + body._conn_stand
    c1.vx = c1.vy = 0.0
    body.pole_move = 0


def _switch_to_vertical(body, pole) -> None:
    c0, c1 = body.chunk0, body.chunk1
    top, bottom = pole.span_y()
    y = max(top + body._conn_stand, min(bottom, pole.nearest_point(pole.x, c0.y)[1]))
    body._ctrl_pole = pole
    body._ctrl_pole_hang = False
    body.on_pole = True
    body.standing = True
    body.bodyMode = "ClimbingOnBeam"
    body.animation = "ClimbOnBeam"
    body.pole_x, body.pole_y = pole.x, y
    c0.pinned = c1.pinned = True
    c1.x, c1.y = pole.x, y
    c0.x, c0.y = pole.x + body.facing * 5.0, y - body._conn_stand
    c0.vx = c0.vy = c1.vx = c1.vy = 0.0
    body.pole_move = 0


def _begin_vertical_hang(body, pole) -> None:
    """进入原版 HangUnderVerticalBeam 的底端吊挂姿态。"""
    top, bottom = pole.span_y()
    c0, c1 = body.chunk0, body.chunk1
    body._ctrl_pole_hang = True
    body.bodyMode = "ClimbingOnBeam"
    body.animation = "HangUnderVerticalBeam"
    body.standing = False
    body.on_pole = True
    body.pole_x, body.pole_y = pole.x, bottom
    # 双节保持自然间距，头部在杆底下方，尾/髋下垂；钉住上节避免重力
    # 将吊挂瞬间拉脱，横向移动由下节速度表达。
    c0.pinned = True
    c0.x = pole.x
    c0.y = bottom + c0.rad + 5.0
    c0.vx = c0.vy = 0.0
    c1.pinned = True
    c1.x = pole.x
    c1.y = c0.y + body._conn_stand
    c1.vx = c1.vy = 0.0
    body.pole_move = 0


def _update_vertical_hang(body, pole, inp) -> None:
    """推进竖杆底端吊挂；上键回到杆身，跳键脱离。"""
    c0, c1 = body.chunk0, body.chunk1
    top, bottom = pole.span_y()
    inpbuf = getattr(body, "_ctrl_input", None)
    prev = inpbuf[1] if inpbuf is not None else type(inp)()
    if inp.jmp and not prev.jmp:
        body._ctrl_pole_hang = False
        c0.pinned = c1.pinned = False
        body.on_pole = False
        body.standing = True
        body.animation = None
        c0.vy += 5.0
        c1.vy += 4.0
        c0.vx += float(inp.x) * 3.0
        c1.vx += float(inp.x) * 2.0
        body._ctrl_pole_cd = REGRAB_TICKS
        return
    if inp.y > 0:
        # 向上把头部拉回杆内，之后继续走 ClimbOnBeam。
        body._ctrl_pole_hang = False
        body.standing = True
        body.animation = "ClimbOnBeam"
        c0.pinned = c1.pinned = True
        c0.x = pole.x + body.facing * 5.0
        c0.y = bottom - body._conn_stand
        c1.x = pole.x
        c1.y = bottom
        c0.vx = c0.vy = c1.vx = c1.vy = 0.0
        body.pole_move = 1
        body.bodyMode = "ClimbingOnBeam"
        return
    # 吊挂时横向输入只让下节轻微摆动，身体仍由杆底约束，不会被物理
    # 求解器拉成长条；松开输入时逐帧收回中性姿态。
    body.bodyMode = "ClimbingOnBeam"
    body.animation = "HangUnderVerticalBeam"
    body.standing = False
    body.on_pole = True
    body.pole_move = int(inp.x)
    c0.pinned = True
    c0.x = pole.x
    c0.y = bottom + c0.rad + 5.0
    c0.vx = c0.vy = 0.0
    c1.pinned = True
    c1.x += float(inp.x) * HORIZ_SPEED * 0.35
    c1.x = max(pole.x - 12.0, min(pole.x + 12.0, c1.x))
    c1.y = c0.y + body._conn_stand
    c1.vx = c1.vy = 0.0


def release(body) -> None:
    body.chunk0.pinned = body.chunk1.pinned = False
    body.on_pole = False
    body._ctrl_pole = None
    body._ctrl_pole_hang = False
    body._ctrl_pole_cd = REGRAB_TICKS
    body.animation = None
