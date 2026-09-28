"""蜥蜴：三节躯干 + 尾链 + 独立头；巡走 / 警觉 / 扑咬 AI。坐标 y↓。

尺寸与色相照搬游戏常量（LizardBreedParams / Lizard.effectColor / LizardGraphics）。
躯干半径 8*bodySizeFac*bodyRadFac、节距 17*(bodySizeFac+1)/2、头连接 11*headSize，
整体再乘 BODY_SCALE 适配桌面。
"""
from __future__ import annotations
import math
import random as _random

from ..core.units import clampf, lerp
from .enums import ItemState

# ── 物理 ──
GRAVITY = 0.9                 # 同石头/蝙蝠量级
AIR_FRICTION = 0.99
GROUND_FRICTION = 0.84
WALL_BOUNCE = 0.2
BODY_SCALE = 1.0              # 与游戏像素 1:1（基准 = 蛞蝓猫 chunk rad 9/8）
N_BODY = 3                    # 躯干三节（同游戏 bodyChunks）
MAX_TAIL_SEGS = 11            # 尾段上限（原版红蜥 tailSegments=11，最长的品种）
SEG_STIFF_BODY = 0.55         # 躯干节跟随刚度（高=挺）
SEG_STIFF_TAIL = 0.30         # 尾节更软
SEG_GRAV = 0.22               # 悬空（被拎起）时链节下坠
HURT_STUN = 70                # 非致命伤的僵直 tick
HURT_FLASH = 8                # 受击白闪帧数
CORPSE_TTL = 1500             # 尸体保留 tick（约 25s）
HEAD_STAND_FAC = 2.05         # 头（链首）离地高度 = 躯干半径 * 此值
BODY_STAND_FAC = 1.7          # 躯干节最低离地 = 自身半径 * 此值
TAIL_SINK_FAC = 0.5           # 尾节可拖到接近地面
TURN_VX = 0.35                # 判定「真的转身」的横向速度阈值（避免停下时身体窜到头前面）
LEG_SIDE_FAC = 0.55           # 腿根挂在躯干侧下方 = 半径 * 此值

# ── AI ──
NOTICE_R = 150.0              # 视野半径：注意到猫（原版关系 Eats 1.0）

# 光标恐惧（原版蜥蜴对秃鹫面具的 fear 反应；宠物里把鼠标当作同级威胁源）
CURSOR_FEAR_R = 90.0          # 光标进入此半径开始害怕
CURSOR_FEAR_ARM = 3           # 连续贴脸这么久才真正受惊（防误触）
CURSOR_FEAR_TICKS = 110       # 单次受惊逃跑时长（≈2.8s）
CURSOR_FEAR_SPEED = 1.05      # 逃跑速度 × base_speed
CURSOR_FEAR_ACCEL = 0.16
CURSOR_FEAR_HOP = 0.02        # 逃跑时回头跳的概率
LOST_R = 230.0                # 超出即失去兴趣
TARGET_HOLD_OBJ = 90          # 对象目标失联后的宽限帧数（原版 forgetDelay）
TARGET_HOLD_POINT = 10 ** 9   # 纯坐标目标（光标）仍按距离判定
LUNGE_ACCEL = 0.20            # 扑咬时朝目标的加速度比例
CLIMB_HOP = -6.4              # 目标在上方时的蹬地（y↓ 取负）
HOP_CD = 46
JAW_OPEN_RATE = 0.22
JAW_CLOSE_RATE = 0.26
BITE_HOLD = 18                # 咬合保持 tick
COOLDOWN_TICKS = 150
IDLE_TICKS = (60, 200)        # 原地停留时长
WANDER_MARGIN = 40.0
WALK_TURN = 0.14              # 游走时速度趋近速率
BLINK_RATE = 0.0125           # 头部呼吸闪烁推进速率（同游戏 LizardGraphics.breath 步长）
MAX_SEG_SPEED = 24.0

# ── 配色（同游戏 LizardGraphics.ApplyPalette / BodyColor）──
TAME_LIKE = 0.5                # 原版：like 超过 0.5 即认主跟随
FOLLOW_GAP = 46.0              # 驯服后与朋友保持的距离

BLACK_RGB = (27, 11, 33)       # 近似 RoomPalette.blackColor：绝大多数蜥蜴的体色
WHITE_RGB = (255, 255, 255)    # 白蜥体色走纯白分支
SALAMANDER_RGB = (232, 232, 244)


def _hsl2rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    """HSL→RGB（0..1），同游戏 Custom.HSL2RGB。"""
    h = h % 1.0
    v = l + s * min(l, 1.0 - l)
    if v <= 0.0:
        return (0, 0, 0)
    m = max(0.0, l + l - v)
    t = clampf((v - m) / v, 0.0, 1.0)

    def f(n):
        return m + v * clampf(abs((h * 6.0 + n) % 6.0 - 3.0) - 1.0, 0.0, 1.0) * t

    if s == 0.0:
        g = int(round(l * 255.0))
        return (g, g, g)
    return (int(round(f(0.0) * 255.0)), int(round(f(4.0) * 255.0)), int(round(f(2.0) * 255.0)))


class LizardBreed:
    """一种蜥蜴的静态定义；字段名对应游戏 LizardBreedParams / LizardBreeds。

    数值全部照抄 LizardBreeds.cs 中各品种的赋值（绿/粉/白优先校对过 wiki）。
    战斗相关：原版 CreatureTemplate.baseDamageResistance = toughness * 2，
    baseStunResistance = stunToughness，LizardState.health 初始恒为 1.0。
    """

    __slots__ = ("key", "name_zh", "name_en", "hue", "sat", "light", "plain_color",
                 "body_rgb", "head_rgb", "spikes",
                 "head_graphics", "body_size_fac", "body_rad_fac", "body_length_fac",
                 "head_size", "tail_segs", "tail_len_fac", "limb_size", "limb_thickness",
                 "base_speed", "jaw_open_angle", "jaw_lower_fac", "jaw_apart",
                 "neck_stiffness", "body_stiffness", "tail_col_start", "tail_col_exp",
                 "bite_damage", "anchor_y", "head_hue_var", "head_light_var",
                 "hide_eyes", "toughness", "stun_toughness", "bite_chance",
                 "attempt_bite_radius", "taming_difficulty", "head_shield_angle",
                 "danger", "visual_radius", "tongue", "tongue_range", "body_mass",
                 "flips_from_rock", "bite_damage_chance")

    def __init__(self, key, name_zh, name_en, hue, light, head_graphics, *,
                 size=1.0, body_rad_fac=1.0, body_length_fac=1.0, head_size=1.0,
                 tail_segs=5, tail_len_fac=1.2, limb_size=1.0, limb_thickness=1.0,
                 base_speed=4.0, jaw_open_angle=90.0, jaw_lower_fac=2.0 / 3.0,
                 jaw_apart=23.0, neck_stiffness=0.2, body_stiffness=0.2,
                 tail_col_start=0.3, tail_col_exp=2.0, bite_damage=1.0,
                 sat=1.0, plain_color=None, anchor_y=0.7,
                 hue_var=0.10, light_var=0.15, hide_eyes=False, spikes=None,
                 toughness=1.0, stun_toughness=1.0, bite_chance=0.5,
                 bite_damage_chance=1.0 / 3.0,
                 attempt_bite_radius=80.0, taming_difficulty=1.0,
                 head_shield_angle=100.0, danger=0.45, visual_radius=900.0,
                 tongue=False, tongue_range=0.0, body_mass=2.1,
                 flips_from_rock=True):
        self.key = key
        self.name_zh = name_zh
        self.name_en = name_en
        self.hue = hue
        self.sat = sat
        self.light = light
        self.plain_color = plain_color      # 白/黑等不走 HSL 的品种
        self.head_graphics = head_graphics  # (jaw, lowerTeeth, upperTeeth, head, eyes)
        self.body_size_fac = size
        self.body_rad_fac = body_rad_fac
        self.body_length_fac = body_length_fac
        self.head_size = head_size
        self.tail_segs = tail_segs
        self.tail_len_fac = tail_len_fac
        self.limb_size = limb_size
        self.limb_thickness = limb_thickness
        self.base_speed = base_speed
        self.jaw_open_angle = jaw_open_angle
        self.jaw_lower_fac = jaw_lower_fac
        self.jaw_apart = jaw_apart
        self.neck_stiffness = neck_stiffness
        self.body_stiffness = body_stiffness
        self.tail_col_start = tail_col_start
        self.tail_col_exp = tail_col_exp
        self.bite_damage = bite_damage
        self.anchor_y = anchor_y
        self.head_hue_var = hue_var
        self.head_light_var = light_var
        self.hide_eyes = hide_eyes
        self.spikes = spikes                # 背刺 (graphic, colored, 出现概率)，None=无
        # ── 原版战斗/AI 参数 ──
        self.toughness = toughness
        self.stun_toughness = stun_toughness
        self.bite_chance = bite_chance          # 咬中时掷的命中概率
        self.bite_damage_chance = bite_damage_chance   # 咬中后造成 biteDamage 的概率
        self.attempt_bite_radius = attempt_bite_radius   # 开始尝试咬的半径（游戏像素）
        self.taming_difficulty = taming_difficulty
        self.head_shield_angle = head_shield_angle
        self.danger = danger
        self.visual_radius = visual_radius
        self.tongue = tongue
        self.tongue_range = tongue_range
        self.body_mass = body_mass
        self.flips_from_rock = flips_from_rock   # 原版红蜥不吃石头转身
        # 体/头配色：白蜥全身纯白、头按原版压黑；蝾螈灰白；黑蜥整体近黑；其余体黑头染品种色
        if plain_color == WHITE_RGB:
            self.body_rgb, self.head_rgb = WHITE_RGB, WHITE_RGB
        elif key in ("salamander", "black"):
            self.body_rgb = self.head_rgb = (SALAMANDER_RGB if key == "salamander"
                                            else BLACK_RGB)
        else:
            self.body_rgb, self.head_rgb = BLACK_RGB, None

    @property
    def damage_resistance(self) -> float:
        """原版 CreatureTemplate.baseDamageResistance = toughness * 2。

        矛伤害 1.0 → 粉蜥(1)  0.5/矛 = 2 矛死（wiki：2-4 矛）；
        绿蜥(2.5) 0.2/矛 = 5 矛（wiki：5-10 矛）；白蜥(0.9) 2 矛；红蜥(3) 6 矛。
        """
        return max(0.05, self.toughness * 2.0)

    @property
    def stun_resistance(self) -> float:
        """原版 CreatureTemplate.baseStunResistance = stunToughness（不乘 2）。"""
        return max(0.05, self.stun_toughness)

    def color(self, rng) -> tuple[int, int, int]:
        """出生时随机化个体色，同游戏 effectColor 的 WrappedRandomVariation。"""
        if self.plain_color is not None:
            return self.plain_color
        h = self.hue + rng.uniform(-self.head_hue_var, self.head_hue_var)
        l = clampf(self.light + rng.uniform(-self.head_light_var, self.head_light_var), 0.12, 0.92)
        return _hsl2rgb(h, self.sat, l)

    def tail_tint(self, rng, color):
        """尾梢渐变色（游戏 iVars.tailColor）：白蜥/黑蜥恒无，其余 1/2 概率，色=品种色。"""
        if self.plain_color is not None or rng.random() > 0.5:
            return None
        return (color, 0.35 + 0.65 * rng.random())


# 九种基础蜥蜴：数值逐项照抄 LizardBreeds.cs（PinkLizard/GreenLizard/BlueLizard/
# YellowLizard/WhiteLizard/RedLizard/BlackLizard/Salamander/CyanLizard）。
BREEDS = (
    LizardBreed("pink", "粉蜥", "Pink lizard", 0.87, 0.50, (0, 0, 0, 0, 0),
                size=1.00, base_speed=4.1, tail_segs=5, tail_len_fac=1.2,
                bite_damage=1.0, bite_damage_chance=1.0 / 3.0, bite_chance=0.5, attempt_bite_radius=80.0,
                taming_difficulty=1.0, danger=0.45, visual_radius=900.0,
                body_mass=2.1, spikes=(0, 0, 0.5)),
    LizardBreed("green", "绿蜥", "Green lizard", 0.32, 0.50, (1, 1, 1, 1, 1),
                size=1.20, base_speed=6.7, tail_segs=7, tail_len_fac=0.9, limb_size=1.4,
                jaw_open_angle=50.0, jaw_lower_fac=0.5, jaw_apart=14.0, neck_stiffness=1.0,
                body_stiffness=0.5, tail_col_start=0.05, tail_col_exp=4.0,
                bite_damage=2.0, bite_damage_chance=0.5, bite_chance=1.0 / 3.0, attempt_bite_radius=100.0,
                anchor_y=0.55,
                toughness=2.5, stun_toughness=2.5, taming_difficulty=0.8,
                danger=0.45, visual_radius=850.0, body_mass=7.5, spikes=(3, 2, 0.8)),
    LizardBreed("blue", "蓝蜥", "Blue lizard", 0.57, 0.50, (0, 0, 0, 0, 0),
                size=0.90, head_size=0.9, base_speed=3.2, tail_segs=4, tail_len_fac=1.0,
                limb_size=0.9, jaw_open_angle=105.0, jaw_lower_fac=0.55, jaw_apart=20.0,
                neck_stiffness=0.0, body_stiffness=0.0, tail_col_start=0.1, tail_col_exp=1.2,
                bite_damage=0.7, bite_damage_chance=0.2, bite_chance=0.4, attempt_bite_radius=90.0,
                toughness=0.5, stun_toughness=0.5, taming_difficulty=1.1,
                danger=0.35, visual_radius=950.0, body_mass=1.4,
                tongue=True, tongue_range=140.0, hue_var=0.08),
    LizardBreed("yellow", "黄蜥", "Yellow lizard", 0.10, 0.50, (0, 0, 0, 0, 0),
                size=0.93, base_speed=4.1, tail_segs=5, tail_len_fac=1.2,
                jaw_open_angle=90.0, jaw_apart=23.0,
                body_stiffness=0.2, tail_col_start=0.3, tail_col_exp=2.0,
                bite_damage=0.8, bite_damage_chance=0.25, bite_chance=1.0 / 6.0, attempt_bite_radius=40.0,
                toughness=0.8, stun_toughness=0.8, taming_difficulty=3.0,
                danger=0.4, visual_radius=900.0, body_mass=1.7, hue_var=0.05),
    LizardBreed("white", "白蜥", "White lizard", 0.0, 1.0, (0, 0, 0, 0, 3),
                size=1.00, base_speed=3.8, tail_segs=5, tail_len_fac=1.2,
                jaw_open_angle=110.0, jaw_lower_fac=0.5, neck_stiffness=0.05,
                body_stiffness=0.15, tail_col_start=0.1, tail_col_exp=1.2,
                bite_damage=1.0, bite_damage_chance=0.2857143, bite_chance=0.5, attempt_bite_radius=85.0,
                toughness=0.9, stun_toughness=0.9, taming_difficulty=3.0,
                danger=0.5, visual_radius=1300.0, body_mass=2.1,
                sat=0.0, plain_color=(255, 255, 255), anchor_y=0.75,
                tongue=True, tongue_range=440.0),
    LizardBreed("red", "红蜥", "Red lizard", 0.0025, 0.50, (0, 0, 0, 0, 0),
                size=1.20, head_size=1.2, base_speed=5.0, tail_segs=11, tail_len_fac=1.9,
                limb_size=1.5, jaw_open_angle=140.0, body_stiffness=0.3,
                bite_damage=4.0, bite_damage_chance=1.0, bite_chance=1.0, attempt_bite_radius=120.0,
                toughness=3.0, stun_toughness=3.0, taming_difficulty=7.0,
                danger=0.8, visual_radius=2300.0, body_mass=3.1,
                tongue=True, tongue_range=350.0, flips_from_rock=False,
                hue_var=0.02, spikes=(0, 0, 0.7)),
    LizardBreed("black", "黑蜥", "Black lizard", 0.0, 0.10, (0, 0, 0, 0, 0),
                size=0.90, base_speed=3.9, tail_segs=6, tail_len_fac=1.2, limb_size=1.1,
                body_stiffness=0.25, bite_damage=1.0, bite_damage_chance=5.0 / 14.0, bite_chance=1.0 / 3.0,
                attempt_bite_radius=70.0, toughness=1.0, stun_toughness=1.0,
                taming_difficulty=4.0, danger=0.45, visual_radius=0.0, body_mass=2.0,
                sat=0.0, plain_color=(26, 26, 26),
                hue_var=0.0, light_var=0.0, hide_eyes=True, spikes=(0, 0, 0.7)),
    LizardBreed("salamander", "蝾螈", "Salamander", 0.90, 0.40, (2, 2, 2, 2, 2),
                size=0.90, head_size=0.9, base_speed=3.1, tail_segs=5, tail_len_fac=1.2,
                limb_size=0.65, jaw_apart=15.0, bite_damage=0.9, bite_damage_chance=1.0 / 3.0,
                bite_chance=1.0 / 3.0, attempt_bite_radius=70.0,
                toughness=1.0, stun_toughness=1.0, taming_difficulty=3.5,
                head_shield_angle=70.0, danger=0.4, visual_radius=960.0, body_mass=2.1,
                tongue=True, tongue_range=150.0, hue_var=0.15),
    LizardBreed("cyan", "青蜥", "Cyan lizard", 0.49, 0.50, (0, 0, 0, 0, 0),
                size=0.65, base_speed=3.0, tail_segs=5, tail_len_fac=1.44, limb_size=0.8,
                limb_thickness=0.8, jaw_open_angle=80.0, jaw_apart=17.0, body_stiffness=0.8,
                bite_damage=1.0, bite_damage_chance=0.25, bite_chance=0.5, attempt_bite_radius=80.0,
                toughness=0.35, stun_toughness=50.0, taming_difficulty=1.0,
                head_shield_angle=70.0, danger=0.25, visual_radius=990.0, body_mass=0.8,
                tongue=True, tongue_range=160.0, hue_var=0.04),
)
BREED_BY_KEY = {b.key: b for b in BREEDS}


class _Seg:
    """链体节：位置 + 半径 + 到前一节的固定距离 + 跟随刚度。"""

    __slots__ = ("x", "y", "lx", "ly", "rad", "dist", "stiff", "tail")

    def __init__(self, x, y, rad, dist, stiff, tail):
        self.x = self.lx = float(x)
        self.y = self.ly = float(y)
        self.rad = float(rad)
        self.dist = float(dist)
        self.stiff = stiff
        self.tail = tail


class _Leg:
    """一条腿：脚点位 + 迈步摆动 + 前后/远近标记。"""

    __slots__ = ("x", "y", "lx", "ly", "tx", "ty", "swing", "lift", "back", "near", "rest")

    def __init__(self, x, y, back: bool, near: bool):
        self.x = self.lx = float(x)
        self.y = self.ly = float(y)
        self.tx = float(x)
        self.ty = float(y)
        self.swing = 0.0
        self.lift = 0.0
        self.back = back
        self.near = near
        self.rest = 0.0


class Lizard:
    """一只蜥蜴：头为驱动质点，躯干/尾逐节跟随；巡走 → 警觉 → 扑咬。"""

    collision_layer = 0                 # 不参与 chunk 互推，交互全部走 AI

    __slots__ = ("breed", "color", "tail_edge", "tail_amt", "rng", "seed", "id",
                 "x", "y", "vx", "vy", "last_x", "last_y", "head_rad", "head_conn",
                 "body_rad", "seg", "legs", "state", "facing", "look_at",
                 "head_angle", "last_head_angle", "jaw", "last_jaw",
                 "target", "target_obj", "bite_event", "bite_hold", "bite_cd", "_tgt_hold",
                 "walk_phase", "idle_timer", "goal_x", "hop_cd", "blink", "last_blink",
                 "chain_dir",
                 "held_by_hand", "water_y", "room_gravity", "_contact_floor",
                 "dead", "spacing", "spikes", "like", "tamed", "friend_id",
                 "max_health", "health", "stun", "hurt_flash", "dead_t",
                 "rock_push", "rock_push_dir",
                 "fear_t", "fear_x", "fear_y", "fear_seen", "wall_dir")

    def __init__(self, x: float, y: float, breed: LizardBreed | None = None,
                 seed: int = 0, id: int = 0):
        self.rng = _random.Random(seed * 7919 + 13)
        self.breed = breed or BREEDS[0]
        self.seed = int(seed)
        self.id = int(id)
        rng = self.rng
        self.color = self.breed.color(rng)
        tint = self.breed.tail_tint(rng, self.color)
        self.tail_edge = tint[0] if tint else None
        self.tail_amt = tint[1] if tint else 0.0
        self.like = 0.0                  # 原版 SocialMemory.like
        self.tamed = False
        self.friend_id = None            # 驯服它的猫（PetUnit.id）

        b = self.breed
        self.head_rad = 6.0 * b.head_size * BODY_SCALE
        self.head_conn = 11.0 * b.head_size * BODY_SCALE
        self.body_rad = 8.0 * b.body_size_fac * b.body_rad_fac * BODY_SCALE
        self.spacing = 17.0 * b.body_length_fac * (b.body_size_fac + 1.0) / 2.0 * BODY_SCALE

        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.room_gravity = 1.0
        self.water_y = None
        self._contact_floor = False
        self.held_by_hand = None
        self.dead = False
        # 原版 HealthState/LizardState 的 health 初始恒为 1.0；
        # 抗性走 CreatureTemplate.baseDamageResistance = toughness * 2。
        self.max_health = self.health = 1.0
        self.stun = 0            # 受击眩晕 tick
        self.rock_push = 0       # 被石头砸歪的剩余 tick（原版 turnedByRockCounter=20）
        self.rock_push_dir = 0
        self.hurt_flash = 0      # 受击白闪（渲染用）
        self.dead_t = 0          # 尸体已躺 tick
        # 光标恐惧（原版 LizardAI 的 fear 状态）
        self.fear_t = 0
        self.fear_x = 0.0
        self.fear_y = 0.0
        self.fear_seen = 0
        self.wall_dir = 0        # 贴在左右墙时记墙侧（窗口边缘＝墙）

        # 链体：躯干 N_BODY 节 + 尾若干节；dist 为到前一节的固定距离
        n_tail = max(2, min(int(b.tail_segs), MAX_TAIL_SEGS))
        segs = []
        prev_x, prev_y, prev_d = self.x, self.y, self.head_conn
        for i in range(N_BODY):
            segs.append(_Seg(prev_x - prev_d, prev_y, self.body_rad, prev_d, SEG_STIFF_BODY, False))
            prev_x, prev_y, prev_d = segs[-1].x, segs[-1].y, self.spacing
        for j in range(n_tail):
            rad = 8.0 * b.body_size_fac * (n_tail - j) / float(n_tail) * BODY_SCALE
            conn = ((16.0 if j == 0 else 8.0) * BODY_SCALE + rad) / 2.0 * b.tail_len_fac
            segs.append(_Seg(prev_x - conn, prev_y, rad, conn, SEG_STIFF_TAIL, True))
            prev_x, prev_y, prev_d = segs[-1].x, segs[-1].y, conn
        self.seg = segs

        # 四条腿：前对挂第 0 节、后对挂第 2 节；每条腿分远近（绘制层不同）
        fx = self.seg[0].x
        bx = self.seg[2].x if len(self.seg) > 2 else self.seg[-1].x
        fy = self.seg[0].y + self.body_rad * LEG_SIDE_FAC
        by = (self.seg[2].y if len(self.seg) > 2 else self.seg[-1].y) + self.body_rad * LEG_SIDE_FAC
        self.legs = [_Leg(fx, fy, False, False), _Leg(fx, fy, False, True),
                     _Leg(bx, by, True, False), _Leg(bx, by, True, True)]

        # 背刺（游戏 SpineSpikes）：数量/长度/大小曲线逐个随机
        self.spikes = None
        if b.spikes:
            graphic, colored, chance = b.spikes
            if rng.random() < chance:
                n = rng.randint(5, 8)
                end = rng.uniform(0.2, 0.95)             # 覆盖到体长/总长的比例
                lo = rng.uniform(0.15, 0.5)
                hi = max(lo, rng.uniform(lo, 1.1))
                skew = rng.uniform(0.1, 0.9)
                pts = []
                for k in range(n):
                    t = k / (n - 1.0)
                    pts.append((0.05 + (end - 0.05) * t,
                                lo + (hi - lo) * math.sin((t ** skew) * math.pi)))
                self.spikes = (graphic, colored, pts)

        self.state = ItemState.FREE
        self.facing = 1
        self.chain_dir = 1.0
        self.look_at = None
        self.head_angle = 0.0
        self.last_head_angle = 0.0
        self.jaw = 0.0
        self.last_jaw = 0.0
        self.target = None
        self.target_obj = None
        self.bite_event = None
        self._tgt_hold = 0
        self.bite_cd = rng.randint(30, 90)
        self.bite_hold = 0
        self.walk_phase = rng.random()
        self.blink = self.last_blink = rng.random()   # 原版 LizardGraphics.blink：头部呼吸闪烁相位
        self.idle_timer = rng.randint(*IDLE_TICKS)
        self.goal_x = self.x
        self.hop_cd = 0

    # ── 查询 ──
    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def rad(self):
        """通用工具（边界夹取/水花溅射）读的半径。"""
        return self.body_rad

    @property
    def mass(self):
        """通用工具（水花溅射强度）读的质量。"""
        return 1.0 + 0.5 * self.breed.body_size_fac

    def body_path(self):
        """头到尾的折线，供渲染与包围盒。"""
        pts = [(self.x, self.y)]
        pts.extend((s.x, s.y) for s in self.seg)
        return pts

    @property
    def notice_r(self) -> float:
        """视野半径：原版按品种 visualRadius 缩放。

        黑蜥 visualRadius = 0（全盲，只靠近身/声音），红蜥 2300 最远，白蜥 1300。
        基准 900 = 粉蜥，保持与旧常量 NOTICE_R 同量级。
        """
        return clampf(NOTICE_R * self.breed.visual_radius / 900.0, 52.0, NOTICE_R * 2.2)

    def bounding_pad(self):
        """脏矩形外扩半径。"""
        return max(self.body_rad, self.head_rad) + 26.0 * self.breed.limb_size + 8.0

    # ── 状态 ──
    def die(self) -> None:
        """立即移除（清场 / 被超度）。"""
        self.dead = True
        self.state = ItemState.GONE

    def kill(self) -> None:
        """被杀死：留尸、瘫软，不再行动（同游戏死蜥尸体）。"""
        if self.dead:
            return
        self.dead = True
        self.dead_t = 0
        self.stun = 0
        self.jaw = 0.0
        self.target = self.target_obj = None
        self.look_at = None
        self.state = ItemState.FREE

    # ── 受击：Lizard.Violence / HitHeadShield / HitInMouth 的移植 ──
    def hit_in_mouth(self, dvec) -> bool:
        """原版 Lizard.HitInMouth：在 Unity(y↑) 里 direction.y > 0 直接返回 false，
        再 Slerp(direction, up, 0.1)，与 -bodyChunks[0].Rotation 的夹角 < Lerp(-15, 11, JawOpen)。
        """
        dx, dy = dvec
        ux, uy = dx, -dy                       # 本工程 y↓ → Unity y↑
        if uy > 0.0:
            return False
        n = math.hypot(ux, uy)
        if n < 1e-9:
            return False
        ux, uy = ux / n, uy / n
        a0 = math.atan2(uy, ux)                # Vector3.Slerp(dir, (0,1), 0.1)
        d = ((-a0 + math.pi) % math.tau) - math.pi
        a = a0 + d * 0.1
        ux, uy = math.cos(a), math.sin(a)
        hx = math.sin(math.radians(self.head_angle))
        hy = math.cos(math.radians(self.head_angle))
        dot = clampf(ux * hx + uy * hy, -1.0, 1.0)
        return math.degrees(math.acos(dot)) < lerp(-15.0, 11.0, clampf(self.jaw, 0.0, 1.0))

    def hit_head_shield(self, dvec) -> bool:
        """原版 Lizard.HitHeadShield：伤害方向与「头朝后」夹角 < headShieldAngle + 20*JawOpen
        （也就是从正面打脸时被头甲弹开）。红蜥之外的品种在嘴张开时盾角更大。
        """
        if self.hit_in_mouth(dvec):
            return False
        n = math.hypot(dvec[0], dvec[1])
        if n < 1e-9:
            return False
        dir_angle = math.degrees(math.atan2(dvec[0], -dvec[1]))
        back = self.head_angle + 180.0          # -bodyChunks[0].Rotation
        a = abs((dir_angle - back + 180.0) % 360.0 - 180.0)
        return a < self.breed.head_shield_angle + 20.0 * clampf(self.jaw, 0.0, 1.0)

    def hurt(self, damage: float, *, dvec=None, speed: float = 0.0,
             stun_bonus: float = 0.0, hit_head: bool = False,
             knock_k: float = 0.0) -> bool:
        """受伤（原版 Creature.Violence → Lizard.Violence）。返回本次是否致死。

        damage      伤害值：矛 1.0（Spear.spearDamageBonus）/ 石头 0.01（Rock）
        dvec        攻击动量方向（单位向量，y↓）；None = 无方向
        speed       攻击物速度；原版 momentum = vel * (mass * 2)，这里折算成 knock_k*speed
        stun_bonus  眩晕附加：矛 20 / 石头 45
        hit_head    是否命中头节（原版 hitChunk.index == 0）
        """
        if self.dead:
            return True
        num = damage / self.breed.damage_resistance
        num2 = (damage * 30.0 + stun_bonus) / self.breed.stun_resistance
        shielded = False
        if hit_head and dvec is not None:
            if self.hit_in_mouth(dvec):                 # 打进喉咙：伤害 ×1.5、眩晕翻倍
                num *= 1.5
                num2 = min(num2 * 2.0, 120.0)
            elif self.hit_head_shield(dvec):            # 头甲：伤害 ×0.1
                shielded = True
                num *= 0.1
                num2 = ((damage * 0.5 * 30.0 + stun_bonus * (2.0 / 3.0))
                        / self.breed.stun_resistance)
        if dvec is not None and speed > 0.0 and knock_k > 0.0:
            # 原版：hitChunk.vel += directionAndMomentum / hitChunk.mass
            f = knock_k * speed / max(0.6, self.breed.body_mass)
            if shielded:
                f /= 3.0                                # 头盾：directionAndMomentum / 3
            self.vx += dvec[0] * f
            self.vy += dvec[1] * f
        self.hurt_flash = HURT_FLASH
        self.health -= num
        self.stun = max(self.stun, int(min(num2, 200.0)))
        self.jaw = 0.0
        if shielded:
            # 原版会 WhiteFlicker + 火花：这里只保留头甲的手感（不打断目标）
            return False
        if self.health <= 1e-6:            # 原版 HealthState.health <= 0f（容浮点累减）
            self.kill()
            return True
        self.target = self.target_obj = None
        return False
    def grab(self, cursor) -> None:
        """被鼠标拎起。"""
        self.held_by_hand = True
        self.state = ItemState.MOUSE
        self.vx = self.vy = 0.0
        self.target = None
        self.target_obj = None

    def release(self, vx=0.0, vy=0.0) -> None:
        self.held_by_hand = None
        self.state = ItemState.FREE
        self.vx, self.vy = vx, vy

    # ── 主循环 ──
    def step(self, WL: float, HL: float, targets=(), cursor=None,
             rivals=(), prey=()) -> None:
        """推进一 tick。

        targets: [(obj, x, y)] 蛞蝓猫（原版关系 Eats 1.0）
        rivals:  [(obj, weight)] 同族竞争者（原版 AgressiveRival，只有绿蜥有）
        prey:    [(obj, weight)] 小猎物（原版 LizardTemplate → CicadaA Eats 0.05）
        cursor:  鼠标逻辑坐标
        """
        self.last_x, self.last_y = self.x, self.y
        self.last_head_angle = self.head_angle
        self.last_jaw = self.jaw
        self.last_blink = self.blink
        self.blink = (self.blink + BLINK_RATE + self.rng.random() * 0.001) % 1.0
        for s in self.seg:
            s.lx, s.ly = s.x, s.y
        for lg in self.legs:
            lg.lx, lg.ly = lg.x, lg.y

        if self.hurt_flash > 0:
            self.hurt_flash -= 1
        if self.dead:
            self.dead_t += 1
            if self.dead_t > CORPSE_TTL:
                self.state = ItemState.GONE
            self.vx *= 0.9
            self._integrate(WL, HL)
        elif self.state == ItemState.MOUSE:
            self._step_held(WL, HL, cursor)
        else:
            self._step_ai(WL, HL, targets, cursor, rivals, prey)
            self._integrate(WL, HL)

        self._step_chain(HL)
        self._step_legs(HL)
        self._step_head()

        if self.bite_hold > 0:
            self.bite_hold -= 1
        if self.bite_cd > 0:
            self.bite_cd -= 1
        if self.hop_cd > 0:
            self.hop_cd -= 1

    def _step_held(self, WL, HL, cursor) -> None:
        """被拎起：头跟光标，链体自然垂落。"""
        if cursor is None:
            return
        px, py = cursor
        self.vx = clampf(px - self.x, -MAX_SEG_SPEED, MAX_SEG_SPEED)
        self.vy = clampf(py - self.y, -MAX_SEG_SPEED, MAX_SEG_SPEED)
        self.x, self.y = px, py
        self.jaw = clampf(self.jaw + JAW_OPEN_RATE * 0.6, 0.0, 0.5)

    def _integrate(self, WL, HL) -> None:
        """自由态：重力积分 + 地面 / 侧墙。"""
        self.vx *= AIR_FRICTION
        self.vy = (self.vy + GRAVITY * self.room_gravity) * AIR_FRICTION
        if self.water_y is not None and self.y + self.head_rad > self.water_y:
            self.vy -= GRAVITY * 0.7 * self.room_gravity        # 浮力抵掉大部分重力
            self.vy *= 0.93
            self.vx *= 0.95
        self.x += self.vx
        self.y += self.vy

        r = self.head_rad
        floor = HL - self.body_rad * HEAD_STAND_FAC
        self._contact_floor = False
        self.wall_dir = 0
        if self.y > floor:
            self.y = floor
            if self.vy > 0.0:
                self.vy = 0.0
            self._contact_floor = True
            self.vx *= GROUND_FRICTION
        elif not self.dead and self.y < r:
            # 尸体不挡顶边：被甩出去就飞走（活动物照旧撞顶）
            self.y = r
            self.vy = max(self.vy, 0.0)
        if self.dead:
            return                      # 尸体只剩地面这一面（左右不挡）
        if self.x < r:
            self.x = r
            self.vx = abs(self.vx) * WALL_BOUNCE
            self.wall_dir = -1        # 窗口左边缘＝墙
        elif self.x > WL - r:
            self.x = WL - r
            self.vx = -abs(self.vx) * WALL_BOUNCE
            self.wall_dir = 1         # 窗口右边缘＝墙

    # ── AI ──
    def _step_ai(self, WL, HL, targets, cursor, rivals=(), prey=()) -> None:
        if self.rock_push > 0:
            # 原版 Lizard.cs：turnedByRockCounter 期间 WeightedPush(0, 2, (dir,0), 6f)
            self.rock_push -= 1
            self.vx += 0.14 * self.rock_push_dir * self.room_gravity
        if self.stun > 0:
            self.stun -= 1
            self.jaw = max(0.0, self.jaw - JAW_CLOSE_RATE)
            self.vx *= 0.90
            return
        if self._fear_tick(cursor, HL):           # 光标恐惧优先于捕猎
            return
        if self.tamed:                           # 认主的蜥蜴不再咬人，只跟着走
            self._follow(WL, HL, targets)
            return
        self._pick_target(targets, rivals, prey)
        if self.bite_hold > 0:                       # 咬合保持
            self.vx *= 0.84
            self.jaw = clampf(self.jaw + JAW_OPEN_RATE * 0.4, 0.0, 0.34)
            self._track_head()
            return
        if self.bite_cd > 0:
            self.jaw = max(0.0, self.jaw - JAW_CLOSE_RATE * 0.4)

        if self.target is not None:
            tx, ty = self.target
            dx, dy = tx - self.x, ty - self.y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                self._lunge(dx / d, dy / d, d, HL)
            return
        self._wander(WL, HL)

    def _follow(self, WL, HL, targets) -> None:
        """跟上朋友：近了就停下，远了就追。"""
        self.jaw = max(0.0, self.jaw - JAW_CLOSE_RATE)
        self.target = None
        self.target_obj = None
        tx = None
        for obj, ox, oy in targets:
            if self.friend_id is not None and getattr(obj, "id", None) == self.friend_id:
                tx, ty = ox, oy
                self.look_at = (ox, oy)
                break
        if tx is None:
            self.look_at = None
            self._wander(WL, HL)
            return
        dx = tx - self.x
        if abs(dx) > FOLLOW_GAP:
            want = clampf(dx * 0.05, -2.2, 2.2)
            self.vx += (want - self.vx) * WALK_TURN
        else:
            self.vx -= self.vx * 0.22

    def _fear_tick(self, cursor, HL) -> bool:
        """光标恐惧：原版蜥蜴对秃鹫面具的逃跑反应，这里把鼠标当威胁源。

        受惊期间背对光标加速逃开、闭颌、不咬任何人；结束后回到正常 AI。
        """
        if self.fear_t > 0:
            self.fear_t -= 1
            if cursor is not None:
                self.fear_x, self.fear_y = cursor[0], cursor[1]
            dx, dy = self.x - self.fear_x, self.y - self.fear_y
            d = math.hypot(dx, dy) or 1.0
            sp = self.breed.base_speed * CURSOR_FEAR_SPEED
            self.vx += (dx / d * sp - self.vx) * CURSOR_FEAR_ACCEL
            self.jaw = max(0.0, self.jaw - JAW_CLOSE_RATE)
            self.target = None
            self.target_obj = None
            self.look_at = (self.fear_x, self.fear_y)
            if self._contact_floor and self.rng.random() < CURSOR_FEAR_HOP:
                self.vy = CLIMB_HOP * 0.7
            return True
        if cursor is None or self.dead:
            self.fear_seen = 0
            return False
        if math.hypot(cursor[0] - self.x, cursor[1] - self.y) > CURSOR_FEAR_R:
            self.fear_seen = 0
            return False
        self.fear_seen += 1
        if self.fear_seen < CURSOR_FEAR_ARM:
            return False
        self.fear_t = CURSOR_FEAR_TICKS
        self.fear_x, self.fear_y = cursor[0], cursor[1]
        return True

    def _pick_target(self, targets, rivals=(), prey=()) -> None:
        """按「关系强度 / 距离」选目标（原版 Creature.Relationship + 猎物追踪器）。

        权重来自 StaticWorld.EstablishRelationship：
        蛞蝓猫 1.0；绿蜥对绿/粉/白的 AgressiveRival 0.8/0.2/0.05；
        蝉乌贼 LizardTemplate 0.05（蓝蜥/白蜥 0.7）。
        """
        notice = self.notice_r
        best, bestscore, bestobj = None, None, None

        def consider(obj, ox, oy, w):
            nonlocal best, bestscore, bestobj
            d = math.hypot(ox - self.x, oy - self.y)
            if d > notice:
                return
            score = d / max(0.05, w)          # 权重越高越优先
            if bestscore is None or score < bestscore:
                best, bestscore, bestobj = (ox, oy), score, obj

        for obj, ox, oy in targets:
            if self.friend_id is not None and getattr(obj, "id", None) == self.friend_id:
                continue
            consider(obj, ox, oy, 1.0)
        for obj, w in rivals:
            consider(obj, obj.x, obj.y, w)
        for obj, w in prey:
            consider(obj, obj.x, obj.y, w)
        if best is not None:
            self.target, self.target_obj = best, bestobj
            self.look_at = best
            self._tgt_hold = 0
            return
        # 失去目标：留一点余温，避免抖动。但对象类目标（猎物/同族/猫）不能拖太久，
        # 否则会拎着早就过期的坐标一路撞墙瞪着空气（原版 PreyTracker 的 forgetDelay）。
        if self.target is not None:
            self._tgt_hold += 1
            if self.target_obj is not None:
                if self._tgt_hold <= TARGET_HOLD_OBJ:
                    return
            else:
                tx, ty = self.target
                if self._tgt_hold <= TARGET_HOLD_POINT and math.hypot(tx - self.x, ty - self.y) < LOST_R:
                    return
        self.target = None
        self.target_obj = None
        self.look_at = None
    def _lunge(self, kx, ky, d, HL) -> None:
        """朝目标加速；够近了就咬。"""
        sp = self.breed.base_speed * 0.8
        self.vx += (kx * sp - self.vx) * LUNGE_ACCEL
        self.jaw = clampf(self.jaw + JAW_OPEN_RATE, 0.0, 0.9)
        reach = self.head_rad + (16.0 * self.breed.body_size_fac
                                 * (self.breed.attempt_bite_radius / 80.0))
        if d <= reach and self.bite_cd <= 0 and self.target_obj is not None:
            self._start_bite()
        elif self._contact_floor and self.hop_cd <= 0 and (self.y - self.target[1]) > 34.0:
            self.vy = CLIMB_HOP * math.sqrt(max(0.4, self.breed.body_size_fac))
            self.hop_cd = HOP_CD

    def gift_received(self, alive: bool, friend_id) -> None:
        """收到礼物（对照 LizardAI.GiftRecieved）。

        原版：like += (活体 1.2 : 尸体 0.6) / tamingDifficulty，
        tamingDifficulty = lizardParams.tamingDifficulty * Lerp(0.9,1.1,dominance)。
        粉蜥难度 1.0 → 一次活体 +0.6；绿蜥 0.8 → +0.75（wiki：1-2 次）；红蜥 7 → +0.086。
        """
        # LizardAI.GiftRecieved: flag = 礼物是尸体 → InfluenceLike((flag ? 1.2 : 0.6) / diff)
        gain = (0.6 if alive else 1.2) / max(0.1, self.breed.taming_difficulty)
        self.like += gain
        if not self.tamed and self.like > TAME_LIKE:
            self.tamed = True
            self.friend_id = friend_id
            self.jaw = 0.0
            self.bite_event = None

    def _start_bite(self) -> None:
        """原版 Lizard.cs:1238：按 biteDamageChance 掷骰，命中则 biteDamage * Lerp(0.8,1.2,rand)。"""
        self.bite_hold = BITE_HOLD
        self.bite_cd = COOLDOWN_TICKS
        self.jaw = 1.0
        b = self.breed
        dmg = 0.0
        if b.bite_damage_chance >= 1.0 or self.rng.random() < b.bite_damage_chance:
            dmg = b.bite_damage * lerp(0.8, 1.2, self.rng.random())
        self.bite_event = (self.target_obj, dmg)
        self.vx *= 0.2

    def _wander(self, WL, HL) -> None:
        """游走：定一个近处落点，走到／超时就换，再歇一会儿。"""
        self.jaw = max(0.0, self.jaw - JAW_CLOSE_RATE)
        self.idle_timer -= 1
        if self.idle_timer <= 0:
            span = self.rng.uniform(-1.0, 1.0) * 120.0
            self.goal_x = clampf(self.x + span, WANDER_MARGIN,
                                 max(WANDER_MARGIN, WL - WANDER_MARGIN))
            self.idle_timer = self.rng.randint(*IDLE_TICKS)
        dx = self.goal_x - self.x
        if abs(dx) < 10.0 or self.idle_timer > IDLE_TICKS[1] - 24:
            self.vx -= self.vx * 0.22
            return
        want = clampf(dx * 0.06, -2.4, 2.4)
        self.vx += (want - self.vx) * WALK_TURN

    def _track_head(self) -> None:
        """咬合期把头锁在目标方向。"""
        if self.target is not None:
            self.look_at = self.target

    def _step_head(self) -> None:
        if self.dead:
            self.head_angle = _ang_lerp(self.head_angle, 90.0 * self.facing, 0.04)
            self.jaw = max(0.0, self.jaw - JAW_CLOSE_RATE * 0.25)
            if math.sin(math.radians(self.head_angle)) >= 0.0:
                self.facing = 1
            else:
                self.facing = -1
            return
        """头朝向：优先看向目标／光标，否则顺着颈轴。"""
        nx, ny = self.seg[0].x, self.seg[0].y
        want = None
        if self.look_at is not None:
            want = _ang_from_up(self.look_at[0] - nx, self.look_at[1] - ny)
        elif self.state != ItemState.MOUSE:
            want = _ang_from_up(self.x - nx, self.y - ny)
        if want is not None:
            self.head_angle = _ang_lerp(self.head_angle, want, 0.25)
        if math.sin(math.radians(self.head_angle)) >= 0.0:
            self.facing = 1
        else:
            self.facing = -1

    # ── 链体 ──
    def _step_chain(self, HL) -> None:
        """头为领头点，逐节跟随；悬空节受重力。

        首节方向：有横向速度时强制「挂在头正后方」（原版靠头节质点击打实现；
                     若按节自身相对头的方位跟随，转身时身体会留在头前面，
                     看起来就是在朝反方向走）。
        其余节仍按上一节的实际方位跟随，并含重力分量 —— 这样贴地时会自然
        铺平、悬空时会垂挂，而不会因为方向被冻结而竖直堆在头顶。
        """
        prev_x, prev_y = self.x, self.y
        held = self.state == ItemState.MOUSE
        # 方向带记忆：只有真正走出速度才翻面；否则停稳瞬间的
        # ±0.0x 抖动会把躯干甩到头前面，看起来就是「朝反方向走」。
        if abs(self.vx) > TURN_VX:
            self.chain_dir = 1.0 if self.vx > 0.0 else -1.0
        forced = abs(self.vx) > 0.05
        # 链节恒受重力
        grav = SEG_GRAV * (1.35 if held else 1.0) * self.room_gravity
        for i, s in enumerate(self.seg):
            s.y += grav
            if forced and i == 0:
                ux, uy = -self.chain_dir, 0.0
            else:
                dx, dy = s.x - prev_x, s.y - prev_y
                d = math.hypot(dx, dy)
                ux, uy = ((-self.facing), 0.0) if d <= 1e-6 else (dx / d, dy / d)
            tx = prev_x + ux * s.dist
            ty = prev_y + uy * s.dist
            s.x += (tx - s.x) * s.stiff
            s.y += (ty - s.y) * s.stiff
            lim = HL - s.rad * (TAIL_SINK_FAC if s.tail else BODY_STAND_FAC)
            if s.y > lim:
                s.y = lim
            prev_x, prev_y = s.x, s.y
        # 步态摇摆：尾梢额外横向摆动
        if self.state != ItemState.MOUSE:
            for i, s in enumerate(self.seg):
                if s.tail:
                    s.y -= math.sin(self.walk_phase * math.tau + i * 0.7) * (0.16 * s.rad * 0.5)

    # ── 腿 ──
    def _step_legs(self, HL) -> None:
        """四足：挂在躯干两侧，走动迈步，悬空则垂下。"""
        anchors = self._leg_anchors()
        stride = 10.0 * self.breed.body_size_fac * BODY_SCALE
        self.walk_phase += abs(self.vx) * 0.045
        airborne = not self._contact_floor
        for i, lg in enumerate(self.legs):
            ax, ay = anchors[i]
            lg.rest = self.body_rad * 1.0
            if airborne:
                lg.swing = 0.0
                lg.lift = 0.0
                lg.tx, lg.ty = ax, ay + lg.rest * 0.8
                lg.x += (lg.tx - lg.x) * 0.12
                lg.y += (lg.ty - lg.y) * 0.12
                continue
            phase = (self.walk_phase + (0.5 if lg.back else 0.0)) % 1.0
            lg.tx = ax + (phase - 0.5) * stride
            lg.ty = HL - 1.0
            if abs(lg.tx - lg.x) > stride * 1.15:
                lg.swing = 1.0
            if lg.swing > 0.0:
                lg.swing = max(0.0, lg.swing - 0.22)
                lg.x += (lg.tx - lg.x) * 0.32
                lg.y += (lg.ty - lg.y) * 0.32
                lg.lift = math.sin((1.0 - lg.swing) * math.pi) * 4.5 * self.breed.body_size_fac
            else:
                lg.x += (lg.tx - lg.x) * 0.16
                lg.y += (lg.ty - lg.y) * 0.30
                lg.lift = 0.0

    def _leg_anchors(self):
        """前腿挂第 0 节两侧，后腿挂第 2 节两侧（远近各一）。"""
        f, b = self.seg[0], (self.seg[2] if len(self.seg) > 2 else self.seg[-1])
        out = []
        for seg, near in ((f, False), (f, True), (b, False), (b, True)):
            side = seg.rad * LEG_SIDE_FAC if near else seg.rad * (LEG_SIDE_FAC * 0.45)
            out.append((seg.x, seg.y + side))
        return out


def _ang_from_up(dx: float, dy: float) -> float:
    """由向量取 0=上、顺时针为正的角度（y↓）。"""
    return math.degrees(math.atan2(dx, -dy))


def _ang_lerp(a: float, b: float, k: float) -> float:
    """角度插值（走最短弧）。"""
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d * k
