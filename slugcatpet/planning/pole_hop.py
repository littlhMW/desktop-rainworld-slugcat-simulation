"""杆间跳跃规划：从当前杆位带方向（+ 高度档）起跳，找一根『跳过去能在空中抓住』的杆。

原版 Controls/Pole_Movement 的 jump-pole-hopping：站在杆上（竖杆顶或横杆面）
朝一侧 beam jump 跳出，飞行中贴到另一根杆就抓住，于是能一路换杆爬到目的地。

离杆跳有两档高度（都取自反编译 Player.Jump 的 ClimbOnBeam 分支）：
  up=True  小冲量斜跳（同高邻杆；平地起跳弧只覆盖「起跳点以上」那段，目标是下方的
           杆时根本扫不到，必须用实测小跳弧 get_pole_hop_arc）；
  up=False 离杆平跳（原版 input.x==0 / y≤0：胸 vy=+2、vx=2·朝向，够略低/正下方的杆）。

「落到平台面」的轨迹族另见 land_sweep / platform_hop_plan。
"""
from __future__ import annotations

import math

from ..behavior import tuning
from ..world.pole import VERTICAL
from .jump_arc import (get_arc, get_backflip_arc, get_drop_arc, get_jump_fall_arc,
                       get_pole_hop_arc, sweep_hit)

# 轨迹族排序档（同分时先选序号小的：跳 → 跳落 → 落 → 后空翻）
_TIER = {"jump": 0, "jumpfall": 1, "drop": 2, "flip": 3}


def pole_hit(pole, x, y, r):
    """点 (x,y) 是否落在杆身抓取范围（r）内。"""
    if getattr(pole, "kind", None) == VERTICAL:
        lo, hi = min(pole.ay, pole.by), max(pole.ay, pole.by)
        return abs(x - pole.x) <= r and lo - r <= y <= hi + r
    lo, hi = min(pole.ax, pole.bx), max(pole.ax, pole.bx)
    return abs(y - pole.ay) <= r and lo - r <= x <= hi + r


def hop_plan(stats, poles, x, y, exclude=None, grab=None, want=None):
    """从 (x,y) 起跳：返回 (pole, move_dir, hit_ticks, up)，没有则 None。

    want=(tx,ty)：横杆上「要够的东西 / 要跨过去的间隙」那一头。给了它就不再只挑
    「最早抓到的那根」，而是挑**落点离目标最近**的那根 —— 于是猫会按目标的相对位置
    （斜上/斜下、左右、带上下偏移）选方向与力度，而不是原地小跳或直上直下。
    up 是高度档（True 小跳 / False 离杆平跳），同样按 want 挑最省的那档。
    """
    if stats is None or not poles:
        return None
    r = tuning.POLE_AIRGRAB_R if grab is None else grab
    best = None
    for md in (1, -1):
        for up in (True, False):
            arc = get_pole_hop_arc(stats, md, up)
            for p in poles:
                if p is exclude:
                    continue
                for i, (px, py) in enumerate(arc.points):
                    if not pole_hit(p, x + px, y + py, r):
                        continue
                    if want is None:
                        key = (0.0, i)
                    else:
                        hx, hy = x + px, y + py
                        d = math.hypot(hx - want[0], (hy - want[1]) * 0.5)
                        if d > tuning.POLE_HOP_WANT_R:
                            break            # 这根本不在目标那一头：不跳
                        key = (d, i)
                    if best is None or key < best[0]:
                        best = (key, i, p, md, up)
                    break
    if best is None:
        return None
    _, i, p, md, up = best
    return (p, md, i + 1, up)


def beam_jump_plan(stats, x, y, tx, ty, radius=None, holds=None):
    """站在横杆/杆顶：给目标点挑一档「带方向、带距离」的跳跃。返回 (hold, md, hit_ticks)。

    与 hop_plan（跳去抓另一根杆）不同：这里目标是**一个点**（果子/矛/飞虫/杆上缝隙），
    于是在「档位×横向输入」的实测起跳弧里挑最省的一档 —— 档位决定跳多高多远，
    md 决定朝哪边，合起来就是方向与距离参数。够不到返回 None（别白掷骰子）。
    """
    if stats is None:
        return None
    r = tuning.GRAB_REACH if radius is None else radius
    dx, dy = tx - x, ty - y
    dirs = (0,) if abs(dx) < 1e-6 else (0, 1 if dx > 0 else -1)
    best = None
    for hold in (tuning.PLAN_JUMP_HOLD_GEARS if holds is None else holds):
        for md in dirs:
            hit = sweep_hit(get_arc(stats, hold, md), dx, dy, r)
            if hit is None:
                continue
            key = (hold, hit)            # 先省档、再省时间
            if best is None or key < best[0]:
                best = (key, hold, md, hit)
    if best is None:
        return None
    return best[1], best[2], best[3]


def land_sweep(stats, platforms, launches, want=None, holds=None, flips=(),
               land_off=0.0):
    """从若干起跳点 (lx, ly) 起跳，找一条落到平台面上的轨迹。

    轨迹族：
      jump（hold 档 + 横向 md）：够「差不多高、隔着一段间隙」的平台
      jumpfall（同上但一路掉下去）：够「隔一段间隙、而且在下面」的平台
      drop（直接走出杆面 + 横向 md）：够「正下方」的平台
      flip（flips 里的每个 boosted；md 即飞行方向）：后空翻跨间隙 —— 跳不动时的兜底族

    落点判定＝轨迹本 tick 从上往下穿过平台面、且穿越处落在平台跨内（判定穿越而不是
    距离阈值 —— 下落后期每 tick 能掉十几像素，用距离阈值会整段漏掉）。
    land_off：轨迹采的是 chunk0（胸）位移，而猫站上那块面时胸比面高一个站姿胸高
    （TakeoffC0H）—— 不减去它就会把「脚根本没抬过面」的轨迹也算成落地。
    返回 (kind, hold, md, land_x, land_y, ticks, launch_x)；kind=flip 时 hold 是 0/1＝未续力/续力。
    """
    if stats is None or not platforms or not launches:
        return None
    best = None
    for (lx, ly) in launches:
        for md in (1, -1):
            trajs = []
            for hold in (tuning.PLAN_JUMP_HOLD_GEARS if holds is None else holds):
                trajs.append(("jump", hold, get_arc(stats, hold, md).points))
                trajs.append(("jumpfall", hold, get_jump_fall_arc(stats, hold, md).points))
            trajs.append(("drop", 0, get_drop_arc(stats, md).points))
            for boosted in flips:
                trajs.append(("flip", 1 if boosted else 0,
                              get_backflip_arc(stats, md, bool(boosted)).points))
            for kind, hold, pts in trajs:
                prev_y = ly
                below = False
                for i, (px, py) in enumerate(pts):
                    ax, ay = lx + px, ly + py
                    if i < 1 or ay < prev_y:              # 还没离地 / 本 tick 在上升：不算落地
                        prev_y = ay
                        continue
                    for (x0, py0, x1) in platforms:
                        if not (x0 - 2.0 <= ax <= x1 + 2.0):
                            continue
                        # 本 tick 从上往下压到平台面（+6 容差：起跳弧的采样在「踩到地面」
                        # 那一拍就截断了，尾巴可能差几像素没到平台高度）
                        if not (prev_y <= py0 - land_off <= ay + 6.0):
                            continue
                        tier = _TIER[kind]
                        if want is None:
                            key = (0.0, tier, hold, i)
                        else:
                            key = (abs(ax - want[0]) + abs(py0 - want[1]) * 0.5,
                                   tier, hold, i)
                        if best is None or key < best[0]:
                            best = (key, kind, hold, md, ax, py0, i + 1, lx)
                    prev_y = ay
                    if below:
                        break      # 已经掉到所有平台面之下：再往后只会更低
                    below = all(py0 - land_off + 6.0 < ay
                                for (_sx, py0, _ex) in platforms)
    if best is None:
        return None
    return best[1:]


def platform_hop_plan(stats, platforms, x, y, want=None, holds=None):
    """从杆面/地面朝一侧跳/走出去、落到对侧窗口顶边（单向平台）上。

    返回 (kind, hold, md, land_x, land_y)；kind∈{"jump","jumpfall","drop"}。
    实现在 land_sweep（同一套轨迹族与排序档），这里只是单起跳点的写法。
    """
    r = land_sweep(stats, platforms, [(x, y)], want=want, holds=holds)
    return None if r is None else r[:5]

