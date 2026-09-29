# -*- coding: utf-8 -*-
"""庇护所：地面上的安全区矩形 + 入口 + 会动的门（全程序化绘制，不依赖单张 sprite）。

反编译口径：原版庇护所是一个「房间」，门是一对会合拢的板。桌宠这边刻意**不**把
庇护所塞进 chunkphys.PLATFORMS —— 否则碰撞 / SurfaceGraph / geometry_version /
跳跃可达性全被牵进来。它只对外提供四件东西：

    contains(px, py)   stormcycle 判断「这只猫进没进去」
    entry_goal()       StormSeekShelter 交给现有 PlanExecutor 的一个地面点目标
    coverage_at(px,py) 渲染层据此把暴雨在庇护所里衰减（里面听得到、淋不着）
    door_rect()/step() 会动的两块门板

猫仍然站在原来的地面上，庇护所只负责「安全区」这一个语义。
"""
from __future__ import annotations

from ..planning import point_goal

OPEN = "open"
CLOSING = "closing"
CLOSED = "closed"
OPENING = "opening"

# 配色：RW 庇护所是灰褐色金属
_FRAME = (62, 58, 52, 236)
_METAL = (104, 99, 90, 255)
_METAL_HI = (138, 131, 118, 255)
_METAL_LO = (74, 70, 64, 255)
_INNER = (34, 31, 28, 255)
_DOOR = (88, 84, 78, 255)
_DOOR_HI = (152, 146, 132, 255)
_RUST = (124, 92, 58, 255)
_RIVET = (176, 170, 156, 255)


def _clampf(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _lerp(a, b, t):
    return a + (b - a) * t


def ease(t):
    """门板的缓动：起步慢、中段快、收尾慢。"""
    t = _clampf(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Shelter:
    """地面上一间庇护所。左下角由 width/height 与 ground_y 决定（底边永远贴地）。"""

    MIN_W = 60.0
    MAX_W = 460.0
    MIN_H = 44.0
    MAX_H = 240.0

    def __init__(self, x, y, w, h, ground_y, WL, seed=0, door_ticks=40):
        self.ground_y = float(ground_y)
        self.w = _clampf(float(w), self.MIN_W, self.MAX_W)
        self.x = float(x)
        self.h = _clampf(self.ground_y - float(y), self.MIN_H, self.MAX_H)
        self.y = self.ground_y - self.h
        self.seed = int(seed)
        self.door_ticks = max(1, int(door_ticks))
        self.center_x = self.x + self.w * 0.5
        self.center_y = self.y + self.h * 0.5
        # 门方向：创建时定一次。靠左半屏 → 门朝右；靠右半屏 → 门朝左。
        self.door_side = "right" if self.center_x < float(WL) * 0.5 else "left"
        self.door_state = OPEN
        self.door_t = 0.0                 # 0=全开 1=全关
        self.eaves = 18.0                 # 屋檐余量（coverage 0.25 那条带）
        # 程序化细节：建一次就固定，免得每帧抖动
        self._rivets = [(0.12, 0.10), (0.88, 0.10), (0.12, 0.88), (0.88, 0.88)]

    # ── 几何 ──
    @property
    def edge(self):
        return _clampf(self.w * 0.055, 6.0, 12.0)

    @property
    def door_w(self):
        return _clampf(self.w * 0.34, 20.0, 52.0)

    @property
    def door_h(self):
        return _clampf(self.h * 0.66, 24.0, 70.0)

    @property
    def door_x0(self):
        return self.x + self.w - self.door_w if self.door_side == "right" else self.x

    @property
    def door_x1(self):
        return self.x + self.w if self.door_side == "right" else self.x + self.door_w

    @property
    def door_y1(self):
        return self.ground_y

    @property
    def door_y0(self):
        return self.ground_y - self.door_h

    def entry_x(self):
        """入口内侧那一点：门宽的中点，往里收一点，免得站在门框里。"""
        cx = (self.door_x0 + self.door_x1) * 0.5
        inset = self.door_w * 0.5
        return cx - inset if self.door_side == "right" else cx + inset

    def entry_goal(self, radius=26.0):
        """给 PlanExecutor 的地面点目标（key 稳定，冷却记账才有效）。"""
        return point_goal(self.entry_x(), self.ground_y, radius=radius, contact="body")

    def safe_rect(self):
        return (self.x, self.y, self.x + self.w, self.ground_y)

    def door_rect(self):
        return (self.door_x0, self.door_y0, self.door_x1, self.door_y1)

    # ── 语义 ──
    def contains(self, px, py):
        """在不在安全区里（脚下两像素容差：猫站着时 chunk1 略高于地线）。"""
        if px is None or py is None:
            return False
        return (self.x <= px <= self.x + self.w
                and self.y - 4.0 <= py <= self.ground_y + 6.0)

    def coverage_at(self, px, py):
        """挡雨系数：外面 0 / 屋檐下 0.25 / 里面 1.0。"""
        if px is None or py is None:
            return 0.0
        if self.contains(px, py):
            return 1.0
        m = self.eaves
        if (self.x - m <= px <= self.x + self.w + m
                and py >= self.y - m and py <= self.ground_y + m):
            return 0.25
        return 0.0

    def distance_to(self, px, py):
        """到安全区外沿的近似距离（焦虑 / 选庇护所用）。"""
        dx = max(self.x - px, 0.0, px - (self.x + self.w))
        dy = max(self.y - py, 0.0, py - self.ground_y)
        return (dx * dx + dy * dy) ** 0.5

    # ── 门 ──
    def start_closing(self):
        if self.door_state in (OPEN, OPENING):
            self.door_state = CLOSING

    def start_opening(self):
        if self.door_state in (CLOSED, CLOSING):
            self.door_state = OPENING

    @property
    def door_closed(self):
        return self.door_state == CLOSED

    def step(self):
        rate = 1.0 / float(self.door_ticks)
        if self.door_state == CLOSING:
            self.door_t = min(1.0, self.door_t + rate)
            if self.door_t >= 1.0:
                self.door_state = CLOSED
        elif self.door_state == OPENING:
            self.door_t = max(0.0, self.door_t - rate)
            if self.door_t <= 0.0:
                self.door_state = OPEN

    def panel_rects(self):
        """两块门板的当前矩形 (left, right)。开着时缩在门框两侧，关时合成一扇。"""
        pw = self.door_w * 0.5
        dcx = (self.door_x0 + self.door_x1) * 0.5
        t = ease(self.door_t)
        l0 = self.door_x0 - pw          # 全开：整块缩进左墙
        r0 = self.door_x1               # 全开：整块缩进右墙
        lx = _lerp(l0, dcx - pw, t)
        rx = _lerp(r0, dcx, t)
        y0, y1 = self.door_y0, self.door_y1
        return ((lx, y0, lx + pw, y1), (rx, y0, rx + pw, y1))

    # ── 绘制 ──
    def draw(self, p):
        from PySide6.QtGui import QColor, QPen
        from PySide6.QtCore import QRectF, QPointF, Qt

        x0, y0, x1, y1 = self.safe_rect()
        e = self.edge
        body = QRectF(x0, y0, self.w, self.h)

        # 1) 内部：安全区底色（暴雨时这里是唯一不被压暗的地方）
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*_INNER))
        p.drawRect(body)

        # 2) 外框
        p.setPen(QPen(QColor(*_FRAME), e * 0.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(body.adjusted(e * 0.45, e * 0.45, -e * 0.45, -e * 0.45))

        # 3) 第二层金属线
        ins = e * 1.55
        p.setPen(QPen(QColor(*_METAL_LO), max(1.0, e * 0.28)))
        p.drawRect(body.adjusted(ins, ins, -ins, -ins))

        # 4) 支撑条：两根立柱 + 一道横梁（都不压门）
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*_METAL_LO))
        strut_w = max(2.0, self.w * 0.022)
        top = y0 + ins
        bot = y1 - e * 0.6
        door_lo, door_hi = self.door_x0, self.door_x1
        for fx in (0.22, 0.78):
            sx = x0 + self.w * fx
            if door_lo - strut_w <= sx <= door_hi + strut_w:
                continue
            p.drawRect(QRectF(sx - strut_w * 0.5, top, strut_w, bot - top))
        p.drawRect(QRectF(x0 + ins, y0 + self.h * 0.30, self.w - ins * 2.0, strut_w * 0.8))

        # 5) 角落结构 + 铆钉
        cs = max(3.0, self.w * 0.05)
        p.setBrush(QColor(*_METAL))
        for fx, fy in self._rivets:
            cx = x0 + self.w * fx
            cy = y0 + self.h * fy
            p.drawRect(QRectF(cx - cs * 0.5, cy - cs * 0.5, cs, cs))
        p.setBrush(QColor(*_RIVET))
        r = max(1.0, cs * 0.16)
        for fx, fy in self._rivets:
            p.drawEllipse(QPointF(x0 + self.w * fx, y0 + self.h * fy), r, r)

        # 6) 门洞（比内部更黑）
        dx0, dy0, dx1, dy1 = self.door_rect()
        p.setBrush(QColor(16, 15, 14, 255))
        p.drawRect(QRectF(dx0, dy0, dx1 - dx0, dy1 - dy0))

        # 7) 两块门板 + 中缝 + 铆钉
        for (px0, py0, px1, py1) in self.panel_rects():
            if px1 - px0 <= 0.5:
                continue
            p.setBrush(QColor(*_DOOR))
            p.drawRect(QRectF(px0, py0, px1 - px0, py1 - py0))
            p.setPen(QPen(QColor(*_DOOR_HI), max(1.0, e * 0.18)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(px0 + 1.0, py0 + 1.0, (px1 - px0) - 2.0, (py1 - py0) - 2.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(*_RIVET))
            p.drawEllipse(QPointF((px0 + px1) * 0.5, py0 + (py1 - py0) * 0.28), r, r)
            p.drawEllipse(QPointF((px0 + px1) * 0.5, py0 + (py1 - py0) * 0.72), r, r)

        # 8) 机械锁：门关到位才咬合（中缝上一根横栓 + 一处锈迹）
        dcx = (dx0 + dx1) * 0.5
        closed = ease(self.door_t)
        lock_w = max(4.0, self.door_w * 0.42) * closed
        if lock_w > 0.6:
            ly = dy0 + self.door_h * 0.16
            p.setBrush(QColor(*_METAL_HI))
            p.drawRect(QRectF(dcx - lock_w * 0.5, ly, lock_w, max(2.0, self.door_h * 0.10)))
        p.setBrush(QColor(*_RUST))
        p.drawEllipse(QPointF(dcx, dy0 + self.door_h * 0.5), r * 1.2, r * 1.2)

    # ── 存档 ──
    def to_dict(self):
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "ground_y": self.ground_y, "seed": self.seed,
                "door_side": self.door_side, "door_state": self.door_state,
                "door_t": self.door_t, "door_ticks": self.door_ticks}


def shelter_from_dict(d, WL, ground_y=None):
    """从存档建回（旧档缺字段一律有默认值）。"""
    if not isinstance(d, dict):
        return None
    gy = float(d.get("ground_y", ground_y if ground_y is not None else 0.0))
    try:
        sh = Shelter(float(d.get("x", 0.0)), float(d.get("y", gy - 80.0)),
                     float(d.get("w", 140.0)), float(d.get("h", 80.0)),
                     gy, WL, seed=int(d.get("seed", 0) or 0),
                     door_ticks=int(d.get("door_ticks", 40) or 40))
    except Exception:
        return None
    side = d.get("door_side")
    if side in ("left", "right"):
        sh.door_side = side
    st = d.get("door_state")
    if st in (OPEN, CLOSING, CLOSED, OPENING):
        sh.door_state = st
    try:
        sh.door_t = _clampf(float(d.get("door_t", 0.0)), 0.0, 1.0)
    except Exception:
        sh.door_t = 0.0
    return sh