"""竖杆够取族（爬杆到指定高度为共用前置）：杆上任意高度 beam jump 斜跳 / 杆顶站立跳直上 / 任意高度松杆落体漂移 / 杆上舌取（Saint）。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..core.units import clampf
from .ability import (Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist,
                      walk_band)
from .jump_arc import get_arc, get_drop_arc, get_pole_jump_arc, sweep_hit
from .tongue_reach import FETCH_IDEAL, FETCH_REEL, APPROACH_TIMEOUT, reset_tongue
from ..world.enums import ItemState

POLE_TIP_C0_H = 17.0        # 杆顶/站立时 chunk0 距顶高
LAUNCH_ARRIVE_EPS = 6.0


def _vpoles(pet):
    """本世界可攀的实体竖杆（忽略随鼠标移动的虚杆）。"""
    return [p for p in getattr(pet, "poles", ())
            if (getattr(p, "kind", None) == "vertical"
                and getattr(p, "state", ItemState.FREE) == ItemState.FREE
                and not getattr(p, "virtual", False))]


def _c0_range(pet, pole):
    """杆上 chunk0 可及 y 区间；不可从当前支撑面直接抓住时返回 None。

    这族直连能力会先走到杆下，再由 PoleClimber 抓杆；它不能假定世界里任意
    一根竖杆都从屏幕地板长上来。旧版把上限固定成 ``HL - 17``，于是浮空杆也
    被估成「地面走过去 → 沿杆爬高 → 起跳」，规划器不断派猫到杆底，却永远
    抓不到。只有杆跨过当前身体高度、且杆下仍在当前可走带时，才允许用这条
    单能力路线；浮空杆若能从平台/另一根杆跳到，交给 SurfaceGraph 的真实跳杆边。
    """
    body = pet.body
    # This shortcut starts by walking to the rod from the current support. The
    # actual floor-grab branch in PoleClimber requires the hip chunk to be on a
    # surface; `body.on_floor()` is weaker because it also accepts head-only
    # contact during a fall.
    if (getattr(body, "on_pole", False)
            or not getattr(body.chunk1, "on_floor", False)):
        return None
    if not pole.touches_support_y(body.support_y()):
        return None
    c1_y = float(body.chunk1.y)
    pad = tuning.POLE_AIRGRAB_PAD
    if not (pole.top_y - pad <= c1_y <= pole.bottom_y + pad):
        return None
    lo_x, hi_x = walk_band(pet)
    approach_x = min(hi_x, max(lo_x, float(pole.x)))
    dx_to_approach = abs(float(pole.x) - approach_x)
    if dx_to_approach > 1.0:
        # A wall cut the current walk band: do not accept the controller's
        # proximity tolerance as permission to grab a pole through that wall.
        # The only safe out-of-band exception is a rod just beyond the screen
        # edge, where there is no intervening solid.
        at_screen_edge = ((approach_x <= 1.0 and pole.x < lo_x)
                          or (approach_x >= pet._WL - 1.0 and pole.x > hi_x))
        if (not at_screen_edge
                or dx_to_approach >= tuning.POLE_CLIMB_ARRIVE_EPS):
            return None
    # stand_h 是当前真实支撑面（屏幕地板、窗口顶边或墙顶），不是固定 HL。
    # 计算发射高度时还要裁到杆底：未接地的短浮杆不能被虚构成一直延伸到
    # 当前地面的长杆，否则图上会出现实际上无法爬到的发射高度。
    stand_h = float(pet.stand_h())
    conn_stand = float(getattr(body, "_conn_stand", POLE_TIP_C0_H)
                       or POLE_TIP_C0_H)
    top_c0 = float(pole.top_y) - conn_stand
    base_c0 = stand_h - conn_stand
    rod_bottom_c0 = (float(pole.bottom_y) - float(body.chunk1.rad)
                     - conn_stand)
    max_c0 = min(base_c0, rod_bottom_c0)
    if max_c0 < top_c0:
        return None
    return top_c0, max_c0


def _climb_cost_to(pet, pole, hy):
    """走到杆下 + 爬到 chunk0 高 hy 的粗线性 (耗时, 体力)。"""
    walk_t = abs(pet.body.chunk1.x - pole.x) / tuning.PLAN_WALK_SPEED
    base_c0 = float(pet.stand_h()) - float(
        getattr(pet.body, "_conn_stand", POLE_TIP_C0_H) or POLE_TIP_C0_H)
    climb_t = max(0.0, base_c0 - hy) / tuning.PLAN_CLIMB_SPEED
    return (walk_t + climb_t,
            walk_t * tuning.PLAN_EN_RATE_LIGHT + climb_t * tuning.PLAN_EN_RATE_VIGOROUS)


def _search_height(arc, gx, gy, pole_x, hy_lo, hy_hi, radius, pet, pole):
    """定 launch_x=pole_x、自由 chunk0 发射高 hy∈[hy_lo,hy_hi]：找弧上某点命中的最省 (hy, tick, 爬耗时, 爬体力)。"""
    best = None
    best_c = None
    for i, (px, py) in enumerate(arc.points):
        hy = gy - py                       # 令该采样点竖直正对目标
        if not (hy_lo <= hy <= hy_hi):
            continue
        if abs((pole_x + px) - gx) > radius:
            continue
        ct, ce = _climb_cost_to(pet, pole, hy)
        c = ct + (i + 1)
        if best_c is None or c < best_c:
            best_c = c
            best = (hy, i + 1, ct, ce)
    return best


class _PoleClimb:
    """爬杆到指定高度混入：_step_to_height() 回 running/ready/fail；_drop_pole() 收 PoleClimber。"""

    def _ensure_climber(self):
        if self.climber is None:
            from ..behavior.pole_climb import PoleClimber
            self.climber = PoleClimber(self.pet, self.pole, getattr(self.pet, "rng", None))

    def _step_to_height(self, release_hy, want_tip):
        pet = self.pet
        if self.pole not in getattr(pet, "poles", ()):
            return "fail"
        self._ensure_climber()
        done = self.climber.update(want_dismount=False)
        if self.climber.giveup:
            return "fail"
        phase = self.climber.phase
        if want_tip:
            return "ready" if phase == "tip" else ("fail" if done else "running")
        # 中途高度：须已抓上杆（phase climb/tip）且 chunk0 爬到发射高
        if phase in ("climb", "tip") and pet.body.chunk0.y <= release_hy + LAUNCH_ARRIVE_EPS:
            return "ready"
        if phase == "tip":                 # 到顶仍没到（目标比顶高，不该发生）→ 就用顶
            return "ready"
        return "fail" if done else "running"

    def _drop_pole(self):
        if self.climber is not None:
            self.climber.release()
            self.climber = None


# 杆上跳
class PoleJumpReach(Ability):
    key = "polejump"

    def _plan(self, goal):
        pet = self.pet
        gx, gy = goal.pos()
        stats = pet.cat.stats
        best = None
        best_t = None

        def consider(pole, kind, params, hy, t, e):
            nonlocal best, best_t
            if best_t is None or t < best_t:
                best_t = t
                best = (pole, kind, params, hy, t, e)

        for pole in _vpoles(pet):
            span = _c0_range(pet, pole)
            if span is None:
                continue
            hy_lo, hy_hi = span
            tip_c0y = hy_lo
            # 杆顶站立跳：竖直优先，再左右横弧
            ct, ce = _climb_cost_to(pet, pole, tip_c0y)
            for md in (0, 1, -1):
                done = False
                for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                    hit = sweep_hit(get_arc(stats, hold, md), gx - pole.x,
                                    gy - tip_c0y, tuning.GRAB_REACH)
                    if hit is not None:
                        consider(pole, "tip", (hold, md), tip_c0y,
                                 ct + hit + tuning.PLAN_STARTUP_TICKS,
                                 ce + hit * tuning.PLAN_EN_RATE_VIGOROUS)
                        done = True
                        break
                if done:
                    break
            # 任意高度 beam jump（左右）：搜发射高度
            for d in (1, -1):
                r = _search_height(get_pole_jump_arc(stats, d), gx, gy, pole.x,
                                   hy_lo, hy_hi, tuning.GRAB_REACH, pet, pole)
                if r is not None:
                    hy, hit, ct2, ce2 = r
                    consider(pole, "beam", (d,), hy,
                             ct2 + hit + tuning.PLAN_STARTUP_TICKS,
                             ce2 + hit * tuning.PLAN_EN_RATE_VIGOROUS)
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        return Estimate(plan[4], plan[5])

    def make_controller(self, goal):
        return PoleLaunchController(self.pet, goal, self._plan(goal))


# 杆上松杆落体漂移
class PoleDropReach(Ability):
    key = "poledrop"

    def _plan(self, goal):
        pet = self.pet
        gx, gy = goal.pos()
        stats = pet.cat.stats
        best = None
        best_t = None
        for pole in _vpoles(pet):
            span = _c0_range(pet, pole)
            if span is None:
                continue
            hy_lo, hy_hi = span
            for md in (0, 1, -1):
                r = _search_height(get_drop_arc(stats, md), gx, gy, pole.x,
                                   hy_lo, hy_hi, tuning.GRAB_REACH, pet, pole)
                if r is not None:
                    hy, hit, ct, ce = r
                    t = ct + hit + tuning.PLAN_STARTUP_TICKS
                    if best_t is None or t < best_t:
                        best_t = t
                        best = (pole, "drop", (md,), hy, t,
                                ce + hit * tuning.PLAN_EN_RATE_LIGHT)
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        return Estimate(plan[4], plan[5])

    def make_controller(self, goal):
        return PoleLaunchController(self.pet, goal, self._plan(goal))


class PoleLaunchController(_PoleClimb):
    """爬杆到发射高度 → 按 kind 起跳/落体（tip=杆顶站立跳、beam=竖杆跳、drop=松杆落体）→ 持向探身/漂移，落地报 done。"""

    def __init__(self, pet, goal, plan):
        self.pet = pet
        self.goal = goal
        self.plan = plan
        self.pole = plan[0] if plan else None
        self.kind = plan[1] if plan else None
        self.params = plan[2] if plan else None
        self.release_hy = plan[3] if plan else None
        self.climber = None
        self.phase = "climb"
        self._airborne = False
        self._md = 0

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        if self.pole is None:
            return GIVEUP
        if self.phase == "climb":
            reach_assist(pet, self.goal, gx, gy)
            st = self._step_to_height(self.release_hy, want_tip=(self.kind == "tip"))
            if st == "fail":
                return GIVEUP
            if st == "ready":
                self.phase = "launch"
            return RUNNING
        if self.phase == "launch":
            self._drop_pole()
            if self.kind == "tip":
                hold, md = self._pick_tip(gx, gy)
                body.tip_launch(hold_ticks=hold, move_dir=md)
                self._md = md
            elif self.kind == "beam":
                d = self.params[0]
                body.pole_jump(d)
                self._md = d
            else:
                md = self.params[0]
                body.release_to_air(move_dir=md)
                self._md = md
            self.phase = "air"
            return RUNNING
        # air
        reach_assist(pet, self.goal, gx, gy)
        if not body.on_floor():
            self._airborne = True
            body.move_dir = self._md
        elif self._airborne:
            body.stop_walk()
            return DONE
        return RUNNING

    def _pick_tip(self, gx, gy):
        # 起跳时以实际位置重选，无命中回落原计划
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        for md in (0, 1, -1):
            for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                if sweep_hit(get_arc(stats, hold, md), gx - c0.x, gy - c0.y,
                             tuning.GRAB_REACH) is not None:
                    return hold, md
        return self.params

    def cancel(self):
        self._drop_pole()
        self.pet.body.stop_walk()


# 杆上舌取（Saint）
class PoleTongueReach(Ability):
    key = "poletongue"

    def _plan(self, goal):
        pet = self.pet
        tg = pet.tongue
        if tg is None:
            return None
        gx, gy = goal.pos()
        rng = tg.total * tuning.PLAN_TONGUE_RANGE_FRAC
        best = None
        best_t = None
        for pole in _vpoles(pet):
            span = _c0_range(pet, pole)
            if span is None:
                continue
            hy_lo, hy_hi = span
            hy = clampf(gy, hy_lo, hy_hi)          # 贴目标高度最省舌
            d = math.hypot(gx - pole.x, gy - hy)
            if d <= rng:
                ct, ce = _climb_cost_to(pet, pole, hy)
                t = ct + d / tuning.PLAN_TONGUE_SPEED + tuning.PLAN_STARTUP_TICKS
                if best_t is None or t < best_t:
                    best_t = t
                    best = (pole, hy, Estimate(t, ce + (d / tuning.PLAN_TONGUE_SPEED)
                                               * tuning.PLAN_EN_RATE_LIGHT))
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        return plan[2] if plan is not None else None

    def make_controller(self, goal):
        plan = self._plan(goal)
        return PoleTongueController(self.pet, goal,
                                    plan[0] if plan else None,
                                    plan[1] if plan else None)


class PoleTongueController(_PoleClimb):
    """爬杆到目标同高 → 松杆射舌粘果收绳，消费方查抓取即终止；落空/超时报 giveup。"""

    def __init__(self, pet, goal, pole, release_hy):
        self.pet = pet
        self.goal = goal
        self.pole = pole
        self.release_hy = release_hy
        self.climber = None
        self.phase = "climb"
        self.timer = 0

    def update(self):
        pet = self.pet
        gx, gy = self.goal.pos()
        if self.pole is None:
            return GIVEUP
        reach_assist(pet, self.goal, gx, gy)
        if self.phase == "climb":
            tip_c0y = self.pole.top_y - POLE_TIP_C0_H
            st = self._step_to_height(self.release_hy,
                                      want_tip=(self.release_hy <= tip_c0y + LAUNCH_ARRIVE_EPS))
            if st == "fail":
                return GIVEUP
            if st == "ready":
                self._drop_pole()
                pet.body.release_to_air(move_dir=0)   # 松杆，靠舌把身/果收拢
                self.phase = "fire"
            return RUNNING
        tg = pet.tongue
        if self.phase == "fire":
            if tg is None:
                return GIVEUP
            if tg.is_idle():
                if self.goal.obj is not None:
                    pet.fire_tongue_at_obj(self.goal.obj)
                else:
                    pet.fire_tongue_at(gx, gy)
                self.phase = "reel"
                self.timer = 0
            return RUNNING
        # reel
        self.timer += 1
        if tg.attached:
            tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)
            if self.timer > 2 * APPROACH_TIMEOUT:
                reset_tongue(pet)
                return GIVEUP
            return RUNNING
        if self.timer > APPROACH_TIMEOUT:
            reset_tongue(pet)
            return GIVEUP
        return RUNNING

    def cancel(self):
        self._drop_pole()
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
