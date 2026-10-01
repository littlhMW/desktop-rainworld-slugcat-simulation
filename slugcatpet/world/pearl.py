"""珍珠 Pearl：小而有弹性的球，落地点弹几下停住；可被鼠标拿起投掷。y↓。"""
from __future__ import annotations
import math
import random as _random

from ..core.chunkphys import aabb_wall_collide, apply_water
from .enums import ItemState
from .combat import CombatTarget

RAD = 5.0                # DataPearl.cs:184 bodyChunks[0].rad
MASS = 0.07              # DataPearl.cs:184 bodyChunks[0].mass
GRAVITY = 0.9
AIR_FRICTION = 0.999
BOUNCE = 0.4             # DataPearl.cs:188
SURFACE_FRICTION = 0.4   # DataPearl.cs:189
BUOYANCY = 0.4           # DataPearl.cs:192
WATER_FRICTION = 0.98    # DataPearl.cs:191

REST_VEL_EPS = 0.5

# 品种色：原版 DataPearl.ApplyPalette / UniquePearlMainColor（非 MSC 分支）
PEARL_CORE = (255, 255, 255)
PEARL_HUES = ((233, 233, 233),            # Misc：通用白珍珠
              (255, 153, 230),            # Misc2
              (230, 153, 26),             # CC
              (0, 179, 26),               # DS
              (0, 179, 128),              # GW
              (2, 50, 255),               # HI
              (255, 26, 26),              # LF_bottom
              (255, 0, 77),               # LF_west
              (26, 128, 128),             # SB_filtration
              (51, 0, 26),                # SH
              (230, 242, 51),             # SL_moon
              (102, 26, 230),             # SL_bridge
              (128, 153, 230),            # SU
              (102, 153, 102),            # UW
              (255, 0, 140),              # SL_chimney
              (153, 255, 230),            # Red_stomach
              (179, 179, 179),            # PebblesPearl 1
              (255, 122, 2),              # PebblesPearl 2/3（橙）
              (0, 116, 163))              # PebblesPearl 2（<0，蓝）
GLIMMER_SPEED = (1.0 / 5.0, 1.0 / 15.0)   # 原版 glimmerSpeed = 1/Lerp(5,15,rand)
GLIMMER_WAIT = (20, 40)                   # 原版 glimmerWait


class Pearl(CombatTarget):
    """珍珠：单点质点 + 自旋；高弹度小球的滚动与落定。"""
    collision_layer = 2
    is_edible = False        # 不能吃：原版里珍珠是货币

    # stalk = 复用果子的叼持槽（猫叼珍珠时就当果子槽用）
    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "stalk",
                 "air_friction", "bounce", "surface_friction", "buoyancy",
                 "water_friction", "water_y", "room_gravity", "state",
                 "rotation_deg", "last_rotation", "spin", "tint", "_id",
                 "_contact_floor", "_contact_x", "_impact_cb", "collide_with_objects",
                 "glimmer", "last_glimmer", "glimmer_prog", "glimmer_speed",
                 "glimmer_wait", "_glimmer_amp", "held_by_hand")

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
        self.stalk = None              # 复用果子的叼持槽
        self.rotation_deg = 0.0
        self.last_rotation = 0.0
        self.held_by_hand = None       # "scav" = 被拾荒者拿着（交易用）
        self.spin = 0.0
        self.tint = PEARL_HUES[int(seed) % len(PEARL_HUES)]
        self._id = int(seed)
        self._contact_floor = False
        self._contact_x = 0
        self._impact_cb = None
        self.collide_with_objects = True
        # 原版高光脉冲：glimmerProg 走 0→1，glimmer = sin(prog*π) * 随机幅度，然后停一会儿
        rng = _random.Random(seed * 4409 + 7)
        self.glimmer = self.last_glimmer = 0.0
        self.glimmer_prog = rng.random()
        self.glimmer_speed = rng.uniform(*GLIMMER_SPEED)
        self.glimmer_wait = 0
        self._glimmer_amp = rng.random()

    @property
    def pos(self):
        return (self.x, self.y)

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        """被抓在手里：珠子无尖端，停自旋即可（对齐 Fruit 的同名接口）。"""
        self.spin = 0.0
        self.last_rotation = self.rotation_deg

    def glimmer_at(self, ts: float) -> float:
        """插值后的高光强度（绘制用）。"""
        return self.last_glimmer + (self.glimmer - self.last_glimmer) * ts

    def collision_chunks(self):
        self.collide_with_objects = self.state not in (
            ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE)
        return (self,) if self.collide_with_objects else ()

    def _step_glimmer(self) -> None:
        """原版 DataPearl.Update 的高光脉冲。"""
        self.glimmer = math.sin(self.glimmer_prog * math.pi) * self._glimmer_amp
        if self.glimmer_prog < 1.0:
            self.glimmer_prog = min(1.0, self.glimmer_prog + self.glimmer_speed)
        elif self.glimmer_wait > 0:
            self.glimmer_wait -= 1
        else:
            self.glimmer_wait = _random.randint(*GLIMMER_WAIT)
            self.glimmer_prog = 0.0
            self.glimmer_speed = _random.uniform(*GLIMMER_SPEED)
            self._glimmer_amp = _random.random()

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
        self.last_glimmer = self.glimmer
        self._step_glimmer()
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
