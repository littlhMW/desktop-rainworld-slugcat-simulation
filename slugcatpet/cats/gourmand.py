# -*- coding: utf-8 -*-
"""Gourmand（美食家）种族定义：食谱极广的杂食猫。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (11, 7)
  SlugcatStats.cs:216-224  bodyWeightFac 1.35 / poleClimbSpeedFac 0.8 / throwingSkill 2
  SlugcatStats.cs:354-357  NourishmentOfObjectEaten 走默认分支（植物/小猎物全份）
  Player.cs:12075-12084    非蜈蚣尸体每口 AddQuarterFood()×2（半格）
  PlayerGraphics.cs:3864   DefaultSlugcatColor = (0.94118, 0.75686, 0.59216)
"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY, DIET_GOURMAND
from .stats import DEFAULT_STATS

GOURMAND_DEF = CatDef(
    key="gourmand",
    body_color=(240, 193, 151),   # DefaultSlugcatColor（PlayerGraphics.cs:3864）
    eye_color=(22, 30, 16),
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="gourmand.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, weight_fac=1.35, pole_fac=0.8,
                  max_food=11, food_hibernate=7, throwing_skill=2),
    # 美食家：慢吞吞、能吃、爱做东西给你看
    personality=replace(DEFAULT_PERSONALITY, activity=0.45, stamina=1.15,
                        sociability=0.75, temper=0.4, crawl_like=0.45,
                        point_like=0.35, bravery=0.6, kindness=0.7,
                        play_style="sit", diet=DIET_GOURMAND,
                        hurry=0.3, spear_like=0.9, pearl_like=0.9,
                        risk_tolerance=0.45, patience=0.9),
    tuning={},
    fsm_mount=None,
    wip=True,      # 外观差异待后续（数值/食性/性格已按反编译实装）
)
