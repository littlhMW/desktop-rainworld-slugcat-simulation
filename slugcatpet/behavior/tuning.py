"""行为参数中枢，tick=1/40s；每猫专属覆盖见 cats/<variant>.CatDef.tuning。"""
from __future__ import annotations

# 心情仲裁打分噪声
MOOD_NOISE_AMP = 0.20

# 趴下休息：体力驱动的强制疲劳
EXHAUST_ENTER_ENERGY = 0.1
EXHAUST_EXIT_ENERGY = 0.50
LIE_SETTLE_TICKS = 40

# 耗能玩法体力门
PLAY_ENERGY_GATE = 0.40

# 性格接线全局旋钮
PERS_ACT_SPREAD  = 1.0
PERS_GATE_SPREAD = 0.20
PERS_GATE_FLOOR  = 0.20


# 爬竖杆权重与新鲜度
POLE_BASE = 1.00
POLE_START = 0.70
POLE_QUIT = 0.30
POLE_INIT = 0.30
POLE_DECAY = 0.0040
POLE_RECOVER = 0.00100
POLE_SF_FRESH = 1.50
POLE_SF_TIRED = 0.10

# 横杆权重与新鲜度
# 横杆（原版 horizontal beam）：无舌猫走「爬交叉竖杆换杆」或「地面起跳抓杆」
HPOLE_JUMP_RISE = 37.0        # 站立跳胸心上升量（实测），杆再高就跳不到
HPOLE_JUMP_GRAB = 22.0        # 空中贴杆转 HPole 的距离
HPOLE_JUMP_TRIES = 4          # 起跳尝试次数上限
HPOLE_JUMP_CD = 48            # 每次起跳后的等待 tick（等落地/判失败）
HPOLE_BASE = 1.00
HPOLE_START = 0.72
HPOLE_QUIT = 0.30
HPOLE_INIT = 0.30
HPOLE_DECAY = 0.0035
HPOLE_RECOVER = 0.00100
HPOLE_SF_FRESH = 1.30
HPOLE_SF_TIRED = 0.10

# 上天花板权重与新鲜度
CEIL_BASE = 1.00
CEIL_START = 0.75
CEIL_QUIT = 0.30
CEIL_INIT = 0.10
CEIL_DECAY = 0.0018
CEIL_RECOVER = 0.00070
CEIL_SF_FRESH = 1.30
CEIL_SF_TIRED = 0.15
# 避水闸：涨水强制中断上吊顶
CEIL_WATER_ENERGY_GATE = 0.20

# 发呆兜底候选权重与驻留
IDLE_BASE = 1.00
IDLE_SF_KNEE = 0.9
IDLE_SF_FRESH = 0.18
IDLE_SF_TIRED = 24.0
IDLE_HOLD_MIN = 55
IDLE_HOLD_MAX = 240
IDLE_HOLD_TIRED_MULT = 1.8
IDLE_BREATHER = 40

# 饱食度
FOOD_INIT = 2
FOOD_KILL_PENALTY = 4
EN_EAT_RESTORE = 0.10

# 业力与冬眠
# 死亡后原地长业力花的延迟（tick = 1/40s）。
# 原版 Player.PlaceKarmaFlower：黄猫无条件 / 其他猫要有 reinforcedKarma；
# 桌宠没有雨循环，改成「死后等一段时间原地长出来」。
FLOWER_HUNTER_MIN    = 600      # 猎手 15s
FLOWER_HUNTER_MAX    = 1800     # 猎手 45s
FLOWER_OTHER_MIN     = 6000     # 其他猫 150s
FLOWER_OTHER_MAX     = 8400     # 其他猫 210s

KARMA_INIT = 8
KARMA_MAX = 9
HIBERNATE_TICKS = 3600
REVIVE_TICKS = 50

# 好感
TEMPER_SWING_SPEED = 10.0
TEMPER_SWING_RATE = -0.0008
# 被鼠标抓着剧烈左右摇晃 → 手里的东西甩出去
DRAG_SHAKE_SPEED  = 6.0        # 单帧横向速度门限（px/tick）
DRAG_SHAKE_FLIPS  = 3          # 计数窗口内的反向次数
DRAG_SHAKE_WINDOW = 90         # 反向计数的保持窗口（tick）
DRAG_SHAKE_CD     = 40         # 甩掉一件后的冷却（tick）
DRAG_SHAKE_THROW  = 0.6        # 甩出速度 = 摆动速度 × 该系数
DRAG_SHAKE_TEMPER = -0.0005    # 被摇烦
TEMPER_STUN = -0.25
TEMPER_KILL_REVIVED = -0.50
TEMPER_FEED = 0.20
TEMPER_LICK = 0.10
TEMPER_DECAY = 1.0 / 180000.0

# 寒冷、暴风雪、暖灯供暖、转世
COLD_BLIZZARD_DEFAULT_OFF = True
COLD_BLIZZARD_RAMP   = 2400
COLD_BLIZZARD_HOLD   = 2400
COLD_BLIZZARD_TOTAL  = 2 * COLD_BLIZZARD_RAMP + COLD_BLIZZARD_HOLD
COLD_EXPOSURE        = 1.0
COLD_GAIN_CLAMP_HI   = 0.0055
COLD_LAMP_WARMTH     = 0.0005
COLD_LAMP_RANGE      = 350.0
COLD_LAMP_SCALE      = 0.6
COLD_CRAMP_GAIN_GATE = 0.0003
COLD_DEATH_STUN      = 50
COLD_WARMTH_INNER    = 70.0
COLD_NATURAL_DECAY   = 0.001
REINCARNATE_TICKS    = 600
# 睡到自然醒的时长：20~40s 随机（用户口径；tick = 1/40s）
SLEEP_SECS_MIN       = 20.0
SLEEP_SECS_MAX       = 40.0
ALL_DEAD_GRACE_TICKS = 300     # 全员死亡后守灵等待（窗口内同伴仍可扒拉救回）

# 自主趋暖与冻醒
COLD_SEEK_ENTER  = 0.30
COLD_SEEK_EXIT   = 0.10
COLD_NOSLEEP     = 0.20
COLD_SEEK_BASE   = 3.0
COLD_ARRIVE_FRAC = 0.8

# 雪与霜冻氛围
SNOW_ENABLED      = True
SNOW_MAX_FLAKES   = 50
SNOW_VIGNETTE_MAX = 15

# 水环境（默认关）
WATER_FULL_DEPTH = 0.55
WATER_EASE_TICKS = 400
WATER_STILL_EPS  = 0.15
WATER_SPACING    = 20.0
WATER_FLOW       = 0.08
WATER_BODY_RGBA    = (46, 120, 150, 92)
WATER_SURFACE_RGBA = (150, 214, 232, 175)
WATER_THREAT_SAFE_DEPTH = 60.0

# 游泳/憋气/淹死（y↓）
SWIM_ENTER            = 0.2
SWIM_DEEP_DEPTH       = 30.0
SWIM_DEEP_DIVE_DEPTH  = 10.0
SWIM_DEEP_FULL        = 80.0
SWIM_DEEP_HIP_SUB     = 0.6
SWIM_BOOST_MIN_AIR    = 0.5
SWIM_BOOST_DIST       = 60.0
SWIM_SURFACE_HEAD_ABOVE = 15.0
SWIM_LUNG_SUBMERGE    = 0.9
SWIM_DROWN_SUB_HIP    = 0.5
SWIM_DROWN_STEP       = 1.0 / 120.0
SWIM_LUNG_RECOVER     = 60.0
SWIM_LUNG_RECOVER_EXH = 240.0
SWIM_ARRIVE_R         = 34.0
SWIM_FETCH_SEEK_R     = 220.0
SWIM_FETCH_REACH      = 22.0
SWIM_VEL_MAX          = 45.0
SWIM_SURFACE_REST_FAC = 0.5
# 漂游潜深随 swim_zeal 插值
SWIM_DRIFT_DEPTH_MIN  = 15.0
SWIM_DRIFT_DEPTH_MAX  = 70.0
SWIM_DRIFT_DEEP_MAX   = 260.0
SWIM_BOOST_DIST_ZEAL  = 25.0
# 圣徒落水自救：贴墙舌爬出水面
SWIM_ESCAPE_ENERGY    = 0.35
SWIM_ESCAPE_CD        = 200
SWIM_ESCAPE_WALL_REACH = 70.0
PYRO_DEATH_THRESH     = 0.65    # 工匠溺水引爆阈

# 工匠 AI 爆跳：弧线 sim 与 FSM 控制器共用参数
PYRO_BOOST_AIR_TICKS  = 6
PYRO_REACH_MIN_DX     = 140.0

# 工匠爆跳撒欢权重与新鲜度
PYROROMP_BASE = 1.00
PYROROMP_START = 0.72
PYROROMP_QUIT = 0.30
PYROROMP_INIT = 0.30
PYROROMP_DECAY = 0.0040
PYROROMP_RECOVER = 0.00055
PYROROMP_JUMPS = 2

# 溪流后空翻上横杆权重与新鲜度
RIVFLIP_BASE = 1.00
RIVFLIP_START = 0.72
RIVFLIP_QUIT = 0.30
RIVFLIP_INIT = 0.30
RIVFLIP_DECAY = 0.0040
RIVFLIP_RECOVER = 0.00055

# 溺水吐泡
BUBBLE_MAX         = 40
BUBBLE_DRAW_SCALE  = 0.45
BUBBLE_RGBA        = (0, 1, 0)
BUBBLE_OPACITY     = 0.25
BUBBLE_INHERIT_VEL = 0.025
BUBBLE_SPAWN_KICK  = 0.5

# idle 兜底层：东张西望
LOOK_UPDATE_PROB = 0.025
LOOK_NOTHING_PROB = 0.002
LOOK_GLANCE_PROB = 0.002
LOOK_GLANCE_INTEREST = 0.40
LOOK_INTEREST_DECAY_TICKS = 24
LOOK_MIN_INTEREST = 0.20
LOOK_DIST_NEAR = 400.0
LOOK_CURSOR_BASE = 1.00
LOOK_ITEM_BASE = 0.80
# idle 兜底层：踱步
PACE_PROB = 0.0016
# idle 社交走位：按 sociability 决定趋近/远离/随机
SOCIAL_WANDER_LO = 0.4
SOCIAL_WANDER_HI = 0.6
SOCIAL_WANDER_SAMPLES = 11
SOCIAL_WANDER_SIGMA_FRAC = 0.15
SOCIAL_WANDER_MOVE_W = 0.6
SOCIAL_WANDER_CROSS_W = 0.8
SOCIAL_WANDER_STAY_GAIN = 0.05
SOCIAL_WANDER_STAY_SPAN_FRAC = 0.06

# ── 六类欲望（进食/恐惧/战斗/玩耍/睡眠/社交）──
# 爬墙（窗口左右边缘＝墙）
WALL_SEEK_R = 90.0            # 墙多近算「贴着墙」（退无可退的角落判定用）

# 被抓：偶尔挣扎（原版 Player 被叼住时蹬腿乱蹬）
DRAG_STRUGGLE_PROB = 0.012    # 每 tick 起挣扎的概率
DRAG_STRUGGLE_MIN_FRAMES = 20 # 刚抓起先愣一下
DRAG_STRUGGLE_TICKS_MIN = 14
DRAG_STRUGGLE_TICKS_MAX = 34
DRAG_STRUGGLE_KICK = 2.6      # 挣扎蹬腿冲量
DRAG_STRUGGLE_VMAX = 3.2      # 自由那截的挣扎速度上限（别甩飞）
DRAG_STRUGGLE_TEMPER = 0.03   # 每次挣扎的心烦增量
DRAG_STRUGGLE_COST = 0.004    # 每次挣扎的体力消耗

# 吊顶（窗口上边缘＝地面/天花）
CEIL_BASE = 1.00
CEIL_START = 0.70
CEIL_QUIT = 0.30
CEIL_INIT = 0.20
CEIL_DECAY = 0.0030
CEIL_RECOVER = 0.00060
CEIL_HANG_TICKS_MIN = 160
CEIL_HANG_TICKS_MAX = 480
CEIL_SHIMMY_PROB = 0.02
CEIL_GRAB_REACH = 96.0        # 跳起来够顶边的判定距离
CEIL_SETTLE_SPEED = 3.0       # 蹭到顶边且慢到这个速度 → 吊住（顶边当平地）
CEIL_WALK_PROB = 0.03         # 吊着时开始沿顶边走动
CEIL_WALK_TICKS_MIN = 20
CEIL_WALK_TICKS_MAX = 70
CEIL_PLACED_TICKS_MIN = 600   # 鼠标放到顶边：愿意多挂一会（10s）
CEIL_PLACED_TICKS_MAX = 1200

# 爆米花（原版外部食物源）：开荚后贴上去啃，每口 +1 饱食
COB_FEED_R = 25.0             # 原版 Custom.DistLess(mainBodyChunk, 最近点, 25f)
COB_EAT_TICKS = 15            # 原版 eatExternalFoodSourceCounter = 15
COB_EAT_CD = 45               # 原版 dontEatExternalFoodSourceCounter = 45
COB_EAT_FOOD = 1              # 原版 AddFood(1)
COB_FEED_SEEK_R = 300.0       # 饿了才会走这么远去啃
COB_REACH_DY = 70.0           # 挂得比胸口高这么多就够不着（跳起来也啃不到）
COB_FEED_TICKS = 600          # 没吃到东西就撤的预算（每吃一口重置）
COB_CHECK_TICKS = 20          # 找豆荚的闸
COB_SEEK_RETRY = 300          # 放弃后的重试冷却
COB_SPEAR_R = 420.0           # 拿矛打未开荚爆米花的距离

# 玩耍：追光标/抓光标（原版蛞蝓猫对移动物体的注意）
PLAYCUR_BASE = 1.00
PLAYCUR_START = 0.66
PLAYCUR_QUIT = 0.30
PLAYCUR_INIT = 0.30
PLAYCUR_DECAY = 0.0042
PLAYCUR_RECOVER = 0.00110
PLAYCUR_SF_FRESH = 1.25
PLAYCUR_SF_TIRED = 0.12
PLAYCUR_R = 520.0             # 光标在此半径内才会想过去（范围调大：更注意到鼠标）
CURSOR_NEAR_R      = 260.0   # 「鼠标停在猫附近」的判定半径（范围调大）
CURSOR_POINT_DWELL = 150     # 鼠标在附近停留够这么多 tick 才会被指指点点（约 3.7s）
DRAGGED_PEER_POINT_FAC = 0.45  # 有同伴正被鼠标拖着：被指指点点的门槛打这个折（更容易被指）
CURSOR_NEAR_R      = 260.0   # 「鼠标停在猫附近」的判定半径（范围调大）
CURSOR_POINT_DWELL = 150     # 鼠标在附近停留够这么多 tick 才会被指指点点（约 3.7s）
DRAGGED_PEER_POINT_FAC = 0.45  # 有同伴正被鼠标拖着：被指指点点的门槛打这个折（更容易被指）
PLAYCUR_ARRIVE = 46.0
PLAYCUR_TICKS_MIN = 120
PLAYCUR_TICKS_MAX = 320
PLAYCUR_GRAB_R = 26.0         # 够得着就伸手抓
PLAYCUR_CHASE_SPEED = 0.7     # 走速比例

# 社交：靠近同伴 / 抚摸同伴 / 指指点点
SOCIAL_BASE = 1.00
SOCIAL_START = 0.62
SOCIAL_QUIT = 0.30
SOCIAL_INIT = 0.25
SOCIAL_DECAY = 0.0030
SOCIAL_RECOVER = 0.00062
SOCIAL_SF_FRESH = 1.20
SOCIAL_SF_TIRED = 0.12
SOCIAL_R = 220.0              # 同伴在此半径内才想凑过去
SOCIAL_ARRIVE = 30.0
SOCIAL_ABANDON_R = 300.0      # 对象跑出这个距离：手上的社交动作直接放弃（不强制演完）
SOCIAL_THANK_P = 0.02         # 每 tick 想去道谢的概率（260 tick 窗口内基本会去；跑远就放弃）
SOCIAL_TICKS_MIN = 160
SOCIAL_TICKS_MAX = 420
SOCIAL_POKE_TICKS = 90        # 扒拉/抚摸/指指点点动作时长
SOCIAL_POKE_INTERVAL = 22     # 每次伸手的间隔
# ── 社交欲望（第六类：进食/恐惧/战斗/玩耍/睡眠/社交）──
# 动作词表见 behavior/social.py；这里只放手势参数与抽取权重
SOCIAL_URGE_RATE = 1.0 / 4200.0   # 每 tick 累积（约 105s 攒满才想找人）
# 社交欲望的「事件加成」：吃到东西 / 吃饱 / 睡醒 / 别人的社交 都会大幅拉高
SOCIAL_URGE_BOOST_EAT = 0.34      # 每吃到一口
SOCIAL_URGE_BOOST_FULL = 0.50     # 吃到饱
SOCIAL_URGE_BOOST_WAKE = 0.45     # 睡醒
SOCIAL_URGE_BOOST_NEAR = 0.40     # 看到同伴做社交动作
SOCIAL_BOOST_R = 300.0            # 别人社交影响到自己的半径
PET_BASE = 1.00                   # 抚摸
PAT_BASE = 0.85                   # 拍拍
POINTHOLD_BASE = 0.70             # 指向（举着不放）
SOCIAL_SCOLD_BASE = 0.60          # 指指点点
CROUCH_WALK_BASE = 0.25           # 匍匐行走（匍匐族唯一动作；只在附近有蜥蜴时抽得到）
PET_REPS_MIN = 2                  # 抚摸/拍拍：折返次数
PET_REPS_MAX = 5
PET_ON_TICKS = 10                 # 单程 tick（一个来回 = 2×）
PET_SPAN = 15.0                   # 横向折返半宽（px）
PAT_ON_TICKS = 9
PAT_SPAN = 13.0                   # 竖向折返半高（px）
PET_SOOTHE = 0.05                 # 一次抚摸/拍拍的安抚量（双方 temper 各降）
# ── 平时随手小动作：不在社交欲望态里也能冒出来（词表同一份）──
IDLE_SOCIAL_CHECK = 90            # 每隔这么多 tick 掷一次骰
IDLE_SOCIAL_P = 0.45              # 附近有同伴时的触发概率（再乘性格）
IDLE_SOCIAL_CURSOR_P = 0.35       # 鼠标在附近停够久时对鼠标做动作的概率
IDLE_SOCIAL_CD = 220              # 一次平时小动作后的冷却（约 5.5s）
IDLE_SOCIAL_TICKS_MIN = 40        # 单次小动作时长
IDLE_SOCIAL_TICKS_MAX = 130
IDLE_SOCIAL_HOLD = 30             # 做完歇一拍再重抽
MAKEWAY_SOCIAL_P = 0.35           # 让完路回头对顶人者做个小动作的概率
CURSOR_SCOLD_PROB = 0.30          # 追鼠标时改成「指指点点」的概率（暴躁猫）
POINTED_SCOLD_PROB = 0.30         # 被指后回头指回去的概率（暴躁猫）

# 帮别的猫取食（自己饱了别人没饱）
HELPFEED_SEEK_R = 900.0
HELPFEED_TICKS = 1600
HELPFEED_DROP_R = 40.0

# 被抢东西后的扒拉指指点点
PROTEST_TICKS = 260
PROTEST_R = 240.0

# 战斗（攻击/反击）
FIGHT_R = 320.0
FIGHT_TICKS = 900
FIGHT_THROW_CD = 26
FIGHT_ARM_R = 170.0           # 手里/脚边有家伙时主动迎战的距离
FIGHT_MELEE_R = 40.0          # 够近就用身子撞/抓咬
FIGHT_ARM_KEEP = 72.0         # 持械时与威胁保持的距离（拉开了才好扔）
FIGHT_RECOVER_TICKS = 40      # 反击的迟疑

# 复活同伴：特殊表情（吐舌/舔）扒拉一会儿
REVIVE_ARM_MIN = 12.0        # 复活时每条胳膊至少要伸出这么多（手贴着身子不算按上）
REVIVE_TOUCH_R = 34.0        # 最近 chunk 对间距：挨着尸体就算摸到（原 26 一直够不着）
REVIVE_TOUCH_TICKS = 150
REVIVE_APPROACH_TICKS = 900
REVIVE_PRESS_MIN = 4         # 复活：按压次数
REVIVE_PRESS_MAX = 8
REVIVE_PRESS_TICKS = 12      # 单次下压 tick
REVIVE_RELEASE_TICKS = 8     # 单次抬手 tick
REVIVE_PRESS_DOWN = 0.6      # 下压时身体向下的力

# 恐惧：匍匐潜行躲避
CRAWL_FEAR_R = 150.0          # 蜥蜴进这个半径 → 趴下潜行
# ── 威胁圈（第41轮）：恐惧半径 ≈ 1/3 桌面宽度，随窗口缩放，不写死 ──
THREAT_WIN_FRAC = 1.0 / 3.0   # 威胁半径 = 窗口宽度 * 此值
THREAT_MIN_R = 90.0           # 小窗口时的下限，免得贴脸才怕
# 有威胁时倾向握家伙（矛/石头）：这么近的地面武器会专门跑过去捡
ARM_SEEK_R = 170.0
ARM_COOLDOWN = 420            # 两次「为了威胁去捡家伙」之间的冷却
# 有威胁时优先往高处躲（原版猫见敌常爬高）：旁边有墙/竖杆就先爬上去
FLEE_CLIMB_P = 0.7            # 逃之前先试着爬高的概率（没有可爬的东西就直接跑）
FLEE_POLE_R = 170.0           # 威胁时愿意跑过去爬的竖杆水平距离
# 害怕时逃跑优先级最高；只有勇敢的敢还手、善良的敢救人，且敌贴太近一律逃
FEAR_TOO_CLOSE_R = 76.0       # 蜥蜴贴到这个距离：不管性格，一律逃／跳过它
FEAR_BRAVE_FIGHT = 0.60       # 勇敢度超过它才敢在恐惧状态下还手
FEAR_KIND_RESCUE = 0.60       # 善良度超过它才敢在恐惧状态下先救人
APOLOGY_TICKS = 220           # 误伤同伴后抱歉：面对它匍匐
THANK_TICKS = 260             # 被救活后去拍拍恩人
# 送礼驯服（原版 FriendTracker.GiftRecieved）：拿着蝉乌贼贴近未驯服蜥蜴才可能交付
GIFT_SEEK_R = 420.0           # 端着礼物时愿意走过去的距离
GIFT_APPROACH_R = 130.0       # 拿着礼物靠近蜥蜴到这么近才算「送过去」
GIFT_START_P = 1.0 / 1600.0   # 每 tick 决定「去喂蜥蜴」的概率（极其低）
GIFT_DELIVER_DELAY = 26       # 走到嘴边后迟疑这么久才真交出去
GIFT_TRY_TICKS = 1400         # 一次送礼尝试最多磨这么久
FEAR_JUMP_MIN_GAIN = 26.0     # 反方向也挪不动 → 判定被逼到角落
FEAR_JUMP_PUSH = 1.15         # 跳过敌人时的额外水平初速
RIP_SPEAR_R = 74.0            # 够得着蜥蜴身上的矛才敢拔
RIP_SPEAR_BRAVE = 0.70        # 勇敢度超过它才敢去拔矛重投
FIGHT_UNARMED_R = 150.0       # 空手也敢主动扑上去的距离（只有勇敢的猫用）
FIGHT_UNARMED_BRAVE = 0.70    # 勇敢度超过它，空手也会主动迎战敌对威胁
CRAWL_FEAR_SPEED = 0.55       # 匍匐速度比例
CRAWL_AWAY_TICKS = 260

# 睡眠：吃饱后入睡概率从 0 缓慢升到 100（现在拉得很长，吃饱也别急着睡）
SLEEP_URGE_RATE = 1.0 / 36000.0  # 每 tick 累积（约 600s 到满）
SLEEP_URGE_DECAY = 1.0 / 12000.0 # 没吃饱时回落（也很慢）
SLEEP_CHECK_TICKS = 20           # 每隔这么久掷一次骰

# 觅食欲望：吃完一口归 0，再慢慢涨回 100 才想再去找吃的（饱了也涨，只是更慢）
FOOD_URGE_RATE      = 1.0 / 2400.0    # 没吃饱：约 60s 攒满
FOOD_URGE_RATE_FULL = 1.0 / 14400.0   # 吃饱了：约 360s（频率更低）
FOOD_SEEK_P         = 0.75            # 攒满也只是这个命中率 → 找食频率整体略降
# 玩耍式狩猎：吃饱了也会去追飞虫玩（原版蛞蝓猫的捕猎本能，非进食目的）
HUNT_PLAY_PROB      = 0.10     # 每次重算闸（每 8 tick）掷中的概率

# 徒手抓飞虫（蝙蝠/蝉乌贼）：饿了吃掉，吃饱了抓着玩会儿再放走
CATCH_SEEK_R        = 150.0    # 飞虫进这个半径才想起来抓
CATCH_REACH         = 26.0     # 手/嘴到这个距离就抓住
CATCH_UP_MAX        = 150.0    # 比嘴高太多就够不到
CATCH_JUMP_GAP      = 26.0     # 比嘴高这么多就起跳去够
CATCH_JUMP_CD       = 36       # 连跳间隔
CATCH_CHASE_TIMEOUT = 420      # 追不到就放弃
CATCH_RETRY         = 420      # 两次抓虫之间的冷却
CATCH_PLAN_R        = 420.0    # 规划可达的飞虫：从这么远也会动身走过去/跳起来抓（像抓果子）
CATCH_HUNGRY_FRAC   = 0.5      # 饱食度低于这个比例算「饿到一半以下」：主动追幼年面条蝇
CATCH_HUNGRY_R      = 300.0    # 饿着时抓幼体的认距（比平时大）
FLY_PLAY_TICKS      = 260      # 吃饱了抓着玩多久
FLY_PLAY_POKE       = 36       # 玩的时候每隔这么久拨一下（虫挣扎、自己也晃）
SPIT_UP_VY          = -2.8     # 放走时把飞虫往上送
SPIT_AWAY_VX        = 2.6
SQUID_LIFT          = 0.11     # 叼着活蝉乌贼时的额外升力（每 tick）
SQUID_LIFT_MAX      = 2.4      # 升力上限（|vy| 到这儿就不再加）
SQUID_DRAG          = 0.996    # 叼着时的水平拖拽

# 平时也爱抓地上的东西玩（矛/石头）
ITEMPLY_SEEK_R      = 170.0
PEARL_SEEK_R        = 520.0    # 溪流找珍珠的搜索半径（隔着大半个窗口也会去叼）
ITEMPLY_REACH       = 22.0
ITEMPLY_TICKS_MIN   = 150
ITEMPLY_TICKS_MAX   = 320
ITEMPLY_RETRY       = 480
ITEMPLY_PRANCE_CD   = 55       # 玩得高兴时每隔这么久蹦一下
ITEMPLY_HOP_DIST_MIN = 14.0    # 玩耍跳的横向落点距离（随机 → 方向、距离都不一样）
ITEMPLY_HOP_DIST_MAX = 46.0
ITEMPLY_HOP_AIRTIME  = 7.0     # 一次小跳的滞空 tick（横速 = 落点距离 / 滞空）
ITEMPLY_HOP_VY_K     = 0.80    # 玩耍跳比全力跳矮一点
ITEMPLY_TURN_P      = 0.35     # 坐着玩时每隔 PRANCE_CD 换个朝向的概率
ITEMPLY_FLING_P     = 0.55     # 收手时按 temper 加权，暴躁的猫把家伙甩出去
ITEMPLY_P           = 0.55     # 闲下来时每次抽查愿意去玩的概率

# 觅食时拿矛打爆米花：没矛就去地上捡一根
COB_SPEAR_FETCH_R   = 240.0

# 站杆顶/横杆面平衡
BAL_FLAIL_PROB = 0.15
BAL_FLAIL_TIP = 6.0
BAL_RECOVER = 0.83
BAL_MAX = 120.0
BAL_COUNTER_WRAP = 300.0
BAL_SWAY_X = 0.08
BAL_SWAY_Y = 0.02

# 站杆顶退出：摔落与主动下杆
TIP_FALL_DISBALANCE = 95.0
TIP_FALL_PROB = 0.04
TIP_TIRED_ENERGY = 0.15
TIP_DISMOUNT_CLIMB_PROB = 0.5
TIP_MIN_TICKS = 40

# 横杆站面拓展：停顿、吊荡、晃动
HP_PAUSE_PROB = 0.04
HP_PAUSE_MIN = 20
HP_PAUSE_MAX = 80
HP_HANG_PROB = 0.010       # 站杆面时翻到杆下悬挂（原版 StandOnBeam+下 → HangFromBeam）
HP_HANG_TICKS = 70
HP_JUMP_PROB = 0.5         # 站够久了：起跳离开（原版 StandOnBeam canJump=5）而不是直挺挺掉下去
# 交叉杆横↔竖切换 + 杆间跳跃（原版 Controls/Pole_Movement：HangFromBeam+上→ClimbOnBeam、
# ClimbOnBeam+侧→HangFromBeam、jump-pole-hopping）
CROSS_DWELL = 3                # 在交点附近待够这么多 tick 才「看见」交叉杆
CROSS_SWITCH_PROB = 0.25       # 每次经过交点换横/竖的概率（每个交点只掷一次）
CROSS_PAD = 22.0               # 胸心离交点这么近算「站在交点上」（≈爬杆 10 tick 窗口）
POLE_TIP_HOP_PROB = 0.02       # 杆顶站着时每 tick 想跳到另一根杆的概率
POLE_LEAVE_MIN_TICKS = 90      # 杆上待够这么久才会为了吃东西下杆（杆=地面）
POLE_TIP_LOITER_MAX = 300      # 杆顶最多赖这么久：到点主动跳杆/下杆（别都挤在杆头）
POLE_AIRGRAB_R = 12.0          # 空中贴杆即抓（jump-pole-hopping）
POLE_AIRGRAB_PAD = 10.0        # 杆端外这点范围仍算够得着
HPOLE_AIRGRAB_Y = 16.0         # 空中贴横杆即抓的竖直容差
HP_HOP_PROB = 0.40            # 站横杆走腻了：跳向附近另一根杆的概率
HP_HOP_MAX_DX = 70.0          # 横杆跳杆最大横距
POLE_HOP_WANT_R = 190.0       # 带目标跳杆：落点离目标超过它就不算「跳对了方向」
HPOLE_JUMP_FAR = 64.0         # 杆上带方向/距离跳起来够东西的最远横距（再远先沿杆走过去）
HPOLE_GAP_GIVEUP = 24         # 走到杆端跳不过去时，站这么久就放弃（规划是确定性的，不用等太久）
HPOLE_GAP_LAND_R = 30.0       # 跳过间隙的落点离目标多近才算「跳到位」
HP_HOP_UP_DY = 46.0           # 目标杆高于自身这么多以内才敢跳
AIR_POLE_CD = 16              # 刚离开杆后这段时间不把同一根杆又抓回来（防粘杆死循环）
POLE_HOP_PROB = 0.30           # 下杆时改为跳向另一根杆的概率
POLE_HOP_MAX_DX = 46.0        # 小跳落到“同高邻杆”的有效横距（小跳弧在同高处的水平覆盖）
POLE_HOP_VX = 4.0              # 跳向另一根杆的横冲量
POLE_HOP_VY = 4.2              # 跳向另一根杆的上抛
TIP_FALL_VX = 1.2             # 杆顶失衡滑落横速（原版失衡只是视觉量，不带发射冲量）
TIP_FALL_VY = 0.4             # 杆顶失衡滑落初速（y↓）
MOUSE_POLE_SLIP_V = 40.0    # 光标虚杆：单 tick 位移超此值算「甩」（1600px/s @40Hz）
MOUSE_POLE_SLIP_FLING = 3.0  # 被甩下来时吃到的横向反冲上限（px/tick）
HP_WOBBLE_MIN = 30.0
HP_WOBBLE_MAX = 60.0
HP_RETARGET_TICKS = 40

# 吊顶子动作随机化
CEIL_SWAY_AMP_MIN = 0.3
CEIL_SWAY_AMP_MAX = 0.8
CEIL_SWAY_HALF_MIN = 8
CEIL_SWAY_HALF_MAX = 18
CEIL_VMOVE_RANGE = 18.0

# 取物机制常量
GRAB_REACH = 18.0
REACH_GATE_K = 2.0

# 运动规划层：覆盖几何、粗线性代价、执行器失败语义
# 土狼跳（Controls「土狼跳」/「杆上土狼跳」）：原版 Player.cs:7798 StandOnBeam
# 给 canJump=5、7840 ClimbOnBeam 给 canJump=1；Player.cs:5512 每 tick 减 1，
# 于是跑出边缘/松杆后这几帧内仍然跳得起来。AI 路径原本要求「此刻正踩地」。
COYOTE_TICKS = 5                 # 接地授权（跑出边缘仍可跳）
POLE_COYOTE_TICKS = 1            # 杆上 canJump=1：松手后剩 1 tick

# 上手冷却（用户第 55 轮）：拿到东西后先揣一会儿才会「用」（吃/投/送/交易）。
# 非食物：0-3s 随机；食物：按饱食度，每格 +1.5s 上限（0 格 0-1.5s、2 格 0-3s）。
ITEM_CD_KEEP = 120               # 非食物道具：0-120 tick（3s）
ITEM_CD_FOOD = 60                # 食物：每格饱食度 +60 tick（1.5s）

PLAN_WALK_SPEED = 4.2
PLAN_TONGUE_SPEED = 3.0
PLAN_CLIMB_SPEED = 1.6
PLAN_STARTUP_TICKS = 20.0
PLAN_STAND_REACH_H = 17.0 + GRAB_REACH
PLAN_FLOOR_TOL = 12.0
PLAN_WALK_X_PAD = 30.0
PLAN_MOUTH_H = 22.0
PLAN_TONGUE_RANGE_FRAC = 1.0
PLAN_EN_RATE_LIGHT = 1.0 / 4800.0
PLAN_EN_RATE_VIGOROUS = 1.0 / 1200.0
PLAN_PROGRESS_MIN = 20.0
PLAN_REPLAN_BUDGET = 8
PLAN_COOLDOWN_TICKS = 1200
PLAN_FAILS_PER_SCHEME = 2
PLAN_SCHEMES_MAX = 2
PLAN_STEP_TIMEOUT_MIN = 240.0
PLAN_STEP_TIMEOUT_K = 3.0
PLAN_ARRIVE_EPS = 14.0
PLAN_ARRIVE_HOLD = 30
PLAN_JUMP_HOLD_GEARS = (0, 3, 6)
PLAN_JUMP_TAKEOFF_EPS = 6.0

# 舌锚吊挂驻留参数
PLAN_HANG_WALL_IDEAL = 30.0
PLAN_HANG_BULB_IDEAL = 12.0
PLAN_HANG_CEIL_IDEAL = 50.0
PLAN_HANG_SHOOT_V = 46.7
PLAN_HANG_REEL_RATE = 3.0
PLAN_HANG_ATTACH_TICKS = 40.0
PLAN_HANG_WALL_STOP_FRAC = 0.85
PLAN_HANG_MAX_RECLIMB = 3

# 机会主义舌头补救层：空中掠过果子时抢射舌收回
PLAN_SNATCH_MAX_TRIES = 2
PLAN_SNATCH_TIMEOUT = 120

# 挡路让位：被顶约 1s 顺向让开
SHOVE_CONTACT_DIST = 24.0
SHOVE_YIELD_TICKS  = 40
SHOVE_CLEAR_PAD    = 28.0
MAKEWAY_TIMEOUT    = 200

# 顶人方兜底跳越
BLOCKED_JUMP_TICKS = 100
JUMP_OVER_HOLD     = 6
JUMP_OVER_COOLDOWN = 80
BLOCK_GRACE_TICKS  = 30        # 短暂丢失阻挡（跳起的那几帧/擦身）不清零，超过这么久才算真的不再被挡

# 挡路升级：跳不过去 → 上手推对方，再回头指指点点
BLOCKED_PUSH_TICKS  = 60        # 跳越后又一直被挡满这么久 → 上手推
BLOCKED_PUSH_IMPULSE = 1.8      # 推对方的水平冲量
BLOCKED_PUSH_RECOIL  = 0.4      # 自己的反冲
BLOCKED_PUSH_POSE    = 14       # 推人姿势时长
HPOLE_GOAL_EPS = 10.0          # 上横杆后离目标 x 多近算走到位
HPOLE_GOAL_R   = 84.0          # 横杆线上离食物多近算「够得着」（上杆去拿）
HPOLE_GOAL_TIGHT_EPS = 2.0     # 杆上伸手够东西时用的收紧停位（10 的余量够不到目标）
HPOLE_GOAL_TIMEOUT   = 150     # 杆上够不到的目标最多再等这么久就放弃（别原地发呆/掉下杆）
# 横杆 → 窗口地面（别人窗口顶边＝单向平台）：杆面够不到、落到那块面上才够得到就下杆
HPOLE_HAND_DOWN      = 12.0    # 贴杆伸手能探到杆面之下多少（实测悬挂偏移 c0.y-p.ay=-11,
                               #   GRAB_REACH=18 → 手最远探到杆面下 ~7px；取 12 留点余量）
HPOLE_STEP_MIN_DROP  = 14.0    # 目标的面比杆面低这么多才算「跳下去」够得到
HPOLE_STEP_SURF_EPS  = 18.0    # 目标离面这么近才认为它是摆在那块面上的
HPOLE_STEP_CD        = 200     # 下杆捡东西的冷却（防上上下下抽风）
HPOLE_STEP_STANDOFF  = 20.0    # 落点离目标留一步：正对着目标落下去会把果子顺着单向平台压穿

BLOCKED_POINT_PROB  = 0.55      # 推完回头指指点点的概率（再乘性格系数）
BLOCKED_POINT_FIRST_MAX = 0.45  # 暴躁/爱指的猫被挡时「先指指点点不跳」的最大概率
BLOCKED_POINT_AFTER_JUMP = 0.16 # 跳过去之后回头指指点点的小概率
POINT_TEMPER_LO = 0.35          # 性格系数：最温顺时的乘子
POINT_TEMPER_HI = 1.25          # 性格系数：最暴躁时的乘子
SCOLD_TICKS         = 240       # 指指点点状态时长
SCOLD_R             = 240.0     # 对方跑这么远就不指了
SCOLD_CD            = 420       # 下一次挡路抗议的冷却

# 杆上被同伴挡路：停在中间扒拉几下（最后有概率改成指指点点）
POLE_BLOCK_DIST       = 26.0
POLE_NUDGE_TICKS      = 56
POLE_NUDGE_POKE       = 12      # 扒拉节奏（每这么多个 tick 扒一下）
POLE_NUDGE_POINT_TAIL = 30      # 最后这么多 tick 改成指指点点
POLE_NUDGE_POINT_PROB = 0.5
POLE_NUDGE_CD         = 150     # 扒拉完的冷却

# 杆上冲突按性格分流（原版：好脾气的猫先让路，坏脾气的死磕到底）
POLE_SOFT_EPS         = 0.18    # |善良-暴躁| 在此以内算中性
POLE_CONTEST_DIST     = 42.0    # 算「同一场挤位赛」的沿杆距离
POLE_CONTEST_TICKS    = 70      # 坏性格死磕这么久才分胜负
POLE_WAIT_TICKS       = 110     # 中性等这么久还没人让就随机让一只先走
POLE_GIVE_VX          = 1.4     # 让路：松手离杆的横冲量
POLE_GIVE_VY          = 1.0     # 让路：下坠初速
POLE_KNOCK_VX         = 2.6     # 被挤掉的横冲量
POLE_KNOCK_VY         = 1.4     # 被挤掉的下坠初速

# 指指点点手势：伸出 → 收回，重复 1~5 次
POINT_REPS_MIN = 1
POINT_REPS_MAX = 5
POINT_ON_TICKS  = 10
POINT_OFF_TICKS = 8

# 被鼠标抓住时自己够杆/够食物
DRAG_REACH_R  = 34.0            # 手够得着就抓（原版手碰到就抓）
DRAG_REACH_CD = 24
DRAG_POLE_R   = 46.0            # 贴到这么近算抱上杆了

# 空中投矛（wiki Throwing midair：在空中也能把矛/石头掷出去）
AIR_THROW_R  = 190.0            # 空中锁定目标半径
AIR_THROW_CD = 55               # 两次空中投掷的最小间隔 tick

# ── 社交：摇醒睡着的同伴（社交欲望满、对方在睡才会做）──
WAKE_P              = 0.55      # 基础概率，再 × (0.2 + 1.6 × 性格 wake_like)
WAKE_SHAKE_REPS_MIN = 2
WAKE_SHAKE_REPS_MAX = 4
WAKE_SHAKE_TICKS    = 5         # 每一下摇晃的 tick
WAKE_SHAKE_SPAN     = 4.0       # 摇晃幅度（手左右摆）
WAKE_SHAKE_POKE     = 8         # 每这么多 tick 顺手扒拉一下

# ── 被吓一跳（工匠爆炸：先炸醒睡着的，再按性格指指点点）──
STARTLE_POINT_BASE  = 0.45

# ── 用矛意愿门：低于此值的猫不肯为了开爆米花去捡矛（圣徒）──
SPEAR_WILLING_MIN   = 0.4

# ── 圣徒吃荤：原版 Saint 碰到活体/电击就 SaintStagger（Player.cs:3581 = Stun(t/5)）──
#    Cicada.cs:871 触发电蝉时用 220 → 44 tick；这里当成「素食猫吃下荤食」的眩晕时长。
MEAT_SICK_STUN      = 44

# ── 打高处的目标：平地起跳抬不起掷矛线时，爬竖杆到目标同高再出手 ──
POLE_THROW_CLIMB_DY = 40.0      # 目标高出这么多（≈一次跳跃的高度）→ 改爬杆
T_POLE_THROW_RETRY  = 300       # 爬杆也没够到目标：这么久之内不再试

# ── 喜欢珍珠的猫（溪流）：闲着会把地上的珍珠叼起来拿着 ──
PEARL_HOARD_P       = 0.25      # 每次重算的概率
PEARL_HOARD_CD      = 900       # 放下之后这么久才会再去叼
PEARL_LOOK_TICKS    = 90        # 拿到珍珠后「端在手里看一眼」的时长
PEARL_CARRY_TICKS   = 240       # 把玩珍珠多久才放下（放下后进 PEARL_HOARD_CD 冷却，不会原地反复叼）

# ── 圣徒舌头黏住生物：一路使劲拽，快速掉体力直到松舌 ──
SAINT_LICK_HOLD_DRAIN = 1.0 / 200.0   # 每 tick；满体力约 200 tick（≈3.3 s）拉空

# ── 兴趣目标抖动（同屏多只猫：别都盯上同一个最近目标）──
INTEREST_JITTER   = 0.40        # 每只猫对每件目标的个体偏好系数 1±这个值（稳定，不逐 tick 乱跳）
INTEREST_TAKEN_MUL = 1.55       # 已经有同伴把它当目标 → 打分乘这个数（让位）
