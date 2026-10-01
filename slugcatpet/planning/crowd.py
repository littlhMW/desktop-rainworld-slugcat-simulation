# -*- coding: utf-8 -*-
"""CrowdField：共享世界层「哪里挤」（文档 §CrowdField）。

board.py 的 crowd 是**目标级**拥挤（5 只猫抢同一个果子 → 分位置）。它解决
不了**导航级**拥挤：5 只猫的目标各不相同，却都要经过同一条 100px 宽的平台。

本模块只回答一个问题：某个位置 / 某条边现在有多少只猫。代价折进 A* 之后，
「左边 base=30 / crowd=80，右边 base=40 / crowd=10」会自己选右边 —— 而不用在
FSM 里写 `if another_cat_nearby: go_right()`。

竖杆额外给一笔很重的占用：同一根竖杆本来就是低容量交通通道（原版一杆一猫）。
"""
from __future__ import annotations

import math

from ..behavior import tuning

POLE_LANE_EPS = 10.0       # 「在不在同一根竖杆上」的横向容差


class CrowdField:
    """整张「哪里挤」的表：世界一份，每 tick update() 一次。"""

    __slots__ = ("win", "actors")

    def __init__(self, win=None):
        self.win = win
        self.actors = []            # [(unit, body, x, y), ...]

    def update(self, win=None):
        if win is not None:
            self.win = win
        out = []
        for p in getattr(self.win, "pets", ()) or ():
            body = getattr(p, "body", None)
            ch = getattr(body, "chunk1", None)
            if ch is None:
                continue
            out.append((p, body, float(ch.x), float(ch.y)))
        self.actors = out
        return out

    # ── 查询 ──
    def point_cost(self, x, y, me=None) -> float:
        """(x, y) 附近有多少只别的猫：exp(-d / CROWD_SCALE) 之和。"""
        total = 0.0
        for p, _b, px, py in self.actors:
            if p is me:
                continue
            d = math.hypot(px - x, py - y)
            if d > tuning.CROWD_R:
                continue
            total += math.exp(-d / tuning.CROWD_SCALE)
        return total

    def pole_riders(self, pole_x, me=None) -> int:
        """同一根竖杆上还有几只（低容量通道的占用）。"""
        if pole_x is None:
            return 0
        n = 0
        for p, body, _x, _y in self.actors:
            if p is me or body is me:
                continue
            if not getattr(body, "on_pole", False):
                continue
            px = getattr(body, "pole_x", None)
            if px is not None and abs(float(px) - float(pole_x)) <= POLE_LANE_EPS:
                n += 1
        return n

    def edge_cost(self, edge, context=None) -> float:
        """一条边的拥挤代价：沿边采样累加 point_cost，再加杆占用。"""
        from .navgraph import edge_pole_x, edge_points, sample_points
        me = getattr(context, "me", None)
        total = 0.0
        pts = edge_points(edge, context)
        for sx, sy in sample_points(pts, tuning.CROWD_EDGE_SAMPLES):
            total += self.point_cost(sx, sy, me)
        cost = total * tuning.CROWD_EDGE_SCALE
        n = self.pole_riders(edge_pole_x(edge), me)
        if n:
            cost += n * tuning.CROWD_POLE_OCCUPANCY
        return cost
