# -*- coding: utf-8 -*-
"""左下角固定 HUD：Starvation + 雨循环倒计时。

数据全部来自 ``StormCycle.hud_info()``（相位 / 秒数 / 饱食差）；这一层只负责画，
不推进任何逻辑（Starvation 不接 ``food_eat()``）。绘制坐标是屏幕（逻辑）坐标，
不跟 ``window._shake`` 晃。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen

from ..i18n import t

HUD_W = 172.0        # 固定宽高：脏矩形要能在不算文字尺寸的前提下稳定取值
HUD_H = 46.0
HUD_MARGIN = 10.0
_LINE_H = 15.0

# 能画汉字的字体族（有其一才用中文文案）
_CJK_FAMS = ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun",
             "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
             "PingFang SC", "WenQuanYi Micro Hei")
# 没有汉字字体时的 ASCII 兜底（画方框比英文更糟）
_ASCII = {"hud_rain_cycle": "Calm", "hud_rain": "Omen",
          "hud_hibernation": "Storm", "hud_starvation": "Starving"}
_FONT_OK = None      # None = 还没探过


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
    mode = info.get("mode")
    if mode == "rain":
        head = "%s %s" % (_label("hud_rain"), _fmt_time(info.get("seconds", 0.0)))
    elif mode == "hibernation":
        head = "%s %s" % (_label("hud_hibernation"), _fmt_time(info.get("seconds", 0.0)))
    else:
        head = "%s %s" % (_label("hud_rain_cycle"), _fmt_time(info.get("seconds", 0.0)))
    out = [head]
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
    """画左下角 HUD。雨循环未开时什么都不画。"""
    try:
        info = win.storm.hud_info(getattr(win, "pets", ()))
    except Exception:
        return
    if not info:
        return
    lines = hud_lines(info)
    if not lines:
        return
    x0, y0, x1, y1 = hud_rect(win)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(12, 11, 10, 150))
    p.drawRoundedRect(QRectF(x0, y0, x1 - x0, y1 - y0), 4.0, 4.0)
    f = QFont()
    f.setFamilies(list(_CJK_FAMS) + ["Segoe UI", "sans-serif"])
    f.setPointSizeF(9.0)
    f.setBold(True)
    p.setFont(f)
    align = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    y = y0 + 5.0
    for i, ln in enumerate(lines):
        p.setPen(QPen(QColor(238, 232, 214) if i == 0 else QColor(228, 106, 92)))
        p.drawText(QRectF(x0 + 9.0, y, x1 - x0 - 18.0, _LINE_H), align, ln)
        y += _LINE_H
    p.restore()
