# -*- coding: utf-8 -*-
"""面条蝇 NeedleWorm 渲染（对照 NeedleWormGraphics.DrawSprites，坐标 y↓）。

原版身体是 TriangleMesh 程序化网格（不是贴图），眼睛/翅膀/腿/卵复用现成元件：
  JetFishEyeB（4x4 眼）、CentipedeWing（8x52 翅）、JetFishFlipper3（23x18 鳍）。
这里同样程序化：躯干+尾用 draw_rope 画中轴带，再叠高光带、眼睛、翅膀、鳍。
"""
from __future__ import annotations
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen

from ..core.units import clampf, lerp, inv_lerp
from ..core.gfxmath import _hsl2rgb
from ..rendering.primitives import blit, draw_rope
from ..rendering.pixelmode import aa_hint
from .needleworm import AGE_EGG, WING_SEG, _lerp_map

BLACK_RGB = (27, 11, 33)
FOG_RGB = (78, 92, 104)


def _rgb(h, sl, l):
    r, g, b = _hsl2rgb(h % 1.0, sl, l)
    return (int(clampf(round(r * 255.0), 0, 255)),
            int(clampf(round(g * 255.0), 0, 255)),
            int(clampf(round(b * 255.0), 0, 255)))


def _perp(ux, uy):
    """Custom.PerpendicularVector（原版 y↑ 写成 (-y, x)；这里保持同一式子）。"""
    return -uy, ux


def _aim(ux, uy) -> float:
    """0 = 上、顺时针为正（Qt 同号）。"""
    return math.degrees(math.atan2(ux, -uy))


def _wing_rgb(body, hi, ang):
    """原版翅膀顶点色 = 体色↔高光色（CicadaWing 着色器再乘一圈透明）。"""
    t = clampf(0.1 + 0.35 * ang, 0.0, 0.45)
    return (int(body[0] + (hi[0] - body[0]) * t),
            int(body[1] + (hi[1] - body[1]) * t),
            int(body[2] + (hi[2] - body[2]) * t))


def _dir(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-6 else (0.0, -1.0)


def palette(nw):
    """-> (bodyColor, highLightColor)：NeedleWormGraphics.ApplyPalette。"""
    num = nw.hue + 0.478
    light = nw.lightness
    body = _rgb(num, _lerp_map(light, 0.5, 1.0, 0.9, 0.5), lerp(0.1, 0.8, light * light))
    hi = _rgb(num, _lerp_map(light, 0.5, 1.0, 0.5, 1.0), lerp(0.2, 1.0, light))
    return body, hi


def draw_needle_egg(painter, atlas, nw, ts) -> None:
    """卵：NeedleEgg 外壳（波瓣壳 + 半透明内芯）。"""
    x = lerp(nw.last_x, nw.x, ts)
    y = lerp(nw.last_y, nw.y, ts)
    r = nw.head_rad
    h = 0.99 + 0.09 * ((nw.hue * 7.3) % 1.0)
    shell = _rgb(h, lerp(0.8, 1.0, (nw.hue * 3.1) % 1.0), 0.5)
    painter.save()
    aa_hint(painter)
    pen = QPen(QColor(*_rgb(h, 1.0, 0.32)))
    pen.setWidthF(1.6)
    painter.setPen(pen)
    painter.setBrush(QColor(*shell))
    painter.drawEllipse(x - r, y - r * 1.15, r * 2.0, r * 2.3)
    painter.restore()


def draw_needleworm(painter, atlas, nw, ts) -> None:
    """画一只面条蝇（幼体/成体）。"""
    painter.save()
    aa_hint(painter)
    body, hi = palette(nw)
    pts, rads = [], []
    for s in nw.seg:
        pts.append((lerp(s.lx, s.x, ts), lerp(s.ly, s.y, ts)))
        rads.append(max(0.8, s.rad))
    # 身体：吻尖 → 尾梢的中轴带
    draw_rope(painter, pts, [r * 2.0 for r in rads], body)
    # 高光带：躯干开始、沿 (-1,+1) 偏一点、宽度 /3.2（原版 HighLightMesh）
    sn = nw.snout_n
    if len(pts) > sn + 2:
        hp, hr = [], []
        for i in range(sn, len(pts)):
            x, y = pts[i]
            hp.append((x - 1.0, y + 1.0))
            hr.append(max(0.5, rads[i] / 3.2))
        draw_rope(painter, hp, [r * 2.0 for r in hr], hi)
    if nw.age == AGE_EGG:
        painter.restore()
        return
    # 翅膀：挂在 WING_SEG 的躯干节上，点/成体各两对
    flap = lerp(nw.last_wing_flap, nw.wing_flap, ts)
    f = clampf((flap % 1.0), 0.0, 1.0)
    for ci in [sn + k for k in WING_SEG[nw.age]]:
        if ci >= len(pts):
            continue
        bx, by = pts[ci]
        seg_dir = _dir(pts[ci - 1][0], pts[ci - 1][1], bx, by) if ci > 0 else (1.0, 0.0)
        for m in (0, 1):
            ang = (0.5 + 0.5 * math.sin((flap + (0.33 if m == 0 else 0.0)) * math.tau))
            ext = 18.0 + 18.0 * math.sin((flap + (0.33 if m == 0 else 0.0)) * math.tau)
            tip = (bx + seg_dir[0] * 4.0 - seg_dir[1] * 26.0 * nw.wings_size,
                   by + seg_dir[1] * 4.0 + seg_dir[0] * 26.0 * nw.wings_size
                   + ext * 0.35 * (1.0 if nw.facing >= 0 else -1.0))
            d = _dir(bx, by, tip[0], tip[1])
            rot = _aim(d[0], d[1]) + 180.0
            blit(painter, atlas, "CentipedeWing", bx, by, rot,
                 nw.wings_size * 0.55, 0.55, _wing_rgb(body, hi, ang),
                 ax=0.5, ay=1.0)
    # 眼睛：头顶两侧
    if sn + 1 < len(pts):
        hx, hy = pts[sn]
        v3 = _dir(hx, hy, pts[1][0], pts[1][1])
        hx = lerp(hx, pts[0][0], 0.4)
        hy = lerp(hy, pts[0][1], 0.4)
        mid = pts[min(len(pts) - 1, sn + max(1, nw.body_n // 2))]
        axis = _dir(mid[0], mid[1], pts[sn][0], pts[sn][1])
        t = inv_lerp(0.0, 0.7, v3[0] * axis[0] + v3[1] * axis[1])
        px, py = _perp(v3[0], v3[1])
        sc = 0.65 if nw.small else 1.0
        for i in (0, 1):
            s = -1.0 if ((i == 0) != (v3[0] < 0.0)) else 1.0
            off = 4.0 * sc * s * v3[1]
            ex, ey = hx + px * off, hy + py * off
            rot = _aim(v3[0] + axis[0], v3[1] + axis[1])
            blit(painter, atlas, "JetFishEyeB", ex, ey, rot,
                 lerp(0.8, 0.6, t) * sc, lerp(1.1, 1.5, t) * sc, BLACK_RGB)
    painter.restore()
