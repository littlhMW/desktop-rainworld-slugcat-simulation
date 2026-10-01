# -*- coding: utf-8 -*-
"""矛大师掷出的活针与尾巴之间那条有机细线（反编译 Spear.Umbilical，Spear.cs:714）。

wiki：「掷出白色的矛针后，可以看到一条长的有机线连接矛和矛大师，就像运输营养
物质一样，前提是矛命中了活物。」原版在 Weapon.Thrown 时 AddObject 一条
Umbilical，一端钉在矛大师 tail[0]（尾巴根），另一端钉在矛尖后方 25px 的矛尾上，
自身是 10~19 个自由点，宽约 1px 的米黄色细线。
消失时机（用户口径，覆盖原版 Spear_NeedleDisconnect 的那几处）：只有
① 这根针实体被删掉、或 ② 下一根活针出现 时才断；扎中生物 / 插墙 / 落地都不再断。

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

# 细线颜色：从尾巴根（红）渐变到针尾（黄）—— 用户指定（原版 ApplyPalette
# threadCol 是一色米黄，这里按用户口径改成渐变）。
THREAD_RGB = (242, 204, 140)     # 兼容旧引用（已不再作为收色）
THREAD_TAIL_RGB = (226, 58, 44)  # 尾巴根端：红
THREAD_TIP_RGB = (248, 222, 82)  # 针端：黄
LINK_DIST = 6.0                  # 相邻两点最小间距
LIFE_MIN, LIFE_MAX = 150.0, 200.0
LIFE_START = 2.0                 # points[i,3].x 初值（2）
WIDTH_FULL = 0.3                 # InverseLerp(0, 0.3, life)
GRAV_LO, GRAV_HI = 0.1, 0.6
LIFE_HOLD = 1.0                  # 寿命下限：只负责把重力/宽度带到稳态，不再归零
THREAD_HOLD_TICKS = 80.0         # 拉出后先完整显示 2 秒（定步长 40fps）再开始渐隐
THREAD_FADE_TICKS = 40.0         # 再用 1 秒渐隐到 0，这条线才真的消失


def _lerp(a, b, t):
    return a + (b - a) * t


def _ilerp(a, b, v):
    if a == b:
        return 0.0
    return min(1.0, max(0.0, (v - a) / (b - a)))


class NeedleThread:
    """尾巴根 ↔ 针尾的一条自由点细线。"""

    __slots__ = ("pts", "spear", "dead", "last_head", "age", "alpha")

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
        self.last_head = (float(tail_xy[0]), float(tail_xy[1]))
        self.age = 0.0                                  # 出生后经过的 tick
        self.alpha = 1.0                                 # 整体不透明度（1=不透明）

    def _life(self, i):
        if i > 0:
            return min(self.pts[i][6], self.pts[i - 1][6])
        return self.pts[i][6]

    def update(self, head_xy, tail_xy) -> None:
        """一 tick：自由点积分 + 相邻约束 + 寿命夹到稳态；两端钉住。

        生命周期（用户口径）：拉出后完整显示 THREAD_HOLD_TICKS（2 秒），之后用
        THREAD_FADE_TICKS 渐隐到 0 并置 dead，由 items._needle_thread_tick 回收；
        针实体被删 / 被剪断时也会立刻消失（见那里的过滤器）。
        """
        pts = self.pts
        n = len(pts)
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
            if q[6] < LIFE_HOLD:
                # 原版寿命到点就 Destroy()；用户口径改成「线只跟着实体走」：
                # 寿命只把重力/宽度带到稳态，之后一直挂着。
                q[6] = LIFE_HOLD
        if self._life(0) > 0.0:                       # 首点钉在尾巴根
            pts[0][0], pts[0][1] = head_xy
            pts[0][4] = pts[0][5] = 0.0
        self.last_head = (pts[0][0], pts[0][1])
        if self._life(n - 1) > 0.0:                   # 末点钉在针尾
            pts[n - 1][0], pts[n - 1][1] = tail_xy
            pts[n - 1][4] = pts[n - 1][5] = 0.0
        self.age += 1.0
        if self.age > THREAD_HOLD_TICKS:               # 2 秒后：渐隐
            self.alpha = max(0.0, 1.0 - (self.age - THREAD_HOLD_TICKS)
                             / THREAD_FADE_TICKS)
            if self.alpha <= 0.0:
                self.dead = True                       # 褪尽：真的消失

    def _shade(self, i):
        """第 i 个节点的颜色：首端（尾巴根）红 → 末端（针）黄。"""
        n = len(self.pts)
        t = 0.0 if n < 2 else i / float(n - 1)
        a, b = THREAD_TAIL_RGB, THREAD_TIP_RGB
        return (int(a[0] + (b[0] - a[0]) * t),
                int(a[1] + (b[1] - a[1]) * t),
                int(a[2] + (b[2] - a[2]) * t))

    def draw(self, painter) -> None:
        """逐段细线：宽度 2*0.5*InverseLerp(0,0.3,life)，alpha = min(life,1)*self.alpha。

        颜色沿线长从尾巴根的红渐变到针端的黄（用户口径）。
        """
        pts = self.pts
        n = len(pts)
        if n < 2 or self.alpha <= 0.0:
            return
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(1, n):
            life = min(self._life(i), self._life(i - 1))
            if life <= 0.0:
                continue
            col = QColor(*self._shade(i))
            col.setAlphaF(min(1.0, life) * self.alpha)
            pen = QPen(col, max(0.6, _ilerp(0.0, WIDTH_FULL, life)))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(pts[i - 1][0], pts[i - 1][1]),
                             QPointF(pts[i][0], pts[i][1]))
        painter.restore()
