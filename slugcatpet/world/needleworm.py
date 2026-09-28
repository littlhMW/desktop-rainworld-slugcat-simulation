# -*- coding: utf-8 -*-
"""面条蝇 NeedleWorm（原版 MSC 生物）：出生年龄段随机 —— 卵 / 幼体 / 成体。

反编译依据（work/scratch/decomp_full）：
- NeedleWorm.cs:74-111     体节数/半径/质量/物理常量（airFriction 0.999、gravity 0.9、
                           bounce 0.3、surfaceFriction 0.4、waterFriction 0.96、buoyancy 1.05、
                           windAffectiveness 0.4）、bodyChunks 3(幼)/5(成)、tail 行 4/10
- NeedleWorm.cs:370-400    flying 插值 + 体节正弦摆动
- NeedleWorm.cs:70         TotalSegments = bodyChunks + tail 行
- NeedleWormGraphics.cs:146-187  个体随机（wingsSize/legsFac/fatness/snoutLength/hue/lightness/hueDiv）
- NeedleWormGraphics.cs:722-787  ApplyPalette 配色（hue+0.478 系列）
- NeedleWormGraphics.cs:709-720  GraphSegmentRad（吻 1.0 / 躯干 chunkRad×fatness / 尾锥化）
- SmallNeedleWorm.cs:14      bites = 5；:72 FoodPoints = 2
- SmallNeedleWorm.cs:136-158 被抓 → screamCounter → Scream()（成体会被激怒）
- BigNeedleWorm.cs:59-173   attackReady / chargingAttack / 獠牙撞击 Violence(Stab, 0.05, 30)
- NeedleEgg.cs               卵：可搬运，落地/时间到孵化成幼体
- StaticWorld.cs:3488-3520  baseDamageResistance 0.4(成) / 0.2(幼)，instantDeathDamageLimit 1.2
- StaticWorld.cs:3682-3684  LizardTemplate → 成体 Eats 0.25 / 幼体 Eats 0.3 ⇒ is_tame_food
坐标 y↓（原版 y↑，这里全部换算）；角度沿用原版「0=上、顺时针为正」。
"""
from __future__ import annotations
import math
import random as _random

from ..core.chunkphys import aabb_wall_collide, apply_water
from ..core.units import clampf, lerp, inv_lerp
from .enums import ItemState

# ── 物理：NeedleWorm.cs:101-108 逐项照抄 ──
GRAVITY = 0.9
AIR_FRICTION = 0.999
BOUNCE = 0.3
SURFACE_FRICTION = 0.4
WATER_FRICTION = 0.96
BUOYANCY = 1.05

AGE_EGG = "egg"
AGE_SMALL = "small"
AGE_BIG = "big"
# 出生年龄随机（卵 25% / 幼体 40% / 成体 35%）
AGE_ROLL = ((AGE_EGG, 0.25), (AGE_SMALL, 0.40), (AGE_BIG, 0.35))

CHUNKS = {AGE_SMALL: 3, AGE_BIG: 5}     # NeedleWorm.cs:78
CHUNK_RAD_MIN = 2.0                     # NeedleWorm.cs:85 Mathf.Lerp(2f, 5f, t) * num
CHUNK_RAD_MAX = 5.0
CHUNK_MASS_MIN = 0.05                   # 同行 Mathf.Lerp(0.05f, 0.15f, t) * num
CHUNK_MASS_MAX = 0.15
TAIL_ROWS = {AGE_SMALL: 4, AGE_BIG: 10}  # NeedleWorm.cs:99
SNOUT_SEGS = {AGE_SMALL: 3, AGE_BIG: 5}  # NeedleWormGraphics.cs:188

EGG_RAD = 6.0
EGG_MASS = 0.25
HATCH_TICKS = (1500, 3600)      # 卵孵化时间（约 25-60 秒）
EGG_WOBBLE_DECAY = 0.94

# ── 飞行：NeedleWormAI（Idle 游走 / Flee 逃 / Attack 冲撞）──
HOVER_MARGIN = 30.0
LIFT = 0.9                  # 扑翅抵消的重力比例（原版靠翅膀持续升力悬停）
FLY_ACCEL = 0.30
FLY_SPEED_MAX = 4.6
FLEE_ACCEL = 0.72           # 幼体遇猫逃得更急
FLEE_R = 120.0
CHARGE_ACCEL = 1.05
CHARGE_SPEED = 6.4
ANGRY_TICKS = 720           # 愤怒持续（约 12 秒，NeedleWormAI.attackCounter 上限 100 的量级）
GOAL_REPICK = 150
WALL_PAD = 22.0

# ── 吃 / 伤害 ──
SMALL_BITES = 5             # SmallNeedleWorm.cs:14
SMALL_FOOD = 2              # FoodPoints => 2
SMALL_HP = 0.2              # StaticWorld baseDamageResistance
BIG_HP = 0.4
STAB_DAMAGE = 0.05          # BigNeedleWorm.cs:168
STAB_STUN = 30.0
EATEN_COUNTDOWN = 3

# ── 渲染外形：NeedleWormGraphics.cs:146-187 ──
WING_SEG = {AGE_SMALL: (1,), AGE_BIG: (2, 3)}   # 翅膀挂载的 chunk（small 时才 1 对）


class _Seg:
    """一个图段（吻尖→尾梢）：位置 + 上次位置 + 半径 + 到下一节的绳长。"""
    __slots__ = ("x", "y", "lx", "ly", "rad", "dist")

    def __init__(self, x, y, rad, dist):
        self.x = self.lx = float(x)
        self.y = self.ly = float(y)
        self.rad = rad
        self.dist = dist


def _chunk_rads(age):
    """躯干各 chunk 半径：NeedleWorm.cs:81-87 的 Lerp(2,5,t)*num 逐项照抄。"""
    n = CHUNKS[age]
    num = 0.7 if age == AGE_SMALL else 1.0
    out = []
    for i in range(n):
        t0 = inv_lerp(0.0, n - 1.0, i)
        t = lerp(0.6, clampf(math.sin(math.sqrt(t0) * math.pi), 0.0, 1.0), 0.5 + 0.5 * t0)
        out.append(lerp(CHUNK_RAD_MIN, CHUNK_RAD_MAX, t) * num)
    return out


def _chunk_masses(age):
    """躯干各 chunk 质量：同上 Lerp(0.05,0.15,t)*num。"""
    n = CHUNKS[age]
    num = 0.7 if age == AGE_SMALL else 1.0
    out = []
    for i in range(n):
        t0 = inv_lerp(0.0, n - 1.0, i)
        t = lerp(0.6, clampf(math.sin(math.sqrt(t0) * math.pi), 0.0, 1.0), 0.5 + 0.5 * t0)
        out.append(lerp(CHUNK_MASS_MIN, CHUNK_MASS_MAX, t) * num)
    return out


def _rope_rad(age, i):
    """绳长用半径：NeedleWorm.cs:878-885 GetSegmentRadForRopeLength。

    躯干 = chunkRad*(幼体 0.8)；尾段 = LerpMap(seg, chunks, Total-1, 末节 chunkRad, 幼体 8 / 成体 11)。
    相邻节距 = 两节绳半径之和（connectionRopes 的静止长度）。
    """
    n = CHUNKS[age]
    if i < n:
        return _chunk_rads(age)[i] * (0.8 if age == AGE_SMALL else 1.0)
    total = n + TAIL_ROWS[age]
    return _lerp_map(float(i), float(n), float(total - 1), _chunk_rads(age)[-1],
                     8.0 if age == AGE_SMALL else 11.0)


def _roll_age(rng):
    r = rng.random()
    acc = 0.0
    for age, w in AGE_ROLL:
        acc += w
        if r <= acc:
            return age
    return AGE_BIG


class NeedleWorm:
    """面条蝇：幼体/成体会飞，卵会孵。接口对齐 Squidcada / BatFly。"""
    collision_layer = 0

    __slots__ = ("age", "small", "x", "y", "last_x", "last_y", "vx", "vy",
                 "rad", "mass", "head_rad", "gravity", "air_friction", "bounce",
                 "surface_friction", "buoyancy", "water_friction", "water_y",
                 "room_gravity", "state", "held_by_hand", "stalk", "bites",
                 "dead", "eaten", "is_meat", "is_tame_food", "food_value",
                 "health", "edible", "collide_with_objects", "_id", "_impact_cb",
                 "seg", "snout_n", "body_n", "facing", "rotation", "last_rotation",
                 # 行为
                 "flying", "flying_target", "angry", "focus", "charge", "attack_ready",
                 "scream", "scream_counter", "has_screamed", "stab_t", "stab_event",
                 "hatch_t", "hatched", "_wobble", "_goal", "_goal_timer",
                 "_contact_floor", "_contact_x", "_rng", "crawl_sin",
                 # 渲染个体差异（NeedleWormGraphics 的 ivars）
                 "hue", "lightness", "hue_div", "fatness", "wings_size", "legs_fac",
                 "snout_len", "cos_bools", "fang_out", "wing_flap", "last_wing_flap",
                 "blink", "zrot", "lzrot")

    def __init__(self, x: float, y: float, seed: int = 0, age: str | None = None):
        rng = self._rng = _random.Random(seed * 4897 + 11)
        self.age = age if age in (AGE_EGG, AGE_SMALL, AGE_BIG) else _roll_age(rng)
        self.small = self.age != AGE_BIG
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.gravity, self.air_friction, self.bounce = GRAVITY, AIR_FRICTION, BOUNCE
        self.surface_friction, self.buoyancy, self.water_friction = (
            SURFACE_FRICTION, BUOYANCY, WATER_FRICTION)
        self.water_y = None
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.held_by_hand = None
        self.stalk = None
        self.dead = False
        self.eaten = 0
        self.is_meat = True                 # 幼体是肉（素食猫不吃）
        self.is_tame_food = True            # StaticWorld：蜥蜴会吃面条蝇（驯服食物）
        self.food_value = SMALL_FOOD
        self.health = 1.0
        self.edible = self.age == AGE_SMALL  # 原版只有幼体 IPlayerEdible
        self.bites = SMALL_BITES if self.age == AGE_SMALL else 0
        self.collide_with_objects = True
        self._id = int(seed) * 100 + (0 if self.age == AGE_EGG else 1)
        self._impact_cb = None
        self._contact_floor, self._contact_x = False, 0

        self.facing = 1
        self.rotation = self.last_rotation = (0.0, -1.0)
        self.flying = self.flying_target = 0.0 if self.age == AGE_EGG else 1.0
        self.angry, self.charge, self.attack_ready = 0, 0.0, 0.0
        self.focus = None                   # 愤怒时的追击目标 (x, y)
        self.scream, self.scream_counter, self.has_screamed = 0.0, 0.0, False
        self.stab_t, self.stab_event = 0, None
        self.hatch_t = rng.randint(*HATCH_TICKS) if self.age == AGE_EGG else 0
        self.hatched = False
        self._wobble = rng.uniform(-0.5, 0.5)
        self._goal = (x + rng.uniform(-70.0, 70.0), y - rng.uniform(0.0, 90.0))
        self._goal_timer = 0
        self.crawl_sin = rng.uniform(0.0, 6.28)
        # ── 个体随机：NeedleWormGraphics.cs:148-186 的顺序照抄 ──
        self.wings_size = (0.5 if self.age == AGE_SMALL else 1.0) * lerp(
            0.8, 1.2, _clamped_var(rng, 0.5, 0.5, 0.4))
        self.legs_fac = (0.8 if self.age == AGE_SMALL else 1.0) * lerp(0.6, 1.4, rng.random())
        self.fatness = _clamped_var(rng, 0.5, 0.5, 0.4)
        self.snout_len = lerp(0.5, 1.5, rng.random())
        self.cos_bools = [False] * 4
        self.hue = _wrapped_var(rng, 0.5, 0.08, 0.2)
        self.cos_bools[0] = rng.random() < 0.5
        self.cos_bools[1] = rng.random() < (0.25 if self.cos_bools[0] else 0.75)
        self.cos_bools[2] = rng.random() < 0.5
        self.cos_bools[3] = rng.random() < 0.25
        if not self.cos_bools[2] and self.cos_bools[3]:
            self.cos_bools[1] = False
        if self.age == AGE_SMALL:
            self.lightness = lerp(0.3, 1.0, math.pow(_clamped_var(rng, 0.5, 0.5, 0.4), 0.4))
            self.cos_bools[0] = self.cos_bools[1] = False
            self.cos_bools[3] = True
            self.hue_div = 0.0
        else:
            self.lightness = 0.4
            if rng.random() < 1.0 / 3.0:
                self.lightness = 0.4 * math.pow(rng.random(), 5.0)
            elif rng.random() < 1.0 / 17.0:
                self.lightness = 1.0 - 0.6 * math.pow(rng.random(), 5.0)
            self.hue_div = lerp(-1.0, 1.0, rng.random()) * _lerp_map(
                abs(0.5 - self.hue), 0.0, 0.08, 0.06, 0.3)
        if (self.age == AGE_BIG and self.lightness < 0.4
                and rng.random() > self.lightness and rng.random() < 0.1):
            self.hue = rng.random()
        self.fang_out, self.wing_flap, self.last_wing_flap = 0.0, 0.0, 0.0
        self.blink = rng.randrange(20, 300)
        self.zrot = self.lzrot = (float(self.facing), 0.0)
        # ── 链条（吻尖 → 尾）：NeedleWorm.TotalSegments = 躯干 + 尾行 ──
        self.snout_n = SNOUT_SEGS[self.age] if self.age != AGE_EGG else 0
        self.body_n = CHUNKS[self.age] if self.age != AGE_EGG else 0
        self.seg = self._build_chain(x, y, rng)
        self.head_rad = (self.seg[self.snout_n].rad if self.age != AGE_EGG
                         else EGG_RAD)
        self.rad = max((s.rad for s in self.seg), default=EGG_RAD) + 2.0
        self.mass = (sum(_chunk_masses(self.age)) if self.age != AGE_EGG
                     else EGG_MASS)

    def _build_chain(self, x, y, rng):
        """吻尖(0) → 吻根 → 躯干 → 尾梢；半径照 GraphSegmentRad，节距照绳长。"""
        segs = []
        if self.age == AGE_EGG:
            segs.append(_Seg(x, y, EGG_RAD, 0.0))
            return segs
        rads = _chunk_rads(self.age)
        fat = lerp(0.75, 1.35, self.fatness)
        sn = self.snout_n
        # 吻：吻根 → 吻尖（链上倒序：0 = 尖）；间距 = 3*snoutLength
        step = 3.0 * self.snout_len            # NeedleWormGraphics.Update:311
        for i in range(sn):
            segs.append(_Seg(x, y - (sn - i) * step, 1.0, step))
        # 躯干：半径 = chunkRad*fatness，节距 = 相邻绳半径之和
        y_body = y
        for i in range(self.body_n):
            nxt = min(i + 1, self.body_n - 1)
            segs.append(_Seg(x, y_body, rads[i] * fat,
                             _rope_rad(self.age, i) + _rope_rad(self.age, nxt)))
            y_body += segs[-1].dist
        # 尾：NeedleWormGraphics.GraphSegmentRad 的锥化
        last = rads[-1] * fat
        for i in range(TAIL_ROWS[self.age]):
            t = (i + 1.0) / TAIL_ROWS[self.age]
            j = self.body_n + i
            segs.append(_Seg(x, y_body, lerp(last, 0.9, t),
                             _rope_rad(self.age, j) + _rope_rad(self.age, j + 1)))
            y_body += segs[-1].dist
        segs[-1].dist = segs[-2].dist if len(segs) > 1 else 1.0
        return segs

    # ── 查询 ──
    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def catchable(self) -> bool:
        """能徒手抓：活着且没被别人叼走（幼体成体飞行中都能抓）。"""
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and not self.dead and self.age != AGE_EGG)

    @property
    def fetch_ready(self) -> bool:
        """走过去的取食路径：幼体飞着也够得到（原版徒手抓飞虫）。"""
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and self.age == AGE_SMALL)

    @property
    def airborne(self) -> bool:
        return self.age != AGE_EGG and not self.dead and self.state == ItemState.FREE

    def collision_chunks(self):
        self.collide_with_objects = self.state not in (
            ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE) and not self.dead
        return (self,) if self.collide_with_objects else ()

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        self.last_rotation = self.rotation
        dx, dy = _dirvec(self.x, self.y, gx, gy)
        self.rotation = (dy, -dx) if self.dead else (dy, -abs(dx))

    # ── 吃 / 打 ──
    def bite(self) -> bool:
        """被啃一口：原版幼体 5 口吃完（FoodPoints 2）。"""
        if self.eaten == 0:
            self.eaten = EATEN_COUNTDOWN
            self.die()
            return True
        return False

    @property
    def DAMAGE_RESISTANCE(self) -> float:
        return SMALL_HP if self.age != AGE_BIG else BIG_HP

    def hurt(self, dmg: float, kx: float = 0.0, ky: float = 0.0) -> bool:
        """被武器打中：原版 Violence num = damage / baseDamageResistance。

        矛 1.0 / 0.4(成) = 2.5 ≥ instantDeathDamageLimit 1.2 → 一矛毙命；
        幼体 1.0 / 0.2 = 5 → 同样一矛。石头 0.01/0.4 = 0.025 → 只被震飞。
        """
        self.vx += kx * 0.35
        self.vy += ky * 0.35
        if self.health > 0.0:
            self.health -= dmg / max(1e-6, self.DAMAGE_RESISTANCE)
        if self.health <= 0.0 and not self.dead:
            self.die()
            return True
        return self.dead

    def die(self, enrage: bool = True) -> None:
        """死亡：NeedleWorm.cs:128-158 —— 死时惨叫，成体会被激怒（原版母亲复仇）。"""
        if self.dead:
            return
        self.dead = True
        self.flying_target = 0.0
        self.stab_t = 0
        if self.age == AGE_SMALL:
            self.scream = 1.0
            self.has_screamed = True
        elif enrage:
            self.scream = 1.0

    def enrage(self, focus=None) -> None:
        """被激怒：NeedleWormAI.Behavior.Attack（Stab 冲击）。"""
        if self.age != AGE_BIG or self.dead:
            return
        self.angry = max(self.angry, ANGRY_TICKS)
        self.scream = max(self.scream, 0.6)
        if focus is not None:
            self.focus = focus

    # ── 主循环 ──
    def step(self, WL: float, HL: float, threats=()) -> None:
        self.gfx_tick()
        if self.state in (ItemState.MOUSE, ItemState.CARRIED):
            self._step_chain(HL)
            return
        self.last_x, self.last_y = self.x, self.y
        if self.state in (ItemState.GONE, ItemState.EATEN):
            return
        if self.eaten > 0:
            self.eaten -= 1
            if self.eaten == 0:
                self.state = ItemState.EATEN
                return
        if self.age == AGE_EGG:
            self._step_egg(WL, HL)
            return
        self._step_fly(WL, HL, threats)
        self._step_chain(HL)

    def _step_egg(self, WL, HL) -> None:
        """卵：普通坠落 + 落地轻微摆动；落地后计时孵化成幼体。"""
        self.flying_target = 0.0
        self.vy += self.gravity * self.room_gravity
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.vx *= self.air_friction
        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        if self._contact_floor or self._contact_x != 0:
            self.vx *= 0.72
            self._wobble *= EGG_WOBBLE_DECAY
            if abs(self._wobble) < 0.01:
                self._wobble = 0.0
        if not self.dead and not self.hatched:
            self.hatch_t -= 1
            if self.hatch_t <= 0:
                self.hatched = True
                self._wobble = 1.0
        s = self.seg[0]
        s.lx, s.ly = s.x, s.y
        s.x, s.y = self.x, self.y

    def _step_fly(self, WL, HL, threats) -> None:
        """飞行：Idle 游走 / Flee 逃 / Attack 冲撞（NeedleWormAI）。"""
        self.last_wing_flap = self.wing_flap
        self.wing_flap += (0.4 + self._rng.random() * 0.05) * max(0.0, self.flying)
        self.flying_target = 1.0
        self.angry = max(0, self.angry - 1)
        ax = ay = 0.0
        # 1) 愤怒的成体：追击 focus（NeedleWormAI.Behavior.Attack）
        if self.angry > 0 and self.age == AGE_BIG and self.focus is not None:
            self.charge = min(1.0, self.charge + 1.0 / 90.0)
            ux, uy = _dirvec(self.x, self.y, self.focus[0], self.focus[1])
            ax += ux * CHARGE_ACCEL * (1.0 + self.charge)
            ay += uy * CHARGE_ACCEL * (1.0 + self.charge)
            self._facing_from(ux)
        else:
            self.charge = max(0.0, self.charge - 1.0 / 60.0)
            # 2) 逃：猫贴太近（幼体阈值更小、逃得更急）
            threat = None
            bestd = FLEE_R if self.age == AGE_SMALL else FLEE_R * 0.7
            for _obj, ox, oy in threats:
                d = math.hypot(ox - self.x, oy - self.y)
                if d < bestd:
                    bestd, threat = d, (ox, oy)
            if threat is not None and self.angry <= 0:
                ux, uy = _dirvec(threat[0], threat[1], self.x, self.y)
                ax += ux * FLEE_ACCEL
                ay += uy * FLEE_ACCEL * 0.7 - 0.10
                self._facing_from(ux)
            else:
                self._wander(WL, HL)
                ux, uy = _dirvec(self.x, self.y, self._goal[0], self._goal[1])
                ax += ux * FLY_ACCEL
                ay += uy * FLY_ACCEL * 0.7
                if abs(ux) > 0.12:
                    self._facing_from(ux)
        self.vx += ax
        self.vy += ay + self.gravity * self.room_gravity * (1.0 - LIFT)
        self.vx *= AIR_FRICTION
        self.vy *= AIR_FRICTION
        sp = math.hypot(self.vx, self.vy)
        cap = CHARGE_SPEED if self.charge > 0.2 else FLY_SPEED_MAX
        if sp > cap:
            self.vx *= cap / sp
            self.vy *= cap / sp
        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        if self._contact_floor or self._contact_x != 0:
            # 撞墙就往上顶一下（原版面条蝇贴墙会抖着爬开）
            th = threats[0] if threats else None
            self.vy = min(self.vy, -0.8)
            if abs(self.vx) < 0.3:
                self.vx += (1.0 if self.facing >= 0 else -1.0) * 0.45
            self._goal_timer = GOAL_REPICK

    def _facing_from(self, ux: float) -> None:
        if abs(ux) > 0.05:
            self.facing = 1 if ux > 0 else -1

    def _wander(self, WL, HL) -> None:
        self._goal_timer += 1
        d = math.hypot(self._goal[0] - self.x, self._goal[1] - self.y)
        if d < 30.0 or self._goal_timer > GOAL_REPICK:
            m = WALL_PAD
            self._goal = (self._rng.uniform(m, max(m, WL - m)),
                          self._rng.uniform(m, max(m, HL * 0.72)))
            self._goal_timer = 0

    def _step_chain(self, HL) -> None:
        """链条：吻尖→尾。吻随体轴前伸（NeedleWormGraphics.Update:295-325），
        躯干由飞行驱动、体节互推，尾部自然拖行 + 正弦摆动（NeedleWorm.cs:388-400）。"""
        if self.age == AGE_EGG:
            return
        sn = self.snout_n
        body0 = self.seg[sn]
        body0.lx, body0.ly = body0.x, body0.y
        body0.x, body0.y = self.x, self.y   # 主躯干 = 飞行/拖拽的驱动点
        # 体轴（躯干 1 → 躯干 0），退化时用朝向
        if len(self.seg) > sn + 1:
            ux, uy = _dirvec(self.seg[sn + 1].x, self.seg[sn + 1].y, body0.x, body0.y)
        else:
            ux, uy = float(self.facing), 0.0
        if abs(ux) + abs(uy) < 1e-6:
            ux, uy = float(self.facing), 0.0
        self.lzrot, self.zrot = self.zrot, (ux, uy)
        self.crawl_sin += 0.14 * max(0.0, self.flying)
        # 吻：从躯干前端伸出，常态略下垂（原版 snout 段 vel += (0,-0.9)）
        num = (3.0 + 2.0 * inv_lerp(0.5, 0.0, self.fang_out)) * self.snout_len
        if self.age == AGE_SMALL:
            num *= 0.85
        bx = body0.x + ux * (body0.rad + 5.0)
        by = body0.y + uy * (body0.rad + 5.0)
        px, py = -uy, ux
        droop = (1.0 - inv_lerp(0.25, 0.0, self.fang_out)) * (1.0 - self.scream)
        for k in range(sn - 1, -1, -1):
            f = (sn - 1 - k) / max(1, sn - 1)
            tx = bx + ux * (num * (sn - 1 - k)) + px * (droop * f * 2.0)
            ty = by + uy * (num * (sn - 1 - k)) + py * (droop * f * 2.0) + droop * f * 1.5
            s = self.seg[k]
            s.lx, s.ly = s.x, s.y
            s.x += (tx - s.x) * 0.45
            s.y += (ty - s.y) * 0.45
        # 躯干 + 尾：依次跟随前一节
        grav = 0.16 * self.room_gravity
        for i in range(sn + 1, len(self.seg)):
            s = self.seg[i]
            p = self.seg[i - 1]
            s.lx, s.ly = s.x, s.y
            dx, dy = s.x - p.x, s.y - p.y
            d = math.hypot(dx, dy)
            ux2, uy2 = ((dx / d, dy / d) if d > 1e-6 else (ux, uy))
            tx = p.x + ux2 * s.dist
            ty = p.y + uy2 * s.dist
            s.x += (tx - s.x) * 0.5
            s.y += (ty - s.y) * 0.5 + grav
            # 摆动：从躯干到尾部逐渐变强
            wave = math.sin(self.crawl_sin + i * 0.55) * (0.35 + 0.045 * (i - sn))
            s.x += -(uy2) * wave
            s.y += (ux2) * wave
            floor = HL - s.rad * 0.5
            if s.y > floor:
                s.y = floor
        # 头节位置同步（主躯干 = 交互/抓取判定的锚点）
        self.head_rad = body0.rad

    def _collide(self, WL, HL) -> None:
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb,
                          open_sides=self.dead)

    # ── 渲染状态推进 ──
    def gfx_tick(self) -> None:
        """NeedleWormGraphics.Update：flying 插值、獠牙伸出、惨叫抖动、眨眼。"""
        self.flying = _lerp_tick(self.flying, self.flying_target, 0.11, 1.0 / 30.0)
        target_fang = 1.0 if (self.age == AGE_BIG and
                              (self.charge > 0.5 or self.angry > 0)) else 0.0
        self.fang_out = _lerp_tick(self.fang_out, target_fang, 0.06, 0.02)
        self.scream = max(0.0, self.scream - 0.02)
        self.scream_counter = max(0.0, self.scream_counter - 0.02)
        if self.dead:
            self.blink = 0
        else:
            self.blink += 0.0025 + self._rng.random() * 0.001

    # ── 被抓住（猫手/鼠标拖拽）：原版 SmallNeedleWorm 会惨叫求援 ──
    def on_grabbed(self, grabber=None) -> None:
        """SmallNeedleWorm.cs:136-158：被 Player 抓 0.2 秒后开始惨叫，1 秒后尖叫求援。"""
        if self.age != AGE_SMALL or self.dead:
            return
        if self.scream_counter <= 0.0 and not self.has_screamed:
            self.scream_counter = 0.01
        self.scream = max(self.scream, 0.35)

    def scream_tick(self) -> bool:
        """推进惨叫计时；返回 True = 本 tick 发出「尖叫」（激怒所有成体）。"""
        if self.scream_counter <= 0.0 or self.has_screamed:
            return False
        self.scream_counter += 1.0 / 190.0
        if self.scream_counter > 1.0:
            self.has_screamed = True
            self.scream = 1.0
            return True
        return False

    def stab_reach(self):
        """獠牙尖位置（BigNeedleWorm.cs:37 FangPos = 躯干0 + 体轴 * fangLength）。"""
        if self.age != AGE_BIG:
            return None
        sn = self.snout_n
        if len(self.seg) <= sn:
            return None
        return (self.seg[0].x, self.seg[0].y)

    def can_stab(self) -> bool:
        """原版：attackReady > 0.8 且獠牙伸出时才撞得到。"""
        return self.age == AGE_BIG and self.angry > 0 and self.charge > 0.3


# ── 小工具：原版 Custom 的随机变体与 LerpAndTick ──
def _scurve(x, k):
    """原版 Custom.SCurve（RWCustom/Custom.cs）—— 与 lizard._scurve 同一实现。"""
    x = x * 2.0 - 1.0
    if x < 0.0:
        x = abs(1.0 + x)
        return k * x / (k - x + 1.0) * 0.5
    k = -1.0 - k
    return 0.5 + k * x / (k - x + 1.0) * 0.5


def random_deviation(rng, k):
    return _scurve(rng.random() * 0.5, k) * 2.0 * (1.0 if rng.random() < 0.5 else -1.0)


def _clamped_var(rng, base, max_dev, k):
    return clampf(base + random_deviation(rng, k) * max_dev, 0.0, 1.0)


def _wrapped_var(rng, base, max_dev, k):
    return (base + random_deviation(rng, k) * max_dev + 1.0) % 1.0


def _lerp_map(v, a, b, A, B, e=1.0):
    if a == b:
        return A
    t = clampf((v - a) / (b - a), 0.0, 1.0)
    if e != 1.0:
        t = math.pow(t, e)
    return A + (B - A) * t


def _lerp_tick(cur, target, lerp_k, tick):
    """Custom.LerpAndTick：向目标插值，但每 tick 至少走 tick 步（原版常用）。"""
    d = target - cur
    if abs(d) <= tick:
        return target
    step = d * lerp_k
    if abs(step) < tick:
        step = tick if d > 0 else -tick
    return cur + step


def _dirvec(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)
