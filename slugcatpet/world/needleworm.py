# -*- coding: utf-8 -*-
"""面条蝇 NeedleWorm（原版 MSC 生物）：卵 / 幼体 / 成体三种年龄段。

反编译依据（work/scratch/decomp_full，坐标一律换成 y↓）：
- NeedleWorm.cs:74-111   体节数/半径/质量/物理常量（airFriction 0.999、gravity 0.9、
                         bounce 0.3、surfaceFriction 0.4、waterFriction 0.96、
                         buoyancy 1.05）、bodyChunks 3(幼)/5(成)、tail 4/10 行
- NeedleWorm.cs:168-366  Update：尾链绳、体节互推、绳模式开关
- NeedleWorm.cs:380-438  Act：flying、extraMovementForce、reallyStuckAtSamePos
- NeedleWorm.cs:602-623  MoveUpFromFloor：飞到 MinFlyHeight 之上
- NeedleWorm.cs:625-811  Fly：路径目标、卡住时的抖动、出屏回推
- NeedleWorm.cs:813-831  Crawl
- NeedleWorm.cs:833-858  SinMovementInBody：身体正弦波（crawlSin）
- NeedleWormAI.cs:135-214 Update：flySpeed / flyHeightAdd / MinFlyHeight
- NeedleWormAI.cs:254-303 LikeRoom / MigrationBehaviorRoll
- NeedleWormAI.cs:306-373 UncomfortableToAfraidRelationshipModifier：<5 tiles 贴脸 → Afraid
- BigNeedleWorm.cs:59-173  attackReady / chargingAttack / 獠牙撞击 FangPos（Violence 0.05/stun 30）
- BigNeedleWorm.cs:175-191 SmallCry / BigCry
- BigNeedleWorm.cs:193-242 Fly：attackCounter→attackReady、同族互刺闪避
- BigNeedleWorm.cs:244-304 StuckInChunk：扎进生物
- BigNeedleWorm.cs:306-355 StuckInWall：0.0125/tick，>1 挣脱（浮点 17/19 反冲、lameCounter 7）
- BigNeedleWorm.cs:357-475 Swish：6 tick 突刺；撞地→卡墙，撞生物→Violence(Stab,1.22,60)
- BigNeedleWorm.cs:477-581 AttackCharge：蓄力位移、满蓄 + 视线 → Swish
- BigNeedleWorm.cs:583-594 FlyingWeapon：只对朝自己飞来的投掷物反应
- BigNeedleWorm.cs:596-626 Dodge：10 tick 冷却、最近 chunk 侧移 12*flying
- BigNeedleWorm.cs:628-635 HitThisObject：成体打不到幼体
- BigNeedleWormAI.cs:66-84   SmallRespondCry / BigRespondCry
- BigNeedleWormAI.cs:272-323 AttackBehavior：idealAttackDist 200(成体 400)、attackFromPos 掷骰
- BigNeedleWormAI.cs:333-413 UpdateDynamicRelationship：持幼体/蛋 → Attacks 1.0；
                            tempLike < -0.25 → Attacks|tempLike|；否则 Uncomfortable→Afraid
- BigNeedleWormAI.cs:415-455 SocialEvent：五种攻击事件扣 tempLike / like
- SmallNeedleWorm.cs:14,70-76  bites = 5；FoodPoints = 2
- SmallNeedleWorm.cs:108-173    被抓 → screamCounter（每 tick +1/190）→ Die / Scream
- SmallNeedleWorm.cs:223-250    HangOnMom：挂母亲尾节（30px、0.95/0.05 力分配）
- SmallNeedleWorm.cs:252-298    Act：每 17 tick 掷骰找尾节空位 Grab
- SmallNeedleWorm.cs:300-345    Scream / ClosestCreature（优先 grabber）
- SmallNeedleWorm.cs:356-371    BitByPlayer：一口一口吃，bites<1 才销毁
- SocialMemory.cs               EvenOutTemps / InfluenceTempLike / InfluenceLike
- StaticWorld.cs:3488-3520      伤害抗性 0.4(成)/0.2(幼)、instantDeathDamageLimit 1.2
- StaticWorld.cs:3682-3684      LizardTemplate → 成体 Eats 0.25 / 幼体 Eats 0.3
- StaticWorld.cs:4007           BigNeedleWorm → BigNeedleWorm Attacks 0.9（同族永远敌对）
- NeedleWormGraphics.cs:146-187 个体随机（wingsSize/legsFac/fatness/snoutLength/hue/…）
- NeedleWormGraphics.cs:709-720 GraphSegmentRad（吻 1.0 / 躯干 chunkRad×fatness / 尾锥化）
- NeedleWormGraphics.cs:722-787 ApplyPalette（hue+0.478 系列）
- NeedleWormGraphics.cs:267-294 獠牙 fangOut/fangBlack（伸出后由白转黑）
- NeedleWormGraphics.cs:549-582 4 张翅（2 对 × 左右）
- NeedleWormGraphics.cs:583-600 腿：幼体 1 对（退化）、成体 3 对
- NeedleEgg.cs                  卵：挂在藤上 / 落地会自己动 / 孵化出 2 只幼体

坐标 y↓（原版 y↑，这里全部换算）；像素 1:1（同 lizard.BODY_SCALE）。
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
AGE_ROLL = ((AGE_SMALL, 0.5), (AGE_BIG, 0.5))     # 随机生成不带卵（卵是物件，不是面条蝇）

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
EGG_HATCH_SPAWN = 2             # wiki：孵化出 2 只幼体

# ── 尺度：原版 1 tile = 20px（桌宠同样 1:1）──
TILE = 20.0
CLOSE_TILES = 5.0               # NeedleWormAI.cs:306 起：<5 tiles 视为贴脸
UNCLOSE_TILES = 10.0            # 同处：>10 tiles 且空间开阔才解除
HOSTILE_TEMP = -0.25            # BigNeedleWormAI.cs:404 tempLike < -0.25 → Attacks
# 静态关系（StaticWorld：BigNeedleWorm → Slugcat = Eats 0.25）让成体远远地就把
# 猫当猎物扑上去；但 AI.cs UncomfortableToAfraidRelationshipModifier 会在
# Lerp(150, 450, nervous) 以内把 Attacks 改判成 Afraid —— 贴脸反而掉头跑。
PREY_W = 0.25                   # StaticWorld：BigNeedleWorm → Slugcat = Eats
AFRAID_MIN = 150.0              # UncomfortableToAfraidRelationshipModifier minDist
AFRAID_MAX = 450.0              # 同处 maxDist（按 nervous 性格插值）
TEMP_EVEN_SPEED = 0.0005        # BigNeedleWormAI.cs:121 EvenOutAllTemps(0.0005f)
# SocialEventRecognizer.EventID → 扣 tempLike 的量（BigNeedleWormAI.cs:415-455）
SOCIAL_INFLUENCE = {
    "NonLethalAttackAttempt": 0.1,
    "NonLethalAttack": 0.2,
    "LethalAttackAttempt": 0.4,
    "LethalAttack": 0.6,
    "Killing": 0.9,
}

# ── 飞行：NeedleWormAI ──
LIFT = 0.9                      # 扑翅抵消的重力比例（原版靠翅膀持续升力悬停）
FLY_ACCEL = 0.32
FLY_SPEED_MAX = 4.6
SLOW_FLY_MIN = 0.25             # NeedleWorm.SlowFlySpeed
SLOW_FLY_SMALL = 0.7
SLOW_FLY_BIG = 0.5
FLY_HEIGHT_RISE = 1.0 / 60.0    # NeedleWormAI.cs:182
FLY_HEIGHT_FALL = 0.0045454544  # NeedleWormAI.cs:186
MIN_FLY_TILES = 4               # NeedleWormAI.cs:200 MinFlyHeight = 4 + 4*flyHeightAdd
GOAL_REPICK = 150
WALL_PAD = 22.0

# ── 成体攻击：BigNeedleWorm ──
IDEAL_ATTACK_DIST = 200.0       # BigNeedleWormAI.cs:283（打成体时 400）
IDEAL_ATTACK_DIST_ADULT = 400.0
ATTACK_DIST_800 = 800.0         # BigNeedleWormAI.cs:313
ATTACK_DIST_300 = 300.0         # BigNeedleWormAI.cs:307
READY_LO = 65.0                 # BigNeedleWorm.cs:210 InverseLerp(65, 85, attackCounter)
READY_HI = 85.0
READY_TICK = 1.0 / 160.0
CHARGE_STEP = 55.0              # BigNeedleWorm.cs:537 /55f
UNCHARGE_STEP = 30.0            # 同处 /30f
SWISH_TICKS = 6                 # BigNeedleWorm.cs:577
FANG_LENGTH = 50.0              # BigNeedleWorm.cs:15
STAB_DAMAGE = 1.22              # BigNeedleWorm.cs:454 Violence(Stab, 1.22f, 60f)
STAB_STUN = 60.0
POKE_DAMAGE = 0.05              # BigNeedleWorm.cs:168 Violence(Stab, 0.05f, 30f)
POKE_STUN = 30.0
STUCK_WALL_RATE = 0.0125        # BigNeedleWorm.cs:328（0.0125/tick，>1 挣脱）
STUCK_CHUNK_RATE = 0.0035714286  # BigNeedleWorm.cs:261
DODGE_COOLDOWN = 10             # BigNeedleWorm.cs:602
DODGE_PUSH = 12.0               # BigNeedleWorm.cs:617
LAME_TICKS = 7                  # BigNeedleWorm.cs:353
RESPOND_CRY = (10, 50)          # BigNeedleWormAI.SmallRespondCry
RESPOND_BIG = (6, 16)           # BigNeedleWormAI.BigRespondCry

# ── 吃 / 伤害 ──
SMALL_BITES = 5                 # SmallNeedleWorm.cs:14
SMALL_FOOD = 2                  # FoodPoints => 2
SMALL_HP = 0.2                  # StaticWorld baseDamageResistance
BIG_HP = 0.4
INSTANT_LIMIT = 1.2             # StaticWorld instantDeathDamageLimit

# ── 渲染外形：NeedleWormGraphics.cs:146-187 ──
# 翅膀挂载的躯干节序号（相对 snout_n 的偏移）：幼体 2 对都挂在 chunk1，
# 成体分别挂 chunk1 / chunk2（NeedleWormGraphics.cs:204）。
WING_SEG = {AGE_SMALL: (1, 1), AGE_BIG: (1, 2)}
EGG_SHELL_RGB = (36, 30, 34)


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
    """绳长用半径：NeedleWorm.cs:878-885 GetSegmentRadForRopeLength。"""
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
                 # 飞行 / 渲染
                 "flying", "flying_target", "wing_flap", "last_wing_flap",
                 "fang_out", "last_fang_out", "fang_black", "thin_tail",
                 "scream", "scream_counter", "has_screamed", "crawl_sin",
                 "blink", "zrot", "lzrot", "fly_speed", "fly_height_add",
                 "hue", "lightness", "hue_div", "fatness", "wings_size",
                 "legs_fac", "snout_len", "cos_bools",
                 # 关系（SocialMemory）
                 "temp_like", "like", "close_flags", "hold_child",
                 # 成体攻击
                 "attack_counter", "attack_ready", "charging_attack", "swish_dir",
                 "swish_counter", "stuck_pos", "stuck_dir", "stuck_time",
                 "lame_counter", "dodge_delay", "stun", "attack_from", "attack_target",
                 "target_vel", "target_chunk", "respond_cry", "keep_close",
                 "follow", "fleeing", "threat", "prey", "focus", "attack_event",
                 "poke_event", "last_stuck_tip", "ideal_dist",
                 "nervous",
                 # 幼体 / 卵
                 "mother", "mom_seg", "follow_cat", "hatch_t", "hatched",
                 "hatch_spawn", "_wobble", "_goal", "_goal_timer",
                 "_contact_floor", "_contact_x", "_rng")

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
        self.is_tame_food = self.age != AGE_EGG   # StaticWorld：蜥蜴会吃面条蝇（卵是物件）
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
        self.fly_speed = 0.0
        self.fly_height_add = 0.0
        self.fang_out = self.last_fang_out = 0.0
        self.fang_black = 0.0
        self.thin_tail = 0.0
        self.scream, self.scream_counter, self.has_screamed = 0.0, 0.0, False
        self.crawl_sin = rng.uniform(0.0, 6.28)
        # ── 关系（SocialMemory）：key = 对方 uid ──
        self.temp_like = {}
        self.like = {}
        self.close_flags = {}               # NeedleWormTrackState.close
        self.hold_child = {}                # NeedleWormTrackState.holdingChild
        # ── 成体攻击 ──
        self.ideal_dist = IDEAL_ATTACK_DIST
        self.nervous = rng.random()         # personality.nervous：决定「多近就怂」
        self.attack_counter = 0
        self.attack_ready = 0.0
        self.charging_attack = 0.0
        self.swish_dir = None
        self.swish_counter = 0
        self.stuck_pos = None
        self.stuck_dir = (0.0, 0.0)
        self.stuck_time = 0.0
        self.lame_counter = 0
        self.dodge_delay = 0
        self.stun = 0
        self.attack_from = (float(x), float(y))
        self.attack_target = (float(x), float(y))
        self.target_vel = (0.0, 0.0)
        self.target_chunk = rng.randrange(100)
        self.respond_cry = 0
        self.keep_close = None
        self.follow = None
        self.fleeing = False
        self.threat = None
        self.prey = None
        self.focus = None
        self.attack_event = None
        self.poke_event = None
        self.last_stuck_tip = None
        # ── 幼体 / 卵 ──
        self.mother = None
        self.mom_seg = -1
        self.follow_cat = False
        self.hatch_t = rng.randint(*HATCH_TICKS) if self.age == AGE_EGG else 0
        self.hatched = False
        self.hatch_spawn = 0
        self._wobble = rng.uniform(-0.5, 0.5)
        self._goal = (x + rng.uniform(-70.0, 70.0), y - rng.uniform(0.0, 90.0))
        self._goal_timer = 0
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
        self.wing_flap, self.last_wing_flap = 0.0, 0.0
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
        step = 3.0 * self.snout_len            # NeedleWormGraphics.cs:311
        for i in range(sn):
            segs.append(_Seg(x, y - (sn - i) * step, 1.0, step))
        y_body = y
        for i in range(self.body_n):
            nxt = min(i + 1, self.body_n - 1)
            segs.append(_Seg(x, y_body, rads[i] * fat,
                             _rope_rad(self.age, i) + _rope_rad(self.age, nxt)))
            y_body += segs[-1].dist
        last = rads[-1] * fat
        for i in range(TAIL_ROWS[self.age]):
            t = (i + 1.0) / TAIL_ROWS[self.age]
            j = self.body_n + i
            segs.append(_Seg(x, y_body, lerp(last, 0.9, t),
                             _rope_rad(self.age, j) + _rope_rad(self.age, j + 1)))
            y_body += segs[-1].dist
        segs[-1].dist = segs[-2].dist if len(segs) > 1 else 1.0
        return segs

    def snap_to(self, x: float, y: float) -> None:
        """把整条虫硬搬到 (x,y)（放置预览用：预览不 tick，不搬整条链会留在原地）。"""
        dx, dy = float(x) - self.x, float(y) - self.y
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        for s in self.seg:
            s.x += dx
            s.y += dy
            s.lx = s.x
            s.ly = s.y

    # ── 查询 ──
    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def catchable(self) -> bool:
        """能徒手抓：卵（NeedleEgg : PlayerCarryableItem）与幼体（IPlayerEdible）。

        成体 BigNeedleWorm 不是 IPlayerEdible，抓不走（原版徒手抓不到）。
        """
        return (self.state == ItemState.FREE and self.held_by_hand is None
                and not self.dead and self.age == AGE_SMALL)

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
        """被啃一口：SmallNeedleWorm.cs:356-371 BitByPlayer —— bites--，<1 才吃完。"""
        if self.age != AGE_SMALL:
            return False
        self.bites -= 1
        if self.bites < 1:
            self.die()                        # 被啃完：原版 ObjectEaten → 生物销毁
            self.state = ItemState.EATEN
            return True
        return False

    @property
    def DAMAGE_RESISTANCE(self) -> float:
        return SMALL_HP if self.age != AGE_BIG else BIG_HP

    def hurt(self, dmg: float, kx: float = 0.0, ky: float = 0.0, by=None,
             lethal: bool = True) -> bool:
        """被武器打中：原版 Violence num = damage / baseDamageResistance。

        矛 1.0 / 0.4(成) = 2.5 ≥ instantDeathDamageLimit 1.2 → 一矛毙命；
        幼体 1.0 / 0.2 = 5 → 同样一矛。石头 0.01/0.4 = 0.025 → 只被震飞。
        `by` = 攻击者 uid（用于成体的 tempLike 记账）。
        """
        self.vx += kx * 0.35
        self.vy += ky * 0.35
        if by is not None and self.age == AGE_BIG:
            self.social_event("LethalAttack" if lethal else "NonLethalAttack",
                              by, victim_is_self=True, victim_dead=False)
        if self.health > 0.0:
            self.health -= dmg / max(1e-6, self.DAMAGE_RESISTANCE)
        if self.health <= 0.0 and not self.dead:
            if by is not None and self.age == AGE_BIG:
                self.social_event("Killing", by, victim_is_self=True, victim_dead=False)
            self.die()
            return True
        return self.dead

    def die(self) -> None:
        """死亡：SmallNeedleWorm.cs:347-354 Die() 会把惨叫计时拨到 0.01（之后仍会惨叫）。"""
        if self.dead:
            return
        self.dead = True
        self.flying_target = 0.0
        self.swish_counter = 0
        self.swish_dir = None
        self.charging_attack = 0.0
        if self.age == AGE_SMALL and self.scream_counter == 0.0:
            self.scream_counter = 0.01
        elif self.age == AGE_BIG:
            self.scream = max(self.scream, 0.5)

    def enrage(self, uid=None) -> None:
        """被激怒：BigNeedleWormAI.UpdateDynamicRelationship → Attacks（tempLike=-1）。"""
        if self.age != AGE_BIG or self.dead:
            return
        self.scream = max(self.scream, 0.6)
        if uid is not None:
            self.like[uid] = -1.0
            self.temp_like[uid] = -1.0

    # ── 关系（SocialMemory + BigNeedleWormAI.UpdateDynamicRelationship）──
    def influence_temp_like(self, uid, change: float) -> None:
        self.temp_like[uid] = clampf(self.temp_like.get(uid, 0.0) + change, -1.0, 1.0)

    def influence_like(self, uid, change: float) -> None:
        self.like[uid] = clampf(self.like.get(uid, 0.0) + change, -1.0, 1.0)

    def social_event(self, kind: str, subject_uid, victim_is_self: bool,
                     victim_dead: bool) -> None:
        """BigNeedleWormAI.cs:415-455 SocialEvent：攻击事件扣 tempLike / like。"""
        if subject_uid is None or self.age != AGE_BIG:
            return
        num = SOCIAL_INFLUENCE.get(kind, 0.0)
        if kind in ("NonLethalAttackAttempt", "LethalAttackAttempt") and not victim_is_self:
            num /= 2.0
        if victim_dead:
            num /= 3.0
        if victim_is_self:
            num /= 2.0
        self.influence_temp_like(subject_uid, -num)
        self.influence_like(subject_uid, -num * 0.1)

    def weapon_attempt(self, by, lethal: bool) -> None:
        """Weapon.cs:149-152：投掷物在 120px 内掠过 → Attack(Attempt) 社交事件。"""
        if self.dead or self.age != AGE_BIG or by is None:
            return
        self.social_event("LethalAttackAttempt" if lethal else "NonLethalAttackAttempt",
                          by, victim_is_self=True, victim_dead=False)

    def weapon_hit(self, by, lethal: bool) -> None:
        """Weapon.cs:383：投掷物命中 → Attack 社交事件。"""
        if self.dead or self.age != AGE_BIG or by is None:
            return
        self.social_event("LethalAttack" if lethal else "NonLethalAttack",
                          by, victim_is_self=True, victim_dead=False)

    def even_out_temps(self, speed: float = TEMP_EVEN_SPEED) -> None:
        """SocialMemory.EvenOutAllTemps：tempLike 每 tick 朝 like 靠 speed。"""
        for uid, tl in self.temp_like.items():
            lk = self.like.get(uid, 0.0)
            if tl < lk:
                self.temp_like[uid] = min(lk, tl + speed)
            else:
                self.temp_like[uid] = max(lk, tl - speed)

    def hostile_to(self, cat) -> bool:
        """BigNeedleWormAI.cs:378-410：持幼体/蛋 → Attacks 1.0；tempLike<-0.25 → Attacks。"""
        if self.age != AGE_BIG or self.dead:
            return False
        if self.hold_child.get(cat["uid"]):
            return True
        return self.temp_like.get(cat["uid"], 0.0) < HOSTILE_TEMP

    # ── 主循环 ──
    def step(self, WL: float, HL: float, threats=(), cats=None, adults=(),
             weapons=()) -> None:
        """一 tick。cats/adults/weapons 由 items 组装（见 items._needleworm_cats）。"""
        self.gfx_tick()
        self.attack_event = None
        self.poke_event = None
        if cats is None:
            cats = [_cat_from_threat(t) for t in threats]
        if self.age == AGE_SMALL:
            self._step_scream(cats)          # 被抓住时也在跑（SmallNeedleWorm.Update:136）
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
        self.even_out_temps()
        if self.age == AGE_SMALL:
            self._step_small(WL, HL, cats)
        else:
            self._step_big(WL, HL, cats, adults, weapons)
        self._step_chain(HL)

    # ── 卵：NeedleEgg（可搬运、落地自己动、孵化出 2 只幼体）──
    def _step_egg(self, WL, HL) -> None:
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
        # wiki：卵在地上/挂着时会自己小幅移动，被拿在手里偶尔发抖
        if self._rng.random() < 1.0 / 90.0:
            self._wobble = self._rng.uniform(-0.6, 0.6)
        if not self.dead and not self.hatched:
            self.hatch_t -= 1
            if self.hatch_t <= 0:
                self.hatched = True
                self.hatch_spawn = EGG_HATCH_SPAWN
                self._wobble = 1.0
        s = self.seg[0]
        s.lx, s.ly = s.x, s.y
        s.x, s.y = self.x, self.y

    # ── 幼体：惨叫链（SmallNeedleWorm.cs:108-173 / 209-345）──
    def _holder(self, cats):
        """谁抓着我（优先取手上那只猫）。"""
        for c in cats:
            b = c.get("body")
            if b is not None and getattr(b, "carried_fruit", None) is self:
                return c
        return None

    def _step_scream(self, cats) -> None:
        rng = self._rng
        holder = self._holder(cats)
        grabbed = self.state in (ItemState.MOUSE, ItemState.CARRIED)
        saint = bool(holder is not None and holder.get("saint"))
        # SmallNeedleWorm.cs:136：被抓即开始计时；圣徒抓幼体不叫（wiki）
        if not self.dead and grabbed and self.scream_counter == 0.0 and not saint:
            self.scream_counter = 0.01
        if self.scream_counter <= 0.0 or self.has_screamed:
            return
        prev = self.scream_counter
        self.scream_counter += 1.0 / 190.0
        if prev <= 0.2 < self.scream_counter:
            self.die()
        if self.scream_counter > 1.0:
            self._scream(cats)
        elif math.floor(prev * 4.0) != math.floor(self.scream_counter * 4.0):
            self._small_scream(holder is not None, holder)
        m = self.mother
        if m is not None and not m.dead:
            closest = self._closest_creature(cats, holder)
            if m.keep_close is None or (closest is not None and rng.random() < 0.025):
                m.keep_close = closest

    def _small_scream(self, mother_respond: bool, holder=None) -> None:
        """SmallNeedleWorm.cs:209-221 SmallScream：小声叫 → 母亲应答。"""
        self.scream = lerp(0.4, 0.6, self._rng.random())
        m = self.mother
        if mother_respond and m is not None and not m.dead:
            if holder is not None:
                m.focus = holder
            m.small_respond_cry()

    def _scream(self, cats) -> None:
        """SmallNeedleWorm.cs:300-326 Scream：死 + 母亲 BigRespondCry + 锁定最近生物。"""
        if self.has_screamed:
            return
        self.die()
        self.scream = 1.0
        self.has_screamed = True
        m = self.mother
        if m is None or m.dead:
            return
        m.big_respond_cry()
        closest = self._closest_creature(cats, self._holder(cats))
        if closest is None:
            return
        uid = closest["uid"]
        m.like[uid] = -1.0            # AbstractMother.state.socialMemory...like = -1f
        m.temp_like[uid] = -1.0
        m.follow = closest            # abstractAI.followCreature = creature
        m.focus = closest

    def _closest_creature(self, cats, holder=None):
        """SmallNeedleWorm.cs:328-345 ClosestCreature：优先抓我的人，否则最近的大家伙。"""
        if holder is not None:
            return holder
        best, bestd = None, 1e18
        for c in cats:
            if c.get("dead") or c.get("small"):
                continue
            d = math.hypot(c["x"] - self.x, c["y"] - self.y)
            if d < bestd:
                best, bestd = c, d
        return best

    def on_grabbed(self, grabber=None, saint: bool = False) -> None:
        """外部（鼠标拖拽等）抓住我时手动触发的接口。"""
        if self.age != AGE_SMALL or self.dead or saint:
            return
        if self.scream_counter <= 0.0 and not self.has_screamed:
            self.scream_counter = 0.01
        self.scream = max(self.scream, 0.35)

    def scream_tick(self, cats=()) -> bool:
        """兼容旧接口：推进一次惨叫计时，返回本 tick 是否发出尖叫。"""
        before = self.has_screamed
        self._step_scream(list(cats))
        return self.has_screamed and not before

    # ── 幼体：被动飞行 / 挂母亲尾巴（SmallNeedleWorm.cs:223-298）──
    def _step_small(self, WL, HL, cats) -> None:
        # 挂母亲尾巴：距离 30px 时 0.95/0.05 分力（SmallNeedleWorm.HangOnMom:237-244）
        m = self.mother
        if (m is not None and not m.dead and self.mom_seg >= 0
                and m.age == AGE_BIG and m.stuck_pos is None
                and m.charging_attack < 0.1):
            idx = len(m.seg) - 1 - self.mom_seg
            if 0 <= idx < len(m.seg):
                tx, ty = m.seg[idx].x, m.seg[idx].y
                d = math.hypot(tx - self.x, ty - self.y)
                if d > 30.0:
                    ux, uy = _dirvec(self.x, self.y, tx, ty)
                    self.x += ux * (d - 30.0) * 0.95
                    self.y += uy * (d - 30.0) * 0.95
                    self.vx += ux * (d - 30.0) * 0.95
                    self.vy += uy * (d - 30.0) * 0.95
                self.flying_target = 1.0
                if self._rng.random() < 1.0 / 90.0:
                    self.flying = 1.0 if self._rng.random() < 0.5 else self._rng.random()
                self.crawl_sin += 0.2 * max(0.0, self.flying)
                return
        # 每 17 tick 掷骰找母亲尾节的空位（SmallNeedleWorm.Act:252-298）
        if (m is not None and not m.dead and m.age == AGE_BIG and self.mom_seg < 0
                and self._rng.random() < 1.0 / 17.0):
            n = max(1, len(m.seg) - 1)
            for k in range(min(8, n)):
                idx = len(m.seg) - 2 - k
                if idx < 0:
                    break
                if math.hypot(m.seg[idx].x - self.x, m.seg[idx].y - self.y) < 25.0:
                    self.mom_seg = k
                    break
        # 跟着蛞蝓猫（wiki：卵孵出的幼体跟着蛞蝓猫，遇到成体后改跟成体）
        if self.follow_cat and cats:
            alive = [c for c in cats if not c.get("dead") and not c.get("small")]
            if alive:
                t = min(alive, key=lambda c: math.hypot(c["x"] - self.x, c["y"] - self.y))
                self._fly(WL, HL, (t["x"], t["y"] - 40.0), False)
                return
        # 被猫/蜥蜴贴脸（<5 tiles）→ Afraid 逃跑
        threat = None
        bestd = CLOSE_TILES * TILE
        for c in cats:
            if c.get("dead"):
                continue
            d = math.hypot(c["x"] - self.x, c["y"] - self.y)
            if d < bestd:
                bestd, threat = d, c
        if threat is not None:
            ux, uy = _dirvec(threat["x"], threat["y"], self.x, self.y)
            self._fly(WL, HL, (self.x + ux * 120.0, self.y + uy * 90.0), True)
            return
        self._wander(WL, HL)
        self._fly(WL, HL, self._goal, False)

    def small_respond_cry(self) -> None:
        """BigNeedleWormAI.cs:66-72 SmallRespondCry：迟一点回一声。"""
        if self.respond_cry == 0:
            self.respond_cry = self._rng.randint(*RESPOND_CRY)

    def big_respond_cry(self) -> None:
        """BigNeedleWormAI.cs:74-84 BigRespondCry：先憋一会儿再大叫。"""
        self.respond_cry = -self._rng.randint(*RESPOND_BIG)

    # ── 成体：关系 → 行为 → 攻击（BigNeedleWorm / BigNeedleWormAI）──
    def _step_big(self, WL, HL, cats, adults, weapons) -> None:
        rng = self._rng
        if self.dodge_delay > 0:
            self.dodge_delay -= 1
        if self.lame_counter > 0:
            self.lame_counter -= 1
        if self.stun > 0:
            self.stun -= 1
        # respondScreamCounter（BigNeedleWormAI.cs:100-120）
        if self.respond_cry < 0:
            self.respond_cry += 1
            if self.respond_cry == 0:
                self.scream = 1.0
        elif self.respond_cry > 0:
            self.respond_cry -= 1
            if self.respond_cry == 0:
                self.scream = max(self.scream, 0.5)

        # 关系（BigNeedleWormAI.UpdateDynamicRelationship:333-413 +
        # AI.cs UncomfortableToAfraidRelationshipModifier）：静态关系是
        # Eats 0.25，所以成体在 afraid_range 之外会主动扑向猫；一进
        # afraid_range 就改判 Afraid 掉头跑。旧版只认「拿着幼体」，
        # 于是成体几乎从不出手 —— 这正是「攻击欲望」的缺口。
        afraid_range = lerp(AFRAID_MIN, AFRAID_MAX, self.nervous)
        threat = prey = None
        best_t = best_p = 1e18
        for c in cats:
            uid = c["uid"]
            d = math.hypot(c["x"] - self.x, c["y"] - self.y)
            self.hold_child[uid] = bool(c.get("holds_child"))
            if not c.get("dead"):
                if self.close_flags.get(uid):
                    if d > UNCLOSE_TILES * TILE:
                        self.close_flags[uid] = False
                elif d < CLOSE_TILES * TILE:
                    self.close_flags[uid] = True
            if self.hostile_to(c):
                if d < best_p:
                    best_p, prey = d, c
            elif c.get("dead"):
                pass                        # 尸体既不追也不躲
            elif self.close_flags.get(uid) or d < afraid_range:
                if d < best_t:
                    best_t, threat = d, c
            elif d < best_p:
                best_p, prey = d, c         # 静态 Eats 0.25：远远地就开始追
        for other in adults:            # StaticWorld.cs:4007 同族 Attacks 0.9
            if other is self or other.dead:
                continue
            d = math.hypot(other.x - self.x, other.y - self.y)
            if d < best_p:
                best_p, prey = d, _cat_from_other(other)
        self.threat, self.prey = threat, prey

        # attackCounter（BigNeedleWormAI.cs:148-212）
        self.attack_counter = max(0, self.attack_counter - 1)
        if rng.random() < 1.0 / 120.0:
            self.target_chunk = rng.randrange(100)

        if self.stuck_pos is not None:
            self._step_stuck(WL, HL)
            return
        if self.stun > 0:                     # 被晕住：不发起攻击，只被物理推着走
            self._drift(WL, HL)
            return
        if self.swish_counter > 0:
            self._step_swish(WL, HL)
            return
        if self.lame_counter >= 1:
            self._drift(WL, HL)
            return

        # 行为：ThreatTracker 权重高于 PreyTracker（NeedleWormAI.cs:60-66）
        if threat is not None:
            self.fleeing = True
            ux, uy = _dirvec(threat["x"], threat["y"], self.x, self.y)
            goal = (self.x + ux * 160.0, self.y + uy * 120.0)
            self._fly(WL, HL, goal, True)
        elif prey is not None:
            self.fleeing = False
            goal = self._attack_behavior(prey, WL, HL)
            self._fly(WL, HL, goal, False)
        elif self.keep_close is not None:
            self.fleeing = False
            target = self.keep_close          # 先取住：下面可能把 keep_close 清掉
            if rng.random() < 0.0125:
                self.keep_close = None
            goal = self._attack_behavior(target, WL, HL, charge=False)
            self._fly(WL, HL, goal, False)
        else:
            self.fleeing = False
            self._wander(WL, HL)
            self._fly(WL, HL, self._goal, False)

        # attackReady（BigNeedleWorm.cs:208-226）
        if self.attack_counter > READY_LO:
            self.attack_ready = _lerp_tick(
                self.attack_ready, inv_lerp(READY_LO, READY_HI, float(self.attack_counter)),
                0.0, READY_TICK)
        else:
            self.attack_ready = max(0.0, self.attack_ready - 1.0 / 60.0)
        if prey is not None and self.attack_ready > 0.5:
            self._attack_charge(prey)
        else:
            self.charging_attack = 0.0
        self.attack_counter = int(clampf(self.attack_counter, 0, 100))
        self._poke_check(cats)

    def _attack_behavior(self, target, WL, HL, charge: bool = True):
        """BigNeedleWormAI.cs:272-323 AttackBehavior：挑进攻点 + 预测瞄准。"""
        self.focus = target
        self.ideal_dist = (IDEAL_ATTACK_DIST_ADULT if target.get("other") is not None
                           else IDEAL_ATTACK_DIST)
        chunks = target.get("chunks") or ((target["x"], target["y"], 5.0, 0.0, 0.0),)
        ch = chunks[self.target_chunk % len(chunks)]
        tx, ty = ch[0], ch[1]
        vel = (ch[0] - ch[3], ch[1] - ch[4])
        # BigNeedleWormAI.cs:154：目标速度估计每 tick 衰减 1%。
        self.target_vel = (self.target_vel[0] * 0.99, self.target_vel[1] * 0.99)
        self.target_vel = _move_towards(self.target_vel, vel, 0.075)
        # attackFromPos：每 tick 在「当前进攻点 / 目标点」周围撒一个候选点，
        # 分数更低就换过去（BigNeedleWormAI.cs:299-306）。这是它「凑上去打」
        # 的欲望来源：之前只在偏差 >60px 且 1/60 概率才换，几乎不挪窝。
        ax, ay = self.attack_from
        if self.charging_attack < 0.5:
            bx, by = (ax, ay) if self._rng.random() < 0.5 else (tx, ty)
            r = 300.0 * self._rng.random()
            ang = self._rng.uniform(0.0, math.tau)
            tst = (bx + math.cos(ang) * r, by + math.sin(ang) * r)
            if (self._attack_pos_score(tst[0], tst[1], tx, ty, WL, HL)
                    < self._attack_pos_score(ax, ay, tx, ty, WL, HL)):
                ax, ay = tst
        ax = clampf(ax, WALL_PAD, max(WALL_PAD, WL - WALL_PAD))
        ay = clampf(ay, WALL_PAD, max(WALL_PAD, HL - self.rad - WALL_PAD))
        self.attack_from = (ax, ay)
        # 预判提前量（BigNeedleWormAI.cs:203）：距离进攻点越远，目标速度放得越大
        # （80px→0 倍，400px→30 倍，指数 0.35）。少了这一项就总是打在目标身后。
        lead_k = _lerp_map(math.hypot(ax - tx, ay - ty), 80.0, 400.0, 0.0, 30.0, 0.35)
        lead = (self.target_vel[0] * lead_k, self.target_vel[1] * lead_k)
        smooth = inv_lerp(0.9, 0.5, self.charging_attack)
        self.attack_target = (
            lerp(self.attack_target[0], tx + lead[0], smooth),
            lerp(self.attack_target[1], ty + lead[1], smooth))
        d = math.hypot(self.x - ax, self.y - ay)
        if charge and d < ATTACK_DIST_300:      # 只在 Attack 行为里加（原版 :307）
            self.attack_counter += 1
        if d < ATTACK_DIST_800:
            self.attack_counter += 1
        # 蓄力时往后一缩（BigNeedleWorm.cs:561）
        if charge and self.charging_attack > 0.05:
            ux, uy = _dirvec(ax, ay, self.attack_target[0], self.attack_target[1])
            return (ax - ux * (self.charging_attack * 100.0),
                    ay - uy * (self.charging_attack * 100.0))
        return (ax, ay)

    def _attack_pos_score(self, tx, ty, px, py, WL, HL) -> float:
        """BigNeedleWormAI.cs:325-349 AttackPosScore 的可移植部分。

        原版＝不可达/没视线→MaxValue、贴地<2→MaxValue、|理想距离-到目标距离|
        -50 起步、减去地形贴近度×20、加上离身体的距离/10，够近（<60）时按
        attackCounter 打折，出房间 +1000。宠物里没有寻路与视线网格，保留
        距离项与越界惩罚（越低越好）。
        """
        diag = math.hypot(tx - px, ty - py)
        num = max(0.0, abs(self.ideal_dist - diag) - 50.0)
        num += math.hypot(tx - self.x, ty - self.y) / 10.0
        if math.hypot(tx - self.x, ty - self.y) < 60.0:
            num -= float(self.attack_counter) * 5.0
        if tx < 0.0 or ty < 0.0 or tx > WL or ty > HL:
            num += 1000.0
        return num

    def _attack_charge(self, prey) -> None:
        """BigNeedleWorm.cs:477-581 AttackCharge：蓄力 → 满蓄且看得见獠牙 → Swish。"""
        ax, ay = self.attack_from
        tx, ty = self.attack_target
        ux, uy = _dirvec(ax, ay, tx, ty)
        # 身体指向与进攻方向一致 & 目标在视野内（原版 num3/num4）
        # :520 身体朝向取「体节中点 → 头」而不是「进攻点 → 身体」：取错源会让
        # num4 几乎永远为 0，蓄力条件不成立 → 成体几乎不出手。
        mid = self.seg[len(self.seg) // 2] if self.seg else None
        bx, by = _dirvec(mid.x if mid is not None else self.x,
                         mid.y if mid is not None else self.y, self.x, self.y)
        num3 = inv_lerp(0.5, 0.95, self.attack_ready)
        num4 = (inv_lerp(0.2, 0.9, ux * bx + uy * by)
                * inv_lerp(20.0, 50.0, math.hypot(tx - self.x, ty - self.y)))
        near = math.hypot(self.x - ax, self.y - ay) < 40.0     # 原版 :533 是 40f
        if self.charging_attack > 0.0 or (near and num4 > 0.5):
            if num3 >= 1.0:
                self.charging_attack = min(1.0, self.charging_attack
                                           + (0.1 + 0.9 * num4) / CHARGE_STEP)
            else:
                self.charging_attack = max(0.0, self.charging_attack - 1.0 / UNCHARGE_STEP)
        else:
            self.charging_attack = max(0.0, self.charging_attack - 1.0 / UNCHARGE_STEP)
        if self.charging_attack > 0.5:
            self.crawl_sin += 0.8 * self.charging_attack
        if (self.charging_attack >= 1.0 and self.dodge_delay < 1
                and self._visual_contact(self.x, self.y,
                                         self.x + ux * FANG_LENGTH,
                                         self.y + uy * FANG_LENGTH)):
            self.charging_attack = 0.0
            self.swish_dir = (ux, uy)
            self.swish_counter = SWISH_TICKS

    def _step_swish(self, WL, HL) -> None:
        """BigNeedleWorm.cs:357-475 Swish：6 tick 突刺，撞地卡住 / 撞生物扎穿。"""
        self.flying = 0.0
        self.dodge_delay = 30
        self.swish_counter -= 1
        if self.swish_counter < 1 or self.swish_dir is None:
            self.swish_counter = 0
            self.swish_dir = None
            self.lame_counter = LAME_TICKS
            return
        num = 90.0 + 90.0 * math.sin(inv_lerp(1.0, 5.0, float(self.swish_counter)) * math.pi)
        self.attack_ready = 1.0
        value = self.swish_dir
        tip_from = (self.last_x + value[0] * FANG_LENGTH, self.last_y + value[1] * FANG_LENGTH)
        tip_to = (self.x + value[0] * (FANG_LENGTH + num), self.y + value[1] * (FANG_LENGTH + num))
        # 1) 撞到墙/地/顶：卡住 3~4 秒（decompile: 0.0125/tick ⇒ 80 tick）
        hit = _terrain_hit(tip_from[0], tip_from[1], tip_to[0], tip_to[1],
                            self.rad, WL, HL)
        if hit is not None:
            if abs(value[0] * hit[2] + value[1] * hit[3]) > 0.73:
                self.stuck_pos = hit[:2]
                self.stuck_dir = value
                self.last_stuck_tip = hit[:2]
                self.swish_counter = 0
                self.swish_dir = None
                self.stuck_time = 0.0
                self.stun = 60                # 原版 Stun(60)：眩晕期间 stuckTime 涨得极慢
                return
            self.swish_counter = 0            # 擦着地面滑过：不卡，只是瘸一会儿
            self.swish_dir = None
            self.lame_counter = 30
            self.vx = value[0] * 6.0
            self.vy = value[1] * 6.0
            return
        # 2) 扎到生物：Violence(Stab, 1.22, 60) → 钉在它身上
        for c in ([self.prey] if self.prey is not None else []):
            chunks = c.get("chunks") or ()
            for (cx, cy, crad, clx, cly) in chunks:
                if _seg_dist(tip_from[0], tip_from[1], tip_to[0], tip_to[1], cx, cy) < crad + 4.0:
                    self.stuck_pos = (cx, cy)
                    self.stuck_dir = value
                    self.last_stuck_tip = (cx, cy)
                    self.swish_counter = 0
                    self.swish_dir = None
                    self.stuck_time = 0.0
                    self.attack_event = (c, STAB_DAMAGE, STAB_STUN)
                    return
        # 3) 没撞上：整体前冲
        self.vx = value[0] * num * 0.45
        self.vy = value[1] * num * 0.45
        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        self.crawl_sin += 0.8
        self.thin_tail = 1.0

    def _step_stuck(self, WL, HL) -> None:
        """BigNeedleWorm.cs:306-355 StuckInWall：前半身钉住，计时到点挣脱。"""
        rng = self._rng
        sx, sy = self.stuck_pos
        ux, uy = self.stuck_dir
        self.attack_ready = 1.0
        pinned = (sx - ux * FANG_LENGTH, sy - uy * FANG_LENGTH)
        for i, s in enumerate(self.seg[:max(1, len(self.seg) // 2)]):
            s.lx, s.ly = s.x, s.y
            k = 0.55 * (1.0 - i / max(1.0, len(self.seg) * 0.5))
            s.x += (pinned[0] - s.x) * k
            s.y += (pinned[1] - s.y) * k
        self.last_x, self.last_y = self.x, self.y
        self.x += (pinned[0] - self.x) * 0.6
        self.y += (pinned[1] - self.y) * 0.6
        self.vx = self.vy = 0.0
        self.flying_target = 0.0
        self.charging_attack = 0.0
        self.swish_dir = None
        self.swish_counter = 0
        if self.stun < 1:                    # 原版 BigNeedleWorm.cs:329 判的是 Consious
            self.stuck_time += STUCK_WALL_RATE
        else:
            self.stuck_time += rng.random() / 150.0
        self.crawl_sin += 0.4 * self.stuck_time
        if self.stuck_time > 1.0:
            self.stuck_time = 0.0
            self.stuck_pos = None
            self.last_stuck_tip = None
            self.lame_counter = LAME_TICKS
            f = max(0.2, self.flying)
            self.vx -= ux * 17.0 * f        # BigNeedleWorm.cs:348
            self.vy -= uy * 17.0 * f
            self.x += self.vx * 0.5
            self.y += self.vy * 0.5

    # ── 飞行（NeedleWorm.Fly + NeedleWormAI 的 flySpeed/flyHeightAdd）──
    def _fly(self, WL, HL, goal, fleeing: bool) -> None:
        rng = self._rng
        self.last_wing_flap = self.wing_flap
        self.wing_flap += (0.4 + rng.random() * 0.05) * max(0.0, self.flying)
        self.flying_target = 1.0
        self.fly_speed = _lerp_tick(self.fly_speed, 1.0 if goal is not None else 0.0,
                                    0.06, 1.0 / 60.0)
        if fleeing:
            self.fly_height_add = min(1.0, self.fly_height_add + FLY_HEIGHT_RISE)
        else:
            self.fly_height_add = max(0.0, self.fly_height_add - FLY_HEIGHT_FALL)
        min_h = (MIN_FLY_TILES + 4.0 * self.fly_height_add) * TILE
        slow = lerp(SLOW_FLY_MIN, SLOW_FLY_SMALL if self.small else SLOW_FLY_BIG,
                    self.fly_speed)
        ax = ay = 0.0
        if goal is not None:
            ux, uy = _dirvec(self.x, self.y, goal[0], goal[1])
            ax += ux * FLY_ACCEL * (0.5 + slow)
            ay += uy * FLY_ACCEL * (0.5 + slow) * 0.8
            if abs(ux) > 0.12:
                self._facing_from(ux)
        # MoveUpFromFloor：低于最低飞行高度就往上顶（NeedleWorm.cs:602-623）
        low = (self.y - (HL - min_h)) / max(1.0, min_h)
        if low > 0.0:
            ay -= 0.55 * clampf(low, 0.0, 1.5)
        self.vx += ax
        self.vy += ay + self.gravity * self.room_gravity * (1.0 - LIFT)
        self.vx *= AIR_FRICTION
        self.vy *= AIR_FRICTION
        sp = math.hypot(self.vx, self.vy)
        if sp > FLY_SPEED_MAX:
            self.vx *= FLY_SPEED_MAX / sp
            self.vy *= FLY_SPEED_MAX / sp
        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        if self._contact_floor or self._contact_x != 0:
            self.vy = min(self.vy, -0.8)
            if abs(self.vx) < 0.3:
                self.vx += (1.0 if self.facing >= 0 else -1.0) * 0.45
            self._goal_timer = GOAL_REPICK

    def _drift(self, WL, HL) -> None:
        """僵硬（lameCounter / 被晕）：只走物理，不主动飞（NeedleWorm.cs:87）。"""
        self.flying_target = 0.0
        self.vy += self.gravity * self.room_gravity
        self.vx *= AIR_FRICTION
        self.vy *= AIR_FRICTION
        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)
        if self._contact_floor:
            self.vx *= SURFACE_FRICTION

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

    # ── 獠牙贴脸（BigNeedleWorm.cs:154-172）：poke，stun + 掉手上东西 ──
    def _poke_check(self, cats) -> None:
        if (not self.attack_ready > 0.8 or self._rng.random() >= 1.0 / 3.0
                or self.swish_dir is not None or self.stuck_pos is not None):
            return
        ux = self.x - self.last_x
        uy = self.y - self.last_y
        d = math.hypot(ux, uy)
        if d < 1e-6:
            return
        ux /= d
        uy /= d
        bx, by = _dirvec(self.seg[self.snout_n + 1].x if len(self.seg) > self.snout_n + 1 else self.x,
                         self.seg[self.snout_n + 1].y if len(self.seg) > self.snout_n + 1 else self.y,
                         self.x, self.y)
        if ux * bx + uy * by <= -0.2:
            return
        reach = self.stab_reach()
        if reach is None:
            return
        fx, fy = reach
        for c in cats:
            if c.get("dead"):
                continue
            for ch in (c.get("chunks") or ()):
                if math.hypot(ch[0] - fx, ch[1] - fy) < ch[2]:
                    self.poke_event = (c, POKE_DAMAGE, POKE_STUN)
                    self.vx -= ux * 1.6
                    self.vy -= uy * 1.6
                    return

    # ── 投掷物：Dodge（BigNeedleWorm.cs:583-626）──
    def on_flying_weapon(self, wx: float, wy: float, wvx: float, wvy: float) -> bool:
        """有武器朝我飞来时侧移闪避；返回是否真的闪了。"""
        if self.age != AGE_BIG or self.dead:
            return False
        sp = math.hypot(wvx, wvy)
        if sp < 1e-6:
            return False
        ux, uy = wvx / sp, wvy / sp
        dx = self.x - (wx + ux * 200.0)
        dy = (self.y - (wy + uy * 200.0)) * 2.0
        if math.hypot(dx, dy) > 200.0:
            return False
        return self.dodge(wx, wy, ux, uy)

    def dodge(self, px: float, py: float, ux: float, uy: float) -> bool:
        if self.dodge_delay > 0 or self.flying <= 0.0:
            return False
        self.dodge_delay = DODGE_COOLDOWN
        self.charging_attack /= 2.0
        # Custom.PerpendicularVector(dir) * Sign(DistanceToLine(body1, projPos, projPos+dir))
        side = _dist_to_line(self.y, self.x, py, px, ux, uy)
        perp = (-uy, ux)
        sgn = 1.0 if side >= 0.0 else -1.0
        self.vx += perp[0] * sgn * DODGE_PUSH * self.flying
        self.vy += perp[1] * sgn * DODGE_PUSH * self.flying
        for i, s in enumerate(self.seg):
            k = 1.0 - i / max(1.0, len(self.seg) - 1.0)
            s.x += perp[0] * sgn * DODGE_PUSH * k * self.flying
            s.y += perp[1] * sgn * DODGE_PUSH * k * self.flying
        return True

    # ── 查询（接口兼容）──
    def stab_reach(self):
        """獠牙尖位置（BigNeedleWorm.cs:37 FangPos）。"""
        if self.age != AGE_BIG or len(self.seg) <= self.snout_n + 1:
            return None
        b1 = self.seg[self.snout_n + 1]
        ux, uy = _dirvec(b1.x, b1.y, self.x, self.y)
        return (self.x + ux * FANG_LENGTH, self.y + uy * FANG_LENGTH)

    def can_stab(self) -> bool:
        """原版：攻击准备就绪 / 正在突刺时才伸得出獠牙。"""
        return (self.age == AGE_BIG and not self.dead
                and (self.attack_ready > 0.5 or self.swish_counter > 0
                     or self.swish_dir is not None or self.scream > 0.5
                     or bool(self.temp_like)))

    def _visual_contact(self, ax, ay, bx, by) -> bool:
        """本窗口没有地形遮挡（原版 room.VisualContact）。"""
        return True

    # ── 链条（吻尖→尾）──
    def _step_chain(self, HL) -> None:
        """吻随体轴前伸（NeedleWormGraphics.Update:295-325），躯干由飞行驱动、
        体节互推，尾部正弦摆动（NeedleWorm.cs:833-858 SinMovementInBody）。"""
        if self.age == AGE_EGG:
            return
        sn = self.snout_n
        body0 = self.seg[sn]
        body0.lx, body0.ly = body0.x, body0.y
        body0.x, body0.y = self.x, self.y
        if len(self.seg) > sn + 1:
            ux, uy = _dirvec(self.seg[sn + 1].x, self.seg[sn + 1].y, body0.x, body0.y)
        else:
            ux, uy = float(self.facing), 0.0
        if abs(ux) + abs(uy) < 1e-6:
            ux, uy = float(self.facing), 0.0
        self.lzrot, self.zrot = self.zrot, (ux, uy)
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
        grav = 0.16 * self.room_gravity
        for i in range(sn + 1, len(self.seg)):
            s = self.seg[i]
            p = self.seg[i - 1]
            s.lx, s.ly = s.x, s.y
            dx, dy = s.x - p.x, s.y - p.y
            d = math.hypot(dx, dy)
            ux2, uy2 = ((dx / d, dy / d) if d > 1e-6 else (ux, uy))
            s.x += (p.x + ux2 * s.dist - s.x) * 0.5
            s.y += (p.y + uy2 * s.dist - s.y) * 0.5 + grav
            wave = math.sin(self.crawl_sin + i * 0.55) * (0.35 + 0.045 * (i - sn))
            s.x += -uy2 * wave
            s.y += ux2 * wave
            floor = HL - s.rad * 0.5
            if s.y > floor:
                s.y = floor
        self.head_rad = body0.rad

    def _collide(self, WL, HL) -> None:
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb,
                          open_sides=self.dead)

    # ── 渲染状态推进（NeedleWormGraphics.Update）──
    def gfx_tick(self) -> None:
        self.flying = _lerp_tick(self.flying, self.flying_target, 0.11, 1.0 / 30.0)
        if self.age == AGE_BIG:
            self.last_fang_out = self.fang_out
            if self.swish_dir is not None or self.stuck_pos is not None:
                self.fang_out = 1.0
            else:
                self.fang_out = _scurve(inv_lerp(0.0, 0.75, self.attack_ready), 0.6)
            self.thin_tail = (1.0 if self.swish_dir is not None else
                              _lerp_tick(self.thin_tail,
                                         inv_lerp(0.5, 1.0, self.charging_attack),
                                         0.07, 0.05))
            if self.fang_out == 0.0 and self.last_fang_out == 0.0:
                self.fang_black = 0.0
            else:
                # 伸出来见空气之后由白转黑（NeedleWormGraphics.cs:286-293）
                self.fang_black = _lerp_tick(self.fang_black,
                                             inv_lerp(0.5, 1.0, self.fang_out),
                                             0.002, 0.0038461538)
        self.scream = max(0.0, self.scream - 1.0 / 70.0)
        if self.dead:
            self.blink = 0
        else:
            self.blink += 0.0025 + self._rng.random() * 0.001


# ── 小工具：原版 Custom 的随机变体、LerpAndTick、向量数学 ──
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
    """Custom.LerpAndTick：向目标插值，但每 tick 至少走 tick 步。"""
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


def _move_towards(a, b, speed):
    """Custom.MoveTowards：朝 B 走 speed 步。"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d <= speed or d < 1e-9:
        return (b[0], b[1])
    return (a[0] + dx / d * speed, a[1] + dy / d * speed)


def _dist_to_line(vx, vy, l2x, l2y, l1x, l1y):
    """Custom.DistanceToLine(V, l2, l1)（RWCustom/Custom.cs:1087）——带符号距离。"""
    dy = l2y - l1y
    dx = l2x - l1x
    n = math.sqrt(dx * dx + dy * dy)
    if n < 1e-9:
        return 0.0
    return (dy * vx - dx * vy + l2x * l1y - l2y * l1x) / n


def _seg_dist(ax, ay, bx, by, px, py):
    """点到线段距离（扫掠命中用）。"""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = clampf(((px - ax) * dx + (py - ay) * dy) / L2, 0.0, 1.0)
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def _terrain_hit(ax, ay, bx, by, rad, WL, HL):
    """獠牙尖从 (ax,ay) 扫到 (bx,by) 是否撞进窗口四壁。

    返回 (命中点 x, 命中点 y, 法线 x, 法线 y)；没撞到返回 None。
    窗口只有 4 面墙（原版房间地形在桌宠里就这 4 面）。
    """
    if by <= 0.0:
        return (bx, 0.0, 0.0, -1.0)
    if by >= HL:
        return (bx, HL, 0.0, 1.0)
    if bx <= 0.0:
        return (0.0, by, -1.0, 0.0)
    if bx >= WL:
        return (WL, by, 1.0, 0.0)
    return None


def _cat_from_threat(t):
    """旧接口 threats=[(obj, x, y)] → cats 结构。"""
    obj, x, y = t[0], t[1], t[2]
    body = getattr(obj, "body", None)
    chunks = []
    if body is not None:
        for c in (body.chunk0, body.chunk1):
            chunks.append((c.x, c.y, c.rad, c.last_x, c.last_y))
    if not chunks:
        chunks = [(x, y, 8.0, x, y)]
    return {"uid": id(obj), "x": x, "y": y, "chunks": tuple(chunks),
            "dead": bool(getattr(obj, "dead", False)),
            "saint": getattr(obj, "variant", None) == "saint",
            "body": body, "pet": obj, "other": None,
            "holds_child": False, "holds_me": False, "small": False}


def _cat_from_other(other):
    """把另一只面条蝇当成目标（同族 Attacks 0.9）。"""
    chunks = tuple((s.x, s.y, max(1.0, s.rad), s.lx, s.ly) for s in other.seg)
    return {"uid": id(other), "x": other.x, "y": other.y, "chunks": chunks,
            "dead": other.dead, "saint": False, "body": None, "pet": None,
            "other": other, "holds_child": False, "holds_me": False, "small": False}
