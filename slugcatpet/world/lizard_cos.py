# -*- coding: utf-8 -*-
"""蜥蜴花纹（LizardCosmetics/*）：照抄 LizardGraphics.cs 的生成链。

原版在 ``LizardGraphics.cctor``（LizardGraphics.cs:439-640）里按一串互斥的
else-if 掷点决定「这只蜥蜴有哪些花纹」，每一族在自己的构造函数里继续掷点决定
数量/大小/贴图号。本模块用同序的掷点复刻这条链，所以「什么品种容易长出什么、
哪些品种几乎不出现、一只能有几族」跟游戏一致。

摆放规则来自各族自己的构造函数与绘图函数：
``BodyScales.GeneratePatchPattern / GenerateTwoLines / GenerateSegments``、
``GetBackPos``（沿脊按 y 取样，再沿法线偏 x*rad）、``SpineSpikes``、
``TailFin``、``TailTuft``、``AxolotlGills``、``LongHeadScales``、``WingScales``。

坐标约定：``(x, y)`` 中 ``x`` 是**横向比例**（-1 腹部 .. +1 背部，同原版
``scalesPositions.x``），``y`` 是**沿体长的归一化比例**（0 头 .. 1 尾梢）。
"""
from __future__ import annotations

import math

LIZ_SCALE = 1.0          # 桌宠与游戏像素 1:1

# ── 层级 / 物理开关（原版 Template.SpritesOverlap + LizardGraphics.AddToContainer）
# 原版挂载顺序：Behind → 远侧腿 → 体+尾 → BodySurface → 近侧腿 → BehindHead →
# 头 0/1 → 口腔 → 头 2/3/4 → InFront → HUD。花纹不是一个整体贴在最上面：
# 背刺/体鳞/尾羽夹在躯干与头之间，头冠/翅鳞/胡须在头之上。
Z_BEHIND_HEAD = "behind_head"
Z_FRONT = "front"
SPRITE_Z = {
    "SpineSpikes": Z_BEHIND_HEAD,
    "BumpHawk": Z_BEHIND_HEAD,
    "BodyStripes": Z_BEHIND_HEAD,
    "TailGeckoScales": Z_BEHIND_HEAD,
    "TailFin": Z_BEHIND_HEAD,
    "ShortBodyScales": Z_BEHIND_HEAD,
    "TailTuft": Z_BEHIND_HEAD,
    "AxolotlGills": Z_BEHIND_HEAD,
    "LongShoulderScales": Z_BEHIND_HEAD,
    "LongHeadScales": Z_FRONT,
    "WingScales": Z_FRONT,
    "Whiskers": Z_FRONT,
    "Antennae": Z_FRONT,
    "JumpRings": Z_FRONT,
}
# 用 LizardScale 摆锤物理的族（原版 LongBodyScales.Update：角度弹簧 + ConnectToPoint）
PHYS_KINDS = frozenset(("TailTuft", "AxolotlGills", "LongShoulderScales",
                        "LongHeadScales"))
NECK_RAD_K = 0.82        # 颈根半径系数（相对躯干半径，渲染与花纹共用）


def spine_at(spine, rads, s, with_dir=False):
    """按归一化体长 s∈[0,1] 在脊柱折线上取样：返点、背侧法线（屏幕系）、该处半径。"""
    segs = []
    total = 0.0
    for k in range(len(spine) - 1):
        d = math.hypot(spine[k + 1][0] - spine[k][0], spine[k + 1][1] - spine[k][1])
        segs.append(d)
        total += d
    if total <= 0.0:
        if with_dir:
            return spine[0], (0.0, -1.0), rads[0], (1.0, 0.0)
        return spine[0], (0.0, -1.0), rads[0]
    want = _clamp01(s) * total
    for k, d in enumerate(segs):
        if want <= d or k == len(segs) - 1:
            t = (want / d) if d > 0 else 0.0
            t = _clamp01(t)
            ax, ay = spine[k]
            bx, by = spine[k + 1]
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            tx, ty = bx - ax, by - ay
            L = math.hypot(tx, ty) or 1.0
            tx, ty = tx / L, ty / L
            nx, ny = -ty, tx
            if ny > 0.0:                    # 法线取背侧（屏幕上方）
                nx, ny = -nx, -ny
            r = _lerp(rads[k], rads[k + 1], t)
            if with_dir:
                return (px, py), (nx, ny), r, (tx, ty)
            return (px, py), (nx, ny), r
        want -= d
    if with_dir:
        return spine[-1], (0.0, -1.0), rads[-1], (1.0, 0.0)
    return spine[-1], (0.0, -1.0), rads[-1]


def depth_f(y, depth):
    """原版 SpinePosition 的 f = Pow(|depth|, Lerp(1.2, 0.3, Pow(s, 0.5))) * Sign(depth)。"""
    f = abs(depth) ** _lerp(1.2, 0.3, math.sqrt(max(0.0, _clamp01(y))))
    return f if depth >= 0.0 else -f


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

# 滚动生成时的上下文（原版从 LizardGraphics 上取 bodyLength / BodyAndTailLength）
_TOTAL = 100.0
_BODY_FRAC = 0.5

# 原版 Random.Range 语义：int 版是 [min,max)，float 版是 [min,max]
def _lerp(a, b, t):
    return a + (b - a) * t


def _inv(a, b, v):
    if b == a:
        return 0.0
    return (v - a) / (b - a)


class Cos:
    """一族花纹。``insts`` 是 (x, y, length, width, row) 实例表。"""

    __slots__ = ("kind", "graphic", "colored", "colored_mode", "scale_x",
                 "insts", "a_head", "gradient", "rigor")

    def __init__(self, kind, graphic, colored=False, colored_mode=1,
                 scale_x=1.0, a_head=False, gradient=False, rigor=0.0):
        self.kind = kind
        self.graphic = int(graphic)
        self.colored = bool(colored)
        # 1 = B 片纯 effectColor；2 = B 片在 effectColor 与体色间按 y 渐变
        self.colored_mode = int(colored_mode)
        self.scale_x = float(scale_x)
        self.a_head = bool(a_head)        # A 片用 HeadColor 而不是 BodyColor
        self.gradient = bool(gradient)    # A 片颜色沿体长渐变（尾斑）
        self.rigor = float(rigor)         # LizardScale 硬度（0 软摆 / 1 硬）
        self.insts = []

    def add(self, x, y, length, width, row=0, backwards=0.5):
        """``backwards`` = 原版 backwardsFactors：鳞片顺体轴后掠的比例（0=朝外）。"""
        self.insts.append((float(x), float(y), float(length), float(width),
                           int(row), float(backwards)))

    def __repr__(self):
        return "<Cos %s x%d g%d%s>" % (self.kind, len(self.insts), self.graphic,
                                       " colored" if self.colored else "")


class _R:
    """UnityEngine.Random 的等价掷点器。"""

    __slots__ = ("r",)

    def __init__(self, rnd):
        self.r = rnd

    def value(self):
        return self.r.random()

    def rng_i(self, a, b):
        # Unity Random.Range(int,int) 是 [a,b)；b <= a 时恒返回 a（空区间），
        # 但照样消耗一次掷点，所以这里先吃掉一个随机数再判断。
        a = int(a)
        b = int(b)
        u = self.r.random()
        if b <= a:
            return a
        return a + int(u * (b - a))

    def rng_f(self, a, b):
        return a + (b - a) * self.r.random()

    # Custom.ClampedRandomVariation(0.5, dev, 0.5) 的等价式
    def clamped_var(self, mean, dev, k):
        return _clamped_var(self.r, mean, dev, k)


def _clamped_var(rnd, mean, dev, k):
    import random as _random
    return max(mean - dev, min(mean + dev, rnd.gauss(mean, dev * k)))


# ── BodyScales 家族的三种落点模式（逐字照抄 BodyScales.cs） ────────────────
def _gen_patch(R, n, start, max_len, exp, body_frac=None):
    pos = []
    num = _lerp(start + 0.1, max(start + 0.2, max_len), R.value() ** exp)
    frac = _BODY_FRAC if body_frac is None else body_frac
    for _ in range(n):
        deg = R.value() * 360.0
        rad = R.value()
        vx = math.cos(math.radians(deg)) * rad
        vy = math.sin(math.radians(deg)) * rad
        pos.append((vx, _lerp(start * frac, num * frac, (vy + 1.0) / 2.0)))
    return pos


def _gen_lines(R, start, max_len, exp, spacing, blue, total=None):
    num = _lerp(start + 0.1, max(start + 0.2, max_len), R.value() ** exp)
    num2 = num * (_TOTAL if total is None else total)
    space = _lerp(2.0, 9.0, R.value())
    if blue:
        space = 2.0
    space *= spacing
    n = int(num2 / space)
    if n < 3:
        n = 3
    pos = []
    for i in range(n):
        y = _lerp(0.0, num, i / float(n - 1))
        w = 0.6 + 0.4 * math.sin(i / float(n - 1) * math.pi)
        pos.append((w, y))
        pos.append((-w, y))
    return pos


def _gen_segments(R, start, max_len, exp, red, total=None):
    num = _lerp(start + 0.1, max(start + 0.2, max_len), R.value() ** exp)
    num2 = num * (_TOTAL if total is None else total)
    gap = _lerp(7.0, 14.0, R.value())
    if red:
        gap = min(gap, 11.0) * 0.75
    n = max(3, int(num2 / gap))
    lines = R.rng_i(1, 4) * 2
    pos = []
    for i in range(n):
        y = _lerp(0.0, num, i / float(n - 1))
        for j in range(lines):
            w = 0.6 + 0.6 * math.sin(i / float(n - 1) * math.pi)
            w *= _lerp(-1.0, 1.0, j / float(lines - 1))
            pos.append((w, y))
    return pos


def _scale_objs(R, cos, pos, lo, hi, width_fac, backwards=None, rigor=0.0):
    """给一排落点配长度/宽度（LongBodyScales 里那两段 Lerp）。"""
    ymin = min(p[1] for p in pos)
    ymax = max(p[1] for p in pos)
    p_exp = _lerp(0.1, 0.9, R.value())
    for i, (x, y) in enumerate(pos):
        t = _inv(ymin, ymax, y) ** p_exp if ymax > ymin else 0.0
        arc = math.sin(t * math.pi)
        k = _lerp(arc, 1.0, 0.5 if t < 0.5 else 0.0)
        length = _lerp(lo, hi, k)
        width = _lerp(0.8, 1.2, k) * width_fac
        cos.add(x, y, length * LIZ_SCALE, width)


# ── 各族的生成 ─────────────────────────────────────────────────────────────
def _spine_spikes(R, key):
    c = Cos("SpineSpikes", 0)
    num = _lerp(5.0, 8.0, R.value() ** 0.7)
    spine_len = _lerp(0.2, 0.95, R.value())
    size_min = _lerp(0.1, 0.5, R.value() ** 2.0)
    size_max = _lerp(size_min, 1.1, R.value())
    if R.value() < 0.5:
        size_max = 1.0
    if key == "blue":
        size_min = min(size_min, 0.3)
        size_max = min(size_max, 0.6)
    elif key != "green" and R.value() < 0.7:
        size_min *= 0.7
        size_max *= 0.7
    elif key == "green" and R.value() < 0.7:
        size_min = _lerp(size_min, 1.1, 0.1)
        size_max = _lerp(size_max, 1.1, 0.4)
    skew = _lerp(0.1, 0.9, R.value())
    bumps = int(spine_len * _TOTAL / num) if num else 0
    g = R.rng_i(0, 5)
    if g == 1:
        g = 0
    if g == 4:
        g = 3
    elif g == 3 and R.value() < 0.5:
        c.scale_x = -1.0
    elif R.value() < 1.0 / 15.0:
        c.scale_x = -1.0
    if key == "pink" and R.value() < 0.7:
        g = 0
    elif key == "green" and R.value() < 0.5:
        g = 3
    c.graphic = g
    colored = R.rng_i(0, 3)
    if key == "pink" and R.value() < 0.5:
        colored = 0
    elif key == "green" and R.value() < 0.5:
        colored = 2
    elif key == "green" and R.value() < 0.5:
        colored = 1
    c.colored = colored > 0
    c.colored_mode = colored
    bumps = max(1, bumps)
    for i in range(bumps):
        t = i / float(max(1, bumps - 1))
        size = _lerp(size_min, size_max, math.sin((t ** skew) * math.pi))
        c.add(1.0, spine_len * t, 14.0 * size, 1.0 * abs(c.scale_x) * size)
    return c, colored


def _bump_hawk(R):
    c = Cos("BumpHawk", 1)
    colored_hawk = R.value() < 0.5
    c.colored = colored_hawk
    if colored_hawk:
        num = _lerp(3.0, 8.0, R.value() ** 0.7)
        spine_len = _lerp(0.3, 0.7, R.value())
        size_min = _lerp(0.1, 0.2, R.value())
        size_max = _lerp(size_min, 0.35, R.value() ** 0.5)
    else:
        num = _lerp(6.0, 12.0, R.value() ** 0.5)
        spine_len = _lerp(0.3, 0.9, R.value())
        size_min = _lerp(0.2, 0.3, R.value() ** 0.5)
        size_max = _lerp(size_min, 0.5, R.value())
    skew = _lerp(0.1, 0.7, R.value())
    bumps = max(1, int(spine_len * _TOTAL / num) if num else 1)
    for i in range(bumps):
        t = i / float(max(1, bumps - 1))
        size = _lerp(size_min, size_max, math.sin((t ** skew) * math.pi))
        c.add(0.0, spine_len * t, 8.0 * size + 4.0, 3.5 * size + 1.6)
    return c


def _tail_tuft(R, key, prev_graphic):
    c = Cos("TailTuft", 0)
    two = (R.value() < 1.0 / 7.0
           or (R.value() < 0.9 and key == "blue")
           or key == "red" or key == "zoop")
    if two:
        if key in ("blue", "red"):
            pos = _gen_lines(R, 0.0, 0.3 if key == "red" else 0.7, 1.0, 3.0,
                             key == "blue")
        else:
            pos = _gen_lines(R, 0.0, 0.4, 1.2, 1.3, False)
    else:
        n = R.rng_i(3, 7)
        pos = _gen_patch(R, n, 0.0, 1.6, 1.5)
    top = max(p[1] for p in pos) if pos else 0.0
    pos = [(x, y + 0.9 - top) for (x, y) in pos]
    num = _lerp(1.0, 1.0 / _lerp(1.0, max(1.0, float(len(pos))), R.value() ** 2.0), 0.5)
    if key in ("red", "zoop"):
        num = max(num, 0.4) * 1.1
    a = _lerp(5.0, 10.0, R.value()) * num
    b = _lerp(a, 25.0, R.value() ** 0.5) * num
    c.colored = R.value() < 0.8
    g = R.rng_i(3, 7)
    if g == 3:
        g = 1
    if R.value() < 1.0 / 30.0:
        g = R.rng_i(0, 7)
    if (R.value() < 0.8 or key in ("red", "zoop")) and prev_graphic is not None:
        g = prev_graphic
    c.graphic = g
    ymin = min(p[1] for p in pos) if pos else 0.0
    ymax = max(p[1] for p in pos) if pos else 1.0
    for (x, y) in pos:
        t = _inv(ymin, ymax, y)
        length = _lerp(a, b, t)
        back = 0.3 + 0.7 * _clamp01(_inv(0.75, 1.0, y))
        c.add(x, y, length * LIZ_SCALE, 1.0, backwards=back)
    return c


def _tail_fin(R, key, prev_graphic):
    c = Cos("TailFin", 0)
    num = _lerp(4.0, 7.0, R.value() ** 0.7)
    spine_len = R.clamped_var(0.5, 0.17, 0.5)
    underside = _lerp(0.3, 0.9, R.value())
    size_min = _lerp(0.1, 0.3, R.value() ** 2.0)
    size_max = _lerp(size_min, 0.6, R.value())
    skew = _lerp(0.5, 1.5, R.value())
    g = R.rng_i(0, 6)
    if key == "red":
        g = prev_graphic if prev_graphic is not None else 0
        size_min *= 2.0
        size_max *= 1.5
        spine_len = R.clamped_var(0.3, 0.17, 0.5)
    c.graphic = g
    bumps = max(1, int(spine_len * 100.0 / num) if num else 1)
    sx = _lerp(1.0, 2.0, R.value())
    if g == 3 and R.value() < 0.5:
        sx = -sx
    elif g != 0 and R.value() < 1.0 / 15.0:
        sx = -sx
    c.scale_x = sx
    c.colored = R.value() > 1.0 / 3.0
    y0 = 1.0 - spine_len
    for i in range(bumps):
        t = i / float(max(1, bumps - 1))
        y = _lerp(y0, 1.0, t)
        size = _lerp(size_min, size_max, math.sin((t ** skew) * math.pi))
        c.add(1.0, y, 22.0 * size, 1.0, 0)
        c.add(-1.0, y, 22.0 * size * underside, 1.0, 1)
    return c


def _axolotl_gills(R, key):
    c = Cos("AxolotlGills", 0, colored=True, a_head=True)
    c.rigor = R.value()
    num = (R.value() ** 0.7) * 1.0
    g = R.rng_i(0, 6)
    if g == 2:
        g = R.rng_i(0, 6)
    c.graphic = g
    n2 = R.rng_i(2, 8)
    value = R.value()
    num3 = _lerp(0.1, 0.9, R.value())
    for i in range(n2):
        y = _lerp(0.0, 0.07, R.value() ** 1.3)
        x = _lerp(0.5, 1.5, R.value())
        num5 = _lerp(0.2, 1.0, R.value() ** 0.5)
        back = num3 * (R.value() ** 0.5)          # num6
        length = _lerp(5.0, 35.0, num * num5)
        width = _lerp(0.65, 1.2, value * num)
        c.add(x, y, length * LIZ_SCALE, width, backwards=back)
        c.add(-x, y, length * LIZ_SCALE, width, backwards=back)
    return c


def _long_head_scales(R, key):
    c = Cos("LongHeadScales", 0, a_head=True)
    c.rigor = R.value()
    y = _lerp(0.0, 0.07, R.value())
    x = _lerp(0.5, 1.5, R.value())
    num = (R.value() ** 0.7) * 1.0
    c.colored = R.value() < 0.5 and key != "white"
    g = R.rng_i(4, 6)
    if num < 0.5 and R.value() < 0.5:
        g = 6
    elif num > 0.8:
        g = 5
    if num < 0.2 and key != "white":
        c.colored = True
    if key == "black":
        c.colored = False
    c.graphic = g
    value = R.value()
    back = R.value() ** 0.85
    for sx in (-x, x):
        c.add(sx, y, _lerp(5.0, 35.0, num) * LIZ_SCALE,
              _lerp(0.65, 1.2, value * num), backwards=back)
    return c


def _long_shoulder_scales(R, key):
    c = Cos("LongShoulderScales", 0)
    mode = 0
    if key != "pink" or R.value() < 1.0 / 3.0:
        mode = R.rng_i(0, 3)
    elif key == "green" or R.value() < 0.5:
        mode = 2
    if mode == 0:
        pos = _gen_patch(R, R.rng_i(4, 15), 0.05, 0.9, 2.0)
    elif mode == 1:
        pos = _gen_lines(R, 0.07, 1.0, 1.5, 3.0, key == "blue")
    else:
        pos = _gen_segments(R, 0.1, 0.8, 5.0, key == "red")
    lo = min(p[1] for p in pos) if pos else 0.0
    if lo > 0.07:
        pos = [(x, y - (lo - 0.07)) for (x, y) in pos]
    n = R.value()
    num2 = _lerp(1.0, 1.0 / _lerp(1.0, max(1.0, float(len(pos))), R.value() ** 2.0), 0.5)
    num3 = _lerp(5.0, 15.0, R.value()) * num2
    b = _lerp(num3, 35.0, R.value() ** 0.5) * num2
    if key == "red":
        num2 = max(0.5, num2)
        num3 = max(10.0, num3) * 1.2
        b = max(25.0, b) * 1.2
    c.colored = key in ("green", "red") or R.value() < 0.4
    if R.value() < 0.1:
        g = R.rng_i(0, 7)
    else:
        g = R.rng_i(3, 6)
    if key == "pink" and R.value() < 0.25:
        g = 0
    if key == "red":
        g = 0
        if R.value() < 0.3:
            g = 3
            c.scale_x = -1.0 if R.value() < 0.5 else 1.0
    c.graphic = g
    ymin = min(p[1] for p in pos) if pos else 0.0
    ymax = max(p[1] for p in pos) if pos else 1.0
    p_exp = _lerp(0.1, 0.9, R.value())
    for (x, y) in pos:
        t = _inv(ymin, ymax, y) ** p_exp if ymax > ymin else 0.0
        arc = math.sin(t * math.pi)
        k = _lerp(arc, 1.0, 0.5 if t < 0.5 else 0.0)
        c.add(x, y, _lerp(num3, b, k) * LIZ_SCALE, _lerp(0.8, 1.2, k) * num2,
              backwards=y * 0.7)
    _ = n
    return c


def _short_body_scales(R, key):
    c = Cos("ShortBodyScales", 0, a_head=True)
    mode = R.rng_i(0, 3)
    if key == "green" and R.value() < 0.7:
        mode = 2
    elif key == "blue" and R.value() < 0.93:
        mode = 1
    if mode == 0:
        pos = _gen_patch(R, R.rng_i(4, 15), 0.1, 0.9, 1.2)
    elif mode == 1:
        pos = _gen_lines(R, 0.1, 1.0, 1.5, 1.0, key == "blue")
    else:
        pos = _gen_segments(R, 0.1, 0.9, 1.5 if key == "pink" else 0.6, key == "red")
    g = R.rng_i(0, 7)
    c.graphic = g
    for (x, y) in pos:
        c.add(x, y, 12.0 * LIZ_SCALE, 1.0)
    return c


def _body_stripes(R):
    c = Cos("BodyStripes", 0, a_head=True)
    num = 1.5
    num2 = _lerp(0.4, 0.8, R.value())
    num3 = num2 * _TOTAL
    num4 = _lerp(5.0, 12.0, R.value()) * num
    n = max(3, int(num3 / num4) if num4 else 3)
    g = R.rng_i(0, 7)
    c.graphic = g
    for i in range(n):
        y = _lerp(0.0, num2, i / float(n - 1))
        w = 0.6 + 0.4 * math.sin(i / float(n - 1) * math.pi)
        c.add(w, y, 14.0 * LIZ_SCALE, 1.0)
        c.add(-w, y, 14.0 * LIZ_SCALE, 1.0)
    return c


def _wing_scales(R, key):
    c = Cos("WingScales", 0)
    cols = 2
    rows = 3 if R.value() < 0.2 else 2
    g = R.rng_i(0, 5) if not (R.value() < 0.4) else 0
    c.graphic = g
    R.value()                       # sturdy
    R.value()                       # posSqueeze
    length = _lerp(5.0, 40.0, R.value() ** 0.75)
    front = _lerp(-0.1, 0.2, R.value())
    back = _lerp(max(0.0, front), front + rows * 0.2, R.value())
    c.colored = False
    for i in range(cols):
        for j in range(rows):
            t = j / float(max(1, rows - 1))
            y = _lerp(front, back, t)
            x = (1.0 if i == 0 else -1.0) * 0.9
            c.add(x, max(0.02, y), length * LIZ_SCALE, 1.0)
    return c


def _tail_gecko_scales(R, tail_amt, wing_len):
    c = Cos("TailGeckoScales", 0, gradient=True)
    rows = R.rng_i(7, 14)
    lines = R.rng_i(3, R.rng_i(3, 4))
    big = False
    if tail_amt > 0.1 and R.value() < _lerp(0.7, 0.99, min(1.0, tail_amt)):
        big = True
        if wing_len is not None and wing_len > 10.0:
            big = False
    if R.value() < 0.5:
        rows += R.rng_i(0, R.rng_i(0, 7))
        lines += R.rng_i(0, R.rng_i(0, 3))
    rows = max(2, rows)
    lines = max(2, lines)
    c.colored = True
    scale = 1.4 if big else 1.0
    for i in range(rows):
        t = i / float(rows - 1)
        y = _lerp(0.42, 1.0, t)          # 只在尾段
        for j in range(lines):
            x = _lerp(-0.85, 0.85, j / float(max(1, lines - 1)))
            c.add(x, y, 7.0 * scale, 1.0)
    return c


def _jump_rings(R, key):
    c = Cos("JumpRings", 0, colored=True)
    for i in range(8):
        y = _lerp(0.02, 0.34, i / 7.0)
        c.add(1.0, y, 9.0, 1.0)
    return c


def _whiskers(R, key):
    c = Cos("Whiskers", 0, a_head=True, colored=True)
    amount = R.rng_i(3, 5)
    for i in range(amount):
        R.value()                                   # whiskerDirections
        prop0 = _clamped_var(R.r, 0.5, 0.4, 0.5) * 40.0
        R.value()                                   # prop1
        R.value()                                   # prop2
        R.value()                                   # prop3
        prop4 = _lerp(0.6, 1.2, R.value() ** 1.6)
        for j in range(5):
            if i > 0 and j != 1:
                R.value()
        y = 0.02 + 0.03 * (i / float(max(1, amount - 1)))
        c.add(1.0, y, max(6.0, prop0 * 0.5), max(0.3, prop4 * 0.5))
        c.add(-1.0, y, max(6.0, prop0 * 0.5), max(0.3, prop4 * 0.5))
    return c


def _antennae(R, key):
    c = Cos("Antennae", 0, a_head=True, colored=True)
    length = R.value()
    segs = int(_lerp(3.0, 8.0, length ** _lerp(1.0, 6.0, length)))
    alpha = length * 0.9 + R.value() * 0.1
    for k in range(max(1, segs)):
        t = k / float(max(1, segs - 1))
        y = _lerp(0.02, -0.04, t)
        c.add(1.0, y, 10.0, 0.5)
        c.add(-1.0, y, 10.0, 0.5)
    c.scale_x = alpha
    return c


def _body_lines(R, n, y0, y1, x, length=16.0):
    for i in range(n):
        yield (x, _lerp(y0, y1, i / float(max(1, n - 1))), length)


# ── 主入口：逐字照抄 LizardGraphics.cs:439-640 的 else-if 链 ───────────────
def roll_cosmetics(rnd, key, total_len, body_frac):
    """返回这只蜥蜴的花纹表（原版顺序、原版概率）。

    ``key`` 是品种键（pink/green/blue/yellow/white/red/black/salamander/
    cyan/caramel/eel/zoop…），``total_len`` 是体+尾总长（游戏像素），
    ``body_frac`` 是 bodyLength / BodyAndTailLength。
    """
    global _TOTAL, _BODY_FRAC
    _TOTAL = float(total_len)
    _BODY_FRAC = float(body_frac)
    R = _R(rnd)
    out = []
    caramel = key == "caramel"
    blue = key == "blue"
    red = key == "red"
    green = key == "green"

    # DLC 专属分支（原版最前面两条）
    if key == "eel":
        out.append(_axolotl_gills(R, key))
        gk = _tail_gecko_scales(R, 0.0, None)
        out.append(gk)
        if R.value() < 0.75:
            out.append(_long_shoulder_scales(R, key))
            out.append(_tail_fin(R, key, None))
        else:
            out.append(_short_body_scales(R, key))
            out.append(_tail_fin(R, key, None) if R.value() < 0.75
                       else _tail_tuft(R, key, None))
    elif key == "zoop":
        out.append(_wing_scales(R, key) if R.value() < 0.175
                   else _spine_spikes(R, key)[0])
        out.append(_tail_tuft(R, key, None))

    if key == "cyan":
        if R.value() < 0.75:
            out.append(_wing_scales(R, key))
        # 注意：tailColor != 0 时必给 TailGeckoScales
        if R.value() >= 0.5:
            out.append(_tail_gecko_scales(R, 1.0, None))
        else:
            out.append(_tail_tuft(R, key, None))
        out.append(_jump_rings(R, key))
    elif key != "white":
        num8 = 0
        flag = False
        flag2 = False
        prev_graphic = None
        body_done = False
        if caramel and R.value() < 0.6:
            c = _body_stripes(R)
            out.append(c)
            prev_graphic = c.graphic
            num8 += 1
            body_done = True
        elif (R.value() < 1.0 / 15.0
              or (R.value() < 0.8 and green)
              or (R.value() < 0.7 and key == "black")):
            c, _col = _spine_spikes(R, key)
            out.append(c)
            prev_graphic = c.graphic
            num8 += 1
            body_done = True
        elif R.value() < 1.0 / 30.0 and not caramel:
            out.append(_bump_hawk(R))
            num8 += 1
            body_done = True
        elif ((R.value() < 1.0 / 21.0
               or (key == "pink" and R.value() < 0.5)
               or (red and R.value() < 0.9)) and key != "salamander"):
            c = _long_shoulder_scales(R, key)
            out.append(c)
            prev_graphic = c.graphic
            flag = True
            num8 += 1
            body_done = True
        elif ((R.value() < 0.0625
               or (blue and R.value() < 0.5)) and key != "salamander"):
            c = _short_body_scales(R, key)
            out.append(c)
            prev_graphic = c.graphic
            flag2 = True
            num8 += 1
            body_done = True
        elif green and R.value() < 0.5:
            c = _short_body_scales(R, key)
            out.append(c)
            prev_graphic = c.graphic
            flag2 = True
            num8 += 1
            body_done = True
        _ = body_done

        if key not in ("salamander", "indigo"):
            if caramel and R.value() < 0.5:
                out.append(_tail_tuft(R, key, prev_graphic))
            elif (R.value() < 1.0 / 9.0
                  or (num8 == 0 and R.value() < 0.7)
                  or (key == "pink" and R.value() < 0.6)
                  or (blue and R.value() < 0.96)):
                out.append(_tail_tuft(R, key, prev_graphic))
            elif num8 < 2 and green and R.value() < 0.7:
                if R.value() < 0.5 or flag or flag2:
                    out.append(_tail_tuft(R, key, prev_graphic))
                else:
                    c = _long_shoulder_scales(R, key)
                    out.append(c)
                    prev_graphic = c.graphic
                    flag = True
                    num8 += 1

        thr = 0.7 if num8 == 0 else 0.1
        if R.value() < thr and key not in ("salamander", "yellow", "indigo"):
            ok = False
            if not flag:
                ok = R.value() < 0.9
                if not ok:
                    ok = R.value() < 1.0 / 30.0
            else:
                ok = R.value() < 1.0 / 30.0
            if ok:
                out.append(_long_head_scales(R, key))

        if key == "salamander":
            out.append(_axolotl_gills(R, key))
            out.append(_tail_fin(R, key, prev_graphic))
        elif key == "black":
            out.append(_whiskers(R, key))
        elif key == "yellow":
            out.append(_antennae(R, key))
            if num8 == 0 and R.value() < 0.6:
                out.append(_short_body_scales(R, key))
                flag2 = True
                num8 += 1
        elif red:
            c = _long_shoulder_scales(R, key)
            out.append(c)
            prev_graphic = c.graphic
            flag = True
            num8 += 1
            c2, _col = _spine_spikes(R, key)
            out.append(c2)
            num8 += 1
            out.append(_tail_tuft(R, key, prev_graphic) if R.value() < 0.5
                       else _tail_fin(R, key, prev_graphic))
    return out
