"""表面图（最小可用形态）：把「地板 / 窗口顶边（单向平台）」当成节点，把
「跳上去」与「在上面走 / 起跳够到目标」当成两条边，穷举出最优两段路线。

原版导航是「房间 tile 图 + A*」（Room.CreateTileGraph / PathFinder）；桌宠没有
tile 图，但窗口顶边就是原版的单向平台（one-way platform）。旧版规划器只会对
「从我此刻站的地方能不能直接碰到目标」问一遍每个能力，于是「果子挂在那块平台
上方、必须跳上平台才够得到」这种目标永远没人去拿 —— 这不是参数问题，是导航
拓扑没成形（见第 74 轮文档 S 级第一条）。

路线结构（Goal → SurfaceGraph → Route）：
    Node  = 猫当前所在的支撑面 / 每块窗口顶边
    Edge1 = hop（跳上那块顶边，交给已经测过的 HopReach 执行）
    Edge2 = 在顶边上走过去伸手 / 起跳弧扫掠够到目标（纯几何）
每条边都带 耗时 / 体力 / 是否落地 / 落点 这些量，总代价乘一个保守系数
（模型误差 > 0），所以只有当两段路线**确实更好**时才会被选上。

执行：第一段直接复用 HopReach 的控制器；落到顶边后执行器会重新规划，
此时「从这块面直接够」已经是第一段，于是自动接上第二段。
"""
from __future__ import annotations

from ..behavior import tuning
from ..core import chunkphys
from .ability import walk_band
from .backflip_reach import takeoff_c0_h
from .goal import point_goal
from .hop_reach import HopReach, surface_under
from .jump_arc import get_arc, sweep_hit

OPTIMISM = 1.30          # 多段路线的代价保守系数（宁可低估直连、不高估两段）
DECK_SAMPLES = 4         # 每块平台上试几个落点
HAND_UP = 12.0           # 站在平台上时手离脚面的高度（手在身侧偏下）
JUMP_X_TRIES = 3         # 平台上起跳点候选个数


def _reach_from_surface(stats, y0, lo, hi, start_x, gx, gy):
    """站在支撑面 y0（可走区间 [lo,hi]）上能不能够到 (gx,gy)：走+伸手 / 起跳弧。

    返回 (耗时, 体力)；够不到 None。纯几何（不读实时 body），所以可测试、
    也可以拿去问「我落在那块面上以后够不够得到」。
    """
    if hi < lo:
        lo, hi = hi, lo
    best = None
    wx = min(max(gx, lo), hi)
    hand_y = y0 - HAND_UP
    # ① 走过去伸手
    if (abs(gy - hand_y) <= tuning.GRAB_REACH + 6.0
            and abs(gx - wx) <= tuning.GRAB_REACH):
        t = abs(wx - start_x) / tuning.PLAN_WALK_SPEED
        best = (t, t * tuning.PLAN_EN_RATE_LIGHT)
    # ② 平台上起跳（士狼跳那套弧线族）：起跳点取目标附近几档
    launch_y = y0 - takeoff_c0_h(stats)
    xs = []
    for k in (0.0, -1.0, 1.0):
        x = min(max(wx + k * tuning.PLAN_WALK_X_PAD, lo), hi)
        if x not in xs:
            xs.append(x)
    xs = xs[:JUMP_X_TRIES]
    for hold in tuning.PLAN_JUMP_HOLD_GEARS:
        for md in (0, 1, -1):
            arc = get_arc(stats, hold, md)
            for lx in xs:
                hit = sweep_hit(arc, gx - lx, gy - launch_y, tuning.GRAB_REACH)
                if hit is None:
                    continue
                t = (abs(lx - start_x) / tuning.PLAN_WALK_SPEED + hit
                     + tuning.PLAN_STARTUP_TICKS)
                e = (t * tuning.PLAN_EN_RATE_LIGHT
                     + hit * tuning.PLAN_EN_RATE_VIGOROUS)
                if best is None or t < best[0]:
                    best = (t, e)
    return best


class SurfaceHop:
    """一条两段路线：先跳到 deck 的 land_x，再从那里够到目标。"""
    __slots__ = ("deck", "y", "land_x", "time", "energy", "goal")

    def __init__(self, deck, land_x, time, energy):
        self.deck = deck
        self.y = float(deck[1])                # 平台元组＝(x0, y0, x1)
        self.land_x = land_x
        self.time = float(time)
        self.energy = float(energy)
        self.goal = point_goal(land_x, self.y, contact="travel")


class SurfaceRoute:
    """表面图寻路：Goal → (第一段 hop 目标, 代价)。"""

    key = "route"

    def __init__(self, pet):
        self.pet = pet

    # ── 当前支撑面 ──
    def _here(self):
        """猫此刻的支撑面 (y, lo, hi)。"""
        pet = self.pet
        y = pet.stand_h()
        lo, hi = walk_band(pet)
        s = surface_under(pet.body.chunk1.x, y)
        if s is not None:                     # 站在窗口顶边上：只能在这块面的范围内走
            lo = max(lo, min(s[1], s[2]))
            hi = min(hi, max(s[1], s[2]))
        return (y, lo, hi)

    def plan(self, goal):
        """两段路线；直连够得到、或没有任何平台/没有可取的第二段时返回 None。"""
        pet = self.pet
        body = pet.body
        if getattr(body, "swimming", False) or getattr(body, "zerog", False):
            return None
        if getattr(body, "on_pole", False):
            return None                       # 杆上另有杆间跳/落平台的路
        decks = chunkphys.platforms()
        if not decks:
            return None
        gx, gy = goal.pos()
        if surface_under(gx, gy) is not None:
            return None                       # 目标就在某块顶边上：HopReach 直连即可
        stats = pet.cat.stats
        hy, hlo, hhi = self._here()
        if _reach_from_surface(stats, hy, hlo, hhi, body.chunk1.x, gx, gy) is not None:
            return None                       # 此刻就够得到：交给直连能力，别绕
        floor_y = hy
        best = None
        for d in decks:
            d0, y0, d1 = d                     # 平台元组＝(x0, y0, x1)
            lo, hi = min(d0, d1), max(d0, d1)
            lo, hi = max(lo, hlo), min(hi, hhi)          # 只走窗口内的那一段
            if hi - lo < 2.0 or abs(y0 - floor_y) < 2.0:
                continue
            for land_x in self._samples(lo, hi, gx):
                hop_goal = point_goal(land_x, y0, contact="travel")
                est = HopReach(pet).can_touch(hop_goal)
                if est is None:
                    continue
                seg2 = _reach_from_surface(stats, y0, lo, hi, land_x, gx, gy)
                if seg2 is None:
                    continue
                t = (est.time_est + seg2[0]) * OPTIMISM
                e = (est.energy_est + seg2[1]) * OPTIMISM
                if best is None or t < best.time:
                    best = SurfaceHop(d, land_x, t, e)
        return best

    @staticmethod
    def _samples(lo, hi, gx):
        """平台上的落点候选：贴着目标 x 优先，再取面上几个均分点。"""
        out = []
        for x in (min(max(gx, lo), hi),
                  lo + (hi - lo) * 0.25, (lo + hi) * 0.5, hi - (hi - lo) * 0.25):
            x = min(max(x, lo), hi)
            if all(abs(x - o) > 1.0 for o in out):
                out.append(x)
        return out[:DECK_SAMPLES]

    def make_controller(self, hop):
        """第一段直接交给 HopReach（跳上那块顶边）；落地后执行器会重新规划。"""
        return HopReach(self.pet).make_controller(hop.goal)
