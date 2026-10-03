# -*- coding: utf-8 -*-
"""表面图寻路：Goal → SurfaceGraph(锚点图) → RoutePlan → RouteExecutor。

旧版只有「地板 → 一块窗口顶边 → 目标」这条定长两段路，于是「先爬杆、再跳平台、
再够到目标」这类目标永远没人去拿 —— 不是参数问题，是导航拓扑没成形。
原版是「房间 tile 图 + A*」（Room.CreateTileGraph / PathFinder）；桌宠没有 tile 图，
但有等价的东西：地板段、窗口顶边（单向平台）、竖杆顶、横杆面，都是可站立的支撑面。

导航节点不是「一整块面」，而是 **面 × 锚点**（NavNode = surf_id + x_anchor）：

    A 面 [100..500] → A@116 / A@280 / A@420 …（同面相邻锚点用 walk 边相连）
    Edge = 一次位移，带类型与代价：
           walk        同一面上相邻锚点走过去（含小缝隙 STEP_X）
           jump / drop 从一个锚点跳到另一块面的锚点上（实测轨迹族 jump/jumpfall/drop/flip）
           climb_pole  沿竖杆爬到杆顶
           pole_beam   杆间跳跃（空中抓另一根杆）
           finish      从该锚点伸手 / 起跳弧够到目标点
    每条边带：耗时 / 体力 / 风险 / 是否落地 / 终点姿态 / 起终锚点。
    代价 = route.edge 的六轴模型（时间 / 体力 / 风险 / 噪音 / 精度 / 后摇）× 性格。

为什么必须带锚点：代价里的「走到起跳点」必须用**真实起点**。旧版用
`abs(launch_x - a.clamp(launch_x))`，而 launch_x 本来就采在 a 的区间内 → 恒等于 0，
于是规划器认为「走到起跳位置不花时间」，路线看着聪明、走起来不对。

寻路：Dijkstra（节点数是个位数～几十，无需启发式）；终点（finish）当普通 terminal
边参与比较，不再「一弹出就返回」。可达性：只有「去得了、还能回来」的锚点才允许收尾
（原版 accessibility mapping 的等价物），免得猫跳进一个回不来的角落。

执行：RouteExecutor 按当前 leg 建既有控制器（HopReach / PoleJumpReach），落地后
**重新规划**接着走下一段；只有原目标（original_goal）被满足才算结束 —— 不会把
「第一段落点」当成终点，于是不会再出现「跳上平台就发呆」。
"""
from __future__ import annotations

import bisect
import heapq
import math

from ..behavior import tuning
from ..core import chunkphys
from ..core.units import clampf
from .ability import (DONE, GIVEUP, HOLD, HOLDING, MODE_TOUCH, RUNNING,
                      reach_assist, walk_band)
from . import navgeom
from .backflip_reach import takeoff_c0_h
from .goal import point_goal
from .hop_reach import (HopReach, HopReachController, SETTLE_MAX, SETTLE_VX,
                        surface_under)
from .jump_arc import (get_arc, get_backflip_arc, get_drop_arc,
                       get_jump_fall_arc, get_pole_hop_arc, sweep_hit)
from .jump_reach import _arc_hits_solids
from .pole_hop import hop_plan, land_sweep, pole_hit
from .navgraph import NavGraph, dynamic_edge_cost
from .pole_reach import PoleJumpReach
from .route import edge_for, landing_safe, route_cost
from .walk_reach import WalkReach

OPTIMISM = 1.30          # 多段路线的代价保守系数（宁可低估直连、不高估两段）
ANCHOR_STEP = 120.0      # 同一块面上锚点间距（NavNode 的位置分辨率）
ANCHOR_INSET = 16.0      # 锚点离面两端至少这么远（landing_safe 边距之外）
HAND_UP = 12.0           # 站在面上时手离脚面的高度（手在身侧偏下）
WALK_Y_EPS = 6.0         # 同一块面：纵向容差（像素）
STEP_X = 14.0            # 走过去能跨过的横向缝隙上限
POLE_TIP_PAD = 10.0      # 杆顶可站立的横向范围
POLE_CLIMB_SPEED = 0.55  # 爬杆速度（px/tick，整条腿留给执行器）
BEAM_PENALTY = 1.25      # 杆上位移的保守系数（比走地面更容易失败）
LAND_PAD = tuning.PLAN_WALK_X_PAD

_ENV = {}


def _anchors(lo, hi):
    """一块面上的锚点 x 列表（面 × 锚点 = 导航节点）。"""
    lo, hi = min(lo, hi), max(lo, hi)
    if hi - lo <= 2.0 * ANCHOR_INSET:
        return [0.5 * (lo + hi)]
    a, b = lo + ANCHOR_INSET, hi - ANCHOR_INSET
    n = max(2, int((b - a) // ANCHOR_STEP) + 1)
    if n <= 2:
        return [a, b]
    step = (b - a) / (n - 1)
    return [a + i * step for i in range(n)]


def _dedupe(xs):
    out = []
    for x in xs:
        if not out or x - out[-1] > 0.5:
            out.append(x)
    return out


def _envelope(stats):
    """本猫的跳跃包线 (最高升高, 最远横距)：够不到的面就别扫掠（空间粗筛）。"""
    v = _ENV.get(stats)
    if v is None:
        rise, dx = 0.0, 0.0
        for hold in tuning.PLAN_JUMP_HOLD_GEARS:
            for md in (0, 1, -1):
                arc = get_arc(stats, hold, md)
                rise = max(rise, max(-p[1] for p in arc.points))
                dx = max(dx, max(abs(p[0]) for p in arc.points))
        v = (rise, dx)
        _ENV[stats] = v
    return v


def _arc_grab(stats, lx, ly, pole, r):
    """从地面起跳抓杆：返回 (hold, move_dir, hit_tick)，无解 None。"""
    for hold in tuning.PLAN_JUMP_HOLD_GEARS:
        for md in (1, -1):
            arc = get_arc(stats, hold, md)
            # 隔着实体墙不能直接抓杆；先验证整条跳弧，再检查命中点。
            if _arc_hits_solids(arc, lx, ly, r):
                continue
            for i, (px, py) in enumerate(arc.points):
                if i < 1:
                    continue
                if pole_hit(pole, lx + px, ly + py, r):
                    return (hold, md, i + 1)
    return None


class PoleBeamRouteController:
    """执行 SurfaceGraph 给出的起跳抓杆边，避免执行时换成另一套估算轨迹。"""

    def __init__(self, pet, leg):
        self.pet = pet
        self.leg = leg
        self.target = getattr(leg.dst, "pole", None)
        self.plan = leg.plan
        self.phase = "approach"
        self.timer = 0
        self._airborne = False
        self._captured = False
        self.climber = None
        self.target_walk = None

    def _walk_horizontal_target(self):
        self.target_walk = PoleWalkRouteController(
            self.pet, pole=self.target, target_x=self.leg.dst.anchor)
        self.phase = "walk_target"

    def _update_horizontal_target(self):
        status = self.target_walk.update()
        if status == DONE:
            self.target_walk.cancel()
            self.target_walk = None
            self._captured = True
            return DONE
        if status == GIVEUP:
            return GIVEUP
        return RUNNING

    def _target_grabbed(self):
        b, p = self.pet.body, self.target
        if p is None or not b.on_pole:
            return False
        c0 = b.chunk0
        if getattr(p, "kind", None) == "vertical":
            return (abs(c0.x - p.x) <= tuning.POLE_AIRGRAB_R + 2.0
                    and p.top_y - tuning.POLE_AIRGRAB_PAD <= c0.y
                    <= p.bottom_y + tuning.POLE_AIRGRAB_PAD)
        lo, hi = p.span_x()
        return (abs(c0.y - p.cross_coord()) <= tuning.HPOLE_AIRGRAB_Y + 2.0
                and lo - tuning.POLE_AIRGRAB_PAD <= c0.x
                <= hi + tuning.POLE_AIRGRAB_PAD)

    def _aim_at_target(self):
        fsm = getattr(self.pet, "behavior", None)
        if fsm is not None and hasattr(fsm, "_air_pole_target"):
            fsm._air_pole_target = self.target

    def _climb_vertical_target(self):
        fsm = getattr(self.pet, "behavior", None)
        self.climber = getattr(fsm, "poleclimb", None)
        if self.climber is None or self.climber.pole is not self.target:
            from ..behavior.pole_climb import PoleClimber
            self.climber = PoleClimber(self.pet, self.target,
                                       getattr(self.pet, "rng", None),
                                       start="climb", no_handoff=True)
        else:
            self.climber.no_handoff = True
        self.phase = "climb"

    def update(self):
        b = self.pet.body
        self.timer += 1
        if self.target is None or self.target not in getattr(self.pet, "poles", ()):
            return GIVEUP
        if self._captured:
            return DONE

        if self.phase == "walk_target":
            return self._update_horizontal_target()

        if self.phase == "climb":
            if self.climber is None:
                return GIVEUP
            self.climber.update(want_dismount=False)
            if getattr(self.climber, "giveup", False):
                return GIVEUP
            if self.climber.phase == "tip":
                self._captured = True
                return DONE
            return RUNNING

        if self.phase == "approach":
            if not self.plan:
                return GIVEUP
            source_kind = self.plan[0]
            if source_kind == "pole":
                # ('pole', hop_plan)；hop_plan = (target pole, dir, hit tick, height tier)
                _tag, hop = self.plan
                _target, md, _hit, up = hop
                if not b.on_pole:
                    return GIVEUP
                fsm = getattr(self.pet, "behavior", None)
                # 交还当前竖/横杆控制器，但保留身体当前坐标，由计划弧直接离杆。
                if fsm is not None and getattr(fsm, "pole_ctl", None) is not None:
                    fsm._pole_release()
                self._aim_at_target()
                b.facing = 1 if md > 0 else -1
                b.pole_hop(md, move_dir=md, up=up)
                b.chunk0.cy = b.chunk1.cy = 0
                self._air_timeout = self.timer + max(90, int(_hit) + 60)
                self.phase = "air"
                return RUNNING
            if source_kind != "ground":
                return GIVEUP

            # ('ground', hold, dir, launch_x, launch_y, hit_tick)
            _tag, hold, md, launch_x, _launch_y, hit = self.plan
            if b.on_pole:
                return GIVEUP
            if not b.on_floor():
                return GIVEUP
            if abs(b.chunk1.x - launch_x) > tuning.PLAN_JUMP_TAKEOFF_EPS:
                b.walk_to(launch_x)
                return RUNNING
            b.stop_walk()
            still = (abs(b.chunk0.vx) < SETTLE_VX
                     and abs(b.chunk1.vx) < SETTLE_VX)
            if not still and self.timer < SETTLE_MAX:
                return RUNNING
            self._aim_at_target()
            b.facing = 1 if md > 0 else -1
            b.request_jump("stand", hold_ticks=hold)
            b.move_dir = md
            self.phase = "air"
            self._air_timeout = self.timer + max(90, int(hit) + 60)
            return RUNNING

        if self._target_grabbed():
            if getattr(self.target, "kind", None) == "vertical":
                # A pole_beam edge is represented by the pole-tip node. The jump
                # can catch anywhere along the rod, so climb to that node before
                # handing the route to its next leg.
                self._climb_vertical_target()
                return RUNNING
            self._walk_horizontal_target()
            return self._update_horizontal_target()
        if self.phase == "air":
            # Fetch/flee controllers can own a jump without entering the global
            # Airborne FSM state. Let this planned edge perform the same exact
            # beam contact check and attach the specified target pole in place;
            # a normal state transition here would cancel the multi-leg route.
            fsm = getattr(self.pet, "behavior", None)
            grab = getattr(fsm, "_air_pole_grab", None)
            if grab is not None and grab(route_owned=True):
                if getattr(self.target, "kind", None) == "vertical":
                    self._climb_vertical_target()
                    return RUNNING
                self._walk_horizontal_target()
                return self._update_horizontal_target()
        if b.on_pole or b.on_floor():
            # 还没起跳时不能把源杆/地面误认作到达；空中落回地面则此边失败。
            if self._airborne or self.timer > 2:
                return GIVEUP
            return RUNNING
        self._airborne = True
        if self.timer > getattr(self, "_air_timeout", 180):
            return GIVEUP
        if self.plan[0] == "pole":
            md = self.plan[1][1]
        else:
            md = self.plan[2]
        b.move_dir = md
        return RUNNING

    def cancel(self):
        b = self.pet.body
        if self.target_walk is not None:
            self.target_walk.cancel()
            self.target_walk = None
        if not self._captured:
            if self.phase == "climb" and self.climber is not None:
                self.climber.release()
            fsm = getattr(self.pet, "behavior", None)
            if (fsm is not None and getattr(fsm, "_air_pole_target", None) is self.target):
                fsm._air_pole_target = None
        b.stop_walk()


def _pole_beam_controller(pet, leg):
    """建 pole_beam 专用控制器；旧路线没有保存执行所需的发射参数时安全回退。"""
    if leg.plan and leg.plan[0] in ("ground", "pole"):
        return PoleBeamRouteController(pet, leg)
    return None


class PoleClimbRouteController:
    """执行 climb_pole 图边：只爬边上指定的竖杆，登顶即交还路线。"""

    def __init__(self, pet, leg):
        self.pet = pet
        self.pole = getattr(leg.dst, "pole", None)
        self.climber = None
        self.completed = False

    def update(self):
        if (self.pole is None
                or self.pole not in getattr(self.pet, "poles", ())):
            return GIVEUP
        if self.climber is None:
            from ..behavior.pole_climb import PoleClimber
            self.climber = PoleClimber(self.pet, self.pole,
                                       getattr(self.pet, "rng", None),
                                       no_handoff=True)
        done = self.climber.update(want_dismount=False)
        if self.climber.phase == "tip":
            self.completed = True
            return DONE
        if self.climber.giveup or done:
            return GIVEUP
        return RUNNING

    def cancel(self):
        if not self.completed and self.climber is not None:
            self.climber.release()


class PoleTipJumpRouteController:
    """从竖杆顶按 SurfaceGraph 的站立跳弧起跳并等待落地。"""

    def __init__(self, pet, leg):
        self.pet = pet
        self.goal = leg.goal()
        self.plan = leg.plan
        self.phase = "launch"
        self.move_dir = 0
        self.timer = 0
        self.airborne = False

    def update(self):
        body = self.pet.body
        self.timer += 1
        if not self.plan:
            return GIVEUP
        kind, hold, move_dir, _land_x, _land_y, ticks, _launch_x = self.plan
        if kind not in ("jump", "jumpfall", "drop", "flip"):
            return GIVEUP
        self.move_dir = int(move_dir)

        if self.phase == "launch":
            if not body.on_pole:
                return GIVEUP
            fsm = getattr(self.pet, "behavior", None)
            climber = getattr(fsm, "poleclimb", None)
            if climber is not None and climber.phase != "tip":
                return RUNNING
            # Keep the body at its real pole-tip position; HopReach's ground
            # walk/settle phase can never become ready while on a vertical rod.
            if fsm is not None:
                fsm._pole_release()
            body.facing = 1 if self.move_dir >= 0 else -1
            if kind == "drop":
                body.release_to_air(move_dir=self.move_dir)
            elif kind == "flip":
                body.backflip_launch(self.move_dir, boosted=bool(hold))
            else:
                body.tip_launch(hold_ticks=hold, move_dir=self.move_dir)
            self.phase = "air"
            self._timeout = max(90, int(ticks) + 60)
            return RUNNING

        reach_assist(self.pet, self.goal, *self.goal.pos())
        if not body.on_floor():
            self.airborne = True
            body.move_dir = self.move_dir
        elif self.airborne:
            body.stop_walk()
            return DONE
        if self.timer > getattr(self, "_timeout", 180):
            return GIVEUP
        return RUNNING

    def cancel(self):
        self.pet.body.stop_walk()


class PoleWalkRouteController:
    """横杆上的同面 walk 边由横杆控制器执行，不调用地面 WalkReach。"""

    ARRIVE_EPS = 8.0
    TIMEOUT = 900

    def __init__(self, pet, leg=None, pole=None, target_x=None, wait_stand=False):
        self.pet = pet
        self.pole = pole if pole is not None else getattr(leg.src, "pole", None)
        self.target_x = float(target_x if target_x is not None else leg.dst.anchor)
        self.wait_stand = bool(wait_stand)
        self.controller = None
        self.timer = 0

    def update(self):
        from ..world.hpole import HPoleController

        self.timer += 1
        if (self.pole is None
                or self.pole not in getattr(self.pet, "poles", ())
                or self.timer > self.TIMEOUT):
            return GIVEUP
        body = self.pet.body
        if not getattr(body, "on_pole", False):
            return GIVEUP
        fsm = getattr(self.pet, "behavior", None)
        ctl = getattr(fsm, "pole_ctl", None)
        if ctl is None or getattr(ctl, "pole", None) is not self.pole:
            ctl = HPoleController(self.pet, self.pole,
                                  getattr(self.pet, "rng", None),
                                  start="hang", start_x=body.chunk0.x)
            if fsm is not None:
                fsm.pole_ctl = ctl
        self.controller = ctl
        ctl.goal_x = self.target_x
        ctl.goal_eps = self.ARRIVE_EPS
        done = ctl.update()
        arrived = (getattr(body, "on_pole", False)
                   and abs(float(body.chunk0.x) - self.target_x) <= self.ARRIVE_EPS)
        if arrived:
            if not self.wait_stand or getattr(ctl, "phase", None) == "stand":
                ctl.goal_x = None
                ctl.goal_eps = None
                return DONE
            # A route finish may need a real StandOnBeam takeoff. Let the
            # original hang→pullup→stand transition finish at the launch point.
            return RUNNING
        if done or getattr(ctl, "giveup", False):
            return GIVEUP
        return RUNNING

    def cancel(self):
        if self.controller is not None:
            self.controller.goal_x = None
            self.controller.goal_eps = None


class PoleSurfaceFinishRouteController:
    """从杆面执行规划跳跃；落地后交回路线重规划目标。"""

    def __init__(self, pet, goal, leg):
        self.pet = pet
        self.goal = goal
        self.node = leg.src
        self.plan = leg.plan
        self.finish = leg.dst is None
        self.kind = self.plan[0] if self.plan else None
        if self.plan and self.finish:
            # finish: (jump, hold, dir, launch_x, launch_y, ticks)
            self.launch_x = float(self.plan[3])
            self.move_dir = int(self.plan[2])
            self.ticks = int(self.plan[5])
        elif self.plan:
            # edge: (kind, hold, dir, land_x, land_y, ticks, launch_x)
            self.launch_x = float(self.plan[6])
            self.move_dir = int(self.plan[2])
            self.ticks = int(self.plan[5])
        else:
            self.launch_x = 0.0
            self.move_dir = 0
            self.ticks = 0
        self.walk = None
        self.phase = "approach"
        self.timer = 0
        self.airborne = False

    def update(self):
        body = self.pet.body
        self.timer += 1
        if not self.plan or self.kind not in ("jump", "jumpfall", "drop", "flip"):
            return GIVEUP
        if self.node.kind not in ("pole_tip", "pole_h"):
            return GIVEUP
        if self.phase == "approach":
            if not body.on_pole:
                return GIVEUP
            if self.node.kind == "pole_h":
                if self.walk is None:
                    self.walk = PoleWalkRouteController(
                        self.pet, pole=self.node.pole, target_x=self.launch_x,
                        wait_stand=True)
                status = self.walk.update()
                if status != DONE:
                    return status
                self.walk.cancel()
                self.walk = None
            else:
                climber = getattr(self.pet.behavior, "poleclimb", None)
                if climber is not None and climber.phase != "tip":
                    return RUNNING
            self.phase = "launch"

        if self.phase == "launch":
            if not body.on_pole:
                return GIVEUP
            fsm = getattr(self.pet, "behavior", None)
            if fsm is not None:
                fsm._pole_release()
            body.facing = 1 if self.move_dir >= 0 else -1
            if self.kind == "drop":
                body.release_to_air(move_dir=self.move_dir)
            elif self.kind == "flip":
                body.backflip_launch(self.move_dir, boosted=bool(self.plan[1]))
            else:
                body.tip_launch(hold_ticks=self.plan[1], move_dir=self.move_dir)
            self.phase = "air"
            self._timeout = max(90, self.ticks + 60)
            return RUNNING

        gx, gy = self.goal.pos()
        reach_assist(self.pet, self.goal, gx, gy)
        if not body.on_floor():
            self.airborne = True
            body.move_dir = self.move_dir
        elif self.airborne:
            body.stop_walk()
            return DONE
        if self.timer > getattr(self, "_timeout", 180):
            return GIVEUP
        return RUNNING

    def cancel(self):
        if self.walk is not None:
            self.walk.cancel()
            self.walk = None
        self.pet.body.stop_walk()


def _hop_controller(pet, leg):
    '''按边自带的实测轨迹建 HopReachController（先走到起跳锚点再起跳）。'''
    if leg.plan is None:
        return None
    if getattr(leg.src, "kind", None) == "pole_tip":
        return PoleTipJumpRouteController(pet, leg)
    if getattr(leg.src, "kind", None) == "pole_h":
        return PoleSurfaceFinishRouteController(pet, leg.goal(), leg)
    k, hold, md, land_x, _ly, ticks, launch_x = leg.plan
    return HopReachController(pet, leg.goal(), (k, hold, md, launch_x, land_x, ticks))


def _point_in_solids(x, y, shrink=1.0):
    """点是不是落在庇护所墙体 / 关上的门里面（各边向内收，避免贴着面误判）。"""
    for (a0, b0, a1, b1) in chunkphys.cat_solids():
        a0, a1 = sorted((float(a0), float(a1)))
        b0, b1 = sorted((float(b0), float(b1)))
        if a0 + shrink < x < a1 - shrink and b0 + shrink < y < b1 - shrink:
            return True
    return False


def _walk_blocked(x0, x1, y):
    """同一块面上从一个锚点走到另一个：中间会不会被庇护所墙体挡住。

    把猫看成 [x0..x1] × [y-WALK_BODY_H, y] 一条扫掠带：高过脚面一步以上的
    实心块算墙，矮的（庇护所底墙 5.6px）只是台阶，底边高过猫头的（门口上方
    那段外墙 / 走廊层的缺口）也放行 —— 于是「屋外 → 门洞 → 屋内」这一条正通。
    """
    lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
    for (a0, b0, a1, b1) in chunkphys.cat_solids():
        a0, a1 = sorted((float(a0), float(a1)))
        b0, b1 = sorted((float(b0), float(b1)))
        if a1 <= a0 or b1 <= b0:
            continue
        if a1 <= lo or a0 >= hi:
            continue
        if b1 <= y - tuning.WALK_BODY_H:
            continue
        if b0 >= y - tuning.WALK_STEP_UP:
            continue
        return True
    return False


def _merge_spans(spans):
    """把 x 区间合并成互不相邻的几段（走带切分用）。"""
    out = []
    for a, b in sorted(spans):
        if a > b:
            a, b = b, a
        if out and a <= out[-1][1] + 0.5:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _roof_under(pet, x, y):
    """(x,y) 站在哪间庇护所的屋顶上；不是则 None。返回 (x0, x1)。"""
    for sh in getattr(pet, "shelters", ()) or ():
        if abs(y - sh.y) <= 3.0 and sh.x <= x <= sh.x + sh.w:
            return (sh.x, sh.x + sh.w)
    return None


def _reach_from_surface(stats, y0, lo, hi, start_x, gx, gy):
    """站在支撑面 y0（可走区间 [lo,hi]）的锚点 start_x 上能不能够到 (gx,gy)。

    返回 (耗时, 体力)；够不到 None。纯几何（不读实时 body），所以可测试、
    也可以拿去问「我落在那块面上以后够不够得到」。start_x 是真实起点（锚点），
    所以「走过去伸手」那段是真实耗时，不再恒等于 0。
    """
    if hi < lo:
        lo, hi = hi, lo
    best = None
    wx = min(max(gx, lo), hi)
    hand_y = y0 - HAND_UP
    # ① 走过去伸手。快速收尾也要遵守实体墙阻挡，不能穿墙到目标侧。
    if (abs(gy - hand_y) <= tuning.GRAB_REACH + 6.0
            and abs(gx - wx) <= tuning.GRAB_REACH
            and not _walk_blocked(start_x, wx, y0)):
        t = abs(wx - start_x) / tuning.PLAN_WALK_SPEED
        best = (t, t * tuning.PLAN_EN_RATE_LIGHT, ("reach", wx))
    # ② 面上起跳（土狼跳那套弧线族）：起跳点取锚点附近几档
    launch_y = y0 - takeoff_c0_h(stats)
    xs = _dedupe(sorted(clampf(start_x + k * tuning.PLAN_WALK_X_PAD, lo, hi)
                        for k in (0.0, -1.0, 1.0)))
    for hold in tuning.PLAN_JUMP_HOLD_GEARS:
        for md in (0, 1, -1):
            arc = get_arc(stats, hold, md)
            for lx in xs:
                # 起跳前必须在墙的同一侧，且跳弧不能穿过实体墙。
                if _walk_blocked(start_x, lx, y0):
                    continue
                if _arc_hits_solids(arc, lx, launch_y):
                    continue
                hit = sweep_hit(arc, gx - lx, gy - launch_y, tuning.GRAB_REACH)
                if hit is None:
                    continue
                t = (abs(lx - start_x) / tuning.PLAN_WALK_SPEED + hit
                     + tuning.PLAN_STARTUP_TICKS)
                e = (t * tuning.PLAN_EN_RATE_LIGHT
                     + hit * tuning.PLAN_EN_RATE_VIGOROUS)
                if best is None or t < best[0]:
                    best = (t, e, ("jump", hold, md, lx, launch_y, hit))
    return best


# ══════════════════════════ 节点与边 ══════════════════════════

class SurfaceNode:
    """一个导航节点：某块支撑面上的一个锚点（NavNode = surf_id + x_anchor）。"""

    __slots__ = ("kind", "y", "lo", "hi", "pole", "here", "anchor", "sid", "nid")

    def __init__(self, kind, y, lo, hi, pole=None, here=False, anchor=None, sid=""):
        self.kind = kind          # floor / deck / pole_tip / pole_h
        self.nid = -1             # 在本图里的下标（NavGraph 边指向它）
        self.y = float(y)
        self.lo = float(min(lo, hi))
        self.hi = float(max(lo, hi))
        self.pole = pole
        self.here = here          # 猫此刻站在这个锚点上
        self.sid = sid            # 所属支撑面 id（同 id = 同一块面）
        self.anchor = float(clampf((self.lo + self.hi) * 0.5
                                   if anchor is None else anchor, self.lo, self.hi))

    @property
    def width(self):
        return self.hi - self.lo

    def clamp(self, x):
        return clampf(x, self.lo, self.hi)

    def near(self, x, pad=0.0):
        return self.lo - pad <= x <= self.hi + pad

    def key(self):
        return (self.kind, round(self.y, 1), round(self.lo, 1),
                round(self.hi, 1), round(self.anchor, 1))

    def __repr__(self):
        return "<%s y=%.0f [%.0f..%.0f] @%.0f>" % (self.kind, self.y, self.lo,
                                                   self.hi, self.anchor)


def _walkable_span(node):
    """Return the real stand/walk interval for a support node."""
    lo, hi = float(node.lo), float(node.hi)
    if node.kind == "pole_h":
        from ..world.hpole import WALK_MARGIN
        lo += WALK_MARGIN
        hi -= WALK_MARGIN
        if hi < lo:
            lo = hi = (lo + hi) * 0.5
    return lo, hi


class SurfaceEdge:
    """一次位移。字段就是文档里要求的那几项。"""

    __slots__ = ("kind", "src", "dst", "time", "energy", "risk", "lands", "pose",
                 "plan", "land_x")

    def __init__(self, kind, src, dst, time, energy, land_x, pose, plan=None, risk=0.0):
        self.kind = kind          # walk / jump / drop / climb_pole / pole_beam / finish
        self.src = src
        self.dst = dst            # None＝终点是目标点（finish）
        self.time = float(time)
        self.energy = float(energy)
        self.risk = float(risk)   # 0..1 失败倾向
        self.lands = kind in ("jump", "drop", "pole_beam")
        self.pose = pose          # 终点姿态：stand / crouch / hang / tip
        self.plan = plan          # 执行器要的原始轨迹（land_sweep 的返回值等）
        self.land_x = float(land_x)

    def goal(self):
        """这条边跑完之后猫应该把哪个点当目标（执行器用）。"""
        if self.dst is None:
            return None
        return point_goal(self.land_x, self.dst.y, contact="travel")

    def __repr__(self):
        return "<%s→%s %.1ft>" % (self.kind, self.dst, self.time)


class SurfaceGraph(NavGraph):
    """锚点图：节点 + 有向边。懒构建，按几何版本缓存。

    它是 `NavGraph` 的一份实例（文档 §7 / §21–§27：蜥蜴与蛞蝓猫共用同一套
    移动图与寻路器）。蜥蜴那边的邻接表是 list[list]、边是 NavigationEdge；
    这边邻接表是 dict（历史调用方 / 测试都用 `g.adj.get(i, ())`）、边是
    SurfaceEdge（多带实测轨迹 plan、落点 land_x、终点姿态 pose）。形状不同，
    算法同一份：反向邻接 radj、SCC、`can_return` 全部来自 NavGraph。

    几何也不再自己扫一遍：面从 `planning.navgeom.NavGeometry`（与蜥蜴 / 猫
    共用的那一份）取，于是「这里有没有一块面 / 一根杆 / 一面墙」全世界只有一个答案。
    """

    __slots__ = ("start", "_here_sid", "_surf", "_returnable", "geom",
                 "nav_version")

    def __init__(self):
        self.nodes = []
        self.adj = {}             # index → [SurfaceEdge]
        self.start = None
        self._here_sid = None
        self._surf = {}           # sid → dict(kind,y,lo,hi,pole,idx[])
        self._returnable = set()
        self.geom = None          # 本图编译时用的 NavGeometry 快照
        self.nav_version = 0

    def add_node(self, node):
        node.nid = len(self.nodes)
        self.nodes.append(node)
        self.adj[node.nid] = []
        return node.nid

    def add_edge(self, i, edge):
        self.adj[i].append(edge)

    def idx(self, node):
        """O(1)：节点自己记着下标（旧实现是 list.index() 线性扫描，在
        _compute_returnable / route_to 的热路径里被调用了 O(E) 次）。"""
        nid = getattr(node, "nid", -1)
        if 0 <= nid < len(self.nodes) and self.nodes[nid] is node:
            return nid
        return self.nodes.index(node)

    def _finish(self):
        """边全部接好之后，把图交给 NavGraph：建反向邻接 + SCC + 反向可达。

        `_returnable` = 「从哪些节点还能走回起点」= NavGraph 的反向可达集合，
        与蜥蜴侧的 `can_return` 是同一份实现（原版 accessibility mapping 的
        等价物），不再各写一个 BFS。
        """
        NavGraph.__init__(self, self.nodes, self.adj, version=self.nav_version,
                          pos=lambda i: (self.nodes[i].anchor, self.nodes[i].y))
        if self.start is not None:
            self._returnable = self._reachers(self.start)
        return self

    # ── 构建 ──
    def _add_surface(self, sid, kind, y, lo, hi, pole=None):
        """一块面 → 一串锚点节点（相互之间用 walk 边连成链）。"""
        lo, hi = min(lo, hi), max(lo, hi)
        xs = _anchors(lo, hi)
        idxs = []
        for x in xs:
            idxs.append(self.add_node(SurfaceNode(kind, y, lo, hi, pole=pole,
                                                  anchor=x, sid=sid)))
        # 同面相邻锚点：走过去
        for a, b in zip(idxs, idxs[1:]):
            d = abs(self.nodes[b].anchor - self.nodes[a].anchor)
            if d < 0.5:
                continue
            # Surface 上也可能有另一块实体墙横在中间（例如多块墙体叠在一层
            # 横杆/平台之间）。同面节点并不等于物理上能直走；漏掉这项检查会让
            # A* 生成穿墙 walk，执行器撞墙后反复重规划，永远到不了后续跳跃段。
            if _walk_blocked(self.nodes[a].anchor, self.nodes[b].anchor,
                             self.nodes[a].y):
                continue
            t = d / tuning.PLAN_WALK_SPEED
            self.add_edge(a, SurfaceEdge("walk", self.nodes[a], self.nodes[b], t,
                                         t * tuning.PLAN_EN_RATE_LIGHT,
                                         self.nodes[b].anchor, "stand"))
            self.add_edge(b, SurfaceEdge("walk", self.nodes[b], self.nodes[a], t,
                                         t * tuning.PLAN_EN_RATE_LIGHT,
                                         self.nodes[a].anchor, "stand"))
        self._surf[sid] = dict(kind=kind, y=float(y), lo=lo, hi=hi, pole=pole,
                               idx=idxs)
        return idxs

    def _add_shelter_ground(self, k, sh, start_node, WL):
        """屋外两侧的走带（floor）：只有这间屋子确实挡住猫脚下这条走道时才加，
        于是「屋外 → 门洞 → 屋内」由 _link_gaps 的避墙检查连成一条 walk 链。

        屋顶（deck）与屋里地面（shelter）不在这里 —— 它们是全场共用的几何，
        直接从 NavGeometry 取（见 build），免得同一条庇护所屋顶有两个定义。
        """
        gy = start_node.y
        cuts = _merge_spans(sh.cut_span(gy))
        if not cuts:
            return                        # 猫脚下这条走道没被挡：屋里屋外本来就通
        seg, cur = [], 0.0
        for a, b in cuts:
            if a - cur >= 4.0:
                seg.append((cur, a))
            cur = max(cur, b)
        if WL - cur >= 4.0:
            seg.append((cur, WL))
        for j, (a, b) in enumerate(seg):
            self._add_surface("sground:%d:%d" % (k, j), "floor", gy,
                              max(a, 0.0), min(b, WL))

    def start_at(self, x):
        """把「起点」指向猫脚下这块面上离它最近的锚点。

        图本身不因猫移动而重建（锚点是固定的）；猫到该锚点之间那一小段走路
        由调用方按真实起点补进总代价里 —— 于是「走到起跳点」既不恒等于 0，
        也不用每帧重建整张图。
        """
        idxs = self._surf[self._here_sid]["idx"] if self._here_sid else []
        if not idxs:
            return self.start
        k = min(idxs, key=lambda i: abs(self.nodes[i].anchor - x))
        for i in idxs:
            self.nodes[i].here = (i == k)
        self.start = k
        return k

    @classmethod
    def build(cls, pet, start_node):
        g = cls()
        WL = float(pet._WL or 0.0)
        body = pet.body
        sx = clampf(getattr(body.chunk1, "x", 0.0), start_node.lo, start_node.hi)
        g._here_sid = "here"
        g._add_surface("here", start_node.kind, start_node.y,
                       start_node.lo, start_node.hi)
        g.start = 0

        # 面从**共用几何**取（文档 §21：不再自己扫 platforms / poles / shelters）。
        # NavGeometry 由 platform / pole / wall / shelter 编译一次，蜥蜴与蛞蝓猫
        # 看到的是同一份 Surface 对象；这里只做「转成蛞蝓猫的 kind」的映射。
        geom = navgeom.nav_geometry(pet.window)
        g.geom = geom
        g.nav_version = geom.version
        for s in geom.surfaces:
            if s.kind == navgeom.PLATFORM:
                lo, hi = max(s.lo, 0.0), min(s.hi, WL)
                if hi - lo < 2.0:
                    continue
                if (abs(s.y - start_node.y) <= WALK_Y_EPS
                        and lo >= start_node.lo - 1.0 and hi <= start_node.hi + 1.0):
                    continue              # 就是猫脚下那块面，已经在图里了
                g._add_surface("deck:%s" % s.sid, "deck", s.y, lo, hi)
            elif s.kind == navgeom.SHELTER_ROOF:
                if s.hi - s.lo >= 2.0 and s.y > 4.0:
                    g._add_surface("sroof:%s" % s.sid, "deck", s.y, s.lo, s.hi)
            elif s.kind == navgeom.SHELTER_FLOOR and not s.door:
                if s.hi - s.lo >= 2.0:
                    g._add_surface("shell:%s" % s.sid, "shelter", s.y, s.lo, s.hi)
            elif s.kind == navgeom.VPOLE:
                if s.top <= 0.0:
                    continue              # 杆顶贴屏幕顶：站不住
                g._add_surface("vpole:%s" % s.sid, "pole_tip", s.top,
                               s.x - POLE_TIP_PAD, s.x + POLE_TIP_PAD, pole=s.pole)
            elif s.kind == navgeom.HPOLE:
                lo, hi = max(s.lo, 0.0), min(s.hi, WL)
                if hi - lo < 2.0:
                    continue
                g._add_surface("hpole:%s" % s.sid, "pole_h", s.y, lo, hi, pole=s.pole)

        # 屋外两侧的走带：按「猫脚下这一层」把被庇护所挡住的地面切成几段。
        # 这是每只猫自己的东西（依赖它此刻站在哪一层），但用的仍是同一份庇护所几何。
        for k, sh in enumerate(getattr(pet, "shelters", ()) or ()):
            g._add_shelter_ground(k, sh, start_node, WL)

        g._link_gaps()
        g._link_jumps(pet)
        g._link_poles(pet)
        g._link_beams(pet)
        g.start_at(sx)
        return g._finish()

    def _link_gaps(self):
        """两块面同高、缝 ≤ STEP_X：走过去（旧版要求真重叠，8px 小缝直接判不连通）。"""
        flat = ("floor", "deck", "pole_h", "shelter")
        sids = list(self._surf)
        for ii, sa in enumerate(sids):
            a = self._surf[sa]
            if a["kind"] not in flat:
                continue
            for sb in sids[ii + 1:]:
                b = self._surf[sb]
                if b["kind"] not in flat or abs(a["y"] - b["y"]) > WALK_Y_EPS:
                    continue
                if a["hi"] < b["lo"]:
                    if b["lo"] - a["hi"] > STEP_X:
                        continue
                elif b["hi"] < a["lo"]:
                    if a["lo"] - b["hi"] > STEP_X:
                        continue
                # 重叠也算同一块面（屋外走带 / 屋里地面会叠在一起）
                best = None
                for ka in a["idx"]:
                    for kb in b["idx"]:
                        d = abs(self.nodes[kb].anchor - self.nodes[ka].anchor)
                        if best is None or d < best[0]:
                            best = (d, ka, kb)
                if best is None:
                    continue
                d, ka, kb = best
                if _walk_blocked(self.nodes[ka].anchor, self.nodes[kb].anchor,
                                 a["y"]):
                    continue              # 中间隔着庇护所墙 / 关上的门：走不过去
                t = d / tuning.PLAN_WALK_SPEED
                self.add_edge(ka, SurfaceEdge("walk", self.nodes[ka], self.nodes[kb], t,
                                              t * tuning.PLAN_EN_RATE_LIGHT,
                                              self.nodes[kb].anchor, "stand"))
                self.add_edge(kb, SurfaceEdge("walk", self.nodes[kb], self.nodes[ka], t,
                                              t * tuning.PLAN_EN_RATE_LIGHT,
                                              self.nodes[ka].anchor, "stand"))

    def _link_jumps(self, pet):
        """锚点 → 另一块面（或更低的面）的锚点：交给实测轨迹族 land_sweep。"""
        stats = pet.cat.stats
        off = takeoff_c0_h(stats)
        rise_max, dx_max = _envelope(stats)
        # The shelter interior is a real landing surface.  With the centered
        # doorway its floor is separated from the outside floor by the lower
        # door jamb, so a cat must jump through the opening before dropping
        # onto the interior.  Omitting ``shelter`` here made the graph contain
        # the room but no edge into it; StormSeekShelter then treated every
        # shelter as unreachable and the cat waited outside until drowning.
        kinds = ("floor", "deck", "pole_h", "pole_tip", "shelter")
        span_pad = dx_max + 4.0 * tuning.PLAN_WALK_X_PAD
        # 空间粗筛（文档 §22/§36）：候选面按 x 排好，只在自己的横向窗口里取 ——
        # 旧实现是节点两两比（40 块平台就是 2000+ 次 land_sweep 级别的判定）。
        cand = [n for n in self.nodes if n.kind in kinds]
        cand.sort(key=lambda n: n.anchor)
        cx = [n.anchor for n in cand]
        reach_x = span_pad + rise_max + tuning.GRAB_REACH
        for a in cand:
            i = a.nid
            launch_y = a.y - off
            k0 = bisect.bisect_left(cx, a.anchor - reach_x)
            k1 = bisect.bisect_right(cx, a.anchor + reach_x)
            for b in cand[k0:k1]:
                j = b.nid
                if i == j:
                    continue
                up = a.y - b.y                 # >0：目标更高
                same_level_block = (abs(up) <= 2.0
                                    and _walk_blocked(a.anchor, b.anchor, a.y))
                same_surface_jump = (a.sid == b.sid and same_level_block)
                if a.sid == b.sid and not same_surface_jump:
                    continue
                if abs(up) <= 2.0 and not same_level_block:
                    continue                   # 同高且没有墙：walk 已经负责
                if up > rise_max + tuning.GRAB_REACH:
                    continue                   # 高过一个跳跃的极限（空间粗筛）
                if abs(b.anchor - a.anchor) > span_pad + abs(up):
                    continue                   # 横向太远（空间粗筛）
                if same_surface_jump:
                    # Same-surface wall crossings must take off on the source
                    # side. Sampling around the destination would ask the cat
                    # to walk through the very wall this edge is meant to jump.
                    direction = 1.0 if b.anchor > a.anchor else -1.0
                    want_launch = a.anchor + direction * min(
                        60.0, abs(b.anchor - a.anchor) * 0.45)
                    launches = self._launches(a, want_launch, launch_y)
                else:
                    launches = self._launches(a, b.anchor, launch_y)
                r = land_sweep(stats, [(b.lo, b.y, b.hi)], launches,
                               want=(b.anchor, b.y), land_off=off)
                if r is None:
                    continue
                # 轨迹按「真实起跳点」摆正后再查地形：
                # land_sweep 返回 (kind, hold, md, land_x, land_y, ticks, launch_x)，
                # 不能拿落点当起跳点，否则弧线会被挪到墙的另一侧而漏判。
                _rk, rh, rmd, _rland, _rly, _rticks, rlx = r
                if _walk_blocked(a.anchor, rlx, a.y):
                    continue
                if _rk == "jumpfall":
                    arc = get_jump_fall_arc(stats, rh, rmd)
                elif _rk == "drop":
                    arc = get_drop_arc(stats, rmd)
                elif _rk == "flip":
                    arc = get_backflip_arc(stats, rmd, bool(rh))
                else:
                    arc = get_arc(stats, rh, rmd)
                if _arc_hits_solids(arc, rlx, launch_y):
                    continue
                kind, hold, md, land_x, _ly, ticks, launch_x = r
                if not landing_safe(land_x, b.lo, b.hi):
                    continue                   # 落点贴着平台边：这只猫不愿意赌
                if abs(land_x - b.anchor) > max(LAND_PAD, ANCHOR_STEP):
                    continue                   # 落到别的锚点去了：那条边在管
                t = (abs(launch_x - a.anchor) / tuning.PLAN_WALK_SPEED
                     + ticks + tuning.PLAN_STARTUP_TICKS)
                e = t * tuning.PLAN_EN_RATE_LIGHT + ticks * tuning.PLAN_EN_RATE_VIGOROUS
                risk = 0.15 if kind == "flip" else 0.05
                ekind = "jump" if (up > 0.0 or same_surface_jump) else "drop"
                self.add_edge(i, SurfaceEdge(ekind, a, b, t, e, land_x, "crouch",
                                             plan=r, risk=risk))

    def _link_poles(self, pet):
        """沿竖杆爬上杆顶（climb_pole）。"""

        def pole_blocked(pole, y0, y1):
            """竖杆穿过实心墙时，不生成穿墙的爬杆边。"""
            x = float(pole.x)
            lo, hi = sorted((float(y0), float(y1)))
            # 贴着墙边是合法的攀爬面；只有进入矩形内部才算阻挡。
            pad = 2.5
            for x0, yy0, x1, yy1 in chunkphys.cat_solids():
                x0, x1 = sorted((float(x0), float(x1)))
                yy0, yy1 = sorted((float(yy0), float(yy1)))
                if x0 + pad < x < x1 - pad and hi > yy0 and lo < yy1:
                    return True
            return False

        for i, a in enumerate(self.nodes):
            for j, b in enumerate(self.nodes):
                if a.sid == b.sid or b.kind != "pole_tip" or b.pole is None:
                    continue
                pole = b.pole
                if b.y >= a.y - 2.0:
                    continue
                if not pole.touches_support_y(a.y):
                    continue
                if abs(pole.bx - a.anchor) > tuning.POLE_TRANSPORT_NEAR:
                    continue
                if pole_blocked(pole, a.y, b.y):
                    continue
                # 到杆底的走位也必须在同一侧，不能穿过实体墙后再“自动抓杆”。
                if _walk_blocked(a.anchor, pole.bx, a.y):
                    continue
                rise = a.y - b.y
                t = (abs(pole.bx - a.anchor) / tuning.PLAN_WALK_SPEED
                     + rise / POLE_CLIMB_SPEED + tuning.PLAN_STARTUP_TICKS)
                self.add_edge(i, SurfaceEdge("climb_pole", a, b, t * BEAM_PENALTY,
                                             t * tuning.PLAN_EN_RATE_VIGOROUS,
                                             pole.bx, "tip"))

    def _link_beams(self, pet):
        """杆间跳跃 / 地面起跳抓杆：空中贴到另一根杆就抓住（pole_beam）。"""
        stats = pet.cat.stats
        r = tuning.POLE_AIRGRAB_R
        off = takeoff_c0_h(stats)
        for i, a in enumerate(self.nodes):
            for j, b in enumerate(self.nodes):
                if a.sid == b.sid or b.kind not in ("pole_tip", "pole_h") or b.pole is None:
                    continue
                if a.pole is not None and a.pole is b.pole:
                    continue
                if a.kind in ("pole_tip", "pole_h"):
                    # pole_tip 上的胸块实际位于杆顶以下一个身体连接长度；
                    # 横杆空中抓取则胸块就在横杆高度。规划与执行必须使用同一起点。
                    launch_y = (a.y - float(getattr(pet.body, "_conn_stand", 17.0))
                                if a.kind == "pole_tip" else a.y)
                    plan = hop_plan(stats, [b.pole], a.anchor, launch_y,
                                    grab=r, want=(b.anchor, b.y))
                    if plan is None:
                        continue
                    # hop_plan 只负责选择命中哪根杆；这里补上完整杆间弧线的
                    # 实体墙检查，避免隔墙跳杆。
                    _target, hmd, _hticks, hup = plan
                    hop_arc = get_pole_hop_arc(stats, hmd, hup)
                    if _arc_hits_solids(hop_arc, a.anchor, launch_y):
                        continue
                    hit = plan[2]
                    route_plan = ("pole", plan)
                else:
                    launch_y = a.y - off
                    grab_plan = _arc_grab(stats, a.anchor, launch_y, b.pole, r)
                    if grab_plan is None:
                        continue
                    hold, md, hit = grab_plan
                    route_plan = ("ground", hold, md, a.anchor, launch_y, hit)
                t = hit + tuning.PLAN_STARTUP_TICKS
                self.add_edge(i, SurfaceEdge("pole_beam", a, b, t * BEAM_PENALTY,
                                             t * tuning.PLAN_EN_RATE_VIGOROUS,
                                             b.anchor, "hang", plan=route_plan,
                                             risk=0.5))

    @staticmethod
    def _launches(a, want, launch_y):
        lo, hi = _walkable_span(a)
        xs = []
        for k in (-2, -1, 0, 1, 2):
            x = min(max(want + k * 24.0, lo), hi)
            if x not in xs:
                xs.append(x)
        return [(x, launch_y) for x in xs[:5]]

    def _compute_returnable(self):
        """反向可达：从哪些节点能走回起点（原版 accessibility 的「能不能再回来」）。

        保留旧名字；实现已经换成 NavGraph 的反向可达（`_reachers`，与蜥蜴侧
        `can_return` 同一份）。旧版本是本地重写的一份反向 BFS，还要顺着
        `self.nodes.index()` 线性找下标。
        """
        if self.start is not None:
            self._returnable = self._reachers(self.start)
        return self._returnable

    # ── 寻路 ──
    def route_to(self, goal_point, stats, pers=None, context=None):
        """Dijkstra：起面 → 目标点。返回 (legs, time, energy)；到不了 None。

        finish 是一条普通的 terminal 边：所有可能路径按代价比较完才收尾，
        不再「一弹出就返回」（那样只保证看见了，不保证整条路最便宜）。

        ``context``（NavContext）把**动态代价**接进来：威胁与拥挤沿边采样后
        折成 tick 当量（见 planning/threat.py / crowd.py）。取食 / 玩耍 / 社交 /
        逃跑全都自动避开危险和拥堵 —— 不用每个行为各写一次避让。
        """
        if self.start is None or not self.nodes:
            return None
        gx, gy = goal_point
        best = {self.start: (0.0, 0.0, 0.0, ())}     # idx → (cost, time, energy, path)
        done = set()
        heap = [(0.0, self.start)]
        fin = None
        one_way_fin = None
        while heap:
            c0, cur = heapq.heappop(heap)
            rec = best.get(cur)
            if rec is None or c0 > rec[0] + 1e-9 or cur in done:
                continue
            if fin is not None and fin[0] <= c0 + 1e-9:
                break                            # 剩下的都比已知收尾贵
            done.add(cur)
            _c, t0, e0, path = rec
            node = self.nodes[cur]
            # Horizontal beams are wider than the cat's supported standing
            # range: HPoleController keeps stand/walk motion inside its end
            # margin. A finish jump planned from the physical endpoint can
            # otherwise choose an unreachable takeoff x, leaving RouteExecutor
            # walking against the beam clamp forever. Keep the graph surface
            # geometry intact for hanging/grabbing, but constrain stand-jump
            # launch samples to the controller's actual walk band.
            fin_lo, fin_hi = _walkable_span(node)
            fin_est = _reach_from_surface(stats, node.y, fin_lo, fin_hi,
                                          node.anchor, gx, gy)
            if fin_est is not None:
                legs = list(path) + [SurfaceEdge("finish", node, None, fin_est[0],
                                                 fin_est[1], node.anchor, "reach",
                                                 plan=fin_est[2])]
                fcost = c0 + route_cost(edge_for("finish", fin_est[0], fin_est[1]), pers)
                result = (fcost, legs, (t0 + fin_est[0]) * OPTIMISM,
                          (e0 + fin_est[1]) * OPTIMISM)
                if cur in self._returnable:
                    if fin is None or fcost < fin[0]:
                        fin = result
                elif one_way_fin is None or fcost < one_way_fin[0]:
                    one_way_fin = result
            for e in self.edges(cur):
                if e.dst is None:
                    continue
                j = self.idx(e.dst)
                if j in done:
                    continue
                nc = (c0 + route_cost(edge_for(e.kind, e.time, e.energy), pers)
                      + dynamic_edge_cost(e, context))
                old = best.get(j)
                if old is None or nc < old[0] - 1e-9:
                    best[j] = (nc, t0 + e.time, e0 + e.energy, path + (e,))
                    heapq.heappush(heap, (nc, j))
        if fin is None and one_way_fin is None:
            return None
        if fin is None:
            fin = one_way_fin
        return (fin[1], fin[2], fin[3])

    # ── 逃生路线（文档 §六 Escape Goal）──
    def escape_route(self, threat_xy, context, pers=None,
                     min_safety=None, min_dist=None):
        """威胁下「我该往哪逃」：遍历节点找**安全节点**，不是算一个 x。

        旧口径（FSM._flee_target_x）是「当前 x + away * FLEE_GAP」再 clamp 到
        可行走范围。平地左右跑还行，放到真正的地形上就是「往右跑 → 撞墙 →
        停住 → 蜥蜴追过来 → 又往右跑」。这里改成：

            威胁出现 → 问「哪个节点安全」→ A* 用**动态代价**走过去

        安全 = 安全度 exp(-danger) 过线、离威胁够远、且从那里还能走回来
        （原版 accessibility mapping）。评分再加死胡同与拥挤两项 ——
        逃到死路等于把敌人引过来，而几只猫同时往同一条路逃会互相堵。

        返回 (legs, time, energy)；一个候选都没有则 None（调用方回落旧口径）。
        """
        if self.start is None or not self.nodes:
            return None
        tf = getattr(context, "threat_field", None)
        cf = getattr(context, "traffic_field", None)
        me = getattr(context, "me", None)
        lo_safety = tuning.ESCAPE_MIN_SAFETY if min_safety is None else float(min_safety)
        lo_dist = tuning.ESCAPE_MIN_DIST if min_dist is None else float(min_dist)
        tx, ty = float(threat_xy[0]), float(threat_xy[1])
        best = {self.start: (0.0, 0.0, 0.0, ())}
        done = set()
        heap = [(0.0, self.start)]
        out = None
        out_score = float("inf")
        while heap:
            c0, cur = heapq.heappop(heap)
            rec = best.get(cur)
            if rec is None or c0 > rec[0] + 1e-9 or cur in done:
                continue
            if out is not None and c0 > out_score:
                break                            # 剩下的都更贵，不用看了
            done.add(cur)
            _c, t0, e0, path = rec
            if path and cur != self.start and cur in self._returnable:
                node = self.nodes[cur]
                danger = tf.danger_at(node.anchor, node.y) if tf is not None else 0.0
                if (math.exp(-danger) >= lo_safety
                        and self._threat_dist(node, tx, ty) >= lo_dist):
                    score = c0 + danger * tuning.ESCAPE_DANGER_W
                    score += self._dead_end_penalty(cur)
                    if cf is not None:
                        score += (cf.point_cost(node.anchor, node.y, me)
                                  * tuning.ESCAPE_CROWD_W)
                    if score < out_score:
                        out_score = score
                        out = (list(path), t0, e0)
            for e in self.edges(cur):
                if e.dst is None:
                    continue
                j = self.idx(e.dst)
                if j in done:
                    continue
                nc = (c0 + route_cost(edge_for(e.kind, e.time, e.energy), pers)
                      + dynamic_edge_cost(e, context))
                old = best.get(j)
                if old is None or nc < old[0] - 1e-9:
                    best[j] = (nc, t0 + e.time, e0 + e.energy, path + (e,))
                    heapq.heappush(heap, (nc, j))
        if out is None:
            return self._panic_route(best, tx, ty)
        return out

    @staticmethod
    def _threat_dist(node, tx, ty) -> float:
        return math.hypot(node.anchor - tx, node.y - ty)

    def _dead_end_penalty(self, idx) -> float:
        """死胡同（只有一条出边）扣分：逃进去等于把蜥蜴引过来然后无路可走。"""
        n = 0
        for e in self.edges(idx):
            if e.dst is not None:
                n += 1
                if n > 1:
                    return 0.0
        return tuning.ESCAPE_DEAD_END_PENALTY

    def _panic_route(self, best, tx, ty):
        """没有节点够安全（多半是被围住）：退一步，去离它最远的可达节点。

        仍然走图 —— 不是「朝反方向跑一段」，那样只会撞墙。
        """
        far, fd = None, -1.0
        for j in best:
            if j == self.start or j not in self._returnable:
                continue
            d = self._threat_dist(self.nodes[j], tx, ty)
            if d > fd:
                far, fd = j, d
        if far is None:
            return None
        _c, t0, e0, path = best[far]
        if not path:
            return None
        return (list(path), t0, e0)


class RoutePlan:
    """一条多段路线：original_goal + legs + current_leg。

    执行器只跑当前 leg，跑完 current_leg += 1；**只有 original_goal 被满足才算结束**
    （旧版把 legs[0] 的落点当终点，跳上去就发呆）。
    """

    __slots__ = ("original_goal", "legs", "current_leg", "time", "energy")

    def __init__(self, original_goal, legs, time, energy):
        self.original_goal = original_goal
        self.legs = list(legs)
        self.current_leg = 0
        self.time = float(time)
        self.energy = float(energy)

    def leg(self):
        if 0 <= self.current_leg < len(self.legs):
            return self.legs[self.current_leg]
        return None

    def advance(self):
        self.current_leg += 1
        return self.leg()

    def kinds(self):
        return [e.kind for e in self.legs]

    # ── 旧调用兼容：第一段的落点即「眼下的执行目标」 ──
    @property
    def goal(self):
        return self.legs[0].goal()

    @property
    def land_x(self):
        return float(self.legs[0].land_x)

    @property
    def y(self):
        e = self.legs[0]
        return float(e.land_x if e.dst is None else e.dst.y)

    @property
    def deck(self):
        e = self.legs[0]
        return None if e.dst is None else (e.dst.lo, e.dst.y, e.dst.hi)

    def __repr__(self):
        return "<RoutePlan %s>" % (self.kinds(),)


def _nav_version(pet):
    """本帧的**导航几何版本**：平台 / 杆 / 墙 / 庇护所真的变了才 +1。

    旧缓存键里塞了 `world_version` —— 世界每 tick 都在变（猫眨眼、果子掉、
    鼠标动都算），于是「平台没动、猫也没动」的整张图每帧被丢掉重建。文档
    §24/§26：图与路线的身份只跟导航几何（NavGeometry.version）走。
    """
    win = getattr(pet, "window", None)
    if win is None:
        return (getattr(pet, "geometry_version", 0),
                getattr(pet, "world_version", 0))
    try:
        return navgeom.nav_geometry(win).version
    except Exception:
        return (getattr(pet, "geometry_version", 0),
                getattr(pet, "world_version", 0))


class SurfaceRoute:
    """表面图寻路：Goal → SurfaceGraph → 最优多段路线。"""

    key = "route"

    def __init__(self, pet):
        self.pet = pet
        self._cache = {}
        self._cache_key = None
        self._cache_dynamic_tick = None
        self._graph = None            # 锚点图缓存（平台/杆没变就不重建）
        self._gkey = None
        self._ctx = None              # 本猫的 NavContext（世界层每 tick 换内容）

    # ── 当前支撑面 ──
    def _here(self):
        """猫此刻的支撑面 (y, lo, hi)。"""
        pet = self.pet
        y = pet.stand_h()
        lo, hi = walk_band(pet)
        bx = pet.body.chunk1.x
        s = surface_under(bx, y)
        if s is not None:                     # 站在窗口顶边上：只能在这块面的范围内走
            lo = max(lo, min(s[1], s[2]))
            hi = min(hi, max(s[1], s[2]))
        else:
            r = _roof_under(pet, bx, y)       # 站在庇护所屋顶上：同理
            if r is not None:
                lo = max(lo, r[0])
                hi = min(hi, r[1])
        return (y, lo, hi)

    def _pers(self):
        beh = getattr(self.pet, "behavior", None)
        pers = getattr(beh, "pers", None)
        if pers is None:
            pers = getattr(getattr(self.pet, "cat", None), "personality", None)
        return pers

    def _context(self):
        """本猫这一 tick 的 NavContext：威胁 / 拥挤由**世界层**统一提供。

        场是世界的（每 tick 更新一次，所有猫共用），上下文是每只猫的（它自己
        是谁、节点坐标怎么取）。所以这里只做绑定，不重新扫描世界。
        """
        pet = self.pet
        ctx = self._ctx
        if ctx is None:
            from .navgraph import NavContext
            ctx = self._ctx = NavContext(me=pet, body=pet.body)
        win = getattr(pet, "window", None)
        ctx.threat_field = getattr(win, "threat_field", None)
        ctx.traffic_field = getattr(win, "traffic_field", None)
        return ctx

    def _nav_off(self) -> bool:
        """这些状态下没有「多段路」可谈：水里 / 无重力 / 已经在杆上。"""
        b = self.pet.body
        return (getattr(b, "swimming", False) or getattr(b, "zerog", False)
                or getattr(b, "on_pole", False))

    def _graph_now(self):
        """当前站位 + 锚点图（平台 / 杆 / 站位没变就不重建，猫移动不算）。"""
        pet = self.pet
        hy, hlo, hhi = self._here()
        start = SurfaceNode("floor", hy, hlo, hhi, here=True,
                            anchor=pet.body.chunk1.x, sid="here")
        gkey = (_nav_version(pet), pet.cat.stats, round(hy, 1),
                round(hlo, 1), round(hhi, 1))
        if gkey != self._gkey:
            self._graph = None
            self._gkey = gkey
        if self._graph is None:
            self._graph = SurfaceGraph.build(pet, start)
        self._graph.start_at(pet.body.chunk1.x)
        return self._graph

    def plan_escape(self, threat, context=None):
        """威胁下的逃生路线（文档 §六）：Planner 找安全节点，FSM 只决定「要逃」。

        返回 RoutePlan（original_goal = 那个安全点）；找不到则 None，调用方
        回落旧的「朝反方向走一段」。
        """
        pet = self.pet
        if self._nav_off():
            return None
        tx = float(getattr(threat, "x", 0.0))
        ty = float(getattr(threat, "y", 0.0))
        ctx = self._context() if context is None else context
        graph = self._graph_now()
        got = graph.escape_route((tx, ty), ctx, self._pers())
        if got is None:
            return None
        legs, t, e = got
        if not legs:
            return None
        dest = legs[-1].dst
        if dest is None:
            return None
        # 真实起点到「起始锚点」那一小段走路（与 plan() 同一口径）
        walk0 = (abs(pet.body.chunk1.x - graph.nodes[graph.start].anchor)
                 / tuning.PLAN_WALK_SPEED)
        return RoutePlan(point_goal(dest.anchor, dest.y, contact="travel"),
                         legs, t + walk0 * OPTIMISM,
                         e + walk0 * tuning.PLAN_EN_RATE_LIGHT)

    def retreat_point(self, threat):
        """同一块支撑面上的撤退点：走不通时「就地往哪退」也由导航层给。

        文档 §四：``FSM._flee_target_x`` 是第二套逃生算法（当前 x + 反方向
        FLEE_GAP 再 clamp），早就该消掉。这里用**同一条支撑面**（floor / 窗口
        顶边 / 屋顶 —— 走 ``_here()``，和 ``plan_escape`` 同一份口径）的可行走
        带，取离威胁更远的那一头：不跨缺口、不猜墙体，FSM 只剩「要不要逃」。
        """
        pet = self.pet
        _y, lo, hi = self._here()
        x = float(pet.body.chunk1.x)
        if hi <= lo:
            return x
        tx = float(getattr(threat, "x", x))
        left_d, right_d = abs(tx - lo), abs(hi - tx)
        # 多只猫从同一点同时进入无路线兜底时，单纯取“离威胁更远的一头”
        # 会把所有猫送到同一侧墙角。两侧近似等距时按稳定 index 分流，
        # 给每只猫留出可见的横向间隔；危险明显偏向一侧时仍优先安全侧。
        if abs(left_d - right_d) < 60.0:
            idx = int(getattr(pet, "index", 0) or 0)
            return float(hi if (idx & 1) == 0 else lo)
        return float(hi if right_d > left_d else lo)

    def plan(self, goal):
        pet = self.pet
        body = pet.body
        if self._nav_off():
            return None                       # 水里 / 无重力 / 杆上另有路
        gx, gy = goal.pos()
        stats = pet.cat.stats
        hy, hlo, hhi = self._here()
        if surface_under(gx, gy) is not None:
            return None                       # 目标就在某块顶边上：HopReach 直连即可
        if _reach_from_surface(stats, hy, hlo, hhi, body.chunk1.x, gx, gy) is not None:
            return None                       # 此刻就够得到：交给直连能力，别绕
        if (not chunkphys.platforms() and not getattr(pet, "poles", ())
                and not getattr(pet, "shelters", ())):
            return None                       # 世界只有一块地板：没有别的面可去

        # 缓存必须含**起点 x**：同一几何下从不同位置问同一目标，路线并不一样。
        nav_v = _nav_version(pet)
        # Threat/traffic costs are deliberately dynamic and are evaluated by
        # NavGraph.route_to().  Do not reuse a route computed before either
        # field was updated: otherwise a slugcat can keep following a route
        # that has become dangerous or occupied even though the geometry is
        # unchanged.
        win = getattr(pet, "window", None)
        threat = getattr(win, "threat_field", None)
        traffic = getattr(win, "traffic_field", None)
        dynamic_v = (getattr(threat, "tick", 0) or 0,
                     getattr(traffic, "tick", 0) or 0)
        # Dynamic edge costs are sampled from shared world fields, but a route
        # does not need to be rebuilt for every 25 ms physics tick while the
        # cat and target remain in the same place.  Reuse the last result for
        # a couple of ticks (50 ms at 40 Hz); emergency escape routes still
        # bypass this method and are planned immediately.  This removes the
        # worst N-cats × Dijkstra burst without making normal movement feel
        # stale when a threat or another cat moves.
        static_ck = (nav_v, round(hy, 1), round(body.chunk1.x, 1),
                     round(gx, 1), round(gy, 1))
        if static_ck == self._cache_key and self._cache:
            prev_tick = self._cache_dynamic_tick
            cur_tick = max(dynamic_v)
            if prev_tick is not None and 0 <= cur_tick - prev_tick <= 2:
                if "r" in self._cache:
                    return self._cache["r"]
            # The shared danger/traffic fields changed enough that the old
            # route must be replanned.  Do not fall through to the hit below
            # with a stale result (the old code accidentally did exactly that).
            self._cache.pop("r", None)
        if static_ck != self._cache_key:
            self._cache = {}
            self._cache_key = static_ck
        self._cache_dynamic_tick = max(dynamic_v)
        hit = self._cache.get("r")
        if hit is not None:
            return hit                      # 同一几何同一起点同一目标只解一次

        graph = self._graph_now()
        got = graph.route_to((gx, gy), stats, self._pers(), self._context())
        out = None
        if got is not None:
            legs, t, e = got
            # 真实起点到「起始锚点」那一小段走路（锚点是固定的，误差 ≤ 半个锚点间距）
            walk0 = (abs(body.chunk1.x - graph.nodes[graph.start].anchor)
                     / tuning.PLAN_WALK_SPEED)
            t += walk0 * OPTIMISM
            e += walk0 * tuning.PLAN_EN_RATE_LIGHT
            if legs[0].kind not in ("finish",) and len(legs) >= 2:
                out = RoutePlan(goal, legs, t, e)
        self._cache["r"] = out
        return out

    def make_controller(self, plan):
        """按**当前 leg** 建既有控制器；落地后由 RouteExecutor 重新规划接下一段。"""
        leg = plan.leg()
        if leg is None or leg.kind == "finish":
            return None
        if leg.kind == "walk":
            if getattr(leg.src, "kind", None) == "pole_h":
                return PoleWalkRouteController(self.pet, leg)
            return WalkReach(self.pet).make_controller(leg.goal())
        if leg.kind == "climb_pole":
            return PoleClimbRouteController(self.pet, leg)
        if leg.kind == "pole_beam":
            return _pole_beam_controller(self.pet, leg)
        return _hop_controller(self.pet, leg)


class RouteExecutor:
    """多段路线执行器：跑当前 leg → 落地后重新规划 → 直到原目标被满足。

    与 PlanExecutor 的关系：直连能力给不出方案时，PlanExecutor 会把「route」当
    一个候选，控制器就是本类。本类在「没有多段路可走 / 只剩最后一伸」时转交给
    PlanExecutor（allow_route=False，防递归），于是原目标始终是同一个。
    """

    MAX_REPLANS = 8

    def __init__(self, pet, planner, goal, mode=MODE_TOUCH, route_fn=None,
                 plan=None):
        self.pet = pet
        self.planner = planner
        self.goal = goal
        self.mode = mode
        # 逃命这类「目标随威胁移动」的场景换一个 route_fn（见 FSM._escape_replan）：
        # 默认问 SurfaceRoute（固定目标），换了就每次重规划都重问一次安全节点。
        self._route_fn = route_fn
        # 调用方已经算好路线时直接收下：逃生那一步刚跑过一整次 Dijkstra，
        # 不该在这里再问一遍（还会让 goal 与 plan 对不上）。
        self.plan = plan if plan is not None else self._route(goal)
        self._ctrl = None
        self._direct = None
        self._replans = 0
        self._cancelled = False

    def _route(self, goal):
        """这一轮跑哪条路。默认问 SurfaceRoute；逃命换 route_fn。"""
        fn = self._route_fn
        if fn is None:
            return self.planner.surface_route(goal)
        return fn(goal)

    def refresh(self):
        """重取路线（威胁动了）。只在没有正在跑的 leg 时换，免得把半空中
        的那一跳丢掉；驻留中的直连执行器会被收掉，下一 tick 按新目标重建。"""
        if self._ctrl is not None or self._cancelled:
            return
        if self._direct is not None:
            self._direct.cancel()
            self._direct = None
        plan = self._route(self.goal)
        if plan is None:
            return
        self.plan = plan
        if plan.original_goal is not None:
            self.goal = plan.original_goal

    def update(self):
        if self._cancelled:
            return GIVEUP
        if not self.goal.valid():
            return GIVEUP
        body = self.pet.body
        if getattr(body, "swimming", False) or getattr(body, "zerog", False):
            return GIVEUP
        leg = self.plan.leg() if self.plan is not None else None
        # A planned route may intentionally continue from one pole surface to
        # another. Reject stale on-pole starts, but let the edge controller own
        # a pole walk/climb/jump while the current leg says that is the source.
        if getattr(body, "on_pole", False):
            pole_source = (leg is not None
                           and getattr(leg.src, "kind", None)
                           in ("pole_tip", "pole_h")
                           and leg.kind in ("walk", "climb_pole", "pole_beam",
                                            "jump", "drop", "finish"))
            active_pole_leg = (leg is not None and self._ctrl is not None
                               and leg.kind in ("climb_pole", "pole_beam"))
            if not (pole_source or active_pole_leg):
                return GIVEUP
        if leg is None:
            return self._direct_tick()
        if leg.kind == "finish":
            if (getattr(leg.src, "kind", None) in ("pole_tip", "pole_h")
                    and leg.plan and leg.plan[0] == "jump"):
                if self._ctrl is None:
                    self._ctrl = PoleSurfaceFinishRouteController(
                        self.pet, self.goal, leg)
                status = self._ctrl.update()
                if status == RUNNING:
                    return RUNNING
                ctrl, self._ctrl = self._ctrl, None
                if hasattr(ctrl, "cancel"):
                    ctrl.cancel()
                # A successful departure must be replanned from the landing
                # surface; a failed arc gets one bounded route retry as well.
                return self._replan()
            return self._direct_tick()
        if self._ctrl is None:
            self._ctrl = self._build(leg)
            if self._ctrl is None:
                self.plan = None
                return self._direct_tick()
        status = self._ctrl.update()
        if status == RUNNING:
            return RUNNING
        ctrl, self._ctrl = self._ctrl, None
        if hasattr(ctrl, "cancel"):
            ctrl.cancel()
        if status == DONE and getattr(body, "on_pole", False):
            # Keep the graph plan while traversing a pole chain. Replanning from
            # an arbitrary point on a vertical rod loses the source surface and
            # used to strand the cat after the first successful grab.
            next_leg = self.plan.advance() if self.plan is not None else None
            if next_leg is not None:
                return RUNNING
        # DONE（落地）或 GIVEUP（这一段没走通）：都重新规划，接着朝原目辵走
        return self._replan()

    def _direct_tick(self):
        if self._direct is None:
            from .executor import PlanExecutor
            self._direct = PlanExecutor(self.pet, self.planner, self.goal,
                                        mode=self.mode, allow_route=False)
        st = self._direct.update()
        if st == HOLDING:
            return HOLD
        if st == GIVEUP:
            self._cancelled = True
            return GIVEUP
        return RUNNING

    def _replan(self):
        self._replans += 1
        if self._replans > self.MAX_REPLANS:
            self._cancelled = True
            return GIVEUP
        self.plan = self._route(self.goal)
        if self.plan is not None and self.plan.original_goal is not None:
            self.goal = self.plan.original_goal
        leg = self.plan.leg() if self.plan is not None else None
        if leg is None or leg.kind == "finish":
            return self._direct_tick()
        return RUNNING

    def _build(self, leg):
        if leg.kind == "walk":
            if getattr(leg.src, "kind", None) == "pole_h":
                return PoleWalkRouteController(self.pet, leg)
            return WalkReach(self.pet).make_controller(leg.goal())
        if leg.kind == "climb_pole":
            return PoleClimbRouteController(self.pet, leg)
        if leg.kind == "pole_beam":
            return _pole_beam_controller(self.pet, leg)
        return _hop_controller(self.pet, leg)

    def cancel(self):
        self._cancelled = True
        if self._ctrl is not None and hasattr(self._ctrl, "cancel"):
            self._ctrl.cancel()
        self._ctrl = None
        if self._direct is not None:
            self._direct.cancel()
