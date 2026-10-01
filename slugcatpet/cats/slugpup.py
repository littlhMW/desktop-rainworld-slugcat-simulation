# -*- coding: utf-8 -*-
"""幼崽（Slugpup）种族定义：小、轻、弱，食条只有 3 / 2。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (3, 2)
  SlugcatStats.cs:258-266  bodyWeightFac 0.65 / runspeedFac 0.8 /
                           poleClimbSpeedFac 0.8 / throwingSkill 0 / lungsFac 0.8
  PlayerGraphics.cs:3870   默认白
  Player.cs:4114-4131     setPupStatus：躯体间距 12（成年 17）、体块总质量 0.7*bodyWeightFac
  Player.cs:4641-4645     幼崽和成年体块半径相同：9 / 8
  PlayerGraphics.cs:2687 BodyA.scaleY = 0.5（其他部件不整体缩放）
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
        return lo + (hi - lo) * self.next_float()


def _hsl2rgb8(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = _hsl2rgb(h, s, l)
    return tuple(int(round(max(0.0, min(1.0, c)) * 255.0)) for c in (r, g, b))


def _initial_traits(rng: _PupRNG) -> tuple[float, float, float, float, float]:
    """Player.NPCStats: Bal, Met, Stealth, Size, Wideness 的读取顺序。"""
    return tuple(rng.next_float() ** 1.5 for _ in range(5))


def pup_appearance(seed: int):
    """返回 (body_rgb, eye_rgb, size, wideness)，同一 ID 可稳定重建。"""
    rng = _PupRNG(seed)

    # 与 Player.NPCStats 构造函数保持同一随机读取顺序。
    _bal, met, stealth, size, wideness = _initial_traits(rng)

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

    # PlayerGraphics.cs:3291-3294：眼色从 palette.blackColor（深体）或其反相
    # （Dark 体）出发，仅以 EyeColor*0.25 向 palette 黑色的反相插值。
    # 桌面没有房间调色板，沿用其他蛞蝓猫的脸部黑色作为 palette.blackColor。
    black = (22, 30, 16)
    start = tuple(255 - c for c in black) if dark else black
    end = (255 - black[0], 255 - black[2], 255 - black[1])
    t = eye_value * 0.25
    eye = tuple(int(round(start[i] + (end[i] - start[i]) * t)) for i in range(3))
    return body, eye, size, wideness


def pup_stats(seed: int):
    """NPCStats 对 Slugpup 移动/体重/呼吸基数的逐只修正。"""
    bal, met, stealth, _size, wideness = _initial_traits(_PupRNG(seed))
    base = SLUGPUP_DEF.stats
    return replace(
        base,
        runspeed_fac=base.runspeed_fac * (0.85 + 0.15*met + 0.15*(1-bal) + 0.1*(1-stealth)),
        weight_fac=base.weight_fac * (0.85 + 0.15*wideness + 0.1*met),
        pole_fac=base.pole_fac * (0.85 + 0.15*met + 0.15*bal + 0.1*(1-stealth)),
        lungs_fac=base.lungs_fac * (0.8 + 0.2*(1-met) + 0.2*(1-stealth)),
    )


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
                  # Player.setPupStatus：幼崽连接距离 12；本项目的基础体块质量
                  # cp.MASS=0.35 已是原版 0.7/2，不能再乘 0.7/0.75。
                  conn_fac=12.0 / 17.0),
    # 幼崽：性格直接套用白猫（求生者）的基准，但每只的个体振幅很大
    # （PetUnit 用 WIDE_SIGMA）；另外幼崽不能救人、也不被救。
    personality=SURVIVOR_DEF.personality,
    tuning={},
    # 原版没有幼崽整只缩放：体块半径仍为 9/8，连接缩短到 12；只把 BodyA
    # 竖向压到一半，并换 HeadC/PFace 与较短的尾巴。
    visual={"pup_wide": True, "body_sy": 0.5},

    fsm_mount=None,
    wip=False,
)
