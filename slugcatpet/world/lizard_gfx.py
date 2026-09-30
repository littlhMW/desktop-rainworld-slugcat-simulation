"""蜥蜴渲染：脊柱带状躯干+尾、头部件（颚/齿/头/眼）、程序化四肢。坐标 y↓。

对照 LizardGraphics.InitiateSprites / DrawSprites：
- 头 5 片共用 anchorY（游戏从底部量 0.7）→ 本文件 ay = 1 - anchorY = 0.30；
  白蜥（headGraphics[4]==3）仅眼睛片 anchorY=0.75 → ay=0.25。
- 旋转 = aim(颈→头)（0=上、顺时针为正，与 Qt/QPainter.rotate 同号）。
- 朝向：整组头部件按 scaleX = Sign(headDepthRotation) 镜像（同游戏），朝右时该值为 -1
  （原版 LizardGraphics.Update 的 swim 分支：head.x > neck.x → -1）。只转不镜像会让头上下颠倒。
- 张口：上颚组（UpperTeeth/Head/Eyes）转 +A*(1-lf)*jaw*num，下颚组（Jaw/LowerTeeth）转
  -A*lf*jaw*num；位移沿头轴法线 n3 上下分开 A*jaw*num*BODY_SCALE（num = headDepthRotation）。
- 四肢：同游戏 LizardArm_XX 贴图（锚点=中心(0.5,0.5)，位置钉在脚上，
  旋转 = aim(脚→髋) - 90；贴图未旋转时「贴图 +x」指向脚），
  上面叠一层 LizardArmColor_XX 品种色（远侧腿压暗），形成原版「暗底 + 亮面」的腿。
- 体色：同游戏 BodyColor：白蜥纯白，蝾螈灰白，其余 = palette.blackColor（近黑），
  尾梢按 tailColoration 曲线渐变到品种色（effectColor）；头=品种色，齿/眼 = palette.blackColor。
"""
from __future__ import annotations
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath

from ..core.units import clampf, lerp, inv_lerp
from .lizard import (BODY_SCALE, BLACK_RGB, HEAD_DEFLECT_FLASH,
                     _ang_from_up, _ang_lerp)
from . import lizard_cos as _cos
from ..rendering.pixelmode import aa_hint
from ..rendering.primitives import _qcolor

HEAD_KEY = "base"


def head_row(lz, ts: float) -> int:
    """头片行号 num14（原版 LizardGraphics.DrawSprites：3 - int(|num| * 3.9)）。

    num = headDepthRotation 的插值：|num|≈1 → 行 0（正侧面，平时走路）；
    |num|→0 → 行 3（正对/背对镜头，转身途中经过），中间行 1/2 是斜前/斜后。
    贴图集里 LizardHead0..3 / Jaw / Teeth / Eyes 四行都在，直接用。
    """
    num = lerp(lz.last_head_depth, lz.head_depth, ts)
    return max(0, min(3, 3 - int(abs(num) * 3.9)))
# 原版 FSprite.rotation 的符号：FNode.UpdateMatrix 用 SetScaleThenRotate(..., rot * -pi/180)
# 建 [sx*cos, sx*sin ; -sy*sin, sy*cos]（FMatrix.cs:55 / FNode.cs:545），把「贴图 +y」
# （LizardHead* 画布短边朝吻部）转到屏幕朝前方向 —— 与 Qt 的顺时针 rotate(rot) 完全同号，
# 所以 Qt 直接用同一个 rot、scaleX = Sign(headDepthRotation)*headSize、scaleY = +headSize，
# 不需要任何 +180 / sy 取负（那会把左向张口时的上下颚转反，见 _draw_head 的推导）。

BODY_TOP_K = 1.16              # 体色很轻的垂向受光（原版体色近黑，不能提亮太多）
BODY_BOT_K = 0.72
HEAD_FLICKER_EXC = 0.2         # 原版 HeadColor 呼吸系数里的 excitement 取值
LIMB_NEAR_A = 1.0              # 近侧腿色层不透明度
LIMB_FAR_A = 0.30              # 远侧腿色层压暗（原版 Lerp(1, 0.3, |depthRotation|)）
BODY_TINT = 0.30               # 体色里掺入的品种色比例（见 body_color）
BODY_EDGE_K = 0.55
NECK_K = _cos.NECK_RAD_K       # 颈根半径系数（相对躯干半径）


def _shade(rgb, k):
    return (int(clampf(rgb[0] * k, 0, 255)),
            int(clampf(rgb[1] * k, 0, 255)),
            int(clampf(rgb[2] * k, 0, 255)))


def _mix(a, b, t):
    t = clampf(t, 0.0, 1.0)
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def body_color(lz):
    """体色：LizardGraphics.cs:2141-2143 —— 除白蜥/蝾螈/焦糖/草莓外全是 palette.blackColor。

    原版不往体色里掺品种色（亮色只出现在头、尾梢、刺上）。旧版掺了 BODY_TINT，
    于是「深色区域」被染成了深绿/深粉；按反编译改成纯黑。
    """
    rgb = lz.body_rgb or lz.breed.body_rgb      # 白蜥随机色版：整只走个体色
    # 白蜥：整只统一用「周边局部采样」平滑出的迷彩色，再按呼吸在白色 ↔ 它之间换
    camo = getattr(lz, "camo_color", None)
    if camo is not None and getattr(lz, "camo_mix", 0.0) > 0.0:
        rgb = _mix(rgb, camo, lz.camo_mix)
    if lz.hurt_flash > 0:                 # 受击白闪（同游戏被创瞬间整体发白）
        rgb = _mix(rgb, (255, 255, 255), 0.45 * lz.hurt_flash / 8.0)
    return rgb


def head_color(lz, ts: float):
    """原版 LizardGraphics.HeadColor：头色在 palette.blackColor 与 effectColor 间「呼吸」闪烁。

    白蜥／蝾螈／黑蜥在原版是恒定色分支（发光、雪盖等），宠物里直接取品种定色。
    """
    b = lz.breed
    base = b.head_rgb if b.head_rgb is not None else lz.color
    if lz.head_flash > 0:
        # 头甲把矛弹开：头部打一层强烈的白（用户口径：弹开要看得出来）
        return _mix(base, (255, 255, 255),
                    0.55 + 0.45 * lz.head_flash / HEAD_DEFLECT_FLASH)
    if lz.hurt_flash > 0:
        return _mix(base, (255, 255, 255), 0.45 * lz.hurt_flash / 8.0)
    if lz.dead:                            # 尸体：头色定住、不再呼吸闪烁
        return b.head_rgb if b.head_rgb is not None else _mix(BLACK_RGB, lz.color, 0.22)
    if b.head_rgb is not None:
        return b.head_rgb
    ph = lerp(lz.last_blink, lz.blink, ts)
    a = 1.0 - (0.5 + 0.5 * math.sin(ph * math.tau)) ** (1.5 + HEAD_FLICKER_EXC * 1.5)
    # 原版 HeadColor1 = palette.blackColor（宠物近似 = 深色躯干色），HeadColor2 = effectColor
    # 白蜥这类「整只走个体色」的品种，深相位取近黑（原版那双色是白/迷彩，宠物里取对比更明显的黑）
    dark = BLACK_RGB if lz.body_rgb is not None else body_color(lz)
    return _mix(dark, lz.color, a)


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
    for i in range(1, len(left)):
        p0 = left[i-1]; p1 = left[i]
        mid = QPointF((p0.x()+p1.x())*0.5,(p0.y()+p1.y())*0.5)
        path.quadTo(p0, mid)
    path.lineTo(left[-1])
    for i in range(len(right)-1,-1,-1):
        path.lineTo(right[i])
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)
    return path


def _blit(p, atlas, frame, tint, x, y, rot, sx, sy, ax, ay, key=HEAD_KEY,
          opacity=1.0):
    """锚点 (ax, ay)（ay 自图像顶部量）钉在 (x, y)，顺时针 rot 度。"""
    at = atlas.get(key)
    if not at.has(frame):
        return
    pm = at.sprite(frame, _qcolor(tint))
    w, h = float(pm.width()), float(pm.height())
    p.save()
    p.setOpacity(opacity)
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
        # 走动上下颠只作用在躯干三节（原版 drawPositions[0..2].y += bob*walkBob）
        bob = lz.bob[k] if k < len(lz.bob) else 0.0
        spine.append((lerp(s.lx, s.x, ts), lerp(s.ly, s.y, ts) + bob))
        r = s.rad
        if not s.tail:                       # 躯干中段略鼓
            r *= (0.94, 1.06, 1.00)[min(k, 2)]
        elif n_tail:                         # 尾梢收细（二次曲线，避免长楔形）
            t = (k - n_body + 1) / float(n_tail)
            r *= 1.0 - 0.30 * t * t
        rads.append(r)

    jaw = lerp(lz.last_jaw, lz.jaw, ts)
    # 头片朝向 = AI 算出的注视角（原版 num12 = aim(颈→头)，头部由 head 绳索 + look 混合驱动）。
    # 旧实现直接拿「颈→头」的几何向量：头贴着躯干永远水平 ⇒ AI 明明在看上方/下方也画不出来。
    if getattr(lz, "head_driven", False):
        rot = _ang_lerp(lz.last_head_angle, lz.head_angle, ts)
        # 低频动画噪声：个体差异（A 头微抬、B 头微低、C 尾慢摆），不是每帧随机抖
        rot += math.sin(lz._tick * 0.07 + lz.seed * 1.73) * 1.5
    else:
        rot = _ang_from_up(hpx - s0x, hpy - s0y)
    color = lz.color

    p.save()
    aa_hint(p)
    p.setPen(Qt.PenStyle.NoPen)

    _draw_body(p, lz, spine, rads)
    # 远侧腿（偶数号）先画，再画近侧腿（奇数号）；四足时即 (0,2,1,3)
    n_leg = len(lz.legs)
    for i in list(range(0, n_leg, 2)) + list(range(1, n_leg, 2)):
        _draw_leg(p, atlas, lz, i, ts)
    # 原版挂载序：BehindHead 花纹夹在躯干与头之间，InFront 花纹压在头之上
    _draw_cosmetics(p, atlas, lz, spine, rads, ts, _cos.Z_BEHIND_HEAD)
    _draw_head(p, atlas, lz, hx, hy, s0x, s0y, rot, jaw, head_color(lz, ts), ts)
    _draw_cosmetics(p, atlas, lz, spine, rads, ts, _cos.Z_FRONT)
    p.restore()


def _draw_body(p, lz, spine, rads):
    """躯干+尾：单条带，垂向渐变受光，尾梢按游戏曲线染尾色。

    白蜥（``body_rgb`` 有值的个体色/迷彩品种）不叠受光阴影：原版这一类整只是
    均匀的 palette 色，加渐变会把它从「背景色块」变成「有体积感的亮块」，反而
    破坏迷彩效果。
    """
    rgb = body_color(lz)
    path = _strip_path(spine, rads)
    if lz.body_rgb is not None:           # 白蜥：纯色，无渐变无描边
        p.setBrush(QColor(*rgb))
        p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        return
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
            p.setClipPath(path, Qt.ClipOperation.IntersectClip)
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
    pi = lg.pair if lg.pair < len(lz.seg) else len(lz.seg) - 1
    seg = lz.seg[pi]
    return lerp(seg.lx, seg.x, ts), lerp(seg.ly, seg.y, ts)


def _spine_at(spine, rads, s):
    """按归一化体长 s∈[0,1] 在脊柱折线上取样（几何在 lizard_cos.spine_at）。"""
    return _cos.spine_at(spine, rads, s)


def _frame_h(atlas, frame):
    """LizardScaleA<g> 的原始像素高（原版 scaleY = length / graphicHeight）。"""
    try:
        return float(atlas.source_size(HEAD_KEY, frame)[1]) or 1.0
    except Exception:
        return 1.0


def _cos_ay(kind):
    """各族 anchorY（游戏自底部量）→ 本工程 ay（自顶部量）。"""
    if kind in _cos.PHYS_KINDS:
        return 1.0 - 0.10                    # LongBodyScales: anchorY = 0.1
    if kind in ("SpineSpikes", "TailFin"):
        return 1.0 - 0.15
    if kind == "WingScales":
        return 1.0                           # anchorY = 0
    return 0.95


def _draw_cosmetics(p, atlas, lz, spine, rads, ts, layer):
    """品种花纹（world/lizard_cos.py 的生成结果）。

    层级：原版 LizardGraphics.AddToContainer 按各族 spritesOverlap 分三次挂载 ——
    BehindHead（背刺/体鳞/尾羽/鳃/条纹/尾鳍）夹在躯干与头之间，InFront（头冠/
    翅鳞/胡须/触须/跳环）在头之上。以前一股脑画在最后，背刺会盖住头。

    物理：LongBodyScales 族的鳞尖是 LizardScale 摆锤（``Lizard._step_cosmetics``
    每 tick 算好，这里只按 ts 读），贴图从附着点指向鳞尖 ⇒ 转身/急停时鳞片滞后
    摆动；其余族按 GetBackPos 的法线刚性摆放（背刺还要随 |depth| 收短）。

    贴图朝向：原版所有鳞片都沿「体表外法线 ↔ 体轴后掠」方向画，不随 x 正负翻转；
    这里的 180° 翻转只用于我们这套「法线恒朝背侧」的近似（x 压到腹侧时）。
    """
    cos = getattr(lz, "cosmetics", None)
    if not cos:
        return
    pts = getattr(lz, "cosmetic_pts", None)
    body = body_color(lz)
    head = head_color(lz, 1.0)
    eff = lz.color
    depth = clampf(lerp(lz.last_depth, lz.depth, ts), -1.0, 1.0)
    sgn = 1.0 if depth >= 0.0 else -1.0
    for ci, c in enumerate(cos):
        if _cos.SPRITE_Z.get(c.kind, _cos.Z_BEHIND_HEAD) != layer:
            continue
        insts = getattr(c, "insts", None)
        if not insts:
            continue
        st = pts[ci] if pts is not None and ci < len(pts) else None
        frame = "LizardScaleA%d" % c.graphic
        frame_b = "LizardScaleB%d" % c.graphic
        gh = _frame_h(atlas, frame)
        base_col = head if c.a_head else body
        ay = _cos_ay(c.kind)
        for ii, inst in enumerate(insts):
            x, y, length, width = inst[0], inst[1], inst[2], inst[3]
            pt, (nx, ny), rad = _spine_at(spine, rads, y)
            # 原版 GetBackPos: outerPos = pos + perp * Clamp(x + f)；本工程法线恒朝背侧，
            # 折叠成 k = Clamp(|f| - Sign(depth)*x)（|depth|=1 时鳞片全贴到背脊一条线上）。
            k = clampf(abs(_cos.depth_f(y, depth)) - sgn * x, -1.0, 1.0)
            ox = pt[0] + nx * (k * rad)
            oy = pt[1] + ny * (k * rad)
            sy = max(0.12, length / gh)
            sx = c.scale_x * width * (1.0 if k >= 0.0 else -1.0)
            spin = st[ii] if st is not None else None
            dx = dy = 0.0
            if spin is not None:
                dx = lerp(spin[4], spin[0], ts) - ox
                dy = lerp(spin[5], spin[1], ts) - oy
            if abs(dx) + abs(dy) > 1e-6:
                ang = math.degrees(math.atan2(dx, -dy))
            else:
                ang = math.degrees(math.atan2(nx, -ny))
                if c.kind == "SpineSpikes":
                    sy *= max(0.2, inv_lerp(0.0, 0.5, abs(depth)))
                if k < 0.0:
                    ang += 180.0
            _blit(p, atlas, frame, base_col, ox, oy, ang, sx, sy, 0.5, ay)
            if c.colored:
                if c.gradient:
                    t = clampf(inv_lerp(0.42, 1.0, y), 0.0, 1.0)
                    bcol = _mix(base_col, eff, t)
                elif c.colored_mode == 2:
                    bcol = _mix(eff, base_col, clampf(y ** 0.5, 0.0, 1.0))
                else:
                    bcol = eff
                _blit(p, atlas, frame_b, bcol, ox, oy, ang, sx, sy, 0.5, ay)


def _draw_leg(p, atlas, lz, i, ts):
    """一条腿：游戏 LizardArm_XX（锚点=中心、按髋→脚距离选帧）+ 品种色层。

    LizardGraphics.cs:1774-1806：
      val = clamp(int(|脚-髋| / (4*limbSize)) + 1, 1, 9)
            + 9 * (2 - int(clamp(|flip| * 3, 0, 2)))      # flip 越小越取「中段」帧
      后腿 +27；rotation = aim(髋→脚) - 90；scaleY = Sign(flip) * limbThickness
    贴图从脚点向髋方向长（锚点在画布中心，内容偏下），与游戏一致。
    """
    lg = lz.legs[i]
    fx = lerp(lg.lx, lg.x, ts)
    fy = lerp(lg.ly, lg.y, ts)
    hx, hy = _leg_anchor(lz, lg, ts)
    if lg.pair == 0 and len(lz.seg) > 1:             # 游戏：前腿髋 20% 拉向第 1 节
        s1 = lz.seg[1]
        hx = lerp(hx, lerp(s1.lx, s1.x, ts), 0.2)
        hy = lerp(hy, lerp(s1.ly, s1.y, ts), 0.2)
    ux, uy = hx - fx, hy - fy                        # 脚→髋
    dist = math.hypot(ux, uy)
    if dist < 1e-3:
        return
    b = lz.breed
    flip = lg.flip
    val = int(dist / (4.0 * max(0.05, b.limb_size))) + 1
    val = max(1, min(9, val))
    val += 9 * (2 - int(clampf(abs(flip) * 3.0, 0.0, 2.0)))
    if lg.back:
        val += 27
    rot = math.degrees(math.atan2(-uy, -ux))         # = 原版 aim(髋→脚) - 90
    sx = 1.0                                         # 原版只设 scaleY，scaleX 恒为 1
    sy = (1.0 if flip >= 0.0 else -1.0) * b.limb_thickness
    # 远侧腿的色层按 |depthRotation| 压暗（原版 Lerp(1, 0.3, |depth|)，只压偶数号腿）
    far_a = lerp(1.0, 0.3, abs(lerp(lz.last_depth, lz.depth, ts)))
    _blit(p, atlas, "LizardArm_%02d" % val, body_color(lz),
          fx, fy, rot, sx, sy, 0.5, 0.5)
    _blit(p, atlas, "LizardArmColor_%02d" % val, b.head_rgb or lz.color,
          fx, fy, rot, sx, sy, 0.5, 0.5,
          opacity=LIMB_NEAR_A if lg.near else far_a)



def _draw_head(p, atlas, lz, hx, hy, s0x, s0y, rot, jaw, color, ts=1.0):
    """头 5 片：下颚组（Jaw/LowerTeeth）+ 上颚组（UpperTeeth/Head/Eyes）。

    逐行移植 LizardGraphics.cs:1890-1921 的头部段（P9=vector9，头绘制点）：
      num12 = aim(颈→头)                      （= rot，见 draw_lizard）
      normalized3 = PerpendicularVector(颈-头) （屏幕等价见下）
      上颚组 i>=2：pos = P9 + n3 * (jaw*num*jawsApart*(1-ljf))
                   rot = num12 + jawOpenAngle*(1-ljf)*jaw*num
      下颚组 i<2 ：pos = P9 - n3 * (jaw*num*jawsApart*ljf)
                   rot = num12 - jawOpenAngle*ljf*jaw*num
      scaleX = Sign(num)*headSize，scaleY = headSize     （num = headDepthRotation）
    原版没有独立 facing：镜像完全由 Sign(headDepthRotation) 决定，且朝右时
    depthRotation = -1（见 LizardGraphics.Update 的 swim 分支与 FNode.UpdateMatrix）。

    Futile 的 FSprite.rotation θ 实际以 R(-θ) 建矩阵（FNode.cs:545 的 *-0.01745329f），
    与 Qt 的顺时针 rotate(θ) 同向 —— 所以 Qt 直接用同一个角度、scale 也一致，
    不需要额外的 +180 / sy 取负（那会变成左右镜像）。
    """
    b = lz.breed
    hg = b.head_graphics
    num = lerp(lz.last_head_depth, lz.head_depth, ts)
    vnx, vny = s0x - hx, s0y - hy                # 颈-头（屏幕 y↓）
    L = math.hypot(vnx, vny) or 1.0
    n3x, n3y = vny / L, -vnx / L                 # 游戏 normalized3 的屏幕等价
    apart = b.jaw_apart * jaw * num * BODY_SCALE
    lf = b.jaw_lower_fac
    up_off = apart * (1.0 - lf)
    lo_off = -apart * lf
    up_rot = rot + b.jaw_open_angle * (1.0 - lf) * jaw * num
    lo_rot = rot - b.jaw_open_angle * lf * jaw * num
    sc = b.head_size * BODY_SCALE
    sx = (1.0 if num >= 0.0 else -1.0) * sc      # 原版 scaleX = Sign(num)
    row = head_row(lz, ts)
    head_rgb = color                             # 原版 HeadColor（含呼吸闪烁）
    teeth_rgb = BLACK_RGB                        # 原版 ApplyPalette：齿、眼 = palette.blackColor
    ay = 1.0 - b.anchor_y
    eyes_ay = 0.25 if hg[4] == 3 else ay
    for part, idx in (("Jaw", 0), ("LowerTeeth", 1)):
        _blit(p, atlas, "Lizard%s%d.%d" % (part, row, hg[idx]),
              head_rgb if idx == 0 else teeth_rgb,
              hx + n3x * lo_off, hy + n3y * lo_off, lo_rot, sx, sc, 0.5, ay)
    for part, idx in (("UpperTeeth", 2), ("Head", 3)):
        _blit(p, atlas, "Lizard%s%d.%d" % (part, row, hg[idx]),
              teeth_rgb if idx == 2 else head_rgb,
              hx + n3x * up_off, hy + n3y * up_off, up_rot, sx, sc, 0.5, ay)
    if not b.hide_eyes:
        _blit(p, atlas, "LizardEyes%d.%d" % (row, hg[4]), BLACK_RGB,
              hx + n3x * up_off, hy + n3y * up_off, up_rot, sx, sc, 0.5, eyes_ay)
