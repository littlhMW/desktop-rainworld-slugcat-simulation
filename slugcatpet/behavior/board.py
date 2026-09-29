# -*- coding: utf-8 -*-
"""目标认领板（TaskBoard 的最小可用版）：认领 / 拥挤成本 / 失败黑名单。

原版每只生物有自己的 AI 目标与 pathFinder，抢同一件东西时靠各自的 utility
与个体关系自然分流；桌宠里十只猫共用一张「最近 / 最快」表，于是常常一起冲
向同一个果子。这里给「猫 × 目标」加一层轻量租约：

    认领（读当前状态得出）→ 有进展就自动续约 → 卡住 / 目标没了 → 释放

再配两个信号：**拥挤成本**（目标旁边还围着几只猫）和**失败黑名单**（刚试过
拿不到的东西短期内不再选）。全部只参与**排序**，不改物理、不碰任何随机流。

认领不额外登记：直接读猫此刻的状态（FetchFruit 的 fetch.target、FightThreat
的 _fight_target、Socialize 的救援目标……），状态一走开认领就自然消失 ——
没有「忘记释放」这种可能。
"""
from __future__ import annotations

import math
import weakref

CLAIM_TICKS = 150          # 一次认领的租约时长（期间主人每 tick 续约）
CLAIM_STALL_PX = 3.0       # 一 tick 位置变化小于它 = 这一 tick 没挪动
CLAIM_STALL_TICKS = 80     # 连续这么久没挪动 → 记一次「卡住」
CLAIM_DROP_STALLS = 2      # 卡住这么多次 → 把目标拉黑
BLACKLIST_TICKS = 420      # 拉黑时长（≈10 秒）
BLACKLIST_MUL = 4.0        # 拉黑目标在排序里乘这个（不是绝对禁止，防死锁）
CROWD_SCALE = 110.0        # 拥挤成本衰减尺度（像素）
CROWD_W = 0.45             # 拥挤成本权重（乘到「预估耗时」上）
CROWD_MAX = 2.0            # 单目标拥挤成本封顶

# 状态 → (取目标的对象属性, 认领类型)。取到目标就算认领，取不到就释放。
_OBSERVE = (
    ("FetchFruit", "fetch", "target", "eat"),
    ("HuntFly", "flyhunt", "target", "hunt"),
    ("CatchFly", "flycatch", "target", "catch"),
    ("FightThreat", None, "_fight_target", "fight"),
    ("HelpFeed", None, "_help_target", "help"),
)


class Claim:
    __slots__ = ("owner", "obj", "kind", "until", "lx", "ly", "stall", "stalls")

    def __init__(self, owner, obj, kind, tick):
        self.owner = owner
        self.obj = obj
        self.kind = kind
        self.until = tick + CLAIM_TICKS
        self.lx = self.ly = None
        self.stall = 0
        self.stalls = 0


class Board:
    """一张认领板（每个窗口一张）。"""

    def __init__(self):
        self._claims = {}      # 主人 id → Claim
        self._black = {}       # (主人 id, 目标 id) → (目标, 到期 tick)
        self.tick = 0

    # ── 认领 ──
    def sync(self, unit, tick=None) -> None:
        """把这只猫此刻的「正事目标」登记成认领（无正事则注销）。"""
        if tick is not None:
            self.tick = tick
        tick = self.tick
        beh = getattr(unit, "behavior", None)
        obj, kind = _target_of(beh)
        key = id(unit)
        if obj is None:
            self._claims.pop(key, None)
            self._sweep()
            return
        c = self._claims.get(key)
        if c is None or c.obj is not obj or c.kind != kind:
            c = Claim(unit, obj, kind, tick)
            self._claims[key] = c
        else:
            c.until = tick + CLAIM_TICKS
            self._progress(unit, c, tick)
        self._sweep()

    def _progress(self, unit, c, tick) -> None:
        """位置长时间不动的认领：先记卡住，再卡就拉黑（进度看门狗）。"""
        body = getattr(unit, "body", None)
        ch = getattr(body, "chunk1", None)
        if ch is None:
            return
        if c.lx is None:
            c.lx, c.ly = ch.x, ch.y
            return
        if math.hypot(ch.x - c.lx, ch.y - c.ly) >= CLAIM_STALL_PX:
            c.lx, c.ly = ch.x, ch.y
            c.stall = 0
            return
        c.stall += 1
        if c.stall < CLAIM_STALL_TICKS:
            return
        c.stall = 0
        c.stalls += 1
        if c.stalls >= CLAIM_DROP_STALLS:
            self.blacklist(unit, c.obj, tick)
            self._claims.pop(id(unit), None)

    def release(self, unit) -> None:
        self._claims.pop(id(unit), None)

    def observes(self, unit, obj) -> bool:
        """我正在认领它（自己的目标）。"""
        c = self._claims.get(id(unit))
        return c is not None and c.obj is obj

    def taken(self, unit, obj) -> bool:
        """别的猫正认领它（含正去救的人 / 正打的猎物 / 正追的飞虫）。"""
        for key, c in self._claims.items():
            if key != id(unit) and c.obj is obj:
                return True
        return False

    def owner(self, obj):
        """谁正认领它（认小偷用）；没有则 None。"""
        for c in self._claims.values():
            if c.obj is obj:
                return c.owner
        return None

    # ── 黑名单 ──
    def blacklist(self, unit, obj, tick=None) -> None:
        self._black[(id(unit), id(obj))] = (obj, (self.tick if tick is None else tick)
                                            + BLACKLIST_TICKS)

    def blacklisted(self, unit, obj) -> bool:
        e = self._black.get((id(unit), id(obj)))
        return e is not None and e[1] > self.tick

    def _sweep(self) -> None:
        t = self.tick
        for key, c in list(self._claims.items()):
            if c.until < t:
                del self._claims[key]
        for key, (obj, until) in list(self._black.items()):
            if until < t:
                del self._black[key]

    # ── 查询 ──
    def crowd(self, unit, obj) -> float:
        """目标旁边还围着几只别的猫（越近权重越大，指数衰减）。"""
        if obj is None:
            return 0.0
        ox, oy = getattr(obj, "x", None), getattr(obj, "y", None)
        if ox is None or oy is None:
            return 0.0
        acc = 0.0
        for p in _others(unit):
            body = getattr(p, "body", None)
            ch = getattr(body, "chunk1", None)
            if ch is None or getattr(body, "dead", False):
                continue
            acc += math.exp(-math.hypot(ch.x - ox, ch.y - oy) / CROWD_SCALE)
        return min(acc, CROWD_MAX)


def _target_of(beh):
    """这只猫此刻的「正事目标」与类型（认领用）。"""
    if beh is None:
        return None, ""
    state = getattr(beh, "state", None)
    if state is None:
        return None, ""
    for st, holder, attr, kind in _OBSERVE:
        if st != state:
            continue
        src = beh if holder is None else getattr(beh, holder, None)
        if src is None:
            return None, ""
        obj = getattr(src, attr, None)
        return (obj, kind) if obj is not None else (None, "")
    if state == "Socialize" and getattr(beh, "_social_kind", None) == "revive":
        obj = getattr(beh, "_social_target", None)
        return (obj, "revive") if obj is not None else (None, "")
    return None, ""


def _others(unit):
    """同一张桌上除自己以外的猫。

    unit 是 PetUnit 时正常枚举；测试里有时直接传裸 window（它自己不在 pets
    里），这时「别的猫」应当是空的，否则会给单猫场景凭空加上拥挤成本。
    """
    me_win = getattr(unit, "window", None)
    for p in getattr(unit, "pets", ()):
        if p is unit:
            continue
        if me_win is None and getattr(p, "window", None) is unit:
            continue
        yield p


_BOARDS = weakref.WeakKeyDictionary()


def board_for(unit) -> Board:
    """取这只猫（这个窗口）所属的认领板。"""
    w = getattr(unit, "window", None) or unit
    b = _BOARDS.get(w)
    if b is None:
        b = Board()
        try:
            _BOARDS[w] = b
        except TypeError:          # 不可弱引用：退化成一次性板子
            return Board()
    return b
