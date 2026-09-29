# -*- coding: utf-8 -*-
"""怪猫（Sofanthiel / Inv）种族定义：12 格食条的杂食猫，尸体只给半格。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (12, 12)：上限 = 冬眠阈
  SlugcatStats.cs:341-352  走 Red 分支（和红猫同档位）
  Player.cs:12075-12084    非蜈蚣尸体每口 AddQuarterFood()×2（半格）
  PlayerGraphics.cs:3844   DefaultSlugcatColor = (0.09, 0.14, 0.31)
"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY, DIET_GOURMAND
from .stats import DEFAULT_STATS

INV_DEF = CatDef(
    key="inv",
    body_color=(23, 36, 79),      # DefaultSlugcatColor（PlayerGraphics.cs:3844）
    eye_color=(22, 30, 16),
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="inv.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, runspeed_fac=1.2, weight_fac=1.12, pole_fac=1.25,
                  max_food=12, food_hibernate=12, throwing_skill=2),
    # 怪猫：食条最长、什么都吃，性格偏怪
    personality=replace(DEFAULT_PERSONALITY, activity=0.6, stamina=1.2,
                        sociability=0.4, temper=0.7, crawl_like=0.35,
                        point_like=0.7, bravery=0.75, kindness=0.35,
                        play_style="hop", diet=DIET_GOURMAND,
                        hurry=0.6, spear_like=1.1, pearl_like=1.2,
                        risk_tolerance=0.7, patience=0.35),
    tuning={},
    fsm_mount=None,
    wip=True,      # 外观差异待后续（数值/食性/性格已按反编译实装）
)
