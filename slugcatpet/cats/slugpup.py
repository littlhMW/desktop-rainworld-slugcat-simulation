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
from .personality import DEFAULT_PERSONALITY
from .stats import DEFAULT_STATS

SLUGPUP_DEF = CatDef(
    key="slugpup",
    body_color=(255, 255, 255),
    eye_color=(22, 30, 16),
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="slugpup.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, runspeed_fac=0.8, weight_fac=0.65, pole_fac=0.8,
                  max_food=3, food_hibernate=2, throwing_skill=0, lungs_fac=0.8),
    # 幼崽：胆小、黏人、爱跟着别的猫
    personality=replace(DEFAULT_PERSONALITY, activity=0.7, stamina=0.7,
                        sociability=1.0, temper=0.15, crawl_like=0.6,
                        point_like=0.6, bravery=0.15, kindness=0.9,
                        play_style="hop", hurry=0.5, wake_like=0.9,
                        risk_tolerance=0.15, patience=0.4),
    tuning={},
    fsm_mount=None,
    wip=True,      # 外观差异待后续（数值/食性/性格已按反编译实装）
)
