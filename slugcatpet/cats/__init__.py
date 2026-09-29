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

# 幼崽（Slugpup）不是常规蛞蛓猫：只能从「生物生成」里放，不进「添加蛞蛓猫」选单。
PUP_VARIANT = "slugpup"

# 已实装种族（食性/食条/数值全部按反编译；wip=True 的只是外观差异待后续）
REGISTRY: dict[str, CatDef] = {
    "saint": SAINT_DEF,
    "rivulet": RIVULET_DEF,
    "survivor": SURVIVOR_DEF,
    "monk": MONK_DEF,
    "hunter": HUNTER_DEF,
    "artificer": ARTIFICER_DEF,
    "gourmand": GOURMAND_DEF,
    "spearmaster": SPEARMASTER_DEF,
    "inv": INV_DEF,
    "watcher": WATCHER_DEF,
    "slugpup": SLUGPUP_DEF,
}


def pickable_variants() -> tuple:
    """「添加蛞蛓猫」列表里可选的种族（幼崽走生物生成）。"""
    return tuple(k for k in REGISTRY if k != PUP_VARIANT)


def get(variant) -> CatDef:
    """按 variant 取定义；未知回落 saint。"""
    d = REGISTRY.get(variant)
    return d if d is not None else REGISTRY[DEFAULT_VARIANT]


def default_def() -> CatDef:
    return REGISTRY[DEFAULT_VARIANT]
