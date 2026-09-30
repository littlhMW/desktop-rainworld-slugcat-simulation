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
    eye_color=(255, 255, 255),    # DefaultBodyPartColorHex：Spear → FFFFFF（白＝不染色）
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
                  max_food=10, food_hibernate=5, throwing_skill=2, dual_spear=True,
                  hand_spear_max=2, spear_dmg_mul=1.25),
    # 矛大师：性格很好、极其耐心、极其勇敢善良；没嘴所以从不吃地上的东西
    personality=replace(DEFAULT_PERSONALITY, activity=0.7, stamina=1.1,
                        sociability=0.7, temper=0.35, crawl_like=0.3,
                        point_like=0.25, bravery=0.95, kindness=0.95,
                        play_style="sit", diet=DIET_SPECIAL,
                        hurry=0.35, spear_like=1.6, pearl_like=0.7,
                        risk_tolerance=0.55, patience=0.95),
    # 尾巴自己长针（原版 SpearMaster 的独占能力：新鲜的针从尾巴长出来）
    tuning={"tail_needle": True},
    # 外观反编译：PlayerGraphics.cs:2876/2896 体臀 scaleX 0.76、3037 头 scaleX 0.85、
    # 3143 手横向偏移 ×0.6、947-1113 TailSpeckles 尾上 5×3 斑点 + 尾针精灵
    visual={"body_sx": 0.76, "hips_sx": 0.76, "head_sx": 0.85,
            "arm_offset_fac": 0.6, "tail_speckles": True,
            # 尾巴比别的猫肥一档：PlayerGraphics.cs:1741-1744 Spear 分支
            # TailSegment rad 8/6/4/2（默认猫 6/4/2.5/1），尾梢收圆头
            "tail_rad": (8.0, 6.0, 4.0, 2.0), "tail_tip": 2.4},
    fsm_mount=None,
    wip=False,
)
