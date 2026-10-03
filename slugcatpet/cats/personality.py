# -*- coding: utf-8 -*-
"""连续性格模型。

Rain World 的 Slugpup 个体性格可以看成六条 0..1 的轴：同情心、勇气、
活力、焦虑性、攻击性和强势性。项目早期使用了 activity/bravery/kindness
等分散字段；这些字段仍保留作兼容层，但新代码应优先读取 :meth:`trait`。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

# 食性枚举
DIET_OMNIVORE = "omnivore"
DIET_CARNIVORE = "carnivore"
DIET_VEGETARIAN = "vegetarian"
DIET_SPECIAL = "special"
DIET_GOURMAND = "gourmand"

_TRAITS = ("compassion", "courage", "vitality", "anxiety", "aggression", "dominance")
_TRAIT_ALIASES = {"sympathy": "compassion", "energy": "vitality",
                  "nervousness": "anxiety"}

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


@dataclass(frozen=True)
class CatPersonality:
    """族群/个体性格。

    六个 canonical trait 均为 0..1。设为 ``None`` 时从旧兼容字段推导，这使
    存档和已有种族定义无需迁移；只要显式传入任一 canonical trait，就会将
    直接别名（activity、bravery、kindness、temper）同步到 canonical 数值。
    """
    # canonical Slugpup traits
    compassion: float | None = None  # 同情心：更愿意救援/照料生物
    courage: float | None = None     # 勇气：降低焦虑、提高战斗意愿
    vitality: float | None = None    # 活力：玩耍、拾取、活动频率
    anxiety: float | None = None     # 焦虑性：靠近玩家、逃脱和危险物偏好
    aggression: float | None = None  # 攻击性：武器/攻击倾向
    dominance: float | None = None   # 强势性：持有物品、争抢、保持距离

    # 旧字段（公共 API，保留以兼容存档、FSM 和种族原型）
    activity: float = 0.5
    stamina: float = 1.0
    cold_gain_fac: float = 1.0
    sociability: float = 0.5
    swim_zeal: float = 0.5
    temper: float = 0.5
    crawl_like: float = 0.5
    bravery: float = 0.5
    kindness: float = 0.5
    point_like: float = 0.5
    hurry: float = 0.5
    wake_like: float = 0.5
    patience: float = 0.5
    risk_tolerance: float = 0.5
    apologize: bool = True
    spear_like: float = 1.0
    pearl_like: float = 1.0
    tongue_curiosity: float = 0.5
    play_style: str = "sit"
    diet: str = DIET_OMNIVORE
    toy_pref: dict = field(default_factory=dict)

    def __post_init__(self):
        # 旧种族定义只填写旧字段时，先由旧轴得到 canonical 值。
        # canonical 字段默认是 None；只有明确传入任一 canonical 轴时才把
        # 结果同步回旧字段，避免 ``replace(DEFAULT_PERSONALITY, activity=...)``
        # 被误判为新 API。
        # ``DEFAULT_PERSONALITY`` is immutable and therefore its resolved 0.5
        # values are copied by dataclasses.replace. Treat neutral canonical
        # values as unspecified so old role definitions can still override
        # activity/bravery/kindness/temper.
        def _new_axis(name: str) -> bool:
            value = getattr(self, name, None)
            return value is not None and abs(float(value) - 0.5) > 1e-9

        explicit = any(_new_axis(a) for a in _TRAITS)
        comp = _clamp(self.compassion if _new_axis("compassion") else self.kindness)
        cour = _clamp(self.courage if _new_axis("courage") else self.bravery)
        vital = _clamp(self.vitality if _new_axis("vitality") else self.activity)
        aggr = _clamp(self.aggression if _new_axis("aggression") else self.temper)
        anx_default = 0.5 + 0.5 * vital - 0.5 * cour
        anx = _clamp(self.anxiety if _new_axis("anxiety") else anx_default)
        dom_default = (cour + vital + aggr) / 3.0
        dom = _clamp(self.dominance if _new_axis("dominance") else dom_default)
        # 无论是旧种族定义还是新 API，实例上的六个 canonical 字段都保持
        # 具体的 0..1 数值，便于 UI、调试和存档直接读取。
        for name, value in (("compassion", comp), ("courage", cour),
                            ("vitality", vital), ("anxiety", anx),
                            ("aggression", aggr), ("dominance", dom)):
            object.__setattr__(self, name, value)
        # 显式使用新 API 时，让旧 FSM 读取到相同的核心轴；旧原型仍保持
        # 自己的 point_like/patience 等细化值，不被过度覆盖。
        if explicit:
            object.__setattr__(self, "activity", vital)
            object.__setattr__(self, "bravery", cour)
            object.__setattr__(self, "kindness", comp)
            object.__setattr__(self, "temper", aggr)
            object.__setattr__(self, "sociability", _clamp(0.35 + 0.65 * comp))
            object.__setattr__(self, "risk_tolerance", _clamp(0.25 * cour + 0.75 * (1.0 - anx)))
            object.__setattr__(self, "hurry", _clamp(0.25 + 0.75 * dom))
            object.__setattr__(self, "wake_like", _clamp(0.25 + 0.75 * vital))
            object.__setattr__(self, "patience", _clamp(1.0 - anx))

    def trait(self, name: str, default: float = 0.5) -> float:
        """返回任一 canonical 性格轴，保证结果处于 0..1。"""
        name = _TRAIT_ALIASES.get(name, name)
        if name not in _TRAITS:
            raise ValueError(f"unknown personality trait: {name}")
        value = getattr(self, name, None)
        if value is not None:
            return _clamp(value)
        legacy = {
            "compassion": self.kindness,
            "courage": self.bravery,
            "vitality": self.activity,
            "anxiety": 0.5 + 0.5 * self.activity - 0.5 * self.bravery,
            "aggression": self.temper,
            "dominance": (self.bravery + self.activity + self.temper) / 3.0,
        }
        return _clamp(legacy.get(name, default))

    @property
    def traits(self) -> dict[str, float]:
        """适合 UI/调试/存档的六轴快照。"""
        return {name: self.trait(name) for name in _TRAITS}

    def with_traits(self, **traits) -> "CatPersonality":
        """返回一份修改后的性格；输入轴会被夹到 0..1。"""
        traits = {_TRAIT_ALIASES.get(k, k): v for k, v in traits.items()}
        bad = set(traits) - set(_TRAITS)
        if bad:
            raise ValueError("unknown personality traits: " + ", ".join(sorted(bad)))
        return replace(self, **{k: _clamp(v) for k, v in traits.items()})


DEFAULT_PERSONALITY = CatPersonality()

# 六轴个体变异。旧细化字段仍做小幅变异，作为动作层的次级偏好。
INDIV_SIGMA = {
    "compassion": 0.12, "courage": 0.12, "vitality": 0.10,
    "anxiety": 0.12, "aggression": 0.10, "dominance": 0.12,
    "crawl_like": 0.08, "point_like": 0.10, "tongue_curiosity": 0.10,
    "swim_zeal": 0.10,
}


def individualize(pers: CatPersonality, seed: int,
                  sigma: dict | None = None) -> CatPersonality:
    """从原型生成稳定的个体性格（同一 seed 可复现）。"""
    table = INDIV_SIGMA if sigma is None else sigma
    rng = random.Random(int(seed) & 0x7FFFFFFF)
    out = {}
    for ax, sig in table.items():
        base = pers.trait(ax) if ax in _TRAITS else getattr(pers, ax, None)
        if not isinstance(base, (int, float)):
            continue
        d = max(-0.5, min(0.5, rng.gauss(0.0, sig)))
        # Canonical traits 必须严格是 0..1；兼容轴也继续沿用旧的夹取行为。
        if ax in _TRAITS or ax in {"activity", "sociability", "temper", "bravery",
                                   "kindness", "crawl_like", "point_like", "hurry",
                                   "wake_like", "patience", "risk_tolerance", "swim_zeal",
                                   "tongue_curiosity"}:
            out[ax] = _clamp(base + d)
        else:
            out[ax] = base + d
    return replace(pers, **out) if out else pers


__all__ = ["CatPersonality", "DEFAULT_PERSONALITY", "individualize", "DIET_OMNIVORE",
           "DIET_CARNIVORE", "DIET_VEGETARIAN", "DIET_SPECIAL", "DIET_GOURMAND"]
