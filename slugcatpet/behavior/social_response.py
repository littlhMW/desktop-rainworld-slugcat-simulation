# -*- coding: utf-8 -*-
"""社会反应选型：同一件事，不同性格的猫给出不同反应。

原版拾荒者的 aggression / bravery / dominance / energy / nervousness /
sympathy 六个个体属性会细腻地改变「看到同伴被打」「自己的东西被拿走」这类
场面的处理方式；蛞蝓猫的社交动作（指向 / 指指点点 / 抚摸 / 拍拍 / 匍匐）在
原版里也是同一套身体语言。桌宠过去的写法是「被抢了 → 一定去指指点点」，
于是十只猫只有一种反应。

这里把反应做成一次带权选择：

    ignore / point / scold / follow / replace_target / challenge / ask /
    trade / observe

权重来自三处：事件的种类与强度、双方的关系（relationship.py）、猫的性格。

    高 temper + 低 patience      → scold / challenge
    高 kindness + 高 patience    → ignore（自己再找）
    高 sociability               → observe（留下来围观）
    高 point_like                → point / ask
    低 dominance / 高 fear       → ignore

返回 (反应名, 强度 0..1)；调用方只负责把它演出来，不做二次判断。
"""
from __future__ import annotations

from dataclasses import dataclass

from . import events as EV

RESPONSES = ("ignore", "point", "scold", "follow", "replace_target",
             "challenge", "ask", "trade", "observe")

# 事件 → 九种反应的基础分（与性格无关的那部分）
_BASE = {
    EV.OBJECT_TAKEN: dict(ignore=0.30, point=0.35, scold=0.55, follow=0.30,
                          replace_target=0.35, challenge=0.10, ask=0.12,
                          trade=0.0, observe=0.25),
    EV.OBJECT_CLAIMED: dict(ignore=0.50, point=0.25, scold=0.10, follow=0.20,
                            replace_target=0.30, challenge=0.05, ask=0.05,
                            trade=0.0, observe=0.20),
    EV.GESTURE_SCOLDED: dict(ignore=0.45, point=0.30, scold=0.55, follow=0.15,
                             replace_target=0.0, challenge=0.20, ask=0.10,
                             trade=0.0, observe=0.35),
    EV.GESTURE_POINTED: dict(ignore=0.45, point=0.35, scold=0.10, follow=0.25,
                             replace_target=0.0, challenge=0.0, ask=0.30,
                             trade=0.0, observe=0.30),
    EV.CREATURE_THREATENED: dict(ignore=0.40, point=0.35, scold=0.10,
                                 follow=0.10, replace_target=0.0, challenge=0.30,
                                 ask=0.05, trade=0.0, observe=0.30),
    EV.CREATURE_HURT: dict(ignore=0.30, point=0.25, scold=0.20, follow=0.10,
                           replace_target=0.05, challenge=0.45, ask=0.0,
                           trade=0.0, observe=0.40),
    EV.CREATURE_KILLED: dict(ignore=0.20, point=0.30, scold=0.20, follow=0.05,
                             replace_target=0.0, challenge=0.55, ask=0.0,
                             trade=0.0, observe=0.35),
    EV.CREATURE_BLOCKED: dict(ignore=0.40, point=0.35, scold=0.35, follow=0.10,
                              replace_target=0.20, challenge=0.15, ask=0.05,
                              trade=0.0, observe=0.15),
    EV.CREATURE_RESCUED: dict(ignore=0.35, point=0.30, scold=0.0, follow=0.30,
                              replace_target=0.0, challenge=0.0, ask=0.0,
                              trade=0.0, observe=0.45),
    EV.CREATURE_HELPED: dict(ignore=0.40, point=0.25, scold=0.0, follow=0.25,
                             replace_target=0.0, challenge=0.0, ask=0.10,
                             trade=0.0, observe=0.40),
    EV.CREATURE_WARNED: dict(ignore=0.35, point=0.30, scold=0.0, follow=0.20,
                             replace_target=0.0, challenge=0.0, ask=0.10,
                             trade=0.0, observe=0.40),
    EV.TRADE_COMPLETED: dict(ignore=0.40, point=0.30, scold=0.0, follow=0.10,
                             replace_target=0.0, challenge=0.0, ask=0.25,
                             trade=0.35, observe=0.45),
}
_BASE_DEFAULT = dict(ignore=0.50, point=0.20, scold=0.15, follow=0.15,
                     replace_target=0.0, challenge=0.10, ask=0.05,
                     trade=0.0, observe=0.25)

# 反应 × 性格轴权重：轴值 0..1，系数按 (轴值 - 0.5) 乘进去
_AXIS = {
    "scold": {"temper": 0.75, "point_like": 0.45, "patience": -0.40},
    "point": {"point_like": 0.80, "sociability": 0.30, "temper": 0.15},
    "challenge": {"temper": 0.55, "bravery": 0.65, "patience": -0.30,
                  "kindness": -0.15},
    "follow": {"activity": 0.45, "sociability": 0.35, "hurry": 0.20},
    "observe": {"sociability": 0.70, "activity": 0.20, "patience": 0.25},
    "ignore": {"patience": 0.55, "kindness": 0.25, "risk_tolerance": -0.25},
    "replace_target": {"patience": 0.25, "activity": 0.30, "hurry": 0.35},
    "ask": {"sociability": 0.45, "point_like": 0.40, "bravery": -0.25},
    "trade": {"sociability": 0.40, "patience": 0.30},
}


@dataclass(frozen=True)
class SocialContext:
    """做反应判断时能看到的当下情境。"""
    busy: float = 0.0        # 0..1：手里正忙着（拿着东西 / 在别的社交里）
    threat: float = 0.0      # 0..1：附近有威胁
    far: float = 0.0         # 0..1：离当事人太远
    crowd: float = 0.0       # 0..1：这一带已经挤了多少人


def _axis(pers, name, default=0.5) -> float:
    if pers is None:
        return default
    try:
        return min(1.0, max(0.0, float(getattr(pers, name, default))))
    except (TypeError, ValueError):
        return default


def scores(event, pers=None, rel=None, ctx=None) -> dict:
    """这次事件的九种反应各值多少分（未归一）。"""
    base = _BASE.get(event.kind, _BASE_DEFAULT)
    out = {}
    for r in RESPONSES:
        s = base.get(r, 0.0)
        for ax, k in _AXIS.get(r, {}).items():
            s += k * (_axis(pers, ax) - 0.5)
        if rel is not None and event.subject is not None:
            s += 0.5 * rel.bias(r, event.subject)
        out[r] = s
    if ctx is not None:
        # 手上有事 / 有威胁：少惹事
        for r in ("scold", "point", "challenge", "observe", "ask"):
            out[r] -= 0.6 * ctx.busy + 0.8 * ctx.threat
        for r in ("ignore", "replace_target"):
            out[r] += 0.5 * ctx.threat
        out["observe"] += 0.3 * ctx.crowd          # 已经围了一圈 → 更想凑热闹
        out["challenge"] -= 0.8 * ctx.far
        out["scold"] -= 0.5 * ctx.far
    return {k: max(0.0, v) for k, v in out.items()}


def choose(event, pers=None, rel=None, ctx=None, rng=None):
    """选一个反应；返回 (反应名, 强度 0..1)。给了 rng 才带个体抖动。"""
    sc = scores(event, pers, rel, ctx)
    if rng is not None:
        for k in list(sc):
            sc[k] *= 0.85 + 0.30 * rng.random()
    name = max(RESPONSES, key=lambda k: (sc[k], k))
    total = sum(sc.values())
    strength = 0.0 if total <= 0.0 else sc[name] / total
    strength = min(1.0, max(0.0, float(event.intensity)) * strength * 2.5)
    return name, strength


# 这些事件里「动手的人」不是反应对象 —— 被指/被指责的是挨着的那个人
_TARGET_IS_OBJ = frozenset((EV.GESTURE_SCOLDED, EV.GESTURE_POINTED))


def target_of(event):
    """这条事件该对着谁反应 / 记账。

    打人、抢东西：对着**做这件事的人**（subject）。
    指人、指责人：对着**被指的倒霉蛋**（obj）—— 旁边看见的猫跟着起哄，
    骂的是同一个小偷，而不是骂那个先开口的同伴。
    """
    if event.kind in _TARGET_IS_OBJ and event.obj is not None:
        return event.obj
    return event.subject


def is_gesture(response: str) -> bool:
    """这个反应要不要「演」出来（指向 / 指指点点 / 围观）。"""
    return response in ("point", "scold", "observe", "ask")


def social_kind(response: str) -> str:
    """反应 → 社交动作词表键（见 behavior/social.py）。"""
    if response == "scold":
        return "scold"
    if response == "ask":
        return "point"
    return "point"
