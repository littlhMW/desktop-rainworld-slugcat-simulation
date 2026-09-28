"""行为状态机 BehaviorFSM。"""
from __future__ import annotations
import math
import os
import random

from ..behavior import tuning
from ..core.creature import (ZEROG_GRAB_DIST, WALK_STOP_EPS, WALL_CLIMB_SPEED,
                             _closest_on_segment)
from ..planning import (GIVEUP, HOLDING, MODE_STAY, PlanExecutor, Planner, obj_goal)
from .blocking import (blocks_path, yield_target_x, on_same_pole,
                        pole_in_the_way)
from .pointing import PointGesture
from . import social
from .desire import build_arbiter, MoodContext
from .fetch import (fetch_ready, BITE_HEAD_NUDGE, EAT_APPROACH, EAT_CHOMP_POSE,
                    EAT_HOLD_POSE, EAT_INTERVAL)
from ..cats.personality import DIET_VEGETARIAN, DIET_SPECIAL
from .objectlooker import ObjectLooker
from ..control.mouse import GrabController
from ..cats.saint.cursorlick import (BAND_LO as LICK_BAND_LO, BAND_HI as LICK_BAND_HI,
                                     DWELL_TICKS as LICK_DWELL, DWELL_TOL as LICK_DWELL_TOL,
                                     GATE_FRAC as LICK_GATE_FRAC)
from ..world import weaponphys
from ..world.pole import cross_partner
from ..world.enums import ItemState
from ..core import edges as edgeqm
from ..core.units import clampf

# 计时常量（tick）
T_POINT_WAKE = 160
T_POSTTHROW_WANDER = 200
T_POSTTHROW_STAND = 400
ANGER_TOTAL = T_POSTTHROW_WANDER + T_POSTTHROW_STAND
T_FETCH_COOLDOWN = 200
T_FETCH_CHECK = 8   # 取果闸重算间隔
HUNT_CD = 900       # 一次捕猎后的冷却（tick）
T_HPOLE_TIMEOUT = 1600
HPOLE_MAX_CLIMBS = 3
WAKE_STABILIZE_TICKS = 30

# ── 六类欲望（进食/恐惧/战斗/玩耍/睡眠/社交）计时常量 ──
T_WALL_RETRY = 120        # 爬墙失败后的冷却
T_SOCIAL_RETRY = 400      # 社交冷却
T_HELP_RETRY = 600        # 帮取食冷却
T_FIGHT_RETRY = 500       # 战斗冷却
T_COB_RETRY = 300         # 爆米花放弃后的重试冷却
T_CRAWL_RETRY = 300       # 匍匐躲避冷却
T_PROTEST_RETRY = 900     # 抗议被抢东西的冷却
T_REVIVE_RETRY = 200      # 复活失败重试
SPEAR_AI_SPEED = 34.0     # 投矛初速（同 huntfly.SPEED_SPEAR）
STONE_AI_SPEED = 26.0     # 投石初速（同 huntfly.SPEED_STONE）
# 被咬/被矛的致死判定：原版 Player.DeathByBiteMultiplier（故事模式 0.7 + 难度/5）
DEATH_BY_BITE_MULT = 0.75
MONK_DEATH_BY_BITE_MULT = 0.0     # 黄猫（僧侣）永不被咬死
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
_WANTS_STATES = frozenset(("WallClimb", "CeilingHang", "ChaseCursor", "Socialize",
                           "HelpFeed", "FightThreat", "CrawlAway", "EatCob",
                           "ScoldBlocker", "CatchFly", "ItemPlay"))

WALL_MARGIN = 40.0

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
_ZEROG_KEEP = frozenset(("IdleStand", "Dragged", "Dead", "Stunned", "Ascension", "DodgeKill", "Swimming"))
# 浸水下保留态，其余打断转 Swimming
_SWIM_KEEP = frozenset(("Swimming", "Ascension", "Dragged", "Dead", "Stunned", "DodgeKill",
                        "TongueClimb", "CeilingHang"))

ARM_REACH_NEAR = 24.0
ARM_REACH_FAR = 48.0
THROW_JUMP_DY = 12.0      # 目标高出这么多 → 先起跳再水平投（原版只能横着发射）
JUMPCUR_DY = 52.0         # 追鼠标：高度差在这以内才值得跳着够
JUMPCUR_R = 130.0         # 追鼠标：水平距离上限
JUMPCUR_CD = 24
JUMPCUR_P = 0.6
HPOLE_NEAR_Y = 20.0
HPOLE_REACH_FRAC = 0.85
HPOLE_GRAB_REACH = 0.60

# 精力 energy（tick）
EN_DRAIN_VIGOROUS = 1.0 / 1200.0
EN_DRAIN_LIGHT = 1.0 / 4800.0
EN_REC_REST = 1.0 / 800.0
EN_REC_IDLE = 1.0 / 1600.0

_STATE_TO_MOOD = {"PoleClimb": "pole_climb",
                  "SeekHPole": "hpole", "HPole": "hpole",
                  "WallClimb": "wall_climb", "CeilingHang": "ceiling_hang",
                  "ChaseCursor": "play_cursor", "Socialize": "socialize"}
# 疲劳强制休息不打断的态
_EXHAUST_BLOCKED = frozenset(("Dragged", "Dead", "Stunned", "Ascension",
                              "DodgeKill", "WakeSequence", "LieDown", "Sleep", "SeekWarmth",
                              "Swimming"))
# 趋暖强制中断不打断的态
_COLD_BLOCKED = frozenset(("Dragged", "Dead", "Stunned", "Ascension",
                           "DodgeKill", "WakeSequence", "SeekWarmth", "Swimming"))
# 避水强制中断不打断的态
_WATER_BLOCKED = frozenset(("RelocateToWall", "TongueClimb", "CeilingHang", "Swimming",
                            "Dragged", "Dead", "Stunned", "Ascension", "DodgeKill"))
# 取果触发不打断的态
_FETCH_NEVER = frozenset(("FetchFruit", "Ascension", "Dragged", "Dead", "WakeSequence",
                          "Stunned", "DodgeKill", "SeekWarmth", "Swimming",
                          "LieDown", "Sleep",          # 趴/睡时别把猫叫起来去取果
                          "PyroMaul", "RivSnatch", "CatchFly", "ItemPlay"))
# play 态接管取果需果在舌头射程内
_FETCH_PLAY = frozenset(("PoleClimb", "HPole", "CeilingHang"))


_EN_VIGOROUS = frozenset(("TongueClimb", "PoleClimb", "HPole", "CeilingHang", "DodgeKill", "Swimming",
                          "PyroRomp", "RivFlip", "PyroMaul", "RivSnatch"))
_EN_LIGHT = frozenset(("RelocateToWall", "PostThrowWander", "FetchFruit", "AngryStone",
                       "WakeSequence", "CursorLick", "SeekWarmth", "SeekHPole", "MakeWay",
                       "FleeLizard", "CatchFly", "ItemPlay"))
_EN_REST = frozenset(("LieDown", "Sleep"))
_EN_IDLE = frozenset(("IdleStand", "PostThrowStand"))

# 被顶让路仅从这些无更高目的态触发
_MAKEWAY_FROM = frozenset(("IdleStand", "PostThrowWander", "PostThrowStand"))

# ── 躲蜥蜴（原版 Player 见威胁逃逸）──
FLEE_R = 110.0            # 蜥蜴进入此水平距离 → 掉头跑
FLEE_SAFE_R = 150.0       # 拉开到此距离 → 安全，收工
FLEE_GAP = 90.0           # 逃跑目标：离蜥蜴这么远
FLEE_MAX_TICKS = 200      # 单次逃跑上限
FLEE_COOLDOWN = 300       # 两次躲之间至少隔这么久（进场即计时）
# 只从「没事干」的态里起跑：取果/送礼这类有目的的态不打断
_FLEE_FROM = frozenset(("IdleStand", "PostThrowWander", "PostThrowStand", "MakeWay"))


def _energy_delta(state: str, drain_fac: float = 1.0) -> float:
    # 恢复不受体力影响，消耗按 drain_fac 缩放
    if state in _EN_REST:
        return EN_REC_REST
    if state in _EN_IDLE:
        return EN_REC_IDLE
    if state in _EN_VIGOROUS:
        return -EN_DRAIN_VIGOROUS * drain_fac
    if state in _EN_LIGHT:
        return -EN_DRAIN_LIGHT * drain_fac
    return 0.0


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
        self.pers = window.cat.personality
        self._drain_fac = 1.0 / max(0.01, self.pers.stamina)
        self._look_fac = max(0.0, 1.0 + tuning.PERS_ACT_SPREAD * (self.pers.activity - 0.5))
        self.body = window.body
        self.gfx = window.gfx
        self.WL = window._WL
        self.HL = window._HL
        self.rng = random.Random(seed)
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
        self._chew_counter = 0
        self._chew_bit = False
        self._chew_approach = True
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
        self.dodge = None
        self.fetch = None
        self.planner = Planner(window)
        self._fetch_cooldown = 0
        self._fetch_check = 0
        self._shoved_ticks = 0
        self._makeway_of = None
        self._flee_from = None
        self._flee_cd = 0
        # 六类欲望：匍匐/爬墙/吊顶/玩耍/社交/帮取食/抗议/战斗/复活/睡眠
        self._wall_goal = 0
        self._wall_left = 0
        self._wall_ready = False
        self._wall_top_y = 0.0        # 这面墙的可攀爬上沿 y
        self._wall_ledge_t = 0        # 抓沿悬停计时
        self._wall_sliding = False    # 抓不住墙头：贴墙缓慢下滑中
        self._ceil_left = 0
        self._ceil_dir = 1
        self._ceil_walk_t = 0
        self._ceil_placed = False
        self._struggle_left = 0
        self._cob = None              # 正在啃/要打的爆米花豆荚
        self._cob_eat_t = 0           # 本口剩余 tick（原版 eatExternalFoodSourceCounter）
        self._cob_cd = 0              # 两口之间的冷却（原版 dontEatExternalFoodSource…）
        self._cob_left = 0            # 啃食态超时
        self._cob_check = 0
        self._cob_seek_cd = 0
        self._play_left = 0
        self._social_left = 0
        self._social_kind = "pet"
        self._social_target = None
        self._social_touch = 0
        self._social_urge = 0.0
        self._social_gesture = None
        self._social_press_seen = 0
        self._social_press_per = 1
        self._help_left = 0
        self._help_target = None
        self._protest_left = 0
        self._protest_target = None
        self._fight_left = 0
        self._fight_target = None
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
        self._air_throw_cd = 0
        self._crawl_cd = 0
        self._protest_cd = 0
        self._revive_cd = 0
        self._wall_cd = 0
        self._saved_walk = None
        self._fight_throw_t = 0
        self._blocked_ticks = 0
        self._block_grace = 0
        self._jump_over_cd = 0
        # 挡路升级：跳过 → 推人 → 回头指指点点；杆上被挡 → 停住扒拉
        self._jump_tries = 0
        self._push_left = 0
        self._push_x = None
        self._push_side = "r"
        self._blocker_target = None
        self._last_blocker = None
        self._hp_goal_x = None        # 上横杆去够的东西的 x（横杆可达食物）
        self._hp_goal_obj = None
        self._hp_jump_goal = None     # 杆上起跳后空中要摘的东西      # 上次挡我路的人（跳过去后可能回头指他）
        self._scold_left = 0
        self._scold_cd = 0
        self._pole_blocker = None
        self._pole_nudge = 0
        self._pole_nudge_t = 0
        self._pole_nudge_pin = None
        self._pole_nudge_cd = 0
        self._pole_nudge_point = False
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
        # 被指指点点后面对发起者匍匐
        self._crawl_point_to = None
        self.stonethrow = None
        self.flyhunt = None
        self._hunt_cd = 0
        self.flycatch = None            # 徒手抓飞虫控制器
        self._catch_cd = 0
        self._itemplay_cd = 0
        self._back_spear_cd = 0
        self._itemplay_target = None
        self._itemplay_left = 0
        self._itemplay_phase = 0
        self._itemplay_side = "r"
        # 觅食欲望：吃到东西归 0，慢慢涨回 1 才想再找吃的
        self._food_urge = 1.0
        self._food_prev = self.body.food
        # 代谢：体力消耗累计（满一条扣一格饱食）
        self._drain_acc = 0.0
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
        self.threat_response = None
        self.drag_takeover = None
        self.stun_takeover = None
        cat = getattr(self.win, "cat", None)
        if cat is not None and cat.fsm_mount is not None:
            cat.fsm_mount(self)

        self._enter("IdleStand")

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
        if self.state in ("WallClimb", "CeilingHang", "ChaseCursor", "Socialize",
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
        if self.dodge is not None:
            self.dodge.release()
            self.dodge = None
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
        elif self.state in ("WallClimb", "CeilingHang", "ChaseCursor", "Socialize",
                            "HelpFeed", "FightThreat", "CrawlAway", "EatCob",
                            "ScoldBlocker", "CatchFly", "ItemPlay"):
            self._wants_break(self.state)
        self._hibernating = False
        self.body.food_eat(-tuning.FOOD_KILL_PENALTY)
        if self.body.karma > 0 or self.body.karma_bottomed():
            self.body.karma_drop()    # 工匠锁底也照常计入
            self.body.temper_shift(tuning.TEMPER_KILL_REVIVED)
            self.body.die()
            self.gfx.dead = True
            self._transition("Dead")
            self._revive_timer = 0    # 真死：不再自行计时复活，只有同伴 nuzzle 才回来
        else:
            self.body.die()
            self._transition("Dead")
            self._revive_timer = 0

    def kill_cold(self):
        """冻死：环境致死，转世复活，不计好感。"""
        if self.state == "Dead":
            return
        self.body.karma_drop()
        self._dismiss_kill_dialog()
        self._break_active_controllers()
        self.grab.force_release()
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._reincarnate = True
        self._revive_timer = tuning.REINCARNATE_TICKS

    def kill_drown(self):
        """溺死：环境致死，转世复活，不计好感。"""
        if self.state == "Dead":
            return
        self.body.karma_drop()
        self._dismiss_kill_dialog()
        self._break_active_controllers()
        self.grab.force_release()
        self.body.swim_target = None
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._reincarnate = True
        self._revive_timer = tuning.REINCARNATE_TICKS

    def kill_pyro_drown(self):
        """工匠溺水引爆而死，转世复活。"""
        if self.state == "Dead":
            return
        from ..cats.artificer.pyro import pyro_explosion
        pyro_explosion(self.win, self.body)
        self.body.karma_drop()
        self._dismiss_kill_dialog()
        self._break_active_controllers()
        self.grab.force_release()
        self.body.swim_target = None
        self.body.pyro_drown = False
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._reincarnate = True
        self._revive_timer = tuning.REINCARNATE_TICKS

    def kill_threat_canceled(self, by_saint: bool):
        self.body.temper_shift(self.win.cat.tuning["temper_kill_cancel_saint"] if by_saint
                               else tuning.TEMPER_KILL_CANCEL_HUMAN)

    def is_dead(self) -> bool:
        return self.state == "Dead"

    def is_truly_dead(self) -> bool:
        return self.state == "Dead" and self._revive_timer <= 0

    def begin_reincarnation(self) -> bool:
        """全体转生：真死也一起走转世倒计时（环境致死同一通路）。"""
        if self.state != "Dead":
            return False
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
        elif st == "SeekHPole":
            self._seekhpole_break()
        elif st == "Swimming":
            self.body.swim_target = None
        elif st in ("WallClimb", "CeilingHang", "ChaseCursor", "Socialize",
                    "HelpFeed", "FightThreat", "CrawlAway", "EatCob",
                    "ScoldBlocker", "CatchFly", "ItemPlay"):
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

        if (getattr(self.win, "_kill_dialog", None) is not None
                and self.threat_response is not None
                and self.state not in ("Sleep", "Dead", "DodgeKill", "Ascension")):
            self._break_active_controllers()
            self.grab.force_release()
            self.threat_response()

        self.grab.tick()
        if (self.grab.active and self.state not in
                ("Dragged", "Ascension", "Dead", "TongueClimb", "CeilingHang",
                 "FetchFruit", "CursorLick", "AngryStone", "PoleClimb", "HPole",
                 "DodgeKill", "SeekHPole")):
            self._transition("Dragged")
        if self.grab.active:
            self.grab.drag(cursor) if cursor is not None else None
        self._shake_drop_tick()

        # 浸水优先级：溺爆/溺死/入水/出水
        if self.body.pyro_drown and self.state != "Dead":
            self.kill_pyro_drown()
        elif self.body.drown >= 1.0 and self.state != "Dead":
            self.kill_drown()
        elif self.body.swimming:
            if self.state not in _SWIM_KEEP:
                self._break_active_controllers()
                self._transition("Swimming")
        elif self.state == "Swimming":
            self.body.swim_target = None
            self._transition("IdleStand" if self.body.on_floor() else "Airborne")

        # 无重力强制转漂浮 idle
        if self._zerog() and self.state not in _ZEROG_KEEP:
            self._break_active_controllers()
            self._transition("IdleStand")

        # 避水自救压过趋暖
        if (self._water_urgent() and not self.grab.active and not self._zerog()
                and self.state not in _WATER_BLOCKED):
            self._break_active_controllers()
            self._wall_side = -1 if self.body.chunk1.x < self.WL / 2 else 1
            self._transition("RelocateToWall")

        # 趋暖强制中断，避水期间让位
        if (self._cold_urgent() and not self.grab.active and not self._zerog()
                and not self._water_urgent()
                and self.state not in _COLD_BLOCKED):
            self._break_active_controllers()
            self._transition("SeekWarmth")

        # 挡路互动扫描
        self._scan_blocking()

        # 躲蜥蜴：就近出现蜥蜴 → 掉头跑开
        if self._flee_cd > 0:
            self._flee_cd -= 1
        if (self._flee_cd <= 0 and self.state in _FLEE_FROM
                and not self.grab.active and not self._exhausted and not self._zerog()
                and not self._carrying_gift()
                and not self.body.swimming and self.body.on_floor()):
            lz = self._nearby_lizard()
            if lz is not None:
                self._flee_from = lz
                self._transition("FleeLizard")

        # 六类欲望：社交 / 帮取食 / 反击 / 匍匐躲避 / 被抢抗议
        self._wants_tick(cursor)

        # 体力告急强制休息
        if (not self._exhausted and not self._hibernating and not self.grab.active
                and not self._cold_urgent() and not self._zerog()
                and self.body.energy < tuning.EXHAUST_ENTER_ENERGY
                and self.state not in _EXHAUST_BLOCKED):
            self._exhausted = True
            self._enter_exhaustion()

        if self._fetch_cooldown > 0:
            self._fetch_cooldown -= 1

        # 取果触发：门禁 + 间隔节流重算候选
        self._fetch_check = (self._fetch_check + 1) % T_FETCH_CHECK
        self._food_urge_tick()
        self._social_urge_tick()
        if (self._fetch_check == 0
                and self.body.food < self.body.food_max
                and self._food_seek_ready()
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and self._fetch_cooldown <= 0
                and self.state not in _FETCH_NEVER):
            fetch_cands = fetch_ready(self.planner, self.win.fetchables(),
                                      diet=self.pers.diet)
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
            else:
                self._hpole_food_trip()

        # 爆米花（原版外部食物源）：开荚的贴上去就能啃；饿了主动走过去
        if self._cob_cd > 0:
            self._cob_cd -= 1
        if self._cob_seek_cd > 0:
            self._cob_seek_cd -= 1
        self._cob_check = (self._cob_check + 1) % tuning.COB_CHECK_TICKS
        if (self._cob_check == 0 and self._cob_seek_cd <= 0
                and self.body.food < self.body.food_max
                and self._food_seek_ready()
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and self.state in _WANTS_FROM):
            cb = self._nearest_cob(feedable=True)
            if cb is None:
                cb = self._nearest_cob(feedable=False)     # 没开荚：去捡矛打
            if cb is not None:
                self._cob = cb
                self._break_active_controllers()
                self._act_or_wake("EatCob")

        # 狩猎飞虫（原版：蝙蝠/蝉乌贼在空中 → 捡石/持矛预判投掷）
        if self._hunt_cd > 0:
            self._hunt_cd -= 1
        has_weapon = (self.body.carried_stone is not None
                      or self.body.carried_spear is not None)
        hunting = (self.body.food < self.body.food_max and self._food_seek_ready())
        playing = (has_weapon and self.rng.random() < tuning.HUNT_PLAY_PROB)
        if (self._fetch_check == 0 and self._hunt_cd <= 0
                and (hunting or playing)
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander")):
            from .huntfly import FlyHunter
            probe = FlyHunter(self.win, self.rng, self)
            if probe._flies() and (probe._ground_stones() or probe._ground_spears()
                                   or self.body.carried_stone is not None
                                   or self.body.carried_spear is not None):
                self._break_active_controllers()
                self._act_or_wake("HuntFly")

        # 徒手抓飞虫：饿了抓来吃，吃饱了抓着玩一会儿再放走
        if self._catch_cd > 0:
            self._catch_cd -= 1
        if (self._catch_cd <= 0
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander")
                and self._nearest_catchable() is not None):
            self._break_active_controllers()
            self._act_or_wake("CatchFly")

        # 平时也爱捡地上的矛/石头把玩（正饿着找食时先不玩，别把矛/石头抢走）
        if self._itemplay_cd > 0:
            self._itemplay_cd -= 1
        if (self._fetch_check == 0 and self._itemplay_cd <= 0
                and not (self.body.food < self.body.food_max and self._food_urge >= 1.0)
                and not self.grab.active and not self._exhausted
                and not self._cold_urgent() and not self._zerog()
                and not self._hibernating and not self.body.swimming
                and self.state in ("IdleStand", "PostThrowStand", "PostThrowWander")
                and self.rng.random() < tuning.ITEMPLY_P):
            it = self._nearest_play_item()
            if it is not None:
                self._itemplay_target = it
                self._break_active_controllers()
                self._act_or_wake("ItemPlay")

        self._back_spear_tick()

        # 睡眠欲望：吃饱后入睡概率从 0 缓慢升到 100
        self._sleep_urge_tick()
        if (not self._hibernating and not self.grab.active and not self._exhausted
                and not self._too_cold_to_sleep() and not self._zerog()
                and self._sleep_roll()
                and self.state in ("IdleStand", "LieDown")):
            self._hibernating = True
            self._sleep_drop_hands()          # 睡觉前把手里的东西放下（原版睡着不留吃的）
            if self.state == "IdleStand":
                self._transition("LieDown")

        if (self.state in ("PostThrowWander", "PostThrowStand") and self.anger > 0
                and not self.grab.active and self._grounded_stone_available()):
            self._transition("AngryStone")

        lick_dwell_need = _lerpmap(self.body.temper, -1.0, 1.0,
                                   LICK_DWELL * 1.5, LICK_DWELL * 0.5)
        if ("CursorLick" in self._ext_states
                and self.state == "IdleStand" and not self.grab.active and not self._exhausted
                and not self._zerog()
                and self._relick_cooldown <= 0 and self._dwell >= lick_dwell_need
                and cursor is not None
                and self.HL * LICK_BAND_LO <= cursor[1] <= self.HL * LICK_BAND_HI
                and abs(self.body.chunk0.x - cursor[0]) < self.WL * LICK_GATE_FRAC):
            self._transition("CursorLick")

        if self.anger > 0 and self.state in ("PostThrowWander", "PostThrowStand", "AngryStone"):
            self.anger -= 1

        self._squid_lift_tick()
        self.gfx.look_at = None
        # _hibernating 一置位就当场蜷起来（LieDown 期也一样），避免「睁着眼蜷着却睡不着」
        lying = self.state == "Sleep" or self._hibernating
        self.gfx.sleeping = lying
        self.body.sleeping = lying
        if self.state in ("LieDown", "Sleep"):
            self.gfx.face_special = False    # 睡姿不许挂醒着的表情
        self.gfx.dead = (self.state == "Dead")
        self.gfx.stunned = (self.state == "Stunned")

        handler = self._ext_states.get(self.state)
        if handler is None:
            handler = getattr(self, "_st_" + self.state.lower(), None)
        if handler:
            handler(cursor, disturbed)
        self._push_pose_tick()
        e_delta = _energy_delta(self.state, self._drain_fac)
        if (self.state == "PoleClimb" and self.poleclimb is not None
                and self.poleclimb.phase == "tip"):
            e_delta = -EN_DRAIN_LIGHT * self._drain_fac   # 站杆顶不算剧烈
        elif self.state == "Swimming" and self.body.swim_mode == "surface":
            e_delta = EN_REC_IDLE * tuning.SWIM_SURFACE_REST_FAC   # 浮水面歇气
        _en_before = self.body.energy
        self.body.energy_change(e_delta)
        self._metabolism(_en_before)
        if self._force_energy is not None:
            self.body.energy = self._force_energy
        if self._force_temper is not None:
            self.body.temper = self._force_temper
        if self._force_food is not None:
            self.body.food = self._force_food
        if self.body.food > self._food_prev:
            self._food_urge = 0.0          # 吃到东西：觅食欲望归 0
        self._food_prev = self.body.food
        self.mood.tick_freshness(self._active_mood())
        self.timer += 1

    def _transition(self, new):
        if new == self.state:
            return
        old = self.state
        self.state = new
        self.timer = 0
        self.phase = 0
        self._leave(old)
        self._enter(new)

    def _leave(self, old):
        """离开欲望态时统一收尾（幂等；_break_active_controllers 已跑过也无害）。"""
        if old in _WANTS_STATES:
            self._wants_break(old)

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
        elif st == "LieDown":
            self.gfx.face_special = False     # 趴下睡觉：醒着的表情收掉
            b.set_posture(False)
            b.stop_walk()
            self._settle_to_rest()
        elif st == "Sleep":
            self.gfx.face_special = False
            b.set_posture(False)
            b.stop_walk()
            self._settle_to_rest()
            self._sleep_left = int(tuning.HIBERNATE_TICKS * self.rng.uniform(
                tuning.SLEEP_LEN_MULT_MIN, tuning.SLEEP_LEN_MULT_MAX))
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
        elif st == "FleeLizard":
            self._enter_fleelizard()
        elif st == "WallClimb":
            self._wall_enter()
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

    def _mood_select(self):
        ctx = MoodContext(self.body.energy, self.body.temper,
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
        return self.mood.select(ctx)

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
        if self._zerog():
            self._zerog_idle(cursor)
            return
        if self._exhausted:
            self._transition("LieDown")
            return
        self.gfx.look_at = self._ambient_look(cursor)
        if self._idle_hold > 0:
            self._idle_hold -= 1
            self._idle_pace()
            return
        choice = self._mood_select()
        if choice == "seek_warmth":
            self._transition("SeekWarmth")
            return
        if choice == "pole_climb":
            self._transition("PoleClimb")
            return
        if choice == "hpole":
            self._transition("SeekHPole")
            return
        if choice == "ceiling_play":
            self._wall_side = -1 if self.body.chunk1.x < self.WL / 2 else 1
            self._transition("RelocateToWall")
            return
        if choice == "wall_climb":
            self._wall_enter()
            self._transition("WallClimb")
            return
        if choice == "ceiling_hang":
            self._ceiling_enter()
            self._transition("CeilingHang")
            return
        if choice == "play_cursor":
            self._play_enter()
            self._transition("ChaseCursor")
            return
        if choice == "socialize":
            tgt = self._nearest_peer()
            if tgt is None:
                self._idle_hold = self._roll_idle_hold()
                return
            self._social_kind = self._pick_social_kind(tgt)
            self._social_target = tgt
            if self._social_kind == "crouch_walk":
                # 匍匐行走：交给现有的 CrawlAway（害怕强敌潜行）
                self._crawl_from = None
                self._crawl_point_to = None
                self._crawl_left = tuning.CRAWL_AWAY_TICKS
                self._crawl_cd = T_CRAWL_RETRY
                self._break_active_controllers()
                self._transition("CrawlAway")
                return
            self._social_enter()
            self._transition("Socialize")
            return
        ext = self._ext_mood_states.get(choice)
        if ext is not None:
            self._transition(ext)
            return
        # idle 兜底：开发呆驻留再重抽
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
                        self._last_blocker, tuning.BLOCKED_POINT_AFTER_JUMP)):
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
        elif (blocker is not None and self._can_ground_blockreact()
              and self._blocked_ticks >= tuning.BLOCKED_JUMP_TICKS
              and self._jump_over_cd <= 0):
            if self._scold_now(blocker, tuning.BLOCKED_POINT_FIRST_MAX):
                self._blocked_ticks = 0        # 性格不好：懒得跳，先指着骂
            else:                              # 默认先跳，跳不过再推/指
                self.body.request_jump("stand", hold_ticks=tuning.JUMP_OVER_HOLD)
                self._jump_tries += 1
                self._blocked_ticks = 0
                self._jump_over_cd = tuning.JUMP_OVER_COOLDOWN
        elif (blocker is not None and self._can_ground_blockreact() and self._jump_tries > 0
              and self._blocked_ticks >= tuning.BLOCKED_PUSH_TICKS
              and self._jump_over_cd <= 0):
            self._push_blocker(blocker)     # 跳不过去 → 上手推他（推完可能回头指指点点）
            self._jump_tries = 0
            self._blocked_ticks = 0

    def _point_trait_fac(self) -> float:
        """指指点点倾向系数：暴躁 + 爱指的性格更容易指（中性 ≈ 1.0）。"""
        t = clampf(float(getattr(self.pers, "temper", 0.5)), 0.0, 1.0)
        pl = clampf(float(getattr(self.pers, "point_like", 0.5)), 0.0, 1.0)
        return ((tuning.POINT_TEMPER_LO
                 + (tuning.POINT_TEMPER_HI - tuning.POINT_TEMPER_LO) * t)
                * (0.6 + 0.8 * pl))

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
        """回头指指点点：先转身面对挡路者，再一下一下地指。"""
        b = self.body
        self._scold_left = tuning.SCOLD_TICKS
        self._scold_cd = tuning.SCOLD_CD
        b.set_posture(True)
        b.stop_walk()
        tb = getattr(self._blocker_target, "body", None)
        if tb is not None:
            b.facing = 1 if tb.chunk0.x >= b.chunk0.x else -1
        self._point_begin(self._blocker_target)

    def _scold_cleanup(self):
        self._blocker_target = None
        self._point_end()
        self.gfx.face_special = False

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
        if self._point_step():          # 一轮 3~5 下指完 → 再来一轮
            self._point_begin(self._blocker_target)
        if self.timer % tuning.SOCIAL_POKE_INTERVAL == 0:
            self._poke(tb)              # 顺手扒拉

    # ── 杆上被同伴挡路：停在中间扒拉几下（最后有概率指指点点）──
    def _pole_nudge_tick(self):
        """返回 True=本 tick 已被接管（别再推进爬杆控制器）。"""
        o = self._pole_blocker
        b = self.body
        tb = getattr(o, "body", None) if o is not None else None
        if (o is None or self._pole_nudge <= 0 or tb is None
                or not pole_in_the_way(b, tb, tuning.POLE_BLOCK_DIST * 1.6)):
            return self._pole_unfreeze()
        if self._pole_nudge_pin is None:            # 进入：原地钉住
            self._pole_nudge_pin = (b.chunk0.pinned, b.chunk1.pinned,
                                    b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y)
            self._pole_nudge_t = 0
            self._pole_nudge_point = False
            b.stop_walk()
        self._pole_nudge -= 1
        self._pole_nudge_t += 1
        _p0, _p1, x0, y0, x1, y1 = self._pole_nudge_pin
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = c1.pinned = True                # 抱在杆上不动
        c0.x, c0.y, c0.vx, c0.vy = x0, y0, 0.0, 0.0
        c1.x, c1.y, c1.vx, c1.vy = x1, y1, 0.0, 0.0
        self.gfx.look_at = (tb.chunk0.x, tb.chunk0.y)
        if self._pole_nudge <= tuning.POLE_NUDGE_POINT_TAIL and not self._pole_nudge_point:
            self._pole_nudge_point = self.rng.random() < tuning.POLE_NUDGE_POINT_PROB
            if self._pole_nudge_point:
                self._point_begin(o)                # 后半段改成指指点点
            else:
                self._clear_hands()
        if self._pole_nudge_point:
            self._point_step()
        elif self._pole_nudge_t % tuning.POLE_NUDGE_POKE == 0:
            self._poke(tb)                          # 扒拉
            side = "r" if tb.chunk0.x >= c0.x else "l"
            self.gfx.hand_aim[side] = (tb.chunk0.x, tb.chunk0.y)
            self.gfx.hand_aim["l" if side == "r" else "r"] = None
        elif self._pole_nudge_t % tuning.POLE_NUDGE_POKE == tuning.POLE_NUDGE_POKE // 2:
            self._clear_hands()
        if self._pole_nudge <= 0:
            return self._pole_unfreeze()
        return True

    def _pole_unfreeze(self):
        """还原「停住扒拉」钉住的 chunk 状态；返回 False（=没接管本 tick）。"""
        if self._pole_nudge_pin is None:
            return False
        _p0, _p1, x0, y0, x1, y1 = self._pole_nudge_pin
        self._pole_nudge_pin = None
        self._pole_nudge = 0
        self._pole_nudge_point = False
        self._pole_nudge_cd = tuning.POLE_NUDGE_CD
        self._point_end()
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

    def _nearby_lizard(self):
        """水平距离最近且在 FLEE_R 内的蜥蜴；没有则 None。"""
        x = self.body.chunk1.x
        best, bd = None, FLEE_R
        for lz in getattr(self.win, "lizards", ()):
            if getattr(lz, "state", None) != ItemState.FREE:
                continue
            d = abs(lz.x - x)
            if d < bd:
                best, bd = lz, d
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
        return min(max(lz.x + side * FLEE_GAP, lo), hi)

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
        if b.food < b.food_max and self._fetch_cooldown <= 0:
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
            if getattr(f, "is_meat", False) and self.pers.diet in (DIET_VEGETARIAN, DIET_SPECIAL):
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
            b.grab_fruit(e, "r" if e.x >= b.chunk0.x else "l")
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
        self._chew_counter = 0
        self._chew_bit = False
        self._chew_approach = True

    def _carry_chew(self, b):
        """叼果咀嚼动画：起手渐抬后按周期塞嘴，峰值咬一口并头部前探。"""
        f = b.carried_fruit
        self.gfx.look_at = (f.x, f.y)
        self._chew_counter += 1
        if self._chew_approach:
            b.eat_raise = EAT_HOLD_POSE * min(1.0, self._chew_counter / EAT_APPROACH)
            if self._chew_counter >= EAT_APPROACH:
                self._chew_approach = False
                self._chew_counter = 0
            return
        phase = min(1.0, self._chew_counter / EAT_INTERVAL)
        b.eat_raise = EAT_HOLD_POSE + (EAT_CHOMP_POSE - EAT_HOLD_POSE) * math.sin(phase * math.pi)
        if self._chew_counter >= EAT_INTERVAL // 2 and not self._chew_bit:
            self._chew_bit = True
            dx, dy = f.x - self.gfx.head.x, f.y - self.gfx.head.y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                self.gfx.head.vx += dx / d * BITE_HEAD_NUDGE
                self.gfx.head.vy += dy / d * BITE_HEAD_NUDGE
            b.consume_carried()
        if self._chew_counter >= EAT_INTERVAL:
            self._chew_counter = 0
            self._chew_bit = False

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
        if b.food < b.food_max and self._fetch_cooldown <= 0:
            e = self._nearest_swim_edible()
            if e is not None:
                b.swim_target = (e.x, e.y)
                if math.hypot(e.x - b.chunk0.x, e.y - b.chunk0.y) < tuning.SWIM_FETCH_REACH:
                    b.grab_fruit(e, "r" if e.x >= b.chunk0.x else "l")
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
            if getattr(f, "is_meat", False) and self.pers.diet in (DIET_VEGETARIAN, DIET_SPECIAL):
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
            self.body.karma_gain()
            self.body.food_eat(-self.body.food_hibernate)
            self.body.energy = 1.0
            self._hibernating = False
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
            if not self._point_active():
                if self._cursor_point_ok():
                    self._point_begin(cursor, mode="cursor", enforce_side=True)
            if self._point_step() or self.timer >= T_POINT_WAKE:
                self._point_end()
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
        if ch is None or not self.body.hand_of:
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
        kind = min(b.hand_of, key=lambda k: b.ITEM_PRIO.get(k, 0))
        item = {"fruit": b.carried_fruit, "stone": b.carried_stone,
                "spear": b.carried_spear}.get(kind)
        b._release_item(kind, to_free=True)
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
        free_hands = (b.carried_fruit is None and b.carried_stone is None
                      and b.carried_spear is None)
        if free_hands and self._drag_cd <= 0 and self._drag_grab_item():
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
            side = "r" if best.x >= b.chunk0.x else "l"
            if kind == "fruit":
                b.grab_fruit(best, side, snap_stalk=False)   # 摘取类：拖走才把果子拽下来
            elif kind == "spear":
                b.grab_spear(best, side)
            else:
                b.grab_stone(best, side)
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
                self._point_at_cursor(cursor, cover=True)
            if self._struggle_left % 6 == 0:
                self._struggle_kick()
            if self._struggle_left <= 0:
                self._clear_hands()
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

    def _st_airborne(self, cursor, disturbed):
        b = self.body
        self._hp_jump_grab()
        self._air_throw()                # 空中投矛
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
        self.gfx.face_special = False
        # 死亡不再自行复活：只有同伴用特殊表情扒拉（_nuzzle 触碰累计）或
        # 环境致死转世（_reincarnate）才会回来。
        if self._revive_timer > 0:
            self._revive_timer -= 1
            if self._revive_timer <= 0:
                if self._reincarnate:
                    # 转世：window 下 tick 顶部中央 respawn
                    self._reincarnate = False
                    self.win._reincarnate_pending = True
                    return
                self.body.revive()
                self.gfx.dead = False
                self.gfx.sleeping = False
                self.body.sleeping = False
                self.gfx.sleep_curl = 0.0
                self.body.set_posture(False)
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
            self._point_at_cursor(cursor, enforce_side=False,
                                  cover=(d <= ARM_REACH_NEAR))

    def _clear_hands(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    def _climbable_pole_available(self) -> bool:
        return any(p.kind == "vertical" for p in self.win.poles)

    def _pick_climbable_pole(self):
        best = None
        hx = self.body.chunk1.x
        for p in self.win.poles:
            if p.kind != "vertical":
                continue
            if best is None or abs(p.x - hx) < abs(best.x - hx):
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
        want_dismount = self.body.energy <= tuning.TIP_TIRED_ENERGY
        done = self.poleclimb.update(want_dismount)
        if done:
            ho = self.poleclimb.handoff
            if ho is not None:
                self._pole_release()
                self._pole_handoff(ho)
                return
            giveup = self.poleclimb.giveup
            on_floor = self.body.on_floor()
            self._pole_release()
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
        if self.poleclimb is not None:
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
        if self._hpole_goal_grab():      # 上杆来够的东西：够到就摘下来
            return
        done = self.hpole.update()
        if done:
            ho = self.hpole.handoff
            self._hpole_release()
            if ho is not None:
                self._pole_handoff(ho)
                return
            self._transition("IdleStand" if self.body.on_floor() else "Airborne")

    def _hpole_food_trip(self) -> bool:
        """地面/爬杆都够不到、但横杆杆面上够得到的食物：上杆去拿（原版 beam 上摘果）。

        返回 True=已切到 SeekHPole。
        """
        if self.state not in _WANTS_FROM or self._hp_goal_x is not None:
            return False
        if not any(p.kind == "horizontal" for p in self.win.poles):
            return False
        b = self.body
        best = None
        for f in self.win.fetchables():
            if getattr(f, "state", None) not in ("free", "hanging"):
                continue
            if not getattr(f, "fetch_ready", True):
                continue
            if getattr(f, "is_meat", False) and self.pers.diet in (DIET_VEGETARIAN, DIET_SPECIAL):
                continue
            g = None
            for p in self.win.poles:
                if p.kind != "horizontal" or not self._hpole_spans(p, x=f.x, r=tuning.HPOLE_GOAL_EPS):
                    continue
                if abs(f.y - p.ay) > tuning.HPOLE_GOAL_R:
                    continue
                g = p
                break
            if g is None:
                continue
            if self.planner.any_touch(obj_goal(f)):
                continue                    # 正常路就能拿，不必上杆
            d = abs(f.x - b.chunk1.x)
            if best is None or d < best[0]:
                best = (d, f)
        if best is None:
            return False
        f = best[1]
        self._hp_goal_x = f.x
        self._hp_goal_obj = f
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
        lz = self._nearest_lizard(tuning.FIGHT_ARM_R)
        if lz is None or lz.dead:
            return False
        self._aim_target(lz)
        return self._throw_weapon_at(lz)

    def _air_throw(self) -> None:
        """空中投矛：起跳/落地过程中手里有家伙且蜥蜴够近就掷（wiki Throwing midair）。"""
        b = self.body
        if self._air_throw_cd > 0:
            self._air_throw_cd -= 1
            return
        if (b.carried_spear is None and b.carried_stone is None) or self._exhausted:
            return
        lz = self._nearest_lizard(tuning.AIR_THROW_R)
        if lz is None or lz.dead or self._carrying_gift():
            return
        if self._throw_weapon_at(lz):
            self._air_throw_cd = tuning.AIR_THROW_CD

    def _hpole_goal_clear(self):
        self._hp_goal_x = None
        self._hp_goal_obj = None
        self._hp_jump_goal = None

    def _hpole_goal_grab(self) -> bool:
        """在杆上够到目标物就抓进手里（原版 beam 上伸手摘）。"""
        f = self._hp_goal_obj
        if f is None:
            return False
        st = getattr(f, "state", None)
        if st is not None and st not in ("free", "hanging"):
            self._hpole_goal_clear()
            return False
        c0 = self.body.chunk0
        side = "r" if f.x >= c0.x else "l"
        self.gfx.hand_aim[side] = (f.x, f.y)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if math.hypot(f.x - c0.x, f.y - c0.y) <= tuning.GRAB_REACH:
            self.body.grab_fruit(f, side)
            self._hpole_goal_clear()
            return False                 # 抓到就交回普通流程（杆上啃）
        if self._hpole_goal_jump(f):     # 手够不到但跳起来能碰到：起跳空中摘
            return True                  # 已离开 HPole，调用方要立刻收手
        if not self._hpole_reachable_now():
            self._hpole_goal_clear()
        return False

    def _hpole_goal_jump(self, f) -> bool:
        """站在横杆上跳起来能不能碰到目标：能就起跳（原版 beam 上跳抓）。"""
        from ..planning.jump_arc import get_arc, sweep_hit
        c0 = self.body.chunk0
        dx = f.x - c0.x
        if abs(dx) > tuning.HPOLE_JUMP_GRAB:
            return False                      # 水平差太远：先在杆上走过去
        stats = getattr(self.win.cat, "stats", None)
        if stats is None:
            return False
        dy = f.y - c0.y
        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            if sweep_hit(get_arc(stats, hold, 0), dx, dy, tuning.GRAB_REACH) is None:
                continue
            self._hpole_release()          # 先收杆（会清 _hp_goal_*），再记空中目标
            self._hp_jump_goal = f
            self.body.tip_launch(hold_ticks=hold, move_dir=0)
            self._transition("Airborne")
            return True
        return False

    def _hp_jump_grab(self) -> None:
        """空中伸手摘杆上跳起来够的东西。"""
        f = self._hp_jump_goal
        if f is None:
            return
        if getattr(f, "state", None) not in ("free", "hanging"):
            self._hp_jump_goal = None
            return
        c0 = self.body.chunk0
        side = "r" if f.x >= c0.x else "l"
        self.gfx.hand_aim[side] = (f.x, f.y)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if math.hypot(f.x - c0.x, f.y - c0.y) <= tuning.GRAB_REACH:
            self.body.grab_fruit(f, side)
            self._hp_jump_goal = None

    def _hpole_reachable_now(self) -> bool:
        """目标是否仍在那条横杆线上。"""
        h = getattr(self, "hpole", None)
        p = h.pole if h is not None else None
        if p is None:
            return False
        return self._hpole_spans(p, x=self._hp_goal_obj.x)

    def _hpole_release(self):
        self._hpole_goal_clear()
        self._pole_nudge_pin = None
        self._pole_nudge = 0
        self._pole_nudge_point = False
        self._pole_blocker = None
        if self.hpole is not None:
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

    def _fetch_enter(self):
        from .fetch import FruitFetcher
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self.fetch = FruitFetcher(self.win, self.planner, diet=self.pers.diet)

    def _st_fetchfruit(self, cursor, disturbed):
        if self.grab.active:
            self._break_tongue()
            self._fetch_release()
            self._transition("Dragged")
            return
        if self.fetch is None:
            self._transition("IdleStand")
            return
        done = self.fetch.update()
        if self.fetch.giveup:
            self._break_tongue()
            self._fetch_release()
            self._fetch_cooldown = T_FETCH_COOLDOWN
            self._transition("IdleStand")
        elif done:
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
            self._hunt_cd = HUNT_CD
            self._transition("IdleStand")
        elif status == "revert_wander":
            self._flyhunt_release()
            self._hunt_cd = HUNT_CD
            self._transition("PostThrowWander")

    def _flyhunt_release(self):
        """收尾：松手、清瞄准、清控制器。"""
        for o in (self.body.carried_spear, self.body.carried_stone):
            if o is not None and o.state == "carried":
                o.state = "free"
        if self.body.carried_spear is not None:
            self.body.release_spear(to_free=True)
        if self.body.carried_stone is not None:
            self.body.release_stone(to_free=True)
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

    def _wall_side_now(self) -> int:
        s = edgeqm.on_wall(self.body, self.WL, tuning.WALL_SEEK_R)
        if s:
            return s
        return -1 if self.body.chunk1.x < self.WL * 0.5 else 1

    def _ceiling_reachable(self) -> bool:
        c0 = self.body.chunk0
        return edgeqm.on_ceiling(self.body) or (c0.y - c0.rad <= tuning.CEIL_GRAB_REACH)

    def _can_ceil_cling(self) -> bool:
        """屏幕顶端能否攀附：只有圣徒的舌头（原版普通蛞蝓猫吊不住天花板）。"""
        return bool(self.win.cat.caps.tongue)

    def _peer_near(self) -> bool:
        c1 = self.body.chunk1
        for p in self._living_peers():
            ob = p.body
            if math.hypot(ob.chunk1.x - c1.x, ob.chunk1.y - c1.y) <= tuning.SOCIAL_R:
                return True
        return False

    def _cursor_close(self) -> bool:
        cur = self.cursor
        if cur is None:
            return False
        c0 = self.body.chunk0
        return math.hypot(cur[0] - c0.x, cur[1] - c0.y) <= tuning.PLAYCUR_R

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
        lz = self._nearest_lizard(tuning.FIGHT_R)
        if lz is None:
            return 0.0
        c1 = self.body.chunk1
        return clampf(1.0 - math.hypot(lz.x - c1.x, lz.y - c1.y) / tuning.FIGHT_R, 0.0, 1.0)

    def _nearest_peer(self):
        best, bd = None, 1e9
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

    def _dead_peer_near(self):
        """附近倒地的同伴（死了就去扒拉救活）。"""
        best, bd = None, tuning.HELPFEED_SEEK_R
        c1 = self.body.chunk1
        for p in self._peers():
            ob = p.body
            if not ob.dead:
                continue
            d = math.hypot(ob.chunk1.x - c1.x, ob.chunk1.y - c1.y)
            if d < bd:
                best, bd = p, d
        return best

    def _nearest_free_food(self):
        best, bd = None, tuning.HELPFEED_SEEK_R
        c1 = self.body.chunk1
        for f in self.win.fetchables():
            if getattr(f, "state", None) != ItemState.FREE:
                continue
            if getattr(f, "bites", 0) <= 0:      # 珍珠这类不是食物
                continue
            d = math.hypot(f.x - c1.x, f.y - c1.y)
            if d < bd:
                best, bd = f, d
        return best

    def _weapon_ready(self) -> bool:
        """手里拿着家伙，或脚边地上有能马上捡起来的。"""
        b = self.body
        if b.carried_spear is not None or b.carried_stone is not None:
            return True
        w = self._nearest_ground_weapon()
        if w is None:
            return False
        return math.hypot(w.x - b.chunk1.x, w.y - b.chunk1.y) < tuning.FIGHT_ARM_R

    def _nearest_ground_weapon(self):
        """地上能捡的石头/矛（原版捡起投掷物）。"""
        best, bd = None, 260.0
        c1 = self.body.chunk1
        for s in self.win.stones:
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
            if getattr(s, "pinned", False):      # 钉成杆的矛：拔不动也捡不走
                continue
            if not (getattr(s, "stuck", False) or (abs(s.vx) < 0.4 and abs(s.vy) < 0.4)):
                continue
            d = math.hypot(s.x - c1.x, s.y - c1.y)
            if d < bd:
                best, bd = s, d
        return best

    # ── 每 tick 的强制欲望仲裁 ──
    def _wants_tick(self, cursor):
        """社交/帮助/反击/匍匐躲避在「没正事」的态里按优先级抢班。"""
        for k in ("_social_cd", "_help_cd", "_fight_cd", "_crawl_cd",
                  "_protest_cd", "_revive_cd", "_wall_cd", "_scold_cd",
                  "_pole_nudge_cd"):
            v = getattr(self, k)
            if v > 0:
                setattr(self, k, v - 1)
        self._watch_fetch_steal()
        if self.grab.active or self._exhausted or self._zerog():
            return
        if self.state not in _WANTS_FROM:
            return
        b = self.body
        # 1) 倒地的同伴：过去用特殊表情扒拉救活
        if self._revive_cd <= 0 and not b.swimming:
            dp = self._dead_peer_near()
            if dp is not None:
                self._social_kind = "revive"
                self._social_target = dp
                self._social_left = tuning.REVIVE_APPROACH_TICKS
                self._break_active_controllers()
                self._transition("Socialize")
                return
        # 2) 自己饱了、别的猫没饱 → 帮它取食送过去
        if (self._help_cd <= 0 and b.food >= b.food_max
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
            if th.body.dead:
                self._protest_target = None
            else:
                self._start_protest(th)
                return
        # 4) 反击：被咬/被砸后（anger>0）仇人还在附近
        #    手里/脚边有家伙时也会主动迎战（原版持械的猫）
        if self._fight_cd <= 0:
            ranged = self.anger > 0
            lz = self._nearest_lizard(tuning.FIGHT_R if ranged else tuning.FIGHT_ARM_R)
            if lz is not None and (ranged or self._weapon_ready()):
                self._fight_target = lz
                self._fight_left = tuning.FIGHT_TICKS
                self._break_active_controllers()
                self._transition("FightThreat")
                return
        # 5) 恐惧：蜥蜴靠近 → 在它背后就趴下潜行挪开；打了照面直接跑
        if self._crawl_cd <= 0 and not b.swimming and b.on_floor():
            lz = self._nearest_lizard(tuning.CRAWL_FEAR_R)
            if lz is not None and not self._carrying_gift():
                behind = self._behind_creature(lz)
                # 性格：crawl_like 低的猫宁可拔腿就跑，不肯趴下
                can_crawl = (self.rng.random()
                             < 0.25 + 0.75 * getattr(self.pers, "crawl_like", 0.5))
                if (behind or abs(lz.x - b.chunk1.x) > tuning.CRAWL_FEAR_R * 0.6) and can_crawl:
                    self._crawl_from = lz
                    self._crawl_point_to = None
                    self._crawl_left = tuning.CRAWL_AWAY_TICKS
                    self._break_active_controllers()
                    self._transition("CrawlAway")
                    return
                self._flee_from = lz
                self._crawl_cd = T_CRAWL_RETRY
                self._break_active_controllers()
                self._transition("FleeLizard")
                return

    def _pick_social_kind(self, tgt):
        """社交欲望攒满 → 按性格从动作词表（behavior/social.py）里加权抽一个动作。"""
        pers = self.pers
        soc = getattr(pers, "sociability", 0.5)
        pl = getattr(pers, "point_like", 0.5)
        cl = getattr(pers, "crawl_like", 0.5)
        opts = [
            ("pet", tuning.PET_BASE * (0.4 + 1.2 * soc)),      # 抚摸：喜欢/安抚
            ("pat", tuning.PAT_BASE * (0.4 + 1.2 * soc)),      # 拍拍：喜欢/安抚
            ("point", tuning.POINTHOLD_BASE),                  # 指向：想要/注意
            ("scold", tuning.SOCIAL_SCOLD_BASE * (0.3 + 1.4 * pl)),   # 指指点点
        ]
        if cl > 0.25:
            # 匍匐族：不肯趴的猫（crawl_like 低）不抽
            opts.append(("crouch", tuning.CROUCH_SOC_BASE * (0.3 + 1.4 * cl)))
            opts.append(("crouch_point", tuning.CROUCH_POINT_BASE * (0.3 + 1.4 * cl)))
            opts.append(("crouch_scold",
                         tuning.CROUCH_SCOLD_BASE * (0.3 + 1.4 * cl) * (0.4 + 1.2 * pl)))
            if self._nearest_lizard(tuning.CRAWL_FEAR_R * 1.6) is not None:
                opts.append(("crouch_walk", tuning.CROUCH_WALK_BASE * (0.3 + 1.4 * cl)))
        if self.anger > 0 or self._protest_target is tgt:
            # 记恨的对象：匍匐指指点点（仇恨/预备攻击）加权
            opts.append(("crouch_scold", tuning.CROUCH_SCOLD_BASE * 1.5))
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

    def _start_protest(self, thief):
        """被抢东西 → 过去扒拉指指点点。"""
        self._social_kind = "protest"
        self._social_target = thief
        self._social_left = tuning.PROTEST_TICKS
        self._break_active_controllers()
        self._transition("Socialize")

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
        thief = None
        for p in self._living_peers():
            if p.body.carried_fruit is f:
                thief = p
                break
        if thief is None:
            thief = self._nearest_peer()
        if thief is not None:
            self._protest_target = thief
            if self.state in _WANTS_FROM and self._protest_cd <= 0:
                self._start_protest(thief)

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
        full = (self.body.food >= self.body.food_max
                and not self._too_cold_to_sleep() and not self._hibernating)
        if full:
            self._sleep_urge = min(1.0, self._sleep_urge + tuning.SLEEP_URGE_RATE)
        else:
            self._sleep_urge = max(0.0, self._sleep_urge - tuning.SLEEP_URGE_DECAY)

    def _sleep_roll(self) -> bool:
        """每隔 SLEEP_CHECK_TICKS 掷一次骰，概率 = 当前睡意。"""
        if self.body.food < self.body.food_max or self._sleep_urge <= 0.0:
            return False
        self._sleep_check = (self._sleep_check + 1) % tuning.SLEEP_CHECK_TICKS
        if self._sleep_check:
            return False
        # 睡意即概率：平方后刚吃饱几乎不睡、攒满必睡（避免吃饱几秒就倒头睡）
        return self.rng.random() < self._sleep_urge * self._sleep_urge

    # ── 被同伴救：特殊表情扒拉一会儿就复活 ──
    def nuzzle(self, ticks: int = 1) -> bool:
        if self.state != "Dead" or self._reincarnate:
            return False
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
        self._point_end()
        self.gfx.face_special = False
        self.body.set_crawl(False)          # 匍匐类社交动作收势：站起来
        self._social_gesture = None
        self._social_press_seen = 0
        self._social_urge = 0.0             # 社交欲望：做完归 0，重新慢慢攒
        if self._social_kind == "revive":
            self._revive_cd = T_REVIVE_RETRY
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
        if st == "WallClimb":
            b.release_wall()
            self._wall_cd = T_WALL_RETRY
        elif st == "CeilingHang":
            b.release_ceiling()
        elif st == "CrawlAway":
            b.set_crawl(False)
            self._crawl_point_to = None
        elif st == "ScoldBlocker":
            self._scold_cleanup()
        elif st == "Socialize":
            self._social_cleanup()
        elif st == "HelpFeed":
            self._help_cd = T_HELP_RETRY
            self._help_target = None
            self.gfx.face_special = False
        elif st == "FightThreat":
            self._fight_cd = T_FIGHT_RETRY
            self._fight_target = None
        elif st == "ChaseCursor":
            self._clear_hands()
        elif st == "EatCob":
            self.gfx.hand_aim["l"] = None
            self.gfx.hand_aim["r"] = None
            self.body.eat_raise = 0.0
            self._cob = None
            self._cob_eat_t = 0
            self._cob_seek_cd = T_COB_RETRY
        elif st == "CatchFly":
            self._flycatch_release()
        elif st == "ItemPlay":
            self._itemplay_end()
        self._restore_walk_limits()

    # ── 爬墙：窗口左右边缘＝墙（原版 ClimbOnBeam 位姿）──
    def _wall_enter(self):
        b = self.body
        self._wall_goal = self._wall_side_now()
        self._wall_left = self.rng.randint(tuning.WALL_CLIMB_TICKS_MIN,
                                           tuning.WALL_CLIMB_TICKS_MAX)
        self._wall_ready = False
        self._wall_top_y = self._roll_wall_top(b)
        # tick 预算得够爬到这面墙的上沿（上沿才是硬上限，这里的上限只是防呆）
        need = int(max(0.0, b.chunk0.y - self._wall_top_y) / max(0.1, WALL_CLIMB_SPEED)) + 60
        self._wall_left = max(self._wall_left, need)
        self._wall_ledge_t = 0
        self._wall_sliding = False
        self._save_walk_limits()
        b.set_posture(True)
        b.stop_walk()
        b.release_ceiling()

    def _roll_wall_top(self, b):
        """这面墙的可攀爬上沿 y：最高只到「一只蹬辜猫的高度」（力竭更短）。"""
        frac = tuning.WALL_TOP_TIRED_FRAC + (1.0 - tuning.WALL_TOP_TIRED_FRAC) * b.energy
        top = b.chunk0.y - tuning.WALL_CLIMB_MAX_H * frac
        return max(tuning.WALL_TOP_GRAB_R + 4.0, top)

    def _wall_ledge(self, cursor):
        """够到墙头上沿：抓沿悬一下（原版 LedgeGrab），再蹬墙跳或贴墙缓慢滑下。"""
        b = self.body
        self.gfx.look_at = cursor if cursor is not None else (b.chunk0.x, b.chunk0.y - 30.0)
        if self._wall_sliding:                          # 已决定下滑：贴墙缓降到地
            b.wall_climb_dir = 1
            b.wall_slide = True
            if b.on_floor():
                b.release_wall()
                self._wall_cd = T_WALL_RETRY
                self._transition("IdleStand")
            return
        b.wall_climb_dir = 0
        self._wall_ledge_t += 1
        if self._wall_ledge_t < tuning.WALL_LEDGE_HOLD:
            return
        if self.rng.random() < tuning.WALL_LEDGE_JUMP_PROB:
            b.release_wall()
            self._wall_cd = T_WALL_RETRY
            b.wall_jump(up=True)                        # 蹬墙跳离开这面墙
            self._transition("Airborne")
            return
        self._wall_sliding = True                       # 抓不住：缓慢滑下
        b.wall_climb_dir = 1
        b.wall_slide = True

    def _st_wallclimb(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._wants_break("WallClimb")
            self._transition("Dragged")
            return
        if not self._wall_ready:
            tx = edgeqm.wall_hold_x(self._wall_goal, self.WL)
            if abs(b.chunk1.x - tx) > 6.0:
                b.move_dir = 1 if tx > b.chunk1.x else -1
                b.facing = b.move_dir
                return
            b.move_dir = 0
            self._wall_ready = b.grab_wall(self._wall_goal, self._wall_top_y)
            self.timer = 0
            return
        self._wall_left -= 1
        c0 = b.chunk0
        if self._wall_sliding or b.at_wall_top or (c0.y - c0.rad) <= self._wall_top_y + 0.5:
            if self._wall_top_y <= tuning.WALL_TOP_GRAB_R:  # 这面墙直通顶边
                b.release_wall()
                if self._can_ceil_cling():                  # 圣徒的舌头才能上去吊顶
                    self._transition("CeilingHang")
                else:                                       # 普通猫：顶上没得抓，蹬墙跳开
                    self._wall_cd = T_WALL_RETRY
                    b.wall_jump()
                    self._transition("Airborne")
                return
            self._wall_ledge(cursor)                        # 够到墙头：抓沿
            return
        b.wall_climb_dir = -1                              # 向上爬
        self.gfx.look_at = (c0.x, c0.y - 40.0)
        if self.rng.random() < tuning.WALL_WALLJUMP_PROB * 0.5:   # 蹬墙跳
            b.wall_jump()
            self._transition("Airborne")
            return
        if self._wall_left <= 0:
            b.release_wall()
            self._wall_cd = T_WALL_RETRY
            self._transition("Airborne")

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

    # ── 玩耍：追光标 / 试着抓鼠标 ──
    def _play_enter(self):
        self._play_left = self.rng.randint(tuning.PLAYCUR_TICKS_MIN,
                                           tuning.PLAYCUR_TICKS_MAX)
        self.body.set_posture(True)

    def _st_chasecursor(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            self._clear_hands()
            self._transition("Dragged")
            return
        self._play_left -= 1
        if cursor is None:
            self._clear_hands()
            self._transition("IdleStand")
            return
        cx, cy = cursor
        self.gfx.look_at = cursor
        d = math.hypot(cx - b.chunk0.x, cy - b.chunk0.y)
        if d > tuning.PLAYCUR_ARRIVE:
            b.walk_to(cx)
            self._point_end()
        else:
            b.stop_walk()
            if not self._point_active() and self._cursor_point_ok():
                self._point_begin(cursor, mode="cursor")   # 指着鼠标，一下一下
            self._point_step()
            # 鼠标落在跳跃够得到的一层：有概率跳起来拿身子碰它（原版跳抓）
            if (b.on_floor() and self.timer % JUMPCUR_CD == 0
                    and abs(cy - b.chunk0.y) <= JUMPCUR_DY and d <= JUMPCUR_R
                    and self.rng.random() < JUMPCUR_P):
                b.request_jump("protest")
        if self._play_left <= 0 or d > tuning.PLAYCUR_R * 1.6:
            self._point_end()
            self._transition("IdleStand")

    # ── 社交：靠近/抚摸同伴 · 扒拉指指点点 · 救同伴 ──
    def _social_enter(self):
        b = self.body
        kind = self._social_kind
        if kind == "revive":
            self._social_left = tuning.REVIVE_APPROACH_TICKS
        elif kind == "protest":
            self._social_left = tuning.PROTEST_TICKS
            b.drop_all()             # 丢掉手上的东西，腾出手来扒拉
        else:
            self._social_left = self.rng.randint(tuning.SOCIAL_TICKS_MIN,
                                                 tuning.SOCIAL_TICKS_MAX)
        self._social_touch = 0
        self._social_gesture = None      # 本次动作的手势（抚摸/拍拍/复活）
        self._social_press_seen = 0
        if social.is_crouch(kind):       # 匍匐族：趴着做完整段
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
        if tgt is None or getattr(tgt, "body", None) is None:
            self._end_social()
            return
        ob = tgt.body
        kind = social.ALIASES.get(self._social_kind, self._social_kind)
        if social.is_crouch(kind):
            b.set_crawl(True)              # 匍匐族：整段都趴着
        self._social_left -= 1
        d = math.hypot(ob.chunk1.x - b.chunk1.x, ob.chunk1.y - b.chunk1.y)
        if kind == "revive":
            # 必须贴进按压半径（量的是最近 chunk 对），否则永远救不活
            d = self._touch_dist(ob)
        if d > tuning.SOCIAL_ARRIVE:
            b.walk_to(ob.chunk1.x)
            self.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
            self._clear_hands()
        else:
            b.stop_walk()
            b.facing = 1 if ob.chunk0.x >= b.chunk0.x else -1
            self.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
            self._social_act(kind, tgt, ob)
        if self._social_left <= 0:
            self._end_social()

    def _social_act(self, kind, tgt, ob):
        """到位后照动作词表（behavior/social.py）演对应的手势。"""
        if kind == "revive":
            self._social_revive(tgt, ob)
        elif kind == "pet":
            self._social_stroke(tgt, ob, True)      # 抚摸：横线
        elif kind == "pat":
            self._social_stroke(tgt, ob, False)     # 拍拍：竖线
        elif kind in ("point", "crouch_point"):
            # 指向：手举着不放（不上表情），就是「看这个 / 我想要这个」
            self.gfx.face_special = False
            if not self._aim_target(tgt):
                self._end_social()
        elif kind == "crouch":
            # 匍匐：就趴着什么也不做（让路 / 抱歉 / 害怕）
            self.gfx.face_special = False
            self._clear_hands()
        else:
            # 指指点点 / 匍匐指指点点：伸-收快速 1~5 下，指完一轮再来一轮
            if self.timer % tuning.SOCIAL_POKE_INTERVAL == 0:
                self._poke(ob)
            if self._point_step():
                self._point_begin(tgt)

    def _social_stroke(self, tgt, ob, horizontal):
        """抚摸（横线）/ 拍拍（竖线）：手贴着对象来回画 2~5 次。"""
        g = self._social_gesture
        if g is None or g.done:
            n = self.rng.randint(tuning.PET_REPS_MIN, tuning.PET_REPS_MAX)
            self._social_gesture = g = (
                social.StrokeGesture(n, tuning.PET_ON_TICKS, "h", tuning.PET_SPAN)
                if horizontal else
                social.StrokeGesture(n, tuning.PAT_ON_TICKS, "v", tuning.PAT_SPAN))
        self.gfx.face_special = True
        ox, oy = g.offset()
        side = "r" if ob.chunk0.x >= self.body.chunk0.x else "l"
        self.gfx.hand_aim[side] = (ob.chunk0.x + ox, ob.chunk0.y + oy)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if g.step():
            self._soothe(ob)                        # 画完一轮：双方都平复一点

    def _social_revive(self, tgt, ob):
        """复活：伸手按在同伴身上用力下按 4~8 下（身体跟着压），按完同伴复活。"""
        beh = getattr(tgt, "behavior", None)
        if beh is None:
            self._end_social()
            return
        g = self._social_gesture
        if g is None:
            reps = self.rng.randint(tuning.REVIVE_PRESS_MIN, tuning.REVIVE_PRESS_MAX)
            self._social_gesture = g = social.PressGesture(
                reps, tuning.REVIVE_PRESS_TICKS, tuning.REVIVE_RELEASE_TICKS)
            self._social_press_per = max(1, tuning.REVIVE_TOUCH_TICKS // reps)
        self.gfx.face_special = True
        self._point_at_peer(tgt)                    # 伸手按住同伴
        if self._touch_dist(ob) > tuning.REVIVE_TOUCH_R:
            return                                  # 够不着：先把身子挪过去
        if g.pressing:                              # 身体跟着用力向下
            self.body.chunk0.vy += tuning.REVIVE_PRESS_DOWN
            self.body.chunk1.vy += tuning.REVIVE_PRESS_DOWN * 0.6
        if self._social_press_seen < g.presses_done:
            self._social_press_seen = g.presses_done
            self._poke(ob)                          # 把同伴按下去
            beh.nuzzle(self._social_press_per)
            self.body.temper_shift(tuning.TEMPER_FEED * 0.5)
        if g.step():
            beh.nuzzle(tuning.REVIVE_TOUCH_TICKS)   # 按完就复活
            self.body.temper_shift(tuning.TEMPER_FEED)
            self._end_social()

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
        """【指指点点】指一下（单帧）：手臂指向目标并换上特殊表情。"""
        self.gfx.face_special = True
        return self._aim_target(peer)

    # ── 指指点点手势：伸出 → 收回 → 再伸出，重复 3~5 下 ──
    def _point_begin(self, tgt, mode="obj", enforce_side=False, reps=None):
        if reps is None:
            reps = self.rng.randint(tuning.POINT_REPS_MIN, tuning.POINT_REPS_MAX)
            # 性格：爱指的猫指得久，性格好的猫敷衍两下就收
            if self.rng.random() > getattr(self.pers, "point_like", 0.5):
                reps = max(1, reps - 2)
        self._point = PointGesture(reps, tuning.POINT_ON_TICKS, tuning.POINT_OFF_TICKS)
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
        self.gfx.face_special = False        # 指指点点收势：表情一并收掉
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
                self._point_at_cursor(self._point_tgt, enforce_side=self._point_enforce,
                                      cover=True)
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
        self.gfx.face_special = False
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
                or tgt.body.food >= tgt.body.food_max):
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
            side = "r" if f.x >= b.chunk0.x else "l"
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
        self.gfx.face_special = True
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
        self.body.set_posture(True)
        self.body.stop_walk()

    def _cob_end(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self.body.eat_raise = 0.0
        self.body.stop_walk()
        self._cob = None
        self._cob_eat_t = 0
        self._cob_seek_cd = T_COB_RETRY
        self._transition("IdleStand")

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
            if self._cob_fetch_spear() and self._cob_left > 0:
                return                       # 正在去捡矛
            self._cob_end()
            return
        if d > tuning.COB_SPEAR_R:
            b.walk_to(px)                    # 先走进射程
            if self._cob_left <= 0:
                self._cob_end()
            return
        b.stop_walk()
        b.facing = 1 if px >= b.chunk0.x else -1
        if self._cob_left <= 0 or self._throw_weapon_at(cb):
            self._cob_end()

    # ── 战斗：反击（投石/投矛）──
    def _fight_enter(self):
        self._fight_left = tuning.FIGHT_TICKS
        self._fight_throw_t = 0
        self.body.set_posture(True)
        self.body.stop_walk()

    def _fight_end(self):
        self._point_end()
        self.gfx.face_special = False
        self._fight_cd = T_FIGHT_RETRY
        self._fight_target = None
        self.body.stop_walk()
        self._transition("IdleStand")

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
        if b.carried_spear is None and b.carried_stone is None:
            o = self._nearest_ground_weapon()
            if o is not None:
                od = math.hypot(o.x - b.chunk1.x, o.y - b.chunk1.y)
                if od > 60.0:
                    b.walk_to(o.x)
                    return
                b.stop_walk()
                side = "r" if o.x >= b.chunk0.x else "l"
                b.reach_for(o, side)
                if math.hypot(o.x - b.chunk0.x, o.y - b.chunk0.y) <= tuning.GRAB_REACH + b.arm_full_reach:
                    from ..world.spear import Spear
                    if isinstance(o, Spear):
                        b.grab_spear(o, side)
                    else:
                        b.grab_stone(o, side)
                    self._fight_throw_t = tuning.FIGHT_THROW_CD
                return
            # 空手：贴上去拍打指指点点（原版空手打不动蜥蜴）
            if self.anger <= 0:           # 主动迎战但家伙没了：退回躲避
                self._fight_end()
                return
            if d > tuning.FIGHT_MELEE_R:
                b.walk_to(tgt.x)
                self._point_end()
            else:
                b.stop_walk()
                if self._point_step():          # 空手：扒拉着指指点点
                    self._point_begin(tgt)
                if self.timer % tuning.SOCIAL_POKE_INTERVAL == 0:
                    tgt.vx += 0.35 if tgt.x >= b.chunk0.x else -0.35
            return
        # 持械：持续瞄着目标（指向），到点就按原版水平掷出
        self._fight_throw_t += 1
        if d < tuning.FIGHT_ARM_KEEP:                # 太近会被咬：边打边拉开
            b.walk_to(b.chunk1.x - (tgt.x - b.chunk1.x))
        else:
            b.stop_walk()
        self._point_end()
        self._aim_target(tgt)
        if self._fight_throw_t >= tuning.FIGHT_THROW_CD:
            self._fight_throw_t = 0
            self._throw_weapon_at(tgt)

    def _throw_weapon_at(self, tgt) -> bool:
        """原版水平投掷：throwDir = IntVector2(sign(x), 0)，初速走 Weapon.Thrown（40*frc）。

        对照反编译 Weapon.cs:463-502：玩家只有水平分支；Spear.Update 里
        setRotation = throwDir、rotationSpeed = 0 ⇒ 矛头始终顺着飞行方向，不翻滚。
        目标偏高时先起跳对齐高度（跳着发射，原版也是这么打空中猎物的）。
        """
        b = self.body
        c0 = b.chunk0
        spear = b.carried_spear
        if tgt is None:
            return False
        dx = tgt.x - c0.x
        dy = tgt.y - c0.y                       # y↓：<0 目标在上方
        if abs(dy) > THROW_JUMP_DY and b.on_floor():
            b.request_jump("stand")             # 站在地上：跳到那一层再水平掷出
            return False                        # 已经在空中就直接掷（原版空中投矛）
        dir_x = 1 if dx >= 0.0 else -1
        weak, toss = weaponphys.player_throw_mode(
            getattr(self.win, "variant", ""), self._exhausted,
            spear is not None, False)
        if spear is not None:
            b.throw_spear(dir_x, weaponphys.frc(weak=weak),
                          recoil=0.4, toss=toss)
        else:
            b.throw_stone(dir_x, weaponphys.frc(weak=weak),
                          fling=True, recoil=0.4)
        b.chunk0.vx -= dir_x * 0.35
        self.gfx.blink = 15
        return True

    # ── 恐惧：匍匐潜行挪开 ──
    def _behind_creature(self, c) -> bool:
        """我是否在对方背后（对方的头朝着另一侧 → 看不见我）。"""
        facing = getattr(c, "facing", 0) or 0
        if not facing:
            return True                  # 没有朝向信息：当背后处理（悄悄匍匐）
        return (self.body.chunk1.x - c.x) * facing < 0.0

    def be_pointed_at(self, pointer):
        """被别的猫指指点点：有概率转过身来对着它匍匐（缩起来）。"""
        b = self.body
        if (getattr(b, "dead", False) or self.grab.active or self._zerog()
                or b.swimming or not b.on_floor() or self._crawl_cd > 0
                or self.state not in _WANTS_FROM):
            return
        pb = getattr(pointer, "body", None)
        prob = tuning.POINTED_CROUCH_PROB * (0.4 + 1.2 * getattr(self.pers, "crawl_like", 0.5))
        if pb is None or self.rng.random() >= prob:
            return
        self._crawl_point_to = pointer
        self._crawl_from = None
        self._crawl_left = tuning.POINTED_CROUCH_TICKS
        self._crawl_cd = T_CRAWL_RETRY
        self._break_active_controllers()
        self._transition("CrawlAway")

    def _crawl_enter(self):
        b = self.body
        if self._crawl_point_to is None or self._crawl_left <= 0:
            self._crawl_left = tuning.CRAWL_AWAY_TICKS
        b.set_posture(False)
        b.set_crawl(True)

    def _st_crawlaway(self, cursor, disturbed):
        b = self.body
        if self.grab.active:
            b.set_crawl(False)
            self._crawl_point_to = None
            self._transition("Dragged")
            return
        # 被指指点点：原地面对发起者蹲着（不挪窝）
        pt = self._crawl_point_to
        if pt is not None:
            pb = getattr(pt, "body", None)
            self._crawl_left -= 1
            if pb is None or getattr(pb, "dead", False) or self._crawl_left <= 0:
                self._crawl_point_to = None
                b.set_crawl(False)
                self._crawl_cd = T_CRAWL_RETRY
                self._transition("IdleStand")
                return
            b.set_crawl(True)
            b.stop_walk()
            b.facing = 1 if pb.chunk0.x >= b.chunk0.x else -1
            self.gfx.look_at = (pb.chunk0.x, pb.chunk0.y)
            self.gfx.face_special = True
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
        b.move_dir = -1 if lz.x >= b.chunk1.x else 1
        b.facing = b.move_dir
        self.gfx.look_at = (lz.x, lz.y)


    # ── 觅食欲望：吃完一口归 0，再慢慢涨回 1（饱了也涨，只是更慢）──
    def _food_urge_tick(self):
        rate = (tuning.FOOD_URGE_RATE_FULL if self.body.food >= self.body.food_max
                else tuning.FOOD_URGE_RATE)
        self._food_urge = min(1.0, self._food_urge + rate)

    # ── 社交欲望（第六类）：攒满才想找同伴做社交动作 ──
    def _social_urge_tick(self):
        self._social_urge = min(1.0, self._social_urge + tuning.SOCIAL_URGE_RATE)

    def _food_seek_ready(self) -> bool:
        """觅食闸：攒满 100 再掷一次骰，整体找食频率略降。"""
        return self._food_urge >= 1.0 and self.rng.random() < tuning.FOOD_SEEK_P

    # ── 代谢：体力消耗累计满一条 → 扣一格饱食 ──
    def _metabolism(self, before: float):
        e = self.body.energy
        if e < before:
            self._drain_acc += before - e
        while self._drain_acc >= 1.0:
            self._drain_acc -= 1.0
            self.body.food_eat(-tuning.METAB_FOOD_PER_BAR)

    # ── 叼着活的蝉乌贼：扑翅带起一点，下落被拖住 ──
    def _squid_lift_tick(self):
        f = self.body.carried_fruit
        if f is None or not getattr(f, "is_tame_food", False) or getattr(f, "dead", True):
            return
        c0 = self.body.chunk0
        if c0.vy > -tuning.SQUID_LIFT_MAX:
            c0.vy -= tuning.SQUID_LIFT
        c0.vx *= tuning.SQUID_DRAG

    # ── 徒手抓飞虫（蝙蝠/蝉乌贼）──
    def _nearest_catchable(self):
        """半径内可徒手抓的飞虫（含飞行中）。"""
        if self.pers.diet in (DIET_VEGETARIAN, DIET_SPECIAL):
            return None
        c0 = self.body.chunk0
        best, bd = None, tuning.CATCH_SEEK_R
        for f in (*self.win.batflies, *self.win.squidcadas):
            if not getattr(f, "catchable", False):
                continue
            d = math.hypot(f.x - c0.x, f.y - c0.y)
            if d < bd:
                best, bd = f, d
        return best

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
        if (self.state != "IdleStand" or self.grab.active or self._hibernating
                or b.swimming or self._zerog()):
            return
        c0 = b.chunk0
        best, bd = None, 30.0
        for sp in self.win.spears:
            if sp.state != "free" or sp.stuck_to is not None:
                continue
            if getattr(sp, "pinned", False):      # 钉成杆的矛：拔不动也捡不走
                continue
            if not (sp.stuck or (abs(sp.vx) < 0.4 and abs(sp.vy) < 0.4)):
                continue
            d = math.hypot(sp.x - c0.x, sp.y - c0.y)
            if d < bd:
                best, bd = sp, d
        if best is None:
            self._back_spear_cd = 120
            return
        b.put_spear_on_back(best)
        self.gfx.blink = 12

    # ── 平时把玩地上的小物件（矛/石头）──
    def _nearest_play_item(self):
        """挑一样地上的家伙玩；挑哪样看性格（暴躁爱矛，温顺爱石）。"""
        b = self.body
        if b.carried_spear is not None or b.carried_stone is not None:
            return None
        from ..world.spear import Spear
        c0 = b.chunk0
        cands = []
        for o in self.win.stones:
            if o.state != "free" or getattr(o, "unfetchable", False):
                continue
            if not o.at_rest_on_ground(self.HL):
                continue
            cands.append((o, math.hypot(o.x - c0.x, o.y - c0.y)))
        for sp in self.win.spears:
            if sp.state != "free" or sp.stuck_to is not None:
                continue
            if getattr(sp, "pinned", False):      # 钉成杆的矛：拔不动也捡不走
                continue
            if not (sp.stuck or (abs(sp.vx) < 0.4 and abs(sp.vy) < 0.4)):
                continue
            cands.append((sp, math.hypot(sp.x - c0.x, sp.y - c0.y)))
        cands = [c for c in cands if c[1] < tuning.ITEMPLY_SEEK_R]
        if not cands:
            return None
        temper = getattr(self.pers, "temper", 0.5)
        pref = getattr(self.pers, "toy_pref", {})

        def score(c):
            o, d = c
            spear = isinstance(o, Spear)
            w = pref.get("spear_play" if spear else "stone_play", 1.0)
            w *= 1.0 + (temper - 0.5) * (0.8 if spear else -0.8)
            return d / max(0.05, w)
        return min(cands, key=score)[0]

    def _itemplay_enter(self):
        b = self.body
        b.set_posture(True)
        b.stop_walk()
        self._itemplay_phase = 0
        self._itemplay_left = 0
        it = self._itemplay_target
        self._itemplay_side = "r" if (it is not None and it.x >= b.chunk0.x) else "l"

    def _itemplay_fling(self):
        """玩够了顺手甩出去（暴躁的猫）：走原版水平投掷，石头能砸晕同伴。"""
        b = self.body
        dir_x = 1 if b.facing >= 0 else -1
        if b.carried_spear is not None:
            b.throw_spear(dir_x, weaponphys.frc(weak=self._exhausted), recoil=0.3)
        elif b.carried_stone is not None:
            b.throw_stone(dir_x, weaponphys.frc(weak=self._exhausted),
                          fling=True, recoil=0.3)
        self.gfx.blink = 15

    def _itemplay_end(self):
        b = self.body
        if b.carried_stone is not None:
            b.release_stone(to_free=True)
        if b.carried_spear is not None:
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
        self._itemplay_cd = tuning.ITEMPLY_RETRY

    def _st_itemplay(self, cursor, disturbed):
        """拿起地上的矛/石头把玩一会儿，再放下走人。"""
        b = self.body
        if self.grab.active:
            self._itemplay_end()
            self._transition("Dragged")
            return
        if self._itemplay_phase == 0:
            it = self._itemplay_target
            if it is None or it.state != "free":
                self._itemplay_end()
                self._transition("IdleStand")
                return
            side = "r" if it.x >= b.chunk0.x else "l"
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
                from ..world.spear import Spear
                if isinstance(it, Spear):
                    b.grab_spear(it, side)
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
        if b.carried_spear is None and b.carried_stone is None:
            self._itemplay_end()
            self._transition("IdleStand")
            return
        b.stop_walk()
        self._itemplay_left -= 1
        t = self.timer
        # 拿在手里就是玩（eat_raise 保持 0，手别乱晃）；姿态随性格
        style = getattr(self.pers, "play_style", "sit")
        if style == "crawl":
            b.set_crawl(True)                                # 匍匐着玩
            if t % tuning.ITEMPLY_PRANCE_CD == 0:
                b.walk_to(b.chunk1.x + (18.0 if (t // tuning.ITEMPLY_PRANCE_CD) % 2 else -18.0))
        elif style == "hop":
            if t % tuning.ITEMPLY_PRANCE_CD == 0:
                b.walk_to(b.chunk1.x + self.rng.choice((-40.0, 40.0)))
                if b.on_floor():
                    b.request_jump("stand")                  # 边走边跳
        else:
            b.set_crawl(False)
        if self._itemplay_left <= 0 or t > 2400:
            if self.rng.random() < getattr(self.pers, "temper", 0.5) * tuning.ITEMPLY_FLING_P:
                self._itemplay_fling()                       # 暴躁的猫：玩完甩出去
            self._itemplay_end()
            self._transition("IdleStand")

    # ── 觅食时捡矛（打未开荚的爆米花）──
    def _nearest_fetchable_spear(self):
        """地上可取用的矛（插着或躺着的），限 COB_SPEAR_FETCH_R 内。"""
        c0 = self.body.chunk0
        best, bd = None, tuning.COB_SPEAR_FETCH_R
        for sp in self.win.spears:
            if sp.state != "free" or sp.stuck_to is not None:
                continue
            if getattr(sp, "pinned", False):      # 钉成杆的矛：拔不动也捡不走
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
        side = "r" if sp.x >= b.chunk0.x else "l"
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

    def _dismiss_kill_dialog(self):
        """静默消解本猫的死亡威胁弹窗。"""
        if getattr(self.win, "_kill_dialog", None) is not None:
            self.win.dismiss_kill_dialog()
