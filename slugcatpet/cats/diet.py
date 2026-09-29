# -*- coding: utf-8 -*-
"""食性：逐条对照原版反编译。

依据：
  SlugcatStats.cs:327-359  NourishmentOfObjectEaten(slugcat, edible)
  Player.cs:9749-9780      ObjectEaten：==-1 → Stun(60) 并 return
  Player.cs:6812-6830      AddQuarterFood：quarterFoodPoints>3 → 减 4、AddFood(1)
  Player.cs:11815-11859    CanEatMeat / EatMeatOmnivoreGreenList（蜈蚣白名单）
  Player.cs:12075-12084    EatMeatUpdate：美食家/怪猫非蜈蚣尸体每口 2 份（半格）
  SlugcatStats.cs:115-166  SlugcatFoodMeter（各族食物条上限/冬眠阈）

内部单位 = 四分之一食物格（原版 quarterFoodPoints，4 份 = 1 格）。

nourishment(diet, obj) 返回：
    >= 0   营养值（四分之一格）
    -1     不可食且会眩晕（ObjectEaten → Stun(60)）
    -2     完全不吃（没嘴 / 尸体不在本猫食谱里）：不填饱也不眩晕
"""
from __future__ import annotations

from .personality import (DIET_OMNIVORE, DIET_CARNIVORE, DIET_VEGETARIAN,
                          DIET_SPECIAL, DIET_GOURMAND)

# 食物类别
PLANT = "plant"      # 植物性：果子 / 种子 / 黏菌 / 爆米花
PREY = "prey"        # IPlayerEdible 小猎物：蝠蝇(Fly) / 幼年面条蝇(SmallNeedleWorm)
CORPSE = "corpse"    # 非 IPlayerEdible 的尸体：蝉乌贼等，走 CanEatMeat 那条路
KARMA = "karma"      # 业力花：FoodPoints = 0，只填花条
NONE = "none"        # 不是食物：珍珠 / 蜥蜴尸体 / 蛞蝓猫尸体

# 素食不吃、咽下去会当场眩晕的荤食。原版 SlugcatStats.cs:331-334 只列了
# JellyFish / Centipede / Fly / VultureGrub / SmallNeedleWorm / Hazer 六类；
# 用户口径是「圣徒吃肉类会触发眩晕」，所以这里把尸体（CanEatMeat 本来就不放行）
# 一并算进去：都只触发 -1（眩晕、不给食物），不会真的吃下去。
SAINT_STUN_CLASSES = (PREY, CORPSE)


def food_class(obj) -> str:
    """对象属于哪类食物（对象可自带 food_class 类属性覆盖）。"""
    c = getattr(obj, "food_class", None)
    if c:
        return c
    if getattr(obj, "is_karma", False):
        return KARMA
    if not getattr(obj, "is_edible", True):
        return NONE
    return CORPSE if getattr(obj, "is_meat", False) else PLANT


# 红猫/工匠的 4 倍名单（SlugcatStats.cs:344-347）：Centipede / VultureGrub /
# Hazer / EggBugEgg / SmallNeedleWorm / JellyFish。名单外（DangleFruit、Fly…）
# 只按 1 份算 —— 于是「水果和蝠蝇只提供 1/4 格」。
def _red_bonus(obj) -> bool:
    return bool(getattr(obj, "diet_red_bonus", False))


def _food_value(obj) -> int:
    """原版 IPlayerEdible.FoodPoints（本作对象用 food_value，缺省 1）。"""
    try:
        v = int(getattr(obj, "food_value", 1) or 0)
    except (TypeError, ValueError):
        v = 1
    return max(0, v)


def nourishment(diet, obj) -> int:
    """这一口（整只）能吃到多少「四分之一格」。"""
    cls = food_class(obj)
    if cls == NONE:
        return -2
    if cls == KARMA:
        return 0                       # FoodPoints = 0
    fv = _food_value(obj)
    if diet == DIET_SPECIAL:
        return -2                      # 矛大师没有嘴（Player.cs:11826 直接 false）
    if diet == DIET_VEGETARIAN:
        if cls in SAINT_STUN_CLASSES:
            return -1                  # 圣徒吃荤 → Stun(60)
        if cls == PLANT:
            return 4 * fv
        return -2                      # 尸体：CanEatMeat 对圣徒恒 false
    if cls == PLANT or cls == PREY:
        # 红猫/工匠：名单里的东西照给 4 倍，名单外只给 1 份
        # （水果、蝠蝇 = 1/4 格；幼面条蝇 = 4×2 = 2 格）
        if diet == DIET_CARNIVORE and not _red_bonus(obj):
            return fv
        return 4 * fv
    # CORPSE
    if diet == DIET_CARNIVORE:
        return 4 * fv                  # 每口 AddFood(1)
    if diet == DIET_GOURMAND:
        return 2 * fv                  # 非蜈蚣尸体每口 AddQuarterFood()*2
    return -2                          # 杂食/素食：CanEatMeat 不放行


def edible(diet, obj) -> bool:
    """这猫会不会把它当食物（营养 >= 0）。"""
    return nourishment(diet, obj) >= 0


def stuns(diet, obj) -> bool:
    """吃下去会当场眩晕（原版 ObjectEaten 的 -1 分支）。"""
    return nourishment(diet, obj) == -1


def fetchable(diet, obj) -> bool:
    """能不能进「取食」候选：不能吃的食物剔除；非食物（珍珠/业力花）照旧保留。"""
    cls = food_class(obj)
    if cls in (PLANT, PREY, CORPSE):
        return edible(diet, obj)
    return True


def hunts_meat(diet) -> bool:
    """会不会主动猎杀活物（原版 CanEatMeat 的荤食名单）。"""
    return diet not in (DIET_VEGETARIAN, DIET_SPECIAL)
