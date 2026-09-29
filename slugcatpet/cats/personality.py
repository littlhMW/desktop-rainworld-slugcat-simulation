# -*- coding: utf-8 -*-
"""CatPersonality：每种族的原创性格行为层，与 SlugStats 生理层并列。"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

# 食性枚举
DIET_OMNIVORE = "omnivore"
DIET_CARNIVORE = "carnivore"
DIET_VEGETARIAN = "vegetarian"
DIET_SPECIAL = "special"
DIET_GOURMAND = "gourmand"     # 美食家/怪猫：杂食广谱，尸体半格


@dataclass(frozen=True)
class CatPersonality:
    """一种族性格：连续轴 + diet 枚举 + toy_pref 乘子，中性=0.5/1.0。"""
    activity: float = 0.5
    stamina: float = 1.0           # EN_DRAIN÷stamina，低反而更快累
    cold_gain_fac: float = 1.0
    sociability: float = 0.5
    swim_zeal: float = 0.5         # ≤0.5 视为中性
    temper: float = 0.5            # 0 温顺 ↔ 1 暴躁（玩东西会不会甩出去、多远迎战）
    crawl_like: float = 0.5        # 0 讨厌趴着 ↔ 1 爱匍匐（低的宁死也不趴）
    bravery: float = 0.5           # 0 怯懦 ↔ 1 勇敢（恐惧时敢迎战、敢拔敌人身上的矛）
    kindness: float = 0.5          # 0 自私 ↔ 1 善良（恐惧时先救同伴）
    point_like: float = 0.5        # 0 不爱指指点点 ↔ 1 爱指（性格好的猫少指）
    hurry: float = 0.5             # 0 不急 ↔ 1 赶时间（被挡时先跳走，回头再指）
    wake_like: float = 0.5         # 0 不吵人 ↔ 1 爱把睡着的同伴摇醒
    patience: float = 0.5          # 0 急躁 ↔ 1 有耐心（等不到就换目标 / 堵塞时先等还是先动手）
    risk_tolerance: float = 0.5    # 0 怕冒险 ↔ 1 敢冒险（路线打分里「宁可绕路也别跳」的轴）
    apologize: bool = True         # 误伤同伴会不会认错（False=理直气壮，永不道歉）
    spear_like: float = 1.0        # 用矛意愿乘子（0=不肯碰矛）
    pearl_like: float = 1.0        # 对珍珠的偏爱乘子（>1 会专门去拣来拿着）
    tongue_curiosity: float = 0.5   # 0 不爱用舌头 ↔ 1 爱用（圣徒的舌钩/逗弄/吊顶共用这一轴）
    play_style: str = "sit"        # 玩耍姿态：sit 原地 / hop 边走边跳 / crawl 匍匐着玩
    diet: str = DIET_OMNIVORE
    toy_pref: dict = field(default_factory=dict)   # 空=全 1


DEFAULT_PERSONALITY = CatPersonality()

# 个体偏移幅度：同种族每只猫在原型基线上小幅偏移（原版 AbstractCreature.personality
# 的 IndividualVariation：同一物种里也不是一个模子刻出来的）。只列行为轴 ——
# diet / play_style / apologize / spear_like / pearl_like 这类离散或资源轴不参与。
INDIV_SIGMA = {
    "activity": 0.10, "sociability": 0.12, "temper": 0.10, "bravery": 0.12,
    "kindness": 0.12, "patience": 0.12, "risk_tolerance": 0.12,
    "crawl_like": 0.08, "point_like": 0.10, "hurry": 0.10, "wake_like": 0.10,
    "swim_zeal": 0.10, "tongue_curiosity": 0.10,
}


def individualize(pers: CatPersonality, seed: int,
                  sigma: dict | None = None) -> CatPersonality:
    """原型基线上加个体偏移：同种族的猫不再完全一样（原版 IndividualVariation）。

    偏移用固定种子取材，夹在 ±0.5 内再落回 0..1，所以：
    - 同一个 seed 永远得到同一只猫（同种子可复现）；
    - 不会把「讨厌匍匐」的猫偏移成「热爱匍匐」（幅度只有 σ 量级）。
    """
    table = INDIV_SIGMA if sigma is None else sigma
    rng = random.Random(int(seed) & 0x7FFFFFFF)
    out = {}
    for ax, sig in table.items():
        base = getattr(pers, ax, None)
        if not isinstance(base, (int, float)):
            continue
        d = rng.gauss(0.0, sig)
        d = -0.5 if d < -0.5 else (0.5 if d > 0.5 else d)
        out[ax] = min(1.0, max(0.0, float(base) + d))
    return replace(pers, **out) if out else pers
