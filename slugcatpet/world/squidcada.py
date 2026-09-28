"""蝉乌贼 Squidcada：悬停飞行的可抓生物（原版 Cicada）。y↓。

被蛞蝓猫抓住后可喂给蜥蜴——原版蜥蜴驯服就是「收到礼物」：
FriendTracker.GiftRecieved → like += 活体 0.6 / 尸体 1.2，like > 0.5 即跟随。
接口对齐 Fruit/BatFly（state/held_by_hand/stalk/bites/bite()/die()/set_rotation_to_grabber）。
"""
from __future__ import annotations
import math
import random as _random

from ..core.chunkphys import aabb_wall_collide, apply_water
from ..core.units import clampf, lerp, inv_lerp
from .enums import ItemState

RAD = 7.5                 # Cicada.cs:131 bodyChunks[0].rad
MASS = 0.3                # Cicada.cs:129 总质量 0.65(雄)/0.55(雌)，单点取均值
GRAVITY = 0.9             # Cicada.cs:136
AIR_FRICTION = 0.999
BOUNCE = 0.1              # Cicada.cs:137
SURFACE_FRICTION = 0.4    # Cicada.cs:138
BUOYANCY = 0.95           # Cicada.cs:141
WATER_FRICTION = 0.96     # Cicada.cs:140

HOVER_H = 78.0            # 巡航高度（离地）
HOVER_BAND = 18.0         # 高度带：出带才修正
FLAP_PERIOD = 34          # 扑翅周期 tick
FLAP_THRUST = 3.4         # 每周期上冲
DRIFT_ACCEL = 0.10
DRIFT_REPICK = 150

FLEE_R = 82.0             # 猫进此圈即逃
FLEE_ACCEL = 0.34
PANIC_R = 34.0            # 休息时贴脸才炸飞
FLAPS_MAX = 60            # 体力：可连续扑翅次数（大幅拉长，几乎不用休息）
REST_TICKS = 70           # 力竭落地休息时长（歇一会儿就能再飞）
FLEE_FLAP_COST = 6        # 逃命时每扑一次翅多耗几格体力（巡航不耗）
EATEN_COUNTDOWN = 3

WALL_MARGIN = 20.0


class Squidcada:
    """蝉乌贼：悬停游走 → 遇猫扑翅逃 → 力竭落地（此时可被猫抓住）。"""
    collision_layer = 0

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y",
                 "rad", "mass", "gravity", "air_friction", "bounce", "surface_friction",
                 "buoyancy", "water_friction", "water_y", "room_gravity",
                 "state", "held_by_hand", "stalk", "bites", "dead", "eaten",
                 "is_meat", "is_tame_food", "food_value", "health",
                 "collide_with_objects", "_id", "_impact_cb",
                 "male", "hue", "_rng", "flap", "flap_ph", "rest", "flaps", "wings",
                 "dir_x", "dir_y", "facing", "rotation", "last_rotation",
                 "_goal", "_goal_timer", "_contact_floor", "_contact_x")

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
        self.held_by_hand = None
        self.stalk = None                  # 接口占位，恒 None
        self.bites = 3                     # 活体肉食：3 口才吃完（合计 3 格食物）
        self.dead = False
        self.eaten = 0
        self.is_meat = True                # 原版：蝉乌贼是肉食（3 口 = 3 格食物）
        self.is_tame_food = True
        self.food_value = 3                # 原版：一只蝉乌贼 3 格食物
        self.health = 1.0        # 原版 HealthState 初始 1.0
        self.collide_with_objects = True
        self._id = int(seed)
        self._impact_cb = None
        rng = self._rng = _random.Random(seed * 6151 + 7)
        self.male = rng.random() < 0.5     # 原版：雄性偏白、雌性偏黑
        self.hue = 0.55 + rng.uniform(-0.1, 0.1)   # 原版个体色相（蓝紫）
        self.flap = rng.random()
        self.flap_ph = rng.random() * math.tau
        self.rest = 0
        self.flaps = FLAPS_MAX
        self.wings = [self.flap, self.flap]
        self.dir_x, self.dir_y = (1.0 if rng.random() < 0.5 else -1.0), 0.0
        self.facing = 1 if self.dir_x >= 0 else -1
        self.rotation = self.last_rotation = (0.0, -1.0)
        self._goal = (self.x + rng.uniform(-60.0, 60.0), self.y)
        self._goal_timer = 0
        self._contact_floor = False
        self._contact_x = 0

    # ── 查询 ──
    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def resting(self) -> bool:
        return self.rest > 0

    @property
    def fetch_ready(self) -> bool:
        """走过去的取食路径：力竭落地才够得到。"""
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and (self.dead or self.rest > 0))

    @property
    def catchable(self) -> bool:
        """能徒手抓上来：活着且没被别的嘴叼着（飞行中也能抓）。"""
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and not self.dead)

    @property
    def airborne(self) -> bool:
        """是否在飞。"""
        return not self.dead and self.state == ItemState.FREE and self.rest <= 0

    def collision_chunks(self):
        self.collide_with_objects = self.state not in (
            ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE) and not self.dead
        return (self,) if self.collide_with_objects else ()

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        self.last_rotation = self.rotation
        dx, dy = _dirvec(self.x, self.y, gx, gy)
        self.rotation = (dy, -dx) if self.dead else (dy, -abs(dx))

    def bite(self) -> bool:
        """被咬一口：必死，并计入被吃倒计时。"""
        self.die()
        if self.eaten == 0:
            self.eaten = EATEN_COUNTDOWN
            return True
        return False

    DAMAGE_RESISTANCE = 0.8       # 原版 StaticWorld: CicadaA baseDamageResistance = 0.8

    def hurt(self, dmg: float, kx: float = 0.0, ky: float = 0.0) -> bool:
        """被武器打中：原版 Violence 的 num = damage / baseDamageResistance。

        矛 1.0 / 0.8 = 1.25 ≥ 1.0 → 一矛即死；石头 0.01 / 0.8 → 只被震飞，打不死。
        """
        self.vx += kx
        self.vy += ky
        if self.health > 0.0:
            self.health -= dmg / self.DAMAGE_RESISTANCE
        if self.health <= 0.0 and not self.dead:
            self.die()
            return True
        return self.dead

    def die(self) -> None:
        self.dead = True
        self.bites = 3                     # 刚死的蝉乌贼同样是 3 口
        self.surface_friction = 0.4

    # ── 主循环 ──
    def step(self, WL: float, HL: float, threats=()) -> None:
        if self.state in (ItemState.MOUSE, ItemState.CARRIED):
            return
        self.last_x, self.last_y = self.x, self.y
        if self.state == ItemState.GONE:
            return
        if self.eaten > 0:
            self.eaten -= 1
            if self.eaten == 0:
                self.state = ItemState.EATEN
                return

        if self.dead:                        # 尸体：普通坠落
            self.vy += self.gravity * self.room_gravity
            apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                        self.room_gravity, self.air_friction)
            self.vx *= self.air_friction
            self.x += self.vx
            self.y += self.vy
            self._collide(WL, HL)
            return

        self._flight(WL, HL, threats)

    def _flight(self, WL, HL, threats) -> None:
        """悬停巡航 / 逃 / 力竭歇；贴地后自然落地。"""
        floor = HL
        want_y = floor - HOVER_H
        tx, ty, flee = None, None, False
        bestd = FLEE_R
        for obj, ox, oy in threats:
            d = math.hypot(ox - self.x, oy - self.y)
            if d < bestd:
                bestd, tx, ty = d, ox, oy
                flee = True
        self.flap += 0.06
        if self.flap > 1.0:
            self.flap -= 1.0
        airborne = self.rest <= 0 and self.flaps > 0

        self.vx *= AIR_FRICTION
        self.vy *= AIR_FRICTION
        if airborne:
            if flee:
                # 逃：朝远离猫 + 略向上
                ux, uy = _dirvec(tx, ty, self.x, self.y)
                self.vx += ux * FLEE_ACCEL * 3.0
                self.vy += min(0.0, uy) * FLEE_ACCEL * 2.0 - 0.16
                self.flap_ph += 0.55
                if self.flap_ph > math.tau:
                    self.flap_ph -= math.tau
                    self.flaps -= FLEE_FLAP_COST  # 逃命的扑翅格外费体力
                    if self.flaps <= 0:
                        self.flaps = 0
                        self.rest = REST_TICKS
            else:
                self.vy += self.gravity * self.room_gravity * 0.55
                if self.y > want_y + HOVER_BAND:
                    self.vy -= FLAP_THRUST / FLAP_PERIOD * 6.0
                self._drift(WL, HL)
        else:
            self.vy += self.gravity * self.room_gravity
            if flee and bestd < PANIC_R and self.flaps > 0 and self.rest > 0:
                self.rest = 0                     # 贴脸炸飞
                ux, uy = _dirvec(tx, ty, self.x, self.y)
                self.vx += ux * 3.0
                self.vy -= 3.0
            self.vx *= 0.9
            if self.rest > 0:
                self.rest -= 1
                if self.rest == 0:
                    self.flaps = FLAPS_MAX

        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        if self._contact_floor:
            self.rest = max(self.rest, REST_TICKS // 3)
            if abs(self.vx) < 0.25:
                self.vx = 0.0

    def _drift(self, WL, HL) -> None:
        """闲时随机漂移。"""
        self._goal_timer += 1
        if (self._goal_timer > DRIFT_REPICK
                or math.hypot(self._goal[0] - self.x, self._goal[1] - self.y) < 24.0):
            m = WALL_MARGIN
            self._goal = (self._rng.uniform(m, max(m, WL - m)),
                          self._rng.uniform(m, max(m, HL - HOVER_H - 40.0)))
            self._goal_timer = 0
        dx, dy = _dirvec(self.x, self.y, self._goal[0], self._goal[1])
        self.vx += dx * DRIFT_ACCEL
        self.vy += dy * DRIFT_ACCEL * 0.6
        if abs(self.vx) > 0.08:
            self.facing = 1 if self.vx > 0 else -1
        self.dir_x, self.dir_y = dx, dy

    def _collide(self, WL, HL) -> None:
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)


def _dirvec(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)
