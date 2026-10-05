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
from .combat import CombatTarget
from ..behavior.relationship import Relations
from .enums import ItemState
from .terrain import (Caps, ROUTE_ONE_WAY, ROUTE_RETURNABLE, ROUTE_SAFE)
from . import lizard_cos
from ..planning.navgraph import STUCK_NAVIGATION, STUCK_PHYSICS, StuckDetector
from .lizard_ai import (CARRY_HURRY, DEN_ARRIVE_R, DOMINANCE_DEFER, WARN_R,
                        ApproachPlan, Observation, PackAlert, PreyState,
                        SocialMemory, _terrain_route, choose_den, flank_offset,
                        pack_slot_for, pack_slots,
                        plan_approach, prefs_for, route_kinds,
                        virtual_dens, PERCEIVE_EVERY)

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
SEG_ALIGN = 0.22              # 链节「接在父节延长线上」的软约束（替代原版 chunk 间的撑直）
SEG_ALIGN_HELD = 0.08         # 被拎起/拖动时放软：身体拖在后面，看得出被拽的体长变化
SEG_BEND_K = 0.18             # 转向惯性：速度突变把身体往转向侧甩的强度
SEG_BEND_MAX = 1.5            # 单节最大弯曲位移（防甩飞）
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
HEAD_DEFLECT_FLASH = 14       # 头甲把矛弹开的白闪帧数（比普通受击更亮更久）
CORPSE_TTL = 1500             # 尸体保留 tick（约 25s）
HEAD_STAND_FAC = 2.05         # 头（链首）离地高度 = 躯干半径 * 此值
BODY_STAND_FAC = 1.7          # 躯干节最低离地 = 自身半径 * 此值
TAIL_SINK_FAC = 0.5           # 尾节可拖到接近地面
TAIL_GRAV_FAC = 1.7           # 尾巴「更重」：尾节重力倍数（比躯干下坠更快、摆动更迟滞）
TAIL_ALIGN_FAC = 0.72         # 尾巴顺直约束强度倍数（越软越像一条有重量的尾巴）
# 头：原版 Lizard 的 head 是 ConnectToPoint(chunk0 + 12*headSize) 的软体末端，
# 不是驱动质点。驱动权在 bodyChunks[0]（= self.x / self.y）。
HEAD_SPRING = 0.26            # 头追「第 0 节前方 head_conn」的弹性
HEAD_SPRING_SOFT = 0.10       # 晕 / 死 / 被拎：颈子不使劲，头只被轻轻拖着走
HEAD_GRAV = 0.30              # 头自身重力（站定时垂在体前、跳起 / 急停时甩）
HEAD_AIR_FRIC = 0.88          # 头空气阻力
CHAIN_SEED_LERP = 0.22        # 链体朝向的低通：转身时 seed 会横穿 0（锚点正滑过头顶），
                              # 一帧掉头 = 髋部瞬移几十像素、脚全变成坏锚点

TURN_VX = 0.35                # 判定「真的转身」的横向速度阈值（避免停下时身体窜到头前面）
LEG_SIDE_FAC = 0.55           # 腿根挂在躯干侧下方 = 半径 * 此值
LEG_JOINT = 25.0              # 原版 LizardLimb.jointDist 基准（再 ×(sizeFac+1)/2）
LEG_LIMB_RAD = 2.5            # 原版 LizardLimb 构造里的 rad
LEG_AIR_FRIC = 0.99           # 原版 Limb 的 airFriction
LEG_AIM_AHEAD = 26.0          # limbsAimFor 替代：躯干前方这么多像素（原版是行进目标格中心）
LEG_GRIP_DELAY = 1            # 原版 limbGripDelay（各品种都是 1）
FLOOR_GRIP_TOL = 2.5          # 脚离真实地形 ≤ 这么多才算 grounded（原版 gripCounter 的贴合判定）
LEG_LAND_TOL = 3.5            # 自由脚离落点面 ≤ 这么多 → 直接吸附落地（原版 reachedSnapPosition）
LEG_STEP_STAGGER = 2.5        # 每条腿「拉满就换步」的距离错开量：四只脚不会同时抬起（原版靠各腿髋位错开）
LEG_MAX_STRETCH = 1.35        # 脚离髋超过 jointDist × 这个倍数：支点作废，直接放开
                              # （被拖拽 / 被挤飞时脚不该把身体拽回去）
LEG_ANCHOR_MAX = 4.0          # 脚离髋超过 jointDist × 这个倍数：它不是支点，是坏锚点
                              # （身体已经掉走、脚还留在原来的平面上）→ 不参与身体回拉
LEG_SWING_MAX = 14            # 摆腿最多持续这么多 tick，超过就允许随时落地（否则脚会一直悬着）
LEG_MIN_SUPPORT = 2           # 四足品种任何时刻至少留几只脚踩在地上（换步 / 起步都不许破）
NO_GRIP_SPEED = 0.10            # 原版 noGripSpeed：没有脚支撑时地面滑行速度的「上限」（不是摩擦系数）
FOOT_PULL_K = 0.03              # planted 脚把身体拉回腿长以内的强度（辅助 locomotion，不是主推进）
FOOT_PULL_MAX = 0.35            # 单 tick 最大回拉
LINE_COLLIDE_PAD = 1.5          # 竖杆/背景墙碰撞余量
LEG_DEPTH_MIN = 10.0          # 原版 LizardGraphics 里判定 |num11|>10 才计入 depthRotation

# ── AI ──
NOTICE_R = 150.0              # 视野半径：注意到猫（原版关系 Eats 1.0）

LOST_R = 230.0                # 超出即失去兴趣

# 叼走死猫/昏迷猫（原版把猎物拖回巢穴的宠物化改写：改拖到屏幕两侧角落）
CARRY_NOTICE_R = 460.0        # 多远之内会主动去叼尸体/昏迷猫
CARRY_SPEED_FAC = 0.36        # 叼着东西走 = 基准速度 × 这个系数（见 _state_speed）
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
# Planner 给的攀爬段 mode → 动作层的竖线种类（文档三分法）：
#   climb_wall = 实体墙（庇护所墙体）   climb_pole = 竖杆
#   climb_background = 背景区域（别人窗口露出来的竖边）—— 非实体，只挂不撞。
_CLIMB_MODES = {"climb_wall": "wall", "climb_pole": "pole",
                "climb_background": "background"}
# 地形路线（MovementConnection 序列）的保鲜：走完一段、或者过期了就重新问图。
ROUTE_TTL = 20
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
# 咬合前摇 / 扑击的原版参数（文档 §8）。粉蜥的反编译值：biteDelay=12、
# biteInFront=25、biteHomingSpeed=1.7；其余品种在 BREED_BITE 里逐条给。
BITE_IN_FRONT_K = 0.64        # biteInFront → 咬距的折算（16/25：粉蜥 biteInFront=25
                              # 时正好等于旧口径的 16px 前伸）
BITE_HOMING_REF = 1.7         # biteHomingSpeed 基准（粉蜥）；头跟随即按它归一
BITE_HOMING_STEP = 0.30       # 前摇里「边瞄边压上去」的每 tick 位移比例
BITE_SNAP_SLACK = 1.6         # 前摇结束时目标仍在这个倍数咬距内 → 咬中（跑掉 = 落空）
LOUNGE_ACCEL_FAC = 1.35       # lounge 冲刺段相对扑咬加速度的倍率
IDLE_TICKS = (60, 200)        # 原地停留时长
WANDER_MARGIN = 40.0
WALK_TURN = 0.14              # 游走时速度趋近速率
BLINK_RATE = 0.0125           # 头部呼吸闪烁推进速率（同游戏 LizardGraphics.breath 步长）
MAX_SEG_SPEED = 24.0
BODY_SEED_TRAIL_K = 0.5       # 站在地面上时种子朝「拖在头后方」的偏置（方向是中性不动点，不给就会越推越竖）
BODY_AX_LERP = 0.12           # 锚点方向每 tick 朝 body_dir 靠这么多（转身时平滑滑过去，不再瞬移 2*头距）
# ── 身体朝向 / 转身（原版 bodyChunk 惯性转向的桌宠替身）──
# 原版没有「facing 开关」：AI 想看左边时，只有前端 bodyChunk 改变运动方向，连接约束让
# 第 1 节稍晚、尾巴更晚跟上，LizardGraphics 再按 chunk 的实际位置生成身体 —— 看起来
# 就是「头先转 → 前身转 → 中身滞后 → 尾巴最后甩过来」。这里把朝向拆成三条通道：
#   look_dir  头看向哪一侧（独立通道，允许只回头、身体不动）
#   move_dir  这一 tick 想往哪一侧走（= 速度意图）
#   body_dir  身体实际转到哪一侧（连续量、有限速率：+1 右 → 0 横对镜头 → -1 左）
# 转身冲量 _turn_imp 由速度突变产生，喂给前 1~2 节躯干的 vx（原版 chunk 惯性：
# 前节先被带过去，尾巴最后才跟），量小、只持续几 tick。
TURN_RATE = 0.055             # |body_dir| 每 tick 的变化量（2.0/0.055 ≈ 36 tick 掉完头）
TURN_RATE_AIR = 0.032         # 腾空时没有脚蹬地，转身更慢
TURN_IMP_K = 14.0             # 转身冲量 = 本 tick 身体轴摆量 * K（摆量 ≤ TURN_RATE）
TURN_IMP_DV_K = 0.35          # 再叠一点速度突变的贡献（vx - _last_vx）
TURN_IMP_MAX = 0.85           # 冲量上限（像素/tick）
TURN_IMP_SEGS = 2             # 冲量作用在前几节躯干
TURN_DIR_EPS = 0.06           # |body_dir - move_dir| 大于它 = 还在转身
TURN_HOP_VY = 2.6             # 掉头小跳的初速（有力气的品种才会蹬这一下）

# 身体冲量：原版 AI 给的不是「头这一个点」，而是 bodyChunks 拿到的 impulse
# （头只是 head.ConnectToPoint 挂在 chunk0 前方的一个点）。起跳 / 扑击 / 咬合
# 时把同一份冲量直接灌给前几节躯干：前节先走 → 连接被拉长 → 中段和尾巴按惯性
# 滞后跟上。这才是「躯干为什么会动」，而不是给头部加一个火箭、身体靠绳子被拖。
BODY_IMP_SEGS = 2             # 冲量直接作用的前几节躯干
BODY_IMP_FALLOFF = 0.45       # 每往后一节衰减（后节拿到的更少）
BODY_IMP_MAX = 6.0            # 单次冲量上限（防把身体甩飞）
BODY_JUMP_SHARE = 0.55        # 蹬地起跳时分给躯干的初速比例
BODY_BITE_PUSH = 1.6          # 咬合时前半身朝猎物压出去的冲量
BODY_BITE_LUNGE = 2.5         # 咬合瞬间头点朝猎物递出去的距离（原版 snap 的前半身前伸）
JAW_SNAP_MAIN = 8.0           # 原版 Lizard.cs JawsSnapShut：mainBodyChunk.vel += Dir * 8
JAW_SNAP_BACK = 6.0           #   同一条：bodyChunks[1]/[2].vel -= Dir * 6（前冲后坐）
JAW_SNAP_HEAD = 1.0           # 夹合那一帧头点前递的距离（速度 → 本作头点是位置驱动）

# ── 动作序列（文档 §9.3 / §10）：Attack 四阶段姿态 + PrepareToJump 分节点冲量 ──
# 原版 Lizard.ActAnimation() 不是「播一段动画」，而是直接给不同 bodyChunk 注入不同
# 方向的速度。所以这里同样按阶段给**每个 chunk 单独**写速度，而不是整条一起推。
ATK_PREPARE_T = 5             # Attack_Prepare：压低身体、前半身压上去、后半身反推
ATK_LUNGE_T = 6               # Attack_Lunge：chunk 按 loungeSpeed/(k+1) 依次递出
ATK_BITE_T = 4                # Attack_Bite：下颚夹合 + 前半身再顶一下
ATK_RECOVER_T = 10            # Attack_Recover：postLoungeStun，身体回收、尾巴追上
ATK_PUSH_PREP = 0.85          # Prepare 段每 tick 的躯干冲量
ATK_COMPRESS_PREP = 0.55      # Prepare 段压低身体的比例
ATK_RAISE_LUNGE = 0.35        # Lunge 段抬起前身
ATK_COMPRESS_BITE = 0.35
ATK_COMPRESS_RECOVER = 0.15
ATK_LUNGE_K = 0.55            # Lounge：每节拿到的推进比例（原版 1/(k+1)）
ATK_RECOVER_BACK = 0.30       # Recover：反方向回收
BODY_JUMP_MID = 0.30          # PrepareToJump：中节额外拿到的起跳方向速度
BODY_JUMP_REAR = 0.40         # PrepareToJump：后节拿到反向速度（身体被蹬长）

# ── 原版 bodyWiggleCounter（文档 §10.5）：身体自己的低频扰动 ──
WIGGLE_DECAY = 0.90           # 每 tick 衰减
WIGGLE_IDLE_P = 0.02          # 空闲时每 tick 随机抬高的概率（原版「其余时间随机抬高」）
WIGGLE_BUMP = 0.55            # 事件（发现猎物 / 起跳 / 出声）抬高量
WIGGLE_SPEED = 0.30           # 原版 lizardParams.wiggleSpeed：相位推进率与冲量增益
WIGGLE_RATE_LO = 0.05         # 原版 Lerp(0.05, 0.15, BodyWiggleFac)
WIGGLE_RATE_HI = 0.15
WIGGLE_SPD_LO = 0.5           # 原版 Lerp(0.5, 0.8, wiggleSpeed)
WIGGLE_SPD_HI = 0.8
# 原版 Lizard.cs:1926 / 424-426：desperationSmoother → BodyForce / BodyDesperation。
# LerpAndTick(x, target, 0.05, 0.5)：先按 0.05 插值，再限制单次变化不超过 0.5。
DESP_LERP = 0.05
DESP_TICK = 0.5
MAX_MUSCLE_POWER = 2.0        # 原版 lizardParams.maxMusclePower 的量级（BodyForce 上限）
HEAD_LEAD_K = 0.30            # 物理扭头：前 1~2 节被颈子带偏的比例（文档 §9.2/§10.4）

# ── 原版 LizardTongue / LizardSpitTracker（文档 §六）：舌头是一段独立物理 ──
# LizardTongue 不是「咬」，是 chunk 级的一条可伸缩舌头：LashOut 把舌尖射出，
# 碰到猎物转 Grab 后 DragChunk 把猎物拽向嘴边，到嘴才 AttemptBite。
# breed.tongue / tongue_range 是反编译里早就抄进来的参数，之前一直没接。
TONGUE_SPEED = 7.5            # 射出速度（px/tick）
TONGUE_RETRACT = 7.0          # 收回速度
TONGUE_GRAB_R = 18.0          # 舌尖碰到猎物的判定半径
TONGUE_MOUTH_R = 22.0         # 猎物被拽到离嘴这么近 = 到嘴，转 AttemptBite
TONGUE_PULL = 7.0             # 每 tick 拽猎物的速度（原版 DragChunk）
                              #   = 收舌速度：舌尖往回卷，猎物被舌尖拖着一起回到嘴边
TONGUE_CD = 70                # 射舌冷却
TONGUE_W = 3.2                # 舌根半宽（px，向舌尖渐细）
TONGUE_JAW = 0.65             # 射舌时嘴至少张到这么大（原版 ShootTongue）
TONGUE_LASH_MIN = 0.75         # 原版 LashOut：出手速度 = 基础速度 ×（0.75~1.0，看距离）
TONGUE_LASH_K = 0.25           # 上式里距离插值的幅度
TONGUE_DOT_MIN = 0.3           # 目标与体前轴的点积门槛：≤ 它舌头根本不出（原版 LashOut 直接 return）
TONGUE_RECOIL = 0.55           # 射舌反作用：后节 vel -= 方向 × 出手速度（原版 bodyChunks[1]）
TONGUE_DRAG = 1.5              # 舌外伸期间每 tick：头被拽向舌尖、后节反向（原版 Update 里的 ±4）
TONGUE_TERRAIN_PULL = 0.75     # 舌尖粘住地形时，把头往锚点拖（LizardTongue.TerrainDrag）
BODY_JUMP_TAIL = 0.06          # PrepareToJump：尾节逐节冲量（越往后越强）
BODY_JUMP_WOBBLE = 1.6         # PrepareToJump：尾巴垂直方向 ± 交替甩动
WALL_LEAN = 0.35               # 爬墙时前节朝爬行方向、后节反向拉开（身体贴墙而不是被提着）
WALL_TURN_TICKS = 12           # 墙上换向（上↔下）时先给一次反向冲量摆过去

# ── 原版后空翻（文档 §9.4）：不是「跳高一点」，是身体姿态序列的角动量 ──
# 原版翻身的角动量来自 PrepareToJump 给各 chunk 的反向冲量；这里补上真正的
# 「整条身体绕质心转过去」这段：起跳后 FLIP_TICKS 帧里匀速转过 FLIP_ARC。
FLIP_TICKS = 14               # 一次翻滚的 tick 数（约 0.35s）
FLIP_ARC = 360.0              # 整段翻过去的角（度）—— 360 收尾时与 0 等价，不跳变
FLIP_SPEED_MIN = 1.0          # 起跳时的水平速度门槛（够快才带着翻过去）
FLIP_GRACE = 2                # 起跳那几帧还贴着地的宽限（帧）

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
# ── 移动速度：一律「品种基准速度 × 状态系数」──
# 旧口径给巡逻 / 调查 / 叼东西写死了 1.8~2.4 px/tick 的**绝对**上限，与品种无关：
# 只有绿蜥（base 6.7）追猎快得过自己巡逻，粉/蓝/白/黄/红/黑/蝾螈/青/鳗鱼全是
# 「慢悠悠地追」（追猎 1.3~2.2 < 巡逻 2.4），速度上根本看不出「看见猎物了」。
# 现在全部按同一把尺子缩放，状态之间的先后次序与品种无关地固定：
#   发呆 0 < 巡逻 < 叼东西 < 调查 / 上任一分工位 < 追猎(惰性 / 冲刺) < 受伤 < 逃跑
MOVE_SPEED_FLOOR = 1.5        # 基准速度下限：焦糖蜥 base 0.65，纯相对量会几乎贴地不动
PATROL_SPEED = 0.30           # 巡逻游走
SNIFF_SPEED = 0.38            # 循声调查 / 走上墙点 / 黄蜥分工位 / 跟朋友
HUNT_SPEED = 0.80             # 追猎（再乘 sprint：惰性 0.55 / 冲刺 1.0）
FLEE_SPEED = 1.12             # 逃跑速度 × base_speed
FLEE_ACCEL = 0.18
FLEE_HOP = 0.03
FLEE_SEAT_DY = 220.0          # 逃跑落点可以和我差这么多层（再远就不考虑）
FLEE_SEAT_TRIES = 3           # 每次重规划最多试几个「离威胁最远」的落点
PACK_SEAT_TICKS = 30          # 黄蜥包夹位多久重算一次（路线代价不便宜）

# ── 侵略追踪器（AgressionTracker，LizardAI.cs:628 / AgressionTracker.cs）──
ANGER_UP = 0.001              # 原版 angerSpeedUp
ANGER_DOWN = 0.001            # 原版 angerSpeedDown
ANGER_FIGHT = 0.35            # 原版 Utility() = InverseLerp(0.35,1,anger) 的下限
ANGER_W = 0.5                 # 原版 utilityComparer 里 agressionTracker 的权重（LizardAI.cs:648）
# 逃 / 猎 的效用仲裁（文档 §40）：旧版是硬优先级「有威胁就一律逃」，于是
# 「猎物已经叼在嘴里 / 就在嘴边」也会被一个远处的威胁打断。现在两个效用各算
# 一份，差值必须超过迟滞带才切换，避免在边界上每帧横跳。
FLEE_UTIL = 1.0               # 逃的效用上限（威胁贴脸时取到）
HUNT_UTIL = 0.72              # 猎的效用上限（目标进咬合距离时取到）
FLEE_HUNT_HYSTERESIS = 0.12   # 切换需要拉开的效用差
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
# 白蜥迷彩：**每 tick** 采一圈「自己周围」的实时背景主色，整只（含头）渐变过去
# 并一直保持。反编译对照：原版白蜥体色就是**房间背景色**（LizardGraphics 的 camo
# 分支），潜伏时盯着背景一动不动，追逐 / 被攻击就垮掉。桌宠里「房间背景」＝蜥蜴
# 周围的真实桌面；采样以自己为中心、挖掉身体所在区域，拿到的是「周边局部环境色」：
# 不是整屏 dominant，也不是身体各部位各采一个色。不再有呼吸灯。
CAMO_SAMPLE_RADIUS_X = 70.0    # 采样半宽下限（实际取 max(body_rad*4.5, 它)）
CAMO_SAMPLE_RADIUS_Y = 55.0    # 采样半高下限（实际取 max(body_rad*3.5, 它)）
CAMO_COLOR_RATE = 0.25         # 整只体色向新采样色渐变的速度（平滑、跟手）
CAMO_FADE_IN = 0.10            # 进入伪装：体色/头色 → 采样色（~0.5 s 淡入）
CAMO_FADE_OUT = 0.50           # 发起攻击 / 被攻击：伪装立刻垮掉（~4 tick）
CAMO_HIDE_VX = 1.2             # 位移速度低于它 = 潜伏不动，伪装才成立
CAMO_HIDDEN_MIX = 0.70         # 达到这个视觉混合度才算真正隐身（避免淡入首帧突然消失）
CAMO_FLICKER_TICKS = 90        # 受伤后「不由自主胡乱变色」剩余 tick（原版受伤乱闪）
CAMO_FLICKER_STEP = 3          # 乱闪期间每隔几 tick 换一个随机色
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
    locomotion: str = "idle"    # idle / walk / run / lurk / carry / climb
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


def _push_out(px, py, r, rects, step_up):
    """把半径 r 的圆点按最小穿透轴推出所有矩形，返回新位置。

    躯干链、头、庇护所墙体共用这一份 —— 原版本来就是同一个
    PushOutOfTerrain，没必要每处各写一份 AABB。
    """
    for x0, y0, x1, y1 in rects:
        if x1 <= x0 or y1 <= y0:
            continue
        if px + r <= x0 or px - r >= x1:
            continue
        if py + r <= y0 or py - r >= y1:
            continue
        p_left = (px + r) - x0
        p_right = x1 - (px - r)
        p_top = (py + r) - y0
        p_bot = y1 - (py - r)
        m = min(p_left, p_right, p_top, p_bot)
        if m <= 0.0:
            continue
        # 台阶：横向被挡但障碍顶边离脚面不到一步 → 直接踩上去
        if m in (p_left, p_right) and 0.0 <= (py + r) - y0 <= step_up:
            py = y0 - r
            continue
        if m == p_top:
            py = y0 - r
        elif m == p_bot:
            py = y1 + r
        elif m == p_left:
            px = x0 - r
        else:
            px = x1 + r
    return px, py


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
                 "danger", "visual_radius", "tongue", "tongue_range", "tongue_chance",
                 "tongue_warmup", "tongue_segments", "body_mass",
                 "flips_from_rock", "bite_damage_chance", "bite_dominance",
                 "bite_delay", "bite_in_front", "bite_homing_speed",
                 "lounge_distance", "lounge_speed",
                 # 步态（LizardBreedParams 同名参数，原版腿 IK 的行为参数）
                 "step_length", "lift_feet", "feet_down", "limb_speed",
                 "limb_quickness", "smooth_legs", "leg_pair_disp", "walk_bob",
                 "lounge_tendency",
                 # 品种差异（见文件末 BREED_TRAITS）
                 "spawn_weight", "cosmetics", "can_climb", "camo", "charge_leap",
                 "climb_wall", "climb_pole", "wall_attach", "wall_detach", "wall_jump",
                 "jump_fac", "turn_hop", "flip_hop",
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
                 bite_delay=12, bite_in_front=None, bite_homing_speed=1.7,
                 lounge_distance=150.0, lounge_speed=1.0,
                 attempt_bite_radius=80.0, taming_difficulty=1.0,
                 head_shield_angle=100.0, danger=0.45, visual_radius=900.0,
                 tongue=False, tongue_range=0.0, tongue_chance=0.0,
                 tongue_warmup=8, tongue_segments=7, body_mass=2.1,
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
        # 原版 biteDelay：AttemptBite 到 JawsSnapShut 之间隔多少帧（前摇 = 猎物能
        # 逃开的窗口）。biteInFront：嘴在头前多远，没显式给的品种按现有
        # attempt_bite_radius 折算，保证换口径前后每个品种的咬距一个像素都不动。
        self.bite_delay = int(bite_delay)
        self.bite_in_front = (float(bite_in_front) if bite_in_front is not None
                              else 25.0 * attempt_bite_radius / 80.0)
        self.bite_homing_speed = float(bite_homing_speed)   # 前摇里头部锁目标的速率
        # 原版 loungeDistance / loungeSpeed：进入这个距离就是一次全力冲刺
        self.lounge_distance = float(lounge_distance)
        self.lounge_speed = float(lounge_speed)
        self.taming_difficulty = taming_difficulty
        self.head_shield_angle = head_shield_angle
        self.danger = danger
        self.visual_radius = visual_radius
        self.tongue = tongue
        self.tongue_range = tongue_range
        # LizardBreeds.cs:184-192 / LizardAI.cs:1242-1244.  A tongue is not
        # an automatic bite replacement: the AI rolls tongueChance and the
        # graphics warm up for tongueWarmUp ticks before the lash leaves.
        self.tongue_chance = float(tongue_chance)
        self.tongue_warmup = int(tongue_warmup)
        self.tongue_segments = int(tongue_segments)
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
        # 能力默认全 False：由 BREED_TRAITS 逐个显式打开。
        # （默认 True 再关掉很危险 —— 新加一个品种忘登记，就凭空获得全部攀爬能力。）
        self.climb_wall = False
        self.climb_pole = False
        self.wall_attach = False
        # 跳跃能力（≠ 会不会爬）：反编译 LizardBreedParams.loungeJumpyness
        self.jump_fac = 0.5
        self.turn_hop = True
        self.flip_hop = False          # 跳得猛的品种才会在空中翻过去（见 BREED_TRAITS）
        self.wall_detach = False
        self.wall_jump = False
        self.can_climb = False         # = climb_wall or climb_pole（兼容旧调用点）
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
                # LizardBreeds.cs:286-290: Blue tongueChance=0.25,
                # tongueWarmUp=10, tongueSegments=5.
                tongue=True, tongue_range=140.0, tongue_chance=0.25,
                tongue_warmup=10, tongue_segments=5, hue_var=0.08,
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
                # LizardBreeds.cs:465-470: standardColor is pure white.  White
                # camouflage is applied by LizardGraphics at runtime; it is not
                # a pastel spawn-color variation.
                pale_random=False,
                size=1.00, base_speed=3.8, tail_segs=5, tail_len_fac=1.2,
                jaw_open_angle=110.0, jaw_lower_fac=0.5, neck_stiffness=0.05,
                body_stiffness=0.15, tail_col_start=0.1, tail_col_exp=1.2,
                bite_damage=1.0, bite_damage_chance=0.2857143, bite_chance=0.5, attempt_bite_radius=85.0,
                toughness=0.9, stun_toughness=0.9, taming_difficulty=3.0,
                danger=0.5, visual_radius=1300.0, body_mass=2.1,
                sat=0.0, plain_color=(255, 255, 255),
                tongue=True, tongue_range=440.0, tongue_chance=0.10,
                tongue_warmup=80, tongue_segments=10,
                step_length=0.6, lift_feet=0.2, feet_down=0.05, limb_speed=8.0,
                limb_quickness=0.8, smooth_legs=False, leg_pair_disp=0.0,
                walk_bob=0.8),
    LizardBreed("red", "红蜥", "Red lizard", 0.0025, 0.50, (0, 0, 0, 0, 0),
                size=1.20, head_size=1.2, base_speed=5.0, tail_segs=11, tail_len_fac=1.9,
                limb_size=1.5, jaw_open_angle=140.0, body_stiffness=0.3,
                bite_damage=4.0, bite_damage_chance=1.0, bite_chance=1.0, attempt_bite_radius=120.0,
                toughness=3.0, stun_toughness=3.0, taming_difficulty=7.0,
                danger=0.8, visual_radius=2300.0, body_mass=3.1,
                tongue=True, tongue_range=350.0, tongue_chance=0.10,
                tongue_warmup=8, tongue_segments=10, flips_from_rock=False,
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
                tongue=True, tongue_range=150.0, tongue_chance=1.0 / 3.0,
                tongue_warmup=8, tongue_segments=7,
                hue_var=0.15, light_dev_k=0.2,
                smooth_legs=False),
    LizardBreed("cyan", "青蜥", "Cyan lizard", 0.49, 0.50, (0, 0, 0, 0, 0),
                size=0.65, base_speed=3.0, tail_segs=5, tail_len_fac=1.44, limb_size=1.0,
                limb_thickness=0.8, jaw_open_angle=80.0, jaw_apart=17.0, body_stiffness=0.8,
                bite_damage=1.0, bite_damage_chance=0.25, bite_chance=0.5, attempt_bite_radius=80.0,
                toughness=0.35, stun_toughness=50.0, taming_difficulty=1.0,
                head_shield_angle=70.0, danger=0.25, visual_radius=990.0, body_mass=0.8,
                tongue=True, tongue_range=160.0, tongue_chance=1.0 / 3.0,
                tongue_warmup=8, tongue_segments=7, hue_var=0.04,
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
                # LizardBreeds.cs:995-999 (ZoopLizard): long warm-up ambush
                # tongue, not an always-on attack.
                body_mass=0.9, tongue=True, tongue_range=440.0,
                tongue_chance=0.30, tongue_warmup=140, tongue_segments=10,
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
# 咬合 / 扑击的品种参数（文档 §8）。粉蜥那一列是公开的反编译记录
# （biteDelay=12 / biteInFront=25 / biteHomingSpeed=1.7 / attemptBiteRadius=80 /
# biteDamage=1 / biteDamageChance=1/3 / toughness=1 / baseSpeed=4.1 / bodyMass=2.1 /
# bodyStiffness=0.2 / danger=0.45），其余品种按 wiki 的「撕咬间隔 / 撕咬距离 /
# 基本速度 / 体型」相对次序排：绿蜥和红蜥咬得又慢又远又猛，蓝蜥/焦糖蜥反着来。
# 想单独调某个品种的咬距，就在它的 LizardBreed(...) 里直接给 bite_in_front。
BREED_BITE = {
    #            biteDelay  biteHomingSpeed  loungeDistance  loungeSpeed
    "pink":       (12, 1.70, 150.0, 1.00),
    "green":      (10, 1.20, 190.0, 1.20),
    "blue":       (14, 1.90, 110.0, 0.70),
    "yellow":     (12, 1.60, 150.0, 1.00),
    "white":      (12, 2.00, 170.0, 0.85),
    "red":         (8, 2.20, 230.0, 1.35),
    "black":      (12, 1.70, 160.0, 1.10),
    "salamander": (14, 1.50, 140.0, 0.90),
    "cyan":       (10, 1.90, 200.0, 1.15),
    "caramel":    (15, 1.40, 120.0, 0.70),
    "zoop":       (12, 1.60, 140.0, 0.90),
    "eel":        (13, 1.60, 140.0, 0.95),
}

BREED_TRAITS = {
    # climb_wall 只给 WallClimber（反编译 LizardBreedParams.cs:196-210）：
    # 蓝 / 白 / 鳗鱼（DLC）。其余品种「会爬杆但不攀爬背景墙」。
    # 明确能力表：杆攀爬仅允许原版可爬杆品种；背景墙仅 WallClimber。
    # jump_fac = 跳跃能力（≠ 会不会爬）：反编译 LizardBreedParams.loungeJumpyness
    # （LizardBreeds.decompiled.cs:75 粉 0.5 / :157 绿 0 / :249 蓝 0.9 / :338 黄 0.5
    #  / :428 白 0.5 / :525 红 0.5 / :608 黑 0.5 / :690 蝾螈 0.5 / :787 青 0.9 /
    #  DLC 共用的 Salamander 模板 :1642 = 0.5）。绿蜥 = 0 → 扑击压根不往上蹿。
    "pink":       dict(spawn_weight=1.00, climb_wall=False, climb_pole=True,
                       jump_fac=0.5),
    "green":      dict(spawn_weight=0.90, climb_wall=False, climb_pole=False,
                       jump_fac=0.0),
    "blue":       dict(spawn_weight=0.90, climb_wall=True, climb_pole=True,
                       jump_fac=0.9),
    "yellow":     dict(spawn_weight=0.35, climb_wall=False, climb_pole=True,
                       jump_fac=0.5),
    "white":      dict(spawn_weight=0.30, climb_wall=True, climb_pole=True, camo=True,
                       jump_fac=0.5),
    "red":        dict(spawn_weight=0.02, climb_wall=False, climb_pole=True,
                       jump_fac=0.5),
    "black":      dict(spawn_weight=0.30, climb_wall=False, climb_pole=True,
                       jump_fac=0.5),
    "salamander": dict(spawn_weight=0.25, climb_wall=False, climb_pole=True,
                       jump_fac=0.5),
    "cyan":       dict(spawn_weight=0.25, climb_wall=False, climb_pole=True,
                       wall_jump=True, charge_leap=True, jump_fac=0.9),
    # DLC《倾盆大雨》
    "caramel":    dict(spawn_weight=0.03, climb_wall=False, climb_pole=False,
                       jump_fac=0.5),
    "zoop":       dict(spawn_weight=0.05, climb_wall=False, climb_pole=True,
                       jump_fac=0.5),
    "eel":        dict(spawn_weight=0.06, climb_wall=True, climb_pole=True,
                       jump_fac=0.5)
}
for _b in BREEDS:
    _t = BREED_TRAITS.get(_b.key, {})
    _b.spawn_weight = float(_t.get("spawn_weight", 1.0))
    _b.climb_wall = bool(_t.get("climb_wall", False))
    _b.climb_pole = bool(_t.get("climb_pole", False))
    _b.wall_jump = bool(_t.get("wall_jump", False))
    _b.wall_attach = bool(_t.get("wall_attach", _b.climb_wall))
    _b.wall_detach = bool(_t.get("wall_detach", _b.climb_wall))
    _b.can_climb = bool(_b.climb_wall or _b.climb_pole)
    # 三种能力彻底拆开（旧实现把「会不会爬」当成「会不会跳」在用）：
    #   can_climb / climb_wall / climb_pole = 攀爬能力
    #   caps.jump                           = 寻路层能不能用跳跃/跨越连接
    #   jump_fac                            = 物理层跳多猛（反编译 loungeJumpyness）
    #   turn_hop                            = 掉头时会不会蹬一下地（同源 loungeJumpyness）
    _b.jump_fac = float(_t.get("jump_fac", 0.5))
    _b.turn_hop = bool(_t.get("turn_hop", _b.jump_fac > 0.0))
    # flip_hop = 起跳时会不会带着身体翻过去（原版靠 PrepareToJump 的反向冲量拿到
    # 角动量）。和 turn_hop 一样是独立能力，默认只看「跳得猛不猛」：
    # jump_fac >= 0.9 的（蓝 0.9 / 青 0.9）与蓄力弹射的青蜥。
    _b.flip_hop = bool(_t.get("flip_hop", _b.charge_leap or _b.jump_fac >= 0.9))
    _b.camo = bool(_t.get("camo", False))
    _b.charge_leap = bool(_t.get("charge_leap", False))
    # 咬合 / 扑击参数（文档 §8）：没登记的品种走粉蜥那一档
    _bd, _bh, _ld, _ls = BREED_BITE.get(_b.key, (12, 1.70, 150.0, 1.00))
    _b.bite_delay = int(_bd)
    _b.bite_homing_speed = float(_bh)
    _b.lounge_distance = float(_ld)
    _b.lounge_speed = float(_ls)

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
                 "airborne", "swing", "flip", "disabled", "back", "near", "pair")

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
        # 这一趟迈步有没有真的离过地：换步那一下脚还贴在地上，没这个标记
        # 下一帧就会被判成「踩住了」又钉回去，腿永远迈不出去。
        self.airborne = False
        self.swing = 0                 # 这一趟摆腿已经持续了多少 tick
        self.flip = 0.0                # LizardLimb.flip（初值 0，逐帧 Lerp 到 ±1）
        self.disabled = False          # currentlyDisabled（眩晕/游泳时挂起）
        self.back = back
        self.near = near
        # 腿根挂在哪一节躯干（原版 LizardLimb 挂 bodyChunk）：0 前 / 1 中 / 2 后
        self.pair = (2 if back else 0) if pair is None else int(pair)


def _prey_field(name):
    """把「猎物链」的老字段名代理到 `self.prey`（文档 §17）。

    PreyState 是这条链（追踪 / 占有 / 叼住 / 回巢 / 守卫 / 记忆）的**唯一**持有者；
    这里只是让 `self.carry_obj`、`self.guard_t`、`self.mem` 这些老调用点原样可用，
    读写都通到同一个 PreyState，行为与从前逐字段赋值完全一致。
    """
    def _get(self):
        return getattr(self.prey, name)

    def _set(self, value):
        setattr(self.prey, name, value)

    return property(_get, _set)


class Lizard(CombatTarget):
    food_class = "none"      # 不是食物：尸体算无用尸体（会被猫拖出屏幕清场）
    """一只蜥蜴：头为驱动质点，躯干/尾逐节跟随；巡走 → 警觉 → 扑咬。"""

    collision_layer = 0                 # 不参与 chunk 互推，交互全部走 AI

    # 文档 §17：猎物链的老名字 → PreyState（唯一状态对象）的代理。
    target = _prey_field("target")
    target_obj = _prey_field("target_obj")
    carry_obj = _prey_field("carry_obj")
    carry_body = _prey_field("carry_body")
    carry_den = _prey_field("carry_den")
    carry_corner = _prey_field("carry_corner")
    guard_obj = _prey_field("guard_obj")
    guard_t = _prey_field("guard_t")
    mem = _prey_field("mem")

    __slots__ = ("breed", "color", "tail_edge", "tail_amt", "rng", "seed", "id",
                 "body_rgb",
                 "x", "y", "vx", "vy", "last_x", "last_y", "head_rad", "head_conn",
                 "body_rad", "seg", "legs", "state", "facing", "look_at",
                 "limbs_aim",
                 "head_angle", "last_head_angle", "jaw", "last_jaw",
                 "bite_event", "bite_hold", "bite_cd", "_tgt_hold",
                 "bite_wind", "_bite_wind_obj", "_bite_wind_dmg",
                 "walk_phase", "idle_timer", "goal_x", "hop_cd", "blink", "last_blink",
                 "chain_dir", "_ax_c",
                 "body_dir", "move_dir", "look_dir", "turn_mode", "turn_progress",
                 "_turn_imp", "_last_body_dir", "_vx_intent", "_want_vx",
                 "_body_imp_x", "_body_imp_y", "_jaw_rec_x", "_jaw_rec_y",
                 "_atk_phase", "_atk_t", "_atk_dir", "wiggle",
                 "_wiggle_ph", "_desp", "_anim_rng",
                 "tongue_speed", "tongue_warmup_left", "black_salamander",
                 "_wall_turn_left", "_wall_dir_prev",
                 "held_by_hand", "water_y", "room_gravity", "_contact_floor",
                 "dead", "spacing", "spikes", "cosmetics", "cosmetic_pts", "like", "tamed", "friend_id",
                 "climb_x", "climb_dir", "climb_surfaces", "hauler",
                 "max_health", "health", "stun", "hurt_flash", "head_flash", "dead_t",
                 "rock_push", "rock_push_dir",
                 "rock_flip_left", "rock_flip_ang", "rock_flip_dir",
                 "hauled", "haul_thrown", "is_meat", "wall_dir",
                 "anger", "anger_obj", "submitted_to",
                 "threat", "threat_obj", "threat_t",
                 "noise_x", "noise_y", "noise_t", "lurk",
                 "bob", "bob_front", "bob_hind",
                 "sprint",
                 "obs", "prey", "plan", "soc",
                 "alert", "warning_t", "stage", "stage_obj", "peers",
                 "_blockers", "_tick",
                 "depth", "last_depth", "head_depth", "last_head_depth", "turn_lift",
                 "head_driven", "anim", "_last_vx",
                 "depth_in", "rel",
                 "camo_target", "camo_color", "camo_mix", "camo_flicker",
                 "head_x", "head_y", "head_lx", "head_ly", "head_vx", "head_vy",
                 "_seed_prev",
                 "climb_kind", "climb_attached", "climb_side",
                 "climb_top", "climb_bot", "caps", "terrain", "_ground",
                 "shelter_x",
                 "_stuck", "_pack_point", "_pack_point_tick",
                 "_claims", "_scanned", "_scan_tick",
                 "_cursor_until", "_cursor_retry",
                 # 舌头（LizardTongue）：state / 已经伸多长 / 方向 / 舌尖 / 猎物 / 冷却
                 "tongue_state", "tongue_len", "tongue_dir", "tongue_tip",
                 "tongue_prey", "tongue_grab", "tongue_t", "tongue_cd",
                 # 后空翻（文档 §9.4）：剩余帧 / 方向 / 已经转过的角
                 "flip_left", "flip_dir", "flip_ang", "flip_wait")

    def __init__(self, x: float, y: float, breed: LizardBreed | None = None,
                 seed: int = 0, id: int = 0):
        self.rng = _random.Random(seed * 7919 + 13)
        # 动画物理自己的随机流：原版这两段用的是 UnityEngine.Random（全局流）。
        # 混进 self.rng 会把「加一次身体扰动」变成把之后所有行为随机序列整体错位。
        self._anim_rng = _random.Random(seed * 331 + 17)
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
        # 原版非红蜥被石头击中会翻身（Violence -> turnedByRockCounter）。
        # 这里保留一个短角动量状态，让头部命中表现为翻肚皮，而不是只横向滑动。
        self.rock_flip_left = 0
        self.rock_flip_ang = 0.0
        self.rock_flip_dir = 1
        self.hurt_flash = 0      # 受击白闪（渲染用）
        self.head_flash = 0      # 头甲弹开矛的头部强白闪（渲染用）
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
        self.camo_mix = 0.0      # 0＝本体色，1＝完全等于采样到的背景色（淡入淡出）
        self.camo_flicker = 0    # 受伤后「不由自主胡乱变色」剩余 tick
        # ── AI 分层（world/lizard_ai.py）──
        self.obs = {"cats": (), "prey": (), "threats": (), "rivals": (), "pack": ()}
        # 文档 §17：「猎物链」只有这一个状态对象 —— target / target_obj / 咬倒
        # 归属 / carry_obj+carry_body+carry_den+carry_corner（叼回巢穴）/ guard_obj
        # +guard_t（放下后守一会儿）/ mem（我上次在哪看见它）全在里面。
        self.prey = PreyState()
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
        self._claims = None          # None = 没有全场归属表（旧入口/测试）
        self._scanned = False        # 还没看过第一眼 → 第一次必须扫
        self._scan_tick = -PERCEIVE_EVERY
        self._cursor_until = 0
        self._cursor_retry = 120 + self.id % 180
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

        # 头：挂在第 0 节躯干前方的软体末端（原版 head.ConnectToPoint(chunk0)）。
        # 它不是 AI 驱动点 —— 驱动的是 bodyChunk[0]（= self.x / self.y），头只是
        # 被连接约束拖在体前的一个点，所以会滞后、下垂、被甩。
        self.head_x = self.head_lx = self.x + self.head_conn
        self.head_y = self.head_ly = self.y
        self.head_vx = self.head_vy = 0.0
        self._seed_prev = None      # 上一帧的链体朝向（转身限速用，见 _step_chain）

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
        self._stuck = StuckDetector()  # 跟着地形路线走却挪不动窝的检测（文档 §28）
        # 黄蜥这一轮分到的包夹点（文档 §14）：由路线代价从猎物周边的落点里挑，
        # 不是「同一个目标点 + X 偏移」；隔一段时间重算一次。
        self._pack_point = None
        self._pack_point_tick = -10 ** 9
        # 地形能力表（原版 CreatureTemplate / LizardBreedParams）：
        # 地形图全场共用，但「这张图里我能用哪些连接」逐品种过滤。
        self.caps = Caps(
            walk=True, jump=True,
            wall_climb=bool(b.climb_wall and b.wall_attach),
            pole_climb=bool(b.climb_pole),
            # 背景区域（原版 WallClimber 的「背景墙攀爬」）：蓝 / 白 / 鳗才开。
            climb_background=bool(b.climb_wall and b.wall_attach),
            # 横杆杆面也是「杆」：不会用杆的品种（绿蜥等）连站在杆面上都不行
            # （用户口径：无杆能力的品种无论如何都无法与杆子互动）。
            hpole_walk=bool(b.climb_pole),
            wall_jump=bool(getattr(b, "wall_jump", False)),
            climb_reach=CLIMB_WALK_R)
        self.terrain = None           # 这一帧的世界地形查询（items 每 tick 换一份）
        self._ground = float(y)       # 这一 tick 脚下踩的那一层（屏幕地板 / 窗台 / 横杆）
        # 唯一庇护所的中心 x，由窗口每 tick 注入；None 表示场上未放庇护所。
        self.shelter_x = None
        # 清场认领：哪只猫认领了这具尸体（尸体搬运只允许一只猫执行）
        self.hauler = None

        self.state = ItemState.FREE
        self.facing = 1
        self.chain_dir = 1.0
        self._ax_c = 1.0                    # 锚点方向（body_dir 的低通值，见 _step_chain）
        # 身体朝向三条通道（见常量区说明）：头看哪儿 / 想往哪走 / 身体实际转到哪儿
        self.body_dir = 1.0                 # +1 朝右 → 0 横对镜头（转身半途）→ -1 朝左
        self._last_body_dir = 1.0
        self.move_dir = 1.0                 # 这一 tick 的行进意图（0 = 站定/贴墙）
        self.look_dir = 1.0                 # 头看向哪一侧（由 head_angle 推出）
        self.turn_mode = "idle"             # idle / walk / turn
        self.turn_progress = 0.0            # 1-|body_dir|：0 对齐、1 完全横对镜头
        self._turn_imp = 0.0                # 转身冲量（喂给前 TURN_IMP_SEGS 节）
        # 身体冲量（喂给前 BODY_IMP_SEGS 节）：起跳 / 咬合由 AI 直接给躯干，
        # 不是只推头点。_step_chain 取走并清零。
        self._body_imp_x = 0.0
        self._body_imp_y = 0.0
        # JawsSnapShut 的反作用（前节前冲 / 中后节后坐），_step_chain 取走并清零
        self._jaw_rec_x = 0.0
        self._jaw_rec_y = 0.0
        self.tongue_speed = TONGUE_SPEED      # 本次射舌的出手速度（按距离插值）
        self.tongue_warmup_left = 0
        # LizardGraphics.cs:433-437: region dependent in game, one third in
        # the standalone/default room.  Keep this per individual so two
        # salamanders can legitimately have different body/eye palettes.
        self.black_salamander = bool(self.breed.key == "salamander"
                                     and self._anim_rng.random() < (1.0 / 3.0))
        self._wall_turn_left = 0              # 墙上换向的摆体剩余帧
        self._wall_dir_prev = None            # 上一帧的爬行方向（换向检测）
        # Attack 动作序列（文档 §9.3 / §10.3）：Prepare → Lunge → Bite → Recover，
        # 由 _start_bite 触发，_step_attack_pose 每 tick 给各 chunk 单独写速度。
        self._atk_phase = None
        self._atk_t = 0
        self._atk_dir = (1.0, 0.0)
        # 原版 bodyWiggleCounter：停着也不像一块死物（文档 §10.5）
        self.wiggle = 0.0
        # 原版 bodyWiggle（相位累加器）与 desperationSmoother。两者都是**物理量**：
        # 会给三节 bodyChunk 直接灌速度（Lizard.cs:2116-2158），不是贴图抖动。
        self._wiggle_ph = 0.0
        self._desp = 0.0
        # 舌头（文档 §六）：None / "out" / "hold" / "back"
        self.tongue_state = None
        self.tongue_len = 0.0
        self.tongue_dir = (1.0, 0.0)
        self.tongue_tip = (0.0, 0.0)
        self.tongue_prey = None
        self.tongue_grab = None
        self.tongue_t = 0
        self.tongue_cd = 0
        # 后空翻（文档 §9.4）
        self.flip_left = 0
        self.flip_dir = 1
        self.flip_ang = 0.0
        self.flip_wait = 0
        # AI 这一 tick 的行进意图速度（物理改 vx 之前先记下来：脚支撑会把 vx 清零，
        # 不能拿积分后的 vx 当「想往哪走」）
        self._vx_intent = 0.0
        # AI 这一 tick 真正想走的速度（_drive_vx 记的 want）。脚支撑会把实际 vx
        # 压到 TURN_VX 以下，转身状态机看的是意图而不是被压过的结果。
        self._want_vx = 0.0
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
        self.bite_event = None
        self.bite_wind = 0            # 咬合前摇剩余 tick（原版 biteDelay）
        self._bite_wind_obj = None    # 前摇锁定的目标 / 这一口掷出的伤害
        self._bite_wind_dmg = 0.0
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

    def _camo_hide(self) -> bool:
        """潜伏中：站着不动、没追东西、没被抓、没受伤 —— 伪装才成立。"""
        if (self.dead or self.stun > 0 or self.held_by_hand or self.hauled
                or self.state != ItemState.FREE or self.hurt_flash > 0):
            return False
        if self.prey.chasing:
            return False
        return math.hypot(self.vx, self.vy) < CAMO_HIDE_VX

    @property
    def camo_hidden(self) -> bool:
        """当前是否已达到可被视为「隐身」的白蜥迷彩状态。

        关系/威胁系统不能只看 ``breed.camo``：白蜥刚开始淡入、移动淡出，
        以及受伤乱闪时都仍然应该能被发现。统一使用混合度阈值并排除乱闪，
        让猫和蜥蜴的感知口径与画面实际可见度一致。
        """
        return bool(getattr(self.breed, "camo", False)
                    and self.camo_flicker <= 0
                    and self.camo_mix >= CAMO_HIDDEN_MIX)

    def camo_tick(self, win, tick: int) -> None:
        """白蜥：**每 tick** 采一次「自己周围」的**背景**主色，整只（含头）保持它。

        采样在 `platform.bgcolor` 里会把「我们自己画的前景」（猫 / 生物 / 物品 /
        HUD）挖掉，只留桌面背景 —— 别的猫从旁边走过不会带着白蜥一起变色。
        潜伏不动时持续采样（一直贴着背景走）；发起攻击 / 被攻击立刻淡出；受伤
        期间还会不由自主地胡乱变色（原版白蜥受伤乱闪）。只有 `breed.camo`
        的品种（白蜥）跑。采样本身按位置缓存，站着不动时几乎不花时间。
        """
        if not getattr(self.breed, "camo", False):
            return
        if self.camo_flicker > 0:
            # 受伤乱闪：每隔几 tick 换一个随机色，体色和头色一起乱变
            self.camo_flicker -= 1
            if self.camo_flicker % CAMO_FLICKER_STEP == 0:
                self.camo_color = (self.rng.randrange(256), self.rng.randrange(256),
                                   self.rng.randrange(256))
            self.camo_mix = 1.0
            return
        hide = self._camo_hide()
        if hide:
            from ..platform.bgcolor import dominant_around
            rx = max(self.body_rad * 4.5, CAMO_SAMPLE_RADIUS_X)
            ry = max(self.body_rad * 3.5, CAMO_SAMPLE_RADIUS_Y)
            col = dominant_around(win, self.x, self.y, rx, ry)
            if col is not None:
                self.camo_target = col
        elif self.camo_mix <= 0.02:
            # 已经完全垮掉：忘掉旧色，下次潜伏时重新采（淡出是渐近的，到不了 0.0）
            self.camo_target = None
        if self.camo_target is not None:
            if self.camo_color is None:
                self.camo_color = self.camo_target
            else:
                t = CAMO_COLOR_RATE
                # 使用四舍五入并在最后一个色阶内直接收敛，避免 int 截断让
                # 某个通道永远停在目标值 1 像素之外，导致“变色不精确”。
                if max(abs(self.camo_color[i] - self.camo_target[i])
                       for i in range(3)) <= 1:
                    self.camo_color = tuple(self.camo_target)
                else:
                    self.camo_color = tuple(
                        int(round(self.camo_color[i]
                                  + (self.camo_target[i] - self.camo_color[i]) * t))
                        for i in range(3))
        # 淡入 / 淡出：潜伏时满值（不再呼吸），追猎或被攻击后迅速垮掉
        tgt = 1.0 if hide else 0.0
        rate = CAMO_FADE_IN if tgt > self.camo_mix else CAMO_FADE_OUT
        self.camo_mix = clampf(self.camo_mix + (tgt - self.camo_mix) * rate, 0.0, 1.0)

    def bounding_pad(self):
        """脏矩形外扩半径。"""
        return (max(self.body_rad, self.head_rad) + self.head_conn
                + 26.0 * self.breed.limb_size + 8.0)

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
        self.bite_wind = 0
        self._bite_wind_obj = None
        self._bite_wind_dmg = 0.0
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
        self.camo_flicker = CAMO_FLICKER_TICKS    # 白蜥：受伤不由自主地胡乱变色
        if shielded:
            # 头甲把矛弹开：头部强烈白闪一下（用户口径：表示这次弹开无效）
            self.head_flash = HEAD_DEFLECT_FLASH
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
        self.decide(WL, HL, cursor=cursor)
        self.act(WL, HL, cursor=cursor)
        self.step_physics(WL, HL, cursor=cursor)

    def step_physics(self, WL: float, HL: float, cursor=None) -> None:
        """物理与渲染状态推进（不含 AI）：被拎着 / 被猫拖着 / 尸体 / 自由态。

        拆出来是为了让 items.py 能做「全体先感知、再决策、最后执行」—— 决策
        阶段不碰速度也不碰世界，执行阶段才真正落到物理上。
        """
        self.last_x, self.last_y = self.x, self.y
        self._vx_intent = self.vx      # AI 的意图速度（在物理改 vx 之前先记下来）
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
        if self.head_flash > 0:
            self.head_flash -= 1
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
            # 尸体不再按 TTL 自行消失（用户口径：蜥蜴尸体老是突然消失）。
            # 只有被拖出窗口 / 被甩出去（items._cull_flung_corpses）才清除。
            self.vx *= 0.9
            self._integrate(WL, HL)
        else:
            self._integrate(WL, HL)

        self._step_turn()                   # 身体朝向 / 转身状态（在链体之前定 body_dir）
        self._step_attack_pose()            # Attack 四阶段：先给 chunk 写速度，再映射体态
        self.anim = self._intent()          # AI → 动画意图（这一帧的映射只发生一次）
        self._step_chain(self._ground)
        self._step_legs(HL)
        self._step_head()
        self._step_depth()
        self._step_head_point(WL)     # 头是挂在第 0 节前方的软体末端（要在 turn_lift 之后）
        self._tongue_tick()           # 舌头（LizardTongue）：射出 / 拽回 / 到嘴转咬合
        self._step_cosmetics()
        self._want_vx = 0.0           # 这一 tick 的意图已经用完（下一 tick AI 再写）

        if self.bite_wind > 0:
            self.bite_wind -= 1
            self._bite_homing()               # 前摇里继续瞄 / 压上去
            if self.bite_wind == 0:
                self._snap_jaws()             # 原版 JawsSnapShut：这一刻才结算
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
        return tq.support(self.x, self.y, HL, self.caps)

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
        # 卡住检测（文档 §28）：手里有一条正式路线、却连着几个窗口都没挪窝 ——
        # 说明这条路走不通（贴着爬不上去的墙、卡在门口）。丢掉它，下一 tick
        # 重新问图，而不是永远顶在同一面墙上。
        if o is not None and plan.drifted(o.x, o.y):
            # 目标从我规划时的位置漂走了（文档 §12）：这条路线已经过时，立即
            # 重规划 —— 不是硬走完 TTL 才对。
            self.plan = None
            return False
        edge = (leg.mode, round(leg.x, 1), round(leg.y, 1))
        lvl = self._stuck.update(self.x, self.y, self._tick, owner=leg.x, edge=edge)
        if lvl >= 1:
            if self._stuck.kind == STUCK_NAVIGATION:
                # 同一条边反复把我带到同一个死点：记进导航黑名单（文档 §13），
                # 下一次寻路自然绕开它，而不是又给同一条路线。
                self._stuck.block(leg.x, leg.y, self._tick)
            else:
                # 路线是对的、位移被墙 / 碰撞吞掉了（STUCK_PHYSICS）：
                # 蹭一下脱困就行，**不丢路线**。
                if self._contact_floor and self.hop_cd <= 0:
                    self._leap(0.55)
                    self.hop_cd = HOP_CD
        if lvl >= 2:
            self.plan = None
            self._climb_release()
            self._stuck.reset(self.x, self.y, self._tick)
            return False
        if leg.mode in ("climb_wall", "climb_pole", "climb_background",
                        "jump", "hop"):
            return False                   # 爬 / 跳各有自己的执行器
        if o is not None and o.visible:
            self.look_at = (o.x, o.y)
        goal_x, goal_y = leg.x, leg.y
        if leg.mode == "drop" and leg.tx is not None:
            goal_x, goal_y = leg.tx, leg.ty      # 掉下去：朝落点走，剩下交给重力
        self.target, self.target_obj = (goal_x, goal_y), (o.obj if o else None)
        sp = self._state_speed(SNIFF_SPEED)
        want = clampf((goal_x - self.x) * 0.07, -sp, sp)
        self._drive_vx(want, WALK_TURN)
        return True

    def _leg_joint(self) -> float:
        """原版 LizardLimb.jointDist：25 * (sizeFac+1)/2（本项目 BODY_SCALE 恒 1）。

        这是「髋 → 脚」的硬上限，也是 FindGrip 的搜索半径。四足步态、
        ConnectToPoint、FindGrip 全部走这一个值，别再各自算一份。
        """
        b = self.breed
        return LEG_JOINT * ((b.body_size_fac + 1.0) * 0.5) * BODY_SCALE

    def _apply_foot_support(self) -> None:
        planted = [lg for lg in self.legs if lg.planted and not lg.disabled
                   and lg.grip >= LEG_GRIP_DELAY]
        if not planted:
            # 没有任何脚真正踩住地形：身体贴地也只能滑（原版 noGripSpeed 是
            # 速度上限，不是每帧乘一次的摩擦系数 —— 乘系数会几乎瞬间归零）。
            if (self._contact_floor and not self.dead
                    and self.state == ItemState.FREE):
                self.vx = clampf(self.vx, -NO_GRIP_SPEED, NO_GRIP_SPEED)
            return
        # 有支撑：推进仍然由 AI 给（宠物要跟得上鼠标），这里只做辅助 ——
        # 脚是支点，身体被脚拉住，超出腿长的部分把身体往脚的方向回拉一点，
        # 而不是反过来把脚从地面上拽走。
        joint = self._leg_joint()
        corr = 0.0
        for lg in planted:
            hip = self.seg[min(lg.pair, len(self.seg) - 1)]
            ddx, ddy = lg.x - hip.x, lg.y - hip.y
            dd = math.hypot(ddx, ddy)
            if dd > joint * LEG_ANCHOR_MAX:
                # 这不是支点，是留在别的平面上的坏锚点（身体掉了下去、脚还踩
                # 在原来的平台上）。它不参与回拉，否则会像橡皮筋把身体死死拽
                # 在原处（用户报的脚黏在平面 / 被拽走后脚把蜥蜴拉回去）。
                continue
            over = dd - joint
            if over > 0.0 and dd > 1e-6:
                corr += ddx / dd * over      # 身体朝脚的方向回拉
        corr /= len(planted)
        if corr != 0.0 and len(planted) <= self._leg_min_support():
            # 支撑脚只剩最少数量了：这只脚不可能再松开（松开就一只脚都不剩），
            # 于是不能再让身体继续把它拉长 —— 身体朝支撑脚方向的那一份速度直接
            # 拿掉，等腾空的脚落地接管之后这只脚才会换步。
            if self.vx * corr < 0.0:
                self.vx = 0.0
        self.vx += clampf(corr * FOOT_PULL_K, -FOOT_PULL_MAX, FOOT_PULL_MAX)

    def _floor_under(self, x, y):
        """脚下真实的站立面。不会用杆的品种不把横杆杆面当地面（用户口径：
        绿蜥蜴等无杆能力的品种无论如何都不该与杆子互动）。"""
        if self.terrain is None:
            return self._ground
        return self.terrain.floor_under(x, y, self.caps)

    def _collide_solids(self, prev_y=None) -> None:
        """庇护所墙壁（chunkphys.solids）对蜥蜴也是实心地形。

        用户口径：庇护所的墙要正确传给其它生物判定碰撞，尤其是蜥蜴。以前蜥蜴
        只读 terrain 的竖线（杆 / 背景墙），庇护所墙体不在它眼里 —— 蜥蜴能直接
        穿进屋里。这里按 chunkphys 同一套 AABB 把头和整条身体推出去。
        """
        from ..core import chunkphys
        rects = chunkphys.solids()
        if not rects:
            return
        step_up = getattr(chunkphys, "STEP_UP", 8.0)

        def _push(px, py, r):
            return _push_out(px, py, r, rects, step_up)

        r = self.head_rad
        # ① 竖直扫掠补判：这一帧整条身体从障碍顶边上方跨到下方时，先把它接回
        #    顶面。单点 push-out 会因为「已经整个越过去」漏判 —— 用户报的
        #    「从墙上方杆子落下来穿透壁」。
        if prev_y is not None:
            top = chunkphys.sweep_drop_top(self.x, r, prev_y, self.y, rects)
            if top is not None:
                dy = (top - r) - self.y
                self.y = top - r
                for s in self.seg:
                    s.y += dy
                if self.vy > 0.0:
                    self.vy = 0.0
                self._contact_floor = True
        nx_, ny_ = _push(self.x, self.y, r)
        if nx_ != self.x:
            if (nx_ - self.x) * self.vx < 0.0:
                self.vx = 0.0
            self.x = nx_
        if ny_ != self.y:
            if (ny_ - self.y) * self.vy < 0.0:
                self.vy = 0.0
            if ny_ < self.y:
                self._contact_floor = True
            self.y = ny_
        for s in self.seg:
            sx, sy = _push(s.x, s.y, s.rad)
            s.x, s.y = sx, sy

    def _collide_static_lines(self, WL: float) -> None:
        """兼容旧调用：杆是可抓的 Climb 表面，不阻断地面运动。"""
        return

    def _collide_chain_lines(self, WL: float) -> None:
        """杆不会把躯干链推出去；实体墙由 _collide_solids 处理。"""
        return

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
        py = self.y
        self.x += self.vx
        self.y += self.vy
        self._collide_static_lines(WL)
        self._collide_solids(py)

        r = self.head_rad
        # 转身时上半身支起：支起量现在抬的是「挂在体前的头」（_step_head_point），
        # 躯干驱动点自己仍然踏在这一层地面上。
        floor = self._ground - self.body_rad * HEAD_STAND_FAC
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

    def _climb_assign(self, sx, top, bot, direction, kind) -> None:
        """同一表面连续攀爬时保留抓附；换表面时才重新抓。"""
        sx, top, bot = float(sx), float(top), float(bot)
        same = (self.climb_x is not None and abs(self.climb_x - sx) <= 1.0
                and self.climb_kind == kind and self.climb_top is not None
                and abs(self.climb_top - top) <= 12.0 and self.climb_bot is not None
                and abs(self.climb_bot - bot) <= 12.0)
        if not same:
            self.climb_attached = False
            self.climb_side = 0
            self._wall_dir_prev = None
        self.climb_x = sx
        self.climb_top = top
        self.climb_bot = bot
        self.climb_dir = 1 if direction >= 0 else -1
        self.climb_kind = kind

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
            kind = surf[3] if len(surf) > 3 else "pole"
            if (kind == self.climb_kind
                    and abs(float(surf[0]) - self.climb_x) <= 1.0
                    and float(surf[1]) <= self.y + 12.0
                    and float(surf[2]) >= self.y - 12.0):
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
                    self.climb_side = -1 if self.chain_dir < 0.0 else 1
            else:
                # 走过去：朝墙挪（墙体不挡身体，与「窗口顶边可站」同一口径）
                want = CLIMB_APPROACH_SPEED * (1.0 if dx > 0.0 else -1.0)
                self.vx += (want - self.vx) * 0.5
                self.vx *= 0.85
                self.vy = (self.vy + GRAVITY * self.room_gravity) * AIR_FRICTION
                prev_y = self.y
                self.x += self.vx
                self.y += self.vy
                self._collide_solids(prev_y)
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
        # 实体墙有厚度，身体停在墙面外；杆和背景可从任一侧贴住中心线。
        if self.climb_kind == "wall":
            # 实体墙有厚度，身体停在可碰撞墙面外侧。
            anchor_x = sx + self.climb_side * (r + LINE_COLLIDE_PAD)
        elif self.climb_kind == "background":
            # 背景墙是非实体的视觉表面，但蜥蜴仍应贴在背景边缘，不能把
            # 身体中心线直接穿过背景图。偏移小于实体墙，保留原版贴面感。
            anchor_x = sx + self.climb_side * (r * 0.65 + LINE_COLLIDE_PAD)
        else:
            # 竖杆是中心线，允许从任一侧抓附。
            anchor_x = sx
        self.vx += (anchor_x - self.x) * CLIMB_GRIP_SPRING
        self.vx *= CLIMB_GRIP_DAMP
        self.x += self.vx
        self.vy = -CLIMB_SPEED * self.climb_dir
        self.y += self.vy
        if self.climb_kind == "wall":
            self._collide_solids(self.y - self.vy)
        self._contact_floor = False
        self.wall_dir = self.climb_side
        # 身体轴贴墙：前节朝爬行方向、后节反向拉开（墙面切向＝纵向）。旧实现只写
        # 驱动点的 x/y，躯干完全被动跟，看起来像「被提着贴在墙上」。
        if self._wall_dir_prev is not None and self._wall_dir_prev != self.climb_dir:
            self._wall_turn_left = WALL_TURN_TICKS     # 上↔下换向：先摆过去再爬
        self._wall_dir_prev = self.climb_dir
        lean = -1.0 if self.climb_dir >= 0 else 1.0
        if self._wall_turn_left > 0:
            self._wall_turn_left -= 1
            lean = -lean                               # 换向那几帧先把身体反着甩
        if len(self.seg) >= 3:
            self.seg[0].vy -= WALL_LEAN * lean
            self.seg[2].vy += WALL_LEAN * lean
        self.chain_dir = 1.0 if self.climb_side >= 0 else -1.0
        top, bot = self.climb_top, self.climb_bot
        # Lizard.cs:2190-2204（followingConnection 离开 Climb tile）
        # 到达爬面顶部时必须结束 Climb 连接，交回普通地面/空中积分；旧代码
        # 只处理 bot，向上爬会一直把头推进墙体，随后在墙边抖动或穿出屏幕。
        if top is not None and self.climb_dir > 0 and self.y < top:
            self.y = max(float(top), r)
            self.vy = 0.0
            self._contact_floor = False
            self.plan = None
            self._climb_release()
        elif bot is not None and self.y > bot:
            self.y = min(bot, floor)              # 爬到底 / 线到头：站住并脱墙
            self.vy = 0.0
            self._contact_floor = True
            self.plan = None
            self._climb_release()
        elif self.y > floor:
            self.y = floor
            self.vy = 0.0
            self._contact_floor = True
            self.plan = None
            self._climb_release()
        elif self.y < r:
            self.y, self.vy = r, 0.0
            # 线一直延伸到窗口上边缘时没有可站的上端；不能在 y=r 处
            # 永远保持附着，否则下一帧会重复向上爬并卡在顶边。
            if self.climb_dir > 0:
                self.plan = None
                self._climb_release()
        elif top is not None and self.y < top + 4.0:
            self.y = max(r, top + 4.0)            # 到墙头：脱墙，站到墙沿上
            self.vy = 0.0
            self.plan = None
            self._climb_release()

    # ── AI ──
    # ══ 第一层：感知（同一份世界快照，不做任何决策）══
    def should_scan(self, tick: int) -> bool:
        """这一 tick 要不要重建观察（文档 §37 AI 时间片）。

        按 id 错峰：平均每 `PERCEIVE_EVERY` tick 才扫一次，避免所有蜥蜴同一 tick
        一起跑昂贵的感知。第一次必须扫，否则 `obs` 一直是空的。
        """
        if not self._scanned:
            return True
        # 旧存档超出 AI 时间片预算时，有些个体会隔数帧才轮到自己。
        # 再次轮到时必须刷新过期观察，避免追赶早已离开的目标。
        if int(tick) - self._scan_tick >= PERCEIVE_EVERY:
            return True
        return (int(tick) + self.id) % PERCEIVE_EVERY == 0

    def perceive(self, WL, HL, targets=(), prey=(), threats=(), others=(), pack=(),
                 lizards=(), blockers=(), surfaces=(), terrain=None, tick=None,
                 scan=True) -> dict:
        """这一 tick 看见 / 听见什么。

        每条记录都带上距离、关系权重、视野锥得分、**可见性**（锥内且没被挡）、
        姿态（匍匐更难被盯上）以及「这只猎物是不是已经归别人」。这一层不改世界、
        不改速度 —— 所以多只蜥蜴可以拿同一份快照各自决策。

        `scan=False`（AI 时间片，文档 §37）：这一 tick 不重建观察，只刷新地形 /
        遮挡 / 同伴这些便宜字段，直接复用上一次的 `obs`。记忆按跳过的 tick 数
        一次性衰减，保证有效速率和逐帧跑时一致。
        """
        self._tick = int(tick) if tick is not None else self._tick + 1
        # 桌面生态按用户设定不做视觉遮挡；实体碰撞和路径阻挡仍由地形层处理。
        self._blockers = ()
        self.climb_surfaces = tuple(surfaces or ())   # 这一帧可攀爬的竖线
        if terrain is not None:
            self.terrain = terrain                    # 全场共用的一份地形快照
        self.peers = tuple(lizards)
        if not scan:
            self.mem.miss()
            return self.obs
        self._scanned = True
        self._scan_tick = self._tick
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
            if _cat_waa(obj) and not dead:
                # A Survivor broadcasting waa is treated as a dangerous
                # pressure state: lizards give it space instead of hunting it.
                # The normal cat observation is retained for memory, while a
                # stronger threat observation makes Flee win in decide().
                thrs.append(self._observe(obj, ox, oy, "threat",
                                          max(2.0, w), dead, fainted,
                                          "crawl" if crawl else "stand"))
            cats.append(self._observe(obj, ox, oy, "cat", w, dead, fainted,
                                      "crawl" if crawl else "stand"))
        for obj, w in prey:
            if obj is self:
                continue
            preys.append(self._observe(obj, getattr(obj, "x", self.x),
                                       getattr(obj, "y", self.y), "prey", w))
        for obj, w in threats:
            if obj is self:
                continue
            thrs.append(self._observe(obj, getattr(obj, "x", self.x),
                                      getattr(obj, "y", self.y), "threat", w))
        for obj, w in others:
            if obj is self:
                continue
            rivs.append(self._observe(obj, getattr(obj, "x", self.x),
                                      getattr(obj, "y", self.y), "rival", w))
        for obj, w in pack:
            if obj is self:
                continue
            pk.append(self._observe(obj, getattr(obj, "x", self.x),
                                    getattr(obj, "y", self.y), "pack", w))
        self.obs = {"cats": tuple(cats), "prey": tuple(preys),
                    "threats": tuple(thrs), "rivals": tuple(rivs),
                    "pack": tuple(pk)}
        self._update_memory(cats, preys)
        return self.obs

    def _los(self, x0, y0, x1, y1, obj) -> bool:
        """兼容旧调用：桌面生态不做几何视觉遮挡。"""
        return True

    def _observe(self, obj, ox, oy, kind, w=1.0, dead=False, fainted=False,
                 stance="stand") -> Observation:
        """把一个候选变成观察记录，保留品种视距和视野锥。"""
        d = math.hypot(ox - self.x, oy - self.y)
        v = self._visual_fac(ox, oy)
        if obj is self.target_obj:
            in_cone = d <= self.notice_r
        else:
            in_cone = d <= self.notice_r * (VIS_BACK_FAC + (1.0 - VIS_BACK_FAC) * v)
        return Observation(obj, ox, oy, d, kind, w, v, in_cone, dead, fainted,
                           stance, self._claimed_by(obj), los=True)

    def _claimed_by(self, obj):
        """这只猎物是不是已经被别的蜥蜴认领（它咬倒的、正往回叼的）。

        全场归属表由 `items._step_lizards()` 每 tick 建一次（文档 §37）：旧版对
        每个候选都要遍历所有同伴跑 `owns()`，一张表就够了。没有表时（旧入口 /
        单元测试直接调用）退回逐同伴扫描。
        """
        claims = self._claims
        if claims is not None:
            owner = claims.get(id(obj))
            return None if owner is None or owner is self else owner
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
    def decide(self, WL, HL, cursor=None) -> str:
        """Flee(威胁) > ReturnPrey/CarryPrey(猎物) > Injured > 同族竞争 > Hunt
        > InvestigateSound > Pack > Lurk > Idle。产出行为名与接近路线，不碰速度。
        """
        self.warning_t = max(0, self.warning_t - 1)
        self.guard_t = max(0, self.guard_t - 1)
        # 兼容旧存档字段；桌面生态不再启用驯服或认主关系。
        self.tamed, self.friend_id, self.like = False, None, 0.0
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
        obs = self.obs
        # ① 原版 Behavior.Flee（ThreatTracker，utility 权重 1.0 最高）
        self._pick_threat(obs["threats"])
        if self.threat is not None:
            self.threat_t = max(self.threat_t, 10)      # 看得见就续上逃跑计时
        if self.threat_t > 0 and self._flee_outweighs_hunt(obs):
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
        cursor_obs = self._cursor_interest(WL, HL, cursor)
        if cursor_obs is not None:
            return self._stage("InvestigateCursor", cursor_obs)
        if self._lurk_pref():
            return self._stage("Lurk", None)
        return self._stage("Wander")

    def _stage(self, name, obs=None) -> str:
        """记下这一帧的行为（观察记录一起留着，执行阶段要用）。"""
        if name != "InvestigateCursor":
            self._cursor_until = 0
        self.stage = name
        self.stage_obj = obs if isinstance(obs, Observation) else None
        if self.stage_obj is not None:
            self.look_at = (self.stage_obj.x, self.stage_obj.y)
        return name

    def _cursor_interest(self, WL, HL, cursor):
        """桌面交互：闲暇时偶尔靠近鼠标，不占用猎物记忆或攻击目标。"""
        if cursor is None:
            return None
        x, y = cursor
        d = math.hypot(x - self.x, y - self.y)
        if not (0 <= x <= WL and 0 <= y <= HL and 28.0 < d < 420.0):
            return None
        if self._tick >= self._cursor_until:
            if self._tick < self._cursor_retry:
                return None
            self._cursor_retry = self._tick + self.rng.randint(180, 420)
            if self.rng.random() >= 0.08:
                return None
            self._cursor_until = self._tick + self.rng.randint(90, 180)
            self.plan = None
        return Observation(None, x, y, d, "cursor")

    # ══ 第三层：动作（真正改速度 / 下巴；世界结算在 items.py）══
    def act(self, WL, HL, cursor=None) -> None:
        st = self.stage
        o = self.stage_obj
        # 攀爬：够得着的竖杆 / 背景墙竖边就贴上去（原版 Climb / Wall tile）。
        # 每 tick 重算一次，所以「追猎以外」的状态自然松手。
        self._climb_plan(self._climb_obs(st, o), HL)
        if st in ("", "Stunned", "CasualBite"):
            return
        # 地形路线的当前段是「走 / 掉」时由这里接管位移；「爬 / 跳」段交给
        # 上面的 _climb_plan 与下面的 _approach_tick，互不打架。
        if (self.plan is not None and self.plan.legs
                and st in ("HuntPrey", "ApproachPrey", "InvestigatePos",
                           "InvestigateSound", "InvestigateCursor", "PackCoordination", "Flee")
                and self._route_tick(o, WL, HL)):
            return
        if st == "InvestigateCursor":
            self._investigate_tick(o, WL, HL)
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
            if st == "Lurk":
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
    def _climb_obs(self, st, o):
        """哪些状态允许把「这一帧的观察」交给攀爬层（原版 Climb / Wall tile）。

        追猎那几个状态一直交给它；其余状态**只在这条正式路线里含爬段时**才交
        —— Flee / ReturnPrey 之类的路线也会爬墙，但没有路线时不该临时抓线。
        """
        if st in ("Attack", "HuntPrey", "ApproachPrey", "InvestigatePos",
                  "InvestigateSound", "InvestigateCursor", "PackCoordination"):
            return o
        plan = self.plan
        if (o is not None and plan is not None and plan.alive(self._tick)
                and getattr(plan, "climb", None) is not None):
            return o
        return None

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
        """中置信度：去最后看见它的位置找（原版 Investigate，不亮牙）。

        记忆里的位置经常不在同一层（猎物上过窗口顶边 / 杆顶）：这时不再「对着
        那个 x 一路撞墙」，而是先向地形层要一条正式路线（文档 §29/§30）。
        """
        if o is None:
            return
        self.look_at = (o.x, o.y)
        if self._vertical_detour(o.x, o.y, kind=route_kinds("investigate")):
            return
        sp = self._state_speed(SNIFF_SPEED)
        want = clampf((o.x - self.x) * 0.06, -sp, sp)
        self._drive_vx(want, WALK_TURN)

    def _vertical_detour(self, gx, gy, kind=None, no_jump=False) -> bool:
        """目标明显不在同一层时，向地形层要一条正式路线并安装成 self.plan。

        返回 True 表示这一帧改由路线层驱动（_route_tick 走 / _climb_plan 爬 /
        _approach_tick 跳）。原版蜥蜴拿到的是 LizardPather 的 MovementConnection
        序列，不是「动作层临时发现一根竖线就爬」—— 这里照那个口径先问图
        （文档 §6/§29/§30）。

        ``kind`` 是**这个行为**要的路线哲学（文档 §5：Investigate 保守、
        ReturnPrey 留退路、Pack 只要过得去）；``no_jump`` 给那些没有跳跃执行器
        的状态用（叼着猎物时不该跳）。
        """
        if self.terrain is None or self.caps is None or self.dead:
            return False
        if abs(gy - self.y) <= CLIMB_MIN_DY:
            return False                       # 差不多在同一层：直线趋近更省
        plan = self.plan
        if (plan is not None and plan.alive(self._tick) and plan.legs
                and plan.mode != "lurk"):
            if not plan.drifted(gx, gy):
                return True                    # 已经有一条还活着的路线，继续照它走
            self.plan = None                   # 目标漂走了：重规划
        route = _terrain_route(self.terrain, self.caps, self.x, self.y, gx, gy,
                               self._tick, ROUTE_TTL, kind=kind,
                               avoid=self._stuck.blocked_keys(self._tick))
        if route is None or not route.legs:
            return False
        if no_jump and route.legs[0].mode == "jump":
            return False                       # 这个状态没有跳跃执行器
        if all(lg.mode == "walk" for lg in route.legs):
            return False                       # 全程平地：不必抢直线趋近
        self.plan = route
        return True

    def _climb_plan(self, o, HL) -> None:
        """要不要贴着一条竖线爬（原版 LizardPather 的 Climb / Wall 通行能力）。

        ``surfaces`` 每项 ``(x, y_top, y_bot, kind)``：kind == "wall" 是实体墙
        的可见墙段，kind == "background" 是非实体背景墙边缘；两者只有会爬墙的
        品种（WallClimber：蓝/白/鳗鱼蜥）才考虑。kind == "pole" 是竖杆，会爬杆
        的品种都能用。选中条件不再要求「已经贴到
        线上」，而是「线够得着目标那一端」且「我够得着这条线」—— 线还在我这一层
        就抓上去，否则墙底/杆底落在我这层就走过去（原版 Floor→Wall 那条连接）。
        真正的位移交给 _step_wall（附着物理），不再每帧硬钉 x。
        """
        if o is None or self.dead:
            self._climb_release()
            return
        plan = self.plan
        if plan is not None and plan.alive(self._tick) and plan.mode != "lurk":
            # Planner（Terrain ↔ Capability 过滤）已经给了这一帧的正式路线：
            # 动作层不再自己挑线（文档 §6）—— 它只承接「去哪个上墙点 / 往哪个
            # 方向爬」，走路段落归 _route_tick，跳 / 掉段落归 _approach_tick。
            climb = getattr(plan, "climb", None)
            if climb is not None and plan.mode in _CLIMB_MODES:
                sx, top, bot, up = climb
                self._climb_assign(sx, top, bot, up, _CLIMB_MODES[plan.mode])
                return
            # 路线已经离开竖面，结束旧的附着，交还给平地 / 跳跃执行器。
            self._climb_release()
            return
        up = o.y < self.y - CLIMB_MIN_DY
        down = o.y > self.y + CLIMB_MIN_DY
        if not (up or down):
            self._climb_release()
            return
        # 目标仍在当前这条线上时保留附着状态；否则每帧重置为未抓住，
        # 身体只能在墙边抖动而不能真正向上移动。
        if (self.climb_x is not None and self._climb_span_ok()
                and self.climb_kind in ("wall", "background", "pole")):
            self.climb_dir = 1 if up else -1
            return
        grounded = (self._contact_floor
                    or self.y >= self._ground - self.body_rad * HEAD_STAND_FAC
                    - FLOOR_GRIP_TOL)
        pole_surfaces = ()
        if grounded and self.terrain is not None:
            try:
                pole_surfaces = tuple(s for s in self.terrain.geom.verticals(None)
                                      if s.climb == "pole")
            except Exception:
                pole_surfaces = ()
        best = None
        for surf in self.climb_surfaces:
            sx, top, bot = float(surf[0]), float(surf[1]), float(surf[2])
            kind = surf[3] if len(surf) > 3 else "pole"
            if kind == "wall" or kind == "background":
                if not (self.breed.climb_wall and self.breed.wall_attach):
                    continue            # 不会 Background Climb 的品种：背景不是它的地形
            elif not self.breed.climb_pole:
                continue
            if kind == "pole" and grounded:
                # A grounded lizard may walk to a pole only when its actual
                # support plane touches that pole. Keep airborne on-line grabs
                # available so jump capture of floating poles still works.
                supported = any(
                    ps.pole is not None
                    and abs(ps.x - sx) <= 1.0
                    and abs(ps.top - top) <= 1.0
                    and abs(ps.bot - bot) <= 1.0
                    and ps.pole.touches_support_y(self._ground)
                    for ps in pole_surfaces)
                if not supported:
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
            self._climb_assign(best[1], best[4], best[5], best[2], best[3])
        else:
            self._climb_release()

    def _hop_vy(self) -> float:
        """蹬地起跳初速：按「跳跃能力」算，不是按「会不会爬」。

        旧实现拿 breed.can_climb 当跳跃能力用：不会爬的绿蜥 / 焦糖蜥连跳也不会，
        会爬的白蜥却按体型硬算 —— 「爬」和「跳」被绑成了一件事。现在读
        breed.jump_fac（反编译 loungeJumpyness），0.5 = 基准（旧值不变）。
        """
        fac = float(getattr(self.breed, "jump_fac", 0.5))
        if fac <= 0.0:
            return 0.0
        return (CLIMB_HOP * math.sqrt(max(0.4, self.breed.body_size_fac))
                * (0.7 + 0.6 * min(1.0, fac)))

    def _prey_dir(self, o):
        """猎物在往哪跑：伏击点要挑在它的去路侧后方（文档 §15）。"""
        obj = getattr(o, "obj", None)
        vx = float(getattr(obj, "vx", 0.0) or 0.0)
        vy = float(getattr(obj, "vy", 0.0) or 0.0)
        if abs(vx) + abs(vy) > 0.05:
            return (vx, vy)
        lp = self.mem.last_pos
        if lp is not None and (abs(lp[0] - o.x) + abs(lp[1] - o.y)) > 1.0:
            return (o.x - lp[0], o.y - lp[1])
        return (1.0 if o.x >= self.x else -1.0, 0.0)

    def _plan_for(self, o, WL, HL):
        """接近规划：同一套 utility，按品种调「绕路 / 落点 / 贴墙 / 起跳倾向」。

        追猎要哪种路线哲学（文档 §5）与导航黑名单（§13）在这里交给路线层：
        伏击型要留退路，冲刺型愿意走单向。
        """
        if o is None:
            return None
        prefs = prefs_for(self.breed.key)
        floor = HL - self.body_rad * HEAD_STAND_FAC
        hop = self._hop_vy()
        return plan_approach(o.x, o.y, self.x, self.y, floor, WL, self._bite_reach(),
                             prefs, GRAVITY, hop, AIR_FRICTION,
                             sprint=self.sprint, base_speed=self._move_base(),
                             tick=self._tick, terrain=self.terrain, caps=self.caps,
                             route_kind=route_kinds("hunt", prefs),
                             avoid=self._stuck.blocked_keys(self._tick),
                             prey_dir=self._prey_dir(o))

    def _approach_tick(self, o, WL, HL) -> None:
        """去起跳点 → 起跳 → 空中继续修正（旧版缺的就是「去起跳点」这一步）。"""
        if o is None:
            return
        plan = self.plan
        if plan is None or not plan.alive(self._tick) or plan.drifted(o.x, o.y):
            plan = self._plan_for(o, WL, HL)
            self.plan = plan
        if plan is None:
            self._lunge_toward(o, WL, HL)
            return
        self.look_at = (o.x, o.y)
        if plan.mode in ("climb_wall", "climb_pole", "climb_background"):
            # Planner 给的是地形路线：走到上墙点，剩下的交给 _step_wall 的附着物理
            wx = plan.target[0]
            sp = self._state_speed(SNIFF_SPEED)
            want = clampf((wx - self.x) * 0.08, -sp, sp)
            self._drive_vx(want, WALK_TURN)
            return
        lx = plan.launch[0] if plan.launch else self.x
        if abs(self.x - lx) <= 10.0 and self._contact_floor and self.hop_cd <= 0:
            self._leap()
            self.hop_cd = HOP_CD
            sp = self._state_speed(SNIFF_SPEED)
            want = clampf((o.x - self.x) * 0.05, -sp, sp)
            self._drive_vx(want, LUNGE_ACCEL)
            return
        sp = self._state_speed(SNIFF_SPEED)
        want = clampf((lx - self.x) * 0.06, -sp, sp)
        self._drive_vx(want, WALK_TURN)

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
        """伏击待机（原版 LurkTracker）：先挪到伏击点，再压低身体等猎物进圈。

        文档 §15：伏击不能只是「决定不追」—— 白蜥要挑一个猎物看不见、又挡在
        它去路上的位置。伏击点由 plan_approach 用统一地形算好（mode=lurk），
        这里只负责走过去并等。
        """
        self.lurk = True
        plan = self.plan
        if plan is not None and plan.alive(self._tick) and plan.mode == "lurk":
            tx, ty = plan.target
            if math.hypot(tx - self.x, ty - self.y) > 26.0:
                if self._vertical_detour(tx, ty, kind=route_kinds("lurk"),
                                         no_jump=True):
                    if self._route_tick(None, WL, HL):
                        return
                sp = self._state_speed(SNIFF_SPEED)
                want = clampf((tx - self.x) * 0.05, -sp, sp)
                self._drive_vx(want, WALK_TURN)
                return
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
            owner = o.claimed_by
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
        if self.dead or self.prey.carrying:
            return None
        if self.breed.key not in PACK_BREEDS:
            return None
        if not self.mem.hunting or self.mem.last_pos is None:
            return None
        return PackAlert(self.mem.last_pos[0], self.mem.last_pos[1], self.mem.obj,
                         self._tick, self.id, self.mem.confidence)

    def absorb_alert(self, alert) -> None:
        """收到同伴的情报：记下来，包夹位置按自己的序号错开（不要全挤一个点）。"""
        if alert is None or self.dead:
            return
        if self.prey.carrying or alert.obj is None:
            return
        # 「哪条更新」看原始时间戳；同一条被转发到第二次（hops 更大）不该覆盖
        # 更早收到的那份更清晰版本（文档 §16：转发不刷新 TTL）。
        if (self.alert is None or alert.tick > self.alert.tick
                or (alert.tick == self.alert.tick
                    and alert.hops < self.alert.hops)):
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
            if o.claimed_by is not None and o.claimed_by is not self:
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
            # 原版 PreySpotted 也是抬高 bodyWiggleCounter 的事件之一（文档 §10.5）
            self.wiggle = min(1.0, self.wiggle + WIGGLE_BUMP)
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
            sp = self._state_speed(SNIFF_SPEED)
            want = clampf(dx * 0.05, -sp, sp)
            self._drive_vx(want, WALK_TURN)
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
        """可见性：只受视野锥和距离限制，地形不遮挡桌面生态的视线。"""
        d = math.hypot(tx - self.x, ty - self.y)
        if target is not None and target is self.target_obj:
            if d > self.notice_r:
                return False
        else:
            v = self._visual_fac(tx, ty)
            if d > self.notice_r * (VIS_BACK_FAC + (1.0 - VIS_BACK_FAC) * v):
                return False
        return True

    def hear_noise(self, x: float, y: float) -> None:
        """原版 ReactToNoise（LizardAI.cs:1741-1763）：记住最近一次响声的位置。"""
        if self.dead:
            return
        if math.hypot(x - self.x, y - self.y) > NOISE_R:
            return
        self.noise_x, self.noise_y, self.noise_t = float(x), float(y), NOISE_TICKS
        # 原版 HearSound 会抬高 bodyWiggleCounter（文档 §10.5）
        self.wiggle = min(1.0, self.wiggle + WIGGLE_BUMP * 0.6)

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

    # ── 逃 / 猎 的效用（文档 §40：Utility + Hysteresis，不是硬优先级）──
    def _flee_util(self, obs) -> float:
        """Flee 效用：威胁越近越高（原版 ThreatTracker 的 utility 口径）。

        用**当前实际观察到的**威胁算强度，而不是 threat_t —— 后者只是「还在怕」
        的计时器，不是强度。
        """
        notice = self.notice_r * THREAT_NOTICE_FAC
        inner = notice * 0.30                      # 贴到这个距离 = 满效用
        best = 0.0
        for o in self._as_obs(obs.get("threats"), "threat"):
            if o.dead or not o.los or o.dist > notice:
                continue
            u = inv_lerp(notice, inner, o.dist) * FLEE_UTIL
            if u > best:
                best = u
        return best

    def _hunt_util(self, obs) -> float:
        """Hunt 效用：嘴里有肉最高；目标越近越高，出了视野半径就没有。"""
        if self.prey.carrying:
            return HUNT_UTIL
        reach = max(8.0, self._bite_reach() * 1.5)
        best = 0.0
        for key, w in (("cats", 1.0), ("prey", 0.8)):
            for o in self._as_obs(obs.get(key), key):
                if o.dead or (key == "cats" and not o.los):
                    continue
                u = HUNT_UTIL * w * inv_lerp(self.notice_r, reach, o.dist)
                if u > best:
                    best = u
        return best

    def _flee_outweighs_hunt(self, obs) -> bool:
        """逃是不是明显比猎更划算（文档 §40 的迟滞带）。

        还在猎：逃的效用要**超过**猎 + 迟滞带才切过去；
        已经在逃：反过来，猎要超过逃 + 迟滞带才回头。
        两边都要求「明显」，于是不会在边界上每帧横跳。
        """
        flee = self._flee_util(obs)
        hunt = self._hunt_util(obs)
        if self.stage == "Flee":
            return flee + FLEE_HUNT_HYSTERESIS >= hunt
        return flee > hunt + FLEE_HUNT_HYSTERESIS

    def _threat_tick(self, HL) -> bool:
        """原版 Behavior.Flee（LizardAI.cs:797-822）：背对威胁全速逃、闭颌、不咬任何人。"""
        if self.threat_t <= 0:
            return False
        self.threat_t -= 1
        tx, ty = self.threat if self.threat is not None else (self.x, self.y)
        # 威胁在**别的层**（爬到我站着的平台上方 / 掉在下面）：背对它直线跑
        # 一点用都没有 —— 这时才动用统一导航，挑一块离它最远、且 SAFE 路线
        # 过得去的地面当逃跑目标（文档 §5/§16）。
        if abs(ty - self.y) > CLIMB_MIN_DY and self._flee_seat(tx, ty, HL):
            return True
        dx, dy = self.x - tx, self.y - ty
        d = math.hypot(dx, dy) or 1.0
        sp = self._state_speed(FLEE_SPEED)
        self._drive_vx(dx / d * sp, FLEE_ACCEL)
        self.target = self.target_obj = None
        self.look_at = (tx, ty)
        if self._contact_floor and self.rng.random() < FLEE_HOP:
            self._leap(0.7)
        return True

    def _flee_seat(self, tx, ty, HL) -> bool:
        """Flee 的路线层：候选落点里挑「离威胁最远 + 路线最省」的那一块地面。"""
        if self.terrain is None or self.caps is None:
            return False
        plan = self.plan
        if (plan is not None and plan.alive(self._tick) and plan.legs
                and plan.mode != "lurk"):
            return True                        # 还活着就照它跑，TTL 到了再重挑
        seats = []
        for s in self.terrain.geom.floors(self.caps):
            if abs(s.y - self.y) > FLEE_SEAT_DY:
                continue
            for x in (s.lo + 16.0, 0.5 * (s.lo + s.hi), s.hi - 16.0):
                if math.hypot(x - self.x, s.y - self.y) <= 40.0:
                    continue
                seats.append((x, s.y))
        if not seats:
            return False
        seats.sort(key=lambda p: -math.hypot(p[0] - tx, p[1] - ty))
        ban = self._stuck.blocked_keys(self._tick)
        kinds = route_kinds("flee")
        for (x, y) in seats[:FLEE_SEAT_TRIES]:
            route = _terrain_route(self.terrain, self.caps, self.x, self.y, x, y,
                                   self._tick, ROUTE_TTL, kind=kinds, avoid=ban,
                                   force=True)
            if route is None or not route.legs:
                continue
            if all(lg.mode == "jump" for lg in route.legs):
                continue                       # 逃跑不靠跳（Flee 没有跳跃执行器）
            self.plan = route
            self.target, self.target_obj = (x, y), None
            self.look_at = (tx, ty)
            return True
        return False

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
        sp = self._state_speed(INJURY_SPEED)
        want = clampf((best[0] - self.x) * 0.05, -sp, sp)
        self._drive_vx(want, WALK_TURN)
        return True

    def _noise_tick(self, WL, HL) -> bool:
        """原版 Behavior.InvestigateSound（LizardAI.cs:1038-1042）：朝最后听到的响声走。

        响声在上面 / 下面时走正式地形路线（文档 §30），而不是对着 x 一直撞。
        """
        if self.noise_t <= 0:
            return False
        self.noise_t -= 1
        dx, dy = self.noise_x - self.x, self.noise_y - self.y
        if math.hypot(dx, dy) < 24.0:
            self.noise_t = 0
            return False
        self.look_at = (self.noise_x, self.noise_y)
        if self._vertical_detour(self.noise_x, self.noise_y):
            return True
        sp = self._state_speed(SNIFF_SPEED)
        want = clampf(dx * 0.06, -sp, sp)
        self._drive_vx(want, WALK_TURN)
        return True

    def _pack_tick(self, WL, HL) -> bool:
        """原版 Pack（黄蜥）：优先按**同伴广播的猎物情报**去各自的分工位置，
        其次才是跟住最近的同伴（旧版只有后者，所以看起来像「黄蜥喜欢扎堆」）。
        """
        obs = self.obs
        if self.alert is not None and self.alert.fresh(self._tick):
            seat = self._pack_seat(WL, HL)
            if seat is None:
                return False
            gx, gy = seat
            self.look_at = (self.alert.x, self.alert.y)
            if abs(gx - self.x) <= 10.0 and abs(gy - self.y) <= CLIMB_MIN_DY:
                return False                       # 已经站到自己的位置了
            # 包夹位不和我同层时（猎物在窗口顶 / 杆上）：走路线过去，
            # 而不是对着它的 x 一路撞。
            if self._vertical_detour(gx, gy, kind=route_kinds("pack"), no_jump=True):
                return self._route_tick(None, WL, HL)
            sp = self._state_speed(SNIFF_SPEED)
            want = clampf((gx - self.x) * 0.05, -sp, sp)
            self._drive_vx(want, WALK_TURN)
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
        sp = self._state_speed(SNIFF_SPEED)
        want = clampf((best.x - self.x) * 0.05, -sp, sp)
        self._drive_vx(want, WALK_TURN)
        return True

    def _pack_seat(self, WL, HL):
        """这一轮我该站的包夹点（文档 §14）。

        先算猎物所在的**面**，再在它周围挑前 / 后 / 左右四个落点，最后按路线
        代价决定我去哪个 —— 每只黄蜥各自挑最划算的那个，于是自然围上去，
        而不是同一个点 + X 偏移（旧 flank_offset 做的事）。
        """
        a = self.alert
        if a is None:
            return None
        if (self._pack_point is not None
                and self._tick - self._pack_point_tick < PACK_SEAT_TICKS):
            return self._pack_point
        self._pack_point_tick = self._tick
        slots = pack_slots(self.terrain, self.caps, a.x, a.y, a.x - self.x,
                           a.y - self.y)
        if not slots:
            self._pack_point = None
            return None
        if self.terrain is None or self.caps is None:
            self._pack_point = pack_slot_for(slots, self.id)
            return self._pack_point
        ban = self._stuck.blocked_keys(self._tick)
        kinds = route_kinds("pack")
        best, bs = None, None
        for (sx, sy) in slots:
            r = _terrain_route(self.terrain, self.caps, self.x, self.y, sx, sy,
                               self._tick, ROUTE_TTL, kind=kinds, avoid=ban,
                               force=True)
            if r is None or not r.legs:
                continue
            if all(lg.mode == "jump" for lg in r.legs):
                continue
            if bs is None or r.score < bs:
                best, bs = (sx, sy), r.score
        if best is None:
            best = pack_slot_for(slots, self.id)
        self._pack_point = best
        return best

    def intent(self):
        """这只蜥蜴此刻盯上的东西 → (对象, 类型)；没有则 (None, "")。

        优先级：嘴里叼着的 → 我咬倒的猎物 → 同伴广播的猎物情报 → 当前目标。
        原版每只蜥蜴有自己的 PreyTracker，桌宠的猫得让开它盯上的猎物 —— 所以
        把它挂到和猫同一张认领板上（behavior/board.py 的 register_actor），
        「谁在追什么」全场只有一个说法。
        """
        if self.dead or self.state != ItemState.FREE:
            return (None, "")
        if self.prey.carrying:
            return (self.prey.carry_obj, "hunt")
        if self.prey.owns(self.prey.obj, self._tick):
            return (self.prey.obj, "hunt")
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
        sp = self._state_speed(HUNT_SPEED) * self.sprint
        acc = LUNGE_ACCEL
        if self.breed.charge_leap:
            # 青蜥蓄力弹射：扑击整段更快更猛（wiki：爬墙 + 蓄力弹射跳跃）
            sp *= CHARGE_LEAP_SPD
            acc = min(1.0, LUNGE_ACCEL * CHARGE_LEAP_ACC)
        # 原版 loungeDistance → Lounge：进了这个距离就是一次全力冲刺（品种顶速 =
        # loungeSpeed），而不是继续慢悠悠地「走过去」。
        if d <= self.breed.lounge_distance * self.breed.body_size_fac:
            sp *= self.breed.lounge_speed
            acc = min(1.0, acc * LOUNGE_ACCEL_FAC)
        self._drive_vx(kx * sp, acc)
        reach = self._bite_reach()
        if d <= reach and self.bite_cd <= 0 and self.target_obj is not None:
            # 猫端着驯服食物送到嘴边（原版送礼）→ 先吃食不咬它
            if not _cat_offering_food(self.target_obj):
                self._start_bite()
        elif (self.target_obj is not None and self._tongue_ready()
                and d <= self.breed.tongue_range
                and not _cat_offering_food(self.target_obj)
                # LizardAI.cs:1242-1244: tongueChance is rolled for each
                # aggressive opportunity; without this gate every eligible
                # lizard lashes on the first frame and never resembles the
                # species-specific ambush behavior.
                and self.rng.random() < self.breed.tongue_chance):
            # 咬不着、但舌头够得到：原版 ShootTongue（白蜥那根 440px 的长舌）
            self._shoot_tongue(self.target_obj)
        elif self._contact_floor and self.hop_cd <= 0 and (self.y - self.target[1]) > 34.0:
            self._leap()
            self.hop_cd = HOP_CD

    # ── 叼走死猫 / 昏迷猫到屏幕角落 ──
    def _bite_reach(self) -> float:
        """咬得着的距离 = 头半径 + 原版 biteInFront（嘴在头前多远）× 体型。

        attemptBiteRadius 是「离多远就开始尝试咬」（AI 判据），biteInFront 是「嘴
        到底在头前多远」（几何）。旧实现把两者搅成一个式子，这里是拆开后的口径。
        """
        b = self.breed
        return self.head_rad + BITE_IN_FRONT_K * b.bite_in_front * b.body_size_fac

    def _mouth_point(self):
        """嘴前叼点：头轴正前方一个头半径。"""
        a = math.radians(self.head_angle)
        d = self.head_rad * CARRY_MOUTH_FAC
        return self.head_x + math.sin(a) * d, self.head_y - math.cos(a) * d

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
            if o.claimed_by is not None and o.claimed_by is not self:
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
        if self.prey.carrying:
            o = next((c for c in obs["cats"] if c.obj is self.prey.carry_obj), None)
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
                                    HL if HL is not None else self.y, stand, ox,
                                    self.shelter_x)
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
        if self.prey.carrying:
            o = next((c for c in obs["cats"] if c.obj is self.prey.carry_obj), None)
            if o is None:
                self._release_carry()             # 目标没了（被清场 / 转世）
                return False
            if not self._carry_keep(o):
                # 被玩家拽脱手（Lizard.cs:1386）或醒了：松口，回去当普通猎物
                self._release_carry(yanked=self._carry_lost(o))
                return False
            self.prey.refresh(self._tick)
            if self.carry_den is None:
                self.carry_den = choose_den(WL, HL, stand, o.x,
                                            self.shelter_x)
                self.carry_corner = self.carry_den.side
            den = self.carry_den
            if abs(den.x - self.x) <= CARRY_DEN_ARRIVE_R:
                was_dead = bool(o.dead)
                self._release_carry()
                self.prey.delivered(self._tick)
                if was_dead:                       # 尸体：在巢穴边守一会儿
                    self.guard_obj, self.guard_t = o.obj, GUARD_PREY_TICKS
                return True                        # 这一 tick 用来放下
            # 巢穴不在我这一层（我站在窗口顶 / 杆上）：叼着猎物走 SAFE 路线，
            # 而不是对着 den.x 一路撞（文档 §5：Carry 要留退路、不冒险跳）。
            if self._vertical_detour(den.x, den.y, kind=route_kinds("carry"),
                                     no_jump=True):
                self._route_tick(o, WL, HL)
                self._hold_cat()
                self.look_at = (den.x, HL - 12.0)
                return True
            hurry = self._carry_hurry(obs["rivals"])
            sp = self._state_speed(CARRY_SPEED_FAC)
            want = clampf((den.x - self.x) * 0.05, -sp, sp) * hurry
            self._drive_vx(want, WALK_TURN)
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
        """兼容旧存档和猫侧调用；本项目不启用蜥蜴驯服。"""
        self.like = 0.0
        self.tamed = False
        self.friend_id = None

    def _start_bite(self, obj=None) -> None:
        """原版 Lizard.cs:1238 AttemptBite：先张嘴压上去，`biteDelay` 帧后 JawsSnapShut。

        伤害**不再在这一帧结算**：前摇里目标跑出咬距就是原版那样的「落空」，只有
        `biteDelay` 结束的那一刻还在嘴边的才吃这一口（见 _snap_jaws）。
        obj 给 casual 撕咬用（原版 casualAggressionTarget 不是当前猎物目标）。
        """
        if obj is None:
            obj = self.target_obj
        wind = max(0, int(self.breed.bite_delay))
        # bite_hold 盖住「前摇 + 咬合保持」整段：下巴全程张着、头部按扑咬速率跟随。
        self.bite_hold = BITE_HOLD + wind
        self.bite_cd = COOLDOWN_TICKS + wind
        self.bite_wind = wind
        self._bite_wind_obj = obj
        b = self.breed
        dmg = 0.0
        if b.bite_damage_chance >= 1.0 or self.rng.random() < b.bite_damage_chance:
            dmg = b.bite_damage * lerp(0.8, 1.2, self.rng.random())
        self._bite_wind_dmg = dmg
        self.bite_event = None
        self.jaw = 1.0
        self.vx *= 0.2
        # 这一口的出手方向（loungeDir）在动作开始时就定下来，之后整段序列都用它
        px, py = _obj_pos(obj)
        if px is None:
            px, py = _obj_pos(self.target_obj)
        if px is None and self.target is not None:
            px, py = self.target
        if isinstance(px, (int, float)) and not isinstance(px, bool) and \
                isinstance(py, (int, float)) and not isinstance(py, bool):
            fx, fy = float(px) - self.x, float(py) - self.y
            fd = math.hypot(fx, fy)
            self._atk_dir = ((fx / fd, fy / fd) if fd > 1e-6
                             else (float(self.facing), 0.0))
        else:
            self._atk_dir = (float(self.facing), 0.0)
        self._set_attack_phase("prepare", ATK_PREPARE_T)
        self.wiggle = min(1.0, self.wiggle + WIGGLE_BUMP)
        if wind == 0:
            self._snap_jaws()
        # 咬合的一瞬：前半身朝猎物「压」出去（原版 jaw 一夹，前 chunk 被反作用
        # 顶出去，后半身靠惯性拖在后面）。只推前 BODY_IMP_SEGS 节。
        px, py = _obj_pos(obj)
        if px is None:
            px, py = _obj_pos(self.target_obj)
        if px is None and self.target is not None:
            px, py = self.target
        if isinstance(px, (int, float)) and isinstance(py, (int, float)):
            fx, fy = px - self.x, py - self.y
            fd = math.hypot(fx, fy)
            if fd > 1e-6:
                nx, ny = fx / fd, fy / fd
                # 头点（= 原版 head.ConnectToPoint 的目标点）先递出去一点：链子的
                # 杆长约束只消径向误差，光给躯干灌水平冲量会被它原样吃掉（冲量
                # 方向和杆轴共线 = 刚性方向）—— 只有头真的往前一步，前半身才有
                # 「伸出去」的位移；躯干冲量负责让前节跟上、尾节滞后。
                self.x += nx * BODY_BITE_LUNGE
                self.y += ny * BODY_BITE_LUNGE
                self._body_impulse(nx * BODY_BITE_PUSH, ny * BODY_BITE_PUSH)

    def _bite_homing(self) -> None:
        """咬合前摇：照原版 biteHomingSpeed 一边瞄一边压上去。

        前摇不是「站着发呆等 12 帧」——原版这段时间下颚张着、头（和整个前身）朝
        猎物贴过去，所以猎物「能不能在被咬到之前逃开」才变成一个真实的窗口。
        """
        obj = self._bite_wind_obj
        px, py = _obj_pos(obj)
        if px is None:
            px, py = _obj_pos(self.target_obj)
        if px is None and self.target is not None:
            px, py = self.target
        if not isinstance(px, (int, float)) or isinstance(px, bool):
            return
        if not isinstance(py, (int, float)) or isinstance(py, bool):
            return
        px, py = float(px), float(py)
        self.look_at = (px, py)
        fx, fy = px - self.x, py - self.y
        fd = math.hypot(fx, fy)
        if fd <= 1e-6:
            return
        reach = self._bite_reach()
        if fd <= reach * 0.5:
            return                       # 已经贴到嘴边了：别把身体顶进猎物里
        step = self.breed.bite_homing_speed * BITE_HOMING_STEP * self.breed.body_size_fac
        self.x += fx / fd * step
        self.y += fy / fd * step
        imp = step * BODY_BITE_PUSH * 0.4
        self._body_impulse(fx / fd * imp, fy / fd * imp)

    def _snap_jaws(self) -> None:
        """原版 Lizard.cs JawsSnapShut：前摇结束才真正咬下去。

        前摇里目标跑出咬距（BITE_SNAP_SLACK 倍）→ 这一口落空，不写 bite_event；
        还咬得着才交给 items.py 结算伤害。

        不管中没中，下颚夹上这一瞬原版都会给一次反作用（JawsSnapShut 逐行：
        ``mainBodyChunk.vel += DirVec(main, pos) * 8``、``bodyChunks[1]/[2].vel
        -= DirVec(main, pos) * 6``）—— 咬合是「头一口咬出去、身体被反推着坐
        一下」。旧实现只有咬中才写 bite_event，夹合本身没有任何身体反作用，
        所以扑咬看起来「头在动、身体没使劲」。
        """
        obj, dmg = self._bite_wind_obj, self._bite_wind_dmg
        self._bite_wind_obj = None
        self._bite_wind_dmg = 0.0
        self.bite_wind = 0
        self.jaw = 1.0
        self.bite_event = None      # 夹合这一瞬先清：落空就是落空，不留上一口的残留
        hit = False
        if obj is not None:
            px, py = _obj_pos(obj)
            if px is None:
                hit = True                      # 纯坐标目标：够不着这一层，算咬中
            else:
                hit = (math.hypot(px - self.x, py - self.y)
                       <= self._bite_reach() * BITE_SNAP_SLACK)
        # 夹合方向：优先朝真正的猎物，没有目标就用作势时锁定的 _atk_dir
        nx, ny = self._atk_dir
        if obj is not None:
            px, py = _obj_pos(obj)
            if px is not None:
                fd = math.hypot(px - self.x, py - self.y)
                if fd > 1e-6:
                    nx, ny = (px - self.x) / fd, (py - self.y) / fd
        self.x += nx * JAW_SNAP_HEAD
        self.y += ny * JAW_SNAP_HEAD
        self._jaw_rec_x = nx * JAW_SNAP_MAIN
        self._jaw_rec_y = ny * JAW_SNAP_MAIN
        if hit:
            self.bite_event = (obj, dmg)

    def _wander(self, WL, HL) -> None:
        """游走：定一个近处落点，走到／超时就换，再歇一会儿。

        白蜥/蝾螈走原版 LurkTracker（LizardAI.cs:85-216，utility 权重 0.3-0.4）：
        伏击型，原地待机时间是别人的 LURK_IDLE_MULT 倍。
        """
        self.lurk = self.breed.key in ("white", "salamander")
        # 原版 bodyWiggleCounter 除了事件抬高，其余时间是随机抬高的 ——
        # 这是「停着也不像一块死物」的来源（文档 §10.5）。
        if (not self.dead and self.wiggle < 0.25
                and self.rng.random() < WIGGLE_IDLE_P):
            self.wiggle = min(1.0, self.wiggle + WIGGLE_BUMP * 0.5)
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
        sp = self._state_speed(PATROL_SPEED)
        want = clampf(dx * 0.06, -sp, sp)
        self._drive_vx(want, WALK_TURN)

    def chunks(self):
        """可命中点＝头 + 每节（文档 §7 CombatTarget）。

        头的 owner 是蜥蜴自己（``hit_chunk is lz`` 用来判头甲），躯干 / 尾巴给各自链节。
        """
        out = [(None, self.x, self.y, self.head_rad)]
        for sg in self.seg:
            out.append((sg, sg.x, sg.y, sg.rad))
        return out

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
        if self.bite_wind > 0:
            # 咬合前摇：原版 biteHomingSpeed 决定头多快锁住目标（粉蜥 1.7 = 基准）。
            return clampf(HEAD_LOOK_FAST * (self.breed.bite_homing_speed / BITE_HOMING_REF),
                          0.06, 0.60)
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

    # ── 身体朝向 / 转身 ──
    def _move_base(self) -> float:
        """走路 / 追猎用的基准速度：品种 base_speed，带一个下限。

        焦糖蜥 base_speed 只有 0.65，纯相对量会让它巡逻 / 叼东西几乎贴地不动
        （腿都不摆）。下限只保证「走得动」，不改状态之间的先后次序。
        """
        return max(self.breed.base_speed, MOVE_SPEED_FLOOR)

    def _state_speed(self, mult: float) -> float:
        """某个移动状态的速度上限 = 基准速度 × 状态系数（发呆类不走这里）。"""
        return self._move_base() * mult

    def _drive_vx(self, want: float, k: float) -> None:
        """AI 想要的横向速度：既按老口径推 vx，也把「意图」单独记一份。

        脚支撑相里踩住的脚是支点，身体不许把它拖走 —— 支撑逻辑会把 vx 压到
        TURN_VX 以下。只看积分后的 vx，转身状态机就永远不转向（身体朝反方向
        走、链体反向、四条腿全部够不到髋），支撑脚再反过来把身体刹住，成了
        死循环。该往哪边转看 want（意图），不看被脚压过的结果。
        """
        self._want_vx = float(want)
        self.vx += (want - self.vx) * k

    def _step_turn(self) -> None:
        """朝向状态机：Idle/Walk → DirectionChange → Turn → Reoriented → Walk。

        原版扭头不是「头贴图转了个角度」：AI 想看左边 → 前端 bodyChunk 改变运动
        方向 → 连接约束重新收敛 → 第 1 节先动、第 2 节稍晚、尾巴更晚。这里把
        「身体转到哪一侧」做成有限速率的连续量 body_dir，掉头时它从 +1 平滑扫过
        0（= 身体横对镜头）到 -1，锚点随之外移到头顶两侧 —— 于是头先转、前身跟上、
        中段滞后、尾巴最后甩过来，而不是整条身体瞬间镜像。
        """
        prev = self.body_dir
        held_turn = self.state == ItemState.MOUSE or self.hauled
        # ① move_dir：这一 tick 想往哪一侧走。站定 / 被拎 / 眩晕时不给方向
        #    （朝向保持原样，不会因为停下时的 ±0.0x 抖动翻面）。
        if self.dead or self.stun > 0 or self.state == ItemState.MOUSE:
            self.move_dir = 0.0
        elif self.climb_x is not None:
            # 贴在竖杆 / 背景墙上：横轴由表面切线接管（见 _step_head），
            # 身体轴保持进墙前的方向，不被左右速度乱翻。
            self.move_dir = 0.0
        elif abs(self._want_vx) > TURN_VX:
            # 用 AI 的意图速度（不是积分后的 vx：脚支撑会把 vx 压下去，方向会被
            # 抖没 —— 压到 TURN_VX 以下时看起来就像「AI 不打算走了」）。
            self.move_dir = 1.0 if self._want_vx > 0.0 else -1.0
            # 例外：身体**实际**正朝反方向走，而且不是被压慢、是真有速度的
            # （被外力推 / 被脚支撑顶回来 / 被猫拽着走）。这时以真实运动为准 ——
            # 否则腿朝「想去的方向」迈步、身体却滑向另一边，没有一只脚踩得住，
            # 唯一的支撑脚被一路拖到腿长之外（用户报的「脚黏在平面上 / 被拽走后
            # 脚把蜥蜴拉回去」）。脚支撑把 vx 压到门槛以下时不会走到这里，
            # 那种「AI 想走但被脚刹住」的死锁仍然按意图判。
            if (abs(self._vx_intent) > TURN_VX
                    and self._vx_intent * self._want_vx < 0.0):
                self.move_dir = 1.0 if self._vx_intent > 0.0 else -1.0
        elif abs(self._vx_intent) > TURN_VX:
            # 兜底：没走 _drive_vx 的路径（直接改 vx 的那些）照旧按实际意图速度判
            self.move_dir = 1.0 if self._vx_intent > 0.0 else -1.0
        else:
            self.move_dir = 0.0
        # ② body_dir：朝 move_dir 转，但每 tick 只转这么多（原版靠 chunk 惯性跟上）。
        if self.move_dir != 0.0:
            rate = TURN_RATE if self._contact_floor else TURN_RATE_AIR
            if self.move_dir > self.body_dir:
                self.body_dir = min(self.move_dir, self.body_dir + rate)
            elif self.move_dir < self.body_dir:
                self.body_dir = max(self.move_dir, self.body_dir - rate)
        self.turn_progress = clampf(1.0 - abs(self.body_dir), 0.0, 1.0)
        # ③ 状态：站定 / 已对齐（行走）/ 还在转
        if self.move_dir == 0.0:
            self.turn_mode = "idle"
        elif abs(self.body_dir - self.move_dir) > TURN_DIR_EPS:
            self.turn_mode = "turn"
        else:
            self.turn_mode = "walk"
        # ④ 掉头小跳（原版 LizardTurn 的实体动作）：身体正好扫过中线的那一下，
        #    有力气的品种蹬一下地，把上半身甩过顶 —— 顺带让腿重新排步。
        #    turn_hop 是独立能力（绿蜥 0 → 掉头就是慢慢拧过去）。
        if (self.breed.turn_hop and self._contact_floor and self.stun <= 0
                and not self.dead and self.vy >= 0.0
                and ((prev > 0.0 >= self.body_dir) or (prev < 0.0 <= self.body_dir))
                and abs(prev) > 1e-9):
            self.vy = -TURN_HOP_VY * math.sqrt(max(0.4, self.breed.body_size_fac))
            self._body_impulse(0.0, self.vy * BODY_JUMP_SHARE)
        # ⑤ 身体轴：符号跟 body_dir（滞后），腿的前方目标跟 move_dir（意图）——
        #    两件事分开，腿才不会在身体还没转过来时朝旧方向迈步。
        self.chain_dir = 1.0 if self.body_dir >= 0.0 else -1.0
        # ⑥ 转身冲量（原版 chunk 惯性）：身体轴这一 tick 摆过 swing，前 1~2 节先被
        #    带过去，尾巴最后才跟上。主项用 swing（干净、就是「身体在转」这件事
        #    本身），再叠一点速度突变（vx - _last_vx，原版 chunk 拿到的是这个）——
        #    单独用 dv 不行：摩擦 + 脚支撑每 tick 都在改 vx，dv 又小又毛，转身时
        #    常常够不到门槛。
        swing = self.body_dir - prev
        imp = swing * TURN_IMP_K
        if not held_turn and abs(self.vx - self._last_vx) > SEG_BEND_MIN_VX:
            imp += (self.vx - self._last_vx) * TURN_IMP_DV_K
        self._turn_imp = (clampf(imp, -TURN_IMP_MAX, TURN_IMP_MAX)
                          if (self.turn_mode == "turn" or abs(swing) > 1e-9) else 0.0)
        self._last_body_dir = self.body_dir

    # ── 身体冲量：让躯干真的被动作驱动 ──
    def _body_impulse(self, dvx: float, dvy: float) -> None:
        """给躯干 chunk 一次冲量（同 tick 累积，_step_chain 统一施加）。

        原版蜥蜴是「bodyChunks 拿到 impulse → BodyChunkConnection 被拉伸 →
        后节因惯性滞后」；头只是挂在 chunk0 前方的一个点。宠物里头的驱动点仍
        由 AI 直接写（_integrate），但动作的冲量必须同时落到躯干上，否则躯干
        永远只是被锚点拖着的绳子 —— 起跳、扑击、咬合看起来都「没使劲」。
        """
        self._body_imp_x += float(dvx)
        self._body_imp_y += float(dvy)

    # ── 动作序列：Attack_Prepare / Lunge / Bite / Recover（文档 §9.3 / §10.3）──
    def _set_attack_phase(self, phase: str, ticks: int) -> None:
        self._atk_phase = phase
        self._atk_t = max(0, int(ticks))

    def _step_attack_pose(self) -> None:
        """把 Attack 的四个姿态阶段**逐 chunk** 作用上去（原版 Lizard.ActAnimation）。

        原版「扑咬」不是一个 AI 状态，而是一串极短的姿态动作：

            PrepareToLounge  所有 chunk 朝猎物做预备移动（前半身压、后半身反推）
            Lounge           三个 chunk 吃 loungeDir * loungeSpeed / (k + 1)
                             （[0] 最大、[1] 次之、[2] 最弱）
            JawsSnapShut     下颚夹合，前半身再顶一下
            postLoungeStun   身体回收，尾巴最后追上

        这里照同一顺序给每个 chunk 单独写速度 —— 于是「蓄力 → 爆发 → 咬合 → 恢复」
        在身体上真的看得见，而不是只把整体 vx 调大。
        """
        ph = self._atk_phase
        if ph is None:
            return
        if self.dead or self.stun > 0:
            self._atk_phase = None
            return
        self._atk_t -= 1
        if self._atk_t < 0:
            nxt = {"prepare": ("lunge", ATK_LUNGE_T),
                   "lunge": ("bite", ATK_BITE_T),
                   "bite": ("recover", ATK_RECOVER_T)}.get(ph)
            if nxt is None:
                self._atk_phase = None
                return
            self._set_attack_phase(*nxt)
            return
        n = len(self.seg)
        px, py = self._atk_dir
        if ph == "prepare":
            # PrepareToLounge：所有 chunk 先朝猎物做预备移动（前节多、后节少）
            self._body_impulse(px * ATK_PUSH_PREP, py * ATK_PUSH_PREP)
            for k in range(min(3, n)):
                sh = ATK_PUSH_PREP * 0.5 / (k + 1.0)
                self.seg[k].vx += px * sh
                self.seg[k].vy += py * sh
        elif ph == "lunge":
            sp = self.breed.lounge_speed * ATK_LUNGE_K * self.breed.body_size_fac
            for k in range(min(3, n)):
                sh = 1.0 / (k + 1.0)
                self.seg[k].vx += px * sp * sh
                self.seg[k].vy += py * sp * sh
        elif ph == "bite":
            # FightingStance：前半身朝猎物顶出去、后半身反向（身体被拉长）
            self._body_impulse(px * ATK_PUSH_PREP * 0.6, py * ATK_PUSH_PREP * 0.6)
            if n >= 3:
                self.seg[2].vx -= px * ATK_PUSH_PREP * 0.4
                self.seg[2].vy -= py * ATK_PUSH_PREP * 0.4
        else:                                   # recover
            for k in range(min(3, n)):
                sh = ATK_RECOVER_BACK / (k + 1.0)
                self.seg[k].vx -= px * ATK_PUSH_PREP * sh
                self.seg[k].vy -= py * ATK_PUSH_PREP * sh

    # ── 后空翻（文档 §9.4）：身体姿态序列的角动量，不是「跳高一点」──
    def _start_flip(self, direction: int = None) -> bool:
        """起跳时把整段翻滚排上（只有 flip_hop 品种会翻）。

        原版翻身的角动量来自 PrepareToJump 给各 chunk 的反向冲量；这里补上真正
        的「整条身体绕质心转过去」：之后 FLIP_TICKS 帧里匀速转过 FLIP_ARC。
        """
        if not self.breed.flip_hop or self.dead:
            return False
        if self.flip_left > 0:
            return False
        if abs(self.vx) < FLIP_SPEED_MIN:
            return False                    # 原地垂直跳不翻（原版冲量不够）
        self.flip_left = FLIP_TICKS
        self.flip_dir = 1 if (direction or (1 if self.vx >= 0.0 else -1)) >= 0 else -1
        self.flip_ang = 0.0
        self.flip_wait = FLIP_GRACE
        return True

    def _step_flip(self) -> None:
        """翻滚推进：整条身体（含驱动点）绕**质心**匀速转，头部同步旋转。

        绕质心而不是绕前节：绕前节会变成「尾巴甩过头顶」，绕质心才是原版那种
        「整只翻过去」。旋转是刚体变换，节间距离不变，所以后面的杆长约束不会被
        打乱 —— 只有质心位置随之更新（驱动点跟着走）。
        """
        if self.flip_left <= 0 or self.dead:
            self.flip_left = 0
            self.flip_wait = 0
            return
        if self._contact_floor:
            # 还没离地：给 FLIP_GRACE 帧宽限（起跳那一两帧还贴着地）。
            # 宽限用完还没离地（比如跳被卡住了）就彻底作废 —— 不能把
            # 一次没飞起来的起跳挂在这里，否则下次真正离地会突然翻起来。
            if self.flip_wait <= 0:
                self.flip_left = 0
                self.flip_ang = 0.0
            else:
                self.flip_wait -= 1
            return
        self.flip_wait = 0
        self.flip_left -= 1
        n = len(self.seg)
        if n < 2:
            self.flip_left = 0
            return
        cx = sum(s.x for s in self.seg) / n
        cy = sum(s.y for s in self.seg) / n
        d = math.radians(FLIP_ARC / float(FLIP_TICKS)) * self.flip_dir
        ca, sa = math.cos(d), math.sin(d)
        for s in self.seg:
            rx, ry = s.x - cx, s.y - cy
            s.x = cx + rx * ca - ry * sa
            s.y = cy + rx * sa + ry * ca
            s.vx, s.vy = s.vx * ca - s.vy * sa, s.vx * sa + s.vy * ca
        # 驱动点 = 第 0 节（AI 推的就是它），一起转过去，下一帧的积分从这里接着走
        self.x, self.y = self.seg[0].x, self.seg[0].y
        self.flip_ang += math.degrees(d)
        if self.flip_left <= 0:
            self.flip_ang = 0.0      # 360 与 0 等价：收尾直接归零，不跳变

    def _leap(self, scale: float = 1.0) -> float:
        """蹬地起跳：头点拿初速，同一份冲量灌给躯干前几节（原版 Creature.Jump）。"""
        vy = self._hop_vy() * scale
        if vy == 0.0:
            return 0.0
        self.vy = vy
        self._body_impulse(0.0, vy * BODY_JUMP_SHARE)
        # 原版 PrepareToJump（文档 §10.2）：chunk0 沿起跳方向加速、chunk2 反向、
        # chunk1 速度减半 —— 三节拿不同方向的冲量，身体才会被「蹬」长，而不是整条
        # 一起平移。chunk0 的位置由驱动点钉住（速度每 tick 会被重算），所以这里只补
        # 中节和后节。
        if len(self.seg) >= 3:
            self.seg[1].vx *= 0.5                    # 原版：中节速度减半
            self.seg[1].vy += vy * BODY_JUMP_MID
            self.seg[2].vy -= vy * BODY_JUMP_REAR
        # 尾节逐节冲量（原版 PrepareToJump：tail[i].vel -= initVel.normalized * i
        #   + 垂直方向 ±5 每 3 帧交替）—— 尾巴是「甩出去」的，不是跟着平移。
        if len(self.seg) > 3:
            wob = BODY_JUMP_WOBBLE * (1.0 if int(self.walk_phase) % 2 == 0 else -1.0)
            for k in range(3, len(self.seg)):
                self.seg[k].vy -= vy * float(k - 2) * BODY_JUMP_TAIL
                self.seg[k].vy += wob
        self.wiggle = min(1.0, self.wiggle + WIGGLE_BUMP)
        # 跳得猛的品种：这一跳带着身体翻过去（文档 §9.4）
        self._start_flip(1 if self.facing >= 0 else -1)
        return vy

    # ── 原版 LizardTongue（文档 §六）：射出 → 抓住 → 拽回嘴边 → AttemptBite ──
    def _tongue_ready(self) -> bool:
        b = self.breed
        return (b.tongue and b.tongue_range > 0.0 and self.tongue_state is None
                and self.tongue_cd <= 0 and self.bite_cd <= 0 and self.bite_hold <= 0
                and self.bite_wind <= 0 and not self.dead and self.stun <= 0
                and self.hauled is False and self.climb_x is None
                and self.state != ItemState.MOUSE
                and self.carry_body is None)

    def _shoot_tongue(self, o) -> bool:
        """原版 LizardTongue.LashOut：舌尖朝目标射出去（不是「咬」，是「舔」）。

        白蜥那根 440px 的长舌就是靠这个抓猫的；同时按 §10.5 抬高
        bodyWiggleCounter（原版 ShootTongue 是抬高事件之一）。
        """
        px, py = _obj_pos(o)
        if px is None:
            return False
        mx, my = self._mouth_point()
        # 原版 LizardTongue.LashOut 会把目标抬高 5% 的射程，避免舌头
        # 总是打到目标脚下（LizardTongue.cs:519）。
        raw_dx, raw_dy = px - mx, py - my
        raw_d = math.hypot(raw_dx, raw_dy)
        py += raw_d * 0.05
        dx, dy = px - mx, py - my
        d = math.hypot(dx, dy)
        if d <= 1e-6:
            return False
        # 原版 LizardTongue.LashOut（LizardTongue.cs:519）第一件事就是方向闸：
        # 体前轴（chunks[1]→chunks[0]）与「头→目标」的点积 ≤ 0.3 直接 return，
        # 舌头根本不出来。旧实现没这道闸，背后的目标也照射（「背后长舌头」）。
        # LizardTongue.cs:519 uses bodyChunks[1]→bodyChunks[0].  In this
        # port seg[0] is the driven chunk at (self.x, self.y), so using it
        # produces a zero vector and silently disables the forward-angle
        # check.  seg[1] is the actual rear chunk.
        ax, ay = self.seg[0].x - self.seg[1].x, self.seg[0].y - self.seg[1].y
        ad = math.hypot(ax, ay)
        if ad > 1e-6 and (ax * dx + ay * dy) / (ad * d) <= TONGUE_DOT_MIN:
            return False
        # 出手速度按距离插值（原版 num = Lerp(InverseLerp(elRange*0.5, totR, dist), 1, 0.75)）
        rng = float(self.breed.tongue_range)
        self.tongue_speed = TONGUE_SPEED * (
            TONGUE_LASH_MIN
            + TONGUE_LASH_K * clampf((d - rng * 0.5) / max(1.0, rng * 0.5), 0.0, 1.0))
        self.tongue_dir = (dx / d, dy / d)
        self.tongue_len = 0.0
        self.tongue_tip = (mx, my)
        self.tongue_prey = o
        self.tongue_grab = None
        self.tongue_t = 0
        # LizardBreeds.cs:288-290 / LizardTongue.cs:519: the tongue has a
        # visible warm-up before the lash starts, especially pronounced on a
        # white lizard (80 ticks).  Keeping this state also gives the head and
        # jaw animation a chance to lead the rope instead of popping it out.
        self.tongue_warmup_left = max(0, int(self.breed.tongue_warmup))
        self.tongue_state = "warmup" if self.tongue_warmup_left > 0 else "out"
        self.tongue_cd = int(TONGUE_CD)
        self.jaw = max(self.jaw, TONGUE_JAW)
        self.wiggle = min(1.0, self.wiggle + WIGGLE_BUMP)
        # 反作用（原版 LashOut：bodyChunks[1].vel -= vector * lashOutSpeed）：
        # 舌头一甩出去，身体后节被顶退 —— 舌越猛、自己越退。旧实现完全没有这一下，
        # 于是「舔」看起来只是头上多了一条线。
        if len(self.seg) >= 2:
            self.seg[1].vx -= (dx / d) * self.tongue_speed * TONGUE_RECOIL
            self.seg[1].vy -= (dy / d) * self.tongue_speed * TONGUE_RECOIL
        return True

    def _tongue_reset(self) -> None:
        self.tongue_state = None
        self.tongue_warmup_left = 0
        self.tongue_len = 0.0
        self.tongue_prey = None
        self.tongue_grab = None
        self.tongue_t = 0

    def _tongue_pull(self, o) -> bool:
        """原版 DragChunk：把咬住的猎物往嘴边拽；到嘴返回 True（该 AttemptBite）。

        拽得动的只有「有物理的对象」：带 body.chunk0/1 的（蛞蝓猫）推它的 chunk
        速度，带 vx/vy 的（蝠蝇 / 蝉乌贼 / 面条蝇）推它的速度。都没有的对象只是
        被舔一下 —— 不硬改坐标（改别人的坐标会把别处的物理搅乱）。
        """
        tgt = getattr(o, "obj", o)
        px, py = _obj_pos(tgt)
        if px is None:
            return True
        mx, my = self._mouth_point()
        dx, dy = mx - px, my - py
        d = math.hypot(dx, dy)
        if d <= TONGUE_MOUTH_R:
            return True
        k = min(1.0, TONGUE_PULL / max(1.0, d))
        body = getattr(tgt, "body", None)
        chunks = [c for c in (getattr(body, "chunk0", None),
                              getattr(body, "chunk1", None)) if c is not None]
        if chunks:
            for c in chunks:
                c.vx = float(getattr(c, "vx", 0.0)) + dx * k * 0.5
                c.vy = float(getattr(c, "vy", 0.0)) + dy * k * 0.5
            return False
        vx, vy = getattr(tgt, "vx", None), getattr(tgt, "vy", None)
        if isinstance(vx, (int, float)) and isinstance(vy, (int, float)):
            tgt.vx = vx + dx * k
            tgt.vy = vy + dy * k
        return False

    def _tongue_tick(self) -> None:
        """舌头这一段物理：射出 → 命中 → 拽回来 → 到嘴转 AttemptBite → 收回。"""
        if self.tongue_cd > 0:
            self.tongue_cd -= 1
        if self.tongue_state is None:
            return
        if self.dead or self.stun > 0 or self.state == ItemState.MOUSE:
            self._tongue_reset()
            return
        self.tongue_t += 1
        mx, my = self._mouth_point()
        dx, dy = self.tongue_dir
        st = self.tongue_state
        if st == "warmup":
            self.tongue_warmup_left -= 1
            self.jaw = max(self.jaw, TONGUE_JAW)
            if self.tongue_warmup_left > 0:
                return
            self.tongue_state = "out"
            st = "out"
        # 舌外伸期间的拖拽（原版 LizardTongue.Update 262-280）：只要舌头还在外面，
        # 每 tick chunks[0].vel += DirVec(c0→tip)*4、chunks[1].vel -= 同向*4。
        # 所以「舌头拽着重物」时蜥蝎自己会被拉过去、「甩出去」时身体被反推 ——
        # 这一层旧实现完全没有，舌头就只是画出来的一条线。
        if st in ("out", "hold"):
            tipx, tipy = self.tongue_tip
            tdx, tdy = tipx - self.x, tipy - self.y
            tl = math.hypot(tdx, tdy)
            if tl > 1e-6:
                k = TONGUE_DRAG * min(1.0, tl / 60.0)
                self.vx += (tdx / tl) * k
                self.vy += (tdy / tl) * k
                if len(self.seg) >= 2:
                    self.seg[1].vx -= (tdx / tl) * k
                    self.seg[1].vy -= (tdy / tl) * k
        if st == "out":
            from ..core import chunkphys
            self.tongue_len += self.tongue_speed
            tip = (mx + dx * self.tongue_len, my + dy * self.tongue_len)
            # 原版舌尖逐 tick 扫掠地形；撞到实体墙后停在最后一个空气点，
            # 进入 StuckInTerrain，而不是穿墙继续追目标（LizardTongue.cs:370-440）。
            prev = self.tongue_tip
            hit = None
            solids = chunkphys.cat_solids()
            for i in range(1, 9):
                q = (prev[0] + (tip[0] - prev[0]) * i / 8.0,
                     prev[1] + (tip[1] - prev[1]) * i / 8.0)
                if any(a0 <= q[0] <= a1 and b0 <= q[1] <= b1
                       for a0, b0, a1, b1 in solids):
                    hit = i
                    break
            if hit is not None:
                frac = max(0.0, (hit - 1) / 8.0)
                tip = (prev[0] + (tip[0] - prev[0]) * frac,
                       prev[1] + (tip[1] - prev[1]) * frac)
                self.tongue_tip = tip
                self.tongue_state = "terrain"
                self.tongue_len = math.hypot(tip[0] - mx, tip[1] - my)
                return
            # 射程到头（原版 tongueRange）→ 收回
            if self.tongue_len >= self.breed.tongue_range:
                self.tongue_len = self.breed.tongue_range
                tip = (mx + dx * self.tongue_len, my + dy * self.tongue_len)
                self.tongue_state = "back"
            o = self.tongue_prey
            op = _obj_pos(getattr(o, "obj", o))
            if (o is not None and op[0] is not None
                    and math.hypot(op[0] - tip[0], op[1] - tip[1]) <= TONGUE_GRAB_R):
                self.tongue_grab = o          # 舌尖碰到：原版 Grab
                self.tongue_state = "hold"
            self.tongue_tip = tip
            return
        if st == "terrain":
            # StuckInTerrain：舌尖固定，身体沿舌方向受地形拖拽；靠近锚点后收回。
            tipx, tipy = self.tongue_tip
            dx0, dy0 = tipx - mx, tipy - my
            d0 = math.hypot(dx0, dy0)
            if d0 <= TONGUE_MOUTH_R:
                self.tongue_state = "back"
                return
            if d0 > 1e-6:
                ux, uy = dx0 / d0, dy0 / d0
                self.vx += ux * TONGUE_TERRAIN_PULL
                self.vy += uy * TONGUE_TERRAIN_PULL
                self.tongue_len = d0
            return
        if st == "hold":
            o = self.tongue_grab
            if o is None:
                self.tongue_state = "back"
                self.tongue_tip = (mx + dx * self.tongue_len, my + dy * self.tongue_len)
                return
            # 原版 DragChunk：舌头往回卷，猎物被舌尖拖着一起回到嘴边（两者
            # 同速，所以不会出现「舌头缩回了猎物还在原地」）。
            self.tongue_len = max(0.0, self.tongue_len - TONGUE_RETRACT)
            if self._tongue_pull(o):
                # 到嘴了：原版接着就是 AttemptBite，舌头这一趟结束
                self._start_bite(getattr(o, "obj", o))
                self.tongue_grab = None
                self.tongue_state = "back"
            elif self.tongue_len <= 0.0:
                # 卷到底了猎物还没到嘴：拽不动的东西（石头之类），放舌
                self.tongue_grab = None
                self.tongue_state = "back"
            self.tongue_tip = (mx + dx * self.tongue_len, my + dy * self.tongue_len)
            return
        # back：收回
        self.tongue_len -= TONGUE_RETRACT
        if self.tongue_len <= 0.0:
            self._tongue_reset()
            return
        self.tongue_tip = (mx + dx * self.tongue_len, my + dy * self.tongue_len)

    def _step_head(self) -> None:
        if not self.dead:
            nx, ny = self.head_x, self.head_y
            want = None
            if self.look_at is not None:
                vx, vy = self.look_at[0] - nx, self.look_at[1] - ny
                if math.hypot(vx, vy) > 0.5:          # 目标贴在颈上时不改朝向
                    want = _ang_from_up(vx, vy)
            elif self.state == ItemState.MOUSE:
                if abs(self.vx) + abs(self.vy) > 0.4:  # 被拎着：头随拖拽方向
                    want = _ang_from_up(self.vx, self.vy)
            elif self.climb_x is not None and self.climb_dir != 0:
                # 贴在竖杆 / 背景墙上：头沿「表面切线」朝上或朝下。原来这里沿用
                # 水平的 chain_dir，于是爬杆时头一直朝左右、身体朝上 —— 头方向
                # 和移动方向脱节（原版爬杆时头是朝爬行方向的）。
                want = 0.0 if self.climb_dir < 0 else 180.0
            else:
                # 没有观察目标时，头朝行进方向（move_dir）；身体轴 body_dir 滞后跟上。
                want = 90.0 if self.move_dir >= 0.0 else 270.0
            if want is not None:
                self.head_angle = _ang_lerp(self.head_angle, want, self._look_rate())
            self.head_driven = True
        else:
            self.head_angle = _ang_lerp(self.head_angle, 90.0 * self.facing, 0.04)
        # look_dir：头看向哪一侧（独立通道 —— 头可以只回头、身体不动）。
        self.look_dir = math.sin(math.radians(self.head_angle))
        # facing = 身体实际朝向（跟 body_dir），不是「这一帧的速度符号」：
        # 旧写法一帧就把 facing 翻过去，于是出现「身体还朝右、却在往左滑」的
        # 背面倒退帧。现在朝向只按 _step_turn 的速率扫过去。
        self.facing = 1 if self.body_dir >= 0.0 else -1
        # 下颚：单一目标 + 开/闭双速率（原版 jaw 是独立通道，不是「追猎就一路张着」）
        target = self.anim.jaw_open if self.anim is not None else self._jaw_target()
        rate = JAW_OPEN_RATE if target > self.jaw else JAW_CLOSE_RATE
        self.jaw = clampf(self.jaw + clampf(target - self.jaw, -rate, rate), 0.0, 1.0)

    def _step_head_point(self, WL: float) -> None:
        """头：挂在第 0 节躯干前方的软体末端（原版 head.ConnectToPoint）。

        目标 = bodyChunk0 + 体轴 × head_conn（颈长），再叠上转身 / 抬头的支起量。
        头是**被拖着**的：弹簧追目标 + 自身重力 + 空气阻力 —— 身体急停它还会往前
        窜一点、跳起来会被甩到体后、被拎着时垂在体前。原版头本来就在 bodyChunks
        物理系统里（不是游离的驱动质点），驱动权在躯干第 0 节。
        """
        self.head_lx, self.head_ly = self.head_x, self.head_y
        tx = self.x + self._ax_c * self.head_conn
        ty = self.y - self.turn_lift
        # 翻滚中头挂在体前的那一段也要跟着转（原版头在 bodyChunks 里一起翻）
        if self.flip_ang:
            fa = math.radians(self.flip_ang)
            rx, ry = tx - self.x, ty - self.y
            tx = self.x + rx * math.cos(fa) - ry * math.sin(fa)
            ty = self.y + rx * math.sin(fa) + ry * math.cos(fa)
        if (self.dead or self.stun > 0 or self.held_by_hand
                or self.state == ItemState.MOUSE):
            k = HEAD_SPRING_SOFT          # 颈子不使劲：头只被轻轻拖着
        else:
            k = HEAD_SPRING
        self.head_vx += (tx - self.head_x) * k
        self.head_vy += (ty - self.head_y) * k + HEAD_GRAV * self.room_gravity
        self.head_vx *= HEAD_AIR_FRIC
        self.head_vy *= HEAD_AIR_FRIC
        self.head_x += self.head_vx
        self.head_y += self.head_vy
        r = self.head_rad
        # 头也不许穿过庇护所墙体（和躯干同一份 PushOutOfTerrain）
        from ..core import chunkphys
        rects = chunkphys.solids()
        if rects:
            top = chunkphys.sweep_drop_top(self.head_x, r, self.head_ly,
                                          self.head_y, rects)
            if top is not None:                  # 头也会穿透薄墙：同一份扫掠
                self.head_y = top - r
                self.head_vy = 0.0
            self.head_x, self.head_y = _push_out(
                self.head_x, self.head_y, r, rects,
                getattr(chunkphys, "STEP_UP", 8.0))
        # 竖杆是 Climb surface，不是 Solid；头部可以穿过杆线，抓附时由
        # `_step_wall` 的横向弹簧统一处理，避免地面移动被杆子挡住。
        lim = self._ground - r * HEAD_STAND_FAC
        if self.head_y > lim:
            self.head_y = lim
            if self.head_vy > 0.0:
                self.head_vy = 0.0
        if self.head_x < r:
            self.head_x = r
            self.head_vx = 0.0
        elif self.head_x > WL - r:
            self.head_x = WL - r
            self.head_vx = 0.0
        # 物理扭头（文档 §9.2 / §10.4）：原版 HeadRotation 的头方向来自「颈→真实
        # head 节点」的几何 —— 头先转、前 1~2 节被颈子带偏、中段与尾巴滞后。旧实现
        # 只有 head_angle 在转，头的位置永远挂在体轴正前方，于是「贴图在看上头、脖子
        # 还朝前」，俯仰完全看不出来。
        #
        # 驱动量取 **AI 的注视角**（head_angle），不取头弹簧的瞬时位移：弹簧位移里混着
        # 重力下垂和咬合/起跳的冲量，拿它当弯曲源会反过来吃掉那些动作（实测把咬合时
        # 「前节比尾节先动」的位移差压掉一半）。没在看任何东西（look_at 为空，头只是
        # 沿 move_dir 朝前）时不带偏 —— 那种情况本来就不需要弯。
        if (not self.dead and self.stun <= 0 and not self.hauled
                and self.state != ItemState.MOUSE and len(self.seg) > 2
                and self.look_at is not None):
            ax, ay = _dirvec(self.seg[0].x - self.seg[2].x,
                             self.seg[0].y - self.seg[2].y)
            if abs(ax) + abs(ay) > 0.3:
                view = math.radians(self.head_angle)
                vx_, vy_ = math.sin(view), -math.cos(view)     # 0=上 90=右（屏幕系）
                nx_, ny_ = -ay, ax                             # 体轴法向
                lat = vx_ * nx_ + vy_ * ny_
                if lat < 0.0:                                  # 取朝观察方向那一侧
                    lat, nx_, ny_ = -lat, -nx_, -ny_
                off = HEAD_LEAD_K * self.head_conn * lat
                self.seg[1].x += nx_ * off
                self.seg[1].y += ny_ * off
                self.seg[2].x += nx_ * off * 0.45
                self.seg[2].y += ny_ * off * 0.45

    def _intent(self) -> LizardAnimIntent:
        """按当前 stage 生成动画意图 —— AI 与动画之间唯一的映射点（品种不进这层）。"""
        it = self.anim
        it.look_at = self.look_at
        it.jaw_open = self._jaw_target()
        it.look_lift = self._look_lift()
        it.alert = it.aggression = it.fear = 0.0
        it.body_compress = it.body_raise = 0.0
        it.locomotion = "idle"
        # Attack 动作序列的体态（文档 §9.3）：压低 → 递出 → 夹合 → 回收
        ph = self._atk_phase
        if ph == "prepare":
            it.body_compress = max(it.body_compress, ATK_COMPRESS_PREP)
            it.aggression = max(it.aggression, 0.7)
        elif ph == "lunge":
            it.body_raise = max(it.body_raise, ATK_RAISE_LUNGE)
            it.aggression, it.locomotion = 0.9, "run"
        elif ph == "bite":
            it.body_compress = max(it.body_compress, ATK_COMPRESS_BITE)
            it.aggression = max(it.aggression, 0.9)
        elif ph == "recover":
            it.body_compress = max(it.body_compress, ATK_COMPRESS_RECOVER)
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
        elif st == "InvestigateCursor":
            it.alert = 0.25
            it.locomotion = "walk"
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
        # 攀爬是独立的动作层状态。AI 的 stage 可能仍是 Hunt/Investigate，
        # 但一旦真正附着在竖杆、实体墙或背景墙上，渲染和步态都应使用爬行动画。
        if self.climb_x is not None and self.climb_attached:
            it.locomotion = "climb"
        it.turn = clampf(self._turn_imp, -2.0, 2.0)
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
        hx, hy = self.head_x - s0.x, self.head_y - s0.y
        hl = math.hypot(hx, hy) or 1.0
        lx, ly = (self.look_at if self.look_at is not None
                  else (self.head_x, self.head_y))
        vx, vy = lx - s0.x, ly - s0.y
        vl = math.hypot(vx, vy) or 1.0
        f2 = inv_lerp(0.0, 0.6, abs((hx / hl) * (vx / vl) + (hy / hl) * (vy / vl)))
        self.head_depth = lerp(self.head_depth, self.depth * f2, HEAD_DEPTH_LERP)
        # 转身中支起上半身（|depth| 越小 = 越正对镜头 = 转得越狠）
        # 再叠上「视觉注意方向」（目标在上→颈抬高）与动画意图的支起/压低。
        if self.dead:
            self.turn_lift = 0.0
            return
        # 支起量由「身体转过多少」驱动（turn_progress = 1-|body_dir|），而不是由
        # 腿反推的 depth 顺带带出来：转身是身体的事，腿只是跟着重新排步。两者
        # 形状同源（都在转身半途到 1），但 body_dir 才是这条链的驱动量。
        lift = TURN_LIFT * self.turn_progress
        lift += max(0.0, self.anim.look_lift) * LOOK_LIFT
        lift += self.anim.body_raise * BODY_RAISE_LIFT
        lift -= self.anim.body_compress * BODY_COMPRESS_DIP
        self.turn_lift = max(0.0, lift)

    def _head_dir(self):
        """颈→头的单位方向（原版 HeadRotation，花纹前段用）。"""
        s0 = self.seg[0]
        dx, dy = self.head_x - s0.x, self.head_y - s0.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return (1.0, 0.0)
        return (dx / d, dy / d)

    def _cosmetic_spine(self):
        """渲染用的脊柱折线（与 lizard_gfx.draw_lizard 同一套几何）。"""
        hx = self.head_x + (self.seg[0].x - self.head_x) * 0.2
        hy = self.head_y + (self.seg[0].y - self.head_y) * 0.2
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

    def _step_rock_flip(self) -> None:
        """推进石头击中的翻肚皮动作（Lizard.cs turnedByRockCounter）。

        原版用 WeightedPush 让首尾 body chunk 在约 20 帧内翻向侧面；
        我们同时给链体一个短角动量，渲染层通过 ``rock_flip_ang`` 同步头部，
        因此能看到「被石头打头 → 翻身」而不是仅有横向击退。
        """
        if self.rock_flip_left <= 0 or self.dead:
            self.rock_flip_ang *= 0.82
            if abs(self.rock_flip_ang) < 0.25:
                self.rock_flip_ang = 0.0
            return
        self.rock_flip_left -= 1
        self.rock_flip_ang += self.rock_flip_dir * (180.0 / 20.0)
        # 首尾反向冲量形成翻滚趋势；约束会把中节自然带回。
        if len(self.seg) >= 3:
            f = 0.32 * self.rock_flip_dir
            self.seg[0].vy -= f
            self.seg[2].vy += f
        if self.rock_flip_left <= 0:
            self.rock_flip_ang = 0.0

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
        # 转身冲量由 _step_turn 算好（身体轴摆量 + 速度突变），这里只施加到前 1~2
        # 节：前节先被带过去，中段靠约束传播稍晚、尾巴最后跟。
        dv = self.vx - self._last_vx
        self._last_vx = self.vx
        if held:
            self._turn_imp = 0.0
        # 方向带记忆：只有真正走出速度才翻面；否则停稳瞬间的
        # ±0.0x 抖动会把躯干甩到头前面，看起来就是「朝反方向走」。
        # chain_dir 现在由 _step_turn 按 body_dir 定；这里只管「没跑过 _step_turn
        # 的裸调用」（单元测试直接调 _step_chain）也要能翻面。
        if abs(self.vx) > TURN_VX and self.vx * self.chain_dir < 0.0:
            self.chain_dir = 1.0 if self.vx > 0.0 else -1.0
        grav = SEG_GRAV * (1.35 if held else 1.0) * self.room_gravity
        align = SEG_ALIGN_HELD if held else SEG_ALIGN
        conn = SEG_CONN_HELD if held else SEG_CONN_ELASTICITY
        # ① BodyChunk.Update：vel 受重力、乘空气阻力，pos += vel
        for k in range(min(TURN_IMP_SEGS, len(self.seg))):
            self.seg[k].vx += self._turn_imp * (1.0 - 0.45 * k)
        self._step_rock_flip()
        # 起跳 / 扑击 / 咬合的身体冲量：前 BODY_IMP_SEGS 节拿到全部，后面递减。
        # 施加两处：积分前（这一 tick 就动）+ 末尾的速度结算（下几 tick 仍带着
        # 它走）—— 于是「前节先出去、连接被拉长、中段和尾巴滞后跟上」。
        imp_x = clampf(self._body_imp_x, -BODY_IMP_MAX, BODY_IMP_MAX)
        imp_y = clampf(self._body_imp_y, -BODY_IMP_MAX, BODY_IMP_MAX)
        self._body_imp_x = self._body_imp_y = 0.0
        if held:
            imp_x = imp_y = 0.0
        shares = [0.0] * len(self.seg)
        for k in range(min(BODY_IMP_SEGS, len(self.seg))):
            shares[k] = (1.0 - BODY_IMP_FALLOFF) ** k
            self.seg[k].vx += imp_x * shares[k]
            self.seg[k].vy += imp_y * shares[k]
        # JawsSnapShut 的反作用（原版逐行：main += Dir * 8、bodyChunks[1]/[2] -= Dir * 6）：
        # 前节朝猎物冲出去、中后节被反推着坐一下 —— 夹合那一瞬整条身体是受力的，
        # 不是「头点自己动了」。尾巴挂在第 2 节后面，自然就滞后甩出去。
        if self._jaw_rec_x or self._jaw_rec_y:
            jx = clampf(self._jaw_rec_x, -BODY_IMP_MAX, BODY_IMP_MAX)
            jy = clampf(self._jaw_rec_y, -BODY_IMP_MAX, BODY_IMP_MAX)
            self._jaw_rec_x = self._jaw_rec_y = 0.0
            if not held:
                for k in range(min(3, len(self.seg))):
                    f = 1.0 if k == 0 else -(JAW_SNAP_BACK / JAW_SNAP_MAIN)
                    self.seg[k].vx += jx * f
                    self.seg[k].vy += jy * f
        # ⑥ bodyWiggleCounter（原版 Lizard.cs:2149-2158，逐行）：
        #    身体自己的低频扰动不是「按节画正弦」，而是**三节 bodyChunk 的反相速度
        #    冲量** —— bodyWiggle 相位累加 → 垂直于体轴的分量 → c0/c2 同号、c1 双倍
        #    反号。旧实现直接改 s.y（贴图在抖），动量传不到连接和尾巴上；改成冲量后
        #    被拖 / 转身 / 停着都是同一套物理在跑。
        self._desp_tick()
        fac = self.wiggle_fac()
        if not self.dead and fac > 0.0:
            self._wiggle_ph += (WIGGLE_RATE_LO
                                + (WIGGLE_RATE_HI - WIGGLE_RATE_LO) * fac) \
                * (WIGGLE_SPD_LO + (WIGGLE_SPD_HI - WIGGLE_SPD_LO) * WIGGLE_SPEED)
            k = (fac + 2.0) / ((1.0 - WIGGLE_SPEED) ** 2 + 2.0)
            ax_, ay_ = self._wiggle_axis()
            osc = math.sin(self._wiggle_ph * math.tau) * k
            wx_, wy_ = ax_ * osc, ay_ * osc
            self.seg[0].vx += wx_
            self.seg[0].vy += wy_
            self.seg[1].vx -= wx_ * 2.0
            self.seg[1].vy -= wy_ * 2.0
            self.seg[2].vx += wx_
            self.seg[2].vy += wy_
        self.wiggle *= WIGGLE_DECAY
        # ⑦ BodyDesperation 乱蹬（原版 Lizard.cs:2116-2122）：卡住 / 被拎起来时三节
        #    接到随机方向的 ±(0.5 / 1 / 0.5) 冲量 —— 原版「挣扎」就是这个，不是动画。
        if not self.dead and not self.hauled:
            desp = self.body_desperation()
            if desp > 0.0:
                ang = self._anim_rng.random() * math.tau
                mag = desp * MAX_MUSCLE_POWER * 2.0 * self._anim_rng.random()
                bx_, by_ = math.cos(ang) * mag, math.sin(ang) * mag
                self.seg[0].vx += bx_ * 0.5
                self.seg[0].vy += by_ * 0.5
                self.seg[1].vx -= bx_
                self.seg[1].vy -= by_
                self.seg[2].vx += bx_ * 0.5
                self.seg[2].vy += by_ * 0.5
        for s in self.seg:
            s.vy += grav * (TAIL_GRAV_FAC if s.tail else 1.0)
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
        c = getattr(self, "_ax_c", float(self.body_dir))
        c += (self.body_dir - c) * BODY_AX_LERP
        self._ax_c = c
        # 链根 = 第 0 节躯干本身（= AI 驱动点 self.x / self.y）。原版就是
        # bodyChunks[0] 被 AI 推着走、头挂在它前方 12*headSize；这里拓扑调成同一
        # 形状：躯干是驱动体，头是挂在体前的软体末端（见 _step_head_point）。
        self.seg[0].x, self.seg[0].y = self.x, self.y
        # 后空翻：整条身体绕质心转（含驱动点），必须在杆长约束之前 ——
        # 旋转是刚体变换（节距不变），先转再解约束，链子不会被掰回去。
        self._step_flip()
        anc_x = self.x
        anc_y = self.y
        # ② BodyChunkConnection + 顺直软约束：
        #    杆长约束只消掉径向误差，光靠它链子会自己折回来（两节各自满足距离但
        #    朝向反了）。原版 3 个 chunk 有质量互相顶、尾节还有 tailStiffness 撑直。
        #    旧实现在这里把「父节方向」的种子写死成水平（-chain_dir, 0），等于每帧
        #    强行把整条身体摊平到水平线 —— 身体因此呆滞、不会自然弯曲。现在种子取
        #    「锚点→第 0 节」的当前朝向（连续性），顺直只负责撑住，不负责摆正。
        # 基线取「锚点 → 第 1 节」而不是第 0 节：出生瞬间 seg[0] 与锚点重合
        # （初始几何就是 x-head_conn），拿 seg[0] 会退化成一个纯竖直方向，
        # 而长度约束只消径向误差、方向本身是中性不动点 —— 整条躯干从此锁成
        # 一根竖条（脚永远够不到地 = 「脚没踩地但身体在滑」，渲染上就是竖棍）。
        # 用第 1 节当基线既不退化，又保留链子自己的弯曲（不强行摊平）。
        # 种子的基线必须落在链子**外面**：驱动点 seg[0] 现在就是链根，下落 / 起跳
        # 时它比链节跑得快得多，拿它当基线等于把驱动点的瞬时速度灌进「链子朝哪
        # 边」——正反馈，链子会一路立起来（尾巴朝天，再也回不来）。和原版一样把
        # 基线放在驱动点**前方 head_conn**（＝原版 head 挂点那一带，在链子外面、
        # 不滞后），量到的才是链子自己的形状，不会把速度算成弯曲。
        _ref = self.seg[1] if len(self.seg) > 1 else self.seg[0]
        base_x = anc_x + self.chain_dir * self.head_conn
        seed_x, seed_y = _dirvec(_ref.x - base_x, _ref.y - anc_y)
        w = 1.0 - abs(c)                       # 0＝没在转身，1＝锚点正滑过头顶
        if w > 0.0:
            #    转身半途把「头后方」的指令方向混进种子里：光靠平滑的锚点，链子会
            #    原地不动被头拖着走（看起来倒着走），depth 也不会扫过中间几行；
            #    混入之后身体是按转身进度「滑」到另一侧的，不是被瞬间甩过去。
            cb = -1.0 if c >= 0.0 else 1.0
            seed_x = seed_x * (1.0 - w) + cb * w
            seed_y *= (1.0 - w)
        # 方向本身是中性不动点：头上下起伏（turn_lift / 落地）会把链子的朝向
        # 一点点推上去，几十帧后就成一根竖条。站在地面上（脚确实踩住这一层）时
        # 把种子朝「拖在头后方」拉一把，把不动点钉回水平；空中 / 被拎 / 贴墙攀爬
        # 保留纯几何方向 —— 那几种状态本来就该垂着/贴着，不该被强行摊平。
        trail_x, trail_y = -self.chain_dir, 0.0
        if self._contact_floor and not self.hauled and self.climb_x is None:
            seed_x, seed_y = (seed_x * (1.0 - BODY_SEED_TRAIL_K) + trail_x * BODY_SEED_TRAIL_K,
                              seed_y * (1.0 - BODY_SEED_TRAIL_K))
        if abs(seed_x) < 1e-6 and abs(seed_y) < 1e-6:
            seed_x, seed_y = trail_x, trail_y
        sn = math.hypot(seed_x, seed_y) or 1.0
        seed_x, seed_y = seed_x / sn, seed_y / sn
        # 链体朝向低通（和 _ax_c 同一套「不许瞬移」的思路）：转身时 seed 会在 c 过 0
        # 的那一帧整条掉头，等于把整条身体从一侧甩到另一侧 —— 髋部瞬移几十像素，
        # 踩在地上的脚立刻变成 50px 外的坏锚点，把身体往回拽（用户报的「脚黏住 /
        # 身体被拽回去」）。低通之后链体是绕过去的，不是被甩过去的。
        ps = self._seed_prev
        if ps is not None:
            seed_x = ps[0] + (seed_x - ps[0]) * CHAIN_SEED_LERP
            seed_y = ps[1] + (seed_y - ps[1]) * CHAIN_SEED_LERP
            sn = math.hypot(seed_x, seed_y)
            if sn < 1e-6:
                seed_x, seed_y = -self.chain_dir, 0.0
            else:
                seed_x, seed_y = seed_x / sn, seed_y / sn
        self._seed_prev = (seed_x, seed_y)
        for _ in range(SEG_SOLVER_ITER):
            prev_x, prev_y = anc_x, anc_y
            dir_x, dir_y = seed_x, seed_y
            for s in self.seg[1:]:      # 第 0 节是链根（驱动点），不被约束拉
                al = align * (TAIL_ALIGN_FAC if s.tail else 1.0)
                s.x += (prev_x + dir_x * s.dist - s.x) * al
                s.y += (prev_y + dir_y * s.dist - s.y) * al
                dx, dy = s.x - prev_x, s.y - prev_y
                d = math.hypot(dx, dy)
                if d > 1e-6:
                    k = (d - s.dist) * conn / d
                    s.x -= dx * k
                    s.y -= dy * k
                    nl = math.hypot(s.x - prev_x, s.y - prev_y) or 1.0
                    nx, ny = (s.x - prev_x) / nl, (s.y - prev_y) / nl
                    if (not held and not s.tail
                            and nx * dir_x + ny * dir_y < 0.0):
                        # 防自折：这一节相对父节折回去了（脖子处 180° 打结）。原版
                        # 3 个 chunk 有质量、会互相顶开，2D 里等价于「躯干节必须落在
                        # 父节的延长线一侧」。折回去对 align 来说是个吸收态 —— 光靠
                        # 每帧 16% 的软拉永远拉不回来（往旧方向拉、杆长约束又把它
                        # 推回旧位置），所以只能在这里直接摆正。尾巴不设限（能卷）。
                        nx, ny = dir_x, dir_y
                        s.x = prev_x + nx * s.dist
                        s.y = prev_y + ny * s.dist
                    dir_x, dir_y = nx, ny
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
        turn = dv
        if not held and abs(turn) > SEG_BEND_MIN_VX:
            bend = clampf(turn * SEG_BEND_K, -SEG_BEND_MAX, SEG_BEND_MAX)
            n_seg = len(self.seg)
            for k, s in enumerate(self.seg):
                if k == 0:
                    continue            # 弯曲冲量只给后面的节（第 0 节是驱动点）
                t = k / max(1, n_seg - 1)
                s.y -= bend * (1.0 - t) ** 2
                lim = HL - s.rad * (TAIL_SINK_FAC if s.tail else BODY_STAND_FAC)
                if s.y > lim:
                    s.y = lim
        # ④ 速度 = 本 tick 的实际位移：约束消掉的只是径向分量，切向动量得以保留
        for k, s in enumerate(self.seg):
            if k == 0:
                s.vx, s.vy = self.vx, self.vy     # 驱动点的速度就是身体速度
                continue
            s.vx = (s.x - ax0[k]) + imp_x * shares[k]
            s.vy = (s.y - ay0[k]) + imp_y * shares[k]
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
                if i == 0:
                    continue
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
        # 链根最后再钉一次：上面所有修正（弯曲 / 步态 / 落地）都不许把第 0 节
        # 从驱动点上拽走
        self.seg[0].x, self.seg[0].y = self.x, self.y

    # ── 腿 ──
    def wiggle_fac(self) -> float:
        """原版 Lizard.cs:474 BodyWiggleFac。

        ``Clamp((bodyWiggleCounter - wiggleDelay) / (50 + wiggleDelay), 0, 1)``。
        本作的 self.wiggle 就是 0..1 的等价计数器（事件抬高 / 每 tick 衰减），
        wiggleDelay 取 0 → Fac = Clamp(wiggle * 2)。
        """
        return clampf(self.wiggle * 2.0, 0.0, 1.0)

    def body_force(self) -> float:
        """原版 Lizard.cs:424：``Clamp(desperationSmoother * 0.025, 1, maxMusclePower)``。"""
        return clampf(self._desp * 0.025, 1.0, MAX_MUSCLE_POWER)

    def body_desperation(self) -> float:
        """原版 Lizard.cs:426：``InverseLerp(120, 400, desperationSmoother)``。"""
        return inv_lerp(120.0, 400.0, self._desp)

    def _desp_tick(self) -> None:
        """原版 Lizard.cs:1926：``desperationSmoother = LerpAndTick(…, 0.05, 0.5)``。

        目标值 = ``max(这次移动已经试了多久 + Lerp(-300,0,…), stuckTracker.Utility()*100)``。
        本作对应的两个量：被拎在半空（``state == MOUSE``）= 整只乱蹬（直接顶到 400，
        BodyDesperation = 1）；被地形卡住 = 按 StuckDetector 的等级给
        ``100 * level``（第 1 级就把 smoother 推过 120 的门槛）。
        """
        if self.state == ItemState.MOUSE:
            target = 400.0
        elif self.hauled or self.dead:
            target = 0.0
        else:
            target = 100.0 * max(0, self._stuck.level)
        # 原版 Custom.LerpAndTick：先按 lerp 插值，再把「单次变化量」**垫到至少
        # tick**（是下限不是上限 —— 抄成上限的话 smoother 每 tick 只动 0.5，
        # 400 要走 800 tick，等于永远不挣扎）。
        cur = self._desp + (target - self._desp) * DESP_LERP
        if self._desp < target:
            cur = min(target, max(self._desp + DESP_TICK, cur))
        elif self._desp > target:
            cur = max(target, min(self._desp - DESP_TICK, cur))
        self._desp = cur

    def _wiggle_axis(self):
        """原版 Lizard.cs:2153 的冲量方向：``Perpendicular(Slerp(Dir(c1→c0), Dir(c2→c1), 0.5))``。

        2D 里两个单位向量在 t=0.5 的 Slerp 就是「相加再归一化」（夹角 < 180° 时）；
        完全反向（加出来是零向量）就退回前一段的方向，避免除零。
        """
        c0, c1, c2 = self.seg[0], self.seg[1], self.seg[2]
        ax_, ay_ = c0.x - c1.x, c0.y - c1.y
        la = math.hypot(ax_, ay_) or 1.0
        ax_, ay_ = ax_ / la, ay_ / la
        bx_, by_ = c1.x - c2.x, c1.y - c2.y
        lb = math.hypot(bx_, by_) or 1.0
        bx_, by_ = bx_ / lb, by_ / lb
        mx, my = ax_ + bx_, ay_ + by_
        d = math.hypot(mx, my)
        if d < 1e-6:
            mx, my = ax_, ay_
        else:
            mx, my = mx / d, my / d
        return (-my, mx)

    def _step_legs(self, room_hl) -> None:
        """四足：逐行移植 LizardLimb.Update + Limb.Update（屏幕系 y↓，60 tick/秒）。

        要点（与原版一一对应）：
          jointDist = 25*(sizeFac+1)/2
          a = normalize(Lerp(DirVec(rotationChunk→髋), DirVec(髋→limbsAimFor), 0.4))
          num = DistanceToLine(脚, 髋, 髋+Perp(a)) == -(脚-髋)·a（屏幕叉积换算来的）
          换步触发：脚被拉到髋后方超过 StepLength
          绝对猎点：Lerp(脚, 髋, liftFeet) + a*(jointDist+1)；踩住时 FindGrip 锁定世界坐标
          腿长硬上限：ConnectToPoint(髋, jointDist)（原版 BodyPart.ConnectToPoint）

        状态机（「碰到了」和「已经踩稳了」必须分开）：

          Free ──伸腿──→ Reaching ──落到真实地形上──→ Grounded ──连贴 N 帧──→ Planted
            ↑                                                                  │
            └──────────── 换步（拉到身后）/ 脚下地形消失 ←──────────────────────┘

        支撑判定只看「脚 y 和这只脚脚下真实地形的差」，**不看 reaching**。
        reaching 只是「这条腿正在动」的标记；拿它当 grounded 的门，会出现
        「脚明明踩在地上、reaching 却已经清零」的腿永远进不了支撑相 ——
        身体只能靠剩下的腿滑行，这就是四脚全 false 的来历。

        planted 的脚这一相里完全不跑 Limb.Update 的位移（脚是支点，停在世界上
        不动，身体自己走过去），只有换步 / 地形消失才解除。
        """
        b = self.breed
        # LizardGraphics.cs:1154-1202 counts each Limb.gripCounter while the
        # creature is on a Climb/Wall tile.  The normal ground IK below asks
        # for a horizontal floor, so leaving it active during a vertical
        # climb made the legs dangle at the old floor and the body appear to
        # slide up a pole.  Keep the four limbs attached to the same vertical
        # surface and give alternating limbs a small climbing gait.
        if self.climb_x is not None and self.climb_attached:
            self._step_climb_legs()
            return
        joint = self._leg_joint()
        hunt = b.limb_speed
        quick = b.limb_quickness
        lift = clampf(b.lift_feet, 0.0, 0.85)
        step_len = lerp(-0.5, 0.5, b.step_length)         # StepLength（health = 1）
        floor = room_hl - LEG_LIMB_RAD
        stunned = self.stun > 0
        # limbsAimFor：原版是行进目标格中心，宠物里取躯干前方一点。
        # 用 move_dir（这一 tick 想去哪）而不是 chain_dir（身体轴，转身时滞后）——
        # 腿朝「要去的方向」迈步，身体自己慢慢拧过去。
        aim_dir = self.move_dir if self.move_dir != 0.0 else self.chain_dir
        self.limbs_aim = (self.x + aim_dir * LEG_AIM_AHEAD, self.y)
        grip = [0, 0, 0, 0]
        num8 = 0.0

        def foot_floor(lg):
            """这只脚脚底下的真实站立面（腿的着地点）。"""
            return (self._floor_under(lg.x, lg.y) - LEG_LIMB_RAD
                    if self.terrain is not None else floor)

        # ① 支撑相的门：这一帧脚是不是真的踩在真实地形上（完全不看 reaching）。
        #    用单侧判定：脚「低于面」也算接触（下一相 PushOutOfTerrain 会把它顶上来），
        #    只看「脚还悬在面上方多少」。双侧 abs() 会让脚在面上方 1.6px 悬着时
        #    误判成离地 —— 这正是换步脚永远落不了地的来历。
        # 被鼠标拎着 / 被猫拖着走：身体不是自己走出来的，这一帧的支撑脚全部
        # 作废 —— 否则旧支点会像橡皮筋把身体往回拽（甚至穿墙），也就是用户
        # 报的「拉拽离开后松手，脚把蜥蜴拽回去，脚还永远黏在那里」。
        held_body = self.state == ItemState.MOUSE or self.hauled
        on_ground = [bool(not stunned and not held_body
                          and lg.y >= foot_floor(lg) - FLOOR_GRIP_TOL)
                     for lg in self.legs]
        support_now = sum(1 for i, lg in enumerate(self.legs)
                          if lg.planted and on_ground[i])
        # planted 的总数（含腾空还钉着的老支点）：脚底下没面时用它来判
        # 「松开会不会一只都不剩」。
        planted_n = sum(1 for lg in self.legs if lg.planted)

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
            ax0, ay0 = ax, ay     # FindGrip 会就地改 a；抬脚位要用原始 a（原版如此）
            # 原版 num = DistanceToLine(脚, 髋, 髋+Perp(a)) == -(脚-髋)·a
            num = -(ax * (lg.x - hx) + ay * (lg.y - hy))

            if lg.planted:
                sd = math.hypot(lg.x - hx, lg.y - hy)
                if (sd > joint * LEG_MAX_STRETCH
                        and (planted_n - 1 >= self._leg_min_support()
                             or sd > joint * LEG_ANCHOR_MAX)):
                    # 脚被拉到腿长极限之外：它已经不可能还是真的支点（被拖拽 /
                    # 被挤飞 / 身体被窗口夹回来 / 被瞬移）。放开它、让它重新迈步。
                    # 原地钉住就是用户报的「脚永远黏在这里」—— 身体走远了它还
                    # 对着身体往回拉，而它自己永远不掉。
                    #   · 还有别的支撑脚时（放开后仍 ≥ 最少支撑数）按普通换步放开；
                    #   · 只剩它一只脚、且已远过 LEG_ANCHOR_MAX（_apply_foot_support
                    #     本来就不再把它当支点的距离）时无条件放开 —— 那种脚
                    #     本来就没有支撑作用，放开不会让身体失去真正的支撑。
                    # airborne=True 是必须的：脚此刻还贴在地面上，若给 False，下面
                    # 「没钉住的脚」那一段会在同一 tick 立刻把它按原位重新踩住 ——
                    # 于是「放开→重踩→再放开」每帧循环，脚永远黏在原地。
                    lg.planted = False
                    lg.reaching = True
                    lg.airborne = True
                    lg.swing = 0
                    lg.grip = 0
                    lg.plant_dx = lg.plant_dy = 0.0
                    if planted_n > 0:
                        planted_n -= 1
                    if support_now > 0:
                        support_now -= 1
            if stunned:
                lg.disabled = True
                lg.reaching = False
                lg.planted = False
                lg.grip = 0
                lg.airborne = False
                lg.swing = 0
                lg.plant_dx = lg.plant_dy = 0.0
                lg.vy += 0.9                             # 原版 vel.y -= 0.9f（y↑）→ 屏幕 +
            else:
                lg.disabled = False
                if lg.planted and on_ground[i]:
                    # ② 支撑相：钉住的脚这一帧还踩得住 —— 只累 gripCounter，
                    #    位置完全不动。该换步才解除。
                    lg.grip += 1
                    lg.snap = True
                    if self._leg_should_release(i, lg, hx, hy, num, joint, b,
                                                support_now):
                        lg.planted = False
                        lg.reaching = True           # 换步：立刻进下一次 FindGrip
                        lg.airborne = True           # 这一趟必须真的离过地才算迈步
                        lg.swing = 0
                        lg.grip = 0
                        lg.plant_dx = lg.plant_dy = 0.0
                        support_now -= 1
                        planted_n -= 1
                    else:
                        grip[2 if lg.pair >= 1 else 0] += 1
                elif lg.planted:
                    # 脚下地形没了（窗口挪走 / 走出平台边 / 整只蜥蜴在飞）：
                    # 解除，重新找落点。
                    # ① 还有脚踩着地的时候，松开不能把支撑脚数拉到最少支撑数
                    #    以下 —— 等别的脚先落地接管，避免「四脚同时腾空 →
                    #    身体贴地滑」。
                    # ② 一只脚都没接地（真的在飞 / 被吊起来）时全部松开：
                    #    这时候支点只是把身体拴在半空的橡皮筋，没有任何支撑意义。
                    if (not any(on_ground)
                            or planted_n - 1 >= self._leg_min_support()):
                        lg.planted = False
                        lg.reaching = True
                        lg.airborne = True
                        lg.swing = 0
                        lg.grip = 0
                        lg.snap = False
                        lg.plant_dx = lg.plant_dy = 0.0
                        support_now -= 1
                        planted_n -= 1

                if not lg.planted:
                    # ③ 没钉住的脚：脚在地上就直接进支撑相（原版 stance），
                    #    不在就伸腿去够地形（原版 FindGrip）。
                    lg.swing += 1
                    if lg.swing >= LEG_SWING_MAX:
                        # 摆太久还没落地：取消「必须先离地」的限制，让它随时能踩住。
                        lg.airborne = False
                    if (on_ground[i] and not lg.airborne
                            and math.hypot(lg.x - hx, lg.y - hy)
                            <= joint * LEG_MAX_STRETCH):
                        # 达到腿长极限以外的脚不能被“重新踩住”：身体被拖走后松手，
                        # 脚还在原来的地面上（on_ground 为真），旧实现会就地把它当成支点重新钉住 170px 外
                        # —— 这就是用户报的「脚永远黏在这里」的来历。先让 ConnectToPoint
                        # 把它拉回腿长以内，下一 tick 在合法位置重新落地。
                        lg.grip += 1
                        if lg.grip >= LEG_GRIP_DELAY:
                            lg.planted = True
                            lg.reaching = False
                            lg.snap = True
                            lg.abs_x, lg.abs_y = lg.x, lg.y
                            lg.plant_dx, lg.plant_dy = lg.x - hx, lg.y - hy
                            lg.swing = 0
                            grip[2 if lg.pair >= 1 else 0] += 1
                            support_now += 1
                            planted_n += 1
                    else:
                        if not on_ground[i]:
                            lg.airborne = False      # 真的离地了：这一趟在迈步
                        lg.reaching = True
                        lg.grip = 0
                        if lg.airborne:
                            # 刚拔脚：先朝「髋前方 jointDist+1」的猎点把脚抬起来
                            # （原版 liftFeet 那一步）。少了这一相，脚会贴着地面
                            # 平移到落点，永远不离地，也就永远进不了支撑相。
                            lg.abs_x = (lg.x + (hx - lg.x) * lift
                                        + ax * (joint + 1.0))
                            lg.abs_y = (lg.y + (hy - lg.y) * lift
                                        + ay * (joint + 1.0))
                            continue_out = True
                        else:
                            continue_out = False
                        # FindGrip 的宠物版：先问「脚下这块地形的表面在哪」，
                        # 再把落点夹进 jointDist 半径内 —— 而不是先把 x 顶到
                        # joint-1 处再硬塞到地面、最后又被腿长压回来。
                        k = (6.0 - 12.0 * (i % 2)) * 0.2
                        px_, py_ = ay * k, -ax * k             # Perp_screen(dx,dy) = (dy,-dx)
                        ax += px_
                        ay += py_
                        ay += 0.3 * b.feet_down                # 原版 a.y -= 0.3*feetDown
                        ax += (-1.0 if i % 2 == 0 else 1.0) * b.leg_pair_disp * lg.flip
                        if not continue_out:
                            rmax = joint - 1.0
                            want_x = hx + ax * rmax
                            support_y = (self._floor_under(want_x, hy)
                                         if self.terrain is not None else room_hl)
                            gy = support_y - LEG_LIMB_RAD
                            dy_g = gy - hy
                            if abs(dy_g) > rmax:
                                # 地形整块落在 jointDist 之外：这一脚够不到，
                                # 不生成虚假的悬空落点，把猎点放回「髋前方
                                # jointDist+1」的抬脚位（原版 liftFeet），等身体
                                # 走近再迈 —— 而不是留着一个陈旧的 abs 乱指。
                                lg.abs_x = (lg.x + (hx - lg.x) * lift
                                            + ax0 * (joint + 1.0))
                                lg.abs_y = (lg.y + (hy - lg.y) * lift
                                            + ay0 * (joint + 1.0))
                                lg.snap = False
                            else:
                                reach_x = math.sqrt(max(0.0, rmax * rmax - dy_g * dy_g))
                                lg.abs_x = hx + clampf(want_x - hx, -reach_x, reach_x)
                                lg.abs_y = gy
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
                if not lg.planted:
                    # 只有「在空中的脚」才跑 Limb.Update 的位移；踩住的脚是
                    # 支点，这一相里它就该停在世界上不动（身体自己走过去）。
                    lg.x += lg.vx
                    lg.y += lg.vy
                    lg.vx *= LEG_AIR_FRIC
                    lg.vy *= LEG_AIR_FRIC
                leg_floor = (self._floor_under(lg.x, lg.y)
                             - LEG_LIMB_RAD if self.terrain is not None else floor)
                if lg.y > leg_floor:                         # PushOutOfTerrain
                    lg.y = leg_floor
                    if lg.vy > 0.0:
                        lg.vy = 0.0
                elif (not lg.planted and not lg.airborne
                      and lg.vy >= 0.0 and lg.abs_y >= lg.y - 0.5
                      and leg_floor - lg.y <= LEG_LAND_TOL):
                    # 落地吸附（原版 reachedSnapPosition）：脚已经降到落点面附近、
                    # 目标是地面就踩下去。少了这一步，脚会因为「水平距离远 →
                    # 方向矢量几乎水平 → vy 极小」而永远贴着面上方飘。
                    lg.y = leg_floor
                    lg.vy = 0.0
            # ── ConnectToPoint(髋, jointDist)：腿长硬上限（脚不会被甩飞）──
            ddx, ddy = lg.x - hx, lg.y - hy
            dd = math.hypot(ddx, ddy)
            if dd >= joint and dd > 1e-6 and not lg.planted:
                over = dd - joint
                ox_, oy_ = ddx / dd, ddy / dd
                lg.x -= ox_ * over
                lg.y -= oy_ * over
                lg.vx -= ox_ * over
                lg.vy -= oy_ * over
            # planted 脚是支点：绝不拖离地面。超长的部分交给
            # _apply_foot_support() 把身体往脚的方向回拉。
            # ── flip（原版 LizardGraphics.cs:1209-1215）──
            # num11 = DistanceToLine(脚, connection.pos, rotationChunk.pos)；
            # 本式算出的值 = -原版值（屏幕 y↓），所以符号规则与原版一致：i<2 取负。
            # 朝右时四腿 num11 全为负 → num8=-1 → depthRotation=-1 → 头 scaleX=-1。
            num11 = _leg_flip_num(i, hx, hy, rx, ry, lg)
            lg.flip = lerp(lg.flip, 1.0 if num11 < 0.0 else -1.0, 0.3)
            if abs(num11) > LEG_DEPTH_MIN:
                num8 += 1.0 if num11 > 0.0 else -1.0
        self._collide_chain_lines(room_hl)
        for lg in self.legs:
            if not lg.planted:
                lg.plant_dx = lg.plant_dy = 0.0
        self.depth_in = clampf(num8, -1.0, 1.0)
        self._step_bob(grip)

    def _step_climb_legs(self) -> None:
        """Attach limbs to a vertical wall/pole/background surface.

        This is the desktop equivalent of LizardLimb.FindGrip on a Climb tile
        (LizardGraphics.cs:1154-1202): no floor support is consulted while a
        limb is gripping the vertical surface.  ``climb_side`` is the outside
        normal for a solid wall; poles/background surfaces are centred.
        """
        joint = self._leg_joint()
        top = self.climb_top
        bot = self.climb_bot
        span = (float(top), float(bot)) if top is not None and bot is not None else None
        if self.climb_kind == "wall":
            # 实体墙的脚也落在墙面外侧，避免四肢穿进 shelter/extra wall。
            wall_x = (float(self.climb_x)
                      + self.climb_side * (self.head_rad + LINE_COLLIDE_PAD))
        elif self.climb_kind == "background":
            # 背景墙不参与实体碰撞，但四肢仍要挂在其可见边缘，而不是
            # 以背景中心线为抓点，否则爬行动画看起来会穿过背景。
            wall_x = (float(self.climb_x)
                      + self.climb_side * (self.head_rad * 0.65 + LINE_COLLIDE_PAD))
        else:
            # 竖杆的抓点是中心线；左右脚仅通过 along/flip 做视觉分层。
            wall_x = float(self.climb_x)
        # ``walk_phase`` advances in the body stepper.  Offset front/rear
        # pairs in opposite phases so three visible contact points remain on
        # the surface when the lizard changes direction.
        for i, lg in enumerate(self.legs):
            pi = lg.pair if lg.pair < len(self.seg) else len(self.seg) - 1
            hip = self.seg[pi]
            side = -1.0 if (i % 2 == 0) else 1.0
            phase = self.walk_phase * 0.12 + i * math.pi * 0.5
            along = math.sin(phase) * joint * 0.32 + side * joint * 0.16
            want_y = hip.y + along
            if span is not None:
                want_y = clampf(want_y, span[0] + 4.0, span[1] - 4.0)
            # Keep a little spring instead of teleporting the feet when the
            # wall climb reverses direction.
            lg.vx = (wall_x - lg.x) * 0.45
            lg.vy = (want_y - lg.y) * 0.45
            lg.x += lg.vx
            lg.y += lg.vy
            lg.vx *= 0.55
            lg.vy *= 0.55
            lg.planted = True
            lg.reaching = False
            lg.airborne = False
            lg.grip = LEG_GRIP_DELAY
            lg.snap = True
            lg.plant_dx = lg.x - hip.x
            lg.plant_dy = lg.y - hip.y
            lg.flip = lerp(lg.flip, 1.0 if self.climb_side < 0 else -1.0, 0.2)
        self.depth_in = -1.0 if self.climb_side < 0 else 1.0
        nfront = sum(1 for lg in self.legs if not lg.back)
        nhind = len(self.legs) - nfront
        self._step_bob([nfront, 0, nhind, 0])

    def _leg_min_support(self) -> int:
        """支撑相至少保留几只脚（四足 = 2，两腿品种 = 1）。"""
        return max(1, min(LEG_MIN_SUPPORT, len(self.legs) - 1))

    def _leg_should_release(self, i, lg, hx, hy, num, joint, b, support_now) -> bool:
        """支撑相里的脚什么时候让位（原版 LizardLimb 的换步条件）。

        ① 脚已经被拉到髋后方超过 ``jointDist * -0.5*(stepLength+0.1)``；
        ② 脚和髋的实际距离超过这条腿的阈值（按腿号错开，四只脚不会一起抬）。

        **不允许把支撑脚数拉到最少支撑数以下**，也没有「拉到硬上限就放它走」的
        例外 —— 那条例外是四脚同时腾空的源头：支撑脚被拽到 joint 就无条件松开，
        哪怕松开之后一只脚都不剩。被拽长的部分由 ``_apply_foot_support`` 让身体
        停下来等腾空的脚落地，而不是把腿拽断。
        """
        # 每条腿的「拉满」阈值都要落在硬上限 joint 以内，否则 0 号腿的阈值正好
        # 等于 joint —— 它只有被拽到硬上限才能换步，一换步支撑脚数就掉到最少
        # 支撑数以下（这正是四脚全 false 的另一半来历）。
        stretch = joint - LEG_STEP_STAGGER * (i + 1)
        if not (num > joint * -0.5 * (b.step_length + 0.1)
                and not _dist_less(lg.x, lg.y, hx, hy, stretch)):
            return False
        return support_now > self._leg_min_support()

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


def _cat_waa(obj) -> bool:
    """Whether the Survivor's waa cue is currently active."""
    return bool(getattr(obj, "_waa_active", False)
                and getattr(obj, "variant", "") == "survivor")


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


def _obj_pos(src):
    """取目标坐标 (x, y)；拿不到（没有目标 / .x 不是数）时返回 (None, None)。

    有些对象（Qt 控件、部分观察替身）的 .x 是个方法而不是坐标 —— 直接拿去相减
    会 TypeError，所以这里只认真正的数值。
    """
    if src is None:
        return None, None
    px, py = getattr(src, "x", None), getattr(src, "y", None)
    if (isinstance(px, (int, float)) and not isinstance(px, bool)
            and isinstance(py, (int, float)) and not isinstance(py, bool)):
        return float(px), float(py)
    # Cats are PetUnit instances: their world position lives in body.chunk0,
    # not on PetUnit.x/y.  The observation has coordinates, but _lunge stores
    # the underlying PetUnit as target_obj.  Without this fallback
    # _shoot_tongue immediately returns False for every slugcat.
    chunk = getattr(getattr(src, "body", None), "chunk0", None)
    if chunk is not None:
        px, py = getattr(chunk, "x", None), getattr(chunk, "y", None)
        if isinstance(px, (int, float)) and isinstance(py, (int, float)):
            return float(px), float(py)
    return None, None


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


