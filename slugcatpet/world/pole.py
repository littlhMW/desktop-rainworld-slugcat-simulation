"""竖/横杆几何实体；攀爬逻辑见 pole_climb.py。"""
from __future__ import annotations

import math

from .enums import ItemState

VERTICAL = "vertical"
HORIZONTAL = "horizontal"

POLE_RAD = 1.4            # 杆体半宽（视觉）：细一点，贴原版像素粗细
MIN_LENGTH = 40.0
TOP_MARGIN = 48.0
CROSS_TOL = 6.0          # 交点到端点/线心的容差（原版 tile 级判定）
SUPPORT_EPS = 2.0        # 竖杆与水平支撑面接触的数值容差（不能用抓杆伸手范围代替）


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

    # ── 统一杆接口（文档 §3 / §7）──
    # 外面只有这一个杆接口，里面才分竖杆 / 横杆两套运动实现。调用方（FSM /
    # Planner / blocking / ThreatField）只问这几件事，不再各自读 ax/ay/bx/by
    # 算「这是哪一头」「离我多远」「在不在我身上」。
    def geometry(self):
        """两端点 ``((ax, ay), (bx, by))``。"""
        return ((self.ax, self.ay), (self.bx, self.by))

    def length(self) -> float:
        """杆长。"""
        return math.hypot(self.bx - self.ax, self.by - self.ay)

    def axis(self):
        """杆轴单位向量（a 端 → b 端）；零长返回 (0, 0)。"""
        dx, dy = self.bx - self.ax, self.by - self.ay
        L = math.hypot(dx, dy)
        if L <= 1e-9:
            return (0.0, 0.0)
        return (dx / L, dy / L)

    def nearest_point(self, x, y):
        """点 (x, y) 到杆段的最近点 ``(x, y)``。"""
        ax, ay = self.ax, self.ay
        dx, dy = self.bx - ax, self.by - ay
        L2 = dx * dx + dy * dy
        if L2 <= 1e-9:
            return (ax, ay)
        t = ((x - ax) * dx + (y - ay) * dy) / L2
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        return (ax + dx * t, ay + dy * t)

    def progress(self, x, y) -> float:
        """点在杆上的归一化进度 0..1（a 端 = 0，b 端 = 1）。"""
        ax, ay = self.ax, self.ay
        dx, dy = self.bx - ax, self.by - ay
        L2 = dx * dx + dy * dy
        if L2 <= 1e-9:
            return 0.0
        t = ((x - ax) * dx + (y - ay) * dy) / L2
        return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)

    def contains(self, x, y, tol: float = POLE_RAD) -> bool:
        """点是否落在杆体上（含 tol 容差）。"""
        nx, ny = self.nearest_point(x, y)
        return math.hypot(x - nx, y - ny) <= float(tol)

    def intersection(self, other, tol: float = CROSS_TOL):
        """与另一根杆的交点；同向 / 不相交返回 None。"""
        return cross_point(self, other, tol)

    def surface_at(self, x, y) -> str:
        """(x, y) 附近的表面类型：普通杆给它的 kind（竖/横）。"""
        return self.kind

    def anchor(self):
        """锚边那一端 ``(ax, ay)``（拖动时按下的那一点）。"""
        return (self.ax, self.ay)

    def free_end(self):
        """松开鼠标那一端 ``(bx, by)``（拖动时松手的那一点）。"""
        return (self.bx, self.by)

    def span_x(self):
        """x 方向跨度 ``(lo, hi)``（与 kind 无关，横杆就是它的长度范围）。"""
        return (self.ax, self.bx) if self.ax <= self.bx else (self.bx, self.ax)

    def span_y(self):
        """y 方向跨度 ``(top, bottom)``（top 是 y 较小的一端）。"""
        return (self.top_y, self.bottom_y)

    def mid_x(self) -> float:
        """两端 x 的中点。"""
        return (self.ax + self.bx) * 0.5

    def cross_coord(self) -> float:
        """杆「横截面」所在的那条线：竖杆＝杆心 x，横杆＝杆面 y。

        FSM 里到处写 ``p.ay``（横杆杆面）与 ``p.x``（竖杆杆心）其实是同一件事，
        这里给一个名字，调用方不必知道自己拿的是竖杆还是横杆。
        """
        return self.x if self.kind == VERTICAL else self.ay

    def axis_coord(self, x, y) -> float:
        """沿杆方向的坐标：竖杆取 y，横杆取 x。"""
        return float(y) if self.kind == VERTICAL else float(x)

    def clamp_axis(self, v: float, pad: float = 0.0) -> float:
        """把一个沿杆坐标夹进杆的跨度内（可选两端各留 pad）。"""
        lo, hi = self.span_y() if self.kind == VERTICAL else self.span_x()
        return min(max(float(v), lo + pad), hi - pad)

    def spans(self, v: float, r: float = 0.0) -> bool:
        """这个沿杆坐标是否落在杆的跨度内（含 r 余量）。"""
        lo, hi = self.span_y() if self.kind == VERTICAL else self.span_x()
        return lo - r <= float(v) <= hi + r

    def touches_support_y(self, y: float, tol: float = SUPPORT_EPS) -> bool:
        """竖杆是否实际跨过水平支撑面 y。

        抓杆半径/空中抓杆余量描述的是生物伸手能否碰到杆，不代表杆已与地面或
        平台相连。把这两种距离混用会令端点悬空数像素的竖杆被导航图接到地面，
        多只猫随后会一起走到杆底反复尝试攀爬。这里只给物理端点留少量浮点容差；
        可跳抓的浮杆仍由空中抓杆路径处理。
        """
        if self.kind != VERTICAL:
            return False
        top, bottom = self.span_y()
        return top - float(tol) <= float(y) <= bottom + float(tol)

    def nearest(self, x, y):
        """最近点与距离 ``(cx, cy, d)``（点-段距离的唯一口径）。"""
        cx, cy = self.nearest_point(x, y)
        return (cx, cy, math.hypot(float(x) - cx, float(y) - cy))

    def step(self, WL: float, HL: float) -> None:
        """静态，无积分。"""
        return
