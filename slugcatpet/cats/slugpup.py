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

import random
from dataclasses import replace

from .base import CatCaps, CatDef
from .stats import DEFAULT_STATS
from .survivor import SURVIVOR_DEF

# ── 个体颜色（wiki Slugpup）──────────────────────────────────────────────
# 「猫崽的体色和瞳色多变，绿色和黄色系的最常见，而红色和紫色系的最罕见。」「体色由
#   游戏文件里的变量 Dark 控制（1/2 抽深色/浅色色板）；瞳色与体色相关：深色猫崽的
#   眼睛固定纯白，浅色猫崽的眼睛固定纯黑。」这里只做体型/外观区分，不做性格差异。
PUP_DARK_P = 0.5                 # Dark 变量：1/2 抽深色板

# 色相权重 (起, 止, 权重)：绿 / 黄最多，红 / 紫最少
PUP_HUE_BANDS = (
    (0.0, 30.0, 1.0),            # 红
    (30.0, 70.0, 4.0),           # 黄 / 橙
    (70.0, 160.0, 5.0),          # 绿（最常见）
    (160.0, 250.0, 2.0),         # 青 / 蓝
    (250.0, 340.0, 1.0),         # 紫（最罕见）
    (340.0, 360.0, 1.0),         # 品红 / 红
)


def pup_hsv_to_rgb(h, s, v):
    """HSV（各自 0..1）→ 0..255 的 RGB。"""
    h = (h % 1.0) * 6.0
    i = int(h)
    f = h - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return tuple(int(round(max(0.0, min(1.0, c)) * 255.0)) for c in (r, g, b))


def pup_colors(seed: int):
    """按个体种子抽 (体色, 瞳色)。同一只猫（id）每次启动都一致。"""
    rng = random.Random((seed ^ 0x5A17C0DE) & 0xFFFFFFFF)
    total = sum(w for _, _, w in PUP_HUE_BANDS)
    pick = rng.random() * total
    lo, hi = PUP_HUE_BANDS[0][0], PUP_HUE_BANDS[-1][1]
    for a, b, w in PUP_HUE_BANDS:
        pick -= w
        if pick <= 0.0:
            lo, hi = a, b
            break
    hue = (lo + (hi - lo) * rng.random()) / 360.0     # 绿 / 黄最常见的色相区
    dark = rng.random() < PUP_DARK_P                  # 深色板 or 浅色板
    if dark:
        sat = 0.10 + 0.85 * rng.random()              # 深色板：中高饱和 + 低明度
        val = 0.02 + 0.23 * rng.random()
    else:
        sat = 0.05 + 0.60 * rng.random()              # 浅色板：低中饱和 + 高明度
        val = 0.80 + 0.19 * rng.random()
    body = pup_hsv_to_rgb(hue, sat, val)
    # 瞳色不随机、只跟体色深浅走：深色体 → 纯白瞳，浅色体 → 纯黑瞳。
    eye = (255, 255, 255) if dark else (0, 0, 0)
    return body, eye


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
    # 外观反编译 PlayerGraphics.cs:2880/2900/3041：0.9 + 0.2*Lerp(Wideness,0.5,0.5)
    # draw_scale：绘整只缩到成年的一半（wiki：猫崽约为成年的一半大）
    visual={"pup_wide": True, "draw_scale": 0.5},
    fsm_mount=None,
    wip=False,
)
