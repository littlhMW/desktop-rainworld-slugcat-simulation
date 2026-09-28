# -*- coding: utf-8 -*-
"""Squidcada (Cicada) renderer, transcribed from CicadaGraphics.

Screen coords are y-down; the original is y-up, so:
  * "aim" angles (0 = up, positive = right) are identical in both.
  * aim angles and rotation values are numerically identical (both add).
"""
from __future__ import annotations
import math

from PySide6.QtGui import QPainter

from ..core.units import clampf, lerp
from ..core.gfxmath import _hsl2rgb
from ..rendering.primitives import blit, draw_rope
from ..rendering.pixelmode import aa_hint

FOG_RGB = (78, 92, 104)           # stand-in for palette.fogColor
BLACK_RGB = (27, 11, 33)          # same as palette.blackColor
CHUNK_GAP = 14.0                  # Cicada.cs bodyChunkConnections[0].distance
BODY_MID = CHUNK_GAP * 0.5        # sprites sit on the midpoint of the two chunks
TENT_REACH = (24.0, 19.0)         # ConnectToPoint length, n == 0 / n == 1
TENT_HALF = (1.6, 1.0, 0.8)       # tube half widths per segment
FLAP_PERIOD = 3.0                 # wingTimeAdd 0..3


def _rgb(h, sl, l):
    r, g, b = _hsl2rgb(h % 1.0, sl, l)
    return (int(clampf(round(r * 255.0), 0, 255)), int(clampf(round(g * 255.0), 0, 255)),
            int(clampf(round(b * 255.0), 0, 255)))


def _mix(a, b, t):
    t = clampf(t, 0.0, 1.0)
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _inv(a: float, b: float, v: float) -> float:
    """Mathf.InverseLerp (clamped)."""
    if b == a:
        return 0.0
    return clampf((v - a) / (b - a), 0.0, 1.0)


def _aim(ux: float, uy: float) -> float:
    """AimFromOneVectorToAnother(zero, u): 0 = up, positive = right."""
    return math.degrees(math.atan2(ux, -uy))


def palette(sc):
    """-> (body, shield, eyes1, eyes2, highlight); cf. CicadaGraphics.ApplyPalette."""
    hue = sc.hue
    vivid = _rgb(hue, 1.0, 0.5)
    if sc.male:                                   # gender=true
        body = _mix(_rgb(hue, 0.2, 0.9), FOG_RGB, 0.1)
        return (body, _mix(body, _rgb(hue, 0.5, 0.4), 0.8),
                _mix(body, BLACK_RGB, 0.8), vivid, _mix(body, (255, 255, 255), 0.7))
    body = _mix(_rgb(hue, 1.0, 0.1), BLACK_RGB, 0.85)     # gender=false
    return (body, _mix(body, _rgb(hue, 0.5, 0.5), 0.4),
            vivid, BLACK_RGB, _mix(body, vivid, 0.07))


def _tent_points(sc, ux, uy, px, py, zx, zy, ax, m, l, ts):
    """One tentacle: 3-segment polyline from the body front to the limb tip."""
    x, y = lerp(sc.last_x, sc.x, ts), lerp(sc.last_y, sc.y, ts)
    v3x = x + ux * (8.0 + 2.0 * ax) + px * (zx * 3.0)
    v3y = y + uy * (8.0 + 2.0 * ax) + py * (zx * 3.0)
    sx, sy = v3x, v3y
    if l == 0:
        sx, sy = v3x + ux * (3.0 * ax), v3y + uy * (3.0 * ax)
    t0 = sc.tent_last[m * 2 + l]
    t1 = sc.tent[m * 2 + l]
    tx, ty = lerp(t0[0], t1[0], ts), lerp(t0[1], t1[1], ts)
    pts = [(sx, sy)]
    n12 = 1.0
    for n in range(3):
        if n < 2:
            fq = float(n + 1) / 3.0
            vx, vy = lerp(v3x, tx, fq), lerp(v3y, ty, fq)
            dl = math.hypot(vx - sx, vy - sy)
            dot = ((vx - sx) * ux + (vy - sy) * uy) / dl if dl > 1e-6 else 1.0
            push = n12 * 15.0 * _inv(1.0, -1.0, dot)
            vx += ux * push
            vy += uy * push
            if l == 1 and n == 0:
                vx += px * (zx * n12 * 5.0)
                vy += py * (zx * n12 * 5.0)
            lat = abs(zy) * (1.0 if m == 0 else -1.0) * n12 * (3.0 if l == 1 else 1.5)
            vx += px * lat
            vy += py * lat
        else:
            vx, vy = tx + ux * 2.1, ty + uy * 2.1
        n12 *= 0.5
        pts.append((vx, vy))
    return pts


def draw_squidcada(painter, atlas, sc, ts) -> None:
    """Draw one cicada; ts = 0..1 interpolation between last and current tick."""
    x = lerp(sc.last_x, sc.x, ts)
    y = lerp(sc.last_y, sc.y, ts)
    ux, uy = sc.hd
    px, py = -uy, ux                                   # vector2
    zx = lerp(sc.lzx, sc.zx, ts)
    zy = lerp(sc.lzy, sc.zy, ts)
    _d = math.hypot(zx, zy)
    if _d > 1e-6:
        zx, zy = zx / _d, zy / _d
    ax = abs(zx)                                       # p.x
    num = _aim(ux, uy)                                 # body axis
    num2 = _aim(zx, zy)                                # zRotation
    n = int(clampf(8.0 - float(int(abs(num2) / 180.0 * 9.0)), 0.0, 8.0))
    sign2 = 1.0 if num2 > 0.0 else -1.0
    num4 = float(8 - n) * 22.5 * sign2
    rot = num - num4                                   # body sprite rotation
    sfx = -1.0 if num2 > 0.0 else 1.0                  # scaleX mirror flag
    fat = getattr(sc, "fatness", 1.0)
    body, shield, eyes_a, eyes_b, glow = palette(sc)
    c1x, c1y = x - ux * CHUNK_GAP, y - uy * CHUNK_GAP  # chunk1 (tail end)
    mx, my = x - ux * BODY_MID, y - uy * BODY_MID      # sprite anchor (midpoint)

    painter.save()
    aa_hint(painter)
    blit(painter, atlas, "Cicada%dbody" % n, mx, my, rot, sfx, fat, body)
    # 原版 CicadaGraphics.DrawSprites:605-607 —— 钉在 chunk1 + (-2, +3)，rotation = num + 12；
    # 缩放 CicadaGraphics.cs:430-431 的 Lerp(5,3)/Lerp(12,8)（20 = Circle20 元件尺寸）。
    t_full = clampf(abs(fat - 1.0) * 10.0, 0.0, 1.0)
    blit(painter, atlas, "Circle20", c1x - 2.0, c1y + 3.0, num + 12.0,
         lerp(5.0, 3.0, t_full) / 20.0, lerp(12.0, 8.0, t_full) / 20.0, glow)
    for m in (0, 1):
        for l in (0, 1):
            pts = _tent_points(sc, ux, uy, px, py, zx, zy, ax, m, l, ts)
            w = sc.tent_thick
            draw_rope(painter, pts, [TENT_HALF[0] * 2.0 * w, TENT_HALF[1] * 2.0 * w,
                                     TENT_HALF[2] * 2.0 * w, 0.6 * w], body)
    blit(painter, atlas, "Cicada%dhead" % n, mx, my, rot, sfx, 1.0, body)
    blit(painter, atlas, "Cicada%dshield" % n, mx, my, rot, sfx, 1.0, shield)
    blink = getattr(sc, "blink", 1)
    blit(painter, atlas, "Cicada%deyes1" % n, mx, my, rot, sfx, 1.0,
         eyes_a if blink > 0 else shield)
    if blink >= 0:
        blit(painter, atlas, "Cicada%deyes2" % n, mx, my, rot, sfx, 1.0, eyes_b)
    dep = getattr(sc, "wing_dep", [1.0, 1.0, 1.0, 1.0])
    wph = getattr(sc, "wing_offset", 0.0) + _inv(0.0, 3.0, getattr(sc, "flap_t", 0.0) + ts)
    for j in (0, 1):
        num7 = (5.0 if j == 0 else 11.0) + 3.0 * ax
        num8 = -20.0 if j == 0 else 24.0
        frame = "CicadaWingA" if j == 0 else "CicadaWingB"
        for k in (0, 1):
            # 原版两处符号不同：位置偏移用 (k==0 ? 1 : -1)，而 rotation 与
            # scaleX 用 (k==0 ? -1 : 1)。混用会把两只翅的摆动方向镜像反。
            ks = 1.0 if k == 0 else -1.0        # p2 的侧向偏移
            km = -1.0 if k == 0 else 1.0        # rotation / scaleX 镜像
            d = clampf(float(dep[k * 2 + j]), 0.0, 1.0)
            num9 = (11.0 if j == 0 else 9.0) * (0.2 + 0.8 * abs(zy)) * lerp(1.0, 0.85, _inv(0.5, 0.0, d))
            off = num9 * ks + zx * lerp(-3.0, -5.0, _inv(0.5, 0.0, d))
            wx = mx + ux * num7 + px * off
            wy = my + uy * num7 + py * off
            a = ax
            if d < 1.0:
                a = max(_inv(30.0, 18.0, math.dist((c1x, c1y), (wx, wy))), _inv(1.0, 0.5, d))
            wcol = _mix(BLACK_RGB, shield, abs(a) + 0.2)
            # 原版翅膀 alpha = |p.x|^3 是连续渐变；本项目要干净像素 ⇒ 折算成
            # 「够看得见就整片画，几乎侧对镜头就不画」，不留半透明毛边。
            walpha = 1.0 if abs(a) >= 0.66 else 0.0
            if d >= 1.0:
                frac = wph if j == 0 else wph + 0.8
                frac = frac - math.floor(frac)          # Custom.Decimal
                g = (0.5 + 0.5 * math.sin(frac ** (0.75 if j == 0 else 1.3) * math.tau)) ** 0.7
                ang = lerp(-65.0, 40.0, g) if j == 0 else lerp(-45.0, 75.0, g)
                wrot = num - 180.0 + (num8 + ang) * km
                # 原版：扑翅到两端时翅膀接近侧对镜头 ⇒ 用 scaleX 收窄
                wsc = (max(0.0, lerp(abs(zy), 1.0, abs(0.5 - ang) * 1.4))
                       * km * sc.wing_len)
            else:
                px2 = wx - ux * 20.0 * sc.wing_len + px * ks * 4.0
                py2 = wy - uy * 20.0 * sc.wing_len + py * ks * 4.0
                wrot = _aim(px2 - wx, py2 - wy) - 90.0 * km
                wsc = km * sc.wing_len
            if walpha <= 0.0:
                continue
            blit(painter, atlas, frame, wx, wy, wrot, wsc, sc.wing_thick, wcol, ax=0.0, ay=0.5)
    painter.restore()
