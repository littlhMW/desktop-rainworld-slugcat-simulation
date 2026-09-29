# -*- coding: utf-8 -*-
"""幼崽（Slugpup）种族定义：小、轻、弱，食条只有 3 / 2。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (3, 2)
  SlugcatStats.cs:258-266  bodyWeightFac 0.65 / runspeedFac 0.8 /
                           poleClimbSpeedFac 0.8 / throwingSkill 0 / lungsFac 0.8
  PlayerGraphics.cs:3870   默认白
"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from .stats import DEFAULT_STATS
from .survivor import SURVIVOR_DEF

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
                  max_food=3, food_hibernate=2, throwing_skill=0, lungs_fac=0.8),
    # 幼崽：性格直接套用白猫（求生者）的基准，但每只的个体振幅很大
    # （PetUnit 用 WIDE_SIGMA）；另外幼崽不能救人、也不被救。
    personality=SURVIVOR_DEF.personality,
    tuning={},
    # 外观反编译 PlayerGraphics.cs:2880/2900/3041：0.9 + 0.2*Lerp(Wideness,0.5,0.5)
    visual={"pup_wide": True},
    fsm_mount=None,
    wip=False,
)
