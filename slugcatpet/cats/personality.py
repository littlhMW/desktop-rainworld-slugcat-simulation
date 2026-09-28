"""CatPersonality：每种族的原创性格行为层，与 SlugStats 生理层并列。"""
from __future__ import annotations

from dataclasses import dataclass, field

# 食性枚举
DIET_OMNIVORE = "omnivore"
DIET_CARNIVORE = "carnivore"
DIET_VEGETARIAN = "vegetarian"
DIET_SPECIAL = "special"


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
    point_like: float = 0.5        # 0 不爱指指点点 ↔ 1 爱指（性格好的猫少指）
    play_style: str = "sit"        # 玩耍姿态：sit 原地 / hop 边走边跳 / crawl 匍匐着玩
    diet: str = DIET_OMNIVORE
    toy_pref: dict = field(default_factory=dict)   # 空=全 1


DEFAULT_PERSONALITY = CatPersonality()
