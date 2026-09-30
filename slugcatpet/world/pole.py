"""竖/横杆几何实体；攀爬逻辑见 pole_climb.py。"""
from __future__ import annotations

from .enums import ItemState

VERTICAL = "vertical"
HORIZONTAL = "horizontal"

POLE_RAD = 1.4            # 杆体半宽（视觉）：细一点，贴原版像素粗细
MIN_LENGTH = 40.0
TOP_MARGIN = 48.0
CROSS_TOL = 6.0          # 交点到端点/线心的容差（原版 tile 级判定）


def _within(a, b, v, tol):
    """v 是否落在 a~b 段内（含容差）。"""
    lo, hi = (a, b) if a <= b else (b, a)
    return lo - tol <= v <= hi + tol


def cross_point(pa, pb, tol=CROSS_TOL):
    """两根杆的交点；同向或不相交返回 None。

    原版 Room.Tile 上 verticalBeam / horizontalBeam 可同格共存，
    该格即「交叉杆」；这里用线段相交等价表达。

    虚拟杆（鼠标那一小截）不参与交叉：原版杆子是固定 tile，鼠标会到处跑，
    交叉换杆会让猫在光标处反复换手。
    """
    if pa.kind == pb.kind:
        return None
    if getattr(pa, "virtual", False) or getattr(pb, "virtual", False):
        return None
    v, h = (pa, pb) if pa.kind == VERTICAL else (pb, pa)
    if not _within(v.ay, v.by, h.ay, tol):
        return None
    if not _within(h.ax, h.bx, v.bx, tol):
        return None
    return (v.bx, h.ay)


def cross_partner(pole, poles, tol=CROSS_TOL):
    """返回与 pole 交叉的异类杆；没有则 None。"""
    for q in poles:
        if q is pole:
            continue
        if cross_point(pole, q, tol) is not None:
            return q
    return None


class Pole:
    """单根杆子：端点+攀爬标记（ax/ay=锚边端，bx/by=光标端）。"""

    __slots__ = ("kind", "ax", "ay", "bx", "by", "state", "has_been_climbed", "_id",
                 "from_spear", "virtual")

    def __init__(self, kind, ax, ay, bx, by, seed=0):
        self.kind = kind
        self.ax = float(ax)
        self.ay = float(ay)
        self.bx = float(bx)
        self.by = float(by)
        self.state = ItemState.FREE
        self.has_been_climbed = False
        self._id = int(seed)
        self.from_spear = None      # 由插进墙/地的矛变成的杆（非 None 时指向那枝矛）
        self.virtual = False        # 鼠标那截「随光标移动的竖杆」：不渲染、不换代

    # ── 竖杆便捷访问 ──
    @property
    def x(self) -> float:
        # 竖杆两端 x 相同（place_pole_line 会把 x1 归到 x0）；取中点防手滑。
        return (self.ax + self.bx) * 0.5

    @property
    def top_y(self) -> float:
        """顶端＝ y 较小的那一端。

        **不能写死成 by**：place_pole_line 的 (ax, ay) 是按下鼠标那一点、
        (bx, by) 是松开那一点 —— 从上往下拉的竖杆 ay < by，by 是**杆底**。
        旧实现把杆底当顶端，猫一抓住杆就满足「已经到顶」→ _enter_tip() →
        _snap_axis() 把两个 chunk 直接瞬移到 by（用户报的「一尝试爬就瞬间
        极快被打到底部」；重画杆子时拉的方向不同，所以「有概率修好」）。
        """
        return min(self.ay, self.by)

    @property
    def bottom_y(self) -> float:
        """底端＝ y 较大的那一端 —— 与 top_y 对称，别再用 by 冒充。"""
        return max(self.ay, self.by)

    def step(self, WL: float, HL: float) -> None:
        """静态，无积分。"""
        return
