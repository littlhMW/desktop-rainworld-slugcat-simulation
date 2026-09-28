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

SPEAR_SHAFT = (94, 78, 60)
SPEAR_TIP = (206, 206, 198)


class Spear:
    """矛：单点质点 + 朝向；插住后不再模拟（原版 Mode.StuckInWall）。"""
    collision_layer = 2

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "air_friction", "bounce", "surface_friction", "buoyancy", "water_friction",
                 "water_y", "room_gravity",
                 "state", "angle_deg", "last_angle", "spin", "stuck", "stuck_angle",
                 "_id", "_rng", "_contact_floor", "_contact_x", "_impact_cb",
                 "_thrown", "_throw_dir", "_exit_spd", "_throw_x", "_throw_y",
                 "collide_with_objects", "held_by", "embedded", "stuck_to")

    def __init__(self, x: float, y: float, seed: int = 0, angle_deg: float = 90.0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad, self.mass, self.gravity = RAD, MASS, GRAVITY
        self.air_friction, self.bounce, self.surface_friction = AIR_FRICTION, BOUNCE, SURFACE_FRICTION
        self.buoyancy, self.water_friction = BUOYANCY, WATER_FRICTION
        self.water_y = None
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.angle_deg = self.last_angle = float(angle_deg)
        self.spin = 0.0
        self.stuck = False
        self.stuck_angle = float(angle_deg)
        self.embedded = STUCK_SINK
        self._id = int(seed)
        self._rng = _random.Random(int(seed) * 3571 + 11)
        self._contact_floor = False
        self._contact_x = 0
        self._impact_cb = None
        self._thrown = False
        self._throw_dir = 0
        self._exit_spd = 0.0
        self._throw_x = self._throw_y = 0.0
        self.collide_with_objects = True
        self.held_by = None            # 拾荒者手上
        self.stuck_to = None           # 插在生物身上的 (obj, dx, dy)；由 items 层维护

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
        """插入地面（wall=0）或左右墙（wall=±1）。"""
        self.stuck = True
        self._thrown = False
        self.vx = self.vy = 0.0
        self.spin = 0.0
        if wall:                                    # 掷进侧墙：杆横着插住
            self.stuck_angle = 90.0 if wall > 0 else 270.0
            self.x = (WL - LEN * 0.5 + self.embedded) if wall > 0 else (LEN * 0.5 - self.embedded)
        else:                                       # 插地：立住
            self.y = HL - LEN * 0.5 + self.embedded
            self.stuck_angle = clampf(self.angle_deg, 45.0, 135.0)

    def unstuck(self) -> None:
        self.stuck = False
        self.embedded = STUCK_SINK

    def _enter_free(self) -> None:
        """Weapon.ChangeMode(Free)：SetRandomSpin + 退出投掷态。"""
        self._thrown = False
        self._exit_spd = 0.0
        self.spin = wp.set_random_spin(self._rng, self.room_gravity)

    def step(self, WL: float, HL: float) -> None:
        if self.stuck or self.state in (ItemState.MOUSE, ItemState.CARRIED):
            return
        if self.state == ItemState.GONE:
            return
        self.last_x, self.last_y = self.x, self.y
        self.last_angle = self.angle_deg
        if self._thrown:                            # Spear.Update: vel.y += 0.45f（y↑）
            self.vy -= wp.SPEAR_FLIGHT_LIFT
        self.vy += self.gravity * self.room_gravity
        self.angle_deg = (self.angle_deg + self.spin) % 360.0
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if self._thrown:
            if self._contact_x == self._throw_dir:  # Weapon.Update: ContactPoint == throwDir
                if wp.stick_roll(self, self._rng):
                    self.stick(WL, HL, wall=self._throw_dir)
                else:
                    self._enter_free()              # Weapon.HitWall：弹开 + 随机翻滚
            elif wp.exit_check(self):
                self._enter_free()
            return
        # Mode.Free：位移够大就乱转（原版 !DistLess(lastPos, pos, 6f) → SetRandomSpin）
        if math.hypot(self.x - self.last_x, self.y - self.last_y) > 6.0:
            self.spin = wp.set_random_spin(self._rng, self.room_gravity)
        if self._contact_floor:                     # 旋转中的矛碰地即插住
            self.stick(WL, HL)
