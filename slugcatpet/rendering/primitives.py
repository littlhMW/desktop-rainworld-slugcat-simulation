"""共享渲染原语：软绳/带状/三角网格/atlas sprite 绘制。"""
from __future__ import annotations
import math
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)
from PySide6.QtCore import QPointF, Qt

from ..core.units import clampf


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
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
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
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
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
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawPath(path)
    painter.restore()


def mesh(painter, verts, tris, vcolors, outline: bool = True) -> None:
    """逐三角填充三角网格（尾/舌）；vcolors 逐顶点色（三角取均值）。"""
    if not verts or not tris:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
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
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
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


CIRCLE_SPRITE = "Circle20"       # 原版拾荒者的髋/胸/头/眼都是 Circle20
SCAV_HAND = "ScavengerHandA"    # 原版手（张开帧；原版握矛手用 ScavengerHandB）
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


def draw_scavenger(painter, atlas, sc, ts=1.0, body_rgb=(58, 60, 68),
                   head_rgb=(226, 226, 214), eye_rgb=(26, 26, 30),
                   leg_rgb=None, hand_rgb=None) -> None:
    """拾荒者：原版贴图组合 = Circle20（髋/胸/头/眼）+ ScavengerHandA/B（手）。

    腰/颈/臂/腿在原版就是 Futile_White 三角网格与 "pixel" 线段，这里照做。
    锚点 (x, y) = 髋部（sc.y 即髋心，脚下 7px 为地面）。
    """
    x = sc.last_x + (sc.x - sc.last_x) * ts
    y = sc.last_y + (sc.y - sc.last_y) * ts
    if leg_rgb is None:
        leg_rgb = _scale_rgb(body_rgb, 0.78)
    if hand_rgb is None:
        hand_rgb = _mix_rgb(body_rgb, head_rgb, 0.55)
    f = 1.0 if sc.facing >= 0 else -1.0
    phase = sc.walk_phase * math.tau
    step = clampf(abs(sc.vx) * 0.5, 0.0, 1.0) * 3.0
    lean = clampf(sc.vx * 1.2, -3.0, 3.0)
    # 三个骨点（原版 bodyChunks：胸 / 髋 / 头）
    chx, chy = x + lean * 0.6, y - SCAV_CHEST_DY
    hdx, hdy = x + 6.0 * f + lean, chy - SCAV_HEAD_DY
    neck_rgb = _mix_rgb(body_rgb, head_rgb, 0.55)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # 腿（原版 ScavengerLeg 就是 "pixel" 线段，只有宽窄之分）
    painter.setPen(QPen(QColor(*leg_rgb), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for i, sgn in ((0, -1.0), (1, 1.0)):
        swing = math.sin(phase + (0.0 if i == 0 else math.pi)) * step
        lx = x + sgn * 3.0 * f
        painter.drawLine(QPointF(lx, y - 2.0), QPointF(lx + swing * f, y + SCAV_STANCE))
    # 短尾
    painter.setPen(QPen(QColor(*leg_rgb), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(x - 2.0 * f, y - 3.0), QPointF(x - 9.0 * f, y - 8.0))
    # 腰（髋→胸）与颈（胸→头）
    _tapered(painter, x, y, chx, chy, SCAV_HIP_R * 0.9, SCAV_CHEST_R * 0.75, body_rgb)
    _tapered(painter, chx, chy, hdx, hdy, SCAV_CHEST_R * 0.5, SCAV_HIP_R * 0.55, neck_rgb)
    # 髋（原版 scale = rad/15 → 直径 2*rad，但 Circle20 本身直径即贴图 20）
    _circle(painter, atlas, x, y, SCAV_HIP_R * 2.0, SCAV_HIP_R * 2.0, body_rgb)
    # 胸（原版最粗一节）
    _circle(painter, atlas, chx, chy, SCAV_CHEST_R * 2.0 * SCAV_CHEST_W,
            SCAV_CHEST_R * 2.15, body_rgb)
    # 臂：上臂下探 + 前臂前伸，末端原版 ScavengerHandA/B
    painter.setPen(QPen(QColor(*body_rgb), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(chx, chy + 1.0), QPointF(chx + 6.0 * f, chy + 10.0))
    painter.drawLine(QPointF(chx, chy + 1.5), QPointF(chx + 12.0 * f, chy + 5.0))
    _blit_hand(painter, atlas, chx + 12.0 * f, chy + 5.0, f, hand_rgb)
    # 头（原版 headSize 决定大小与朝向下的压扁）
    _circle(painter, atlas, hdx, hdy, 14.4 * SCAV_S * SCAV_HEAD_W,
            15.0 * SCAV_S, head_rgb, rot=0.0)
    # 眼（原版两只眼是后脑两侧的小 Circle20）
    for sgn in (-1.0, 1.0):
        _circle(painter, atlas, hdx - 2.0 * f + sgn * 2.6 * f, hdy - 0.4,
                3.6, 2.8, eye_rgb)
    painter.restore()


def _blit_hand(painter, atlas, x, y, f, rgb) -> None:
    """手（原版 ScavengerHandA，18x20 贴图）。"""
    blit(painter, atlas, SCAV_HAND, x, y, 90.0 * (1.0 if f > 0 else -1.0),
         1.0, 1.0, rgb)


def draw_scavenger_spear(painter, atlas, sc, ts=1.0) -> None:
    """拾荒者手里的矛（原版 SmallSpear，瞄准时后仰）。"""
    sp = getattr(sc, "spear", None)
    if sp is None:
        return
    x = sp.last_x + (sp.x - sp.last_x) * ts
    y = sp.last_y + (sp.y - sp.last_y) * ts
    ang = sp.last_angle + (sp.angle_deg - sp.last_angle) * ts
    draw_spear(painter, atlas, x, y, ang, length=SPEAR_DRAW_LEN)
