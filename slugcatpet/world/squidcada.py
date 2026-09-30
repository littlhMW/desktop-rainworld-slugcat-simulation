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

# ── 原版 Cicada 飞行模型（数字全部取自 Cicada.cs / CicadaAI.cs）──
STAMINA_REGEN = 1.0 / 70.0          # :234 没被抓/没黏住时每 tick 回 1/70（约 1.75 s 回满）
STAMINA_FLY = 1.0 / 3.0             # :587 flying = stamina > 1/3
LIFT_DRAIN_M = 1.0 / 190.0          # :591 雄：托着猫飞时每 tick 掉这么多
LIFT_DRAIN_F = 1.0 / 120.0          # :591 雌
FLY_DRAG0, FLY_DRAG1 = 0.98, 0.94   # :305-306 两个 bodyChunk 各自的阻尼
FLY_LIFT0, FLY_LIFT1 = 0.8, 1.2     # :309-310 两个 bodyChunk 各自的升力
FLY_SIN = 0.05                      # :303-304 正弦抖动的幅度
FLY_SIN_PERIOD = (45.0, 85.0)       # :298 抖动周期
STEER0, STEER1 = 1.1, 0.65          # :512-513 朝路径目标推进
CONTACT_PUSH = 8.0                  # :369 贴地/贴墙时的顶开力
TAKEOFF_V0, TAKEOFF_V1 = 9.0, 7.0   # :764-765 起飞初速
LAND_WAIT = 30                      # :531 落地后等这么久才起飞
CHARGE_SPINUP = 21                  # :540 <21 蓄势后仰；>=21 直线突进
CHARGE_END = 38                     # :550 >38 收招
CHARGE_THRUST = 4.0                 # :559 突进每 tick 的推力
CHARGE_BACK = 0.8                   # :544 蓄势时后仰
CHARGE_WINDUP_DECAY = 0.8           # :542-543 蓄势阻尼
CHARGE_EXIT_DECAY = 0.5             # :553-554 收招阻尼
CHARGE_VIS_UP, CHARGE_VIS_DOWN = 0.1, 0.05   # CicadaGraphics.cs:174-178
ANTAGONIZE_LIKE = -0.1              # CicadaAI.cs:640 num < -0.1 → 敌意
AFRAID_LIKE = -0.5                  # CicadaAI.cs:645 num < -0.5 且对方带武器 → 畏惧
IGNORE_LIKE = 0.5                   # CicadaAI.cs:652 num > 0.5 → 无视
CHARGE_RANGE = 40.0                 # CicadaAI.cs:485 贴到 40px 内才顶
CHARGE_CHANCE = 1.0 / 30.0          # CicadaAI.cs:485 每 tick 掷 1/30
LIKE_HURT = 0.5                     # 被矛/石头打中：关系直接恶化
LIKE_CARRIED = 0.002                # 被拎在手里持续恶化（原版 Cicada.cs:614 是 0.00025，按桌宠节奏放大）
CICADA_STUN = 10                    # :866 顶完自己的硬直
TILE = 20.0                         # 原版一格 20px（terrainProximity 换算）
STUN_KNOCK = 5.0                    # :852 撞到生物时的击退量级

DRIFT_REPICK = 150        # 闲时多久换一个漂移目标
DRIFT_TOP = 0.5           # 漂移目标的高度上限（占窗口高度的比例）
FLAPS_MAX = 60            # 兼容旧字段：体力条的刻度数
REST_TICKS = 70           # 兼容旧字段：rest>0 表示落着没飞
EATEN_COUNTDOWN = 3

# ── 捕食蝠蝇（原版 CicadaAI 的 BatFly 猎食：饿了主动去抓，抓到当场吃掉）──
HUNGER_DRAIN = 1.0 / 2400.0   # 每 tick 掉一点（满 → 饿约 60 s）
HUNGER_INIT = (0.35, 1.0)     # 出生时的饥饿度区间（随机，不是全都饿）
HUNGRY_BELOW = 0.55           # 低于它才开始找蝠蝇
HUNT_R = 320.0                # 捕食视线半径
CATCH_D = 12.0                # 贴到这么近就咬中
PREY_FLEE_R = 70.0            # 蝠蝇察觉到蝉乌贼的距离
PREY_FLEE_D = 140.0           # 逃跑目标点距离

WALL_MARGIN = 20.0

# 4 条触须的初始散开偏移（原版是 4 个独立 Limb，各自的物理历史不同）
_TENT_SPREAD = ((-2.5, 1.5), (2.5, 1.5), (-4.5, 4.0), (4.5, 4.0))


class Squidcada:
    # 食性：尸体（Player.CanEatMeat，Player.cs:11824）；杂食猫不放行
    food_class = "corpse"
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
                 "hd", "zx", "zy", "lzx", "lzy", "tent", "tent_last",
                 # 原版 Cicada / CicadaGraphics 状态
                 "stamina", "flying", "flying_power", "sin_counter", "wait_fly",
                 "charge_counter", "charge_dir", "like", "stun", "armed_threat",
                 "look_at", "look_dir", "look_rot", "charging_vis",
                 "threat_mode", "threat_pos", "_contact_ceil",
                 "hunger", "prey")

    @property
    def haul_chunk_mass(self):
        """被拖拽时「被抓那节」的质量：Cicada.cs:130-133（每节 = num/2，num 公 0.65 / 母 0.55）。"""
        return (0.65 if self.male else 0.55) / 2.0

    @property
    def haul_mass(self):
        """被拖拽对象总质量：Cicada.cs:130-133 两节合计 = num（公 0.65 / 母 0.55）。"""
        return 0.65 if self.male else 0.55

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
        self.hunger = rng.uniform(HUNGER_INIT[0], HUNGER_INIT[1])   # 饿了就去抓蝠蝇
        self.prey = None         # 正在追的那只蝠蝇（原版 CicadaAI 的 prey）
        self.flap = rng.random()
        self.flap_ph = rng.random() * math.tau
        self.wings = [self.flap, self.flap]
        # ── 原版 Cicada 状态（Cicada.cs）──
        self.stamina = 1.0                  # :73 初始满体力
        self.flying = True                  # :145 出生就在飞
        self.flying_power = 0.5
        self.sin_counter = rng.random()     # :143
        self.wait_fly = 0                   # waitToFlyCounter
        self.charge_counter = 0             # :539 <21 蓄势 / 21..38 突进
        self.charge_dir = (0.0, 0.0)
        self.like = 0.0                     # LikeOfPlayer：-1..1（CicadaAI.cs:627）
        self.stun = 0
        self.armed_threat = False           # 最近那只猫手上有没有武器
        self.threat_mode = None             # None / "antagonize" / "afraid"
        self.threat_pos = None
        self.look_at = None                 # 这一 tick 看向哪儿（CicadaGraphics.creatureLooker）
        self.look_dir = (0.0, 0.0)          # :17
        self.look_rot = 0.0                 # :19
        self.charging_vis = 0.0             # :45
        self.rest = 0
        self.flaps = FLAPS_MAX
        self.dir_x, self.dir_y = (1.0 if rng.random() < 0.5 else -1.0), 0.0
        self.facing = 1 if self.dir_x >= 0 else -1
        self.rotation = self.last_rotation = (0.0, -1.0)
        # 渲染：体轴 / zRotation（原版 CicadaGraphics.zRotation，每 tick 向体轴插值 0.15）
        self.hd = (1.0 if self.facing >= 0 else -1.0, 0.0)
        self.zx, self.zy = self.hd
        self.lzx, self.lzy = self.zx, self.zy
        self._lay_tent_pts(x, y)
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
        self._contact_ceil = False
        self._contact_x = 0

    def _lay_tent_pts(self, x, y) -> None:
        """触须铺到本体前端（原版 4 条独立 Limb 的初始位）。"""
        self.tent = [(float(x) + _TENT_SPREAD[i][0], float(y) + 6.0 + _TENT_SPREAD[i][1],
                      0.0, 0.0) for i in range(4)]
        self.tent_last = list(self.tent)

    def lay_tentacles(self) -> None:
        """把触须按当前本体位重新铺开（放置预览用：预览不 tick，不铺就留在原点）。"""
        self._lay_tent_pts(self.x, self.y)

    # ── 查询 ──
    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def resting(self) -> bool:
        """落在地上没飞（原版 flying == false）。"""
        return not self.flying

    @property
    def fetch_ready(self) -> bool:
        """走过去的取食路径：落在地上才够得到。"""
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and (self.dead or not self.flying))

    @property
    def catchable(self) -> bool:
        """能徒手抓上来：活着且没被别的嘴叼着（飞行中也能抓）。"""
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and not self.dead)

    @property
    def airborne(self) -> bool:
        """是否在飞。"""
        return not self.dead and self.state == ItemState.FREE and self.flying

    @property
    def lift_power(self) -> float:
        """托举猫的力气：Cicada.cs:107 SCurve(stamina, 0.15) * (0.4 + playerJumpBoost*0.6)。"""
        return _scurve(clampf(self.stamina, 0.0, 1.0), 0.15) * 0.4

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

    def hurt(self, dmg: float, kx: float = 0.0, ky: float = 0.0,
             by=None, lethal: bool = True) -> bool:
        """被武器打中：原版 Violence 的 num = damage / baseDamageResistance。

        矛 1.0 / 0.8 = 1.25 ≥ 1.0 → 一矛即死；石头 0.01 / 0.8 → 只被震飞，打不死。
        `by`/`lethal` 和面条蝇统一签名（投掷物命中循环共用）；蝉乌贼不用它们。
        """
        self.vx += kx
        self.vy += ky
        self.like = max(-1.0, self.like - LIKE_HURT)      # 被打：关系恶化（CicadaAI 社会记忆）
        if self.health > 0.0:
            self.health -= dmg / self.DAMAGE_RESISTANCE
        if self.health <= 0.0 and not self.dead:
            self.die()
            return True
        # Cicada.cs:176-183 残血时会时不时被打懵一下
        if self.health < 0.5 and self._rng.random() > self.health and self._rng.random() < 1.0 / 3.0:
            self.stun = 4
        return self.dead

    def die(self) -> None:
        self.dead = True
        self.flying = False
        self.charge_counter = 0
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
        if self.charge_counter > 0:                  # CicadaGraphics.cs:204-205
            self.blink = -5
            self.zy -= 0.5
        # ── CicadaGraphics.cs:247-264 lookDir / lookRotation ──
        if not self.dead and self.look_at is not None and self.blink > 0:
            lx, ly = _dirvec(self.x, self.y, self.look_at[0], self.look_at[1])
            self.look_dir = (lx, ly)
            self.look_rot = _aimd(lx, ly) - _aimd(ux, uy)
        else:
            self.look_dir = (self.look_dir[0] * 0.9, self.look_dir[1] * 0.9)
            self.look_rot *= 0.8
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
        if self.flying:
            self.wing_dep_to = 1.0                   # CicadaGraphics.cs:201 飞着就一直展开
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
    def step(self, WL: float, HL: float, threats=(), look_at=None,
             prey=()) -> None:
        self.look_at = look_at
        self.gfx_tick()
        if self.state in (ItemState.MOUSE, ItemState.CARRIED):
            self._stamina_tick(grabbed=True)      # 位置由手每 tick 写入，只推进体力
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
            self.flying = False
            self.vy += self.gravity * self.room_gravity
            apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                        self.room_gravity, self.air_friction)
            self.x += self.vx
            self.y += self.vy
            self._collide(WL, HL)
            self._flags_sync()
            return

        self._stamina_tick(grabbed=False)
        self._hunt_tick(prey)
        self._flight(WL, HL, threats)
        self._try_catch()
        self._flags_sync()

    # ── 体力（Cicada.cs:232-235 / :587-592）──
    def _stamina_tick(self, grabbed: bool) -> None:
        if self.dead:
            self.flying = False
            return
        if self.state == ItemState.CARRIED:
            # 被拎在手里：托举它要花体力，同时关系变差（:591 / :611-615）
            self.stamina -= LIFT_DRAIN_M if self.male else LIFT_DRAIN_F
            self.stamina = clampf(self.stamina, 0.0, 1.0)
            self.flying = self.stamina > STAMINA_FLY
            self.like = max(-1.0, self.like - LIKE_CARRIED)
        elif not grabbed:
            self.stamina = min(1.0, self.stamina + STAMINA_REGEN)

    def _flags_sync(self) -> None:
        """新模型映射回旧字段：flaps = 体力刻度，rest > 0 表示落着没飞。"""
        self.flaps = int(round(clampf(self.stamina, 0.0, 1.0) * FLAPS_MAX))
        self.rest = 0 if self.flying else REST_TICKS

    # ── 捕食蝠蝇 ──
    def _hunt_tick(self, prey) -> None:
        """饿了就挑最近的一只蝠蝇当猎物（原版 CicadaAI：蝉乌贼会捕食蝠蝇）。"""
        self.hunger = clampf(self.hunger - HUNGER_DRAIN, 0.0, 1.0)
        cur = self.prey
        if cur is not None and (getattr(cur, 'dead', False)
                                or cur.state != ItemState.FREE
                                or self.hunger > HUNGRY_BELOW):
            cur = self.prey = None
        if cur is None and self.hunger <= HUNGRY_BELOW:
            best, bd = None, HUNT_R
            for bf in prey:
                if getattr(bf, 'dead', False) or bf.state != ItemState.FREE:
                    continue
                d = math.hypot(bf.x - self.x, bf.y - self.y)
                if d < bd:
                    best, bd = bf, d
            self.prey = best
        tgt = self.prey
        if tgt is None:
            return
        # 蝠蝇会被扑过来的蝉乌贼惊走：把它的漂移目标改到反方向（原版 BatFly 逃跑）
        if math.hypot(tgt.x - self.x, tgt.y - self.y) < PREY_FLEE_R:
            ux, uy = _dirvec(self.x, self.y, tgt.x, tgt.y)
            tgt.goal = (tgt.x + ux * PREY_FLEE_D, tgt.y + uy * PREY_FLEE_D)

    def _try_catch(self) -> bool:
        """贴到猎物身上就一口咬死（吃完饥饿度回满，进入下一个捕食周期）。"""
        bf = self.prey
        if bf is None or getattr(bf, 'dead', False) or bf.state != ItemState.FREE:
            return False
        if math.hypot(bf.x - self.x, bf.y - self.y) > CATCH_D:
            return False
        bf.bite()                 # BatFly：die() + 尸体倒计时，由 items 层剔除
        self.hunger = 1.0
        self.prey = None
        return True

    def _charge(self, px: float, py: float) -> None:
        """Cicada.cs:694-704 Charge(pos)：锁定方向，起手蓄势。"""
        if self.charge_counter > 0:
            return
        self.charge_dir = _dirvec(self.x, self.y, px, py)
        self.charge_counter = 1

    def _charge_tick(self) -> None:
        """Cicada.cs:537-573：<21 蓄势后仰 → 21..38 直线突进 → >38 收招。"""
        self.charge_counter += 1
        ux, uy = self.charge_dir
        if self.charge_counter < CHARGE_SPINUP:
            self.vx *= CHARGE_WINDUP_DECAY
            self.vy *= CHARGE_WINDUP_DECAY
            self.vx -= ux * CHARGE_BACK
            self.vy -= uy * CHARGE_BACK
        elif self.charge_counter > CHARGE_END:
            self.charge_counter = 0
            self.vx *= CHARGE_EXIT_DECAY
            self.vy *= CHARGE_EXIT_DECAY
        else:
            self.vx += ux * CHARGE_THRUST
            self.vy += uy * CHARGE_THRUST
        self.flying = True

    def _flight(self, WL, HL, threats) -> None:
        """原版 Cicada.Act 的飞行段（:296-418）。"""
        tx = ty = None
        bestd = 1e9
        armed = False
        for pt in threats:
            d = math.hypot(pt[1] - self.x, pt[2] - self.y)
            if d < bestd:
                bestd, tx, ty = d, pt[1], pt[2]
                armed = bool(pt[3]) if len(pt) > 3 else False
        self.armed_threat = armed
        if self.charge_counter > 0:              # CicadaGraphics.cs:172-179
            self.charging_vis = min(self.charging_vis + CHARGE_VIS_UP, 1.0)
        else:
            self.charging_vis = max(self.charging_vis - CHARGE_VIS_DOWN, 0.0)

        if self.charge_counter > 0:
            self._charge_tick()
        elif self.stun > 0:
            self.stun -= 1
            self.flying_power = lerp(self.flying_power, 0.0, 0.05)
        else:
            self._decide(tx, ty, bestd)
            if self.flying:
                self._fly_tick(WL, HL, tx, ty)
            else:
                self._sit_tick(WL, HL, tx, ty)

        self.vy += self.gravity * self.room_gravity          # :158 base.Update 的重力
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        if self._contact_floor and self.charge_counter > 0:
            self.charge_counter = 0              # 撞到地面/墙就收招（:569 narrowSpace）

    def _decide(self, tx, ty, bestd) -> None:
        """CicadaAI.cs:627-660：< -0.1 敌意 / < -0.5 且对方持械 → 畏惧 / > 0.5 无视。"""
        self.threat_mode = None
        if tx is None or self.like > IGNORE_LIKE:
            return
        if self.like < AFRAID_LIKE and self.armed_threat:
            self.threat_mode = "afraid"
            self.threat_pos = (tx, ty)
            return
        if self.like < ANTAGONIZE_LIKE:
            self.threat_mode = "antagonize"
            self.threat_pos = (tx, ty)
            if (self.charge_counter <= 0 and bestd < CHARGE_RANGE
                    and self._rng.random() < CHARGE_CHANCE):
                self._charge(tx, ty)

    def _fly_tick(self, WL, HL, tx, ty) -> None:
        """Cicada.cs:296-418：正弦抖动 + 阻尼 + 升力 + 朝目标推进 + 贴墙顶开。"""
        fp = self.flying_power = lerp(self.flying_power, 1.0, 0.1)     # :417
        st = clampf(self.stamina, 0.0, 1.0)
        self.sin_counter += 1.0 / lerp(FLY_SIN_PERIOD[0], FLY_SIN_PERIOD[1],
                                       self._rng.random())             # :298
        if self.sin_counter > 1.0:
            self.sin_counter -= 1.0
        self.vy += math.sin(self.sin_counter * math.tau) * FLY_SIN * fp * st * 2.0   # :303-304
        drag = lerp(1.0, (FLY_DRAG0 + FLY_DRAG1) * 0.5, fp * st)       # :305-306
        self.vx *= drag
        self.vy *= drag
        self.vy -= (FLY_LIFT0 + FLY_LIFT1) * 0.5 * fp * st             # :309-310
        gx, gy = self._fly_goal(WL, HL, tx, ty)
        if gx is not None:
            dx, dy = gx - self.x, gy - self.y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                a = self._openness(WL, HL, dx / d, dy / d, math.hypot(self.vx, self.vy))
                k = min(d, 40.0) / 40.0
                self.vx += dx / d * (STEER0 * k * a * fp * st)         # :512
                self.vy += dy / d * (STEER1 * k * a * fp * st)         # :513
        if abs(self.vx) > 0.08:
            self.facing = 1 if self.vx > 0 else -1
        for cx, cy in self._contacts():                                # :365-371
            self.vx += cx * CONTACT_PUSH * fp * st * self._rng.random()
            self.vy += cy * CONTACT_PUSH * fp * st * self._rng.random()

    def _fly_goal(self, WL, HL, tx, ty):
        """敌意 → 贴到对方身边 30px 好顶；畏惧 → 掉头逃；饿了 → 追蝠蝇；否则闲逛。"""
        if self.threat_pos is not None and self.threat_mode is not None:
            gx, gy = self.threat_pos
            dx, dy = self.x - gx, self.y - gy
            d = math.hypot(dx, dy) or 1.0
            if self.threat_mode == "antagonize":
                return (gx + dx / d * 30.0, gy + dy / d * 30.0)
            return (self.x + dx / d * 160.0, self.y + dy / d * 160.0)
        if self.prey is not None:                # 饿了：猎物就是路径目标
            return (self.prey.x, self.prey.y)
        self._drift(WL, HL)
        return self._goal

    def _openness(self, WL, HL, ux, uy, spd) -> float:
        """Cicada.cs:505-507 的 a：朝去路越挤，推进越弱（三次方）。"""
        ahead = clampf(spd * 5.0, 5.0, 15.0)
        cur = _wall_dist(self.x, self.y, WL, HL)
        nxt = _wall_dist(self.x + ux * ahead, self.y + uy * ahead, WL, HL)
        return min(cur / max(nxt, 1.0), 1.0) ** 3

    def _contacts(self):
        out = []
        if self._contact_floor:
            out.append((0.0, -1.0))
        if self._contact_ceil:
            out.append((0.0, 1.0))
        if self._contact_x:
            out.append((-float(self._contact_x), 0.0))
        return out

    def _sit_tick(self, WL, HL, tx, ty) -> None:
        """落地歇着（Cicada.cs:420-434 / :530-534）：等 30 tick 攒够体力再起飞。"""
        self.flying_power = lerp(self.flying_power, 0.0, 0.05)
        self.vx *= 0.9
        self.wait_fly += 1
        if self.wait_fly > LAND_WAIT and self.stamina > STAMINA_FLY:
            gx, gy = self._fly_goal(WL, HL, tx, ty)
            self._takeoff(gx - self.x, gy - self.y)

    def _takeoff(self, dx, dy) -> None:
        """Cicada.cs:747-768 TakeOff(dir)：带初速的蹬地起飞。"""
        self.wait_fly = 0
        self.flying = True
        ux, uy = _dirvec(0.0, 0.0, dx, dy)
        if ux == 0.0 and uy == 0.0:
            ux, uy = 0.0, -1.0
        v = self._rng.random() * (TAKEOFF_V0 + TAKEOFF_V1) * 0.5
        self.vx += ux * v
        self.vy += uy * v
        self.flying_power = 0.5


    def _drift(self, WL, HL) -> None:
        """闲时随机换一个漂移目标（原版由 CicadaPather 提供路径点）。"""
        self._goal_timer += 1
        if (self._goal_timer > DRIFT_REPICK
                or math.hypot(self._goal[0] - self.x, self._goal[1] - self.y) < 24.0):
            m = WALL_MARGIN
            self._goal = (self._rng.uniform(m, max(m, WL - m)),
                          self._rng.uniform(m, max(m, HL * DRIFT_TOP)))
            self._goal_timer = 0
        self.dir_x, self.dir_y = _dirvec(self.x, self.y, self._goal[0], self._goal[1])

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


def _wall_dist(x: float, y: float, WL: float, HL: float) -> float:
    """到最近一面窗口墙的距离（换算成原版的格：20px/格）。"""
    return max(0.0, min(x, y, WL - x, HL - y) / TILE)


def _aimd(ux: float, uy: float) -> float:
    """AimFromOneVectorToAnother：0 = 上，正 = 右（与 squidcada_gfx._aim 同）。"""
    return math.degrees(math.atan2(ux, -uy))


def _scurve(x: float, k: float) -> float:
    """Custom.SCurve（Custom.cs:1177）。"""
    x = x * 2.0 - 1.0
    if x < 0.0:
        x = abs(1.0 + x)
        return k * x / (k - x + 1.0) * 0.5
    k = -1.0 - k
    return 0.5 + k * x / (k - x + 1.0) * 0.5


