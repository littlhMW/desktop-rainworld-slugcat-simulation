"""蜥蜴渲染：脊柱带状躯干+尾、头部件（颚/齿/头/眼）、程序化四肢。坐标 y↓。

对照 LizardGraphics.InitiateSprites / DrawSprites：
- 头 5 片共用 anchorY（游戏从底部量 0.7）→ 本文件 ay = 1 - anchorY = 0.30；
  白蜥（headGraphics[4]==3）仅眼睛片 anchorY=0.75 → ay=0.25。
- 旋转 = aim(躯干节→头)（0=上、顺时针为正，与 Qt/QPainter.rotate 同号）。
- 朝向：头朝左时整组头部件按 scaleX=-1 镜像（同游戏 Sign(headDepthRotation)）；
  只转不镜像会让头上下颠倒，且颚的开合位移方向也会反。
- 张口：上颚组（UpperTeeth/Head/Eyes）转 -A*(1-lf)*jaw，下颚组（Jaw/LowerTeeth）转 +A*lf*jaw，
  位移沿头轴法线上下分开 A*jaw*BODY_SCALE。
- 四肢：游戏用 LizardArm_XX 贴图（脚点锚定 + atan2 旋转），但 24px 级别下呈「拱形」不好看，
  这里改为程序化「髋→膝→脚」锥形折线，前腿膝向后、后腿膝向前，脚掌朝前。
- 体色：游戏用房间调色板（近似中性灰）× effectColor，这里取固定中性灰与品种色混合。
"""
from __future__ import annotations
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from ..core.units import clampf, lerp, inv_lerp
from .lizard import BODY_SCALE, _ang_from_up

HEAD_KEY = "base"
NUM14 = 0                      # 头片行号：0 = 正侧面（游戏 |headDepthRotation|≈1）

NEUTRAL = (150, 156, 168)      # 中性体色（代替房间调色板）
BODY_TINT = 0.46
HEAD_TINT = 0.56
EYE_RGB = (238, 244, 250)      # 眼睛：亮色高光（游戏里用房间调色板，这里取亮色更好认）
NEAR_LEG_K = 1.0
FAR_LEG_K = 0.82
LIMB_EDGE_W = 1.7              # 四肢描边总加宽（每侧 ~0.85px）
BODY_TOP_K = 1.10
BODY_BOT_K = 0.74
BODY_EDGE_K = 0.55
NECK_K = 0.82                  # 颈根半径系数（相对躯干半径）


def _shade(rgb, k):
    return (int(clampf(rgb[0] * k, 0, 255)),
            int(clampf(rgb[1] * k, 0, 255)),
            int(clampf(rgb[2] * k, 0, 255)))


def _mix(a, b, t):
    t = clampf(t, 0.0, 1.0)
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _strip_path(pts, halfw) -> QPainterPath:
    """沿中心线按半宽挤出闭合多边形。"""
    n = len(pts)
    path = QPainterPath()
    if n < 2:
        return path

    def normal(i):
        ax, ay = pts[max(0, i - 1)]
        bx, by = pts[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        return -dy / L, dx / L

    left, right = [], []
    for i, (cx, cy) in enumerate(pts):
        nx, ny = normal(i)
        hw = halfw[i]
        left.append(QPointF(cx + nx * hw, cy + ny * hw))
        right.append(QPointF(cx - nx * hw, cy - ny * hw))
    path.moveTo(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)
    return path


def _blit(p, atlas, frame, tint, x, y, rot, sx, sy, ax, ay, key=HEAD_KEY):
    """锚点 (ax, ay)（ay 自图像顶部量）钉在 (x, y)，顺时针 rot 度。"""
    at = atlas.get(key)
    if not at.has(frame):
        return
    pm = at.sprite(frame, QColor(*tint))
    w, h = float(pm.width()), float(pm.height())
    p.save()
    p.translate(x, y)
    if rot:
        p.rotate(rot)
    if sx != 1.0 or sy != 1.0:
        p.scale(sx, sy)
    p.drawPixmap(QRectF(-ax * w, -ay * h, w, h), pm, QRectF(pm.rect()))
    p.restore()


def draw_lizard(p, atlas, lz, ts: float) -> None:
    """绘制一只蜥蜴：躯干带 → 四肢 → 头。"""
    ts = clampf(ts, 0.0, 1.0)
    # 头绘制点：头部 20% 拉向第 0 节（同游戏 vector9 / 体带起点 a）
    hpx = lerp(lz.last_x, lz.x, ts)
    hpy = lerp(lz.last_y, lz.y, ts)
    s0x = lerp(lz.seg[0].lx, lz.seg[0].x, ts)
    s0y = lerp(lz.seg[0].ly, lz.seg[0].y, ts)
    hx = hpx + (s0x - hpx) * 0.2
    hy = hpy + (s0y - hpy) * 0.2

    spine = [(hx, hy)]
    rads = [lz.body_rad * NECK_K]
    n_body = sum(1 for s in lz.seg if not s.tail)
    n_tail = sum(1 for s in lz.seg if s.tail)
    for k, s in enumerate(lz.seg):
        spine.append((lerp(s.lx, s.x, ts), lerp(s.ly, s.y, ts)))
        r = s.rad
        if not s.tail:                       # 躯干中段略鼓
            r *= (0.94, 1.06, 1.00)[min(k, 2)]
        elif n_tail:                         # 尾梢收细（二次曲线，避免长楔形）
            t = (k - n_body + 1) / float(n_tail)
            r *= 1.0 - 0.30 * t * t
        rads.append(r)

    jaw = lerp(lz.last_jaw, lz.jaw, ts)
    rot = _ang_from_up(hpx - s0x, hpy - s0y)
    color = lz.color

    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)

    _draw_body(p, lz, spine, rads, color)
    for i in (0, 2, 1, 3):                      # 远侧前后腿 → 近侧前后腿
        _draw_leg(p, atlas, lz, i, ts)
    _draw_head(p, atlas, lz, hx, hy, rot, jaw, color)
    p.restore()


def _body_color(color):
    return _mix(NEUTRAL, color, BODY_TINT)


def _draw_body(p, lz, spine, rads, color):
    """躯干+尾：单条带，垂向渐变受光，尾梢按游戏曲线染尾色。"""
    rgb = _body_color(color)
    path = _strip_path(spine, rads)
    x0, y0 = spine[0]
    x1, y1 = spine[-1]
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    span = max(rads) * 2.2
    grad = QLinearGradient(QPointF((x0 + x1) * 0.5 + nx * span, (y0 + y1) * 0.5 + ny * span),
                           QPointF((x0 + x1) * 0.5 - nx * span, (y0 + y1) * 0.5 - ny * span))
    grad.setColorAt(0.0, QColor(*_shade(rgb, BODY_TOP_K)))
    grad.setColorAt(1.0, QColor(*_shade(rgb, BODY_BOT_K)))
    p.setBrush(grad)
    p.drawPath(path)

    if lz.tail_edge is not None and lz.tail_amt > 0.0:
        n_tail = sum(1 for s in lz.seg if s.tail)
        if n_tail:
            idx = len(spine) - n_tail
            tpts = [spine[idx - 1]] + spine[idx:]
            thw = [rads[idx - 1] * 0.98] + [r * 0.98 for r in rads[idx:]]
            tpath = _strip_path(tpts, thw)
            p.save()
            p.setClipPath(path)
            tg = QLinearGradient(QPointF(*tpts[0]), QPointF(*tpts[-1]))
            for k in range(len(tpts)):
                t = k / max(1, len(tpts) - 1)
                f2 = inv_lerp(lz.breed.tail_col_start, 0.95, t)
                f2 = (f2 ** lz.breed.tail_col_exp) * lz.tail_amt
                tg.setColorAt(t, QColor(*_mix(rgb, lz.tail_edge, f2)))
            p.setBrush(tg)
            p.drawPath(tpath)
            p.restore()

    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = p.pen()
    pen.setColor(QColor(*_shade(rgb, BODY_EDGE_K)))
    pen.setWidthF(1.0)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)


def _leg_anchor(lz, lg, ts):
    """腿根 = 所挂躯干节中心（游戏里 limb 挂在 bodyChunk 上）。"""
    seg = lz.seg[0] if not lg.back else (lz.seg[2] if len(lz.seg) > 2 else lz.seg[-1])
    return lerp(seg.lx, seg.x, ts), lerp(seg.ly, seg.y, ts)


def _tapered(p, pts, widths, rgb, outline_rgb):
    """沿折线画锥形肢体：逐段圆头笔，先粗的描边层再填本色（细边、无珠子感）。"""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for col, extra in ((outline_rgb, LIMB_EDGE_W), (rgb, 0.0)):
        for k in range(len(pts) - 1):
            w = (widths[k] + widths[k + 1]) * 0.5 + extra
            pen = QPen(QColor(*col), max(0.8, w))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawLine(QPointF(*pts[k]), QPointF(*pts[k + 1]))
    p.restore()


def _draw_leg(p, atlas, lz, i, ts):
    """一条腿：髋→膝→脚 三段锥形折线 + 脚掌；远侧腿略暗。"""
    lg = lz.legs[i]
    hx, hy = _leg_anchor(lz, lg, ts)
    fx = lerp(lg.lx, lg.x, ts)
    fy = lerp(lg.ly, lg.y, ts) - lg.lift
    dx, dy = fx - hx, fy - hy
    d = math.hypot(dx, dy)
    if d < 1e-3:
        return
    ux, uy = dx / d, dy / d
    b = lz.breed
    w0 = lz.body_rad * 0.80 * b.limb_thickness
    w1 = lz.body_rad * 0.62 * b.limb_thickness
    w2 = lz.body_rad * 0.40 * b.limb_thickness
    # 膝：中点向「后（前腿）/前（后腿）」偏移，像蜥蜴的折腿
    bend = d * (0.22 if lg.back else 0.18)
    dirx = 1.0 if lg.back else -1.0
    kx = (hx + fx) * 0.5 + dirx * bend
    ky = (hy + fy) * 0.5 - abs(bend) * 0.10
    # 脚掌：朝身体前方伸出
    step = lz.body_rad * 0.55
    fx_dir = 1.0 if lz.facing >= 0 else -1.0
    tox, toy = fx + fx_dir * step, fy
    near = lg.near
    k = NEAR_LEG_K if near else FAR_LEG_K
    rgb = _shade(_body_color(lz.color), 0.86 * k)
    edge = _shade(_body_color(lz.color), BODY_EDGE_K * k)
    _tapered(p, [(hx, hy), (kx, ky), (fx, fy)], [w0, w1, w2], rgb, edge)
    _tapered(p, [(fx, fy), (tox, toy)], [w2, w2 * 0.75], rgb, edge)


def _draw_head(p, atlas, lz, hx, hy, rot, jaw, color):
    """头部件：下颚组（Jaw/LowerTeeth）+ 上颚组（UpperTeeth/Head/Eyes）。"""
    b = lz.breed
    hg = b.head_graphics
    a = math.radians(rot)
    hdx, hdy = math.sin(a), -math.cos(a)     # 头前向
    face = 1.0 if hdx >= 0.0 else -1.0       # 朝左时 sprite 水平镜像（同游戏 scaleX=Sign(num)）
    nx, ny = hdy * face, -hdx * face         # 背侧法线：恒指头的上方一侧
    apart = b.jaw_apart * jaw * BODY_SCALE
    lf = b.jaw_lower_fac
    up_off = apart * (1.0 - lf)
    lo_off = -apart * lf
    up_rot = rot - b.jaw_open_angle * (1.0 - lf) * jaw
    lo_rot = rot + b.jaw_open_angle * lf * jaw
    sc = b.head_size * BODY_SCALE
    sx = face * sc
    body_rgb = _body_color(color)
    head_rgb = _mix(NEUTRAL, color, HEAD_TINT)
    teeth_rgb = _shade(body_rgb, 1.30)
    ay = 1.0 - b.anchor_y
    eyes_ay = 0.25 if hg[4] == 3 else ay
    for part, idx in (("Jaw", 0), ("LowerTeeth", 1)):
        _blit(p, atlas, "Lizard%s%d.%d" % (part, NUM14, hg[idx]),
              head_rgb if idx == 0 else teeth_rgb,
              hx + nx * lo_off, hy + ny * lo_off, lo_rot, sx, sc, 0.5, ay)
    for part, idx in (("UpperTeeth", 2), ("Head", 3)):
        _blit(p, atlas, "Lizard%s%d.%d" % (part, NUM14, hg[idx]),
              teeth_rgb if idx == 2 else head_rgb,
              hx + nx * up_off, hy + ny * up_off, up_rot, sx, sc, 0.5, ay)
    if not b.hide_eyes:
        _blit(p, atlas, "LizardEyes%d.%d" % (NUM14, hg[4]), EYE_RGB,
              hx + nx * up_off, hy + ny * up_off, up_rot, sx, sc, 0.5, eyes_ay)
