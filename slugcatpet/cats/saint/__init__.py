"""Saint 种族定义与独占机制归属包。"""
from __future__ import annotations

from dataclasses import replace

from ..base import CatCaps, CatDef
from ..personality import DEFAULT_PERSONALITY, DIET_VEGETARIAN
from ..stats import DEFAULT_STATS

SAINT_COLOR = (170, 241, 86)     # #AAF156
SAINT_EYE = (22, 30, 16)         # 眼 / 脸暗色


def _fsm_mount(fsm):
    """按 caps 注册 Saint 独占状态（超度/舌头系）。"""
    from .states import mount
    mount(fsm)


SAINT_DEF = CatDef(
    key="saint",
    body_color=SAINT_COLOR,
    eye_color=SAINT_EYE,
    frames={
        "head": ("msc", "HeadB"),
        "face": ("base", "FaceB"),        # 闭眼
        "face_blink": ("base", "FaceB"),
        "face_open": ("base", "FaceB"),   # 原版 SaintFaceCondition() 恒 true：圣徒永远闭眼
        # 晕眩脸：原版 PlayerGraphics.cs:2964/3006 对**所有**蛞蝓猫（含圣徒）都用
        # 同一张 FaceStunned，不做种族分支；圣徒的"永远闭眼"只作用在常态表情上
        # （DefaultFaceSprite：SaintFaceCondition() 恒 true → FaceB 族）。
        "face_stunned": ("base", "FaceStunned"),
        # 复活按压借的那张脸（行为层 face_override = "stun"）：圣徒照旧用自己的
        # 默认表情（闭眼的 FaceB 族），不借晕眩脸；其他蛞蝓猫不变
        "face_press": ("base", "FaceB"),
        "face_dead": ("base", "FaceDead"),  # 死亡脸是标记不是表情，沿用原版
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="saint.json",
    atlas_keys=("base", "msc", "ui", "uimsc"),
    caps=CatCaps(tongue=True, ascension=True),
    stats=replace(DEFAULT_STATS, throwing_skill=0),   # 原版 Saint throwingSkill = 0
    # 慈悲孱弱纯素：偏静易累最耐寒，爱舌钩荡跃
    personality=replace(DEFAULT_PERSONALITY, activity=0.4, stamina=0.8, cold_gain_fac=0.5,
                        sociability=0.3, temper=0.3, crawl_like=0.55,
                        point_like=0.4, bravery=0.35, kindness=0.95,
                        play_style="hop", diet=DIET_VEGETARIAN,
                        hurry=0.35, spear_like=0.15, tongue_curiosity=0.95,
                        risk_tolerance=0.30, patience=0.85,   # 宽容：不冒险，肯等
                        toy_pref={"ceiling_play": 1.4}),
    tuning={
        "temper_ascend_gate": -0.20,          # ≤此值才可超度
    },
    fsm_mount=_fsm_mount,
    wip=False,
)
