# -*- coding: utf-8 -*-
"""暴雨天气：连续雨强 + 固定雨滴池 + 雨幕参数 + 积水驱动（纯逻辑，不绘制）。

反编译口径：原版暴雨不是离散档位，而是一条 0→1 的连续曲线。这里也只暴露一个
连续值 ``intensity``，其它所有量（变暗 / 雨滴数 / 雨幕密度 / 震动 / 积水）都是
它的函数，于是「安静 → 变暗 → 偶尔一滴 → 第一滴重雨 → 整屏雨幕 → 死亡雨」是
一条平滑过程，不需要任何 ``if rain_level >= 3`` 之类的分支。

雨滴不做粒子洪流：``RainDrop`` 是带 ``__slots__`` 的定长池，``step`` 只把 ``y``
往前推，落到地面就从顶上绕回去，可见数量按 intensity 截断 —— 全程不新建/销毁
对象，所以暴雨期间整窗刷新也不会掉帧。
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


DROP_COUNT = 120          # 雨滴池容量（固定，不增删）
FIRST_DROP_AT = 0.62      # 第一滴重雨的强度阈值
FIRST_DROP_FLASH = 26     # 第一滴重雨 + 落地溅射的余韵时长（tick）
RAIN_FORCE_SCALE = 0.30   # 雨压：满强度、全暴露时每 tick 给猫/生物的下压加速度
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
        self.rng = random.Random(seed)
        self.drops = []
        self._make_drops()
        self.intensity = 0.0
        self.visible_drops = 0
        self.sheet_density = 0.0
        self.darkness = 0.0
        self.shake = 0.0
        self.flood = 0.0
        self.rumble = 0.0
        self.tile_off = 0.0
        self.exposure = 1.0
        self.first_drop = False        # 本 tick 刚打第一滴重雨
        self.first_drop_done = False
        self.flash = 0                 # 第一滴的余韵倒计时（供渲染层用）
        self.impact = False            # 本 tick 触发一次明显冲击（震屏 + 冲击环）
        self.impact_xy = None
        self._t = 0

    # ── 建池 ──
    def _make_drops(self):
        r = self.rng
        drops = []
        for i in range(DROP_COUNT):
            drops.append(RainDrop(
                x=r.uniform(-8.0, self.WL + 8.0),
                y=r.uniform(-self.HL, self.HL),
                speed=r.uniform(9.0, 17.0),
                length=r.uniform(6.0, 16.0),
                alpha=r.uniform(0.28, 0.72),
                width=1.0 if r.random() < 0.7 else 2.0,
                seed=i))
        self.drops = drops

    @property
    def active(self):
        """还在下雨 / 还有雨痕（整窗刷新的判据）。"""
        return self.intensity > 0.001 or self.flash > 0

    def set_world(self, WL, HL):
        """窗口尺寸 / 地面线变化：雨滴池按新尺寸重铺，别落在旧坐标上。"""
        self.WL = float(WL)
        self.HL = float(HL)
        self.rng.seed(0x5A17)
        self._make_drops()

    def reset(self):
        self.intensity = 0.0
        self.visible_drops = 0
        self.sheet_density = 0.0
        self.darkness = 0.0
        self.shake = 0.0
        self.flood = 0.0
        self.rumble = 0.0
        self.first_drop = False
        self.first_drop_done = False
        self.flash = 0
        self.impact = False
        self.impact_xy = None

    def rain_force(self, exposure=1.0):
        """雨压：按强度与暴露度算一个向下的加速度（只影响猫 / 生物 / 水）。"""
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
        # 雨滴：只推 y，落地绕回
        fall = 1.0 + 6.0 * i
        top = -self.HL
        for d in self.drops:
            d.y += d.speed * fall
            if d.y > self.HL + 10.0:
                d.y -= self.HL + 20.0
                if d.y < top:
                    d.y = top
        self.visible_drops = int(len(self.drops) * i)
        self.sheet_density = smoothstep(0.62, 0.95, i)
        self.darkness = smoothstep(0.05, 0.75, i) * 0.78
        self.shake = max(0.0, (i - 0.45) / 0.55) ** 2
        self.flood = smoothstep(0.65, 1.0, i)
        self.rumble = i
        self.tile_off = (self.tile_off + 14.0 + 60.0 * i) % 4096.0
        self.first_drop = False
        self.impact = False
        if self.flash > 0:
            self.flash -= 1
        if not self.first_drop_done and i >= FIRST_DROP_AT:
            self.first_drop_done = True
            self.first_drop = True
            self.impact = True
            self.flash = FIRST_DROP_FLASH
            self.impact_xy = (self.rng.uniform(self.WL * 0.15, self.WL * 0.85), self.HL)