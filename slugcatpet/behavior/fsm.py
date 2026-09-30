"""行为状态机 BehaviorFSM。"""
from __future__ import annotations
import math
import os
import random

from ..behavior import tuning
from ..core.creature import (RUN_UPPER, ZEROG_GRAB_DIST, THROW_ORIGIN_DX, THROW_ORIGIN_DY,
                             WALK_STOP_EPS, _closest_on_segment)
from ..planning import (GIVEUP, HOLDING, MODE_STAY, Goal, PlanExecutor, Planner,
                        obj_goal)
from ..planning.fly_reach import in_reach
from .blocking import (blocks_path, yield_target_x, on_same_pole,
                        pole_in_the_way, pole_push_role)
from . import social
from .board import board_for
from . import events as EV
from .relationship import WITNESS_SCALE, relations_for
from .social_response import (SocialContext, target_of,
                              choose as _choose_response)
from .anim_intent import PRIO_AMBIENT, PRIO_FORCE, PRIO_URGENT, point_of
from .desire import build_arbiter, MoodContext
from .action import (ActionArbiter, ActionContext, ActionSpec,
                     build_arbiter as build_action_arbiter,
                     BAND_EMERGENCY, BAND_NEED, BAND_PERSONALITY, BAND_PREEMPT,
                     TAG_EMERGENCY, TAG_FOOD, TAG_INTERACT, TAG_SOCIAL,
                     TAG_PERSONALITY, TAG_NAV, TAG_CHARACTER)
from .interest import goal_key as _interest_key
from .fetch import (fetch_ready, ChewCycle, BITE_HEAD_NUDGE, EAT_APPROACH,
                    EAT_CHOMP_POSE, EAT_HOLD_POSE, EAT_INTERVAL)
from ..cats.personality import (DIET_CARNIVORE, DIET_VEGETARIAN, DIET_SPECIAL,
                                DIET_GOURMAND)
from ..cats import diet as _diet
from .objectlooker import ObjectLooker
from ..control.mouse import GrabController
from ..cats.saint.cursorlick import (BAND_LO as LICK_BAND_LO, BAND_HI as LICK_BAND_HI,
                                     DWELL_TICKS as LICK_DWELL, DWELL_TOL as LICK_DWELL_TOL,
                                     GATE_FRAC as LICK_GATE_FRAC)
from ..world import weaponphys
from ..world.pole import VERTICAL, cross_partner
from ..world.enums import ItemState
from ..core import edges as edgeqm
from ..core.units import clampf

class _ShotProbe:
    """预演弹道时用的假矛：只带命中判定要用的字段。"""
    __slots__ = ("x", "y", "last_x", "last_y", "rad", "_seg_x", "_seg_y")

    def __init__(self, rad: float):
        self.x = self.y = self.last_x = self.last_y = 0.0
        self._seg_x = self._seg_y = 0.0
        self.rad = float(rad)


# 计时常量（tick）
T_POINT_WAKE = 160
T_POSTTHROW_WANDER = 200
T_POSTTHROW_STAND = 400
ANGER_TOTAL = T_POSTTHROW_WANDER + T_POSTTHROW_STAND
T_FETCH_COOLDOWN = 200
T_FETCH_CHECK = 8   # 取果闸重算间隔
HUNT_CD = 620       # 一次捕猎后的冷却（tick）
CORPSE_HAUL_SEEK_R = 340.0   # 多远之内会主动去拖无用尸体（死蜥蜴…）
CORPSE_HAUL_REACH = 30.0     # 离尸体这么近＝上手抓住
CORPSE_HAUL_MAX_DY = 70.0    # 尸体高出自己这么多（躺在别的窗口顶边上）＝够不到
CORPSE_HAUL_ARRIVE = 26.0    # 猫离屏幕边这么近＝把尸体甩出去
CORPSE_HAUL_FLING = 14.0     # 甩出去的初速（够飞出窗口被清掉）
CORPSE_HAUL_TICKS = 3600     # 单趟最长 tick（约 90s；绿蜥等重尸按原版质量比拖得很慢，超时松爪）
T_CORPSE_HAUL_RETRY = 600    # 一趟之后多久不再惦记（约 15s）
CORPSE_HAUL_P = 0.5          # 闲下来时每次检查起意的概率
LICK_PLAY_P = 0.125          # 圣徒：射程内有生物时起意伸舌逗它（用户口径：减少到 1/8）
LICK_PLAY_CD = 240           # 一次逗弄后的冷却（约 6s）
LICK_REACH_FRAC = 0.85       # 舌头总长的这个比例之内才够得着
T_HPOLE_TIMEOUT = 1600
HPOLE_MAX_CLIMBS = 3
WAKE_STABILIZE_TICKS = 30

# ── 六类欲望（进食/恐惧/战斗/玩耍/睡眠/社交）计时常量 ──
T_SOCIAL_RETRY = 280      # 社交冷却
T_HELP_RETRY = 480        # 帮取食冷却
T_FIGHT_RETRY = 380       # 战斗冷却
T_COB_RETRY = 220         # 爆米花放弃后的重试冷却
COB_STAND_DX = 60.0       # 打爆米花时站到离豆荚多远的水平距离上掷矛
COB_HIT_TOL = 15.0        # 这一掷能不能命中豆荚的竖直容差（矛 rad5+豆荚 rad8+玩家 pad5−3）
COB_THROW_CD = 24         # 两矛之间的最短间隔（等矛飞出去、看豆荚开没开）
COB_TRY_MAX = 5           # 一次啃食预算里最多掷几次矛
COB_JUMP_APEX = 46.0      # 站立起跳能把掷矛线抬高的量（实测 49.5，留点余量）
COB_STAND_EPS = 4.0       # 站位的收尾公差（WALK_STOP_EPS=2，留点姿态余量）
COB_SIDE_EPS = 6.0        # 猫离豆荚中点多近算「站在正下方」（方向会乱翻，得先退开）
COB_STAND_STEPS = (60.0, 46.0, 34.0, 24.0, 16.0)
                          # 掷矛位的候选距离（从远到近）：站远处掷不中就往豆荚挪一档
T_CRAWL_RETRY = 300       # 匍匐躲避冷却
T_PROTEST_RETRY = 900     # 抗议被抢东西的冷却
T_REVIVE_RETRY = 200      # 复活磨到超时才放弃：长冷却
T_REVIVE_RETRY_SOON = 40  # 被威胁打断 / 刚救完：短冷却，马上能再上手
# ── 躲在「持有矛/石头的同伴」背后（有威胁、自己空手）──
T_COVER_RETRY = 240       # 躲完让位的冷却
COVER_TICKS = 300         # 单次躲在同伴背后的时长上限
COVER_SEEK_R = 260.0      # 同伴离这么近才值得过去躲
COVER_BACK_OFF = 26.0     # 站在同伴背对威胁那一侧的偏移
COVER_MIN_GAP = 70.0      # 躲过去的落点离威胁至少这么远，太近就宁可跑开
SPEAR_AI_SPEED = 34.0     # 投矛初速（同 huntfly.SPEED_SPEAR）
STONE_AI_SPEED = 26.0     # 投石初速（同 huntfly.SPEED_STONE）
# 被咬/被矛的致死判定：原版 Player.DeathByBiteMultiplier（故事模式 0.7 + 难度/5）
DEATH_BY_BITE_MULT = 0.75
MONK_DEATH_BY_BITE_MULT = 0.0     # 僧侣永不被咬死
SAINT_DEATH_BY_BITE_MULT = 100.0  # 圣徒一咬必死
# 原版 Slugcat CreatureTemplate：baseDamageResistance=1 / baseStunResistance=1
# / instantDeathDamageLimit=1（矛 1.0 伤害 ⇒ 1.0 ≥ 1 即致死）
SLUG_INSTANT_DEATH_LIMIT = 1.0
SLUG_DAMAGE_RESISTANCE = 1.0
SLUG_STUN_RESISTANCE = 1.0
# 强制欲望只从这些「没正事」的态起手
_WANTS_FROM = frozenset(("IdleStand", "PostThrowWander", "PostThrowStand", "MakeWay"))
# 这些态靠 _wants_break 收尾（释放墙/天花/手持、恢复行走边界）；
# 必须保证「离开该态」时一定跑到一次，否则 walk_min/walk_max 会永久留 None
_WANTS_STATES = frozenset(("CeilingHang", "ChaseCursor", "Socialize",
                           "HelpFeed", "FightThreat", "CrawlAway", "EatCob",
                           "ScoldBlocker", "CatchFly", "ItemPlay", "CoverAlly"))

WALL_MARGIN = 40.0

# 投掷视线：自己与目标之间站着别的蛞蝓猫就不出手（用户规格）
THROW_BLOCK_R = 14.0            # 同伴躯干算多粗（挡枪判定半径）
THROW_BLOCK_LEN = 320.0         # 没给目标时的水平射线长度

# 零重力漂浮 idle
ZEROG_ARRIVE_R = 30.0
ZEROG_KICK_FAR = 60.0
ZEROG_TWITCH_PROB = 0.02
ZEROG_CURSOR_FRAC = 0.6
ZEROG_LICK_PROB = 0.012
ZEROG_CHASE_LICK_PROB = 0.03
# 抓杆：赖杆来回滑一会再松
ZEROG_GRAB_ALIGN = 12.0
ZEROG_POLE_COOLDOWN = 40
ZEROG_POLE_SEEK_R = 220.0
ZEROG_POLE_SEEK_PROB = 0.5
ZEROG_POLE_PLAY_TICKS = 120
ZEROG_SLIDE_PERIOD = 30
# 零重力下保留原态，其余打断转漂浮 idle
_ZEROG_KEEP = frozenset(("IdleStand", "Dragged", "Dead", "Stunned", "Ascension", "Swimming",
                         "ShelterSleep"))
# 浸水下保留态，其余打断转 Swimming
_SWIM_KEEP = frozenset(("Swimming", "Ascension", "Dragged", "Dead", "Stunned",
                        "TongueClimb", "CeilingHang", "ShelterSleep"))

ARM_REACH_NEAR = 24.0
ARM_REACH_FAR = 48.0
THROW_JUMP_DY = 12.0      # 目标高出这么多 → 先起跳再水平投（原版只能横着发射）
JUMPCUR_DY = 52.0         # 追鼠标：高度差在这以内才值得跳着够
JUMPCUR_DY_SLACK = 1.35     # 「差不多够得到」：稍微高一点也跳一下试试（用户规格）
JUMPCUR_R = 130.0         # 追鼠标：水平距离上限
JUMPCUR_CD = 24
JUMPCUR_P = 0.6
HPOLE_NEAR_Y = 20.0
HPOLE_REACH_FRAC = 0.85
HPOLE_GRAB_REACH = 0.60

# 精力 energy（tick）：原仓库的口径 —— 只有剧烈/轻度「玩法态」耗体力，
# 其它行动不额外扣，也不吃饱食度（体力经济已移除）。
EN_DRAIN_VIGOROUS = 1.0 / 1200.0
EN_DRAIN_LIGHT = 1.0 / 4800.0
EN_REC_REST = 1.0 / 800.0
EN_REC_IDLE = 1.0 / 1600.0

_STATE_TO_MOOD = {"PoleClimb": "pole_climb",
                  "SeekHPole": "hpole", "HPole": "hpole",
                  "CeilingHang": "ceiling_hang",
                  "ChaseCursor": "play_cursor", "Socialize": "socialize"}
# 疲劳强制休息不打断的态
_EXHAUST_BLOCKED = frozenset(("Dragged", "Dead", "Stunned", "Ascension",
                              "WakeSequence", "LieDown", "Sleep", "SeekWarmth",
                              "Swimming", "StormSeekShelter", "ShelterSleep"))
# 趋暖强制中断不打断的态
_COLD_BLOCKED = frozenset(("Dragged", "Dead", "Stunned", "Ascension",
                           "WakeSequence", "SeekWarmth", "Swimming",
                           "StormSeekShelter", "ShelterSleep"))
# 避水强制中断不打断的态
_WATER_BLOCKED = frozenset(("RelocateToWall", "TongueClimb", "CeilingHang", "Swimming",
                            "Dragged", "Dead", "Stunned", "Ascension", "ShelterSleep"))
# 暴雨集合 / 庇护所睡眠：这两态里不许被别的动作拉走（含自身，防重复入态）
_STORM_BLOCKED = frozenset(("Dragged", "Dead", "Ascension", "Stunned", "Swimming",
                            "TongueClimb", "CeilingHang",
                            "StormSeekShelter", "ShelterSleep"))
# 取果触发不打断的态
_FETCH_NEVER = frozenset(("FetchFruit", "Ascension", "Dragged", "Dead", "WakeSequence",
                          "Stunned", "SeekWarmth", "Swimming", "StormSeekShelter",
                          "LieDown", "Sleep", "ShelterSleep",   # 趴/睡时别把猫叫起来去取果
                          "PyroMaul", "RivSnatch", "CatchFly", "ItemPlay",
                          # 面敌做出的决定是锁：迎战 / 掩护同伴 / 逃跑这三个态里
                          # 不许取食欲望把人拆走去吃果子（旧版漏了这三项，于是
                          # 「刚决定迎战 → 下一拍又被叫去取果」，战斗态形同虚设）
                          "FightThreat", "CoverAlly", "FleeLizard"))
# play 态接管取果需果在舌头射程内
_FETCH_PLAY = frozenset(("PoleClimb", "HPole", "CeilingHang"))


_EN_VIGOROUS = frozenset(("TongueClimb", "PoleClimb", "CeilingHang", "Swimming",
                          "PyroRomp", "RivFlip", "PyroMaul", "RivSnatch"))
_EN_LIGHT = frozenset(("RelocateToWall", "PostThrowWander", "FetchFruit", "AngryStone",
                       "WakeSequence", "CursorLick", "SeekWarmth", "SeekHPole", "MakeWay",
                       "FleeLizard", "CatchFly", "ItemPlay", "CoverAlly",
                       "StormSeekShelter"))
_EN_REST = frozenset(("LieDown", "Sleep", "ShelterSleep"))
_EN_IDLE = frozenset(("IdleStand", "PostThrowStand"))

# 被顶让路仅从这些无更高目的态触发
_MAKEWAY_FROM = frozenset(("IdleStand", "PostThrowWander", "PostThrowStand"))
# 平时随手社交动作只从这些「没正事」的态起手（做完不切态，歇一拍再重抽）
_IDLE_SOCIAL_FROM = frozenset(("IdleStand",))

# ── 躲蜥蜴（原版 Player 见威胁逃逸）──
FLEE_R = 110.0            # 蜥蜴进入此水平距离 → 掉头跑
FLEE_SAFE_R = 150.0       # 拉开到此距离 → 安全，收工
FLEE_GAP = 90.0           # 逃跑目标：离蜥蜴这么远
FLEE_MAX_TICKS = 200      # 单次逃跑上限
FLEE_COOLDOWN = 300       # 两次躲之间至少隔这么久（进场即计时）
# 只从「没事干」的态里起跑：取果/送礼这类有目的的态不打断
_FLEE_FROM = frozenset(("IdleStand", "PostThrowWander", "PostThrowStand", "MakeWay"))

# 面敌逻辑（合并旧「威胁」+「害怕」）：恐慌区（FEAR_TOO_CLOSE_R 内）能打断的态。
# 不含 Dead/Stunned/Dragged/Ascension/Swimming/TongueClimb/HPole 等不可打断的。
_FACE_PANIC_FROM = frozenset((
    "IdleStand", "PostThrowWander", "PostThrowStand", "MakeWay", "ChaseCursor",
    "Socialize", "FetchFruit", "CatchFly", "ItemPlay", "HelpFeed", "PoleClimb",
    "ScoldBlocker", "LieDown"))
CRAWL_AWAY_STEP = 60.0     # 匍匐潜行每 tick 朝反方向重取的「一步」长度
CRAWL_CORNER_EPS = 1.0     # 夹进可走范围后离原地的余量 ≤ 此值 = 贴边（不再推）
REVIVE_SAFE_PAD = 1.6      # 倒地同伴离威胁小于「我离威胁的距离×此值」＝在刀口上，不去



def _energy_delta(state: str, drain_fac: float = 1.0) -> float:
    """本态本 tick 的体力变化：恢复不受体力影响，消耗按 drain_fac 缩放。"""
    if state in _EN_REST:
        return EN_REC_REST
    if state in _EN_IDLE:
        return EN_REC_IDLE
    if state in _EN_VIGOROUS:
        return -EN_DRAIN_VIGOROUS * drain_fac
    if state in _EN_LIGHT:
        return -EN_DRAIN_LIGHT * drain_fac
    return 0.0


def _spear_takeable(sp) -> bool:
    """插住/插在其他生物身上的矛拔不动；插在爆米花上的能拔下来。"""
    host = sp.stuck_to
    if host is None:
        return True
    return hasattr(host[0], "can_feed")


class _MoodWeight:
    """mood 候选项的基础权重（不含噪声）：与 MoodArbiter 的 weight 公式逐项一致。"""

    __slots__ = ("cand",)

    def __init__(self, cand):
        self.cand = cand

    def __call__(self, ctx):
        c = self.cand
        return (c.base * c.energy_factor(ctx.body.energy)
                * c.temper_factor(ctx.body.temper)
                * c.cold_factor(ctx.body.cold))


def _lerpmap(x, lo, hi, flo, fhi):
    if hi == lo:
        return flo
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return flo + (fhi - flo) * t


def pick_open_x(fsm, margin=120.0):
    """走带内离两缘留 margin 余量的随机开阔点 x。"""
    b = fsm.body
    lo = 0.0 if b.walk_min is None else b.walk_min
    hi = fsm.WL if b.walk_max is None else b.walk_max
    if hi - lo > margin * 2.0:
        lo, hi = lo + margin, hi - margin
    return fsm.rng.uniform(lo, hi)


def pick_social_wander_x(lo, hi, self_x, others_x, sociability, rng, sigma, samples,
                         lo_thresh, hi_thresh, move_w, cross_w, stay_gain, stay_span):
    """按 sociability 选走位 x：密度 + 距离 + 穿越代价最小化。"""
    if not others_x or lo_thresh <= sociability <= hi_thresh:
        return rng.uniform(lo, hi)
    span = max(1.0, hi - lo)
    inv = -1.0 / (2.0 * sigma * sigma)
    avoid = sociability < lo_thresh
    sign = 1.0 if avoid else -1.0
    def density(x):
        return sum(math.exp(inv * (x - ox) ** 2) for ox in others_x)
    def crosses(x):
        a, b = (self_x, x) if self_x <= x else (x, self_x)
        return any(a < ox < b for ox in others_x)
    def cost(x):
        c = sign * density(x) + move_w * abs(x - self_x) / span
        if avoid and crosses(x):
            c += cross_w
        return c
    n = max(1, samples)
    step = span / n
    best = min((lo + step * (i + rng.random()) for i in range(n)), key=cost)
    if cost(best) >= sign * density(self_x) - stay_gain:
        return min(max(self_x + rng.uniform(-stay_span, stay_span), lo), hi)
    return best


class BehaviorFSM:
    def __init__(self, window, seed: int | None = None):
        self.win = window
        # 个体性格：PetUnit 每只猫一份「原型 + 个体偏移」；没有就回落种族原型
        self.pers = getattr(window, "personality", None) or window.cat.personality
        self._drain_fac = 1.0 / max(0.01, self.pers.stamina)
        self._look_fac = max(0.0, 1.0 + tuning.PERS_ACT_SPREAD * (self.pers.activity - 0.5))
        self.body = window.body
        self.gfx = window.gfx
        self.WL = window._WL
        self.HL = window._HL
        # seed=None 时从全局 random 取种：debug 模式下先 random.seed(N) ⇒ 整套行为可复现
        self.rng = random.Random(seed if seed is not None else random.randrange(1 << 30))
        # 尾针拔出特效自己的随机流：UnityEngine.Random 在那边是独立的，
        # 混进 self.rng 会把行为和测试序列整体错位。
        self._needle_rng = random.Random(
            (seed if seed is not None else 0) * 977 + 41)
        self.grab = GrabController(self.body, self.gfx)
        self.mood = build_arbiter(self.rng, self.pers)
        self.looker = ObjectLooker(self.rng, self._look_fac)

        self.state = "IdleStand"
        self.timer = 0
        self.phase = 0
        self.point_side = 0
        self._point_stopped = False
        self.protest_left = 0
        self.cursor = None
        self._settle = 0
        self._idle_hold = 0
        self._zerog_target = None
        self._swim_goal = None
        self._chew = ChewCycle()          # 与普通重力路径共用同一咀嚼周期
        self._water_escape_cd = 0
        # 水性 zeal → 漂游潜深/冲刺距离插值
        _z = max(0.0, min(1.0, (self.pers.swim_zeal - 0.5) * 2.0))
        self._swim_depth_max = _lerpmap(_z, 0.0, 1.0, tuning.SWIM_DRIFT_DEPTH_MAX,
                                        tuning.SWIM_DRIFT_DEEP_MAX)
        self.body.swim_boost_dist = _lerpmap(_z, 0.0, 1.0, tuning.SWIM_BOOST_DIST,
                                             tuning.SWIM_BOOST_DIST_ZEAL)
        self._zerog_pole_cd = 0
        self._zerog_pole_play = 0
        self._zerog_slide_sign = 1.0
        self._prev_zerog = False
        self._zerog_entered = False
        self._wake_then = None
        self._wake_stable = 0
        self._hibernating = False
        self._exhausted = False
        self._revive_timer = 0
        self._reincarnate = False
        self._flower_planted = False     # 这具身体是否已排过「死后原地长业力花」
        self._warm_exec = None
        self._warm_goal_obj = None

        self.karma = None
        self.climb = None
        self.poleclimb = None
        self.hpole = None
        self._hpole_pole = None
        self._hpole_start = None
        self._hpole_start_x = None
        self._poleclimb_pole = None
        self._poleclimb_start = None
        self._hp = None
        self._hp_phase = None
        self.fetch = None
        self.planner = Planner(window)
        self._fetch_cooldown = 0
        # 取果闸相位错峰：_fetch_check 每 tick 加一，初值按猫的序号错开 ⇒ 十只猫
        # 的「什么时候重新挑目标」天然分散，不再同一个心跳一起重算、一起扑同一个
        # 目标。用序号推导（不抽自己的 rng），行为序列对同一种子仍完全可复现。
        self._fetch_check = (int(getattr(window, "index", 0) or 0) * 3) % T_FETCH_CHECK
        self._shoved_ticks = 0
        self._makeway_of = None
        self._flee_from = None
        self._flee_cd = 0
        # 六类欲望：匍匐/吊顶/玩耍/社交/帮取食/抗议/战斗/复活/睡眠
        self._ceil_left = 0
        self._ceil_dir = 1
        self._ceil_walk_t = 0
        self._ceil_placed = False
        self._struggle_left = 0
        self._cob = None              # 正在啃/要打的爆米花豆荚
        self._cob_climber = None      # 为够到高处的豆荚而爬的那根**真竖杆**
        self._cob_climb_thrown = False
        self._cob_eat_t = 0           # 本口剩余 tick（原版 eatExternalFoodSourceCounter）
        self._cob_cd = 0              # 两口之间的冷却（原版 dontEatExternalFoodSource…）
        self._cob_left = 0            # 啃食态超时
        self._cob_check = 0
        self._cob_seek_cd = 0
        self._cob_try = 0             # 这一轮打豆荚已经掷了几次矛
        self._cob_throw_cd = 0
        self._cob_off_i = 0           # 掷矛位候选（COB_STAND_STEPS）的下标
        self._play_left = 0
        self._social_left = 0
        self._social_kind = "pet"
        self._social_target = None
        self._social_touch = 0
        self._social_urge = 0.0
        self._social_gesture = None
        self._social_press_seen = 0
        self._social_press_per = 1
        self._social_press_down = False   # 本 tick 正在往下按（手也往目标里压）
        self._revive_gave_up = False      # 复活是「磨到超时放弃」还是被打断
        self._rescue_exec = None          # 救援赶路的执行器（复用觅食那套寻路）
        self._cursor_exec = None           # 追鼠标的统一寻路执行器
        self._cursor_goal = None           # 动态鼠标 Goal（位置每 tick 更新）
        self._cursor_plan_pos = None       # 上次规划时的鼠标位置
        self._cursor_replan_cd = 0
        self._cursor_jump_cd = 0
        self._apology_target = None      # 误伤同伴 → 抱歉：面对它匍匐
        self._apology_t = 0
        self._thank_target = None        # 被同伴救活 → 去拍拍恩人
        self._thank_t = 0
        self._reviver = None             # 是谁把自己救活的
        self._gift_left = 0              # 送礼驯服的剩余尝试窗口
        self._gift_wait = 0              # 走到蜥蜴嘴边后的迟疑计时
        self._help_left = 0
        self._help_target = None
        self._protest_left = 0
        self._protest_target = None
        self._fight_left = 0
        self._fight_target = None
        self._fight_climber = None       # 为够到高处的目标而爬的那根竖杆
        self._fight_climb_thrown = False # 本次爬杆已经出手过（爬完就收工）
        self._pole_throw_cd = 0          # 爬杆够不着目标的重试冷却
        self._crawl_left = 0
        self._crawl_from = None
        self._nuzzle_t = 0
        self._fetch_watch = None
        self._sleep_urge = 0.0
        self._sleep_check = 0
        self._sleep_left = tuning.HIBERNATE_TICKS   # 本次睡眠时长（入睡时掷）
        self._social_cd = 0
        self._help_cd = 0
        self._fight_cd = 0
        self._arm_cd = 0                 # 「为了威胁去捡家伙」的冷却
        self._cover_ally = None          # 躲到谁背后（有威胁、自己空手）
        self._cover_cd = 0
        self._pincur_cd = 0             # 猎手把矛钉在鼠标上的冷却
        self._pincur_urge = 0.0         # 猎手对光标的兴趣累积（满 1 才出手）
        self._air_throw_cd = 0
        self._crawl_cd = 0
        self._protest_cd = 0
        self._revive_cd = 0
        # 动态关系表 + 事件游标：关系由事件驱动、每 tick 衰减（behavior/relationship.py）
        self._rel = relations_for(self.win)
        self._ev_seen = -1                # 事件总线游标（事件序号，不是 tick）
        self._protest_kind = "protest"
        self._last_response = ("", 0.0)     # 最近一次社会反应（状态面板 / 测试用）
        self._saved_walk = None
        self._fight_throw_t = 0
        self._throw_jumped = False           # 上一次 _throw_weapon_at 只是起跳没出手
        self._blocked_ticks = 0
        self._block_grace = 0
        self._jump_over_cd = 0
        # 被逼退记账（面敌时的「退无可退」判据）：连续退了多远／多久、卡住多久
        self._press_x = None
        self._press_back = 0.0
        self._press_t = 0
        self._stuck_t = 0
        # 挡路升级：跳过 → 推人 → 回头指指点点；杆上被挡 → 停住扒拉
        self._jump_tries = 0
        self._push_left = 0
        self._push_x = None
        self._push_side = "r"
        self._blocker_target = None
        self._last_blocker = None
        self._hp_goal_x = None        # 上横杆去够的东西的 x（横杆可达食物）
        self._hp_goal_obj = None
        self._hp_goal_t = 0           # 杆上够这个目标已经等了多久（超时放弃）
        self._hp_step_cd = 0          # 横杆下杆捡东西的冷却
        self._hp_step_obj = None     # 正在为它沿杆挪到下杆位置的窗口顶边目标
        self._hp_jump_goal = None     # 杆上起跳后空中要摘的东西      # 上次挡我路的人（跳过去后可能回头指他）
        self._scold_left = 0
        self._scold_cd = 0
        self._pole_blocker = None
        self._pole_nudge = 0
        self._pole_nudge_t = 0
        self._pole_nudge_pin = None
        self._pole_nudge_cd = 0
        self._pole_nudge_point = False
        self._pole_contest_t = 0        # 死磕/等待累计 tick（挤位赛计时）
        self._pole_nudge_role = 0       # 本次冲突里的角色（进入时定下，钉住期间冻结）
        self._pole_scold_on_land = False   # 被挤掉后落地要找挤赢的算账
        # 指指点点手势（伸出→收回→再伸出，重复 3~5 下）
        self._point = None
        self._point_tgt = None
        self._point_mode = "obj"
        self._point_enforce = False
        # 被鼠标抓住时自己够杆/够食物
        self._drag_cd = 0
        self._drag_pole = None
        # 被鼠标抓着剧烈摇晃 → 抖掉手里的东西
        self._shake_flips = 0
        self._shake_dir = 0
        self._shake_hold = 0
        self._shake_cd = 0
        # 统一社交动作 API（词表 behavior/social.py）：起手 / 推进 / 收势
        self._act_key = None
        self._act_tgt = None
        self._act_owner = None        # 起手这个动作时所在的态（换态即收势）
        self._act_mode = "obj"
        self._act_enforce = False
        self._act_left = 0
        self._act_idle = False        # 平时随手做的小动作（只在家闲态里做）
        self._act_cd = 0
        self._act_check = 0
        self.stonethrow = None
        self.flyhunt = None
        self._hunt_cd = 0
        self.flycatch = None            # 徒手抓飞虫控制器
        self._catch_cd = 0
        self._air_pole_cd = 0           # 刚离开杆：这段时间不把同一根杆又抓回来
        self._left_pole = None
        self._air_pole_target = None    # 空中想抓住的那根杆（带方向跳杆时记下）
        self._itemplay_cd = 0
        self._back_spear_cd = 0
        self._tail_needle_cd = 0      # 矛大师：尾巴长针的间隔
        # 饕餮：体重坠落攻击（cats/gourmand_slam.py 的独占记账字段）
        self._slam_cd = 0             # 砸击冷却
        self._slam_target = None      # 本次要压的目标
        self._slam_phase = "rise"     # rise → drop
        self._slam_t = 0              # 本次砸击已进行 tick
        self._pearl_cd = 0            # 喜欢珍珠的猫：两颗珍珠之间的间隔
        self._haul_cd = 0             # 清场（拖走无用尸体）的冷却
        self._clear_target = None     # 正在拖的那具无用尸体
        self._haul_left = 0           # 本趟剩余 tick
        self._itemplay_target = None
        self._itemplay_left = 0
        self._itemplay_phase = 0
        self._itemplay_side = "r"
        self._itemplay_mode = "inspect"
        self._itemplay_mode_t = 0
        self._itemplay_chase_exec = None
        self._itemplay_throw_count = 0
        self._itemplay_chase_exec = None
        self._itemplay_throw_count = 0
        self._lick_cd = 0                # 圣徒舔生物玩耍的冷却
        self._play_face = 1              # 玩耍时的朝向倾向（进玩法时随机一次）
        # 觅食欲望：
        # - 冬眠食物线以下：由 hunger_need + _food_urge 驱动，保证真的饿了会找
        # - 已达到冬眠线：每次吃东西后按“距离 food_max 还差几格”安排下一次觅食等待
        self._food_urge = 1.0
        self._food_prev = self.body.food
        self._food_prev_q = self.body.food * 4 + self.body.food_quarter
        self._food_seek_wait = 0       # 冬眠线以上的主动觅食等待（tick）
        self._karma_cd = 0            # 业力花（独立行动）的冷却
        self._karma_shoot_cd = 0      # 矛大师「用白针打落业力花」的短冷却
        self._fetch_karma = False     # 下一次 FetchFruit 是去拔业力花（独立目标链）
        self.anger = 0
        self.cursorlick = None
        self._cursor_prev = None
        self._cursor_speed = 0.0
        self._dwell = 0
        self._cursor_dwell = 0     # 鼠标停在猫附近的连续 tick 数
        self._relick_cooldown = 0
        self.cursorfx = getattr(window, "cursorfx", None)
        self._force_energy = None
        _fs = os.environ.get("SLUGCATPET_FORCE_ENERGY")
        if _fs:
            try:
                self._force_energy = max(0.0, min(1.0, float(_fs)))
            except ValueError:
                pass
        self._force_temper = None
        _ft = os.environ.get("SLUGCATPET_FORCE_TEMPER")
        if _ft:
            try:
                self._force_temper = max(-1.0, min(1.0, float(_ft)))
            except ValueError:
                pass
        self._force_food = None
        _ff = os.environ.get("SLUGCATPET_FORCE_FOOD")
        if _ff:
            try:
                self._force_food = max(0, min(self.body.food_max, int(_ff)))
            except ValueError:
                pass

        # 暴雨集合 / 庇护所睡眠
        self._storm_exec = None            # StormSeekShelter 的 PlanExecutor
        self._storm_goal_obj = None        # 状态面板「目标是什么」用
        self._storm_cd = 0                 # 够不到庇护所时的重试冷却
        self._shelter_sleep_left = 0       # 雨循环睡眠剩余 tick

        # 独占状态挂载槽：CatDef.fsm_mount 按 caps 注册
        self._ext_states = {}
        self._ext_enters = {}
        self._ext_breaks = {}
        self._ext_kill_breaks = {}
        self._ext_fx = {}
        self._ext_mood_states = {}
        self._ext_state_moods = {}
        self._ext_tickers = []
        self._interaction_blockers = set()
        self.drag_takeover = None
        self.stun_takeover = None
        cat = getattr(self.win, "cat", None)
        # 统一动作注册表：主 tick 里所有「决定」的唯一出处（见 behavior/action.py）。
        # 先建表再 fsm_mount：角色的独有动作（preempt band）在挂载时登记进来。
        self.actions = build_action_arbiter(self.rng)
        if cat is not None and cat.fsm_mount is not None:
            cat.fsm_mount(self)

        self._register_actions()
        self._register_mood_actions()

        self._enter("IdleStand")

    def register_action(self, key, band, gate, start, pre=None, score=None,
                        tags=(), cooldown=0, interrupt=0.0, one_shot=False):
        """角色模块用：把独有动作登记进同一个动作注册表（key 全局唯一）。"""
        return self.actions.register(ActionSpec(
            key=key, band=band, gate=gate, pre=pre, start=start, score=score,
            tags=frozenset(tags), cooldown=cooldown, interrupt=interrupt,
            one_shot=one_shot))

    def act_ctx(self):
        """当前 tick 的动作上下文（角色 ticker 走注册表起手时用）。"""
        return ActionContext(self, self.cursor)

    # 独占状态注册与查询
    def register_state(self, name, enter=None, tick=None, brk=None, kill_break=None, fx=None,
                       mood=None):
        if enter is not None:
            self._ext_enters[name] = enter
        if tick is not None:
            self._ext_states[name] = tick
        if brk is not None:
            self._ext_breaks[name] = brk
        if kill_break is not None:
            self._ext_kill_breaks[name] = kill_break
        if fx is not None:
            self._ext_fx[name] = fx
        if mood is not None:
            self._ext_mood_states[mood] = name
            self._ext_state_moods[name] = mood

    def register_ticker(self, fn):
        """挂载每 tick 回调。"""
        self._ext_tickers.append(fn)

    def blocks_interaction(self) -> bool:
        """当前独占状态是否屏蔽光标交互。"""
        return self.state in self._interaction_blockers

    def exclusive_fx(self):
        """当前状态的全屏特效提供者，无则 None。"""
        get = self._ext_fx.get(self.state)
        return None if get is None else get()

    def on_press(self, cursor):
        if self.blocks_interaction():
            return False
        return self.grab.begin(cursor)

    def on_release(self):
        self.grab.end()

    def apply_stun(self, ticks):
        if self.state in ("Ascension", "Dead", "Dragged"):
            return False
        if self.state in ("CeilingHang", "ChaseCursor", "Socialize",
                          "HelpFeed", "FightThreat", "CrawlAway", "EatCob",
                          "ScoldBlocker", "CatchFly", "ItemPlay"):
            self._wants_break(self.state)
        self._break_tongue()
        self.climb = None
        if self.fetch is not None:
            self.fetch.release()
            self.fetch = None
        self.cursorlick = None
        self.stonethrow = None
        self.flyhunt = None
        if self.body.carried_spear is not None:
            self.body.release_spear(to_free=True)
        if self.poleclimb is not None:
            self.body.chunk0.pinned = False
            self.body.chunk1.pinned = False
            self.body.on_pole = False
            self.body.animation = None
            self.poleclimb = None
        if self.hpole is not None:
            self.hpole.release()
            self.hpole = None
        if self.state == "SeekHPole":
            self.body.stop_walk()
            self._hp = None
            self._hp_phase = None
        if self.body.carried_fruit is not None:
            self.body.carried_fruit.stalk = None
            self.body.carried_fruit.state = "free"
            self.body.carried_fruit.held_by_hand = None
            self.body.release_fruit()
        if self.body.carried_stone is not None:
            self.body.release_stone(to_free=True)
        self._clear_hands()
        self.body.zerog_pole = None       # 砸晕即松杆
        self.body.set_posture(False)
        self.body.stun = max(self.body.stun, int(ticks))
        self.gfx.stunned = True
        self.body.temper_shift(tuning.TEMPER_STUN)
        self._transition("Stunned")
        return True

    def _pup_final(self) -> bool:
        """猫崽的身份是非蛞蝓猫生物：不转世、也不会被同伴救 —— 死了就是死了。"""
        return bool(getattr(self.win, "is_pup", False))

    def _after_death_reincarnate(self):
        """环境致死的死后收尾：普通蛞蝓猫排转世倒计时；猫崽什么都不排。"""
        if self._pup_final():
            self._reincarnate = False
            self._revive_timer = 0
            return
        self._reincarnate = True
        self._revive_timer = tuning.REINCARNATE_TICKS

    def kill(self):
        if self.state == "Dead":
            return
        kb = self._ext_kill_breaks.get(self.state)
        if kb is not None:
            kb()
        elif self.state == "AngryStone":
            self._angrystone_release()
        elif self.state == "PoleClimb":
            self._pole_release()
        elif self.state == "HPole":
            self._hpole_release()
        elif self.state == "SeekWarmth":
            self._seekwarmth_break()
        elif self.state == "SeekHPole":
            self._seekhpole_break()
        elif self.state in ("CeilingHang", "ChaseCursor", "Socialize",
                            "HelpFeed", "FightThreat", "CrawlAway", "EatCob",
                            "ScoldBlocker", "CatchFly", "ItemPlay"):
            self._wants_break(self.state)
        self._hibernating = False
        self.body.food_eat(-tuning.FOOD_KILL_PENALTY)
        had_flower = self.body.flower_karma
        if self.body.karma > 0 or self.body.karma_bottomed() or had_flower:
            if self._death_karma_settle():
                self.body.temper_shift(tuning.TEMPER_KILL_REVIVED)
            self.body.die()
            self.gfx.dead = True
            self._transition("Dead")
            self._revive_timer = 0    # 真死：不再自行计时复活，只有同伴 nuzzle 才回来
        else:
            self.body.die()
            self._transition("Dead")
            self._revive_timer = 0
        self._schedule_karma_flower(had_flower)

    def kill_cold(self):
        """冻死：环境致死，转世复活，不计好感。"""
        if self.state == "Dead":
            return
        had_flower = self.body.flower_karma
        self._death_karma_settle()
        self._break_active_controllers()
        self.grab.force_release()
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._after_death_reincarnate()
        self._schedule_karma_flower(had_flower)

    def kill_storm(self):
        """暴雨致死：没赶上进庇护所。环境致死，转世复活，不计好感。

        与 kill_cold / kill_drown 同一口径；只不过倒计时在暴雨期间被 _st_dead
        冻结，雨停了才转世。
        """
        if self.state == "Dead":
            return
        had_flower = self.body.flower_karma
        self._death_karma_settle()
        self._break_active_controllers()
        self.grab.force_release()
        self.body.swim_target = None
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._after_death_reincarnate()
        self._schedule_karma_flower(had_flower)

    def kill_drown(self):
        """溺死：环境致死，转世复活，不计好感。"""
        if self.state == "Dead":
            return
        had_flower = self.body.flower_karma
        self._death_karma_settle()
        self._break_active_controllers()
        self.grab.force_release()
        self.body.swim_target = None
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._after_death_reincarnate()
        self._schedule_karma_flower(had_flower)

    def kill_pyro_drown(self):
        """工匠溺水引爆而死，转世复活。"""
        if self.state == "Dead":
            return
        from ..cats.artificer.pyro import pyro_explosion
        pyro_explosion(self.win, self.body)
        had_flower = self.body.flower_karma
        self._death_karma_settle()
        self._break_active_controllers()
        self.grab.force_release()
        self.body.swim_target = None
        self.body.pyro_drown = False
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._after_death_reincarnate()
        self._schedule_karma_flower(had_flower)

    def _death_karma_settle(self) -> bool:
        """死亡业力结算：有业力花条（原版 reinforcedKarma）→ 消耗花条、业力不掉；
        否则照原规则掉一级。返回是否真的掉了业力。"""
        if self.body.flower_karma:
            self.body.flower_karma = False
            return False
        self.body.karma_drop()
        return True

    def _schedule_karma_flower(self, had_flower: bool):
        """排「死后原地长业力花」（原版 Player.PlaceKarmaFlower / karmaFlowerGrowPos）。

        僧侣（monk）无条件；猎手 15~45s；其他猫死亡时带着业力花条才长（150~210s）。
        同一具尸体只排一次。
        """
        if self._pup_final():
            return                      # 猫崽不是蛞蝓猫：死后不长业力花
        if self._flower_planted:
            return
        variant = getattr(self.win, "variant", "")
        if variant == "monk":
            delay = self.rng.randrange(tuning.FLOWER_OTHER_MIN,
                                       tuning.FLOWER_OTHER_MAX + 1)
        elif variant == "hunter":
            delay = self.rng.randrange(tuning.FLOWER_HUNTER_MIN,
                                       tuning.FLOWER_HUNTER_MAX + 1)
        elif had_flower:
            delay = self.rng.randrange(tuning.FLOWER_OTHER_MIN,
                                       tuning.FLOWER_OTHER_MAX + 1)
        else:
            return
        self._flower_planted = True
        c0 = self.body.chunk0
        self.win.schedule_karma_flower(c0.x, c0.y, delay)

    def is_dead(self) -> bool:
        return self.state == "Dead"

    def is_truly_dead(self) -> bool:
        return self.state == "Dead" and self._revive_timer <= 0

    def begin_reincarnation(self) -> bool:
        """全体转生：暴雨期间冻结；救援复活不走这里。"""
        if self.state != "Dead":
            return False
        if getattr(self.win, "storm_active", False):
            return False
        if self._pup_final():
            return False                # 猫崽不转世：死了就是死了
        self._reincarnate = True
        if self._revive_timer <= 0:
            self._revive_timer = tuning.REINCARNATE_TICKS
        return True

    def is_reincarnating(self) -> bool:
        return self.state == "Dead" and self._reincarnate and self._revive_timer > 0

    def enter_dead(self):
        """直接置真死态（持久化恢复用）。"""
        self._break_active_controllers()
        self.grab.force_release()
        self._hibernating = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._revive_timer = 0
        self._flower_planted = True      # 持久化恢复：不补长花

    def _break_active_controllers(self):
        st = self.state
        brk = self._ext_breaks.get(st)
        if brk is not None:
            brk()
        elif st == "AngryStone":
            self._angrystone_release()
        elif st == "HuntFly":
            self._flyhunt_release()
        elif st == "PoleClimb":
            self._pole_release()
        elif st == "HPole":
            self._hpole_release()
        elif st == "FetchFruit":
            self._break_tongue()
            self._fetch_release()
        elif st == "SeekWarmth":
            self._seekwarmth_break()
        elif st == "StormSeekShelter":
            self._storm_break()
        elif st == "SeekHPole":
            self._seekhpole_break()
        elif st == "Swimming":
            self.body.swim_target = None
        elif st in ("CeilingHang", "ChaseCursor", "Socialize",
                    "HelpFeed", "FightThreat", "CrawlAway", "EatCob",
                    "ScoldBlocker", "CatchFly", "ItemPlay", "CoverAlly"):
            self._wants_break(st)

    def _break_tongue(self):
        tg = self.win.tongue
        if tg is not None:
            tg.retract()
            tg.reset_config()
        self.body.suspended = False

    def update(self, cursor):
        self.cursor = cursor
        for fn in self._ext_tickers:
            fn()
        self._track_cursor(cursor)
        disturbed = self.grab.active

        z = self._zerog()   # 无重力边沿检测
        if z and not self._prev_zerog:
            self._zerog_entered = True
        elif (self._prev_zerog and not z and self.state == "IdleStand"
                and self.body.carried_fruit is not None):
            # 重力恢复：松开漂浮啃食中的果子，落地走正常取食
            f = self.body.carried_fruit
            self.body.release_fruit()
            f.state = "free"
        self._prev_zerog = z

        # ── 决策：唯一入口。保命 → 该做的事（见 behavior/action.py）──
        ctx = ActionContext(self, cursor)
        self._storm_lockdown(ctx)
        self.actions.tick()
        self.actions.decide(ctx)

        # 圣徒舌头黏着生物：一路拽着，不许摆匍匐（下面按 tick 扣体力）
        tongue_hold = self._tongue_holding_creature()
        if tongue_hold is not None:
            self.body.set_crawl(False)
        # _hibernating 一置位就当场蜷起来（LieDown 期也一样），避免「睁着眼蜷着却睡不着」
        lying = self.state == "Sleep" or self._hibernating
        self.gfx.sleeping = lying
        self.body.sleeping = lying
        if self.state in ("LieDown", "Sleep"):
            self.gfx.face(False, PRIO_FORCE)   # 睡姿不许挂醒着的表情（不可被顶掉）
        self.gfx.dead = (self.state == "Dead")
        self.gfx.stunned = (self.state == "Stunned")

        # 社交动作只属于起手它的那个态：换态（或被无重力接管）就收势
        if self._act_active() and (self.state != self._act_owner or self._zerog()):
            self._act_end()
        handler = self._ext_states.get(self.state)
        if handler is None:
            handler = getattr(self, "_st_" + self.state.lower(), None)
        if handler:
            handler(cursor, disturbed)
        self._push_pose_tick()
        e_delta = _energy_delta(self.state, self._drain_fac)
        if self.state == "HPole":
            # 横杆＝地面移动口径（轻度），不额外算攀爬体力
            e_delta = -EN_DRAIN_LIGHT * self._drain_fac
        elif (self.state == "PoleClimb" and self.poleclimb is not None
                and self.poleclimb.phase == "tip"):
            e_delta = -EN_DRAIN_LIGHT * self._drain_fac   # 站杆顶不算剧烈
        elif self.state == "Swimming" and self.body.swim_mode == "surface":
            e_delta = EN_REC_REST * tuning.SWIM_SURFACE_REST_FAC   # 浮水面歇气
        self.body.energy_change(e_delta)
        if tongue_hold is not None:
            self.body.energy_change(-tuning.SAINT_LICK_HOLD_DRAIN)
            if self.body.energy <= 0.0:                  # 拉不动了 → 松舌
                tg = getattr(self.win, "tongue", None)
                if tg is not None:
                    tg.retract()
        if self._force_energy is not None:
            self.body.energy = self._force_energy
        if self._force_temper is not None:
            self.body.temper = self._force_temper
        if self._force_food is not None:
            self.body.food = self._force_food
        food_now_q = self.body.food * 4 + self.body.food_quarter
        if food_now_q > self._food_prev_q:
            self._food_urge = 0.0          # 吃到东西：基础觅食欲望归 0
            self._social_urge_boost(tuning.SOCIAL_URGE_BOOST_EAT)
            if (self.body.food_satisfied()
                    and self._food_prev_q < self.body.food_hibernate * 4):
                self._social_urge_boost(tuning.SOCIAL_URGE_BOOST_FULL)
            # 已满足冬眠线，但还没有达到真正的 food_max：
            # 根据“还差几格”安排下一次主动觅食。小数格也算“没有满”。
            if self.body.food_satisfied() and food_now_q < self.body.food_max * 4:
                missing_cells = int(math.ceil(
                    (self.body.food_max * 4 - food_now_q) / 4.0))
                # 种族的 food_max / food_hibernate 已经由 SlugStats 定义；
                # 这里仅计算“距离这个种族自己的满饱值还差几格”。
                # 只有最后 3 个未满格进入减速区：
                #   还差 3 → 0~10s；2 → 0~20s；1 → 0~30s；4+ → 0s。
                slow_cells = tuning.FOOD_POST_HIBERNATE_SLOW_CELLS
                max_wait_sec = max(
                    0.0,
                    min(
                        tuning.FOOD_POST_HIBERNATE_WAIT_MAX_SEC,
                        (slow_cells + 1 - missing_cells)
                        * tuning.FOOD_POST_HIBERNATE_CELL_SEC,
                    )
                )
                # 每只猫用自己的 rng；activity/hurry 只改变区间内取值的位置，
                # 不改变你规定的 0~10 / 0~20 / 0~30 上限。
                if max_wait_sec > 0.0:
                    urgency = clampf(
                        (float(self.pers.activity) + float(self.pers.hurry)) * 0.5,
                        0.0, 1.0)
                    exponent = 1.0 + 1.5 * (urgency - 0.5)
                    u = self.rng.random() ** exponent
                    wait_sec = max_wait_sec * u
                    self._food_seek_wait = int(round(wait_sec * 40.0))
                else:
                    self._food_seek_wait = 0
            else:
                # 尚未达到冬眠线：继续走原来的 hunger_need 逻辑，不额外拖延。
                self._food_seek_wait = 0
        self._food_prev = self.body.food
        self._food_prev_q = food_now_q
        self.mood.tick_freshness(self._active_mood())
        self.mood.tick_freshness(self._active_mood())
        self.timer += 1

    # ── 统一动作注册表：主 tick 的全部「决定」都登记在这里 ──
    # 旧版 update() 里那条又长又散的 if 链搬进来了：顺序 = 注册顺序，
    # 每条动作的 pre（无条件记账）/ gate（什么条件做）/ start（做什么）
    # 都是从原处逐字搬过来的，所以行为与随机数流与旧版一致。
    def _register_actions(self):
        A = self.actions.register
        A(ActionSpec(key='Dragged', band=BAND_EMERGENCY,
                    pre=self._act_dragged_pre, gate=self._act_dragged_gate, start=self._act_dragged,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='PyroDrown', band=BAND_EMERGENCY,
                    pre=self._act_pyrodrown_pre, gate=self._act_pyrodrown_gate, start=self._act_pyrodrown,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='Drown', band=BAND_EMERGENCY,
                    pre=self._act_drown_pre, gate=self._act_drown_gate, start=self._act_drown,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='SwimEnter', band=BAND_EMERGENCY,
                    pre=self._act_swimenter_pre, gate=self._act_swimenter_gate, start=self._act_swimenter,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='SwimExit', band=BAND_EMERGENCY,
                    pre=self._act_swimexit_pre, gate=self._act_swimexit_gate, start=self._act_swimexit,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='ZeroG', band=BAND_EMERGENCY,
                    pre=self._act_zerog_pre, gate=self._act_zerog_gate, start=self._act_zerog,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='WaterUrgent', band=BAND_EMERGENCY,
                    pre=self._act_waterurgent_pre, gate=self._act_waterurgent_gate, start=self._act_waterurgent,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='ColdUrgent', band=BAND_EMERGENCY,
                    pre=self._act_coldurgent_pre, gate=self._act_coldurgent_gate, start=self._act_coldurgent,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='StormSeekShelter', band=BAND_EMERGENCY,
                    pre=self._act_stormseek_pre, gate=self._act_stormseek_gate,
                    start=self._act_stormseek,
                    tags=frozenset({TAG_EMERGENCY, TAG_NAV})))
        A(ActionSpec(key='StormSleep', band=BAND_EMERGENCY,
                    pre=self._act_stormsleep_pre, gate=self._act_stormsleep_gate,
                    start=self._act_stormsleep,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='BlockReact', band=BAND_NEED,
                    pre=self._act_blockreact_pre, gate=self._act_blockreact_gate, start=self._act_blockreact,
                    tags=frozenset({TAG_NAV})))
        A(ActionSpec(key='WakeOnThreat', band=BAND_NEED,
                    pre=self._act_wakeonthreat_pre, gate=self._act_wakeonthreat_gate, start=self._act_wakeonthreat,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='FaceThreat', band=BAND_NEED,
                    pre=self._act_facethreat_pre, gate=self._act_facethreat_gate, start=self._act_facethreat,
                    tags=frozenset({TAG_EMERGENCY})))
        A(ActionSpec(key='Wants', band=BAND_NEED,
                    pre=self._act_wants_pre, gate=self._act_wants_gate, start=self._act_wants,
                    tags=frozenset({TAG_SOCIAL})))
        A(ActionSpec(key='Exhaustion', band=BAND_NEED,
                    pre=self._act_exhaustion_pre, gate=self._act_exhaustion_gate, start=self._act_exhaustion,
                    tags=frozenset({TAG_FOOD})))
        A(ActionSpec(key='FetchFood', band=BAND_NEED,
                    pre=self._act_fetchfood_pre, gate=self._act_fetchfood_gate, start=self._act_fetchfood,
                    tags=frozenset({TAG_FOOD})))
        A(ActionSpec(key='KarmaFlower', band=BAND_NEED,
                    pre=self._act_karmaflower_pre, gate=self._act_karmaflower_gate, start=self._act_karmaflower,
                    tags=frozenset({TAG_FOOD})))
        A(ActionSpec(key='PearlHoard', band=BAND_NEED,
                    pre=self._act_pearlhoard_pre, gate=self._act_pearlhoard_gate, start=self._act_pearlhoard,
                    tags=frozenset({TAG_FOOD})))
        A(ActionSpec(key='EatCob', band=BAND_NEED,
                    pre=self._act_eatcob_pre, gate=self._act_eatcob_gate, start=self._act_eatcob,
                    tags=frozenset({TAG_FOOD})))
        A(ActionSpec(key='HuntFly', band=BAND_NEED,
                    pre=self._act_huntfly_pre, gate=self._act_huntfly_gate, start=self._act_huntfly,
                    tags=frozenset({TAG_FOOD})))
        A(ActionSpec(key='CatchFly', band=BAND_NEED,
                    pre=self._act_catchfly_pre, gate=self._act_catchfly_gate, start=self._act_catchfly,
                    tags=frozenset({TAG_FOOD})))
        A(ActionSpec(key='ItemPlay', band=BAND_NEED,
                    pre=self._act_itemplay_pre, gate=self._act_itemplay_gate, start=self._act_itemplay,
                    tags=frozenset({TAG_PERSONALITY})))
        A(ActionSpec(key='SaintLickPlay', band=BAND_NEED,
                    pre=self._act_saintlickplay_pre, gate=self._act_saintlickplay_gate, start=self._act_saintlickplay,
                    tags=frozenset({TAG_PERSONALITY})))
        A(ActionSpec(key='ClearCorpse', band=BAND_NEED,
                    pre=self._act_clearcorpse_pre, gate=self._act_clearcorpse_gate, start=self._act_clearcorpse,
                    tags=frozenset({TAG_INTERACT})))
        A(ActionSpec(key='SleepRoll', band=BAND_NEED,
                    pre=self._act_sleeproll_pre, gate=self._act_sleeproll_gate, start=self._act_sleeproll,
                    tags=frozenset({TAG_PERSONALITY})))
        A(ActionSpec(key='AngryStone', band=BAND_NEED,
                    pre=self._act_angrystone_pre, gate=self._act_angrystone_gate, start=self._act_angrystone,
                    tags=frozenset({TAG_PERSONALITY})))
        A(ActionSpec(key='CursorLick', band=BAND_NEED,
                    pre=self._act_cursorlick_pre, gate=self._act_cursorlick_gate, start=self._act_cursorlick,
                    tags=frozenset({TAG_PERSONALITY})))

    def _act_dragged_pre(self, ctx):
        self.grab.tick()
    def _act_dragged_gate(self, ctx):
        return (self.grab.active and self.state not in
                ("Dragged", "Ascension", "Dead", "TongueClimb", "CeilingHang",
                 "FetchFruit", "CursorLick", "AngryStone", "PoleClimb", "HPole",
                 "SeekHPole"))
    def _act_dragged(self, ctx):
            self._transition("Dragged")

    def _act_pyrodrown_pre(self, ctx):
        if self.grab.active:
            self.grab.drag(ctx.cursor) if ctx.cursor is not None else None
        self._shake_drop_tick()
    def _act_pyrodrown_gate(self, ctx):
        return (self.body.pyro_drown and self.state != "Dead")
    def _act_pyrodrown(self, ctx):
            self.kill_pyro_drown()

    def _act_drown_pre(self, ctx):
        pass
    def _act_drown_gate(self, ctx):
        return (not self.body.pyro_drown and self.body.drown >= 1.0 and self.state != "Dead")
    def _act_drown(self, ctx):
            self.kill_drown()

    def _act_swimenter_pre(self, ctx):
        pass
    def _act_swimenter_gate(self, ctx):
        return (not self.body.pyro_drown and self.body.drown < 1.0 and self.body.swimming and self.state not in _SWIM_KEEP)
    def _act_swimenter(self, ctx):
                self._break_active_controllers()
                self._transition("Swimming")

    def _act_swimexit_pre(self, ctx):
        pass
    def _act_swimexit_gate(self, ctx):
        return (not self.body.pyro_drown and self.body.drown < 1.0 and not self.body.swimming and self.state == "Swimming")
    def _act_swimexit(self, ctx):
            self.body.swim_target = None
            self._transition("IdleStand" if self.body.on_floor() else "Airborne")

    def _act_zerog_pre(self, ctx):
        pass
    def _act_zerog_gate(self, ctx):
        return (self._zerog() and self.state not in _ZEROG_KEEP)
    def _act_zerog(self, ctx):
            self._break_active_controllers()
            self._transition("IdleStand")

    def _act_waterurgent_pre(self, ctx):
        pass
    def _act_waterurgent_gate(self, ctx):
        return (self._water_urgent() and not self.grab.active and not self._zerog()
                and self.state not in _WATER_BLOCKED)
    def _act_waterurgent(self, ctx):
            self._break_active_controllers()
            self._wall_side = -1 if self.body.chunk1.x < self.WL / 2 else 1
            self._transition("RelocateToWall")

    def _act_coldurgent_pre(self, ctx):
        pass
    def _act_coldurgent_gate(self, ctx):
        return (self._cold_urgent() and not self.grab.active and not self._zerog()
                and not self._water_urgent()
                and self.state not in _COLD_BLOCKED)
    def _act_coldurgent(self, ctx):
            self._break_active_controllers()
            self._transition("SeekWarmth")

    def _act_stormseek_pre(self, ctx):
        if self._storm_cd > 0:
            self._storm_cd -= 1
    def _act_stormseek_gate(self, ctx):
        return (self.win.storm_active and getattr(self.win, "shelters", None)
                and self._storm_phase() == "gather"
                and self._storm_cd <= 0
                and not self.grab.active and not self._zerog()
                and not self.body.swimming
                and self.state not in _STORM_BLOCKED)
    def _act_stormseek(self, ctx):
            self._break_active_controllers()
            self._transition("StormSeekShelter")

    def _act_stormsleep_pre(self, ctx):
        pass
    def _act_stormsleep_gate(self, ctx):
        if self._storm_phase() != "sleep" or self.grab.active:
            return False
        sh = self._storm_shelter()
        if sh is None:
            return False
        b = self.body
        return (self.state not in ("ShelterSleep", "Dead", "Dragged", "Ascension",
                                   "Stunned", "Swimming")
                and sh.contains(b.chunk1.x, b.chunk1.y))
    def _act_stormsleep(self, ctx):
            self._transition("ShelterSleep")

    def _act_blockreact_pre(self, ctx):
        pass
    def _act_blockreact_gate(self, ctx):
        return (True)
    def _act_blockreact(self, ctx):
        self._scan_blocking()

    def _act_wakeonthreat_pre(self, ctx):
        board_for(self.win).sync(self.win, getattr(self.win, "_pole_tick", 0))
        self._board_loss_tick()
        self._watch_fetch_steal()          # 同样只负责«发现被抢 + 发事件»
        # 事件总线：消化这一 tick 别人做过的事（关系变化 + 社会反应）。
        # 决策不写在这一层 —— 这里只把「发生了什么」翻成「我要做什么」。
        self._event_tick()
        if self._flee_cd > 0:
            self._flee_cd -= 1
    def _act_wakeonthreat_gate(self, ctx):
        return (self.state in ("LieDown", "Sleep") and not self.grab.active
                and self._threat_present())
    def _act_wakeonthreat(self, ctx):
            self._hibernating = False          # 威胁在场：睡着也要立刻醒
            self._transition("WakeSequence")

    def _act_facethreat_pre(self, ctx):
        self._threat_pressure_tick()      # 被逼退记账（每 tick 无条件）
    def _act_facethreat_gate(self, ctx):
        return (not self.grab.active and not self._exhausted and not self._zerog())
    def _act_facethreat(self, ctx):
            self._face_threat_tick(ctx.cursor)

    def _act_wants_pre(self, ctx):
        pass
    def _act_wants_gate(self, ctx):
        return (True)
    def _act_wants(self, ctx):
        self._wants_tick(ctx.cursor)

    def _act_exhaustion_pre(self, ctx):
        pass
    def _act_exhaustion_gate(self, ctx):
        return (not self._exhausted and not self._hibernating and not self.grab.active
                and not self._cold_urgent() and not self._zerog()
                and self.body.energy < tuning.EXHAUST_ENTER_ENERGY
                and self.state not in _EXHAUST_BLOCKED)
    def _act_exhaustion(self, ctx):
            self._exhausted = True
            self._enter_exhaustion()

    def _act_fetchfood_pre(self, ctx):
        if self._fetch_cooldown > 0:
            self._fetch_cooldown -= 1
        if self._food_seek_wait > 0:
            self._food_seek_wait -= 1

        # 取果触发：门禁 + 间隔节流重算候选
        self._fetch_check = (self._fetch_check + 1) % T_FETCH_CHECK
        self._food_urge_tick()
        self._social_urge_tick()
    def _act_fetchfood_gate(self, ctx):
        return (self._fetch_check == 0
                and (self.body.food * 4 + self.body.food_quarter) < self.body.food_max * 4
                and self._food_seek_ready()
                and self._food_seek_wait <= 0
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and self._fetch_cooldown <= 0
                and self.state not in _FETCH_NEVER)
    def _act_fetchfood(self, ctx):
            # 横杆上的食物先交给 HPole 专线：Planner 能算「可达」，
            # 但不该由 Planner 决定怎么吃。交出去之后 SurfaceRoute 就别再抢同一个目标。
            if self._hpole_food_trip():
                return

            fetch_cands = fetch_ready(
                self.planner,
                self.win.fetchables(want_karma=not self.body.flower_karma),
                diet=self.pers.diet, unit=self.win)
            if fetch_cands:
                take = True
                if self.state in _FETCH_PLAY:
                    tg = self.win.tongue
                    if tg is None:
                        take = False
                    else:
                        mox, moy = self.gfx.mouth_world()
                        take = any(math.hypot(f.x - mox, f.y - moy) <= tg.total
                                   for f in fetch_cands)
                if take:
                    self._break_active_controllers()
                    self._act_or_wake("FetchFruit")

    def _act_karmaflower_pre(self, ctx):
        if self._karma_cd > 0:
            self._karma_cd -= 1
        if self._karma_shoot_cd > 0:
            self._karma_shoot_cd -= 1
    def _act_karmaflower_gate(self, ctx):
        return (self._fetch_check == 0 and self._karma_cd <= 0
                and self.win.karmaflowers and not self.body.flower_karma
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.state in _WANTS_FROM
                and self.rng.random() < tuning.KARMA_SEEK_P)
    def _act_karmaflower(self, ctx):
            if self._shoot_karma_flower():
                return
            if self._karma_flowers_reachable():
                self._break_active_controllers()
                self._fetch_karma = True
                self._act_or_wake("FetchFruit")

    def _shoot_karma_flower(self) -> bool:
        """矛大师：站在射程内用白针把扎根的业力花打下来（用户口径，仅此一家）。

        它没有嘴，又只有尾针能喂饱自己，所以看到业力花不走去啃，而是抬手一针
        把花钉下来 —— 命中结算在 items._step_spear_hit（花被打落 + 业力花槽填满）。
        手里不是活白针、已经离根、或超出射程时返回 False，交回普通链路。
        """
        if self._karma_shoot_cd > 0 or not self._needle_only():
            return False
        b = self.body
        if not self._own_needle(b.carried_spear):
            return False
        c1 = b.chunk1
        best, bd = None, tuning.KARMA_SHOOT_R
        for f in self.win.karma_targets():
            if getattr(f, "grow_pos", None) is None:
                continue                        # 已经离根：这针打不出花来了
            d = math.hypot(f.x - c1.x, f.y - c1.y)
            if d < bd:
                best, bd = f, d
        if best is None or abs(best.x - c1.x) < tuning.KARMA_SHOOT_NEAR:
            return False                        # 射程外 / 贴脸：走过去连根拔更划算
        b.facing = 1 if best.x >= c1.x else -1
        b.stop_walk()
        self.gfx.look_at = (best.x, best.y)
        self._aim_target(best)
        fired = self._launch_weapon(b.facing, best)   # 平着打：花就悬在地面上方一点
        self._karma_shoot_cd = tuning.KARMA_SHOOT_CD
        if fired:
            self._karma_cd = tuning.KARMA_SEEK_CD     # 打完了，短时间不再惦记
        return True

    def _act_pearlhoard_pre(self, ctx):
        if self._pearl_cd > 0:
            self._pearl_cd -= 1
    def _act_pearlhoard_gate(self, ctx):
        return (self._fetch_check == 0 and self._pearl_cd <= 0
                and float(getattr(self.pers, "pearl_like", 1.0)) > 1.0
                and self.body.carried_fruit is None and self.body.carried_spear is None
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander")
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.rng.random() < tuning.PEARL_HOARD_P)
    def _act_pearlhoard(self, ctx):
            if self._free_pearl_near() is not None:
                self._pearl_cd = tuning.PEARL_HOARD_CD
                self._break_active_controllers()
                self._act_or_wake("FetchFruit")

    def _act_eatcob_pre(self, ctx):
        if self._cob_cd > 0:
            self._cob_cd -= 1
        if self._cob_seek_cd > 0:
            self._cob_seek_cd -= 1
        if self._cob_throw_cd > 0:
            self._cob_throw_cd -= 1
        if self._pole_throw_cd > 0:
            self._pole_throw_cd -= 1
        self._cob_check = (self._cob_check + 1) % tuning.COB_CHECK_TICKS
    def _act_eatcob_gate(self, ctx):
        return (self._cob_check == 0 and self._cob_seek_cd <= 0
                and not self.body.food_satisfied()
                and self._food_seek_ready()
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and self.state in _WANTS_FROM)
    def _act_eatcob(self, ctx):
            cb = self._nearest_cob(feedable=True)
            if cb is None and self._cob_spear_willing():
                cb = self._nearest_cob(feedable=False)     # 没开荚：去捡矛打
            if cb is not None:
                self._cob = cb
                self._break_active_controllers()
                self._act_or_wake("EatCob")

    def _act_huntfly_pre(self, ctx):
        if self._hunt_cd > 0:
            self._hunt_cd -= 1
        fed = self.body.food_satisfied()
        full = self.body.food >= self.body.food_max
        meat = self._meat_zeal()
        rage = self._spear_rage()
        hunting = ((not fed and (meat > 0.0 or rage)
                    and self._food_seek_ready()))   # 没到冬眠阈：正经狩猎（吃素的猫不猎；矛大师狂暴时必猎）
        # 吃到顶格：捕食也算娱乐项目（空手也会先去捡石头/矛再打）
        playing = (full and self.rng.random() < tuning.HUNT_PLAY_PROB)
        self._fly_hunt_on = hunting or playing    # 记账结果给 gate 读（pre 无条件先跑）
    def _act_huntfly_gate(self, ctx):
        return (self._fetch_check == 0 and self._hunt_cd <= 0
                and self._fly_hunt_on
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander"))
    def _act_huntfly(self, ctx):
            from .huntfly import FlyHunter
            probe = FlyHunter(self.win, self.rng, self)
            if probe._flies() and (self._spear_rage()
                                   or probe.ground_pool()
                                   or self.body.carried_stone is not None
                                   or self.body.carried_spear is not None):
                self._break_active_controllers()
                self._act_or_wake("HuntFly")

    def _act_catchfly_pre(self, ctx):
        if self._catch_cd > 0:
            self._catch_cd -= 1
    def _act_catchfly_gate(self, ctx):
        return (self._catch_cd <= 0
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander")
                and self._nearest_catchable() is not None)
    def _act_catchfly(self, ctx):
            self._break_active_controllers()
            self._act_or_wake("CatchFly")

    def _act_itemplay_pre(self, ctx):
        if self._itemplay_cd > 0:
            self._itemplay_cd -= 1
    def _act_itemplay_gate(self, ctx):
        return (self._fetch_check == 0 and self._itemplay_cd <= 0
                and (self.body.food_satisfied() or self._food_urge < 1.0)
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander")
                and self.rng.random() < tuning.ITEMPLY_P)
    def _act_itemplay(self, ctx):
            it = self._nearest_play_item()
            if it is not None:
                self._itemplay_target = it
                self._break_active_controllers()
                self._act_or_wake("ItemPlay")

    def _act_saintlickplay_pre(self, ctx):
        if self._lick_cd > 0:
            self._lick_cd -= 1
    def _act_saintlickplay_gate(self, ctx):
        return (self._lick_cd <= 0 and self.win.tongue is not None
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self._threat_lizard() is None
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander"))
    def _act_saintlickplay(self, ctx):
            tgt = self._lick_creature()
            if tgt is not None and self.rng.random() < self._lick_want():
                self.win.fire_tongue_at_obj(tgt)
                self._lick_cd = LICK_PLAY_CD
                self.gfx.look_at = (tgt.x, tgt.y)

    def _act_clearcorpse_pre(self, ctx):
        if self._haul_cd > 0:
            self._haul_cd -= 1
    def _act_clearcorpse_gate(self, ctx):
        return (self._fetch_check == 0 and self._haul_cd <= 0
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.body.on_floor()
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander")
                and self._threat_lizard() is None)
    def _act_clearcorpse(self, ctx):
            jc = self._junk_corpse_near()
            # 先看有没有垃圾再掷骰：没尸体就不动随机流（随机数纪律）
            if jc is not None and self.rng.random() < CORPSE_HAUL_P:
                self._clear_target = jc
                jc.hauler = self                 # 认领：这具尸体只由我来搬
                self._break_active_controllers()
                self._act_or_wake("ClearCorpse")

    def _act_sleeproll_pre(self, ctx):
        self._back_spear_tick()
        self._tail_needle_tick()
        self._sleep_urge_tick()
    def _act_sleeproll_gate(self, ctx):
        return (not self._hibernating and not self.grab.active and not self._exhausted
                and self._tongue_holding_creature() is None     # 舌头黏着生物：不许入睡
                and not self._too_cold_to_sleep() and not self._zerog()
                and self._sleep_roll()
                and self.state in ("IdleStand", "LieDown"))
    def _act_sleeproll(self, ctx):
            self._hibernating = True
            self._sleep_drop_hands()          # 睡觉前把手里的东西放下（原版睡着不留吃的）
            if self.state == "IdleStand":
                self._transition("LieDown")

    def _act_angrystone_pre(self, ctx):
        pass
    def _act_angrystone_gate(self, ctx):
        return (self.state in ("PostThrowWander", "PostThrowStand") and self.anger > 0
                and not self.grab.active and self._grounded_stone_available())
    def _act_angrystone(self, ctx):
            self._transition("AngryStone")

    def _act_cursorlick_pre(self, ctx):
        self._lick_dwell_need = _lerpmap(self.body.temper, -1.0, 1.0,
                                         LICK_DWELL * 1.5, LICK_DWELL * 0.5)
    def _act_cursorlick_gate(self, ctx):
        return ("CursorLick" in self._ext_states
                and self.state == "IdleStand" and not self.grab.active and not self._exhausted
                and not self._zerog()
                and self._relick_cooldown <= 0 and self._dwell >= self._lick_dwell_need
                and ctx.cursor is not None
                and self.HL * LICK_BAND_LO <= ctx.cursor[1] <= self.HL * LICK_BAND_HI
                and abs(self.body.chunk0.x - ctx.cursor[0]) < self.WL * LICK_GATE_FRAC)
    def _act_cursorlick(self, ctx):
            self._transition("CursorLick")


    def _transition(self, new):
        if new == self.state:
            return
        old = self.state
        # 睡眠意图只能存在于休息态：换到别的状态就统一撤销。不变量写在这里，
        # 以后再加「强制中断状态」（涉水 / 无重力 / 冷水 / 爆炸…）也不会漏清
        # _hibernating，不会再卡成「闭着眼耷拉着头却还在活动」的半睡姿态。
        # WakeSequence 例外：起床动画要靠 sleep_curl 自己渐退，不能被一刀削掉。
        if new not in ("LieDown", "Sleep", "ShelterSleep", "WakeSequence"):
            self._hibernating = False
            self.gfx.sleeping = False
            self.body.sleeping = False
            self.gfx.sleep_curl = 0.0
        self.state = new
        self.timer = 0
        self.phase = 0
        self._leave(old)
        self._enter(new)

    def _leave(self, old):
        """离开欲望态时统一收尾（幂等；_break_active_controllers 已跑过也无害）。"""
        if old in _WANTS_STATES:
            self._wants_break(old)
        if old == "ClearCorpse":
            self._haul_release(0.0)

    def _act_or_wake(self, target):
        """趴/睡态先起身并稳定一会再行动；已站立则直接进入目标态。"""
        if self.state in ("LieDown", "Sleep"):
            self._transition("WakeSequence")   # 顺序：_enter 会清 _wake_then
            self._wake_then = target
        else:
            self._transition(target)

    def _enter(self, st):
        ext = self._ext_enters.get(st)
        if ext is not None:
            ext()
            return
        b = self.body
        if st == "IdleStand":
            b.set_posture(True)
            b.stop_walk()
            self._idle_hold = tuning.IDLE_BREATHER   # 落地喘息，先停一拍再重抽
        elif st == "ClearCorpse":
            b.set_posture(True)
            b.stop_walk()
            self._haul_left = CORPSE_HAUL_TICKS       # 拖尸总时长预算
        elif st == "LieDown":
            self.gfx.face(False, PRIO_FORCE)   # 趴下睡觉：醒着的表情收掉
            b.set_posture(False)
            b.stop_walk()
            self._settle_to_rest()
        elif st == "Sleep":
            self.gfx.face(False, PRIO_FORCE)
            b.set_posture(False)
            b.stop_walk()
            self._settle_to_rest()
            _lo = int(tuning.SLEEP_SECS_MIN * 40.0)      # 20s（40 tick/s）
            _hi = int(tuning.SLEEP_SECS_MAX * 40.0)      # 40s
            self._sleep_left = self.rng.randrange(_lo, _hi + 1)
            # 入睡瞬间结算：按格数扣掉睡眠饱食度、业力 +1（用户口径）
            b.karma_gain()
            b.food_eat(-b.food_hibernate)
        elif st == "WakeSequence":
            self._hibernating = False        # 起身就清掉睡眠意图，免得卡在半睡
            self.gfx.sleeping = False
            self.body.sleeping = False
            self.phase = 0
            self._wake_stable = 0
            self._wake_then = None
        elif st == "Dragged":
            self._hibernating = False
            b.set_posture(True)
            b.stop_walk()
            self._struggle_left = 0
        elif st == "Airborne":
            b.set_posture(True)
            b.stop_walk()
            self._settle = 0
        elif st == "PostThrowWander":
            b.set_posture(True)
            self._pick_wander_target()
        elif st == "PostThrowStand":
            b.set_posture(True)
            b.stop_walk()
        elif st == "MakeWay":
            self._enter_makeway()
        elif st == "CoverAlly":
            self._cover_enter()
        elif st == "FleeLizard":
            self._enter_fleelizard()
        elif st == "CeilingHang":
            self._ceiling_enter()
        elif st == "ChaseCursor":
            self._play_enter()
        elif st == "Socialize":
            self._social_enter()
        elif st == "HelpFeed":
            self._help_enter()
        elif st == "FightThreat":
            self._fight_enter()
        elif st == "CrawlAway":
            self._crawl_enter()
        elif st == "ScoldBlocker":
            self._scold_enter()
        elif st == "EatCob":
            self._cob_enter()
        elif st == "PoleClimb":
            self._poleclimb_enter()
        elif st == "HPole":
            self._hpole_enter()
        elif st == "SeekWarmth":
            self._seekwarmth_enter()
        elif st == "StormSeekShelter":
            self._storm_enter()
        elif st == "ShelterSleep":
            self._shelter_sleep_enter()
        elif st == "SeekHPole":
            self._seekhpole_enter()
        elif st == "FetchFruit":
            self._fetch_enter()
        elif st == "AngryStone":
            from .throwfetch import StoneThrower
            self.gfx.hand_aim["l"] = None
            self.gfx.hand_aim["r"] = None
            self.stonethrow = StoneThrower(self.win, self.rng, self)
        elif st == "HuntFly":
            from .huntfly import FlyHunter
            self.gfx.hand_aim["l"] = None
            self.gfx.hand_aim["r"] = None
            self.flyhunt = FlyHunter(self.win, self.rng, self)
        elif st == "CatchFly":
            from .catchfly import FlyCatcher
            self.gfx.hand_aim["l"] = None
            self.gfx.hand_aim["r"] = None
            self.flycatch = FlyCatcher(self.win, self.rng, self)
        elif st == "ItemPlay":
            self._itemplay_enter()
        elif st == "Stunned":
            b.set_posture(False)
            b.stop_walk()
            self.gfx.stunned = True
        elif st == "Swimming":
            b.set_posture(False)
            b.stop_walk()
            self._swim_goal = None
        elif st == "Dead":
            b.die()
            self.gfx.dead = True

    def _active_mood(self):
        m = self._ext_state_moods.get(self.state)
        return m if m is not None else _STATE_TO_MOOD.get(self.state)

    def water_threat(self) -> float:
        """涨水威胁 0~1，开水恒 1，排空按残水深衰减。"""
        w = self.win
        if getattr(w, "water_surface", None) is None or w.water_y is None:
            return 0.0
        if getattr(w, "water_on", False):
            return 1.0
        depth = w._HL - w.water_y
        return max(0.0, min(1.0, depth / tuning.WATER_THREAT_SAFE_DEPTH))

    def _water_urgent(self) -> bool:
        """避水强制上吊顶判据。"""
        return ("RelocateToWall" in self._ext_states
                and self.win.tongue is not None
                and self.water_threat() > 0.5
                and self.body.energy >= tuning.CEIL_WATER_ENERGY_GATE)

    # ── mood 候选表 → 注册表（personality band）──
    def _register_mood_actions(self):
        """把 mood 候选原样登记成性格层动作：权重＝MoodArbiter 的同一套公式。"""
        for cand in self.mood.order:
            self.actions.register(ActionSpec(
                key="mood:" + cand.name, band=BAND_PERSONALITY,
                gate=self._mood_gate(cand.name), score=_MoodWeight(cand),
                start=self._mood_start(cand.name),
                tags=frozenset({TAG_PERSONALITY})))

    def _mood_gate(self, name):
        def gate(ctx):
            c = self.mood.candidates.get(name)
            if c is None:
                return False
            return bool(c.gate(self._mood_ctx_v) and c.freshness >= c.start)
        return gate

    def _mood_start(self, name):
        def start(ctx):
            return self._mood_enter(name, ctx.cursor)
        return start

    def _pick_mood(self, ctx):
        """加权抽一个 mood 候选（唯一真正掷骰的 band）。"""
        self._mood_ctx_v = self._mood_ctx()
        return self.actions.pick_weighted(ctx, tuning.MOOD_NOISE_AMP)

    def _mood_enter(self, name, cursor):
        """候选名 → 对应状态（旧 _st_idlestand 里的那条链，原样搬过来）。"""
        if name == "seek_warmth":
            self._transition("SeekWarmth")
            return True
        if name == "pole_climb":
            self._transition("PoleClimb")
            return True
        if name == "hpole":
            self._transition("SeekHPole")
            return True
        if name == "ceiling_play":
            self._wall_side = -1 if self.body.chunk1.x < self.WL / 2 else 1
            self._transition("RelocateToWall")
            return True
        if name == "ceiling_hang":
            self._ceiling_enter()
            self._transition("CeilingHang")
            return True
        if name == "play_cursor":
            self._play_enter()
            self._transition("ChaseCursor")
            return True
        if name == "socialize":
            tgt = self._nearest_peer()
            if tgt is None:
                self._idle_hold = self._roll_idle_hold()
                return True
            self._social_kind = self._social_kind_for(tgt)
            self._social_target = tgt
            self._social_left = 0        # 随机时长交给 _social_enter 掷
            if self._social_kind == "crouch_walk" and not self.body.on_pole:
                # 匍匐行走：交给现有的 CrawlAway（害怕强敌潜行）
                self._crawl_from = None
                self._crawl_left = tuning.CRAWL_AWAY_TICKS
                self._crawl_cd = T_CRAWL_RETRY
                self._break_active_controllers()
                self._transition("CrawlAway")
                return True
            self._social_enter()
            self._transition("Socialize")
            return True
        ext = self._ext_mood_states.get(name)
        if ext is not None:
            self._transition(ext)
            return True
        # idle 兜底：开发呆驻留再重抽
        self._idle_hold = self._roll_idle_hold()
        self._idle_pace()
        return True

    def _mood_ctx(self):
        """这次的 mood 判据（注册表 gate 与旧 _mood_select 共用一份）。"""
        return MoodContext(self.body.energy, self.body.temper,
                          self._climbable_pole_available(),
                          cold=self.body.cold,
                          has_warm_lamp=self._warm_lamp_available(),
                          has_hpole=self._has_hpole_available(),
                          can_ceiling_play="RelocateToWall" in self._ext_states,
                          can_ceil_hang=self._can_ceil_cling(),
                          submerged=self.body.swimming,
                          near_wall=self._near_wall(),
                          near_ceiling=self._ceiling_reachable(),
                          peer_near=self._peer_near(),
                          cursor_close=self._cursor_close(),
                          threat=self._threat_level(),
                          social_urge=self._social_urge)

    def _mood_select(self):
        return self.mood.select(self._mood_ctx())

    def _look_candidates(self, cursor):
        # 键用对象本身，避免 id() 字符串撞码
        c = []
        if cursor is not None:
            c.append(("cursor", cursor, tuning.LOOK_CURSOR_BASE, self._cursor_speed))
        for f in self.win.edibles():
            c.append((f, (f.x, f.y), tuning.LOOK_ITEM_BASE, 0.0))
        for p in self.win.poles:
            c.append((p, (p.bx, p.by), tuning.LOOK_ITEM_BASE, 0.0))
        for s in self.win.stones:
            c.append((s, (s.x, s.y), tuning.LOOK_ITEM_BASE, 0.0))
        return c

    def _ambient_look(self, cursor):
        head = (self.gfx.head.x, self.gfx.head.y)
        return self.looker.update(head, self._look_candidates(cursor), self.WL, self.HL)

    def _st_idlestand(self, cursor, disturbed):
        if self._act_idle and self._act_active():   # 平时社交动作：站着做完整段
            self._act_idle_tick()
            return
        if self._zerog():
            self._zerog_idle(cursor)
            return
        if self._exhausted:
            self._transition("LieDown")
            return
        self.gfx.look_at = self._ambient_look(cursor)
        self._storm_anxiety_tick()       # 雨前焦虑：只影响闲暇表现
        if self._idle_hold > 0:
            self._idle_hold -= 1
            self._idle_pace()
            return
        # 性格层（personality band）：候选表在注册表里，这里只查询
        mctx = ActionContext(self, cursor)
        spec = self._pick_mood(mctx)
        if spec is None or not self.actions.start_spec(spec, mctx):
            # 发呆驻留再重抽（idle 候选恒合格，理论到不了这里）
            self._idle_hold = self._roll_idle_hold()
            self._idle_pace()

    def _idle_pace(self):
        if not self.body.is_moving() and self.rng.random() < tuning.PACE_PROB * self._look_fac:
            self._pick_wander_target()

    def _scan_blocking(self):
        """一遍扫在场猫：我挡了谁的路(被顶→计时让路)、谁挡了我的路(被挡→跳/推/指)。"""
        if self._jump_over_cd > 0:
            self._jump_over_cd -= 1
        myx = self.body.chunk1.x
        # 杆上被同伴挡路：停在中间扒拉几下（+有概率指指点点）
        if (self._pole_nudge_pin is None and self._pole_nudge_cd <= 0
                and not self.grab.active and self.body.on_pole):
            self._pole_blocker = None
            for o in getattr(self.win, "pets", ()):
                if o is self.win:
                    continue
                pb = getattr(o, "body", None)
                if pb is None:
                    continue
                if (on_same_pole(self.body, pb)
                        and pole_in_the_way(self.body, pb, tuning.POLE_BLOCK_DIST)):
                    self._pole_blocker = o
                    self._pole_nudge = tuning.POLE_NUDGE_TICKS
                    break
        shover = None
        blocker = None
        for o in getattr(self.win, "pets", ()):
            if o is self.win:
                continue
            ob = getattr(o, "body", None)
            if ob is None or not ob.on_floor():      # 悬空猫不参与挡路判定
                continue
            if shover is None and blocks_path(myx, ob.chunk1.x, ob.walk_target_x,
                                              tuning.SHOVE_CONTACT_DIST):
                shover = o
            obeh = getattr(o, "behavior", None)
            ostate = obeh.state if obeh is not None else None
            if (blocker is None and ostate != "MakeWay"
                    and blocks_path(ob.chunk1.x, myx, self.body.walk_target_x,
                                    tuning.SHOVE_CONTACT_DIST)):
                blocker = o
        if shover is not None:
            self._shoved_ticks += 1
            self._makeway_of = shover
        else:
            self._shoved_ticks = 0
            self._makeway_of = None
        if blocker is not None:
            self._blocked_ticks += 1
            self._block_grace = 0
            self._last_blocker = blocker
        else:
            # 跳起来的那几帧/擦身而过会短暂判不到阻挡，别就此清零（原版也是持续贴着硬顶）
            self._block_grace += 1
            if self._block_grace > tuning.BLOCK_GRACE_TICKS:
                # 刚跳过一个人：小概率回头指指点点（性格说了算）
                if (self._jump_tries > 0 and not self._scold_now(
                        self._last_blocker,
                        tuning.BLOCKED_POINT_AFTER_JUMP
                        * (0.4 + 1.2 * self._hurry()))):
                    pass
                self._blocked_ticks = 0
                self._jump_tries = 0
                self._last_blocker = None

        tx = self._makeway_target(self._makeway_of) \
            if self._shoved_ticks >= tuning.SHOVE_YIELD_TICKS else None
        if (tx is not None and abs(tx - myx) > WALK_STOP_EPS
                and self.state in _MAKEWAY_FROM
                and not self.grab.active and not self._zerog() and not self.body.swimming
                and not self._exhausted and not self._cold_urgent()
                and self.body.on_floor()):
            self._transition("MakeWay")     # 被顶满时长 → 让路
            return True
        elif (blocker is not None and self._can_ground_blockreact()
              and self._blocked_ticks >= tuning.BLOCKED_JUMP_TICKS
              and self._jump_over_cd <= 0):
            # 有威胁时不再「性格不好就先骂」：无论性格都先跳过阻挡者自己让步（用户规格）
            if (not self._threat_present() and self._scold_now(
                    blocker, tuning.BLOCKED_POINT_FIRST_MAX
                    * (1.3 - 0.6 * self._hurry()))):
                self._blocked_ticks = 0        # 性格不好：懒得跳，先指着骂
            else:                              # 默认先跳，跳不过再推/指
                self.body.request_jump("stand", hold_ticks=tuning.JUMP_OVER_HOLD)
                self._jump_tries += 1
                self._blocked_ticks = 0
                self._jump_over_cd = tuning.JUMP_OVER_COOLDOWN
                return True
        elif (blocker is not None and self._can_ground_blockreact() and self._jump_tries > 0
              and self._blocked_ticks >= tuning.BLOCKED_PUSH_TICKS
              and self._jump_over_cd <= 0):
            self._push_blocker(blocker)     # 跳不过去 → 上手推他（推完可能回头指指点点）
            self._jump_tries = 0
            self._blocked_ticks = 0
            return True
        return False

    def _point_trait_fac(self) -> float:
        """指指点点倾向系数：暴躁 + 爱指的性格更容易指（中性 ≈ 1.0）。"""
        t = clampf(float(getattr(self.pers, "temper", 0.5)), 0.0, 1.0)
        pl = clampf(float(getattr(self.pers, "point_like", 0.5)), 0.0, 1.0)
        return ((tuning.POINT_TEMPER_LO
                 + (tuning.POINT_TEMPER_HI - tuning.POINT_TEMPER_LO) * t)
                * (0.6 + 0.8 * pl))

    def _hurry(self) -> float:
        """赶时间倾向（0 不急 ↔ 1 急着走）：被挡时先跳走、回头再指。"""
        return clampf(float(getattr(self.pers, "hurry", 0.5)), 0.0, 1.0)

    def _meat_zeal(self) -> float:
        """食性 → 打猎热情（荤 1.0 / 美食家 0.7 / 杂 0.5 / 素与特殊 0.0）。"""
        d = getattr(self.pers, "diet", None)
        if d == DIET_CARNIVORE:
            return 1.0
        if d == DIET_GOURMAND:
            return 0.7
        if d in (DIET_VEGETARIAN, DIET_SPECIAL):
            return 0.0
        return 0.5

    def _can_eat(self, f) -> bool:
        """食性闸：这本猫吃不吃 f（原版 NourishmentOfObjectEaten >= 0）。"""
        return _diet.edible(getattr(self.pers, "diet", None), f)

    def _spear_willing(self) -> bool:
        """肯不肯使矛（圣徒几乎不肯碰矛，够不着就用别的办法）。"""
        return float(getattr(self.pers, "spear_like", 1.0)) >= tuning.SPEAR_WILLING_MIN

    def _cob_spear_willing(self) -> bool:
        """肯不肯为了开爆米花去捡矛：素食猫（圣徒）只吃素，不开荚就没得吃。

        原版 SeedCob.HitByWeapon（SeedCob.cs:398）确实把圣徒排除在外（圣徒的矛
        打不开荚），这里是用户点名要求的例外：圣徒愿意拿矛敲爆米花，也敲得开。
        """
        return self._spear_willing() or not _diet.hunts_meat(self.pers.diet)

    def meat_sick(self, f) -> bool:
        """素食猫（圣徒）把荤食咽下去 → 眩晕。

        原版圣徒碰到活体/电击就吃 SaintStagger（Player.cs:3581 = Stun(t/5) 外加一阵
        抽搐）：Centipede 680、JellyFish 520、Cicada 220、Snail 800。wiki 也写明圣徒
        是严格素食者。这里取电蝉那档 220 → MEAT_SICK_STUN tick。
        """
        if not _diet.stuns(getattr(self.pers, "diet", None), f):
            return False
        return self.apply_stun(tuning.MEAT_SICK_STUN)

    def _point_prob(self, base: float) -> float:
        """按性格缩放一个指指点点概率。"""
        return clampf(base * self._point_trait_fac(), 0.0, 1.0)

    def _scold_now(self, o, base: float) -> bool:
        """本次是否改用「指指点点」代替跳跃/推挤。返回 True=已进入指指点点。"""
        if o is None or self._scold_cd > 0 or self.state not in _MAKEWAY_FROM:
            return False
        if self.rng.random() >= self._point_prob(base):
            return False
        self._blocker_target = o
        self._break_active_controllers()
        self._transition("ScoldBlocker")
        return True

    def _can_ground_blockreact(self) -> bool:
        """地面挡路反应（跳/推）的公共门禁。"""
        return (self.body.on_floor() and not self.grab.active
                and not self._zerog() and not self.body.swimming)

    def _makeway_target(self, o):
        """让路目标 x，无顶人者则 None。"""
        ob = getattr(o, "body", None) if o is not None else None
        if ob is None or ob.walk_target_x is None:
            return None
        b = self.body
        lo = WALL_MARGIN if b.walk_min is None else max(b.walk_min, WALL_MARGIN)
        hi = (self.WL - WALL_MARGIN) if b.walk_max is None else min(b.walk_max, self.WL - WALL_MARGIN)
        if hi <= lo:
            lo, hi = WALL_MARGIN, self.WL - WALL_MARGIN
        return yield_target_x(ob.chunk1.x, ob.walk_target_x, lo, hi, tuning.SHOVE_CLEAR_PAD)

    def _enter_makeway(self):
        """让路进入：走向让路目标。"""
        b = self.body
        b.set_posture(True)
        tx = self._makeway_target(self._makeway_of)
        b.walk_to(tx if tx is not None else b.chunk1.x)
        self._shoved_ticks = 0

    def _st_makeway(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._transition("Dragged")
            return
        o = self._makeway_of
        ob = getattr(o, "body", None) if o is not None else None
        if ob is not None:
            self.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
        # 退出：让到位/超时/顶人者失效
        if (not b.is_moving() or self.timer >= tuning.MAKEWAY_TIMEOUT or ob is None
                or not blocks_path(b.chunk1.x, ob.chunk1.x, ob.walk_target_x,
                                   tuning.SHOVE_CONTACT_DIST)):
            self._transition("IdleStand")
            # 让完路：小概率回头对顶人者做个社交动作（词表）
            if o is not None and not b.is_moving():
                self._idle_social_start(o, tuning.MAKEWAY_SOCIAL_P)

    # ── 一直被挡路：跳不过就推人，再回头指指点点 ──
    def _push_blocker(self, o):
        """推挡路者一把（原版贴身推挤）；推完有概率回头指指点点。"""
        ob = getattr(o, "body", None)
        if ob is None:
            return
        b = self.body
        s = 1.0 if ob.chunk0.x >= b.chunk0.x else -1.0
        ob.chunk0.vx += s * tuning.BLOCKED_PUSH_IMPULSE
        ob.chunk1.vx += s * tuning.BLOCKED_PUSH_IMPULSE * 0.6
        ob.chunk0.vy -= 0.2
        ob.chunk1.vy -= 0.1
        b.chunk0.vx -= s * tuning.BLOCKED_PUSH_RECOIL
        b.temper_shift(tuning.TEMPER_FEED * 0.05)
        self._push_left = tuning.BLOCKED_PUSH_POSE
        self._push_side = "r" if s > 0 else "l"
        self._push_x = ob.chunk0.x
        self._scold_now(o, tuning.BLOCKED_POINT_PROB)

    def _push_pose_tick(self):
        """推人姿势：手臂朝被推者伸一下（很短）。"""
        if self._push_left <= 0:
            return
        self._push_left -= 1
        if self._push_x is None:
            return
        self.gfx.hand_aim[self._push_side] = (self._push_x, self.body.chunk0.y + 4.0)
        self.gfx.hand_aim["l" if self._push_side == "r" else "r"] = None

    def _scold_enter(self):
        """回头指指点点：先转身面对挡路者，再按词表一下一下地指。"""
        b = self.body
        self._scold_left = tuning.SCOLD_TICKS
        self._scold_cd = tuning.SCOLD_CD
        b.set_posture(True)
        b.stop_walk()
        tb = getattr(self._blocker_target, "body", None)
        if tb is not None:
            b.facing = 1 if tb.chunk0.x >= b.chunk0.x else -1
        self._act_begin("scold", self._blocker_target)

    def _scold_cleanup(self):
        self._blocker_target = None
        self._act_end()

    def _st_scoldblocker(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._scold_cleanup()
            self._transition("Dragged")
            return
        tb = getattr(self._blocker_target, "body", None)
        self._scold_left -= 1
        if (tb is None or getattr(tb, "dead", False) or self._scold_left <= 0
                or abs(tb.chunk0.x - b.chunk0.x) > tuning.SCOLD_R):
            self._scold_cleanup()
            self._transition("IdleStand" if b.on_floor() else "Airborne")
            return
        b.stop_walk()
        b.facing = 1 if tb.chunk0.x >= b.chunk0.x else -1     # 回头
        self.gfx.look_at = (tb.chunk0.x, tb.chunk0.y)
        if not self._act_active():      # 被中断过：重新起手
            self._act_begin("scold", self._blocker_target)
        elif not self._act_tick():      # 一轮 1~5 下指完 → 再来一轮
            self._act_begin("scold", self._blocker_target)
        if self.timer % tuning.SOCIAL_POKE_INTERVAL == 0:
            self._poke(tb)              # 顺手扒拉

    # ── 杆上被同伴挡路：按性格分流（原版好脾气的猫先让路，坏脾气的死磕）──
    def _pole_soft(self) -> float:
        """杆上让路倾向 = 善良 − 暴躁：>0 会让路，<0 硬挤，≈0 中性。"""
        return self._pers_soft(self.win)

    @staticmethod
    def _pers_soft(pet) -> float:
        pers = getattr(getattr(pet, "cat", None), "personality", None)
        if pers is None:
            return 0.0
        k = clampf(float(getattr(pers, "kindness", 0.5)), 0.0, 1.0)
        t = clampf(float(getattr(pers, "temper", 0.5)), 0.0, 1.0)
        return k - t

    def _tip_tenure(self, pet) -> int | None:
        """pet 蹲在竖杆杆头上的时长；不在杆头则 None。"""
        pc = getattr(getattr(pet, "behavior", None), "poleclimb", None)
        if pc is None or getattr(pc, "phase", None) != "tip":
            return None
        return int(getattr(pc, "tip_ticks", 0))

    def _pole_role(self, o, tb) -> int:
        """我对 o 的杆上角色（含「杆头只许一只猫」的补判）。"""
        # 杆头只许一只猫：都在杆顶时按「谁先站上来」定先后 —— 摇摆出来的
        # 几像素高低差不算数，否则两端角色会随平衡摆动反复互换。
        mine = self._tip_tenure(self.win)
        theirs = self._tip_tenure(o)
        if mine is not None and theirs is not None:
            return 1 if (mine, id(self.win)) < (theirs, id(o)) else -1
        return pole_push_role(self.body, tb)

    def _pole_obj(self):
        """我正抱着的杆。"""
        for ctl in (self.poleclimb, self.hpole):
            p = getattr(ctl, "pole", None)
            if p is not None:
                return p
        return None

    def _pole_crowd(self) -> list:
        """同一根杆上跟我挤在同一段的全部猫（含我自己）。"""
        out = [self.win]
        for pet in getattr(self.win, "pets", ()):
            if pet is self.win:
                continue
            pb = getattr(pet, "body", None)
            if pb is None:
                continue
            if pole_in_the_way(self.body, pb, tuning.POLE_CONTEST_DIST):
                out.append(pet)
        return out

    def _pole_nudge_tick(self) -> bool:
        """返回 True=本 tick 已被接管（别再推进爬杆控制器）。

        好性格：让路（松手/跳下来）；中性：停住等待，能挪到横杆就挪过去；
        坏性格：坚持硬挤。挤够时间后同一场冲突里只随机留一只，其余让路/被挤掉。
        """
        o = self._pole_blocker
        b = self.body
        tb = getattr(o, "body", None) if o is not None else None
        if (o is None or tb is None or self._pole_nudge_cd > 0
                or not pole_in_the_way(b, tb, tuning.POLE_BLOCK_DIST * 1.6)):
            return self._pole_unfreeze()
        if self._pole_nudge_pin is None:            # 进入冲突：原地钉住 + 定下角色
            role = self._pole_role(o, tb)
            if role == 0:
                return self._pole_unfreeze()
            self._pole_nudge_pin = (b.chunk0.pinned, b.chunk1.pinned,
                                    b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y)
            # 钉住期间角色冻结：横杆上「沿杆方向」靠速度判定，会随平衡摆动来回翻，
            # 每 tick 重算会让冲突判定在 0 与非 0 之间抖，谁也分不出胜负。
            self._pole_nudge_role = role
            self._pole_nudge_t = 0
            self._pole_nudge_point = False
            self._pole_contest_t = 0
            b.stop_walk()
        else:
            role = self._pole_nudge_role
        self._pole_nudge_t += 1
        _p0, _p1, x0, y0, x1, y1 = self._pole_nudge_pin
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = c1.pinned = True                # 抱在杆上不动
        c0.x, c0.y, c0.vx, c0.vy = x0, y0, 0.0, 0.0
        c1.x, c1.y, c1.vx, c1.vy = x1, y1, 0.0, 0.0
        self.gfx.look_at = (tb.chunk0.x, tb.chunk0.y)
        soft = self._pole_soft()
        if soft >= tuning.POLE_SOFT_EPS:
            return self._pole_give_way(role)        # 好性格：让路
        if soft <= -tuning.POLE_SOFT_EPS:
            return self._pole_contest(o, tb)        # 坏性格：硬挤
        if role < 0 and self._pole_shift_to_beam():
            return True                             # 中性（被顶）：挪到横杆上
        return self._pole_contest(o, tb)            # 中性：停住等待，等有人分胜负

    def _pole_shove_tick(self, tb) -> None:
        """挤的动作：伸手贴住对方推/扒拉（原版贴身硬挤）。"""
        c0 = self.body.chunk0
        if self._pole_nudge_t % tuning.POLE_NUDGE_POKE == 0:
            self._poke(tb)
        side = "r" if tb.chunk0.x >= c0.x else "l"
        self.gfx.hand_aim[side] = (tb.chunk0.x, tb.chunk0.y)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None

    def _pole_contest(self, o, tb) -> bool:
        """坚持挤 / 停住等待：计时到点后同一场冲突只留一只（随机，两端一致）。"""
        soft = self._pole_soft()
        self._pole_contest_t += 1
        if soft <= -tuning.POLE_SOFT_EPS:
            self._pole_shove_tick(tb)               # 坏性格：一直在挤
            limit = tuning.POLE_CONTEST_TICKS
        else:
            # 中性：停住等待，尾巴上有概率改成「指指点点」
            limit = tuning.POLE_WAIT_TICKS
            if self._pole_contest_t >= limit - tuning.POLE_NUDGE_POINT_TAIL:
                if not self._pole_nudge_point:
                    self._pole_nudge_point = True
                    if self.rng.random() < tuning.POLE_NUDGE_POINT_PROB:
                        self._act_begin("scold", o)
                if self._pole_nudge_point and self._act_active():
                    if not self._act_tick():
                        self._act_begin("scold", o)
                elif self._pole_nudge_t % tuning.POLE_NUDGE_POKE == 0:
                    self._pole_shove_tick(tb)
            elif self._pole_nudge_t % tuning.POLE_NUDGE_POKE == 0:
                self._clear_hands()
        if self._pole_contest_t < limit:
            return True
        return self._pole_resolve()

    def _pole_resolve(self) -> bool:
        """挤位赛分胜负：只留一只占位，其余让路（好/中性）或被挤掉（坏）。"""
        crowd = self._pole_crowd()
        pushers = [p for p in crowd
                   if self._pers_soft(p) <= -tuning.POLE_SOFT_EPS]
        pool = pushers or crowd
        get = getattr(self.win, "pole_contest_winner", None)
        winner = get(self._pole_obj(), pool) if get is not None else pool[0]
        if winner is None or winner is self.win:
            self._pole_contest_t = 0                # 我赢：继续占住位置
            return True
        self._pole_shove_tick(getattr(winner, "body", self.body))
        if self._pole_soft() <= -tuning.POLE_SOFT_EPS:
            self._pole_knocked_off(winner)          # 坏性格被挤掉：摔下去 + 记仇
        else:
            self._pole_give_way(-1)                 # 中性让路：松手/下滑
        return True

    def _pole_give_way(self, role: int) -> bool:
        """让路：松手离杆（顶部跳下来 / 底部下滑）。"""
        b = self.body
        side = float(b.facing or 1)
        self._pole_release()
        self._pole_nudge_cd = tuning.POLE_NUDGE_CD
        c0, c1 = b.chunk0, b.chunk1
        c0.vx += side * tuning.POLE_GIVE_VX
        c1.vx += side * tuning.POLE_GIVE_VX * 0.6
        if role < 0:
            c0.vy += tuning.POLE_GIVE_VY            # 顶部：跳下来
        c1.vy += tuning.POLE_GIVE_VY * 0.5
        self._transition("Airborne")
        return True

    def _pole_knocked_off(self, winner) -> bool:
        """被挤掉：脱杆甩出去；坏脾气落地后去找挤赢的那只算账。"""
        b = self.body
        wb = getattr(winner, "body", None)
        side = 1.0
        if wb is not None:
            side = 1.0 if b.chunk0.x >= wb.chunk0.x else -1.0
            if abs(b.chunk0.x - wb.chunk0.x) < 1.0:
                side = float(b.facing or 1.0)       # 竖杆上左右重合：按朝向甩出去
        self._pole_release()
        self._pole_nudge_cd = tuning.POLE_NUDGE_CD
        c0, c1 = b.chunk0, b.chunk1
        c0.vx += side * tuning.POLE_KNOCK_VX
        c1.vx += side * tuning.POLE_KNOCK_VX * 0.6
        c0.vy += tuning.POLE_KNOCK_VY
        c1.vy += tuning.POLE_KNOCK_VY
        if self._pole_soft() <= -tuning.POLE_SOFT_EPS and winner is not None:
            self._blocker_target = winner
            self._pole_scold_on_land = True
        self._transition("Airborne")
        return True

    def _pole_shift_to_beam(self) -> bool:
        """中性让路：踩着交点挪到横杆上（原版 ClimbOnBeam+侧 → HangFromBeam）。"""
        pole = getattr(self.poleclimb, "pole", None)
        if pole is None:
            return False
        hp = cross_partner(pole, self.win.poles)
        if hp is None or hp.kind == VERTICAL:
            return False
        x = pole.x
        self._pole_release()
        self._pole_nudge_cd = tuning.POLE_NUDGE_CD
        self._pole_handoff(("h", hp, x))
        return True

    def _pole_unfreeze(self):
        """还原「停住扒拉」钉住的 chunk 状态；返回 False（=没接管本 tick）。"""
        if self._pole_nudge_pin is None:
            return False
        _p0, _p1, x0, y0, x1, y1 = self._pole_nudge_pin
        self._pole_nudge_pin = None
        self._pole_nudge = 0
        self._pole_nudge_point = False
        self._pole_contest_t = 0
        self._pole_nudge_role = 0
        self._pole_nudge_cd = tuning.POLE_NUDGE_CD
        self._act_end()
        b = self.body
        b.chunk0.pinned = False
        b.chunk1.pinned = False
        b.chunk0.x, b.chunk0.y = x0, y0
        b.chunk1.x, b.chunk1.y = x1, y1
        return False

    # ── 躲蜥蜴 ──
    def _carrying_gift(self) -> bool:
        """手上正拿着要送蜥蜴的蝉乌贼 —— 送礼优先，先不躲。"""
        f = self.body.carried_fruit
        return f is not None and getattr(f, "is_tame_food", False)

    # ── 面敌逻辑（合并旧「威胁」+「害怕」两套）──
    def _armed_in_hand(self) -> bool:
        """手上/背上**已经**有家伙（区别于「附近有得捡」）。

        矛大师只认「手里/背上的活白针」：普通矛、石头对它不是武器。
        """
        b = self.body
        if self._needle_only():
            return (self._own_needle(b.carried_spear)
                    or self._own_needle(b.back_spear))
        return (b.carried_spear is not None or b.carried_stone is not None
                or b.back_spear is not None)

    def _revive_target_safe(self, th):
        """附近倒地的同伴，且**不在威胁那一侧**（不为了一具尸体往刀口上跑）。

        原版 Player 见威胁的第一反应是远离；「贴着敌人救人」既不符合原版，
        也让人看着像送死 —— 所以尸体比我更靠近威胁时一律放弃。
        已经在救的不抢（复用 _revive_claimed_by 的认领规则）。
        """
        b = self.body
        if getattr(self.win, "is_pup", False):
            return None                     # 幼崽：不救人（也不会被救）
        my_gap = abs(th.x - b.chunk1.x)
        c1 = b.chunk1
        best, bd = None, tuning.HELPFEED_SEEK_R
        for p in self._peers():
            ob = p.body
            if getattr(p, "is_pup", False):
                continue                    # 幼崽不算救援目标
            if not self._peer_needs_help(ob) or self._revive_claimed_by(p) is not None:
                continue
            d = math.hypot(ob.chunk1.x - c1.x, ob.chunk1.y - c1.y)
            if d >= bd:
                continue
            if abs(th.x - ob.chunk1.x) < min(my_gap, tuning.FEAR_TOO_CLOSE_R * REVIVE_SAFE_PAD):
                continue                    # 尸体就贴在敌人嘴边：不去了
            best, bd = p, d
        return best

    def _face_threat_tick(self, cursor) -> bool:
        """面敌逻辑的唯一入口：迎战 / 去拿家伙 / 救人 / 撤退。

        合并了旧版互相抢班的「威胁圈」与「恐惧」两段（旧版在同一 tick 里
        重复调用 _flee_lizard_now，面对面也照躲，于是出现发呆、来回踱步）。

        规则（对照原版 Player 的恐惧圈 + Lizards 的威胁判定）：
          ① 威胁贴到 FEAR_TOO_CLOSE_R：手里有家伙、上手冷却也走完了 → 当场掷；
             否则一律先脱离接触（被逼到角落就跳过它，近处有竖杆就爬上去）。
          ② 中距离（威胁圈内）：手上/背上有家伙 → 迎战；空手但近处有矛/石头
             → 去捡（原版捡起投掷物）；勇敢的够得到敌人身上的矛 → 拔下来重投。
          ③ 空手又没家伙可拿：善良的只在「倒地的同伴不在威胁那一侧」时去救，
             其余一律朝远离威胁的方向撤 —— 不空手贴身、不面对面发呆。
          ④ 匍匐只在**真的在它背后**时才做（见 _flee_lizard_now）。

        返回 True = 本 tick 已决定；False = 让给别的欲望。
        """
        b = self.body
        if b.dead or self.grab.active or b.swimming or self._zerog():
            return False
        if self._carrying_gift():
            return False                 # 端着要送出去的蝉乌贼：不躲（原版送礼）
        th = self._threat_lizard()
        if th is None:
            return False
        if not b.on_floor():
            # 空中没有「匈匐」也没有「跳过它」这些选项：落地再决定。
            # （旧版这段也在 on_floor 里；中途插嘴会让猫在半空
            # 就定下「跑」，落地后反而不再评估，于是不会跳过蜥蜩。）
            return False
        c1 = b.chunk1
        d = abs(th.x - c1.x)
        # ① 恐慌区：先脱离接触（如果手里有家伙就回身一掷再走）
        if d <= tuning.FEAR_TOO_CLOSE_R:
            if self.state not in _FACE_PANIC_FROM:
                return False
            if (b.on_floor() and self._armed_in_hand() and b.item_ready()
                    and (b.carried_stone is not None or b.carried_spear is not None)):
                self._fight_target = th
                self._fight_left = tuning.FIGHT_TICKS
                self._break_active_controllers()
                self._transition("FightThreat")
                return True
            self._flee_lizard_now(th)
            return True
        # ② 已经在救人的：同伴一旦变成「在刀口上」（或者自己被逼到威胁边上），
        # 立刻放弃救人先撒 —— 用户口径：不为了尸体往敌人嘴上凑（旧版中距离不打断
        # Socialize，于是出现「贴着敌人救人」。）
        if (self.state == "Socialize" and self._social_kind == "revive"
                and b.on_floor() and self._revive_target_safe(th) is not self._social_target):
            self._flee_lizard_now(th)
            return True
        # ② 中距离：只在「没正事」的态里抢班
        if self.state not in _WANTS_FROM or not b.on_floor():
            return False
        if self._armed_in_hand():
            self._fight_target = th
            self._fight_left = tuning.FIGHT_TICKS
            self._break_active_controllers()
            self._transition("FightThreat")
            return True
        gw = self._nearest_ground_weapon() if b.carried_fruit is None else None
        if (gw is not None and self._arm_cd <= 0
                and math.hypot(gw.x - c1.x, gw.y - c1.y) <= tuning.ARM_SEEK_R):
            self._fight_target = th
            self._fight_left = tuning.FIGHT_TICKS
            self._arm_cd = tuning.ARM_COOLDOWN
            self._break_active_controllers()
            self._transition("FightThreat")
            return True
        brave = getattr(self.pers, "bravery", 0.5)
        if brave >= tuning.RIP_SPEAR_BRAVE and self._nearest_rip_spear(th) is not None:
            self._fight_target = th
            self._fight_left = tuning.FIGHT_TICKS
            self._break_active_controllers()
            self._transition("FightThreat")
            return True
        kind = getattr(self.pers, "kindness", 0.5)
        if (kind >= tuning.FEAR_KIND_RESCUE and self._cover_cd <= 0
                and self._cover_ally_start(th)):
            return True                  # 空手又有持械同伴：躲到它背后（落点先验距）
        if kind >= tuning.FEAR_KIND_RESCUE and self._revive_cd <= 0:
            dp = self._revive_target_safe(th)
            if dp is not None:
                self._social_kind = "revive"
                self._social_target = dp
                self._social_left = tuning.REVIVE_APPROACH_TICKS
                self._break_active_controllers()
                self._transition("Socialize")
                return True
        if self._flee_cd > 0 and self._crawl_cd > 0:
            # 跑和趴都还在冷却：这一轮中距离先不折腾（不然每帧重新起跑）
            return False
        self._flee_lizard_now(th)        # ③④ 撤退（匍匐只在真的在它背后时）
        return True

    def _pin_throw_at_cursor(self, cursor) -> bool:
        """猎手怪癖：朝光标横着掷一支矛，命中就把矛钉在光标上。

        原版没有「矛钉鼠标」（鼠标不是游戏里的对象），这是桌宠扩展出来的小玩法，
        但物理仍旧是原版那一套：矛走 Weapon.Thrown 水平掷出（setRotation =
        throwDir、不翻滚），只是飞行途中穿过光标就挂上去；甩鼠标（光标一 tick
        位移超过阈值）会把它甩下来，之后照常自由落体（见 items._step_cursor_pin）。
        """
        b = self.body
        if b.carried_spear is None and b.back_spear is not None:
            b.take_back_spear("r")           # 猎手：从背上抽矛（原版 CanRetrieveSpearFromBack）
        if b.carried_spear is None or not b.item_ready():
            return False
        cx, cy = cursor
        c0 = b.chunk0
        if abs(cy - c0.y) > tuning.PIN_CURSOR_DY:
            return False                     # 高度差超一跳：原版只能横着掷，够不到就算了
        if abs(cx - c0.x) < 24.0:
            return False                     # 贴脸掷会立刻插墙
        b.facing = 1 if cx >= c0.x else -1
        b.stop_walk()
        self.gfx.look_at = (cx, cy)
        b.carried_spear.aim_cursor = True
        b.throw_spear(b.facing, weaponphys.frc(), recoil=0.4)
        self._pincur_cd = tuning.PIN_CURSOR_CD
        self.gfx.blink = 15
        return True

    def _tongue_curiosity(self) -> float:
        """共享的「舌头动作偏好」轴（0..1）：圣徒舌钩荡跃 / 逗生物 / 吊顶都用它。

        旧版每个舌头动作各自 if 一个常量概率，谁也不知道这猫到底「爱不爱用舌头」；
        现在性格里有一个统一轴，各处都读它（见 cats/personality.py 的
        tongue_curiosity），于是爱用舌头的个体在所有舌头动作上都更活跃。
        """
        return clampf(float(getattr(self.pers, "tongue_curiosity", 0.5)), 0.0, 1.0)

    def _lick_want(self) -> float:
        """逗弄生物的概率：上限就是基准 1/8，舌头好奇心只在 0.75×~1× 之间微调。"""
        return clampf(LICK_PLAY_P * (0.75 + 0.25 * self._tongue_curiosity()), 0.0, 1.0)

    def _nearby_lizard(self):
        """水平距离最近且在威胁圈内的威胁（蜥蜴 / 愤怒的面条蝇成体）；没有则 None。"""
        x = self.body.chunk1.x
        best, bd = None, self._threat_r()
        for lz in getattr(self.win, "lizards", ()):
            if getattr(lz, "state", None) != ItemState.FREE:
                continue
            # 环境伪装（白蜥）：折算成「更远」，蛞蝓猫更晚才发现它
            d = abs(lz.x - x) * getattr(getattr(lz, "breed", None), "camo_fac", 1.0)
            if d < bd:
                best, bd = lz, d
        for f in getattr(self.win, "needleworms", ()):
            if not self._hostile_fly(f):
                continue
            d = abs(f.x - x)
            if d < bd:
                best, bd = f, d
        return best

    def _flee_target_x(self, lz) -> float:
        """逃向蜥蜴的反面，至少隔开 FLEE_GAP；夹在可行走范围内。"""
        b = self.body
        lo = WALL_MARGIN if b.walk_min is None else max(b.walk_min, WALL_MARGIN)
        hi = (self.WL - WALL_MARGIN if b.walk_max is None
              else min(b.walk_max, self.WL - WALL_MARGIN))
        if hi < lo:
            lo, hi = WALL_MARGIN, self.WL - WALL_MARGIN
        x = b.chunk1.x
        side = 1.0 if x >= lz.x else -1.0
        # 目标点 = 「从我现在的位置再往外退 FLEE_GAP」再夹进可行走范围。
        # 旧版写的是「离敌人 FLEE_GAP 的那个点」——猫本来就在 GAP 之外时，
        # 那个点反而在它和敌人之间，猫会朝敌人走过去（用户看到的「贴着敌人」）。
        return min(max(x + side * FLEE_GAP, lo), hi)

    def _flee_lizard_now(self, lz) -> None:
        """立刻躲开这只敌人：被逼到角落先跳过它，否则顺背匍匐潜走 / 掉头跑。

        对照原版：蜥蜴进恐惧圈时优先逃；匍匐只在「在它背后」时才顺手做。
        """
        b = self.body
        if self._cornered_by(lz) and self._jump_over(lz):
            self._flee_from = lz
            self._flee_cd = FLEE_COOLDOWN
            self._crawl_cd = T_CRAWL_RETRY
            self._break_active_controllers()
            self._transition("FleeLizard")
            return
        # 往高处躲：近处有竖杆 → 爬上去（离地才是真的安全）。
        # 墙爬不了（Controls：蛞蝓猫只能扶墙下滑/蹬墙跳，没有「爬上去」），
        # 只有杆是上升通道。
        if self.rng.random() < tuning.FLEE_CLIMB_P:
            pole = self._pick_climbable_pole()
            if (pole is not None
                    and abs(pole.x - b.chunk1.x) <= tuning.FLEE_POLE_R):
                self._poleclimb_pole = pole
                self._poleclimb_start = None
                self._flee_from = lz
                self._flee_cd = FLEE_COOLDOWN
                self._crawl_cd = T_CRAWL_RETRY
                self._break_active_controllers()
                self._transition("PoleClimb")
                return
        # 匍匐潜行只在**真的在它背后**时才做：原版 Player 的匍匐是「没被看见」时的
        # 潜行姿态，不是「离得远就趴下」。旧版把「距离 > CRAWL_FEAR_R*0.6」也当成
        # 趴下的条件，于是场上一有蜥蜴猫就动不动突然趴下 —— 这就是那个「喜欢突然
        # 匍匐」的来源。性格 crawl_like 只决定肯不肯趴。
        behind = self._behind_creature(lz)
        can_crawl = (self.rng.random()
                     < 0.25 + 0.75 * getattr(self.pers, "crawl_like", 0.5))
        if behind and can_crawl:
            self._crawl_from = lz
            self._crawl_left = tuning.CRAWL_AWAY_TICKS
            self._break_active_controllers()
            self._transition("CrawlAway")
            return
        self._flee_from = lz
        self._crawl_cd = T_CRAWL_RETRY
        self._break_active_controllers()
        self._transition("FleeLizard")

    def _press_reset(self):
        """被逼退记账归零（灵了、跳过了、不在地面上）。"""
        self._press_x = None
        self._press_back = 0.0
        self._press_t = 0
        self._stuck_t = 0

    def _threat_pressure_tick(self):
        """被逼退记账：连续退了多远、退了多久、贴墙卡住多久。

        只统计「敌人就在跳得过去的范围内」的 tick：猫一旦把它甩开
        （超出 FEAR_JUMP_MAX_R）就清零 —— 那是逃掉了，不是被逼退。
        """
        b = self.body
        if b.dead or self.grab.active or not b.on_floor():
            self._press_reset()
            return
        th = self._threat_lizard()
        if th is None:
            self._press_reset()
            return
        x = b.chunk1.x
        if abs(th.x - x) > tuning.FEAR_JUMP_MAX_R:
            self._press_reset()
            self._press_x = x
            return
        if self._press_x is None:
            self._press_x = x
            return
        dx = x - self._press_x
        self._press_x = x
        if abs(dx) < tuning.FEAR_STUCK_EPS:
            self._stuck_t += 1
        else:
            self._stuck_t = 0
        away = 1.0 if x >= th.x else -1.0
        if dx * away > 0.0:                  # 朝远离威胁的方向挪动
            self._press_back += abs(dx)
            self._press_t += 1
        else:
            self._press_t = 0                # 被顶回来：连续后退断掉

    def _cornered_by(self, lz) -> bool:
        """退无可退 → 回头跳过它。

        旧版只看「贴墙」与「反方向挪不动」两个瞬时几何量，于是「被一路追着
        往墙角退、退了一屏还甩不掉」的猫永远不跳。现在加三条被逼退记账
        （见 _threat_pressure_tick）：被逼退够远 ／ 够久 ／ 背后是墙又卡住；
        只要它还在一跳可及的范围内就跳。
        """
        b = self.body
        if not b.on_floor():
            return False
        gap = abs(lz.x - b.chunk1.x)
        pressed = (self._press_back >= tuning.FEAR_PRESS_DIST
                   or self._press_t >= tuning.FEAR_PRESS_TICKS
                   or (self._near_wall() and self._stuck_t >= tuning.FEAR_STUCK_TICKS))
        if pressed:
            return gap <= tuning.FEAR_JUMP_MAX_R
        if gap > tuning.FEAR_TOO_CLOSE_R:
            return False
        if self._near_wall():
            return True
        return abs(self._flee_target_x(lz) - b.chunk1.x) < tuning.FEAR_JUMP_MIN_GAIN

    def _jump_over(self, lz) -> bool:
        """面向威胁，从它头上跳到对面去（不是往墙角里跳）。

        旧版把起跳方向取成「远离敌人」，猫在墙角时那一跳实际上是撞墙；
        用户口径是「面向威胁跳过威胁到对面」——所以这里朝敌人起跳并越过它，
        落地时人已在另一侧，FleeLizard 接着往新的反方向跑。
        """
        b = self.body
        if not b.on_floor():
            return False
        cross = 1.0 if lz.x >= b.chunk1.x else -1.0
        b.facing = 1 if cross > 0 else -1
        b.move_dir = b.facing
        b.walk_target_x = None
        b.chunk0.vx = b.chunk1.vx = cross * tuning.FEAR_JUMP_VX
        b.request_jump("stand")
        self.gfx.look_at = (lz.x, lz.y)
        self._press_reset()          # 跳完重新记账：别在空中又判定「退无可退」
        return True

    def _nearest_rip_spear(self, lz=None):
        """插在蜥蜴身上、够得着的矛（勇敢的猫会拔下来重投）。"""
        best, bd = None, tuning.RIP_SPEAR_R * 2.2
        c1 = self.body.chunk1
        lizzies = getattr(self.win, "lizards", ())
        for sp in getattr(self.win, "spears", ()):
            if sp.state != ItemState.FREE or getattr(sp, "stuck_to", None) is None:
                continue
            host = sp.stuck_to[0]
            if host not in lizzies or getattr(host, "dead", False):
                continue
            if lz is not None and host is not lz:
                continue
            if self._needle_only() and not self._own_needle(sp):
                continue                    # 矛大师：不拔别人（或已变黑）的矛当武器
            d = math.hypot(sp.x - c1.x, sp.y - c1.y)
            if d < bd:
                best, bd = sp, d
        return best

    def _enter_fleelizard(self):
        b = self.body
        b.set_posture(True)
        self._flee_cd = FLEE_COOLDOWN      # 进场即计时：被咬断也算躲过一轮
        b.walk_to(self._flee_target_x(self._flee_from))

    def _st_fleelizard(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._transition("Dragged")
            return
        lz = self._flee_from
        alive = lz is not None and getattr(lz, "state", None) == ItemState.FREE
        if alive:
            self.gfx.look_at = (lz.x, lz.y)
            # 退无可退（被逼退够远／够久，或背后是墙又挪不动）：不往回
            # 跑了 —— 转身面向它，从它头上跳到对面继续逃。
            if (self._jump_over_cd <= 0 and self._cornered_by(lz)
                    and self._jump_over(lz)):
                self._jump_over_cd = tuning.JUMP_OVER_COOLDOWN
                self._flee_cd = FLEE_COOLDOWN
                b.walk_to(self._flee_target_x(lz))   # 落点已在对侧，继续往反方向跑
                return
            if self.timer % 12 == 0:              # 蜥蜴在动，隔几拍重取反方向
                b.walk_to(self._flee_target_x(lz))
        if ((not alive) or self.timer >= FLEE_MAX_TICKS or not b.on_floor()
                or abs(lz.x - b.chunk1.x) >= FLEE_SAFE_R):
            self._transition("IdleStand")

    def _zerog(self) -> bool:
        return getattr(self.body, "zerog", False)

    def _zerog_idle(self, cursor):
        """漂浮 idle：叼果啃食＞追食＞寻杆抓握赖玩＞划水漂向目标。"""
        b = self.body
        b.stop_walk()
        if b.carried_fruit is not None:
            self._zerog_eat(b)
            return
        self.gfx.look_at = self._ambient_look(cursor)
        if self._zerog_pole_cd > 0:
            self._zerog_pole_cd -= 1
        if not b.food_satisfied() and self._fetch_cooldown <= 0:
            e = self._nearest_zerog_edible()
            if e is not None:
                self._zerog_chase(b, e)
                return

        if self._zerog_entered:
            self._zerog_entered = False
            if self._zerog_pole_cd <= 0:
                pole = self._zerog_nearest_pole(b.chunk0.x, b.chunk0.y)
                if pole is not None:
                    b.zerog_pole = pole
                    b.zerog_pole_intent = (0.0, 0.0)
                    self._zerog_pole_play = 0

        if b.zerog_pole is not None:
            self._zerog_on_pole(b)
            return

        tx, ty = self._zerog_pick_target(cursor)
        dx, dy = tx - b.chunk0.x, ty - b.chunk0.y
        dist = math.hypot(dx, dy)
        if dist > ZEROG_ARRIVE_R:
            ux, uy = dx / dist, dy / dist
            if self._zerog_try_pole(b, tx, ty):
                return
            on_wall = b.canJump > 0
            b.zerog_swim(ux, uy, on_wall)
            if on_wall and dist > ZEROG_KICK_FAR:
                b.request_zerog_kick(ux, uy)
        else:
            self._zerog_target = None
            if self.rng.random() < ZEROG_TWITCH_PROB:
                ang = self.rng.uniform(0.0, math.tau)
                b.zerog_swim(math.cos(ang), math.sin(ang), b.canJump > 0)

        if (self.win.tongue is not None
                and self.win.tongue.is_idle()
                and self.rng.random() < ZEROG_LICK_PROB):
            self.win.fire_tongue(tx, ty)

    def _nearest_zerog_edible(self):
        """全房间最近可食物；飞行中蝙蝠与食性禁忌排除，无则 None。"""
        b = self.body
        best, bd = None, None
        for f in self.win.edibles():
            if f.state not in ("free", "hanging"):
                continue
            if not getattr(f, "fetch_ready", True):
                continue
            if not self._can_eat(f):
                continue
            d = math.hypot(f.x - b.chunk0.x, f.y - b.chunk0.y)
            if bd is None or d < bd:
                bd, best = d, f
        return best

    def _zerog_chase(self, b, e):
        """漂向食物，接触即抓；远距按概率吐舌加速。"""
        b.zerog_pole = None
        self.gfx.look_at = (e.x, e.y)
        dx, dy = e.x - b.chunk0.x, e.y - b.chunk0.y
        dist = math.hypot(dx, dy)
        if dist < tuning.SWIM_FETCH_REACH:
            if getattr(e, "stuck_pos", None) is not None:
                e.stuck_pos = None    # 抓取瞬间剥离黏菌
            b.grab_fruit(e)          # 槽位优先级：主手（右手）先
            self._chew_reset()
            return
        ux, uy = dx / dist, dy / dist
        b.zerog_swim(ux, uy, b.canJump > 0)
        if b.canJump > 0 and dist > ZEROG_KICK_FAR:
            b.request_zerog_kick(ux, uy)
        if (self.win.tongue is not None
                and self.win.tongue.is_idle()
                and dist > ZEROG_KICK_FAR
                and self.rng.random() < ZEROG_CHASE_LICK_PROB):
            self.win.fire_tongue(e.x, e.y)

    def _zerog_eat(self, b):
        """悬浮啃食：共用咀嚼动画，吃完由 consume_carried 结算释放。"""
        b.zerog_pole = None
        f = b.carried_fruit
        if f.state != "carried":
            b.release_fruit()
            return
        self._carry_chew(b)

    def _chew_reset(self):
        self._chew.reset()

    def _carry_chew(self, b):
        """叼果咀嚼：与普通重力路径共用同一份 ChewCycle（只有咬合点才真的咬）。"""
        f = b.carried_fruit
        self.gfx.look_at = (f.x, f.y)
        pose, bit = self._chew.tick()
        b.eat_raise = pose
        if not bit:                      # 非咬合点：只播动画，不减 bites
            return
        dx, dy = f.x - self.gfx.head.x, f.y - self.gfx.head.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            self.gfx.head.vx += dx / d * BITE_HEAD_NUDGE
            self.gfx.head.vy += dy / d * BITE_HEAD_NUDGE
        if b.consume_carried():          # 咽下去：素食猫吃荤当场晕
            self.meat_sick(f)

    def _zerog_on_pole(self, b):
        """已抓杆：滑向目标，或赖杆来回滑玩够松开。"""
        pole = b.zerog_pole
        lx, ly = pole.bx - pole.ax, pole.by - pole.ay
        ll = math.hypot(lx, ly) or 1.0
        axis_x, axis_y = lx / ll, ly / ll
        perp_x, perp_y = -axis_y, axis_x
        t = self._zerog_target
        if t is None:
            along = perp = 0.0
        else:
            rx, ry = t[0] - b.chunk0.x, t[1] - b.chunk0.y
            along = rx * axis_x + ry * axis_y
            perp = rx * perp_x + ry * perp_y
        if abs(along) > ZEROG_GRAB_ALIGN and abs(perp) <= ZEROG_GRAB_DIST:
            self._zerog_pole_play = 0
            s = 1.0 if along > 0.0 else -1.0
            b.zerog_pole_intent = (axis_x * s, axis_y * s)
            return
        self._zerog_pole_play += 1
        if self._zerog_pole_play % ZEROG_SLIDE_PERIOD == 0:
            self._zerog_slide_sign = -self._zerog_slide_sign
        b.zerog_pole_intent = (axis_x * self._zerog_slide_sign, axis_y * self._zerog_slide_sign)
        if self._zerog_pole_play >= ZEROG_POLE_PLAY_TICKS:
            b.zerog_pole = None
            self._zerog_pole_play = 0
            self._zerog_pole_cd = ZEROG_POLE_COOLDOWN

    def _zerog_nearest_pole(self, x, y):
        """chunk0 点-段距离 < GRAB_DIST 的最近杆；无则 None。"""
        best = None
        best_d = ZEROG_GRAB_DIST
        for p in self.win.poles:
            d = _closest_on_segment(x, y, p.ax, p.ay, p.bx, p.by)[2]
            if d < best_d:
                best_d = d
                best = p
        return best

    def _zerog_seek_pole(self, x, y):
        """chunk0 点-段距离 < SEEK_R 的最近杆（主动寻杆半径）；无则 None。"""
        best = None
        best_d = ZEROG_POLE_SEEK_R
        for p in self.win.poles:
            d = _closest_on_segment(x, y, p.ax, p.ay, p.bx, p.by)[2]
            if d < best_d:
                best_d = d
                best = p
        return best

    def _zerog_try_pole(self, b, tx, ty):
        """漂近杆(GRAB_DIST 内) → 抓住并给初始沿杆意图。"""
        if self._zerog_pole_cd > 0:
            return False
        pole = self._zerog_nearest_pole(b.chunk0.x, b.chunk0.y)
        if pole is None:
            return False
        lx, ly = pole.bx - pole.ax, pole.by - pole.ay
        ll = math.hypot(lx, ly) or 1.0
        axis_x, axis_y = lx / ll, ly / ll
        rx, ry = tx - b.chunk0.x, ty - b.chunk0.y
        along = rx * axis_x + ry * axis_y
        s = 1.0 if along > ZEROG_GRAB_ALIGN else (-1.0 if along < -ZEROG_GRAB_ALIGN else 0.0)
        b.zerog_pole = pole
        b.zerog_pole_intent = (axis_x * s, axis_y * s)
        self._zerog_pole_play = 0
        return True

    def _zerog_pick_target(self, cursor):
        """取/续漂移目标：已有续用，否则寻杆/光标/随机漫游点。"""
        t = self._zerog_target
        if t is not None:
            return t
        if self._zerog_pole_cd <= 0 and self.rng.random() < ZEROG_POLE_SEEK_PROB:
            b = self.body
            pole = self._zerog_seek_pole(b.chunk0.x, b.chunk0.y)
            if pole is not None:
                cx, cy, _ = _closest_on_segment(b.chunk0.x, b.chunk0.y,
                                                pole.ax, pole.ay, pole.bx, pole.by)
                self._zerog_target = (cx, cy)
                return self._zerog_target
        if cursor is not None and self.rng.random() < ZEROG_CURSOR_FRAC:
            t = (float(cursor[0]), float(cursor[1]))
        else:
            t = (self.rng.uniform(WALL_MARGIN, self.WL - WALL_MARGIN),
                 self.rng.uniform(WALL_MARGIN, self.HL - WALL_MARGIN))
        self._zerog_target = t
        return t

    def _roll_idle_hold(self) -> int:
        base = self.rng.uniform(tuning.IDLE_HOLD_MIN, tuning.IDLE_HOLD_MAX)
        mult = _lerpmap(self.body.energy, 0.0, 1.0, tuning.IDLE_HOLD_TIRED_MULT, 1.0)
        # 雨前焦虑：越焦虑越坐不住（短距离来回走、活动零碎）
        p = getattr(self.win, "storm_pressure", 0.0)
        if p > tuning.STORM_PRESSURE_LO:
            mult *= _lerpmap(p, tuning.STORM_PRESSURE_LO, 1.0, 1.0,
                             tuning.STORM_ANXIETY_HOLD_MULT)
        return int(base * mult)

    # 游泳漂游 Swimming
    def _st_swimming(self, cursor, disturbed):
        """浸水态：求生上浮优先，否则漂游或觅食。"""
        b = self.body
        if self.grab.active:
            b.swim_target = None
            self._transition("Dragged")
            return
        if not b.swimming:
            b.swim_target = None
            if b.carried_fruit is not None:
                f = b.carried_fruit
                b.release_fruit()
                f.state = "free"
            self._transition("IdleStand" if b.on_floor() else "Airborne")
            return
        self.gfx.look_at = self._ambient_look(cursor)
        ws = getattr(b, "water_surface", None)
        if self._water_escape_cd > 0:
            self._water_escape_cd -= 1
        # 缺氧求生上浮优先级最高
        if b.air_frac < b.stats.drown_threshold and ws is not None:
            b.swim_target = (b.chunk0.x, ws.level_at(b.chunk0.x) - 20.0)
            return
        # 落水自救：游到墙边舌爬出水
        if self._water_escape_ready(ws):
            wall_x = 0.0 if b.chunk0.x < self.WL * 0.5 else float(self.WL)
            if abs(b.chunk0.x - wall_x) < tuning.SWIM_ESCAPE_WALL_REACH:
                self._wall_side = -1 if wall_x == 0.0 else 1
                self._water_escape_cd = tuning.SWIM_ESCAPE_CD
                self._swim_goal = None
                b.swim_target = None
                self._transition("TongueClimb")
            else:
                b.swim_target = (wall_x, ws.level_at(b.chunk0.x) + 40.0)
            return
        if b.carried_fruit is not None:
            self._swim_eat()
            return
        if not b.food_satisfied() and self._fetch_cooldown <= 0:
            e = self._nearest_swim_edible()
            if e is not None:
                b.swim_target = (e.x, e.y)
                if math.hypot(e.x - b.chunk0.x, e.y - b.chunk0.y) < tuning.SWIM_FETCH_REACH:
                    b.grab_fruit(e)
                    self._chew_reset()
                return
        g = self._swim_goal
        if g is None or self._swim_reached(g):
            g = self._pick_swim_target(cursor, ws)
            self._swim_goal = g
        b.swim_target = g

    def _water_escape_ready(self, ws) -> bool:
        """落水自救可否起念。"""
        return (ws is not None
                and "RelocateToWall" in self._ext_states
                and self.win.tongue is not None
                and self._water_escape_cd <= 0
                and self.body.energy >= tuning.SWIM_ESCAPE_ENERGY)

    def _nearest_swim_edible(self):
        """搜寻半径内最近可食浮物，无则 None。"""
        b = self.body
        best, bd = None, tuning.SWIM_FETCH_SEEK_R
        for f in self.win.edibles():
            if f.state not in ("free", "hanging"):
                continue
            if not self._can_eat(f):
                continue    # 素食/圣徒不自主吃肉
            d = math.hypot(f.x - b.chunk0.x, f.y - b.chunk0.y)
            if d < bd:
                bd, best = d, f
        return best

    def _swim_eat(self):
        """边游边啃：悬停原地，共用咀嚼动画。"""
        b = self.body
        f = b.carried_fruit
        if f.state not in ("carried",):
            b.release_fruit()
            return
        b.swim_target = (b.chunk0.x, b.chunk0.y - 4.0)
        self._carry_chew(b)

    def _swim_reached(self, g) -> bool:
        return math.hypot(g[0] - self.body.chunk0.x, g[1] - self.body.chunk0.y) < tuning.SWIM_ARRIVE_R

    def _pick_swim_target(self, cursor, ws):
        """取漂游目标：偶尔追光标，否则水下漫游点。"""
        if cursor is not None and self.rng.random() < 0.4:
            return (float(cursor[0]), float(cursor[1]))
        x = self.rng.uniform(WALL_MARGIN, self.WL - WALL_MARGIN)
        if ws is not None:
            y = ws.level_at(x) + self.rng.uniform(tuning.SWIM_DRIFT_DEPTH_MIN,
                                                  self._swim_depth_max)
            y = min(y, self.HL - WALL_MARGIN)
        else:
            y = self.rng.uniform(WALL_MARGIN, self.HL - WALL_MARGIN)
        return (x, y)

    def _enter_exhaustion(self):
        """体力告急：中断当前动作、收舌，回地面准备趴下。"""
        self._break_active_controllers()
        self._clear_hands()
        self._transition("LieDown" if self.body.on_floor() else "Airborne")

    def _st_liedown(self, cursor, disturbed):
        if not self.body.on_floor() and not self.body.ceil_cling:
            self._transition("Airborne")     # 悬空不能趴：先落地
            return
        if self._hibernating:
            if self._too_cold_to_sleep():
                self._hibernating = False
                self._transition("WakeSequence")
                return
            if self.timer >= tuning.LIE_SETTLE_TICKS:
                self._transition("Sleep")
            return
        if self.body.energy >= tuning.EXHAUST_EXIT_ENERGY:
            self._exhausted = False
            self._transition("WakeSequence")
            return

    def _st_sleep(self, cursor, disturbed):
        if not self.body.on_floor() and not self.body.ceil_cling:
            self._transition("Airborne")     # 悬空睡不了（原版没有空中睡着）
            return
        self.gfx.sleeping = True
        self.body.sleeping = True
        if self._too_cold_to_sleep():
            self._hibernating = False
            self._transition("WakeSequence")
            return
        if self.timer >= self._sleep_left:
            self.body.energy = 1.0
            self._hibernating = False
            self._social_urge_boost(tuning.SOCIAL_URGE_BOOST_WAKE)   # 睡醒：想找人
            self._transition("WakeSequence")

    def _st_wakesequence(self, cursor, disturbed):
        b = self.body
        if self.phase == 0:
            self.gfx.sleeping = False
            b.sleeping = False
            b.set_posture(False)
            if self.gfx.sleep_curl <= 0.05:
                self.phase = 1
                b.request_jump("wake")
                b.set_posture(True)
        elif self.phase == 1:
            self._wake_stable = self._wake_stable + 1 if b.on_floor() else 0
            if self._wake_then is not None:
                if self._wake_stable > WAKE_STABILIZE_TICKS:
                    target = self._wake_then
                    self._wake_then = None
                    self._clear_hands()
                    self._transition(target)
                return
            if b.on_floor() and self.timer > 5:
                if self.rng.random() < 0.5:
                    self.phase = 2
                    self.timer = 0
                    self.point_side = 0
                else:
                    self.phase = 3
                    self.protest_left = self.rng.randint(1, 3)
                    self.timer = 0
        elif self.phase == 2:
            self.gfx.look_at = cursor
            if not self._act_active() and self._cursor_point_ok():
                self._act_begin("point", cursor, mode="cursor", enforce_side=True)
            if not self._act_tick() or self.timer >= T_POINT_WAKE:
                self._act_end()
                self._transition("IdleStand")
        elif self.phase == 3:
            if b.on_floor():
                if self.protest_left > 0 and self.timer > 16:
                    b.request_jump("protest")
                    self.protest_left -= 1
                    self.timer = 0
                elif self.protest_left <= 0 and self.timer > 16:
                    self._transition("IdleStand")

    def _st_dragged(self, cursor, disturbed):
        self._clear_hands()
        self._drag_reach_tick(cursor)     # 贴到杆/食物旁边就自己抓住
        ch = self.grab.chunk
        if ch is not None and math.hypot(ch.vx, ch.vy) > tuning.TEMPER_SWING_SPEED:
            self.body.temper_shift(tuning.TEMPER_SWING_RATE)
        if self.drag_takeover is not None and self.drag_takeover(self.grab.frames):
            return
        if not self.grab.active:
            self._drag_release()
            return
        self._struggle_tick(cursor)

    def _shake_drop_tick(self):
        """被鼠标抓着剧烈左右摇晃 → 每次抖掉一件（石头 < 果子 < 矛）。"""
        if self._shake_cd > 0:
            self._shake_cd -= 1
        ch = self.grab.chunk
        if ch is None or not self.body.hand_items():
            self._shake_flips = 0
            self._shake_hold = 0
            return
        if self._shake_hold > 0:
            self._shake_hold -= 1
        else:
            self._shake_flips = 0
            self._shake_dir = 0
        vx = ch.vx
        if abs(vx) < tuning.DRAG_SHAKE_SPEED:
            return
        d = 1 if vx > 0 else -1
        if d != self._shake_dir:
            if self._shake_dir != 0:
                self._shake_flips += 1
            self._shake_dir = d
            self._shake_hold = tuning.DRAG_SHAKE_WINDOW
        if self._shake_flips < tuning.DRAG_SHAKE_FLIPS:
            return
        if self._shake_cd > 0:
            return                     # 冷却中：计数保留，冷却一过立刻掉
        self._shake_flips = 0
        self._shake_cd = tuning.DRAG_SHAKE_CD
        self._drag_cd = max(self._drag_cd, tuning.DRAG_SHAKE_CD)   # 刚被摇掉，别再一把抓回
        self._shake_drop_one(ch)

    def _shake_drop_one(self, ch):
        """甩掉优先级最低的一件，并带走摆动速度（同原版丢物品）。"""
        b = self.body
        items = b.hand_items()               # 两只手各一支矛也算两件
        if not items:
            return
        side = min(items, key=lambda s: b.ITEM_PRIO.get(b.held_kind(s), 0))
        item = items[side]
        b._release_item_at(side, to_free=True)
        if item is not None:
            item.vx = ch.vx * tuning.DRAG_SHAKE_THROW
            item.vy = ch.vy * tuning.DRAG_SHAKE_THROW - 1.0
            self.win.add_spark(item.x, item.y, 0.0, -1.0, white=True, life=30)
        b.temper_shift(tuning.DRAG_SHAKE_TEMPER)

    def _drag_reach_tick(self, cursor):
        """被鼠标抓着时：手碰到杆/食物就自己抓上去（松手就抓牢/把果子拽下来）。"""
        b = self.body
        if self._drag_cd > 0:
            self._drag_cd -= 1
        if b.has_free_hand() and self._drag_cd <= 0 and self._drag_grab_item():
            self._drag_cd = tuning.DRAG_REACH_CD
            return
        p = self._drag_reach_pole()
        self._drag_pole = p
        if p is not None:
            px, py, _d = self._pole_near_point(p)
            side = "r" if px >= b.chunk0.x else "l"
            self.gfx.hand_aim[side] = (px, py)       # 伸手抱杆
            self.gfx.hand_aim["l" if side == "r" else "r"] = None
            self.gfx.look_at = (px, py)

    def _drag_grab_item(self) -> bool:
        """够得着就抓最近的果子 / 矛 / 石头（原版：手碰到就抓，抓着不撒手）。"""
        b = self.body
        for kind, items in (("fruit", getattr(self.win, "fruits", ())),
                            ("spear", getattr(self.win, "spears", ())),
                            ("stone", getattr(self.win, "stones", ()))):
            best, bd = None, tuning.DRAG_REACH_R
            for it in items:
                if getattr(it, "state", None) not in (ItemState.FREE, ItemState.HANGING):
                    continue
                if getattr(it, "pinned", False):   # 钉住的矛拉不动
                    continue
                if getattr(it, "held_by_hand", None) is not None:
                    continue
                d = min(self._reach_dist(b.chunk0, it), self._reach_dist(b.chunk1, it))
                if d < bd:
                    best, bd = it, d
            if best is None:
                continue
            if kind == "fruit":
                b.grab_fruit(best, snap_stalk=False)   # 摘取类：拖走才把果子拽下来
            elif kind == "spear":
                b.grab_spear(best)
            else:
                b.grab_stone(best)
            return True
        return False

    @staticmethod
    def _reach_dist(chunk, item) -> float:
        return math.hypot(item.x - chunk.x, item.y - chunk.y)

    def _pole_near_point(self, p):
        """杆上离本猫最近的点 (x, y) 与距离：竖杆按 y 夹、横杆按 x 夹。"""
        from ..world.pole import HORIZONTAL
        b = self.body
        if p.kind == HORIZONTAL:
            lo, hi = (p.ax, p.bx) if p.ax <= p.bx else (p.bx, p.ax)
            x = min(max(b.chunk0.x, lo), hi)
            y = p.ay
        else:
            lo, hi = (p.ay, p.by) if p.ay <= p.by else (p.by, p.ay)
            x = p.bx
            y = min(max(b.chunk0.y, lo), hi)
        d = min(math.hypot(x - b.chunk0.x, y - b.chunk0.y),
                math.hypot(x - b.chunk1.x, y - b.chunk1.y))
        return x, y, d

    def _drag_reach_pole(self):
        """够得着的杆（原版贴杆就能抱）：竖杆横杆都算。"""
        best, bd = None, tuning.DRAG_POLE_R
        for p in getattr(self.win, "poles", ()):
            _x, _y, d = self._pole_near_point(p)
            if d < bd:
                best, bd = p, d
        return best

    def _drag_release(self):
        """松手：抱着杆 → 抓牢杆子（竖杆爬上去 / 横杆就地挂住）；在顶部放下 → 抓住上边缘；否则自由落。"""
        p = self._drag_pole
        self._drag_pole = None
        from ..world.pole import VERTICAL
        if p is not None and p in getattr(self.win, "poles", ()):
            px, _py, d = self._pole_near_point(p)
            if d <= tuning.DRAG_POLE_R * 1.2:        # 松手那一刻还在杆边才算抱住
                if p.kind == VERTICAL:
                    self._pole_handoff(("v", p, "climb"))   # 原版：贴杆松手即抓牢
                else:
                    self._pole_handoff(("h", p, px))        # 横杆：就地挂上去
                return
        if (self._can_ceil_cling() and self._ceiling_reachable()
                and self.body.wall_cd <= 0):
            self._ceil_placed = True     # 鼠标放到顶边 → 吊住（只有圣徒能）
            self._transition("CeilingHang")
            return
        self._transition("Airborne")

    def _struggle_tick(self, cursor):
        """被抓着时偶尔挣扎：扒鼠标、蹬腿扭身、心烦值上升、掉体力。"""
        b = self.body
        if self._struggle_left > 0:
            self._struggle_left -= 1
            if cursor is not None:
                if not self._act_active():
                    self._act_begin("point", cursor, mode="cursor")
                self._act_tick()
            if self._struggle_left % 6 == 0:
                self._struggle_kick()
            if self._struggle_left <= 0:
                self._act_end()
            return
        if self.grab.frames < tuning.DRAG_STRUGGLE_MIN_FRAMES:
            return
        p = tuning.DRAG_STRUGGLE_PROB
        if b.temper > 0.2:
            p *= 2.0                       # 本来就不爽：挣得更凶
        if b.energy < 0.3:
            p *= 0.4                       # 没力气了：挣不动
        if self.rng.random() < p:
            self._struggle_left = self.rng.randint(tuning.DRAG_STRUGGLE_TICKS_MIN,
                                                   tuning.DRAG_STRUGGLE_TICKS_MAX)
            b.temper_shift(tuning.DRAG_STRUGGLE_TEMPER)
            b.energy_change(-tuning.DRAG_STRUGGLE_COST)

    def _struggle_kick(self):
        """蹬腿：给没被抓住的那截一个短促冲量（垂直身体轴左右甩，尾巴跟着甩）。"""
        ch = self.grab.chunk
        if ch is None:
            return
        free = self.body.chunk1 if ch is self.body.chunk0 else self.body.chunk0
        dx, dy = free.x - ch.x, free.y - ch.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            dx, dy, d = 0.0, 1.0, 1.0
        k = tuning.DRAG_STRUGGLE_KICK
        side = -1.0 if (self._struggle_left // 6) % 2 == 0 else 1.0   # 一左一右地甩
        free.vx += dy / d * k * side
        free.vy += -dx / d * k * side * 0.45 + k * 0.35               # 顺带往下蹬
        sp = math.hypot(free.vx, free.vy)
        if sp > tuning.DRAG_STRUGGLE_VMAX:
            q = tuning.DRAG_STRUGGLE_VMAX / sp
            free.vx *= q
            free.vy *= q
        self.gfx.look_at = (ch.x, ch.y)

    # ── 空中：带方向跳杆 / 抓杆 / 抓飞虫 ──
    def _air_steer_pole(self) -> None:
        """带方向跳杆：空中朝目标杆漂（原版 jump-pole-hopping 的空中微调）。"""
        p = self._air_pole_target
        if p is None:
            return
        if self.body.on_floor():
            self._air_pole_target = None
            return
        px = (p.x if getattr(p, "kind", None) == "vertical"
              else (p.ax + p.bx) * 0.5)
        c0 = self.body.chunk0
        if px > c0.x + 1.0:
            self.body.move_dir = 1
        elif px < c0.x - 1.0:
            self.body.move_dir = -1

    def _air_pole_grab(self) -> bool:
        """空中抓住杆子：贴杆即抓，抓到就转攀爬/吊杆（原版空中抓 beam）。"""
        b = self.body
        c0 = b.chunk0
        tgt = self._air_pole_target
        # 让路/被挤掉之后这阵子不抓路过的杆，否则刚松开又贴回来（挤位永远分不出胜负）
        if tgt is None and self._pole_nudge_cd > 0:
            return False
        for p in self.win.poles:
            if tgt is not None and p is not tgt:
                continue
            if p is self._left_pole and self._air_pole_cd > 0:
                continue                      # 刚放开的杆别立刻抓回来（防粘杆）
            if getattr(p, "kind", None) == "vertical":
                top, bot = min(p.ay, p.by), max(p.ay, p.by)
                if not (abs(c0.x - p.x) <= tuning.POLE_AIRGRAB_R
                        and top - tuning.POLE_AIRGRAB_PAD <= c0.y
                        <= bot + tuning.POLE_AIRGRAB_PAD):
                    continue
                self._air_pole_target = None
                self._poleclimb_pole = p
                self._poleclimb_start = None
                self._transition("PoleClimb")
                return True
            lo, hi = min(p.ax, p.bx), max(p.ax, p.bx)
            if not (lo - tuning.POLE_AIRGRAB_PAD <= c0.x <= hi + tuning.POLE_AIRGRAB_PAD
                    and abs(c0.y - p.ay) <= tuning.HPOLE_AIRGRAB_Y):
                continue
            self._air_pole_target = None
            self._hpole_pole = p
            self._hpole_start = "hang"
            self._hpole_start_x = c0.x
            self._transition("HPole")
            return True
        return False

    def _air_catch_fly(self) -> bool:
        """空中徒手抓住飞虫（蝙蝠/蝉乌贼/幼面条蝇）：贴到手边就抓（原版上手抓）。"""
        if not _diet.hunts_meat(self.pers.diet):
            return False
        b = self.body
        if b.carried_fruit is not None:
            return False
        c0 = b.chunk0
        for f in (*self.win.batflies, *self.win.squidcadas, *self.win.needleworms):
            if not getattr(f, "catchable", False):
                continue
            side = b.pick_hand("fruit")
            if side is None:
                continue
            hx, hy = b._carry_pos(side)
            if math.hypot(hx - f.x, hy - f.y) > tuning.CATCH_REACH:
                continue
            b.grab_fruit(f, side)
            self._transition("CatchFly")
            if self.flycatch is not None:      # 已经到手：直接进「拿着」相，别再追
                self.flycatch.target = f
                self.flycatch.phase = "hold"
                self.flycatch.timer = 0
            return True
        return False

    def _air_catch_item(self) -> bool:
        """空中伸手摘路过的东西（果子/珍珠/种子…）——原仓库版那种空中互动。

        原版蛞蝓猫在空中本来就能上手抓（Player.cs 抓住判据不看是否踩地），
        杆上跳起来摘我们已经有；这里补上「下落途中路过就顺手摘」。
        """
        b = self.body
        if b.carried_fruit is not None or self.grab.active:
            return False
        side = b.pick_hand("fruit")
        if side is None:
            return False
        hx, hy = b._carry_pos(side)
        items = [*self.win.fruits, *self.win.seeds, *self.win.slimemolds]
        if self.win.pearls:
            items += self.win.pearls
        if not b.flower_karma and self.win.karmaflowers:
            items += self.win.karmaflowers
        for f in items:
            if getattr(f, "state", None) not in ("free", "hanging"):
                continue
            if not self._can_eat(f):
                continue
            if math.hypot(f.x - hx, f.y - hy) > tuning.GRAB_REACH:
                continue
            if getattr(f, "stuck_pos", None) is not None:
                continue                     # 还粘在黏菌/植株上：空中顺手摘不到
            b.grab_fruit(f, side)
            return True
        return False

    def _st_airborne(self, cursor, disturbed):
        b = self.body
        if self._hp_jump_grab():         # 杆上跳起来摘到了：交回取食流程
            return
        self._air_catch_item()           # 空中顺手摘路过的东西
        self._air_throw()                # 空中投矛
        if self._air_pole_cd > 0:
            self._air_pole_cd -= 1
        self._air_steer_pole()           # 带方向跳杆：空中朝目标杆漂
        if self._air_catch_fly() or self._air_pole_grab():
            return                       # 空中抓到飞虫 / 贴到杆上
        sp = math.hypot(b.chunk1.vx, b.chunk1.vy) + math.hypot(b.chunk0.vx, b.chunk0.vy)
        on_ceil = (not b.on_floor() and b.wall_cd <= 0 and sp < tuning.CEIL_SETTLE_SPEED
                   and self._can_ceil_cling()
                   and (edgeqm.on_ceiling(b) or self._ceiling_reachable()))
        if (b.on_floor() and sp < 1.2 and b.chunk0.y < b.chunk1.y - 2) or on_ceil:
            self._settle += 1
        else:
            self._settle = 0
        if self._settle >= 4:
            self._hp_jump_goal = None
            if on_ceil:
                self._transition("CeilingHang")     # 窗口顶部当平地：吊住
                return
            if self._pole_scold_on_land and self._blocker_target is not None:
                # 杆上被挤掉：落地就去找挤赢的那只指指点点（性格不好才记仇）
                self._pole_scold_on_land = False
                self._transition("ScoldBlocker")
                return
            self._transition("LieDown" if self._exhausted else "IdleStand")

    def _st_postthrowwander(self, cursor, disturbed):
        self._postthrow_point(cursor)
        if not self.body.is_moving():
            self._pick_wander_target()
        if self.anger <= T_POSTTHROW_STAND:
            self._clear_hands()
            self._transition("PostThrowStand")

    def _st_postthrowstand(self, cursor, disturbed):
        self.gfx.look_at = cursor
        self._postthrow_point(cursor)
        if self.anger <= 0:
            self._clear_hands()
            self._transition("IdleStand")

    def _st_dead(self, cursor, disturbed):
        self._clear_hands()
        self.gfx.face(False, PRIO_FORCE)    # 尸体不挂表情
        # 死亡不再自行复活：只有同伴用特殊表情扒拉（_nuzzle 触碰累计）或
        # 环境致死转世（_reincarnate）才会回来。
        if self._revive_timer > 0:
            # 暴雨期间冻结环境致死的自动复活/转生倒计时。
            # 救援复活例外：_social_revive 在成功按压后会清掉 _reincarnate。
            if getattr(self.win, "storm_active", False) and self._reincarnate:
                return
            self._revive_timer -= 1
            if self._revive_timer <= 0:
                if self._reincarnate:
                    # 转世：window 下 tick 顶部中央 respawn
                    self._reincarnate = False
                    self.win._reincarnate_pending = True
                    return
                self.body.revive()
                self._flower_planted = False     # 复活了：以后再死可以再长一朵
                self.gfx.dead = False
                self.gfx.sleeping = False
                self.body.sleeping = False
                self.gfx.sleep_curl = 0.0
                self.body.set_posture(False)
                # 被同伴救活：醒来后去拍拍恩人（感谢）
                rv = self._reviver
                if (rv is not None and getattr(rv, "body", None) is not None
                        and not rv.body.dead):
                    self._thank_target = rv
                    self._thank_t = tuning.THANK_TICKS
                self._reviver = None
                self._transition("WakeSequence")

    def _st_stunned(self, cursor, disturbed):
        self._clear_hands()
        if self.body.stun <= 0:
            self.gfx.stunned = False
            self.body.set_posture(True)
            if self.stun_takeover is not None and self.stun_takeover():   # 苏醒接管：超度反击
                return
            self.anger = ANGER_TOTAL
            self._transition("PostThrowWander")

    def _track_cursor(self, cursor):
        if self._relick_cooldown > 0:
            self._relick_cooldown -= 1
        inst = 0.0
        if cursor is not None and self._cursor_prev is not None:
            inst = math.hypot(cursor[0] - self._cursor_prev[0],
                              cursor[1] - self._cursor_prev[1])
        self._cursor_speed = self._cursor_speed * 0.5 + inst * 0.5
        in_band = (cursor is not None
                   and self.HL * LICK_BAND_LO <= cursor[1] <= self.HL * LICK_BAND_HI)
        if in_band and inst < LICK_DWELL_TOL:
            self._dwell += 1
        else:
            self._dwell = 0
        # 鼠标停在猫附近才算「值得指」：远处划过/扫过不算
        c0 = self.body.chunk0
        near = (cursor is not None
                and math.hypot(cursor[0] - c0.x, cursor[1] - c0.y) <= tuning.CURSOR_NEAR_R)
        if near:
            # 只要在附近待着就算（划过来扫一下也会待够，不需要鼠标一动不动）
            self._cursor_dwell += 1
        else:
            self._cursor_dwell = 0
        self._cursor_prev = cursor

    def _peer_dragged(self, peer=None) -> bool:
        """同伴是否正被鼠标抓着（拖着别的猫时更容易被指指点点）。"""
        if peer is not None:
            gr = getattr(getattr(peer, "behavior", None), "grab", None)
            return bool(gr is not None and gr.active)
        for p in getattr(self.win, "pets", ()):
            if p is self.win:
                continue
            gr = getattr(getattr(p, "behavior", None), "grab", None)
            if gr is not None and gr.active:
                return True
        return False

    def _cursor_point_ok(self) -> bool:
        """鼠标得在猫附近停够久才允许指它；拖着别的猫时门槛降低。"""
        need = float(tuning.CURSOR_POINT_DWELL)
        if self._peer_dragged():
            need *= tuning.DRAGGED_PEER_POINT_FAC
        return self._cursor_dwell >= need

    def _pick_wander_target(self):
        lo = WALL_MARGIN if self.body.walk_min is None else max(self.body.walk_min, WALL_MARGIN)
        hi = ((self.WL - WALL_MARGIN) if self.body.walk_max is None
              else min(self.body.walk_max, self.WL - WALL_MARGIN))
        if hi <= lo:
            lo, hi = WALL_MARGIN, self.WL - WALL_MARGIN
        others_x = [o.body.chunk1.x for o in getattr(self.win, "pets", ())
                    if o is not self.win and getattr(o, "body", None) is not None]
        x = pick_social_wander_x(lo, hi, self.body.chunk1.x, others_x,
                                 self.pers.sociability, self.rng,
                                 self.WL * tuning.SOCIAL_WANDER_SIGMA_FRAC,
                                 tuning.SOCIAL_WANDER_SAMPLES,
                                 tuning.SOCIAL_WANDER_LO, tuning.SOCIAL_WANDER_HI,
                                 tuning.SOCIAL_WANDER_MOVE_W, tuning.SOCIAL_WANDER_CROSS_W,
                                 tuning.SOCIAL_WANDER_STAY_GAIN,
                                 self.WL * tuning.SOCIAL_WANDER_STAY_SPAN_FRAC)
        x = self._storm_wander_bias_x(x, lo, hi)
        self.body.walk_to(x)

    def _point_at_cursor(self, cursor, enforce_side=False, cover=False):
        self._point_stopped = False
        if cursor is None:
            self._clear_hands()
            return
        b = self.body
        cx, cy = cursor
        spine_ang = self.gfx.body_axis()
        slx, sly = self.gfx._shoulder(-1.0, spine_ang)
        srx, sry = self.gfx._shoulder(+1.0, spine_ang)
        dl = math.hypot(cx - slx, cy - sly)
        dr = math.hypot(cx - srx, cy - sry)
        side = "l" if dl <= dr else "r"
        sx, sy = (slx, sly) if side == "l" else (srx, sry)
        sgn = 1 if cx >= b.chunk0.x else -1
        if enforce_side:
            if self.point_side == 0:
                self.point_side = sgn
            elif sgn != self.point_side:
                self._point_stopped = True
                self._clear_hands()
                return
        ty = max(cy, self.gfx.head.y - 6.0)
        tx = cx
        if cover and math.hypot(cx - sx, cy - sy) <= ARM_REACH_NEAR:
            tx, ty = cx, max(cy, self.gfx.head.y - 6.0)
        self.gfx.hand_aim[side] = (tx, ty)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None

    def _postthrow_point(self, cursor):
        """投掷后仍举着手瞄着鼠标（原版 40px 内松手），只是「指向」不是指指点点。"""
        self.gfx.face_special = False
        if cursor is None:
            self._clear_hands()
            return
        d = math.hypot(cursor[0] - self.body.chunk0.x, cursor[1] - self.body.chunk0.y)
        if d > ARM_REACH_FAR:
            self._clear_hands()
        else:
            self._aim_act(cursor, "cursor", cover=(d <= ARM_REACH_NEAR))

    def _clear_hands(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    def _climbable_pole_available(self) -> bool:
        """此刻真有一根「我用得上的竖杆」——不是「世界上存在竖杆」。

        旧版是 any(p.kind == "vertical")：猫在 x=100、杆在 x=900 也算可爬，
        于是杆一多就出现「爬上去 → 发现地面更近 → 下来 → 再爬」。统一走
        planner.reachable_transports（横距 + 纵向跨度双重判定），Mood / 取食 /
        玩杆共用同一份结果（见 planning/planner.py）。
        """
        return bool(self.planner.reachable_transports(("vertical",)))

    def _pole_in_reach(self, p) -> bool:
        """够得着这根杆：横距在够取圈内，且身体高度落在杆的纵向跨度内。

        光标虚杆悬空、底部不接地：鼠标抬高时地面上的猫够不着它，
        既不该选它去爬，也不该为它白跑一趟。
        """
        return self.planner.transport_in_reach(p)

    def _pick_climbable_pole(self):
        best = None
        hx = self.body.chunk1.x
        for p in self.planner.reachable_transports(("vertical",)):
            if best is None or abs(p.bx - hx) < abs(best.bx - hx):
                best = p
        return best

    def _pole_eat(self) -> bool:
        """杆上进食：手里的东西跟着手走，饿了就在杆上咬几口（原版 beam 上也能咬）。"""
        b = self.body
        f = b.carried_fruit
        if f is None:
            return False
        b._apply_carry()                    # 跟手：爬杆时手里的东西不能掉在半空
        if b.food >= b.food_max or not getattr(f, "is_edible", True):
            return False
        self.gfx.face_special = False
        self._carry_chew(b)
        return True

    def _hand_reach_dist(self, o) -> float:
        """手够得着的距离：躯干两节 + 两只手的真实位置取最近。

        杆上站立时 chunk0 在身体中段、离目标常比手远十几像素（手在身侧偏下），
        只量 chunk0 会把「其实抓得到」判成够不到 → 上杆走到位却发呆。
        """
        b = self.body
        d = min(math.hypot(o.x - b.chunk0.x, o.y - b.chunk0.y),
                math.hypot(o.x - b.chunk1.x, o.y - b.chunk1.y))
        for side in ("l", "r"):
            hx, hy = b._carry_pos(side)
            d = min(d, math.hypot(o.x - hx, o.y - hy))
        return d

    def _pole_release_any(self):
        """松开当前抱着的杆（横杆/竖杆通用）——离开杆之前统一走这里。"""
        if self.hpole is not None:
            self._hpole_release()
        else:
            self._pole_release()

    def _pole_reach_pickups(self) -> bool:
        """站在杆上伸手也能做的事：捡够得到的矛/石头（有威胁又肯用矛）、徒手抓飞虫。

        原版杆上（StandOnBeam / ClimbOnBeam）照样能捡东西、上手抓飞虫——杆只是脚下的地面。
        """
        b = self.body
        if self.grab.active or b.carried_fruit is not None:
            return False
        if b.carried_spear is None and b.carried_stone is None \
                and self._threat_present() and self._spear_willing():
            o = self._nearest_ground_weapon()
            if o is not None and self._hand_reach_dist(o) <= tuning.GRAB_REACH:
                from ..world.spear import Spear
                side = b.pick_hand("spear" if isinstance(o, Spear) else "stone")
                if side is not None:
                    b.reach_for(o, side)
                    if isinstance(o, Spear):
                        b.grab_spear(o, side)
                    else:
                        b.grab_stone(o, side)
                    self._act_end()
                    return True
        f = self._nearest_catchable()
        if f is not None and self._hand_reach_dist(f) <= tuning.CATCH_REACH:
            side = b.pick_hand("fruit")
            if side is not None:
                b.grab_fruit(f, side)
                self._pole_release_any()        # 抓着虫松杆落下去（同原版空中上手抓）
                self._transition("CatchFly")
                if self.flycatch is not None:   # 已经到手：直接进「拿着」相
                    self.flycatch.target = f
                    self.flycatch.phase = "hold"
                    self.flycatch.timer = 0
                return True
        return False

    def _poleclimb_enter(self):
        from .pole_climb import PoleClimber
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        pole = self._poleclimb_pole
        start = self._poleclimb_start
        self._poleclimb_pole = None
        self._poleclimb_start = None
        if pole is None:
            pole = self._pick_climbable_pole()
        self.poleclimb = (PoleClimber(self.win, pole, self.rng, start=start)
                          if pole is not None else None)

    def _st_poleclimb(self, cursor, disturbed):
        if self.grab.active:
            self._pole_release()
            self._transition("Dragged")
            return
        if self.poleclimb is None or self.poleclimb.pole not in self.win.poles:
            on_floor = self.body.on_floor()
            self._pole_release()
            self._transition("IdleStand" if on_floor else "Airborne")
            return
        if self._pole_nudge_tick():      # 被同伴挡在杆上：停住扒拉/指指点点
            return
        if self._pole_throw():           # 杆上持械遇敌：就地掷出（原版杆上可投掷）
            return
        if self._pole_eat():             # 手里有吃的：先在杆上吃完
            return
        if self._pole_reach_pickups():   # 杆上伸手：捡矛/石头、徒手抓飞虫
            return
        # 有明确的横杆食物目标：爬到交点就 100% 换那根横杆（不再等随机换杆）
        target_hp = self._hpole_target_for_food()
        if target_hp is not None:
            from ..world.pole import cross_partner
            vp = self.poleclimb.pole
            hp = cross_partner(vp, self.win.poles)
            if (hp is target_hp
                    and abs(self.body.chunk0.y - hp.ay) <= tuning.CROSS_PAD):
                self._pole_release()
                self._pole_handoff(("h", hp, vp.x))
                return
        if self._pole_tip_grab():        # 杆上够得着的东西：伸手摘（同横杆）
            return
        if self._pole_leave_for_food():  # 杆上等同地面：有别的更想吃的就下杆去拿
            return
        want_dismount = self.body.energy <= tuning.TIP_TIRED_ENERGY
        done = self.poleclimb.update(want_dismount)
        if done:
            air_t = self.poleclimb.air_target
            ho = self.poleclimb.handoff
            if ho is not None:
                self._pole_release()
                self._pole_handoff(ho)
                return
            giveup = self.poleclimb.giveup
            on_floor = self.body.on_floor()
            self._pole_release()
            if air_t is not None:
                self._air_pole_target = air_t
            self._transition("IdleStand" if (giveup or on_floor) else "Airborne")

    def _pole_handoff(self, ho):
        """交叉杆横↔竖切换 / 跳到另一根竖杆（原版 Controls/Pole_Movement）。"""
        from .pole_climb import PoleClimber
        kind, pole, arg = ho
        if kind == "h":
            self._hpole_pole = pole
            self._hpole_start = "hang"
            self._hpole_start_x = arg
            self._transition("HPole")
            return
        if self.state == "PoleClimb":
            self.poleclimb = PoleClimber(self.win, pole, self.rng, start=arg)
            self.timer = 0
            return
        self._poleclimb_pole = pole
        self._poleclimb_start = arg
        self._transition("PoleClimb")

    def _pole_release(self):
        self._pole_nudge_pin = None
        self._pole_nudge = 0
        self._pole_nudge_point = False
        self._pole_blocker = None
        self._act_end()
        if self.poleclimb is not None:
            self._left_pole = self.poleclimb.pole
            self._air_pole_cd = tuning.AIR_POLE_CD
            self.poleclimb.release()
            self.poleclimb = None
        self.body.chunk0.pinned = False
        self.body.chunk1.pinned = False
        self.body.on_pole = False
        self.body.animation = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    def _horizontal_pole_near(self, cursor):
        if cursor is None:
            return None
        cx, cy = cursor
        for p in self.win.poles:
            if p.kind != "horizontal":
                continue
            lo, hi = (p.ax, p.bx) if p.ax <= p.bx else (p.bx, p.ax)
            if lo <= cx <= hi and abs(cy - p.ay) <= HPOLE_NEAR_Y:
                return p
        return None

    def _hpole_enter(self):
        from ..world.hpole import HPoleController
        pole = self._hpole_pole
        start = self._hpole_start
        start_x = self._hpole_start_x
        self._hpole_pole = None
        self._hpole_start = None
        self._hpole_start_x = None
        self.hpole = (HPoleController(self.win, pole, self.rng, start=start, start_x=start_x)
                      if pole is not None else None)
        if self.hpole is not None and self._hp_goal_x is not None:
            self.hpole.goal_x = max(min(pole.ax, pole.bx) + 2.0,
                                    min(max(pole.ax, pole.bx) - 2.0, self._hp_goal_x))
            g = self._hp_goal_obj
            gy = (getattr(g, "y", None) if g is not None else None)
            self.hpole.want = (float(self._hp_goal_x),
                               float(pole.ay if gy is None else gy))

    def _st_hpole(self, cursor, disturbed):
        if self.grab.active:
            self._hpole_release()
            self._transition("Dragged")
            return
        if self.hpole is None or self.hpole.pole not in self.win.poles:
            self._hpole_release()
            self._transition("IdleStand" if self.body.on_floor() else "Airborne")
            return
        if self._pole_nudge_tick():      # 被同伴挡在杆上：停住扒拉/指指点点
            return
        if self._pole_throw():           # 杆上持械遇敌：就地掷出（原版杆上可投掷）
            return
        if self._pole_eat():             # 手里有吃的：先在杆上吃完
            return
        if self._pole_reach_pickups():   # 杆上伸手：捡矛/石头、徒手抓飞虫
            return
        if self._hpole_step_off():       # 杆面够不到、落到窗口顶边才够得到 → 沿着杆挪到位再下去
            return                       # （必须排在 _pole_leave_for_food 前面：那条是「走地面
                                         #   路线」，对摆在窗口顶边上的东西会走空）
        if self._pole_leave_for_food():  # 杆上等同地面：有别的更想吃的就下杆去拿
            return
        if self._hpole_goal_grab():      # 上杆来够的东西：够到就摘下来
            return
        done = self.hpole.update()
        if done:
            air_t = self.hpole.air_target
            ho = self.hpole.handoff
            self._hpole_release()
            if air_t is not None:
                self._air_pole_target = air_t
            if ho is not None:
                self._pole_handoff(ho)
                return
            self._transition("IdleStand" if self.body.on_floor() else "Airborne")

    def _hpole_target_for_food(self):
        """为了吃：目标食物摆在哪根横杆的杆面上（没有就 None）。"""
        f = self._hp_goal_obj
        if f is None:
            return None
        for p in self.win.poles:
            if p.kind != "horizontal":
                continue
            lo = min(p.ax, p.bx)
            hi = max(p.ax, p.bx)
            if not (lo - tuning.HPOLE_GOAL_EPS <= f.x <= hi + tuning.HPOLE_GOAL_EPS):
                continue
            if not (p.ay - tuning.HPOLE_GOAL_R <= f.y <= p.ay + tuning.HPOLE_HAND_DOWN):
                continue
            return p
        return None

    def _hpole_food_trip(self) -> bool:
        """地面/爬杆都够不到、但横杆杆面上够得到的食物：上杆去拿（原版 beam 上摘果）。

        返回 True=已切到 SeekHPole。
        """
        if self.state not in _WANTS_FROM and self.state != "HPole":
            return False
        if self._hp_goal_x is not None:
            return False
        if not any(p.kind == "horizontal" for p in self.win.poles):
            return False
        b = self.body
        # 已经站在某根横杆上：脚下这根优先处理，别的杆留作退路
        cur = None
        if self.state == "HPole" and self.hpole is not None:
            cp = self.hpole.pole
            if cp is not None and cp.kind == "horizontal":
                cur = cp
        best = None
        best_cur = None
        for f in self.win.fetchables():
            if getattr(f, "state", None) not in ("free", "hanging"):
                continue
            if not getattr(f, "fetch_ready", True):
                continue
            if not self._can_eat(f):
                continue
            g = None
            for p in self.win.poles:
                if p.kind != "horizontal":
                    continue
                if not (self._hpole_spans(p, x=f.x, r=tuning.HPOLE_GOAL_EPS)
                        or self._hpole_gap_ok(p, f)):
                    continue
                # 杆面能拿到的高度带：杆上跳得到（上方 HPOLE_GOAL_R）或贴杆探得到（下方
                # HPOLE_HAND_DOWN）。再低的就是摆在窗口顶边上的，得下杆去捡（见 _hpole_step_off）
                if not (p.ay - tuning.HPOLE_GOAL_R <= f.y
                        <= p.ay + tuning.HPOLE_HAND_DOWN):
                    continue
                g = p
                break
            if g is None:
                for p in self.win.poles:
                    if p.kind == "horizontal" and self._hpole_gap_ok(p, f):
                        g = p
                        break
            if g is None:
                continue
            if self.state != "HPole" and self.planner.any_touch(obj_goal(f)):
                continue                    # 正常路就能拿，不必上杆（已在杆上时不算：脚下这根优先）
            d = abs(f.x - b.chunk1.x)
            if best is None or d < best[0]:
                best = (d, f)
            if g is cur and (best_cur is None or d < best_cur[0]):
                best_cur = (d, f)
        if best is None:
            return False
        f = (best_cur or best)[1]
        self._hp_goal_x = f.x
        self._hp_goal_obj = f
        self._hp_goal_t = 0
        if self.state == "HPole" and self.hpole is not None:
            # 已经在杆上：把现有控制器直接指过去就好。
            # 这里绝不能 _break_active_controllers —— 那会把杆一起放掉。
            h = self.hpole
            p = h.pole
            if p is not None:
                h.goal_x = max(min(p.ax, p.bx) + 2.0,
                               min(max(p.ax, p.bx) - 2.0, f.x))
            h.want = (float(f.x), float(f.y))
            return True
        if self._hpole_entry() is None:      # 没有可行的上杆路线
            self._hpole_goal_clear()
            return False
        self._break_active_controllers()
        self._act_or_wake("SeekHPole")
        return True

    def _pole_throw(self) -> bool:
        """杆上投矛：手里有矛/石头且近处有蜥蜴，就在杆上原地掷出去。

        wiki「Throwing midair」/原版：投掷不要求落地，站在杆上照样能投。
        """
        b = self.body
        if b.carried_spear is None and b.carried_stone is None:
            return False
        tgt = self._nearest_throw_target(tuning.FIGHT_ARM_R)
        if tgt is None:
            return False
        self._aim_target(tgt)
        return self._throw_weapon_at(tgt)

    def _pole_tip_grab(self) -> bool:
        """杆上够得着的东西：伸手摘下来（原版 beam 上伸手，同横杆 _hpole_goal_grab）。"""
        pc = self.poleclimb
        if pc is None or pc.phase not in ("climb", "tip"):
            return False
        best, bd = None, None
        for f in self.win.fetchables():
            if getattr(f, "state", None) not in ("free", "hanging"):
                continue
            if not getattr(f, "fetch_ready", True):
                continue
            if not self._can_eat(f):
                continue
            d = self._hand_reach_dist(f)
            if best is None or d < bd:
                best, bd = f, d
        if best is None:
            return False
        side = self.body.pick_hand("fruit")
        if side is None:
            return False
        self.gfx.hand_aim[side] = (best.x, best.y)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if bd <= tuning.GRAB_REACH:
            self.body.grab_fruit(best, side)
            return False                 # 抓到就交回普通流程（杆上啃/玩）
        return self._pole_jump_grab(best)   # 手够不到：跳一下试试（竖杆同横杆）

    def _pole_leave_for_food(self) -> bool:
        """杆上等同地面：有更值得拿的东西（普通路就够得到）就下杆去拿。

        原版蛞蝓猫不会因为站在杆上就放弃进食欲望；杆只是脚下的地面。
        """
        b = self.body
        if b.carried_fruit is not None or self.grab.active or self._exhausted:
            return False
        if self.timer < tuning.POLE_LEAVE_MIN_TICKS:
            return False                 # 刚上杆先待一会儿，别上去就下来
        if self._hp_step_obj is not None:
            return False                 # 正沿着杆挪到下杆位置：别被「走地面」抢走
        if self.state == "HPole" and self._hp_goal_x is not None:
            return False                 # 上杆本来就是为了够那个东西
        if not (not b.food_satisfied() and self._food_seek_ready()):
            return False
        if not fetch_ready(self.planner,
                           self.win.fetchables(want_karma=not b.flower_karma),
                           diet=self.pers.diet, unit=self.win):
            return False
        self._break_active_controllers()
        self._act_or_wake("FetchFruit")
        return True

    def _air_throw(self) -> None:
        """空中投矛：起跳/落地过程中手里有家伙且蜥蜴够近就掷（wiki Throwing midair）。"""
        b = self.body
        if self._air_throw_cd > 0:
            self._air_throw_cd -= 1
            return
        if (b.carried_spear is None and b.carried_stone is None) or self._exhausted:
            return
        if self._spear_rage():                      # 矛大师狂暴：整屏找非猫目标
            lz = self._rage_target(tuning.SPEAR_RAGE_R)
        else:
            lz = self._nearest_lizard(tuning.AIR_THROW_R)
        if lz is None or lz.dead or self._carrying_gift():
            return
        if self._throw_weapon_at(lz):
            self._air_throw_cd = tuning.AIR_THROW_CD

    def _hpole_goal_clear(self):
        self._hp_goal_x = None
        self._hp_goal_obj = None
        self._hp_goal_t = 0
        self._hp_jump_goal = None
        self._hp_step_obj = None
        h = getattr(self, "hpole", None)
        if h is not None:                # 控制器还留着停位 → 它会原地站到天荒地老
            h.goal_x = None
            h.goal_eps = None
            h.want = None
            h._gap_t = 0

    def _platform_under(self, o):
        """o 摆在哪块「别人窗口顶边」上；不是平台就 None。返回 (y, x0, x1)。"""
        from ..core import chunkphys
        for x0, y0, x1 in chunkphys.platforms():
            if x0 <= o.x <= x1 and abs(o.y - y0) <= tuning.HPOLE_STEP_SURF_EPS:
                return (y0, x0, x1)
        return None

    def _hpole_step_off(self) -> bool:
        """横杆上：杆面够不到、但落到下面那块窗口顶边才够得到的东西 → 沿杆挪到位再下杆。

        原版横杆只是脚下的地面（够不到就下杆）；用户口径要求补上
        「从横杆跳到窗口地面捡东西」：别人窗口顶边是单向平台，
        先沿杆面走到那块平台上方，再松杆落上去，落地后由普通取物流程接手
        （那时脚下地面＝平台，规划层 stand_h() 会认它）。

        返回 True 只在「已经松杆、切到 Airborne」那一帧 —— 还在沿杆挪的时候
        必须返回 False，否则调用方会直接 return 掉、hpole.update() 永远跑不到，猫卡在原地。
        """
        b = self.body
        if self._hp_step_cd > 0:
            self._hp_step_cd -= 1
        h = self.hpole
        if h is None or self.state != "HPole":
            self._hp_step_obj = None
            return False
        if self._hp_goal_x is not None:      # 正在为别的目标走位
            return False
        if b.carried_fruit is not None or self.grab.active or self._exhausted:
            self._hp_step_obj = None
            return False
        p = h.pole
        c0, c1 = b.chunk0, b.chunk1
        f = self._hp_step_obj
        if f is not None:                    # 已经瞄上了：中途失效就作废
            surf = self._platform_under(f)
            if (getattr(f, "state", None) not in ("free", "hanging")
                    or surf is None or b.food >= b.food_max
                    or not self._hpole_spans(p, x=f.x)
                    or not (surf[0] > p.ay + tuning.HPOLE_STEP_MIN_DROP)):
                f = self._hp_step_obj = None
        if f is None:
            if self._hp_step_cd > 0:
                return False
            best = None
            for cand in self.win.fetchables():
                if getattr(cand, "state", None) not in ("free", "hanging"):
                    continue
                if not getattr(cand, "fetch_ready", True):
                    continue
                if not self._can_eat(cand):
                    continue
                if (self._hpole_spans(p, x=cand.x)
                        and cand.y <= p.ay + tuning.HPOLE_HAND_DOWN):
                    continue                 # 杆面（贴杆伸手/杆上跳）够得到：交给普通杆上流程
                surf = self._platform_under(cand)
                if surf is None:
                    continue                 # 地板上的东西由 _pole_leave_for_food 负责
                if not (surf[0] > p.ay + tuning.HPOLE_STEP_MIN_DROP):
                    continue                 # 那块面不比杆面低：不是「跳下去」能解决的
                d = abs(cand.x - c0.x)
                if best is None or d < best[0]:
                    best = (d, cand, surf)
            if best is None:
                return False                 # 杆上没有「摆在窗口顶边上」的目标：
                                             # 不掷 _food_seek_ready 的骰子（别白吃随机流）
            if not (not b.food_satisfied() and self._food_seek_ready()):
                return False
            _, f, _surf = best
            self._hp_step_obj = f
        sy, sx0, sx1 = self._platform_under(f)
        # 先沿杆面挪到那块平台上方（平台窄就走到最近处）
        # 落点留一步：正对着目标落下去 = 直接踩在果子上，会把果子顺着单向平台压穿
        step = tuning.HPOLE_STEP_STANDOFF * (-1.0 if f.x >= c0.x else 1.0)
        tx = f.x + step
        if sx1 - sx0 > 36.0:
            tx = min(max(tx, sx0 + 8.0), sx1 - 8.0)
        lo, hi = (p.ax, p.bx) if p.ax <= p.bx else (p.bx, p.ax)
        tx = min(max(tx, lo + 2.0), hi - 2.0)
        if abs(c0.x - tx) > tuning.HPOLE_GOAL_EPS:
            h.goal_x = tx
            h.goal_eps = tuning.HPOLE_GOAL_EPS
            return False                     # 让 hpole.update() 接着沿杆挪
        # 到位：松杆落向那块面，落地后普通取物流程接手
        self._hp_step_obj = None
        self._hp_step_cd = tuning.HPOLE_STEP_CD
        d = 1 if f.x >= c0.x else -1
        b.facing = d
        self._hpole_release()
        b.release_to_air(move_dir=d)
        self._transition("Airborne")
        return True

    def _hpole_goal_grab(self) -> bool:
        """在杆上够到目标物就抓进手里（原版 beam 上伸手摘）。"""
        f = self._hp_goal_obj
        if f is None:
            return False
        st = getattr(f, "state", None)
        if st is not None and st not in ("free", "hanging"):
            self._hpole_goal_clear()
            return False
        self._hp_goal_t += 1
        h = getattr(self, "hpole", None)
        if h is not None:
            h.want = (float(f.x), float(f.y))   # 目标会动（飞虫/被挤走的果子）：每 tick 刷新
        side = self.body.pick_hand("fruit")
        if side is not None:
            self.gfx.hand_aim[side] = (f.x, f.y)
            self.gfx.hand_aim["l" if side == "r" else "r"] = None
            if self._hand_reach_dist(f) <= tuning.GRAB_REACH:
                self.body.grab_fruit(f, side)
                self._hpole_goal_clear()
                return False             # 抓到就交回普通流程（杆上啃）
            if self._pole_jump_grab(f):  # 手够不到但跳起来能碰到：起跳空中摘
                return True              # 已离开 HPole，调用方要立刻收手
        if not self._hpole_reachable_now():
            self._hpole_goal_clear()     # 目标不在杆面上了：作废
            return False
        if h is not None and abs(h.body.chunk1.x - f.x) > tuning.HPOLE_GOAL_TIGHT_EPS:
            h.goal_x = f.x               # 还没走够近：收紧停位继续挪过去
            h.goal_eps = tuning.HPOLE_GOAL_TIGHT_EPS
            return False
        if self._hp_goal_t > tuning.HPOLE_GOAL_TIMEOUT:
            self._hpole_goal_clear()     # 走到位也够不到：放弃，别原地发呆到掉下杆
        return False

    def _pole_jump_grab(self, f) -> bool:
        """杆上跳起来够目标：能碰到就松杆起跳、空中伸手摘（原版 beam 上跳抓）。

        用 beam_jump_plan 在「档位×横向输入」的实测弧里挑最省的一档 —— 于是目标是
        斜上/斜下、左侧/右侧（带上下偏移）时都能选到合适的起跳角度与力度，
        而不是只会原地竖直跳。横距太大（HPOLE_JUMP_FAR 外）仍然先在杆上走过去。
        """
        from ..planning.pole_hop import beam_jump_plan
        c0 = self.body.chunk0
        if abs(f.x - c0.x) > tuning.HPOLE_JUMP_FAR:
            return False                      # 水平差太远：先在杆上走过去
        stats = getattr(self.win.cat, "stats", None)
        if stats is None:
            return False
        plan = beam_jump_plan(stats, c0.x, c0.y, f.x, f.y, tuning.GRAB_REACH)
        if plan is None:
            return False
        hold, md, _hit = plan
        self._pole_release_any()           # 先收杆（会清 _hp_goal_*），再记空中目标
        self._hp_jump_goal = f
        self.body.tip_launch(hold_ticks=hold, move_dir=md)
        self._transition("Airborne")
        return True

    def _hp_jump_grab(self) -> bool:
        """空中伸手摘杆上跳起来够的东西。摘到就交回 FetchFruit（别重新选果）。"""
        f = self._hp_jump_goal
        if f is None:
            return False
        if getattr(f, "state", None) not in ("free", "hanging"):
            self._hp_jump_goal = None
            self._hpole_goal_clear()
            return False
        side = self.body.pick_hand("fruit")
        if side is None:
            return False
        self.gfx.hand_aim[side] = (f.x, f.y)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if self._hand_reach_dist(f) <= tuning.GRAB_REACH:
            self.body.grab_fruit(f, side)
            self._hp_jump_goal = None
            self._hpole_goal_clear()
            self._transition("FetchFruit")
            return True
        return False

    def _hpole_reachable_now(self) -> bool:
        """目标是否仍在那条横杆线上（或杆端外跳/走出去就到的那一小块平台上）。"""
        h = getattr(self, "hpole", None)
        p = h.pole if h is not None else None
        if p is None:
            return False
        f = self._hp_goal_obj
        if f is None:
            return False
        return (self._hpole_spans(p, x=f.x)
                or self._hpole_gap_ok(p, f))

    def _hpole_gap_ok(self, p, f) -> bool:
        """目标在杆端外、但落在下面的窗口顶边（单向平台）上，跳出去就能到。

        用 platform_hop_plan 按目标的相对位置挑轨迹（隔间隙跳过去 / 走出去掉下去），
        落点还得离目标够近（HPOLE_GAP_LAND_R）——否则跳过去也是白跳。
        """
        if getattr(f, "state", None) not in ("free", "hanging"):
            return False
        lo, hi = min(p.ax, p.bx), max(p.ax, p.bx)
        if lo <= f.x <= hi:
            return False                     # 在杆面跨内：那是 _hpole_spans 的事
        surf = self._platform_under(f)
        if surf is None or surf[0] <= p.ay + tuning.HPOLE_STEP_MIN_DROP:
            return False                     # 不在窗口顶边上 / 不比杆面低
        stats = getattr(getattr(self.win, "cat", None), "stats", None)
        if stats is None:
            return False
        from ..core import chunkphys
        from ..planning.pole_hop import platform_hop_plan
        px = max(lo + 14.0, min(hi - 14.0, hi if f.x > hi else lo))
        py = p.ay - 5.0                      # 杆面站姿（HPoleController.STAND_HOVER）
        pf = platform_hop_plan(stats, chunkphys.platforms(), px, py, want=(f.x, f.y))
        if pf is None:
            return False
        _kind, _hold, _md, lx, _ly = pf
        return abs(lx - f.x) <= tuning.HPOLE_GAP_LAND_R

    def _hpole_release(self):
        self._hpole_goal_clear()
        self._pole_nudge_pin = None
        self._pole_nudge = 0
        self._pole_nudge_point = False
        self._pole_blocker = None
        self._act_end()
        if self.hpole is not None:
            self._left_pole = self.hpole.pole
            self._air_pole_cd = tuning.AIR_POLE_CD
            self.hpole.release()
            self.hpole = None
        self.body.chunk0.pinned = False
        self.body.chunk1.pinned = False
        self.body.on_pole = False
        self.body.animation = None
        self.body.suspended = False
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    # 自主上横杆 SeekHPole
    def _has_hpole_available(self) -> bool:
        return self._hpole_entry() is not None

    def _hpole_spans(self, p, x=None, r=None) -> bool:
        """目标 x 是否落在这条横杆的杆面上（含端头余量）。"""
        if x is None:
            x = self._hp_goal_x
        if x is None:
            return True
        if r is None:
            r = tuning.HPOLE_GOAL_EPS
        lo, hi = min(p.ax, p.bx), max(p.ax, p.bx)
        return lo - r <= x <= hi + r

    def _hpole_entry(self):
        """横杆可达入口（原版三条路）：('tongue'|'climb'|'jump', 横杆[, 交叉竖杆])。

        舌（Saint）直接舔；普通猫要么爬交叉竖杆到交点按 上 换杆，
        要么横杆够低时从地面跳起来抓杆端。
        """
        ps = [p for p in self.win.poles if p.kind == "horizontal"]
        if self._hp_goal_x is not None:      # 有目的：只要够得到目标的那几条
            ps = [p for p in ps if self._hpole_spans(p)]
        if not ps:
            return None
        if self.win.tongue is not None:
            p = self._pick_hpole()
            return ("tongue", p) if p is not None else None
        for p in ps:
            cv = cross_partner(p, self.win.poles)
            if cv is not None and cv.kind == "vertical":
                return ("climb", p, cv)
        for p in ps:
            if self._hpole_jumpable(p):
                return ("jump", p)
        return None

    def _hpole_jumpable(self, p) -> bool:
        """横杆够低：地面起跳的弧线贴得到杆（用实测跳弧，别用估算——估算比真跳高十几像素）。"""
        from ..planning.jump_arc import get_arc, sweep_hit
        stats = getattr(self.win.cat, "stats", None)
        c0 = self.body.chunk0
        if stats is None or not self.body.on_floor():
            return False
        lo, hi = min(p.ax, p.bx), max(p.ax, p.bx)
        if hi - lo < 16.0:                         # 杆面太短，站不到杆下
            return False
        dy = p.ay - c0.y
        for md in (0, 1, -1):
            for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                if sweep_hit(get_arc(stats, hold, md), 0.0, dy, tuning.HPOLE_JUMP_GRAB) is not None:
                    return True
        return False

    def _pick_hpole(self):
        best = None
        hx = self.body.chunk1.x
        for p in self.win.poles:
            if p.kind != "horizontal":
                continue
            midx = (p.ax + p.bx) * 0.5
            if best is None or abs(midx - hx) < abs((best.ax + best.bx) * 0.5 - hx):
                best = p
        return best

    def _seekhpole_enter(self):
        b = self.body
        b.set_posture(True)
        self._clear_hands()
        self.climb = None
        self._hp_tries = 0
        self._hp_climbs = 0
        self._hp_jumps = 0
        self._hp_jump_cd = 0
        self._hp_air = False
        self._hp_cv = None
        entry = self._hpole_entry()
        self._hp_entry = entry[0] if entry is not None else None
        p = entry[1] if entry is not None else None
        self._hp = p
        if p is None:
            self._hp_phase = "done"
            return
        self._hp_lo = min(p.ax, p.bx)
        self._hp_hi = max(p.ax, p.bx)
        if self._hp_entry == "climb":       # 无舌：爬交叉竖杆，交点换横杆
            self._hp_cv = entry[2]
            self._hp_kind = "climb"
            self._hp_phase = "to_climb"
            return
        if self._hp_entry == "jump":        # 无舌：横杆够低，跳起来抓
            self._hp_kind = "jump"
            self._hp_ux = max(self._hp_lo + 6.0, min(self._hp_hi - 6.0, b.chunk1.x))
            self._hp_phase = "walk_under_jump"
            b.walk_to(self._hp_ux)
            return
        mox, moy = self.gfx.mouth_world()
        reach = self.win.tongue.total * HPOLE_REACH_FRAC
        if p.ay >= moy - reach:    # 低杆直舔，高杆先到锚墙脚再爬
            self._hp_kind = "low"
            self._hp_ux = max(self._hp_lo + 8.0, min(self._hp_hi - 8.0, b.chunk1.x))
            self._hp_phase = "walk_under"
            b.walk_to(self._hp_ux)
        else:
            self._hp_kind = "high"
            self._hp_side = -1 if p.ax < self.WL * 0.5 else 1
            self._hp_phase = "to_wall"
            b.walk_to(b.walk_max if self._hp_side > 0 else b.walk_min)

    def _try_grab_pole(self, p) -> bool:
        """够得着则舔杆点；已粘住杆→交 HPole。返回 True=本 tick 有进展。"""
        tg = self.win.tongue
        lo, hi = self._hp_lo, self._hp_hi
        if tg.attached:
            ax, ay = tg.anchor if tg.anchor is not None else (None, None)
            if ax is not None and abs(ay - p.ay) < 24.0 and lo - 6.0 <= ax <= hi + 6.0:
                self._hpole_pole = p
                self._hp = None
                self._transition("HPole")
            return True
        if tg.is_idle():
            mox, moy = self.gfx.mouth_world()
            tx = max(lo + 6.0, min(hi - 6.0, mox))
            if math.hypot(mox - tx, moy - p.ay) <= tg.total * HPOLE_REACH_FRAC:
                self.win.fire_tongue_at(tx, p.ay)
                self._hp_tries += 1
                return True
            return False
        return True

    def _st_seekhpole(self, cursor, disturbed):
        from ..cats.saint.climb import TongueClimber
        b = self.body
        if self.grab.active:
            self._seekhpole_break()
            self._transition("Dragged")
            return
        p = self._hp
        if p is None or p not in self.win.poles or self.timer > T_HPOLE_TIMEOUT:
            self._seekhpole_break()
            self._transition("IdleStand" if b.on_floor() else "Airborne")
            return
        lo, hi = self._hp_lo, self._hp_hi
        self.gfx.look_at = ((lo + hi) * 0.5, p.ay)
        ph = self._hp_phase

        if ph == "to_climb":         # 无舌：交给竖杆攀爬，交点处自动换横杆
            cv = self._hp_cv
            self._seekhpole_break()
            if cv is None or cv not in self.win.poles:
                self._transition("IdleStand")
                return
            self._poleclimb_pole = cv
            self._poleclimb_start = None
            self._transition("PoleClimb")
            return

        if ph == "walk_under_jump":  # 无舌：走到杆下
            if not b.is_moving() or abs(b.chunk1.x - self._hp_ux) < 8.0:
                b.stop_walk()
                self._hp_phase = "jump_grab"
            return

        if ph == "jump_grab":        # 无舌：起跳贴杆转 HPole
            c0 = b.chunk0
            ax = max(self._hp_lo + 2.0, min(self._hp_hi - 2.0, c0.x))
            self.gfx.look_at = (ax, p.ay)
            if math.hypot(ax - c0.x, p.ay - c0.y) <= tuning.HPOLE_JUMP_GRAB:
                self._hpole_pole = p
                self._hpole_start = "hang"
                self._hpole_start_x = c0.x
                self._hp = None
                self._transition("HPole")
                return
            if self._hp_jump_cd > 0:
                self._hp_jump_cd -= 1
                return
            if not b.on_floor():     # 空中朝杆端微调
                if ax > c0.x + 1.0:
                    b.move_dir = 1
                elif ax < c0.x - 1.0:
                    b.move_dir = -1
                return
            if abs(c0.x - ax) > 12.0:
                b.walk_to(ax)
                return
            if self._hp_jumps >= tuning.HPOLE_JUMP_TRIES:
                self._seekhpole_break()
                self._transition("IdleStand")
                return
            b.stop_walk()
            b.move_dir = 0
            b.request_jump("stand")
            self._hp_jumps += 1
            self._hp_jump_cd = tuning.HPOLE_JUMP_CD
            return

        if ph == "walk_under":       # 低杆走到杆下
            if not b.is_moving() or abs(b.chunk1.x - self._hp_ux) < 8.0:
                b.stop_walk()
                self._hp_phase = "lick_low"
            return

        if ph == "lick_low":         # 低杆直舔上杆
            prog = self._try_grab_pole(p)
            if self.state != "SeekHPole":
                return
            if prog and self._hp_tries < 4:
                return
            self._seekhpole_break()
            self._transition("IdleStand")
            return

        if ph == "to_wall":          # 高杆先到锚墙脚
            tx = b.walk_max if self._hp_side > 0 else b.walk_min
            if not b.is_moving() or abs(b.chunk1.x - tx) < 8.0:
                b.stop_walk()
                self.climb = None
                self._hp_phase = "climb"
            return

        if ph == "climb":            # 高杆爬锚墙到够杆端
            mox, moy = self.gfx.mouth_world()
            if math.hypot(mox - p.ax, moy - p.ay) <= self.win.tongue.total * HPOLE_GRAB_REACH:
                self._break_tongue()
                self.climb = None
                self._hp_phase = "grab"
                self._hp_tries = 0
                return
            wall_x = 0.0 if self._hp_side < 0 else self.WL
            if self.climb is None:
                self.climb = TongueClimber(self.win, self._hp_side,
                                           target=(wall_x, p.ay), stop_dist=40.0)
            done = self.climb.update()
            if getattr(self.climb, "giveup", False):
                self._hp_reclimb(b)
            elif done:
                self._break_tongue()
                self.climb = None
                self._hp_phase = "grab"
                self._hp_tries = 0
            return

        if ph == "grab":             # 够杆舌粘转 HPole
            prog = self._try_grab_pole(p)
            if self.state != "SeekHPole":
                return
            if prog and self._hp_tries < 5:
                return
            self._hp_reclimb(b)
            return

        self._seekhpole_break()
        self._transition("IdleStand")

    def _hp_reclimb(self, b):
        """高杆够不着→回墙脚重爬(限次)；低杆/超限→放弃回 idle。"""
        self._break_tongue()
        self.climb = None
        self._hp_tries = 0
        self._hp_climbs += 1
        if self._hp_kind == "high" and self._hp_climbs <= HPOLE_MAX_CLIMBS:
            self._hp_phase = "to_wall"
            b.walk_to(b.walk_max if self._hp_side > 0 else b.walk_min)
        else:
            self._seekhpole_break()
            self._transition("IdleStand")

    def _seekhpole_break(self):
        self._hpole_goal_clear()
        self._break_tongue()
        self.body.stop_walk()
        self.climb = None
        self._hp = None
        self._hp_phase = None
        self._hp_cv = None
        self._hp_entry = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    # 趋暖 SeekWarmth
    def _too_cold_to_sleep(self):
        """冷到阈值就别睡。"""
        return self.body.cold >= tuning.COLD_NOSLEEP

    def _warm_goal(self):
        """趋暖目标：灯泡 + 暖区到位半径，复用同一 Goal 保冷却 key 稳定。"""
        lamp = getattr(self.win, "lamp", None)
        if lamp is None:
            self._warm_goal_obj = None
            return None
        g = self._warm_goal_obj
        if g is None or g.obj is not lamp:
            from ..world.lamp import ARRIVE_RADIUS
            g = obj_goal(lamp, valid=lambda l: getattr(self.win, "lamp", None) is l,
                         radius=ARRIVE_RADIUS)
            self._warm_goal_obj = g
        return g

    def _warm_lamp_available(self):
        """有灯且不在冷却。"""
        if getattr(self.win, "lamp", None) is None:
            return False
        return not self.planner.in_cooldown(self._warm_goal())

    def _cold_urgent(self):
        """需强制趋暖判据。"""
        lamp = getattr(self.win, "lamp", None)
        if lamp is None or self.body.cold < tuning.COLD_SEEK_ENTER:
            return False
        if lamp.in_warm_zone(self.body.chunk1.x, self.body.chunk1.y):
            return False
        return not self.planner.in_cooldown(self._warm_goal())

    def _seekwarmth_enter(self):
        self.gfx.sleeping = False
        self.body.sleeping = False
        self.gfx.sleep_curl = 0.0
        self.body.set_posture(True)
        self._clear_hands()
        self.climb = None
        self._warm_exec = None
        g = self._warm_goal()
        if g is None:
            return
        if not self.planner.stay_candidates(g):
            self.planner.on_giveup(g)    # 够不到就登记冷却
            return
        self._warm_exec = PlanExecutor(self.win, self.planner, g, mode=MODE_STAY)

    def _st_seekwarmth(self, cursor, disturbed):
        b = self.body
        lamp = getattr(self.win, "lamp", None)
        if lamp is None or self._warm_exec is None:
            self._seekwarmth_break(); self._transition("IdleStand"); return
        if self.grab.active:
            self._seekwarmth_break(); self._transition("Dragged"); return
        self.gfx.look_at = lamp.bulb
        status = self._warm_exec.update()
        if status == GIVEUP:
            self._seekwarmth_break()
            self._transition("IdleStand" if b.on_floor() else "Airborne")
            return
        if status == HOLDING:
            storm = bool(getattr(self.win, "blizzard_on", False))   # 暖够且风停才收工
            if b.cold <= tuning.COLD_SEEK_EXIT and not storm:
                self._seekwarmth_break()
                self._transition("IdleStand" if b.on_floor() else "Airborne")

    def _seekwarmth_break(self):
        if self._warm_exec is not None:
            self._warm_exec.cancel()
            self._warm_exec = None
        self._break_tongue()
        self.body.stop_walk()
        self.climb = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    # ── 暴雨：集合 / 庇护所睡眠 / 雨前焦虑 ──
    def _storm_lockdown(self, ctx):
        """雨落下以后，进庇护所是**唯一**优先：该做的事整条 band 让开。

        只让开 need band 的 start（``pre`` 记账照跑），所以社交账本 / 事件总线在
        集合期不会断线；保命 band 不受影响（被拖、淹水、昏迷仍然优先）。
        """
        if not getattr(self.win, "storm_active", False):
            return
        if self.state in ("Dead", "Dragged", "Stunned", "Ascension", "ShelterSleep"):
            return
        sh = self._storm_shelter()
        if sh is not None and sh.contains(self.body.chunk1.x, self.body.chunk1.y):
            return                    # 已经进屋：等门关上就睡，不再压别的事
        ctx.skip_from(self.actions.keys(BAND_NEED))
    def _storm_phase(self):
        st = getattr(self.win, "storm", None)
        return getattr(st, "phase", "focus") if st is not None else "focus"

    def _storm_shelter(self):
        """离自己最近的那间庇护所（现在只有一间，多间时自动选近的）。"""
        shs = getattr(self.win, "shelters", None)
        if not shs:
            return None
        b = self.body
        best, bd = None, 1.0e18
        for sh in shs:
            d = sh.distance_to(b.chunk1.x, b.chunk1.y)
            if d < bd:
                best, bd = sh, d
        return best

    def _storm_enter(self):
        """暴雨集合：只把「庇护所入口」交给现有 PlanExecutor，不另写一套 A*。"""
        self.gfx.sleeping = False
        self.body.sleeping = False
        self.gfx.sleep_curl = 0.0
        self.body.set_posture(True)
        self.climb = None
        self._storm_exec = None
        sh = self._storm_shelter()
        if sh is None:
            return
        self._storm_goal_obj = sh
        g = sh.interior_goal(tuning.SHELTER_ENTRY_RADIUS)
        if not self.planner.stay_candidates(g):
            self.planner.on_giveup(g)      # 够不到就登记冷却，别每 tick 重规划
            self._storm_cd = tuning.STORM_RETRY_TICKS
            return
        self._storm_exec = PlanExecutor(self.win, self.planner, g, mode=MODE_STAY)

    def _storm_break(self):
        if self._storm_exec is not None:
            self._storm_exec.cancel()
            self._storm_exec = None
        self.body.stop_walk()

    def _st_stormseekshelter(self, cursor, disturbed):
        """跑向庇护所入口；到了就站着等门关（入睡由 StormSleep 统一接管）。"""
        b = self.body
        sh = self._storm_shelter()
        if sh is None or not self.win.storm_active:
            self._storm_break()
            self._transition("IdleStand" if b.on_floor() else "Airborne")
            return
        if self.grab.active:
            self._storm_break()
            self._transition("Dragged")
            return
        self.gfx.look_at = (sh.center_x, sh.center_y)
        gx, gy = sh.interior_goal(tuning.SHELTER_ENTRY_RADIUS).pos()
        if sh.contains(b.chunk1.x, b.chunk1.y) and math.hypot(
                b.chunk1.x - gx, b.chunk1.y - gy) <= tuning.SHELTER_ENTRY_RADIUS:
            self._storm_break()
            self._transition("IdleStand")
            return
        if self._storm_exec is None:
            self._storm_break()
            self._storm_cd = tuning.STORM_RETRY_TICKS
            self._transition("IdleStand" if b.on_floor() else "Airborne")
            return
        status = self._storm_exec.update()
        if status == GIVEUP:
            self._storm_break()
            self._storm_cd = tuning.STORM_RETRY_TICKS
            self._transition("IdleStand" if b.on_floor() else "Airborne")

    def _shelter_sleep_enter(self):
        """雨循环睡眠：固定时长；不扣食物、不加业力、不掷睡眠长度。"""
        b = self.body
        self._hibernating = True
        self.gfx.face(False, PRIO_FORCE)
        b.set_posture(False)
        b.stop_walk()
        self.gfx.sleeping = True
        b.sleeping = True
        self._settle_to_rest()
        self._sleep_drop_hands()
        self._storm_break()
        st = getattr(self.win, "storm", None)
        left = getattr(st, "sleep_ticks", None) if st is not None else None
        self._shelter_sleep_left = int(left) if left else 24000

    def _st_sheltersleep(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._transition("Dragged")
            return
        self.gfx.sleeping = True
        b.sleeping = True
        sh = self._storm_shelter()
        if sh is not None and not sh.contains(b.chunk1.x, b.chunk1.y):
            self._hibernating = False
            self._transition("IdleStand")     # 被挪出安全区：先回去，Storm* 会接上
            return
        if not self.win.storm_active or self.timer >= self._shelter_sleep_left:
            self._hibernating = False
            self._transition("WakeSequence")  # 复用现有起床动画

    def _storm_anxiety_tick(self):
        """雨前焦虑：只改闲暇表现 —— 看庇护所、少久呆、往庇护所附近靠。

        不强制进庇护所，也不碰吃饭 / 战斗 / 鼠标抓取；真正落雨那一刻才交给
        StormSeekShelter。没庇护所、压力不够时不掷任何骰子（随机数纪律）。
        """
        p = getattr(self.win, "storm_pressure", 0.0)
        if p <= tuning.STORM_PRESSURE_LO or not getattr(self.win, "shelters", None):
            return
        sh = self._storm_shelter()
        if sh is None:
            return
        prob = tuning.STORM_ANXIETY_LOOK_P * _lerpmap(
            p, tuning.STORM_PRESSURE_LO, 1.0, 0.25, 1.0)
        if self.rng.random() < prob:
            self.gfx.look_at = (sh.center_x, sh.center_y)

    def _storm_wander_bias_x(self, x, lo, hi):
        """雨前焦虑：闲逛目标有概率被拉向庇护所（只是靠过去，不是去躲雨）。"""
        p = getattr(self.win, "storm_pressure", 0.0)
        if p <= tuning.STORM_PRESSURE_LO or not getattr(self.win, "shelters", None):
            return x
        sh = self._storm_shelter()
        if sh is None:
            return x
        prob = tuning.STORM_ANXIETY_WANDER_BIAS * _lerpmap(
            p, tuning.STORM_PRESSURE_LO, 1.0, 0.2, 1.0)
        if self.rng.random() >= prob:
            return x
        return clampf(sh.entry_x() + self.rng.uniform(-40.0, 40.0), lo, hi)

    def _karma_flowers_reachable(self):
        """场上够得着、还没被吃掉的业力花（独立链路，不混普通食物）。"""
        out = []
        for f in self.win.karma_targets():
            if getattr(f, "state", None) not in ("free", "hanging"):
                continue
            if not getattr(f, "fetch_ready", True):
                continue
            if self.planner.any_touch(obj_goal(f)):
                out.append(f)
        return out

    def _fetch_enter(self):
        from .fetch import FruitFetcher
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        karma = self._fetch_karma
        self._fetch_karma = False
        self.fetch = FruitFetcher(self.win, self.planner, diet=self.pers.diet,
                                  pearl_like=getattr(self.pers, "pearl_like", 1.0),
                                  karma_only=karma)

        # 杆上跳起来摘到的：手里已经有目标，别重新选果（重选会因为「已到手」
        # 被排除在候选外而直接放弃、把果子丢掉），直接进 carry_fall / eat。
        held = self.body.carried_fruit
        if held is not None:
            self.fetch.target = held
            self.fetch.phase = "carry_fall"

    def _st_fetchfruit(self, cursor, disturbed):
        if self.grab.active:
            self._break_tongue()
            self._fetch_release()
            self._transition("Dragged")
            return
        if self.fetch is None:
            self._transition("IdleStand")
            return
        fh = self.fetch
        done = fh.update()
        if fh.giveup:
            if fh.karma_only:       # 业力花：走独立链路的冷却，别和觅食抢班
                self._karma_cd = tuning.KARMA_SEEK_CD
            self._break_tongue()
            self._fetch_release()
            self._fetch_cooldown = T_FETCH_COOLDOWN
            self._transition("IdleStand")
        elif done:
            if fh.pearl_done:       # 把玩完珍珠：放地上进冷却，别原地又叼起来
                self._pearl_cd = tuning.PEARL_HOARD_CD
            if fh.karma_only:
                self._karma_cd = tuning.KARMA_SEEK_CD
            self._break_tongue()
            self._fetch_release()
            self._transition("IdleStand")

    def _fetch_release(self):
        if self.fetch is not None:
            self.fetch.release()
        if self.body.carried_fruit is not None:
            self.body.carried_fruit.stalk = None
            self.body.carried_fruit.state = "free"
            self.body.carried_fruit.held_by_hand = None
            self.body.release_fruit()
        self.body.arm_aim["l"] = None
        self.body.arm_aim["r"] = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self.fetch = None

    def _grounded_stone_available(self) -> bool:
        return any(s.state == "free" and not s.unfetchable and s.at_rest_on_ground(self.HL)
                   for s in self.win.stones)

    def _st_angrystone(self, cursor, disturbed):
        if self.grab.active:
            self._angrystone_release()
            self._transition("Dragged")
            return
        if self.stonethrow is None:
            self._transition("IdleStand")
            return
        status = self.stonethrow.update(self.anger > 0)
        if status in ("thrown", "idle"):
            self._angrystone_release()
            self._transition("IdleStand")
        elif status == "revert_wander":
            self._angrystone_release()
            if self.anger <= 0:
                self._transition("IdleStand")
            elif self.anger <= T_POSTTHROW_STAND:
                self._transition("PostThrowStand")
            else:
                self._transition("PostThrowWander")

    def _st_huntfly(self, cursor, disturbed):
        """狩猎飞虫：控制器给出路由串，本函数只做态切换与收尾。"""
        if self.grab.active:
            self._flyhunt_release()
            self._transition("Dragged")
            return
        if self.flyhunt is None:
            self._transition("IdleStand")
            return
        want = (self.body.food < self.body.food_max and not self._exhausted)
        status = self.flyhunt.update(want)
        if status in ("thrown", "giveup", "idle"):
            self._flyhunt_release()
            self._hunt_cd = self._hunt_cd_after()
            self._transition("IdleStand")
        elif status == "revert_wander":
            self._flyhunt_release()
            self._hunt_cd = self._hunt_cd_after()
            self._transition("PostThrowWander")

    def _junk_corpse_near(self):
        """最近的无用尸体（不能吃的死尸：死蜥蜴…），够不着就是 None。"""
        best, bd = None, CORPSE_HAUL_SEEK_R
        bx = self.body.chunk1.x
        for e in self.win.junk_corpses():
            if abs(e.y - self.body.chunk1.y) > CORPSE_HAUL_MAX_DY:
                continue                      # 躺在别的窗口顶边上的：够不到
            d = abs(e.x - bx)
            if d < bd:
                best, bd = e, d
        return best

    def _haul_edge(self) -> float:
        """离自己最近的屏幕边（窗口左右边＝墙，尸体从这里甩出去）。"""
        return 0.0 if self.body.chunk1.x < self.WL * 0.5 else float(self.WL)

    def _haul_speed_fac(self, tgt) -> float:
        """拖尸限速因子（原版 Player.GraphicsModuleUpdated 的 HeavyCarry 绳约束）。

        原版每帧把「超过绳长 num5」的部分按质量比分配：猫被往回拉 num6、尸体被拉近
        1-num6（Player.cs:5958-5974），于是「猫 + 尸体」整体每帧只前进
        walk * (1 - num6) —— num6 越大（尸体越重）拖得越慢。
        num6 = 被抓那一节的 mass / (猫胸节 mass + 该节 mass)；被抓物总质量比猫轻时
        num6 再 /2。蜥蜴「被抓那一节」= bodyMass/3（Lizard.cs 三节均分）。
        """
        m_p = float(self.body.chunk0.mass)
        m_c = float(getattr(tgt, "haul_chunk_mass", 0.3))
        # Player.cs:5963 比的是双方 TotalMass（猫 = 两节合计 0.7，不是胸节 0.35）
        if float(getattr(tgt, "haul_mass", m_c * 3.0)) < float(self.body.total_mass):
            m_c *= 0.5
        return max(0.08, 1.0 - m_c / (m_p + m_c))

    def _haul_release(self, vx: float = 0.0) -> None:
        """松爪：被打断 / 放弃时把那具尸体放回自由态并真删。

        没有指定速度（被打断、超时放弃）时也朝最近的屏幕边甩出去（并打上
        thrown_out 标记）—— 否则尸体会原地停在屏幕上（常常正好是它被拖到的那条
        边），既不消失也没人再管。
        """
        self.body.walk_speed_target = None       # 松爪＝解除拖拽限速
        tgt = self._clear_target
        if tgt is not None and getattr(tgt, "hauler", None) is self:
            tgt.hauler = None                    # 交还认领：尸体重新可被搬运
        if tgt is not None and getattr(tgt, "hauled", False):
            if vx == 0.0:
                cx = getattr(tgt, "x", self.body.chunk1.x)
                vx = (-CORPSE_HAUL_FLING if cx < self.WL * 0.5
                      else CORPSE_HAUL_FLING)
            tgt.release_haul(vx, -1.0, thrown_out=True)
        self._clear_target = None

    def _st_clearcorpse(self, cursor, disturbed):
        """清场：把无用又不能吃的尸体（死蜥蜴…）拖到屏幕边甩出去。

        走位用 walk_to（跟地面行走同一套），尸体位置由 Lizard.haul 每 tick 钉在
        猫手边；到边甩出去之后由 window._cull_flung_corpses 直接清掉。
        """
        b = self.body
        if self.grab.active:
            self._transition("Dragged")
            return
        tgt = self._clear_target
        if (tgt is None or not getattr(tgt, "dead", False)
                or getattr(tgt, "state", None) != ItemState.FREE
                or not b.on_floor()):
            self._transition("IdleStand")
            return
        self._haul_left -= 1
        edge = self._haul_edge()
        dirv = 1.0 if edge > b.chunk1.x else -1.0
        if not getattr(tgt, "hauled", False):
            if (self._haul_left <= 0
                    or abs(tgt.y - b.chunk1.y) > CORPSE_HAUL_MAX_DY):
                self._haul_cd = T_CORPSE_HAUL_RETRY     # 走太久 / 够不到：算了
                self._transition("IdleStand")
                return
            if abs(tgt.x - b.chunk1.x) > CORPSE_HAUL_REACH:
                b.walk_to(tgt.x)                   # 走过去上手
                self.gfx.look_at = (tgt.x, tgt.y)
                return
            b.stop_walk()
            tgt.haul(b.chunk1.x, b.chunk1.y, 0.0)  # 先贴身边，下一 tick 开始拖
            return
        # 已经拖着：往最近的屏幕边挪，够近就甩出去。
        # walk_to(edge) 会被 walk_min/walk_max 夹到窗口内边（猫自身半宽），重尸按
        # 原版质量比拖得很慢时刚好停在到达圈外一点点 → 再补一条「贴到自己能走到
        # 的极限」也算到边，免得拖着拖着永远到不了边（尸体停在边上不消失）。
        stop_x = b.walk_min if dirv < 0.0 else b.walk_max
        if stop_x is None:
            stop_x = edge
        arrived = (abs(b.chunk1.x - edge) <= CORPSE_HAUL_ARRIVE
                   or abs(b.chunk1.x - stop_x) <= WALK_STOP_EPS + 0.5)
        if arrived or self._haul_left <= 0:
            b.stop_walk()
            tgt.release_haul(dirv * CORPSE_HAUL_FLING, -1.0, thrown_out=True)
            self._clear_target = None
            self._haul_cd = T_CORPSE_HAUL_RETRY
            self._transition("IdleStand")
            return
        b.walk_to(edge)
        # 拖得越重走得越慢：原版绳约束的质量比（绿蜥 7.5 ≈ 蛞蝓猫的 12%，粉/白蜥 ≈ 33%）
        b.walk_speed_target = RUN_UPPER * b.stats.runspeed_fac * self._haul_speed_fac(tgt)
        side = "l" if dirv < 0.0 else "r"
        hx, hy = b._carry_pos(side)
        tgt.haul(hx, hy, -dirv)        # 身体朝行进前方摊开，不压在猫身上
        self.gfx.look_at = (edge, self.HL - 12.0)

    def _hunt_cd_after(self) -> int:
        """一次捕猎后的冷却：越爱吃肉越想接着打（荤 0.6× / 杂 1.0× / 素 1.4×）。"""
        return int(HUNT_CD * (1.4 - 0.8 * self._meat_zeal()))

    def _flyhunt_release(self):
        """收尾：松手、清瞄准、清控制器（矛大师自己尾巴长的活白针继续拿着）。"""
        b = self.body
        if b.carried_spear is not None and not self._own_needle(b.carried_spear):
            b.carried_spear.state = "free"
            b.release_spear(to_free=True)
        if b.carried_stone is not None:
            b.carried_stone.state = "free"
            b.release_stone(to_free=True)
        self.body.stop_walk()
        self.flyhunt = None
        self.body.arm_aim["l"] = None
        self.body.arm_aim["r"] = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    def _angrystone_release(self):
        if self.body.carried_stone is not None:
            self.body.release_stone(to_free=True)
        self.body.stop_walk()
        self.stonethrow = None
        self.body.arm_aim["l"] = None
        self.body.arm_aim["r"] = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    # ─────────────────────────────────────────────────────────────
    #  六类欲望：进食 / 恐惧 / 战斗 / 玩耍 / 睡眠 / 社交
    # ─────────────────────────────────────────────────────────────
    # 判据扫描
    def _peers(self):
        """在场上、不是自己的同伴。"""
        out = []
        for p in getattr(self.win, "pets", ()):
            if p is self.win or getattr(p, "body", None) is None:
                continue
            out.append(p)
        return out

    def _living_peers(self):
        return [p for p in self._peers() if not p.body.dead]

    def _has_living_peer(self) -> bool:
        return bool(self._living_peers())

    def _near_wall(self) -> bool:
        return edgeqm.on_wall(self.body, self.WL, tuning.WALL_SEEK_R) != 0

    def _ceiling_reachable(self) -> bool:
        c0 = self.body.chunk0
        return edgeqm.on_ceiling(self.body) or (c0.y - c0.rad <= tuning.CEIL_GRAB_REACH)

    def _can_ceil_cling(self) -> bool:
        """屏幕顶端一律不许攀附（爪子吊顶取消）。

        只有圣徒的**舌头**能挂在天花板上，那是 TongueClimb/CeilingHang 里的
        舌头物理，与本判定无关；这里恒 False 表示没有猫用爪子扒住顶边。
        """
        return False

    def _peer_near(self) -> bool:
        c1 = self.body.chunk1
        for p in self._living_peers():
            ob = p.body
            if math.hypot(ob.chunk1.x - c1.x, ob.chunk1.y - c1.y) <= tuning.SOCIAL_R:
                return True
        return False

    def _peer_asleep(self, p) -> bool:
        """这只同伴是不是在睡（Sleep/LieDown，或 body.sleeping 标记）。"""
        beh = getattr(p, "behavior", None)
        if beh is not None and beh.state in ("Sleep", "LieDown"):
            return True
        return bool(getattr(getattr(p, "body", None), "sleeping", False))

    def _cursor_close(self) -> bool:
        cur = self.cursor
        if cur is None:
            return False
        c0 = self.body.chunk0
        return math.hypot(cur[0] - c0.x, cur[1] - c0.y) <= tuning.PLAYCUR_R

    def _spear_rage(self) -> bool:
        """矛大师饿到一半以下：攻击性 + 识别范围拉满（会拿自己的尾针戳一切非猫生物）。"""
        if not self.win.cat.tuning.get("tail_needle"):
            return False
        b = self.body
        return b.food <= b.food_max * tuning.SPEAR_RAGE_FRAC

    def _rage_target(self, r):
        """狂暴时的目标：半径内最近的非蛞蝓猫活物（蜥蜴 / 蝙蝠 / 禅乌贼 / 面条蝇 / 拾荒者）。"""
        best, bd = None, float(r)
        c1 = self.body.chunk1
        cand = list(getattr(self.win, "lizards", ()))
        cand += list(getattr(self.win, "squidcadas", ()))
        cand += list(getattr(self.win, "batflies", ()))
        cand += list(getattr(self.win, "needleworms", ()))
        cand += list(getattr(self.win, "scavengers", ()))
        for o in cand:
            if getattr(o, "dead", False):
                continue
            if getattr(o, "state", None) not in (None, ItemState.FREE):
                continue
            d = math.hypot(o.x - c1.x, o.y - c1.y)
            if d < bd:
                best, bd = o, d
        return best

    def _nearest_lizard(self, r):
        best, bd = None, float(r)
        c1 = self.body.chunk1
        for lz in getattr(self.win, "lizards", ()):
            if getattr(lz, "dead", False) or lz.state != ItemState.FREE:
                continue
            d = math.hypot(lz.x - c1.x, lz.y - c1.y)
            if d <= bd:
                best, bd = lz, d
        return best

    def _threat_level(self) -> float:
        lz = self._threat_lizard()
        if lz is None:
            return 0.0
        c1 = self.body.chunk1
        return clampf(1.0 - math.hypot(lz.x - c1.x, lz.y - c1.y) / self._threat_r(), 0.0, 1.0)

    def _threat_r(self) -> float:
        """恐惧半径 ≈ 1/3 桌面宽度（原版 Player 见威胁的恐惧圈按窗口缩放，不写死）。"""
        return max(tuning.THREAT_MIN_R, self.WL * tuning.THREAT_WIN_FRAC)

    def _threat_lizard(self):
        """威胁圈内最近的活威胁：蜥蜴 + 愤怒的面条蝇成体（唤醒/持械/超度/逃跑都用它）。"""
        return self._nearest_throw_target(self._threat_r())

    def _hostile_fly(self, f) -> bool:
        """愤怒的面条蝇成体：原版 BigNeedleWormAI 的 Attacks（拿着幼体 / tempLike<-0.25）。"""
        if getattr(f, "age", None) != "big" or getattr(f, "dead", False):
            return False
        if getattr(f, "state", None) != ItemState.FREE:
            return False
        try:
            return bool(f.hostile_to({"uid": id(self.win)}))
        except Exception:
            return False

    def _nearest_throw_target(self, r):
        """最近的投掷/对抗目标：蜥蜴 / 愤怒的面条蝇成体 / 敌对拾荒者（r 之内）。"""
        c1 = self.body.chunk1
        best = self._nearest_lizard(r)
        bd = float(r) if best is None else math.hypot(best.x - c1.x, best.y - c1.y)
        for f in getattr(self.win, "needleworms", ()):
            if not self._hostile_fly(f):
                continue
            d = math.hypot(f.x - c1.x, f.y - c1.y)
            if d < bd:
                best, bd = f, d
        for sc in getattr(self.win, "scavengers", ()):
            if not self._hostile_scavenger(sc):
                continue
            d = math.hypot(sc.x - c1.x, sc.y - c1.y)
            if d < bd:
                best, bd = sc, d
        return best

    @staticmethod
    def _hostile_scavenger(sc) -> bool:
        """会朝猫扔矛的拾荒者（珍珠交易过的 friendly 不再算威胁）。"""
        return (not getattr(sc, "dead", False)
                and getattr(sc, "state", None) == ItemState.FREE
                and not getattr(sc, "friendly", False))

    def _threat_present(self) -> bool:
        return self._threat_lizard() is not None

    def _nearest_peer(self, r=None):
        """最近的同伴；给了 r 就只找这么近的。"""
        best, bd = None, (1e9 if r is None else float(r))
        c1 = self.body.chunk1
        for p in self._living_peers():
            ob = p.body
            d = math.hypot(ob.chunk1.x - c1.x, ob.chunk1.y - c1.y)
            if d < bd:
                best, bd = p, d
        return best

    def _hungriest_peer(self):
        """最饿的同伴（缺得最多）。"""
        best, best_need = None, 0
        for p in self._living_peers():
            need = p.body.food_max - p.body.food
            if need > best_need:
                best, best_need = p, need
        return best

    @staticmethod
    def _peer_needs_help(ob) -> bool:
        """倒地要同伴搭手：真死，或者被击晕还没醒（原版被击晕也是倒地）。"""
        return bool(ob.dead) or getattr(ob, "stun", 0) > 0

    def _wants_rescue(self, kind: float) -> bool:
        """肯不肯去救倒地的同伴。

        旧版这条路上完全没有 kindness —— 无威胁时人人都会救，有威胁时又只有
        kindness >= FEAR_KIND_RESCUE 才救，两边口径不一致。这里统一：善良度
        够高一定去，其余按善良度掷骰（每个决策 tick 掷一次，累计很快）。
        """
        return kind >= tuning.FEAR_KIND_RESCUE or self.rng.random() < kind

    @staticmethod
    def _rescue_key(ob):
        return ("rescue", id(ob))

    def _rescue_goal(self, ob):
        """救援目标点：同伴最近的一截身体（坐标每帧重取，跟着它走）。"""
        return Goal(lambda: (ob.chunk1.x, ob.chunk1.y), lambda: True,
                    self._rescue_key(ob))

    def _rescue_step(self, ob) -> None:
        """救援赶路：复用觅食那套表面寻路（走 / 跳 / 落 / 爬杆 / 上窗口顶边）。

        旧版只 b.walk_to(尸体.x)：同伴躺在平台/杆上，或者中间隔着缺口时，AI 已经
        决定去救、画面却只在原地朝那个 x 走 —— 这就是「AI 明明该救却看着不积极」。
        规划放弃（真的够不到）才退回直奔。
        """
        if not self._peer_needs_help(ob):
            self._rescue_exec = None
            self.body.stop_walk()
            return
        b = self.body
        if (b.on_floor()
                and abs(ob.chunk1.y - b.chunk1.y) <= tuning.RESCUE_LEVEL_PAD):
            # 同层：直接走过去（原版地面追人就是这么走的）
            self._rescue_exec = None
            b.walk_to(ob.chunk1.x)
            return
        ex = self._rescue_exec
        if ex is None or ex.goal.key() != self._rescue_key(ob):
            ex = self._rescue_exec = PlanExecutor(
                self.win, self.planner, self._rescue_goal(ob))
        if ex.update() == GIVEUP:
            self._rescue_exec = None
            self.body.walk_to(ob.chunk1.x)

    def _dead_peer_near(self):
        """附近倒地的同伴（真死 / 晕着的都算）；已经有人在救的不抢。"""
        if getattr(self.win, "is_pup", False):
            return None                     # 幼崽：不救人（也不会被救）
        best, bd = None, tuning.HELPFEED_SEEK_R
        c1 = self.body.chunk1
        for p in self._peers():
            ob = p.body
            if getattr(p, "is_pup", False):
                continue                    # 幼崽不算救援目标
            if not self._peer_needs_help(ob) or self._revive_claimed_by(p) is not None:
                continue
            d = math.hypot(ob.chunk1.x - c1.x, ob.chunk1.y - c1.y)
            if d < bd:
                best, bd = p, d
        return best

    def _revive_claimed_by(self, dead):
        """这只死猫是否已经有别的猫在救（一个死者配一个救护者就够）。

        不记登记表：直接看谁的状态是「Socialize + revive + 目标就是它」。
        救活、放弃、或者救护者自己倒下都会离开 Socialize，认领自然失效，
        死猫就重新变得可被认领。
        """
        for q in self._peers():
            if q.body.dead:
                continue
            beh = getattr(q, "behavior", None)
            if beh is None or beh.state != "Socialize":
                continue
            if beh._social_kind == "revive" and beh._social_target is dead:
                return q
        return None

    def _free_pearl_near(self):
        """脚边能捡的珍珠（喜欢珍珠的猫闲着会去叼）。"""
        best, bd = None, tuning.PEARL_SEEK_R
        c0 = self.body.chunk0
        for pr in getattr(self.win, "pearls", ()):
            if getattr(pr, "state", None) != ItemState.FREE:
                continue
            d = math.hypot(pr.x - c0.x, pr.y - c0.y)
            if d < bd:
                best, bd = pr, d
        return best

    def _nearest_free_food(self):
        best, bd = None, tuning.HELPFEED_SEEK_R
        c1 = self.body.chunk1
        for f in self.win.fetchables():
            if getattr(f, "state", None) != ItemState.FREE:
                continue
            if getattr(f, "bites", 0) <= 0:      # 珍珠这类不是食物
                continue
            if getattr(f, "is_karma", False):     # 业力花不填饱食度，不算帮喂目标
                continue
            d = math.hypot(f.x - c1.x, f.y - c1.y)
            d = _interest_key(self.win, f, d, tuning.INTEREST_JITTER,
                              tuning.INTEREST_TAKEN_MUL, kind="help")
            if d < bd:
                best, bd = f, d
        return best

    def _needle_only(self) -> bool:
        """这只猫是不是「只用自己的活白针」动手（矛大师，tail_needle）。

        用户口径：矛大师只拿尾巴长出来、还连着细绳的白针攻击 —— 地上捡的普通矛、
        石头一律不当武器（白针扎中活物才回饱食度，别的家伙喂不了它）。
        这条闸统管「算不算持械 / 去捡什么 / 掷什么」，别的猫完全不受影响。
        """
        return bool(self.win.cat.tuning.get("tail_needle"))

    def _weapon_ready(self) -> bool:
        """手里拿着家伙、脚边有能马上捡的，或（猎手）背上还备着一支。

        纯查询：不许在这里动背包里的矛 —— 原版是「真要动手时」才
        CanRetrieveSpearFromBack 抽出来（见 _st_fightthreat）。
        """
        b = self.body
        if b.carried_spear is not None or b.carried_stone is not None:
            if not self._needle_only():
                return True
            if self._own_needle(b.carried_spear):
                return True                  # 矛大师：手里得是活白针才算持械
        w = self._nearest_ground_weapon()
        if w is not None and math.hypot(w.x - b.chunk1.x,
                                        w.y - b.chunk1.y) < tuning.FIGHT_ARM_R:
            return True
        if b.back_spear is not None:
            if not self._needle_only() or self._own_needle(b.back_spear):
                return True
        return False

    def _needle_pref(self, sp) -> float:
        """矛大师永远优先用白针：活着的尾针在候选里权重极大。"""
        if (self.win.cat.tuning.get("tail_needle")
                and getattr(sp, "needle_live", False)):
            return 0.05
        return 1.0

    def _spear_usable(self, sp) -> bool:
        """地上这枝矛此刻取不取用：钉成杆的矛只有工匠拔得动（用户口径）。"""
        if not getattr(sp, "pinned", False):
            return True
        return bool(getattr(self.body.stats, "is_artificer", False))

    def _nearest_ground_weapon(self):
        """地上能捡的石头/矛（原版捡起投掷物）；肯不肯捡矛看用矛意愿。

        矛大师（tail_needle）例外：地上这些一概不算 —— 石头和普通矛都换不来
        饱食度，捡了还白占一只手，挡着尾巴长下一根白针。
        """
        sfac = clampf(float(getattr(self.pers, "spear_like", 1.0)), 0.05, 2.0)
        needle_only = self._needle_only()
        best, bd = None, 260.0
        c1 = self.body.chunk1
        for s in (self.win.stones if not needle_only else ()):
            if s.state != ItemState.FREE or getattr(s, "unfetchable", False):
                continue
            if not s.at_rest_on_ground(self.HL):
                continue
            d = math.hypot(s.x - c1.x, s.y - c1.y)
            if d < bd:
                best, bd = s, d
        for s in self.win.spears:
            if s.state != ItemState.FREE or getattr(s, "stuck_to", None) is not None:
                continue
            if not self._spear_usable(s):        # 钉成杆的矛：只有工匠拔得动
                continue
            if needle_only and not self._own_needle(s):
                continue                         # 矛大师：地上只有自己的活白针值得捡
            if not (getattr(s, "stuck", False) or (abs(s.vx) < 0.4 and abs(s.vy) < 0.4)):
                continue
            d = math.hypot(s.x - c1.x, s.y - c1.y) / sfac * self._needle_pref(s)
            if d < bd:
                best, bd = s, d
        return best

    # ── 每 tick 的强制欲望仲裁 ──
    def _wants_tick(self, cursor):
        """社交/帮助/反击/匍匐躲避在「没正事」的态里按优先级抢班。"""
        for k in ("_social_cd", "_help_cd", "_fight_cd", "_crawl_cd",
                  "_protest_cd", "_revive_cd", "_scold_cd",
                  "_pole_nudge_cd", "_act_cd", "_apology_t", "_thank_t",
                  "_arm_cd", "_cover_cd", "_pincur_cd"):
            v = getattr(self, k)
            if v > 0:
                setattr(self, k, v - 1)
        if self.grab.active or self._exhausted or self._zerog():
            return
        if self.state not in _WANTS_FROM:
            return
        b = self.body
        brave = getattr(self.pers, "bravery", 0.5)
        kind = getattr(self.pers, "kindness", 0.5)
        # 0) 威胁已在 _face_threat_tick（主 tick 的唯一威胁入口）里处理完：
        #    迎战 / 拿家伙 / 救人 / 撤退都在那儿一次性决定，这里不再重复抢班。
        # 0b) 送礼驯服：手里端着蝉乌贼 → 极低概率决定去喂未驯服的蜥蜴
        #     （原版 FriendTracker.GiftRecieved；概率调得极低，驯服是稀有事）
        if self._carrying_gift() and self.rng.random() < tuning.GIFT_START_P:
            glz = self.win.nearest_untamed_lizard(b.chunk1.x)
            if glz is not None and abs(glz.x - b.chunk1.x) <= tuning.GIFT_SEEK_R:
                self._social_kind = "gift"
                self._social_target = glz
                self._social_left = tuning.GIFT_TRY_TICKS
                self._gift_wait = 0
                self._break_active_controllers()
                self._transition("Socialize")
                return
        # 1) 误伤同伴 → 抱歉：走过去拍拍它（安抚；非蜥蜴对象不再匍匐）
        if self._apology_t > 0:
            ap = self._apology_target
            if ap is None or ap.body.dead:
                self._apology_target = None
                self._apology_t = 0
            else:
                d = math.hypot(ap.body.chunk1.x - b.chunk1.x,
                               ap.body.chunk1.y - b.chunk1.y)
                if d > tuning.SOCIAL_R:
                    self._apology_t = 0        # 跑太远了：算了
                else:
                    self._social_kind = "pat"         # 拍拍 = 抱歉 / 安抚
                    self._social_target = ap
                    self._social_left = tuning.APOLOGY_TICKS
                    self._break_active_controllers()
                    self._transition("Socialize")
                    return
        # 1b) 被同伴救活 → 去拍拍恩人（感谢）。不强制：恩人跑远了就算了，
        #     而且只有掷骰掷中才去谢（_thank_t 就是道谢窗口，来回几次机会）。
        if self._thank_t > 0 and self._thank_target is not None:
            th = self._thank_target
            far = (th is not self and th.body is not None
                   and math.hypot(th.body.chunk1.x - b.chunk1.x,
                                  th.body.chunk1.y - b.chunk1.y) > tuning.SOCIAL_R)
            if th.body.dead or th is self or far:
                self._thank_target = None
                self._thank_t = 0
            elif self.rng.random() < tuning.SOCIAL_THANK_P:
                # 不强制：每 tick 小概率才动身，窗口内基本会去；对象跑远就放弃
                self._social_kind = "pat"         # 拍拍 = 喜欢/感谢
                self._social_target = th
                self._social_left = tuning.THANK_TICKS
                self._break_active_controllers()
                self._transition("Socialize")
                return
        # 2) 倒地的同伴（真死 / 被击晕）：过去用特殊表情扒拉救活。善良的更积极
        if self._revive_cd <= 0 and not b.swimming:
            dp = self._dead_peer_near()
            # 先看有没有倒地的同伴再掷骰：没同伴就不动随机流（随机数纪律）
            if dp is not None and self._wants_rescue(kind):
                self._social_kind = "revive"
                self._social_target = dp
                self._social_left = tuning.REVIVE_APPROACH_TICKS
                self._break_active_controllers()
                self._transition("Socialize")
                return
        # 2) 自己饱了、别的猫没饱 → 帮它取食送过去
        if (self._help_cd <= 0 and b.food_satisfied()
                and b.carried_fruit is None):
            hp = self._hungriest_peer()
            if hp is not None:
                self._help_target = hp
                self._help_left = tuning.HELPFEED_TICKS
                self._break_active_controllers()
                self._transition("HelpFeed")
                return
        # 3) 被抢了果子 → 去扒拉指指点点那个小偷
        if self._protest_cd <= 0 and self._protest_target is not None:
            th = self._protest_target
            if getattr(getattr(th, "body", None), "dead", True):
                self._protest_target = None
            else:
                self._start_protest(th, self._protest_kind)
                return
        # 4) 反击：被咬/被砸后（anger>0）仇人还在附近
        #    手里/脚边有家伙时也会主动迎战（原版持械的猫）
        if self._fight_cd <= 0:
            ranged = self.anger > 0          # 被咬/被砸过：记仇，去报复（会先找家伙）
            armed = self._weapon_ready()
            # 越勇敢迎战越远。**空手不再主动扑上去**：原版空手根本打不动蜥蜴，
            # 旧版让高勇敢的猫空手也能进 FightThreat，进去发现没家伙立刻
            # _fight_end，于是反复「冲上去 → 结束」——就是「飞快上去挤着送死」。
            r = tuning.FIGHT_R if ranged else (
                tuning.FIGHT_ARM_R * (0.55 + 0.90 * brave) if armed else 0.0)
            if self._spear_rage():                 # 矛大师狂暴：整屏找目标
                r = max(r, tuning.SPEAR_RAGE_R)
                lz = self._rage_target(r)
            else:
                lz = self._nearest_throw_target(r) if r > 0.0 else None
            can_rip = (brave >= tuning.RIP_SPEAR_BRAVE and lz is not None
                       and self._nearest_rip_spear(lz) is not None)
            if lz is not None and (ranged or armed or can_rip):
                self._fight_target = lz
                self._fight_left = tuning.FIGHT_TICKS
                self._break_active_controllers()
                self._transition("FightThreat")
                return
        # 4b) 威胁圈内有活威胁 → 倾向握家伙：空手且近处有矛/石头就过去捡起来
        if (self._arm_cd <= 0 and not self.grab.active and not b.swimming
                and b.on_floor() and not self._exhausted
                and b.carried_spear is None and b.carried_stone is None
                and b.carried_fruit is None
                and self.state in _MAKEWAY_FROM):
            tlz = self._threat_lizard()
            if tlz is not None:
                gw = self._nearest_ground_weapon()
                if (gw is not None
                        and math.hypot(gw.x - b.chunk1.x, gw.y - b.chunk1.y)
                        <= tuning.ARM_SEEK_R):
                    self._fight_target = tlz
                    self._fight_left = tuning.FIGHT_TICKS
                    self._arm_cd = tuning.ARM_COOLDOWN
                    self._break_active_controllers()
                    self._transition("FightThreat")
                    return
        # 5) 恐惧/威胁：已合并到 _face_threat_tick（主 tick 入口），此处不再重复。
        # 5b) 猎手怪癖：拿矛去钉鼠标（钉上的矛甩一下鼠标就能甩下来）。
        #     门槛＝「对光标的兴趣攒满 + 按性格出手」，不是每 tick 掷一次渺茫的骰：
        #     光标待在附近就开始攒（spear_like / hurry / activity 决定出手率），
        #     手上有矛或背上有矛都算（背上会自动抽出来）。
        if (self._pincur_cd <= 0 and self.state in _IDLE_SOCIAL_FROM
                and not b.swimming and b.on_floor() and cursor is not None
                and getattr(self.pers, "spear_like", 1.0) >= tuning.PIN_CURSOR_SPEAR_LIKE
                and self._armed_in_hand()):
            self._pincur_urge = min(1.0, self._pincur_urge + tuning.PIN_CURSOR_URGE_RATE)
            if self._pincur_urge >= 1.0:
                sl = clampf(float(getattr(self.pers, "spear_like", 1.0)), 0.0, 2.0) * 0.5
                hu = clampf(float(getattr(self.pers, "hurry", 0.5)), 0.0, 1.0)
                ac = clampf(float(getattr(self.pers, "activity", 0.5)), 0.0, 1.0)
                p = clampf(tuning.PIN_CURSOR_ARMED_P * sl * (0.5 + hu) * (0.6 + 0.8 * ac),
                           0.0, 1.0)
                if self.rng.random() < p:
                    self._pincur_urge = 0.0
                    if self._pin_throw_at_cursor(cursor):
                        return
        else:
            self._pincur_urge = max(0.0, self._pincur_urge - tuning.PIN_CURSOR_URGE_RATE)
        # 6) 平时：附近有同伴 / 鼠标在附近停够久 → 随手做个小社交动作（不切态）
        if (self._act_cd <= 0 and self.state in _IDLE_SOCIAL_FROM
                and not b.swimming and b.on_floor()):
            self._idle_social_try(cursor)

    def _social_kind_for(self, tgt) -> str:
        """社交欲望满时对这一位同伴要做的动作：同伴在睡就按 wake_like 改成「摇醒」。"""
        kind = self._pick_social_kind(tgt)
        if kind != "wake" and self._peer_asleep(tgt):
            wl = clampf(float(getattr(self.pers, "wake_like", 0.5)), 0.0, 1.0)
            if self.rng.random() < tuning.WAKE_P * (0.2 + 1.6 * wl):
                kind = "wake"
        return kind

    def _pick_social_kind(self, tgt):
        """社交欲望攒满 → 按性格从动作词表（behavior/social.py）里加权抽一个动作。"""
        pers = self.pers
        soc = getattr(pers, "sociability", 0.5)
        pl = getattr(pers, "point_like", 0.5)
        cl = getattr(pers, "crawl_like", 0.5)
        # 被它抢过东西：这笔账还没过期的话，社交动作明显偏向「指指点点」
        # （性格只决定平常的分布，记仇是跨性格的）
        grudge = tuning.GRUDGE_SCOLD_MUL if self._grudge_alive(tgt) else 1.0
        opts = [
            ("pet", tuning.PET_BASE * (0.4 + 1.2 * soc)),      # 抚摸：喜欢/安抚
            ("pat", tuning.PAT_BASE * (0.4 + 1.2 * soc)),      # 拍拍：喜欢/安抚
            ("point", tuning.POINTHOLD_BASE),                  # 指向：想要/注意
            ("scold", tuning.SOCIAL_SCOLD_BASE * (0.3 + 1.4 * pl) * grudge),  # 指指点点
        ]
        if cl > 0.25:
            # 匍匐族只剩「匍匐行走（害怕强敌潜行）」，而且必须是附近真有蜥蜴才抽得到：
            # 遇到同伴 / 鼠标这些非蜥蜴对象不再做任何匍匐动作（匍匐指指点点、匍匐指向已删）。
            if self._nearest_lizard(tuning.CRAWL_FEAR_R * 1.6) is not None:
                opts.append(("crouch_walk", tuning.CROUCH_WALK_BASE * (0.3 + 1.4 * cl)))
        total = sum(w for _, w in opts)
        if total <= 0.0:
            return "pet"
        r = self.rng.random() * total
        acc = 0.0
        for k, w in opts:
            acc += w
            if r <= acc:
                return k
        return opts[-1][0]

    def _start_protest(self, thief, kind="protest"):
        """被抢东西 → 过去扒拉指指点点（旁边的同伴看见也会跟着起哄）。

        kind 由 SocialResponseChooser 定：protest=指指点点（指责）、
        point=指着（请求/示意）、watch=围观（留下来看着）。
        """
        self._social_kind = kind
        self._social_target = thief
        self._social_left = tuning.PROTEST_TICKS
        self._break_active_controllers()
        self._transition("Socialize")
        self._witness_protest(thief)

    def _board_loss_tick(self):
        """抢位形槽抢输了 → 生成一条「我的目标被谁拿走了」的事件。

        位形槽满了不是「不能去」，是「去了要排队」；排队在社会层要有反应。
        这里只负责生成事实与关系账，具体反应（指 / 指指点点 / 追过去 / 围观 /
        算了）交给 SocialResponseChooser 按性格与关系定。太远就算了 —— 社交
        动作一律不强制。
        """
        if self.state not in _WANTS_FROM or self.grab.active or self._zerog():
            return
        loss = board_for(self.win).consume_loss(self.win)
        if loss is None:
            return
        obj, winner = loss
        if winner is None or winner is self.win or self._social_left > 0:
            return
        wb = getattr(winner, "body", None)
        if wb is None or getattr(wb, "dead", False):
            return
        d = math.hypot(wb.chunk1.x - self.body.chunk1.x,
                       wb.chunk1.y - self.body.chunk1.y)
        if d > tuning.PROTEST_R:
            return
        EV.emit_for(self.win, EV.OBJECT_TAKEN, subject=winner, obj=obj,
                    other=self.win, intensity=0.7)

    def _witness_protest(self, thief):
        """目击同伴被抢：往总线上发一条「有人在指责谁」，谁跟不跟由各自决定。

        原版拾荒者的威吓与指认本来就是群体行为；这里让「一个猫的动作被另一只
        猫看见、然后产生下一个动作」成链 —— 目击者在自己的 _event_tick 里按
        性格与关系选反应（高 sociability 的留下来围观，高 point_like 的跟着指），
        而不是在这里全场广播、人人必做。
        """
        EV.emit_for(self.win, EV.GESTURE_SCOLDED, subject=self.win, obj=thief,
                    intensity=0.6)

    def _watch_fetch_steal(self):
        """盯住正在取的果子：被别人抢先拿走 → 记下小偷，回头去扒拉。"""
        if self.state == "FetchFruit" and self.fetch is not None:
            f = getattr(self.fetch, "target", None)
            if f is not None and getattr(f, "state", None) == ItemState.FREE:
                self._fetch_watch = f
                return
        f = self._fetch_watch
        if f is None:
            return
        if getattr(f, "state", None) == ItemState.FREE:
            if self.timer > 800:
                self._fetch_watch = None
            return
        self._fetch_watch = None
        thief = self._thief_of(f)
        if thief is None:
            # 认不出是谁拿走的：只当「东西没了」，不冤枉最近的同伴
            # （旧版找不到人就退化成 _nearest_peer()，于是经常骂错人）
            return
        EV.emit_for(self.win, EV.OBJECT_TAKEN, subject=thief, obj=f,
                    other=self.win, intensity=0.7)

    def _thief_of(self, f):
        """谁拿走了这件东西：先看手上，再看谁正认领它（认领板）。认不出则 None。"""
        for p in self._living_peers():
            if p.body.carried_fruit is f or p.body.carried_stone is f:
                return p
        holder = board_for(self.win).owner(f)
        # 认领板上可能有世界生物（蜥蜴 / 拾荒者）占的位：它们不是猫，不能当小偷
        if (holder is None or holder is self.win
                or getattr(holder, "body", None) is None
                or getattr(holder.body, "dead", False)):
            return None
        return holder

    # ── 被抢的记忆：下次它再靠近我的东西，这笔账还在 ──
    def _remember_grievance(self, other) -> None:
        """被它抢过 / 被它打过：记一笔怨气（记在关系表里，会随时间衰减）。"""
        self._rel.note_toward(other, "resentment", 0.35,
                              getattr(self.win, "_pole_tick", 0))

    def _grudge_alive(self, other) -> bool:
        """这笔账还没过期：怨气还没衰减到阈值以下（旧版是按 tick 计时）。"""
        return self._rel.resents(other) >= tuning.GRUDGE_RESENT_THRESH

    # ── 事件 → 关系 → 社会反应（FSM 在这里只是执行器）──
    def _social_ctx(self, dist) -> SocialContext:
        """反应判断能看到的当下情境。"""
        busy = 1.0 if self.grab.active else (
            0.0 if self.state in _WANTS_FROM else 0.6)
        return SocialContext(
            busy=busy,
            threat=1.0 if self._threat_present() else 0.0,
            far=clampf((dist - tuning.PROTEST_R * 0.5)
                       / max(1.0, tuning.PROTEST_R * 0.5), 0.0, 1.0))

    def _react(self, event, who, dist):
        """按事件选一个社会反应并落到状态上（SocialResponseChooser）。

        反应可能是「什么都不做」—— 那不是失败，而是这只猫对这件事的解释。
        选出来的反应写进 _last_response，状态面板与测试都读它。
        """
        if who is None or who is self.win:
            return None
        resp, strength = _choose_response(event, self.pers, self._rel,
                                          self._social_ctx(dist), self.rng)
        self._last_response = (resp, strength)
        self.gfx.look(who, PRIO_URGENT)          # 至少先看它一眼
        if getattr(who, "body", None) is None:
            # 对象不是同伴（蜥蜴 / 拾荒者）：没有「社交」可言，只剩敢不敢打。
            # 「挑战 / 指责」在这里都翻成「记上这一笔，回头找它算账」——
            # 复用被咬之后的报复路径（_wants_tick 第 4 条会去找家伙）。
            if resp in ("challenge", "scold"):
                self.body.temper_shift(tuning.TEMPER_CHALLENGE)
                self.anger = max(self.anger, ANGER_TOTAL)
            return resp
        if resp == "scold":
            self._protest_kind = "protest"
            self._protest_target = who
        elif resp in ("point", "ask", "follow"):
            self._protest_kind = "point"
            self._protest_target = who
        elif resp == "challenge":
            self._protest_kind = "protest"
            self._protest_target = who
            self.body.temper_shift(tuning.TEMPER_CHALLENGE)
        elif resp == "observe":
            self._protest_kind = "watch"        # 留下来看一会儿（围观本身是身体语言）
            self._protest_target = who
            self.gfx.look(who, PRIO_AMBIENT)
        elif resp == "replace_target" and event.obj is not None:
            # 算了：这件东西不跟它抢了，转头干别的（认领板黑名单，见 board.py）
            board_for(self.win).blacklist(self.win, event.obj,
                                          getattr(self.win, "_pole_tick", 0))
        return resp

    def _event_tick(self) -> None:
        """消化总线上的事件：先记关系，再按性格/关系选反应。

        高优先级反应（被咬、被抓、目标死亡）本来就在别的分支逐 tick 处理；
        这里管的是普通社会事件 —— 谁的东西被谁拿走、谁被谁打了、谁在指谁。

        记账和反应都先过一道「我看见了吗」：当事人全额，旁边看见的目击者按
        WITNESS_SCALE 打折，目击半径之外的人和这件事无关 —— 否则屏幕另一头
        发生什么都会改变我对某只猫的看法，那不是关系，是全局广播。
        """
        tick = int(getattr(self.win, "_pole_tick", 0) or 0)
        self._rel.decay(tick)
        bus = EV.bus_for(self.win)
        me = self.win
        dead = bool(getattr(self.body, "dead", False))
        for ev in bus.since(self._ev_seen):
            self._ev_seen = ev.seq                  # 看过就推进游标
            mine = ev.involves(me)
            if not mine and (dead or not bus.witnesses(ev, (me,))):
                continue                       # 没看见（或已经死了）：与我无关
            self._rel.note(ev, scale=1.0 if mine else WITNESS_SCALE)
            if ev.subject is None or dead:
                continue
            who = target_of(ev)
            if who is None or who is me:       # 该反应的对象是自己：没什么好说的
                continue
            if (self._social_left > 0 or self._protest_cd > 0 or self.grab.active
                    or self._zerog() or self.state not in _WANTS_FROM):
                continue
            p = point_of(who)
            if p is None:
                continue
            d = math.hypot(p[0] - self.body.chunk1.x, p[1] - self.body.chunk1.y)
            # 看见了就记账、就有反应 —— 「值不值得走过去」不在这里一刀切：
            # 距离折进 ctx.far（越远的「指责 / 挑战」分越低），真要去理论由
            # 社交态自己的接近与放弃逻辑决定（社交动作一律不强制）。
            if ev.intensity < EV.REACT_INTENSITY_MIN:
                continue
            self._react(ev, who, d)

    # ── 睡眠欲望：吃饱后入睡概率从 0 缓慢升到 100 ──
    def _settle_to_rest(self):
        """趴/睡前先落地：解开吊顶与悬浮（原版没有挂在半空睡着的猫）。"""
        b = self.body
        if b.ceil_cling:
            b.release_ceiling()
        b.suspended = False

    def _sleep_drop_hands(self):
        """入睡前把手里攥着的东西放到地上（否则会攥着食物蜷着睡不着）。"""
        b = self.body
        if b.carried_fruit is not None:
            f = b.carried_fruit
            f.stalk = None
            f.state = "free"
            f.held_by_hand = None
            b.release_fruit()
            f.y = min(f.y, b.chunk1.y - f.rad)
        if b.carried_stone is not None:
            b.release_stone(to_free=True)
        if b.carried_spear is not None:
            b.release_spear(to_free=True)

    def _sleep_urge_tick(self):
        full = (self.body.food_satisfied()
                and not self._too_cold_to_sleep() and not self._hibernating)
        if full:
            self._sleep_urge = min(1.0, self._sleep_urge + tuning.SLEEP_URGE_RATE)
        else:
            self._sleep_urge = max(0.0, self._sleep_urge - tuning.SLEEP_URGE_DECAY)

    def _sleep_roll(self) -> bool:
        """每隔 SLEEP_CHECK_TICKS 掷一次骰，概率 = 当前睡意。"""
        if not self.body.food_satisfied() or self._sleep_urge <= 0.0:
            return False
        if self._threat_present():          # 场上还有活威胁 → 睡不着
            return False
        self._sleep_check = (self._sleep_check + 1) % tuning.SLEEP_CHECK_TICKS
        if self._sleep_check:
            return False
        # 睡意即概率：平方后刚吃饱几乎不睡、攒满必睡（避免吃饱几秒就倒头睡）
        return self.rng.random() < self._sleep_urge * self._sleep_urge

    # ── 被同伴救：特殊表情扒拉一会儿就复活 ──
    def nuzzle(self, ticks: int = 1, by=None) -> bool:
        if self.state != "Dead" or self._reincarnate:
            return False
        if by is not None:
            self._reviver = by
        self._nuzzle_t += int(ticks)
        if self._nuzzle_t < tuning.REVIVE_TOUCH_TICKS:
            return False
        self._nuzzle_t = 0
        self._revive_timer = 1
        return True

    def accept_gift_food(self, fruit) -> bool:
        """同伴喂到嘴边：吃掉，涨饱食/好感/体力。"""
        if self.state == "Dead":
            return False
        bites = max(1, int(getattr(fruit, "bites", 1)))
        self.body.food_eat(bites)
        self.body.temper_shift(tuning.TEMPER_FEED)
        self.body.energy_change(tuning.EN_EAT_RESTORE * bites)
        self.meat_sick(fruit)            # 同伴喂来的荤食：素食猫照晕
        fruit.stalk = None
        fruit.state = ItemState.EATEN
        if fruit in getattr(self.win, "fruits", ()):
            self.win.fruits.remove(fruit)
        return True

    # ── 断态清理 ──
    def _save_walk_limits(self):
        if self._saved_walk is None:
            self._saved_walk = (self.body.walk_min, self.body.walk_max)
            self.body.walk_min = None
            self.body.walk_max = None

    def _restore_walk_limits(self):
        if self._saved_walk is not None:
            self.body.walk_min, self.body.walk_max = self._saved_walk
            self._saved_walk = None

    def _social_cleanup(self):
        self._act_end()
        self.body.set_crawl(False)          # 匍匐类社交动作收势：站起来
        self._social_gesture = None
        self._social_press_seen = 0
        self._social_press_down = False
        self.gfx.face_override = None       # 借来的表情（按压时的晕眩脸）收势
        self._rescue_exec = None            # 救援赶路的执行器（换了目标就重建）
        self._social_urge = 0.0             # 社交欲望：做完归 0，重新慢慢攒
        if self._social_target is self._apology_target and self._apology_target is not None:
            self._apology_target = None     # 抱歉做完了
            self._apology_t = 0
        elif self._social_target is self._thank_target and self._thank_target is not None:
            self._thank_target = None       # 谢过了
            self._thank_t = 0
        elif self._social_kind == "gift":
            self._gift_left = 0
        if self._social_kind == "revive":
            # 被威胁打断 / 刚救完：短冷却，马上能再上手；磨到超时才算真放弃
            self._revive_cd = (T_REVIVE_RETRY if self._revive_gave_up
                               else T_REVIVE_RETRY_SOON)
            self._revive_gave_up = False
        elif self._social_kind == "protest":
            self._protest_cd = T_PROTEST_RETRY
        else:
            self._social_cd = T_SOCIAL_RETRY
        self._social_target = None
        self._protest_target = None

    def _end_social(self):
        self._social_cleanup()
        self._transition("IdleStand")

    def _wants_break(self, st):
        """中断新欲望态时的收尾（不切换状态）。"""
        b = self.body
        if st == "CeilingHang":
            b.release_ceiling()
        elif st == "CrawlAway":
            b.set_crawl(False)
        elif st == "ScoldBlocker":
            self._scold_cleanup()
        elif st == "Socialize":
            self._social_cleanup()
        elif st == "HelpFeed":
            self._help_cd = T_HELP_RETRY
            self._help_target = None
            self.gfx.face(False, PRIO_URGENT)
        elif st == "FightThreat":
            self._fight_cd = T_FIGHT_RETRY
            self._fight_target = None
            self._fight_climber_release()
        elif st == "ChaseCursor":
            self._cursor_plan_end()
            self._act_end()
        elif st == "EatCob":
            self.gfx.hand_aim["l"] = None
            self.gfx.hand_aim["r"] = None
            self.body.eat_raise = 0.0
            self._cob = None
            self._cob_climber_release()
            self._cob_eat_t = 0
            self._cob_seek_cd = T_COB_RETRY
        elif st == "CatchFly":
            self._flycatch_release()
        elif st == "ItemPlay":
            self._itemplay_end()
        elif st == "CoverAlly":
            self._cover_cd = T_COVER_RETRY
            self._cover_ally = None
            self.gfx.face(False, PRIO_URGENT)
        self._restore_walk_limits()

    # ── 有威胁、自己空手：躲到「持有矛/石头的同伴」背后（用户规格）──
    def _peer_armed(self, p) -> bool:
        """同伴手上/背上有没有家伙（矛/石头）。"""
        ob = getattr(p, "body", None)
        if ob is None or ob.dead:
            return False
        return (ob.carried_spear is not None or ob.carried_stone is not None
                or getattr(ob, "back_spear", None) is not None)

    def _armed_peer(self):
        """最近一个持械同伴（有威胁时空手猫的掩体）。"""
        best, bd = None, COVER_SEEK_R
        c1 = self.body.chunk1
        for p in self._living_peers():
            if not self._peer_armed(p):
                continue
            ob = p.body
            d = math.hypot(ob.chunk1.x - c1.x, ob.chunk1.y - c1.y)
            if d < bd:
                best, bd = p, d
        return best

    def _cover_x(self, ally, th):
        """躲到同伴背后时该站的 x：同伴背对威胁的那一侧。"""
        ob = getattr(ally, "body", None) if ally is not None else None
        if ob is None or ob.dead or not self._peer_armed(ally):
            return None
        side = 1.0 if ob.chunk1.x >= th.x else -1.0
        lo = 0.0 if self.body.walk_min is None else self.body.walk_min
        hi = self.WL if self.body.walk_max is None else self.body.walk_max
        return clampf(ob.chunk1.x + side * COVER_BACK_OFF, lo, hi)

    def _cover_ally_start(self, th) -> bool:
        """有威胁、自己空手 → 起手「躲到持械同伴背后」。返回是否已切态。"""
        b = self.body
        if self._weapon_ready():
            return False                    # 手里有家伙：照旧迎战/逃
        gw = self._nearest_ground_weapon()
        if (gw is not None
                and math.hypot(gw.x - b.chunk1.x, gw.y - b.chunk1.y)
                <= tuning.ARM_SEEK_R):
            return False                    # 近处有家伙可捡：先去拿
        ally = self._armed_peer()
        tx = self._cover_x(ally, th) if ally is not None else None
        if tx is None:
            return False
        if abs(tx - th.x) < COVER_MIN_GAP:
            return False                    # 躲过去的落点离威胁太近：宁可跑开
        self._cover_ally = ally
        self._break_active_controllers()
        self._transition("CoverAlly")
        return True

    def _cover_enter(self):
        b = self.body
        b.set_posture(True)
        b.stop_walk()

    def _st_coverally(self, cursor, disturbed):
        """空手的猫缩在持械同伴背对威胁的那一侧（跟着它挪，威胁没了就走开）。"""
        b = self.body
        if self.grab.active:
            self._transition("Dragged")
            return
        ally = self._cover_ally
        ob = getattr(ally, "body", None) if ally is not None else None
        th = self._threat_lizard()
        if (ob is None or ob.dead or th is None or not self._peer_armed(ally)
                or self.timer >= COVER_TICKS):
            self._transition("IdleStand")
            return
        fd = math.hypot(th.x - b.chunk1.x, th.y - b.chunk1.y)
        if fd <= tuning.FEAR_TOO_CLOSE_R:
            self._flee_lizard_now(th)                   # 威胁压上来：逃命优先于躲掩体
            return
        if self._weapon_ready():                        # 自己拿到家伙了：不躲了
            self._transition("IdleStand")
            return
        tx = self._cover_x(ally, th)                    # 站到威胁够不着的那一侧
        if tx is None:
            self._transition("IdleStand")
            return
        if abs(tx - b.chunk1.x) > WALK_STOP_EPS:
            b.walk_to(tx)
        else:
            b.stop_walk()
        b.facing = 1 if th.x >= b.chunk0.x else -1      # 面朝威胁，随时能跑
        self.gfx.look_at = (th.x, th.y)

    # ── 吊顶：窗口上边缘＝地面/天花 ──
    def _ceiling_enter(self):
        b = self.body
        if self._ceil_placed:            # 鼠标放上去的：多挂一会（原版这里是没得挂）
            self._ceil_left = self.rng.randint(tuning.CEIL_PLACED_TICKS_MIN,
                                               tuning.CEIL_PLACED_TICKS_MAX)
            self._ceil_placed = False
        else:
            self._ceil_left = self.rng.randint(tuning.CEIL_HANG_TICKS_MIN,
                                               tuning.CEIL_HANG_TICKS_MAX)
        self._ceil_walk_t = 0
        self._hibernating = False        # 吊在顶上不算睡觉（免得蜷在半空）
        b.set_posture(True)
        b.stop_walk()

    def _st_ceilinghang(self, cursor, disturbed):
        b = self.body
        if not self._can_ceil_cling():      # 顶端不许攀附（只有圣徒的舌头能）
            b.release_ceiling()
            self._transition("Airborne" if not b.on_floor() else "IdleStand")
            return
        if self.grab.active:
            b.release_ceiling()
            self._transition("Dragged")
            return
        if not b.ceil_cling:
            if not self._ceiling_reachable():
                if b.on_floor() and self.timer % 20 == 0:
                    b.request_jump("stand")
                if self.timer > 160:
                    self._transition("Airborne")
                return
            if not b.grab_ceiling(b.chunk0.x):
                self._transition("Airborne")
                return
            self.timer = 0
        self._ceil_left -= 1
        self.gfx.look_at = cursor
        # 上边缘当平地：沿着顶边像走路一样挪动
        if self._ceil_walk_t > 0:
            self._ceil_walk_t -= 1
            b.ceil_shimmy(float(self._ceil_dir))
        elif self.rng.random() < tuning.CEIL_WALK_PROB:
            self._ceil_dir = 1 if self.rng.random() < 0.5 else -1
            self._ceil_walk_t = self.rng.randint(tuning.CEIL_WALK_TICKS_MIN,
                                                 tuning.CEIL_WALK_TICKS_MAX)
        if self._ceil_left <= 0:
            b.release_ceiling()
            self._transition("Airborne")

    # ── 玩耍：追光标 / 试着跳跃够鼠标 ──
    def _cursor_plan_end(self):
        ex = self._cursor_exec
        self._cursor_exec = None
        if ex is not None:
            ex.cancel()
        self._cursor_goal = None
        self._cursor_plan_pos = None
        self._cursor_replan_cd = 0
        self._cursor_jump_cd = 0
        self.body.stop_walk()

    def _cursor_dynamic_goal(self):
        """鼠标目标是动态 Goal：Planner 每次取 pos() 都拿当前光标，而不是起手那一帧的死坐标。"""
        if self._cursor_goal is None:
            self._cursor_goal = Goal(
                lambda: self.cursor if self.cursor is not None else (0.0, 0.0),
                lambda: self.cursor is not None,
                ("cursor-play", id(self.win)))
        return self._cursor_goal

    def _cursor_nav_tick(self, cursor):
        """追鼠标统一走 Planner：直走 / 跳 / 多段表面路线都由同一套导航选择。

        鼠标本身不断移动，所以除了 Goal 动态位置，还会定期按位移主动重规划；
        否则一条已经针对旧光标位置生成的跳弧/绕行路线会追到「旧鼠标」。
        """
        goal = self._cursor_dynamic_goal()
        pos_changed = (self._cursor_plan_pos is None
                       or math.hypot(cursor[0] - self._cursor_plan_pos[0],
                                      cursor[1] - self._cursor_plan_pos[1]) >= 24.0)
        if (self._cursor_exec is None or self._cursor_replan_cd <= 0 or pos_changed):
            if self._cursor_exec is not None:
                self._cursor_exec.cancel()
            self._cursor_exec = PlanExecutor(self.win, self.planner, goal)
            self._cursor_plan_pos = tuple(cursor)
            self._cursor_replan_cd = 10
        else:
            self._cursor_replan_cd -= 1
        status = self._cursor_exec.update()
        if status == GIVEUP:
            self._cursor_exec = None
            return GIVEUP
        return status

    def _cursor_jump_attempt(self, cursor):
        """只有 Planner 确认「当前鼠标确实存在可用跳跃候选」后，才主动尝试跳。

        这样跳不是随机撞运气：墙后/够不到的鼠标不会反复空跳；能跳到的目标会
        在平地、障碍边缘持续获得跳跃尝试。
        """
        b = self.body
        if self._cursor_jump_cd > 0:
            self._cursor_jump_cd -= 1
            return False
        if not b.on_floor() or b.on_pole or b.ceil_cling:
            return False
        dx = cursor[0] - b.chunk0.x
        dy = b.chunk0.y - cursor[1]
        if abs(dx) < 22.0 and dy <= 8.0:
            return False
        if abs(dy) > JUMPCUR_DY * JUMPCUR_DY_SLACK + 18.0:
            return False
        goal = self._cursor_dynamic_goal()
        try:
            jump_ok = any(c.ability_key == "jump"
                           for c in self.planner.touch_candidates(goal))
        except Exception:
            jump_ok = False
        if not jump_ok:
            return False
        activity = clampf(float(getattr(self.pers, "activity", 0.5)), 0.0, 1.0)
        p = clampf(JUMPCUR_P * (0.75 + 0.7 * activity), 0.0, 0.95)
        if self.rng.random() >= p:
            return False
        md = 1 if dx > 0.0 else -1
        b.move_dir = md
        b.request_jump("stand", hold_ticks=3)
        self._cursor_jump_cd = JUMPCUR_CD
        return True

    def _play_enter(self):
        self._play_left = self.rng.randint(tuning.PLAYCUR_TICKS_MIN,
                                           tuning.PLAYCUR_TICKS_MAX)
        self._cursor_exec = None
        self._cursor_goal = None
        self._cursor_plan_pos = None
        self._cursor_replan_cd = 0
        self._cursor_jump_cd = 0
        self.body.set_posture(True)

    def _st_chasecursor(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._cursor_plan_end()
            self._clear_hands()
            self._transition("Dragged")
            return
        self._play_left -= 1
        if cursor is None:
            self._cursor_plan_end()
            self._clear_hands()
            self._transition("IdleStand")
            return
        cx, cy = cursor
        self.gfx.look_at = cursor
        d = math.hypot(cx - b.chunk0.x, cy - b.chunk0.y)

        # 第一优先：真正调用统一 Planner。目标移动明显时立刻重算，普通情况下每 10 tick
        # 更新一次；路线可能是 walk、jump 或多段 surface route。
        status = self._cursor_nav_tick(cursor)

        # 第二优先：Planner 已经确认能跳，再按性格做「够鼠标」的主动尝试。
        # 这不替代 Planner，只是在它给出 jump 候选时把跳跃从「可能选中」提升成真正的行为。
        self._cursor_jump_attempt(cursor)

        if d <= tuning.PLAYCUR_ARRIVE:
            self._cursor_plan_end()
            b.stop_walk()
            if not self._act_active() and self._cursor_point_ok():
                # 追到鼠标后不总是立刻结束：随机选择指向 / 指指点点继续互动。
                self._act_begin(self._cursor_social_kind(), cursor, mode="cursor")
            self._act_tick()
        elif status == GIVEUP:
            # Planner 实在没有路线时才退回最简单的直奔；下一轮位置变化仍会重新走 Planner。
            b.walk_to(cx)
            self._act_end()
        else:
            self._act_end()

        if self._play_left <= 0 or d > tuning.PLAYCUR_R * 1.6:
            self._cursor_plan_end()
            self._act_end()
            self._transition("IdleStand")

    # ── 社交：靠近/抚摸同伴 · 扒拉指指点点 · 救同伴 ──
    def _social_enter(self):
        b = self.body
        kind = self._social_kind
        if kind == "revive":
            self._social_left = tuning.REVIVE_APPROACH_TICKS
        elif kind == "protest":
            self._social_left = tuning.PROTEST_TICKS
            if not self._needle_only():
                b.drop_all()         # 丢掉手上的东西，腾出手来扒拉
        elif kind == "gift":
            self._social_left = tuning.GIFT_TRY_TICKS   # 送礼：磨到交出去或放弃
        elif kind == "pat":
            if self._social_left <= 0:               # 抱歉/道谢：沿用调用方给的时长
                self._social_left = self.rng.randint(tuning.SOCIAL_TICKS_MIN,
                                                     tuning.SOCIAL_TICKS_MAX)
        elif kind == "watch":
            self._social_left = tuning.OBSERVE_TICKS
        else:
            self._social_left = self.rng.randint(tuning.SOCIAL_TICKS_MIN,
                                                 tuning.SOCIAL_TICKS_MAX)
        self._social_touch = 0
        self._social_gesture = None      # 本次动作的手势（抚摸/拍拍/复活）
        self._social_press_seen = 0
        self._revive_gave_up = False
        if social.is_crouch(kind) and not b.on_pole:   # 匍匐族：趴着做完整段（杆上不匍匐）
            b.set_crawl(True)
        else:
            b.set_posture(True)
        self._clear_hands()

    def _st_socialize(self, cursor, disturbed):
        b = self.body
        tgt = self._social_target
        if self.grab.active:
            self._social_cleanup()
            self._transition("Dragged")
            return
        if tgt is None:
            self._end_social()
            return
        kind = social.ALIASES.get(self._social_kind, self._social_kind)
        if kind == "gift":                 # 给蜥蜴送礼：目标没有 body，用 x/y
            self._st_social_gift(tgt)
            return
        if getattr(tgt, "body", None) is None:
            self._end_social()
            return
        ob = tgt.body
        if social.is_crouch(kind) and not b.on_pole:
            b.set_crawl(True)              # 匍匐族：整段都趴着（杆上不匍匐）
        self._social_left -= 1
        d = math.hypot(ob.chunk1.x - b.chunk1.x, ob.chunk1.y - b.chunk1.y)
        if kind == "revive":
            # 必须贴进按压半径（量的是最近 chunk 对），否则永远救不活
            d = self._touch_dist(ob)
        if kind == "revive" and d > tuning.SOCIAL_ARRIVE and self._both_hands_on(ob):
            d = tuning.SOCIAL_ARRIVE     # 两只手真按上了就算到位（与 IK 同一套几何）
        if d > tuning.SOCIAL_ARRIVE:
            if kind == "revive":
                self._rescue_step(ob)    # 救援赶路：走 / 跳 / 落 / 爬杆
            else:
                b.walk_to(ob.chunk1.x)
            self.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
            self._clear_hands()
            if d > tuning.SOCIAL_ABANDON_R and not getattr(ob, "dead", False):
                # 活的对象自己跑远了：别一路追着硬演（倒地的同伴躺着不算，照样去救）
                self._end_social()
                return
        else:
            self._rescue_exec = None
            b.stop_walk()
            b.facing = 1 if ob.chunk0.x >= b.chunk0.x else -1
            self.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
            self._social_act(kind, tgt, ob)
        if self._social_left <= 0:
            if kind == "revive":
                self._revive_gave_up = True   # 磨到超时才算真放弃（长冷却）
            self._end_social()

    def _st_social_gift(self, lz):
        """送礼驯服：端着蝉乌贼走到未驯服蜥蜴身边，极低概率交出去。

        对照原版 FriendTracker.GiftRecieved（活体 like += 0.6 / 尸体 1.2）。
        """
        b = self.body
        self._social_left -= 1
        if (getattr(lz, "dead", False) or getattr(lz, "tamed", False)
                or lz.state != ItemState.FREE or not self._carrying_gift()
                or self._social_left <= 0):
            self._end_social()
            return
        self.gfx.look_at = (lz.x, lz.y)
        d = math.hypot(lz.x - b.chunk1.x, lz.y - b.chunk1.y)
        if d > tuning.GIFT_APPROACH_R:
            b.walk_to(lz.x)
            return
        b.stop_walk()
        b.facing = 1 if lz.x >= b.chunk0.x else -1
        self._aim_target(lz)
        self._gift_wait += 1
        if self._gift_wait >= tuning.GIFT_DELIVER_DELAY:
            self.win.deliver_gift(self.win, lz)
            self.body.temper_shift(tuning.TEMPER_FEED)
            self._end_social()

    def _social_act(self, kind, tgt, ob):
        """到位后照动作词表（behavior/social.py）演对应的手势。"""
        if kind == "revive":
            self._social_revive(tgt, ob)
        elif kind == "wake":
            self._social_wake(tgt, ob)
        elif kind == "pet":
            self._social_stroke(tgt, ob, True)      # 抚摸：横线
        elif kind == "pat":
            self._social_stroke(tgt, ob, False)     # 拍拍：竖线
        elif kind == "point":
            # 指向：手举着不放（不上表情），就是「看这个 / 我想要这个」
            self.gfx.face(False, PRIO_URGENT)
            if not self._aim_target(tgt):
                self._end_social()
        elif kind == "watch":
            # 围观：站着看着，不动手（围观本身就是一种身体语言）
            self.gfx.face(False, PRIO_URGENT)
        else:
            # 指指点点：伸-收快速 1~5 下，指完一轮再来一轮
            if self.timer % tuning.SOCIAL_POKE_INTERVAL == 0:
                self._poke(ob)
            if self._point_step():
                self._point_begin(tgt)

    def _social_stroke(self, tgt, ob, horizontal):
        """抚摸（横线）/ 拍拍（竖线）：手贴着对象来回画 2~5 次。"""
        g = self._social_gesture
        if not isinstance(g, social.StrokeGesture):
            g = None
        if g is None or g.done:
            n = self.rng.randint(tuning.PET_REPS_MIN, tuning.PET_REPS_MAX)
            self._social_gesture = g = (
                social.StrokeGesture(n, tuning.PET_ON_TICKS, "h", tuning.PET_SPAN)
                if horizontal else
                social.StrokeGesture(n, tuning.PAT_ON_TICKS, "v", tuning.PAT_SPAN))
        self.gfx.face(True, PRIO_URGENT)     # 抚摸 / 拍拍的表情
        ox, oy = g.offset()
        side = "r" if ob.chunk0.x >= self.body.chunk0.x else "l"
        self.gfx.hand_aim[side] = (ob.chunk0.x + ox, ob.chunk0.y + oy)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if g.step():
            self._soothe(ob)                        # 画完一轮：双方都平复一点

    def _social_wake(self, tgt, ob):
        """摇醒：抓着睡着的同伴左右晃几下，晃完它就醒了。

        对照原版 Player.GrabNPC / 拖拽时对被抓者的 nudzh；桌宠原创的社交动作，
        只有社交欲望攒满、且对方正在睡的时候才会做（爱吵的性格更乐意）。
        """
        beh = getattr(tgt, "behavior", None)
        if beh is None or not self._peer_asleep(tgt):
            self._end_social()
            return
        g = self._social_gesture
        if not isinstance(g, social.StrokeGesture):
            g = None
        if g is None:
            reps = self.rng.randint(tuning.WAKE_SHAKE_REPS_MIN,
                                    tuning.WAKE_SHAKE_REPS_MAX)
            self._social_gesture = g = social.StrokeGesture(
                reps, tuning.WAKE_SHAKE_TICKS, "h", tuning.WAKE_SHAKE_SPAN)
        self.gfx.face(False, PRIO_URGENT)
        ox, oy = g.offset()
        side = "r" if ob.chunk0.x >= self.body.chunk0.x else "l"
        self.gfx.hand_aim[side] = (ob.chunk0.x + ox, ob.chunk0.y + oy)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        self._social_touch += 1
        if self._social_touch % tuning.WAKE_SHAKE_POKE == 0:
            self._poke(ob)                  # 摇的时候顺手把对方扒拉一下
        if g.step():
            beh.wake_up(by=self.win)        # 晃完这一轮：对方被叫醒
            self._end_social()

    def _social_revive(self, tgt, ob):
        """复活：伸手按在同伴身上用力下按 4~8 下（身体跟着压），按完同伴复活。"""
        beh = getattr(tgt, "behavior", None)
        if beh is None:
            self._end_social()
            return
        if not ob.dead:
            # 只是被打晕：按不活，改成拍拍它（晕的自己会醒）
            self._social_kind = "pat"
            self._social_gesture = None     # 手势槽按动作类型复用：换动作必须换手势
            return
        g = self._social_gesture
        if not isinstance(g, social.PressGesture):
            g = None
        if g is None:
            reps = self.rng.randint(tuning.REVIVE_PRESS_MIN, tuning.REVIVE_PRESS_MAX)
            self._social_gesture = g = social.PressGesture(
                reps, tuning.REVIVE_PRESS_TICKS, tuning.REVIVE_RELEASE_TICKS)
            self._social_press_per = max(1, tuning.REVIVE_TOUCH_TICKS // reps)
        self.gfx.face(True, PRIO_URGENT)     # 复活按压的表情
        # 用力按的时候借晕眩脸来演「憋着一股劲儿往下按」（借表情，不是真晕）
        self.gfx.face_override = "stun"
        self._social_press_down = g.pressing
        if not self._both_hands_on(ob):
            return                                  # 两只手都要按上去（够不着就先挪身子）
        if g.pressing:                              # 身体跟着用力向下
            self.body.chunk0.vy += tuning.REVIVE_PRESS_DOWN
            self.body.chunk1.vy += tuning.REVIVE_PRESS_DOWN * 0.6
        if self._social_press_seen < g.presses_done:
            self._social_press_seen = g.presses_done
            self._poke(ob)                          # 把同伴按下去
            beh.nuzzle(self._social_press_per, by=self.win)
            self.body.temper_shift(tuning.TEMPER_FEED * 0.5)
        if g.step():
            revived = beh.nuzzle(tuning.REVIVE_TOUCH_TICKS, by=self.win)   # 按完就复活
            if revived:
                # 暴雨期间允许同伴救援；清掉环境致死留下的“转生”标记，
                # 让下一 tick 走普通 revive，而不是继续被暴雨锁住。
                beh._reincarnate = False
                beh._revive_timer = 1
            self.body.temper_shift(tuning.TEMPER_FEED)
            if tgt is not self.win:
                # 救活了谁：上总线（目击者会各自反应），被救的那只记下这份亲近
                EV.emit_for(self.win, EV.CREATURE_RESCUED, subject=self.win,
                            obj=tgt, intensity=0.9)
                rt = relations_for(tgt)
                rt.note_toward(self.win, "affinity", 0.60,
                               getattr(self.win, "_pole_tick", 0))
                rt.note_toward(self.win, "respect", 0.25,
                               getattr(self.win, "_pole_tick", 0))
            self._end_social()

    def _both_hands_on(self, ob) -> bool:
        """复活要「两只手都放在目标身上」：两手分别按住目标的两截，且都够得着。

        对照原版 Player 抓取（两只手各抓一个 chunk）；按住期间两只手都钉在目标上，
        所以只有真的贴上去、两只手都按到了才会推进按压计数。
        """
        a, b = ob.chunk0, ob.chunk1
        # 下压那一拍：两只手不只贴着，还往目标身体里按进去一点（用力按下去）
        press = tuning.REVIVE_HAND_PRESS if self._social_press_down else 0.0
        self.gfx.hand_aim["l"] = (a.x, a.y + press)
        self.gfx.hand_aim["r"] = (b.x, b.y + press)
        hl, hr = self.gfx.hands[0], self.gfx.hands[1]
        rd = tuning.REVIVE_TOUCH_R

        def on_target(h):
            # 手挨上目标身体的任意一截都算「放在目标身上」（尸体是会滚的），
            # 同时胳膊得真的伸出去——手缩在肩边不算按上。
            if min(math.hypot(h.x - a.x, h.y - a.y),
                   math.hypot(h.x - b.x, h.y - b.y)) > rd:
                return False
            sx, sy = self.gfx._shoulder(-1.0 if h is hl else 1.0, self.gfx.body_axis())
            return math.hypot(h.x - sx, h.y - sy) >= tuning.REVIVE_ARM_MIN

        return on_target(hl) and on_target(hr)

    def _soothe(self, ob):
        """安抚：一次抚摸/拍拍画完，双方都平复一点。"""
        self.body.temper_shift(-tuning.PET_SOOTHE)
        ob.temper_shift(-tuning.PET_SOOTHE)

    def _aim_target(self, tgt) -> bool:
        """【指向】手臂持续瞄着目标（投掷预备/战斗瞄准）；目标无效返回 False。

        对照原版 Player.cs:3728 makeThrowCounter：举手指向不换表情，
        「指指点点」才走 _point_step 的伸-收-伸手势并换上表情。
        """
        if tgt is None:
            return False
        ob = getattr(tgt, "body", None)
        if ob is not None:
            tx, ty = ob.chunk0.x, ob.chunk0.y
        else:
            tx, ty = getattr(tgt, "x", None), getattr(tgt, "y", None)
            if tx is None or ty is None:
                return False
        b = self.body
        side = "r" if tx >= b.chunk0.x else "l"
        self.gfx.hand_aim[side] = (tx, ty)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        return True

    def _point_at_peer(self, peer):
        self.gfx.face(True, PRIO_URGENT)
        return self._aim_target(peer)

    # ══ 统一社交动作 API：词表（behavior/social.py）驱动的 起手 / 推进 / 收势 ══
    # 所有「伸手比划」的地方——社交欲望态、被挡路、杆上被挡、被抢、追鼠标、
    # 睡醒、空手反击、让路、被指、挣扎——都走这里，手势与含义只有词表一份。
    def _act_begin(self, key, tgt, mode="obj", enforce_side=False, reps=None, left=0):
        """起手一个社交动作（词表键 → 手势 + 姿态）；返回 False=没起来。"""
        a = social.action(key)
        if a is None or tgt is None:
            return False
        self._act_key = a.key
        self._act_tgt = tgt
        self._act_owner = self.state
        self._act_mode = "cursor" if mode == "cursor" else "obj"
        self._act_enforce = bool(enforce_side)
        self._act_left = int(left)
        self._act_idle = False
        self._social_gesture = None
        self._social_press_seen = 0
        if a.gesture == "scold":
            self._point_begin(tgt, mode=self._act_mode, enforce_side=enforce_side, reps=reps)
        else:
            self._point_end()
        if a.crouch:
            self.body.set_crawl(True)
        self.gfx.face(a.gesture == "scold", PRIO_URGENT)
        self._social_witness_boost()       # 别人在社交：附近同伴也想社交
        return True

    def _act_active(self) -> bool:
        return self._act_key is not None

    def _aim_act(self, tgt, mode="obj", enforce_side=False, cover=True) -> bool:
        """把一个「指向」瞄到对象/鼠标上；返回 False=目标没了。"""
        if mode == "cursor":
            # 指鼠标：**每 tick 重取当帧光标**。起手那一帧的坐标是个死元组，
            # 鼠标一动手臂/头就再也追不上（用户：指向要持续跟随而不是只瞄一次）。
            cur = self._cursor_live(tgt if isinstance(tgt, tuple) else None)
            if cur is None:
                self._clear_hands()
                return False
            self._point_at_cursor(cur, enforce_side=enforce_side, cover=cover)
            return not self._point_stopped
        return self._aim_target(tgt)

    def _cursor_live(self, fallback=None):
        """指向鼠标时的当前目标＝当帧光标（光标没了才退回 fallback）。"""
        return self.cursor if self.cursor is not None else fallback

    def _act_tick(self) -> bool:
        """推进一 tick 当前社交动作；返回 True=还要接着做。"""
        a = social.action(self._act_key)
        tgt = self._act_tgt
        if a is None or tgt is None:
            return False
        ob = getattr(tgt, "body", None)
        # 社交动作不强制：对象自己跑远了就收手（被救活后的道谢、平时的小动作都算）
        if ob is not None and self._touch_dist(ob) > tuning.SOCIAL_ABANDON_R:
            return False
        g = a.gesture
        if a.crouch:
            self.body.set_crawl(True)          # 匍匐族：整段都趴着
        if g == "scold":
            if self._point_step():             # 一轮指完（想接着做就再来一轮）
                return False
        elif g == "hold":
            self.gfx.face(False, PRIO_URGENT)  # 指向：只是举着手，不上表情
            if not self._aim_act(tgt, self._act_mode, self._act_enforce):
                return False
        elif g in ("stroke_h", "stroke_v"):
            if ob is None:
                return False
            self._social_stroke(tgt, ob, g == "stroke_h")
        elif g == "press":
            if ob is None:
                return False
            self._social_revive(tgt, ob)       # 按完自己收势
            return self._act_active()
        else:                                  # walk：趴着不动
            self.gfx.face(False, PRIO_URGENT)
            self._clear_hands()
        if self._act_left > 0:
            self._act_left -= 1
        return True

    def _act_end(self):
        """收势：清手势、站起来、收表情。"""
        self._act_key = None
        self._act_tgt = None
        self._act_owner = None
        self._act_idle = False
        self._point_end()
        self.body.set_crawl(False)
        self.gfx.face(False, PRIO_URGENT)     # 收势要压得住起势那一档

    # ── 平时随手小动作：不切状态，站着（或趴着）做一小段 ──
    def _act_idle_tick(self):
        """推进平时小动作；做完/超时/目标没了就收势。"""
        b = self.body
        tgt = self._act_tgt
        ob = getattr(tgt, "body", None)
        b.stop_walk()
        if ob is not None:
            b.facing = 1 if ob.chunk0.x >= b.chunk0.x else -1
            self.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
        elif isinstance(tgt, tuple):
            self.gfx.look_at = self._cursor_live(tgt)   # 头也跟着鼠标走
        alive = self._act_tick()
        if not alive or self._act_left <= 0 or (ob is not None and getattr(ob, "dead", False)):
            self._act_end()
            self._idle_hold = tuning.IDLE_SOCIAL_HOLD

    def _idle_social_kind(self, tgt) -> str:
        """平时小动作抽词：跟社交欲望同一套性格权重，去掉要走长流程的两个。"""
        for _ in range(4):
            k = self._pick_social_kind(tgt)
            if k not in ("revive", "crouch_walk"):
                return k
        return "point"

    def _idle_social_start(self, tgt, p, kind=None) -> bool:
        """随手起一个小社交动作（同伴或鼠标）；返回 True=起来了。"""
        if tgt is None or self._act_active() or self._act_cd > 0:
            return False
        if self.rng.random() >= p:
            return False
        mode = "cursor" if isinstance(tgt, tuple) else "obj"
        if kind is None:
            kind = "point" if mode == "cursor" else self._idle_social_kind(tgt)
        left = self.rng.randint(tuning.IDLE_SOCIAL_TICKS_MIN, tuning.IDLE_SOCIAL_TICKS_MAX)
        if not self._act_begin(kind, tgt, mode=mode, left=left):
            return False
        self._act_idle = True
        self._act_cd = tuning.IDLE_SOCIAL_CD
        return True

    def _idle_social_try(self, cursor):
        """平时（非社交欲望态）也有概率对附近同伴/鼠标做个社交动作。"""
        self._act_check = (self._act_check + 1) % max(1, tuning.IDLE_SOCIAL_CHECK)
        if self._act_check:
            return False
        peer = self._nearest_peer(tuning.SOCIAL_R * 0.75)
        if peer is not None:
            p = tuning.IDLE_SOCIAL_P * (0.4 + 1.2 * getattr(self.pers, "sociability", 0.5))
            if self._idle_social_start(peer, clampf(p, 0.0, 1.0)):
                return True
        if (cursor is not None and self._cursor_point_ok()
                and self.rng.random() < tuning.IDLE_SOCIAL_CURSOR_P):
            return self._idle_social_start(cursor, 1.0)
        return False

    def _cursor_social_kind(self) -> str:
        """对着鼠标：通常「指向」，性格不好的猫有概率改成「指指点点」。"""
        if self.rng.random() < self._point_prob(tuning.CURSOR_SCOLD_PROB):
            return "scold"
        return "point"

    # ── 指指点点手势：伸出 → 收回 → 再伸出，重复 1~5 下 ──
    def _point_begin(self, tgt, mode="obj", enforce_side=False, reps=None):
        if reps is None:
            reps = social.social_reps(self.rng, getattr(self.pers, "point_like", 0.5))
        self._point = social.PointGesture(reps, tuning.POINT_ON_TICKS, tuning.POINT_OFF_TICKS)
        self._point_tgt = tgt
        self._point_mode = mode
        self._point_enforce = bool(enforce_side)
        if mode == "cursor":
            self.point_side = 0
        # 被指的同伴：有概率转过身来对着发起者匍匐
        beh = getattr(tgt, "behavior", None) if tgt is not None else None
        if beh is not None and hasattr(beh, "be_pointed_at"):
            beh.be_pointed_at(self.win)

    def _point_active(self) -> bool:
        return self._point is not None

    def _point_end(self):
        self._point = None
        self._point_tgt = None
        self.gfx.face(False, PRIO_URGENT)    # 指指点点收势：表情一并收掉
        self._clear_hands()

    def _point_step(self) -> bool:
        """推进一步指指点点；返回 True=整段结束（手也收回去了）。"""
        pg = self._point
        if pg is None:
            return True
        if pg.done:
            self._point_end()
            return True
        if pg.extended:
            if self._point_mode == "cursor":
                self._point_at_cursor(self._cursor_live(self._point_tgt),
                                      enforce_side=self._point_enforce, cover=True)
                if self._point_stopped:
                    self._point_end()
                    return True
            elif not self._point_at_peer(self._point_tgt):
                self._point_end()
                return True
        else:
            self._clear_hands()          # 收回这一下（表情留着，别一闪一闪）
        pg.step()
        if pg.done:
            self._point_end()
            return True
        return False

    def _poke(self, ob):
        """扒拉：推对方一下（原版挥拳/拍打的轻推）。"""
        dx = ob.chunk0.x - self.body.chunk0.x
        ob.chunk0.vx += 0.6 if dx >= 0 else -0.6
        ob.chunk0.vy -= 0.25
        self.body.temper_shift(tuning.TEMPER_FEED * 0.05)

    def _touch_dist(self, ob) -> float:
        """本猫与该身体最近的两个 chunk 间距（倒地的同伴躺着，得按最近点算）。"""
        mine = (self.body.chunk0, self.body.chunk1)
        theirs = (ob.chunk0, ob.chunk1)
        best = 1e9
        for a in mine:
            for c in theirs:
                d = math.hypot(c.x - a.x, c.y - a.y)
                if d < best:
                    best = d
        return best

    # ── 进食互助：饱了给别的猫取食 ──
    def _help_enter(self):
        self._help_left = tuning.HELPFEED_TICKS
        self.body.set_posture(True)

    def _help_end(self):
        self._clear_hands()
        self.gfx.face(False, PRIO_URGENT)
        self._help_cd = T_HELP_RETRY
        self._help_target = None
        self.body.stop_walk()
        self._transition("IdleStand")

    def _st_helpfeed(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._help_end()
            self._transition("Dragged")
            return
        tgt = self._help_target
        self._help_left -= 1
        if (self._help_left <= 0 or tgt is None or tgt.body.dead
                or tgt.body.food_satisfied()):
            self._help_end()
            return
        fruit = b.carried_fruit
        if fruit is None:
            f = self._nearest_free_food()
            if f is None:
                self._help_end()
                return
            d = math.hypot(f.x - b.chunk0.x, f.y - b.chunk0.y)
            self.gfx.look_at = (f.x, f.y)
            if d > 60.0:
                b.walk_to(f.x)
                return
            b.stop_walk()
            side = b.pick_hand("fruit")
            if side is None:
                return
            b.reach_for(f, side)
            if d <= tuning.GRAB_REACH + b.arm_full_reach:
                b.grab_fruit(f, side)
            return
        ob = tgt.body
        d = math.hypot(ob.chunk1.x - b.chunk1.x, ob.chunk1.y - b.chunk1.y)
        self.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
        if d > tuning.HELPFEED_DROP_R:
            b.walk_to(ob.chunk1.x)
            return
        b.stop_walk()
        b.facing = 1 if ob.chunk0.x >= b.chunk0.x else -1
        self.gfx.face(True, PRIO_URGENT)     # 喂食的表情
        fruit.x, fruit.y = ob.chunk0.x, ob.chunk0.y
        fruit.vx = fruit.vy = 0.0
        b.release_fruit()
        tgt.behavior.accept_gift_food(fruit)
        self._help_end()

    # ── 爆米花（原版外部食物源）：开荚后贴上去啃，每口 +1 饱食 ──
    def _nearest_cob(self, feedable: bool = True):
        """最近的爆米花豆荚；feedable=False 找还没开荚的（拿矛打）。"""
        best, bd = None, tuning.COB_FEED_SEEK_R
        c0 = self.body.chunk0
        for cb in getattr(self.win, "seedcobs", ()):
            if cb.state != ItemState.FREE or cb.dead:
                continue
            if feedable:
                if not cb.can_feed():
                    continue
            elif cb.opened:
                continue
            px, py = cb.feed_point(c0.x, c0.y)
            if feedable and py < c0.y - tuning.COB_REACH_DY:
                continue                                  # 挂太高：跳起来也够不着
            d = math.hypot(px - c0.x, py - c0.y)
            if d < bd:
                best, bd = cb, d
        return best

    def _cob_enter(self):
        self._cob_left = tuning.COB_FEED_TICKS
        self._cob_eat_t = 0
        self._cob_try = 0
        self._cob_throw_cd = 0
        self._cob_off_i = 0           # 掷矛位候选（COB_STAND_STEPS）的下标
        self.body.set_posture(True)
        self.body.stop_walk()

    def _cob_end(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self.body.eat_raise = 0.0
        self.body.stop_walk()
        self._cob_climber_release()
        self._cob = None
        self._cob_eat_t = 0
        self._cob_seek_cd = T_COB_RETRY
        self._transition("IdleStand")

    # ── 够不着的豆荚：爬到**真竖杆**同一高度再横着投矛 ──
    #    原版矛只能水平发射（Weapon.cs:463-502 玩家只有水平分支），而植株本身
    #    不是杆子（不许爬），所以唯一的上升通道是旁边的真竖杆。
    def _start_cob_climb(self, cb) -> bool:
        cx = (cb.p0[0] + cb.p1[0]) * 0.5
        cy = min(cb.p0[1], cb.p1[1])           # 瞄靠上的那个 chunk
        pole = self._throw_climb_pole_at(cx, cy)
        if pole is None:
            return False
        from .pole_climb import PoleClimber
        self._cob_climber_release()
        self._cob_climber = PoleClimber(self.win, pole, self.rng, no_handoff=True)
        self._cob_climb_thrown = False
        return True

    def _cob_climber_release(self):
        if self._cob_climber is not None:
            self._cob_climber.release()
            self._cob_climber = None

    def _cob_climb_tick(self, cb) -> None:
        """爬杆途中：爬到和豆荚同高就横着投一矛；杆爬完（到顶/跳走）就收工。"""
        b = self.body
        cl = self._cob_climber
        px = (cb.p0[0] + cb.p1[0]) * 0.5
        py = (cb.p0[1] + cb.p1[1]) * 0.5
        dir_x = 1 if px >= b.chunk0.x else -1
        b.facing = dir_x
        b.stop_walk()
        self.gfx.look_at = (px, py)
        if not self._cob_climb_thrown and b.carried_spear is not None:
            if self._cob_would_hit(cb, dir_x) and self._launch_weapon(dir_x):
                self._cob_climb_thrown = True
                self._cob_try += 1
                self._cob_throw_cd = COB_THROW_CD
        if cl.update(self._cob_climb_thrown):
            self._cob_climber_release()
            self._cob_end()

    def _cob_chew(self, cb):
        """原版 Player.cs:5168-5208：手搭豆荚啃 15 tick → AddFood(1)，再冷却 45 tick。"""
        b = self.body
        px, py = cb.feed_point(b.chunk0.x, b.chunk0.y)
        side = "r" if px >= b.chunk0.x else "l"
        b.stop_walk()
        b.facing = 1 if px >= b.chunk0.x else -1
        self.gfx.look_at = (px, py)
        self.gfx.hand_aim[side] = (px, py)               # 原版 handOnExternalFoodSource
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        self._cob_eat_t -= 1
        done = float(max(1, tuning.COB_EAT_TICKS))
        phase = min(1.0, (done - self._cob_eat_t) / done)
        b.eat_raise = EAT_HOLD_POSE + (EAT_CHOMP_POSE - EAT_HOLD_POSE) * math.sin(phase * math.pi)
        if self._cob_eat_t > 0:
            return
        b.food_eat(tuning.COB_EAT_FOOD)                  # 原版 AddFood(1)
        b.energy_change(tuning.EN_EAT_RESTORE)
        self._cob_left = tuning.COB_FEED_TICKS           # 吃到东西就续上预算
        b.temper_shift(tuning.TEMPER_FEED)
        self._cob_cd = tuning.COB_EAT_CD                 # 原版 dontEat…Counter = 45
        self.gfx.hand_aim[side] = None
        b.eat_raise = 0.0
        dx, dy = px - self.gfx.head.x, py - self.gfx.head.y
        dd = math.hypot(dx, dy)
        if dd > 1e-6:                                    # 咬一口头前探
            self.gfx.head.vx += dx / dd * BITE_HEAD_NUDGE
            self.gfx.head.vy += dy / dd * BITE_HEAD_NUDGE

    # ── 打未开荚的爆米花：原版只能横着发射，所以要先让自己和豆荚同高 ──
    def _throw_line(self) -> float:
        """水平掷矛经过的高度（原版 firstChunk.pos + dir*10 + (0,4) 的 y）。"""
        return self.body.chunk0.y - THROW_ORIGIN_DY

    def _cob_band(self, cb):
        """豆荚两个 chunk 组成的可命中竖直区间（含命中半径）。"""
        lo, hi = min(cb.p0[1], cb.p1[1]), max(cb.p0[1], cb.p1[1])
        return lo - COB_HIT_TOL, hi + COB_HIT_TOL

    def _cob_would_hit(self, cb, dir_x, stand_x=None) -> bool:
        """预演这一掷：按原版 Weapon.Thrown 弹道飞一遍，用命中判定函数看会不会中豆荚。

        物理逐行对照 world/spear.py 的 Spear.step（飞行时 vel.y += 0.45、重力减半、
        空气阻力 0.999）；命中判定直接复用 items._cob_hit（真正命中时用的同一个函数）。
        只比高度是不行的：豆荚两个 chunk 是斜的，光看高度会把「chunk 已经在掷出点
        身后」也当成能打中，投出去就是空。

        stand_x：假装站在这个 x 上掷（默认＝现在的位置）。挑站位时要用它逐个试：
        命中与否跟掷出点的 x 有关（豆荚斜着挂，同一个高度上也有一段段的空隙）。

        """
        from ..world.items import SPEAR_COB_PAD, _cob_hit
        from ..world.spear import AIR_FRICTION, GRAVITY, RAD as SPEAR_RAD
        b = self.body
        sp = b.carried_spear
        if sp is None:
            return False
        c0 = b.chunk0
        weak, toss = weaponphys.player_throw_mode(
            getattr(self.win, "variant", ""), self._exhausted, True, False)
        if toss:
            vx, vy = weaponphys.toss_velocity(
                c0, dir_x, float(getattr(sp, "mass", 0.07)), 1, 1.0)
        else:
            vx, vy = weaponphys.throw_velocity(c0, dir_x, True,
                                               weaponphys.frc(weak=weak))
        ox = c0.x if stand_x is None else float(stand_x)
        x = ox + float(dir_x) * THROW_ORIGIN_DX
        y = c0.y - THROW_ORIGIN_DY
        tx0, ty0 = x, y                              # 出手点：平飞段按到这里的距离算
        lx = ox - float(dir_x) * THROW_ORIGIN_DX      # 原版 firstFrameTraceFromPos
        ly = c0.y
        grav = GRAVITY * self.win.room_gravity
        probe = _ShotProbe(SPEAR_RAD)
        for _ in range(64):
            if toss:
                vy += grav           # 轻抛没进 Mode.Thrown → Spear.step 里吃满重力
            elif math.hypot(x - tx0, y - ty0) >= weaponphys.SPEAR_FLIGHT_FLAT_PX:
                vy += grav - weaponphys.SPEAR_FLIGHT_LIFT       # 平飞段之后：原版半重力
            # 平飞段内不加重力（上抬抵掉）
            vx *= AIR_FRICTION
            vy *= AIR_FRICTION
            x += vx
            y += vy
            probe.last_x, probe.last_y = lx, ly      # 逐帧和 Spear.step 一模一样
            probe.x, probe.y = x, y
            probe._seg_x, probe._seg_y = x, y
            if _cob_hit(cb, probe, SPEAR_COB_PAD) is not None:
                return True
            if not (0.0 < x < self.win._WL and y < self.win._HL):
                return False                 # 先撞地/飞出窗口：这一掷打不到
            lx, ly = x, y
        return False

    def _cob_high(self, cb) -> bool:
        """豆荚整个在掷矛线上方 → 得跳起来（或在空中）才打得到。"""
        return self._cob_band(cb)[1] < self._throw_line()

    def _cob_side(self, cb) -> int:
        """从哪边打（＝掷矛方向）：猫在豆荚哪一侧就站哪一侧、朝豆荚掷。

        正下方（|dx| ≤ COB_SIDE_EPS）时方向会逐帧翻：挑离墙更近的一侧退开。
        """
        mid = (cb.p0[0] + cb.p1[0]) * 0.5
        dx = self.body.chunk0.x - mid
        if abs(dx) > COB_SIDE_EPS:
            return 1 if dx < 0.0 else -1
        return 1 if mid < self.win._WL * 0.5 else -1

    def _cob_stand_x(self, cb) -> float:
        """站到哪个水平位置：挑离掷矛线更近的那个 chunk，再往猫这侧退 COB_STAND_DX。

        不能站在 chunk 正下方：矛的出手点在身体前 THROW_ORIGIN_DX 处，站正下方
        等于出手点已经越过豆荚（原版 Weapon.cs:416 是 lastPos→pos 的扫掠判定，
        越过就不会相交）——所以必须站在豆荚外侧，朝豆荚掷。
        """
        line = self._throw_line()
        cx = cb.p0[0] if abs(cb.p0[1] - line) <= abs(cb.p1[1] - line) else cb.p1[0]
        off = COB_STAND_STEPS[min(self._cob_off_i, len(COB_STAND_STEPS) - 1)]
        return cx - self._cob_side(cb) * off

    def _cob_ground_reach(self, cb) -> bool:
        """站在地上、起跳，能不能把掷矛线抬进豆荚的判定带。"""
        lo, hi = self._cob_band(cb)
        line = self._throw_line()
        if line < lo:                        # 豆荚整个在掷矛线下方：跳也没用
            return False
        return line - hi <= COB_JUMP_APEX

    def _st_eatcob(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._transition("Dragged")
            return
        cb = self._cob
        if (cb is None or cb.state != ItemState.FREE or cb.dead
                or b.food >= b.food_max):
            self._cob_end()
            return
        if self._cob_eat_t > 0:                          # 正啃着这一口：原地不动
            self._cob_chew(cb)
            return
        if self._cob_climber is not None:            # 正在爬竖杆去够高处的豆荚
            self._cob_climb_tick(cb)
            return
        px, py = cb.feed_point(b.chunk0.x, b.chunk0.y)
        d = math.hypot(px - b.chunk0.x, py - b.chunk0.y)
        self.gfx.look_at = (px, py)
        self._cob_left -= 1
        if cb.can_feed():
            if d > tuning.COB_FEED_R:
                if abs(px - b.chunk0.x) > tuning.COB_FEED_R * 0.5:
                    b.walk_to(px)
                else:
                    b.stop_walk()
                    b.facing = 1 if px >= b.chunk0.x else -1
                    if py < b.chunk0.y and b.on_floor() and self._cob_left % 24 == 0:
                        b.request_jump("stand")          # 豆荚挂得高：跳起来啃
                if self._cob_left <= 0:
                    self._cob_end()
                return
            b.stop_walk()
            b.facing = 1 if px >= b.chunk0.x else -1
            if self._cob_cd > 0:                         # 两口之间歇一下
                return
            self._cob_eat_t = tuning.COB_EAT_TICKS
            cb.push_from(b.chunk0.x, b.chunk0.y)         # 原版 delayedPush
            return
        # 还没开荚：原版要用矛打一下才 Open()（空手打不开）。
        # 觅食时会愿意先去地上捡一根矛再回来打（用户要求：选择投矛命中爆米花）。
        if b.carried_spear is None:
            if self._cob_spear_willing() and self._cob_fetch_spear() and self._cob_left > 0:
                return                       # 正在去捡矛（不肯用矛的猫直接放弃）
            self._cob_end()
            return
        tx = self._cob_stand_x(cb)
        tgt = tx
        if b.walk_min is not None:                   # 和 Body.walk_to 一样先夹进可行走范围
            tgt = min(max(tx, b.walk_min), b.walk_max)
        # 方向＝从豆荚外侧朝豆荚掷（tx 在豆荚外侧，拿它定方向会翻）。
        dir_x = self._cob_side(cb)
        high = self._cob_high(cb)
        # 先站到豆荚外侧的掷矛位再掷。远距离掷是掷硬币：出手点离豆荚越远，
        # 命中高度（掷矛线）对身体的零点几像素越敏感，预演说中、真矛擦边落空。
        # （旧版「站着不动也能掷」的捷径就是这么把豆荚打不开的。）
        near = abs(tgt - b.chunk0.x) <= (COB_STAND_DX if high else COB_STAND_EPS)
        if b.on_floor() and not high and not near:
            b.walk_to(tgt)
            if self._cob_left <= 0:
                self._cob_end()
            return
        b.stop_walk()
        b.facing = dir_x
        if self._cob_left <= 0 or self._cob_try >= COB_TRY_MAX:
            self._cob_end()                  # 预算用完 / 掷了几次都打不开：放弃
            return
        if self._cob_throw_cd > 0:           # 上一矛还在飞：等它落定再说
            return
        if self._cob_would_hit(cb, dir_x):   # 预演能中：投出去
            if self._launch_weapon(dir_x):
                self._cob_try += 1
                self._cob_throw_cd = COB_THROW_CD
                self._cob_off_i = 0      # 掷过一次：下一根矛从最远的掷矛位重新试
            return
        if (b.on_floor() and not high
                and self._cob_off_i + 1 < len(COB_STAND_STEPS)):
            # 这个距离掷不中（圣徒的轻抛抬得快，站远了从豆荚上方擦过）→ 挪近一档
            self._cob_off_i += 1
            return
        if self._cob_high(cb):               # 豆荚比掷矛线高
            if self._cob_try < 2 and self._cob_ground_reach(cb):
                if b.on_floor():             # 起跳能把线抬上去：跳起来掷
                    b.request_jump("stand")
                    self._cob_try += 1
                return                       # 空中就等预演能中
            # 跳也够不着：植株不是杆子（不许爬），但旁边的**真竖杆**可以爬上去 ——
            # 爬到和豆荚同一高度再横着投矛（原版矛只有水平分支）。
            if (b.on_floor() and not b.on_pole and self._pole_throw_cd <= 0
                    and self._cob_try < COB_TRY_MAX and self._start_cob_climb(cb)):
                return
            self._cob_end()                  # 附近没杆可爬：放弃
            return
        self._cob_end()                      # 豆荚在掷矛线下方：站着够不着

    # ── 战斗：反击（投石/投矛）──
    def _fight_enter(self):
        self._fight_left = tuning.FIGHT_TICKS
        self._fight_throw_t = 0
        self._throw_jumped = False
        self.body.set_posture(True)
        self.body.stop_walk()

    def _fight_end(self):
        self._act_end()
        self._fight_climber_release()
        self._fight_climb_thrown = False
        self._fight_cd = T_FIGHT_RETRY
        self._fight_target = None
        self.body.stop_walk()
        self._transition("IdleStand")

    # ── 爬竖杆打高处：站地面时矛只能水平掷（原版 Weapon.Thrown 只有水平分支），
    #    所以要先爬到和猎物同一高度。爬杆动作/物理全交给 PoleClimber（原版
    #    ClimbOnBeam 的驱动、杆顶 BeamTip 的失衡与跳杆都在里面）。──
    def _throw_climb_pole(self, tgt):
        """能爬到目标那一层的竖杆（目标带 .x/.y）。"""
        return self._throw_climb_pole_at(tgt.x, tgt.y)

    def _throw_climb_pole_at(self, tx: float, ty: float):
        """能爬到 (tx,ty) 那一层的竖杆：杆顶不低于目标，且尽量靠近目标的 x。

        矛在原版只有水平分支（Weapon.cs:463-502），所以要爬到自己和目标的
        高度对齐才打得到 —— 爬的是**真竖杆**，不是爆米花植株。
        """
        c0 = self.body.chunk0
        best, best_c = None, None
        for p in getattr(self.win, "poles", ()):
            if getattr(p, "kind", None) != VERTICAL:
                continue
            if p.top_y > ty + tuning.POLE_THROW_CLIMB_DY:
                continue                    # y↓：杆顶比目标还低，爬上去也够不着
            c = abs(p.x - tx) + abs(p.x - c0.x) * 0.5
            if best_c is None or c < best_c:
                best, best_c = p, c
        return best

    def _start_throw_climb(self, tgt) -> bool:
        pole = self._throw_climb_pole(tgt)
        if pole is None:
            return False
        from .pole_climb import PoleClimber
        self._fight_climber_release()
        # no_handoff：交叉杆换杆由 PoleClimb 态负责，这里不需要
        self._fight_climber = PoleClimber(self.win, pole, self.rng, no_handoff=True)
        self._fight_climb_thrown = False
        return True

    def _fight_climber_release(self):
        if self._fight_climber is not None:
            self._fight_climber.release()
            self._fight_climber = None

    def _fight_climb_tick(self, tgt):
        """爬杆途中：到目标高度就出手；杆爬完（到顶/跳走）就收杆回普通战斗。"""
        b = self.body
        cl = self._fight_climber
        self._aim_target(tgt)                # 爬杆途中手也一直指着猎物
        if (not self._fight_climb_thrown
                and (b.carried_spear is not None or b.carried_stone is not None)
                and abs(b.chunk0.y - tgt.y) <= THROW_JUMP_DY):
            dir_x = 1 if tgt.x >= b.chunk0.x else -1
            b.facing = dir_x
            b.stop_walk()
            if self._launch_weapon(dir_x):
                self._fight_climb_thrown = True
                self._fight_throw_t = 0
        # 已经出手过就让攀爬器按「想下杆」走（到顶后跳杆/爬下），不再第二掷
        if cl.update(self._fight_climb_thrown):
            self._fight_climber_release()
            self._pole_throw_cd = tuning.T_POLE_THROW_RETRY

    def _st_fightthreat(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._clear_hands()
            self._transition("Dragged")
            return
        tgt = self._fight_target
        self._fight_left -= 1
        if (tgt is None or tgt.dead or tgt.state != ItemState.FREE
                or self._fight_left <= 0):
            self._fight_end()
            return
        d = math.hypot(tgt.x - b.chunk1.x, tgt.y - b.chunk1.y)
        self.gfx.look_at = (tgt.x, tgt.y)
        # 手真正够得到的距离。旧版过去拿矛用的是 RIP_SPEAR_R(74)/60px
        # 这两个止步阈值，都大于手长(18+24=42) —— 猫走到止步点就停下，
        # 手又够不到，于是站在矛边发呆直到冷却结束（用户反馈的「站在矛边也发呆」）。
        reach = tuning.GRAB_REACH + b.arm_full_reach
        if b.carried_spear is None and b.carried_stone is None:
            rip = None
            if getattr(self.pers, "bravery", 0.5) >= tuning.RIP_SPEAR_BRAVE:
                rip = self._nearest_rip_spear(tgt) or self._nearest_rip_spear()
            if rip is not None:
                rd = math.hypot(rip.x - b.chunk1.x, rip.y - b.chunk1.y)
                if rd > reach * 0.8:      # 走到真的够得到再停（不然停在手够不到的地方）
                    b.walk_to(rip.x)
                    return
                b.stop_walk()
                side = b.pick_hand("spear")
                if side is None:                 # 手里攥着果子之类：腾出手再拔
                    b.drop_one_item()
                    side = b.pick_hand("spear")
                    if side is None:
                        self._fight_end()
                        return
                b.reach_for(rip, side)
                if (math.hypot(rip.x - b.chunk0.x, rip.y - b.chunk0.y)
                        <= tuning.GRAB_REACH + b.arm_full_reach):
                    if b.grab_spear(rip, side):        # 拔出来（grab_spear 清 stuck）
                        self._fight_throw_t = tuning.FIGHT_THROW_CD
                return
            if b.back_spear is not None and (not self._needle_only()
                                             or self._own_needle(b.back_spear)):
                # 原版 CanRetrieveSpearFromBack：手空了但背上还备着矛 → 抽到主手
                # （矛大师：背上那根得是活白针才抽，变黑的针不算武器）
                if b.take_back_spear("r") is not None:
                    self._fight_throw_t = tuning.FIGHT_THROW_CD
                    return
            o = self._nearest_ground_weapon()
            if o is not None:
                od = math.hypot(o.x - b.chunk1.x, o.y - b.chunk1.y)
                if od > reach * 0.8:
                    b.walk_to(o.x)
                    return
                b.stop_walk()
                side = b.pick_hand("spear")
                if side is None:                 # 手里攥着果子之类：腾出手再捡
                    b.drop_one_item()
                    side = b.pick_hand("spear")
                    if side is None:
                        self._fight_end()
                        return
                b.reach_for(o, side)
                if math.hypot(o.x - b.chunk0.x, o.y - b.chunk0.y) <= tuning.GRAB_REACH + b.arm_full_reach:
                    from ..world.spear import Spear
                    if isinstance(o, Spear):
                        b.grab_spear(o, side)
                    else:
                        b.grab_stone(o, side)
                    self._fight_throw_t = tuning.FIGHT_THROW_CD
                return
            # 空手又找不到家伙：原版空手根本打不动蜥蜴，贴上去只是送死 ——
            # 结束迎战，交回面敌逻辑（撤退，或者去更远的地方找矛）。
            self._fight_end()
            return
        # 持械：持续瞄着目标（指向），到点就按原版水平掷出
        # 目标高出一跳够不着的量（例如站在杆上/墙上的蜥蜴）→ 先爬竖杆到同一高度
        if self._fight_climber is not None:
            self._fight_climb_tick(tgt)
            return
        if (b.chunk0.y - tgt.y > tuning.POLE_THROW_CLIMB_DY
                and b.on_floor() and not b.on_pole
                and self._pole_throw_cd <= 0 and self._start_throw_climb(tgt)):
            return
        self._fight_throw_t += 1
        if d < tuning.FIGHT_ARM_KEEP:                # 太近会被咬：边打边拉开
            b.walk_to(b.chunk1.x - (tgt.x - b.chunk1.x))
        else:
            b.stop_walk()
        self._act_end()
        self._aim_target(tgt)
        if self._fight_throw_t >= tuning.FIGHT_THROW_CD:
            # 只有**真的掷出去了**才重新计满冷却。旧版无条件把 _fight_throw_t 清零，
            # 而目标偏高时 _throw_weapon_at 只是 request_jump 就返回 False：跳跃
            # 时长短于 FIGHT_THROW_CD 时下一轮又从头计时、再跳一次，形成「面对敌人
            # 一直跳却从不投矛」的相位死锁。现在分三种结果（出手 / 起跳 / 条件不满足）
            # 处理：没出手只等一个短重试窗口，跳起来以后下一轮就在空中把矛掷出去。
            self._throw_jumped = False
            if self._throw_weapon_at(tgt):
                self._fight_throw_t = 0
            else:
                self._fight_throw_t = tuning.FIGHT_THROW_CD - tuning.FIGHT_RETRY_CD

    def _throw_line_blocked(self, dir_x, tgt=None) -> bool:
        """自己→目标之间站着别的蛞蝓猫 → 这一掷取消。

        投掷一律水平（Weapon.cs:463-502 玩家只有水平分支），所以沿掷出方向扫一条
        与胸口同高的线段：任何同伴躯干落在线段 THROW_BLOCK_R 内就算被挡住。
        给了 tgt 就只用「自己到目标」那一段，免得把目标身后的同伴也算进去。
        """
        c0 = self.body.chunk0
        ax, ay = c0.x, c0.y
        if tgt is not None:
            bx, by = tgt.x, tgt.y
            if (bx - ax) * dir_x <= 0.0:
                return False                 # 目标在背后：交给调用方处理
        else:
            bx, by = ax + dir_x * THROW_BLOCK_LEN, ay
        for o in getattr(self.win, "pets", ()):
            if o is self.win:
                continue
            ob = getattr(o, "body", None)
            if ob is None or ob.dead:
                continue
            for c in (ob.chunk0, ob.chunk1):
                if _closest_on_segment(c.x, c.y, ax, ay, bx, by)[2] < THROW_BLOCK_R:
                    return True
        return False

    def _launch_weapon(self, dir_x, tgt=None) -> bool:
        """按原版水平掷出手里的矛/石头（不做高度判断，由调用方负责对准）。"""
        b = self.body
        if not b.item_ready():
            return False                 # 上手冷却没走完：先攥着不扔
        if self._needle_only() and not self._own_needle(b.carried_spear):
            return False                 # 矛大师：白针以外的家伙一律不出手（用户口径）
        if self._throw_line_blocked(dir_x, tgt):
            return False                     # 同伴挡在掷出线上：不出手
        spear = b.carried_spear
        if (spear is not None and b.carried_stone is not None
                and b.held_kind("r") == "stone"):
            spear = None                  # 双手都拿着家伙：优先用主手（右手）那件
        weak, toss = weaponphys.player_throw_mode(
            getattr(self.win, "variant", ""), self._exhausted,
            spear is not None, False)
        if spear is not None:
            b.throw_spear(dir_x, weaponphys.frc(weak=weak),
                          recoil=0.4, toss=toss)
        elif b.carried_stone is not None:
            b.throw_stone(dir_x, weaponphys.frc(weak=weak),
                          fling=True, recoil=0.4)
        else:
            return False
        b.chunk0.vx -= dir_x * 0.35
        self.gfx.blink = 15
        return True

    def _throw_weapon_at(self, tgt) -> bool:
        """原版水平投掷：throwDir = IntVector2(sign(x), 0)，初速走 Weapon.Thrown（40*frc）。

        对照反编译 Weapon.cs:463-502：玩家只有水平分支；Spear.Update 里
        setRotation = throwDir、rotationSpeed = 0 ⇒ 矛头始终顺着飞行方向，不翻滚。
        目标偏高时先起跳对齐高度（跳着发射，原版也是这么打空中猎物的）。
        """
        b = self.body
        c0 = b.chunk0
        if tgt is None:
            return False
        if b.carried_spear is None and b.carried_stone is None:
            return False
        dx = tgt.x - c0.x
        dy = tgt.y - c0.y                       # y↓：<0 目标在上方
        if abs(dy) > THROW_JUMP_DY and b.on_floor():
            b.request_jump("stand")             # 站在地上：跳到那一层再水平掷出
            self._throw_jumped = True           # 告诉调用方「这是起跳，不是出手」
            return False                        # 已经在空中就直接掷（原版空中投矛）
        return self._launch_weapon(1 if dx >= 0.0 else -1, tgt)

    # ── 恐惧：匍匐潜行挪开 ──
    def _behind_creature(self, c) -> bool:
        """我是否在对方背后（对方的头朝着另一侧 → 看不见我）。"""
        facing = getattr(c, "facing", 0) or 0
        if not facing:
            return True                  # 没有朝向信息：当背后处理（悄悄匍匐）
        return (self.body.chunk1.x - c.x) * facing < 0.0

    def be_pointed_at(self, pointer):
        """被指指点点：性格不好就回头指回去（scold）；不再有匍匐反应。"""
        b = self.body
        if (getattr(b, "dead", False) or self.grab.active or self._zerog()
                or b.swimming or not b.on_floor()
                or self._act_active() or self.state not in _WANTS_FROM):
            return
        pb = getattr(pointer, "body", None)
        if pb is None:
            return
        if (self.rng.random() < self._point_prob(tuning.POINTED_SCOLD_PROB)
                and self._idle_social_start(pointer, 1.0, kind="scold")):
            return

    def _crawl_enter(self):
        b = self.body
        if self._crawl_left <= 0:
            self._crawl_left = tuning.CRAWL_AWAY_TICKS
        if b.on_pole:                    # 杆上没有匍匐：站着走完这一段
            b.set_crawl(False)
            b.set_posture(True)
            return
        b.set_posture(False)
        b.set_crawl(True)

    def _st_crawlaway(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            b.set_crawl(False)
            self._transition("Dragged")
            return
        lz = self._nearest_lizard(tuning.CRAWL_FEAR_R * 1.6)
        self._crawl_left -= 1
        if lz is None or self._crawl_left <= 0:
            b.set_crawl(False)
            self._crawl_cd = T_CRAWL_RETRY
            self._transition("IdleStand")
            return
        d = math.hypot(lz.x - b.chunk1.x, lz.y - b.chunk1.y)
        if d < tuning.CRAWL_FEAR_R * 0.5 and not self._behind_creature(lz):
            b.set_crawl(False)                  # 打了照面：别匍匐了，拔腿就跑
            self._flee_from = lz
            self._crawl_cd = T_CRAWL_RETRY
            self._transition("FleeLizard")
            return
        # 用 walk_to 驱动而不是裸 move_dir：夹进可行走范围后到墙就自然「到站」，
        # 不再出现「顶着屏幕两侧的墙一直跑」（旧版 move_dir 一旦设上就没人清，
        # 离场后还会带着它一路撞墙）。
        away = 1.0 if lz.x < b.chunk1.x else -1.0
        goal = b.chunk1.x + away * CRAWL_AWAY_STEP
        if b.walk_min is not None:
            goal = min(max(goal, b.walk_min), b.walk_max)
        if (goal - b.chunk1.x) * away <= CRAWL_CORNER_EPS:
            # 已经贴到那一侧的边：夹完的落点还在原地/反方向。再 walk_to 就会被
            # 夹到身体另一侧，朝一边、身体往另一边挪（用户报的「面向正面却后退」）。
            # 贴边就别推了，就地蹲下、转过去面朝威胁。
            b.stop_walk()
            b.facing = 1 if away < 0 else -1
        else:
            b.walk_to(goal)
            b.facing = 1 if away > 0 else -1
        self.gfx.look_at = (lz.x, lz.y)


    def _tongue_holding_creature(self):
        """舌头正黏着的**生物**（果子/珍珠/地形不算）；没黏着返回 None。

        圣徒拿舌头黏活物时得一直使劲拽（体力见 _tick），期间不许匍匐/入睡 ——
        它正拉着东西，不是趴着休息。
        """
        tg = getattr(self.win, "tongue", None)
        if tg is None or not tg.attached:
            return None
        o = getattr(tg, "attached_obj", None)
        if o is None:
            return None
        for seq in (self.win.batflies, self.win.squidcadas, self.win.needleworms,
                    self.win.lizards, self.win.scavengers):
            for c in seq:
                if c is o:
                    return o
        return None

    # ── 觅食欲望：吃完一口归 0，再慢慢涨回 1（够冬眠了也涨，只是更慢）──
    def _food_urge_tick(self):
        rate = (tuning.FOOD_URGE_RATE_FULL if self.body.hunger_need <= 0.0
                else tuning.FOOD_URGE_RATE)
        self._food_urge = min(1.0, self._food_urge + rate)

    # ── 社交欲望（第六类）：攒满才想找同伴做社交动作 ──
    def _social_urge_tick(self):
        self._social_urge = min(1.0, self._social_urge + tuning.SOCIAL_URGE_RATE)

    def _social_urge_boost(self, amount: float) -> None:
        """社交欲望的事件加成：吃到东西 / 吃饱 / 睡醒 / 看到别人社交。"""
        self._social_urge = clampf(self._social_urge + float(amount), 0.0, 1.0)

    def _social_witness_boost(self) -> None:
        """别人做社交动作 → 附近同伴的社交欲望大幅上涨。"""
        c0 = self.body.chunk0
        for p in self._living_peers():
            ob = p.body
            if math.hypot(ob.chunk0.x - c0.x, ob.chunk0.y - c0.y) <= tuning.SOCIAL_BOOST_R:
                p.behavior._social_urge_boost(tuning.SOCIAL_URGE_BOOST_NEAR)

    def wake_up(self, by=None) -> bool:
        """被同伴摇醒 / 被爆炸吓醒：打断睡眠，从 WakeSequence 起身。返回 True=确实叫醒了。"""
        if self.grab.active or self.state not in ("Sleep", "LieDown"):
            return False
        self._hibernating = False
        self.gfx.sleeping = False
        self.body.sleeping = False
        self._sleep_urge = 0.0
        self._wake_then = None
        self._wake_stable = 0
        self._social_urge_boost(tuning.SOCIAL_URGE_BOOST_WAKE)   # 被叫醒也是社交事件
        self._transition("WakeSequence")
        return True

    def startle(self, origin=None) -> None:
        """被吓一跳（工匠爆炸）：睡着的直接被炸醒，醒着的按性格回头指指点点。"""
        if self.wake_up():
            return                      # 刚被炸醒：先起身，账以后再算
        p = clampf(tuning.STARTLE_POINT_BASE
                   * (0.4 + 1.2 * float(getattr(self.pers, "point_like", 0.5)))
                   * (0.5 + 1.0 * float(getattr(self.pers, "temper", 0.5))), 0.0, 1.0)
        if self.rng.random() >= p:
            return
        tgt = self._startle_target(origin)
        if tgt is None:
            return
        self._protest_target = tgt
        self._start_protest(tgt)        # 词表：指指点点

    def _startle_target(self, origin=None):
        """吓人那一方（爆炸的工匠）：离爆心最近的那只同伴。"""
        best, bd = None, 1e9
        ox, oy = (origin if origin is not None else (self.body.chunk1.x,
                                                     self.body.chunk1.y))
        for p in self._living_peers():
            ob = p.body
            d = math.hypot(ob.chunk1.x - ox, ob.chunk1.y - oy)
            if d < bd:
                best, bd = p, d
        return best

    def apologize(self, victim) -> None:
        """误伤同伴：记下它，回头面对它匍匐道歉（抱歉）。"""
        if victim is None or getattr(victim, "body", None) is None:
            return
        if not getattr(self.pers, "apologize", True):
            return                      # 工匠：暴躁执拗，不认错
        if victim.body.dead or victim is self:
            return
        if self._apology_target is victim:
            return
        self._apology_target = victim
        self._apology_t = tuning.APOLOGY_TICKS

    def _food_seek_ready(self) -> bool:
        """觅食闸：**饥饿需求**与**觅食欲望**分开判。

        - 离够冬眠还差 FOOD_DEFICIT_URGENT 格以上：饿了就找，不等欲望攒满
          （旧版刚吃一口就把欲望清零，于是「明明没吃饱却一分钟不找食」）；
        - 只差一点：按欲望闸（吃完归零、慢慢攒回）+ 概率再掷；
        - 已经够冬眠：不再主动找（口径与 food_satisfied() 一致）。
        """
        need = self.body.hunger_need
        if need <= 0.0:
            # 已达到冬眠线：只有还没真正满饱时，才允许进入“补满”觅食。
            # 下一次起意由 _food_seek_wait 控制，避免吃到 4 格后立刻又去找。
            return ((self.body.food * 4 + self.body.food_quarter)
                    < self.body.food_max * 4)
        if need >= tuning.FOOD_DEFICIT_URGENT:
            return True
        return self._food_urge >= 1.0 and self.rng.random() < tuning.FOOD_SEEK_P

    # ── 叼着活的蝉乌贼：扑翅带起一点，下落被拖住 ──
    def _squid_lift_tick(self):
        f = self.body.carried_fruit
        if f is None or not getattr(f, "is_tame_food", False) or getattr(f, "dead", True):
            return
        # Cicada.cs:107 LiftPlayerPower：体力越低托举越弱，耗尽就托不动了
        power = clampf(getattr(f, "lift_power", 0.4) / 0.4, 0.0, 1.0)
        if power <= 0.0:
            return
        c0 = self.body.chunk0
        if c0.vy > -tuning.SQUID_LIFT_MAX:
            c0.vy -= tuning.SQUID_LIFT * power
        c0.vx *= tuning.SQUID_DRAG

    # ── 徒手抓飞虫（蝙蝠/蝉乌贼）──
    def _nearest_catchable(self):
        """半径内可徒手抓的飞虫（蝙蝠/蝉乌贼/面条蝇，含飞行中）。"""
        rage = self._spear_rage()
        if not _diet.hunts_meat(self.pers.diet) and not rage:
            return None
        c0 = self.body.chunk0
        b = self.body
        # 饿到一半以下：幼年面条蝇直接进入猎物名单（认距也放大），不管够不够得着先扑过去
        hungry = b.food < b.food_max * tuning.CATCH_HUNGRY_FRAC
        best, bd = None, None
        for f in (*self.win.batflies, *self.win.squidcadas,
                  *self.win.needleworms):
            if not getattr(f, "catchable", False):
                continue
            d = math.hypot(f.x - c0.x, f.y - c0.y)
            if rage and d <= tuning.SPEAR_RAGE_R:
                ok = True
            elif hungry and self._is_infant(f):
                ok = d <= tuning.CATCH_HUNGRY_R
            else:
                ok = in_reach(self.win, f)      # 一跳够得到就追过去（像抓果子）
            if ok and (best is None or d < bd):
                best, bd = f, d
        return best

    def _is_infant(self, f) -> bool:
        """幼年面条蝇（饿到一半以下时主动攻击/抓取的对象）。"""
        from ..world.needleworm import AGE_SMALL
        return getattr(f, "age", None) == AGE_SMALL

    def _st_catchfly(self, cursor, disturbed):
        if self.grab.active:
            self._flycatch_release()
            self._transition("Dragged")
            return
        if self.flycatch is None:
            self._transition("IdleStand")
            return
        want = self.body.food < self.body.food_max
        status = self.flycatch.update(want)
        if status in ("eaten", "released", "delivered", "revert", "idle"):
            self._flycatch_release()
            self._transition("IdleStand")

    def _flycatch_release(self):
        """收尾：控制器清空，手里还捏着就松手放生。"""
        self.flycatch = None
        f = self.body.carried_fruit
        if f is not None:
            self.body.release_fruit()
            f.stalk = None
            f.state = "free"
            f.held_by_hand = None
        self.body.eat_raise = 0.0
        self.body.stop_walk()
        self.body.arm_aim["l"] = None
        self.body.arm_aim["r"] = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self._catch_cd = tuning.CATCH_RETRY

    def _needle_slot(self):
        """这根尾针长好后落在哪：``"r"`` / ``"l"``（那只手空着）/ ``"back"``
        （两只手都攥着自己的活针 → 先挪一支到背上腾出手）/ ``None``＝真没位置。

        原版 Player.cs:9993 的长针条件就是「至少一只手空着」
        （``grasps[0] == null || grasps[1] == null``），成针时 10053 交给
        ``FreeHand()`` 那只手；背上那格（``spearOnBack.spear``）另算 —— 所以
        「两手各一支 + 背上一支」才是这只猫的上限。

        矛大师永远优先自己的活针（``Spear.spearmasterNeedle``）：那只手上占着的
        如果「不是自己连线的活针」就顶掉让位。旧实现是「两只手都攥着矛就不再长」，
        于是手里一根、背上又一根时每根新针都无处安放、直接掉在地上。
         （背槽是猎手专属：矛大师的容量就是两只手。）
        """
        b = self.body
        free = b.free_hand()
        if free is not None:
            return free                  # 有手空着：直接进那只手（原版 FreeHand()）
        # Spearmaster 只允许双手各持一支；背槽是 Hunter 专属，不参与尾针容量。
        if self._own_needle_count() >= tuning.SPEARMASTER_NEEDLE_HOLD:
            return None                  # 两手已经是自己的活针：没有背槽可借，不再长
        # 手占着但不是「自己连线的活针」（别人的矛 / 断线的死针）→ 顶掉它，让新针入手
        for side in ("r", "l"):
            if not self._own_needle(b.hand_spears.get(side)):
                return side
        return None

    def _tail_needle_tick(self):
        """矛大师：尾巴自己长针（原版 SpearMaster 的独占能力）。

        反编译出处 Player.cs:9995-10036 / PlayerGraphics.cs:947-1113：针先在尾巴里
        长出来（spearProg 0→1，尾上斑点与针精灵一起变大），到 1 才真正成矛入手；
        手里/背上已有矛、正抓着东西、睡着、游泳、无重力时不长。长针有间隔。
        """
        if not self.win.cat.tuning.get("tail_needle"):
            return
        b = self.body
        if self.gfx.tail_needle_prog > 0.0:      # 正在长：先推进动画
            self._tail_needle_grow()
            return
        if self._own_needle_count() >= tuning.SPEARMASTER_NEEDLE_HOLD:
            return                       # 两手 + 背上都是白针了：先不长下一根
        if self._needle_slot() is None:
            return                       # 手上没地方接新针：先不长
        if self._tail_needle_cd > 0:
            self._tail_needle_cd -= 1
            return
        if self.grab.active or self._hibernating or b.swimming or self._zerog():
            return
        if self.state not in ("IdleStand", "PostThrowStand", "PostThrowWander"):
            return
        # 原版 newSpearSlot()：这一针从尾上哪一格冒出来（行/列/针型）
        g = self.gfx
        g.tail_needle_row = self.rng.randint(0, g.TAIL_SPECK_ROWS - 1)
        g.tail_needle_line = self.rng.randint(0, g.TAIL_SPECK_LINES - 1)
        g.tail_needle_type = self.rng.randint(0, 2)
        g.tail_needle_prog = 0.011
        self._tail_needle_grow()

    def _tail_needle_burst(self):
        """拔出尾针那一瞬：尾中点溅 4 颗水珠 + 5 点白火花（Player.cs:10025-10035）。

        原版：`pos = tail[tail.Length / 2].pos`，先 4 个 `WaterDrip`（朝髋方向、
        速度 2~6、带随机横漂），再 5 个 `Spark`（位置随机散开 40px 内、速度 4~30、
        寿命 18）。水珠这里用同一条白色加法粒子代替，靠低速短寿命区分。
        """
        if not self.win.cat.tuning.get("tail_needle"):
            return
        segs = getattr(getattr(self.win, "tail", None), "segs", None)
        if not segs:
            return
        mid = segs[len(segs) // 2]
        px, py = mid.x, mid.y
        b = self.body
        dx, dy = b.chunk1.x - px, b.chunk1.y - py
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        rng = self._needle_rng
        for _ in range(4):                      # WaterDrip
            k = 3.0 * rng.random()
            ax = (rng.random() * 2.0 - 1.0) * k + ux * (2.0 + 4.0 * rng.random())
            ay = (rng.random() * 2.0 - 1.0) * k + uy * (2.0 + 4.0 * rng.random())
            self.win.add_spark(px + (rng.random() * 2.0 - 1.0) * 1.5,
                               py + (rng.random() * 2.0 - 1.0) * 1.5,
                               ax, ay, True, 26)
        for _ in range(5):                      # Spark
            a = rng.random() * 2.0 - 1.0
            c = rng.random() * 2.0 - 1.0
            n = math.hypot(a, c) or 1.0
            sp = 4.0 + 26.0 * rng.random()
            self.win.add_spark(px + a * rng.random() * 40.0,
                               py + c * rng.random() * 40.0,
                               a / n * sp, c / n * sp, True, 18)

    def _tail_needle_grow(self):
        """尾针生长的每 tick 推进（Player.cs:10000-10036）：到 1 才把矛交到手上。"""
        b, g = self.body, self.gfx
        if (self.grab.active or self._hibernating or b.swimming or self._zerog()
                or self._own_needle_count() >= tuning.SPEARMASTER_NEEDLE_HOLD):
            # 原版 Player.cs:4191：中途被打断按 0.05 缩回，< 0.025 归零
            g.tail_needle_prog *= 0.95
            if g.tail_needle_prog < 0.025:
                g.tail_needle_prog = 0.0
            return
        prog = g.tail_needle_prog
        if prog < 0.1:
            g.tail_needle_prog = prog + (0.11 - prog) * 0.1
        else:
            g.tail_needle_prog = prog + (1.0 - prog) * 0.05
            if g.tail_needle_prog > 0.6:         # 越接近拔出来，头抖得越厉害
                k = (g.tail_needle_prog - 0.6) / 0.4 * 2.0
                g.head.vx += (self.rng.random() * 2.0 - 1.0) * k
                g.head.vy += (self.rng.random() * 2.0 - 1.0) * k
        if g.tail_needle_prog > 0.95:
            g.tail_needle_prog = 1.0
        if g.tail_needle_prog < 1.0:
            return
        g.tail_needle_prog = 0.0
        slot = self._needle_slot()
        if slot is None:
            # 长到一半手被占死（正好抓到东西）：按原版缩回，别把针丢在地上
            self._tail_needle_cd = tuning.TAIL_NEEDLE_CD
            return
        if slot == "back":
            # 背槽已经不参与尾针容量（猎手专属）：没有手就等下一轮。
            self._tail_needle_cd = tuning.TAIL_NEEDLE_CD
            return
        self._tail_needle_burst()          # 拔出那一瞬的溅射（Player.cs:10025-10035）
        tx, ty = b.chunk1.x, b.chunk1.y
        segs = getattr(getattr(self.win, "tail", None), "segs", None)
        if segs:
            tx, ty = segs[-1].x, segs[-1].y
        from ..world.spear import Spear
        win = self.win.window
        sp = Spear(tx, ty, seed=win._spear_seed, angle_deg=180.0)
        sp.needle = True                 # 尾巴长的针（Spear.spearmasterNeedle）
        sp.needle_live = True            # 还连着尾巴：扎中活物能吸食
        sp.needle_type = int(self.gfx.tail_needle_type) % 3   # BioSpear1..3
        win._spear_seed += 1
        win.spears.append(sp)
        win.world_version += 1
        if b.held_kind(slot) is not None and not self._own_needle(b.held_kind(slot)):
            b._release_item_at(slot, to_free=True)   # 那只手不是自己的活针：放下腾出手
        if not b.grab_spear(sp, side=slot):
            win.spears.remove(sp)             # 真接不住就别丢一地
            win.world_version += 1
            self._tail_needle_cd = tuning.TAIL_NEEDLE_CD
            return
        self._tail_needle_cd = tuning.TAIL_NEEDLE_CD
        self.gfx.blink = 12

    def _back_spear_tick(self):
        """原版 Player.spearOnBack：能背矛的猫闲下来会把脚边多余的矛背到背上。"""
        b = self.body
        if not self.win.cat.tuning.get("back_spear"):   # 只有猎手系会背矛
            return
        if b.back_spear is not None or b.carried_spear is not None:
            return
        if self._back_spear_cd > 0:
            self._back_spear_cd -= 1
            return
        eager = float(getattr(self.pers, "spear_like", 1.0)) > 1.0   # 猎手：急着补矛
        if self.grab.active or self._hibernating or b.swimming or self._zerog():
            return
        if not eager and self.state != "IdleStand":
            return
        c0 = b.chunk0
        best, bd = None, (30.0 * float(getattr(self.pers, "spear_like", 1.0)))
        for sp in self.win.spears:
            if sp.state != "free" or not _spear_takeable(sp):
                continue
            if not self._spear_usable(sp):        # 钉成杆的矛：只有工匠拔得动
                continue
            if not (sp.stuck or (abs(sp.vx) < 0.4 and abs(sp.vy) < 0.4)):
                continue
            d = math.hypot(sp.x - c0.x, sp.y - c0.y)
            if d < bd:
                best, bd = sp, d
        if best is None:
            self._back_spear_cd = 60 if eager else 120
            return
        b.put_spear_on_back(best)
        self.gfx.blink = 12

    # ── 平时把玩地上的小物件（矛/石头）──
    def _nearest_play_item(self):
        """寻找「可以拿来玩」的小物件：矛、石头、水果、珍珠。

        食物在玩耍阶段不会被吃掉；它只是一件会被端详、拨弄、带跳的东西。
        目标评分仍走 interest board，避免所有猫同时抢同一个玩具。
        """
        b = self.body
        if (b.carried_spear is not None or b.carried_stone is not None
                or b.carried_fruit is not None):
            return None
        from ..world.spear import Spear
        from ..world.pearl import Pearl
        c0 = b.chunk0
        cands = []
        for o in self.win.stones:
            if o.state != "free" or getattr(o, "unfetchable", False):
                continue
            if not o.at_rest_on_ground(self.HL):
                continue
            cands.append((o, math.hypot(o.x - c0.x, o.y - c0.y), "stone"))
        for sp in self.win.spears:
            if sp.state != "free" or sp.stuck_to is not None:
                continue
            if getattr(sp, "pinned", False):
                continue
            if not (sp.stuck or (abs(sp.vx) < 0.4 and abs(sp.vy) < 0.4)):
                continue
            cands.append((sp, math.hypot(sp.x - c0.x, sp.y - c0.y)
                          * self._needle_pref(sp), "spear"))
        for f in self.win.fruits:
            if f.state not in ("free", "hanging") or getattr(f, "is_edible", True) is False:
                # 非食物水果/特殊果实也可以玩；这里只跳过已经被别猫拿走的
                if f.state not in ("free", "hanging"):
                    continue
            cands.append((f, math.hypot(f.x - c0.x, f.y - c0.y), "fruit"))
        for pr in self.win.pearls:
            if pr.state != "free":
                continue
            cands.append((pr, math.hypot(pr.x - c0.x, pr.y - c0.y), "pearl"))
        cands = [c for c in cands if c[1] < tuning.ITEMPLY_SEEK_R]
        if not cands:
            return None
        temper = getattr(self.pers, "temper", 0.5)
        pref = getattr(self.pers, "toy_pref", {})

        def score(c):
            o, d, kind = c
            if kind == "spear":
                w = pref.get("spear_play", 1.0) * (
                    1.0 + (temper - 0.5) * 0.8)
                w *= clampf(float(getattr(self.pers, "spear_like", 1.0)), 0.0, 2.0)
            elif kind == "stone":
                w = pref.get("stone_play", 1.0) * (
                    1.0 - (temper - 0.5) * 0.8)
            elif kind == "pearl":
                w = 1.10
            else:
                w = 0.95
            return _interest_key(self.win, o, d / max(0.05, w),
                                 tuning.INTEREST_JITTER, tuning.INTEREST_TAKEN_MUL,
                                 kind="play")
        return min(cands, key=score)[0]

    def _itemplay_enter(self):
        b = self.body
        b.set_posture(True)
        b.stop_walk()
        self._itemplay_phase = 0
        self._itemplay_left = 0
        self._itemplay_mode_t = 0
        it = self._itemplay_target
        from ..world.spear import Spear
        from ..world.pearl import Pearl
        if isinstance(it, Spear):
            kind = "spear"
        elif isinstance(it, (Pearl,)):
            kind = "fruit"
        else:
            kind = "fruit" if it in getattr(self.win, "fruits", ()) else "stone"
        self._itemplay_side = b.pick_hand(kind) or "r"
        self._play_face = 1 if self.rng.random() < 0.5 else -1
        # 不是每只猫都用同一个「坐着拿着」模板；活跃度、脾气决定跳/拨弄/端详的比重。
        act = clampf(float(getattr(self.pers, "activity", 0.5)), 0.0, 1.0)
        temp = clampf(float(getattr(self.pers, "temper", 0.5)), 0.0, 1.0)
        r = self.rng.random()
        if r < 0.30 + 0.20 * act:
            self._itemplay_mode = "paw"
        elif r < 0.52 + 0.28 * act + 0.08 * temp:
            self._itemplay_mode = "hop"
        else:
            self._itemplay_mode = "inspect"

    def _own_needle(self, sp) -> bool:
        """这根矛是不是「这只猫自己尾巴长出来的针」（Spear.spearmasterNeedle）。

        原版判定：`Spear.spearmasterNeedle` + 掷出者是 Spearmaster。桌宠里
        needle 标记就是尾巴长的针（`_tail_needle_grow` 写 sp.needle = True），
        种族看 `tail_needle` 能力位。
        """
        return (bool(getattr(sp, "needle", False))
                and bool(getattr(sp, "needle_live", False))
                and bool(self.win.cat.tuning.get("tail_needle")))

    def _own_needle_count(self) -> int:
        """两只手里还连着的白针有几根（上限＝两只手各一支；背槽是猎手专属）。"""
        b = self.body
        return sum(1 for sp in b.hand_spears.values()
                   if self._own_needle(sp))

    def _itemplay_fling(self):
        """玩够了顺手甩出去（暴躁的猫）：走原版水平投掷，石头能砸晕同伴。"""
        b = self.body
        if not b.item_ready():
            return                       # 上手冷却没走完：先接着玩
        dir_x = 1 if b.facing >= 0 else -1
        if b.carried_spear is not None and not self._own_needle(b.carried_spear):
            # 矛大师自己尾巴长的针不当玩具扔（原版针是它唯一的取食工具）
            b.throw_spear(dir_x, weaponphys.frc(weak=self._exhausted), recoil=0.3)
        elif b.carried_stone is not None:
            b.throw_stone(dir_x, weaponphys.frc(weak=self._exhausted),
                          fling=True, recoil=0.3)
        self.gfx.blink = 15

    def _itemplay_end(self):
        b = self.body
        if b.carried_stone is not None:
            b.release_stone(to_free=True)
        if b.carried_spear is not None and not self._own_needle(b.carried_spear):
            # 收尾只放下「玩的东西」：自己尾巴长的针继续拿着，别因为玩耍掉了
            b.release_spear(to_free=True)
        b.eat_raise = 0.0
        b.set_crawl(False)
        b.set_posture(True)
        b.stop_walk()
        b.arm_aim["l"] = None
        b.arm_aim["r"] = None
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self._itemplay_target = None
        self._itemplay_left = 0
        self._itemplay_phase = 0
        self._itemplay_mode = "inspect"
        ex = self._itemplay_chase_exec
        self._itemplay_chase_exec = None
        if ex is not None:
            ex.cancel()
        self._itemplay_mode_t = 0
        self._itemplay_throw_count = 0
        self._itemplay_cd = tuning.ITEMPLY_RETRY

    def _lick_targets(self):
        """能被舌头黏着玩的生物（活的、自由态的）。"""
        w = self.win
        out = []
        for seq in (w.batflies, w.squidcadas, w.needleworms, w.lizards, w.scavengers):
            for e in seq:
                if getattr(e, "dead", False):
                    continue
                if getattr(e, "state", None) != ItemState.FREE:
                    continue
                out.append(e)
        return out

    def _lick_creature(self):
        """射程内最近的生物（舌头够得着才玩）。"""
        tg = self.win.tongue
        if tg is None or not tg.is_idle():
            return None
        c0 = self.body.chunk0
        best, bd = None, tg.total * LICK_REACH_FRAC
        for e in self._lick_targets():
            d = math.hypot(e.x - c0.x, e.y - c0.y)
            if d < bd:
                best, bd = e, d
        return best

    def _st_itemplay(self, cursor, disturbed):
        """拿起地上的矛/石头把玩一会儿，再放下走人。"""
        b = self.body
        if self.grab.active:
            self._itemplay_end()
            self._transition("Dragged")
            return
        if self._itemplay_phase == 0:
            it = self._itemplay_target
            if it is None or it.state not in ("free", "hanging"):
                self._itemplay_end()
                self._transition("IdleStand")
                return
            from ..world.spear import Spear
            from ..world.pearl import Pearl
            is_spear = isinstance(it, Spear)
            is_fruit = it in getattr(self.win, "fruits", ()) or isinstance(it, Pearl)
            kind = "spear" if is_spear else ("fruit" if is_fruit else "stone")
            side = b.pick_hand(kind)
            if side is None:
                self._itemplay_end()
                self._transition("IdleStand")
                return
            if side is None:
                side = "r"            # 两手都塞着更重要的东西：这次抓不动，下次再来
            self._itemplay_side = side
            b.walk_to(it.x)
            self.gfx.look_at = (it.x, it.y)
            hx, hy = b._carry_pos(side)
            d = min(math.hypot(b.chunk0.x - it.x, b.chunk0.y - it.y),
                    math.hypot(hx - it.x, hy - it.y))
            if d < b.arm_full_reach * 2.0:
                b.reach_for(it, side)
            if d < tuning.GRAB_REACH:
                b.stop_walk()
                if is_spear:
                    b.grab_spear(it, side)
                elif is_fruit:
                    b.grab_fruit(it, side)
                else:
                    b.grab_stone(it, side)
                self._itemplay_phase = 1
                self.timer = 0
                self._itemplay_left = self.rng.randint(tuning.ITEMPLY_TICKS_MIN,
                                                       tuning.ITEMPLY_TICKS_MAX)
            elif self.timer > 240:
                self._itemplay_end()
                self._transition("IdleStand")
            return
        carried = b.carried_spear
        if carried is None:
            carried = b.carried_stone if b.carried_stone is not None else b.carried_fruit
        if carried is None:
            self._itemplay_end()
            self._transition("IdleStand")
            return

        # 「甩出去后追」是独立的一段玩法：物件飞出去后，猫用统一 Planner 追回，
        # 追不到才放弃。只对能真正投掷的石头/矛启用。
        if self._itemplay_phase == 2:
            it = self._itemplay_target
            if it is None or getattr(it, "state", None) == "gone":
                self._itemplay_end()
                self._transition("IdleStand")
                return
            if self._itemplay_chase_exec is None:
                goal = obj_goal(it,
                                valid=lambda o: getattr(o, "state", None) == "free",
                                radius=tuning.ITEMPLY_REACH,
                                contact="travel")
                self._itemplay_chase_exec = PlanExecutor(
                    self.win, self.planner, goal, mode=MODE_TOUCH)
            self.gfx.look_at = (it.x, it.y)
            status = self._itemplay_chase_exec.update()
            if math.hypot(it.x - b.chunk1.x, it.y - b.chunk1.y) <= tuning.ITEMPLY_REACH:
                self._itemplay_end()
                self._transition("IdleStand")
                return
            if status == GIVEUP:
                self._itemplay_end()
                self._transition("IdleStand")
            return
        self._itemplay_left -= 1
        self._itemplay_mode_t += 1
        t = self.timer
        self._play_face = 1 if self._play_face >= 0 else -1
        b.facing = self._play_face

        # 上手冷却结束后，活跃猫有机会把玩具甩出去，再用 Planner 追回；
        # 追一次后本轮不再连续投，避免「循环扔-追-扔」变成死循环。
        from ..world.spear import Spear
        can_throw_toy = (isinstance(carried, Spear) or carried is b.carried_stone)
        if (can_throw_toy and self.body.item_ready()
                and self._itemplay_phase == 1
                and self._itemplay_throw_count == 0
                and self._itemplay_mode_t > 45
                and self.rng.random() < tuning.ITEMPLY_TOSS_P):
            dir_x = 1 if self._play_face >= 0 else -1
            thrown = False
            if isinstance(carried, Spear):
                thrown = self._launch_weapon(dir_x)
            elif b.carried_stone is carried:
                b.throw_stone(dir_x, weaponphys.frc(weak=self._exhausted),
                              fling=True, recoil=0.25)
                thrown = True
            if thrown:
                self._itemplay_throw_count = 1
                self._itemplay_phase = 2
                self._itemplay_mode_t = 0
                return

        # 一个玩具内部也会换「微动作」，不再整段保持同一姿势。
        if self._itemplay_mode_t >= self.rng.randint(34, 70):
            old_mode = self._itemplay_mode
            choices = ["inspect", "paw", "hop"]
            choices.remove(old_mode)
            self._itemplay_mode = self.rng.choice(choices)
            self._itemplay_mode_t = 0

        side = self._itemplay_side
        hx, hy = b._carry_pos(side)
        if self._itemplay_mode == "paw":
            # 两只手轮流拨弄：手腕随时间做一个小弧线，视觉上像捏、拨、拍玩具。
            other = "l" if side == "r" else "r"
            phase = (self._itemplay_mode_t / 34.0) * math.tau
            ox = math.sin(phase) * 8.0
            oy = math.cos(phase) * 4.0
            b.arm_aim[side] = (hx + self._play_face * ox, hy + oy)
            b.arm_aim[other] = None
            self.gfx.hand_aim[side] = b.arm_aim[side]
            self.gfx.hand_aim[other] = None
            if self._itemplay_mode_t % 17 == 0:
                self._play_face = -self._play_face
        elif self._itemplay_mode == "hop":
            b.set_crawl(False)
            # 活跃/急躁猫更容易带着玩具小跳，不是每个 tick 都跳。
            if b.on_floor() and self._itemplay_mode_t % tuning.ITEMPLY_PRANCE_CD == 0:
                self._play_hop()
            self.gfx.look_at = (hx, hy)
        else:
            # 端详玩具：头跟着手中的物件扫，不时转身换朝向。
            b.set_crawl(False)
            sway = math.sin(self._itemplay_mode_t * 0.16) * 12.0
            self.gfx.look_at = (hx + sway, hy - 3.0)
            b.arm_aim[side] = (hx, hy)
            b.arm_aim["l" if side == "r" else "r"] = None
            self.gfx.hand_aim[side] = (hx, hy)
            self.gfx.hand_aim["l" if side == "r" else "r"] = None
            if self._itemplay_mode_t % tuning.ITEMPLY_PRANCE_CD == 0:
                if self.rng.random() < tuning.ITEMPLY_TURN_P:
                    self._play_face = -self._play_face

        if self._itemplay_left <= 0 or t > 2400:
            if self.rng.random() < getattr(self.pers, "temper", 0.5) * tuning.ITEMPLY_FLING_P:
                self._itemplay_fling()
            self._itemplay_end()
            self._transition("IdleStand")

    def _play_hop(self) -> float:
        """玩耍跳：方向与距离都随机；返回这次抽到的横向落点（带符号，供验收）。

        宠物猫没有输入，横速只能在起跳那一帧写进 chunk；横速由「落点距离 / 滞空 tick」
        反推，这样抽到的距离就是真的跳出去的距离（不是只把距离当摆设）。
        """
        b = self.body
        d = 1.0 if self.rng.random() < 0.5 else -1.0
        dist = self.rng.uniform(tuning.ITEMPLY_HOP_DIST_MIN, tuning.ITEMPLY_HOP_DIST_MAX)
        self._play_face = int(d)
        b.facing = int(d)
        b.walk_to(b.chunk1.x + d * dist)
        if b.on_floor() or b.coyote > 0:
            b.play_hop(d, dist / tuning.ITEMPLY_HOP_AIRTIME, tuning.ITEMPLY_HOP_VY_K)
        return d * dist

    # ── 觅食时捡矛（打未开荚的爆米花）──
    def _nearest_fetchable_spear(self):
        """地上可取用的矛（插着或躺着的），限 COB_SPEAR_FETCH_R 内。"""
        c0 = self.body.chunk0
        best, bd = None, tuning.COB_SPEAR_FETCH_R
        for sp in self.win.spears:
            if sp.state != "free" or not _spear_takeable(sp):
                continue
            if not self._spear_usable(sp):        # 钉成杆的矛：只有工匠拔得动
                continue
            if not (sp.stuck or (abs(sp.vx) < 0.4 and abs(sp.vy) < 0.4)):
                continue
            d = math.hypot(sp.x - c0.x, sp.y - c0.y)
            if d < bd:
                best, bd = sp, d
        return best

    def _cob_fetch_spear(self) -> bool:
        """去把地上最近的矛捡起来；有矛可捡返回 True。"""
        b = self.body
        sp = self._nearest_fetchable_spear()
        if sp is None:
            return False
        side = b.pick_hand("spear")
        if side is None:
            return False
        b.walk_to(sp.x)
        self.gfx.look_at = (sp.x, sp.y)
        hx, hy = b._carry_pos(side)
        d = min(math.hypot(b.chunk0.x - sp.x, b.chunk0.y - sp.y),
                math.hypot(hx - sp.x, hy - sp.y))
        if d < b.arm_full_reach * 2.0:
            b.reach_for(sp, side)
        if d < tuning.GRAB_REACH:
            b.stop_walk()
            b.grab_spear(sp, side)
        return True

