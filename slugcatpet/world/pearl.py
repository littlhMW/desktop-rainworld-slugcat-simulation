"""珍珠 Pearl：小而有弹性的球，落地点弹几下停住；可被鼠标拿起投掷。y↓。"""
from __future__ import annotations
import math

from ..core.chunkphys import aabb_wall_collide, apply_water
from .enums import ItemState

RAD = 4.5
MASS = 0.04
GRAVITY = 0.9
AIR_FRICTION = 0.999
BOUNCE = 0.62            # 原版珍珠很弹
SURFACE_FRICTION = 0.5
BUOYANCY = 0.5
WATER_FRICTION = 0.99

REST_VEL_EPS = 0.5

# 光泽配色（白珍珠 + 彩色高光）
PEARL_CORE = (255, 255, 255)
PEARL_HUES = ((255, 214, 170), (196, 240, 255), (255, 190, 210),
              (214, 255, 208), (232, 214, 255), (255, 248, 196))


class Pearl:
    """珍珠：单点质点 + 自旋；高弹度小球的滚动与落定。"""
    collision_layer = 2

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "air_friction", "bounce", "surface_friction", "buoyancy",
                 "water_friction", "water_y", "room_gravity", "state",
                 "rotation_deg", "last_rotation", "spin", "tint", "_id",
                 "_contact_floor", "_contact_x", "_impact_cb", "collide_with_objects")

    def __init__(self, x: float, y: float, seed: int = 0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad, self.mass, self.gravity = RAD, MASS, GRAVITY
        self.air_friction, self.bounce = AIR_FRICTION, BOUNCE
        self.surface_friction, self.buoyancy, self.water_friction = (
            SURFACE_FRICTION, BUOYANCY, WATER_FRICTION)
        self.water_y = None
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.rotation_deg = 0.0
        self.last_rotation = 0.0
        self.spin = 0.0
        self.tint = PEARL_HUES[int(seed) % len(PEARL_HUES)]
        self._id = int(seed)
        self._contact_floor = False
        self._contact_x = 0
        self._impact_cb = None
        self.collide_with_objects = True

    @property
    def pos(self):
        return (self.x, self.y)

    def collision_chunks(self):
        self.collide_with_objects = self.state not in (
            ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE)
        return (self,) if self.collide_with_objects else ()

    def at_rest_on_ground(self, HL: float) -> bool:
        return (self.y + self.rad >= HL - 0.5
                and abs(self.vx) < REST_VEL_EPS and abs(self.vy) < REST_VEL_EPS)

    def step(self, WL: float, HL: float) -> None:
        if self.state in (ItemState.MOUSE, ItemState.CARRIED):
            self._contact_floor = False
            return
        if self.state == ItemState.GONE:
            return
        self.last_x, self.last_y = self.x, self.y
        self.last_rotation = self.rotation_deg
        self.rotation_deg += self.spin
        self.vy += self.gravity * self.room_gravity
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if self._contact_floor or self._contact_x:
            self.spin = (self.spin * 2.0 + self.vx * 6.0) / 3.0
        if abs(self.vx) < 0.08 and self._contact_floor:
            self.vx = 0.0
            self.spin *= 0.6
