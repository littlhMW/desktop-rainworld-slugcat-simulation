# -*- coding: utf-8 -*-
"""目标认领板：认领 / 位形槽 / 拥挤成本 / 失败黑名单。

原版每只生物有自己的 AI 目标与 pathFinder，抢同一件东西时靠各自的 utility
与个体关系自然分流；桌宠里十只猫共用一张「最近 / 最快」表，于是常常一起冲
向同一个果子。

这里给「猫 × 目标」加两件事：

1. **认领**（读当前状态得出）—— 有进展就自动续约，卡住 / 目标没了就释放。
   认领不额外登记：直接读猫此刻的状态（FetchFruit 的 fetch.target、
   FightThreat 的 _fight_target、Socialize 的救援目标……），状态一走开认领
   就自然消失，没有「忘记释放」这种可能。

2. **位形槽**（capacity）—— 一件目标同时只站得下几只猫（果子两侧、蜥蜴的
   正面/侧面/捡矛位、爆米花的下方、救援位只有 1 个……）。槽位按「谁离得近」
   分，多出来的人排在等待名单里，并且**记一次「抢输」**：输家会去指/指指点点
   那个抢先的人（见 fsm 的社交反应）。于是「拥挤」变成有上限的社会场景，
   而不是十只猫一起挤在同一颗果子上 —— 也不是死锁：等待者照样会换目标
   （打分里 `full()` 只是一项成本，不是禁止）。

另外两个信号：**拥挤成本**（目标旁边还围着几只猫）和**失败黑名单**（刚试过
拿不到的东西短期内不再选）。全部只参与**排序**，不改物理、不碰任何随机流。

世界生物（拾荒者、蜥蜴）也能来占位（`register_actor`）：它们盯上的珍珠 /
猎物在猫眼里就是「有主」的。
"""
from __future__ import annotations

import math
import weakref

from .anim_intent import point_of

CLAIM_TICKS = 150          # 一次认领的租约时长（期间主人每 tick 续约）
CLAIM_STALL_PX = 3.0       # 一 tick 位置变化小于它 = 这一 tick 没挪动
CLAIM_STALL_TICKS = 80     # 连续这么久没挪动 → 记一次「卡住」
CLAIM_DROP_STALLS = 2      # 卡住这么多次 → 把目标拉黑
BLACKLIST_TICKS = 420      # 拉黑时长（≈10 秒）
BLACKLIST_MUL = 4.0        # 拉黑目标在排序里乘这个（不是绝对禁止，防死锁）
CROWD_SCALE = 110.0        # 拥挤成本衰减尺度（像素）
CROWD_W = 0.45             # 拥挤成本权重（乘到「预估耗时」上）
CROWD_MAX = 2.0            # 单目标拥挤成本封顶

# ── 位形槽容量：一件目标同时站得下几只猫 ──
SLOT_CAP = {
    "eat": 2,        # 果子：左右两侧
    "hunt": 2,       # 猎物（蝙蝠 / 乌贼 / 面条蝇）
    "catch": 2,      # 抓飞虫玩
    "play": 2,       # 玩物品
    "fight": 3,      # 围一只蜥蜴：正面 / 侧面 / 去拔矛
    "help": 1,       # 帮喂：一次一个人喂
    "revive": 1,     # 复活：一只猫两只手就够
    "trade": 1,      # 珍珠交易位
    "corpse": 1,     # 收尸 / 拖尸体
}
SLOT_CAP_DEFAULT = 2
SLOT_FULL_MUL = 1.7        # 槽位满了的目标在排序里乘这个（软惩罚 → 有上限但不会死锁）
LOSS_TICKS = 240           # 抢输的记忆保留多久（社交反应窗口）

# 状态 → (取目标的对象属性, 认领类型)。取到目标就算认领，取不到就释放。
_OBSERVE = (
    ("FetchFruit", "fetch", "target", "eat"),
    ("HuntFly", "flyhunt", "target", "hunt"),
    ("CatchFly", "flycatch", "target", "catch"),
    ("FightThreat", None, "_fight_target", "fight"),
    ("HelpFeed", None, "_help_target", "help"),
)


class Claim:
    __slots__ = ("owner", "obj", "kind", "until", "lx", "ly", "stall", "stalls",
                 "born", "slot", "dist", "external")

    def __init__(self, owner, obj, kind, tick, external=False):
        self.owner = owner
        self.obj = obj
        self.kind = kind
        self.until = tick + CLAIM_TICKS
        self.lx = self.ly = None
        self.stall = 0
        self.stalls = 0
        self.born = tick          # 认领的起始 tick（同位形槽并列时先来先得）
        self.slot = 0             # 位形槽序号；-1 = 排在等待名单里
        self.dist = 0.0           # 到目标的距离（分槽用）
        self.external = external  # 世界生物（拾荒者 / 蜥蜴）占的位


class Board:
    """一张认领板（每个窗口一张）。"""

    def __init__(self):
        self._claims = {}      # 主人 id → Claim
        self._black = {}       # (主人 id, 目标 id) → (目标, 到期 tick)
        self._losses = {}      # 输家 id → (目标, 赢家, 到期 tick)
        self.tick = 0

    # ── 认领 ──
    def sync(self, unit, tick=None, *, sweep=True) -> None:
        """把这只猫此刻的「正事目标」登记成认领（无正事则注销）。"""
        if tick is not None:
            self.tick = tick
        tick = self.tick
        beh = getattr(unit, "behavior", None)
        obj, kind = _target_of(beh)
        key = id(unit)
        if obj is None:
            self._claims.pop(key, None)
            if sweep:
                self._sweep()
            return
        c = self._claims.get(key)
        if c is None or c.obj is not obj or c.kind != kind:
            c = Claim(unit, obj, kind, tick)
            self._claims[key] = c
        else:
            c.until = tick + CLAIM_TICKS
            self._progress(unit, c, tick)
        if sweep:
            self._sweep()

    def register_actor(self, actor, obj, kind, tick=None) -> None:
        """世界生物（拾荒者 / 蜥蜴）来占位：它盯上的东西在猫眼里就是「有主」的。

        和猫的认领同一张表，所以 `taken()` / `owner()` 照样认；不参与位形槽
        排序（`_seat` 跳过），也不算拥挤成本（拥挤成本只数同类）。
        """
        if tick is not None:
            self.tick = tick
        key = id(actor)
        if obj is None:
            self._claims.pop(key, None)
            return
        c = self._claims.get(key)
        if c is None or c.obj is not obj or c.kind != kind:
            c = Claim(actor, obj, kind, self.tick, external=True)
            self._claims[key] = c
        else:
            c.until = self.tick + CLAIM_TICKS
            c.external = True

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

    # ── 位形槽 ──
    def _seat(self) -> None:
        """按「谁离得近」给每件目标分位形槽，排不上的人记一次抢输。

        每 tick 重算（不比上 tick 的状态，没有残留），并列时先来先得。
        """
        groups = {}
        for key, c in self._claims.items():
            if c.external or c.obj is None:
                continue
            groups.setdefault((id(c.obj), c.kind), []).append(c)
        for lst in groups.values():
            for c in lst:
                c.dist = _dist_to(c.owner, c.obj)
            lst.sort(key=lambda c: (c.dist, c.born))
            cap = SLOT_CAP.get(lst[0].kind, SLOT_CAP_DEFAULT)
            for i, c in enumerate(lst):
                c.slot = i if i < cap else -1
                if i >= cap:
                    self._note_loss(c, lst[cap - 1])

    def _note_loss(self, loser: Claim, winner: Claim) -> None:
        """抢输的人记一笔（同一目标 + 同一赢家合成一条）。

        一直抢不到就一直续约（到期时间往后推）：这条记录代表「我还在排
        队」，只要还在排队就不该过期；真正消费掉（`consume_loss`）之后下一 tick
        又会重新记上（相当于每 tick 都可以重新抢），而社交动作本身由
        `_protest_cd` 限流。"""
        key = id(loser.owner)
        e = self._losses.get(key)
        if e is not None and e[0] is loser.obj and e[1] is winner.owner:
            self._losses[key] = (e[0], e[1], self.tick + LOSS_TICKS)
            return
        self._losses[key] = (loser.obj, winner.owner, self.tick + LOSS_TICKS)

    def consume_loss(self, unit):
        """取走「抢输」事件（只报一次）→ (目标, 赢家)；没有则 None。"""
        e = self._losses.pop(id(unit), None)
        return None if e is None else (e[0], e[1])

    def slot_of(self, unit, obj) -> int:
        """我在这件目标上排到第几个位形槽（-1 = 在等待名单，None = 没认领）。"""
        c = self._claims.get(id(unit))
        if c is None or c.obj is not obj:
            return None
        return c.slot

    def capacity(self, kind) -> int:
        return SLOT_CAP.get(kind, SLOT_CAP_DEFAULT)

    def seated_count(self, obj, kind) -> int:
        """这件目标上真正占到位的猫（不含自己以外的人时也照数）。"""
        n = 0
        for c in self._claims.values():
            if c.external or c.obj is not obj or c.kind != kind:
                continue
            if c.slot >= 0:
                n += 1
        return n

    def full(self, obj, kind, skip=None) -> bool:
        """位形槽满了（`skip` 这只猫不算在内）—— 排序里当成本用，不是禁止。"""
        n = 0
        for c in self._claims.values():
            if c.external or c.obj is not obj or c.kind != kind:
                continue
            if skip is not None and c.owner is skip:
                continue
            if c.slot >= 0:
                n += 1
        return n >= self.capacity(kind)

    def release(self, unit) -> None:
        self._claims.pop(id(unit), None)
        self._losses.pop(id(unit), None)

    def observes(self, unit, obj) -> bool:
        """我正在认领它（自己的目标）。"""
        c = self._claims.get(id(unit))
        return c is not None and c.obj is obj

    def taken(self, unit, obj) -> bool:
        """别的猫 / 生物正认领它（含正去救的人 / 正打的猎物 / 正追的飞虫）。"""
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

    def owners(self, obj) -> list:
        """正认领它的所有人（社会反应要找出「抢了我位子的人」）。"""
        return [c.owner for c in self._claims.values() if c.obj is obj]

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
        # 记忆只看到期：抢输的人往往是在「放弃这件事」之后才腾出手来反应的，
        # 所以不能因为认领消失就把账抹掉（那样这条反应永远不会发生）。
        for key, (obj, winner, until) in list(self._losses.items()):
            if until < t:
                del self._losses[key]
        self._seat()

    # ── 查询 ──
    def target_crowd(self, unit, obj) -> float:
        """**目标级**拥挤：这个目标旁边还围着几只别的猫（越近权重越大）。

        与 ``planning/crowd.TrafficField``（路线级交通）不是同一件事，改名只为
        避免看混（文档 §14）。
        """
        o = point_of(obj)
        if o is None:
            return 0.0
        ox, oy = o
        acc = 0.0
        for p in _others(unit):
            body = getattr(p, "body", None)
            ch = getattr(body, "chunk1", None)
            if ch is None or getattr(body, "dead", False):
                continue
            acc += math.exp(-math.hypot(ch.x - ox, ch.y - oy) / CROWD_SCALE)
        return min(acc, CROWD_MAX)


def _dist_to(unit, obj) -> float:
    """认领者到目标的距离（分位形槽用）；缺坐标一律算 0（先来先得）。"""
    body = getattr(unit, "body", None)
    ch = getattr(body, "chunk1", None)
    o = point_of(obj)
    if ch is None or o is None:
        return 0.0
    return math.hypot(ch.x - o[0], ch.y - o[1])


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


def win_of(unit):
    """unit 所属的窗口；unit 自己就是窗口时返回它自己。

    `QWidget.window` 是个**方法**，所以不能直接 `getattr(unit, "window")` 当
    属性用 —— 那样每次拿到一个新的绑定方法，认领板会一张接一张地新建。
    """
    w = getattr(unit, "window", None)
    if w is None or w is unit or callable(w):
        return unit
    return w


def _others(unit):
    """同一张桌上除自己以外的猫。

    unit 是 PetUnit 时正常枚举；直接传裸 window（它自己不在 pets 里）时就是
    窗口里的每一只猫。
    """
    me = win_of(unit)
    for p in getattr(unit, "pets", ()):
        if p is unit:
            continue
        if win_of(p) is not me:
            continue
        yield p


_BOARDS = weakref.WeakKeyDictionary()


def board_for(unit) -> Board:
    """取这只猫（这个窗口）所属的认领板。"""
    w = win_of(unit)
    b = _BOARDS.get(w)
    if b is None:
        b = Board()
        try:
            _BOARDS[w] = b
        except TypeError:          # 不可弱引用：退化成一次性板子
            return Board()
    return b
