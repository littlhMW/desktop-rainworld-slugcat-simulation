# -*- coding: utf-8 -*-
"""桌面背景取样：给白蜥迷彩用 —— 抓屏幕上一小块，返回出现最多的颜色。

桌宠窗口是透明置顶窗，蜥蜴身后的像素其实是真实桌面（壁纸 / 别的窗口）。原版白蜥
的体色取的是**房间背景色**，这里用「实时抓屏 + 颜色直方图」等价替代；抓屏在部分
环境（锁屏 / RDP / 独占全屏）会失败，失败一律返回 None —— 蜥蜴保持白色，不崩。
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication

CACHE_TTL = 1.6          # 同一块地方这么久复用一次采样（低频）
PIXEL_STEP = 2           # 环形采样步长：隔一个像素取一个，够了又便宜
INNER_FRAC = 0.42        # 挖掉的中央椭圆 = 采样半径 × 这个系数（避开自己身体）
_CACHE = {}


def _screen_of(widget):
    try:
        s = widget.screen() if (widget is not None and hasattr(widget, "screen")) else None
    except Exception:
        s = None
    return s or QGuiApplication.primaryScreen()


def _to_global(widget, x, y):
    try:
        if widget is not None and hasattr(widget, "mapToGlobal"):
            q = widget.mapToGlobal(QPoint(int(round(x)), int(round(y))))
            return int(q.x()), int(q.y())
    except Exception:
        pass
    return int(round(x)), int(round(y))


def dominant(widget, x, y, w, h, now=None):
    """窗口逻辑坐标 (x, y) 起 w×h 的屏幕区域里出现最多的颜色；失败 None。"""
    gx, gy = _to_global(widget, x, y)
    w, h = max(4, int(w)), max(4, int(h))
    now = time.monotonic() if now is None else float(now)
    key = (gx // 32, gy // 32)
    hit = _CACHE.get(key)
    if hit is not None and now - hit[0] < CACHE_TTL:
        return hit[1]
    col = _grab(_screen_of(widget), gx, gy, w, h)
    _CACHE[key] = (now, col)
    return col


def dominant_behind(widget, cx, cy, w, h, now=None):
    """以 (cx, cy) 往**上**取一块（旧的白蜥采样；现改用 dominant_around）。"""
    return dominant(widget, cx - w * 0.5, cy - h, w, h, now=now)


def dominant_around(widget, cx, cy, half_w, half_h, now=None):
    """以 (cx, cy) 为中心、半宽半高 (half_w, half_h) 的**周围一圈**环境主色。

    白蜥迷彩用：抓的是一块以自己为中心的矩形，但**挖掉中央椭圆**（自己身体
    占的那块），所以拿到的是周边的环境色，而不是被自己染白的色。失败 None。
    """
    half_w, half_h = max(4.0, float(half_w)), max(4.0, float(half_h))
    gx, gy = _to_global(widget, cx - half_w, cy - half_h)
    w, h = int(round(half_w * 2.0)), int(round(half_h * 2.0))
    now = time.monotonic() if now is None else float(now)
    key = (gx // 32, gy // 32, int(half_w), int(half_h))
    hit = _CACHE.get(key)
    if hit is not None and now - hit[0] < CACHE_TTL:
        return hit[1]
    col = _grab_ring(_screen_of(widget), gx, gy, w, h, half_w, half_h)
    _CACHE[key] = (now, col)
    return col


def _grab_ring(scr, gx, gy, w, h, half_w, half_h):
    """矩形抓屏 → 挖掉中央椭圆 → 降色阶直方图 → 出现最多的颜色。"""
    if scr is None:
        return None
    try:
        pm = scr.grabWindow(0, gx, gy, w, h)
        img = pm.toImage()
        if img.isNull():
            return None
    except Exception:
        return None
    hist = {}
    cx, cy = (w - 1) * 0.5, (h - 1) * 0.5
    irx = max(1.0, half_w * INNER_FRAC)
    iry = max(1.0, half_h * INNER_FRAC)
    step = max(1, int(PIXEL_STEP))
    for iy in range(0, img.height(), step):
        dy = (iy - cy) / iry
        for ix in range(0, img.width(), step):
            dx = (ix - cx) / irx
            if dx * dx + dy * dy < 1.0:
                continue                          # 中央椭圆＝自己身体，不采
            px = img.pixel(ix, iy)
            if ((px >> 24) & 0xFF) < 8:           # 全透明：什么也没抓到
                continue
            q = ((px >> 16) & 0xF8, (px >> 8) & 0xF8, px & 0xF8)
            hist[q] = hist.get(q, 0) + 1
    if not hist:
        return None
    q = max(hist, key=hist.get)
    return (q[0] | 7, q[1] | 7, q[2] | 7)


def _grab(scr, gx, gy, w, h):
    if scr is None:
        return None
    try:
        pm = scr.grabWindow(0, gx, gy, w, h)
        img = pm.toImage()
        if img.isNull():
            return None
    except Exception:
        return None
    hist = {}
    step_x = max(1, img.width() // 48)
    step_y = max(1, img.height() // 24)
    for iy in range(0, img.height(), step_y):
        for ix in range(0, img.width(), step_x):
            px = img.pixel(ix, iy)
            if ((px >> 24) & 0xFF) < 8:              # 全透明：什么也没抓到
                continue
            q = ((px >> 16) & 0xF8, (px >> 8) & 0xF8, px & 0xF8)
            hist[q] = hist.get(q, 0) + 1
    if not hist:
        return None
    q = max(hist, key=hist.get)
    return (q[0] | 7, q[1] | 7, q[2] | 7)
