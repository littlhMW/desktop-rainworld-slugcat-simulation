# -*- coding: utf-8 -*-
"""动态关系：静态基线 + 个体记忆 + 近期事件 + 情境 → 每 tick 的实时关系。

原版关系不是一张常量表：LizardAI / ScavengerAI 都拿 StaticRelationship
（物种之间的基线）叠加这只个体亲身经历过的事件，算出此刻的
DynamicRelationship，再交给 Utility 决定下一步。

桌宠过去只有零散的 _grudge（被抢东西记住一段时间）和拾荒者的 like0。
这里把「谁对谁怎么样」统一成一条关系记录：

    base        物种 / 角色基线（静态，进来就定死）
    like        长期好感（原版 like）
    temp_like   短期情绪（原版 tempLike）：事件拉低，随时间回中间
    fear        怕它
    resentment  记恨它（被抢、被打）
    affinity    亲近它（被救、被喂、被送礼）
    respect     敬它（被它警告 / 被它救过）
    dominance   支配度

每条关系每 tick 按 DECAY 往基线衰减 —— 这就是「关系与记忆衰减」：没有新事件
时短期情绪几秒内散掉，长期好感慢慢回到基线，不会永久记仇。
"""
from __future__ import annotations

import math
import weakref

from . import events as EV

# 每 tick 乘一次的衰减率（40 tick = 1 秒）
DECAY = {
    "like": 0.99985,        # 长期好感：几分钟才回基线
    "temp_like": 0.99860,   # 短期情绪：几秒散掉
    "fear": 0.99820,
    "resentment": 0.99920,
    "affinity": 0.99940,
    "respect": 0.99950,
}
NEUTRAL_LIKE = 0.5          # 好感中性值
TEMP_MID = 1.0              # temp_like 中间值（原版从 1.0 起算）
MEMORY_TICKS = 7200         # 完全没有互动的旧关系多久清一次（约 3 分钟）
MAX_RELATIONS = 32          # 一只生物最多记多少条关系
WITNESS_SCALE = 0.40        # 目击者受到的关系冲击 = 当事人的这个比例

# 事件 → 关系增减。值是一串 (关系名, 对象角色, 系数)，系数再乘事件强度。
EVENT_EFFECTS = {
    EV.OBJECT_TAKEN: (("resentment", "subj", 0.35),
                      ("temp_like", "subj", -0.30),
                      ("affinity", "subj", -0.08)),
    EV.CREATURE_HURT: (("fear", "subj", 0.30),
                       ("resentment", "subj", 0.40),
                       ("temp_like", "subj", -0.55)),
    EV.CREATURE_KILLED: (("fear", "subj", 0.45),
                         ("resentment", "subj", 0.70),
                         ("temp_like", "subj", -1.00)),
    EV.CREATURE_THREATENED: (("fear", "subj", 0.20),
                             ("temp_like", "subj", -0.25)),
    EV.CREATURE_RESCUED: (("affinity", "subj", 0.60),
                          ("like", "subj", 0.15),
                          ("respect", "subj", 0.25)),
    EV.CREATURE_HELPED: (("affinity", "subj", 0.40),
                         ("like", "subj", 0.10)),
    EV.CREATURE_WARNED: (("respect", "subj", 0.15),
                         ("fear", "subj", 0.10)),
    EV.GESTURE_SCOLDED: (("resentment", "subj", 0.25),
                         ("temp_like", "subj", -0.20)),
    EV.GESTURE_POINTED: (("temp_like", "subj", 0.05),),
    EV.GESTURE_ANSWERED: (("affinity", "subj", 0.10),),
    EV.CREATURE_BLOCKED: (("resentment", "subj", 0.12),),
    EV.OBJECT_DROPPED: (("temp_like", "subj", 0.04),),
    EV.TRADE_COMPLETED: (("affinity", "subj", 0.35),
                         ("like", "subj", 0.20),
                         ("respect", "subj", 0.15)),
}


def _actor(event, role):
    if role == "subj":
        return event.subject
    if role == "obj":
        return event.obj
    return event.other


class Relation:
    """一只生物对另一只生物的实时关系。"""

    __slots__ = ("other", "base", "like", "temp_like", "fear", "resentment",
                 "affinity", "respect", "dominance", "tick")

    def __init__(self, other, base=NEUTRAL_LIKE, tick=0):
        self.other = other
        self.base = float(base)
        self.like = float(base)
        self.temp_like = TEMP_MID
        self.fear = 0.0
        self.resentment = 0.0
        self.affinity = 0.0
        self.respect = 0.0
        self.dominance = 0.5
        self.tick = int(tick)

    @property
    def value(self) -> float:
        """综合好感 0..1（Utility 用；中性 = 0.5）。"""
        v = (self.like + 0.5 * (self.temp_like - TEMP_MID)
             + 0.5 * self.affinity - 0.6 * self.resentment
             - 0.4 * self.fear + 0.2 * self.respect)
        return min(1.0, max(0.0, v))

    @property
    def hostility(self) -> float:
        """敌意 0..1：够高就该动手了。"""
        v = (0.9 * self.resentment
             + 0.6 * max(0.0, NEUTRAL_LIKE - self.like)
             + 0.3 * self.fear
             - 0.5 * self.affinity - 0.3 * self.respect)
        return min(1.0, max(0.0, v))

    @property
    def trust(self) -> float:
        """可依赖程度 0..1：好感高、又不怕它。"""
        return min(1.0, max(0.0, self.value - 0.5 * self.fear))

    def __repr__(self):
        return ("Relation(%s, like=%.2f temp=%.2f fear=%.2f res=%.2f aff=%.2f)"
                % (type(self.other).__name__, self.like, self.temp_like,
                   self.fear, self.resentment, self.affinity))


class Relations:
    """一只生物的关系表：记事件、按 tick 衰减、给 Utility 提供偏置。"""

    __slots__ = ("owner", "_map", "tick")

    def __init__(self, owner=None):
        self.owner = owner
        self._map = {}          # id(other) → Relation
        self.tick = 0

    # ── 取 ──
    def get(self, other, base=NEUTRAL_LIKE) -> Relation:
        if other is None:
            return Relation(None, base, self.tick)
        key = id(other)
        r = self._map.get(key)
        if r is None or r.other is not other:
            if len(self._map) >= MAX_RELATIONS:
                self._evict()
            r = Relation(other, base, self.tick)
            self._map[key] = r
        return r

    def _evict(self) -> None:
        key = min(self._map, key=lambda k: self._map[k].tick)
        del self._map[key]

    def __len__(self):
        return len(self._map)

    def others(self):
        return [r.other for r in self._map.values() if r.other is not None]

    # ── 记 ──
    def note(self, event, scale=1.0) -> None:
        """把一条事件记成关系变化（只记这次事件涉及的角色）。"""
        eff = EVENT_EFFECTS.get(event.kind)
        if not eff:
            return
        amount0 = max(0.0, float(event.intensity)) * float(scale)
        for name, role, k in eff:
            who = _actor(event, role)
            if who is None or who is self.owner:
                continue
            r = self.get(who)
            r.tick = int(event.tick)
            amount = k * amount0
            cur = getattr(r, name)
            setattr(r, name, min(1.0, max(0.0, cur + amount)))

    def note_toward(self, other, name, amount, tick=None) -> None:
        """直接改一条关系（给「被喂」「被让位」这种没有事件对象的场合用）。"""
        if other is None or other is self.owner:
            return
        r = self.get(other)
        if tick is not None:
            r.tick = int(tick)
        cur = getattr(r, name, None)
        if cur is None:
            return
        if name == "temp_like":
            r.temp_like = max(0.0, cur + amount)
        else:
            setattr(r, name, min(1.0, max(0.0, cur + amount)))

    # ── 衰减 ──
    def decay(self, tick=None) -> None:
        """每 tick 衰减一次；长期没有互动的旧关系清掉。"""
        if tick is not None:
            self.tick = int(tick)
        t = self.tick
        dead = []
        for key, r in self._map.items():
            r.like = r.base + (r.like - r.base) * DECAY["like"]
            r.temp_like = TEMP_MID + (r.temp_like - TEMP_MID) * DECAY["temp_like"]
            for name in ("fear", "resentment", "affinity", "respect"):
                setattr(r, name, getattr(r, name) * DECAY[name])
            if t - r.tick > MEMORY_TICKS:
                dead.append(key)
        for key in dead:
            del self._map[key]

    # ── 查询 ──
    def value_of(self, other) -> float:
        return self.get(other).value

    def hostility_to(self, other) -> float:
        return self.get(other).hostility

    def resents(self, other) -> float:
        return self.get(other).resentment

    def fears(self, other) -> float:
        return self.get(other).fear

    def affinity_to(self, other) -> float:
        return self.get(other).affinity

    def respects(self, other) -> float:
        return self.get(other).respect

    def bias(self, action: str, other) -> float:
        """Utility 偏置：关系决定「愿不愿意为它做这件事」。"""
        if other is None:
            return 0.0
        r = self.get(other)
        if action in ("pet", "pat"):
            return 0.6 * r.affinity + 0.4 * max(0.0, r.value - NEUTRAL_LIKE)
        if action == "scold":
            return 0.9 * r.resentment + 0.4 * max(0.0, NEUTRAL_LIKE - r.like)
        if action == "point":
            return 0.5 * r.resentment + 0.2 * r.affinity
        if action == "revive":
            return 0.7 * r.affinity + 0.3 * max(0.0, r.value - NEUTRAL_LIKE)
        if action == "follow":
            return 0.5 * r.affinity
        if action in ("challenge", "fight"):
            return 1.0 * r.hostility
        if action == "trade":
            return 0.4 * r.value
        return 0.0


_RELS = weakref.WeakKeyDictionary()


def relations_for(unit) -> Relations:
    """取这只生物的关系表。

    优先用它自己身上的 `rel`（__slots__ 的生物在 __init__ 里就建好一份），
    其次按对象缓存（猫这种普通对象），最后退化成一次性表 —— 无论如何不抛。
    """
    r = getattr(unit, "rel", None)
    if isinstance(r, Relations):
        return r
    try:
        r = _RELS.get(unit)
    except TypeError:              # 不可弱引用：只能退化成一次性表
        return Relations(unit)
    if r is None:
        r = Relations(unit)
        try:
            _RELS[unit] = r
        except TypeError:
            return Relations(unit)
    return r
