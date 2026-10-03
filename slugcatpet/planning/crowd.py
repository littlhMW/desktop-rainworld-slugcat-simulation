# -*- coding: utf-8 -*-
"""TrafficField：共享世界层「哪里挤」（文档 §14）。

和 ``Board.target_crowd`` 不是同一个系统，只是名字过去很像（文档 §14 建议改名
避免看混）：``target_crowd`` 是**目标级**拥挤（5 只猫抢同一个果子 → 分位置），
本模块是**路线级**交通（5 只猫目标各不相同，却都要经过同一条 100px 宽的
平台）。

本模块只回答一个问题：某个位置 / 某条边现在有多少只猫。代价折进 A* 之后，
「左边 base=30 / crowd=80，右边 base=40 / crowd=10」会自己选右边 —— 而不用在
FSM 里写 `if another_cat_nearby: go_right()`。

竖杆额外给一笔很重的占用：同一根竖杆本来就是低容量交通通道（原版一杆一猫）。
"""
from __future__ import annotations

import math

from ..behavior import tuning

POLE_LANE_EPS = 10.0       # 「在不在同一根竖杆上」的横向容差


class TrafficField:
    """整张「哪里挤」的表：世界一份，每 tick update() 一次。"""

    __slots__ = ("win", "actors", "_point_cache", "_pole_cache")

    def __init__(self, win=None):
        self.win = win
        self.actors = []            # [(unit, body, x, y), ...]
        # Route searches sample the same graph points for every cat.  Cache the
        # all-actor density once per traffic snapshot, then subtract the
        # querying cat's own contribution in point_cost().
        self._point_cache = {}
        self._pole_cache = {}

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
        self._point_cache.clear()
        self._pole_cache.clear()
        return out

    # ── 查询 ──
    def point_cost(self, x, y, me=None) -> float:
        """(x, y) 附近有多少只别的猫：exp(-d / CROWD_SCALE) 之和。"""
        key = (float(x), float(y))
        total = self._point_cache.get(key)
        if total is None:
            total = 0.0
            for _p, _b, px, py in self.actors:
                d = math.hypot(px - x, py - y)
                if d <= tuning.CROWD_R:
                    total += math.exp(-d / tuning.CROWD_SCALE)
            self._point_cache[key] = total
        if me is not None:
            for p, _b, px, py in self.actors:
                if p is me:
                    d = math.hypot(px - x, py - y)
                    if d <= tuning.CROWD_R:
                        total -= math.exp(-d / tuning.CROWD_SCALE)
                    break
        return max(0.0, total)

    def pole_riders(self, pole_x, me=None) -> int:
        """同一根竖杆上还有几只（低容量通道的占用）。"""
        if pole_x is None:
            return 0
        key = float(pole_x)
        # Riders are independent of the queried edge.  Cache the all-rider
        # count, then remove the requesting cat (if it is riding this pole).
        n = self._pole_cache.get(key)
        if n is None:
            n = 0
            for _p, body, _x, _y in self.actors:
                if not getattr(body, "on_pole", False):
                    continue
                px = getattr(body, "pole_x", None)
                if px is not None and abs(float(px) - key) <= POLE_LANE_EPS:
                    n += 1
            self._pole_cache[key] = n
        if me is not None:
            for p, body, _x, _y in self.actors:
                if p is me or body is me:
                    if not getattr(body, "on_pole", False):
                        break
                    px = getattr(body, "pole_x", None)
                    if px is not None and abs(float(px) - key) <= POLE_LANE_EPS:
                        n -= 1
                    break
        return max(0, n)

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
