"""果取薄应用：选果/够取交规划层驱动，接触抓取与 grabbed→carry_fall→eat 留本地。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..planning import GIVEUP, PlanExecutor, TongueSnatch, obj_goal
from ..cats.personality import DIET_VEGETARIAN, DIET_SPECIAL, DIET_CARNIVORE

# 取食/啃咬参数
MEAT_PREF = 0.6
EAT_INTERVAL = 15
EAT_APPROACH = 12
EAT_HOLD_POSE = 0.25
EAT_CHOMP_POSE = 1.0
BITE_HEAD_NUDGE = 2.0
CARRY_FALL_TIMEOUT = 200
DELIVER_REACH = 30.0          # 送蝉乌贼给蜥蜴的交接距离
DELIVER_TIMEOUT = 900         # 送不出去就放弃（防呆）
DELIVER_GAP = 40.0            # 走到离蜥蜴这么近就不再逼近

_EDIBLE_STATES = ("free", "hanging")


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _seg_point_dist(ax, ay, bx, by, px, py):
    """点 (px,py) 到线段 (a,b) 的最近距。"""
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    if d2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / d2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _edible_goal(obj):
    """可食目标 Goal：离开 free/hanging 即失效。"""
    return obj_goal(obj, valid=lambda o: o.state in _EDIBLE_STATES, contact="grasp")


def fetch_candidates(planner, edibles, diet=None, pearl_like=1.0):
    """选果候选：可达且不冷却的 (obj, goal, 预估耗时)，按耗时升序。

    pearl_like > 1 的猫（溪流）把珍珠的预估耗时缩短，于是珍珠排在果子前面 ——
    「喜欢珍珠，会尝试持有珍珠」。
    """
    out = []
    for f in edibles:
        if f.state not in _EDIBLE_STATES:
            continue
        if not getattr(f, "fetch_ready", True):
            continue    # 飞行中蝙蝠够不到
        meat = getattr(f, "is_meat", False)
        if meat and diet in (DIET_VEGETARIAN, DIET_SPECIAL):
            continue    # 素食/圣徒不自主吃肉
        g = _edible_goal(f)
        if planner.in_cooldown(g):
            continue
        cands = planner.touch_candidates(g)
        if cands:
            time_est = cands[0].time_est
            if meat and diet == DIET_CARNIVORE:
                time_est *= MEAT_PREF
            elif not getattr(f, "is_edible", True):
                time_est /= max(1.0, float(pearl_like))   # 珍珠：越喜欢越先拿
            out.append((f, g, time_est))
    out.sort(key=lambda item: item[2])
    return out


def fetch_ready(planner, edibles, diet=None):
    """触发闸用：早退版 fetch_candidates，仅返回可达列表。"""
    out = []
    for f in edibles:
        if f.state not in _EDIBLE_STATES:
            continue
        if not getattr(f, "fetch_ready", True):
            continue
        if getattr(f, "is_meat", False) and diet in (DIET_VEGETARIAN, DIET_SPECIAL):
            continue
        g = _edible_goal(f)
        if planner.in_cooldown(g):
            continue
        if planner.any_touch(g):
            out.append(f)
    return out


PEARL_HOLD_TICKS = tuning.PEARL_CARRY_TICKS   # 拿着珍珠多久才放下（对齐 fsm 的携带计时）


class FruitFetcher:
    def __init__(self, win, planner, diet=None, pearl_like=1.0):
        self.win = win
        self.body = win.body
        self.tongue = win.tongue
        self.planner = planner
        self.diet = diet
        self.pearl_like = float(pearl_like)

        self.target = None
        self.phase = "select"
        self.eaten = 0
        self.giveup = False
        self.timer = 0
        self.grab_side = "r"
        self.eat_counter = 0
        self._eat_approaching = False
        self._bit_this_cycle = False
        self._executor = None
        self._giveup_pending = False
        self._goal = None
        self._deliver = None          # 驯服交付目标（Lizard）
        self._trade_to = None         # 珍珠交易目标（Scavenger）
        self._snatch = TongueSnatch(win)
        self.pearl_done = False       # 本次取物以「把玩珍珠收尾」结束

    def _chunk0(self):
        return self.body.chunk0

    def _grab_dist(self):
        """果到扫掠线段/持物手最近距，防高速跨过抓取圈漏判。"""
        f = self.target
        c0 = self._chunk0()
        d = _seg_point_dist(c0.last_x, c0.last_y, c0.x, c0.y, f.x, f.y)
        hx, hy = self.body._carry_pos(self.grab_side)
        d = min(d, _dist(hx, hy, f.x, f.y))
        return d

    def _try_grab(self):
        """够取判定，命中则抓果转 carry_fall。"""
        if self._grab_dist() < tuning.GRAB_REACH:
            self._reset_tongue()
            if getattr(self.target, "stuck_pos", None) is not None:
                self.target.stuck_pos = None    # 抓取瞬间剥离黏菌
            self.body.grab_fruit(self.target, self.grab_side)
            self.phase = "grabbed"
            self.timer = 0
            return True
        return False

    def _reset_tongue(self):
        """舌头收缩与悬停清理。"""
        if self.tongue is not None:
            self.tongue.retract()
            self.tongue.reset_config()
        self.body.suspended = False

    def _pick_grab_side(self):
        """选更近的抓取手。"""
        return "r" if self.target.x >= self._chunk0().x else "l"

    def _drop_executor(self):
        if self._executor is not None:
            self._executor.cancel()
            self._executor = None

    def release(self):
        """外部中断：终止执行器 + 收回补救舌头。"""
        self._snatch.abort()
        self._drop_executor()

    def update(self) -> bool:
        """推进一 tick，完成返回 True。"""
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return True
        return m()

    def _phase_select(self):
        # 候选空 + 曾放弃 → giveup
        cands = fetch_candidates(self.planner,
                                 self.win.fetchables(pearl_like=self.pearl_like),
                                 diet=self.diet,
                                 pearl_like=self.pearl_like)
        if not cands:
            self.giveup = self._giveup_pending
            return True
        self.target, goal, _ = cands[0]
        self.grab_side = self._pick_grab_side()
        self._giveup_pending = False
        self._goal = goal
        self._snatch.reset()
        self._executor = PlanExecutor(self.win, self.planner, goal)
        self.timer = 0
        self.phase = "approach"
        return False

    def _phase_approach(self):
        # 执行器驱动够取，每 tick 自查抓取
        f = self.target
        if f.state not in _EDIBLE_STATES:
            self._snatch.abort()
            self._drop_executor()
            self.phase = "select"
            return False
        self.grab_side = self._pick_grab_side()
        if self._try_grab():
            self._snatch.abort()
            self._drop_executor()
            return False
        # 补救层需在 try_grab 后、executor 前抢射
        self._snatch.update(self._goal)
        if self._snatch.holding():
            # 持有补救舌头时暂停 executor，防裸 retract 撕舌
            return False
        if self._executor.update() == GIVEUP:
            self._snatch.abort()
            self._executor = None
            self.target = None
            self._giveup_pending = True
            self.phase = "select"
        return False

    def _phase_grabbed(self):
        self._reset_tongue()
        self.body.suspended = False
        self.phase = "carry_fall"
        self.timer = 0
        return False

    def _phase_carry_fall(self):
        f = self.body.carried_fruit
        if f is None:
            self.phase = "select"
            return False
        # 蝉乌贼：叼去喂给还没驯服的蜥蜴（原版送礼驯服），没有人要则当食物吃掉
        if getattr(f, "is_tame_food", False):
            lz = self.win.nearest_untamed_lizard(self.body.chunk0.x)
            if lz is not None:
                self._deliver = lz
                self.phase = "deliver"
                self.timer = 0
                return False
        # 不能吃的东西（珍珠）：叼去跟拾荒者交易（原版：手里的珍珠换东西）
        if not getattr(f, "is_edible", True):
            sc = self.win.nearest_scavenger(self.body.chunk0.x)
            if sc is not None:
                self._trade_to = sc
                self.phase = "trade"
                self.timer = 0
            elif self.pearl_like > 1.0:
                # 喜欢珍珠的猫（溪流）：没得交易也舍不得撒手，先拿着把玩一段
                self.phase = "pearl_hold"
                self.timer = 0
            else:
                self.body.release_fruit()
                f.state = "free"
                f.held_by_hand = None
                self.phase = "select"
            return False
        # 悬空卡死兜底超时
        if self.timer > CARRY_FALL_TIMEOUT and f.stalk is not None:
            f.stalk = None
        if self.body.on_floor() or self.body.on_pole:
            self.phase = "eat"
            self.timer = 0
            self.eat_counter = 0
            self._eat_approaching = True
            self._bit_this_cycle = False
        return False

    def _phase_deliver(self):
        """把礼物送到蜥蜴嘴边：走到它旁边，够近即交出。"""
        f = self.body.carried_fruit
        lz = self._deliver
        if (f is None or lz is None or lz.tamed
                or lz.state not in _EDIBLE_STATES or self.timer > DELIVER_TIMEOUT):
            self._deliver = None
            self.phase = "select"
            return False
        hx, hy = lz.x, lz.y - lz.body_rad * 1.2      # 蜥蜴头侧
        c0 = self.body.chunk0
        d = math.hypot(hx - c0.x, hy - (c0.y - 8.0))
        self.win.gfx.look_at = (hx, hy)
        if d <= DELIVER_REACH:
            self._deliver = None
            if self.win.deliver_gift(self.win, lz):
                return True
            self.phase = "select"
            return False
        if d > DELIVER_GAP:
            self.body.walk_to(hx)
        else:
            self.body.stop_walk()
        return False

    def _phase_pearl_hold(self):
        """喜欢珍珠的猫：把珍珠端在手里看一会儿，玩够了自己放下（原版珍珠可携带）。"""
        f = self.body.carried_fruit
        if f is None:
            self.phase = "select"
            return False
        self.win.gfx.look_at = (f.x, f.y)
        if self.timer > PEARL_HOLD_TICKS:
            self.pearl_done = True
            side = self.body.hand_of.get("fruit")
            if side is not None:
                self.body.arm_aim[side] = None
            self.body.release_fruit()
            f.state = "free"
            f.held_by_hand = None
            return True
        return False

    def _phase_trade(self):
        """把珍珠送到拾荒者旁边：够近它自己会收下（items._step_scavenger_trade）。"""
        f = self.body.carried_fruit
        sc = self._trade_to
        if (f is None or sc is None or sc.dead or sc.state != "free"
                or self.timer > DELIVER_TIMEOUT):
            self._trade_to = None
            self.phase = "select"
            return False
        c0 = self.body.chunk0
        hx, hy = sc.x, sc.y - 10.0
        self.win.gfx.look_at = (hx, hy)
        d = math.hypot(hx - c0.x, hy - (c0.y - 8.0))
        if d <= DELIVER_REACH:
            if self.win.hand_pearl(sc):
                self._trade_to = None
                return True
            self._trade_to = None
            self.phase = "select"
            return False
        if d > DELIVER_GAP:
            self.body.walk_to(hx)
        else:
            self.body.stop_walk()
        return False

    def _phase_eat(self):
        f = self.body.carried_fruit
        if f is None:
            self.phase = "select"
            return False
        self.win.gfx.look_at = (f.x, f.y)
        self.eat_counter += 1

        # 预咬摆动
        if self._eat_approaching:
            self.body.eat_raise = EAT_HOLD_POSE * min(1.0, self.eat_counter / EAT_APPROACH)
            if self.eat_counter >= EAT_APPROACH:
                self._eat_approaching = False
                self.eat_counter = 0
                self._bit_this_cycle = False
            return False

        # 咀嚼周期，峰值咬一口
        phase = min(1.0, self.eat_counter / EAT_INTERVAL)
        pulse = math.sin(phase * math.pi)
        self.body.eat_raise = EAT_HOLD_POSE + (EAT_CHOMP_POSE - EAT_HOLD_POSE) * pulse
        if self.eat_counter >= EAT_INTERVAL // 2 and not self._bit_this_cycle:
            self._bit_this_cycle = True
            self._bite_head_nudge(f)
            if self.body.bite_carried():
                f.state = "eaten"
                self.eaten += 1
                self.body.temper_shift(tuning.TEMPER_FEED)
                self.body.food_eat(getattr(f, "food_value", 1))
                self.body.energy_change(tuning.EN_EAT_RESTORE)
                self.body.release_fruit()
                if self.body.food >= self.body.food_max:
                    return True
                self.phase = "select"
                self.timer = 0
                return False
        if self.eat_counter >= EAT_INTERVAL:
            self.eat_counter = 0
            self._bit_this_cycle = False
        return False

    def _bite_head_nudge(self, f):
        """每口头部朝果轻推。"""
        g = self.win.gfx
        dx, dy = f.x - g.head.x, f.y - g.head.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            g.head.vx += dx / d * BITE_HEAD_NUDGE
            g.head.vy += dy / d * BITE_HEAD_NUDGE
