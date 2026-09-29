"""拾荒者 Scavenger：地面行走的持矛生物（原版 Scavenger）。y↓。

看到蜥蜴/猫靠近 → 站定瞄准 → 把矛掷出 → 逃跑；没矛了就一直躲。
外形按原版 ScavengerGraphics 的贴图组合绘制（见 rendering/primitives.py），
个体差异 ivar 复刻原版 IndividualVariations。
"""
from __future__ import annotations
import math
import random as _random

from ..core.units import clampf, lerp
from ..core.gfxmath import _hsl2rgb
from ..rendering.primitives import (SCAV_STANCE, scav_pose, scav_spear_pose,
                                    scav_shoulder)
from .enums import ItemState
from .spear import Spear

GRAVITY = 0.9
AIR_FRICTION = 0.999        # Scavenger.cs:1719
GROUND_FRICTION = 0.86
WALL_BOUNCE = 0.1

BODY_RAD = 7.0             # Scavenger.cs:1611 bodyChunks[1].rad（髋）
HEAD_RAD = 5.0             # Scavenger.cs:1611 bodyChunks[2].rad（头）
STAND_H = 40.0            # 绘制高度：髋心往上 40（原版 髋7+链18+头22 的悬垂投影）
SPEED_WALK = 0.85
SPEED_RUN = 1.5
ALERT_R = 190.0           # 察觉半径（蜥蜴/猫）
PANIC_R = 150.0
AIM_TICKS = 34            # 瞄准时长
THROW_CD = 90
IDLE_TICKS = (90, 260)
FLEE_TICKS = 260

# 原版 ScavengerAI.CheckThrow：在目标体节里挑 |DirVec.x| 最大的那一节下手；
# 若 |DirVec.x| <= 0.5 则要求垂直差 < 40（游戏像素），否则不打（不朝天/地扔）。
AIM_VERT_TOL = 40.0

# 鼠标也是威胁：原版 Scavenger 对任何靠近的生物都会举矛（ScavengerAI.ThreatRequired）
CURSOR_ALERT_R = 240.0
CURSOR_ARM = 6                    # 连续靠近这么久才举矛，防误触

# 原版 wiki 起始声望 → 对这只猫的好感（0..1；0.5 = 中立，>=0.6 = 友好不攻击）
# Survivor/Gourmand/Saint/Inv 0、Monk +25、Hunter -35、Rivulet -21、Spearmaster -45、
# Artificer 恒定敌对。这里只做映射，不做任何自动升降（用户要求）。
LIKE0_BY_VARIANT = {
    "survivor": 0.500, "gourmand": 0.500, "saint": 0.500, "inv": 0.500,
    "monk": 0.625, "hunter": 0.325, "rivulet": 0.395, "spearmaster": 0.275,
    "artificer": 0.000,
}
ATTACK_LIKE_COST = 0.25           # 被猫打一次掉的好感
ARM_HEALTH = 0.9                  # 血量低于此值就从背上拔矛
TRADE_LIKE = 1.0                  # 收下珍珠后的好感（wiki 珍珠价值 10 最高）

PEARL_SEEK_R = 300.0              # 看到珍珠就去捡的半径（原版 CollectScore=10）
PEARL_TAKE_PAD = 9.0
TRADE_GIVE_TICKS = 70             # 拿到珍珠后回礼（给矛）的延迟

BODY_RGB = (58, 60, 68)          # 兜底体色
HEAD_RGB = (226, 226, 214)       # 面具（原版偏白的骨质面具）
EYE_RGB = (26, 26, 30)
SPIKE_RGB = (232, 232, 224)
LEG_RGB = (44, 46, 52)


def _scurve(x, k):
    """原版 Custom.SCurve。"""
    x = x * 2.0 - 1.0
    if x < 0.0:
        x = abs(1.0 + x)
        return k * x / (k - x + 1.0) * 0.5
    k = -1.0 - k
    return 0.5 + k * x / (k - x + 1.0) * 0.5


def _rand_dev(rng, k):
    """原版 Custom.RandomDeviation。"""
    return _scurve(rng.random() * 0.5, k) * 2.0 * (1.0 if rng.random() < 0.5 else -1.0)


def _clamped_var(rng, base, dev, k):
    """原版 Custom.ClampedRandomVariation。"""
    return clampf(base + _rand_dev(rng, k) * dev, 0.0, 1.0)


def _dist01(a, b):
    """原版 Custom.DistanceBetweenZeroToOneFloats。"""
    return min(abs(a - b), abs(a + 1.0 - b), abs(a - 1.0 - b))


def _inverse_lerp(a, b, v):
    if b == a:
        return 0.0
    return clampf((v - a) / (b - a), 0.0, 1.0)


def _rot_deg(v, deg):
    """原版 Custom.RotateAroundOrigo。"""
    a = -math.radians(deg)
    c, sn = math.cos(a), math.sin(a)
    return (c * v[0] - sn * v[1], sn * v[0] + c * v[1])


def _hsl255(h, s, l):
    return tuple(int(c * 255.0) for c in
                 _hsl2rgb(h % 1.0, clampf(s, 0.0, 1.0), clampf(l, 0.0, 1.0)))


def _hsl_rgb(h, s, l):
    return _hsl2rgb(h % 1.0, clampf(s, 0.0, 1.0), clampf(l, 0.0, 1.0))


def _mix255(a, b, t):
    t = clampf(t, 0.0, 1.0)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


BLACK_RGB = (27, 11, 33)          # 原版 palette.blackColor


def _push_from_half(v, e):
    """原版 Custom.PushFromHalf：把 0.5 附近的值推向两端。"""
    if v < 0.5:
        return 0.5 * (2.0 * v) ** e
    return 1.0 - 0.5 * (2.0 - 2.0 * v) ** e


def _lerp_map(v, a, b, A, B, e=1.0):
    """原版 Custom.LerpMap（含可选的曲线指数）。"""
    if a == b:
        return A
    t = clampf((v - a) / (b - a), 0.0, 1.0)
    if e != 1.0:
        t = t ** e
    return A + (B - A) * t


def individual_variations(rng, elite=False):
    """原版 ScavengerGraphics.IndividualVariations。

    宠物没有 AbstractCreature.personality，energy/dominance/sympathy/aggression
    一律取中性 0.5（原版公式在这些取值下退化为最朴素的那一支）。
    """
    v = {}
    v["general_melanin"] = _push_from_half(rng.random(), 2.0)
    v["head_size"] = _clamped_var(rng, 0.5, 0.5, 0.1)
    v["eartler_width"] = rng.random()
    v["eye_size"] = math.pow(max(0.0, lerp(rng.random(), math.pow(v["head_size"], 0.5),
                                           rng.random() * 0.4)),
                             lerp(0.95, 0.55, 0.5))
    v["narrow_eyes"] = (0.0 if rng.random() < lerp(0.3, 0.7, 0.5)
                        else math.pow(rng.random(), lerp(0.5, 1.5, 0.5)))
    if elite:
        v["narrow_eyes"] = 1.0
    v["eyes_angle"] = math.pow(rng.random(), lerp(2.5, 0.5, math.pow(0.5, 0.03)))
    fat = lerp(rng.random(), 0.5, rng.random() * 0.2)      # dominance = 0.5
    # energy = 0.5 → InverseLerp(0.5, 1, 0.5) = 0，两支都不生效
    v["fat"] = fat
    v["waist"] = lerp(lerp(rng.random(), 1.0 - fat, rng.random()),
                     1.0 - 0.5, rng.random())
    v["neck"] = lerp(math.pow(rng.random(), 1.5 - 0.5), 1.0 - fat, rng.random() * 0.5)
    v["pupil"] = 0.0
    v["deep"] = False
    v["colored_pupils"] = 0
    if rng.random() < 0.65 and v["eye_size"] > 0.4 and v["narrow_eyes"] < 0.3:
        if rng.random() < math.pow(0.5, 1.5) * 0.8:
            v["pupil"] = lerp(0.4, 0.8, math.pow(rng.random(), 0.5))
            if rng.random() < 2.0 / 3.0:
                v["colored_pupils"] = rng.randint(1, 3)
        else:
            v["pupil"] = 0.7
            v["deep"] = True
    if elite:
        v["colored_pupils"] = rng.randint(1, 3)
    if rng.random() < v["general_melanin"]:
        r = rng.random()
        v["hands_head_color"] = r if r < 0.3 else (1.0 if rng.random() < 0.6 else 0.0)
    else:
        r = rng.random()
        v["hands_head_color"] = r if r < 0.2 else (1.0 if rng.random() < 0.8 else 0.0)
    v["legs"] = rng.random()
    v["arm"] = lerp(rng.random(), lerp(0.5, fat, 0.5), rng.random())
    v["colored_eartler_tips"] = elite or rng.random() < 1.0 / lerp(1.2, 10.0,
                                                                   v["general_melanin"])
    v["wide_teeth"] = rng.random()
    v["tail_segs"] = 0 if rng.random() < 0.5 else rng.randint(1, 4)
    v["scruffy"] = 0.0
    if rng.random() < 0.25:
        v["scruffy"] = math.pow(rng.random(), 0.3)
    v["elite"] = elite
    v["mask"] = rng.choice(("KrakenMask", "SpikeMask", "HornedMask", "SadMask")) if elite else None
    # 原版 teeth = new float[Range(2,5)*2, 2]，尺寸在构造期定死（否则每帧抖动）
    v["teeth_n"] = rng.randint(2, 4) * 2
    nt = v["teeth_n"]
    t_width = lerp(0.5, 1.5, math.pow(rng.random(), 1.0))
    t_width = lerp(t_width, t_width * _lerp_map(nt, 4.0, 8.0, 1.0, 0.5), 0.3)
    ta = lerp(t_width + 0.2, lerp(0.7, 1.2, rng.random()), rng.random())
    ta = lerp(ta, _lerp_map(nt, 4.0, 8.0, 1.5, 0.2), 0.4)
    ta2 = 0.3 + 0.7 * rng.random()
    v["teeth"] = []
    for i in range(nt):
        u = i / float(nt - 1) if nt > 1 else 0.0
        t0 = lerp(ta2, 1.0, math.sin(u * math.pi)) * t_width
        if rng.random() < v["scruffy"] and rng.random() < 0.2:
            t0 = 0.0
        v["teeth"].append((t0, lerp(0.5, 1.0, math.sin(u * math.pi)) * ta))
    v["hands"] = 1.0 if rng.random() < 0.8 else 0.0
    return v


def body_colors(rng, iv, elite=False):
    """原版 ScavengerGraphics.GenerateColors（darkness=0，即明亮房间）。

    返回 (体色, 头色, 眼色, 腹色, 瞳色, 装饰色)，都已按 Blended*Color 与黑混合。
    """
    mel = iv["general_melanin"]
    hue = rng.random() * 0.1
    if rng.random() < 0.025:
        hue = math.pow(rng.random(), 0.4)
    if elite:
        hue = math.pow(rng.random(), 5.0)
    hue2 = (hue + lerp(-1.0, 1.0, rng.random()) * 0.3 * math.pow(rng.random(), 2.0)) % 1.0

    body_h = hue
    body_s = lerp(0.05, 1.0, math.pow(rng.random(), 0.85))
    body_l = lerp(0.05, 0.8, rng.random())
    body_s *= 1.0 - mel
    body_l = lerp(body_l, 0.5 + 0.5 * math.pow(rng.random(), 0.8), 1.0 - mel)

    def _avg_rgb(h, s, l):
        return sum(_hsl_rgb(h, s, l)) / 3.0

    def _black_of(rgb_avg):
        """原版 bodyColorBlack：LerpMap(avg, .04,.8, .3,.95, e=.5) 再按 rand^3 拉。"""
        t = _lerp_map(rgb_avg, 0.04, 0.8, 0.3, 0.95, 0.5)
        t = lerp(t, lerp(0.5, 1.0, rng.random()), rng.random() ** 3)
        return t * mel

    def _black_of_head(rgb_avg):
        """原版 headColorBlack：另一套区间 + 0.2+0.7*mel 上限。"""
        t = _lerp_map(rgb_avg, 0.035, 0.26, 0.7, 0.95, 0.25)
        t = lerp(t, lerp(0.8, 1.0, rng.random()), rng.random() ** 3)
        return t * (0.2 + 0.7 * mel)

    bcb = _black_of(_avg_rgb(body_h, body_s, body_l))
    # 原版 float2 张力修正：饱和+亮度都太低时把颜色撑开
    fx, fy = body_s, lerp(-1.0, 1.0, body_l * (1.0 - bcb))
    mag = math.hypot(fx, fy)
    if mag < 0.5:
        t = _inverse_lerp(0.5, 0.3, mag)
        body_s = _inverse_lerp(-1.0, 1.0, lerp(fx, fx / mag, t))
        body_l = _inverse_lerp(-1.0, 1.0, lerp(fy, fy / mag, t))
        bcb = _black_of(_avg_rgb(body_h, body_s, body_l))
    # 头色相：75% 用 hue2，否则用 a（此处 a 用 hue2 的随机偏移近似）
    a_hue = (hue2 + lerp(-1.0, 1.0, rng.random()) * 0.1 * math.pow(rng.random(), 1.5)) % 1.0
    a_hue = lerp(a_hue, 0.15, rng.random())          # 原版两支都有的「拉向 0.15」
    head_h = hue2 if rng.random() < 0.75 else a_hue
    head_s = 1.0
    head_l = 0.05 + 0.15 * rng.random()
    head_s *= math.pow(1.0 - mel, 2.0)
    head_l = lerp(head_l, 0.5 + 0.5 * math.pow(rng.random(), 0.8), 1.0 - mel)
    head_s *= 0.1 + 0.9 * _inverse_lerp(0.1, 0.0,
                                        _dist01(body_h, head_h)
                                        * _lerp_map(abs(0.5 - head_l), 0.0, 0.5, 1.0, 0.3))
    if head_l < 0.5:
        head_l *= 0.5 + 0.5 * _inverse_lerp(0.2, 0.05, _dist01(body_h, head_h))
    hcb = _black_of_head(_avg_rgb(head_h, head_s, head_l))
    hcb = max(hcb, bcb)
    head_s = _lerp_map(head_l * (1.0 - hcb), 0.0, 0.15, 1.0, head_s)
    if head_l > body_l:
        head_h, head_s, head_l = body_h, body_s, body_l
    if head_s < body_s * 0.75:
        if rng.random() < 0.5:
            head_h = body_h
        else:
            head_l *= 0.25
        head_s = body_s * 0.75
    deco_h = hue if rng.random() < 0.65 else (hue2 if rng.random() < 0.5 else a_hue)
    deco_s = rng.random()
    deco_l = 0.5 + 0.5 * math.pow(rng.random(), 0.5)
    deco_l *= lerp(mel, rng.random(), 0.5)
    eye_h = 0.0 if elite else a_hue
    eye_s = 1.0
    eye_l = (0.5 + rng.random() * 0.5) if rng.random() < 0.2 else 0.5
    if iv["colored_pupils"] > 0:
        eye_l = lerp(eye_l, 1.0, 0.3)
    if head_l * (1.0 - hcb) > eye_l / 2.0 and (iv["pupil"] == 0.0 or iv["deep"]):
        eye_l *= 0.2
    v1, v2 = rng.random(), rng.random()
    belly_h = lerp(body_h, deco_h, v1 * 0.7)
    belly_s = body_s * lerp(1.0, 0.5, v1)
    belly_l = body_l + 0.05 + 0.3 * v2
    belly_black = lerp(bcb, 1.0, 0.3 * math.pow(v2, 1.4))
    if rng.random() < 1.0 / 30.0:
        head_l = lerp(0.2, 0.35, rng.random())
        hcb *= lerp(1.0, 0.8, rng.random())
        belly_h = lerp(belly_h, head_h, math.pow(rng.random(), 0.5))
    # 瞳孔（原版 ApplyPalette 的 switch 分支）
    if iv["colored_pupils"] == 1:
        pupil = _hsl255(body_h, 1.0, 0.35)
    elif iv["colored_pupils"] == 2:
        pupil = _hsl255(head_h, 1.0, 0.35)
    elif iv["colored_pupils"] == 3:
        pupil = _hsl255(deco_h, 1.0, 0.35)
    elif head_l * (1.0 - hcb) > 0.1:
        pupil = _mix255(_hsl255(head_h, head_s, 0.15), BLACK_RGB, hcb)
    else:
        pupil = _mix255(_hsl255(head_h, head_s, head_l), BLACK_RGB, hcb)
    return (_mix255(_hsl255(body_h, body_s, body_l), BLACK_RGB, bcb),
            _mix255(_hsl255(head_h, head_s, head_l), BLACK_RGB, hcb),
            _hsl255(eye_h, eye_s, eye_l),
            _mix255(_hsl255(belly_h, belly_s, belly_l), BLACK_RGB, belly_black),
            pupil,
            _mix255(_hsl255(deco_h, deco_s, deco_l), BLACK_RGB, 0.0))

class Scavenger:
    """拾荒者：巡走/警觉/投矛/逃跑 四态。"""
    collision_layer = 0

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "air_friction", "surface_friction", "bounce", "water_y", "room_gravity",
                 "state", "facing", "walk_phase", "state_t", "idle_timer", "goal_x",
                 "spear", "aim", "aim_t", "throw_event", "throw_cd", "dead", "health",
                 "held_by_hand",
                 "_contact_floor", "_rng", "seed", "id", "body_rgb", "head_rgb", "eye_rgb",
                 "belly_rgb", "pupil_rgb", "deco_rgb", "mask_rgb", "ivar",
                 "pearl", "like", "bring_pearl_home", "gift_t", "gift_event",
                 "goal_pearl", "_cursor_seen", "variant", "like0", "flip",
                 "back_spear", "look_screen", "look_up", "neutral", "eyes_open",
                 "last_flip", "last_neutral", "last_look_up",
                 "eyes_pop", "last_eyes_open", "last_eyes_pop", "blink",
                 "_blink_off", "rise_body", "hurt_cd")

    @property
    def haul_chunk_mass(self):
        """被拖拽时「被抓那节」的质量：Scavenger.cs:1727-1730。

        被普通蛞蝓猫抓住时每帧 Lerp(旧值, 0.5 / 0.3 / 0.05, 0.6)，几帧就收敛到
        这三档（工匠抓的分支是 0.05 / 0.05 / 0.01，见 1721-1723）。
        """
        return 0.5

    @property
    def haul_mass(self):
        """被拖拽对象总质量：Scavenger.cs:1728-1730（0.5 + 0.3 + 0.05）。"""
        return 0.85

    def __init__(self, x: float, y: float, seed: int = 0, id: int = 0,
                 variant: str = "saint"):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad = BODY_RAD
        self.mass = 0.85           # 0.5 + 0.3 + 0.05（三节合计）
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
        self.health = 1.0          # 原版 Scavenger HealthState.health（无伤害抗性）
        self.seed = int(seed)
        self.id = int(id)
        self._rng = _random.Random(seed * 3571 + 11)
        self.ivar = individual_variations(self._rng)
        (self.body_rgb, self.head_rgb, self.eye_rgb, self.belly_rgb,
         self.pupil_rgb, self.deco_rgb) = body_colors(self._rng, self.ivar)
        # 原版 VultureMaskGraphics.ColorA：浅色骨面具（色相随机偏移、明度 0.7–0.8）
        if self.ivar["mask"] is None:
            self.mask_rgb = None
        else:
            _mh = 0.02 + self._rng.random() * 0.12
            self.mask_rgb = tuple(int(c * 255) for c in
                                  _hsl2rgb(_mh, 0.25 + 0.2 * self._rng.random(),
                                           0.76 + 0.05 * self._rng.random()))
        self.idle_timer = self._rng.randint(*IDLE_TICKS)
        self.goal_x = self.x
        self.aim = None                 # (x, y) 瞄准点
        self.aim_t = 0
        self.throw_cd = 0
        self.throw_event = None         # (tx, ty) 窗口读走后生成飞矛
        self.spear = Spear(self.x + 6.0, self.y - 6.0, seed=seed, angle_deg=90.0)
        self.spear.held_by = self
        self.back_spear = True          # 原版：背上还插着一支备用矛
        self.flip = 1.0                 # 原版 flip 是连续量（0.1 插值），不只是 ±1
        self.last_flip = 1.0
        # 面部/视线平滑量（原版 ScavengerGraphics.Update）
        self.look_screen = (self.x + 90.0, self.y - 26.0)
        self.look_up = 0.0
        self.neutral = 0.0
        self.last_look_up = 0.0
        self.last_neutral = 0.0
        self.eyes_open = 1.0
        self.eyes_pop = 0.0
        self.last_eyes_open = 1.0
        self.last_eyes_pop = 0.0
        self.blink = self._rng.randint(10, 60)
        self._blink_off = 3
        self.rise_body = 0.0
        self.hurt_cd = 0
        self._contact_floor = False
        # ── 珍珠交易（原版 ScavengerAI：DataPearl 价值 10，收到后好感大涨）──
        self.pearl = None               # 手上的珍珠
        # 初始好感按 wiki 的起始声望定（之后只被「被攻击」和「给珍珠」改变）
        self.variant = variant
        self.like0 = LIKE0_BY_VARIANT.get(variant, 0.5)
        self.like = self.like0     # 对猫的好感 0..1（原版 relationship.like）
        self.bring_pearl_home = False   # 原版 GrabObject(DataPearl) 时置位
        self.gift_t = -1                # ≥0 表示回礼倒计时
        self.gift_event = False         # 窗口读走后生成回礼的矛
        self.goal_pearl = None          # 正在去捡的珍珠
        self._cursor_seen = 0           # 光标贴脸计数

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def friendly(self) -> bool:
        """给过珍珠 → 不再把猫当猎物（原版关系值高了就不敌对）。"""
        return self.like >= 0.6 or self.bring_pearl_home

    def receive_pearl(self, pearl=None) -> None:
        """收到珍珠：原版 GrabObject → bringPearlHome，且 InfluenceTempLike(2f)。

        CollectScore(DataPearl)=10 → InfluenceLike(10/7.5*0.6) 直接拉满好感。
        """
        if pearl is not None:
            pearl.state = ItemState.CARRIED
            pearl.held_by_hand = "scav"
            pearl.vx = pearl.vy = 0.0
        self.pearl = pearl
        self.bring_pearl_home = True
        self.goal_pearl = None
        self.like = 1.0
        self.gift_t = TRADE_GIVE_TICKS
        self.throw_event = None
        self.aim = None
        if self.state in ("aim", "flee"):
            self.state = ItemState.FREE
            self.state_t = 0
        self.throw_cd = max(self.throw_cd, THROW_CD)

    def _carry_pearl(self) -> None:
        pr = self.pearl
        (gx, gy), _ = scav_spear_pose(scav_pose(self))
        pr.x, pr.y = gx, gy
        pr.last_x, pr.last_y = pr.x, pr.y
        pr.vx = pr.vy = 0.0
        pr.state = ItemState.CARRIED
        pr.held_by_hand = "scav"

    def bounding_pad(self) -> float:
        return 46.0

    def die(self) -> None:
        self.dead = True
        self.state = ItemState.GONE

    def hurt(self, damage: float) -> bool:
        """被咬 / 被矛击中：原版 Scavenger 的 HealthState（health 1.0，无抗性）。
        返回本次是否致死。"""
        if self.dead:
            return True
        self.health -= damage
        if self.health <= 1e-6:
            self.die()
            return True
        return False

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
        self._threat_scan(threats, cursor)
        self._integrate(WL, HL)
        self._step_legs(HL)
        self._face_tick(cursor)
        self._arm_needs()
        if self.throw_cd > 0:
            self.throw_cd -= 1
        if self.spear is not None:                  # 矛跟着手
            self._carry_spear()
        if self.pearl is not None:                  # 珍珠跟着手
            self._carry_pearl()
            if self.gift_t > 0:
                self.gift_t -= 1
            elif self.gift_t == 0:
                self.gift_event = True              # 回礼：给猫一根矛
                self.gift_t = -1

    # ── 背矛 / 被攻击 / 面部平滑（原版 ScavengerGraphics.Update）──
    def _arm_needs(self) -> None:
        """受伤、或要打架而手里没矛时，从背上把备用矛抽到右手。"""
        if self.hurt_cd > 0:
            self.hurt_cd -= 1
        if self.spear is not None or not self.back_spear:
            return
        if self.health > ARM_HEALTH and self.state != "aim" and self.aim is None:
            return
        self.back_spear = False
        sp = Spear(self.x + self.facing * 6.0, self.y - 8.0, seed=self.seed,
                   angle_deg=90.0)
        sp.held_by = self
        self.spear = sp

    def on_attacked(self, dmg: float = 1.0) -> None:
        """被猫攻击：掉好感并立刻反击（好感不会自己回升）。"""
        self.like = clampf(self.like - ATTACK_LIKE_COST * clampf(dmg, 0.5, 2.0), 0.0, 1.0)
        self.bring_pearl_home = False
        self.hurt_cd = 40
        if self.spear is None:
            self.back_spear = True
        if self.state != "flee":
            self.state = "aim"
            self.aim_t = 0

    def _face_tick(self, cursor=None) -> None:
        """原版 ScavengerGraphics.Update 的 lookUp / neutralFace / 眨眼。"""
        self.last_flip = self.flip
        self.last_neutral = self.neutral
        self.last_look_up = self.look_up
        self.flip = clampf(self.flip + (float(self.facing) - self.flip) * 0.1, -1.0, 1.0)
        if self.state == "aim" and self.aim is not None:
            self.look_screen = self.aim
        elif cursor is not None and (self.friendly
                                     or math.hypot(cursor[0] - self.x,
                                                   cursor[1] - self.y) < 200.0):
            self.look_screen = cursor
        else:
            self.look_screen = (self.x + self.facing * 90.0, self.y - 26.0)
        pose = scav_pose(self)
        up = _rot_deg(pose["f"], pose["body_deg"])
        if up[1] > 0.8:
            self.look_up = min(1.0, self.look_up + 1.0 / 12.0)
        else:
            self.look_up = max(0.0, self.look_up - 1.0 / 12.0)
        lx, ly = self.look_screen
        dist = math.hypot(lx - self.x, ly - self.y)
        # 原版 :1496：num3 = Lerp(200, 600, shiftingNeutralFace^1.7)，中值 ≈ 323
        num3 = 323.4
        num4 = clampf((num3 - dist) / num3, 0.0, 1.0)
        self.neutral = lerp(self.neutral, num4, 0.1)
        self.last_eyes_open = self.eyes_open
        self.last_eyes_pop = self.eyes_pop
        self.eyes_pop *= 0.9
        self.blink -= 1
        if self.blink < 0:
            self.eyes_open = max(0.0, self.eyes_open - 0.5)
            if self.blink < -self._blink_off:
                self.blink = self._rng.randint(4, 12)
                self._blink_off = self._rng.randint(2, 5)
        else:
            self.eyes_open = min(1.0, self.eyes_open + 0.52)

    def _step_held(self, HL, cursor=None) -> None:
        """被拎起：跟光标垂着，矛与投掷意图都失效。"""
        if cursor is not None:
            self.x, self.y = cursor[0], min(cursor[1], HL - SCAV_STANCE)
        self.throw_event = None
        if self.spear is not None:      # 手里仍握着矛
            self._carry_spear()

    def _pick_aim_point(self, pts):
        """原版 CheckThrow 的选点：|DirVec.x| 最大且 (|DirVec.x| > 0.5 或垂直差 < 40)。"""
        best, best_ax = None, -1.0
        for px, py in pts:
            dx, dy = px - self.x, py - self.y
            n = math.hypot(dx, dy)
            if n < 1e-6:
                continue
            ax = abs(dx / n)
            if ax <= 0.5 and abs(dy) >= AIM_VERT_TOL:
                continue
            if ax > best_ax:
                best, best_ax = (px, py), ax
        return best

    def _cursor_threat_points(self, cursor):
        """鼠标也当威胁：贴脸一段时间后进入举矛流程。"""
        if cursor is None:
            return None
        px, py = cursor
        if math.hypot(px - self.x, py - self.y) > CURSOR_ALERT_R:
            self._cursor_seen = 0
            return None
        self._cursor_seen += 1
        if self._cursor_seen < CURSOR_ARM:
            return None
        # 给三个虚拟体节点，让 CheckThrow 的 |DirVec.x| 规则有得挑
        return [(px, py - 12.0), (px, py), (px, py + 12.0)]

    def _threat_scan(self, threats, cursor=None) -> None:
        """按威胁距离切态：瞄准→投矛→逃跑。"""
        best, bd = None, ALERT_R
        for obj, pts, is_pet in threats:
            if is_pet and self.friendly:            # 交易过的拾荒者不攻击猫
                continue
            aim = self._pick_aim_point(pts)
            if aim is None:
                continue
            d = math.hypot(aim[0] - self.x, aim[1] - self.y)
            if d < bd:
                best, bd = aim, d
        cpts = self._cursor_threat_points(cursor)
        if cpts is not None:
            aim = self._pick_aim_point(cpts)
            if aim is not None:
                d = math.hypot(aim[0] - self.x, aim[1] - self.y)
                if d < bd:
                    best, bd = aim, d
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
        elif self.goal_pearl is not None and self.goal_pearl.state == ItemState.FREE:
            gp = self.goal_pearl                # 原版：去捡珍珠（beeline）
            self.facing = 1 if gp.x >= self.x else -1
            self.vx += (SPEED_WALK * self.facing - self.vx) * 0.10
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
        if self.y + SCAV_STANCE > HL:
            self.y = HL - SCAV_STANCE
            self.vy = 0.0
            self._contact_floor = True
        elif self.y - BODY_RAD < 0:
            self.y = BODY_RAD          # 顶边同样是实心：别被顶出窗口
            self.vy = 0.0
            self._contact_floor = False
        else:
            self._contact_floor = False

    def _step_legs(self, HL) -> None:
        if abs(self.vx) > 0.05:
            self.walk_phase = (self.walk_phase + abs(self.vx) * 0.05) % 1.0

    def _carry_spear(self) -> None:
        """矛握在右手里：位置/朝向按原版 ScavengerGraphics.ItemPosition/WeaponDir。"""
        sp = self.spear
        for ts in (1.0, 0.0):
            (gx, gy), ang = scav_spear_pose(scav_pose(self, ts))
            if ts >= 1.0:
                sp.x, sp.y, sp.angle_deg = gx, gy, ang
            else:
                sp.last_x, sp.last_y, sp.last_angle = gx, gy, ang
        sp.state = ItemState.CARRIED
        sp.unstuck()

    # ── 头/眼（绘制用）──
    def head_pos(self):
        """骨架头位（原版 drawPositions[0]）。"""
        p = scav_pose(self)
        return (p["org"][0] + p["d"][0][0], p["org"][1] - p["d"][0][1])
