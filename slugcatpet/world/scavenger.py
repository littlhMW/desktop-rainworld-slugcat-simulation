"""拾荒者 Scavenger：地面行走的持矛生物（原版 Scavenger）。y↓。

看到蜥蜴/猫靠近 → 站定瞄准 → 把矛掷出 → 逃跑；没矛了就一直躲。
外形程序化绘制（原版拾荒者是骨架+面具头，图集里只有 ScavengerHandA/B）。
"""
from __future__ import annotations
import math
import random as _random

from ..core.units import clampf, lerp
from ..core.gfxmath import _hsl2rgb
from .enums import ItemState
from .spear import Spear

GRAVITY = 0.9
AIR_FRICTION = 0.98
GROUND_FRICTION = 0.86
WALL_BOUNCE = 0.1

BODY_RAD = 7.0
HEAD_RAD = 6.0
STAND_H = 26.0            # 站立时躯干中心离地高度
SPEED_WALK = 0.85
SPEED_RUN = 1.5
ALERT_R = 190.0           # 察觉半径（蜥蜴/猫）
PANIC_R = 150.0
AIM_TICKS = 34            # 瞄准时长
THROW_CD = 90
IDLE_TICKS = (90, 260)
FLEE_TICKS = 260

BODY_RGB = (58, 60, 68)          # 兜底体色
HEAD_RGB = (226, 226, 214)       # 面具（原版偏白的骨质面具）
EYE_RGB = (26, 26, 30)
SPIKE_RGB = (232, 232, 224)
LEG_RGB = (44, 46, 52)


def body_colors(rng):
    """原版 GenerateColors：体色随机色相，面具恒白，眼睛同色相深色。"""
    hue = rng.random()
    sat = lerp(0.05, 1.0, rng.random() ** 0.85)
    light = lerp(0.05, 0.8, rng.random())
    r, g, b = _hsl2rgb(hue, sat, light)
    return ((int(r * 255), int(g * 255), int(b * 255)), HEAD_RGB,
            (int(r * 90), int(g * 90), int(b * 90)))


class Scavenger:
    """拾荒者：巡走/警觉/投矛/逃跑 四态。"""
    collision_layer = 0

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "air_friction", "surface_friction", "bounce", "water_y", "room_gravity",
                 "state", "facing", "walk_phase", "state_t", "idle_timer", "goal_x",
                 "spear", "aim", "aim_t", "throw_event", "throw_cd", "dead", "held_by_hand",
                 "_contact_floor", "_rng", "seed", "id", "body_rgb", "head_rgb", "eye_rgb")

    def __init__(self, x: float, y: float, seed: int = 0, id: int = 0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad = BODY_RAD
        self.mass = 1.2
        self.gravity = GRAVITY
        self.air_friction = AIR_FRICTION
        self.surface_friction = GROUND_FRICTION
        self.bounce = WALL_BOUNCE
        self.water_y = None
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.held_by_hand = None
        self.facing = -1
        self.walk_phase = 0.0
        self.state_t = 0
        self.dead = False
        self.seed = int(seed)
        self.id = int(id)
        self._rng = _random.Random(seed * 3571 + 11)
        self.body_rgb, self.head_rgb, self.eye_rgb = body_colors(self._rng)
        self.idle_timer = self._rng.randint(*IDLE_TICKS)
        self.goal_x = self.x
        self.aim = None                 # (x, y) 瞄准点
        self.aim_t = 0
        self.throw_cd = 0
        self.throw_event = None         # (tx, ty) 窗口读走后生成飞矛
        self.spear = Spear(self.x + 6.0, self.y - 6.0, seed=seed, angle_deg=90.0)
        self.spear.held_by = self
        self._contact_floor = False

    @property
    def pos(self):
        return (self.x, self.y)

    def bounding_pad(self) -> float:
        return 46.0

    def die(self) -> None:
        self.dead = True
        self.state = ItemState.GONE

    def grab(self, cursor=None) -> None:
        self.held_by_hand = True
        self.state = ItemState.MOUSE
        self.vx = self.vy = 0.0

    def release(self, vx=0.0, vy=0.0) -> None:
        self.held_by_hand = None
        self.state = ItemState.FREE
        self.vx, self.vy = vx, vy

    # ── 主循环 ──
    def step(self, WL: float, HL: float, threats=(), cursor=None) -> None:
        self.last_x, self.last_y = self.x, self.y
        if self.state == ItemState.MOUSE:
            self._step_held(HL, cursor)
            return
        self.vx *= AIR_FRICTION
        self.vy = (self.vy + GRAVITY * self.room_gravity) * AIR_FRICTION
        self._threat_scan(threats)
        self._integrate(WL, HL)
        self._step_legs(HL)
        if self.throw_cd > 0:
            self.throw_cd -= 1
        if self.spear is not None:                  # 矛跟着手
            self._carry_spear()

    def _step_held(self, HL, cursor=None) -> None:
        """被拎起：跟光标垂着，矛与投掷意图都失效。"""
        if cursor is not None:
            self.x, self.y = cursor[0], min(cursor[1], HL - BODY_RAD)
        self.throw_event = None
        if self.spear is not None:      # 手里仍握着矛
            self._carry_spear()

    def _threat_scan(self, threats) -> None:
        """按威胁距离切态：瞄准→投矛→逃跑。"""
        best, bd = None, ALERT_R
        for obj, ox, oy in threats:
            d = math.hypot(ox - self.x, oy - self.y)
            if d < bd:
                best, bd = (ox, oy), d
        if best is None:
            self.aim = None
            if self.state_t > 0 or self.state != ItemState.FREE or self.aim_t:
                pass
            if self.state in ("flee", "aim"):
                self.state = ItemState.FREE
                self.state_t = 0
        else:
            self.facing = 1 if best[0] >= self.x else -1
            if self.spear is not None and self.throw_cd <= 0 and self.state != "flee":
                self.aim = best
                if self.state != "aim":
                    self.state = "aim"
                    self.aim_t = 0
            elif self.state != "flee":
                self.state = "flee"
                self.state_t = FLEE_TICKS
        if self.state == "aim":
            self.aim_t += 1
            if self.aim_t >= AIM_TICKS and self.spear is not None:
                self.throw_event = (self.aim[0], self.aim[1])
                self.spear = None
                self.throw_cd = THROW_CD
                self.state = "flee"
                self.state_t = FLEE_TICKS
        elif self.state == "flee":
            self.state_t -= 1
            if self.state_t <= 0:
                self.state = ItemState.FREE

    def _integrate(self, WL, HL) -> None:
        if self.state == "aim":
            self.vx *= 0.7
        elif self.state == "flee":
            self.vx += (SPEED_RUN * self.facing - self.vx) * 0.12
            if self.throw_event is None and self._rng.random() < 0.01:
                self.facing = -self.facing
        else:
            self.state_t += 1
            self.idle_timer -= 1
            if self.state_t > self.idle_timer or abs(self.x - self.goal_x) < 8.0:
                self.state_t = 0
                self.idle_timer = self._rng.randint(*IDLE_TICKS)
                self.goal_x = clampf(self._rng.uniform(60.0, WL - 60.0), 20.0, WL - 20.0)
            if abs(self.x - self.goal_x) > 10.0:
                self.facing = 1 if self.goal_x > self.x else -1
                self.vx += (SPEED_WALK * self.facing - self.vx) * 0.08

        self.x += self.vx
        self.y += self.vy
        if self.x < self.rad:
            self.x, self.vx = self.rad, 0.0
        elif self.x > WL - self.rad:
            self.x, self.vx = WL - self.rad, 0.0
        if self.y + BODY_RAD > HL:
            self.y = HL - BODY_RAD
            self.vy = 0.0
            self._contact_floor = True
        else:
            self._contact_floor = False

    def _step_legs(self, HL) -> None:
        if abs(self.vx) > 0.05:
            self.walk_phase = (self.walk_phase + abs(self.vx) * 0.05) % 1.0

    def _carry_spear(self) -> None:
        """矛握在手里：斜举在身前，瞄准时后仰。"""
        sp = self.spear
        ang = 70.0 if self.state != "aim" else 55.0
        a = math.radians(ang)
        sp.x, sp.y = self.x + self.facing * 5.0 + math.sin(a) * 6.0, self.y - 4.0
        sp.angle_deg = ang * self.facing
        sp.last_x, sp.last_y = sp.x, sp.y
        sp.last_angle = sp.angle_deg
        sp.state = ItemState.CARRIED
        sp.unstuck()

    # ── 头/眼（绘制用）──
    def head_pos(self):
        return (self.x + self.facing * 6.0, self.y - STAND_H + 4.0)
