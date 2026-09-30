# -*- coding: utf-8 -*-
"""幼崽（Slugpup）种族定义：小、轻、弱，食条只有 3 / 2。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (3, 2)
  SlugcatStats.cs:258-266  bodyWeightFac 0.65 / runspeedFac 0.8 /
                           poleClimbSpeedFac 0.8 / throwingSkill 0 / lungsFac 0.8
  PlayerGraphics.cs:3870   默认白
  Player.cs:4114-4131     setPupStatus：躯体间距 12（成年 17）、体块质量 0.7/2（成年 0.75/2）
"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from ..core.gfxmath import _hsl2rgb
from .stats import DEFAULT_STATS
from .survivor import SURVIVOR_DEF

# ── 个体外观：按 Rain World 的 Player.NPCStats 生成 ────────────────────
# NPCStats 的随机顺序、幂分布和 H/S/L/Dark/EyeColor 取值按反编译结果保持一致。
# 绿/黄更常见、红/紫更少见来自 H 的原生随机分布，不再人为切色相区间。
_MASK32 = 0xFFFFFFFF
_MT19937 = 1812433253


class _PupRNG:
    """Rain World NPCStats 所用的 XorShift128，保持 32-bit 溢出语义。"""

    __slots__ = ("x", "y", "z", "w")

    def __init__(self, seed: int):
        self.x = seed & _MASK32
        self.y = (_MT19937 * self.x + 1) & _MASK32
        self.z = (_MT19937 * self.y + 1) & _MASK32
        self.w = (_MT19937 * self.z + 1) & _MASK32

    def _next_u32(self) -> int:
        t = (self.x ^ ((self.x << 11) & _MASK32)) & _MASK32
        self.x, self.y, self.z = self.y, self.z, self.w
        self.w = (self.w ^ (self.w >> 19) ^ t ^ (t >> 8)) & _MASK32
        return self.w

    def next_float(self) -> float:
        return self._next_u32() / 4294967295.0

    def next_float_range(self, lo: float, hi: float) -> float:
        # 保持原版 NextFloatRange 的方向：hi - (hi-lo)*u。
        return (lo - hi) * self.next_float() + hi


def _hsl2rgb8(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = _hsl2rgb(h, s, l)
    return tuple(int(round(max(0.0, min(1.0, c)) * 255.0)) for c in (r, g, b))


def pup_appearance(seed: int):
    """返回 (body_rgb, eye_rgb, size, wideness)，同一 ID 可稳定重建。"""
    rng = _PupRNG(seed)

    # 与 Player.NPCStats 构造函数保持同一随机读取顺序。
    _bal = rng.next_float() ** 1.5
    met = rng.next_float() ** 1.5
    stealth = rng.next_float() ** 1.5
    size = rng.next_float() ** 1.5
    wideness = rng.next_float() ** 1.5

    h0 = rng.next_float_range(0.15, 0.58)
    h1 = rng.next_float()
    hue = h0 + (h1 - h0) * (rng.next_float() ** (1.5 - met))

    sat = rng.next_float_range(0.0, 1.0) ** (0.3 + stealth * 0.3)
    dark = rng.next_float_range(0.0, 1.0) <= 0.3 + stealth * 0.2
    lightness = rng.next_float_range(0.9 if dark else 0.75, 1.0) ** (1.5 - stealth)
    eye_value = rng.next_float() ** (2.0 - stealth * 1.5)

    # PlayerGraphics：Dark 时把 L 反向，形成低明度体色。
    body_l = max(0.01, min(1.0, 1.0 - lightness if dark else lightness))
    body = _hsl2rgb8(hue, sat, body_l)

    # 眼睛靠近黑/白两端，同时保留 NPCStats.EyeColor 的随机明暗。
    base_eye = _hsl2rgb8(hue, sat, max(0.01, min(1.0, 1.0 - eye_value)))
    target = (255, 255, 255) if dark else (0, 0, 0)
    eye = tuple(int(round(base_eye[i] * 0.2 + target[i] * 0.8)) for i in range(3))
    return body, eye, size, wideness


SLUGPUP_DEF = CatDef(
    key="slugpup",
    body_color=(255, 255, 255),
    eye_color=(22, 30, 16),
    frames={
        # 外观反编译 PlayerGraphics.cs:3025/4291：幼崽头用 HeadC 族、脸用 PFace 族
        "head": ("msc", "HeadC"),
        "face": ("msc", "PFaceA"),
        "face_blink": ("msc", "PFaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="slugpup.json",
    atlas_keys=("base", "msc"),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, runspeed_fac=0.8, weight_fac=0.65, pole_fac=0.8,
                  max_food=3, food_hibernate=2, throwing_skill=0, lungs_fac=0.8,
                  # Player.setPupStatus：幼崾躯体真的短（12 vs 17）、轻（0.7 vs 0.75）
                  conn_fac=12.0 / 17.0, mass_fac=0.7 / 0.75),
    # 幼崽：性格直接套用白猫（求生者）的基准，但每只的个体振幅很大
    # （PetUnit 用 WIDE_SIGMA）；另外幼崽不能救人、也不被救。
    personality=SURVIVOR_DEF.personality,
    tuning={},
    # 猫崽整体缩放：0.65 同时用于绘制、碰撞体尺寸，并通过 SlugcatBody 的
    # body_scale 参与骨骼相关的步距/站姿/手臂活动范围计算。
    # conn_fac 仍单独保留 Player.setPupStatus 的 12/17 原始胸胯比例；
    # 两者不是重复缩放，而是分别表达“原版骨架比例”和“本项目整体尺寸”。
    # 表情（face / eye / expression）保持原有实现，这里只声明体型参数。
    visual={"pup_wide": True, "draw_scale": 0.65},

    fsm_mount=None,
    wip=False,
)
