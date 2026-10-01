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


def flight_far(x, y, ox, oy) -> bool:
    """掷出的矛是否已经飞过「平飞段」（过了这段才回到原版半重力）。"""
    return math.hypot(x - ox, y - oy) >= wp.SPEAR_FLIGHT_FLAT_PX


def gravity_delta(x, y, ox, oy, thrown, gravity, room_gravity) -> float:
    """这一 tick 要加的竖直速度。逐行对应 Spear.step 的重力块。"""
    g = float(gravity) * float(room_gravity)
    if not thrown:
        return g
    if flight_far(x, y, ox, oy):
        return g - wp.SPEAR_FLIGHT_LIFT
    return 0.0


def advance(x, y, vx, vy, air_friction=AIR_FRICTION):
    """空气摩擦 + 位移。返回下一 tick 的 ``(x, y, vx, vy)``。"""
    vx *= air_friction
    vy *= air_friction
    return x + vx, y + vy, vx, vy


def preview(ox, oy, vx, vy, ticks, gravity=0.9, room_gravity=1.0,
            thrown=True, air_friction=AIR_FRICTION):
    """AI 预演：出手点 + 初速 → 逐 tick 的弹道点 ``[(x, y), ...]``。

    和 ``Spear.step`` 用同一组 ``gravity_delta`` / 摩擦常数，所以预演说能中
    就是真能中（差别只在预演不模拟入水与地形碰撞）。
    """
    pts = []
    x, y = float(ox), float(oy)
    vx, vy = float(vx), float(vy)
    for _ in range(int(ticks)):
        vy += gravity_delta(x, y, ox, oy, thrown, gravity, room_gravity)
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
    __slots__ = ("name", "radius", "hit_pad", "is_spear", "gravity")

    def __init__(self, name: str, radius: float, hit_pad: float,
                 is_spear: bool, gravity: float):
        self.name = str(name)
        self.radius = float(radius)
        self.hit_pad = float(hit_pad)
        self.is_spear = bool(is_spear)
        self.gravity = float(gravity)


SPEAR_PROFILE = ProjectileProfile("spear", wp.SPEAR_RAD, wp.SPEAR_HIT_PAD, True, 0.9)
STONE_PROFILE = ProjectileProfile("stone", wp.STONE_RAD, wp.STONE_HIT_PAD, False, 0.9)


def profile_for(is_spear: bool) -> ProjectileProfile:
    """这一掷的档位：矛 / 石头。"""
    return SPEAR_PROFILE if is_spear else STONE_PROFILE
