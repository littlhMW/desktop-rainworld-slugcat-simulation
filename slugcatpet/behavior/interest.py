# -*- coding: utf-8 -*-
"""兴趣目标抖动：同屏多只猫，别都盯上同一个最近目标。

原版每只生物有自己的 AI 目标与 pathFinder，同种生物不会整齐地扑同一件东西；
桌宠里所有猫共用同一张目标表 + 同一套「最近/最快」打分，于是十只猫会一起冲向
同一个果子。这里给「猫 × 目标」一个**稳定的**个体偏好系数（不是每 tick 乱跳），
让排序错开；再给「已经有同伴盯着」的目标一个让位惩罚。

系数只用来**排序**，不改物理，也不改任何随机流（不调用目标上的 rng）。
"""
from __future__ import annotations


def _cat_id(unit) -> int:
    """每只猫的稳定身份：PetUnit.index（0..9）。"""
    return int(getattr(unit, "index", 0))


def interest_noise(unit, obj, amp: float) -> float:
    """(猫, 目标) → 1±amp 的稳定偏好系数；换猫或换目标就变，同猫同目标恒定。"""
    h = (hash((_cat_id(unit), id(obj))) & 0xFFFF) / 65535.0
    return 1.0 + amp * (2.0 * h - 1.0)


def taken_by_peer(unit, obj) -> bool:
    """这件东西（食物/猎物/玩具）已经被别的猫当成目标了。"""
    for p in getattr(unit, "pets", ()):
        if p is unit:
            continue
        beh = getattr(p, "behavior", None)
        if beh is None:
            continue
        for attr in ("fetch", "flyhunt", "flycatch"):
            sub = getattr(beh, attr, None)
            if sub is not None and getattr(sub, "target", None) is obj:
                return True
    return False


def goal_key(unit, obj, score: float, amp: float, taken_mul: float) -> float:
    """把「耗时/距离」打分加上个体抖动与让位惩罚，供 min()/sort() 排序。"""
    k = score * interest_noise(unit, obj, amp)
    if taken_by_peer(unit, obj):
        k *= taken_mul
    return k
