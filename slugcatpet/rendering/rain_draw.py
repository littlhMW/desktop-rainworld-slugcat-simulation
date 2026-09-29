# -*- coding: utf-8 -*-
"""暴雨渲染层：变暗 / 远景雨幕 / 前景雨滴 / 第一滴重雨。

雨是「廉价屏幕层」，不是粒子洪流：远景雨幕是两张预生成的低分辨率 QImage 循环
平铺（``drawImage`` 而已），前景雨滴直接画池中前 N 条，门帘/暗化都用
``DifferenceClip`` 把 ``shelter.safe_rect`` 挖掉 —— 庇护所里既不被压暗也淋不到雨，
于是「安全区」是自己读出来的，不需要额外标记。
"""
from __future__ import annotations

import random

from PySide6.QtCore import Qt, QPointF, QRectF, QRect
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QRegion

from ..world.rain import FIRST_DROP_FLASH

_PATTERN = 256            # 雨幕贴图边长（循环平铺）
_ALPHA_BANDS = (0.40, 0.64, 0.88)
_SHEET_RGBA = (196, 214, 234)
_DARK_RGB = (16, 18, 26)
_DROP_RGB = (204, 222, 242)


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
            slant = 9.0 + 11.0 * k
            for _ in range(80 + 70 * k):
                x = rng.uniform(-slant, _PATTERN + slant)
                y = rng.uniform(-_PATTERN, _PATTERN)
                ln = rng.uniform(22.0, 66.0)
                a = int(rng.uniform(24, 60)) + 10 * k
                w = 1.0 if rng.random() < 0.72 else 2.0
                p.setPen(QPen(QColor(*_SHEET_RGBA, a), w))
                p.drawLine(QPointF(x, y), QPointF(x + slant, y + ln))
        finally:
            p.end()
        out.append(img)
    return tuple(out)


def safe_regions(shelters):
    """每间庇护所各自的矩形（**不是**并集）。

    旧实现 ``safe_hole`` 名字叫并集、实际却对全部矩形做 min/max 合并：场上放两间
    相距很远的庇护所时，中间整片露天区域会被一起从雨幕里挖掉。这里改成逐个矩形
    返回，各自挖各自的洞。
    """
    return [sh.safe_rect() for sh in (shelters or ())]


def _punch(p, holes, WL, HL):
    """把每间庇护所的区域从当前剪辑里挖掉（不改画笔，只改 clip）。

    用 QRegion 做差集：PySide6 的 Qt.ClipOperation 没有 DifferenceClip。
    """
    reg = QRegion(QRect(0, -4, int(WL) + 1, int(HL) + 48))
    for (x0, y0, x1, y1) in (holes or ()):
        reg = reg.subtracted(QRegion(QRect(int(x0), int(y0),
                                           int(x1 - x0) + 1, int(y1 - y0) + 1)))
    p.setClipRegion(reg, Qt.ClipOperation.IntersectClip)


def draw_rain_under(p, rain, shelters, WL, HL):
    """远景雨幕（在猫身之前画）。"""
    if rain is None:
        return
    d = rain.sheet_density
    if d <= 0.002:
        return
    pats = getattr(rain, "patterns", None)
    if not pats:
        return
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    _punch(p, safe_regions(shelters), WL, HL)
    p.setOpacity(min(0.70, 0.14 + 0.62 * d))
    off = rain.tile_off
    for k, img in enumerate(pats):
        s = _PATTERN * (1.0 if k == 0 else 2.0)
        ox = ((off * (0.35 + 0.30 * k)) % s) - s
        oy = ((off * (1.00 + 0.45 * k)) % s) - s
        x = ox
        while x < WL:
            y = oy
            while y < HL:
                p.drawImage(QRectF(x, y, s, s), img)
                y += s
            x += s
    p.restore()


def draw_rain_over(p, rain, shelters, WL, HL):
    """前景雨滴 + 落地溅射 + 第一滴重雨（在特效附近画）。"""
    if rain is None:
        return
    i = rain.intensity
    flash = getattr(rain, "flash", 0)
    if i <= 0.02 and flash <= 0:
        return
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    _punch(p, safe_regions(shelters), WL, HL)
    n = min(rain.visible_drops, len(rain.drops))
    scale = min(1.0, 0.35 + 0.75 * i)
    if n > 0:
        for w in (1.0, 2.0):
            for band in range(len(_ALPHA_BANDS)):
                col = QColor(*_DROP_RGB)
                col.setAlphaF(min(1.0, _ALPHA_BANDS[band] * scale))
                pen = QPen(col, w)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                for k in range(n):
                    d = rain.drops[k]
                    if d.width != w or (d.seed % len(_ALPHA_BANDS)) != band:
                        continue
                    x, y = d.x, d.y
                    p.drawLine(QPointF(x, y), QPointF(x + d.length * 0.16, y + d.length))
    # 第一滴重雨：一条特别长的雨线 + 落地 splash + 数点余韵
    if flash > 0 and rain.impact_xy is not None:
        ix, iy = rain.impact_xy
        t = flash / float(FIRST_DROP_FLASH)
        ln = 40.0 + 70.0 * (1.0 - t)
        p.setPen(QPen(QColor(234, 246, 255, int(60 + 180 * t)), 2.6))
        p.drawLine(QPointF(ix, iy - ln), QPointF(ix + 7.0, iy))
        r = 6.0 + 26.0 * (1.0 - t)
        p.setPen(QPen(QColor(216, 234, 252, int(40 + 150 * t)), 2.0))
        p.drawLine(QPointF(ix - r, iy - 3.0), QPointF(ix - r * 0.25, iy - 9.0 * (1.0 - t)))
        p.drawLine(QPointF(ix + r, iy - 3.0), QPointF(ix + r * 0.25, iy - 9.0 * (1.0 - t)))
    p.restore()


def draw_rain_darkness(p, rain, shelters, WL, HL):
    """全屏变暗（最后画）。庇护所安全区挖洞 —— 里面是唯一不被压暗的地方。"""
    if rain is None:
        return
    dk = rain.darkness
    if dk <= 0.002:
        return
    r, g, b = _DARK_RGB
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    path.addRect(QRectF(0.0, -4.0, WL, HL + 44.0))
    for (hx0, hy0, hx1, hy1) in safe_regions(shelters):
        path.addRect(QRectF(hx0, hy0, hx1 - hx0, hy1 - hy0))
    p.fillPath(path, QColor(r, g, b, int(255 * dk)))
    p.restore()