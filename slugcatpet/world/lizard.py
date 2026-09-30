"""蜥蜴：三节躯干 + 尾链 + 独立头；巡走 / 警觉 / 扑咬 AI。坐标 y↓。

尺寸与色相照搬游戏常量（LizardBreedParams / Lizard.effectColor / LizardGraphics）。
躯干半径 8*bodySizeFac*bodyRadFac、节距 17*(bodySizeFac+1)/2、头连接 11*headSize，
整体再乘 BODY_SCALE 适配桌面。
"""
from __future__ import annotations
import math
import random as _random
from dataclasses import dataclass

from ..core.units import clampf, lerp, inv_lerp
from ..behavior.relationship import Relations
from .enums import ItemState
from .terrain import Caps
from . import lizard_cos
from .lizard_ai import (CARRY_HURRY, DEN_ARRIVE_R, DOMINANCE_DEFER, WARN_R,
                        ApproachPlan, Memory, Observation, PackAlert, PreyTracker,
                        SocialMemory, choose_den, flank_offset, los_blocked,
                        plan_approach, prefs_for, virtual_dens)

# ── 物理 ──
GRAVITY = 0.9                 # 同石头/蝙蝠量级
AIR_FRICTION = 0.99
GROUND_FRICTION = 0.84
WALL_BOUNCE = 0.2
BODY_SCALE = 1.0              # 与游戏像素 1:1（基准 = 蛞蝓猫 chunk rad 9/8）
N_BODY = 3                    # 躯干三节（同游戏 bodyChunks）
MAX_TAIL_SEGS = 11            # 尾段上限（原版红蜥 tailSegments=11，最长的品种）
SEG_STIFF_BODY = 0.80         # 躯干节跟随刚度（原版 elasticity 0.95，接近刚性）
SEG_STIFF_TAIL = 0.30         # 尾节更软
SEG_GRAV = 0.22               # 悬空（被拎起）时链节下坠
SEG_AIR_FRIC = 0.90           # 链节空气阻力（原版 BodyChunk airFriction 0.999，宠物里加重防抖）
SEG_CONN_ELASTICITY = 0.95    # 原版 BodyChunkConnection(Normal, elasticity 0.95)
SEG_ALIGN = 0.16              # 链节「接在父节延长线上」的软约束（替代原版 chunk 间的撑直）
SEG_ALIGN_HELD = 0.08         # 被拎起/拖动时放软：身体拖在后面，看得出被拽的体长变化
SEG_BEND_K = 0.30             # 转向惯性：速度突变把身体往转向侧甩的强度
SEG_BEND_MAX = 2.4            # 单节最大弯曲位移（防甩飞）
SEG_BEND_MIN_VX = 0.30        # 触发弯曲的最小速度变化
GAIT_WAVE = 0.50              # 步态波浪幅度（躯干随步频起伏）
SEG_CONN_HELD = 0.35          # 同上的杆长约束强度（原版 BodyChunkConnection 0.95 太硬，拖动时像根棍）
SEG_SOLVER_ITER = 3           # 杆长约束迭代次数（原版 chunk 之间有质量互顶，等价于多次收敛）
SEG_SMOOTH_ITER = 0           # 连接平滑迭代：把每节往相邻两节中点拉，消掉折角
SEG_SMOOTH_K = 0.0           # 每次平滑拉过去的比例（太大就变成一根软绳）
TAIL_LEN_BOOST = 1.12         # 尾节距整体略微加长（原版尾比躯干松弛，宠物里偏短）
DEPTH_LERP = 0.1              # 原版 depthRotation 的插值系数（LizardGraphics.Update）
HEAD_DEPTH_LERP = 0.5         # 原版 headDepthRotation 的插值系数
TURN_LIFT = 6.0               # 转身时上半身支起的高度（原版靠头部绳索，这里直接抬驱动点）
HURT_STUN = 70                # 非致命伤的僵直 tick
HURT_FLASH = 8                # 受击白闪帧数
CORPSE_TTL = 1500             # 尸体保留 tick（约 25s）
HEAD_STAND_FAC = 2.05         # 头（链首）离地高度 = 躯干半径 * 此值
BODY_STAND_FAC = 1.7          # 躯干节最低离地 = 自身半径 * 此值
TAIL_SINK_FAC = 0.5           # 尾节可拖到接近地面
TURN_VX = 0.35                # 判定「真的转身」的横向速度阈值（避免停下时身体窜到头前面）
LEG_SIDE_FAC = 0.55           # 腿根挂在躯干侧下方 = 半径 * 此值
LEG_JOINT = 25.0              # 原版 LizardLimb.jointDist 基准（再 ×(sizeFac+1)/2）
LEG_LIMB_RAD = 2.5            # 原版 LizardLimb 构造里的 rad
LEG_AIR_FRIC = 0.99           # 原版 Limb 的 airFriction
LEG_AIM_AHEAD = 26.0          # limbsAimFor 替代：躯干前方这么多像素（原版是行进目标格中心）
LEG_GRIP_DELAY = 1            # 原版 limbGripDelay（各品种都是 1）
NO_GRIP_SPEED = 0.10            # 原版 noGripSpeed：失去脚支撑后只保留极低滑行速度
FOOT_LEVERAGE = 0.045           # planted foot 对身体的反作用
FOOT_LEVERAGE_MAX = 0.75        # 单 tick 最大反作用
LINE_COLLIDE_PAD = 1.5          # 竖杆/背景墙碰撞余量
LEG_DEPTH_MIN = 10.0          # 原版 LizardGraphics 里判定 |num11|>10 才计入 depthRotation

# ── AI ──
NOTICE_R = 150.0              # 视野半径：注意到猫（原版关系 Eats 1.0）

LOST_R = 230.0                # 超出即失去兴趣

# 叼走死猫/昏迷猫（原版把猎物拖回巢穴的宠物化改写：改拖到屏幕两侧角落）
CARRY_NOTICE_R = 460.0        # 多远之内会主动去叼尸体/昏迷猫
CARRY_SPEED_FAC = 0.55        # 叼着东西走，速度打这个折
CARRY_CORNER_MARGIN = 34.0    # 角落落点距屏幕边缘
CARRY_ARRIVE_R = 22.0         # 距角落多近算「到了」
CARRY_MOUTH_FAC = 1.1         # 嘴前叼点 = 头半径 * 此值
CARRY_STUN_KEEP = 90          # 被叼住期间保持的昏迷 tick
CARRY_LOSE_DIST = 70.0        # 原版 Lizard.cs:1386：猎物被抓的那一截离嘴前锚点超过
                              # 「70 + 该截 rad」就 LoseAllGrasps（玩家能把它拽出来）
FAINT_BITE_BONUS = 2.2        # 昏迷的猫在选目标时的权重加成（优先咬死）
CARRY_DEN_ARRIVE_R = DEN_ARRIVE_R   # 巢穴落点判定（world/lizard_ai.py）
GUARD_PREY_TICKS = 1200       # 把猎物送回巢穴后守一会儿（原版回巢进食）
WARN_TICKS = 26               # 竞争者靠近时举头警告的时长
CONTEST_W = 1.4               # 争夺别人嘴里的猎物时，目标权重的加成
CROUCH_TARGET_MULT = 1.9      # 匍匐潜行的猫：权重除以这个（越大越不优先被盯上）
CAMO_TARGET_MULT = 4.0        # 隐身中的猫（守望者伪装）：权重再除以这个
TARGET_HOLD_OBJ = 90          # 对象目标失联后的宽限帧数（原版 forgetDelay）
TARGET_HOLD_POINT = 10 ** 9   # 纯坐标目标（光标）仍按距离判定
LUNGE_ACCEL = 0.20            # 扑咬时朝目标的加速度比例
CLIMB_HOP = -6.4              # 目标在上方时的蹬地（y↓ 取负）
CLIMB_SPEED = 2.6             # 贴着竖杆 / 背景墙往上爬的速度（原版 Climb tile 的爬速）
CLIMB_GRIP_R = 15.0           # 离竖线这么近才抓得住（抓附判定半径）
CLIMB_MIN_DY = 26.0           # 目标至少要比自己高/低这么多才值得爬
CLIMB_WALK_R = 150.0          # 没贴上去时，最多走这么远去找上墙点（Floor→Wall 那条连接）
CLIMB_WALK_TOL = 44.0         # 墙底 / 杆底离我这层楼这么近 = 这里就是上墙点
CLIMB_APPROACH_SPEED = 1.7    # 朝墙面挪的速度（还没有附着之前）
CLIMB_APPROACH_PENALTY = 90.0 # 要「走过去」的墙，打分加上这个（优先已经贴着的）
CLIMB_GRIP_SPRING = 0.30      # 贴上后把身体吸向墙面的弹性（不是每帧硬钉 x）
CLIMB_GRIP_DAMP = 0.60        # 贴墙时的横向阻尼
CLIMB_JUMP_PUSH = 4.6         # wall_jump 品种从墙上蹬出去的水平初速
# 青蜥蓄力弹射（wiki：爬墙 + 蓄力弹射）：扑击整段的顶速与加速都上调一档
CHARGE_LEAP_SPD = 1.9
CHARGE_LEAP_ACC = 0.55
# 白蜥环境伪装：蛞蝓猫注意它的距离打这个折扣（RIV 里玩家也更难看见它）
CAMO_NOTICE_FAC = 1.65
HOP_CD = 46
JAW_OPEN_RATE = 0.30          # 下颚张开速率（开得比闭快：扑咬要利落）
JAW_CLOSE_RATE = 0.26
HEAD_LOOK_FAST = 0.28          # 注视角跟随速率：攻击/扑咬
HEAD_LOOK_ALERT = 0.20         # 注视角跟随速率：追猎/逃跑/警告
HEAD_LOOK_SLOW = 0.12          # 注视角跟随速率：闲逛
LOOK_LIFT = 3.0                # 目标在上时颈部抬起的像素（视觉注意方向的竖向分量）
BODY_RAISE_LIFT = 2.0          # 威吓/警觉时支起上半身
BODY_COMPRESS_DIP = 1.2        # 恐惧/伏击时压低身体
BITE_HOLD = 18                # 咬合保持 tick
COOLDOWN_TICKS = 150
IDLE_TICKS = (60, 200)        # 原地停留时长
WANDER_MARGIN = 40.0
WALK_TURN = 0.14              # 游走时速度趋近速率
BLINK_RATE = 0.0125           # 头部呼吸闪烁推进速率（同游戏 LizardGraphics.breath 步长）
MAX_SEG_SPEED = 24.0
BODY_AX_LERP = 0.12           # 锚点方向每 tick 朝 chain_dir 靠这么多（转身时平滑滑过去，不再瞬移 2*头距）

# ── 原版关系表（StaticWorld.InitStaticWorldRelationships，decomp_full/StaticWorld.cs:3668-3726）──
# 值 = (关系类型, 强度)。类型 -> AI 模块的映射照抄 LizardAI.ModuleToTrackRelationship
# （LizardAI.cs:1346-1361）：
#   Eats / Attacks   -> PreyTracker（CreatureTemplate.Relationship.GoForKill：这两类且强度>0）
#   Afraid           -> ThreatTracker（逃跑）
#   AgressiveRival   -> AgressionTracker（anger 缓慢累积，够高才争夺；平时只 casual 撕咬）
#   Pack / Ignores / SocialDependent -> 不追踪
LIZ_REL = {
    "pink": {"pink": ("AgressiveRival", 0.4), "green": ("AgressiveRival", 0.15),
             "blue": ("AgressiveRival", 0.2), "white": ("AgressiveRival", 0.25)},
    "green": {"pink": ("AgressiveRival", 0.2), "green": ("AgressiveRival", 0.8),
              "white": ("AgressiveRival", 0.05), "blue": ("Eats", 0.25)},
    "blue": {"pink": ("AgressiveRival", 0.3), "blue": ("AgressiveRival", 0.45),
             "green": ("Afraid", 0.25), "white": ("Afraid", 0.1),
             "cyan": ("Afraid", 0.2), "squidcada": ("Eats", 0.7)},
    "white": {"pink": ("AgressiveRival", 0.15), "green": ("AgressiveRival", 0.05),
              "blue": ("AgressiveRival", 0.35), "white": ("AgressiveRival", 0.25),
              "squidcada": ("Eats", 0.7)},
    "cyan": {"cyan": ("AgressiveRival", 0.075), "blue": ("Eats", 0.15)},
    "black": {"black": ("AgressiveRival", 0.05)},
    "yellow": {"yellow": ("Pack", 0.2)},
    "red": {"red": ("Attacks", 1.0)},
    "salamander": {},
}
# 有 Pack 关系的品种（黄蜥）：会把「我在哪看见猎物」广播给同伴
PACK_BREEDS = frozenset(k for k, v in LIZ_REL.items()
                        if any(r[0] == "Pack" for r in v.values()))
# LizardTemplate 基表（StaticWorld.cs:3668-3689），只列本作场上存在的对象。
# 注意蛞蝓猫基表是 SocialDependent 0.5 —— 真正的捕食判定走动态关系
# （RelationshipTracker.cs:1460：like<0.5 → Eats，强度 = Pow(InverseLerp(0.5,-1,like),0.925)），
# 本工程即"未被驯服就捕食"。
LIZ_BASE_REL = {
    "lizard": ("AgressiveRival", 0.1),
    "squidcada": ("Eats", 0.05),
    "noodle_small": ("Eats", 0.3),
    "noodle_big": ("Eats", 0.25),
    "scavenger": ("Eats", 0.8),
}
# 视野锥：LizardBreeds.cs 里 perfectVisionAngle / periferalVisionAngle = Mathf.Lerp(1f,-1f,t)
# （LizardAI.VisualScore.cs:1184 用它把偏轴目标的得分线性扣掉）。
LIZ_VISION = {
    "pink": (0.0, 7.0 / 12.0),
    "green": (0.0, 5.0 / 18.0),
    "blue": (1.0 / 18.0, 11.0 / 24.0),
    "yellow": (1.0 / 12.0, 19.0 / 36.0),
    "white": (1.0 / 6.0, 19.0 / 36.0),
    "red": (4.0 / 9.0, 7.0 / 9.0),
    "black": (0.0, 0.0),                 # 全盲：只靠近身/声音（visualRadius=0）
    "salamander": (0.0, 31.0 / 36.0),
    "cyan": (1.0 / 12.0, 11.0 / 24.0),
}
TILE = 20.0                   # 原版一格 = 20px（AgressionTracker 的格距换算用）
VIS_BACK_FAC = 0.4            # 锥外残余视野：偏轴时等效视距压到 40%（原版扣分近似）

# ── 威胁 / 逃跑（Behavior.Flee）──
THREAT_NOTICE_FAC = 1.25      # 对 Afraid 对象的警觉半径放大（原版威胁阈值低于猎物）
FLEE_TICKS = 80               # 单次逃跑持续 tick
FLEE_SPEED = 1.12             # 逃跑速度 × base_speed
FLEE_ACCEL = 0.18
FLEE_HOP = 0.03

# ── 侵略追踪器（AgressionTracker，LizardAI.cs:628 / AgressionTracker.cs）──
ANGER_UP = 0.001              # 原版 angerSpeedUp
ANGER_DOWN = 0.001            # 原版 angerSpeedDown
ANGER_FIGHT = 0.35            # 原版 Utility() = InverseLerp(0.35,1,anger) 的下限
ANGER_W = 0.5                 # 原版 utilityComparer 里 agressionTracker 的权重（LizardAI.cs:648）
PREY_W = 0.6                  # 原版 preyTracker 权重（LizardAI.cs:644）
CASUAL_BITE_CHANCE = 0.5      # 原版 LizardAI.cs:1092 / DoIWantToBiteThisCreature:1678
CASUAL_PANIC_CHANCE = 0.1     # 原版 DoIWantToBiteThisCreature 第一行：残血时乱咬

# ── 受伤 / 潜伏 / 声音 ──
INJURY_UTIL = 0.3             # LizardInjuryTracker.Utility 超过此值 → Behavior.Injured
INJURY_SPEED = 0.7            # 受伤躲避的移动速度系数
LURK_IDLE_MULT = 4.0          # LurkTracker：白蜥/蝾螈原地待机时间 ×4（伏击）
NOISE_R = 320.0               # 听到地形撞击的半径
NOISE_TICKS = 240             # 声音记忆时长
PACK_GAP = 96.0               # 黄蜥结群保持的距离


def lizard_rel(mine: str, other: str):
    """两只蜥蜴之间的关系：品种专属表优先，否则退回 LizardTemplate 基表。"""
    r = LIZ_REL.get(mine, {}).get(other)
    if r is not None:
        return r
    return LIZ_BASE_REL["lizard"]


def lizard_rel_kind(mine: str, kind: str):
    """蜥蜴对非蜥蜴对象的关系（kind ∈ {"cat","squidcada","noodle_small",
    "noodle_big","scavenger"}）。"""
    if kind == "cat":
        return ("Eats", 1.0)      # 动态关系：like<0.5 才是 Eats（RelationshipTracker.cs:1460）
    r = LIZ_REL.get(mine, {}).get(kind)     # 品种专属覆盖优先（蓝/白蜥对蝉乌贼 0.7）
    if r is not None:
        return r
    return LIZ_BASE_REL.get(kind, ("Ignores", 0.0))


# ── 配色（同游戏 LizardGraphics.ApplyPalette / BodyColor）──
TAME_LIKE = 0.5                # 原版：like 超过 0.5 即认主跟随
FOLLOW_GAP = 46.0              # 驯服后与朋友保持的距离

BLACK_RGB = (27, 11, 33)       # 近似 RoomPalette.blackColor：绝大多数蜥蜴的体色
WHITE_RGB = (255, 255, 255)    # 白蜥体色走纯白分支
# 白蜥迷彩：低频采一圈「自己周围」的实时背景主色，整只体色平滑渐变过去，再按
# 缓慢呼吸在白色 ↔ 迷彩色之间换。反编译对照：原版白蜥体色就是**房间背景色**
# （LizardGraphics 的 camo 分支），头色在它和白色之间随叫声闪 —— 桌宠里「房间
# 背景」＝蜥蜴周围的真实桌面。采样以自己为中心、挖掉身体所在椭圆，所以拿到的是
# 「周边局部环境色」：不是整屏 dominant，也不是身体各部位各采一个色。
CAMO_SAMPLE_TICKS = 100        # 每 ~2.5 s 采一次（低频率）
CAMO_SAMPLE_RADIUS_X = 70.0    # 采样半宽下限（实际取 max(body_rad*4.5, 它)）
CAMO_SAMPLE_RADIUS_Y = 55.0    # 采样半高下限（实际取 max(body_rad*3.5, 它)）
CAMO_COLOR_RATE = 0.15         # 整只体色向新采样色渐变的速度（平滑、不跳色）
# 呼吸节律：绝大部分时间停在「纯取色」不动，只在每周期末尾短暂退回体色再变回来。
# 原来是一条正弦（一半时间卡在中间色），看起来像整只一直在变色。
CAMO_BREATH_TICKS = 900        # 一个完整呼吸周期 ~22.5 s
CAMO_PULSE_TICKS = 150         # 其中只有 ~3.75 s 真的退回体色
CAMO_MIX_MAX = 1.0             # 保持段：整只＝取到的背景色
CAMO_MIX_MIN = 0.0             # 换气到体色那一瞬
SALAMANDER_RGB = (232, 232, 244)
HUE_DEV_K = 0.6                # 原版体色色相偏差的 SCurve 参数（所有品种都是 0.6）
WHITE_PALE_SAT = 0.45          # 白蜥随机色版本：低饱和 + 高亮度 = 淡彩色
WHITE_PALE_LIGHT = 0.86
WHITE_PALE_LIGHT_DEV = 0.10


@dataclass
class LizardAnimIntent:
    """一只蜥蜴这一帧的「动画意图」：AI 只写意图，动画层只读意图。

    链路：AI（stage/目标/威胁）→ AnimIntent → 脊柱/头/下颚/步态 → 渲染。
    品种差异不进动画层（不再 if green… / if red…），动画只认
    「平静 / 警觉 / 威吓 / 追猎 / 冲锋 / 受伤 / 逃跑」这几档。
    """
    look_at: object = None      # 注视角用
    look_lift: float = 0.0      # 注视角竖向分量：+1 目标在上 / -1 在下
    alert: float = 0.0          # 警觉：头转得快
    aggression: float = 0.0     # 攻击性：张嘴前倾
    fear: float = 0.0           # 恐惧：压低身体
    jaw_open: float = 0.0       # 下颚目标开度
    body_compress: float = 0.0  # 压低身体
    body_raise: float = 0.0     # 支起上半身
    locomotion: str = "idle"    # idle / walk / run / lurk / carry
    turn: float = 0.0


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


def _scurve(x: float, k: float) -> float:
    """原版 Custom.SCurve（同 needleworm._scurve）。"""
    x = x * 2.0 - 1.0
    if x < 0.0:
        x = abs(1.0 + x)
        return k * x / (k - x + 1.0) * 0.5
    k = -1.0 - k
    return 0.5 + k * x / (k - x + 1.0) * 0.5


def _random_deviation(rng, k: float) -> float:
    """原版 Custom.RandomDeviation：SCurve 分布（两头重、中间轻），带随机符号。"""
    return _scurve(rng.random() * 0.5, k) * 2.0 * (1.0 if rng.random() < 0.5 else -1.0)


def _clamped_var(rng, base: float, max_dev: float, k: float) -> float:
    """原版 Custom.ClampedRandomVariation。"""
    return clampf(base + _random_deviation(rng, k) * max_dev, 0.0, 1.0)


def _wrapped_var(rng, base: float, max_dev: float, k: float) -> float:
    """原版 Custom.WrappedRandomVariation（色相环绕）。"""
    n = base + _random_deviation(rng, k) * max_dev + 1.0
    return n - math.floor(n)


class LizardBreed:
    """一种蜥蜴的静态定义；字段名对应游戏 LizardBreedParams / LizardBreeds。

    数值全部照抄 LizardBreeds.cs 中各品种的赋值（绿/粉/白优先校对过 wiki）。
    战斗相关：原版 CreatureTemplate.baseDamageResistance = toughness * 2，
    baseStunResistance = stunToughness，LizardState.health 初始恒为 1.0。
    """

    __slots__ = ("key", "name_zh", "name_en", "hue", "sat", "light", "plain_color",
                 "body_rgb", "head_rgb", "spikes",
                 "pale_random",
                 "head_graphics", "body_size_fac", "body_rad_fac", "body_length_fac",
                 "head_size", "tail_segs", "tail_len_fac", "limb_size", "limb_thickness",
                 "base_speed", "jaw_open_angle", "jaw_lower_fac", "jaw_apart",
                 "neck_stiffness", "body_stiffness", "tail_col_start", "tail_col_exp",
                 "bite_damage", "anchor_y", "head_hue_var", "head_light_var",
                 "light_dev_k",
                 "hide_eyes", "toughness", "stun_toughness", "bite_chance",
                 "attempt_bite_radius", "taming_difficulty", "head_shield_angle",
                 "danger", "visual_radius", "tongue", "tongue_range", "body_mass",
                 "flips_from_rock", "bite_damage_chance", "bite_dominance",
                 # 步态（LizardBreedParams 同名参数，原版腿 IK 的行为参数）
                 "step_length", "lift_feet", "feet_down", "limb_speed",
                 "limb_quickness", "smooth_legs", "leg_pair_disp", "walk_bob",
                 "lounge_tendency",
                 # 品种差异（见文件末 BREED_TRAITS）
                 "spawn_weight", "cosmetics", "can_climb", "camo", "charge_leap",
                 "climb_wall", "climb_pole", "wall_attach", "wall_detach", "wall_jump",
                 # DLC 品种（LizardBreeds.cs：SpitLizard / ZoopLizard / EelLizard）
                 "spit", "swim_speed", "leg_pairs", "lizard_spit_immune")

    def __init__(self, key, name_zh, name_en, hue, light, head_graphics, *,
                 size=1.0, body_rad_fac=1.0, body_length_fac=1.0, head_size=1.0,
                 tail_segs=5, tail_len_fac=1.2, limb_size=1.0, limb_thickness=1.0,
                 base_speed=4.0, jaw_open_angle=90.0, jaw_lower_fac=2.0 / 3.0,
                 jaw_apart=23.0, neck_stiffness=0.2, body_stiffness=0.2,
                 tail_col_start=0.3, tail_col_exp=2.0, bite_damage=1.0,
                 sat=1.0, plain_color=None, anchor_y=0.7,
                 pale_random=False,
                 hue_var=0.10, light_var=0.15, light_dev_k=0.1,
                 hide_eyes=False, spikes=None,
                 toughness=1.0, stun_toughness=1.0, bite_chance=0.5,
                 bite_damage_chance=1.0 / 3.0,
                 attempt_bite_radius=80.0, taming_difficulty=1.0,
                 head_shield_angle=100.0, danger=0.45, visual_radius=900.0,
                 tongue=False, tongue_range=0.0, body_mass=2.1,
                 bite_dominance=0.5,
                 flips_from_rock=True,
                 step_length=0.5, lift_feet=0.3, feet_down=0.5, limb_speed=5.0,
                 limb_quickness=0.5, smooth_legs=True, leg_pair_disp=0.2,
                 walk_bob=4.0, lounge_tendency=0.05,
                 spit=False, swim_speed=0.0, lizard_spit_immune=False,
                 leg_pairs=None):
        self.key = key
        self.name_zh = name_zh
        self.name_en = name_en
        self.hue = hue
        self.sat = sat
        self.light = light
        self.plain_color = plain_color      # 白/黑等不走 HSL 的品种
        self.pale_random = pale_random      # 白蜥随机色变体：色相每次出生重掷
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
        self.light_dev_k = light_dev_k
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
        self.bite_dominance = bite_dominance      # 原版 biteDominance：同族嘶咬时的支配度
        self.flips_from_rock = flips_from_rock   # 原版红蜥不吃石头转身
        # 步态：照抄 LizardBreedParams（步幅 / 抬脚 / 落脚 / 腿速 / 腿灵巧度 /
        # 腿部是否平滑 / 前后腿错位 / 走动上下颠 / 冲刺倾向）
        self.step_length = step_length
        self.lift_feet = lift_feet
        self.feet_down = feet_down
        self.limb_speed = limb_speed
        self.limb_quickness = limb_quickness
        self.smooth_legs = smooth_legs
        self.leg_pair_disp = leg_pair_disp
        self.walk_bob = walk_bob
        self.lounge_tendency = lounge_tendency
        # 品种差异：默认值在这里，具体每个品种在 BREED_TRAITS 里覆写
        self.spawn_weight = 1.0
        self.cosmetics = ()            # 品种花纹（BREED_COSMETICS，见文件末）
        self.climb_wall = False        # 必须由 BREED_TRAITS 显式开启
        self.climb_pole = False
        self.wall_attach = True
        self.wall_detach = True
        self.wall_jump = False
        self.can_climb = True          # = climb_wall or climb_pole（兼容旧调用点）
        self.camo = False
        self.charge_leap = False
        # DLC：喷唾液 / 免疫爆炸 / 水生速度 / 腿的挂点（(躯干节下标, 是否后腿)）
        self.spit = bool(spit)
        self.swim_speed = float(swim_speed)
        self.lizard_spit_immune = bool(lizard_spit_immune)
        self.leg_pairs = tuple(leg_pairs) if leg_pairs else (
            (0, False), (0, False), (2, True), (2, True))
        # 体/头配色：白蜥全身纯白、头按原版压黑；蝾螈灰白；黑蜥整体近黑；其余体黑头染品种色
        if plain_color == WHITE_RGB:
            # 白蜥：躯干纯白，头走「黑↔白呼吸闪烁」（原版 HeadColor1=白 / HeadColor2=黑），
            # 因此这里只钉体色，头交给 head_color 的呼吸分支。
            # pale_random 变体则整只按出生随机淡彩色（见 color/body_color）。
            self.body_rgb, self.head_rgb = WHITE_RGB, None
        elif key in ("salamander", "black"):
            self.body_rgb = self.head_rgb = (SALAMANDER_RGB if key == "salamander"
                                            else BLACK_RGB)
        else:
            self.body_rgb, self.head_rgb = BLACK_RGB, None

    @property
    def camo_fac(self) -> float:
        """蛞蝓猫注意它的距离倍数：有环境伪装（白蜥）的猫更难被发现。"""
        return CAMO_NOTICE_FAC if self.camo else 1.0

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

    @property
    def vision(self) -> tuple[float, float]:
        """原版 (perfectVisionAngle, periferalVisionAngle)：Lerp(1,-1,t) 展开。"""
        tp, tq = LIZ_VISION.get(self.key, (0.0, 7.0 / 12.0))
        return 1.0 - 2.0 * tp, 1.0 - 2.0 * tq

    def color(self, rng) -> tuple[int, int, int]:
        """出生时随机化个体色：逐字照抄 Lizard.cctor 里 effectColor 的赋值。

        原版每个品种都是 `Custom.HSL2RGB(WrappedRandomVariation(hue, hueDev, 0.6),
        sat, ClampedRandomVariation(light, lightDev, lightK))`，白/黑蜥走
        `lizardParams.standardColor`（纯色分支，见 plain_color）。
        SCurve 偏差是两头重的分布，所以同种蜥蜴既有接近基准色的个体，
        也有明显偏色/偏亮的个体 —— 这是原版体色「鲜艳且多样」的来源。
        """
        if self.plain_color is not None:
            if not self.pale_random:
                return self.plain_color
            # 白蜥随机色版：整圈随机色相 + 低饱和高亮度（淡彩），个体差异靠 light 抖动
            return _hsl2rgb(rng.random(),
                            WHITE_PALE_SAT,
                            _clamped_var(rng, WHITE_PALE_LIGHT, WHITE_PALE_LIGHT_DEV,
                                         self.light_dev_k))
        h = _wrapped_var(rng, self.hue, self.head_hue_var, HUE_DEV_K)
        l = _clamped_var(rng, self.light, self.head_light_var, self.light_dev_k)
        return _hsl2rgb(h, self.sat, l)

    def tail_tint(self, rng, color):
        """尾梢渐变（游戏 iVars.tailColor，LizardGraphics.cs:718-721）。

        原版是 `tailColor = 0; if (type != WhiteLizard && Random.value > 0.5)
        tailColor = Random.value;` —— **只有白蜥恒无**（黑蜥也有，只是它的
        effectColor 本来就深，看不出渐变），数值就是那次掷点本身。
        BodyColor 里 `f2 = pow(曲线) * tailColor`，tailColor 直接是渐变强度，
        不做 0.35+0.65 的拉伸。蝾螈虽然掷得出，但 BodyColor 走 SalamanderColor
        分支，尾巴照样看不到渐变。
        """
        if self.key == "white":
            return None
        if rng.random() <= 0.5:
            return None
        return (color, rng.random())


# 九种基础蜥蜴：数值逐项照抄 LizardBreeds.cs（PinkLizard/GreenLizard/BlueLizard/
# YellowLizard/WhiteLizard/RedLizard/BlackLizard/Salamander/CyanLizard）。
BREEDS = (
    LizardBreed("pink", "粉蜥", "Pink lizard", 0.87, 0.50, (0, 0, 0, 0, 0),
                size=1.00, base_speed=4.1, tail_segs=5, tail_len_fac=1.2,
                bite_damage=1.0, bite_damage_chance=1.0 / 3.0, bite_chance=0.5, attempt_bite_radius=80.0,
                taming_difficulty=1.0, danger=0.45, visual_radius=900.0,
                body_mass=2.1, spikes=None),
    LizardBreed("green", "绿蜥", "Green lizard", 0.32, 0.50, (1, 1, 1, 1, 1),
                size=1.20, base_speed=6.7, tail_segs=7, tail_len_fac=0.9, limb_size=1.4,
                jaw_open_angle=50.0, jaw_lower_fac=0.5, jaw_apart=14.0, neck_stiffness=1.0,
                body_stiffness=0.5, tail_col_start=0.05, tail_col_exp=4.0,
                bite_damage=2.0, bite_damage_chance=0.5, bite_chance=1.0 / 3.0, attempt_bite_radius=100.0,
                anchor_y=0.55,
                toughness=2.5, stun_toughness=2.5, taming_difficulty=0.8,
                danger=0.45, visual_radius=850.0, body_mass=7.5, spikes=(3, 2, 0.8),
                step_length=0.9, lift_feet=0.5, feet_down=1.0, limb_speed=3.0,
                limb_quickness=0.3, smooth_legs=False, leg_pair_disp=1.0,
                walk_bob=4.0, lounge_tendency=1.0),
    LizardBreed("blue", "蓝蜥", "Blue lizard", 0.57, 0.50, (0, 0, 0, 0, 0),
                size=0.90, head_size=0.9, base_speed=3.2, tail_segs=4, tail_len_fac=1.0,
                limb_size=0.9, jaw_open_angle=105.0, jaw_lower_fac=0.55, jaw_apart=20.0,
                neck_stiffness=0.0, body_stiffness=0.0, tail_col_start=0.1, tail_col_exp=1.2,
                bite_damage=0.7, bite_damage_chance=0.2, bite_chance=0.4, attempt_bite_radius=90.0,
                toughness=0.5, stun_toughness=0.5, taming_difficulty=1.1,
                danger=0.35, visual_radius=950.0, body_mass=1.4,
                tongue=True, tongue_range=140.0, hue_var=0.08,
                step_length=0.4, lift_feet=0.0, feet_down=0.0, limb_speed=6.0,
                limb_quickness=0.6, leg_pair_disp=0.0, walk_bob=0.4,
                lounge_tendency=0.01),
    LizardBreed("yellow", "黄蜥", "Yellow lizard", 0.10, 0.50, (0, 0, 0, 0, 0),
                size=0.93, base_speed=4.1, tail_segs=5, tail_len_fac=1.2,
                jaw_open_angle=90.0, jaw_apart=23.0,
                body_stiffness=0.2, tail_col_start=0.3, tail_col_exp=2.0,
                bite_damage=0.8, bite_damage_chance=0.25, bite_chance=1.0 / 6.0, attempt_bite_radius=40.0,
                toughness=0.8, stun_toughness=0.8, taming_difficulty=3.0,
                danger=0.4, visual_radius=900.0, body_mass=1.7, hue_var=0.05),
    LizardBreed("white", "白蜥", "White lizard", 0.0, 1.0, (0, 0, 0, 0, 3),
                pale_random=True,
                size=1.00, base_speed=3.8, tail_segs=5, tail_len_fac=1.2,
                jaw_open_angle=110.0, jaw_lower_fac=0.5, neck_stiffness=0.05,
                body_stiffness=0.15, tail_col_start=0.1, tail_col_exp=1.2,
                bite_damage=1.0, bite_damage_chance=0.2857143, bite_chance=0.5, attempt_bite_radius=85.0,
                toughness=0.9, stun_toughness=0.9, taming_difficulty=3.0,
                danger=0.5, visual_radius=1300.0, body_mass=2.1,
                sat=0.0, plain_color=(255, 255, 255),
                tongue=True, tongue_range=440.0,
                step_length=0.6, lift_feet=0.2, feet_down=0.05, limb_speed=8.0,
                limb_quickness=0.8, smooth_legs=False, leg_pair_disp=0.0,
                walk_bob=0.8),
    LizardBreed("red", "红蜥", "Red lizard", 0.0025, 0.50, (0, 0, 0, 0, 0),
                size=1.20, head_size=1.2, base_speed=5.0, tail_segs=11, tail_len_fac=1.9,
                limb_size=1.5, jaw_open_angle=140.0, body_stiffness=0.3,
                bite_damage=4.0, bite_damage_chance=1.0, bite_chance=1.0, attempt_bite_radius=120.0,
                toughness=3.0, stun_toughness=3.0, taming_difficulty=7.0,
                danger=0.8, visual_radius=2300.0, body_mass=3.1,
                tongue=True, tongue_range=350.0, flips_from_rock=False,
                hue_var=0.02, spikes=(0, 0, 0.7),
                step_length=0.8, lift_feet=0.3, limb_speed=9.0, limb_quickness=0.8,
                walk_bob=3.0),
    LizardBreed("black", "黑蜥", "Black lizard", 0.0, 0.10, (0, 0, 0, 0, 0),
                size=0.90, base_speed=3.9, tail_segs=6, tail_len_fac=1.2, limb_size=1.1,
                body_stiffness=0.25, bite_damage=1.0, bite_damage_chance=5.0 / 14.0, bite_chance=1.0 / 3.0,
                attempt_bite_radius=70.0, toughness=1.0, stun_toughness=1.0,
                taming_difficulty=4.0, danger=0.45, visual_radius=0.0, body_mass=2.0,
                sat=0.0, plain_color=(26, 26, 26),
                hue_var=0.0, light_var=0.0, hide_eyes=True, spikes=(0, 0, 0.7),
                step_length=0.6, lift_feet=0.25, limb_quickness=0.6, walk_bob=3.0),
    LizardBreed("salamander", "蝾螈", "Salamander", 0.90, 0.40, (2, 2, 2, 2, 2),
                size=0.90, head_size=0.9, base_speed=3.1, tail_segs=5, tail_len_fac=1.2,
                limb_size=0.65, jaw_apart=15.0, bite_damage=0.9, bite_damage_chance=1.0 / 3.0,
                bite_chance=1.0 / 3.0, attempt_bite_radius=70.0,
                toughness=1.0, stun_toughness=1.0, taming_difficulty=3.5,
                head_shield_angle=70.0, danger=0.4, visual_radius=960.0, body_mass=2.1,
                tongue=True, tongue_range=150.0, hue_var=0.15, light_dev_k=0.2,
                smooth_legs=False),
    LizardBreed("cyan", "青蜥", "Cyan lizard", 0.49, 0.50, (0, 0, 0, 0, 0),
                size=0.65, base_speed=3.0, tail_segs=5, tail_len_fac=1.44, limb_size=1.0,
                limb_thickness=0.8, jaw_open_angle=80.0, jaw_apart=17.0, body_stiffness=0.8,
                bite_damage=1.0, bite_damage_chance=0.25, bite_chance=0.5, attempt_bite_radius=80.0,
                toughness=0.35, stun_toughness=50.0, taming_difficulty=1.0,
                head_shield_angle=70.0, danger=0.25, visual_radius=990.0, body_mass=0.8,
                tongue=True, tongue_range=160.0, hue_var=0.04,
                step_length=0.4, lift_feet=0.0, feet_down=0.0, limb_speed=6.0,
                limb_quickness=0.6, leg_pair_disp=0.0, walk_bob=2.0,
                lounge_tendency=1.0 / 30.0),
    LizardBreed("caramel", "焦糖蜥", "Caramel lizard", 0.10, 0.55, (1, 1, 1, 1, 1),
                size=1.75, base_speed=0.65, tail_segs=4, tail_len_fac=1.2,
                limb_size=1.1, limb_thickness=1.5,
                jaw_open_angle=90.0, jaw_apart=23.0, head_size=1.2,
                bite_damage=1.2, bite_damage_chance=0.5, bite_chance=0.46511626,
                attempt_bite_radius=90.0, head_shield_angle=100.0,
                toughness=2.5, stun_toughness=2.5, taming_difficulty=0.3,
                danger=0.8, visual_radius=2300.0, body_mass=4.2,
                walk_bob=4.0, flips_from_rock=False,
                sat=0.55, hue_var=0.03, light_var=0.2,
                spit=True, lizard_spit_immune=True,
                leg_pairs=((0, False), (0, False), (1, True), (1, True),
                           (2, True), (2, True))),
    LizardBreed("zoop", "草莓蜥", "Strawberry lizard", 0.95, 0.73, (0, 0, 0, 0, 0),
                size=0.74, base_speed=5.1, tail_segs=4, tail_len_fac=1.8,
                limb_size=0.9, limb_speed=9.0, limb_quickness=0.5,
                lift_feet=0.6, feet_down=0.2, leg_pair_disp=0.8, walk_bob=9.0,
                jaw_open_angle=80.0, jaw_apart=23.0, head_size=0.9,
                bite_damage=0.18, bite_damage_chance=0.65, bite_chance=0.31,
                attempt_bite_radius=80.0, toughness=0.7, stun_toughness=0.7,
                taming_difficulty=2.0, danger=0.8, visual_radius=1400.0,
                body_mass=0.9, tongue=True, tongue_range=440.0,
                sat=0.55, hue_var=0.02, light_var=0.05),
    LizardBreed("eel", "鳗鱼蜥", "Eel lizard", 0.42, 0.40, (2, 2, 2, 2, 2),
                size=0.95, head_size=1.0, base_speed=3.75, tail_segs=16,
                tail_len_fac=1.1, tail_col_start=0.9,
                limb_size=0.75, limb_speed=9.0, limb_quickness=1.0,
                lift_feet=0.0, walk_bob=0.4, neck_stiffness=0.9,
                jaw_open_angle=110.0, jaw_apart=15.0,
                bite_damage=0.2, bite_damage_chance=1.0, bite_chance=14.0 / 15.0,
                attempt_bite_radius=800.0, body_rad_fac=0.5,
                toughness=0.8, stun_toughness=0.8, taming_difficulty=3.0,
                danger=0.45, visual_radius=990.0, body_mass=2.4,
                sat=0.9, swim_speed=8.0,
                leg_pairs=((0, False), (0, False))),
)
BREED_BY_KEY = {b.key: b for b in BREEDS}

# ── 品种差异（反编译 LizardBreeds.cs + wiki）──────────────────────────────
# spawn_weight = 自然生成权重。原版由各区域的 spawn 表决定（绿/粉/蓝最常见，
#                红/青/白/黄/蝾螈稀有）；桌宠没有区域表，折算成这张固定权重表。
# can_climb    = 「会不会爬」的合并口径（climb_wall or climb_pole），旧调用点还在用。
#                LizardBreeds.cs GreenLizard 段没登记 Climb/Wall → 绿蜥不能爬。
# climb_wall   = 能不能攀爬背景墙。反编译 LizardBreedParams.WallClimber
#                （LizardBreedParams.cs:196-210）：只有 BlueLizard / WhiteLizard /
#                DlcEelLizard 为 true。
# climb_pole   = 能不能沿竖杆上下（AItile.Accessibility.Climb，原版竖杆＝beam）。
# wall_attach  = 能不能主动贴到墙面上；wall_detach = 能不能主动脱墙。
# wall_jump    = 能不能从墙面蹬跳出去（青蜥的蓄力弹射系，见 LizardAI 的 jump 逻辑）。
# camo         = 环境伪装。白蜥（wiki：环境伪装 + 长舌伏击）：蛞蝓猫更晚注意到它。
# charge_leap  = 蓄力弹射。青蜥（wiki：爬墙 + 蓄力弹射跳跃）：扑击瞬间更快更猛。
# cosmetics    = LizardCosmetics/* 的品种花纹（反编译 LizardGraphics.cs:440-620）。
#                全部落在 LizardScaleA<g> 一套贴图上，只是族的摆放/数量不同：
#                shoulder=LongShoulderScales/WingScales、head=LongHeadScales、
#                whisker=Whiskers（黑蜥固有）、antenna=Antennae（黄蜥固有）、
#                gill=AxolotlGills（蝾螈/鳗鱼蜥）、fin=TailFin（尾鳍）。
BREED_TRAITS = {
    # climb_wall 只给 WallClimber（反编译 LizardBreedParams.cs:196-210）：
    # 蓝 / 白 / 鳗鱼（DLC）。其余品种「会爬杆但不攀爬背景墙」。
    # 明确能力表：杆攀爬仅允许原版可爬杆品种；背景墙仅 WallClimber。
    "pink":       dict(spawn_weight=1.00, climb_wall=False, climb_pole=True),
    "green":      dict(spawn_weight=0.90, climb_wall=False, climb_pole=False),
    "blue":       dict(spawn_weight=0.90, climb_wall=True, climb_pole=True),
    "yellow":     dict(spawn_weight=0.35, climb_wall=False, climb_pole=True),
    "white":      dict(spawn_weight=0.30, climb_wall=True, climb_pole=True, camo=True),
    "red":        dict(spawn_weight=0.02, climb_wall=False, climb_pole=True),
    "black":      dict(spawn_weight=0.30, climb_wall=False, climb_pole=True),
    "salamander": dict(spawn_weight=0.25, climb_wall=False, climb_pole=True),
    "cyan":       dict(spawn_weight=0.25, climb_wall=False, climb_pole=True,
                       wall_jump=True, charge_leap=True),
    # DLC《倾盆大雨》
    "caramel":    dict(spawn_weight=0.03, climb_wall=False, climb_pole=False),
    "zoop":       dict(spawn_weight=0.05, climb_wall=False, climb_pole=True),
    "eel":        dict(spawn_weight=0.06, climb_wall=True, climb_pole=True)
}
for _b in BREEDS:
    _t = BREED_TRAITS.get(_b.key, {})
    _b.spawn_weight = float(_t.get("spawn_weight", 1.0))
    _b.climb_wall = bool(_t.get("climb_wall", True))
    _b.climb_pole = bool(_t.get("climb_pole", True))
    _b.wall_jump = bool(_t.get("wall_jump", False))
    _b.wall_attach = bool(_t.get("wall_attach", _b.climb_wall))
    _b.wall_detach = bool(_t.get("wall_detach", True))
    _b.can_climb = bool(_b.climb_wall or _b.climb_pole)
    _b.camo = bool(_t.get("camo", False))
    _b.charge_leap = bool(_t.get("charge_leap", False))

_WEIGHT_TOTAL = sum(b.spawn_weight for b in BREEDS)


def pick_breed(index: int):
    """按 spawn_weight 加权抽一个品种（真随机顺序，不再按次序轮换）。

    index 用 splitmix64 风格的整数散列打散：连续序号之间没有相关性（直接拿
    序号喂 random.Random 的话，梅森旋转的头几个输出会明显聚簇），但同一个
    index 永远抽出同一个品种 —— 渲染黄金帧与测试仍可复现。
    """
    x = (int(index) * 0x9E3779B97F4A7C15 + 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    x ^= x >> 31
    r = (x >> 11) / float(1 << 53) * _WEIGHT_TOTAL
    for b in BREEDS:
        r -= b.spawn_weight
        if r <= 0.0:
            return b
    return BREEDS[-1]


class _Seg:
    """链体节（原版 BodyChunk）：位置 + 速度 + 半径 + 到前一节的固定距离。"""

    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "rad", "dist", "stiff", "tail")

    def __init__(self, x, y, rad, dist, stiff, tail):
        self.x = self.lx = float(x)
        self.y = self.ly = float(y)
        self.vx = self.vy = 0.0
        self.rad = float(rad)
        self.dist = float(dist)
        self.stiff = stiff
        self.tail = tail


class _Leg:
    """一条腿：脚点质点 + 速度 + 绝对猎点（原版 LizardLimb / Limb 的 2D 简化）。"""

    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "abs_x", "abs_y",
                 "reaching", "snap", "grip", "planted", "plant_dx", "plant_dy",
                 "flip", "disabled", "back", "near", "pair")

    def __init__(self, x, y, back: bool, near: bool, pair: int = None):
        self.x = self.lx = float(x)
        self.y = self.ly = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.abs_x = float(x)          # absoluteHuntPos
        self.abs_y = float(y)
        self.reaching = False          # reachingForTerrain
        self.snap = False              # reachedSnapPosition
        self.grip = 0                  # gripCounter
        self.planted = False            # 已真正抓住地形
        self.plant_dx = 0.0             # 种植时：脚相对髋的偏移
        self.plant_dy = 0.0
        self.flip = 0.0                # LizardLimb.flip（初值 0，逐帧 Lerp 到 ±1）
        self.disabled = False          # currentlyDisabled（眩晕/游泳时挂起）
        self.back = back
        self.near = near
        # 腿根挂在哪一节躯干（原版 LizardLimb 挂 bodyChunk）：0 前 / 1 中 / 2 后
        self.pair = (2 if back else 0) if pair is None else int(pair)


class Lizard:
    food_class = "none"      # 不是食物：尸体算无用尸体（会被猫拖出屏幕清场）
    """一只蜥蜴：头为驱动质点，躯干/尾逐节跟随；巡走 → 警觉 → 扑咬。"""

    collision_layer = 0                 # 不参与 chunk 互推，交互全部走 AI

    __slots__ = ("breed", "color", "tail_edge", "tail_amt", "rng", "seed", "id",
                 "body_rgb",
                 "x", "y", "vx", "vy", "last_x", "last_y", "head_rad", "head_conn",
                 "body_rad", "seg", "legs", "state", "facing", "look_at",
                 "limbs_aim",
                 "head_angle", "last_head_angle", "jaw", "last_jaw",
                 "target", "target_obj", "bite_event", "bite_hold", "bite_cd", "_tgt_hold",
                 "walk_phase", "idle_timer", "goal_x", "hop_cd", "blink", "last_blink",
                 "chain_dir", "_ax_c",
                 "held_by_hand", "water_y", "room_gravity", "_contact_floor",
                 "dead", "spacing", "spikes", "cosmetics", "cosmetic_pts", "like", "tamed", "friend_id",
                 "climb_x", "climb_dir", "climb_surfaces", "hauler",
                 "max_health", "health", "stun", "hurt_flash", "dead_t",
                 "rock_push", "rock_push_dir",
                 "hauled", "haul_thrown", "is_meat", "wall_dir",
                 "anger", "anger_obj", "submitted_to",
                 "threat", "threat_obj", "threat_t",
                 "noise_x", "noise_y", "noise_t", "lurk",
                 "bob", "bob_front", "bob_hind",
                 "carry_obj", "carry_body", "carry_corner", "carry_den", "sprint",
                 "guard_obj", "guard_t", "obs", "mem", "prey", "plan", "soc",
                 "alert", "warning_t", "stage", "stage_obj", "peers",
                 "_blockers", "_tick",
                 "depth", "last_depth", "head_depth", "last_head_depth", "turn_lift",
                 "head_driven", "anim", "_last_vx",
                 "depth_in", "rel",
                 "camo_target", "camo_color", "camo_mix",
                 "climb_kind", "climb_attached", "climb_side",
                 "climb_top", "climb_bot", "caps", "terrain", "_ground")

    def __init__(self, x: float, y: float, breed: LizardBreed | None = None,
                 seed: int = 0, id: int = 0):
        self.rng = _random.Random(seed * 7919 + 13)
        self.breed = breed or BREEDS[0]
        self.seed = int(seed)
        self.id = int(id)
        rng = self.rng
        self.color = self.breed.color(rng)
        self.body_rgb = self.color if self.breed.pale_random else None
        tint = self.breed.tail_tint(rng, self.color)
        self.tail_edge = tint[0] if tint else None
        self.tail_amt = tint[1] if tint else 0.0
        self.like = 0.0                  # 原版 SocialMemory.like
        self.tamed = False
        self.friend_id = None            # 驯服它的猫（PetUnit.id）

        b = self.breed
        self.head_rad = 6.0 * b.head_size * BODY_SCALE
        self.head_conn = 12.0 * b.head_size * BODY_SCALE   # 原版 head 目标点 = 体节0 + 12*headSize
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
        self.is_meat = False     # 蜥蜴不是食物：尸体算无用尸体（会被猫拖出屏幕清场）
        self.hauled = False      # 正被蛞蝓猫拖着走：位置每 tick 由猫写死
        self.haul_thrown = False  # 被猫拖到屏幕边丢出去：过边即真删（window._cull_flung_corpses）
        self.wall_dir = 0        # 贴在左右墙时记墙侧（窗口边缘＝墙）
        # 原版 AgressionTracker：对 AggressiveRival 对象的怒气（0..1，涨落各 0.001/tick）
        self.anger = 0.0
        self.anger_obj = None
        self.submitted_to = None     # 原版 RecieveCommunication：认怂对象 id
        # 原版 ThreatTracker：对 Afraid 对象的逃跑
        self.threat = None
        self.threat_obj = None
        self.threat_t = 0
        # 原版 NoiseTracker：最后听到的响声位置
        self.noise_x = 0.0
        self.noise_y = 0.0
        self.noise_t = 0
        self.lurk = False        # 原版 LurkTracker：伏击待机中
        # 走动上下颠（原版 drawPositions[i].y += frontBob/hindBob * walkBob）
        self.bob = [0.0, 0.0, 0.0]
        self.bob_front = 0.0
        self.bob_hind = 0.0
        # 白蜥迷彩：camo_target = 最近一次采到的周边环境主色；camo_color = 平滑后的
        # 整只体色（每 tick 慢速渐变到 target）。None = 还没采到 / 采不到（保持白色）。
        self.camo_target = None
        self.camo_color = None
        self.camo_mix = 0.0      # 体色在白色 ↔ 迷彩色之间的呼吸比例
        # 叼着死猫/昏迷猫回巢穴：carry_obj 是那只猫（PetUnit），carry_body 是
        # 它的身体（被钉住跟着嘴走）。carry_den 是**开始搬运时锁定的那个巢穴**
        # （原版 ReturnPrey 的 den：定了就不换），carry_corner 只是它的左右符号。
        self.carry_obj = None
        self.carry_body = None
        self.carry_den = None
        self.carry_corner = 0
        # ── AI 分层（world/lizard_ai.py）──
        self.obs = {"cats": (), "prey": (), "threats": (), "rivals": (), "pack": ()}
        self.mem = Memory()          # 「我上次在哪看见它」（置信度记忆）
        self.prey = PreyTracker()    # 「这只是我的猎物」（咬倒 → 归我 → 回巢穴）
        self.plan = None             # 这一帧的接近路线（ApproachPlan）
        self.soc = SocialMemory()    # 同族关系：支配度 / 认怂 / 敬意
        self.rel = Relations(self)   # 动态关系：好感 / 恐惧 / 记恨（事件总线记账）
        self.soc.dominance = self.dominance
        self.alert = None            # 黄蜥的猎物情报（PackTracker）
        self.warning_t = 0           # 举头警告剩余 tick
        self.stage = ""              # 当前行为（原版 Behavior.* 的名字）
        self.peers = ()              # 同场其它蜥蜴（认猎物归属用）
        self._blockers = ()          # 视线遮挡物：(杆子线段, 大生物圆)
        self._tick = 0
        self.guard_obj = None        # 刚送回巢穴的猎物（守一会儿）
        self.guard_t = 0
        # loungeTendency：锁定新目标时掷一次（绿蜥 1.0 必全速冲，蓝蜥 0.01 慢慢蹭）
        self.sprint = 0.55

        # 链体：躯干 N_BODY 节 + 尾若干节；dist 为到前一节的固定距离
        n_tail = max(2, min(int(b.tail_segs), MAX_TAIL_SEGS))
        segs = []
        prev_x, prev_y, prev_d = self.x, self.y, self.head_conn
        for i in range(N_BODY):
            segs.append(_Seg(prev_x - prev_d, prev_y, self.body_rad, prev_d, SEG_STIFF_BODY, False))
            prev_x, prev_y, prev_d = segs[-1].x, segs[-1].y, self.spacing
        for j in range(n_tail):
            rad = 8.0 * b.body_size_fac * (n_tail - j) / float(n_tail) * BODY_SCALE
            conn = (((16.0 if j == 0 else 8.0) * BODY_SCALE + rad) / 2.0
                    * b.tail_len_fac * TAIL_LEN_BOOST)
            segs.append(_Seg(prev_x - conn, prev_y, rad, conn, SEG_STIFF_TAIL, True))
            prev_x, prev_y, prev_d = segs[-1].x, segs[-1].y, conn
        self.seg = segs

        # 四条腿：前对挂第 0 节、后对挂第 2 节；每条腿分远近（绘制层不同）
        # 腿数/挂点按品种：四足是默认；鳗鱼蜥两条腿、焦糖蜥六条腿
        # （LizardGraphics.cs:371 `new LizardLimb[Caramel ? 6 : 4]`）
        self.legs = []
        for li, (pair_i, is_back) in enumerate(b.leg_pairs):
            ps = self.seg[pair_i] if pair_i < len(self.seg) else self.seg[-1]
            self.legs.append(_Leg(ps.x, ps.y + self.body_rad * LEG_SIDE_FAC,
                                  is_back, bool(li % 2), pair_i))
        # 原版 limbsAimFor：蜥蜴行进目标点，腿朝它伸。宠物里取躯干前方一点。
        self.limbs_aim = (self.x, self.y)

        # 花纹（LizardCosmetics/*）：逐条照抄 LizardGraphics.cs:439-640 的生成链，
        # 见 world/lizard_cos.py。背刺（SpineSpikes）也在这条链里，不再是单独的
        # 「品种概率」表。走独立随机流，免得扰动 this.rng（步态/咬合/眨眼都吃这条
        # 流，加一次掷点会让同一只蜥蜴的整条行为序列错位）。
        self.spikes = None
        crng = _random.Random(self.seed * 104729 + 7)
        body_len = self.head_conn * 0.5 + sum(sg.dist for sg in segs if not sg.tail)
        tail_len = sum(sg.dist for sg in segs if sg.tail)
        total_len = body_len + tail_len
        self.cosmetics = lizard_cos.roll_cosmetics(
            crng, b.key, total_len, (body_len / total_len) if total_len > 0 else 0.5)
        # 花纹物理状态（原版 LizardScale 摆锤）：每条实例 [x, y, vx, vy, lx, ly]；
        # None = 该族不用物理（背刺/条纹/翅鳞等是刚性贴图）。
        self.cosmetic_pts = [
            ([[0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for _ in c.insts]
             if c.kind in lizard_cos.PHYS_KINDS else None)
            for c in self.cosmetics]

        # 攀爬（原版 LizardPather 的 Climb/Wall tile）：贴在竖杆或背景墙竖边上。
        # climb_x/climb_dir = 这一 tick 的攀爬意图；climb_attached = 是否已经真的
        # 贴到墙面上（没贴上就先走过去 —— 原版 Floor→Wall 那条 MovementConnection）。
        self.climb_x = None           # 要抓的那条竖线的 x；None＝不去爬
        self.climb_dir = 0            # +1 向上、-1 向下
        self.climb_kind = None        # "wall" / "pole"
        self.climb_attached = False   # 已经附着在墙面上（横向用弹簧吸住）
        self.climb_side = 0           # 贴在墙的哪一侧（-1 左 / +1 右）；杆为 0
        self.climb_top = None         # 当前这条线的上下端（到头上/底下就脱墙）
        self.climb_bot = None
        self.climb_surfaces = ()      # 这一帧可攀爬的面 [(x, y_top, y_bot, kind)]
        # 地形能力表（原版 CreatureTemplate / LizardBreedParams）：
        # 地形图全场共用，但「这张图里我能用哪些连接」逐品种过滤。
        self.caps = Caps(
            walk=True, jump=True,
            wall_climb=bool(b.climb_wall and b.wall_attach),
            pole_climb=bool(b.climb_pole),
            wall_jump=bool(getattr(b, "wall_jump", False)),
            climb_reach=CLIMB_WALK_R)
        self.terrain = None           # 这一帧的世界地形查询（items 每 tick 换一份）
        self._ground = float(y)       # 这一 tick 脚下踩的那一层（屏幕地板 / 窗台 / 横杆）
        # 清场认领：哪只猫认领了这具尸体（尸体搬运只允许一只猫执行）
        self.hauler = None

        self.state = ItemState.FREE
        self.facing = 1
        self.chain_dir = 1.0
        self._ax_c = 1.0                    # 锚点方向（chain_dir 的低通值，见 _step_chain）
        # 原版 LizardGraphics 的 depthRotation / headDepthRotation（决定头取哪一行贴图）
        self.depth = self.last_depth = -1.0          # 原版初值：朝右 = -1
        self.head_depth = self.last_head_depth = -1.0
        self.depth_in = -1.0                         # 原版 num8（腿推导的 depth 输入）
        self.turn_lift = 0.0
        self.head_driven = False      # AI 是否已经驱动过 head_angle（首帧渲染兜底用）
        self.anim = LizardAnimIntent()
        self._last_vx = 0.0
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

    @property
    def dominance(self) -> float:
        """支配度：原版 biteDominance 再按体型放大（同族争夺 / 认怂用）。"""
        return clampf(self.breed.bite_dominance * (0.75 + 0.25 * self.breed.body_size_fac),
                      0.0, 1.0)

    @property
    def haul_chunk_mass(self):
        """被拖拽时「被抓那一节」的质量：Lizard.cs bodyChunks[0] = bodyMass / 3。"""
        return self.breed.body_mass / 3.0

    @property
    def haul_mass(self):
        """拖拽质量判据用的总质量：原版 grabbed.TotalMass（蜥蜴三节合计 = bodyMass）。"""
        return self.breed.body_mass

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

    def camo_tick(self, win, tick: int) -> None:
        """白蜥：低频采一次「自己身后」的**背景**主色，整只长时间保持它。

        采样在 `platform.bgcolor` 里会把「我们自己画的前景」（猫 / 生物 / 物品 /
        HUD）挖掉，只留桌面背景 —— 别的猫从旁边走过不会带着白蜥一起变色。
        每 `CAMO_SAMPLE_TICKS` 按 `self.id` 错开采样点，半径随身体大小放大；
        采样失败就保持上次的颜色（一直失败则保持白色）。只有 `breed.camo`
        的品种（白蜥）跑。
        """
        if not getattr(self.breed, "camo", False):
            return
        if tick % CAMO_SAMPLE_TICKS == self.id % CAMO_SAMPLE_TICKS:
            from ..platform.bgcolor import dominant_around
            rx = max(self.body_rad * 4.5, CAMO_SAMPLE_RADIUS_X)
            ry = max(self.body_rad * 3.5, CAMO_SAMPLE_RADIUS_Y)
            col = dominant_around(win, self.x, self.y, rx, ry)
            if col is not None:
                self.camo_target = col
        if self.camo_target is not None:
            if self.camo_color is None:
                self.camo_color = self.camo_target
            else:
                t = CAMO_COLOR_RATE
                self.camo_color = (
                    int(self.camo_color[0] + (self.camo_target[0] - self.camo_color[0]) * t),
                    int(self.camo_color[1] + (self.camo_target[1] - self.camo_color[1]) * t),
                    int(self.camo_color[2] + (self.camo_target[2] - self.camo_color[2]) * t))
        # 呼吸：长时间停在取色，周期末尾才短暂退回体色再变回来（每只错开相位）
        ph = (tick + int(self.seed * 0.13 * CAMO_BREATH_TICKS)) % CAMO_BREATH_TICKS
        hold = CAMO_BREATH_TICKS - CAMO_PULSE_TICKS
        if ph < hold:
            self.camo_mix = CAMO_MIX_MAX
        else:
            v = (ph - hold) / float(max(1, CAMO_PULSE_TICKS))
            breath = 0.5 - 0.5 * math.cos(v * math.tau)
            self.camo_mix = CAMO_MIX_MAX - (CAMO_MIX_MAX - CAMO_MIX_MIN) * breath

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
        self._release_carry()
        self.dead = True
        self.dead_t = 0
        self.stun = 0
        self.jaw = 0.0
        self.target = self.target_obj = None
        self.look_at = None
        self.threat = self.threat_obj = None
        self.anger = 0.0
        self.anger_obj = None
        self.lurk = False
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

    def haul(self, x, y, dirv=0.0) -> None:
        """被蛞蝓猫拖着走（清场拖尸）：位置每 tick 由猫写死，自己不做物理。

        dirv＝拖动方向（猫的走向），只用来定「身体拖在头的哪一侧」。
        位置钉死 + step 里跳过 _integrate，尸体就不会自己往下掉 / 乱弹。
        """
        self.hauled = True
        self.haul_thrown = False      # 又被拖起来了：丢掉上一次的丢出标记
        self.vx = self.vy = 0.0
        self.x, self.y = x, y
        if abs(dirv) > TURN_VX:
            self.chain_dir = 1.0 if dirv > 0.0 else -1.0

    def release_haul(self, vx=0.0, vy=0.0, thrown_out=False) -> None:
        """松爪（拖到屏幕边甩出去 / 被打断）。

        thrown_out=True ＝ 这一下是「丢出屏幕」（被猫拖到边丢掉的）：
        打上标记后一过窗口边就真删（window._cull_flung_corpses 只对标记过的
        尸体做这种「过边即删」）。被打断/超时放弃也走这条 —— 那时同样朝最近
        的屏幕边甩，否则尸体会原地躺在边上既不消失也没人再管。
        """
        self.hauled = False
        self.haul_thrown = bool(thrown_out)
        self.vx, self.vy = vx, vy

    # ── 主循环 ──
    def step(self, WL: float, HL: float, targets=(), cursor=None,
             prey=(), cats=(), threats=(), others=(), pack=(), rivals=(), surfaces=(),
             lizards=(), blockers=(), tick=None) -> None:
        """推进一 tick。

        targets: [(obj, x, y, dead, fainted)] 蛞蝓猫（动态关系：like<0.5 → Eats）
        prey:    [(obj, weight)] 原版 Eats/Attacks（蝉乌贼 / 面条蝇 / 拾荒者 / 被吃的蜥蜴）
        threats: [(obj, weight)] 原版 Afraid（蓝蜥怕绿/白/青蜥）
        others:  [(obj, weight)] 原版 AgressiveRival（anger 累积 + casual 撕咬）
        pack:    [(obj, weight)] 原版 Pack（黄蜥结群）
        rivals:  旧参数名，等价于 others（保留兼容）
        cats:    同 targets（叼走 / 咬死流程用）
        cursor:  鼠标逻辑坐标
        lizards: 同场其它蜥蜴（认「这只猎物已经归谁」用）
        blockers: 视线遮挡物 (杆子线段, 大生物圆)；由 items.py 每 tick 建一次快照
        tick:    世界 tick（记忆 / 归属 / 情报的时效都按它算）
        """
        others = tuple(others) + tuple(rivals)
        self.perceive(WL, HL, targets=targets, prey=prey, threats=threats,
                      others=others, pack=pack, lizards=lizards,
                      blockers=blockers, surfaces=surfaces, tick=tick)
        self.decide(WL, HL)
        self.act(WL, HL, cursor=cursor)
        self.step_physics(WL, HL, cursor=cursor)

    def step_physics(self, WL: float, HL: float, cursor=None) -> None:
        """物理与渲染状态推进（不含 AI）：被拎着 / 被猫拖着 / 尸体 / 自由态。

        拆出来是为了让 items.py 能做「全体先感知、再决策、最后执行」—— 决策
        阶段不碰速度也不碰世界，执行阶段才真正落到物理上。
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

        # 脚下的支撑面（原版 Floor tile 不止一种：屏幕地板 / 别的窗口顶边 /
        # 横杆杆面都是可站立地形），链体与四足都踩在它上面。
        self._ground = self._ground_y(HL)
        if self.hurt_flash > 0:
            self.hurt_flash -= 1
        # 被鼠标拎着的分支必须排在尸体之前：死蜥也要能被拖。
        # 之前 dead 先命中，尸体每帧只做自由落体（vx *= 0.9 + _integrate），
        # 拎起来就原地往下掉 —— 表现就是「蜥蜴尸体拖不动」。
        if self.state == ItemState.MOUSE:
            self._step_held(WL, HL, cursor)
        elif self.hauled:            # 被猫拖着走：位置由猫写，自己不做物理
            self.vx = self.vy = 0.0
        elif self.dead:
            self._release_carry()
            self.dead_t += 1
            if self.dead_t > CORPSE_TTL:
                self.state = ItemState.GONE
            self.vx *= 0.9
            self._integrate(WL, HL)
        else:
            self._integrate(WL, HL)

        self.anim = self._intent()          # AI → 动画意图（这一帧的映射只发生一次）
        self._step_chain(self._ground)
        self._step_legs(HL)
        self._step_head()
        self._step_depth()
        self._step_cosmetics()

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
        dx, dy = px - self.x, py - self.y
        d = math.hypot(dx, dy)
        # 与拖蛞蝓猫同一手感：头点**直接**跟光标（没有限速延迟），
        # 身体链自己按约束追上来。只把松手时的速度限幅。
        self.x, self.y = px, py
        self.vx = clampf(dx, -MAX_SEG_SPEED, MAX_SEG_SPEED)
        self.vy = clampf(dy, -MAX_SEG_SPEED, MAX_SEG_SPEED)

    def _ground_y(self, HL: float) -> float:
        """这一 tick 脚下的支撑面 y：屏幕地板 / 别的窗口顶边 / 横杆杆面。

        原版 Floor tile 本来就不止一种（LizardPather 拿到的是 AImap 里的可站立
        tile），所以这里问共用的地形层，而不是一律把屏幕底边当地面。没有地形层
        （单元测试直接造 Lizard）时退回屏幕地板。
        """
        tq = self.terrain
        if tq is None:
            return HL
        return tq.support(self.x, self.y, HL)

    def _route_tick(self, o, WL, HL) -> bool:
        """执行地形路线（MovementConnection 多段）的当前这一段。

        爬段与跳段不在这里：爬段由 ``_climb_plan`` 写进 climb_* 字段、交给
        ``_step_wall`` 的附着物理；跳段由 ``_approach_tick`` 照旧处理。这里只管
        「走过去」和「走下去」两段 —— 返回 True 表示这一帧的位移由本方法接管。
        """
        plan = self.plan
        if plan is None:
            return False
        legs = getattr(plan, "legs", ())
        if not legs:
            return False
        leg = legs[0]
        if leg.mode in ("climb_wall", "climb_pole", "jump", "hop"):
            return False                   # 爬 / 跳各有自己的执行器
        if o is not None and o.visible:
            self.look_at = (o.x, o.y)
        goal_x, goal_y = leg.x, leg.y
        if leg.mode == "drop" and leg.tx is not None:
            goal_x, goal_y = leg.tx, leg.ty      # 掉下去：朝落点走，剩下交给重力
        self.target, self.target_obj = (goal_x, goal_y), (o.obj if o else None)
        want = clampf((goal_x - self.x) * 0.07, -2.4, 2.4)
        self.vx += (want - self.vx) * WALK_TURN
        return True

    def _apply_foot_support(self) -> None:
        planted = [lg for lg in self.legs if lg.planted and not lg.disabled]
        if not planted:
            if (self._contact_floor and not self.dead
                    and self.state == ItemState.FREE):
                self.vx *= NO_GRIP_SPEED
            return
        corr = 0.0
        for lg in planted:
            hip = self.seg[min(lg.pair, len(self.seg) - 1)]
            corr += (lg.x - lg.plant_dx) - hip.x
        corr /= len(planted)
        self.vx += clampf(corr * FOOT_LEVERAGE,
                          -FOOT_LEVERAGE_MAX, FOOT_LEVERAGE_MAX)

    def _collide_static_lines(self, WL: float) -> None:
        """竖杆与可见背景墙都是实体线；只有能力决定能否主动附着攀爬。"""
        tq = self.terrain
        if tq is None or self.climb_attached:
            return
        lines = [(x, top, bot) for x, top, bot in tq.vpoles()]
        lines += [(x, top, bot) for x, top, bot in tq.walls()]
        for x, top, bot in lines:
            rr = self.head_rad + LINE_COLLIDE_PAD
            if self.y < top - rr or self.y > bot + rr:
                continue
            dx = self.x - x
            if abs(dx) >= rr:
                continue
            side = 1.0 if dx > 0.0 else (-1.0 if dx < 0.0 else self.chain_dir)
            self.x = x + side * rr
            if self.vx * side < 0.0:
                self.vx = 0.0

    def _collide_chain_lines(self, WL: float) -> None:
        tq = self.terrain
        if tq is None or self.climb_attached:
            return
        lines = [(x, top, bot) for x, top, bot in tq.vpoles()]
        lines += [(x, top, bot) for x, top, bot in tq.walls()]
        for s in self.seg:
            rr = s.rad + LINE_COLLIDE_PAD
            for x, top, bot in lines:
                if s.y < top - rr or s.y > bot + rr:
                    continue
                dx = s.x - x
                if abs(dx) >= rr:
                    continue
                side = 1.0 if dx > 0.0 else -1.0
                s.x = x + side * rr

    def _integrate(self, WL, HL) -> None:
        """自由态：重力积分 + 地面 / 侧墙（攀爬中改用墙面附着物理）。"""
        if self.climb_x is not None and not self.dead:
            self._step_wall(WL, HL)
            return
        self._apply_foot_support()
        self.vx *= AIR_FRICTION
        self.vy = (self.vy + GRAVITY * self.room_gravity) * AIR_FRICTION
        if self.water_y is not None and self.y + self.head_rad > self.water_y:
            self.vy -= GRAVITY * 0.7 * self.room_gravity        # 浮力抵掉大部分重力
            self.vy *= 0.93
            self.vx *= 0.95
        self.x += self.vx
        self.y += self.vy
        self._collide_static_lines(WL)

        r = self.head_rad
        # 转身时上半身支起：头的落点抬高 turn_lift（链体仍受各自的落地限制）
        floor = self._ground - self.body_rad * HEAD_STAND_FAC - self.turn_lift
        self._contact_floor = False
        self.wall_dir = 0
        if self.y > floor:
            self.y = floor
            if self.vy > 0.0:
                self.vy = 0.0
            self._contact_floor = True
            if not self.haul_thrown:      # 被丢出屏幕的尸体不吃地面摩擦：一路滑出去
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

    # ── 墙面附着（原版 Floor→Wall→Climb 那条移动链的桌宠替身）──
    def _climb_release(self) -> None:
        """脱墙 / 放弃攀爬：清掉这一 tick 的攀爬意图与附着状态。"""
        self.climb_x = None
        self.climb_dir = 0
        self.climb_kind = None
        self.climb_attached = False
        self.climb_side = 0
        self.climb_top = None
        self.climb_bot = None

    def _climb_span_ok(self) -> bool:
        """现在这条线还抓得住吗：线还在这一帧的清单里、我也还在它的高度范围内。"""
        top, bot = self.climb_top, self.climb_bot
        if top is None or bot is None:
            return True
        if not (top - 12.0 <= self.y <= bot + 12.0):
            return False
        if not self.climb_surfaces:
            return True
        for surf in self.climb_surfaces:
            if abs(float(surf[0]) - self.climb_x) <= 1.0:
                return True
        return False

    def _step_wall(self, WL, HL) -> None:
        """贴墙：先走过去抓附（保留重力），贴上后用弹簧吸在墙面上再纵向爬。

        反编译对照：原版「上墙」= Floor→Wall 的 MovementConnection + Wall/Climb
        移动，不是把身体每帧硬钉在 x 上。旧实现 `x = climb_x` 会让蜥蜴瞬移贴墙、
        墙顶/窗口交界处弹跳；这里拆成「靠近 → 抓附 → 沿墙运动 → 到头上/底下脱墙」。
        """
        sx = self.climb_x
        dx = sx - self.x
        r = self.head_rad
        floor = self._ground - self.body_rad * HEAD_STAND_FAC - self.turn_lift
        if not self.climb_attached:
            if abs(dx) <= CLIMB_GRIP_R and self._climb_span_ok():
                self.climb_attached = True
                if dx > 0.0:
                    self.climb_side = -1
                elif dx < 0.0:
                    self.climb_side = 1
            else:
                # 走过去：朝墙挪（墙体不挡身体，与「窗口顶边可站」同一口径）
                want = CLIMB_APPROACH_SPEED * (1.0 if dx > 0.0 else -1.0)
                self.vx += (want - self.vx) * 0.5
                self.vx *= 0.85
                self.vy = (self.vy + GRAVITY * self.room_gravity) * AIR_FRICTION
                self.x += self.vx
                self.y += self.vy
                self._contact_floor = False
                self.wall_dir = 0
                if self.y > floor:
                    self.y = floor
                    self.vy = 0.0
                    self._contact_floor = True
                    self.vx *= GROUND_FRICTION
                elif self.y < r:
                    self.y, self.vy = r, 0.0
                return
        # wall_jump（青蜥的蓄力弹射系）：目标就在旁边但不在正上/正下 → 蹬墙出去
        o = getattr(self, "stage_obj", None)
        if (self.breed.wall_jump and o is not None
                and abs(o.y - self.y) < CLIMB_MIN_DY
                and CLIMB_GRIP_R < abs(o.x - self.x) <= CLIMB_WALK_R):
            self._climb_release()
            self.vx = CLIMB_JUMP_PUSH * (1.0 if o.x > self.x else -1.0)
            self.vy = CLIMB_HOP * 0.7
            return
        # 已经贴上：横向用弹簧吸住（不是硬钉 x），纵向按爬速走
        self.vx += dx * CLIMB_GRIP_SPRING
        self.vx *= CLIMB_GRIP_DAMP
        self.x += self.vx
        self.vy = -CLIMB_SPEED * self.climb_dir
        self.y += self.vy
        self._contact_floor = False
        self.wall_dir = self.climb_side
        top, bot = self.climb_top, self.climb_bot
        if bot is not None and self.y > bot:
            self.y = min(bot, floor)              # 爬到底 / 线到头：站住并脱墙
            self.vy = 0.0
            self._contact_floor = True
            self._climb_release()
        elif self.y > floor:
            self.y = floor
            self.vy = 0.0
            self._contact_floor = True
            self._climb_release()
        elif self.y < r:
            self.y, self.vy = r, 0.0
        elif top is not None and self.y < top + 4.0:
            self.y = max(r, top + 4.0)            # 到墙头：脱墙，站到墙沿上
            self.vy = 0.0
            if self.breed.wall_detach:
                self._climb_release()

    # ── AI ──
    # ══ 第一层：感知（同一份世界快照，不做任何决策）══
    def perceive(self, WL, HL, targets=(), prey=(), threats=(), others=(), pack=(),
                 lizards=(), blockers=(), surfaces=(), terrain=None, tick=None) -> dict:
        """这一 tick 看见 / 听见什么。

        每条记录都带上距离、关系权重、视野锥得分、**可见性**（锥内且没被挡）、
        姿态（匍匐更难被盯上）以及「这只猎物是不是已经归别人」。这一层不改世界、
        不改速度 —— 所以多只蜥蜴可以拿同一份快照各自决策。
        """
        if tick is not None:
            self._tick = int(tick)
        self._blockers = blockers or ()
        self.climb_surfaces = tuple(surfaces or ())   # 这一帧可攀爬的竖线
        if terrain is not None:
            self.terrain = terrain                    # 全场共用的一份地形快照
        self.peers = tuple(lizards)
        cats, preys, thrs, rivs, pk = [], [], [], [], []
        for row in targets:
            obj, ox, oy, dead, fainted = _cat_row(row)
            if obj is None:
                continue
            crawl = _cat_crouching(obj)
            w = FAINT_BITE_BONUS if fainted and not dead else 1.0
            if crawl:
                w /= CROUCH_TARGET_MULT
            if _cat_camo(obj):
                w /= CAMO_TARGET_MULT
            cats.append(self._observe(obj, ox, oy, "cat", w, dead, fainted,
                                      "crawl" if crawl else "stand"))
        for obj, w in prey:
            preys.append(self._observe(obj, getattr(obj, "x", self.x),
                                       getattr(obj, "y", self.y), "prey", w))
        for obj, w in threats:
            thrs.append(self._observe(obj, getattr(obj, "x", self.x),
                                      getattr(obj, "y", self.y), "threat", w))
        for obj, w in others:
            rivs.append(self._observe(obj, getattr(obj, "x", self.x),
                                      getattr(obj, "y", self.y), "rival", w))
        for obj, w in pack:
            pk.append(self._observe(obj, getattr(obj, "x", self.x),
                                    getattr(obj, "y", self.y), "pack", w))
        self.obs = {"cats": tuple(cats), "prey": tuple(preys),
                    "threats": tuple(thrs), "rivals": tuple(rivs),
                    "pack": tuple(pk)}
        self._update_memory(cats, preys)
        return self.obs

    def _observe(self, obj, ox, oy, kind, w=1.0, dead=False, fainted=False,
                 stance="stand") -> Observation:
        """把一个候选变成观察记录（含视野锥与视线遮挡判定）。"""
        d = math.hypot(ox - self.x, oy - self.y)
        los = True
        if self._blockers:
            segs, circles = self._blockers
            los = not los_blocked(self.x, self.y, ox, oy, segs, circles)
        return Observation(obj, ox, oy, d, kind, w, self._visual_fac(ox, oy),
                           self.sees(ox, oy, obj) and los, dead, fainted,
                           stance, self._prey_owner(obj), los=los)

    def _prey_owner(self, obj):
        """这只猎物是不是已经归别的蜥蜴（它咬倒的、正往回叼的）。"""
        for other in self.peers:
            if other is self or getattr(other, "dead", False):
                continue
            if other.prey.owns(obj, self._tick):
                return other
        return None

    def _update_memory(self, cats, preys) -> None:
        """记忆层：这一帧最值得记的那个目标（看得见、不是尸体）。"""
        cands = [o for o in list(cats) + list(preys) if o.visible and not o.dead]
        if cands:
            best = min(cands, key=lambda o: o.score)
            self.mem.see(best.obj, (best.x, best.y), self._tick, best.kind)
        else:
            self.mem.miss()

    # ══ 第二层：行为效用（原版 Behavior.* 的权重顺序）══
    def decide(self, WL, HL) -> str:
        """Flee(威胁) > ReturnPrey/CarryPrey(猎物) > Injured > 同族竞争 > Hunt
        > InvestigateSound > Pack > Lurk > Idle。产出行为名与接近路线，不碰速度。
        """
        self.warning_t = max(0, self.warning_t - 1)
        self.guard_t = max(0, self.guard_t - 1)
        if self.dead or self.state != ItemState.FREE or self.hauled:
            return self._stage("")
        if self.rock_push > 0:
            # 原版 Lizard.cs：turnedByRockCounter 期间 WeightedPush(0, 2, (dir,0), 6f)
            self.rock_push -= 1
            self.vx += 0.14 * self.rock_push_dir * self.room_gravity
        if self.stun > 0:
            self.stun -= 1
            self._release_carry()                 # 被砸晕/击晕 → 松口（原版猎物掉出来）
            self.vx *= 0.90
            return self._stage("Stunned")
        if self.tamed:                            # 认主的蜥蜴不再咬人，只跟着走
            self._release_carry()
            return self._stage("FollowFriend")
        obs = self.obs
        # ① 原版 Behavior.Flee（ThreatTracker，utility 权重 1.0 最高）
        self._pick_threat(obs["threats"])
        if self.threat is not None:
            self.threat_t = max(self.threat_t, 10)      # 看得见就续上逃跑计时
        if self.threat_t > 0:
            self._release_carry()
            return self._stage("Flee")
        # ② 原版 Behavior.ReturnPrey：把咬倒的猎物拖回巢穴
        carry = self._carry_intent(WL, HL)
        if carry is not None:
            return self._stage(carry)
        # ③ 原版 Behavior.Injured（LizardInjuryTracker，权重 0.9）
        if self.injured >= INJURY_UTIL:
            return self._stage("Injured")
        # ④ 原版 AgressionTracker（权重 0.5）→ casual 撕咬 → 争夺
        fight = self._anger_tick(obs["rivals"])
        if self._casual_bite(obs["rivals"]):
            return self._stage("CasualBite")
        if fight is not None:
            return self._stage("FightRival", fight)
        if self.warning_t <= 0 and self.anger >= ANGER_FIGHT * 0.5:
            rival = self._nearest_rival(obs["rivals"])
            if rival is not None and rival.dist <= WARN_R:
                self.warning_t = WARN_TICKS             # 举头警告：先亮牙再动手
                return self._stage("Warn", rival)
        # ④b 我想要的猎物在别人嘴里：支配度不够就认怂，够就上去抢
        thief = self._contest_pick(obs)
        if thief is not None:
            return self._stage("FightRival", thief)
        # ⑤ 狩猎：选目标 → 该怎么靠近（同层直冲 / 去起跳点 / 伏击）
        tgt = self._choose_target(obs, fight)
        if tgt is not None:
            if tgt.visible and tgt.dist <= self._bite_reach():
                return self._stage("Attack", tgt)
            self.plan = self._plan_for(tgt, WL, HL)
            if self.plan is not None and self.plan.mode == "lurk":
                return self._stage("Lurk", tgt)
            if not tgt.visible:
                return self._stage("InvestigatePos", tgt)
            if self.plan is not None and self.plan.mode == "jump":
                return self._stage("ApproachPrey", tgt)
            return self._stage("HuntPrey", tgt)
        # ⑥ 守猎物：刚送回巢穴，在巢穴边待一会儿（原版回巢进食）
        if self.guard_t > 0 and self._guard_alive():
            return self._stage("GuardPrey")
        # ⑦ 原版 Behavior.InvestigateSound（NoiseTracker，权重 0.2 最低）
        if self._noise_wants():
            return self._stage("InvestigateSound")
        # ⑧ 原版 Pack（黄蜥）：按同伴的猎物情报包夹，其次跟住同伴
        if self._pack_wants(obs):
            return self._stage("PackCoordination")
        if self._lurk_pref():
            return self._stage("Lurk", None)
        return self._stage("Wander")

    def _stage(self, name, obs=None) -> str:
        """记下这一帧的行为（观察记录一起留着，执行阶段要用）。"""
        self.stage = name
        self.stage_obj = obs if isinstance(obs, Observation) else None
        if self.stage_obj is not None:
            self.look_at = (self.stage_obj.x, self.stage_obj.y)
        return name

    # ══ 第三层：动作（真正改速度 / 下巴；世界结算在 items.py）══
    def act(self, WL, HL, cursor=None) -> None:
        st = self.stage
        o = self.stage_obj
        # 攀爬：够得着的竖杆 / 背景墙竖边就贴上去（原版 Climb / Wall tile）。
        # 每 tick 重算一次，所以「追猎以外」的状态自然松手。
        self._climb_plan(o if st in ("Attack", "HuntPrey", "ApproachPrey",
                                     "InvestigatePos", "InvestigateSound",
                                     "PackCoordination") else None, HL)
        if st in ("", "Stunned", "CasualBite"):
            return
        # 地形路线的当前段是「走 / 掉」时由这里接管位移；「爬 / 跳」段交给
        # 上面的 _climb_plan 与下面的 _approach_tick，互不打架。
        if (self.plan is not None and self.plan.legs
                and st in ("HuntPrey", "ApproachPrey", "InvestigatePos",
                           "InvestigateSound", "PackCoordination")
                and self._route_tick(o, WL, HL)):
            return
        if st == "FollowFriend":
            self._follow(WL, HL)
            return
        if st == "Flee":
            self._threat_tick(HL)
            return
        if st in ("ReturnPrey", "CarryPrey"):
            self._carry_tick(WL, HL)
            return
        if st == "Injured":
            self._injured_tick(WL, HL)
            return
        if st == "Warn":
            self._warn_tick(o, WL, HL)
            return
        if st == "FightRival":
            self._fight_rival_tick(o, WL, HL)
            return
        if st == "GuardPrey":
            self._guard_tick(WL, HL)
            return
        if st in ("Attack", "HuntPrey", "ApproachPrey", "InvestigatePos", "Lurk"):
            if self.bite_hold > 0:                       # 咬合保持
                self.vx *= 0.84
                self._track_head()
                return
            if self.bite_cd > 0:
                pass                              # 咬合冷却期：下巴由 _jaw_target 收回
            if st == "Lurk" and o is None:
                self._lurk_idle(WL, HL)
                return
            if st == "ApproachPrey":
                self._approach_tick(o, WL, HL)
                return
            if st == "InvestigatePos":
                self._investigate_tick(o, WL, HL)
                return
            self._lunge_toward(o, WL, HL)
            return
        if st == "InvestigateSound":
            self._noise_tick(WL, HL)
            return
        if st == "PackCoordination":
            self._pack_tick(WL, HL)
            return
        self._wander(WL, HL)

    # ── 动作层的几个小件 ──
    def _lunge_toward(self, o, WL, HL, bite=True) -> None:
        """朝目标加速（原版直接扑）：写目标坐标 + 交给 _lunge。"""
        if o is None:
            return
        self.target, self.target_obj = (o.x, o.y), o.obj
        if o.visible:
            self.look_at = (o.x, o.y)
        dx, dy = o.x - self.x, o.y - self.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            self._lunge(dx / d, dy / d, d, HL)

    def _investigate_tick(self, o, WL, HL) -> None:
        """中置信度：去最后看见它的位置找（原版 Investigate，不亮牙）。"""
        if o is None:
            return
        self.look_at = (o.x, o.y)
        want = clampf((o.x - self.x) * 0.06, -2.2, 2.2)
        self.vx += (want - self.vx) * WALK_TURN

    def _climb_plan(self, o, HL) -> None:
        """要不要贴着一条竖线爬（原版 LizardPather 的 Climb / Wall 通行能力）。

        ``surfaces`` 每项 ``(x, y_top, y_bot, kind)``：kind == "wall" 是背景墙
        的可见墙段，只有会爬墙的品种（WallClimber：蓝/白/鳗鱼蜥）才考虑；
        kind == "pole" 是竖杆，会爬杆的品种都能用。选中条件不再要求「已经贴到
        线上」，而是「线够得着目标那一端」且「我够得着这条线」—— 线还在我这一层
        就抓上去，否则墙底/杆底落在我这层就走过去（原版 Floor→Wall 那条连接）。
        真正的位移交给 _step_wall（附着物理），不再每帧硬钉 x。
        """
        self._climb_release()
        if o is None or self.dead:
            return
        plan = self.plan
        if (plan is not None and plan.alive(self._tick)
                and plan.mode in ("climb_wall", "climb_pole")):
            climb = getattr(plan, "climb", None)
            if climb is not None:
                # Planner（Terrain ↔ Capability 过滤）选出来的正式路线：
                # 动作层不再自己挑线，只承接「去哪个上墙点 / 往哪个方向爬」。
                sx, top, bot, up = climb
                self.climb_x = float(sx)
                self.climb_dir = 1 if up else -1
                self.climb_kind = "wall" if plan.mode == "climb_wall" else "pole"
                self.climb_top = float(top)
                self.climb_bot = float(bot)
                self.climb_attached = False
                return
        up = o.y < self.y - CLIMB_MIN_DY
        down = o.y > self.y + CLIMB_MIN_DY
        if not (up or down):
            return
        best = None
        for surf in self.climb_surfaces:
            sx, top, bot = float(surf[0]), float(surf[1]), float(surf[2])
            kind = surf[3] if len(surf) > 3 else "pole"
            if kind == "wall":
                if not (self.breed.climb_wall and self.breed.wall_attach):
                    continue                    # 不会爬墙的品种：背景墙不是它的地形
            elif not self.breed.climb_pole:
                continue
            if up and top > o.y + 10.0:
                continue                        # 线不够高，爬上去也够不着
            if down and bot < o.y - 10.0:
                continue                        # 线不够低
            on_line = top - 12.0 <= self.y <= bot + 12.0
            # 墙底/杆底落在我这一层：走过去就能上墙
            foot_here = (bot >= self.y - CLIMB_WALK_TOL
                         and bot <= self.y + CLIMB_WALK_TOL)
            if not (on_line or foot_here):
                continue
            d = abs(self.x - sx)
            if d > CLIMB_WALK_R:
                continue                        # 太远：走不到这个上墙点
            score = d + (0.0 if d <= CLIMB_GRIP_R else CLIMB_APPROACH_PENALTY)
            if best is None or score < best[0]:
                best = (score, sx, 1 if up else -1, kind, top, bot)
        if best is not None:
            self.climb_x = best[1]
            self.climb_dir = best[2]
            self.climb_kind = best[3]
            self.climb_top = best[4]
            self.climb_bot = best[5]
            self.climb_attached = False

    def _hop_vy(self) -> float:
        """蹬地起跳初速：不会爬的品种（绿蜥）压根不往上蹿。焦糖蜥跳跃也靠它。"""
        if not self.breed.can_climb:
            return 0.0
        return CLIMB_HOP * math.sqrt(max(0.4, self.breed.body_size_fac))

    def _plan_for(self, o, WL, HL):
        """接近规划：同一套 utility，按品种调「绕路 / 落点 / 贴墙 / 起跳倾向」。"""
        if o is None:
            return None
        floor = HL - self.body_rad * HEAD_STAND_FAC
        hop = self._hop_vy()
        return plan_approach(o.x, o.y, self.x, self.y, floor, WL, self._bite_reach(),
                             prefs_for(self.breed.key), GRAVITY, hop, AIR_FRICTION,
                             sprint=self.sprint, base_speed=self.breed.base_speed,
                             tick=self._tick, terrain=self.terrain, caps=self.caps)

    def _approach_tick(self, o, WL, HL) -> None:
        """去起跳点 → 起跳 → 空中继续修正（旧版缺的就是「去起跳点」这一步）。"""
        if o is None:
            return
        plan = self.plan
        if plan is None or not plan.alive(self._tick):
            plan = self._plan_for(o, WL, HL)
            self.plan = plan
        if plan is None:
            self._lunge_toward(o, WL, HL)
            return
        self.look_at = (o.x, o.y)
        if plan.mode in ("climb_wall", "climb_pole"):
            # Planner 给的是地形路线：走到上墙点，剩下的交给 _step_wall 的附着物理
            wx = plan.target[0]
            want = clampf((wx - self.x) * 0.08, -2.6, 2.6)
            self.vx += (want - self.vx) * WALK_TURN
            return
        lx = plan.launch[0] if plan.launch else self.x
        if abs(self.x - lx) <= 10.0 and self._contact_floor and self.hop_cd <= 0:
            self.vy = self._hop_vy()
            self.hop_cd = HOP_CD
            want = clampf((o.x - self.x) * 0.05, -2.6, 2.6)
            self.vx += (want - self.vx) * LUNGE_ACCEL
            return
        want = clampf((lx - self.x) * 0.06, -2.4, 2.4)
        self.vx += (want - self.vx) * WALK_TURN

    def _warn_tick(self, o, WL, HL) -> None:
        """警告同族竞争者：站定、举头、张嘴（原版同族对峙的 warning）。"""
        self.vx -= self.vx * 0.25
        if o is not None and o.visible:
            self.look_at = (o.x, o.y)

    def _fight_rival_tick(self, o, WL, HL) -> None:
        """争夺 / 打架：朝竞争者冲，够近就咬（原版 AgressionTracker → Fighting）。"""
        if self.bite_hold > 0:
            self.vx *= 0.84
            self._track_head()
            return
        self._lunge_toward(o, WL, HL)

    def _guard_tick(self, WL, HL) -> None:
        """守在巢穴边看住刚拖回来的猎物（原版把猎物带回巢穴后进食 / 看守）。"""
        self.vx -= self.vx * 0.30
        if self.carry_den is not None:
            self.look_at = (self.carry_den.x, HL - 12.0)

    def _guard_alive(self) -> bool:
        """守在巢穴边的那具猎物还在（没被清场、没被救活）。"""
        obj = self.guard_obj
        body = getattr(obj, "body", None)
        if obj is None or body is None or getattr(body, "dead", False) is False:
            self.guard_obj, self.guard_t = None, 0
            return False
        if getattr(obj, "state", None) is ItemState.GONE:
            self.guard_obj, self.guard_t = None, 0
            return False
        return True

    def _lurk_pref(self) -> bool:
        return prefs_for(self.breed.key).get("lurk", 0.0) >= 0.5

    def _lurk_idle(self, WL, HL) -> None:
        """伏击待机（原版 LurkTracker）：原地压低身体等猎物进圈。"""
        self.lurk = True
        self.vx -= self.vx * 0.25

    def _noise_wants(self) -> bool:
        if self.noise_t <= 0:
            return False
        return math.hypot(self.noise_x - self.x, self.noise_y - self.y) >= 24.0

    def _nearest_rival(self, rivals):
        rivals = self._as_obs(rivals, "rival")
        best = None
        for o in rivals:
            if o.dead or not o.visible:
                continue
            if best is None or o.dist < best.dist:
                best = o
        return best

    def _contest_pick(self, obs):
        """我想要的猎物在别人嘴里：支配度差太多就认怂，否则上去抢。"""
        for o in list(obs["cats"]) + list(obs["prey"]):
            owner = o.owner
            if owner is None or owner is self or o.dead or not o.visible:
                continue
            if self.soc.defers_to(owner, self._tick):
                continue
            odom = float(getattr(owner, "dominance", 0.5))
            if odom - self.dominance > DOMINANCE_DEFER:
                self.soc.submit(owner, self._tick)     # 打不过：认怂，不去抢
                continue
            push = float(getattr(owner, "x", None) or 0.0)
            return self._observe(owner, push, float(getattr(owner, "y", 0.0)),
                                 "rival", CONTEST_W)
        return None

    def _pack_wants(self, obs) -> bool:
        """黄蜥要不要走群体协调：手上有新鲜情报，或者同伴离得太远。"""
        if self.alert is not None and self.alert.fresh(self._tick):
            return True
        return any(o.obj is not self and not o.dead and o.dist > PACK_GAP
                   for o in obs["pack"])

    def offer_alert(self):
        """黄蜥广播「我在哪看见什么猎物」（原版 Pack 情报，不是站在一起）。"""
        if self.dead or self.tamed or self.carry_body is not None:
            return None
        if self.breed.key not in PACK_BREEDS:
            return None
        if not self.mem.hunting or self.mem.last_pos is None:
            return None
        return PackAlert(self.mem.last_pos[0], self.mem.last_pos[1], self.mem.obj,
                         self._tick, self.id, self.mem.confidence)

    def absorb_alert(self, alert) -> None:
        """收到同伴的情报：记下来，包夹位置按自己的序号错开（不要全挤一个点）。"""
        if alert is None or self.dead or self.tamed:
            return
        if self.carry_body is not None or alert.obj is None:
            return
        if self.alert is None or alert.tick >= self.alert.tick:
            self.alert = alert

    def _as_obs(self, seq, kind) -> tuple:
        """兼容直接喂 [(obj, w)] 的旧调用：不是观察记录就现场转一份。"""
        if not seq:
            return ()
        first = next(iter(seq))
        if isinstance(first, Observation):
            return tuple(seq)
        return tuple(self._entries(seq, kind))

    def _entries(self, seq, kind) -> list:
        """把 [(obj, w)] / [(obj, x, y, dead, fainted)] / [Observation] 统一成观察记录。"""
        out = []
        for row in seq:
            if isinstance(row, Observation):
                out.append(row)
                continue
            if len(row) == 2:
                obj, w = row[0], float(row[1])
                out.append(self._observe(obj, getattr(obj, "x", self.x),
                                         getattr(obj, "y", self.y), kind, w))
                continue
            obj, ox, oy, dead, fainted = _cat_row(row)
            if obj is None:
                continue
            crawl = _cat_crouching(obj)
            w = FAINT_BITE_BONUS if fainted and not dead else 1.0
            if crawl:
                w /= CROUCH_TARGET_MULT
            if _cat_camo(obj):
                w /= CAMO_TARGET_MULT
            out.append(self._observe(obj, ox, oy, kind, w, dead, fainted,
                                     "crawl" if crawl else "stand"))
        return out

    def _choose_target(self, obs, fight=None):
        """选「我现在想吃什么」（原版 PreyTracker）。

        看得见的优先，别人咬倒的猎物不碰；失去视线时按**记忆**继续找：
        高置信度继续追、中置信度去最后看见的位置找、低到看不见才放弃。
        """
        best = None
        for o in list(obs["cats"]) + list(obs["prey"]):
            if not o.visible or o.dead:
                continue
            if (o.kind == "cat" and self.friend_id is not None
                    and getattr(o.obj, "id", None) == self.friend_id):
                continue
            if o.owner is not None and o.owner is not self:
                continue
            if o.kind == "cat" and _cat_offering_food(o.obj):
                pass
            if best is None or o.score < best.score:
                best = o
        if best is not None:
            self._adopt(best)
            return best
        if fight is not None:
            self._adopt(fight)
            return fight
        mem = self.mem
        if mem.holds(None, self._tick) and mem.last_pos is not None:
            mx, my = mem.last_pos
            o = Observation(mem.obj, mx, my, math.hypot(mx - self.x, my - self.y),
                            mem.kind or "cat", 1.0, 1.0, False)
            self.target, self.target_obj = (mx, my), mem.obj
            self.look_at = (mx, my)
            return o
        self.target = self.target_obj = None
        self.look_at = None
        return None

    def _adopt(self, o) -> None:
        """锁上一个目标：掷一次 loungeTendency（原版冲刺倾向）。"""
        if o.obj is not self.target_obj:
            self.sprint = 1.0 if self.rng.random() < self.breed.lounge_tendency else 0.55
            if o.kind == "prey":
                self.prey.hunting(o.obj, self._tick)
        self.target, self.target_obj = (o.x, o.y), o.obj
        self.look_at = (o.x, o.y)

    def _follow(self, WL, HL) -> None:
        """跟上朋友（被驯服后）：近了就停下，远了就追。"""
        self.target = None
        self.target_obj = None
        tx = None
        for o in self.obs["cats"]:
            if self.friend_id is not None and getattr(o.obj, "id", None) == self.friend_id:
                tx = o.x
                self.look_at = (o.x, o.y)
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

    # ── 原版关系追踪器（LizardAI.ModuleToTrackRelationship，LizardAI.cs:1346-1361）──
    @property
    def injured(self) -> float:
        """原版 LizardInjuryTracker.Utility（LizardAI.cs:75-82）：
        SCurve(InverseLerp(0.2, 0.9, 1 - health), 0.01)。health 越高越接近 0。"""
        return _scurve(inv_lerp(0.2, 0.9, 1.0 - clampf(self.health, 0.0, 1.0)), 0.01)

    def _visual_fac(self, tx, ty) -> float:
        """原版 LizardAI.VisualScore（LizardAI.cs:1184-1192）：
        目标偏出视野锥（perfectVisionAngle→periferalVisionAngle）时得分线性扣减。
        返回 1=正前方、0=身后。"""
        perfect, perif = self.breed.vision
        dx, dy = tx - self.x, ty - self.y
        n = math.hypot(dx, dy)
        if n < 1e-6:
            return 1.0
        a = math.radians(self.head_angle)
        dot = clampf((dx * math.sin(a) - dy * math.cos(a)) / n, -1.0, 1.0)
        return clampf(1.0 - inv_lerp(perfect, perif, dot), 0.0, 1.0)

    def sees(self, tx, ty, target=None, blockers=None) -> bool:
        """可见性：锥内按满视距，锥外只留 VIS_BACK_FAC 倍（原版按 VisualScore 扣分的近似），
        并且**中间不能有东西挡着**（杆子 / 石堆 / 别的生物）。已锁定的目标不重判视野锥
        （原版 forgetCounter 期间继续追），但遮挡照样算 —— 挡住就等于看不见，记忆衰减。"""
        d = math.hypot(tx - self.x, ty - self.y)
        if target is not None and target is self.target_obj:
            if d > self.notice_r:
                return False
        else:
            v = self._visual_fac(tx, ty)
            if d > self.notice_r * (VIS_BACK_FAC + (1.0 - VIS_BACK_FAC) * v):
                return False
        if blockers is None:
            blockers = self._blockers
        if blockers:
            segs, circles = blockers
            if los_blocked(self.x, self.y, tx, ty, segs, circles):
                return False
        return True

    def hear_noise(self, x: float, y: float) -> None:
        """原版 ReactToNoise（LizardAI.cs:1741-1763）：记住最近一次响声的位置。"""
        if self.dead or self.tamed:
            return
        if math.hypot(x - self.x, y - self.y) > NOISE_R:
            return
        self.noise_x, self.noise_y, self.noise_t = float(x), float(y), NOISE_TICKS

    def _pick_threat(self, threats) -> None:
        """原版 ThreatTracker（Afraid 关系）：挑最近 / 最重的威胁。

        威胁判定只看距离与遮挡，不看视野锥 —— 背后来的东西照样可怕。被杆子挡住
        时看不见（记忆里的位置还在，所以不会瞬间忘记）。
        """
        threats = self._as_obs(threats, "threat")
        notice = self.notice_r * THREAT_NOTICE_FAC
        best, bestscore, bestobj = None, None, None
        for o in threats:
            if o.dead or not o.los:
                continue
            if o.dist > notice:
                continue
            score = o.dist / max(0.05, o.weight * (1.0 + 1.5 * self.rel.fears(o.obj)))
            if bestscore is None or score < bestscore:
                best, bestscore, bestobj = (o.x, o.y), score, o.obj
        self.threat, self.threat_obj = best, bestobj

    def _threat_tick(self, HL) -> bool:
        """原版 Behavior.Flee（LizardAI.cs:797-822）：背对威胁全速逃、闭颌、不咬任何人。"""
        if self.threat_t <= 0:
            return False
        self.threat_t -= 1
        tx, ty = self.threat if self.threat is not None else (self.x, self.y)
        dx, dy = self.x - tx, self.y - ty
        d = math.hypot(dx, dy) or 1.0
        sp = self.breed.base_speed * FLEE_SPEED
        self.vx += (dx / d * sp - self.vx) * FLEE_ACCEL
        self.target = self.target_obj = None
        self.look_at = (tx, ty)
        if self._contact_floor and self.rng.random() < FLEE_HOP:
            self.vy = self._hop_vy() * 0.7
        return True

    def _anger_tick(self, others):
        """原版 AgressionTracker（AgressionTracker.cs，ctor angerSpeedUp/Down = 0.001）：
        anger 缓慢趋向 baseAnger × 距离系数（InverseLerp(10+base*70, 5, 格距)）；
        Utility = InverseLerp(0.35, 1, anger)。Utility×0.5 压过猎物权重 0.6 才转 Fighting，
        所以有猎物在场时永远先打猎物，只有没猎物时才去争夺领地。

        这里多一层社会关系：已经认怂过的同族不再容易激怒我（原版 RecieveCommunication）。
        返回的是**观察记录**（谁让我生气），不是裸坐标。
        """
        others = self._as_obs(others, "rival")
        target, base, best = None, 0.0, None
        for o in others:
            if o.dead:
                continue
            if o.dist > self.notice_r * THREAT_NOTICE_FAC:
                continue
            w = o.weight
            if self.soc.defers_to(o.obj, self._tick):
                w *= 0.35
            w *= 1.0 + 1.2 * self.rel.hostility_to(o.obj)   # 有仇的更想打
            tiles = (abs(o.x - self.x) + abs(o.y - self.y)) / TILE
            num = w * inv_lerp(10.0 + w * 70.0, 5.0, tiles)
            if num > base:
                target, base, best = o.obj, num, o
        if target is None:
            self.anger = max(0.0, self.anger - ANGER_DOWN)
            self.anger_obj = None
            return None
        if self.anger_obj is not target:
            self.anger_obj, self.anger = target, 0.0
        if self.anger < base:
            self.anger = min(base, self.anger + ANGER_UP)
        else:
            self.anger = max(base, self.anger - ANGER_DOWN)
        if inv_lerp(ANGER_FIGHT, 1.0, self.anger) * ANGER_W > 0.0:
            return best
        return None

    def _casual_bite(self, others) -> bool:
        """原版 casualAggressionTarget（LizardAI.cs:1084-1095）+ DoIWantToBiteThisCreature
        （LizardAI.cs:1667-1683）：对可见的 AgressiveRival 按 50% 概率咬一口；
        残血（Random>health）时另有 10% 概率对可见对象乱咬。"""
        if self.bite_cd > 0 or self.bite_hold > 0:
            return False
        others = self._as_obs(others, "rival")
        for o in others:
            if o.dead or not o.visible:
                continue
            if o.dist > self.breed.attempt_bite_radius:
                continue
            if self.rng.random() < CASUAL_BITE_CHANCE:
                self.look_at = (o.x, o.y)
                self._start_bite(o.obj)
                return True
            if self.rng.random() < CASUAL_PANIC_CHANCE and self.rng.random() > self.health:
                self.look_at = (o.x, o.y)
                self._start_bite(o.obj)
                return True
        return False

    def _injured_tick(self, WL, HL) -> bool:
        """原版 Behavior.Injured（LizardAI.cs:977-988）：残血时全速逃回巢穴并躲起来。
        宠物里没有巢穴，改成「远离最近的威胁/猫，缩到最远的地面角落」。"""
        if self.injured < INJURY_UTIL:
            return False
        obs = self.obs
        danger = [(o.x, o.y) for o in obs["threats"]]
        danger += [(o.x, o.y) for o in obs["cats"] if not o.dead]
        corners = ((WANDER_MARGIN, HL - self.body_rad * 2.0),
                   (WL - WANDER_MARGIN, HL - self.body_rad * 2.0))
        best, bestd = corners[0], -1.0
        for cx, cy in corners:
            d = min((math.hypot(cx - px, cy - py) for px, py in danger), default=0.0)
            if d > bestd:
                best, bestd = (cx, cy), d
        self.target = self.target_obj = None
        self.look_at = best
        want = clampf((best[0] - self.x) * 0.05, -2.0, 2.0) * INJURY_SPEED
        self.vx += (want - self.vx) * WALK_TURN
        return True

    def _noise_tick(self, WL, HL) -> bool:
        """原版 Behavior.InvestigateSound（LizardAI.cs:1038-1042）：朝最后听到的响声走。"""
        if self.noise_t <= 0:
            return False
        self.noise_t -= 1
        dx, dy = self.noise_x - self.x, self.noise_y - self.y
        if math.hypot(dx, dy) < 24.0:
            self.noise_t = 0
            return False
        self.look_at = (self.noise_x, self.noise_y)
        want = clampf(dx * 0.06, -2.0, 2.0)
        self.vx += (want - self.vx) * WALK_TURN
        return True

    def _pack_tick(self, WL, HL) -> bool:
        """原版 Pack（黄蜥）：优先按**同伴广播的猎物情报**去各自的分工位置，
        其次才是跟住最近的同伴（旧版只有后者，所以看起来像「黄蜥喜欢扎堆」）。
        """
        obs = self.obs
        if self.alert is not None and self.alert.fresh(self._tick):
            gx = clampf(self.alert.x + flank_offset(self.id), WANDER_MARGIN,
                        max(WANDER_MARGIN, WL - WANDER_MARGIN))
            self.look_at = (self.alert.x, self.alert.y)
            if abs(gx - self.x) <= 10.0:
                return False                       # 已经站到自己的位置了
            want = clampf((gx - self.x) * 0.05, -2.2, 2.2)
            self.vx += (want - self.vx) * WALK_TURN
            return True
        best, bd = None, 1e9
        for o in obs["pack"]:
            if o.obj is self or o.dead:
                continue
            if o.dist < bd:
                best, bd = o, o.dist
        if best is None or bd <= PACK_GAP:
            return False
        self.look_at = (best.x, best.y)
        want = clampf((best.x - self.x) * 0.05, -2.0, 2.0)
        self.vx += (want - self.vx) * WALK_TURN
        return True

    def intent(self):
        """这只蜥蜴此刻盯上的东西 → (对象, 类型)；没有则 (None, "")。

        优先级：嘴里叼着的 → 我咬倒的猎物 → 同伴广播的猎物情报 → 当前目标。
        原版每只蜥蜴有自己的 PreyTracker，桌宠的猫得让开它盯上的猎物 —— 所以
        把它挂到和猫同一张认领板上（behavior/board.py 的 register_actor），
        「谁在追什么」全场只有一个说法。
        """
        if self.dead or self.state != ItemState.FREE:
            return (None, "")
        if self.carry_obj is not None:
            return (self.carry_obj, "hunt")
        if self.prey.owner is not None and self.prey.owns(self.prey.owner, self._tick):
            return (self.prey.owner, "hunt")
        if (self.alert is not None and self.alert.obj is not None
                and self.alert.fresh(self._tick)):
            return (self.alert.obj, "hunt")
        obj = self.target_obj
        return (obj, "hunt") if obj is not None else (None, "")

    def _pick_target(self, targets, prey=(), fight=None) -> None:
        """兼容入口：直接给「行 / (对象, 权重)」也能选目标（测试与旧调用在用）。

        真正的选择逻辑在 _choose_target：看得见的优先、别人咬倒的猎物不碰、
        失去视线时按记忆继续找。
        """
        obs = {"cats": tuple(self._entries(targets, "cat")),
               "prey": tuple(self._entries(prey, "prey")),
               "threats": (), "rivals": (), "pack": ()}
        rival = None
        if fight is not None:
            rival = (fight if isinstance(fight, Observation)
                     else self._observe(fight, getattr(fight, "x", self.x),
                                        getattr(fight, "y", self.y), "rival"))
        self._choose_target(obs, rival)

    def _lunge(self, kx, ky, d, HL) -> None:
        """朝目标加速；够近了就咬。

        loungeTendency 决定「冲刺倾向」：绿蜥 1.0 一发现猎物就全速冲，
        蓝蜥 0.01 基本是慢慢蹭过去（原版 LizardAI 用同一参数掷骰）。
        """
        sp = self.breed.base_speed * 0.8 * self.sprint
        acc = LUNGE_ACCEL
        if self.breed.charge_leap:
            # 青蜥蓄力弹射：扑击整段更快更猛（wiki：爬墙 + 蓄力弹射跳跃）
            sp *= CHARGE_LEAP_SPD
            acc = min(1.0, LUNGE_ACCEL * CHARGE_LEAP_ACC)
        self.vx += (kx * sp - self.vx) * acc
        reach = self.head_rad + (16.0 * self.breed.body_size_fac
                                 * (self.breed.attempt_bite_radius / 80.0))
        if d <= reach and self.bite_cd <= 0 and self.target_obj is not None:
            # 猫端着驯服食物送到嘴边（原版送礼）→ 先吃食不咬它
            if not _cat_offering_food(self.target_obj):
                self._start_bite()
        elif self._contact_floor and self.hop_cd <= 0 and (self.y - self.target[1]) > 34.0:
            self.vy = self._hop_vy()
            self.hop_cd = HOP_CD

    # ── 叼走死猫 / 昏迷猫到屏幕角落 ──
    def _bite_reach(self) -> float:
        """咬得着的距离（同 _lunge 里的 reach）。"""
        b = self.breed
        return self.head_rad + 16.0 * b.body_size_fac * (b.attempt_bite_radius / 80.0)

    def _mouth_point(self):
        """嘴前叼点：头轴正前方一个头半径。"""
        a = math.radians(self.head_angle)
        d = self.head_rad * CARRY_MOUTH_FAC
        return self.x + math.sin(a) * d, self.y - math.cos(a) * d

    def _best_carry(self, cats, WL=0.0, HL=None):
        """挑一只该叼的猫：昏迷优先于尸体，同档取最近的。

        原版猎物归属：**别人咬倒并占着的猎物不去抢**，路过的蜥蜴只接手没人管的
        那具；已经躺进巢穴里的尸体也不用再叼（省得来回甩）。
        """
        if HL is None:
            HL = self.y
        dens = virtual_dens(WL, HL, self.body_rad * HEAD_STAND_FAC) if WL else ()
        best = None
        for o in cats:
            if not (o.dead or o.fainted):
                continue
            if o.owner is not None and o.owner is not self:
                continue
            if o.dist > CARRY_NOTICE_R:
                continue
            if o.dead and (self.guard_obj is o.obj
                           or (dens and min(abs(o.x - d.x) for d in dens)
                               <= CARRY_DEN_ARRIVE_R)):
                continue
            key = (0 if o.fainted else 1, o.dist)
            if best is None or key < best[0]:
                best = (key, o)
        return best[1] if best is not None else None

    def _carry_intent(self, WL, HL):
        """要不要走搬运流程（原版 Behavior.ReturnPrey / CarryPrey）。"""
        obs = self.obs
        if self.carry_body is not None:
            o = next((c for c in obs["cats"] if c.obj is self.carry_obj), None)
            if o is None:
                self._release_carry()
                return None
            if not self._carry_keep(o):
                # 被玩家拽脱手（Lizard.cs:1386）或它自己醒了：松口
                self._release_carry(yanked=self._carry_lost(o))
                return None
            return "ReturnPrey"
        return "CarryPrey" if self._best_carry(obs["cats"], WL, HL) else None

    def _at_den(self, o, WL, HL) -> bool:
        """这具猎物是不是已经躺在某个巢穴里了。"""
        dens = virtual_dens(WL, HL, self.body_rad * HEAD_STAND_FAC)
        return min(abs(o.x - d.x) for d in dens) <= CARRY_DEN_ARRIVE_R

    def _carry_hurry(self, rivals) -> float:
        """回巢路上有同族靠近：举头警告；它比我强就加速跑（原版竞争）。"""
        rivals = self._as_obs(rivals, "rival")
        for o in rivals:
            if not o.visible or o.dist > WARN_R:
                continue
            self.warning_t = WARN_TICKS
            self.soc.note_resentment(o.obj, 0.15, self._tick)
            if self.soc.defers_to(o.obj, self._tick) or \
                    float(getattr(o.obj, "dominance", 0.5)) > self.dominance:
                return CARRY_HURRY
            return 1.0
        return 1.0

    def _begin_carry(self, obj, ox, WL=None, HL=None) -> None:
        """张嘴咬住（不造成伤害）并把这只猫叼起来，**这时定下回哪个巢穴**。"""
        body = getattr(obj, "body", None)
        chunk = getattr(body, "chunk0", None)
        if chunk is None:
            return
        self.carry_obj = obj
        self.carry_body = body
        stand = self.body_rad * HEAD_STAND_FAC
        self.carry_den = choose_den(WL if WL else self.x * 2.0,
                                    HL if HL is not None else self.y, stand, ox)
        self.carry_corner = self.carry_den.side
        self.prey.claim(obj, self._tick, fainted=True)   # 我叼住的猎物归我
        self.bite_event = None
        self.bite_hold = 0
        self._hold_cat()

    def _hold_cat(self) -> None:
        """把手里的猫钉在嘴前（pinned chunk 不积分不撞，其余链节自然垂下）。"""
        body = self.carry_body
        chunk = None if body is None else getattr(body, "chunk0", None)
        if chunk is None:
            self.carry_obj = self.carry_body = None
            return
        if not getattr(body, "dead", False) and getattr(body, "stun", 0) < CARRY_STUN_KEEP:
            body.stun = CARRY_STUN_KEEP          # 叼住＝挣不开，放下才恢复
        mx, my = self._mouth_point()
        chunk.pinned = True
        chunk.x = mx
        chunk.y = my
        chunk.vx = chunk.vy = 0.0

    def _release_carry(self, yanked: bool = False) -> None:
        """松口（放下 / 被击晕 / 自己死了 / 玩家把猎物拽出来）。

        yanked=True 是原版 LoseAllGrasps 那条路（Lizard.cs:1386）：除了解钉，还要
        撤掉「叼住＝挣不开」那点强制昏迷 —— 原版靠 pacifying grasp 压住玩家，桌宠
        用 CARRY_STUN_KEEP 顶替，松口就得一起收掉（只收这一档，真被咬狠了的长眩晕留着）。
        """
        body = self.carry_body
        chunk = None if body is None else getattr(body, "chunk0", None)
        if chunk is not None:
            chunk.pinned = False
            chunk.vx = self.vx * 0.5
            chunk.vy = 0.0
        if yanked and body is not None:
            if 0 < getattr(body, "stun", 0) <= CARRY_STUN_KEEP:
                body.stun = 0
        self.carry_obj = None
        self.carry_body = None
        self.carry_corner = 0

    def _carry_grab_chunk(self, o):
        """这只猎物身上正被鼠标抓着的那一截（没人抓 → None）。"""
        beh = getattr(getattr(o, "obj", None), "behavior", None)
        grab = getattr(beh, "grab", None)
        chunk = getattr(grab, "chunk", None)
        body = self.carry_body
        if grab is None or chunk is None or body is None:
            return None
        if not grab.active or chunk not in (body.chunk0, body.chunk1):
            return None
        return chunk

    def _carry_lost(self, o) -> bool:
        """原版 Lizard.cs:1386：猎物被抓的那一截离嘴前锚点超过 70 + 该截 rad → 脱手。"""
        chunk = self._carry_grab_chunk(o)
        if chunk is None:
            return False
        mx, my = self._mouth_point()
        return (math.hypot(chunk.x - mx, chunk.y - my)
                > CARRY_LOSE_DIST + float(getattr(chunk, "rad", 0.0)))

    def _carry_keep(self, o) -> bool:
        """这一 tick 还该继续叼着吗（原版 CarryObject 的 grasps[0] 还在不在）。

        尸体 / 昏迷：一路叼回巢穴。玩家用鼠标抓着的：没拽过距离上限就继续叼
        （`_hold_cat` 会把它拽回嘴边），拽过头就按 Lizard.cs:1386 脱手；
        真醒过来的（既没昏迷也没被鼠标抓着）照样松口。
        """
        if self._carry_lost(o):
            return False
        return bool(o.dead or o.fainted) or self._carry_grab_chunk(o) is not None

    def _carry_tick(self, WL: float, HL: float) -> bool:
        """Behavior.ReturnPrey：把咬倒的猎物叼回**锁定的那个巢穴**。

        巢穴在开始搬运的那一刻就定下来（原版抓到猎物选 den，之后一路走到底），
        不会走到屏幕中间又换成另一侧；到了就放下，尸体在原地守一会儿，昏迷的
        在巢穴里咬死。路上有同族靠近就举头警告并加速回巢。
        """
        obs = self.obs
        stand = self.body_rad * HEAD_STAND_FAC
        if self.carry_body is not None:
            o = next((c for c in obs["cats"] if c.obj is self.carry_obj), None)
            if o is None:
                self._release_carry()             # 目标没了（被清场 / 转世）
                return False
            if not self._carry_keep(o):
                # 被玩家拽脱手（Lizard.cs:1386）或醒了：松口，回去当普通猎物
                self._release_carry(yanked=self._carry_lost(o))
                return False
            self.prey.refresh(self._tick)
            if self.carry_den is None:
                self.carry_den = choose_den(WL, HL, stand, o.x)
                self.carry_corner = self.carry_den.side
            den = self.carry_den
            if abs(den.x - self.x) <= CARRY_DEN_ARRIVE_R:
                was_dead = bool(o.dead)
                self._release_carry()
                self.prey.delivered(self._tick)
                if was_dead:                       # 尸体：在巢穴边守一会儿
                    self.guard_obj, self.guard_t = o.obj, GUARD_PREY_TICKS
                return True                        # 这一 tick 用来放下
            hurry = self._carry_hurry(obs["rivals"])
            want = clampf((den.x - self.x) * 0.05, -1.8, 1.8) * CARRY_SPEED_FAC * hurry
            self.vx += (want - self.vx) * WALK_TURN
            self._hold_cat()
            self.look_at = (den.x, HL - 12.0)
            return True
        pick = self._best_carry(obs["cats"], WL, HL)
        if pick is None:
            return False
        if pick.fainted and not pick.dead and self._at_den(pick, WL, HL):
            # 已经在巢穴里躺着了：直接咬死（原版咬死猎物，而不是再叼一趟）
            self.target, self.target_obj = (pick.x, pick.y), pick.obj
            self.look_at = (pick.x, pick.y)
            dx, dy = pick.x - self.x, pick.y - self.y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                self._lunge(dx / d, dy / d, d, HL)
            return True
        dx, dy = pick.x - self.x, pick.y - self.y
        d = math.hypot(dx, dy)
        if d <= self._bite_reach():
            self._begin_carry(pick.obj, pick.x, WL, HL)
            return True
        self.target, self.target_obj = (pick.x, pick.y), pick.obj
        self.look_at = (pick.x, pick.y)
        if d > 1e-6:
            self._lunge(dx / d, dy / d, d, HL)     # 走过去叼（够不着不会触发咬）
        return True

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

    def _start_bite(self, obj=None) -> None:
        """原版 Lizard.cs:1238：按 biteDamageChance 掷骰，命中则 biteDamage * Lerp(0.8,1.2,rand)。

        obj 给 casual 撕咬用（原版 casualAggressionTarget 不是当前猎物目标）。
        """
        if obj is None:
            obj = self.target_obj
        self.bite_hold = BITE_HOLD
        self.bite_cd = COOLDOWN_TICKS
        self.jaw = 1.0
        b = self.breed
        dmg = 0.0
        if b.bite_damage_chance >= 1.0 or self.rng.random() < b.bite_damage_chance:
            dmg = b.bite_damage * lerp(0.8, 1.2, self.rng.random())
        self.bite_event = (obj, dmg)
        self.vx *= 0.2

    def _wander(self, WL, HL) -> None:
        """游走：定一个近处落点，走到／超时就换，再歇一会儿。

        白蜥/蝾螈走原版 LurkTracker（LizardAI.cs:85-216，utility 权重 0.3-0.4）：
        伏击型，原地待机时间是别人的 LURK_IDLE_MULT 倍。
        """
        self.lurk = self.breed.key in ("white", "salamander")
        self.idle_timer -= (1.0 / LURK_IDLE_MULT) if self.lurk else 1.0
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

    def stuck_frames(self):
        """给「扎在身上的矛」用的局部坐标系：头 + 每节 (x, y, 朝向角)。

        朝向角 = 该节相对前一节的方向（头取 seg[0]→头）。身体弯曲 / 转身时，
        插在身上的矛跟着该节一起转，而不是只跟着整体平移。
        """
        out = [(self.x, self.y,
                _ang_from_up(self.x - self.seg[0].x, self.y - self.seg[0].y))]
        px, py = self.x, self.y
        for sg in self.seg:
            out.append((sg.x, sg.y, _ang_from_up(sg.x - px, sg.y - py)))
            px, py = sg.x, sg.y
        return out

    def _track_head(self) -> None:
        """咬合期把头锁在目标方向。"""
        if self.target is not None:
            self.look_at = self.target

    def _look_rate(self) -> float:
        """头转向速率：扑咬/对峙最快、追猎次之、闲逛最慢（原版头绳索刚度随行为变）。"""
        if self.bite_hold > 0 or self.stage in ("Attack", "FightRival"):
            return HEAD_LOOK_FAST
        if self.stage in ("HuntPrey", "ApproachPrey", "Flee", "Injured", "Warn",
                          "CarryPrey", "ReturnPrey"):
            return HEAD_LOOK_ALERT
        return HEAD_LOOK_SLOW

    def _jaw_target(self) -> float:
        """下颚目标开度（0 闭 / 1 全张）。

        原版下颚是**独立动画通道**：叫声、咬合、叼猎物各驱动一段，而不是
        「一进追猎就一路张着嘴」（旧实现就是这么干的：HuntPrey 全程 +0.22/tick）。
        语义：
          死 / 眩晕 / 游走 / 观望            → 0.0
          追猎锁定 HuntPrey / ApproachPrey  → 0.0（盯着，不张嘴）
          咬合保持 bite_hold > 0             → 1.0
          叼猎物 / 守巢                     → 0.75
          威吓同类 Warn                      → 0.55
          扑咬出手 Attack                    → 0.35
          被拎着挣扎                        → 0.5
        """
        if self.dead or self.stun > 0:
            return 0.0
        if self.bite_hold > 0:
            return 1.0
        if self.state == ItemState.MOUSE:
            return 0.5
        st = self.stage
        if st in ("CarryPrey", "ReturnPrey", "GuardPrey"):
            return 0.75
        if st == "Warn":
            return 0.55
        if st == "Attack":
            return 0.35
        if st == "CasualBite":
            return 0.45
        return 0.0

    def _look_lift(self) -> float:
        """注视角的竖向分量：目标在上 → +1（抬头），在下 → -1（低头）。"""
        if self.dead or self.look_at is None:
            return 0.0
        dx, dy = self.look_at[0] - self.x, self.look_at[1] - self.y
        d = math.hypot(dx, dy) or 1.0
        return clampf(-dy / d, -1.0, 1.0)

    def _step_head(self) -> None:
        if not self.dead:
            nx, ny = self.seg[0].x, self.seg[0].y
            want = None
            if self.look_at is not None:
                vx, vy = self.look_at[0] - nx, self.look_at[1] - ny
                if math.hypot(vx, vy) > 0.5:          # 目标贴在颈上时不改朝向
                    want = _ang_from_up(vx, vy)
            elif self.state == ItemState.MOUSE:
                if abs(self.vx) + abs(self.vy) > 0.4:  # 被拎着：头随拖拽方向
                    want = _ang_from_up(self.vx, self.vy)
            else:
                # 没有观察目标时，头跟随行走方向，不再从头与第0节的瞬时几何位置猜方向。
                want = 90.0 if self.chain_dir > 0.0 else 270.0
            if want is not None:
                self.head_angle = _ang_lerp(self.head_angle, want, self._look_rate())
            self.head_driven = True
        else:
            self.head_angle = _ang_lerp(self.head_angle, 90.0 * self.facing, 0.04)
        # facing 是移动方向状态，不再从“头相对第0节的位置”反推。
        # 头可以独立回头看；只有明确的水平移动才改变实际行进朝向。
        if abs(self.vx) > TURN_VX:
            self.facing = 1 if self.vx > 0.0 else -1
        # 下颚：单一目标 + 开/闭双速率（原版 jaw 是独立通道，不是「追猎就一路张着」）
        target = self.anim.jaw_open if self.anim is not None else self._jaw_target()
        rate = JAW_OPEN_RATE if target > self.jaw else JAW_CLOSE_RATE
        self.jaw = clampf(self.jaw + clampf(target - self.jaw, -rate, rate), 0.0, 1.0)

    def _intent(self) -> LizardAnimIntent:
        """按当前 stage 生成动画意图 —— AI 与动画之间唯一的映射点（品种不进这层）。"""
        it = self.anim
        it.look_at = self.look_at
        it.jaw_open = self._jaw_target()
        it.look_lift = self._look_lift()
        it.alert = it.aggression = it.fear = 0.0
        it.body_compress = it.body_raise = 0.0
        it.locomotion = "idle"
        if self.dead or self.stun > 0:
            it.jaw_open = 0.0
            it.look_lift = 0.0
            return it
        st = self.stage
        if st in ("CarryPrey", "ReturnPrey", "GuardPrey"):
            it.locomotion, it.alert = "carry", 0.5
        elif st == "Warn":
            it.aggression, it.body_raise, it.alert = 0.7, 1.0, 0.6
        elif st in ("Attack", "FightRival"):
            it.aggression, it.body_compress, it.alert = 0.9, 0.3, 0.8
            it.locomotion = "run"
        elif st in ("HuntPrey", "ApproachPrey", "InvestigatePos"):
            it.alert, it.aggression = 0.5, 0.4
            it.locomotion = "run" if self.sprint else "walk"
        elif st == "Flee":
            it.fear, it.body_compress, it.alert = 1.0, 0.5, 0.9
            it.locomotion = "run"
        elif st == "Injured":
            it.fear, it.body_compress, it.alert = 0.7, 0.6, 0.7
            it.locomotion = "walk"
        elif st == "Lurk":
            it.locomotion, it.body_compress, it.alert = "lurk", 0.5, 0.4
        elif st in ("Wander", "FollowFriend", "PackCoordination", "CasualBite"):
            it.locomotion = "walk"
        it.turn = clampf(self.vx - self._last_vx, -2.0, 2.0)
        return it

    # ── 链体 ──
    def _step_depth(self) -> None:
        """原版 LizardGraphics.Update 的 depthRotation / headDepthRotation。

        原版这两个量由四肢相对躯干连线的深度推导（limbs[i].connection 与
        rotationChunk），2D 宠物里没有 z 轴，等价量就是「身体朝向观众的程度」：
        平时 = 朝向的负号（朝右 -1 / 朝左 +1，见 LizardGraphics.Update 的 swim 分支），
        侧视时 |depth|=1 → 头取正侧面贴图行 0；转身时从 -1 扫到 +1，
        中途 |depth|→0，头依次经过行 3/2/1 的正面、斜前贴图 —— 原版蜥蜴转身时
        头「从一侧抬起、绕过身体转到另一侧」正是这个扫描过程。
        Sign(depth) 同时是头部 5 片的水平镜像（原版 scaleX = Sign(num)）。
        """
        self.last_depth = self.depth
        # 原版 depthRotation 由四条腿相对体轴的侧别求和得到（LizardGraphics.Update
        # 的 num8 = clamp(sum(Sign(num11)))，在 _step_legs 里算好放进 depth_in）；
        # 眩晕时冻结（!Stunned || rotateWhileStunned）。
        if self.stun <= 0:
            self.depth = lerp(self.depth, self.depth_in, DEPTH_LERP)
        self.last_head_depth = self.head_depth
        # f2 = InverseLerp(0, 0.6, |dot((lookPos - 躯干0), (头 - 躯干0))|)（原版同名量）
        s0 = self.seg[0]
        hx, hy = self.x - s0.x, self.y - s0.y
        hl = math.hypot(hx, hy) or 1.0
        lx, ly = self.look_at if self.look_at is not None else (self.x, self.y)
        vx, vy = lx - s0.x, ly - s0.y
        vl = math.hypot(vx, vy) or 1.0
        f2 = inv_lerp(0.0, 0.6, abs((hx / hl) * (vx / vl) + (hy / hl) * (vy / vl)))
        self.head_depth = lerp(self.head_depth, self.depth * f2, HEAD_DEPTH_LERP)
        # 转身中支起上半身（|depth| 越小 = 越正对镜头 = 转得越狠）
        # 再叠上「视觉注意方向」（目标在上→颈抬高）与动画意图的支起/压低。
        if self.dead:
            self.turn_lift = 0.0
            return
        lift = TURN_LIFT * (1.0 - min(1.0, abs(self.depth)))
        lift += max(0.0, self.anim.look_lift) * LOOK_LIFT
        lift += self.anim.body_raise * BODY_RAISE_LIFT
        lift -= self.anim.body_compress * BODY_COMPRESS_DIP
        self.turn_lift = max(0.0, lift)

    def _head_dir(self):
        """颈→头的单位方向（原版 HeadRotation，花纹前段用）。"""
        s0 = self.seg[0]
        dx, dy = self.x - s0.x, self.y - s0.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return (1.0, 0.0)
        return (dx / d, dy / d)

    def _cosmetic_spine(self):
        """渲染用的脊柱折线（与 lizard_gfx.draw_lizard 同一套几何）。"""
        hx = self.x + (self.seg[0].x - self.x) * 0.2
        hy = self.y + (self.seg[0].y - self.y) * 0.2
        spine = [(hx, hy)]
        rads = [self.body_rad * lizard_cos.NECK_RAD_K]
        n_body = sum(1 for s in self.seg if not s.tail)
        n_tail = len(self.seg) - n_body
        for k, s in enumerate(self.seg):
            bob = self.bob[k] if k < len(self.bob) else 0.0
            spine.append((s.x, s.y + bob))
            r = s.rad
            if not s.tail:
                r *= (0.94, 1.06, 1.00)[min(k, 2)]
            elif n_tail:
                t = (k - n_body + 1) / float(n_tail)
                r *= 1.0 - 0.30 * t * t
            rads.append(r)
        return spine, rads

    def _step_cosmetics(self) -> None:
        """花纹物理（原版 LizardCosmetics.LongBodyScales.Update 的移植）。

        每片鳞是一根挂在体表的摆锤：角度弹簧把它拉向「体表外法线 ↔ 体轴后掠」的
        混合方向，`ConnectToPoint(push=True)` 再把鳞尖钉在距附着点 length 的圆上，
        于是转身/急停/落地时鳞片会滞后摆一下，而不是硬贴在身上。
        """
        if not self.cosmetic_pts:
            return
        spine, rads = self._cosmetic_spine()
        depth = self.depth
        sgn = 1.0 if depth >= 0.0 else -1.0
        hdx, hdy = self._head_dir()
        for ci, c in enumerate(self.cosmetics):
            st = self.cosmetic_pts[ci]
            if not st:
                continue
            rigor = c.rigor
            stiff = 1.0 / lerp(5.0, 1.5, rigor)
            damp = lerp(1.0, 0.8, rigor)
            for ii, inst in enumerate(c.insts):
                x, y, length = inst[0], inst[1], inst[2]
                back = inst[5] if len(inst) > 5 else 0.5
                pos, (nx, ny), rad, (tx, ty) = lizard_cos.spine_at(
                    spine, rads, y, True)
                f = lizard_cos.depth_f(y, depth)
                k = clampf(abs(f) - sgn * x, -1.0, 1.0)
                ox = pos[0] + nx * (k * rad)
                oy = pos[1] + ny * (k * rad)
                # a = Lerp(体轴, 体表外法线, |f|) + 前段往头侧压 + 后掠混合
                off = k * rad
                if abs(off) > 1e-6:
                    ux, uy = nx * (1.0 if off >= 0.0 else -1.0),                              ny * (1.0 if off >= 0.0 else -1.0)
                else:
                    ux, uy = nx, ny
                ax = lerp(tx, ux, abs(f))
                ay = lerp(ty, uy, abs(f))
                if y < 0.2:
                    kk = 2.0 * (1.0 - y / 0.2) ** 2
                    ax -= hdx * kk
                    ay -= hdy * kk
                ax = lerp(ax, tx, back)
                ay = lerp(ay, ty, back)
                n = math.hypot(ax, ay) or 1.0
                tgx = ox + (ax / n) * length
                tgy = oy + (ay / n) * length
                s = st[ii]
                d = math.hypot(tgx - s[0], tgy - s[1])
                if s[4] == 0.0 and s[5] == 0.0 and d > length * 0.5:
                    s[0], s[1] = tgx, tgy          # 第一次定位：直接摆到目标
                    s[2] = s[3] = 0.0
                    s[4], s[5] = tgx, tgy
                    continue
                dx, dy = tgx - s[0], tgy - s[1]
                d = math.hypot(dx, dy)
                if d > length * 0.5:               # 目标太远：先追一半（原版 DistLess）
                    pull = d - length * 0.5
                    ux2, uy2 = dx / d, dy / d
                    s[0] += ux2 * pull
                    s[1] += uy2 * pull
                    s[2] += ux2 * pull
                    s[3] += uy2 * pull
                    dx, dy = tgx - s[0], tgy - s[1]
                    d = math.hypot(dx, dy)
                if d > 10.0:                       # ClampMagnitude(target-pos, 10)
                    dx *= 10.0 / d
                    dy *= 10.0 / d
                s[2] += dx * stiff
                s[3] += dy * stiff
                s[2] *= damp
                s[3] *= damp
                # 速度限幅：原版靠「身体不会瞬移」隐含成立；桌宠有生成/传送/被拖拽，
                # 不限制会让鳞尖以几十 px/tick 甩出去（方向瞬间翻转）。
                vmax = 4.0 if length < 4.0 else length
                vm = math.hypot(s[2], s[3])
                if vm > vmax:
                    s[2] *= vmax / vm
                    s[3] *= vmax / vm
                s[4], s[5] = s[0], s[1]             # lastPos（渲染插值用）
                s[0] += s[2] * 0.9                  # LizardScale.Update：空气阻尼 + 积分
                s[1] += s[3] * 0.9
                s[2] *= 0.9
                s[3] *= 0.9
                # ConnectToPoint(outer, length, push: true)：把鳞尖钉在距附着点 length
                # 的圆上（原版 vector = DirVec(pos, outer) * (length - rd)，pos -= vector），
                # 同时扣掉速度的径向分量 —— 摆锤只剩切向摆动，方向不会跳变。
                rx, ry = s[0] - ox, s[1] - oy
                rd = math.hypot(rx, ry) or 1.0
                cx = rx / rd * (length - rd)
                cy = ry / rd * (length - rd)
                s[0] += cx
                s[1] += cy
                s[2] += cx
                s[3] += cy

    def _step_chain(self, HL) -> None:
        """躯干+尾：逐行移植 BodyChunk.Update + BodyChunkConnection.Update。

        原版蜥蜴是 3 个自由 BodyChunk（gravity 0.9 / airFriction 0.999）用
        BodyChunkConnection(Normal, elasticity 0.95, weightSymmetry 0.5) 串起来，
        头由 head.ConnectToPoint 挂在 chunk0 前方 12*headSize 处。
        这里头仍是 AI 驱动点（被 _integrate 落到地面/墙面），躯干按同样的
        「重力速度积分 → 杆长约束 → 落地」三步走，长度约束只消掉径向误差，
        所以切向速度会保留 —— 转身/被拖时身体自然甩过去，不会卡成竖条或
        飘在头的上方。
        """
        held = self.state == ItemState.MOUSE or self.hauled
        # 方向带记忆：只有真正走出速度才翻面；否则停稳瞬间的
        # ±0.0x 抖动会把躯干甩到头前面，看起来就是「朝反方向走」。
        if abs(self.vx) > TURN_VX and self.vx * self.chain_dir < 0.0:
            self.chain_dir = 1.0 if self.vx > 0.0 else -1.0
        grav = SEG_GRAV * (1.35 if held else 1.0) * self.room_gravity
        align = SEG_ALIGN_HELD if held else SEG_ALIGN
        conn = SEG_CONN_HELD if held else SEG_CONN_ELASTICITY
        # ① BodyChunk.Update：vel 受重力、乘空气阻力，pos += vel
        for s in self.seg:
            s.vy += grav
            s.vx *= SEG_AIR_FRIC
            s.vy *= SEG_AIR_FRIC
            s.x += s.vx
            s.y += s.vy
        ax0 = [s.x for s in self.seg]
        ay0 = [s.y for s in self.seg]
        # 原版里是 bodyChunks[0] 被 AI 推着走、头被 head.ConnectToPoint 拉到头前方
        # 12*headSize；这里反过来：头是 AI 驱动点，躯干 0 挂在「头后方 head_conn」的
        # 锚点上 —— 拓扑等价，效果就是头永远在最前面、身体永远拖在后面（不会倒着走）。
        #    锚点的几何与旧版一致（头后方 head_conn）。但 chain_dir 一翻面，锚点就会
        #    瞬移到头的另一侧（差 2*head_conn ≈ 半个身位），整条躯干被一起拽过去 ——
        #    用户报的「转身时身体碰撞体积出错」就是这个瞬移。这里锚点改用 chain_dir 的
        #    低通值：转身时它平滑地滑过头顶（滑到中间时与头重合），一圈走完几何照旧，
        #    不再是「啪」地跳到另一侧；静止时它恒等于 chain_dir，链形支撑与旧版相同。
        c = getattr(self, "_ax_c", float(self.chain_dir))
        c += (self.chain_dir - c) * BODY_AX_LERP
        self._ax_c = c
        anc_x = self.x - c * self.head_conn
        anc_y = self.y
        # ② BodyChunkConnection + 顺直软约束：
        #    杆长约束只消掉径向误差，光靠它链子会自己折回来（两节各自满足距离但
        #    朝向反了）。原版 3 个 chunk 有质量互相顶、尾节还有 tailStiffness 撑直。
        #    旧实现在这里把「父节方向」的种子写死成水平（-chain_dir, 0），等于每帧
        #    强行把整条身体摊平到水平线 —— 身体因此呆滞、不会自然弯曲。现在种子取
        #    「锚点→第 0 节」的当前朝向（连续性），顺直只负责撑住，不负责摆正。
        seed_x, seed_y = _dirvec(self.seg[0].x - anc_x, self.seg[0].y - anc_y)
        w = 1.0 - abs(c)                       # 0＝没在转身，1＝锚点正滑过头顶
        if w > 0.0:
            #    转身半途把「头后方」的指令方向混进种子里：光靠平滑的锚点，链子会
            #    原地不动被头拖着走（看起来倒着走），depth 也不会扫过中间几行；
            #    混入之后身体是按转身进度「滑」到另一侧的，不是被瞬间甩过去。
            cb = -1.0 if c >= 0.0 else 1.0
            seed_x = seed_x * (1.0 - w) + cb * w
            seed_y *= (1.0 - w)
        if abs(seed_x) < 1e-6 and abs(seed_y) < 1e-6:
            seed_x, seed_y = -self.chain_dir, 0.0
        sn = math.hypot(seed_x, seed_y) or 1.0
        seed_x, seed_y = seed_x / sn, seed_y / sn
        for _ in range(SEG_SOLVER_ITER):
            prev_x, prev_y = anc_x, anc_y
            dir_x, dir_y = seed_x, seed_y
            for s in self.seg:
                s.x += (prev_x + dir_x * s.dist - s.x) * align
                s.y += (prev_y + dir_y * s.dist - s.y) * align
                dx, dy = s.x - prev_x, s.y - prev_y
                d = math.hypot(dx, dy)
                if d > 1e-6:
                    k = (d - s.dist) * conn / d
                    s.x -= dx * k
                    s.y -= dy * k
                    nl = math.hypot(s.x - prev_x, s.y - prev_y) or 1.0
                    dir_x, dir_y = (s.x - prev_x) / nl, (s.y - prev_y) / nl
                # ③ 落地（原版 PushOutOfTerrain + bounce）
                lim = HL - s.rad * (TAIL_SINK_FAC if s.tail else BODY_STAND_FAC)
                if s.y > lim:
                    s.y = lim
                prev_x, prev_y = s.x, s.y
        # ②b 连接平滑：原版 chunk 之间有质量互顶，链子不会出现尖角；杆长约束
        #     只保证「相邻节距离对」，留下的小折角在这里抹平（拖动时不抹，保住手感）。
        # 连接平滑移到渲染层，物理节点在长度约束后不再被二次拉坏。
        # ③ 转向惯性：速度突变（转身/扑出）时身体往转向侧甩 ——
        #    头一节弯得最多、后面依次减少、尾巴最后才跟过来（原版靠 chunk 质量惯性）。
        turn = self.vx - self._last_vx
        self._last_vx = self.vx
        if not held and abs(turn) > SEG_BEND_MIN_VX:
            bend = clampf(turn * SEG_BEND_K, -SEG_BEND_MAX, SEG_BEND_MAX)
            n_seg = len(self.seg)
            for k, s in enumerate(self.seg):
                t = k / max(1, n_seg - 1)
                s.y -= bend * (1.0 - t) ** 2
                lim = HL - s.rad * (TAIL_SINK_FAC if s.tail else BODY_STAND_FAC)
                if s.y > lim:
                    s.y = lim
        # ④ 速度 = 本 tick 的实际位移：约束消掉的只是径向分量，切向动量得以保留
        for k, s in enumerate(self.seg):
            s.vx = s.x - ax0[k]
            s.vy = s.y - ay0[k]
            spd = math.hypot(s.vx, s.vy)
            if spd > MAX_SEG_SPEED:
                q = MAX_SEG_SPEED / spd
                s.vx *= q
                s.vy *= q
        # ⑤ 步态波浪：躯干随步频起伏、尾梢额外摆动（原版由左右腿交替驱动 drawPositions）
        if self.state != ItemState.MOUSE:
            self.walk_phase = (self.walk_phase + 0.015 + abs(self.vx) * 0.010) % 1.0
            amp = clampf(abs(self.vx) / max(0.5, self.breed.base_speed), 0.0, 1.0)
            n_seg = len(self.seg)
            for i, s in enumerate(self.seg):
                t = i / max(1, n_seg - 1)
                ph = self.walk_phase * math.tau + i * 0.7
                s.y -= math.sin(ph) * GAIT_WAVE * amp * (1.0 - 0.5 * t)
                if s.tail:
                    s.y -= math.sin(ph) * (0.16 * s.rad * 0.5) * (0.4 + 0.6 * amp)
                # 步态波浪在约束之后仍可能把尾节重新推入地面；最后再封一次，
                # 保证每个身体 chunk 返回时都在真实窗口地板之上。
                lim = HL - s.rad * (TAIL_SINK_FAC if s.tail else BODY_STAND_FAC)
                if s.y > lim:
                    s.y = lim
                    if s.vy > 0.0:
                        s.vy = 0.0

    # ── 腿 ──
    def _step_legs(self, room_hl) -> None:
        """四足：逐行移植 LizardLimb.Update + Limb.Update（屏幕系 y↓，60 tick/秒）。

        要点（与原版一一对应）：
          jointDist = 25*(sizeFac+1)/2
          a = normalize(Lerp(DirVec(rotationChunk→髋), DirVec(髋→limbsAimFor), 0.4))
          num = DistanceToLine(脚, 髋, 髋+Perp(a)) == -dot(a, 脚-髋)（屏幕叉积换算来的）
          迈步触发：num < jointDist * (-StepLength)，StepLength = Lerp(-0.5,0.5,stepLength)
          绝对猎点：Lerp(脚, 髋, liftFeet) + a*(jointDist+1)；踩住时 FindGrip 锁定世界坐标
          腿长硬上限：ConnectToPoint(髋, jointDist)（原版 BodyPart.ConnectToPoint）
        """
        b = self.breed
        joint = LEG_JOINT * ((b.body_size_fac + 1.0) * 0.5) * BODY_SCALE
        hunt = b.limb_speed
        quick = b.limb_quickness
        lift = b.lift_feet
        step_len = lerp(-0.5, 0.5, b.step_length)         # StepLength（health = 1）
        floor = room_hl - LEG_LIMB_RAD
        stunned = self.stun > 0
        # limbsAimFor：原版是行进目标格中心，宠物里取躯干前方一点
        self.limbs_aim = (self.x + self.chain_dir * LEG_AIM_AHEAD, self.y)
        grip = [0, 0, 0, 0]
        num8 = 0.0
        for i, lg in enumerate(self.legs):
            pi = lg.pair if lg.pair < len(self.seg) else len(self.seg) - 1
            hip = self.seg[pi]
            hx, hy = hip.x, hip.y
            # rotationChunk：前对看最后一节、后对看第一节（原版 legPair 对侧）
            rj = 2 if pi <= 1 else 0
            rj = rj if rj < len(self.seg) else len(self.seg) - 1
            rx, ry = self.seg[rj].x, self.seg[rj].y
            ux, uy = _dirvec(hx - rx, hy - ry)
            if pi >= 2:
                ux, uy = -ux, -uy          # 原版：connection.index == 2 时 a *= -1
            vx, vy = _dirvec(self.limbs_aim[0] - hx, self.limbs_aim[1] - hy)
            ax, ay = _dirvec(ux + (vx - ux) * 0.4, uy + (vy - uy) * 0.4)
            # 原版 num = DistanceToLine(脚, 髋, 髋+Perp(a)) == -(脚-髋)·a
            # （DistanceToLine 的 l1 在最后一位：l1=髋+Perp(a)、l2=髋）。
            num = -(ax * (lg.x - hx) + ay * (lg.y - hy))
            if stunned:
                lg.disabled = True
                lg.reaching = False
                lg.grip = 0
                lg.planted = False
                lg.vy += 0.9                             # 原版 vel.y -= 0.9f（y↑）→ 屏幕 +
            else:
                lg.disabled = False
                if not lg.reaching:
                    lg.abs_x = lg.x + (hx - lg.x) * lift + ax * (joint + 1.0)
                    lg.abs_y = lg.y + (hy - lg.y) * lift + ay * (joint + 1.0)
                    if num < joint * (-step_len):
                        lg.reaching = True
                elif not _dist_less(lg.x, lg.y, lg.abs_x, lg.abs_y, LEG_LIMB_RAD + 1.0):
                    # 还没踩到猎点：朝地形伸（FindGrip 的宠物版＝把落点压到地面/墙）
                    k = (6.0 - 12.0 * (i % 2)) * 0.2
                    px_, py_ = ay * k, -ax * k                 # Perp_screen(dx,dy) = (dy,-dx)
                    ax += px_
                    ay += py_
                    ay += 0.3 * b.feet_down                    # 原版 a.y -= 0.3*feetDown
                    ax += (-1.0 if i % 2 == 0 else 1.0) * b.leg_pair_disp * lg.flip
                    gx = hx + ax * (joint - 1.0)
                    # FindGrip 的宠物版：本窗口只有「地面 + 左右墙」，
                    # 于是落点 = 髋正前方 (joint-1) 处压到地面，再夹进 joint-1 半径内
                    # （原版 FindGrip 也只取 maximumRadiusFromAttachedPos 内的地形格）。
                    support_y = (self.terrain.floor_under(gx, hy)
                                 if self.terrain is not None else room_hl)
                    gy = support_y - LEG_LIMB_RAD
                    gdx, gdy = gx - hx, gy - hy
                    gd = math.hypot(gdx, gdy)
                    rmax = joint - 1.0
                    if gd > rmax:
                        # 原版 FindGrip 找不到 jointDist 范围内的地形时，
                        # 不会生成一个虚假的悬空落点；本次伸脚直接失败，下一帧重算。
                        lg.abs_x, lg.abs_y = lg.x, lg.y
                        lg.reaching = False
                        lg.snap = False
                        lg.grip = 0
                    else:
                        lg.abs_x, lg.abs_y = gx, gy
                else:
                    if (num > joint * -0.5 * (b.step_length + 0.1)
                            and not _dist_less(lg.x, lg.y, hx, hy, joint - 1.0)
                            and not _dist_less(lg.abs_x, lg.abs_y, hx, hy, joint)):
                        lg.reaching = False
                        lg.planted = False
            # ── Limb.Update ──
            if lg.planted:
                lg.abs_x, lg.abs_y = lg.x, lg.y
                lg.vx = lg.vy = 0.0
                lg.snap = True
            elif _dist_less(lg.abs_x, lg.abs_y, lg.x, lg.y, hunt):
                lg.vx = lg.abs_x - lg.x
                lg.vy = lg.abs_y - lg.y
                lg.snap = True
            else:
                ddx, ddy = _dirvec(lg.abs_x - lg.x, lg.abs_y - lg.y)
                lg.vx += (ddx * hunt - lg.vx) * quick
                lg.vy += (ddy * hunt - lg.vy) * quick
                lg.snap = False
            if not stunned:
                lg.x += lg.vx
                lg.y += lg.vy
                lg.vx *= LEG_AIR_FRIC
                lg.vy *= LEG_AIR_FRIC
                leg_floor = (self.terrain.floor_under(lg.x, lg.y)
                             - LEG_LIMB_RAD if self.terrain is not None else floor)
                if lg.y > leg_floor:                         # PushOutOfTerrain
                    lg.y = leg_floor
                    if lg.vy > 0.0:
                        lg.vy = 0.0
            # ── ConnectToPoint(髋, jointDist)：腿长硬上限（脚不会被甩飞）──
            ddx, ddy = lg.x - hx, lg.y - hy
            dd = math.hypot(ddx, ddy)
            if dd >= joint and dd > 1e-6:
                over = dd - joint
                ux, uy = ddx / dd, ddy / dd
                lg.x -= ux * over
                lg.y -= uy * over
                lg.vx -= ux * over
                lg.vy -= uy * over
            # ── flip（原版 LizardGraphics.cs:1209-1215）──
            # num11 = DistanceToLine(脚, connection.pos, rotationChunk.pos)；
            # 本式算出的值 = -原版值（屏幕 y↓），所以符号规则与原版一致：i<2 取负。
            # 朝右时四腿 num11 全为负 → num8=-1 → depthRotation=-1 → 头 scaleX=-1。
            num11 = _leg_flip_num(i, hx, hy, rx, ry, lg)
            lg.flip = lerp(lg.flip, 1.0 if num11 < 0.0 else -1.0, 0.3)
            if abs(num11) > LEG_DEPTH_MIN:
                num8 += 1.0 if num11 > 0.0 else -1.0
            # ── gripCounter ──
            # 原版 gripCounter 只在脚已经到达 FindGrip 的绝对位置、并且
            # 当前位置仍贴着实际地形时才累计。脚悬空就不算支撑。
            grounded = False
            if not stunned and lg.reaching:
                near_grip = lg.snap or _dist_less(
                    lg.x, lg.y, lg.abs_x, lg.abs_y, LEG_LIMB_RAD + 1.0)
                if near_grip:
                    gy = (self.terrain.floor_under(lg.x, lg.y) - LEG_LIMB_RAD
                          if self.terrain is not None else floor)
                    grounded = abs(lg.y - gy) <= 1.5
            if grounded:
                lg.grip += 1
                if lg.grip >= LEG_GRIP_DELAY:
                    grip[2 if lg.pair >= 1 else 0] += 1
            else:
                lg.grip = 0
        self._collide_chain_lines(room_hl)
        for lg in self.legs:
            if not lg.planted:
                lg.plant_dx = lg.plant_dy = 0.0
        self.depth_in = clampf(num8, -1.0, 1.0)
        self._step_bob(grip)

    def _step_bob(self, grabbing) -> None:
        """走动上下颠（原版 drawPositions[0/1/2].y += frontBob/hindBob * walkBob）。

        grabbing = (前腿踩实条数, 0, 后腿踩实条数, 0)：两条都踩实＝+1 身体抬起，
        都在空中＝-1 下沉，
        再用 num6 = (4 + 7/walkBob)/2 做平滑。
        """
        wb = self.breed.walk_bob
        num6 = (4.0 + 7.0 / max(0.05, wb)) * 0.5
        self.bob_front = (self.bob_front * num6 + (grabbing[0] - 1)) / (num6 + 1.0)
        self.bob_hind = (self.bob_hind * num6 + (grabbing[2] - 1)) / (num6 + 1.0)
        if self.dead:
            self.bob = [0.0, 0.0, 0.0]
            return
        # y↓：踩实时身体抬起来（取负）
        self.bob = [-self.bob_front * wb,
                    -(self.bob_front + self.bob_hind * wb * 0.5),
                    -self.bob_hind * wb]



def _cat_row(row):
    """兼容 3 元组 (obj,x,y) 与 5 元组 (obj,x,y,dead,fainted)。"""
    if len(row) >= 5:
        return row[0], row[1], row[2], bool(row[3]), bool(row[4])
    return row[0], row[1], row[2], False, False


def _cat_crouching(obj) -> bool:
    """猫是否在匍匐潜行（原版 Crawl 姿态比站立难被蜥蜴注意到）。"""
    return getattr(getattr(obj, "body", None), "bodyMode", None) == "Crawl"


def _cat_camo(obj) -> bool:
    """猫是否隐身中（守望者伪装：半透明 → 蜥蜴很难盯上）。"""
    return getattr(getattr(obj, "gfx", None), "camo", 0.0) > 0.5


def _cat_offering_food(obj) -> bool:
    """猫是否端着能驯服蜥蜴的食物（原版送到嘴边的食物，蜥蜴吃食不咬人）。"""
    f = getattr(getattr(obj, "body", None), "carried_fruit", None)
    return f is not None and bool(getattr(f, "is_tame_food", False))


def _ang_from_up(dx: float, dy: float) -> float:
    """由向量取 0=上、顺时针为正的角度（y↓）。"""
    return math.degrees(math.atan2(dx, -dy))


def _ang_lerp(a: float, b: float, k: float) -> float:
    """角度插值（走最短弧）。"""
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d * k


def _dirvec(dx: float, dy: float) -> tuple[float, float]:
    """归一化（0 向量回落到 (1,0)，同游戏 Custom.DirVec 的容错语义）。"""
    d = math.hypot(dx, dy)
    if d <= 1e-9:
        return 0.0, 0.0
    return dx / d, dy / d


def _dist_less(ax: float, ay: float, bx: float, by: float, d: float) -> bool:
    """同游戏 Custom.DistLess。"""
    dx, dy = ax - bx, ay - by
    return dx * dx + dy * dy < d * d


def _leg_flip_num(i: int, hx: float, hy: float, rx: float, ry: float, lg) -> float:
    """原版 LizardGraphics.cs:1209-1215 的 num11（屏幕 y↓ 下符号等价）。

    num11 = DistanceToLine(脚, connection.pos, rotationChunk.pos) * (i>1 ? 1 : -1)
    """
    dxr, dyr = hx - rx, hy - ry
    L = math.hypot(dxr, dyr) or 1.0
    num11 = (dxr * (lg.y - ry) - dyr * (lg.x - rx)) / L
    return num11 if i > 1 else -num11


def _leg_flip(lz, lg) -> float:
    """一条腿的翻转目标（±1.0）：原版 LizardGraphics 的 flip Lerp 目标。"""
    i = lz.legs.index(lg)
    pi = lg.pair if lg.pair < len(lz.seg) else len(lz.seg) - 1
    hx, hy = lz.seg[pi].x, lz.seg[pi].y
    rj = 2 if pi <= 1 else 0
    rj = rj if rj < len(lz.seg) else len(lz.seg) - 1
    rx, ry = lz.seg[rj].x, lz.seg[rj].y
    return 1.0 if _leg_flip_num(i, hx, hy, rx, ry, lg) < 0.0 else -1.0


