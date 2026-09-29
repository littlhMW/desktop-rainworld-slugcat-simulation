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

* 原版 ``dir`` = 入口 tile → 第一个非 Solid 邻居（**指向屋内**）；``sh.dir_x`` 记的是
  「门朝屋外」，所以 ``dir = (-dir_x, 0)``，``perp = (-dy, dx) = (0, dir_x)``。
* 位置先在原版坐标系（y 向上）里算，最后统一 ``(vx, vy) -> (zx+vx, zy-vy)`` 映射到
  桌宠（y 向下）。
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

    ``rot`` 用原版角度值（Futile rotation，正＝屏幕上逆时针）。Qt 的 rotate()
    在 y 向下的屏幕里正角＝顺时针，所以这里取负号才是同一个观感 —— 齿轮转向、
    小舱门开合方向都吃这一条。``flip`` 对应 scaleX = -1f。
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
    p.rotate(-rot)
    p.scale(-scale if flip else scale, scale)
    p.drawPixmap(QPointF(-ax * w, -(1.0 - ay) * h), pm)
    p.restore()


# ── 图集上色：ShelterGate 是 **paletted** 贴图 ──────────────────────────────
# 像素是（R = 深度索引 0..255，G = 0，B = 调色板行 0..255，A = 覆盖率），游戏里由
# ``ColoredSprite2.shader``（游戏内名 ``ColoredSprite3``）查一张 32×8 的调色板纹理上色：
#     dpth = texcol.x              # 精灵 color 是白 ⇒ 直接用 R
#     pal  = tex2D(_PalTex, float2(lerp(0.5,29.5,dpth)/32, lerp(0.5,2.5,texcol.z)/8))
# 那张调色板纹理由 ``RoomCamera.LoadPalette`` + ``ApplyFade`` 生成：
#     行 l（l = 0..7）= Lerp(fadeTexA(k, l+8), fadeTexA(k, l), DarkPalette)
# ``LoadImage`` 不翻转，所以 fadeTexA 的 y 就是 PNG 的 (15 - y)。DarkPalette 取 0
# （不压暗），于是行 l 就是 PNG 行 (7 - l)，只用得上 l = 0..2 这三行。
# 下面这张表就是游戏 palette0 的那三行（30 列），数值出处见 docs/DECOMPILE_PROCESS.md。
GATE_PALETTE = (
    # 行 0 = PNG 行 7
    (
        (23, 8, 28), (23, 8, 28), (23, 8, 28), (23, 8, 28), (25, 10, 31),
        (29, 14, 35), (41, 29, 49), (52, 43, 62), (59, 50, 69), (59, 50, 69),
        (59, 50, 69), (59, 50, 69), (61, 51, 71), (62, 53, 73), (65, 56, 76),
        (68, 59, 79), (72, 64, 84), (72, 64, 84), (72, 64, 84), (75, 68, 87),
        (80, 74, 92), (86, 80, 98), (92, 88, 104), (102, 100, 114), (102, 100, 114),
        (102, 100, 114), (102, 100, 114), (102, 100, 114), (102, 100, 114), (102, 100, 114),
    ),
    # 行 1 = PNG 行 6
    (
        (23, 8, 28), (23, 8, 28), (23, 8, 28), (23, 8, 28), (25, 10, 31),
        (29, 14, 35), (41, 29, 49), (52, 43, 62), (59, 50, 69), (59, 50, 69),
        (59, 50, 69), (59, 50, 69), (61, 51, 71), (62, 53, 73), (65, 56, 76),
        (68, 59, 79), (72, 64, 84), (72, 64, 84), (72, 64, 84), (75, 68, 87),
        (80, 74, 92), (86, 80, 98), (92, 88, 104), (102, 100, 114), (102, 100, 114),
        (102, 100, 114), (102, 100, 114), (102, 100, 114), (102, 100, 114), (102, 100, 114),
    ),
    # 行 2 = PNG 行 5
    (
        (49, 40, 57), (49, 40, 57), (49, 40, 57), (49, 40, 57), (51, 42, 60),
        (54, 47, 63), (65, 58, 75), (74, 66, 85), (79, 72, 90), (79, 72, 90),
        (79, 72, 90), (79, 72, 90), (80, 73, 91), (81, 74, 93), (83, 75, 94),
        (84, 77, 96), (87, 80, 99), (87, 80, 99), (87, 80, 99), (89, 82, 101),
        (91, 85, 103), (94, 89, 106), (97, 93, 109), (102, 100, 114), (102, 100, 114),
        (102, 100, 114), (102, 100, 114), (102, 100, 114), (102, 100, 114), (102, 100, 114),
    ),
)
_PAL_LUT = None


def _g_index(v: float) -> int:
    """shader 里的 round(lerp(0.5, 29.5, v))：深度 → 调色板列。"""
    x = int(round(29.0 * v))
    return 0 if x < 0 else (29 if x > 29 else x)


def _row_index(v: float) -> int:
    """shader 里的 round(lerp(0.5, 2.5, v))：蓝通道 → 调色板行 0..2。"""
    x = int(round(2.0 * v))
    return 0 if x < 0 else (2 if x > 2 else x)


def _lut_bytes() -> bytes:
    """(B, R) → (B, G, R) 的 256×256 查表（ARGB32 在内存里是 BGRA 序）。"""
    global _PAL_LUT
    if _PAL_LUT is None:
        buf = bytearray(256 * 256 * 3)
        for b in range(256):
            row = GATE_PALETTE[_row_index(b / 255.0)]
            for r in range(256):
                col = row[_g_index(r / 255.0)]
                j = (b << 8 | r) * 3
                buf[j] = col[2]
                buf[j + 1] = col[1]
                buf[j + 2] = col[0]
        _PAL_LUT = bytes(buf)
    return _PAL_LUT


def _is_paletted(img) -> bool:
    """不透明像素的 G 通道全 0 ⇒ 还是没上色的原始 paletted 贴图。

    透明区的填充色是白的（G=255），必须按 alpha 过滤后再看，否则永远判成已上色。
    """
    try:
        raw = bytes(img.constBits())
    except Exception:
        return False
    if len(raw) < 4:
        return False
    seen = False
    for i in range(0, len(raw), 4):
        if raw[i + 3] == 0:
            continue
        if raw[i + 1] != 0:
            return False
        seen = True
    return seen


def _bake(img):
    """整张图集一次查表（256×256 约 6.5 万像素，一辈子只做一次）。"""
    from PySide6.QtGui import QImage
    im = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h, stride = im.width(), im.height(), im.bytesPerLine()
    raw = bytearray(bytes(im.constBits()))
    lut = _lut_bytes()
    for i in range(0, w * 4 * h, 4):
        if raw[i + 3] == 0:
            continue
        j = (raw[i] << 8 | raw[i + 2]) * 3
        raw[i] = lut[j]
        raw[i + 1] = lut[j + 1]
        raw[i + 2] = lut[j + 2]
    out = QImage(bytes(raw), w, h, stride, QImage.Format.Format_ARGB32)
    return out.copy()


def ensure_baked(atlas) -> None:
    """第一次画门之前把 paletted 图集烘成真彩（旧素材包也自动修好）。"""
    key = atlas.find_atlas(_GATE_FRAME)
    if key is None:
        return
    at = atlas.get(key)
    if getattr(at, "_gate_baked", False):
        return
    at._gate_baked = True
    try:
        if _is_paletted(at.image):
            at.replace_image(_bake(at.image))
    except Exception:
        pass


def draw_door(p, atlas, sh, ts=1.0):
    """按原版装配画整扇门；图集缺失返回 False（交给程序化兜底）。"""
    key = atlas.find_atlas(_GATE_FRAME)
    if key is None:
        return False
    ensure_baked(atlas)
    at = atlas.get(key)
    ph = getattr(sh, "phases", None)
    if ph is None:
        return False
    # 原版 dir = 入口 tile → 第一个非 Solid 邻居 = **指向屋内**（ShelterDoor.cs:1170）。
    # sh.dir_x 记的是「门朝屋外」的那一侧，所以取反才是游戏里的 dir。
    # 所有偏移都先在**原版坐标系（y 向上）**里照抄，最后一步统一映射到桌宠
    # （y 向下）：(vx, vy) -> (zx + vx, zy - vy)。
    dx, dy = -float(sh.dir_x), 0.0
    perp_x, perp_y = -dy, dx            # Custom.PerpendicularVector(dir)
    zx, zy = sh.p_zero
    scale = float(getattr(sh, "door_scale", 1.0))
    # InitiateSprites: rotation = AimFromOneVectorToAnother(dir, zero)
    #   = atan2(-dir.y, -dir.x) → dir 朝右(+x) 时 180°，朝左 0°
    base = 180.0 if dx > 0.0 else 0.0

    def at_xy(ao, bo):
        return (zx + perp_x * ao + dx * bo, zy - (perp_y * ao + dy * bo))

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
