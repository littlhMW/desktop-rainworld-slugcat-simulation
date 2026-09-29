"""跳跃寻路（全员）：目标摆在别的窗口顶边（单向平台）上、走不到也够不着时，
按目标相对位置挑一条「跳 / 跳落 / 走出去 / 后空翻」落到那块面上的轨迹，走过去→
起跳→落在那块面上；落地后由普通走够/跳够接着走完最后一段。

原版的跳跃本来就是位移手段（土狼跳跨间隙、后空翻越过蜥蜴、beam jump 换杆），
这里把「跳跃」接进规划层，于是寻路不再只有走路与原地够取两条路。
方向与距离由轨迹族（md 与 hold）枚举择优，落地判定走 pole_hop.land_sweep 的实测弧。
"""
from __future__ import annotations

from ..behavior import tuning
from ..core import chunkphys
from ..core.units import clampf
from .ability import Ability, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band
from .backflip_reach import takeoff_c0_h
from .jump_arc import get_arc, get_backflip_arc
from .jump_reach import SETTLE_MAX, SETTLE_VX
from .pole_hop import land_sweep

LAUNCH_STEP = 24.0                  # 起跳点采样步长（目标两侧各取两档）
LAUNCH_TRIES = (-2, -1, 0, 1, 2)
FLIP_FALLBACK = (False, True)       # 跳/跳落/落都不行时再试后空翻（未续力/续力）
LAND_PAD = tuning.PLAN_WALK_X_PAD   # 落点离目标超过它就不算「跳到地方了」
_MISS = object()
_memo: dict = {}
_MEMO_MAX = 512
_rise_memo: dict = {}


def _max_rise(stats):
    """本猫的跳跃弧/后空翻弧最高能升多少 px（缓存）：够不着那块面就别扫掠。"""
    v = _rise_memo.get(stats)
    if v is None:
        v = 0.0
        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            v = max(v, max(-p[1] for p in get_arc(stats, hold, 0).points))
        v = max(v, get_backflip_arc(stats, 1, True).apex)
        _rise_memo[stats] = v
    return v


def surface_under(x, y):
    """(x,y) 落在哪块窗口顶边（单向平台）上；不是平台则 None。返回 (y, x0, x1)。"""
    for x0, y0, x1 in chunkphys.platforms():
        if x0 <= x <= x1 and abs(y - y0) <= tuning.HPOLE_STEP_SURF_EPS:
            return (y0, x0, x1)
    return None


def _launch_points(pet, gx, launch_y):
    """起跳点候选：目标正下方 + 两侧各两档，钳在可行走带内。"""
    xmin, xmax = walk_band(pet)
    xs = []
    for k in LAUNCH_TRIES:
        x = clampf(gx + k * LAUNCH_STEP, xmin, xmax)
        if x not in xs:
            xs.append(x)
    return [(x, launch_y) for x in xs]


def plan_hop(pet, gx, gy, floor, launch_y, wv):
    """落到目标所在面的轨迹：返回 (kind, hold, md, launch_x, land_x, ticks)，无解 None。"""
    key = (pet.cat.stats, round(gx, 1), round(gy, 1), round(floor, 1), wv)
    hit = _memo.get(key, _MISS)
    if hit is not _MISS:
        return hit                      # 同一几何下同一目标只扫一次（扫掠不便宜）
    res = _plan_hop(pet, gx, gy, floor, launch_y)
    if len(_memo) >= _MEMO_MAX:
        _memo.clear()
    _memo[key] = res
    return res


def _plan_hop(pet, gx, gy, floor, launch_y):
    surf = surface_under(gx, gy)
    if surf is None:
        return None                  # 目标不在任何窗口顶边上：不是这条路的事
    sy, sx0, sx1 = surf
    if sy >= floor - tuning.PLAN_FLOOR_TOL:
        return None                  # 已经站在这块面上 / 目标面更低：走路就能到
    launches = _launch_points(pet, gx, launch_y)
    plats = [(sx0, sy, sx1)]
    stats = pet.cat.stats
    off = takeoff_c0_h(stats)
    r = land_sweep(stats, plats, launches, want=(gx, gy), land_off=off)
    if r is None:
        r = land_sweep(stats, plats, launches, want=(gx, gy),
                       flips=FLIP_FALLBACK, land_off=off)
    if r is None:
        return None
    kind, hold, md, land_x, _land_y, ticks, launch_x = r
    if abs(land_x - gx) > LAND_PAD:
        return None                  # 落在了这块面上但离目标太远：落地也够不到
    return (kind, hold, md, launch_x, land_x, ticks)


class HopReach(Ability):
    """跳跃寻路：跳 / 跳落 / 走出去 / 后空翻落到目标那块窗口顶边。"""
    key = "hop"

    def _plan(self, goal):
        pet = self.pet
        body = pet.body
        if getattr(body, "swimming", False) or getattr(body, "zerog", False):
            return None
        if getattr(body, "on_pole", False):
            return None                  # 杆上另有杆间跳/落平台的路（platform_hop_plan）
        if not chunkphys.platforms():
            return None                  # 没有别的窗口顶边：只有地板一块面，走/跳够取已覆盖
        gx, gy = goal.pos()
        floor = pet.stand_h()
        surf = surface_under(gx, gy)
        if surf is None:
            return None                  # 目标不在任何窗口顶边上
        if floor - surf[0] > _max_rise(pet.cat.stats) + tuning.GRAB_REACH:
            return None                  # 那块面高过一个跳跃的极限：跳不上去
        launch_y = floor - takeoff_c0_h(pet.cat.stats)
        return plan_hop(pet, gx, gy, floor, launch_y,
                        getattr(pet, "geometry_version", 0))

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        gx, _gy = goal.pos()
        _kind, _hold, _md, launch_x, land_x, ticks = plan
        hipx = self.pet.body.chunk1.x
        t = (abs(hipx - launch_x) / tuning.PLAN_WALK_SPEED
             + ticks
             + abs(land_x - gx) / tuning.PLAN_WALK_SPEED
             + tuning.PLAN_STARTUP_TICKS)
        return Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT
                        + ticks * tuning.PLAN_EN_RATE_VIGOROUS)

    def make_controller(self, goal):
        return HopReachController(self.pet, goal, self._plan(goal))


class HopReachController:
    """走到起跳点 → 驻停 → 起跳/后空翻/走出面 → 落地报 done（余下交给普通流程）。"""

    def __init__(self, pet, goal, plan):
        self.pet = pet
        self.goal = goal
        self.plan = plan
        self.phase = "walk"
        self._settle = 0
        self._airborne = False
        self._flip = False

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        reach_assist(pet, self.goal, gx, gy)
        plan = self.plan
        if plan is None:
            return GIVEUP
        kind, hold, md, launch_x, _land_x, _ticks = plan
        xmin, xmax = walk_band(pet)
        lx = clampf(launch_x, xmin, xmax)
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
                body.facing = 1 if md > 0 else -1
                if kind == "flip":
                    body.backflip_launch(md, boosted=bool(hold))
                    self._flip = True
                elif kind == "drop":
                    body.release_to_air(move_dir=md)
                else:                    # jump / jumpfall：同一档起跳，后半段自然下落
                    body.request_jump("stand", hold_ticks=hold)
                    body.move_dir = md
                self.phase = "air"
            return RUNNING
        # air
        if not body.on_floor():
            self._airborne = True
            body.move_dir = md
        elif self._airborne:
            self._finish()
            return DONE
        return RUNNING

    def _finish(self):
        body = self.pet.body
        body.stop_walk()
        if self._flip:
            body.animation = None        # 非手操路径无 ANIM_RESET 兜底
            body.jump_boost = 0.0
            body.set_posture(True)

    def cancel(self):
        self.pet.body.stop_walk()

