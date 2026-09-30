# -*- coding: utf-8 -*-
"""背景墙：把「别人窗口的左右竖边」升级成蜥蜴可导航的墙面（``WallSurface``）。

反编译口径（详见 ``docs/LIZARD_WALL_NAV.md``）：

* 原版墙是地图拓扑的一部分 —— ``AImapper.FindAccessibilityOfCurrentTile``
  （AImapper.cs:188-229）把 ``wallbehind`` / 左右相邻 Solid 的 tile 标成
  ``AItile.Accessibility.Wall``，``verticalBeam/horizontalBeam`` 标成
  ``Accessibility.Climb``；
* 「某条路这只生物能不能走」由 ``CreatureTemplate.AccessibilityResistance`` /
  ``ConnectionResistance`` 决定（AImap.cs:59-77），不是给某只蜥蜴临时开的特例；
* ``LizardBreedParams.WallClimber``（LizardBreedParams.cs:196-210）只有
  BlueLizard / WhiteLizard / DlcEelLizard 为 true。

桌宠映射：桌面几何＝别人的窗口；一块 ``WallSurface`` ＝ 某个非全屏窗口的
**一侧竖边在 Z 序里露出来的可见墙段**（被前面窗口挡住的段不算墙，与
``winplat.clip_tops`` 的「露出来的顶边」同一口径）。
"""
from __future__ import annotations

_EPS = 1.0
WALL_MIN_SEG = 26.0       # 一段墙短于这个长度就不算可爬的墙
WALL_MIN_SIDE = 24.0      # 窗口短边小于它就不是「立着的一块墙」


def _cut(spans, lo, hi):
    """从若干区间里减掉 [lo, hi]（前面窗口挡住的部分）。"""
    out = []
    for a, b in spans:
        if hi <= a or lo >= b:
            out.append((a, b))
            continue
        if lo > a:
            out.append((a, lo))
        if hi < b:
            out.append((hi, b))
    return out


def _merge(spans):
    """把互相重叠 / 相接的区间并起来。"""
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + _EPS:
            if b > out[-1][1]:
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


class WallSurface:
    """一块立着的背景墙：某窗口某一侧露出来的若干竖直墙段。"""

    __slots__ = ("x", "side", "segments", "src", "index")

    def __init__(self, x, side, segments, src):
        self.x = float(x)
        self.side = int(side)                    # -1 = 窗口左边、+1 = 窗口右边
        self.segments = tuple((float(a), float(b)) for a, b in segments)
        self.src = tuple(src)                    # 来源窗口矩形 (x0, y0, x1, y1)
        self.index = -1

    @property
    def top(self) -> float:
        return min(a for a, _b in self.segments)

    @property
    def bottom(self) -> float:
        return max(b for _a, b in self.segments)

    def span_at(self, y):
        """y 落在哪一段墙里（返回 (top, bot)），不在任何一段里就 None。"""
        for a, b in self.segments:
            if a - 4.0 <= y <= b + 4.0:
                return (a, b)
        return None

    def covers(self, y_top, y_bot) -> bool:
        """[y_top, y_bot] 是否有段墙覆盖（用于「墙底落在我这层楼吗」）。"""
        for a, b in self.segments:
            if b >= y_top and a <= y_bot:
                return True
        return False

    def key(self):
        return (round(self.x, 1), self.side, self.segments, self.src)

    def __eq__(self, other):
        return isinstance(other, WallSurface) and self.key() == other.key()

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        segs = ",".join("%.0f-%.0f" % (a, b) for a, b in self.segments)
        return "<Wall x=%.0f side=%d [%s]>" % (self.x, self.side, segs)


def build_wall_surfaces(rects, min_seg=None):
    """把窗口矩形（前→后的 Z 序）切成一块块可见的 ``WallSurface``。

    只保留「露出来的」墙段：一条竖边被前面窗口盖住的那些 y 段不算墙
    （桌宠画在最上层，被挡住的那截墙面根本没有像素，也不算地形）。
    """
    min_seg = WALL_MIN_SEG if min_seg is None else float(min_seg)
    rects = list(rects or ())
    out = []
    for i, r in enumerate(rects):
        x0, y0, x1, y1 = float(r[0]), float(r[1]), float(r[2]), float(r[3])
        if x1 - x0 < WALL_MIN_SIDE:
            continue                              # 太窄：不是一块立着的墙
        top, bot = min(y0, y1), max(y0, y1)
        for side, sx in ((-1, x0), (1, x1)):
            spans = [(top, bot)]
            for j in range(i):                     # 前面的窗口若盖住这条竖边就裁掉
                rj = rects[j]
                rx0, ry0, rx1, ry1 = (float(rj[0]), float(rj[1]),
                                      float(rj[2]), float(rj[3]))
                if rx0 - _EPS <= sx <= rx1 + _EPS:
                    spans = _cut(spans, min(ry0, ry1), max(ry0, ry1))
                    if not spans:
                        break
            segs = [(a, b) for a, b in _merge(spans) if b - a >= min_seg]
            if segs:
                out.append(WallSurface(sx, side, segs, (x0, y0, x1, y1)))
    for k, ws in enumerate(out):
        ws.index = k
    return out