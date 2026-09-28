"""共享渲染原语：软绳/带状/三角网格/atlas sprite 绘制。"""
from __future__ import annotations
import math
import random as _random
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)
from PySide6.QtCore import QPointF, Qt

from ..core.units import clampf, lerp
from .pixelmode import aa_hint


def draw_rope(painter, points, widths, color) -> None:
    """沿点链画锥形软绳（尾巴/舌头）；points 根→尖，widths 各点全宽。"""
    n = len(points)
    if n < 2:
        return
    half = [w * 0.5 for w in widths]

    def normal(i):
        ax, ay = points[max(0, i - 1)]
        bx, by = points[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        return -dy / L, dx / L

    left, right = [], []
    for i, (cx, cy) in enumerate(points):
        nx, ny = normal(i)
        hw = half[i]
        left.append(QPointF(cx + nx * hw, cy + ny * hw))
        right.append(QPointF(cx - nx * hw, cy - ny * hw))

    path = QPainterPath()
    path.moveTo(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)            # 防自交留洞

    painter.save()
    aa_hint(painter)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*color) if not isinstance(color, QColor) else color)
    painter.drawPath(path)
    # 尖端圆帽
    tx, ty = points[-1]
    painter.drawEllipse(QPointF(tx, ty), half[-1], half[-1])
    painter.restore()


def blit(painter, atlas, element, x, y, rotation, scale_x, scale_y, color,
         ax=0.5, ay=0.5) -> None:
    """画 atlas sprite；锚点 (ax,ay) 归一化，钉在 (x,y)。"""
    key = atlas.find_atlas(element)
    if key is None:                                # 缺帧静默跳过
        return
    col = color if isinstance(color, QColor) else QColor(*color)
    pm = atlas.sprite(key, element, col)
    sw, sh = atlas.source_size(key, element)
    apx, apy = ax * sw, ay * sh
    painter.save()
    painter.translate(x, y)
    if rotation:
        painter.rotate(rotation)
    painter.scale(scale_x, scale_y)
    painter.drawPixmap(QPointF(-apx, -apy), pm)
    painter.restore()


def draw_fruit(painter, atlas, x, y, rot_deg, bites,
               flesh_color=(0, 0, 255), outline_color=(0, 0, 0),
               scalex=1.0, scaley=1.0) -> None:
    """果子两层叠加（A 底 / B 上），k=clamp(3-bites,0,2)。"""
    k = int(max(0, min(2, 3 - bites)))
    blit(painter, atlas, f"DangleFruit{k}A", x, y, rot_deg, scalex, scaley,
         outline_color, ax=0.5, ay=0.5)
    blit(painter, atlas, f"DangleFruit{k}B", x, y, rot_deg, scalex, scaley,
         flesh_color, ax=0.5, ay=0.5)


def draw_stone(painter, atlas, x, y, rot_deg, frame, color=(70, 72, 78), scale=1.0) -> None:
    """石头：Pebble1..14 帧，中心锚 (0.5,0.5)。"""
    blit(painter, atlas, frame, x, y, rot_deg, scale, scale, color, ax=0.5, ay=0.5)


def draw_stone_trail(painter, x, y, ux, uy, length, halfwidth, color, alpha) -> None:
    """抛石运动拖尾：宽端在石头、沿 -(ux,uy) 收成尖的半透明三角。"""
    nx, ny = -uy, ux
    tailx, taily = x - ux * length, y - uy * length
    poly = QPolygonF([QPointF(x + nx * halfwidth, y + ny * halfwidth),
                      QPointF(x - nx * halfwidth, y - ny * halfwidth),
                      QPointF(tailx, taily)])
    col = QColor(color if isinstance(color, QColor) else QColor(*color))
    col.setAlpha(alpha)
    painter.save()
    aa_hint(painter)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(col)
    painter.drawPolygon(poly)
    painter.restore()


def ribbon(painter, points, halfwidths, colors) -> None:
    """带状路径渲染：沿中心线挤出闭合多边形，线性渐变填充。"""
    n = len(points)
    if n < 2:
        return

    def normal(i):
        ax, ay = points[max(0, i - 1)]
        bx, by = points[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        return -dy / L, dx / L

    left, right = [], []
    for i, (cx, cy) in enumerate(points):
        nx, ny = normal(i)
        hw = halfwidths[i]
        left.append(QPointF(cx + nx * hw, cy + ny * hw))
        right.append(QPointF(cx - nx * hw, cy - ny * hw))

    path = QPainterPath()
    path.moveTo(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)        # 防自交留洞

    grad = QLinearGradient(QPointF(points[0][0], points[0][1]),
                           QPointF(points[-1][0], points[-1][1]))
    for i, c in enumerate(colors):
        grad.setColorAt(i / (n - 1), QColor(*c))

    painter.save()
    aa_hint(painter)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawPath(path)
    painter.restore()


def mesh(painter, verts, tris, vcolors, outline: bool = True) -> None:
    """逐三角填充三角网格（尾/舌）；vcolors 逐顶点色（三角取均值）。"""
    if not verts or not tris:
        return
    painter.save()
    aa_hint(painter)
    if not outline:
        painter.setPen(Qt.PenStyle.NoPen)
    n = len(verts)
    for (i, j, k) in tris:
        if i >= n or j >= n or k >= n:
            continue
        vi, vj, vk = verts[i], verts[j], verts[k]
        if vi is None or vj is None or vk is None:
            continue
        ci, cj, ck = vcolors[i], vcolors[j], vcolors[k]
        r = int((ci[0] + cj[0] + ck[0]) / 3.0)
        g = int((ci[1] + cj[1] + ck[1]) / 3.0)
        b = int((ci[2] + cj[2] + ck[2]) / 3.0)
        col = QColor(r, g, b)
        if outline:
            # 同色细描边封住 AA 接缝
            painter.setPen(QPen(col, 0.5))
        painter.setBrush(col)
        poly = QPolygonF([QPointF(vi[0], vi[1]),
                          QPointF(vj[0], vj[1]),
                          QPointF(vk[0], vk[1])])
        painter.drawPolygon(poly)
    painter.restore()

# ── 珍珠 / 矛 / 拾荒者：都用原版图集贴图 ──
# 原版：DataPearl = JetFishEyeA(珠体) + tinyStar(高光) + Futile_White(柔光)；
#       Spear = SmallSpear；Scavenger = Circle20 拼的圆滚身体 + ScavengerHandA/B。

SPEAR_DRAW_LEN = 46.0       # 与世界 Spear.LEN 一致
SPEAR_SPRITE = "SmallSpear"
SPEAR_ART_LEN = 53.0        # SmallSpear 贴图里杆本身的可视长度（像素）
SPEAR_TIP_PIVOT_Y = 0.85    # 原版：插住时以杆尖为轴（anchorY 0.85）
SPEAR_RGB = (27, 11, 33)    # 原版 Spear.ApplyPalette：color = palette.blackColor
PEARL_SPRITE = "JetFishEyeA"      # 原版珍珠本体（6x6 圆）
PEARL_ART_RAD = 3.0               # 本体贴图半径（像素），用于换算缩放
PEARL_STAR = "tinyStar"           # 原版高光小星
PEARL_STAR_OFF = (-0.5, 1.5)      # 原版高光相对珠心的偏移（像素）


def draw_pearl(painter, atlas, x, y, rot_deg=0.0, tint=(255, 255, 255), rad=4.5,
               glimmer=0.0) -> None:
    """珍珠：原版贴图 + 原版高光脉冲（glimmer 0..1：珠体与高光一起发亮）。"""
    k = rad / PEARL_ART_RAD
    body = _mix_rgb(tint, (255, 255, 255), glimmer)
    star = _mix_rgb(_scale_rgb(tint, 1.3), (255, 255, 255),
                    0.5 + 0.5 * glimmer)
    painter.save()
    aa_hint(painter)
    if glimmer > 0.01:                       # 柔光（原版 Futile_White + 0.5*num 透明度）
        g = QRadialGradient(QPointF(x, y), 10.0 * glimmer * k)
        g.setColorAt(0.0, QColor(tint[0], tint[1], tint[2], int(150 * glimmer)))
        g.setColorAt(1.0, QColor(tint[0], tint[1], tint[2], 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(g)
        painter.drawEllipse(QPointF(x, y), 10.0 * glimmer * k, 10.0 * glimmer * k)
    blit(painter, atlas, PEARL_SPRITE, x, y, rot_deg, k, k, body)
    blit(painter, atlas, PEARL_STAR, x + PEARL_STAR_OFF[0] * k, y + PEARL_STAR_OFF[1] * k,
         0.0, k, k, star)
    painter.restore()


def draw_spear(painter, atlas, x, y, ang_deg, length=46.0,
               tint=SPEAR_RGB, pivot_tip=False) -> None:
    """矛：原版 SmallSpear 贴图（白剪影按杆色染色）；ang 0=朝上、顺时针为正（y↓）。"""
    k = length / SPEAR_ART_LEN
    blit(painter, atlas, SPEAR_SPRITE, x, y, ang_deg, k, k, tint,
         ax=0.5, ay=SPEAR_TIP_PIVOT_Y if pivot_tip else 0.5)


def _scale_rgb(rgb, k):
    return (min(255, int(rgb[0] * k)), min(255, int(rgb[1] * k)), min(255, int(rgb[2] * k)))


def _mix_rgb(a, b, t):
    t = clampf(t, 0.0, 1.0)
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _ilerp(a, b, v):
    """原版 Mathf.InverseLerp（a>b 时反向，也 clamp 到 0..1）。"""
    if a == b:
        return 0.0
    return clampf((v - a) / (b - a), 0.0, 1.0)


def _lmap(v, a, b, A, B, e=1.0):
    """原版 Custom.LerpMap（带可选曲线指数）。"""
    if a == b:
        return A
    tt = clampf((v - a) / (b - a), 0.0, 1.0)
    if e != 1.0:
        tt = tt ** e
    return A + (B - A) * tt


CIRCLE_SPRITE = "Circle20"       # 原版拾荒者的髋/胸/头/眼都是 Circle20
SCAV_HAND_A = "ScavengerHandA"  # 原版手：张开
SCAV_HAND_B = "ScavengerHandB"  # 原版手：握持
SCAV_MASKS = ("KrakenMask", "SpikeMask", "HornedMask", "SadMask")  # 精英面具
SCAV_MASK_LAYERS = ((1.0, 1.0), (0.85, 0.9), (1.0, 1.1))  # 原版 3 片叠加

# 缺个体参数时的兜底（原版 IndividualVariations 中间值）
_IVAR_MID = {"head_size": 0.5, "fat": 0.5, "waist": 0.4, "eye_size": 0.55,
             "narrow_eyes": 0.0, "eyes_angle": 0.4, "pupil": 0.0, "deep": False,
             "pupil_hue": None, "hands": 1.0, "arm": 0.6, "legs": 0.5,
             "wide_teeth": 0.5, "elite": False, "mask": None}
SCAV_S = 0.72                    # 相对原版像素的整体缩放（与蜥蜴同一屏幕比例）
SCAV_HIP_R = 7.0 * SCAV_S         # 原版 bodyChunks[1].rad = 7
SCAV_CHEST_R = 9.5 * SCAV_S       # 原版 bodyChunks[0].rad = 9.5
SCAV_CHEST_DY = 18.0 * SCAV_S     # 原版 髋→胸 连接长度 18
SCAV_HEAD_DY = 22.0 * SCAV_S      # 原版 胸→头 连接长度 22

# 部件常量（锚点 (x, y) = 髋心，脚下 stance 为地面）
SCAV_STANCE = 7.0
SCAV_CHEST_W = 1.15              # 胸横向放大（原版 scaleX/scaleY 由 fatness/narrowWaist 定）
SCAV_HEAD_W = 1.0


def _tapered(painter, x0, y0, x1, y1, r0, r1, rgb) -> None:
    """锥形杆（原版拾荒者的腰/颈/臂都是 Futile_White 三角网格）。"""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    poly = QPolygonF([QPointF(x0 + nx * r0, y0 + ny * r0),
                      QPointF(x0 - nx * r0, y0 - ny * r0),
                      QPointF(x1 - nx * r1, y1 - ny * r1),
                      QPointF(x1 + nx * r1, y1 + ny * r1)])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*rgb))
    painter.drawPolygon(poly)


def _circle(painter, atlas, x, y, w, h, rgb, rot=0.0) -> None:
    """原版 Circle20 单帧按 (w, h) 像素画在 (x, y)。"""
    blit(painter, atlas, CIRCLE_SPRITE, x, y, rot, w / 20.0, h / 20.0, rgb)


# ══ 拾荒者：逐片复刻原版 ScavengerGraphics（InitiateSprites / DrawSprites / ApplyPalette）══
# 原版没有任何「画出来的脸」：髋/胸/头/眼是 Circle20，腰/颈/腹/齿/须/四肢全是
# Futile_White 三角网格。下面按原版公式重算顶点。
# 坐标系：原版世界 y↑ / 屏幕 y↓。这里全部用「游戏空间」(y↑, 单位 = 游戏像素 × SCAV_S)
# 算，最后统一翻转成屏幕坐标：  screen = (ox + gx, oy - gy)。
# FSprite 旋转：旋转角 = Custom.VecToDeg(v) = atan2(v.x, v.y)（0 = 上、顺时针），
# 与 Qt 的 QPainter.rotate 在 y↓ 屏幕下同号 —— 直接可用。


def _nrm(v):
    m = math.hypot(v[0], v[1])
    return (v[0] / m, v[1] / m) if m > 1e-9 else (0.0, 0.0)


def _perp(v):
    x, y = _nrm(v)
    return (-y, x)


def _dirvec(a, b):
    return _nrm((b[0] - a[0], b[1] - a[1]))


def _add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k)


def _vec_deg(v):
    """原版 Custom.VecToDeg（0 = 上、顺时针）；也是 FSprite.rotation 的 Qt 等价角。"""
    return math.degrees(math.atan2(v[0], v[1]))


def _dist_line(v, l2, l1):
    """原版 Custom.DistanceToLine。"""
    dy, dx = l2[1] - l1[1], l2[0] - l1[0]
    d = math.hypot(dy, dx)
    if d < 1e-9:
        return 0.0
    return (dy * v[0] - dx * v[1] + l2[0] * l1[1] - l2[1] * l1[0]) / d


def _rot_origo(v, deg):
    """原版 Custom.RotateAroundOrigo。"""
    a = -math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1])


def _slerp2(a, b, t):
    """原版 Vector3Ext.Slerp2（单位向量球面插值）。"""
    a, b = _nrm(a), _nrm(b)
    if t <= 0.0:
        return a
    if t >= 1.0:
        return b
    d = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
    th = math.acos(d)
    if th < 1e-4:
        return a
    s = math.sin(th)
    return _nrm(((a[0] * math.sin((1 - t) * th) + b[0] * math.sin(t * th)) / s,
                 (a[1] * math.sin((1 - t) * th) + b[1] * math.sin(t * th)) / s))


def _ik(va, vc, A, B, flip):
    """原版 Custom.InverseKinematic（两段等长肢体的肘/膝求解）。"""
    d = math.dist(va, vc)
    k = 0.0 if d < 1e-6 else (d * d + A * A - B * B) / (2.0 * d * A)
    ang = math.acos(max(0.2, min(0.98, k))) * flip
    t = math.radians(_vec_deg(_dirvec(va, vc))) + ang
    return (va[0] + math.sin(t) * A, va[1] + math.cos(t) * A)


def _long_mesh(pts, rads):
    """复刻 Futile TriangleMesh.MakeLongMesh：每点 4 顶点（前侧用平均半径）。
    顶点序： i*4=(前,左) i*4+1=(前,右) i*4+2=(本,左) i*4+3=(本,右)。"""
    verts, tris = [], []
    n = len(pts)
    for i in range(n):
        p, r = pts[i], rads[i]
        if i == 0:
            prev, pr, d = p, r, (0.0, 1.0)
            seg = 0.0
        else:
            prev, pr = pts[i - 1], rads[i - 1]
            d = _dirvec(prev, p)
            if d == (0.0, 0.0):
                d = (0.0, 1.0)
            seg = math.dist(prev, p) / 4.0
        nx, ny = _perp(d)
        mr = (pr + r) * 0.5
        verts.append((prev[0] - nx * mr - d[0] * seg, prev[1] - ny * mr - d[1] * seg))
        verts.append((prev[0] + nx * mr - d[0] * seg, prev[1] + ny * mr - d[1] * seg))
        verts.append((p[0] - nx * r + d[0] * seg, p[1] - ny * r + d[1] * seg))
        verts.append((p[0] + nx * r + d[0] * seg, p[1] + ny * r + d[1] * seg))
    for i in range(n - 1):
        b = i * 4
        for k in range(6):
            tris.append((b + k, b + k + 1, b + k + 2))
    return verts, tris


def _scav_head_dir(sc, flip):
    """原版 ScavengerGraphics.HeadDir（游戏空间，y↑）。

    0.2 * ClampMagnitude(注视点 - 胸, 300)/300 + ClampMagnitude(头 - 胸, 100)/100。
    头-胸 = 22 px 的连接，站立时头在胸的前上方，前倾约 40°。
    """
    axis = _nrm((0.90 * flip, 1.15))
    aim = getattr(sc, "aim", None)
    if aim is not None:
        # aim 是屏幕坐标 (y↓) → 换到游戏空间
        chest_y = sc.y - SCAV_CHEST_DY
        d = _nrm((aim[0] - sc.x, chest_y - aim[1]))
        if d != (0.0, 0.0):
            axis = _nrm((axis[0] + d[0] * 0.20 / 0.22, axis[1] + d[1] * 0.20 / 0.22))
    return axis


def _scav_mask(painter, atlas, name, x, y, rot, rgb, s) -> None:
    """原版 VultureMaskGraphics：同一帧 3 片叠出面具厚度（anchorY 逐层微移）。"""
    for i, (sx, sy) in enumerate(SCAV_MASK_LAYERS):
        blit(painter, atlas, name + "0", x, y, rot, sx * s, sy * s, rgb,
             ax=0.5, ay=0.5 + (0.015 if i == 2 else 0.0))


def _scav_eartler_branches(iv, rng):
    """原版 ScavengerGraphics.Eartlers.GenerateSegments（非精英）。"""
    elite = bool(iv.get("elite"))
    k = 1.75 if elite else 1.0
    lo, hi = (45.0, 90.0) if elite else (15.0, 45.0)
    n2 = 1.5 if elite else 1.0
    n3 = 2.0 if elite else 1.0
    n5 = 0.0 if elite else 1.0
    n6 = 2.0 if elite else 1.0
    n7 = 0.0 if elite else 1.0
    pts = []

    def deg(a):
        r = math.radians(a)
        return (math.sin(r), math.cos(r))

    def define(vl):
        pts.append(list(vl))
        pts.append([(-p[0], p[1],) + tuple(p[2:]) for p in vl])

    vl = [(0.0, 0.0, 1.0)]
    vl.append(_add(deg(lerp(40.0, 90.0, rng.random())), (0.0, 0.0), 0.4 * n2) + (1.0 * n3,))
    far = deg(lerp(lo, hi, rng.random()) * k)
    pos = _add(far, deg(lerp(40.0, 90.0, rng.random())), -0.4 * n2)
    if pos[0] < 0.2:
        pos = (lerp(pos[0], far[0], 0.4), pos[1])
    vl.append(pos + (1.5,))
    vl.append(far + (2.0 * n5,))
    define(vl)

    vl = [(pts[0][1][0], pts[0][1][1], 1.0)]
    nbranch = 2 if (math.dist(pts[0][1][:2], pts[0][2][:2]) > 0.6 and rng.random() < 0.5) else 1
    p3 = (lerp(pts[0][1][0], pts[0][2][0], lerp(0.0, 0.7 if nbranch == 1 else 0.25, rng.random())),
          lerp(pts[0][1][1], pts[0][2][1], lerp(0.0, 0.7 if nbranch == 1 else 0.25, rng.random())))
    vl.append(p3 + (1.2,))
    tip = _add(_add(p3, (pts[0][3][0] - pts[0][2][0], pts[0][3][1] - pts[0][2][1])),
               deg(rng.random() * 360.0), 0.1)
    vl.append(tip + (1.75,))
    define(vl)
    if nbranch == 2:
        vl = []
        p3 = (lerp(pts[0][1][0], pts[0][2][0], lerp(0.45, 0.7, rng.random())),
              lerp(pts[0][1][1], pts[0][2][1], lerp(0.45, 0.7, rng.random())))
        vl.append(p3 + (1.2,))
        tip = _add(_add(p3, (pts[0][3][0] - pts[0][2][0], pts[0][3][1] - pts[0][2][1])),
                   deg(rng.random() * 360.0), 0.1)
        vl.append(tip + (1.75,))
        define(vl)

    flag = rng.random() < 0.5 and not elite
    if flag:
        vl = []
        f4 = _add(deg(90.0 + lerp(-20.0, 20.0, rng.random())), (0.0, 0.0),
                  lerp(0.2, 0.5, rng.random()))
        if f4[1] > pts[0][1][1] - 0.1:
            f4 = (f4[0], f4[1] - 0.2)
        n9 = lerp(0.8, 2.0, rng.random())
        if rng.random() < 0.5:
            f4 = _add(f4, deg(lerp(120.0, 170.0, rng.random())), lerp(0.1, 0.3, rng.random()))
            vl.append((0.0, 0.0, n9))
            vl.append(f4 + (n9,))
        else:
            vl.append((0.0, 0.0, 1.0))
            vl.append(f4 + ((1.0 + n9) / 2.0,))
            vl.append(_add(f4, deg(lerp(95.0, 170.0, rng.random())),
                           lerp(0.1, 0.2, rng.random())) + (n9,))
        define(vl)

    if rng.random() > 0.25 or not flag or elite:
        vl = []
        n10 = 1.0 + rng.random() * 1.5
        flag2 = rng.random() < 0.5
        vl.append((0.0, 0.0, 1.0))
        n11 = lerp(95.0, 135.0, rng.random())
        n12 = lerp(0.25, 0.4, rng.random()) * n6
        vl.append(_add(deg(n11), (0.0, 0.0), n12) +
                  ((0.8 if flag2 else lerp(1.0, n10, 0.3)) * n6,))
        second = _add(deg(n11 + lerp(5.0, 35.0, rng.random())), (0.0, 0.0),
                      max(n12 + 0.1, lerp(0.3, 0.6, rng.random())))
        vl.append(second + ((0.8 if flag2 else lerp(1.0, n10, 0.6)),))
        last = _nrm(vl[-1][:2])
        r_last = math.hypot(vl[-1][0], vl[-1][1])
        vl.append(_add(last, (0.0, 0.0), r_last + lerp(0.15, 0.25, rng.random()) * n6) +
                  (n10 * n7,))
        define(vl)
    return pts


def _scav_eartlers(painter, atlas, iv, rng, org, head_g, f, f2, body_deg, s, head_rgb, deco_rgb):
    """原版 Eartlers.DrawSprites：从头部放射的须（细长网格，可染色尖端）。"""
    branches = _scav_eartler_branches(iv, rng)
    head_pos = head_g
    rotat = _vec_deg((-f2[0], -f2[1]))
    xsq = 1.0 - abs(_rot_origo((f[0], f[1]), body_deg)[0]) ** 1.5
    ysq = 1.0
    reach = lerp(15.0, 35.0, 0.5) * s
    tips = bool(iv.get("colored_eartler_tips"))
    ew = iv.get("eartler_width", 0.5)
    for br in branches:
        pos = [(_rot_origo((p[0] * xsq, p[1] * ysq), rotat)[0] * reach,
                _rot_origo((p[0] * xsq, p[1] * ysq), rotat)[1] * reach) for p in br]
        pos = [(_add(head_pos, q, 1.0)) for q in pos]
        verts, tris, cols = [], [], []
        prev = pos[0]
        a = _perp((br[1][0] - br[0][0], br[1][1] - br[0][1])) if len(br) > 1 else (0.0, 1.0)
        n3 = br[0][2] * s
        n = len(br)
        for j in range(n):
            cur = pos[j]
            d3 = _dirvec(prev, cur)
            if d3 == (0.0, 0.0):
                d3 = (0.0, 1.0)
            d4 = _perp(d3)
            n5 = math.dist(cur, prev) / 10.0
            n6 = lerp(1.0, 2.0, ew) * br[j][2] * s * lerp(0.5, 1.0, xsq)
            mit = _nrm((a[0] + d4[0], a[1] + d4[1]))
            if mit == (0.0, 0.0):
                mit = d4
            verts.append(_add(_add(prev, mit, -(n6 + n3) * 0.5), d3, -n5))
            verts.append(_add(_add(prev, mit, (n6 + n3) * 0.5), d3, -n5))
            last = (j == n - 1)
            if last:
                n6 /= 4.0
            verts.append(_add(_add(cur, d4, -n6), d3, n5))
            verts.append(_add(_add(cur, d4, n6), d3, n5))
            prev, a, n3 = cur, d4, n6
        for i in range(n - 1):
            b = i * 4
            for k in range(6):
                tris.append((b + k, b + k + 1, b + k + 2))
        tip_idx = (n - 1) * 4 + 2
        for i in range(len(verts)):
            cols.append(deco_rgb if (tips and i >= tip_idx) else head_rgb)
        mesh(painter, [_scr(q, org) for q in verts], tris, cols, outline=False)


def _scr(g, org):
    """游戏空间 → 屏幕坐标： (gx, gy) → (ox + gx, oy - gy)，org = 髋心。"""
    return (org[0] + g[0], org[1] - g[1])


def draw_scavenger(painter, atlas, sc, ts=1.0, body_rgb=None, head_rgb=None,
                   eye_rgb=None, leg_rgb=None, hand_rgb=None) -> None:
    """拾荒者：逐片复刻原版 ScavengerGraphics。锚点 = 髋心 (sc.x, sc.y)（髋在脚下上方）。"""
    hx = sc.last_x + (sc.x - sc.last_x) * ts
    hy = sc.last_y + (sc.y - sc.last_y) * ts
    org = (hx, hy)                     # 屏幕空间的髋心
    flip = 1.0 if sc.facing >= 0 else -1.0
    iv = getattr(sc, "ivar", None) or _IVAR_MID
    S = SCAV_S
    body_rgb = sc.body_rgb if body_rgb is None else body_rgb
    head_rgb = sc.head_rgb if head_rgb is None else head_rgb
    eye_rgb = sc.eye_rgb if eye_rgb is None else eye_rgb
    belly_rgb = getattr(sc, "belly_rgb", None) or _mix_rgb(body_rgb, head_rgb, 0.4)
    deco_rgb = getattr(sc, "deco_rgb", None) or _mix_rgb(body_rgb, head_rgb, 0.6)
    pupil_rgb = getattr(sc, "pupil_rgb", None) or (20, 20, 24)
    if leg_rgb is None:
        leg_rgb = body_rgb
    if hand_rgb is None:
        hand_rgb = _mix_rgb(body_rgb, head_rgb, iv.get("hands_head_color", 0.0))

    fat = iv.get("fat", 0.5)
    waist_w = fat * (1.0 - iv.get("waist", 0.4))          # 原版 iVars.WaistWidth
    narrow = iv.get("waist", 0.4)
    neck_t = iv.get("neck", 0.5)
    num11 = lerp(0.6, 1.1, iv.get("head_size", 0.5))       # 头片总缩放

    # ── 骨骼（游戏空间，原点 = 髋心）──
    lean = clampf(-sc.vx * 1.2, -3.0, 3.0)
    body_axis = _nrm((-0.05 * flip + lean * 0.02, 1.0))
    body_deg = -_vec_deg(body_axis)          # 原版 BodyAxis(t) 带负号
    chest_g = _add((0.0, 0.0), body_axis, 18.0 * S)
    head_axis = _scav_head_dir(sc, flip)
    head_g = _add(chest_g, head_axis, 22.0 * S)
    f = _nrm(head_axis)
    f2 = _nrm(((f[0] - body_axis[0]) * 0.5, (f[1] - body_axis[1]) * 0.5))
    if f2 == (0.0, 0.0):
        f2 = f
    waist_mid = (chest_g[0] * 0.5, chest_g[1] * 0.5)
    waist_mid = _add(waist_mid, _perp((0.0 - chest_g[0], 0.0 - chest_g[1])),
                     -lerp(5.0, 15.0, narrow) * flip * S)
    chest_rot = _vec_deg(_dirvec(chest_g, waist_mid))
    hip_pt = (0.0, 0.0)

    painter.save()
    aa_hint(painter)
    painter.setPen(Qt.PenStyle.NoPen)

    # ── 尾（原版 Tail：tailSegs 段，从髋向后下方垂）──
    nseg = int(iv.get("tail_segs", 0) or 0)
    if nseg > 0:
        tpts, trads = [], []
        cur = hip_pt
        d = (-flip * 0.9, -0.44)
        for i in range(nseg + 1):
            t = i / float(nseg)
            d = _nrm((d[0], d[1] - 0.05 * t))
            cur = _add(cur, d, 10.0 * S)
            tpts.append(cur)
            trads.append(lerp(2.0, 1.0, t) * S * 2.2)
        tv, tt = _long_mesh(tpts, trads)
        mesh(painter, [_scr(q, org) for q in tv], tt, [body_rgb] * len(tv), outline=False)

    # ── 背瘤（原版 HardBackSpikes / WobblyBackTufts）──
    for k in range(4):
        t = 0.18 + 0.24 * k
        base = (lerp(0.0, chest_g[0], t), lerp(0.0, chest_g[1], t))
        n = _perp(body_axis)
        r = lerp(9.5, 7.0, t) * S
        c = _add(_add(base, n, r * 0.85 * flip), (0.0, 0.0), 0.0)
        blit(painter, atlas, CIRCLE_SPRITE, *_scr(c, org), 0.0,
             (2.6 + 1.2 * (k % 2)) * S / 10.0, (2.6 + 1.2 * (k % 2)) * S / 10.0, body_rgb)

    # ── 腰（原版 WaistSprite：8 顶点 / 6 三角）──
    dv = _dirvec(waist_mid, chest_g)
    np_ = _perp(_dirvec(hip_pt, waist_mid))
    mid2 = ((waist_mid[0] + chest_g[0]) * 0.5, (waist_mid[1] + chest_g[1]) * 0.5)
    mid40 = (lerp(waist_mid[0], mid2[0], 0.4), lerp(waist_mid[1], mid2[1], 0.4))
    np2 = _perp((-dv[0], -dv[1]))
    wv = [_add(waist_mid, np_, (7.0 * S) * lerp(0.65, 0.9, waist_w)),
          _add(waist_mid, np_, -(7.0 * S) * lerp(0.65, 0.9, waist_w)),
          _add(_add(mid40, dv, -4.0 * S), np2, (9.5 * S) * lerp(0.35, 0.9, waist_w ** 1.3)),
          _add(_add(mid40, dv, -4.0 * S), np2, -(9.5 * S) * lerp(0.35, 0.9, waist_w ** 1.3)),
          _add(_add(mid40, dv, 4.0 * S), np2, (9.5 * S) * lerp(0.25, 0.8, waist_w ** 1.3)),
          _add(_add(mid40, dv, 4.0 * S), np2, -(9.5 * S) * lerp(0.25, 0.8, waist_w ** 1.3)),
          _add(chest_g, np_, (9.5 * S) * lerp(0.7, 1.3, fat)),
          _add(chest_g, np_, -(9.5 * S) * lerp(0.7, 1.3, fat))]
    wtris = [(k, k + 1, k + 2) for k in range(6)]
    mesh(painter, [_scr(q, org) for q in wv], wtris, [body_rgb] * len(wv), outline=False)

    # ── 髋 / 胸（原版 Circle20）──
    blit(painter, atlas, CIRCLE_SPRITE, *_scr(hip_pt, org), 0.0,
         14.0 * S / 20.0, 14.0 * S / 20.0, body_rgb)
    blit(painter, atlas, CIRCLE_SPRITE, *_scr(chest_g, org), chest_rot,
         (9.5 * S) * lerp(0.7, 1.3, fat) * 2.0 / 20.0,
         ((9.5 + lerp(2.0, 1.5, narrow)) * S) * 2.0 / 20.0, body_rgb,
         ax=0.5, ay=0.6 - 0.05 * narrow)

    # ── 腹斑（原版 ChestPatchSprite：8 顶点 / 6 三角）──
    shape = [(-0.25, 0.4), (0.25, 0.4), (-1.0, lerp(0.4, 0.95, 1.0 / 3.0)),
             (1.0, lerp(0.4, 0.95, 1.0 / 3.0)), (-1.0, lerp(0.4, 0.95, 2.0 / 3.0)),
             (1.0, lerp(0.4, 0.95, 2.0 / 3.0)), (-1.0 / 3.0, 0.95), (1.0 / 3.0, 0.95)]
    pv = []
    for (px_, py_) in shape:
        t = clampf((py_ - 0.4) / 0.6, 0.0, 1.0)
        base = (lerp(chest_g[0], hip_pt[0], t), lerp(chest_g[1], hip_pt[1], t))
        n = _perp(_dirvec(chest_g, hip_pt))
        half = lerp(9.5, 7.0, t) * S * 1.1
        pv.append(_add(base, n, clampf(px_ + flip, -1.0, 1.0) * half * 0.5))
    mesh(painter, [_scr(q, org) for q in pv], [(k, k + 1, k + 2) for k in range(6)],
         [_mix_rgb(belly_rgb, (27, 11, 33), 0.45)] * len(pv), outline=False)

    # ── 须（Eartlers）──
    rng = _random.Random(sc.seed * 7919 + 4241)
    _scav_eartlers(painter, atlas, iv, rng, org, head_g, f, f2, body_deg, S,
                   head_rgb, deco_rgb)

    # ── 齿（原版 TeethSprite：每齿 5 顶点三角网格）──
    nteeth = int(iv.get("teeth_n", 4))
    wide = iv.get("wide_teeth", 0.5)
    float14 = _add(head_g, f2, 4.0 * num11 * S)
    teeth = []
    n2 = lerp(0.5, 1.5, rng.random())
    n2 = lerp(n2, n2 * _lmap(nteeth, 4.0, 8.0, 1.0, 0.5), 0.3)
    aa = lerp(n2 + 0.2, lerp(0.7, 1.2, rng.random()), rng.random())
    aa = lerp(aa, _lmap(nteeth, 4.0, 8.0, 1.5, 0.2), 0.4)
    a2 = 0.3 + 0.7 * rng.random()
    for l in range(nteeth):
        num3 = l / float(nteeth - 1) if nteeth > 1 else 0.0
        s0 = lerp(a2, 1.0, math.sin(num3 * math.pi)) * n2
        s1 = lerp(0.5, 1.0, math.sin(num3 * math.pi)) * aa
        teeth.append((s0, s1))
    pp = _perp(f2)
    fx = _rot_origo(f2, body_deg)[0]
    tverts, ttris, tcols = [], [], []
    for m2 in range(nteeth):
        num18 = m2 / float(nteeth - 1) if nteeth > 1 else 0.0
        t0, t1 = teeth[m2]
        p17 = _add(_add(float14, f2, 4.0 * S), pp, lerp(-3.0, 3.0, num18) * fx * S)
        tail_off = lerp(lerp(-9.0, 9.0, num18) * lerp(0.5, 1.2, wide),
                        -2.0 * (1.0 if fx >= 0 else -1.0), 1.0 - abs(f2[1]))
        p18 = _add(_add(float14, f2, lerp(8.0, 10.0, math.sin(num18 * math.pi)) * t0 * S),
                   pp, tail_off * t0 * S)
        tail_off2 = lerp(lerp(-9.0, 9.0, num18) * lerp(0.5, 1.2, wide),
                         -15.0 * (1.0 if fx >= 0 else -1.0), 1.0 - abs(f2[1]))
        p19 = _add(_add(float14, f2, lerp(12.0, 15.0, math.sin(num18 * math.pi)) * t0 * S),
                   pp, tail_off2 * t0 * S)
        d1 = _perp(_dirvec(p17, p18))
        d2 = _perp(_dirvec(p18, p19))
        tverts.append(_add(p17, d1, -1.0 * S))
        tverts.append(_add(p17, d1, 1.0 * S))
        tverts.append(_add(p18, d2, -t1 * S))
        tverts.append(_add(p18, d2, t1 * S))
        tverts.append(p19)
        for k in range(3):
            ttris.append((m2 * 5 + k, m2 * 5 + k + 1, m2 * 5 + k + 2))
    mesh(painter, [_scr(q, org) for q in tverts], ttris, [head_rgb] * len(tverts), outline=False)

    # ── 头（Circle20，长轴沿 f2）──
    head_rot = _vec_deg(f2)
    blit(painter, atlas, CIRCLE_SPRITE, *_scr(head_g, org), head_rot,
         16.0 * num11 * S / 20.0, 22.0 * num11 * S / 20.0, head_rgb)

    # ── 眼（原版 EyeSprite(j,0) 圆 + EyeSprite(j,1) 瞳孔）──
    eye_size = clampf(iv.get("eye_size", 0.55), 0.0, 1.0)
    narrow_eye = iv.get("narrow_eyes", 0.0)
    num14 = clampf(eye_size + 0.5, 0.0, 1.0)
    f12 = _rot_origo(f2, body_deg)
    float15 = _add(float14, f2, lerp(-5.0, 60.0, iv.get("eyes_angle", 0.4)))
    pupil_sz = iv.get("pupil", 0.0)
    for j in (0, 1):
        val = clampf((-1.0 if j == 0 else 1.0) * 0.5 + f12[0], -1.0, 1.0)
        p16 = _add(float14, _perp(f2), 8.0 * num11 * S * val)
        num15 = _vec_deg(_dirvec(p16, float15))
        num16 = (lerp(1.5, 2.0, 0.0) * lerp(0.3, 1.5, num14 ** 0.7) * 1.2
                 * _ilerp(1.0, 0.7, abs(val))
                 * lerp(1.0, lerp(0.5, 0.25, num14), narrow_eye * 0.5))
        num17 = lerp(2.5, 1.5, 1.0) * lerp(0.3, 1.5, num14 ** 0.7) * 1.2
        blit(painter, atlas, CIRCLE_SPRITE, *_scr(p16, org), num15,
             num16 * 0.1, num17 * 0.1, eye_rgb)
        if pupil_sz > 0.0:
            vv = _rot_origo((-f[0], -f[1]) if iv.get("deep") else f2, num15)
            vv = (vv[0] * num16 * (1.0 - pupil_sz), vv[1] * num17 * (1.0 - pupil_sz))
            vv = _rot_origo(vv, -num15)
            blit(painter, atlas, CIRCLE_SPRITE, *_scr(_add(p16, vv, 0.5 * S), org), num15,
                 num16 * 0.1 * pupil_sz, num17 * 0.1 * pupil_sz, pupil_rgb)

    # ── 四肢：远侧（后肢/后手）→ 髋胸 → 近侧 ──
    ground_g = (0.0, -SCAV_STANCE)
    phase = sc.walk_phase * math.tau
    moving = clampf(abs(sc.vx) * 0.6, 0.0, 1.0)
    for limb in (1, 0):
        sgn = -1.0 if limb == 0 else 1.0
        swing = math.sin(phase + (0.0 if limb == 0 else math.pi)) * 3.0 * moving
        foot = (ground_g[0] + sgn * 2.5 * flip + swing * flip,
                ground_g[1] + (3.0 * moving if swing > 0 else 0.0))
        _scav_leg(painter, atlas, org, hip_pt, foot, flip, S, leg_rgb,
                  leg_t=iv.get("legs", 0.5))

    arm_t = iv.get("arm", 0.6)
    spear = getattr(sc, "spear", None)
    _ = arm_t
    for limb in (1, 0):
        sgn = -1.0 if limb == 0 else 1.0
        sh = _add(_add(chest_g, body_axis, 5.0 * S), _perp(body_axis), sgn * 2.0 * S)
        if limb == 0 and spear is not None:
            tgt = (spear.x - hx, hy - spear.y)
        else:
            tgt = (sh[0] - sgn * 1.5 * flip, sh[1] - 30.0 * S)
        reach = 35.0 * S
        if math.dist(sh, tgt) > reach:
            tgt = _add(sh, _dirvec(sh, tgt), reach)
        _scav_hand(painter, atlas, org, sh, tgt, flip, S, body_rgb, hand_rgb,
                   gripping=(limb == 0 and spear is not None), arm_t=arm_t)

    # ── 颈（原版 NeckSprite：16 顶点长网格，体色→头色渐变）──
    npts, nrads = [], []
    start = _add(chest_g, _dirvec(waist_mid, chest_g), 5.0 * S)
    for i in range(4):
        t = i / 3.0
        p = (lerp(start[0], head_g[0], t), lerp(start[1], head_g[1], t))
        bulge = math.sin(t * math.pi) * lerp(0.5, 1.5, neck_t) * 2.0
        p = _add(p, _perp(_dirvec(start, head_g)), -bulge * S * flip)
        npts.append(p)
        nrads.append((lerp(7.0, 3.0, t) - 2.0 * bulge) * S * 0.5)
    nv, nt = _long_mesh(npts, nrads)
    ncols = []
    for i in range(4):
        c0 = _mix_rgb(body_rgb, head_rgb, clampf((i - 0.5) / 3.0, 0.0, 1.0))
        c1 = _mix_rgb(body_rgb, head_rgb, clampf(i / 3.0, 0.0, 1.0))
        ncols += [c0, c0, c1, c1]
    mesh(painter, [_scr(q, org) for q in nv], nt, ncols, outline=False)

    # ── 精英面具 ──
    if iv.get("mask"):
        mask_rgb = getattr(sc, "mask_rgb", None) or (206, 200, 186)
        _scav_mask(painter, atlas, iv["mask"], *_scr(head_g, org),
                   _vec_deg((-f[0], -f[1])), mask_rgb, S)

    painter.restore()


def _scav_leg(painter, atlas, org, hip_g, foot_g, flip, s, leg_rgb, leg_t=0.5) -> None:
    """原版 ScavengerLeg：髋→脚的两段 IK + 12 顶点网格。"""
    n2 = lerp(1.0, 1.4, leg_t)
    seg = lerp(20.0, 40.0, leg_t) * s * 0.5
    if math.dist(hip_g, foot_g) < 3.0 * n2 * s:
        foot_g = _add(hip_g, _dirvec(hip_g, foot_g), 3.0 * n2 * s)
    f3 = _add(foot_g, _dirvec(foot_g, hip_g), 1.5 * n2 * s)
    f4 = _ik(hip_g, f3, seg * n2, seg * n2, flip)
    mid = ((hip_g[0] + foot_g[0]) * 0.5, (hip_g[1] + foot_g[1]) * 0.5)
    f5 = (lerp((hip_g[0] + f4[0] + f3[0]) / 3.0, (hip_g[0] + f3[0]) * 0.5, 0.35),
          lerp((hip_g[1] + f4[1] + f3[1]) / 3.0, (hip_g[1] + f3[1]) * 0.5, 0.35))
    sup = lerp(3.0, 1.0, clampf(_ilerp(10.0 * n2 * s, 30.0 * n2 * s,
                                               math.dist(hip_g, f3)), 0.0, 1.0)) * n2 * s
    dhi = _perp(_dirvec(hip_g, f4))
    v = [_add(hip_g, dhi, 2.0 * n2 * s),
         _add(hip_g, dhi, -2.0 * n2 * s),
         f5,
         _add(f4, _dirvec(hip_g, f3), -3.0 * n2 * s),
         _add(f4, _dirvec(hip_g, f3), 3.0 * n2 * s),
         _add(f3, _nrm((_dirvec(f4, f3)[0] + _dirvec(f4, hip_g)[0],
                        _dirvec(f4, f3)[1] + _dirvec(f4, hip_g)[1])), -sup)]
    db = _dirvec(foot_g, hip_g)
    d32 = _perp(_dirvec(f3, foot_g))
    v += [_add(f3, db, 0.8 * n2 * s),
          _add(f3, db, -0.8 * n2 * s),
          _add(foot_g, d32, -0.8 * n2 * s),
          _add(foot_g, d32, 0.8 * n2 * s),
          _add(_add(foot_g, d32, -0.7 * n2 * s), _dirvec(f3, foot_g), 2.0 * n2 * s),
          _add(_add(foot_g, d32, 1.2 * n2 * s), _dirvec(f3, foot_g), 2.0 * n2 * s)]
    tris = [(0, 1, 2), (1, 2, 3), (3, 4, 2), (4, 2, 5), (2, 5, 6), (5, 6, 7),
            (5, 7, 8), (8, 7, 9), (8, 9, 10), (8, 9, 11)]
    mesh(painter, [_scr(q, org) for q in v], tris, [leg_rgb] * len(v), outline=False)


def _scav_hand(painter, atlas, org, sh_g, tgt_g, flip, s, body_rgb, hand_rgb,
               gripping=False, arm_t=0.6) -> None:
    """原版 ScavengerHand.DrawSprites：肩→手两段 IK + 19 顶点网格 + ScavengerHandA/B。"""
    f = tgt_g                                     # 原版 float2：手的目标点
    f3 = _add(f, _dirvec(f, sh_g), 6.0 * s)       # 原版 float3：腕
    if math.dist(f3, sh_g) < 5.0 * s:
        f3 = _add(sh_g, _dirvec(sh_g, f3), 5.0 * s)
    f4 = _ik(sh_g, f3, 18.0 * s, 18.0 * s, flip)  # 原版 float4：肘
    num = -(1.75 + lerp(-1.0, 1.0, arm_t)) * (1.0 if flip >= 0 else -1.0) * s
    v = [None] * 19
    prev_anchor, prev_perp = sh_g, _perp(_dirvec(sh_g, sh_g))
    prev_perp = _perp(_dirvec((0.0, 0.0), sh_g))
    for i in range(4):
        cur = (sh_g, f4, f3, f)[i]
        d8 = _dirvec(prev_anchor, cur)
        if d8 == (0.0, 0.0):
            d8 = (0.0, 1.0)
        d9 = _perp(d8)
        d = math.dist(cur, prev_anchor)
        if i == 0:
            v[0] = prev_anchor
            v[18] = _add(_add(cur, prev_perp, -num * 2.0), d8, -d * 0.2)
            v[1] = ((lerp(cur[0] + _nrm((d9[0] + prev_perp[0], d9[1] + prev_perp[1]))[0] * num * 2.0
                          - d8[0], prev_anchor[0], 0.5)),
                    (lerp(cur[1] + _nrm((d9[0] + prev_perp[0], d9[1] + prev_perp[1]))[1] * num * 2.0
                          - d8[1], prev_anchor[1], 0.5)))
        elif i == 1:
            v[17] = _add(prev_anchor, _nrm((d9[0] * 2.0 + prev_perp[0], d9[1] * 2.0 + prev_perp[1])),
                         -num * 2.0)
            v[16] = _add(_add(cur, d9, -num), d8, -d * 0.8)
            v[15] = _add(_add(cur, d9, -num * 2.5), d8, -d * 0.5)
            v[2] = _add(_add(cur, d9, num * 2.5), d8, -d * 0.5)
            v[14] = _add(_add(cur, d9, -num), d8, -d * 0.2)
            v[3] = _add(_add(cur, d9, num * 1.6), d8, -d * 0.2)
        elif i == 2:
            v[13] = _add(prev_anchor, _nrm((d9[0] + prev_perp[0], d9[1] + prev_perp[1])), -num * 2.0)
            v[4] = _add(prev_anchor, _slerp2(d9, prev_perp, 0.7), num * 2.0)
            v[12] = _add(_add(cur, d9, -num * 1.3), d8, -d * 0.8)
            v[5] = _add(prev_anchor, _slerp2(d9, prev_perp, 0.3), num * 2.0)
            v[11] = _add(_add(cur, d9, -num * 1.5), d8, -d * 0.65)
            v[6] = _add(_add(cur, d9, num * 1.5), d8, -d * 0.65)
        else:
            m = _nrm((d9[0] + prev_perp[0], d9[1] + prev_perp[1]))
            v[10] = _add(prev_anchor, m, -num)
            v[7] = _add(prev_anchor, m, num)
            v[9] = _add(cur, d9, -num)
            v[8] = _add(cur, d9, num)
        prev_anchor, prev_perp = cur, d9
    v = [sh_g if q is None else q for q in v]
    tris = [(0, 18, 1), (18, 17, 1), (16, 17, 1), (1, 15, 16), (1, 2, 15), (14, 2, 15),
            (3, 2, 14), (14, 3, 13), (4, 3, 13), (12, 4, 13), (4, 12, 5), (11, 12, 5),
            (11, 6, 5), (11, 6, 10), (7, 6, 10), (7, 9, 10), (7, 9, 8)]
    hand_col = _mix_rgb(body_rgb, hand_rgb, 0.85)
    mesh(painter, [_scr(q, org) for q in v], tris, [body_rgb] * len(v), outline=False)
    blit(painter, atlas, SCAV_HAND_B if gripping else SCAV_HAND_A,
         *_scr(f3, org), _vec_deg(_dirvec(f3, f)), -num * 2.0 * 3.0 / 18.0, 1.0,
         hand_col, ax=0.5, ay=1.0)


def draw_scavenger_spear(painter, atlas, sc, ts=1.0) -> None:
    """拾荒者手里的矛（原版 SmallSpear，瞄准时后仰）。"""
    sp = getattr(sc, "spear", None)
    if sp is None:
        return
    x = sp.last_x + (sp.x - sp.last_x) * ts
    y = sp.last_y + (sp.y - sp.last_y) * ts
    ang = sp.last_angle + (sp.angle_deg - sp.last_angle) * ts
    draw_spear(painter, atlas, x, y, ang, length=SPEAR_DRAW_LEN)
