# -*- coding: utf-8 -*-
"""投掷物弹道积分：AI 预演与真实飞行共用同一套规则（文档 §8 / §11「ProjectileTrajectory」）。

以前 AI 的 ``fsm._shot_arc()`` 和真实 ``Spear.step()`` 各写一遍「重力 + 平飞段 +
摩擦 + 位移」，调一个参数就要两边同时改，于是不断出现「AI 认为能中、实际不中」
「实际能中、AI 不投」。这里只放纯函数，两边都调它：

* :func:`gravity_delta` —— 这一 tick 的竖直加速度（掷出的矛过了平飞段才吃半重力）；
* :func:`advance`       —— 摩擦 + 位移；
* :func:`preview`       —— AI 用，跑 ticks 次得到弹道点。

命中判定不在这里，走 ``world/hitgeom.py``；两者合起来才是「一套弹道 AI」。
"""
from __future__ import annotations

import math

from . import weaponphys as wp

AIR_FRICTION = 0.999


def flight_far(x, y, ox, oy, flat=wp.SPEAR_FLIGHT_FLAT_PX) -> bool:
    """掷出的东西是否已经飞过「平飞段」（过了这段才回到常重力）。"""
    return float(flat) > 0.0 and math.hypot(x - ox, y - oy) >= float(flat)


def gravity_delta(x, y, ox, oy, thrown, gravity, room_gravity,
                  lift=wp.SPEAR_FLIGHT_LIFT,
                  flat=wp.SPEAR_FLIGHT_FLAT_PX) -> float:
    """这一 tick 要加的竖直速度。逐行对应 Spear.step 的重力块。

    ``lift`` / ``flat`` 由投掷物的档位（:class:`ProjectileProfile`）给：矛有
    平飞段，石头没有。旧实现把矛的两个常数写死在这里，于是石头预演也吃矛的
    「平飞 + 半重力」，而真实 ``Stone.step`` 吃满重力 —— 预演与真值两套弹道
    （文档 §1「最严重：一套弹道对矛成立，对石头不成立」）。
    """
    g = float(gravity) * float(room_gravity)
    if not thrown:
        return g
    if float(flat) <= 0.0 or float(lift) <= 0.0:
        return g
    if flight_far(x, y, ox, oy, flat):
        return g - float(lift)
    return 0.0


def advance(x, y, vx, vy, air_friction=AIR_FRICTION):
    """空气摩擦 + 位移。返回下一 tick 的 ``(x, y, vx, vy)``。"""
    vx *= air_friction
    vy *= air_friction
    return x + vx, y + vy, vx, vy


def preview(ox, oy, vx, vy, ticks, gravity=0.9, room_gravity=1.0,
            thrown=True, air_friction=AIR_FRICTION, profile=None):
    """AI 预演：出手点 + 初速 → 逐 tick 的弹道点 ``[(x, y), ...]``。

    和 ``Spear.step`` 用同一组 ``gravity_delta`` / 摩擦常数，所以预演说能中
    就是真能中（差别只在预演不模拟入水与地形碰撞）。
    """
    pts = []
    x, y = float(ox), float(oy)
    vx, vy = float(vx), float(vy)
    lift, flat = wp.SPEAR_FLIGHT_LIFT, wp.SPEAR_FLIGHT_FLAT_PX
    if profile is not None:
        gravity = profile.gravity            # 飞行重力模型跟档位走（文档 §1）
        lift, flat = profile.flight_lift, profile.flat_distance
    for _ in range(int(ticks)):
        vy += gravity_delta(x, y, ox, oy, thrown, gravity, room_gravity,
                            lift, flat)
        # 摩擦 + 位移只走 advance：真实 Spear.step 调的是同一个函数，
        # 改摩擦 / 入水 / 平飞段不会只改一半（文档 §1）。
        x, y, vx, vy = advance(x, y, vx, vy, air_friction)
        pts.append((x, y))
    return pts


class ProjectileProfile:
    """一种投掷物的物理档位：命中半径、命中补长、是否矛。

    AI 预演过去写死矛的半径 / 补长，扔石头也按矛算 —— 石头是圆、矛细长，
    两者的补长不一样（文档 §3）。这里只放数值，谁是谁由 :func:`profile_for`
    决定；发射端与命中端读同一份，不再各写一套 if。
    """
    __slots__ = ("name", "radius", "hit_pad", "is_spear", "gravity",
                 "flight_lift", "flat_distance")

    def __init__(self, name: str, radius: float, hit_pad: float,
                 is_spear: bool, gravity: float,
                 flight_lift: float = 0.0, flat_distance: float = 0.0):
        self.name = str(name)
        self.radius = float(radius)
        self.hit_pad = float(hit_pad)
        self.is_spear = bool(is_spear)
        self.gravity = float(gravity)
        # 飞行重力模型也是档位的一部分（文档 §1）：矛「先平飞 flat_distance
        # 像素、之后抵掉 flight_lift 的半重力」；石头两个都是 0 → 吃满重力，
        # 与 Stone.step 逐行一致。AI 预演和真实飞行的真值只有一个来源。
        self.flight_lift = float(flight_lift)
        self.flat_distance = float(flat_distance)

    def gravity_delta(self, x, y, ox, oy, thrown, room_gravity) -> float:
        """这一掷在 (x, y) 处的竖直加速度：档位自己决定飞行重力模型。"""
        return gravity_delta(x, y, ox, oy, thrown, self.gravity, room_gravity,
                             self.flight_lift, self.flat_distance)


SPEAR_PROFILE = ProjectileProfile("spear", wp.SPEAR_RAD, wp.SPEAR_HIT_PAD, True,
                                  0.9, wp.SPEAR_FLIGHT_LIFT,
                                  wp.SPEAR_FLIGHT_FLAT_PX)
# 石头没有平飞段：lift / flat 都是 0 → gravity_delta 直接返回满重力。
STONE_PROFILE = ProjectileProfile("stone", wp.STONE_RAD, wp.STONE_HIT_PAD, False, 0.9)


def profile_for(is_spear: bool) -> ProjectileProfile:
    """这一掷的档位：矛 / 石头。"""
    return SPEAR_PROFILE if is_spear else STONE_PROFILE
