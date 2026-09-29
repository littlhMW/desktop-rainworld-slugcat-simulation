# -*- coding: utf-8 -*-
"""Spearmaster（矛大师）种族定义：没有嘴，只能靠矛取食。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (10, 5)
  SlugcatStats.cs:247-256  runspeedFac 1.2 / bodyWeightFac 0.85 / throwingSkill 2 /
                           poleClimbSpeedFac 1.25
  SlugcatStats.cs:354       NourishmentOfObjectEaten 走 else-if 之外的恒 0 —— 没嘴经口进食
  PlayerGraphics.cs:3860   DefaultSlugcatColor = (0.31, 0.18, 0.41)
"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY, DIET_SPECIAL
from .stats import DEFAULT_STATS

SPEARMASTER_DEF = CatDef(
    key="spearmaster",
    body_color=(79, 46, 105),     # DefaultSlugcatColor（PlayerGraphics.cs:3860）
    eye_color=(22, 30, 16),
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="spearmaster.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, runspeed_fac=1.2, weight_fac=0.85, pole_fac=1.25,
                  max_food=10, food_hibernate=5, throwing_skill=2),
    # 矛大师：快、轻、只信矛；没嘴所以从不吃地上的东西
    personality=replace(DEFAULT_PERSONALITY, activity=0.8, stamina=1.1,
                        sociability=0.3, temper=0.65, crawl_like=0.3,
                        point_like=0.7, bravery=0.8, kindness=0.3,
                        play_style="hop", diet=DIET_SPECIAL,
                        hurry=0.8, spear_like=1.6, pearl_like=0.7,
                        risk_tolerance=0.8, patience=0.3),
    tuning={},
    fsm_mount=None,
    wip=True,      # 外观差异待后续（数值/食性/性格已按反编译实装）
)
