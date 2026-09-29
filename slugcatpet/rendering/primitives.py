"""共享渲染原语：软绳/带状/三角网格/atlas sprite 绘制。"""
from __future__ import annotations
import math
import random as _random
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient, QTransform)
from PySide6.QtCore import QPointF, QRectF, Qt

from ..core.units import clampf, lerp
from .pixelmode import aa_hint, pen_width


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
            # 同色描边封住三角接缝；像素模式下抬到 1px，避免半透明毛边
            painter.setPen(QPen(col, pen_width(0.5)))
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
               tint=SPEAR_RGB) -> None:
    """矛：原版 SmallSpear 贴图（白剪影按杆色染色）；ang 0=朝上、顺时针为正（y↓）。

    锚点恒为杆中点（与 Spear.tip()/butt() 的世界系一致）：贴图尖端在图像顶部，
    所以角度方向即尖端方向。
    """
    k = length / SPEAR_ART_LEN
    blit(painter, atlas, SPEAR_SPRITE, x, y, ang_deg, k, k, tint, ax=0.5, ay=0.5)


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
SCAV_HAND_A = "ScavengerHandA"   # 原版手：张开
SCAV_HAND_B = "ScavengerHandB"   # 原版手：握持
SCAV_MASKS = ("KrakenMask", "SpikeMask", "HornedMask", "SadMask")  # 精英面具
SCAV_MASK_LAYERS = ((1.0, 1.0), (0.85, 0.9), (1.0, 1.1))          # 原版 3 片叠加

# 缺个体参数时的兜底（原版 IndividualVariations 中间值）
_IVAR_MID = {"head_size": 0.5, "fat": 0.5, "waist": 0.4, "eye_size": 0.55,
             "narrow_eyes": 0.0, "eyes_angle": 0.4, "pupil": 0.0, "deep": False,
             "pupil_hue": None, "hands": 1.0, "arm": 0.6, "legs": 0.5,
             "wide_teeth": 0.5, "elite": False, "mask": None, "neck": 0.5,
             "tail_segs": 0, "eartler_width": 0.5, "colored_eartler_tips": False,
             "general_melanin": 0.5, "scruffy": 1.0, "hands_head_color": 0.5,
             "teeth": [(1.0, 1.0), (1.0, 1.0), (1.0, 1.0), (1.0, 1.0)]}

SCAV_S = 1.0                     # 与游戏像素 1:1（同蜥蜴/蛞蝓猫）
SCAV_HIP_RAD = 7.0               # Scavenger.cs:1611 bodyChunks[1].rad
SCAV_CHEST_RAD = 9.5             # Scavenger.cs:1610 bodyChunks[0].rad
SCAV_HEAD_RAD = 5.0              # Scavenger.cs:1612 bodyChunks[2].rad
SCAV_LINK_HIP = 18.0             # :1614 髋→胸 连接距离
SCAV_LINK_HEAD = 22.0            # :1615 胸→头 连接距离
SCAV_HIP_R = SCAV_HIP_RAD * SCAV_S
SCAV_CHEST_R = SCAV_CHEST_RAD * SCAV_S
SCAV_CHEST_DY = SCAV_LINK_HIP * SCAV_S
SCAV_HEAD_DY = SCAV_LINK_HEAD * SCAV_S

SCAV_STANCE = 20.0               # 站立时髋心离地（腿两段 10*num2 = 20~28）
SCAV_LEAN = 52.0                 # 髋→胸 与竖直夹角（度）：躯干前倾成「驼峰」
SCAV_HEAD_TILT = 118.0           # 胸→头 基准夹角（度，>90 = 前下方）
SCAV_HEAD_UP = 44.0              # lookUp 抬头量（度）
SCAV_HEAD_LOOK = 0.35            # 头朝视线点偏转比例
SCAV_ARM_SEG = 18.0              # InverseKinematic(shoulder, wrist, 18, 18)
SCAV_ARM_REACH = 30.0            # StandStill：手伸到躯干前 30
SCAV_ARM_LEN = 50.0              # 手离胸最远 50
SCAV_SPEAR_OUT = 20.0            # ItemPosition(grasp 0) = 手 + WeaponDir*20
# 原版 chestPatchShape（8 点，OnBellySurfacePos 的脊柱坐标）
_SCAV_CHEST_PATCH = ((-0.25, 0.4), (0.25, 0.4),
                     (-1.0, 0.4 + 0.55 / 3.0), (1.0, 0.4 + 0.55 / 3.0),
                     (-1.0, 0.4 + 1.1 / 3.0), (1.0, 0.4 + 1.1 / 3.0),
                     (-1.0 / 3.0, 0.95), (1.0 / 3.0, 0.95))
# LizardScaleA* 贴图高（原版 scaleGrafHeight）：scaleY = 尖长 / 贴图高
_SCAV_SCALE_H = {0: 18.0, 1: 14.0, 2: 10.0, 3: 18.0, 4: 37.0, 5: 29.0, 6: 17.0}


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


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


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


def _mesh_long_tris(npts, nverts):
    """Futile TriangleMesh.MakeLongMesh 的三角表（每段 6 个）。"""
    tris = []
    for i in range(npts - 1):
        b = i * 4
        for k in range(6):
            tris.append((b + k, b + k + 1, b + k + 2))
    return tris


def _long_mesh(pts, rads, pointy=False):
    """复刻 Futile TriangleMesh.MakeLongMesh：每点 4 顶点（前侧用平均半径）。
    顶点序： i*4=(前,左) i*4+1=(前,右) i*4+2=(本,左) i*4+3=(本,右)。
    pointy=True 时末点收成一点（原版 pointyTip）。"""
    verts = []
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
        if pointy and i == n - 1:
            verts.append(p)
            verts.append(p)
        else:
            verts.append((p[0] - nx * r + d[0] * seg, p[1] - ny * r + d[1] * seg))
            verts.append((p[0] + nx * r + d[0] * seg, p[1] + ny * r + d[1] * seg))
    return verts, _mesh_long_tris(n, len(verts))


def _lerp2(a, b, t):
    """原版 math.lerp(float2, float2, t)：线性插值（不归一化）。"""
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _deg2flt(deg):
    """原版 Custom.DegToFloat2。"""
    r = math.radians(deg)
    return (math.sin(r), math.cos(r))


def _clamp_mag(v, m):
    """原版 ClampMagnitude。"""
    d = math.hypot(v[0], v[1])
    if d > m > 1e-9:
        return (v[0] * m / d, v[1] * m / d)
    return v


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _sgn(v):
    return 1.0 if v >= 0.0 else -1.0


def _scr(g, org):
    """游戏空间 → 屏幕坐标： (gx, gy) → (ox + gx, oy - gy)，org = 髋心。"""
    return (org[0] + g[0], org[1] - g[1])


class _ScavSpine:
    """原版 ScavengerGraphics 的 5 点脊线（drawPositions）与 OnSpine* 取点。"""

    def __init__(self, d, flip, iv):
        self.d = list(d)
        self.flip = flip
        self.n = len(self.d)
        self.neck = iv.get("neck", 0.5)
        self.fat = iv.get("fat", 0.5)
        self.waist_w = self.fat * (1.0 - iv.get("waist", 0.4))
        self.length = sum(math.dist(self.d[i], self.d[i + 1])
                          for i in range(self.n - 1))
        self._dtdot = None

    def seg_pos(self, i):
        if i == 0:
            p = self.d[0]
            num = _ilerp(0.0, 10.0, _dist_line(p, self.d[4], self.d[2]) * (-self.flip))
            return _add(p, _perp(_dirvec(self.d[0], self.d[1])), 5.0 * num * self.flip)
        return self.d[i]

    def seg_dir(self, i):
        if i > self.n - 2:
            return _dirvec(self.seg_pos(self.n - 2), self.seg_pos(self.n - 1))
        return _dirvec(self.seg_pos(i), self.seg_pos(i + 1))

    def seg_perp(self, i):
        if i == 0:
            f = _dot(self.seg_dir(0), self.seg_dir(1))
            a = _perp(self.seg_dir(0))
            return _slerp2((a[0] * _sgn(f), a[1] * _sgn(f)), self.seg_perp(1),
                           _ilerp(0.5, 1.0, 1.0 - abs(f)))
        return _perp(self.seg_dir(i))

    def seg_width(self, i):
        if i == 0:
            f = _dot(self.seg_dir(0), self.seg_dir(1))
            return 4.0 * lerp(0.5, 1.5, self.neck) * abs(_sgn(f))
        if i == 1:
            return lerp(8.0, 18.0, self.fat)
        if i == 2:
            return lerp(10.0, 20.0, self.fat)
        if i == 3:
            return lerp(4.0, 8.0, self.waist_w)
        return 10.0

    def index(self, f):
        num = f * self.length
        a = 0.0
        num2 = math.dist(self.d[0], self.d[1])
        i = 0
        while num2 < num:
            a = num2
            i += 1
            if i >= self.n - 1:
                break
            num2 += math.dist(self.d[i], self.d[i + 1])
        return i + _ilerp(a, num2, num)

    def _frac(self, f):
        num = self.index(clampf(f, 0.0, 1.0))
        fl = math.floor(num)
        i = max(0, min(self.n - 1, int(fl)))
        j = max(0, min(self.n - 1, i + 1))
        return i, j, num - fl

    def pos(self, f):
        i, j, fr = self._frac(f)
        return _lerp2(self.seg_pos(i), self.seg_pos(j), fr)

    def dir(self, f):
        i, j, fr = self._frac(f)
        return _slerp2(self.seg_dir(i), self.seg_dir(j), _ilerp(0.5, 1.0, fr))

    def perp(self, f):
        i, j, fr = self._frac(f)
        return _slerp2(self.seg_perp(i), self.seg_perp(j), _ilerp(0.5, 1.0, fr))

    def width(self, f):
        i, j, fr = self._frac(f)
        return lerp(self.seg_width(i), self.seg_width(j), _ilerp(0.5, 1.0, fr))

    def dtdot(self):
        if self._dtdot is None:
            self._dtdot = _dot(self.seg_dir(0), self.seg_dir(1))
        return self._dtdot

    def seg_up(self, i, dt):
        if i == 0:
            a = _perp(self.seg_dir(0))
            a = (a[0] * -_sgn(self.flip), a[1] * -_sgn(self.flip))
            f = _dist_line(self.seg_pos(0), self.seg_pos(1), self.seg_pos(2))
            b = _sgn(f) * _sgn(self.flip)
            return _slerp2((a[0] * b, a[1] * b),
                           (-self.seg_dir(1)[0], -self.seg_dir(1)[1]), abs(dt))
        a = _perp(self.seg_dir(i))
        return (a[0] * -_sgn(self.flip), a[1] * -_sgn(self.flip))

    def seg_dir_ups(self, i):
        if i == 0:
            return self.seg_dir(1)
        return self.seg_dir(i)

    def dir_for_ups(self, f):
        i, j, fr = self._frac(f)
        return _slerp2(self.seg_dir_ups(i), self.seg_dir_ups(j), _ilerp(0.5, 1.0, fr))

    def up_dir(self, f):
        dt = self.dtdot()
        i, j, fr = self._frac(f)
        base = _slerp2(self.seg_up(i, dt), self.seg_up(j, dt), clampf(fr, 0.0, 1.0))
        back = self.dir_for_ups(f)
        return _slerp2(base, (-back[0], -back[1]), 1.0 - abs(self.flip))

    def _seg_out(self, i, dt):
        if i == 0:
            a = _perp(self.seg_dir(0))
            b = _perp(self.seg_dir(1))
            return _slerp2(b, (a[0] * _sgn(dt), a[1] * _sgn(dt)), abs(dt) ** 3)
        if i > self.n - 2:
            return _perp(_dirvec(self.seg_pos(self.n - 2), self.seg_pos(self.n - 1)))
        return _perp(self.seg_dir(i))

    def out_dir(self, rel):
        """原版 OnSpineOutwardsDir：背表面朝外的侧向方向。"""
        x = clampf(rel[0] - self.flip, -1.0, 1.0)
        dt = self.dtdot()
        i, j, fr = self._frac(rel[1])
        v = _slerp2(self._seg_out(i, dt), self._seg_out(j, dt), fr)
        v = (v[0] * _sgn(x), v[1] * _sgn(x))
        return _slerp2(v, (rel[1], 1.0), (1.0 - abs(x)) ** 3)

    def back_pos(self, rel):
        """原版 OnBackSurfacePos。"""
        x = clampf(rel[0] - self.flip, -1.0, 1.0)
        return _add(self.pos(rel[1]), self.perp(rel[1]), self.width(rel[1]) * 0.5 * x)

    def belly_pos(self, rel):
        """原版 OnBellySurfacePos。"""
        x = clampf(rel[0] + self.flip, -1.0, 1.0)
        y = lerp(rel[1], 1.0, _lmap(self.dtdot(), 1.0, -1.0, 0.0, 0.5))
        return _add(self.pos(y), self.perp(y), self.width(y) * 0.5 * x)


def scav_pose(sc, ts=1.0, iv=None):
    """骨架（游戏空间 y↑，原点 = 髋心 = 原版 drawPositions[4]）。

    原版 髋/胸/头 是三个 BodyChunk 物理悬垂：
      髋 = 腿撑着（离地 20），胸 = 髋 + 18 沿身体轴，头 = 胸 + 22 朝视线方向（Pull 连接）。
    桌宠没有那套物理，这里用同样的链长与连接关系直接摆位；
    d[1]/d[3] 仍按原版 drawPositions 公式算，头/眼/齿/须全部由这条路走出来。
    """
    hx = sc.last_x + (sc.x - sc.last_x) * ts
    hy = sc.last_y + (sc.y - sc.last_y) * ts
    iv = iv or getattr(sc, "ivar", None) or _IVAR_MID
    flip = lerp(float(getattr(sc, "last_flip", None) or getattr(sc, "flip", 1.0)),
                float(getattr(sc, "flip", 1.0)), ts)
    face = 1.0 if float(getattr(sc, "facing", 1)) >= 0 else -1.0

    num10 = lerp(float(getattr(sc, "last_neutral", 0.0)),
                 float(getattr(sc, "neutral", 0.0)), ts)
    num9 = lerp(float(getattr(sc, "last_look_up", 0.0)),
                float(getattr(sc, "look_up", 0.0)), ts) * (1.0 - num10)
    num11 = lerp(0.6, 1.1, iv.get("head_size", 0.5))
    moving = 1.0 if abs(getattr(sc, "vx", 0.0)) > 0.15 else 0.0
    cycle = float(getattr(sc, "walk_phase", 0.0)) % 1.0
    bob = math.sin(cycle * math.tau) * 0.9 * moving

    # 转身：原版 chest/head 是物理块，靠 flip（Lerp 0.1/tick，由视线方向驱动）连续摆过去，
    # 没有任何按 facing 的突跳。这里同样用 flip 当前倾方向：flip 过 0 时身体先立正、
    # 再朝另一侧压下去 —— 就是「支起上半身把身子转过去」的观感（用 face 会瞬间镜像）。
    lean = flip
    hip = (0.0, 0.0)
    chest = _add(hip, _deg2flt(lean * SCAV_LEAN), SCAV_LINK_HIP)
    chest = (chest[0], chest[1] + bob + float(getattr(sc, "rise_body", 0.0)))
    # 原版 :1560：胸被「视线点」推开（看近处时上身后仰）
    lp = getattr(sc, "look_screen", None) or (hx + face * 90.0, hy - 26.0)
    look_g = (lp[0] - hx, hy - lp[1])
    push = _dirvec(look_g, chest)
    chest = _add(chest, push, _lmap(math.dist(look_g, chest), 50.0, 400.0, 11.0, 0.0, 0.5))

    # 头：朝向视线点（原版 :1957 WeightedPush(2,0, chunk0 + HeadLookDir*22, ...)）
    base_hd = _deg2flt(lean * (SCAV_HEAD_TILT - SCAV_HEAD_UP * num9))
    ld = _dirvec(chest, look_g)
    hd = _slerp2(base_hd, ld, SCAV_HEAD_LOOK) if ld != (0.0, 0.0) else base_hd
    head = _add(chest, hd, SCAV_LINK_HEAD)

    d = [None] * 5
    d[0] = head
    d[2] = chest
    d[4] = hip
    # :1578-1580  d[3] = mid - Perp(hip-chest)*lerp(5,15,waist)*flip → 朝髋心收 0.25
    d3 = _lerp2(d[2], d[4], 0.5)
    d3 = _add(d3, _perp(_sub(d[4], d[2])), -lerp(5.0, 15.0, iv.get("waist", 0.4)) * flip)
    d[3] = _lerp2(d3, d[4], 0.25)
    # :1581  d[1] = 胸 + DirVec(d[3], d[2]) * 8
    d[1] = _add(chest, _dirvec(d[3], d[2]), 8.0)

    raw_axis = _nrm(_add(_sub(chest, hip), _perp(_sub(chest, hip)), 10.0 * flip))
    axis = _nrm(_lerp2(raw_axis, (0.0, 1.0), 0.909))
    body_deg = -_vec_deg(axis)

    # 原版 HeadDir()：ClampMagnitude(look-chest,300)/300*0.2 + ClampMagnitude(head-chest,100)/100
    t1 = _clamp_mag(_sub(look_g, chest), 300.0)
    t2 = _clamp_mag(_sub(head, chest), 100.0)
    f = _nrm((t1[0] * 0.2 / 300.0 + t2[0] / 100.0,
              t1[1] * 0.2 / 300.0 + t2[1] / 100.0))
    if f == (0.0, 0.0):
        f = hd
    # 原版 ScavengerGraphics.cs:1847
    #   f2 = math.lerp(f.normalized(), -Custom.DegToFloat2(0f - num8), t).normalized()
    # 注意那个外层取负：参考向量 = -(sin(-num8), cos(-num8)) = (sin num8, -cos num8)。
    # 写成 +DegToFloat2(num8) 会让整个头/齿/眼组上下颠倒（这就是「头上下反了」的根因）。
    _br = math.radians(body_deg)
    f2 = _nrm(_lerp2(f, (math.sin(_br), -math.cos(_br)),
                     lerp(0.5, 1.0, max(num9 ** 1.1, num10))))
    f12 = _rot_origo(f2, body_deg)

    aiming = str(getattr(sc, "state", "") or "") == "aim"
    spine = _ScavSpine(d, flip, iv)
    float13 = _slerp2(f2, (-f[0], -f[1]), num9)
    float14 = _add(head, float13,
                   (4.0 - max(10.0 * math.sqrt(num9), 3.0 * num10)) * num11)

    eyes_open = lerp(float(getattr(sc, "last_eyes_open", 1.0)),
                     float(getattr(sc, "eyes_open", 1.0)), ts)
    eyes_pop = max(0.0, lerp(float(getattr(sc, "last_eyes_pop", 0.0)),
                             float(getattr(sc, "eyes_pop", 0.0)), ts))
    num13 = eyes_pop ** 0.25
    num14 = clampf(iv.get("eye_size", 0.55) + lerp(0.5, 0.25, num9) * num13,
                   0.0, 1.0)

    return {
        "org": (hx, hy), "flip": flip, "face": face, "d": d, "spine": spine,
        "axis": axis, "body_axis": axis, "body_deg": body_deg,
        "f": f, "f2": f2, "f12": f12,
        "num9": num9, "num10": num10, "num11": num11,
        "float13": float13, "float14": float14,
        "num13": num13, "num14": num14, "eyes_open": eyes_open,
        "look_g": look_g, "moving": moving, "cycle": cycle, "bob": bob,
        "hip": hip, "chest": chest, "head": head, "aiming": aiming,
    }


def scav_shoulder(pose, limb):
    """原版 ScavengerHand.DrawSprites 的肩点 @float（:511-513）。"""
    chest, hip = pose["d"][2], pose["d"][4]
    sh = _add(chest, _perp(_sub(chest, hip)),
              (1.0 - abs(pose["flip"])) * 10.0 * (-1.0 if limb == 0 else 1.0))
    return _add(sh, _dirvec(hip, chest), 5.0)


def scav_hand_target(pose, limb, grip=None):
    """原版 ScavengerHand.StandardLocomotionProcedure 的落点（:310 / :385）。

    站立/行走：胸 + RotateAroundOrigo((MyFlip*30, 0), Aim(hip→chest))，走路时前后摆。
    """
    if grip is not None:
        return grip
    chest, hip = pose["d"][2], pose["d"][4]
    ang = _vec_deg(_sub(chest, hip))
    face = pose["face"]
    tgt = _add(chest, _rot_origo((face * SCAV_ARM_REACH, 0.0), ang))
    ph = pose["cycle"] + (0.0 if limb == 0 else 0.5)
    sw = math.sin(ph * math.tau)
    return (tgt[0] + sw * 4.0 * pose["moving"] * face
            + (2.0 if limb == 0 else -2.0) * face,
            tgt[1] + max(0.0, sw) * 2.5 * pose["moving"])


def scav_foot(pose, limb):
    """脚落点：髋正下方，走动时左右迈步抬脚（原版 ScavengerLeg.IdealPos 近似）。"""
    hip = pose["d"][4]
    face = pose["face"]
    ph = pose["cycle"] + (0.0 if limb == 0 else 0.5)
    step = math.sin(ph * math.tau)
    drop = SCAV_STANCE * (1.0 - 0.10 * abs(step) * pose["moving"])
    return (hip[0] + step * 5.0 * pose["moving"] + (2.5 if limb == 0 else -2.5) * face,
            -drop + max(0.0, step) * 2.6 * pose["moving"])


def scav_weapon_dir(pose, hand):
    """原版 ScavengerHand.WeaponDir（:618-635）：举矛指向时额外朝视线点偏 7。"""
    chest, hip = pose["d"][2], pose["d"][4]
    v = _perp(_sub(chest, hand))
    v = (v[0] * -pose["face"], v[1] * -pose["face"])
    v = _add(v, _dirvec(hip, chest))
    if pose.get("aiming"):
        v = _add(v, _dirvec(hand, pose["look_g"]), 7.0)
    return _nrm(v)


def scav_spear_pose(pose, limb=0):
    """原版 ItemPosition(grasp 0) = 手 + WeaponDir*20： (屏幕握点, 朝向角)。"""
    hand = scav_hand_target(pose, limb)
    wd = scav_weapon_dir(pose, hand)
    return _scr(_add(hand, wd, SCAV_SPEAR_OUT), pose["org"]), _vec_deg(wd)


def _scav_mask(painter, atlas, name, x, y, rot, rgb, s) -> None:
    """原版 VultureMaskGraphics：同一帧 3 片叠出面具厚度。"""
    for i, (sx, sy) in enumerate(SCAV_MASK_LAYERS):
        blit(painter, atlas, name + "0", x, y, rot, sx * s, sy * s, rgb,
             ax=0.5, ay=0.5 + (0.015 if i == 2 else 0.0))


def _scav_eartler_branches(iv, rng):
    """原版 ScavengerGraphics.Eartlers.GenerateSegments 与 DefineBranch 的镜像。"""
    elite = bool(iv.get("elite"))
    num = 1.75 if elite else 1.0
    lo, hi = (45.0, 90.0) if elite else (15.0, 45.0)
    num2 = 1.5 if elite else 1.0
    num3 = 2.0 if elite else 1.0
    num4 = 1.0
    num5 = 0.0 if elite else 1.0
    num6 = 2.0 if elite else 1.0
    num7 = 0.0 if elite else 1.0
    out = []

    def branch(vs):
        out.append(list(vs))
        out.append([((-p[0], p[1]), r) for (p, r) in vs])

    vs = [((0.0, 0.0), 1.0),
          (_add((0.0, 0.0), _deg2flt(lerp(40.0, 90.0, rng.random())), 0.4 * num2),
           1.0 * num3)]
    far = _deg2flt(lerp(lo, hi, rng.random()) * num)
    pos = _add(far, _deg2flt(lerp(40.0, 90.0, rng.random())), -0.4 * num2)
    if pos[0] < 0.2:
        pos = (lerp(pos[0], far[0], 0.4), pos[1])
    vs.append((pos, 1.5 * num4))
    vs.append((far, 2.0 * num5))
    branch(vs)
    first = out[0]
    vs = [(first[1][0], 1.0)]
    n8 = 2 if (math.dist(first[1][0], first[2][0]) > 0.6 and rng.random() < 0.5) else 1
    f3 = _lerp2(first[1][0], first[2][0], lerp(0.0, 0.7 if n8 == 1 else 0.25, rng.random()))
    vs.append((f3, 1.2))
    vs.append((_add(_add(f3, _sub(first[3][0], first[2][0])),
                    _deg2flt(rng.random() * 360.0), 0.1), 1.75))
    branch(vs)
    if n8 == 2:
        f3 = _lerp2(first[1][0], first[2][0], lerp(0.45, 0.7, rng.random()))
        vs = [(f3, 1.2),
              (_add(_add(f3, _sub(first[3][0], first[2][0])),
                    _deg2flt(rng.random() * 360.0), 0.1), 1.75)]
        branch(vs)
    flag = rng.random() < 0.5 and not elite
    if flag:
        f4 = _add((0.0, 0.0), _deg2flt(90.0 + lerp(-20.0, 20.0, rng.random())),
                  lerp(0.2, 0.5, rng.random()))
        if f4[1] > first[1][0][1] - 0.1:
            f4 = (f4[0], f4[1] - 0.2)
        num9 = lerp(0.8, 2.0, rng.random())
        if rng.random() < 0.5:
            f4 = _add(f4, _deg2flt(lerp(120.0, 170.0, rng.random())),
                      lerp(0.1, 0.3, rng.random()))
            vs = [((0.0, 0.0), num9), (f4, num9)]
        else:
            vs = [((0.0, 0.0), 1.0), (f4, (1.0 + num9) / 2.0),
                  (_add(f4, _deg2flt(lerp(95.0, 170.0, rng.random())),
                        lerp(0.1, 0.2, rng.random())), num9)]
        branch(vs)
    if rng.random() > 0.25 or not flag or elite:
        num10 = 1.0 + rng.random() * 1.5
        flag2 = rng.random() < 0.5
        n11 = lerp(95.0, 135.0, rng.random())
        n12 = lerp(0.25, 0.4, rng.random()) * num6
        def extend(v):
            """原版：末点 = 上一顶点方向 * (上一顶点长度 + lerp(0.15,0.25)*num6)。"""
            m = math.hypot(v[0], v[1])
            return _add((0.0, 0.0), _nrm(v),
                        m + lerp(0.15, 0.25, rng.random()) * num6)

        v2 = _add((0.0, 0.0), _deg2flt(n11 + lerp(5.0, 35.0, rng.random())),
                  max(n12 + 0.1, lerp(0.3, 0.6, rng.random())))
        vs = [((0.0, 0.0), 1.0),
              (_add((0.0, 0.0), _deg2flt(n11), n12),
               (0.8 if flag2 else lerp(1.0, num10, 0.3)) * num6),
              (v2, (0.8 if flag2 else lerp(1.0, num10, 0.6))),
              (extend(v2), num10 * num7)]
        branch(vs)
    return out


def _scav_eartlers(painter, atlas, iv, rng, org, head_g, head_dir, look_up, body_deg, rgb):
    """原版 ScavengerGraphics.Eartlers.DrawSprites（:933-966）。"""
    branches = _scav_eartler_branches(iv, rng)
    rotat = _vec_deg((-head_dir[0], -head_dir[1]))
    num = 1.0 - (abs(_rot_origo(head_dir, body_deg)[0]) ** 1.5) * lerp(1.0, 0.5, look_up)
    y_sq = lerp(1.0, -0.25, look_up)
    reach = lerp(15.0, 35.0, iv.get("dominance", 0.5))
    for pts in branches:
        vs = [None] * (len(pts) * 4)
        prev = _add(head_g, _rot_origo((pts[0][0][0] * num, pts[0][0][1] * y_sq), rotat), reach)
        a = _perp(_sub(pts[1][0], pts[0][0]))
        n3 = pts[0][1]
        for j, (p, rad) in enumerate(pts):
            cur = _add(head_g, _rot_origo((p[0] * num, p[1] * y_sq), rotat), reach)
            f3 = _dirvec(prev, cur)
            f4 = _perp(f3)
            n5 = math.dist(cur, prev) / 10.0
            n6 = lerp(1.0, 2.0, iv.get("eartler_width", 0.5)) * rad * lerp(0.5, 1.0, num)
            mid = _slerp2(a, f4, 0.5)
            vs[j * 4] = _add(_add(prev, mid, -(n6 + n3) * 0.5), f3, -n5)
            vs[j * 4 + 1] = _add(_add(prev, mid, (n6 + n3) * 0.5), f3, -n5)
            if j == len(pts) - 1:
                n6 /= 4.0
            vs[j * 4 + 2] = _add(_add(cur, f4, -n6), f3, n5)
            vs[j * 4 + 3] = _add(_add(cur, f4, n6), f3, n5)
            prev = cur
            a = f4
            n3 = n6
        if len(pts) < 2:
            continue
        mesh(painter, [_scr(v, org) for v in vs], _mesh_long_tris(len(pts), len(vs)),
             [rgb] * len(vs), outline=False)


def _scav_back_deco(painter, atlas, sc, iv, rng, pose, org, body_rgb, head_rgb, deco_rgb):
    """原版 HardBackSpikes（10% + 精英）与 WobblyBackTufts（其余）：背上的刺/绒簇。

    两者都是 LizardScale 贴图钉在 OnBackSurfacePos(rel)，沿 OnSpineUpDir/Dir 长出去；
    anchorY = 0.1（贴图底边），scaleY = 尖端距离 / 贴图高，rotation = 该方向的 VecToDeg。
    软簇原本是 Scale 悬垂物理，静息时尖端 = 背面点 + 方向 * 簇长。
    """
    spine = pose["spine"]
    flip = pose["flip"]
    body_deg = pose["body_deg"]
    scruffy = float(iv.get("scruffy", 0.0))
    elite = bool(iv.get("elite"))
    num = 1.5 if elite else 1.0

    def rnd():
        return rng.random()

    hard = elite or rnd() < 0.1

    # ── BackTuftsAndRidges 基类 ──
    scale_graf = rng.randint(0, 6)
    x_flip = 1.0 if scale_graf == 3 else -1.0
    if rnd() < 0.025:
        x_flip = -x_flip
    if rnd() < 0.5:
        x_flip *= 0.5 + 0.5 * rnd()
    colored = 0.0
    if rnd() > iv.get("general_melanin", 0.5):
        colored = rnd() ** 0.5
    use_detail = rnd() < 0.5

    def gen_pattern(pattern):
        """原版 BackDecals.GeneratePattern → (positions, top, bottom)。"""
        if pattern == 0:                                  # SpineRidge
            top = lerp(0.07, 0.3, rnd())
            bottom = lerp(0.6, 1.0, rnd())
            step = lerp(2.5, 12.0, rnd())
            n = max(2, int((bottom - top) * 100.0 / max(1e-6, step)))
            rel = [(0.0, lerp(top, bottom, i / float(n - 1))) for i in range(n)]
        elif pattern == 1:                                # DoubleSpineRidge
            top = lerp(0.07, 0.3, rnd())
            bottom = lerp(0.6, 1.0, rnd())
            if not hard:
                bottom = lerp(bottom, 0.5, rnd())
            step = lerp(4.5, 12.0, rnd())
            n = max(2, int((bottom - top) * 100.0 / max(1e-6, step)))
            rel = []
            for i in range(n):
                y = lerp(top, bottom, i / float(n - 1))
                rel.append((-0.9, y))
                rel.append((0.9, y))
        else:                                             # RandomBackBlotch
            n = max(2, int(lerp(lerp(20.0, 4.0, scruffy), 40.0,
                                lerp(rnd(), rnd(), 0.5 * rnd()))))
            top = lerp(0.02, 0.2, rnd())
            bottom = lerp(0.4, 0.9, rnd() ** 1.5)
            rel = []
            for _ in range(n):
                ang = rnd() * 360.0
                rel.append((math.sin(math.radians(ang)),
                            _lmap(math.cos(math.radians(ang)), -1.0, 1.0, top, bottom)))
        rel.sort(key=lambda q: -q[1])
        return rel, top, bottom

    if hard:
        pattern = 0 if rnd() < 0.6 else 1
        if rnd() < 0.1:
            pattern = 2
        rel, top, bottom = gen_pattern(pattern)
        if rnd() < 0.5:
            scale_graf = rng.randint(0, 3) if rnd() < 0.85 else 6
    else:
        pattern = 2
        if rnd() < 0.25 and (scruffy == 0.0 or rnd() < 0.05):
            pattern = 1 if rnd() < 0.5 else 0
        if rnd() < 0.2:
            scale_graf = 0
        elif rnd() < 0.5:
            scale_graf = rng.randint(3, 5) if rnd() < 1.1764705 else 0
        else:
            x_flip *= 0.5 + rnd() * 0.5
        rel, top, bottom = gen_pattern(pattern)

    color_alphas = [colored] * len(rel)
    if colored > 0.0 and rnd() < 0.25 + 0.5 * colored:
        lo = min(q[1] for q in rel)
        hi = max(q[1] for q in rel)
        p2 = lerp(0.2, 1.2, rnd())
        color_alphas = [lerp(colored, 0.0, _ilerp(lo, hi, q[1]) ** p2) for q in rel]

    key_a = "LizardScaleA%d" % scale_graf
    sh = float(_SCAV_SCALE_H.get(scale_graf, 18.0))
    if atlas.find_atlas(key_a) is None:
        key_a, sh = "LizardScaleA0", 18.0
    key_b = "LizardScaleB" + key_a[len("LizardScaleA"):]

    def put(anchor, rot, ln, sx, idx):
        sy = max(0.02, ln) / sh
        blit(painter, atlas, key_a, *_scr(anchor, org), rot, sx, sy,
             body_rgb, ax=0.5, ay=0.9)
        if colored > 0.0 and color_alphas[idx] > 0.02:
            col = QColor(*(deco_rgb if use_detail else head_rgb))
            col.setAlphaF(min(1.0, color_alphas[idx]))
            blit(painter, atlas, key_b, *_scr(anchor, org), rot, sx, sy,
                 col, ax=0.5, ay=0.9)

    if hard:
        p0 = lerp(0.3, 1.0, rnd())
        general = _lmap(len(rel), 5.0, 35.0, 1.0, 0.2)
        general = lerp(general, 0.5, rnd())
        general = lerp(general, rnd() ** 0.75, rnd())
        for i, (rx, ry) in enumerate(rel):
            up, dr = spine.up_dir(ry), spine.dir(ry)
            a = lerp(4.0, 14.0 * num, general) * (1.0 - 0.5 * _ilerp(0.5, 1.0, ry))
            b = lerp(4.0 * num, 18.0 * num, general) * 0.5 * _ilerp(0.5, 1.0, ry)
            vec = (up[0] * a + dr[0] * b, up[1] * a + dr[1] * b)
            ln = math.hypot(vec[0], vec[1])
            rot = _vec_deg(_nrm(vec)) if ln > 1e-6 else 0.0
            sx = _sgn(flip + rx * 0.5) * lerp(0.5 * num, num, general) * x_flip
            put(spine.back_pos((rx, ry)), rot, ln, sx, i)
        return

    general = lerp(rnd(), 0.5, rnd())
    general = lerp(general, rnd(), rnd())
    general = general ** lerp(2.0, 0.65, 0.5)
    n2 = lerp(0.1, 0.6, rnd())
    p0 = lerp(1.2, 0.3, rnd())
    a0 = n2 * rnd()
    out_sides = rnd() if pattern == 2 else 0.0
    down_along = rnd()
    for i, (rx, ry) in enumerate(rel):
        rdir = _deg2flt(rnd() * 360.0)
        rdir = (rdir[0] * rnd() * scruffy, rdir[1] * rnd() * scruffy)
        n3 = n2
        if pattern == 2:
            n3 = lerp(n2, 1.0, rnd())
            n3 = min(n3, lerp(a0, 1.0, math.sin((_ilerp(top, bottom, ry) ** p0) * math.pi)))
            rdir = _deg2flt(rnd() * 360.0)
            k = 1.0 - 2.0 * abs(0.5 - _ilerp(top, bottom, ry))
            rdir = (rdir[0] * k, rdir[1] * k)
        elif pattern in (0, 1):
            n3 = lerp(n2, 1.0, math.sin((_ilerp(top, bottom, ry) ** p0) * math.pi))
        if rnd() < scruffy:
            n3 = lerp(n3, rnd(), rnd() ** lerp(4.0, 0.5, scruffy))
        ln = 40.0 * n3 * lerp(0.1, 1.0, general)
        up, dr, od = spine.up_dir(ry), spine.dir(ry), spine.out_dir((rx, ry))
        kx = abs(rx) ** 0.4 * out_sides
        rd = _rot_origo(rdir, body_deg)
        vec = _nrm((up[0] + dr[0] * (0.5 * ry * down_along) + od[0] * kx + rd[0],
                    up[1] + dr[1] * (0.5 * ry * down_along) + od[1] * kx + rd[1]))
        sx = _sgn(flip + rx * 0.5) * lerp(0.5, 1.0, general) * x_flip
        put(spine.back_pos((rx, ry)), _vec_deg(vec), ln, sx, i)


def _scav_leg(painter, atlas, org, hip_g, foot_g, face, limb, s, leg_rgb, leg_t=0.5) -> None:
    """原版 ScavengerLeg.DrawSprites（:736-770）：12 顶点 / 10 三角。"""
    num = _lmap(face, -float(limb), 1.0 - float(limb), -1.0, 1.0)
    num2 = lerp(1.0, 1.4, leg_t)
    f2 = foot_g
    d = math.dist(hip_g, f2) / num2
    f2 = _add(f2, _perp(_dirvec(hip_g, f2)),
              -num2 * _lmap(d, 2.0, 20.0, 6.0, -1.0) * num)
    if math.dist(f2, hip_g) < 3.0:
        f2 = _add(hip_g, _dirvec(hip_g, f2), 3.0)
    f3 = _add(f2, _dirvec(f2, hip_g), 1.5 * num2)
    f4 = _ik(hip_g, f3, 10.0 * num2, 10.0 * num2, -num)
    mid = _lerp2(hip_g, f3, 0.5)
    if math.dist(f4, mid) < 3.0 * num2:
        f4 = _add(mid, _dirvec(mid, f4), 3.0 * num2)
    f2 = _add(f2, _dirvec(hip_g, f4), 3.0 * num2)
    f2 = _add(f2, _dirvec(f3, f4), 2.0 * num2)
    m1 = ((hip_g[0] + f4[0] + f3[0]) / 3.0, (hip_g[1] + f4[1] + f3[1]) / 3.0)
    f5 = _lerp2(m1, mid, 0.35)
    f4 = _add(f4, _perp(_dirvec(f3, hip_g)),
              num2 * _lmap(abs(_dist_line(f4, hip_g, f3)), 0.0, 20.0, 2.0, 0.0) * _sgn(num))
    sg = -_sgn(num)
    n_hip = _perp(_dirvec(hip_g, f4))
    d34 = _dirvec(hip_g, f3)
    dn = _dirvec(f2, f3)
    n_f2 = _perp(dn)
    v = [None] * 12
    v[0] = _add(hip_g, n_hip, 2.0 * num2 * sg)
    v[1] = _add(hip_g, n_hip, -2.0 * num2 * sg)
    v[2] = f5
    v[3] = _add(f4, d34, -3.0 * num2)
    v[4] = _add(f4, d34, 3.0 * num2)
    k5 = _lmap(math.dist(hip_g, f3), 10.0 * num2, 30.0 * num2, 3.0, 1.0)
    v[5] = _add(f3, _nrm(_add(_dirvec(f4, f3), _dirvec(f4, hip_g))), -k5 * num2)
    d_hip_f2 = _dirvec(hip_g, f2)
    v[6] = _add(f3, d_hip_f2, 0.8 * num2)
    v[7] = _add(f3, d_hip_f2, -0.8 * num2)
    v[8] = _add(f2, n_f2, 0.8 * num2 * sg)
    v[9] = _add(f2, n_f2, -0.8 * num2 * sg)
    v[10] = _add(_add(f2, n_f2, 0.7 * num2 * sg), dn, 2.0 * num2)
    v[11] = _add(_add(f2, n_f2, -1.2 * num2 * sg), dn, 2.0 * num2)
    tris = [(0, 1, 2), (1, 2, 3), (3, 4, 2), (4, 2, 5), (2, 5, 6),
            (5, 6, 7), (5, 7, 8), (8, 7, 9), (8, 9, 10), (8, 9, 11)]
    mesh(painter, [_scr(q, org) for q in v], tris, [leg_rgb] * 12, outline=False)


def _scav_hand(painter, atlas, org, chest_g, sh_g, tgt_g, face, limb, s, body_rgb,
               hand_rgb, arm_thickness=0.5, myflip=1.0, gripping=True) -> None:
    """原版 ScavengerHand.DrawSprites（:509-609）：19 顶点 / 17 三角 + 手贴图。"""
    f2 = tgt_g
    f3 = _add(f2, _dirvec(f2, sh_g), 6.0)
    if math.dist(f3, sh_g) < 5.0:
        k = 5.0 - math.dist(sh_g, f3)
        f2 = _add(f2, _dirvec(sh_g, f3), k)
        f3 = _add(f3, _dirvec(sh_g, f3), k)
    if math.dist(sh_g, tgt_g) > SCAV_ARM_LEN:
        f2 = _add(sh_g, _dirvec(sh_g, tgt_g), SCAV_ARM_LEN)
        f3 = _add(f2, _dirvec(f2, sh_g), 6.0)
    f4 = _ik(sh_g, f3, SCAV_ARM_SEG, SCAV_ARM_SEG, myflip)
    f5 = chest_g
    f6 = _perp(_dirvec(f5, sh_g))
    num = -(1.75 + lerp(-1.0, 1.0, arm_thickness)) * _sgn(myflip)
    v = [None] * 19
    src = (sh_g, f4, f3, f2)
    for i in range(4):
        f7 = src[i]
        f8 = _nrm((-(f5[0] - f7[0]), -(f5[1] - f7[1])))
        f9 = _perp(f8)
        num2 = math.dist(f7, f5)
        if i == 0:
            v[0] = f5
            v[18] = _add(_add(f7, f6, -num * 2.0), f8, -num2 * 0.2)
            v[1] = _lerp2(_add(_add(f7, _nrm(_add(f9, f6)), num * 2.0), f8, -1.0), f5, 0.5)
        elif i == 1:
            v[17] = _add(f5, _nrm((f9[0] * 2.0 + f6[0], f9[1] * 2.0 + f6[1])), -num * 2.0)
            v[16] = _add(_add(f7, f9, -num), f8, -num2 * 0.8)
            v[15] = _add(_add(f7, f9, -num * 2.5), f8, -num2 * 0.5)
            v[2] = _add(_add(f7, f9, num * 2.5), f8, -num2 * 0.5)
            v[14] = _add(_add(f7, f9, -num), f8, -num2 * 0.2)
            v[3] = _add(_add(f7, f9, num * 1.6), f8, -num2 * 0.2)
        elif i == 2:
            v[13] = _add(f5, _nrm(_add(f9, f6)), -num * 2.0)
            v[4] = _add(f5, _slerp2(f9, f6, 0.7), num * 2.0)
            v[12] = _add(_add(f7, f9, -num * 1.3), f8, -num2 * 0.8)
            v[5] = _add(f5, _slerp2(f9, f6, 0.3), num * 2.0)
            v[11] = _add(_add(f7, f9, -num * 1.5), f8, -num2 * 0.65)
            v[6] = _add(_add(f7, f9, num * 1.5), f8, -num2 * 0.65)
        else:
            v[10] = _add(f5, _nrm(_add(f9, f6)), -num)
            v[7] = _add(f5, _nrm(_add(f9, f6)), num)
            v[9] = _add(f7, f9, -num)
            v[8] = _add(f7, f9, num)
        f5 = f7
        f6 = f9
    tris = [(0, 18, 1), (18, 17, 1), (16, 17, 1), (1, 15, 16), (1, 2, 15),
            (14, 2, 15), (3, 2, 14), (14, 3, 13), (4, 3, 13), (12, 4, 13),
            (4, 12, 5), (11, 12, 5), (11, 6, 5), (11, 6, 10), (7, 6, 10),
            (7, 9, 10), (7, 9, 8)]
    mesh(painter, [_scr(q, org) for q in v], tris, [body_rgb] * 19, outline=False)
    name = SCAV_HAND_B if gripping else SCAV_HAND_A
    if atlas.find_atlas(name) is None:
        name = SCAV_HAND_A
    blit(painter, atlas, name, *_scr(f3, org), _vec_deg(_dirvec(f3, f2)),
         -num * 2.0 * 3.0 / 18.0, 1.0, hand_rgb, ax=0.5, ay=1.0)


def draw_scavenger(painter, atlas, sc, ts=1.0, body_rgb=None, head_rgb=None,
                   eye_rgb=None, leg_rgb=None, hand_rgb=None) -> None:
    """拾荒者：逐片复刻原版 ScavengerGraphics（骨架/图层/尺寸按反编译）。

    锚点 = 髋心 (sc.x, sc.y)（原版 drawPositions[4]），脚下 SCAV_STANCE 为地面。
    图层顺序 = 原版 AddToContainer：
      后腿 → 后手 → 尾/背饰 → 胸·髋·腰·腹斑 → 前腿 → 前手 → 颈 → 须 → 头 → 齿 → 眼 → 面具。
    """
    S = SCAV_S
    iv = getattr(sc, "ivar", None) or _IVAR_MID
    pose = scav_pose(sc, ts, iv)
    org = pose["org"]
    flip = pose["flip"]
    face = pose["face"]
    d = pose["d"]
    spine = pose["spine"]
    f2 = pose["f2"]
    f12 = pose["f12"]
    num9 = pose["num9"]
    num10 = pose["num10"]
    num11 = pose["num11"]
    float13 = pose["float13"]
    float14 = pose["float14"]
    eyes_open = pose["eyes_open"]
    num13 = pose["num13"]
    num14 = pose["num14"]

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

    hip_rad = SCAV_HIP_RAD * S
    chest_rad = SCAV_CHEST_RAD * S
    fat = iv.get("fat", 0.5)
    narrow = iv.get("waist", 0.4)
    waist_w = fat * (1.0 - narrow)
    neck_t = iv.get("neck", 0.5)
    rng = _random.Random(int(getattr(sc, "seed", 0)) * 7919 + 4241)
    arm_t = iv.get("arm", 0.5)
    legs_t = iv.get("legs", 0.5)

    painter.save()
    aa_hint(painter)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setClipRect(QRectF(-1.0e5, -1.0e5, 2.0e5,
                               1.0e5 + org[1] + SCAV_STANCE + 1.5),
                        Qt.ClipOperation.IntersectClip)

    # ── 后腿（leg[1]）→ 后手（hand[1]）──
    _scav_leg(painter, atlas, org, d[4], scav_foot(pose, 1), face, 1, S, leg_rgb, legs_t)
    _scav_hand(painter, atlas, org, d[2], scav_shoulder(pose, 1),
               scav_hand_target(pose, 1), face, 1, S, body_rgb, hand_rgb,
               arm_t, myflip=flip, gripping=False)

    # ── 尾（原版 Tail：从 drawPositions[3] 起，每段 9~10px，尖端收）──
    nseg = int(iv.get("tail_segs", 0) or 0)
    if nseg > 0:
        pts = [d[3]]
        rads = [2.6 * S]
        cur = d[4]
        for i in range(nseg):
            t = i / float(max(1, nseg - 1))
            ang = face * (-90.0 - lerp(18.0, 74.0, t))
            cur = _add(cur, _deg2flt(ang), 9.0)
            pts.append(cur)
            rads.append(lerp(2.0, 1.0, t) * S)
        tv, tt = _long_mesh(pts, rads, pointy=True)
        mesh(painter, [_scr(q, org) for q in tv], tt, [body_rgb] * len(tv), outline=False)

    # ── 背刺 / 背簇 ──
    _scav_back_deco(painter, atlas, sc, iv, rng, pose, org, body_rgb, head_rgb,
                     deco_rgb)

    # ── 胸 / 髋（原版 Circle20 + InitiateSprites 的 scale / anchorY）──
    float5 = _lerp2(d[2], d[4], 0.5)
    float5 = _add(float5, _perp(_sub(d[4], d[2])), -lerp(5.0, 15.0, narrow) * flip)
    blit(painter, atlas, CIRCLE_SPRITE, *_scr(d[2], org),
         _vec_deg(_dirvec(d[2], float5)),
         chest_rad * lerp(0.7, 1.3, fat) * 2.0 / 20.0,
         (chest_rad + lerp(2.0, 1.5, narrow)) * 2.0 / 20.0, body_rgb,
         ax=0.5, ay=1.0 - (0.4 + 0.05 * narrow))
    blit(painter, atlas, CIRCLE_SPRITE, *_scr(d[4], org), 0.0,
         hip_rad / 15.0, hip_rad / 15.0, body_rgb)

    # ── 腰（原版 WaistSprite：8 顶点 / 6 三角）──
    n1 = _perp(_dirvec(d[4], float5))
    f6v = _dirvec(d[4], d[2])
    n2 = _perp((-f6v[0], -f6v[1]))
    mid40 = _lerp2(float5, _lerp2(d[2], d[4], 0.5), 0.4)
    wv = [_add(d[4], n1, hip_rad * lerp(0.65, 0.9, waist_w)),
          _add(d[4], n1, -hip_rad * lerp(0.65, 0.9, waist_w)),
          _add(_add(mid40, f6v, -4.0), n2, chest_rad * lerp(0.35, 0.9, waist_w ** 1.3)),
          _add(_add(mid40, f6v, -4.0), n2, -chest_rad * lerp(0.35, 0.9, waist_w ** 1.3)),
          _add(_add(mid40, f6v, 4.0), n2, chest_rad * lerp(0.25, 0.8, waist_w ** 1.3)),
          _add(_add(mid40, f6v, 4.0), n2, -chest_rad * lerp(0.25, 0.8, waist_w ** 1.3)),
          _add(d[2], _perp(_dirvec(d[2], float5)), chest_rad * lerp(0.7, 1.3, fat)),
          _add(d[2], _perp(_dirvec(d[2], float5)), -chest_rad * lerp(0.7, 1.3, fat))]
    mesh(painter, [_scr(q, org) for q in wv], [(k, k + 1, k + 2) for k in range(6)],
         [body_rgb] * len(wv), outline=False)

    # ── 腹斑（原版 ChestPatchSprite = OnBellySurfacePos(chestPatchShape)）──
    pv = [spine.belly_pos(p) for p in _SCAV_CHEST_PATCH]
    mesh(painter, [_scr(q, org) for q in pv],
         [(0, 1, 2), (1, 2, 3), (2, 3, 4), (3, 4, 5), (4, 5, 6), (5, 6, 7)],
         [belly_rgb] * len(pv), outline=False)

    # ── 前腿（leg[0]）──
    _scav_leg(painter, atlas, org, d[4], scav_foot(pose, 0), face, 0, S, leg_rgb, legs_t)

    # ── 前手（hand[0]）──
    _scav_hand(painter, atlas, org, d[2], scav_shoulder(pose, 0),
               scav_hand_target(pose, 0), face, 0, S, body_rgb, hand_rgb,
               arm_t, myflip=flip, gripping=(getattr(sc, "spear", None) is not None))

    # ── 颈（原版 NeckSprite：4 段 × 4 顶点）──
    float7 = _add(d[2], _dirvec(float5, d[2]), 5.0)
    f8 = float7
    num3 = chest_rad
    num4 = _ilerp(0.0, 10.0, _dist_line(d[0], d[4], d[2]) * (-flip))
    nv = [None] * 16
    nvc = []
    for i in range(4):
        num5 = i / 3.0
        f9 = _lerp2(float7, d[0], num5)
        f9 = _add(f9, _perp(_dirvec(float7, d[0])),
                  math.sin(num5 * math.pi) * 3.0 * num4 * flip)
        f10 = _dirvec(f9, f8)
        f11 = _perp(f10)
        num6 = math.dist(f9, f8) / 4.0
        num7 = lerp(7.0, 3.0, num5) - 2.0 * math.sin(num5 * math.pi) * lerp(0.5, 1.5, neck_t)
        nv[i * 4] = _add(_add(f8, f11, -(num3 + num7) * 0.5), f10, -num6)
        nv[i * 4 + 1] = _add(_add(f8, f11, (num3 + num7) * 0.5), f10, -num6)
        nv[i * 4 + 2] = _add(_add(f9, f11, -num7), f10, num6)
        nv[i * 4 + 3] = _add(_add(f9, f11, num7), f10, num6)
        f8 = f9
        num3 = num7
        c1 = _mix_rgb(body_rgb, head_rgb, (i - 0.5) / 3.0)
        c2 = _mix_rgb(body_rgb, head_rgb, i / 3.0)
        nvc += [c1, c1, c2, c2]
    mesh(painter, [_scr(q, org) for q in nv], _mesh_long_tris(4, 16), nvc, outline=False)

    # ── 须（Eartlers）──
    eart_rgb = deco_rgb if iv.get("colored_eartler_tips") else head_rgb
    _scav_eartlers(painter, atlas, iv, rng, org, d[0], float13, num9,
                   pose["body_deg"], eart_rgb)

    # ── 头（Circle20）──
    blit(painter, atlas, CIRCLE_SPRITE, *_scr(d[0], org), _vec_deg(f2),
         lerp(8.0, 9.0, math.sqrt(num9)) * num11 / 10.0,
         lerp(11.0, 8.0, math.sqrt(num9)) * num11 / 10.0, head_rgb)

    # ── 齿（TeethSprite：每颗 5 顶点 / 3 三角）──
    teeth = iv.get("teeth") or ()
    if teeth:
        nt = len(teeth)
        tv = [None] * (nt * 5)
        wide = iv.get("wide_teeth", 0.5)
        for m in range(nt):
            num18 = m / float(max(1, nt - 1))
            t0 = teeth[m][0]
            t1 = teeth[m][1]
            f17 = _add(_add(float14, float13, 4.0),
                       _perp(float13), lerp(-3.0, 3.0, num18) * f12[0])
            f18 = _add(_add(float14, float13, lerp(8.0, 10.0, math.sin(num18 * math.pi)) * t0),
                       _perp(float13),
                       lerp(lerp(-9.0, 9.0, num18) * lerp(0.5, 1.2, wide),
                            -2.0 * _sgn(f12[0]), 1.0 - abs(f12[1])) * t0)
            f19 = _add(_add(float14, float13, lerp(12.0, 15.0, math.sin(num18 * math.pi)) * t0),
                       _perp(float13),
                       lerp(lerp(-9.0, 9.0, num18) * lerp(0.5, 1.2, wide),
                            -15.0 * _sgn(f12[0]), 1.0 - abs(f12[1])) * t0)
            tv[m * 5] = _add(f17, _perp(_sub(f18, f17)), -1.0)
            tv[m * 5 + 1] = _add(f17, _perp(_sub(f18, f17)), 1.0)
            tv[m * 5 + 2] = _add(f18, _perp(_sub(f19, f18)), -t1)
            tv[m * 5 + 3] = _add(f18, _perp(_sub(f19, f18)), t1)
            tv[m * 5 + 4] = f19
        tris = []
        for m in range(nt):
            tris += [(m * 5, m * 5 + 1, m * 5 + 2), (m * 5 + 1, m * 5 + 2, m * 5 + 3),
                     (m * 5 + 2, m * 5 + 3, m * 5 + 4)]
        mesh(painter, [_scr(q, org) for q in tv], tris, [head_rgb] * len(tv), outline=False)

    # ── 眼（Circle20 ×2 + 可选瞳孔）──
    float15 = _add(float14, float13,
                   lerp(-5.0, 60.0, iv.get("eyes_angle", 0.5)) * eyes_open)
    for j in range(2):
        value = (-1.0 if j == 0 else 1.0) * 0.5 + f12[0] * (1.0 - num10)
        value = clampf(value, -1.0, 1.0)
        p16 = _add(float14, _perp(float13), 8.0 * num11 * value)
        num15 = _vec_deg(_dirvec(p16, float15))
        num16 = (lerp(1.5, 2.0, num9 ** 1.5) * lerp(0.3, 1.5, num14 ** 0.7)
                 * (1.0 + 0.2 * num13 * (1.0 - num9))
                 * _ilerp(1.0, 0.7, abs(value))
                 * lerp(1.0, lerp(0.5, 0.25, num14),
                        iv.get("narrow_eyes", 0.0) * lerp(1.0, 0.5, num13))
                 * eyes_open)
        num17 = (lerp(2.5, 1.5, math.sqrt(num9)) * lerp(0.3, 1.5, num14 ** 0.7)
                 * (1.0 + 0.2 * num13) * _ilerp(0.0, 0.75, eyes_open))
        ps = iv.get("pupil", 0.0) or 0.0
        if ps > 0.0:
            # 原版 :1904  vec = deepPupils ? (-f) : DirVec(眼, 视线点)*InverseLerp(0,30,d)*InverseLerp(.3,.7,同情心)
            if iv.get("deep"):
                vec = (-pose["f"][0], -pose["f"][1])
            else:
                vec = _dirvec(p16, pose["look_g"])
                k = (_ilerp(0.0, 30.0, math.dist(p16, pose["look_g"]))
                     * _ilerp(0.3, 0.7, float(getattr(sc, "sympathy", 0.5))))
                vec = (vec[0] * k, vec[1] * k)
            vec = _rot_origo(vec, num15)
            vec = (vec[0] * num16 * (1.0 - ps), vec[1] * num17 * (1.0 - ps))
            vec = _rot_origo(vec, -num15)
            blit(painter, atlas, CIRCLE_SPRITE, *_scr(_add(p16, vec), org), num15,
                 num16 * 0.1 * ps, num17 * 0.1 * ps, pupil_rgb)
        blit(painter, atlas, CIRCLE_SPRITE, *_scr(p16, org), num15,
             num16 * 0.1, num17 * 0.1, eye_rgb)

    # ── 精英面具 ──
    if iv.get("mask"):
        _scav_mask(painter, atlas, iv["mask"], *_scr(d[0], org),
                   _vec_deg(f2), getattr(sc, "mask_rgb", None) or (226, 226, 214), num11)

    painter.restore()


def _affine_tri(s0, s1, s2, d0, d1, d2):
    """(src 三角 → dst 三角) 的仿射矩阵；退化三角返回 None。"""
    ax, ay = s1[0] - s0[0], s1[1] - s0[1]
    bx, by = s2[0] - s0[0], s2[1] - s0[1]
    det = ax * by - bx * ay
    if abs(det) < 1e-9:
        return None
    Ax, Ay = d1[0] - d0[0], d1[1] - d0[1]
    Bx, By = d2[0] - d0[0], d2[1] - d0[1]
    m11 = (Ax * by - Bx * ay) / det
    m21 = (-Ax * bx + Bx * ax) / det
    m12 = (Ay * by - By * ay) / det
    m22 = (-Ay * bx + By * ax) / det
    dx = d0[0] - (m11 * s0[0] + m21 * s0[1])
    dy = d0[1] - (m12 * s0[0] + m22 * s0[1])
    return QTransform(m11, m12, m21, m22, dx, dy)


def draw_grid_patch(painter, image, quad, n=5) -> None:
    """把贴图铺到四边形 quad 上（原版 TriangleMesh.QuadGridMesh 的等价实现）。

    quad 顺序 = (u0,v0) (u1,v0) (u1,v1) (u0,v1)。原版是 n×n 网格 + 双线性插值，
    每小格各自仿射 —— 所以四边形被挤扁/缺一角时只是跟着变形。绝不能像
    QTransform.quadToQuad 那样在近退化四边形上解射影矩阵：那会把贴图甩到无穷远，
    整朵花环炸成满屏拉丝（花瓣被啃掉一片时必炸）。
    """
    img = image
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    # 平行四边形（＝纯仿射）快路：一次画完
    ex = quad[0][0] + quad[2][0] - quad[1][0] - quad[3][0]
    ey = quad[0][1] + quad[2][1] - quad[1][1] - quad[3][1]
    if ex * ex + ey * ey < 0.25:
        tr = _affine_tri((0.0, 0.0), (w, 0.0), (0.0, h), quad[0], quad[1], quad[3])
        if tr is not None:
            painter.setTransform(tr, True)
            painter.drawImage(0, 0, img)
        painter.restore()
        return
    grid = []
    for j in range(n + 1):
        v = j / float(n)
        row = []
        for i in range(n + 1):
            u = i / float(n)
            k0 = (1.0 - u) * (1.0 - v)
            k1 = u * (1.0 - v)
            k2 = u * v
            k3 = (1.0 - u) * v
            row.append((quad[0][0] * k0 + quad[1][0] * k1 + quad[2][0] * k2 + quad[3][0] * k3,
                        quad[0][1] * k0 + quad[1][1] * k1 + quad[2][1] * k2 + quad[3][1] * k3))
        grid.append(row)
    for j in range(n):
        for i in range(n):
            x0, x1 = w * i / float(n), w * (i + 1) / float(n)
            y0, y1 = h * j / float(n), h * (j + 1) / float(n)
            s00, s10, s11, s01 = (x0, y0), (x1, y0), (x1, y1), (x0, y1)
            p00, p10 = grid[j][i], grid[j][i + 1]
            p11, p01 = grid[j + 1][i + 1], grid[j + 1][i]
            for sa, sb, sc, da, db, dc in ((s00, s10, s11, p00, p10, p11),
                                           (s00, s11, s01, p00, p11, p01)):
                if abs((sb[0] - sa[0]) * (sc[1] - sa[1])
                       - (sc[0] - sa[0]) * (sb[1] - sa[1])) < 0.35:
                    continue                     # 退化小格：这块贴图本来就看不见
                tr = _affine_tri(sa, sb, sc, da, db, dc)
                if tr is None:
                    continue
                path = QPainterPath()
                path.moveTo(QPointF(*da))
                path.lineTo(QPointF(*db))
                path.lineTo(QPointF(*dc))
                path.closeSubpath()
                painter.save()
                painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
                painter.setTransform(tr, True)
                painter.drawImage(0, 0, img)
                painter.restore()
    painter.restore()


def draw_scavenger_spear(painter, atlas, sc, ts=1.0) -> None:
    """拾荒者手里的矛（原版 SmallSpear，瞄准时后仰）。"""
    sp = getattr(sc, "spear", None)
    if sp is None:
        return
    x = sp.last_x + (sp.x - sp.last_x) * ts
    y = sp.last_y + (sp.y - sp.last_y) * ts
    ang = sp.last_angle + (sp.angle_deg - sp.last_angle) * ts
    draw_spear(painter, atlas, x, y, ang, length=SPEAR_DRAW_LEN)
