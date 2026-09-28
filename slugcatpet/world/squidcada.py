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

HOVER_H = 78.0            # 巡航高度（离地，窗口很矮时的下限）
HOVER_TOP = 104.0         # 巡航高度（离窗口上边；原版在房间上半部悬停）
HOVER_BAND = 18.0         # 高度带：出带才修正
HOVER_PULL = 3.0          # 掉得太低时的额外拉升倍率
TAKEOFF_VY = 2.6          # 落地后再起飞的上冲速度（原版扑翅起飞）
HOVER_VY_MAX = 1.9        # 巡航期垂直速度上限（平滑悬停）
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

# 4 条触须的初始散开偏移（原版是 4 个独立 Limb，各自的物理历史不同）
_TENT_SPREAD = ((-2.5, 1.5), (2.5, 1.5), (-4.5, 4.0), (4.5, 4.0))


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
                 "_goal", "_goal_timer", "_contact_floor", "_contact_x",
                 # 渲染个体差异（Cicada.IndividualVariations / CicadaGraphics 状态）
                 "fatness", "wing_len", "wing_thick", "tent_len", "tent_thick",
                 "wing_offset", "lazy_wing", "busted_wing", "wing_dep",
                 "wing_dep_to", "wing_dep_speed", "blink", "flap_t",
                 # 渲染用体轴 / zRotation（平滑）/ 4 条触须的自由点
                 "hd", "zx", "zy", "lzx", "lzy", "tent", "tent_last")

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
        # 渲染：体轴 / zRotation（原版 CicadaGraphics.zRotation，每 tick 向体轴插值 0.15）
        self.hd = (1.0 if self.facing >= 0 else -1.0, 0.0)
        self.zx, self.zy = self.hd
        self.lzx, self.lzy = self.zx, self.zy
        # 4 条触须各自带一点初始散开量：原版是 4 个独立 Limb，飘着就自然分开
        self.tent = [(float(x) + _TENT_SPREAD[i][0], float(y) + 6.0 + _TENT_SPREAD[i][1],
                      0.0, 0.0) for i in range(4)]
        self.tent_last = list(self.tent)
        # ── 个体差异：对照 Cicada.GenerateIVars ──
        # fatness = ClampedRandomVariation(gender ? 0.6 : 0.4, 0.1, 0.5) * 2
        base = 0.6 if self.male else 0.4
        self.fatness = (base + rng.uniform(-0.1, 0.1)) * 2.0
        # wingSoundPitch 用不到；这里按原版顺序取其余随机量
        r1 = rng.random()
        self.tent_len = 0.6 + 0.8 * rng.random()      # tentacleLength
        self.tent_thick = 0.6 + 0.8 * rng.random()    # tentacleThickness
        self.wing_thick = 1.0 - 0.6 * (r1 * r1)       # wingThickness ∈ 0.4..1
        self.wing_len = max(0.2, (0.66667 + rng.uniform(-0.3, 0.3)) * 1.5)   # wingLength
        self.wing_offset = rng.random()               # wingOffset（扑翅相位漂移）
        self.lazy_wing = rng.randrange(-2, 4)
        self.busted_wing = rng.randrange(4) if rng.random() < 0.125 else -1
        dep0 = rng.random()                           # defaultWingDeployment
        self.wing_dep = [dep0, dep0, dep0, dep0]
        self.wing_dep_to = 1.0
        self.wing_dep_speed = [0.0, 0.0, 0.0, 0.0]
        self.blink = rng.randrange(10, 300)
        self.flap_t = 0.0
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

    # ── 渲染状态：对照 CicadaGraphics.Update（翅膀展开/收起、眨眼、扑翅相位）──
    def _heading(self):
        """体轴（朝头）单位向量：飞的时候取速度方向，否则按朝向横躺。"""
        sp = math.hypot(self.vx, self.vy)
        if sp > 0.6:
            return (self.vx / sp, self.vy / sp)
        return (float(self.facing), 0.0)

    def _tent_tick(self, ux, uy) -> None:
        """4 条触须：自由点 + 重力 + 沿体轴推力 + 侧向推力，再被绳长约束到身体前端。

        对照 CicadaGraphics.Update 的触须段与 ConnectToPoint(mainBodyChunk + 体轴*10,
        (24|19) * tentacleLength)。
        """
        v2x, v2y = -uy, ux
        zx, zy = self.zx, self.zy
        ax0, ay0 = self.x + ux * 10.0, self.y + uy * 10.0
        self.tent_last = list(self.tent)
        out = []
        for m in range(2):
            for n in range(2):
                tx, ty, tvx, tvy = self.tent[m * 2 + n]
                tvy += 0.6                                  # 原版 vel.y -= 0.6（y↑）
                tvx += ux * 0.55
                tvy += uy * 0.55
                # |zRotation.y| 太小时侧向散不开（4 条会重叠成一根细线）：给个下限
                wz = max(0.45, abs(zy))
                lat = (0.2 if n == 0 else 0.6) * (-1.0 if m == 0 else 1.0) * wz
                tvx += v2x * lat
                tvy += v2y * lat
                f_lat = (-0.1 if n == 0 else 0.6) * zx
                tvx -= v2x * f_lat
                tvy -= v2y * f_lat
                tx += tvx
                ty += tvy
                tvx *= 0.9
                tvy *= 0.9
                reach = (24.0 if n == 0 else 19.0) * self.tent_len
                dx, dy = tx - ax0, ty - ay0
                d = math.hypot(dx, dy)
                if d > reach and d > 1e-6:
                    nx, ny = dx / d, dy / d
                    tx, ty = ax0 + nx * reach, ay0 + ny * reach
                    radial = tvx * nx + tvy * ny
                    if radial > 0.0:
                        tvx -= nx * radial
                        tvy -= ny * radial
                out.append((tx, ty, tvx, tvy))
        self.tent = out

    def gfx_tick(self) -> None:
        """只管渲染状态，不影响物理。原版里这些量确实在 GraphicsModule.Update 里推进。"""
        ux, uy = self._heading()
        self.hd = (ux, uy)
        self.lzx, self.lzy = self.zx, self.zy
        self.zx += (ux - self.zx) * 0.15
        self.zy += (uy - self.zy) * 0.15
        dd = math.hypot(self.zx, self.zy)
        if dd > 1e-6:
            self.zx, self.zy = self.zx / dd, self.zy / dd
        self._tent_tick(ux, uy)
        self.flap_t += 1.0
        if self.flap_t >= 3.0:
            self.flap_t -= 3.0                       # wingTimeAdd：每 tick +1，到 3 归零
        self.wing_offset += 1.0 / 55.0               # 原版 1/Random.Range(50,60)
        if self.wing_offset >= 1.0:
            self.wing_offset -= 1.0
        self.blink -= 1
        if self.blink < -15 or (self.blink < -2 and self._rng.random() < 1.0 / 3.0):
            self.blink = self._rng.randrange(10, 300)
        # 被吃掉的部分：每少一口就多收一对翅（原仓库「食物越吃越少、外观跟着变」）
        eaten_fold = max(0, 3 - int(self.bites)) * 2
        for idx in range(min(eaten_fold, 4)):
            self.wing_dep[idx] = 0.0
        if self.dead:
            return                                   # 非清醒：原版不推进 deployment，保持原姿态
        if self.airborne and self.state == ItemState.FREE:
            self.wing_dep_to = 1.0
        elif self.wing_dep_to == 1.0:
            self.wing_dep_to = 0.9
        elif self._rng.random() < 1.0 / 14.0:
            self.wing_dep_to = max(0.0, self.wing_dep_to - self._rng.random() / 6.0)
        for k in range(2):
            for l in range(2):
                idx = k * 2 + l
                if idx < eaten_fold or self.busted_wing == k + l + l:
                    continue                         # 被吃掉的部位/断翅：翅一直收着
                if self._rng.random() < 1.0 / 30.0:
                    self.wing_dep_speed[idx] = self._rng.random() ** 2 * 0.3
                if self.wing_dep_to == 1.0 and self.lazy_wing != k + l + l:
                    self.wing_dep[idx] = 1.0
                elif self.wing_dep[idx] < self.wing_dep_to:
                    self.wing_dep[idx] = min(self.wing_dep[idx] + self.wing_dep_speed[idx],
                                             self.wing_dep_to)
                elif self.wing_dep[idx] > self.wing_dep_to:
                    self.wing_dep[idx] = max(self.wing_dep[idx] - self.wing_dep_speed[idx],
                                             self.wing_dep_to)

    # ── 主循环 ──
    def step(self, WL: float, HL: float, threats=()) -> None:
        self.gfx_tick()
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
        want_y = min(floor - HOVER_H, HOVER_TOP)
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
                self.flap_ph += 0.35
                if self.flap_ph > math.tau:
                    self.flap_ph -= math.tau
                    self.flaps = max(0, self.flaps - 1)     # 巡航也慢慢耗体力
                self.vy += self.gravity * self.room_gravity * 0.55
                if self.y > want_y + HOVER_BAND:
                    # 掉得越低拉得越猛：原版扑翅几下就回到巡航高度
                    k = clampf((self.y - (want_y + HOVER_BAND)) / 60.0, 0.0, 1.0)
                    self.vy -= FLAP_THRUST / FLAP_PERIOD * 6.0 * (1.0 + HOVER_PULL * k)
                self._drift(WL, HL)
                # 巡航垂直速度夹一下：否则扑翅升力会把巡飞变成上下弹跳
                self.vy = clampf(self.vy, -HOVER_VY_MAX, HOVER_VY_MAX)
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
                    self.vy = min(self.vy, -TAKEOFF_VY)     # 歇完起身再飞

        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        if self._contact_floor:
            if self.flaps > 0:
                self.rest = 0                      # 落地只是踉跄一下，立刻扑翅再起
                self.vy = min(self.vy, -TAKEOFF_VY)
                self.vy -= 0.35
            else:
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
        # 尸体：左右/顶边不挡，被甩出窗口即飞出去（由 items 层清除）
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb,
                          open_sides=self.dead)


def _dirvec(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)
