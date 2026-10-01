"""规划目标：点 / 物体统一封装为 pos()+valid()+key()；radius 为达成容差（仅 can_stay 采信）。"""
from __future__ import annotations

from dataclasses import dataclass


class Goal:
    """目标：pos()/valid()/key() + radius 到位容差；contact 声明达成方式，仅补救层读。"""
    __slots__ = ("obj", "radius", "contact", "_pos_fn", "_valid_fn", "_key")

    def __init__(self, pos_fn, valid_fn, key, obj=None, radius=0.0, contact="body"):
        self._pos_fn = pos_fn
        self._valid_fn = valid_fn
        self._key = key
        self.obj = obj
        self.radius = float(radius)
        self.contact = contact

    def pos(self):
        return self._pos_fn()

    def valid(self):
        return bool(self._valid_fn())

    def key(self):
        return self._key


def point_goal(x, y, radius=0.0, contact="body"):
    """固定点目标。"""
    x, y = float(x), float(y)
    return Goal(lambda: (x, y), lambda: True, ("pt", x, y), radius=radius, contact=contact)


@dataclass(slots=True)
class EscapeGoal:
    """逃生目标（文档 §六）：问的不是「往哪跑」，是「哪里安全」。

    FSM 只负责判断「我现在是不是要逃」；「逃到哪里」由 Planner 在导航节点里
    挑安全节点（安全度过线 + 离威胁够远 + 还能走回来）。威胁消失后这个目标
    自然作废，不需要给 FSM 再写一条解除逻辑。
    """

    threat: object = None
    min_safety: float = 0.75      # 安全度下限 exp(-danger)
    min_distance: float = 180.0   # 离威胁的最小距离


def obj_goal(obj, valid=None, radius=0.0, contact="body"):
    """物体目标：坐标随 obj.x/obj.y 每帧更新；valid 为接收 obj 的谓词，缺省恒真。"""
    vf = (lambda: valid(obj)) if valid is not None else (lambda: True)
    return Goal(lambda: (obj.x, obj.y), vf, ("obj", id(obj)), obj=obj,
                radius=radius, contact=contact)
