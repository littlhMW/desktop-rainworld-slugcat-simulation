"""猫种族注册表：variant key → CatDef；未知 variant 回落 saint。"""
from __future__ import annotations

from .artificer import ARTIFICER_DEF
from .base import CatDef
from .gourmand import GOURMAND_DEF
from .hunter import HUNTER_DEF
from .inv import INV_DEF
from .monk import MONK_DEF
from .rivulet import RIVULET_DEF
from .saint import SAINT_DEF
from .slugpup import SLUGPUP_DEF
from .spearmaster import SPEARMASTER_DEF
from .survivor import SURVIVOR_DEF
from .watcher import WATCHER_DEF

DEFAULT_VARIANT = "saint"

# 幼崽（Slugpup）和旧存档的 inv 变体不在「添加蛞蛓猫」选单中。
PUP_VARIANT = "slugpup"

# 已实装种族（食性/食条/数值全部按反编译；wip=True 的只是外观差异待后续）
REGISTRY: dict[str, CatDef] = {
    "monk": MONK_DEF,
    "survivor": SURVIVOR_DEF,
    "hunter": HUNTER_DEF,
    "gourmand": GOURMAND_DEF,
    "artificer": ARTIFICER_DEF,
    "rivulet": RIVULET_DEF,
    "spearmaster": SPEARMASTER_DEF,
    "saint": SAINT_DEF,
    "watcher": WATCHER_DEF,
    # Internal/legacy variant retained for saved pets; it is filtered from
    # pickable_variants() and therefore does not appear in the chooser.
    "inv": INV_DEF,
    "slugpup": SLUGPUP_DEF,
}


def pickable_variants() -> tuple:
    """「添加蛞蛓猫」列表里可选的种族（幼崽走生物生成）。"""
    return tuple(k for k in REGISTRY if k not in (PUP_VARIANT, "inv"))


def display_order(pets) -> list:
    """按角色选择顺序列出已有蛞蝓猫，同种角色保持加入顺序。"""
    rank = {variant: i for i, variant in enumerate(pickable_variants())}
    return sorted(pets, key=lambda pet: rank.get(pet.variant, len(rank)))


def get(variant) -> CatDef:
    """按 variant 取定义；未知回落 saint。"""
    d = REGISTRY.get(variant)
    return d if d is not None else REGISTRY[DEFAULT_VARIANT]


def default_def() -> CatDef:
    return REGISTRY[DEFAULT_VARIANT]
