"""控制态 拾取 / 投掷（原版 Player.PickUpAndThrow + Player.ThrowObject，y↓）。

对照反编译（反编译对象 = Rain World 本体 Assembly-CSharp）：
- Player.cs:10383-10410  pickUpCandidate = PickupCandidate(20f)：够得着距离 = 被抓节半径 + 40，
                         矛多减 20（favorSpears），朝向那一侧再减 10
- Player.cs:10436        input.thrw 升沿 → wantToThrow
- Player.cs:10544-10584  拾取键：手里有东西先放掉（grasps[0] 右手优先）
- Player.cs:11230-11247  throwDir = (ThrowDirection, 0)；animation == Flip 且
                         input.y != 0 且 input.x == 0 → throwDir = (0, input.y)
- Player.cs:11248-11250  出手点 = firstChunk.pos + throwDir * 10 + (0, 4)
- Player.cs:11276-11308  animation == BellySlide 且 8 < rollCounter < 15 → 抛物增距
- Player.cs:11310-11320  收尾 c0.vel += throwDir * 8 / c1.vel -= throwDir * 4
                         （ClimbOnBeam 且开启爬杆抓握时是 +2 / -8，见 THROW_RECOIL_BEAM）
"""
from __future__ import annotations
import math

from ..world import weaponphys

PICK_R = 40.0                 # PickupCandidate：dist < 被抓节半径 + 40
SPEAR_FAVOR = 20.0            # 同上的 favorSpears
FRONT_BIAS = 10.0             # 朝向那一侧的东西更好抓
PICK_LISTS = (("fruits", "fruit"), ("stones", "stone"), ("spears", "spear"))
BELLY_BOOST_VX = 15.0         # Player.cs:11281 滑铲同向掷 → vel.x += throwDir.x * 15
HEAVY_DOWN = 5.0              # Player.cs:11289 HeavyWeapon 同向掷额外 vel.y -= 5（游戏系向下）
REV_LIFT_SPEAR = 3.0          # Player.cs:11295 反向掷（矛）vel.y += 3（游戏 y↑）
REV_LIFT_OTHER = 5.0          # 非矛 5
REV_KICK_VX = 16.0            # Player.cs:11302 长滑铲反冲
REV_POS_X = 6.0               # Player.cs:11298 bodyChunks[1].pos.x += rollDirection * 6
REV_POS_Y = 17.0              # Player.cs:11299 bodyChunks[1].pos.y += 17（游戏 y↑）
THROW_RECOIL = 8.0            # Player.cs:11316 躯干反冲 8 / 4
THROW_RECOIL_UP = 2.0         # Player.cs:11312 ClimbOnBeam 变体 2 / 8
THROW_RECOIL_DOWN = 8.0


def ctl_throw_update(body) -> None:
    """控制态每帧：拾取/投掷键的上升沿（原版 wantToPickUp / wantToThrow）。"""
    inp = getattr(body, "_ctrl_input", None)
    if inp is None:
        return
    inp0, inp1 = inp[0], inp[1]
    if inp0.pckp and not inp1.pckp:
        ctl_pick_or_drop(body)
    if inp0.thrw and not inp1.thrw:
        ctl_throw(body, inp0)


def _grabbable(o) -> bool:
    """原版 CanIPickThisUp 的桌宠子集：自由态、没被别的猫拿着、不是扎成杆子的矛。"""
    if getattr(o, "state", None) != "free":
        return False
    if getattr(o, "pinned", False):           # 扎进墙/地成杆子的矛拔不动
        return False
    if getattr(o, "held_by_hand", None) is not None:
        return False
    return True


def _pickup_candidate(body, win):
    """最近的可抓物 (obj, kind)；够不着/没有 → None。"""
    if win is None:
        return None
    c0 = body.chunk0
    best, best_d, best_kind = None, 1e9, None
    for name, kind in PICK_LISTS:
        for o in getattr(win, name, ()) or ():
            if not _grabbable(o):
                continue
            d = math.hypot(o.x - c0.x, o.y - c0.y)
            if d > getattr(o, "rad", 0.0) + PICK_R:
                continue
            if kind == "spear":
                d -= SPEAR_FAVOR
            if (o.x < c0.x) == (body.facing < 0):
                d -= FRONT_BIAS
            if d < best_d:
                best, best_d, best_kind = o, d, kind
    if best is None:
        return None
    return best, best_kind


def ctl_pick_or_drop(body) -> None:
    """拾取键：手里有东西先放掉（右手优先），两手都空才去抓最近的可抓物。"""
    for side in ("r", "l"):                   # 原版 grasps[0]（右手）优先
        k = body.held_kind(side)
        if k is not None:
            body._release_item(k, to_free=True)
            return
    got = _pickup_candidate(body, getattr(body, "_ctrl_win", None))
    if got is None:
        return
    o, kind = got
    if kind == "fruit":
        body.grab_fruit(o)
    elif kind == "stone":
        body.grab_stone(o)
    elif kind == "spear":
        body.grab_spear(o)


def ctl_throw(body, inp0) -> None:
    """原版 Player.ThrowObject：右手（grasps[0]）优先，空着用左手。"""
    if not body.item_ready():
        return                                # 上手冷却没走完：先攥着不扔
    kind = body.held_kind("r") or body.held_kind("l")
    if kind not in ("spear", "stone"):
        return
    fdir = 1.0 if body.facing >= 0 else -1.0
    dir_x, dir_y = fdir, 0.0
    if body.animation == "Flip" and inp0.y != 0 and inp0.x == 0:
        # Player.cs:11243：Flip 中按上/下（原版只认 y<0，MMF 开「向上掷矛」后为 (0, y)）
        dir_x, dir_y = 0.0, float(inp0.y)
    weak, toss = weaponphys.player_throw_mode(
        getattr(body, "_ctrl_variant", ""), False, kind == "spear", False)
    frc = weaponphys.frc(weak=weak)
    tossed = False
    if kind == "spear":
        if toss and dir_y == 0.0:             # 圣徒轻抛（TossObject）只有水平分支
            obj = body.throw_spear(dir_x, frc, toss=True)
            tossed = True                     # 轻抛自带它那一份反冲
        else:
            obj = body.throw_spear(dir_x, frc, dir_y=dir_y, recoil=0.0)
    else:
        obj = body.throw_stone(dir_x, frc, fling=True, dir_y=dir_y, recoil=0.0)
    if obj is None:
        return
    _belly_boost(body, obj, dir_x, dir_y, kind)
    if not tossed:
        _recoil(body, dir_x, dir_y)


def _recoil(body, dir_x, dir_y) -> None:
    """Player.cs:11310-11320 投掷反冲（爬杆抓杆时是 +2 / -8）。"""
    c0, c1 = body.chunk0, body.chunk1
    up = getattr(body, "bodyMode", None) == "ClimbingOnBeam"
    a = THROW_RECOIL_UP if up else THROW_RECOIL
    b = THROW_RECOIL_DOWN if up else THROW_RECOIL / 2.0
    c0.vx += dir_x * a
    c0.vy -= dir_y * a
    c1.vx -= dir_x * b
    c1.vy += dir_y * b


def _belly_boost(body, obj, dir_x, dir_y, kind) -> None:
    """Player.cs:11276-11308 抛物增距：滑铲中掷物给动能 / 反向掷触发长滑铲。"""
    if body.animation != "BellySlide" or dir_x == 0.0:
        return
    if not (8 < getattr(body, "_ctrl_roll_counter", 0) < 15):
        return
    rd = body._ctrl_roll_direction
    if dir_x == rd and body.stats.throwing_skill > 0:
        obj.vx += dir_x * BELLY_BOOST_VX      # 同向：掷得更远
        if kind == "spear":                   # HeavyWeapon（矛）
            obj.vy += HEAVY_DOWN              # 游戏 vel.y -= 5 → 屏幕 +
            obj.always_stick = True           # alwaysStickInWalls
    elif dir_x == -rd and not body._ctrl_long_belly:
        obj.vy -= (REV_LIFT_SPEAR if kind == "spear" else REV_LIFT_OTHER)
        body._ctrl_roll_counter = 8
        c0, c1 = body.chunk0, body.chunk1
        c0.x += rd * REV_POS_X
        c1.x += rd * REV_POS_X
        c1.y -= REV_POS_Y                     # 游戏 pos.y += 17 → 屏幕 −
        c0.vx += rd * REV_KICK_VX             # 滑行助推：整体反冲
        c1.vx += rd * REV_KICK_VX
        body._ctrl_exit_belly = 0
        body._ctrl_long_belly = True
