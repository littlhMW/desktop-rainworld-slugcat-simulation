# -*- coding: utf-8 -*-
"""怪猫（Sofanthiel / Inv）种族定义：12 格食条的杂食猫，尸体只给半格。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (12, 12)：上限 = 冬眠阈
  SlugcatStats.cs:341-352  走 Red 分支（和红猫同档位）
  Player.cs:12075-12084    非蜈蚣尸体每口 AddQuarterFood()×2（半格）
  PlayerGraphics.cs:3844   DefaultSlugcatColor = (0.09, 0.14, 0.31)
"""
from __future__ import annotations

import math
from dataclasses import replace

from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY, DIET_GOURMAND
from .stats import DEFAULT_STATS
from ..world.enums import ItemState

# 撕咬（SlugcatStats.cs:503-512 SlugcatCanMaul = Artificer 或 Sofanthiel；
# 原版 Player.cs:10157-10212 maulTimer 每 8 tick 一口）
MAUL_RANGE = 34.0        # 贴到这个距离才扑上去咬
MAUL_PERIOD = 8          # 每 8 tick 一口
MAUL_DMG = 0.6           # 每口伤害（怪猫矛弱，撕咬才是它的看家本事）
MAUL_BITES = 4           # 一次压住咬几口
MAUL_CD = 260            # 咬完的冷却


def _fsm_mount(fsm):
    """怪猫独占：像工匠一样能抓着活物撕咬。"""
    fsm._maul_cd = 0
    fsm._maul_bites = 0
    fsm._maul_t = 0
    fsm._maul_target = None

    def maul_tick():
        if fsm._maul_cd > 0:
            fsm._maul_cd -= 1
        b = fsm.body
        if fsm._maul_bites > 0:
            lz = fsm._maul_target
            if lz is None or getattr(lz, "dead", False) or lz.state != ItemState.FREE:
                fsm._maul_bites = 0
                fsm._maul_target = None
                return
            fsm._maul_t += 1
            if fsm._maul_t % MAUL_PERIOD == 0:
                f = 1.0 if b.facing >= 0 else -1.0
                n = math.hypot(f, 0.4) or 1.0
                try:
                    lz.hurt(MAUL_DMG, dvec=(f / n, -0.4 / n), speed=6.0,
                            stun_bonus=12.0, hit_head=False, knock_k=0.3)
                except Exception:
                    pass
                fsm._maul_bites -= 1
                if fsm._maul_bites <= 0:
                    fsm._maul_cd = MAUL_CD
                    fsm._maul_target = None
            return
        if (fsm._maul_cd > 0 or fsm.state != "IdleStand" or not b.on_floor()
                or fsm.grab.active or fsm._hibernating or b.swimming
                or fsm._zerog()):
            return
        th = fsm._threat_lizard()
        if th is None or getattr(th, "dead", False):
            return
        if math.hypot(th.x - b.chunk1.x, th.y - b.chunk1.y) > MAUL_RANGE:
            return
        fsm._maul_target = th
        fsm._maul_bites = MAUL_BITES
        fsm._maul_t = 0

    fsm.register_ticker(maul_tick)

INV_DEF = CatDef(
    key="inv",
    body_color=(23, 36, 79),      # DefaultSlugcatColor（PlayerGraphics.cs:3844）
    eye_color=(255, 255, 255),    # DefaultBodyPartColorHex：Sofanthiel → FFFFFF（白＝不染色）
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
    # 怪猫投掷力是原版最低档（wiki：投掷力 0 / 矛击伤害 0.6-0.9）
    stats=replace(DEFAULT_STATS, runspeed_fac=1.2, weight_fac=1.12, pole_fac=1.25,
                  max_food=12, food_hibernate=12, throwing_skill=0,
                  spear_dmg_range=(0.6, 0.9)),
    # 怪猫：食条最长、什么都吃，逻辑混沌
    personality=replace(DEFAULT_PERSONALITY, activity=0.6, stamina=1.2,
                        sociability=0.4, temper=0.7, crawl_like=0.35,
                        point_like=0.7, bravery=0.75, kindness=0.35,
                        play_style="hop", diet=DIET_GOURMAND,
                        hurry=0.6, spear_like=1.1, pearl_like=1.2,
                        risk_tolerance=0.7, patience=0.35),
    # 性格数据一段时间就整份重揗一次（PetUnit._churn_tick）
    # pers_churn：性格数据一段时间整份重揗（逻辑混沌）；maul：能抓着活物撕咬
    tuning={"pers_churn": True, "maul": True},
    fsm_mount=_fsm_mount,
    wip=False,
)
