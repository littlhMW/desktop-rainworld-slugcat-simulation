# -*- coding: utf-8 -*-
"""Gourmand（饕餮）种族定义：食谱极广的杂食猫。

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

def _fsm_mount(fsm):
    """按 tuning.slam 注册饕餮的独占状态（体重坠落攻击）。"""
    from .gourmand_slam import mount_slam
    mount_slam(fsm)


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
                  max_food=11, food_hibernate=7, throwing_skill=2, spear_dmg_mul=3.0),
    # 饕餮：极其善良、一般勇敢；不喜欢用矛，宁可跳起来用体重砸下去
    personality=replace(DEFAULT_PERSONALITY, activity=0.45, stamina=1.15,
                        sociability=0.8, temper=0.35, crawl_like=0.45,
                        point_like=0.35, bravery=0.5, kindness=0.95,
                        play_style="sit", diet=DIET_GOURMAND,
                        hurry=0.3, spear_like=0.0, pearl_like=0.9,
                        risk_tolerance=0.45, patience=0.9),
    # 体重坠落攻击（原版饕餮的独占能力）
    tuning={"slam": True},
    # 外观反编译 PlayerGraphics.cs:2872/2892：体 scaleX 1.4、臀 scaleX 1.6 —— 更圆
    visual={"body_sx": 1.4, "hips_sx": 1.6},
    fsm_mount=_fsm_mount,
    wip=False,
)
