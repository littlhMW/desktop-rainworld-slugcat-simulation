"""共享渲染原语：软绳/带状/三角网格/atlas sprite 绘制。"""
from __future__ import annotations
import math
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
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

# ── 珍珠 / 矛 / 拾荒者：程序化绘制（原版这三者也都是运行时生成的网格，图集里没有整只精灵）──

SPEAR_DRAW_LEN = 46.0       # 与世界 Spear.LEN 一致
PEARL_RIM_K = 0.92          # 外圈（品种色）相对半径
PEARL_CORE_K = 0.70         # 白芯相对半径


def draw_pearl(painter, x, y, rot_deg=0.0, tint=(255, 255, 255), rad=4.5,
               core=(255, 255, 255)) -> None:
    """珍珠：品种色外圈 + 白芯 + 一点高光。"""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(x, y)
    if rot_deg:
        painter.rotate(rot_deg)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*tint))
    painter.drawEllipse(QPointF(0.0, 0.0), rad, rad)
    painter.setBrush(QColor(*core))
    painter.drawEllipse(QPointF(0.0, 0.0), rad * PEARL_RIM_K * 0.85, rad * PEARL_CORE_K)
    painter.setBrush(QColor(255, 255, 255, 230))
    painter.drawEllipse(QPointF(-rad * 0.26, -rad * 0.30), rad * 0.26, rad * 0.22)
    painter.restore()


def draw_spear(painter, x, y, ang_deg, length=46.0,
               shaft=(94, 78, 60), tip=(206, 206, 198), width=2.6) -> None:
    """矛：锥形木杆 + 亮尖端；ang 0=朝上、顺时针为正（y↓），锚点=杆中点。"""
    a = math.radians(ang_deg)
    ux, uy = math.sin(a), -math.cos(a)
    bx, by = x - ux * length * 0.5, y - uy * length * 0.5
    tx, ty = x + ux * length * 0.5, y + uy * length * 0.5
    hx, hy = tx - ux * length * 0.26, ty - uy * length * 0.26
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(*shaft), width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(bx, by), QPointF(hx, hy))
    pen2 = QPen(QColor(*tip), width * 0.85)
    pen2.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(pen2)
    painter.drawLine(QPointF(hx, hy), QPointF(tx, ty))
    painter.restore()


def draw_scavenger(painter, sc, ts=1.0, body_rgb=(58, 60, 68), head_rgb=(226, 226, 214),
                   eye_rgb=(26, 26, 30), leg_rgb=None, spear_draw=None) -> None:
    """拾荒者：髋点驱动的两足 + 长臂 + 白面具头（原版为三角形网格，无整只精灵）。

    锚点 (x, y) = 髋部（sc.y 即髋心，脚下 7px 为地面）；头在髋上方 22px。
    """
    x = sc.last_x + (sc.x - sc.last_x) * ts
    y = sc.last_y + (sc.y - sc.last_y) * ts
    if leg_rgb is None:
        leg_rgb = (int(body_rgb[0] * 0.8), int(body_rgb[1] * 0.8), int(body_rgb[2] * 0.8))
    f = 1.0 if sc.facing >= 0 else -1.0
    stance = 7.0                       # 髋到脚
    phase = sc.walk_phase * math.tau
    step = clampf(abs(sc.vx) * 0.5, 0.0, 1.0) * 3.0
    lean = clampf(sc.vx * 1.2, -3.0, 3.0)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # 腿（两足，前后交替）
    painter.setPen(QPen(QColor(*leg_rgb), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for i, sgn in ((0, -1.0), (1, 1.0)):
        swing = math.sin(phase + (0.0 if i == 0 else math.pi)) * step
        hx = x + sgn * 3.0 * f
        painter.drawLine(QPointF(hx, y - 2.0),
                         QPointF(hx + swing * f, y + stance))
    # 短尾
    painter.setPen(QPen(QColor(*leg_rgb), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(x - 2.0 * f, y - 3.0), QPointF(x - 9.0 * f, y - 7.0))
    # 躯干：髋→肩的锥形
    shx, shy = x + lean + 1.5 * f, y - 14.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*body_rgb))
    torso = QPainterPath()
    torso.moveTo(x - 4.6, y + 1.0)
    torso.lineTo(x + 4.6, y + 1.0)
    torso.lineTo(shx + 3.6, shy)
    torso.lineTo(shx - 3.6, shy)
    torso.closeSubpath()
    painter.drawPath(torso)
    # 手臂（持矛手在前）
    painter.setPen(QPen(QColor(*body_rgb), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(shx, shy + 1.0), QPointF(shx + 6.0 * f, shy + 11.0))
    painter.drawLine(QPointF(shx, shy + 1.5), QPointF(shx + 12.0 * f, shy + 6.0))
    # 头 + 面具
    hx, hy = x + 6.0 * f + lean, y - 22.0
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*body_rgb))
    painter.drawEllipse(QPointF(hx - 1.0 * f, hy + 1.0), 6.2, 5.6)
    painter.setBrush(QColor(*head_rgb))
    painter.drawEllipse(QPointF(hx + 1.6 * f, hy - 0.4), 5.0, 4.4)
    painter.setBrush(QColor(*eye_rgb))
    painter.drawEllipse(QPointF(hx + 3.0 * f, hy - 0.6), 1.5, 1.1)
    painter.restore()


def draw_scavenger_spear(painter, sc, ts=1.0) -> None:
    """拾荒者手里的矛（瞄准时后仰）。"""
    sp = getattr(sc, "spear", None)
    if sp is None:
        return
    x = sp.last_x + (sp.x - sp.last_x) * ts
    y = sp.last_y + (sp.y - sp.last_y) * ts
    ang = sp.last_angle + (sp.angle_deg - sp.last_angle) * ts
    draw_spear(painter, x, y, ang, length=SPEAR_DRAW_LEN)
