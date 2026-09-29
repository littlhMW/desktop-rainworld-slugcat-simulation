"""原版 Weapon 投掷/飞行物理（矛 / 石头 / 珍珠共用）。y↓（游戏 y↑，凡 y 分量取反）。

对照反编译（反编译对象 = Rain World 本体 Assembly-CSharp）：
- Weapon.Thrown                    → throw_velocity / begin_thrown / exit_thrown_speed
- Weapon.Update 的 Mode.Thrown     → exit 阈值、ContactPoint == throwDir → HitWall
- Spear.Update 的 Mode.Thrown      → 每 tick vel.y += 0.45（矛飞行时重力减半）
- Spear.Update 的插墙判定          → 距离 + 33% 概率
- Weapon.SetRandomSpin            → 退出投掷后翻滚
数值（Weapon.cs:66/68/92、Weapon.cs:463-502、Spear.cs:472）：
    exitThrownModeSpeed = 30；overrideExitThrownSpeed = frc<1 ? Min(30, frc*20) : 0
    vel.x = owner.mainBodyChunk.vel.x * 0.2 + throwDir.x * 40 * frc
    vel.y = owner.mainBodyChunk.vel.y * 0.5 + (矛 1.5 / 其它 3)
"""

from __future__ import annotations
import math

THROW_POWER = 40.0            # Weapon.Thrown: throwDir.x * 40f * frc
LIFT_SPEAR = 1.5              # 矛掷出时的上抬（游戏 y↑）
LIFT_WEAPON = 3.0             # 石头/珍珠的上抬
EXIT_THROWN_SPEED = 30.0      # Weapon.exitThrownModeSpeed 默认值
WEAK_EXIT_K = 20.0            # frc < 1 → overrideExitThrownSpeed = Min(30, frc * 20)
SPEAR_FLIGHT_LIFT = 0.45      # Spear.Update: vel.y += 0.45f（只抵掉一半重力）
SPEAR_FLIGHT_FLAT_PX = 110.0  # 掷出的矛先平飞这一段（这段内上抬抵掉重力），过了这段
                              # 回落到原版的 0.45 上抬 → 半重力自然下落。
                              # 用户点名要「投出的矛需要有一段距离自然下落的物理」；
                              # 平飞段只改出手后的头一段，远处弹道与原版逐帧一致。
STICK_MAX_DIST = 560.0        # 超出这个飞行距离不再插墙
STICK_NEAR_DIST = 140.0       # 近距离必定插墙
STICK_CHANCE = 0.33           # 远距离插墙概率（ExplosiveSpear 才 0.8）
FRC_NORMAL = (1.0, 1.5)       # Player.ThrowObject: Lerp(1, 1.5, Adrenaline)
FRC_WEAK = (0.5, 0.75)        # 圣徒 / 力竭：Lerp(0.5, 0.75, Adrenaline)
FRC_SCAVENGER = 0.35          # Scavenger.ThrowObject（DLC 普通个体）
FRC_SCAVENGER_ELITE = 0.75    # Elite / Templar
SPIN_MIN, SPIN_MAX = 100.0, 100.0   # Weapon.SetRandomSpin: Lerp(-100, 100, rand)
# Spear 覆写 SetRandomSpin（Spear.cs:1150）：(±1) * Lerp(50, 150, rand) * Lerp(0.05, 1, gravity)
SPEAR_SPIN_MIN, SPEAR_SPIN_MAX = 50.0, 150.0


def frc(adrenaline: float = 0.0, weak: bool = False) -> float:
    """Player.ThrowObject 的力系数。"""
    a, b = FRC_WEAK if weak else FRC_NORMAL
    t = 0.0 if adrenaline < 0.0 else (1.0 if adrenaline > 1.0 else adrenaline)
    return a + (b - a) * t


def exit_thrown_speed(frc_value: float) -> float:
    """Weapon.Thrown 末尾的 overrideExitThrownSpeed（0 表示用默认 30）。"""
    if frc_value >= 1.0:
        return EXIT_THROWN_SPEED
    return min(EXIT_THROWN_SPEED, frc_value * WEAK_EXIT_K)


def throw_velocity(c0, dir_x: float, is_spear: bool, frc_value: float):
    """水平投掷分支的初速 (vx, vy)。c0 = 投掷者 mainBodyChunk。"""
    vx = c0.vx * 0.2 + float(dir_x) * THROW_POWER * frc_value
    vy = c0.vy * 0.5 - (LIFT_SPEAR if is_spear else LIFT_WEAPON)
    return vx, vy


def begin_thrown(obj, dir_x: float, frc_value: float) -> None:
    """进入 Mode.Thrown：记投掷方向、退出阈值与投掷起点。"""
    obj._thrown = True
    obj._f1 = True               # 第一帧的扫掠起点＝出手前的位置（原版 firstFrameTraceFromPos）
    obj._throw_dir = 1 if dir_x >= 0.0 else -1
    obj._exit_spd = exit_thrown_speed(frc_value)
    obj._throw_x = obj.x
    obj._throw_y = obj.y


def exit_check(obj) -> bool:
    """Weapon.Update(Thrown)：vel.magnitude < num → SetRandomSpin + ChangeMode(Free)。"""
    return obj._thrown and math.hypot(obj.vx, obj.vy) < obj._exit_spd


def stick_roll(obj, rng) -> bool:
    """Spear.Update 的插墙判定：飞太远不插；近处必插，远处 33%。"""
    d = math.hypot(obj.x - obj._throw_x, obj.y - obj._throw_y)
    if d > STICK_MAX_DIST:
        return False
    return d < STICK_NEAR_DIST or rng.random() < STICK_CHANCE


def set_random_spin(rng, room_gravity: float = 1.0) -> float:
    """Weapon.SetRandomSpin：rotationSpeed = Lerp(-100, 100, rand) * Lerp(0.05, 1, roomGravity)。"""
    k = 0.05 + 0.95 * (0.0 if room_gravity < 0.0 else (1.0 if room_gravity > 1.0 else room_gravity))
    return rng.uniform(-SPIN_MIN, SPIN_MAX) * k


def spear_random_spin(rng, room_gravity: float = 1.0) -> float:
    """Spear.SetRandomSpin：固定正负号，幅值 Lerp(50, 150, rand)（矛比石头轻，翻滚更稳）。"""
    k = 0.05 + 0.95 * (0.0 if room_gravity < 0.0 else (1.0 if room_gravity > 1.0 else room_gravity))
    sgn = -1.0 if rng.random() < 0.5 else 1.0
    return sgn * rng.uniform(SPEAR_SPIN_MIN, SPEAR_SPIN_MAX) * k


def vel_angle(vx: float, vy: float) -> float:
    """投掷物朝向角：0=上、顺时针为正（y↓），与 Spear.tip()/draw_spear 一致。"""
    if abs(vx) < 1e-9 and abs(vy) < 1e-9:
        return 90.0
    return math.degrees(math.atan2(vx, -vy)) % 360.0


# ── Player.TossObject（轻抛：圣徒投矛、非武器投掷）──
# Player.cs:11577-11707，input.x != 0 && y == 0 分支：
#   num  = LerpMap(mass, 0.2, 0.3, 60, 50)        → mass < 0.2 时夹到 60
#   num2 = LerpMap(mass, 0.2, 0.3, 12.5, 8, exp 2) → mass < 0.2 时夹到 12.5
#   Grabability == OneHand → num2 *= 2、num = 70（矛是 BigOneHand，不翻倍）
#   vel = Lerp(vel * 0.35, owner.mainBodyChunk.vel, LerpMap(mass, 0.2, 0.5, 0.6, 0.3))
#   vel += Custom.DegToVec(num * ThrowDirection) * Clamp(num2 / (Lerp(mass, 0.4, 0.2) * chunks), 4, 14)
# 轻抛不进 Mode.Thrown（不插墙、无退出阈值），只是 Free + 速度。
TOSS_NUM_H = 60.0            # 水平轻抛角度（DegToVec 的角，0 = 正上，顺时针为正）
TOSS_NUM2_H = 12.5           # 轻抛力度基数
TOSS_NUM_ONE_HAND = 70.0     # Grabability.OneHand 时的角度
TOSS_ADD_MIN, TOSS_ADD_MAX = 4.0, 14.0
TOSS_VEL_LERP = (0.2, 0.5, 0.6, 0.3)   # LerpMap(mass, 0.2, 0.5, 0.6, 0.3)
TOSS_MASS_LERP = (0.4, 0.2)            # Lerp(mass, 0.4, 0.2)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clampf(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _lerpmap(v: float, a: float, b: float, ra: float, rb: float) -> float:
    """Custom.LerpMap：v 在 [a, b] 外夹取，inside 线性插值。"""
    if b == a:
        return ra
    return _lerp(ra, rb, _clampf((v - a) / (b - a), 0.0, 1.0))


def toss_velocity(c0, dir_x: float, mass: float, chunk_count: int = 1,
                  carry_factor: float = 1.0, one_hand: bool = False):
    """Player.TossObject 的水平轻抛初速 (vx, vy)（屏幕 y↓）。"""
    num = TOSS_NUM_H
    num2 = TOSS_NUM2_H
    if one_hand:
        num2 *= 2.0
        num = TOSS_NUM_ONE_HAND
    num2 *= carry_factor
    k = _lerpmap(mass, *TOSS_VEL_LERP)
    vx0 = c0.vx
    vy0 = min(c0.vy, 0.0)          # 游戏系 vel.y < 0（下落）先夹到 0
    vx = _lerp(vx0 * 0.35, vx0, k)
    vy = _lerp(vy0 * 0.35, vy0, k)
    add = _clampf(num2 / (_lerp(mass, *TOSS_MASS_LERP) * max(1, int(chunk_count))),
                  TOSS_ADD_MIN, TOSS_ADD_MAX)
    ang = math.radians(num * float(dir_x))
    vx += math.sin(ang) * add      # Custom.DegToVec = (sin, cos)，游戏 y↑ → 屏幕取反
    vy += -math.cos(ang) * add
    return vx, vy


def player_throw_mode(variant: str, exhausted: bool, is_spear: bool, is_rock: bool):
    """Player.ThrowObject 的三个分支 → (weak, toss)。

    Player.cs:11250-11264：圣徒投矛走 TossObject；圣徒投非石头 / 力竭 → frc 减半档。
    """
    saint = (variant == "saint")
    if saint and is_spear:
        return (False, True)
    return (bool(exhausted) or (saint and not is_rock), False)
