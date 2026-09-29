# -*- coding: utf-8 -*-
"""庇护所大门：**原版 ShelterGate_* 贴图的真装配**（不是手画的矩形）。

逐条对应 ``ShelterDoor.cs``：

* ``InitiateSprites``：``new FSprite[42]``，全部 ``ColoredSprite3``，容器 ``Items``，
  整体 ``rotation = AimFromOneVectorToAnother(dir, zero)``。
  | idx | sprite | 数量 | 备注 |
  |-----|--------|------|------|
  | 0   | ShelterGate_cog            | 4  | alpha 1-(j<2?6:5)/30 |
  | 4   | ShelterGate_piston1/2      | 2  | alpha 0.9 |
  | 6   | ShelterGate_plug1..8       | 8  | |
  | 14  | ShelterGate_segment1..10   | 10 | |
  | 24  | ShelterGate_cylinder1..4   | 4  | |
  | 28  | ShelterGate_cover1..4      | 4  | |
  | 32  | ShelterGate_pump1..8       | 8  | |
  | 40  | ShelterGate_Hatch          | 2  | anchor (0.2,0.43)，第 1 张 scaleX=-1 |
* ``DrawSprites``：位置全部写成 ``pZero + perp * a - dir * b`` 的形式；
  本模块把 ``a`` 记成 ``ao``（沿走廊法线）、``b`` 记成 ``bo``（沿走廊方向）。
* ``DoorGraphic`` 的 ``Closed`` 分段曲线（flaps/pistons/segments/covers/
  cylinders/pumpsEnter/pumpsExit）在 ``world/shelter.py`` 的 ``DoorPhases`` 里推进。

桌宠坐标是 y 向下，原版是 y 向上，所以：

* ``perp_pet = (0, -dir_x)``（原版 ``PerpendicularVector(dir) = (-dy, dx)``）
* 原版 ``rotation`` 逆时针为正；Qt 的 ``rotate()`` 顺时针为正 → 取负号。
* ``dir`` 在桌宠里恒为水平（门只会朝左/朝右），所以整体只有 0/180 两档。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF

_GATE_FRAME = "ShelterGate_cog"      # 用来探测 shelterGate 图集在不在
_ITEMS_LAYER = "Items"               # ShelterDoor.AddToContainer（非 ancient）


def available(atlas):
    """shelterGate 图集在不在（缺图集时上层退回程序化门板）。"""
    if atlas is None:
        return False
    try:
        return atlas.find_atlas(_GATE_FRAME) is not None
    except Exception:
        return False


def _lerp(a, b, t):
    return a + (b - a) * t


def _sprite(p, at, frame, ax, ay, px, py, rot, scale, alpha, flip=False):
    """画一张 ShelterGate sprite：px/py 是 anchor 点的世界坐标。

    ``rot`` 用原版角度值（Futile rotation，正＝逆时针）；Qt 同一坐标系下
    ``rotate(+rot)`` 观感一致，所以直接传正值。``flip`` 对应 scaleX = -1f。
    """
    if alpha <= 0.004 or scale <= 0.02:
        return
    pm = at.sprite(frame)
    if pm.isNull():
        return
    w = float(pm.width())
    h = float(pm.height())
    p.save()
    if alpha < 0.999:
        p.setOpacity(alpha)
    p.translate(px, py)
    p.rotate(rot)
    p.scale(-scale if flip else scale, scale)
    p.drawPixmap(QPointF(-ax * w, -(1.0 - ay) * h), pm)
    p.restore()


def draw_door(p, atlas, sh, ts=1.0):
    """按原版装配画整扇门；图集缺失返回 False（交给程序化兜底）。"""
    key = atlas.find_atlas(_GATE_FRAME)
    if key is None:
        return False
    at = atlas.get(key)
    ph = getattr(sh, "phases", None)
    if ph is None:
        return False
    dx = float(sh.dir_x)
    perp_x, perp_y = 0.0, -dx          # perp_pet
    zx, zy = sh.p_zero
    scale = float(getattr(sh, "door_scale", 1.0))
    # InitiateSprites: rotation = AimFromOneVectorToAnother(dir, zero)
    #   = atan2(-dir.y, -dir.x) → dir 朝右(+x) 时 180°，朝左 0°
    base = 180.0 if dx > 0.0 else 0.0

    def at_xy(ao, bo):
        return (zx + perp_x * ao + dx * bo, zy + perp_y * ao)

    # 1) 4 个齿轮：perpendicular ±(35|55)，-dir*(50|15)
    for j in range(4):
        ao = ((-1.0 if j % 2 == 0 else 1.0) * (35.0 if j >= 2 else 55.0))
        bo = -(50.0 if j >= 2 else 15.0)
        # DrawSprites 对齿轮是绝对赋值（覆盖 InitiateSprites 的 rotation）
        rot = sh.close_fac * (400.0 if j >= 2 else -150.0) \
            * (-1.0 if j % 2 == 0 else 1.0)
        px, py = at_xy(ao, bo)
        _sprite(p, at, "ShelterGate_cog", 0.5, 0.5, px, py, rot, scale,
                1.0 - (6.0 if j < 2 else 5.0) / 30.0)

    # 2) 10 段闸板：perpendicular * pow(1-lerp, 0.75) * 55
    for k in range(10):
        num = k // 2
        v = ph.seg_lerp(num, ts)
        ao = (1.0 - v) ** 0.75 * 55.0 * (-1.0 if k % 2 == 0 else 1.0)
        px, py = at_xy(ao, 0.0)
        _sprite(p, at, "ShelterGate_segment%d" % (k + 1), 0.5, 0.5, px, py,
                base, scale, ph.segment_alpha)

    # 3) 2 根活塞：dir * (1-lerp) * -120
    for l in range(2):
        v = ph.piston_lerp(l, ts)
        bo = (1.0 - v) * -120.0
        ao = 5.0 * (-1.0 if l == 0 else 1.0) if ph.pistons_closed > 0.0 else 0.0
        px, py = at_xy(ao, bo)
        _sprite(p, at, "ShelterGate_piston%d" % (l + 1), 0.5, 0.5, px, py,
                base, scale, 0.9)

    # 4) 4 块护板：perpendicular * pow(1-lerp, 2.5) * 65
    for m in range(4):
        v = ph.cover_lerp(m, ts)
        ao = (1.0 - v) ** 2.5 * 65.0 * (-1.0 if m >= 2 else 1.0)
        px, py = at_xy(ao, 0.0)
        _sprite(p, at, "ShelterGate_cover%d" % (m + 1), 0.5, 0.5, px, py,
                base, scale, 1.0)

    # 5) 4 个液压缸：钉在 pZero，按 n/4 < Cylinders 逐个出现
    for nn in range(4):
        if nn / 4.0 < ph.cylinders:
            px, py = at_xy(0.0, 0.0)
            _sprite(p, at, "ShelterGate_cylinder%d" % (nn + 1), 0.5, 0.5,
                    px, py, base, scale, 1.0)

    # 6) 8 根密封泵 + 8 个塞子
    for num2 in range(8):
        v = ph.pump_lerp(num2, ts)
        side = -1.0 if num2 % 2 == 0 else 1.0
        ao = v * -42.0 * side
        bo = -(ph.pumps_exit * 80.0)
        px, py = at_xy(ao, bo)
        _sprite(p, at, "ShelterGate_pump%d" % (num2 + 1), 0.5, 0.5, px, py,
                base, scale, 1.0)
        plug = min(1.0, max(0.0, 1.0 - v - 0.35)) * 60.0 * side
        px, py = at_xy(plug, 0.0)
        _sprite(p, at, "ShelterGate_plug%d" % (num2 + 1), 0.5, 0.5, px, py,
                base, scale, 1.0)

    # 7) 2 片小舱门：dir*46 + perp*lerp(15,25,FlapsOpen)
    #    rotation = AimFromOneVectorToAnother(-dir, dir) - 90*(num3==0?-1:1)*FlapsOpen
    flaps = ph.flaps_open
    hbase = 0.0 if dx > 0.0 else 180.0      # atan2(dir.y, dir.x) → ±0/180
    for num3 in range(2):
        side = 1.0 if num3 == 0 else -1.0
        ao = _lerp(15.0, 25.0, flaps) * side
        bo = 46.0
        rot = hbase + (1.0 if num3 == 0 else -1.0) * 90.0 * flaps
        px, py = at_xy(ao, bo)
        _sprite(p, at, "ShelterGate_Hatch", 0.2, 0.43, px, py, rot, scale, 1.0,
                flip=(num3 == 1))       # 原版 scaleX = -1f
    return True


def sprite_count():
    """原版 FSprite[42] —— 给测试用。"""
    return 42
