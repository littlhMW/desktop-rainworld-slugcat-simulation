# -*- coding: utf-8 -*-
"""守望者（Watcher）种族定义：标准杂食（7 / 4），深蓝紫体色 + 发光 + 伪装。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (7, 4)
  SlugcatStats.cs:268-273  throwingSkill 1 / lungsFac 0.8
  PlayerGraphics.cs:3830   DefaultSlugcatColor = HSL2RGB(0.63055557, 0.54, 0.2)
  PlayerGraphics.cs:3600-3602  ApplyPalette 里守望者/夜猫还有一层压黑：
                           color2 = Lerp(palette.blackColor,
                                         HSL2RGB(0.63055557, 0.54, 0.5),
                                         Lerp(0.08, 0.04, palette.darkness))
                           取 darkness=0 → 黑底掺 8% 紫 → RGB(5,7,16)（几乎黑的深紫）
  PlayerGraphics.cs:3873   DefaultBodyPartColorHex → [body, "FFFFFF"]（眼=白=不染色）
  PlayerGraphics.cs:2672   InitializeLongerWatcherTail：尾段连接 6 / 10.5 / 10.5 / 10.5
                           （普通猫 4 / 7 / 7 / 7）—— 尾巴更长
  Player.cs:2568-2610      camoLimit 1600（涟漪等级不足时）/ enterIntoCamoDuration 80 /
                           exitOutOfCamoDuration 40 / 耗尽后有一段强制解除的疲劳

桌宠简化：涟漪等级、传送点、泪隙这些子系统不存在，所以只实装「发光 + 伪装」两件：
  * 发光 —— 自身一圈冷光（wiki：首遇陀螺后开始发光）
  * 伪装 —— 站住不动且附近没有威胁时进入半透明隐身，蜥蜴更难盯上它；
             电量按原版 1600 tick 上限，耗尽强制解除并进入数秒疲劳
"""
from __future__ import annotations

import math

from dataclasses import replace

from ..core.units import clampf
from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY
from .stats import DEFAULT_STATS

# 伪装（Player.cs:2568-2610 + wiki Controls）
CAMO_MAX = 1600          # camoLimit：涟漪等级不足时的原版上限
CAMO_ENTER = 80          # enterIntoCamoDuration：进入伪装的渐隐 tick
CAMO_EXIT = 40           # exitOutOfCamoDuration：退出伪装的渐显 tick
CAMO_REGEN = 3           # 没隐身时每 3 tick 回 1 点（桌宠简化）
CAMO_FATIGUE = 240       # 电量耗尽后的疲劳（≈6 s 内不能再伪装）
CAMO_NEAR_THREAT = 260.0  # 这个距离内有威胁就不进入伪装
CAMO_SHAKE_MAX = 2.2     # 被鼠标抓着时：光标位移超过这个幅度就藏不住（剧烈摇晃）
CAMO_SHAKE_DECAY = 0.72  # 晃动幅度的衰减（松开鼠标后 ~10 tick 回落）


def _fsm_mount(fsm):
    """守望者：伪装电量 + 半透明隐身。"""
    fsm._camo_charge = CAMO_MAX
    fsm._camo_level = 0.0
    fsm._camo_fatigue = 0
    fsm._camo_regen = 0
    fsm._camo_shake = 0.0

    def camo_tick():
        g, b = fsm.gfx, fsm.body
        if fsm._camo_fatigue > 0:
            fsm._camo_fatigue -= 1
        th = fsm._threat_lizard()
        near = th is not None and abs(th.x - b.chunk1.x) < CAMO_NEAR_THREAT
        # 被鼠标抓着也会试着隐身；但 GrabController.drag 把光标位移写进被抓那
        # 一节的 vx/vy，甩得越猛这个值越大 —— 剧烈摇晃就藏不住（原版被甩的猫
        # 同样维持不了伪装）。
        held = fsm.grab.active
        cur = 0.0
        if held and fsm.grab.chunk is not None:
            c = fsm.grab.chunk
            cur = math.hypot(float(getattr(c, "vx", 0.0)), float(getattr(c, "vy", 0.0)))
        fsm._camo_shake = max(cur, fsm._camo_shake * CAMO_SHAKE_DECAY)
        idle = (fsm.state == "IdleStand" and b.on_floor() and not b.is_moving())
        can = (fsm._camo_fatigue <= 0 and fsm._camo_charge > 0
               and (held or idle) and fsm._camo_shake < CAMO_SHAKE_MAX
               and not b.swimming and not fsm._zerog() and not near)
        if can:
            fsm._camo_charge -= 1
            if fsm._camo_charge <= 0:            # 电量耗尽：强制解除 + 疲劳
                fsm._camo_charge = 0
                fsm._camo_fatigue = CAMO_FATIGUE
                g.blink = 8
        elif fsm._camo_fatigue <= 0:             # 沒隐身时慢慢回电
            fsm._camo_regen += 1
            if fsm._camo_regen >= CAMO_REGEN:
                fsm._camo_regen = 0
                fsm._camo_charge = min(CAMO_MAX, fsm._camo_charge + 1)
        step = (1.0 / CAMO_ENTER) if can else -(1.0 / CAMO_EXIT)
        fsm._camo_level = clampf(fsm._camo_level + step, 0.0, 1.0)
        g.camo = fsm._camo_level

    fsm.register_ticker(camo_tick)


WATCHER_DEF = CatDef(
    key="watcher",
    # ApplyPalette（PlayerGraphics.cs:3600-3602）压黑后的守望者体色：
    # Lerp(black, HSL2RGB(0.63055557, 0.54, 0.5), 0.08) → (5, 7, 16)　几乎黑的深紫
    body_color=(5, 7, 16),
    eye_color=(255, 255, 255),    # DefaultBodyPartColorHex → FFFFFF（白＝不染色）
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
    # 守望者：孤僻（不喜欢任何互动、喜欢远离其他猫、也不喜欢救人），一般勇敢
    personality=replace(DEFAULT_PERSONALITY, activity=0.35, stamina=1.0,
                        sociability=0.05, temper=0.35, crawl_like=0.5,
                        point_like=0.05, bravery=0.5, kindness=0.05,
                        play_style="sit", hurry=0.25, wake_like=0.05,
                        risk_tolerance=0.35, patience=0.85),
    # InitializeLongerWatcherTail（PlayerGraphics.cs:2672-2678）：尾巴更长
    visual={"tail_conn": (6.0, 10.5, 10.5, 10.5),
            "glow": (150, 190, 255)},
    tuning={},
    fsm_mount=_fsm_mount,
    wip=False,
)
