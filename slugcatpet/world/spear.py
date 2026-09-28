"""矛 Spear：可放置/拖拽投掷的长杆；落地后插进地面立在原地（原版矛会插进墙地）。y↓。"""
from __future__ import annotations
import math

from ..core.chunkphys import aabb_wall_collide
from ..core.units import clampf
from .enums import ItemState

LEN = 46.0               # 杆长
HALF_W = 1.6
MASS = 0.12
GRAVITY = 0.9
AIR_FRICTION = 0.995
BOUNCE = 0.05
SURFACE_FRICTION = 0.9
STICK_SPEED = 2.2        # 撞地速度下限才算「插住」
STUCK_SINK = 7.0         # 插进地面的深度

SPEAR_SHAFT = (94, 78, 60)
SPEAR_TIP = (206, 206, 198)


class Spear:
    """矛：单点质点 + 朝向；落地低速即插入，插住后不再模拟。"""
    collision_layer = 2

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "air_friction", "bounce", "surface_friction", "water_y", "room_gravity",
                 "state", "angle_deg", "last_angle", "spin", "stuck", "stuck_angle",
                 "_id", "_contact_floor", "_contact_x", "_impact_cb",
                 "collide_with_objects", "held_by", "embedded")

    def __init__(self, x: float, y: float, seed: int = 0, angle_deg: float = 90.0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad, self.mass, self.gravity = 2.0, MASS, GRAVITY
        self.air_friction, self.bounce, self.surface_friction = AIR_FRICTION, BOUNCE, SURFACE_FRICTION
        self.water_y = None
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.angle_deg = self.last_angle = float(angle_deg)
        self.spin = 0.0
        self.stuck = False
        self.stuck_angle = float(angle_deg)
        self.embedded = STUCK_SINK
        self._id = int(seed)
        self._contact_floor = False
        self._contact_x = 0
        self._impact_cb = None
        self.collide_with_objects = True
        self.held_by = None            # 拾荒者手上

    @property
    def pos(self):
        return (self.x, self.y)

    def collision_chunks(self):
        if self.stuck or self.state in (ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE):
            self.collide_with_objects = False
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

    def stick(self, WL: float, HL: float) -> None:
        """插入地面/墙面。"""
        self.stuck = True
        self.vx = self.vy = 0.0
        self.spin = 0.0
        if self.y + LEN * 0.5 > HL:                # 插地：立住
            self.y = HL - LEN * 0.5 + self.embedded
            self.stuck_angle = clampf(self.angle_deg, 45.0, 135.0)
        else:                                       # 插墙：贴边斜插
            self.x = clampf(self.x, 2.0, WL - 2.0)
            self.stuck_angle = 90.0

    def unstuck(self) -> None:
        self.stuck = False
        self.embedded = STUCK_SINK

    def step(self, WL: float, HL: float) -> None:
        if self.stuck or self.state in (ItemState.MOUSE, ItemState.CARRIED):
            return
        if self.state == ItemState.GONE:
            return
        self.last_x, self.last_y = self.x, self.y
        self.last_angle = self.angle_deg
        self.vy += self.gravity * self.room_gravity
        self.angle_deg = (self.angle_deg + self.spin) % 360.0
        self.vx *= self.air_friction
        self.x += self.vx
        self.y += self.vy
        speed = math.hypot(self.vx, self.vy)
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if self._contact_floor or self._contact_x:
            if speed < STICK_SPEED or self._contact_floor:
                self.stick(WL, HL)
            else:
                self.spin = 0.0
