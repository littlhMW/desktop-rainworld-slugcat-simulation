# -*- coding: utf-8 -*-
"""观察者（Watcher）种族定义：标准杂食（7 / 4）。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (7, 4)
  SlugcatStats.cs:268-273  throwingSkill 1 / lungsFac 0.8
  PlayerGraphics.cs:3830   DefaultSlugcatColor = HSL2RGB(0.6306, 0.54, 0.2)
"""
from __future__ import annotations

from dataclasses import replace

from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY
from .stats import DEFAULT_STATS

WATCHER_DEF = CatDef(
    key="watcher",
    body_color=(23, 35, 79),      # DefaultSlugcatColor（PlayerGraphics.cs:3830）
    eye_color=(22, 30, 16),
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="watcher.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, max_food=7, food_hibernate=4,
                  throwing_skill=1, lungs_fac=0.8),
    # 观察者：孤僻（不喜欢任何互动、喜欢远离其他猫、也不喜欢救人），一般勇敢
    personality=replace(DEFAULT_PERSONALITY, activity=0.35, stamina=1.0,
                        sociability=0.05, temper=0.35, crawl_like=0.5,
                        point_like=0.05, bravery=0.5, kindness=0.05,
                        play_style="sit", hurry=0.25, wake_like=0.05,
                        risk_tolerance=0.35, patience=0.85),
    tuning={},
    fsm_mount=None,
    wip=False,
)
