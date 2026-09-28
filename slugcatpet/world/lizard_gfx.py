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
from .lizard import BODY_SCALE, BLACK_RGB, _ang_from_up
from ..rendering.pixelmode import aa_hint

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


def body_color(lz):
    """体色：原版取 palette.blackColor（明亮来自头/尾/刺）。

    宠物没有房间调色板，纯紫黑会读成一团黑；这里掺一点品种色当「暗染」，
    才像游戏里那种深绿 / 深粉的躯干。
    """
    rgb = lz.body_rgb or lz.breed.body_rgb      # 白蜥随机色版：整只走个体色
    rgb = _mix(rgb, lz.color, BODY_TINT) if rgb == BLACK_RGB else rgb
    if lz.hurt_flash > 0:                 # 受击白闪（同游戏被创瞬间整体发白）
        rgb = _mix(rgb, (255, 255, 255), 0.45 * lz.hurt_flash / 8.0)
    return rgb


def head_color(lz, ts: float):
    """原版 LizardGraphics.HeadColor：头色在 palette.blackColor 与 effectColor 间「呼吸」闪烁。

    白蜥／蝾螈／黑蜥在原版是恒定色分支（发光、雪盖等），宠物里直接取品种定色。
    """
    b = lz.breed
    if lz.hurt_flash > 0:
        base = b.head_rgb if b.head_rgb is not None else lz.color
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
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)
    return path


def _blit(p, atlas, frame, tint, x, y, rot, sx, sy, ax, ay, key=HEAD_KEY,
          opacity=1.0):
    """锚点 (ax, ay)（ay 自图像顶部量）钉在 (x, y)，顺时针 rot 度。"""
    at = atlas.get(key)
    if not at.has(frame):
        return
    pm = at.sprite(frame, QColor(*tint))
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
    rot = _ang_from_up(hpx - s0x, hpy - s0y)
    color = lz.color

    p.save()
    aa_hint(p)
    p.setPen(Qt.PenStyle.NoPen)

    _draw_body(p, lz, spine, rads)
    _draw_spikes(p, atlas, lz, spine, rads)
    for i in (0, 2, 1, 3):                      # 远侧前后腿 → 近侧前后腿
        _draw_leg(p, atlas, lz, i, ts)
    _draw_head(p, atlas, lz, hx, hy, s0x, s0y, rot, jaw, head_color(lz, ts), ts)
    p.restore()


def _draw_body(p, lz, spine, rads):
    """躯干+尾：单条带，垂向渐变受光，尾梢按游戏曲线染尾色。"""
    rgb = body_color(lz)
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


def _spine_at(spine, rads, s):
    """按归一化体长 s∈[0,1] 在脊柱折线上取样：返点、背侧法线（屏幕系）、该处半径。"""
    segs = []
    total = 0.0
    for k in range(len(spine) - 1):
        d = math.hypot(spine[k + 1][0] - spine[k][0], spine[k + 1][1] - spine[k][1])
        segs.append(d)
        total += d
    if total <= 0.0:
        return spine[0], (0.0, -1.0), rads[0]
    want = clampf(s, 0.0, 1.0) * total
    for k, d in enumerate(segs):
        if want <= d or k == len(segs) - 1:
            t = (want / d) if d > 0 else 0.0
            t = clampf(t, 0.0, 1.0)
            ax, ay = spine[k]
            bx, by = spine[k + 1]
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            nx, ny = -(by - ay), (bx - ax)
            L = math.hypot(nx, ny) or 1.0
            nx, ny = nx / L, ny / L
            if ny > 0.0:                    # 法线取背侧（屏幕上方）
                nx, ny = -nx, -ny
            return (px, py), (nx, ny), lerp(rads[k], rads[k + 1], t)
        want -= d
    return spine[-1], (0.0, -1.0), rads[-1]


def _draw_spikes(p, atlas, lz, spine, rads):
    """背刺（游戏 SpineSpikes）：A 片=体色，B 片=品种色（colored 1/2 两种）。"""
    if not lz.spikes:
        return
    graphic, colored, pts = lz.spikes
    n = len(pts)
    for k, (s, size) in enumerate(pts):
        if size <= 0.0:
            continue
        pt, (nx, ny), rad = _spine_at(spine, rads, s)
        x, y = pt[0] + nx * rad * 0.8, pt[1] + ny * rad * 0.8
        rot = math.degrees(math.atan2(nx, -ny))   # 贴图 local up 对齐法线
        tint = body_color(lz)
        _blit(p, atlas, "LizardScaleA%d" % graphic, tint, x, y, rot,
              size, size, 0.5, 0.85)
        if colored:
            t = k / max(1.0, n - 1.0)
            rgb = lz.color if colored == 1 else _mix(
                lz.breed.head_rgb or lz.color, tint, t ** 0.5)
            _blit(p, atlas, "LizardScaleB%d" % graphic, rgb, x, y, rot,
                  size, size, 0.5, 0.85)


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
    if not lg.back and len(lz.seg) > 1:              # 游戏：前腿髋 20% 拉向第 1 节
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
