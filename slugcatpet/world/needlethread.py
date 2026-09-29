# -*- coding: utf-8 -*-
"""矛大师掷出的活针与尾巴之间那条有机细线（反编译 Spear.Umbilical，Spear.cs:714）。

wiki：「掷出白色的矛针后，可以看到一条长的有机线连接矛和矛大师，就像运输营养
物质一样，前提是矛命中了活物。」原版在 Weapon.Thrown 时 AddObject 一条
Umbilical，一端钉在矛大师 tail[0]（尾巴根），另一端钉在矛尖后方 25px 的矛尾上，
自身是 10~19 个自由点，寿命 300~400 tick，宽约 1px 的米黄色细线。

数值出处：
  Spear.cs:714           Spear_NeedleCanFeed() 时 new Umbilical(room, this, player, vel)
  Spear.cs:Umbilical     points = Random.Range(10,20)；life = (2, Lerp(150,200, rand^0.3))
                         points[0] ← （spider.graphicsModule as PlayerGraphics).tail[0].pos
                         末点 ← maggot.bodyChunks[0].pos - maggot.rotation * 25
                         相邻点最小间距 6；LerpMap(|v|,1,30,0.99,0.8) 阻尼
                         重力 vy += Lerp(0.1, 0.6, life)
                         宽度 = 0.5 * InverseLerp(0, 0.3, life)
  ApplyPalette           threadCol = Lerp((0.95,0.8,0.55), fogColor, 0.2) → 约 (242,204,140)
绘制优先级低于生物（用户口径 + 原本就在猫下层）。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

THREAD_RGB = (242, 204, 140)     # ApplyPalette threadCol（fog 只占 0.2，直接取本色）
LINK_DIST = 6.0                  # 相邻两点最小间距
LIFE_MIN, LIFE_MAX = 150.0, 200.0
LIFE_START = 2.0                 # points[i,3].x 初值（2）
WIDTH_FULL = 0.3                 # InverseLerp(0, 0.3, life)
GRAV_LO, GRAV_HI = 0.1, 0.6


def _lerp(a, b, t):
    return a + (b - a) * t


def _ilerp(a, b, v):
    if a == b:
        return 0.0
    return min(1.0, max(0.0, (v - a) / (b - a)))


class NeedleThread:
    """尾巴根 ↔ 针尾的一条自由点细线。"""

    __slots__ = ("pts", "spear", "dead")

    def __init__(self, tail_xy, vx, vy, rng):
        n = rng.randint(10, 19)                     # Random.Range(10, 20)
        tx, ty = tail_xy
        self.pts = []
        for _ in range(n):
            x = tx + rng.uniform(-1.0, 1.0)
            y = ty + rng.uniform(-1.0, 1.0)
            k = 0.3 * rng.random()
            pvx = vx * k + rng.uniform(-1.0, 1.0) * (rng.random() * 1.5)
            pvy = vy * k + rng.uniform(-1.0, 1.0) * (rng.random() * 1.5)
            life = _lerp(LIFE_MIN, LIFE_MAX, rng.random() ** 0.3)
            self.pts.append([x, y, x, y, pvx, pvy, LIFE_START, life])
        self.spear = None
        self.dead = False

    def _life(self, i):
        if i > 0:
            return min(self.pts[i][6], self.pts[i - 1][6])
        return self.pts[i][6]

    def update(self, head_xy, tail_xy) -> None:
        """一 tick：自由点积分 + 相邻约束 + 寿命衰减；两端钉住。"""
        pts = self.pts
        n = len(pts)
        alive = False
        for i in range(n):
            q = pts[i]
            q[2], q[3] = q[0], q[1]
            q[0] += q[4]
            q[1] += q[5]
            spd = math.hypot(q[4], q[5])
            k = _lerp(0.99, 0.8, _ilerp(1.0, 30.0, spd))
            q[4] *= k
            q[5] *= k
            q[5] += _lerp(GRAV_LO, GRAV_HI, self._life(i))    # y↓：重力取正
            if self._life(i) <= 0.0:
                continue
            if i > 0:
                dx, dy = q[0] - pts[i - 1][0], q[1] - pts[i - 1][1]
                d = math.hypot(dx, dy)
                if d > LINK_DIST:
                    ux, uy = dx / d, dy / d
                    pull = d - LINK_DIST
                    back = pts[i - 1]
                    q[0] -= ux * pull * 0.15
                    q[1] -= uy * pull * 0.15
                    q[4] -= ux * pull * 0.25
                    q[5] -= uy * pull * 0.25
                    back[0] += ux * pull * 0.15
                    back[1] += uy * pull * 0.15
                    back[4] += ux * pull * 0.25
                    back[5] += uy * pull * 0.25
            if i > 1 and self._life(i - 1) > 0.0:
                dx, dy = q[0] - pts[i - 2][0], q[1] - pts[i - 2][1]
                d = math.hypot(dx, dy) or 1.0
                ux, uy = dx / d, dy / d
                q[4] += ux * 0.6
                q[5] += uy * 0.6
                pts[i - 2][4] -= ux * 0.6
                pts[i - 2][5] -= uy * 0.6
            q[6] -= 1.0 / q[7]
            if q[6] > 0.0:
                alive = True
        if self._life(0) > 0.0:                       # 首点钉在尾巴根
            pts[0][0], pts[0][1] = head_xy
            pts[0][4] = pts[0][5] = 0.0
        if self._life(n - 1) > 0.0:                   # 末点钉在针尾
            pts[n - 1][0], pts[n - 1][1] = tail_xy
            pts[n - 1][4] = pts[n - 1][5] = 0.0
        self.dead = not alive

    def draw(self, painter) -> None:
        """逐段细线：宽度 2*0.5*InverseLerp(0,0.3,life)，alpha = min(life,1)。"""
        pts = self.pts
        n = len(pts)
        if n < 2:
            return
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(1, n):
            life = min(self._life(i), self._life(i - 1))
            if life <= 0.0:
                continue
            col = QColor(*THREAD_RGB)
            col.setAlphaF(min(1.0, life))
            pen = QPen(col, max(0.6, _ilerp(0.0, WIDTH_FULL, life)))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(pts[i - 1][0], pts[i - 1][1]),
                             QPointF(pts[i][0], pts[i][1]))
        painter.restore()
