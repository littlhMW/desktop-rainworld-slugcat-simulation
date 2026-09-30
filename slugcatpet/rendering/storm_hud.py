# -*- coding: utf-8 -*-
"""左下角固定 HUD：雨眠计时器（雨循环）。

布局照参考图（298×82 设计稿）来，几何全部用「参考单位」写下，绘制前统一乘
``_layout_scale()``：

  左 · 主圆环：环 + 等级符号是同一张 45×45 精灵（``ui`` 图集的 ``smallKarma*``，
  与猫状态面板同一套业力图标）。等级 = 已完成的雨循环次数，1..10 夹紧。
  环外一圈 17 个小圆点 = 当前阶段剩余时间：实心=剩余、空心=已消耗，从右上角
  （约 1:30）起顺时针排，随时间推移从起点开始变空心。

    征兆期与平静期在视觉上合并成同一个「平静期」环（整圈 = 整个专注期）；
    暴雨期（集合段 + 雨眠段）单独一个环，一路走到雨停。
    只有征兆期那一圈会动 —— 而且是柔和呼吸式的明暗，不是硬闪。

  右 · 饥饿条：一排圆圈，竖线左侧是雨眠所需格数、右侧是总上限减去雨眠上限的格数；
  实心格 = 当前饱食度，最后一格按 ``food_quarter`` 画 1/4 扇形。固定只显示第一只猫。
  饥饿条正下方是倒计时数字（``MM:SS``，分钟补零），和一圈圆点读同一个剩余时间。

数据全部来自 ``StormCycle.hud_info()``；这一层只负责画，不推进任何逻辑
（Starvation 不接 ``food_eat()``）。绘制坐标是屏幕（逻辑）坐标，不跟 ``window._shake`` 晃。

这一层不参与像素化滤镜：像素模式下由 ``window.paintEvent`` 在低分辨率缓冲放大**之后**
再调它，层级最高，且圆点/描边用抗锯齿画，保持清晰。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from ..i18n import t

HUD_W = 168.0        # 固定宽高：脏矩形要能在不算文字尺寸的前提下稳定取值
HUD_H = 48.0
HUD_MARGIN = 10.0
_LINE_H = 15.0
_PAD = 3.0           # 面板内边距（逻辑像素）

# ── 参考图几何（直接量参考图得到的像素坐标，见 work/scratch/w109meas.py）──
#  主圆环：45×45（正好是 ui 图集 smallKarma* 精灵的整张大小，环宽 4）
#  一圈 17 个圆点：拟合圆心 (36.2, 40.7)、半径 31.0；实心点 d≈4、空心点 d≈6.6
#  饥饿条：第一格圆心 x=89、圆心距 30、外径 23（描边 2）、实心圆 d=11
REF_X0 = 3.2             # 内容左边界（最左那个圆点的左沿）
REF_Y0 = 7.7             # 内容上边界（最上那个圆点的上沿）
REF_W = 292.5            # 内容宽（主圆环 + 示例的 7 格饥饿条）
REF_H = 66.0             # 内容高
RING_CX = 36.2           # 主圆环中心 x
RING_CY = 40.7           # 主圆环中心 y
RING_R = 31.0            # 一圈圆点所在半径
DOTS = 17                # 一圈圆点个数
DOT_R = 2.0              # 剩余的实心圆点半径
DOT_HOLLOW_R = 3.0       # 已消耗的空心圆点半径
DOT_PEN = 1.1            # 空心圆点描边宽
KARMA_REF = 45.0         # karma 精灵边长（精灵里环外径就是 45，1:1 画回参考图尺寸）
PIP_X0 = 89.0            # 第一格圆心 x
PIP_PITCH = 30.0         # 格中心距
PIP_D = 21.0             # 格椭圆盒直径（+2px 描边 = 参考图量到的 23 墨迹）
PIP_RING = 2.0           # 外圈描边宽
PIP_CORE = 11.0          # 实心圆直径（外径的一半）
PIP_CY = 41.0            # 格圆心 y
DIV_EXTRA = 15.0         # 分隔线额外占宽
DIV_H = 33.0             # 分隔线高（比圆圈高一截，和参考图一致）
TIME_FONT = 14.0         # 倒计时字号（参考单位，≈ 格直径的 0.64，和参考图一致）
TIME_CY = 62.6           # 倒计时文字中心 y：饥饿条正下方
TIME_TRACK = 1.0         # 字距（参考单位）
DOT_START_DEG = -45.0   # 小圆点起点：右上角 1:30 方向，顺时针排
BLINK_TICKS = 28         # 征兆期「呼吸」的半周期（40 tick/s → 0.7s 呼气，整次呼吸 1.4s）
BLINK_DIM = 0.25         # 呼吸最暗那一档的透明度（是变暗，不是熄灭）
KARMA_MIN = 1
KARMA_MAX = 10           # 最低 1 级、最高 10 级

_INK = QColor(238, 232, 214)
_PANEL = QColor(12, 11, 10, 150)

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


def ring_lit(info) -> int:
    """主圆环外一圈里还剩几个实心的（0..DOTS）。"""
    try:
        total = float((info or {}).get("ring_total") or 0.0)
        remain = float((info or {}).get("ring_remain") or 0.0)
    except (TypeError, ValueError):
        return 0
    if total <= 0.0:
        return 0
    remain = max(0.0, min(total, remain))
    progress = 1.0 - remain / total
    if (info or {}).get("mode") == "storm":
        return max(0, min(DOTS, int(math.ceil(progress * DOTS - 1e-6))))
    consumed = max(0, min(DOTS, int(math.floor(progress * DOTS + 1e-6))))
    return DOTS - consumed


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
    """主圆环外一圈小圆点：实心=剩余、空心=已消耗。

    从右上角（约 1:30）起顺时针排；随时间推移从起点那一颗开始变空心。
    征兆期这一圈整体柔和呼吸（见 ``ring_opacity``）。
    """
    lit = ring_lit(info)
    step = 360.0 / float(DOTS)
    hollow_from = DOTS - lit
    storm_mode = (info or {}).get("mode") == "storm"
    hollow_pen = QPen(_INK)
    hollow_pen.setWidthF(DOT_PEN)
    p.save()
    _op = ring_opacity(info)
    if _op < 1.0:
        p.setOpacity(_op)        # 征兆期：整圈一起柔和呼吸
    for i in range(DOTS):
        a = math.radians(DOT_START_DEG + i * step)   # y 向下 = 顺时针
        c = QPointF(RING_CX + RING_R * math.cos(a), RING_CY + RING_R * math.sin(a))
        solid = (i < lit) if storm_mode else (i >= hollow_from)
        if solid:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_INK)
            p.drawEllipse(c, DOT_R, DOT_R)
        else:
            p.setPen(hollow_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, DOT_HOLLOW_R, DOT_HOLLOW_R)
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
    """HUD 在逻辑坐标里的包围盒 (x0, y0, x1, y1)。"""
    hl = float(getattr(win, "_HL", 0.0) or 0.0)
    return (HUD_MARGIN, hl - HUD_H - HUD_MARGIN,
            HUD_MARGIN + HUD_W, hl - HUD_MARGIN)


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
    x0, y0, x1, y1 = hud_rect(win)
    s = _layout_scale()
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_PANEL)
    p.drawRoundedRect(QRectF(x0, y0, x1 - x0, y1 - y0), 4.0, 4.0)
    # 参考图是硬边像素画：贴图放大用最近邻
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    # 不参与像素化滤镜：圆点/描边开抗锯齿，保持清晰
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(x0 + _PAD, y0 + (HUD_H - REF_H * s) * 0.5)
    p.scale(s, s)
    p.translate(-REF_X0, -REF_Y0)        # 参考坐标 -> 内容左上角
    _draw_ring(p, info)
    _draw_karma(p, win, info)
    _draw_pips(p, info)
    _draw_countdown(p, info)
    p.restore()
