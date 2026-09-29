# -*- coding: utf-8 -*-
"""兴趣目标打分：个体稳定偏好 + 认领让位 + 拥挤成本 + 失败黑名单。

原版每只生物有自己的 AI 目标与 pathFinder，同种生物不会整齐地扑同一件东西；
桌宠里所有猫共用同一张目标表 + 同一套「最近 / 最快」打分，于是十只猫会一起
冲向同一个果子。这里给「猫 × 目标」一个**稳定的**个体偏好系数（不是每 tick
乱跳），再叠上认领板的三项：别人正认领 → 让位、旁边围着猫太多 → 加成本、
刚试过拿不到 → 短期不再选（见 board.py）。

系数只用来**排序**，不改物理，也不改任何随机流（不调用目标上的 rng）。
"""
from __future__ import annotations

from .board import BLACKLIST_MUL, CROWD_W, SLOT_FULL_MUL, board_for


def _cat_id(unit) -> int:
    """每只猫的稳定身份：PetUnit.index（0..9）。"""
    return int(getattr(unit, "index", 0) or 0)


def _obj_uid(obj) -> int:
    """目标的稳定身份。

    目标都是 __slots__ 的对象（挂不上属性，仓库里同样用 id 字典，见
    items.py 的 cd.pop(id(...)) 注释）。id 在对象存活期间是稳定的，正好够
    这次会话的排序用。
    """
    return id(obj)


def _mix(a: int, b: int) -> float:
    """把两个整数稳定地混成 0..1。

    不能用内置 hash()：字符串/元组的 hash 带进程随机盐（PYTHONHASHSEED），
    同一只猫同一个目标每次启动得到的偏好都不一样。这里用固定混合器。
    """
    h = (a * 0x9E3779B1 ^ b * 0x85EBCA77) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 0x2545F491) & 0xFFFFFFFF
    h ^= h >> 13
    return (h & 0xFFFFFF) / float(0xFFFFFF)


def interest_noise(unit, obj, amp: float) -> float:
    """(猫, 目标) → 1±amp 的稳定偏好系数；换猫或换目标就变，同猫同目标恒定。"""
    h = _mix(_cat_id(unit), _obj_uid(obj))
    return 1.0 + amp * (2.0 * h - 1.0)


def crowd_cost(unit, obj) -> float:
    """目标旁边围着几只别的猫（指数衰减，已封顶）；用来把猫自然摊开。"""
    return board_for(unit).crowd(unit, obj)


def taken_by_peer(unit, obj) -> bool:
    """这件东西（食物/猎物/玩具/正在救的尸体…）已经被别的猫当成目标了。"""
    if board_for(unit).taken(unit, obj):
        return True
    # 兼容：认领板没覆盖到的控制器（或测试里传的是裸 window）
    for p in _others(unit):
        beh = getattr(p, "behavior", None)
        if beh is None:
            continue
        for attr in ("fetch", "flyhunt", "flycatch"):
            sub = getattr(beh, attr, None)
            if sub is not None and getattr(sub, "target", None) is obj:
                return True
    return False


def _others(unit):
    me_win = getattr(unit, "window", None)
    for p in getattr(unit, "pets", ()):
        if p is unit:
            continue
        if me_win is None and getattr(p, "window", None) is unit:
            continue
        yield p


def goal_key(unit, obj, score: float, amp: float, taken_mul: float,
             crowd_w: float = CROWD_W, kind: str | None = None) -> float:
    """把「耗时/距离」打分加上个体抖动、让位惩罚、拥挤成本、位形槽与黑名单。

    `kind` 给出目标类型（eat / hunt / catch / play / help…）时再看它的位形槽
    还空不空：满了就乘 SLOT_FULL_MUL。**是成本不是禁止** —— 没别的选择时
    照样会去，所以不会因为「大家都满了」而僵住。
    """
    k = score * interest_noise(unit, obj, amp)
    if taken_by_peer(unit, obj):
        k *= taken_mul
    k *= 1.0 + crowd_w * crowd_cost(unit, obj)
    bd = board_for(unit)
    if kind is not None and bd.full(obj, kind, skip=unit):
        k *= SLOT_FULL_MUL
    if bd.blacklisted(unit, obj):
        k *= BLACKLIST_MUL
    return k
