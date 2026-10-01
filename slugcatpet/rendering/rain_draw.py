# -*- coding: utf-8 -*-
"""暴雨渲染：稳定的屏幕空间雨幕 + 低对比度雨线 + 冷色暴雨遮罩。

关键点：
* 暴雨雨幕/遮罩不随世界震屏平移，因此窗口边缘不会露出透明白边。
* 庇护所仍跟着世界震动，安全洞用同样的 shake 偏移跟随庇护所。
* 所有天气层都向窗口外预留 bleed，给亚像素和极端抖动留下安全余量。
"""
from __future__ import annotations

import random

from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import (
    QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QRegion
)

from ..world.rain import FIRST_DROP_FLASH


_PATTERN = 256
SCREEN_BLEED = 24.0
_BOTTOM_BLEED = 52.0

_SHEET_RGBA = (133, 130, 145)
_DROP_RGB = (169, 166, 178)
_STORM_TOP = (47, 45, 57)
_STORM_BOTTOM = (18, 18, 25)
_FOG = (113, 108, 123)

_ALPHA_BANDS = (0.30, 0.48, 0.68)


def make_rain_patterns(seed=0x5A17):
    """预生成两张低分辨率雨幕贴图。只在建窗时算一次。"""
    rng = random.Random(seed)
    out = []
    for k in range(2):
        img = QImage(_PATTERN, _PATTERN, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            slant = 2.0 + 3.0 * k
            count = 145 if k == 0 else 190
            for _ in range(count):
                x = rng.uniform(-slant - 10.0, _PATTERN + 10.0)
                y = rng.uniform(-_PATTERN, _PATTERN)
                ln = rng.uniform(35.0, 105.0) * (1.0 + 0.10 * k)
                a = int(rng.uniform(16, 34) + 7 * k)
                w = 0.8 if rng.random() < 0.86 else 1.2
                p.setPen(QPen(QColor(*_SHEET_RGBA, a), w))
                p.drawLine(QPointF(x, y), QPointF(x + slant, y + ln))
        finally:
            p.end()
        out.append(img)
    return tuple(out)


def safe_regions(shelters, shake=(0.0, 0.0)):
    """返回每间庇护所的安全矩形，并把矩形移动到当前世界抖动后的屏幕位置。"""
    sx, sy = shake
    out = []
    for sh in (shelters or ()):
        x0, y0, x1, y1 = sh.safe_rect()
        out.append((x0 + sx, y0 + sy, x1 + sx, y1 + sy))
    return out


def _punch(p, holes, WL, HL, shake=(0.0, 0.0)):
    """从天气层剪辑里挖掉庇护所安全区。天气本身不震，但洞跟着庇护所走。"""
    reg = QRegion(
        QRect(
            int(-SCREEN_BLEED),
            int(-SCREEN_BLEED),
            int(WL + SCREEN_BLEED * 2.0),
            int(HL + _BOTTOM_BLEED + SCREEN_BLEED),
        )
    )
    for x0, y0, x1, y1 in holes:
        reg = reg.subtracted(
            QRegion(
                QRect(
                    int(x0),
                    int(y0),
                    max(1, int(x1 - x0) + 1),
                    max(1, int(y1 - y0) + 1),
                )
            )
        )
    p.setClipRegion(reg, Qt.ClipOperation.IntersectClip)


def _storm_mist(p, rain, WL, HL):
    """薄雾底层：只在中高雨强出现，负责把暴雨颜色统一起来。"""
    m = float(getattr(rain, "mist", 0.0))
    if m <= 0.002:
        return
    grad = QLinearGradient(0.0, 0.0, 0.0, HL)
    grad.setColorAt(0.0, QColor(*_FOG, int(18 + 24 * m)))
    grad.setColorAt(0.45, QColor(*_FOG, int(10 + 14 * m)))
    grad.setColorAt(1.0, QColor(*_FOG, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRect(QRectF(-SCREEN_BLEED, -SCREEN_BLEED,
                      WL + SCREEN_BLEED * 2.0, HL + _BOTTOM_BLEED))


def draw_rain_under(p, rain, shelters, WL, HL, shake=(0.0, 0.0)):
    """稳定屏幕空间雨幕：画在猫/物体后面。"""
    if rain is None:
        return
    density = float(getattr(rain, "sheet_density", 0.0))
    mist = float(getattr(rain, "mist", 0.0))
    if density <= 0.002 and mist <= 0.002:
        return

    p.save()
    try:
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        holes = safe_regions(shelters, shake)
        _punch(p, holes, WL, HL)

        _storm_mist(p, rain, WL, HL)

        pats = getattr(rain, "patterns", None)
        if pats and density > 0.01:
            off = float(getattr(rain, "tile_off", 0.0))
            for k, img in enumerate(pats):
                scale = _PATTERN * (1.0 if k == 0 else 2.0)
                ox = ((off * (0.26 + 0.16 * k)) % scale) - scale
                oy = ((off * (0.75 + 0.25 * k)) % scale) - scale
                alpha = min(0.42, 0.10 + density * (0.20 if k == 0 else 0.27))
                p.setOpacity(alpha)
                x = ox
                while x < WL + SCREEN_BLEED:
                    y = oy
                    while y < HL + _BOTTOM_BLEED:
                        p.drawImage(QRectF(x, y, scale, scale), img)
                        y += scale
                    x += scale
        p.setOpacity(1.0)
    finally:
        p.restore()


def draw_rain_over(p, rain, shelters, WL, HL, shake=(0.0, 0.0)):
    """稳定屏幕空间前景雨线：只画近景，避免把画面盖成白色噪点。"""
    if rain is None:
        return
    i = float(getattr(rain, "intensity", 0.0))
    flash = int(getattr(rain, "flash", 0))
    if i <= 0.02 and flash <= 0:
        return

    p.save()
    try:
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        _punch(p, safe_regions(shelters, shake), WL, HL)

        n = min(int(getattr(rain, "visible_drops", 0)), len(getattr(rain, "drops", ())))
        if n > 0:
            near = int(n * (0.22 + 0.58 * i))
            # A storm can draw 100+ drops per frame.  Reusing the small set of
            # pens avoids constructing QColor/QPen objects in the inner loop.
            pen_cache = {}
            heavy_cache = {}
            for k in range(near):
                d = rain.drops[k]
                band = d.seed % len(_ALPHA_BANDS)
                key = (band, d.width)
                pen = pen_cache.get(key)
                if pen is None:
                    col = QColor(*_DROP_RGB, int(255 * _ALPHA_BANDS[band] * (0.42 + 0.55 * i)))
                    pen = QPen(col, d.width)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    pen_cache[key] = pen
                p.setPen(pen)
                length = d.length * (1.1 + 0.72 * i)
                p.drawLine(
                    QPointF(d.x, d.y),
                    QPointF(d.x + length * (0.025 + 0.018 * i), d.y + length),
                )
                # RoomRain.cs:343-351 的 bulletDrips 是暴雨阶段少量更重的近景雨柱。
                # 用既有固定雨滴池选样，不在 paintEvent 里新建粒子。
                if i > 0.62 and d.seed % 13 == 0:
                    force = (i - 0.62) / 0.38
                    hkey = int(force * 4.0)
                    hpen = heavy_cache.get(hkey)
                    if hpen is None:
                        hpen = QPen(QColor(188, 184, 198, int(34 + 58 * force)),
                                    1.7 + 0.8 * force)
                        heavy_cache[hkey] = hpen
                    p.setPen(hpen)
                    p.drawLine(QPointF(d.x - 1.5, d.y - length * 0.55),
                               QPointF(d.x + length * 0.12,
                                       d.y + length * (0.90 + 0.55 * force)))

        # 原版 ScreenRain 是密集、近竖直的雨幕。透明桌面窗不能采样背后桌面，
        # 因此只叠加极低对比度的窄竖纹；不绘制装饰性的水平正弦线。
        if i > 0.60:
            force = (i - 0.60) / 0.40
            phase = float(getattr(rain, 'tile_off', 0.0)) * 0.42
            sheet_pen = QPen(QColor(147, 143, 157, int(5 + 10 * force)),
                             0.7 + 0.35 * force)
            for col in range(20):
                x = ((col * (WL / 20.0) + phase * (1.0 + col % 3))
                     % (WL + 20.0)) - 10.0
                p.setPen(sheet_pen)
                p.drawLine(QPointF(x, -SCREEN_BLEED), QPointF(x + 6.0, HL + _BOTTOM_BLEED))

        # 第一滴重雨：聚焦的落点，不再用整屏闪白。
        if flash > 0 and getattr(rain, "impact_xy", None) is not None:
            ix, iy = rain.impact_xy
            t = flash / float(FIRST_DROP_FLASH)
            pulse = max(0.0, min(1.0, t))
            alpha = int(48 + 132 * pulse)
            p.setPen(QPen(QColor(205, 202, 214, alpha), 2.2))
            ln = 32.0 + 64.0 * pulse
            p.drawLine(QPointF(ix, iy - ln), QPointF(ix + 6.0, iy))

            r = 7.0 + 22.0 * (1.0 - pulse)
            p.setPen(QPen(QColor(174, 170, 186, int(34 + 90 * pulse)), 1.4))
            p.drawEllipse(QPointF(ix, iy - 1.5), r * 0.55, r * 0.18)

            p.setPen(QPen(QColor(190, 186, 202, int(24 + 78 * pulse)), 1.0))
            p.drawLine(QPointF(ix - r, iy - 3.0),
                       QPointF(ix - r * 0.25, iy - 8.0 * (1.0 - pulse)))
            p.drawLine(QPointF(ix + r, iy - 3.0),
                       QPointF(ix + r * 0.25, iy - 8.0 * (1.0 - pulse)))
    finally:
        p.restore()


def draw_rain_darkness(p, rain, shelters, WL, HL, shake=(0.0, 0.0)):
    """稳定屏幕空间暴雨遮罩：冷蓝灰渐变 + 轻微边缘暗化，不随震屏移动。"""
    if rain is None:
        return
    dk = float(getattr(rain, "darkness", 0.0))
    if dk <= 0.002:
        return

    p.save()
    try:
        holes = safe_regions(shelters, shake)

        # 先做一层带色的全屏暴雨滤镜。
        grad = QLinearGradient(0.0, 0.0, 0.0, HL + _BOTTOM_BLEED)
        grad.setColorAt(0.0, QColor(*_STORM_TOP, int(205 * dk)))
        grad.setColorAt(0.38, QColor(28, 40, 57, int(224 * dk)))
        grad.setColorAt(1.0, QColor(*_STORM_BOTTOM, int(238 * dk)))

        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(QRectF(-SCREEN_BLEED, -SCREEN_BLEED,
                            WL + SCREEN_BLEED * 2.0,
                            HL + _BOTTOM_BLEED + SCREEN_BLEED))
        for hx0, hy0, hx1, hy1 in holes:
            path.addRect(QRectF(hx0, hy0, hx1 - hx0, hy1 - hy0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(path)

        # 边缘渐暗，只增加氛围，不把中心压黑。
        edge = QRadialGradient(QPointF(WL * 0.50, HL * 0.46), max(WL, HL) * 0.78)
        edge.setColorAt(0.0, QColor(20, 27, 40, 0))
        edge.setColorAt(0.68, QColor(17, 24, 36, 8 + int(18 * dk)))
        edge.setColorAt(1.0, QColor(8, 13, 22, 28 + int(32 * dk)))

        edge_path = QPainterPath()
        edge_path.setFillRule(Qt.FillRule.OddEvenFill)
        edge_path.addRect(QRectF(-SCREEN_BLEED, -SCREEN_BLEED,
                                 WL + SCREEN_BLEED * 2.0,
                                 HL + _BOTTOM_BLEED + SCREEN_BLEED))
        for hx0, hy0, hx1, hy1 in holes:
            edge_path.addRect(QRectF(hx0, hy0, hx1 - hx0, hy1 - hy0))
        p.setBrush(edge)
        p.drawPath(edge_path)
    finally:
        p.restore()
