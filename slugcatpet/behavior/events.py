# -*- coding: utf-8 -*-
"""世界事件总线：一次动作 → 一条事件 → 别的生物各自解释。

原版没有全局任务表：每只生物各自观察世界，「谁的东西被谁拿走了」「谁被谁打了」
只在各自的 AI 里留下痕迹。桌宠过去把这些判断散在 FSM 的各个分支里
（_watch_fetch_steal / _board_loss_tick / _witness_protest），于是「一个动作」
只能被写死的那一处解释，别人看见了也不会有任何反应。

这里把「发生了什么」和「谁怎么反应」拆开：

    动作 → emit(WorldEvent) → 目击者各自选反应（social_response.py）→ 下一个动作

事件只描述事实（谁、对谁、什么、多重、哪一 tick、在哪），不带任何反应；
关系变化由 relationship.py 记账，反应选型由 social_response.py 决定。

总线按窗口一张（与认领板同源），查询**无状态**：consumer 用
bus.recent(tick, span) 取「最近 span tick 内发生的事」，自己不留游标，
所以不存在「忘记释放游标」这种泄漏。
"""
from __future__ import annotations

import weakref

from .anim_intent import point_of

# ── 事件类型（原版 SocialEvent / 关系变化的触发源）──
OBJECT_CLAIMED = "ObjectClaimed"
OBJECT_TAKEN = "ObjectTaken"
OBJECT_DROPPED = "ObjectDropped"
CREATURE_THREATENED = "CreatureThreatened"
CREATURE_HURT = "CreatureHurt"
CREATURE_KILLED = "CreatureKilled"
CREATURE_RESCUED = "CreatureRescued"
CREATURE_HELPED = "CreatureHelped"
CREATURE_BLOCKED = "CreatureBlocked"
CREATURE_WARNED = "CreatureWarned"
GESTURE_POINTED = "GesturePointed"
GESTURE_SCOLDED = "GestureScolded"
GESTURE_ANSWERED = "GestureAnswered"
TRADE_COMPLETED = "TradeCompleted"

KINDS = frozenset((
    OBJECT_CLAIMED, OBJECT_TAKEN, OBJECT_DROPPED,
    CREATURE_THREATENED, CREATURE_HURT, CREATURE_KILLED,
    CREATURE_RESCUED, CREATURE_HELPED, CREATURE_BLOCKED, CREATURE_WARNED,
    GESTURE_POINTED, GESTURE_SCOLDED, GESTURE_ANSWERED, TRADE_COMPLETED,
))

# 目击半径：同一个动作，离得近的才算「看见」（原版靠视觉与听觉，不是全场广播）
WITNESS_R = {
    OBJECT_TAKEN: 300.0,
    OBJECT_CLAIMED: 150.0,
    OBJECT_DROPPED: 150.0,
    CREATURE_THREATENED: 260.0,
    CREATURE_HURT: 300.0,
    CREATURE_KILLED: 340.0,
    CREATURE_RESCUED: 300.0,
    CREATURE_HELPED: 260.0,
    CREATURE_BLOCKED: 200.0,
    CREATURE_WARNED: 220.0,
    GESTURE_POINTED: 280.0,
    GESTURE_SCOLDED: 240.0,
    GESTURE_ANSWERED: 200.0,
    TRADE_COMPLETED: 260.0,
}
WITNESS_R_DEFAULT = 220.0

EVENT_TICKS = 90             # 总线里的事件只留这么久（按窗口时钟）
EVENT_LOG_MAX = 256
REACT_INTENSITY_MIN = 0.15   # 低于它的事件不值得别人起反应


class WorldEvent:
    """一件发生过的事：字段全是事实，不做任何判断。"""

    __slots__ = ("kind", "tick", "subject", "obj", "other", "intensity",
                 "x", "y", "tag", "seq")

    def __init__(self, kind, tick=0, subject=None, obj=None, other=None,
                 intensity=0.5, x=0.0, y=0.0, tag="", seq=0):
        self.seq = int(seq)
        self.kind = kind
        self.tick = int(tick)
        self.subject = subject      # 做这件事的人
        self.obj = obj              # 涉及的东西 / 被牵连的人
        self.other = other          # 第三人（交易对手、目击关系里的关键角色）
        self.intensity = float(intensity)
        self.x = float(x)
        self.y = float(y)
        self.tag = tag

    def involves(self, who) -> bool:
        return who is not None and (who is self.subject or who is self.obj
                                    or who is self.other)

    def __repr__(self):
        return "WorldEvent(%s, subj=%s, obj=%s, i=%.2f, t=%d)" % (
            self.kind, type(self.subject).__name__, type(self.obj).__name__,
            self.intensity, self.tick)


class EventBus:
    """一个窗口一张：记下发生过的事。谁来读、读多久，由读的人决定。"""

    __slots__ = ("_log", "tick", "seq")

    def __init__(self):
        self._log = []          # [event]，按发生顺序
        self.tick = 0
        self.seq = 0            # 发过多少条：消费者的游标（同一 tick 也不会漏）

    # ── 记 ──
    def emit(self, kind, subject=None, obj=None, other=None, intensity=0.5,
             tick=None, x=None, y=None, tag=""):
        """记一件事；x/y 没给就从当事人身上取。"""
        if tick is not None:
            self.tick = int(tick)
        if x is None or y is None:
            p = point_of(subject) if subject is not None else None
            if p is None:
                p = point_of(obj)
            if p is not None:
                x = p[0] if x is None else x
                y = p[1] if y is None else y
        ev = WorldEvent(kind, self.tick, subject, obj, other,
                        intensity, 0.0 if x is None else x,
                        0.0 if y is None else y, tag, self.seq)
        self.seq += 1
        self._log.append(ev)
        if len(self._log) > EVENT_LOG_MAX:
            del self._log[:len(self._log) - EVENT_LOG_MAX]
        old = self.tick - EVENT_TICKS
        while self._log and self._log[0].tick < old:
            del self._log[0]
        return ev

    # ── 读 ──
    def recent(self, tick=None, span=2, kinds=None) -> tuple:
        """最近 span tick 内的事件（按发生顺序）。"""
        t = self.tick if tick is None else int(tick)
        lo = t - max(0, int(span))
        out = []
        for ev in reversed(self._log):
            if ev.tick < lo:
                break
            if kinds is not None and ev.kind not in kinds:
                continue
            out.append(ev)
        out.reverse()
        return tuple(out)

    def since(self, cursor: int, kinds=None) -> tuple:
        """比 cursor 新的所有事件（游标是事件序号，不是 tick）。

        消费者用 `since` 而不是「最近 N tick」：同一 tick 里可能先记一条、再过
        一会儿又记一条，按 tick 查会漏掉后一条。
        """
        out = []
        for ev in reversed(self._log):
            if ev.seq <= cursor:
                break
            if kinds is not None and ev.kind not in kinds:
                continue
            out.append(ev)
        out.reverse()
        return tuple(out)

    def witnesses(self, event, observers, radius=None) -> list:
        """附近看得见这件事的观察者（当事人自己不算）。"""
        if radius is None:
            radius = WITNESS_R.get(event.kind, WITNESS_R_DEFAULT)
        r2 = radius * radius
        out = []
        for o in observers:
            if o is None or event.involves(o):
                continue
            p = point_of(o)
            if p is None:
                continue
            dx, dy = p[0] - event.x, p[1] - event.y
            if dx * dx + dy * dy <= r2:
                out.append(o)
        return out


_BUSES = weakref.WeakKeyDictionary()


def bus_for(unit) -> EventBus:
    """取这个窗口的事件总线（与认领板同一套「unit → 窗口」判断）。"""
    from .board import win_of
    w = win_of(unit)
    b = _BUSES.get(w)
    if b is None:
        b = EventBus()
        try:
            _BUSES[w] = b
        except TypeError:
            return EventBus()
    return b


def emit_for(unit, kind, **kw):
    """便捷入口：往 unit 所在窗口的总线上记一件事。

    没显式给 tick 时按窗口的 `_pole_tick` 打时间戳 —— 事件的时间轴必须和
    读事件的人（FSM 的 _event_tick）用同一根时钟，否则事件永远「太旧」。
    """
    b = bus_for(unit)
    if kw.get("tick") is None:
        from .board import win_of
        kw["tick"] = getattr(win_of(unit), "_pole_tick", b.tick)
    return b.emit(kind, **kw)
