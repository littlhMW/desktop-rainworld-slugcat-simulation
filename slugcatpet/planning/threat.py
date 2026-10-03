# -*- coding: utf-8 -*-
"""ThreatField：共享世界层「哪里危险」（文档 §ThreatField）。

反编译口径：原版生物的「危险」不是「离我多远」这一个标量。蜥蜴的
ThreatTracker 记的是「谁在追我、它在哪个 tile、有没有在靠近」，导航层
（AImap / PathFinder）再把它翻译成路线代价（ConnectionResistance）。

桌宠里 FSM 早就写好了「我要逃」，导航层却只有欧氏距离 + 固定落点，于是出现
「杆上不躲、逃到死角、几只猫挤同一条路」这类「局部聪明、整体笨」的表现。
本模块只做一件事：把「当前世界有哪些威胁、某个位置有多危险」变成一份可查的
表。它不改 FSM、不改物理，只给 Planner 一个 sample()。

    Threat        一条威胁：谁 / 在哪 / 往哪走 / 在哪根杆 / 哪块面上 / 在不在靠近
    ThreatSample  某个位置的危险度：danger / nearest / time_to_contact / same_pole
    ThreatField   整张表：update() 每 tick 采一次，sample() / edge_cost() 随便问

代价量级（文档口径）：威胁代价 > 拥挤代价 > 普通移动代价。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..behavior import tuning
from . import navgeom

POLE_LANE_EPS = 8.0        # 「这条威胁在我这根杆上」的横向容差
_EXTRA_W = 0.25            # 次要威胁只做少量叠加（主威胁取最大值）

# 屏幕地板是唯一「没有 Surface 对象」的可站面（navgeom 传 surface=None）：
# 给它一个稳定身份，否则「同一块地板上的两只」永远算不出 same_surface。
_SCREEN_FLOOR = navgeom.Surface("floor", navgeom.FLOOR, y=0.0, lo=0.0, hi=0.0,
                                stand=True)

_STRENGTH_REF = 0.45       # 原版 danger 的基准（粉蜥）：换成 1.0 的强度


@dataclass(slots=True)
class Threat:
    """一条威胁。不只有「它在哪」——还要有它的速度、所在杆 / 面。"""

    actor: object
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    strength: float = 1.0
    kind: str = "unknown"
    pole: object = None
    surface: object = None


@dataclass(slots=True)
class ThreatSample:
    """某个位置的危险度。time_to_contact 与拓扑标记供 FSM 判定「安全了吗」。"""

    danger: float = 0.0
    nearest: object = None
    time_to_contact: float = math.inf
    same_pole: bool = False
    same_surface: bool = False


def same_terrain(a, b) -> bool:
    """同一块面 / 同一根杆：对象同一，或（跨帧重建的 Surface）sid 相同。"""
    if a is None or b is None:
        return False
    if a is b:
        return True
    sa, sb = getattr(a, "sid", None), getattr(b, "sid", None)
    return sa is not None and sa == sb


def hostile_needleworm(f, win) -> bool:
    """愤怒的面条蝇成体（原版 BigNeedleWormAI.Attacks：拿着幼体 / tempLike<-0.25）。"""
    if getattr(f, "age", None) != "big" or getattr(f, "dead", False):
        return False
    if getattr(f, "state", None) is not None and getattr(f, "state", None) != "free":
        return False
    try:
        return bool(f.hostile_to({"uid": id(win)}))
    except Exception:
        return False


def hostile_scavenger(sc) -> bool:
    """会朝猫扔矛的拾荒者（珍珠交易过的 friendly 不算）。"""
    return (not getattr(sc, "dead", False)
            and getattr(sc, "state", None) == "free"
            and not getattr(sc, "friendly", False))


def _lizard_strength(lz) -> float:
    """威胁强度：原版 LizardBreedParams.danger（粉蜥 0.45 → 1.0）。"""
    d = float(getattr(getattr(lz, "breed", None), "danger", _STRENGTH_REF) or 0.0)
    return max(0.5, min(2.0, d / _STRENGTH_REF))


class ThreatField:
    """整张「哪里危险」的表：世界一份，每 tick 采一次，本 tick 所有猫共用。"""

    __slots__ = ("win", "threats", "tick", "geom", "_edge_cache")

    def __init__(self, win=None):
        self.win = win
        self.threats = []
        self.tick = 0
        self.geom = None
        # Edge costs are shared by every cat's route query during one field
        # snapshot.  Keeping this tiny per-tick cache avoids sampling every
        # threat along the same graph edge once per cat.
        self._edge_cache = {}

    # ── 采集 ──
    def update(self, win=None, geom=None):
        """重采本 tick 的威胁表。

        以后新增秃鹫 / 利维坦 / 拾荒者，只在这里登记一种——不给 FSM 增加新的
        逃跑分支（文档 §「以后新增威胁只往 ThreatField 注册」）。
        """
        from ..world.enums import ItemState
        if win is not None:
            self.win = win
        w = self.win
        self.tick += 1
        self._edge_cache.clear()
        if geom is not None:
            self.geom = geom
        elif w is not None:
            self.geom = navgeom.nav_geometry(w)
        out = []
        if w is not None:
            free = ItemState.FREE
            for lz in getattr(w, "lizards", ()) or ():
                if getattr(lz, "dead", False) or getattr(lz, "state", None) != free:
                    continue
                out.append(self._make(lz, "lizard", _lizard_strength(lz)))
            for f in getattr(w, "needleworms", ()) or ():
                if hostile_needleworm(f, w):
                    out.append(self._make(f, "needleworm", 0.8))
            for sc in getattr(w, "scavengers", ()) or ():
                if hostile_scavenger(sc):
                    out.append(self._make(sc, "scavenger", 0.7))
        self.threats = out
        return out

    def _make(self, actor, kind, strength) -> Threat:
        body = getattr(actor, "body", None)
        ch = getattr(body, "chunk1", None)
        if ch is None:
            ch = actor
        x = float(getattr(ch, "x", 0.0))
        y = float(getattr(ch, "y", 0.0))
        return Threat(
            actor=actor, x=x, y=y,
            vx=float(getattr(ch, "vx", 0.0) or 0.0),
            vy=float(getattr(ch, "vy", 0.0) or 0.0),
            strength=float(strength), kind=kind,
            pole=_pole_at(self.geom, x, y, body),
            surface=_surface_at(self.geom, x, y))

    # ── 查询 ──
    def sample(self, x, y, *, pole=None, surface=None, radius=None, dt=0.0,
               predict=False) -> ThreatSample:
        """(x, y) 处的危险度。

        主威胁取最大值，其余只做 _EXTRA_W 少量叠加 —— 三只远处的蜥蜴不该比
        一只贴脸的更危险。``predict=True`` 时按威胁速度在 0.5s / 1.0s 后各
        采一次并按权重取最大，让猫在「它马上会过来」时就先走。
        """
        best = ThreatSample()
        meta = None
        table = self.threats if not predict else self.threats
        horizons = tuning.THREAT_PREDICT_HORIZONS if predict else (0.0,)
        weights = tuning.THREAT_PREDICT_W if predict else (1.0,)
        extra = 0.0
        for i, h in enumerate(horizons):
            w = weights[i] if i < len(weights) else 1.0
            for t in table:
                v, pole_hit, surf_hit = self._danger(t, x, y, pole, surface,
                                                     radius, dt + h)
                if v <= 0.0:
                    continue
                v *= w
                if v > best.danger:
                    if best.danger > 0.0:
                        extra += best.danger * _EXTRA_W
                    best.danger = v
                    best.nearest = t.actor
                    best.same_pole = pole_hit
                    best.same_surface = surf_hit
                    best.time_to_contact = self.eta(t, x, y)
                    meta = t
                else:
                    extra += v * _EXTRA_W
        best.danger += extra
        if meta is None:
            best.time_to_contact = math.inf
        return best

    def predicted_sample(self, x, y, *, pole=None, surface=None) -> ThreatSample:
        """带速度预测的 sample()（静止不动的威胁与正冲过来的不是一回事）。"""
        return self.sample(x, y, pole=pole, surface=surface, predict=True)

    def _danger(self, t, x, y, pole, surface, radius, dt):
        R = tuning.THREAT_SENSE_R if radius is None else float(radius)
        tx = t.x + t.vx * dt
        ty = t.y + t.vy * dt
        d = math.hypot(tx - x, ty - y)
        prox = math.exp(-d / R)
        if prox < 0.01:
            return 0.0, False, False
        same_pole = pole is not None and same_terrain(t.pole, pole)
        same_surf = surface is not None and same_terrain(t.surface, surface)
        topo = tuning.THREAT_SAME_POLE_MUL if same_pole else (
            tuning.THREAT_SAME_SURFACE_MUL if same_surf else
            self.topology_factor(t, x, y))
        approach = self._approach(t, x, y)
        v = t.strength * prox * topo * (1.0 + approach * 1.5)
        return v, same_pole, same_surf

    def topology_factor(self, t, x=None, y=None) -> float:
        """威胁与查询点的地形关系系数（文档 §topology factor）。

        同一根杆 5.0 / 同一块面 1.8 / 隔墙 0.3 / 其余（同屋不同面）1.2。
        「这只蜥蜴虽然离我 100px，但它就在我这根杆上」只能靠这一项表达。
        """
        if x is None or y is None:
            return tuning.THREAT_SAME_REGION_MUL
        g = self.geom
        if g is not None:
            try:
                if g.los_blocked(t.x, t.y, x, y):
                    return tuning.THREAT_WALL_MUL
            except Exception:
                pass
        return tuning.THREAT_SAME_REGION_MUL

    @staticmethod
    def _approach(t, x, y) -> float:
        """威胁是否正在朝 (x, y) 靠近：0（背向/静止）～ 1（全速冲过来）。"""
        dx, dy = x - t.x, y - t.y
        ln = math.hypot(dx, dy)
        if ln < 1e-5:
            return 1.0
        toward = t.vx * (dx / ln) + t.vy * (dy / ln)
        return max(0.0, min(1.0, toward / 8.0))

    @staticmethod
    def eta(t, x, y) -> float:
        """威胁到 (x, y) 的预计时间（tick）。静止的威胁按最低速度兜底。"""
        d = math.hypot(t.x - x, t.y - y)
        sp = math.hypot(t.vx, t.vy)
        return d / max(sp, tuning.THREAT_ETA_MIN_SPEED)

    def danger_at(self, x, y, pole=None) -> float:
        return self.sample(x, y, pole=pole).danger

    def threat_of(self, actor):
        """某个 actor 在本 tick 表里的那条 Threat（不在表里 → None）。"""
        for t in self.threats:
            if t.actor is actor:
                return t
        return None

    def pole_surface_at(self, x, y, body=None):
        """这个位置所在的竖杆（Surface），没有则 None。"""
        return _pole_at(self.geom, x, y, body)

    # ── 边代价 ──
    def edge_cost(self, edge, context=None) -> float:
        """一条边的威胁代价：沿边采样取最大 danger，再折算成 tick 当量。

        只采起点不够 —— 「A 安全、B 安全、中间突然有蜥蜴」必须能被发现，
        所以竖边（杆 / 墙）采更多点（文档 §edge_cost）。
        同一根杆上已有威胁：加一笔软惩罚，不禁止（走投无路时仍可沿杆逃）。
        """
        cached = self._edge_cache.get(id(edge))
        if cached is not None:
            return cached
        from .navgraph import edge_points, edge_pole, sample_points
        pts = edge_points(edge, context)
        if not pts:
            return 0.0
        pole = edge_pole(edge)
        n = (tuning.THREAT_EDGE_SAMPLES_POLE if pole is not None
             else tuning.THREAT_EDGE_SAMPLES)
        danger = 0.0
        for sx, sy in sample_points(pts, n):
            v = self.sample(sx, sy, pole=pole).danger
            if v > danger:
                danger = v
        cost = danger * tuning.THREAT_EDGE_SCALE
        if pole is not None and any(same_terrain(t.pole, pole) for t in self.threats):
            cost += tuning.THREAT_POLE_EDGE_PENALTY
        self._edge_cache[id(edge)] = cost
        return cost


def _pole_at(geom, x, y, body=None):
    """威胁此刻所在的竖杆（先信它的身体状态，再问几何）。"""
    if body is not None and getattr(body, "on_pole", False):
        px = getattr(body, "pole_x", None)
        if px is not None:
            x = float(px)
    if geom is None:
        return None
    for s in geom.surf_grid.query(x - POLE_LANE_EPS, y, x + POLE_LANE_EPS, y):
        if getattr(s, "kind", None) != navgeom.VPOLE:
            continue
        if abs(float(s.x) - x) <= POLE_LANE_EPS and s.top - 2.0 <= y <= s.bot + 2.0:
            return s
    return None


def _surface_at(geom, x, y):
    """威胁脚下的支撑面（屏幕地板用 _SCREEN_FLOOR 的稳定身份）。"""
    if geom is None:
        return _SCREEN_FLOOR
    try:
        c = geom.support_contact(x, y)
    except Exception:
        return _SCREEN_FLOOR
    return c.surface if getattr(c, "surface", None) is not None else _SCREEN_FLOOR
