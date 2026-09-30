"""走够能力：沿可通行地面走到目标 x；实心地形会把直走方案让给跳跃/路线规划。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..core import chunkphys
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band


def _walk_crosses_solid(x0, x1, foot_y, body_h=None):
    """检查猫从 x0 走到 x1 的身体带是否穿过统一地形 SOLID。

    庇护所墙体、关门、其它未来加入的实体墙都走 chunkphys.cat_solids()；
    这里与物理碰撞共用同一份几何，避免「物理认得墙、寻路不认墙」。
    """
    lo, hi = sorted((float(x0), float(x1)))
    if hi - lo <= 1.0:
        return False
    h = float(body_h if body_h is not None else tuning.WALK_BODY_H)
    step = float(getattr(tuning, "WALK_STEP_UP", 8.0))
    r = max(1.0, float(getattr(chunkphys, "RAD1", 8.0)))
    for x0s, y0s, x1s, y1s in chunkphys.cat_solids():
        if x1s <= x0s or y1s <= y0s:
            continue
        if x1s <= lo or x0s >= hi:
            continue
        # 墙顶低于脚面很近的薄台阶允许直接踩上；高墙则必须跳/绕。
        if y1s <= foot_y - h:
            continue
        if y0s >= foot_y - step:
            continue
        # 猫的脚/髋有实际半径，避免贴着墙边被误认为无障碍。
        if x1s + r > lo and x0s - r < hi:
            return True
    return False


class WalkReach(Ability):
    key = "walk"

    def _plan(self, goal, max_h):
        pet = self.pet
        gx, gy = goal.pos()
        floor = pet.stand_h()
        if gy < floor - max_h or gy > floor + tuning.PLAN_FLOOR_TOL:
            return None
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        if abs(gx - fx) > tuning.PLAN_WALK_X_PAD:
            return None
        sx = pet.body.chunk1.x
        if _walk_crosses_solid(sx, fx, floor):
            # 不再让猫对着横墙持续 WalkReach。Planner 会自然尝试 JumpReach，
            # 若直跳也不可达，再进入 surface route 绕行。
            return None
        t = (abs(sx - fx) / tuning.PLAN_WALK_SPEED
             + tuning.PLAN_STARTUP_TICKS)
        return Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)

    def can_touch(self, goal):
        return self._plan(goal, tuning.PLAN_STAND_REACH_H)

    def can_stay(self, goal):
        r = goal.radius
        if r <= 0.0:
            return self._plan(goal, tuning.PLAN_FLOOR_TOL)
        return self._plan_radius(goal, r)

    def _plan_radius(self, goal, r):
        pet = self.pet
        gx, gy = goal.pos()
        dy = abs(gy - pet.stand_h())
        if dy > r:
            return None
        half = math.sqrt(r * r - dy * dy)
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        if abs(gx - fx) > half:
            return None
        if _walk_crosses_solid(pet.body.chunk1.x, fx, pet.stand_h()):
            return None
        t = (abs(pet.body.chunk1.x - fx) / tuning.PLAN_WALK_SPEED
             + tuning.PLAN_STARTUP_TICKS)
        return Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)

    def make_controller(self, goal):
        return WalkReachController(self.pet, goal)


class WalkReachController:
    """走到目标 x；运行中发现统一地形挡路则交还 Planner。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self._hold = 0

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        if _walk_crosses_solid(body.chunk1.x, fx, pet.stand_h()):
            body.stop_walk()
            return GIVEUP
        reach_assist(pet, self.goal, gx, gy)
        if body.on_floor() and abs(body.chunk1.x - fx) <= tuning.PLAN_ARRIVE_EPS:
            body.stop_walk()
            self._hold += 1
            return DONE if self._hold >= tuning.PLAN_ARRIVE_HOLD else RUNNING
        self._hold = 0
        body.walk_to(fx)
        return RUNNING

    def cancel(self):
        self.pet.body.stop_walk()
