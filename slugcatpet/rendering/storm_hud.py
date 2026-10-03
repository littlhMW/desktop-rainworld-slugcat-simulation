# -*- coding: utf-8 -*-
"""左下角雨循环计时器：业力环、雨点和食物圈。

雨点数量和消失顺序参照 RainMeter.cs；绘制只读取 StormCycle.hud_info()。
矩形背景和图形外缘的黑色微光缓存/分层绘制，不参与世界的像素化滤镜。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from ..i18n import t

HUD_W = 220.0        # 参考图的横向矩形；只包住计时器本体并留一小段右侧余量
HUD_H = 76.0
HUD_MARGIN = 10.0
_LINE_H = 15.0
_PAD = 3.0           # 面板内边距（逻辑像素）

# ── 参考图比例缩到 220×76 逻辑像素；圆点数量/顺序另按 RainMeter.cs ──
#
# The reference HUD is wider and taller around the karma mark than the first
# implementation.  Keep the panel size stable (it is also the drag hit box),
# and tune the contents here so a 2x desktop scale produces the same relative
# geometry as Rain World's RainMeter: a large karma mark, a broad halo of
# dots, then six food circles at roughly 40 px pitch.
REF_X0 = 3.0             # 内容左边界（最左那个圆点的左沿）
REF_Y0 = 4.0             # 内容上边界（最上那个圆点的上沿）
REF_W = 205.0            # 内容宽（主圆环 + 示例的 7 格饥饿条）
REF_H = 70.0             # 内容高
RING_CX = 34.0           # 主圆环中心 x（放大外圈后仍留出左边距）
RING_CY = 29.0           # 主圆环中心 y
RING_R = 26.0            # 一圈圆点所在半径（参考图约 52 px @ 2x）
# Rain World 的雨循环刻度是固定数量。循环长短只改变每个刻度所代表的
# 时间，不能因为不同的 cycle 时长而增删圆点（旧实现会随 ring_total 改变
# 数量，导致计时器每次切相位都重新排版）。
DOTS = 17
DOT_R = 1.15             # 剩余的实心圆点半径
KARMA_REF = 34.0         # karma 精灵边长（参考图中心环约 68 px @ 2x）
PIP_X0 = 75.0            # 第一格圆心 x（与主环留出约 82 px @ 2x）
PIP_PITCH = 21.0         # 格中心距（参考图约 42 px @ 2x）
PIP_D = 15.0             # 格椭圆盒直径（参考图约 30 px @ 2x）
PIP_RING = 1.8           # 外圈描边宽
PIP_CORE = 7.0           # 实心圆直径
PIP_CY = 29.0            # 格圆心 y
DIV_EXTRA = 8.0          # 分隔线额外占宽
DIV_H = 22.0             # 分隔线高（比圆圈高一截）
TIME_FONT = 8.0          # 饥饿条下方显示剩余时间（参考图的紧凑字号）
TIME_CY = 45.0           # 倒计时文字中心 y：首格正下方，不能压到面板底边
TIME_TRACK = 1.0         # 字距（参考单位）
DOT_START_DEG = -90.0   # RainMeter.cs:189：i=0 从正上方起，末颗落在右上
BLINK_TICKS = 28         # 征兆期「呼吸」的半周期（40 tick/s → 0.7s 呼气，整次呼吸 1.4s）
BLINK_DIM = 0.25         # 呼吸最暗那一档的透明度（是变暗，不是熄灭）
KARMA_MIN = 1
KARMA_MAX = 10           # 最低 1 级、最高 10 级

_INK = QColor(245, 245, 245)
_BACKDROP_CACHE = {}


def _backdrop_bounds(info, scale: float):
    """Return the visible timer bounds in local HUD coordinates.

    The old backdrop used the whole 220x76 drag rectangle, which left a large
    empty black block below the countdown.  Keep the drag rectangle unchanged,
    but size the painted background from the ring, food pips and countdown.
    """
    n, hib, pitch, d, xpip, _div = pip_geometry(info)
    ring_pad = DOT_R + 1.8       # include the soft outline/glow around dots
    left = RING_CX - RING_R - ring_pad
    right = RING_CX + RING_R + ring_pad
    top = RING_CY - RING_R - ring_pad
    bottom = RING_CY + RING_R + ring_pad
    if n:
        first = _pip_cx(0, hib, pitch, xpip)
        last = _pip_cx(n - 1, hib, pitch, xpip)
        pip_pad = d * 0.5 + PIP_RING * 0.5 + 1.5
        left = min(left, first - pip_pad)
        right = max(right, last + pip_pad)
        top = min(top, PIP_CY - pip_pad)
        bottom = max(bottom, PIP_CY + pip_pad)
    cx, cy, _cw, ch = countdown_box(info)
    left = min(left, cx - 1.0)
    # countdown_box reserves a wide alignment area, but only the short MM:SS
    # glyph run is visible; do not let that invisible reserve widen the panel.
    right = max(right, cx + 44.0)
    bottom = max(bottom, cy + ch * 0.5 + 1.5)

    # Reference coordinates are transformed in draw_storm_hud immediately
    # after the backdrop is painted.
    tx = _PAD - REF_X0 * scale
    ty = (HUD_H - REF_H * scale) * 0.5 - REF_Y0 * scale
    margin = 3.0
    return (tx + scale * left - margin,
            ty + scale * top - margin,
            tx + scale * right + margin,
            ty + scale * bottom + margin)


def _draw_backdrop(p, x0: float, y0: float, info, scale: float) -> None:
    """Draw a small rounded black backdrop around the actual timer content."""
    bounds = _backdrop_bounds(info, scale)
    key = tuple(round(v, 2) for v in bounds)
    im = _BACKDROP_CACHE.get(key)
    pad = 6
    if im is None:
        bx0, by0, bx1, by1 = bounds
        rw, rh = bx1 - bx0, by1 - by0
        w, h = max(1, int(math.ceil(rw)) + pad * 2), max(1, int(math.ceil(rh)) + pad * 2)
        im = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        cx, cy = pad + rw * 0.5, pad + rh * 0.5
        rx, ry, rad = rw * 0.5, rh * 0.5, 3.5
        for yy in range(h):
            for xx in range(w):
                dx = abs(xx + 0.5 - cx) - (rx - rad)
                dy = abs(yy + 0.5 - cy) - (ry - rad)
                dist = math.hypot(max(dx, 0.0), max(dy, 0.0)) + min(max(dx, dy), 0.0) - rad
                t = max(0.0, min(1.0, (4.5 - dist) / 7.0))
                t = t * t * (3.0 - 2.0 * t)
                im.setPixel(xx, yy, int(175.0 * t) << 24)
        _BACKDROP_CACHE[key] = im
    p.drawImage(QPointF(x0 + bounds[0] - pad, y0 + bounds[1] - pad), im)

# 能画汉字的字体族（有其一才用中文文案）
_CJK_FAMS = ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun",
             "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
             "PingFang SC", "WenQuanYi Micro Hei")
# 没有汉字字体时的 ASCII 兜底（画方框比英文更糟）
_ASCII = {"hud_rain_cycle": "Calm", "hud_rain": "Omen",
          "hud_hibernation": "Storm", "hud_starvation": "Starving"}
_FONT_OK = None      # None = 还没探过


def _layout_scale() -> float:
    """参考单位 → 逻辑像素：按面板尺寸等比缩放，长宽都塞得下。"""
    return min((HUD_W - 2.0 * _PAD) / REF_W, (HUD_H - 2.0 * _PAD) / REF_H)


def karma_frame(level: int) -> str:
    """等级（1..10）→ ``ui`` 图集的 karma 帧名（和猫状态面板同一套映射）。"""
    k = max(KARMA_MIN, min(KARMA_MAX, int(level))) - 1
    return ("smallKarma%d" % k) if k <= 4 else ("smallKarma%d-9" % k)


def ring_count(info) -> int:
    """Return the fixed Rain World meter dot count.

    ``ring_total`` is deliberately ignored here.  A short or long cycle uses
    the same set of dots; each dot simply represents a different amount of
    time (``ring_total / DOTS``).  Keeping the geometry stable avoids the
    visible jump that the old proportional-count implementation caused.
    """
    return DOTS


def ring_lit(info) -> int:
    """RainMeter.cs:169-183：从末颗开始消失，第一颗最后消失。"""
    try:
        total = float((info or {}).get("ring_total") or 0.0)
        remain = float((info or {}).get("ring_remain") or 0.0)
    except (TypeError, ValueError):
        return 0
    if total <= 0.0:
        return 0
    remain = max(0.0, min(total, remain))
    count = ring_count(info)
    return max(0, min(count, int(math.ceil(remain / total * count - 1e-9))))


def pip_geometry(info):
    """饥饿条几何：(格数, 分隔线在第几格之后, 圆心距, 外径, 第一格圆心 x, 分隔线 x|None)。

    格子多了（怪猫 12 格）就按可用宽度等比压窄，保持参考图「盒径 = 圆心距 × 21/30」的比例。
    """
    n = max(0, min(24, int((info or {}).get("food_max") or 0)))
    hib = max(0, min(n, int((info or {}).get("food_hibernate") or 0)))
    if n <= 0:
        return 0, hib, PIP_PITCH, PIP_D, PIP_X0, None
    extra = DIV_EXTRA if (0 < hib < n) else 0.0
    avail = max(40.0, REF_X0 + REF_W - PIP_X0 - extra)
    # 从第一格圆心到最后一格圆心，再加最后一格的半径（不是整个直径，
    # 否则参考图那一档 7 格会被误判放不下、平白压窄成 28.5）
    unit = max(0.001, (n - 1) + PIP_D / PIP_PITCH * 0.5)
    # 描边各外扩 PIP_RING/2，排布时一起算进去，最后一格才不会顶出右边界
    pitch = PIP_PITCH if n == 1 else max(4.0, min(PIP_PITCH,
                                                 (avail - PIP_RING * 0.5) / unit))
    d = pitch * PIP_D / PIP_PITCH
    if hib <= 0:
        div_x = PIP_X0 - pitch * 0.55
    elif hib >= n:
        div_x = PIP_X0 + (n - 1) * pitch + pitch * 0.55
    else:
        div_x = PIP_X0 + (hib - 1) * pitch + (pitch + DIV_EXTRA) * 0.5
    return n, hib, pitch, d, PIP_X0, div_x


def _pip_cx(i, hib, pitch, x0):
    """第 i 格圆心 x：竖线那一格之后整体右移 DIV_EXTRA。"""
    return x0 + i * pitch + (DIV_EXTRA if (0 < hib <= i) else 0.0)


def _draw_karma(p, win, info) -> None:
    """主圆环：直接用猫状态面板同款 karma 精灵（环 + 等级符号在一张图里）。"""
    level = max(KARMA_MIN, min(KARMA_MAX, int((info or {}).get("cycles") or 0)))
    frame = karma_frame(level)
    pm = None
    atlas = getattr(win, "atlas", None)
    if atlas is not None:
        try:
            pm = atlas.sprite("ui", frame)
        except Exception:
            pm = None
    half = KARMA_REF * 0.5
    box = QRectF(RING_CX - half, RING_CY - half, KARMA_REF, KARMA_REF)
    if pm is not None and not pm.isNull():
        p.drawPixmap(box, pm, QRectF(pm.rect()))
        return
    # 图集缺失（没导入 DLC 素材）时退回画等级数字，别让圆环空着
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(KARMA_REF * 0.6))
    p.setPen(_INK)
    p.setFont(f)
    p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "%d" % level)


def ring_opacity(info) -> float:
    """征兆期那一圈的不透明度 0..1：柔和呼吸，不是方波开关。

    ``tick % (2 * BLINK_TICKS)`` 走一个完整余弦：起点最亮、半周期最暗、再回来。
    其余阶段（平静期 / 暴雨期）恒为 1.0。
    """
    if not (info or {}).get("omen"):
        return 1.0
    try:
        tick = int((info or {}).get("tick") or 0)
    except (TypeError, ValueError):
        return 1.0
    phase = (tick % (2 * BLINK_TICKS)) / float(2 * BLINK_TICKS)
    k = 0.5 + 0.5 * math.cos(2.0 * math.pi * phase)
    return BLINK_DIM + (1.0 - BLINK_DIM) * k


def _draw_ring(p, info) -> None:
    """RainMeter.cs:189：正上方起逆时针排，耗尽的时间点保留为空心圆。"""
    lit = ring_lit(info)
    count = ring_count(info)
    step = 360.0 / float(count)
    p.save()
    _op = ring_opacity(info)
    if _op < 1.0:
        p.setOpacity(_op)        # 征兆期：整圈一起柔和呼吸
    # 先画完整的空心刻度，消耗时间后只移除内部填充，位置不会跳变。
    outline = QPen(_INK)
    outline.setWidthF(max(0.7, DOT_R * 0.7))
    p.setPen(outline)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(count):
        a = math.radians(DOT_START_DEG - i * step)
        c = QPointF(RING_CX + RING_R * math.cos(a), RING_CY + RING_R * math.sin(a))
        p.drawEllipse(c, DOT_R, DOT_R)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_INK)
    for i in range(lit):
        a = math.radians(DOT_START_DEG - i * step)
        c = QPointF(RING_CX + RING_R * math.cos(a), RING_CY + RING_R * math.sin(a))
        p.drawEllipse(c, DOT_R, DOT_R)
    p.restore()


def _draw_pips(p, info) -> None:
    """饥饿条：一排圆圈，竖线左侧雨眠所需、右侧距上限；实心=当前饱食度。"""
    n, hib, pitch, d, x0, div_x = pip_geometry(info)
    if n <= 0:
        return
    filled = max(0, min(n, int((info or {}).get("food") or 0)))
    quarter = max(0, min(3, int((info or {}).get("food_quarter") or 0)))
    wpen = max(1.0, PIP_RING * (pitch / PIP_PITCH))
    ring_pen = QPen(_INK)
    ring_pen.setWidthF(wpen)
    r = d * 0.5
    core = max(2.0, PIP_CORE * (d / PIP_D)) * 0.5
    for i in range(n):
        cx = _pip_cx(i, hib, pitch, x0)
        box = QRectF(cx - r, PIP_CY - r, d, d)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(box)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_INK)
        if i < filled:
            p.drawEllipse(QRectF(cx - core, PIP_CY - core, core * 2.0, core * 2.0))
        elif i == filled and quarter:
            # 原版 Player.HUD 的 1/4 格：从 12 点钟顺时针填 quarter/4 个扇形
            p.drawPie(box, 90 * 16, -int(quarter * 90 * 16))
    if div_x is not None:
        p.setPen(ring_pen)
        p.drawLine(QPointF(div_x, PIP_CY - DIV_H * 0.5), QPointF(div_x, PIP_CY + DIV_H * 0.5))


def fmt_countdown(seconds) -> str:
    """倒计时文案：``MM:SS``，分钟补零（参考图是 ``06:42``）。"""
    try:
        s = max(0, int(float(seconds) + 0.5))
    except (TypeError, ValueError):
        s = 0
    return "%02d:%02d" % (s // 60, s % 60)


def countdown_box(info):
    """倒计时文字的盒 (x, y, w, h)，参考单位；左沿对齐饥饿条第一格的左沿。"""
    _n, hib, pitch, d, x0, _div = pip_geometry(info)
    cx0 = _pip_cx(0, hib, pitch, x0)
    h = TIME_FONT * 1.5
    return (cx0 - d * 0.5, TIME_CY - h * 0.5, 200.0, h)


def _draw_countdown(p, info) -> None:
    """饥饿条下方的倒计时数字：和主圆环那一圈读同一个剩余时间。

    不跟着征兆期闪烁 —— 圆点闪是「快到暴雨了」的提示，数字要一直读得清。
    """
    x, y, w, h = countdown_box(info)
    f = QFont()
    f.setPixelSize(max(1, int(round(TIME_FONT))))
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, TIME_TRACK)
    p.save()
    p.setPen(_INK)
    p.setFont(f)
    p.drawText(QRectF(x, y, w, h),
               int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
               fmt_countdown((info or {}).get("seconds")))
    p.restore()


def _font_ok() -> bool:
    """字体库里有没有能画汉字的族；探测结果缓存（QApplication 建好后才有字体库）。"""
    global _FONT_OK
    if _FONT_OK is None:
        try:
            from PySide6.QtWidgets import QApplication
            if QApplication.instance() is None:
                return True          # 还没建 app，字体库没加载，先按有字体算且不写缓存
        except Exception:
            return True
        try:
            from PySide6.QtGui import QFontDatabase
            fams = set(QFontDatabase.families())
            _FONT_OK = bool(fams) and any(f in fams for f in _CJK_FAMS)
        except Exception:
            _FONT_OK = False
    return _FONT_OK


def _label(key: str) -> str:
    """中文文案；字体库画不出汉字就退 ASCII。"""
    if _font_ok():
        return t(key)
    return _ASCII.get(key, key)


def _fmt_time(seconds: float) -> str:
    s = max(0, int(seconds + 0.5))
    return "%d:%02d" % (s // 60, s % 60)


def hud_lines(info) -> list:
    """把 ``hud_info`` 翻成几行文案（第一行主色，其余警示色）。"""
    if not info:
        return []
    key = "hud_hibernation" if info.get("mode") == "storm" else "hud_rain_cycle"
    out = ["%s %s" % (_label(key), _fmt_time(info.get("seconds", 0.0)))]
    if info.get("hungry"):
        out.append(_label("hud_starvation"))
    return out


def hud_rect(win):
    """HUD 在逻辑坐标里的包围盒 (x0, y0, x1, y1)。

    默认贴屏幕左边缘与任务栏上沿；用户拖动后使用窗口保存的临时位置。
    """
    hl = float(getattr(win, "_HL", 0.0) or 0.0)
    pos = getattr(win, "_storm_hud_pos", None)
    scale = max(0.55, min(2.5, float(getattr(win, "_storm_hud_scale", 1.0) or 1.0)))
    width, height = HUD_W * scale, HUD_H * scale
    if pos is None:
        x0, y1 = 0.0, hl
        return (x0, y1 - height, x0 + width, y1)
    x0, y0 = float(pos[0]), float(pos[1])
    return (x0, y0, x0 + width, y0 + height)


def hud_scale(win) -> float:
    """Current user scale, clamped to a useful range."""
    return max(0.55, min(2.5, float(getattr(win, "_storm_hud_scale", 1.0) or 1.0)))


def hud_size(win):
    s = hud_scale(win)
    return HUD_W * s, HUD_H * s


def visible(win) -> bool:
    try:
        return win.storm.hud_info(getattr(win, "pets", ())) is not None
    except Exception:
        return False


def draw_storm_hud(p, win) -> None:
    """画左下角的雨眠计时器。雨循环未开时什么都不画。"""
    try:
        info = win.storm.hud_info(getattr(win, "pets", ()))
    except Exception:
        return
    if not info:
        return
    x0, y0, _, _ = hud_rect(win)
    user_scale = hud_scale(win)
    s = _layout_scale()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # 默认底边正好贴任务栏上沿，柔边也不能伸到任务栏下方。
    p.setClipRect(QRectF(0.0, 0.0, float(win._WL), float(win._HL)),
                  Qt.ClipOperation.IntersectClip)
    # Draw in the original 220×76 design space and apply one uniform scale
    # around the HUD origin.  This keeps the ring, pips, text and backdrop in
    # proportion when the user resizes the timer.
    p.translate(x0, y0)
    p.scale(user_scale, user_scale)
    _draw_backdrop(p, 0.0, 0.0, info, s)
    # 参考图是硬边像素画：贴图放大用最近邻
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    # 不参与像素化滤镜：圆点/描边开抗锯齿，保持清晰
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(_PAD, (HUD_H - REF_H * s) * 0.5)
    p.scale(s, s)
    p.translate(-REF_X0, -REF_Y0)        # 参考坐标 -> 内容左上角
    # 参考图中的白色计时器有一圈很轻的黑色外发光；先画一层扩大后的
    # 黑色轮廓，再画正常内容。它只包住图形本身，不会变成整块椭圆阴影。
    n, hib, pitch, d, xpip, div_x = pip_geometry(info)
    p.save()
    p.setBrush(Qt.BrushStyle.NoBrush)
    for width, opacity in ((3.5, 0.10), (2.2, 0.18)):
        p.setOpacity(opacity)
        glow_pen = QPen(QColor(0, 0, 0))
        glow_pen.setWidthF(width)
        p.setPen(glow_pen)
        p.drawEllipse(QPointF(RING_CX, RING_CY), KARMA_REF * 0.5 + 0.5, KARMA_REF * 0.5 + 0.5)
        for i in range(n):
            cx = _pip_cx(i, hib, pitch, xpip)
            p.drawEllipse(QPointF(cx, PIP_CY), d * 0.5, d * 0.5)
        if div_x is not None:
            p.drawLine(QPointF(div_x, PIP_CY - DIV_H * 0.5), QPointF(div_x, PIP_CY + DIV_H * 0.5))
    p.restore()
    _draw_ring(p, info)
    _draw_karma(p, win, info)
    _draw_pips(p, info)
    _draw_countdown(p, info)
    p.restore()
