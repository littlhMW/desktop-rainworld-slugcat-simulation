"""蝉乌贼渲染：复刻原版 CicadaGraphics（9 向贴图 + 双翅 + 触须 + 高光）。y↓。

对照 CicadaGraphics.DrawSprites：
- 贴图族 Cicada{n}{body,head,shield,eyes1,eyes2}：n=0 头朝下、n=4 头朝左、n=8 头朝上，
  每档 22.5°；n = clamp(int(8 - |aim|/180*9), 0, 8)。
- aim>0（头偏右）整组镜像 scaleX=-1、旋转 = aim - (8-n)*22.5；aim<=0 不镜像、
  旋转 = aim + (8-n)*22.5 —— 贴图自带朝向与旋转相加正好等于 aim。
- 翅膀 CicadaWingA/B（锚点 ax=0 即翅根）：旋转 = aim - 180 + (num8 + 扇动)*±1，
  扇动角 A 在 -65..40、B 在 -45..75；alpha 随身体横倒程度 |轴x|。
- 高光 = Circle20 钉在后背，长轴沿身体轴（原版 HighlightSprite）。
- 颜色：浅色个体（雄）近白、深色（雌）近黑；盾 = 品种色混；眼 1/2 深浅互补。
"""
from __future__ import annotations
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter

from ..core.units import clampf, lerp
from ..core.gfxmath import _hsl2rgb
from ..rendering.primitives import blit, draw_rope
from ..rendering.pixelmode import aa_hint

FOG_RGB = (78, 92, 104)
BLACK_RGB = (27, 11, 33)          # 同原版 palette.blackColor
WING_LEN = 1.0                    # 翅长（原版 iVars.wingLength≈1）
WING_THICK = 0.85
TENTACLE_W = (2.6, 1.3)
CIRCLE_SCALE = (5.0 / 20.0, 12.0 / 20.0)


def _rgb(h, s, l):
    r, g, b = _hsl2rgb(h % 1.0, s, l)
    return (int(clampf(r * 255.0, 0, 255)), int(clampf(g * 255.0, 0, 255)),
            int(clampf(b * 255.0, 0, 255)))


def _mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def palette(sc):
    """→ (体色, 盾色, 眼1, 眼2, 高光色)（对照 CicadaGraphics.ApplyPalette）。"""
    hue = sc.hue
    vivid = _rgb(hue, 1.0, 0.5)
    if sc.male:                                   # 浅色：近白
        body = _mix((255, 255, 255), FOG_RGB, 0.1)
        return (body, _mix(body, _rgb(hue, 0.5, 0.5), 0.4),
                vivid, BLACK_RGB, _mix(body, vivid, 0.07))
    body = _mix(_rgb(hue, 1.0, 0.0), BLACK_RGB, 0.85)   # 深色：近黑
    return (body, _mix(body, _rgb(hue, 0.5, 0.4), 0.8),
            _mix(body, BLACK_RGB, 0.8), vivid, _mix(body, (255, 255, 255), 0.7))


def _aim(sc) -> float:
    """身体轴朝头方向的角（0=上、顺时针正）。"""
    sp = math.hypot(sc.vx, sc.vy)
    if sp > 0.6:
        return math.degrees(math.atan2(sc.vx, -sc.vy))
    if sc.rest > 0 or sc.dead:                    # 落地/尸体：横躺
        return 90.0 * (1.0 if sc.facing >= 0 else -1.0)
    if sc.dir_x or sc.dir_y:
        return math.degrees(math.atan2(sc.dir_x, -sc.dir_y))
    return 0.0


def draw_squidcada(painter, atlas, sc, ts) -> None:
    """一只蝉乌贼；ts=0..1 插值因子。"""
    x = lerp(sc.last_x, sc.x, ts)
    y = lerp(sc.last_y, sc.y, ts)
    body, shield, eyes_a, eyes_b, glow = palette(sc)
    aim = _aim(sc)
    n = int(clampf(8.0 - abs(aim) / 180.0 * 9.0, 0.0, 8.0))
    d4 = (8 - n) * 22.5
    mirror = aim > 0.0
    rot = aim - d4 if mirror else aim + d4
    sx = -1.0 if mirror else 1.0
    ux, uy = math.sin(math.radians(aim)), -math.cos(math.radians(aim))   # 体轴
    px, py = -uy, ux                                                    # 体轴法线
    tilt = abs(ux)

    painter.save()
    aa_hint(painter)
    # 后背高光（原版 HighlightSprite：Circle20）
    hx, hy = x - ux * 6.0, y - uy * 6.0 + 3.0
    blit(painter, atlas, "Circle20", hx, hy, aim + 12.0,
         CIRCLE_SCALE[0] * lerp(1.0, 0.6, abs(tilt - 1.0) * 5.0),
         CIRCLE_SCALE[1] * lerp(1.0, 0.67, abs(tilt - 1.0) * 5.0), glow)
    # 四条触须（原版 TriangleMesh，简化成软绳）
    for i in (0, 1):
        for k in (0, 1):
            s = -1.0 if k == 0 else 1.0
            bx = x + ux * 9.0 + px * 4.5 * s
            by = y + uy * 9.0 + py * 4.5 * s
            len_ = 6.0 if i == 0 else 9.0
            draw_rope(painter, [(bx, by), (bx + px * 2.0 * s, by + len_)],
                      [TENTACLE_W[0], TENTACLE_W[1]], body)
    # 躯干 / 头 / 盾 / 眼
    blit(painter, atlas, "Cicada%dbody" % n, x, y, rot, sx, 1.0, body)
    blit(painter, atlas, "Cicada%dhead" % n, x, y, rot, sx, 1.0, body)
    blit(painter, atlas, "Cicada%dshield" % n, x, y, rot, sx, 1.0, shield)
    blit(painter, atlas, "Cicada%deyes1" % n, x, y, rot, sx, 1.0, eyes_a)
    blit(painter, atlas, "Cicada%deyes2" % n, x, y, rot, sx, 1.0, eyes_b)
    # 双翅：j=0 近（A）、j=1 远（B）；k=0/1 左右
    alpha = clampf(tilt ** 3 + 0.15, 0.0, 1.0)
    wing_col = _mix((0, 0, 0), shield, clampf(alpha + 0.2, 0.0, 1.0))
    for j in (0, 1):
        root = (5.0 if j == 0 else 11.0) + 3.0 * tilt
        spread = (11.0 if j == 0 else 9.0) * (0.2 + 0.8 * abs(uy))
        num8 = -20.0 if j == 0 else 24.0
        ph = sc.flap_ph + (0.0 if j == 0 else 0.8)
        f = (0.5 + 0.5 * math.sin(ph)) ** 0.7
        ang = lerp(-65.0, 40.0, f) if j == 0 else lerp(-45.0, 75.0, f)
        frame = "CicadaWingA" if j == 0 else "CicadaWingB"
        for k in (0, 1):
            s = -1.0 if k == 0 else 1.0
            wx = x + ux * root + px * spread * s
            wy = y + uy * root + py * spread * s
            blit(painter, atlas, frame, wx, wy, aim - 180.0 + (num8 + ang) * s,
                 s * WING_LEN, WING_THICK, wing_col, ax=0.0, ay=0.5)
    painter.restore()
