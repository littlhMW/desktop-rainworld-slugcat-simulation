# -*- coding: utf-8 -*-
"""暴雨天气：连续雨强 + 固定雨滴池 + 雨幕参数 + 积水驱动（纯逻辑，不绘制）。

渲染与天气逻辑分离：这里提供稳定的 0→1 暴雨驱动，以及雨幕、暗化、震屏、
积水等视觉所需的连续参数。雨滴采用固定池，避免暴雨期间反复创建对象。
"""
from __future__ import annotations

import random


def smoothstep(a, b, x):
    """标准 smoothstep：x<=a → 0，x>=b → 1，中间是 S 曲线。"""
    if b == a:
        return 0.0 if x < a else 1.0
    t = (x - a) / (b - a)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


DROP_COUNT = 160
FIRST_DROP_AT = 0.54
FIRST_DROP_FLASH = 34
RAIN_FORCE_SCALE = 0.18
RAIN_FORCE_DEADZONE = 0.20


class RainDrop:
    """一颗雨滴的静态参数 + 当前位置。参数建池时抽一次，之后只改 y。"""

    __slots__ = ("x", "y", "speed", "length", "alpha", "width", "seed")

    def __init__(self, x, y, speed, length, alpha, width, seed):
        self.x = x
        self.y = y
        self.speed = speed
        self.length = length
        self.alpha = alpha
        self.width = width
        self.seed = seed


class RainSystem:
    """整个窗口共用一份。只算天气，不碰任何实体、不绘制。"""

    def __init__(self, WL, HL, seed=0x5A17):
        self.WL = float(WL)
        self.HL = float(HL)
        self._seed = int(seed)
        self.rng = random.Random(seed)
        self.drops = []
        self._make_drops()
        self.intensity = 0.0
        self.visible_drops = 0
        self.sheet_density = 0.0
        self.mist = 0.0
        self.darkness = 0.0
        self.shake = 0.0
        self.flood = 0.0
        self.rumble = 0.0
        self.tile_off = 0.0
        self.exposure = 1.0
        self.first_drop = False
        self.first_drop_done = False
        self.flash = 0
        self.impact = False
        self.impact_xy = None
        self._t = 0

    # ── 建池 ──
    def _make_drops(self):
        r = self.rng
        drops = []
        for i in range(DROP_COUNT):
            drops.append(RainDrop(
                x=r.uniform(-16.0, self.WL + 16.0),
                y=r.uniform(-self.HL, self.HL),
                speed=r.uniform(10.0, 18.0),
                length=r.uniform(14.0, 56.0),
                alpha=r.uniform(0.16, 0.46),
                width=0.8 if r.random() < 0.80 else 1.4,
                seed=i))
        self.drops = drops

    @property
    def active(self):
        """还在下雨 / 还有第一滴余韵。"""
        return self.intensity > 0.001 or self.flash > 0

    def set_world(self, WL, HL):
        """窗口尺寸 / 地面线变化：雨滴池按新尺寸重铺。"""
        self.WL = float(WL)
        self.HL = float(HL)
        self.rng.seed(self._seed)
        self._make_drops()

    def reset(self):
        self.intensity = 0.0
        self.visible_drops = 0
        self.sheet_density = 0.0
        self.mist = 0.0
        self.darkness = 0.0
        self.shake = 0.0
        self.flood = 0.0
        self.rumble = 0.0
        self.first_drop = False
        self.first_drop_done = False
        self.flash = 0
        self.impact = False
        self.impact_xy = None

    def reset_cycle(self):
        """新一轮雨开始：允许重新出现一次第一滴重雨。"""
        self.first_drop = False
        self.first_drop_done = False
        self.flash = 0
        self.impact = False
        self.impact_xy = None

    def rain_force(self, exposure=1.0):
        """雨压：按强度与暴露度算一个向下的加速度。"""
        if self.intensity <= RAIN_FORCE_DEADZONE:
            return 0.0
        e = 0.0 if exposure < 0.0 else (1.0 if exposure > 1.0 else float(exposure))
        return (self.intensity - RAIN_FORCE_DEADZONE) * RAIN_FORCE_SCALE * e

    def step(self, intensity, exposure=1.0):
        """推进一 tick。intensity 是 stormcycle 给的连续驱动值（0..1）。"""
        i = 0.0 if intensity < 0.0 else (1.0 if intensity > 1.0 else float(intensity))
        self.intensity = i
        self.exposure = exposure
        self._t += 1

        # 雨滴：只推 y，落地绕回；稍有横向风感，但不做随机抖动。
        fall = 0.85 + 6.4 * i
        top = -self.HL - 24.0
        wrap = self.HL + 48.0
        drift = 1.2 + 3.0 * i
        for d in self.drops:
            d.y += d.speed * fall
            d.x += drift * (0.25 + 0.75 * (d.seed & 1))
            if d.y > self.HL + 24.0:
                d.y -= wrap
                if d.y < top:
                    d.y = top
            if d.x > self.WL + 24.0:
                d.x -= self.WL + 48.0
            elif d.x < -24.0:
                d.x += self.WL + 48.0

        # 视觉曲线分开：低强度先有湿空气，中段才出现密集雨幕和明显变暗。
        self.visible_drops = int(len(self.drops) * (0.10 + 0.90 * smoothstep(0.34, 0.78, i)))
        self.sheet_density = smoothstep(0.46, 0.86, i)
        self.mist = smoothstep(0.10, 0.70, i)
        self.darkness = (0.16 * smoothstep(0.04, 0.32, i)
                         + 0.42 * smoothstep(0.26, 0.92, i))
        self.darkness = min(0.52, self.darkness)
        # 震屏只服务于世界内容；雨幕和暴雨遮罩本身在屏幕空间稳定绘制。
        self.shake = smoothstep(0.50, 0.96, i)
        self.flood = smoothstep(0.48, 0.94, i)
        self.rumble = i
        self.tile_off = (self.tile_off + 9.0 + 42.0 * i) % 8192.0

        self.first_drop = False
        self.impact = False
        if self.flash > 0:
            self.flash -= 1
        if not self.first_drop_done and i >= FIRST_DROP_AT:
            self.first_drop_done = True
            self.first_drop = True
            self.impact = True
            self.flash = FIRST_DROP_FLASH
            self.impact_xy = (
                self.rng.uniform(self.WL * 0.15, self.WL * 0.85),
                self.HL,
            )
