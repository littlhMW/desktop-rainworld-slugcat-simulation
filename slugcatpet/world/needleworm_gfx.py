# -*- coding: utf-8 -*-
"""面条蝇 NeedleWorm 渲染（对照 NeedleWormGraphics.DrawSprites，坐标 y↓）。

原版身体是 TriangleMesh 程序化网格（不是贴图）：BodyMesh（含吻+尾）/
HighLightMesh（躯干前 2/3 的浅色中线条纹）/ FangMesh（成体獠牙，白尖+淡红根、
见空气后转黑）/ 4 张翅（2 对 × 左右，s=0 在身后、s=1 在身前）/ 退化小短腿 /
JetFishEyeB 椭圆眼。

对应关系：
- NeedleWormGraphics.cs:423-453  InitiateSprites：精灵顺序（≈ 图层）
- NeedleWormGraphics.cs:461-521  BodyMesh / HighLightMesh 顶点
- NeedleWormGraphics.cs:499-501  惨叫时体节随机抖动
- NeedleWormGraphics.cs:549-582  4 张翅（vector14/p 的算法照抄）
- NeedleWormGraphics.cs:583-600  腿（幼体 1 对 / 成体 3 对）
- NeedleWormGraphics.cs:615-655  獠牙 fangOut/fangBlack
- NeedleWormGraphics.cs:666-720  GraphSegmentPos / GraphSegmentRad / Eaten 截断
- NeedleWormGraphics.cs:722-787  ApplyPalette 配色
"""
from __future__ import annotations
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.units import clampf, lerp, inv_lerp
from ..core.gfxmath import _hsl2rgb
from ..rendering.primitives import blit, draw_rope, ribbon
from ..rendering.pixelmode import aa_hint
from .needleworm import (AGE_EGG, AGE_SMALL, WING_SEG, FANG_LENGTH, TAIL_ROWS,
                         _chunk_rads, _lerp_map)

BLACK_RGB = (27, 10, 32)        # RoomPalette.blackColor（Outskirts；wiki 调色板图顶行同值）
FOG_RGB = (78, 92, 104)         # RoomPalette.fogColor 近似值


def _rgb(h, sl, l):
    # 原版 Custom.HSL2RGB 的 switch 只有 case 0..5；(int)(h*6) 落在 6 以上时一个分支都
    # 不匹配，直接返回 r=g=b=l 的**灰**。面条蝇 hue = WrappedRandomVariation(0.5,0.08,0.2)，
    # 有 15.3% 的个体 num = hue + 0.478 > 1 → 就是灰/白/黑那一档（wiki 调色板图右侧灰柱
    # 宽度 15%、wiki 正文「shades of red … some gray」）。这里**不能**对 hue 取模。
    r, g, b = _hsl2rgb(h, sl, l)
    return (int(clampf(round(r * 255.0), 0, 255)),
            int(clampf(round(g * 255.0), 0, 255)),
            int(clampf(round(b * 255.0), 0, 255)))


def _mix(a, b, t):
    t = clampf(t, 0.0, 1.0)
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _perp(ux, uy):
    """Custom.PerpendicularVector（原版 y↑ 写成 (-y, x)；这里保持同一式子）。"""
    return -uy, ux


def _aim(ux, uy) -> float:
    """0 = 上、顺时针为正（Qt 同号）。"""
    return math.degrees(math.atan2(ux, -uy))


def _dir(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-6 else (0.0, -1.0)


def palette(nw):
    """NeedleWormGraphics.cs:722-787 ApplyPalette → (body, highlight, details, eye)。"""
    num = nw.hue + 0.478
    light = nw.lightness
    body = _rgb(num, _lerp_map(light, 0.5, 1.0, 0.9, 0.5), lerp(0.1, 0.8, light * light))
    hi = _rgb(num, _lerp_map(light, 0.5, 1.0, 0.5, 1.0), lerp(0.2, 1.0, light))
    num2 = num + inv_lerp(0.5, 0.6, light) * 0.5
    cb = nw.cos_bools
    if cb[2]:
        eye = _rgb(num2 + 0.5 - nw.hue_div, 1.0, lerp(0.7, 0.3, light ** 1.5))
        det = _rgb(num2 + 0.5 + nw.hue_div, 0.8, 0.4)
    else:
        eye = _rgb(num2 + 0.5, 1.0, lerp(0.7, 0.3, light ** 1.5))
        det = _rgb(num2 + 0.5, 1.0, 0.5) if cb[3] else _rgb(num2, 1.0, 0.5)
    if light < 0.5:
        body = _mix(body, BLACK_RGB, inv_lerp(0.5, 0.0, light) ** 0.5)
        hi = _mix(hi, _mix(BLACK_RGB, FOG_RGB, 0.4), inv_lerp(0.5, 0.0, light) ** 2)
    elif light > 0.5:
        body = _mix(body, FOG_RGB, inv_lerp(0.5, 1.0, light) * 0.2)
        hi = _mix(body, (255, 255, 255), inv_lerp(0.5, 1.0, light))
    return body, hi, det, eye


def _eaten_frac(nw) -> float:
    """NeedleWormGraphics.cs:93-103 Eaten：被啃的幼体越啃越短。"""
    if nw.age != "small":
        return 1.0
    return _lerp_map(float(nw.bites), 4.0, 1.0, 1.0, 0.4)


def draw_needle_egg(painter, atlas, nw, ts) -> None:
    """卵：两片深色壳 + 中间橙红色软带（wiki：壳会随软带伸缩开合）。"""
    x = lerp(nw.last_x, nw.x, ts)
    y = lerp(nw.last_y, nw.y, ts)
    r = nw.head_rad
    wob = clampf(abs(nw._wobble), 0.0, 1.0)
    band = 1.0 + 0.35 * wob
    painter.save()
    aa_hint(painter)
    # 橙红软带
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*_rgb(0.05 + 0.03 * wob, 1.0, 0.5)))
    painter.drawEllipse(x - r * 0.85, y - r * 0.55 * band, r * 1.7, r * 1.1 * band)
    # 上下两片壳
    shell = _rgb(0.72 + 0.03 * ((nw.hue * 7.3) % 1.0), 0.35, 0.16)
    painter.setBrush(QColor(*shell))
    painter.drawEllipse(x - r, y - r * (1.05 + 0.35 * band), r * 2.0, r * 1.25)
    painter.drawEllipse(x - r, y + r * (0.05 + 0.30 * band), r * 2.0, r * 1.25)
    painter.setPen(QPen(QColor(*_mix(shell, BLACK_RGB, 0.5))))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(x - r, y - r * (1.05 + 0.35 * band), r * 2.0, r * 1.25)
    painter.drawEllipse(x - r, y + r * (0.05 + 0.30 * band), r * 2.0, r * 1.25)
    painter.restore()


def _wing_push_dir(bdir, l: int, m: int):
    """NeedleWormGraphics.Update：翅膀每帧被 vector6 推，朝向由它决定。

    原版公式（y 轴向上）：a 以身体切线为基准斜 -45/+45 度且强制朝上，
    b 只看头尾上下关系，vector6 = Lerp(a, b, |vector.y| * 0.6)。缺这一步
    翅会笔直朝上，看上去就是两根竖条。
    """
    gx, gy = bdir[0], -bdir[1]                  # 换成游戏坐标（y 向上）
    s = -1.0 if l == 0 else 1.0
    off = -45.0 if m == 0 else 45.0
    adeg = math.degrees(math.atan2(gy, gx)) + (90.0 + off) * s
    a = (math.cos(math.radians(adeg)), abs(math.sin(math.radians(adeg))))
    bdeg = (90.0 + off * gy) * s * (1.0 if gy >= 0.0 else -1.0)
    b = (math.cos(math.radians(bdeg)), math.sin(math.radians(bdeg)))
    b = (b[0], lerp(b[1], abs(b[1]), 0.4))
    t = abs(gy) * 0.6
    vx, vy = lerp(a[0], b[0], t), lerp(a[1], b[1], t)
    n = math.hypot(vx, vy) or 1.0
    return (vx / n, -vy / n)                    # 换回屏幕坐标（y 向下）


def _draw_wings(painter, atlas, nw, ts, pts, seg_dir, l: int, layer: int,
                body, hi, det, eye) -> None:
    """NeedleWormGraphics.cs:549-582：l=0/1 是身体两侧，layer 是原版 num8 图层。

    原版用 `WingSprite(num8, m)`，`num8 = (l == 0) != (zrot.x > 0)`——朝屏幕里那
    一侧的翅才会翻到上层，不是固定的 l；腿精灵排在所有翅之后（最上层）。
    """
    if nw.small and nw.bites <= 4:
        return                      # 原版 isVisible：幼体没被啃过就不显翅
    cb = nw.cos_bools
    flap = lerp(nw.last_wing_flap, nw.wing_flap, ts)
    flying = clampf(lerp(0.0, nw.flying, ts), 0.0, 1.0)
    zy = lerp(nw.lzrot[1], nw.zrot[1], ts)
    zx = lerp(nw.lzrot[0], nw.zrot[0], ts)
    sn = nw.snout_n
    sign = -1.0 if l == 0 else 1.0
    # 下面这四组都跟 m（第几对翅）无关，提出来一次算好；配色本来逐翅重算
    prof = ((0.0, 0.25), (0.2, 0.5), (0.5, 0.75), (0.78, 1.0),
            (0.93, 0.75), (1.0, 0.25))
    prof_t = [t for t, _ in prof]
    prof_w = [k * 2.0 * nw.wings_size for _, k in prof]
    root_col = _mix(FOG_RGB, det, 0.5)
    tip_col = _mix(eye if cb[1] else FOG_RGB, (255, 255, 255), 0.35 if cb[1] else 0.5)
    prof_c = [_mix(root_col, tip_col, t) for t in prof_t]
    for m, off in enumerate(WING_SEG[nw.age]):
        ci = sn + off
        if ci >= len(pts):
            continue
        bx, by = pts[ci]
        bdir = seg_dir(ci)
        base = (bx - (-bdir[1]) * (nw.wings_size * 5.0 * abs(zy) * sign),
                by - (bdir[0]) * (nw.wings_size * 5.0 * abs(zy) * sign))
        phase = flap + (0.33 if m == 0 else 0.0)
        dirn = _wing_push_dir(bdir, l, m)
        p = (base[0] + dirn[0] * 30.0 * nw.wings_size,
             base[1] + dirn[1] * 30.0 * nw.wings_size)
        p = (p[0], p[1] - (18.0 + 18.0 * math.sin(phase * math.tau)) * flying * nw.wings_size)
        d = _dir(base[0], base[1], p[0], p[1])
        ln = lerp(40.0, 60.0, flying) * nw.wings_size
        # 原版翅是 CustomFSprite("CentipedeWing")：8×52 的白色叶片贴图。CustomFSprite
        # 的 uv 序是 0=左上 1=右上 2=右下 3=左下，而翅顶点 0/1 在尖、2/3 在根
        # （:566-569）→ 贴图上缘 = 翅尖、下缘 = 翅根。半宽一律 2*wingsSize（:565），
        # 贴图逐行宽 2,4,6,6,8×20,6×8,4×9,2×11（行 0 在翅尖、行 51 在翅根）换成
        # 「根→尖」的半宽比 = 0.25,0.5,0.75,1.0,0.75,0.25（翅尖外半段最宽，像蝉翅）。
        # 之前画成 2.4→1.2 的锥条，所以翅又细又小。
        ribbon(painter,
               [(base[0] + d[0] * ln * t, base[1] + d[1] * ln * t) for t in prof_t],
               prof_w, prof_c)
        if not nw.small:
            blit(painter, atlas, "JetFishEyeB", base[0], base[1],
                 _aim(bdir[0], bdir[1]), 0.9, 1.2,
                 body if layer == 0 else _mix(body, hi, abs(zx) * 0.6))


def _wing_side(layer: int, zx: float) -> int:
    """原版 num8 图层 → l 侧：`num8 = (l == 0) != (zrot.x > 0)`（:564）。"""
    return 0 if ((layer == 0) == (zx > 0.0)) else 1


def _draw_fang(painter, nw, ts, pts, zx) -> None:
    """成体獠牙（NeedleWormGraphics.cs:615-655）：口器前伸、白尖淡红根、见风转黑。"""
    if nw.small:
        return
    fo = lerp(nw.last_fang_out, nw.fang_out, ts)
    num10 = inv_lerp(0.5, 1.0, fo)
    if num10 <= 0.0:
        return
    blk = clampf(nw.fang_black, 0.0, 1.0)
    c_root = _mix((255, 0, 0), BLACK_RGB, blk ** 3)
    c_tip = _mix((255, 255, 255), BLACK_RGB, inv_lerp(0.4, 0.55, blk) ** 0.8)
    hx, hy = pts[0]
    ux, uy = _dir(pts[1][0], pts[1][1], pts[0][0], pts[0][1]) if len(pts) > 1 else (0.0, -1.0)
    hw0 = 0.6 + 0.6 * blk
    n = 5
    # 原版 mesh 的第 0 组顶点就在 vector5（= 口腔根部）上，必须先放根点再逐段前伸，
    # 否则整根獠牙会凭空往前挪一段（fangLength/3.5 ≈ 14px），看着像「飘在嘴前面」。
    fp, fw, fc = [(hx, hy)], [hw0], [c_root]
    for i in range(n):
        f = inv_lerp(0.0, n - 1.0, i)
        # 原版这一项末尾还有 * vector2.x（zRot 的 x 分量），漏了獠牙就不随朝向摆动
        wob = math.sin(num10 * math.pi) * lerp(-0.3 + 1.3 * (f ** 0.5), f, num10) * -0.2 * zx
        dx = ux + (-uy) * wob
        dy = uy + (ux) * wob
        d = math.hypot(dx, dy) or 1.0
        ln = (FANG_LENGTH / 3.5) * (num10 ** 0.8)
        hx += dx / d * ln
        hy += dy / d * ln
        fp.append((hx, hy))
        fw.append(lerp(hw0, 0.5, f))                   # 原版 num14 就是半宽
        fc.append(_mix(c_root, c_tip, clampf(inv_lerp(0.1, 0.35 + 0.65 * blk, f), 0.0, 1.0) **
                       (4.0 - 3.95 * (num10 * 3.0 + blk) * 0.25)))
    ribbon(painter, fp, fw, fc)


def _graph_seg_rad(nw, i: int, num3: float) -> float:
    """NeedleWormGraphics.cs:709-720 GraphSegmentRad(i) → 第 i 个图段的渲染半径。

    注意这是**渲染**半径，和物理用的 s.rad 不是一回事：原版 BodyMesh 的顶点横向
    偏移量 = GraphSegmentRad(j) * num3，其中 num3 是成体拉伸时的整体缩放
    （NeedleWormGraphics.cs:486-490）。吻段随张口(fangOut)变粗、尾段带 exponent
    变细，以前这两段是常量/线性，所以躯干看着对不上原版。
    """
    sn = nw.snout_n
    if i < sn:
        return (1.0 + math.pow(inv_lerp(0.0, 0.5, nw.fang_out), 0.6) * 1.5) * num3
    fat = lerp(0.75, 1.35, nw.fatness)
    body_n = nw.body_n
    k = i - sn
    rads = _chunk_rads(nw.age)
    if k < body_n:
        return rads[k] * fat * num3
    return _lerp_map(float(k), float(body_n - 1),
                     float(body_n + TAIL_ROWS[nw.age]),
                     rads[body_n - 1] * fat, 0.7,
                     (1.4 - 1.35 * nw.thin_tail)
                     * lerp(1.8, 0.2, nw.fatness)) * num3


def draw_needleworm(painter, atlas, nw, ts) -> None:
    """画一只面条蝇（幼体/成体）。"""
    if nw.age == AGE_EGG:
        draw_needle_egg(painter, atlas, nw, ts)
        return
    painter.save()
    aa_hint(painter)
    body, hi, det, eye = palette(nw)
    cb = nw.cos_bools
    sn = nw.snout_n
    # ── 顶点：GraphSegmentPos + Eaten 截断 + 惨叫抖动 ──
    pts, rads = [], []
    eaten = _eaten_frac(nw)
    total = len(nw.seg)
    last_i = total - 1
    for i in range(total):
        s = nw.seg[i]
        x, y = lerp(s.lx, s.x, ts), lerp(s.ly, s.y, ts)
        if eaten < 1.0:
            j = int(round(eaten * last_i)) if inv_lerp(0.0, last_i, i) > eaten else i
            t = nw.seg[j]
            x, y = lerp(t.lx, t.x, ts), lerp(t.ly, t.y, ts)
        if nw.scream > 0.0:
            k = (nw.scream ** 0.7) * 4.0 * ((i * 7919 % 97) / 97.0) * inv_lerp(total, sn, i)
            x += (1.0 if (i % 2) else -1.0) * k
            y += (1.0 if (i % 3) else -1.0) * k
        pts.append((x, y))

    # num3：成体拉伸时整体收细（GraphSegmentPos(吻根) ↔ GraphSegmentPos(末躯干) 的
    # 间距 50→80px 映射 1→0.85；NeedleWormGraphics.cs:486-490）。
    num3 = 1.0
    if nw.age != AGE_SMALL:
        p0 = pts[min(sn, len(pts) - 1)]
        p1 = pts[min(sn + nw.body_n - 1, len(pts) - 1)]
        num3 = _lerp_map(math.hypot(p1[0] - p0[0], p1[1] - p0[1]),
                         50.0, 80.0, 1.0, 0.85)
    for i in range(total):
        rads.append(max(0.3, _graph_seg_rad(nw, i, num3)))

    def seg_dir(i):
        if i <= 0:
            return _dir(pts[1][0], pts[1][1], pts[0][0], pts[0][1]) if len(pts) > 1 else (0.0, -1.0)
        return _dir(pts[i][0], pts[i][1], pts[i - 1][0], pts[i - 1][1])

    # 图层顺序照原版 InitiateSprites（NeedleWormGraphics.cs:423-453）：
    #   翅(远侧层,0/1) < 獠牙(FangMesh=5) < 身体(BodyMesh=6) < 腿(7+) < 高光(13)
    #   < 翅(近侧层,17/18) < 眼 —— 以前獠牙画在身体之后（浮在脸上）、两层翅都在
    #   身体之上，所以獠牙「位置」看着不对。
    zx = lerp(nw.lzrot[0], nw.zrot[0], ts)
    _draw_wings(painter, atlas, nw, ts, pts, seg_dir,
                _wing_side(0, zx), 0, body, hi, det, eye)
    _draw_fang(painter, nw, ts, pts, zx)
    # ── 身体（BodyMesh：吻+躯干+尾，尾端渐暗）──
    cols = []
    for i in range(len(pts)):
        if not nw.small:
            v = inv_lerp(0.0, len(pts) - 1.0, i)
            fade = _mix(det, BLACK_RGB, (v * v) * 0.85 if cb[0] else 1.0)
            cols.append(_mix(body, fade, (inv_lerp(0.3, 1.0, v) ** 2) * (1.0 if cb[0] else 0.6)))
        else:
            cols.append(body)
    ribbon(painter, pts, [r for r in rads], cols)
    # ── 浅色中线条纹（HighLightMesh：躯干前 2/3）──
    hl_n = max(2, int(nw.body_n + len(nw.seg) - sn) * 2 // 3)
    hp, hr, hc = [], [], []
    for k in range(hl_n):
        i = min(len(pts) - 1, sn - 1 + k)
        x, y = pts[i]
        hp.append((x - 1.0, y + 1.0))
        hr.append(max(0.5, rads[i] / 3.2))
        f = inv_lerp(0.0, hl_n - 1.0, k)
        hc.append(_mix(body, hi, math.sin((f ** 0.4) * math.pi)))
    ribbon(painter, hp, hr, hc)
    # ── 腿：幼体 1 对（退化）、成体 3 对（NeedleWormGraphics.cs:583-600）──
    #    原版 LegConPos 挂在 OnBodyPos(0.03/0.066/0.1) 上，而 OnBodyPos 用的
    #    TotalSegments **不含 snout**（成体躯干 15 节，NeedleWorm.cs:70,983）→ 腿长在
    #    躯干最前 1~1.4 节。以前漏了 +snout_n 这个偏移，腿被挂到吻部，看着像胡须。
    n_legs = 1 if nw.small else 3
    zy = lerp(nw.lzrot[1], nw.zrot[1], ts)
    tot_body = total - sn
    for side in (-1.0, 1.0):
        for i in range(n_legs):
            f = _lerp_map(float(i), 0.0, 2.0, 0.03, 0.1, 2.0)
            bi = clampf(sn + f * (tot_body - 1.1), 0.0, len(pts) - 1.0)
            i0 = int(bi)
            i1 = min(i0 + 1, len(pts) - 1)
            t = bi - i0
            ax = lerp(pts[i0][0], pts[i1][0], t)
            ay = lerp(pts[i0][1], pts[i1][1], t)
            ar = lerp(rads[i0], rads[i1], t)
            bd = _dir(pts[i1][0], pts[i1][1], pts[i0][0], pts[i0][1]) if i1 != i0 else (0.0, -1.0)
            px, py = _perp(bd[0], bd[1])
            k = (i == 1) and 16.0 or 11.0
            ln = k * nw.legs_fac
            # 根 = LegConPos（体侧）；腿本体被 11/16*legsFac 的连接半径拉住，再被
            # 重力(vel.y-=0.9)与 LegConDir*0.55 往外拽 → 挂在体侧外下方的小短腿
            rx = ax + px * ar * side * zy
            ry = ay + py * ar * side * zy
            gx = px * side * zy * 0.55
            gy = py * side * zy * 0.55 + 0.9
            gd = math.hypot(gx, gy) or 1.0
            tx, ty = rx + gx / gd * ln, ry + gy / gd * ln
            tcol = _mix(body, det, clampf(abs(ln) / (9.0 * nw.legs_fac), 0.0, 1.0))
            ribbon(painter, [(rx, ry), ((rx + tx) * 0.5, (ry + ty) * 0.5), (tx, ty)],
                   [0.8 * nw.legs_fac, 2.2 * nw.legs_fac, 1.5 * nw.legs_fac],
                   [body, body, tcol])
    _draw_wings(painter, atlas, nw, ts, pts, seg_dir,
                _wing_side(1, zx), 1, body, hi, det, eye)
    # ── 眼睛（JetFishEyeB，NeedleWormGraphics.cs:475-483）──
    if len(pts) > sn + 1:
        mid_i = min(len(pts) - 1, sn + max(1, nw.body_n // 2))
        axis = _dir(pts[mid_i][0], pts[mid_i][1], pts[sn][0], pts[sn][1])
        v3 = _dir(pts[sn][0], pts[sn][1], pts[1][0], pts[1][1])
        t = inv_lerp(0.0, 0.7, v3[0] * axis[0] + v3[1] * axis[1])
        hx = lerp(pts[sn][0], pts[0][0], 0.4)
        hy = lerp(pts[sn][1], pts[0][1], 0.4)
        px, py = _perp(v3[0], v3[1])
        sc = 0.65 if nw.small else 1.0
        for i in (0, 1):
            sign = -1.0 if ((i == 0) != (v3[0] < 0.0)) else 1.0
            off = 4.0 * sc * sign * v3[1]
            blit(painter, atlas, "JetFishEyeB", hx + px * off, hy + py * off,
                 _aim(v3[0] + axis[0], v3[1] + axis[1]),
                 lerp(0.8, 0.6, t) * sc, lerp(1.1, 1.5, t) * sc, eye)
    painter.restore()
