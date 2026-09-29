from __future__ import annotations
from dataclasses import replace
from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY, DIET_CARNIVORE
from .stats import DEFAULT_STATS

HUNTER_DEF = CatDef(
    key="hunter",
    body_color=(255, 115, 115),   # Red #FF7373
    eye_color=(22, 30, 16),
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="hunter.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, runspeed_fac=1.2, pole_fac=1.25, weight_fac=1.12,
                  max_food=9, food_hibernate=6, throwing_skill=2),
    # 暴躁猎手：玩东西会甩出去，不爱趴，边走边跳，背后常备一支矛
    personality=replace(DEFAULT_PERSONALITY, activity=0.65, stamina=1.05,
                        sociability=0.3, temper=0.9, crawl_like=0.25,
                        point_like=0.55, bravery=0.90, kindness=0.25,
                        play_style="hop", diet=DIET_CARNIVORE,
                        hurry=0.95, spear_like=1.25, pearl_like=0.6,
                        risk_tolerance=0.85, patience=0.15),   # 赶时间：敢冒险，没耐心等
    # 原版 Player.spearOnBack：猎手背后常备一支矛
    tuning={"back_spear": True},
    fsm_mount=None,
    wip=False,
)
