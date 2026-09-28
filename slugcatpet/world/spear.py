"""矛 Spear：可放置/拖拽/投掷的长杆（原版 Weapon + Spear）。y↓。

尺寸与物理全部取反编译原值：
  Spear.cs:286-295  bodyChunks[0] rad 5 / mass 0.07；airFriction 0.999；gravity 0.9；
                    bounce 0.4；surfaceFriction 0.4；collisionLayer 2；waterFriction 0.98；
                    buoyancy 0.4
  可视杆长 = 原版 SmallSpear 贴图 53px（锚点在杆中点，同 FSprite anchorY 0.5）
投掷走 world.weaponphys 的 frc 模型；飞行时重力减半；撞墙按原版概率插住。
"""
from __future__ import annotations
import math
import random as _random

from ..core.chunkphys import aabb_wall_collide, apply_water
from ..core.units import clampf
from . import weaponphys as wp
from .enums import ItemState

LEN = 53.0               # 杆长（原版 SmallSpear 贴图可视长度）
HALF_W = 1.6             # 杆的半宽（贴图实测 3px）
RAD = 5.0                # Spear.cs:287 bodyChunks[0].rad
MASS = 0.07              # Spear.cs:287 bodyChunks[0].mass
GRAVITY = 0.9
AIR_FRICTION = 0.999
BOUNCE = 0.4
SURFACE_FRICTION = 0.4
BUOYANCY = 0.4
WATER_FRICTION = 0.98
STUCK_SINK = 7.0         # 插进墙地的深度（原版 stuckInWall 取格心）
FLOOR_EMBED_STEEP = 2.0  # 落地时竖向位移/横向位移超过此值 = 近乎垂直扎进地面（原版 ContactPoint == throwDir）

SPEAR_SHAFT = (94, 78, 60)
SPEAR_TIP = (206, 206, 198)


class Spear:
    """矛：单点质点 + 朝向；插住后不再模拟（原版 Mode.StuckInWall）。"""
    collision_layer = 2

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "_f1", "_seg_new", "_seg_x", "_seg_y",
                 "air_friction", "bounce", "surface_friction", "buoyancy", "water_friction",
                 "water_y", "room_gravity",
                 "state", "angle_deg", "last_angle", "spin", "spinning", "stuck", "stuck_angle",
                 "_id", "_rng", "_contact_floor", "_contact_ceil", "_contact_x", "_impact_cb",
                 "_thrown", "_throw_dir", "_exit_spd", "_throw_x", "_throw_y",
                 "collide_with_objects", "held_by", "embedded", "stuck_to", "_still",
                 "thrower", "no_self_t", "pinned", "pole")

    def __init__(self, x: float, y: float, seed: int = 0, angle_deg: float = 90.0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad, self.mass, self.gravity = RAD, MASS, GRAVITY
        self._f1 = False             # 掷出后的第一帧：last_* 保留出手前的位置
        self._seg_new = False        # 本帧这段位移还没判过命中
        self._seg_x, self._seg_y = float(x), float(y)   # 本帧真正飞到的位置（插墙回摆之前）
        self.air_friction, self.bounce, self.surface_friction = AIR_FRICTION, BOUNCE, SURFACE_FRICTION
        self.buoyancy, self.water_friction = BUOYANCY, WATER_FRICTION
        self.water_y = None
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.angle_deg = self.last_angle = float(angle_deg)
        self.spin = 0.0
        self.spinning = False          # Spear.spinning：翻滚中（控制触地收势）
        self._still = 0                # stillCounter：spinning 期间连续静止帧
        self.stuck = False
        self.stuck_angle = float(angle_deg)
        self.embedded = STUCK_SINK
        self._id = int(seed)
        self._rng = _random.Random(int(seed) * 3571 + 11)
        self._contact_floor = False
        self._contact_ceil = False
        self._contact_x = 0
        self._impact_cb = None
        self._thrown = False
        self._throw_dir = 0
        self._exit_spd = 0.0
        self._throw_x = self._throw_y = 0.0
        self.collide_with_objects = True
        self.thrower = None            # 谁扔的（前 no_self_t 帧不插自己）
        self.no_self_t = 0
        self.held_by = None            # 拾荒者手上
        self.stuck_to = None           # 插在生物身上的 (obj, dx, dy)；由 items 层维护
        self.pinned = False            # 钉成杆子（原版 stuckInWall → beam），不能再被拾取
        self.pole = None               # 由 items 层注册的杆实体（钉住时非 None）

    @property
    def pos(self):
        return (self.x, self.y)

    def collision_chunks(self):
        if (self.stuck or self._thrown
                or self.state in (ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE)):
            self.collide_with_objects = False      # 原版 ChangeMode(Thrown/Stuck) → collisionLayer 0
            return ()
        self.collide_with_objects = True
        return (self,)

    def tip(self):
        """尖端坐标（角度 0=上，y↓）。"""
        a = math.radians(self.stuck_angle if self.stuck else self.angle_deg)
        return (self.x + math.sin(a) * LEN * 0.5, self.y - math.cos(a) * LEN * 0.5)

    def butt(self):
        a = math.radians(self.stuck_angle if self.stuck else self.angle_deg)
        return (self.x - math.sin(a) * LEN * 0.5, self.y + math.cos(a) * LEN * 0.5)

    def stick(self, WL: float, HL: float, wall: int = 0) -> None:
        """插入地面（wall=0）或左右墙（wall=±1）。钉住的矛＝一截同长的杆。"""
        self.stuck = True
        self.pinned = True                         # 原版：stuckInWall 的格子标成 beam
        self._thrown = False
        self.vx = self.vy = 0.0
        self.spin = 0.0
        self.spinning = False
        self._still = 0
        if wall:                                    # 掷进侧墙：杆横着插住
            self.stuck_angle = 90.0 if wall > 0 else 270.0
            self.x = (WL - LEN * 0.5 + self.embedded) if wall > 0 else (LEN * 0.5 - self.embedded)
        else:                                       # 插地：立住
            self.y = HL - LEN * 0.5 + self.embedded
            self.stuck_angle = clampf(self.angle_deg, 45.0, 135.0)

    def unstuck(self) -> None:
        self.stuck = False
        self.pinned = False                        # 拔出来就恢复成普通矛
        self.embedded = STUCK_SINK

    def _enter_free(self) -> None:
        """Weapon.Update 退出 Thrown：SetRandomSpin + ChangeMode(Free)。"""
        self._thrown = False
        self._exit_spd = 0.0
        self.spinning = True
        self._still = 0
        self.spin = wp.spear_random_spin(self._rng, self.room_gravity)

    def rest_on_ground(self) -> None:
        """Spear.Update(Free+spinning) 的收势：停转、速度清零、杆尖朝下插进地面。

        原版：rotation = DegToVec(Lerp(-50,50,rand)+180) —— 杆尖向地，杆身斜插出地面。
        位置不动（不像旧实现那样瞬移到立杆位），所以落地不再有跳动/抖动。
        """
        self.spinning = False
        self._still = 0
        self.spin = 0.0
        self.angle_deg = self.last_angle = 180.0 + self._rng.uniform(-50.0, 50.0)
        self.stuck_angle = self.angle_deg
        self.vx = self.vy = 0.0
        self.stuck = True

    def embed_vertical(self, HL: float) -> None:
        """杆身竖直钉进地面（原版 Spear 撞地：ContactPoint == throwDir 才插住）。

        原版把这种矛所在的格子标成 verticalBeam —— 即「对应长度的竖杆」，
        所以这里把杆摆正、扎进地里，由 items 层注册成一截竖杆；钉住后不再能拾取。
        """
        self.stuck = True
        self._thrown = False
        self.vx = self.vy = 0.0
        self.spin = 0.0
        self.spinning = False
        self._still = 0
        self.pinned = True
        self.angle_deg = self.last_angle = 180.0     # 杆尖朝下
        self.stuck_angle = 180.0
        self.y = HL - LEN * 0.5 + self.embedded

    def step(self, WL: float, HL: float) -> None:
        if self.stuck or self.state in (ItemState.MOUSE, ItemState.CARRIED):
            return
        if self.state == ItemState.GONE:
            return
        if self._f1:
            self._f1 = False             # 原版 firstFrameTraceFromPos：第一帧从出手前扫起
        else:
            self.last_x, self.last_y = self.x, self.y
        self.last_angle = self.angle_deg
        if self.no_self_t > 0:
            self.no_self_t -= 1
        if self._thrown:                            # Spear.Update: vel.y += 0.45f（y↑）
            self.vy -= wp.SPEAR_FLIGHT_LIFT
        self.vy += self.gravity * self.room_gravity
        self.angle_deg = (self.angle_deg + self.spin) % 360.0
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy
        self._seg_new = True                     # 这段位移留给命中判定吃
        self._seg_x, self._seg_y = self.x, self.y   # 插墙会把 x/y 拽回墙内，命中要用飞到的位置
        step_x, step_y = self.x - self.last_x, self.y - self.last_y   # 本 tick 落地方向
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if self._thrown:
            if self._contact_floor:
                # 撞到地面平面即停止物理（原地收势插地）；捡起时 unstuck() 恢复正常。
                # 近乎垂直落下（原版 ContactPoint == throwDir）→ 钉住成竖杆，不再可拾取。
                if step_y > abs(step_x) * FLOOR_EMBED_STEEP:
                    self.embed_vertical(HL)
                else:
                    self.rest_on_ground()
                return
            if self._contact_ceil:
                # 顶边也是平面：不弹，直接清掉竖直速度交给重力落回
                self.vy = 0.0
                self._enter_free()
                return
            if self._contact_x == self._throw_dir:  # Weapon.Update: ContactPoint == throwDir
                if wp.stick_roll(self, self._rng):
                    self.stick(WL, HL, wall=self._throw_dir)
                else:
                    self._enter_free()              # Weapon.HitWall：弹开 + 随机翻滚
            elif wp.exit_check(self):
                self._enter_free()
            return
        # Mode.Free（Spear.cs:470-492）
        moved = math.hypot(self.x - self.last_x, self.y - self.last_y)
        if self.spinning:
            # 翻滚中：触地 或 连续 20 帧几乎不动 → 收势插地
            if moved < 4.0 * self.room_gravity:
                self._still += 1
            else:
                self._still = 0
            if self._contact_floor or self._still > 20:
                self.rest_on_ground()
        elif moved > 6.0:
            # 未翻滚且位移够大 → 起转（SetRandomSpin 后 spinning=True，之后转速固定）
            self.spinning = True
            self._still = 0
            self.spin = wp.spear_random_spin(self._rng, self.room_gravity)
