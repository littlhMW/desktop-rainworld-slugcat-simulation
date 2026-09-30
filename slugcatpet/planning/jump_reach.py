"""跳跃够取能力（全员）：走到起跳点→驻停→按档起跳，竖直或持向横弧；空中探身+持向漂移，落地报 done。"""
from __future__ import annotations

import math

from ..behavior import tuning
from ..core.units import clampf
from ..core import chunkphys
from .ability import Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band
from .jump_arc import get_arc, sweep_hit
from .walk_reach import _walk_crosses_solid

SETTLE_VX = 0.3
SETTLE_MAX = 40      # 驻停等待上限，超时按当前状态起跳
# 预留走位残差，防"规划说行/临跳说不行"死循环
PLAN_HIT_RADIUS = tuning.GRAB_REACH - tuning.PLAN_JUMP_TAKEOFF_EPS


def _free_launch_hit(arc, gx, gy, launch_y, xmin, xmax, radius):
    """定 launch_y、自由 launch_x∈[xmin,xmax]：找弧上某点命中 (gx,gy) 的 (launch_x, tick)；无则 None。"""
    for i, (px, py) in enumerate(arc.points):
        lx = gx - px
        if xmin <= lx <= xmax and abs((launch_y + py) - gy) <= radius:
            return lx, i + 1
    return None


def _arc_hits_solids(arc, launch_x, launch_y, radius=None):
    """检查完整跳弧是否穿过统一地形；用于防止规划器选择「理论命中、实际撞墙」的路线。"""
    r = float(radius if radius is not None else chunkphys.RAD0)
    for px, py in arc.points:
        x = launch_x + px
        y = launch_y + py
        for x0, y0, x1, y1 in chunkphys.cat_solids():
            if x + r <= x0 or x - r >= x1 or y + r <= y0 or y - r >= y1:
                continue
            return True
    return False


class JumpReach(Ability):
    key = "jump"

    def _plan(self, goal):
        # 枚举 档×{竖直,右,左}，取耗时最省
        pet = self.pet
        gx, gy = goal.pos()
        xmin, xmax = walk_band(pet)
        stats = pet.cat.stats
        floor = pet.stand_h()
        hipx = pet.body.chunk1.x
        best = None
        best_t = None

        def consider(lx, hold, md, hit, arc):
            nonlocal best, best_t
            # 起跳点本身也必须从当前支撑面走得到，不能隔着庇护所墙「瞬移式」选位。
            if _walk_crosses_solid(hipx, lx, floor):
                return
            launch_y = floor - arc.takeoff_h
            if _arc_hits_solids(arc, lx, launch_y):
                return
            t = abs(hipx - lx) / tuning.PLAN_WALK_SPEED + hit + tuning.PLAN_STARTUP_TICKS
            if best_t is None or t < best_t:
                best_t = t
                best = (lx, hold, md, hit)

        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            arc0 = get_arc(stats, hold, 0)
            if xmin <= gx <= xmax:
                dy = gy - (floor - arc0.takeoff_h)
                hit = sweep_hit(arc0, 0.0, dy, PLAN_HIT_RADIUS)
                if hit is not None:
                    consider(gx, hold, 0, hit, arc0)
            for md in (1, -1):
                arc = get_arc(stats, hold, md)
                lh = _free_launch_hit(arc, gx, gy, floor - arc.takeoff_h,
                                      xmin, xmax, PLAN_HIT_RADIUS)
                if lh is not None:
                    lx, hit = lh
                    consider(lx, hold, md, hit, arc)
        if best is None:
            return None
        return best + (best_t,)

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        _, _, md, hit, t = plan
        walk_t = t - hit - tuning.PLAN_STARTUP_TICKS
        return Estimate(t, walk_t * tuning.PLAN_EN_RATE_LIGHT
                        + hit * tuning.PLAN_EN_RATE_VIGOROUS)

    def make_controller(self, goal):
        return JumpReachController(self.pet, goal)


class JumpReachController:
    """走到起跳 x（紧到位判定）→ 驻停 → 起跳时刻以实际 chunk0 重选 (档,横向) 起跳，持向探身，落地报 done。"""

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.phase = "walk"
        self._settle = 0
        self._airborne = False
        self._move_dir = 0
        plan = JumpReach(pet)._plan(goal)
        self._launch_x = plan[0] if plan is not None else None

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        reach_assist(pet, self.goal, gx, gy)
        if self._launch_x is None:
            return GIVEUP
        xmin, xmax = walk_band(pet)
        lx = clampf(self._launch_x, xmin, xmax)
        if self.phase == "walk":
            if (body.on_floor()
                    and abs(body.chunk1.x - lx) <= tuning.PLAN_JUMP_TAKEOFF_EPS):
                body.stop_walk()
                self.phase = "settle"
                return RUNNING
            body.walk_to(lx)
            return RUNNING
        if self.phase == "settle":
            body.stop_walk()
            self._settle += 1
            still = (abs(body.chunk0.vx) < SETTLE_VX
                     and abs(body.chunk1.vx) < SETTLE_VX)
            if body.on_floor() and (still or self._settle > SETTLE_MAX):
                pick = self._pick_at_launch(gx, gy)
                if pick is None:
                    return GIVEUP
                hold, md = pick
                body.request_jump("stand", hold_ticks=hold)
                body.move_dir = md
                self._move_dir = md
                self.phase = "air"
            return RUNNING
        # air
        if not body.on_floor():
            self._airborne = True
            body.move_dir = self._move_dir
        elif self._airborne:
            body.stop_walk()
            self._airborne = False
            return DONE if self._landed_ok(gx, gy) else GIVEUP
        return RUNNING

    def _landed_ok(self, gx, gy) -> bool:
        """落地判定：摸到目标（TouchJump）或落到目标所在面（TravelJump）才算成功。

        旧版这里是「跳起来再碰到地面就算 DONE」——哪怕实际是「跳过去、摸到目标、
        又落回原地」，执行器也认为这条路线走通了，下一轮重新规划又回到原处。
        这正是「跳跃不聪明」的根。这里拆成两类语义：
          TouchJump  —— 只需要摸到（抓飞虫 / 摘果 / 攻击 / 舌钩补救）：
                        落地时仍在够取圈内即算成功，否则报失败让执行器换方案。
          TravelJump —— 要以位移为目的（goal.contact == "travel"）：
                        必须落在有效支撑面上，且落点离目标横距在 JUMP_TRAVEL_LAND_PAD 内。
        """
        b = self.pet.body
        if math.hypot(gx - b.chunk1.x, gy - b.chunk1.y) <= tuning.GRAB_REACH:
            return True
        if getattr(self.goal, "contact", "body") != "travel":
            return False
        # 落地那一 tick 的接触 chunk 未必是 chunk1（例如头朝下落地）：
        # 两段任一给出支撑面就算站在地上。on_floor() 为真 ⟹ 同 chunk 的
        # support_y 同 tick 被写过，所以这里不会漏判真落地。
        if (getattr(b.chunk1, "support_y", None) is None
                and getattr(b.chunk0, "support_y", None) is None):
            return False
        return abs(b.chunk1.x - gx) <= tuning.JUMP_TRAVEL_LAND_PAD

    def _pick_at_launch(self, gx, gy):
        # 起跳时以实际位置重选：先竖直后横弧
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            if sweep_hit(get_arc(stats, hold, 0),
                         gx - c0.x, gy - c0.y, tuning.GRAB_REACH) is not None:
                return hold, 0
        for md in (1, -1):
            for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                if sweep_hit(get_arc(stats, hold, md),
                             gx - c0.x, gy - c0.y, tuning.GRAB_REACH) is not None:
                    return hold, md
        return None

    def cancel(self):
        self.pet.body.stop_walk()