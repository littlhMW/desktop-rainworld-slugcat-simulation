# -*- coding: utf-8 -*-
"""Interaction Pose：同一个目标没有唯一正确的接近点。

原版一只生物盯上一个东西，并不是「走向它的中心」：果子可以站左边够也可以站
右边够，爆米花要站到能投矛的那一侧，围蜥蜴有正面位 / 侧面位 / 去拔矛位。桌宠
过去把目标当成一个坐标，于是多只猫必然在同一格上互相挤。

这里把「目标 + 动作 + 位形槽」翻成一个 pose：站在哪、朝哪边。认领板（board.py）
已经给每只猫分好了位形槽，pose 就是那个槽的几何含义 —— 第一只猫仍然直奔物体
中心（保持旧行为），第二只站左边、第三只站右边，于是拥挤自己就散了。

    InteractionGoal = Goal（key 与 obj_goal 完全一致，冷却 / 认领都不受影响）
                    + .pose（站位与朝向），执行器照旧只管 Goal 的位置。
"""
from __future__ import annotations

from dataclasses import dataclass

from .anim_intent import point_of
from ..planning.goal import Goal, obj_goal

# 位形槽 → 站位偏移（0 = 直奔物体中心；-1 站左边；+1 站右边）
SEATS = (0.0, -1.0, +1.0)

# 各类交互的站位距离：投掷要留出助跑，吃东西可以贴得很近
STAND_OFF = {
    "eat": 30.0, "pick": 22.0, "play": 26.0, "catch": 26.0,
    "hunt": 40.0, "fight": 44.0, "throw": 48.0, "trade": 34.0,
}
STAND_OFF_DEFAULT = 28.0


@dataclass(frozen=True)
class InteractionPose:
    """一次交互的位形：目标、动作、位形槽、站位侧与距离。"""
    target: object
    action: str
    slot: int
    side: float
    off: float

    def pos(self):
        """该位形的站位点（每帧按目标当前位置重算）。"""
        p = point_of(self.target)
        if p is None:
            return (0.0, 0.0)
        if self.side == 0.0:
            return p
        return (p[0] + self.side * self.off, p[1])

    def facing(self) -> int:
        """朝哪边（±1；0 = 站在正对面 / 不确定）。"""
        return 0 if self.side == 0.0 else (-1 if self.side > 0.0 else 1)

    def stand_side(self) -> float:
        return self.side


def side_for(action: str, slot: int) -> float:
    """位形槽 → 站位偏移（槽号越靠后越往外侧站）。"""
    if slot is None or slot < 0:
        slot = 0
    return SEATS[slot] if slot < len(SEATS) else SEATS[-1]


def pose_for(target, action: str, slot: int = 0) -> InteractionPose:
    return InteractionPose(target, action, 0 if slot is None else int(slot),
                           side_for(action, slot),
                           STAND_OFF.get(action, STAND_OFF_DEFAULT))


class InteractionGoal(Goal):
    """带位形的物体目标：位置 = pose 的站位点，key 与 obj_goal 一致。"""
    __slots__ = ("pose",)

    def __init__(self, pose: InteractionPose, valid_fn, contact="grasp"):
        super().__init__(pose.pos, valid_fn or (lambda: True),
                         ("obj", id(pose.target)), obj=pose.target,
                         contact=contact)
        self.pose = pose


def interaction_goal(target, unit, action: str = "eat", valid=None,
                     contact="grasp") -> InteractionGoal:
    """按 unit 在 target 上排到的位形槽造一个 InteractionGoal。"""
    from .board import board_for
    slot = board_for(unit).slot_of(unit, target)
    pose = pose_for(target, action, 0 if slot is None or slot < 0 else slot)
    vf = (lambda: bool(valid(target))) if valid is not None else (lambda: True)
    return InteractionGoal(pose, vf, contact=contact)


def plain_goal(target, valid=None, contact="grasp") -> Goal:
    """没有认领信息时的回落：直奔物体中心（旧行为）。"""
    return obj_goal(target, valid=valid, contact=contact)
