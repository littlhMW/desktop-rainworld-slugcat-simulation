# -*- coding: utf-8 -*-
"""统一导航几何：蜥蜴（world/terrain.py）与蛞蝓猫（planning/surface.py）共用。

反编译口径：原版一张地图的地形就是 AImap / AItile —— Floor / Wall / Ceiling /
Climb（verticalBeam 竖杆、horizontalBeam 横杆）都在同一张连通图里，
「这条路这只生物能不能走」由 CreatureTemplate.AccessibilityResistance /
ConnectionResistance 决定。桌宠这里原本有两套几何：

    world/terrain.py     蜥蜴：floor / platform / hpole / vpole / wall / shelter solid
    planning/surface.py  蛞蝓猫：floor / deck / shelter / pole_tip / pole_h

同一根竖杆在两边是两种身份、两套「可达」定义。本模块是唯一的那份几何：
两边都从这里取 Surface，只在自己的能力表 / 性格权重上做过滤。

Surface 的两条轴
    axis = "h"  水平面：y + [lo, hi]（地板 / 窗台 / 横杆面 / 庇护所地面与屋顶）
    axis = "v"  竖直线：x + [top, bot]（竖杆 / 背景区域 / 庇护所墙）

三分法（文档：Wall / Pole / Background 彻底分家）：

    Surface  = 「最终可导航的**实体**表面」  —— 墙 WALL / 杆 POLE / 平台 TOP
    Background = 「非实体的**空间区域**」      —— 别人窗口露出来的竖边
    Window   = BackgroundRegion + TopSurface 的组合，**不是**一种墙

具体口径：

    | 类型       | 实体碰撞 | 可站 | 普通攀爬    | 特殊攀爬          |
    | WALL       | 是       | 否   | Wall Climb  | —                 |
    | POLE       | 否       | 否   | Pole Climb  | —                 |
    | BACKGROUND | **否**   | 否   | 否          | **Background Climb** |
    | PLATFORM   | 是/平台  | 是   | —           | —                 |

窗口左右竖边**不再**生成任何可攀爬竖线（旧的 WINDOW_EDGE 已删除）：
它既不是杆子也不是实体墙；窗口 = 背景区域 + 顶面，窗口内的水平活动由
``chunkphys.aabb_wall_collide``（屏幕边框）与 ``_integrate`` 的左右边界负责。
任何 AI 都**不能**靠「看起来像一条竖线」把墙/背景升级成杆子。
"""
from __future__ import annotations

import math

# ── 面种类（原版 AItile.Accessibility / TerrainType 的桌宠映射）──
FLOOR = "floor"                    # 屏幕地板
PLATFORM = "platform"              # 别的窗口露出来的顶边（单向平台）
SHELTER_FLOOR = "shelter_floor"    # 庇护所屋里地面
SHELTER_ROOF = "shelter_roof"      # 庇护所屋顶
HPOLE = "hpole"                    # 横杆的杆面
VPOLE = "vpole"                    # 真正的竖杆
WALL = "wall"                      # 真正的实体墙面（庇护所墙体 / 实心地形边）
BACKGROUND = "background"          # 背景区域（别人窗口露出来的竖边）：非实体
SHELTER_WALL = "shelter_wall"      # 庇护所墙体
# 已废弃：窗口左右竖边不再是一种 Surface（见模块 docstring）。常量留名不产出。
WINDOW_EDGE = "window_edge"

# 竖直面的攀爬能力类：Surface.climb → Caps 里对应的一位
CLIMB_POLE = "pole"                # 竖杆
CLIMB_WALL = "wall"                # 实体墙（WallClimber）
CLIMB_BACKGROUND = "background"    # 背景区域（原版 WallClimber 的背景墙攀爬）
CLIMB_EDGE = "edge"                # 已废弃（旧窗口竖边）

HORIZONTAL_KINDS = frozenset((FLOOR, PLATFORM, SHELTER_FLOOR, SHELTER_ROOF, HPOLE))
VERTICAL_KINDS = frozenset((VPOLE, WALL, BACKGROUND, SHELTER_WALL))
STACK_KINDS = frozenset((FLOOR, PLATFORM, SHELTER_FLOOR, SHELTER_ROOF, HPOLE))

GRID_CELL = 96.0        # 空间桶边长（LOS / 边候选粗筛）
CAPSULE_PAD = 0.5       # 墙 / 竖边的视觉半厚


class Surface:
    """一块导航地形。水平面看 (y, lo, hi)；竖直线看 (x, top, bot)。"""

    __slots__ = ("sid", "kind", "axis", "y", "lo", "hi", "x", "top", "bot",
                 "stand", "climb", "walk_top", "solid", "pole", "shelter",
                 "door", "ref")

    def __init__(self, sid, kind, y=None, lo=None, hi=None, x=None, top=None,
                 bot=None, stand=False, climb=None, walk_top=False, solid=False,
                 pole=None, shelter=None, door=False, ref=None):
        self.sid = sid
        self.kind = kind
        self.axis = "h" if kind in HORIZONTAL_KINDS else "v"
        self.y = float(y) if y is not None else 0.0
        self.lo = float(min(lo, hi)) if lo is not None else 0.0
        self.hi = float(max(lo, hi)) if lo is not None else 0.0
        self.x = float(x) if x is not None else 0.0
        self.top = float(min(top, bot)) if top is not None else 0.0
        self.bot = float(max(top, bot)) if top is not None else 0.0
        self.stand = bool(stand)
        self.climb = climb
        self.walk_top = bool(walk_top)
        self.solid = bool(solid)
        self.pole = pole
        self.shelter = shelter
        self.door = bool(door)
        self.ref = ref

    # ── 通用查询 ──
    @property
    def horizontal(self):
        return self.axis == "h"

    @property
    def width(self):
        return self.hi - self.lo if self.axis == "h" else self.bot - self.top

    def mid(self):
        return (0.5 * (self.lo + self.hi), self.y) if self.axis == "h" \
            else (self.x, 0.5 * (self.top + self.bot))

    def covers_x(self, x, pad=0.0):
        return self.lo - pad <= x <= self.hi + pad

    def covers_y(self, y, pad=0.0):
        return self.top - pad <= y <= self.bot + pad

    def key(self):
        return (self.sid, self.kind, round(self.y, 1), round(self.lo, 1),
                round(self.hi, 1), round(self.x, 1), round(self.top, 1),
                round(self.bot, 1))

    def __repr__(self):
        if self.axis == "h":
            return "<%s y=%.0f [%.0f..%.0f]>" % (self.kind, self.y, self.lo, self.hi)
        return "<%s x=%.0f [%.0f..%.0f]>" % (self.kind, self.x, self.top, self.bot)


class SupportContact:
    """脚下的支撑接触（文档口径）：导航 / 物理 / 脚 / 动画共用同一份。

    旧实现里 TerrainQuery.walk_floors() / _ground_y() / Lizard._integrate() /
    _climb_step() / floor_under() 各算一份「地面」，可能站在不同的面上。
    """

    __slots__ = ("sid", "y", "x_min", "x_max", "kind", "surface")

    def __init__(self, sid, y, x_min, x_max, kind, surface=None):
        self.sid = sid
        self.y = float(y)
        self.x_min = float(min(x_min, x_max))
        self.x_max = float(max(x_min, x_max))
        self.kind = kind
        self.surface = surface

    def __repr__(self):
        return "SupportContact(%s y=%.1f [%.0f..%.0f])" % (
            self.kind, self.y, self.x_min, self.x_max)


# ══════════════════════════════════════════════════════════════════════
# 障碍：LOS / 碰撞共用的底层几何（原版 Solid tile）
# ══════════════════════════════════════════════════════════════════════

class Obstacle:
    """一条胶囊障碍（线段 + 半径）。矩形实心体用四条胶囊表示。"""

    __slots__ = ("x0", "y0", "x1", "y1", "r", "kind")

    def __init__(self, x0, y0, x1, y1, r=CAPSULE_PAD, kind="solid"):
        self.x0, self.y0 = float(x0), float(y0)
        self.x1, self.y1 = float(x1), float(y1)
        self.r = float(r)
        self.kind = kind

    @property
    def bbox(self):
        return (min(self.x0, self.x1) - self.r, min(self.y0, self.y1) - self.r,
                max(self.x0, self.x1) + self.r, max(self.y0, self.y1) + self.r)

    def __repr__(self):
        return "Obstacle(%s %.0f,%.0f-%.0f,%.0f r=%.1f)" % (
            self.kind, self.x0, self.y0, self.x1, self.y1, self.r)


def seg_seg_dist2(ax, ay, bx, by, cx, cy, dx, dy):
    """两条线段的最近距离平方（文档：真正的 capsule intersection，不再用
    「无限薄线段 + 两个端点圆」那种只在端点补圆的近似）。"""
    ux, uy = bx - ax, by - ay
    vx, vy = dx - cx, dy - cy
    wx, wy = ax - cx, ay - cy
    a = ux * ux + uy * uy
    b = ux * vx + uy * vy
    c = vx * vx + vy * vy
    d = ux * wx + uy * wy
    e = vx * wx + vy * wy
    eps = 1e-9
    if a <= eps and c <= eps:
        return wx * wx + wy * wy
    if a <= eps:
        t = 0.0
        s = _clampf(e / c, 0.0, 1.0) if c > eps else 0.0
    else:
        if c <= eps:
            s = 0.0
            t = _clampf(-d / a, 0.0, 1.0)
        else:
            den = a * c - b * b
            t = _clampf((b * e - c * d) / den, 0.0, 1.0) if abs(den) > eps else 0.0
            s = (b * t + e) / c
            if s < 0.0:
                s = 0.0
                t = _clampf(-d / a, 0.0, 1.0)
            elif s > 1.0:
                s = 1.0
                t = _clampf((b - d) / a, 0.0, 1.0)
    px, py = ax + t * ux, ay + t * uy
    qx, qy = cx + s * vx, cy + s * vy
    return (px - qx) ** 2 + (py - qy) ** 2


def _clampf(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


class SpatialGrid:
    """均匀网格（文档 §9/§22/§36）：把 O(N×M) 的全表扫描压到局部邻居。"""

    __slots__ = ("cell", "_cells")

    def __init__(self, cell=GRID_CELL):
        self.cell = float(cell)
        self._cells = {}

    def add(self, x0, y0, x1, y1, item):
        c = self.cell
        ix0, ix1 = int(math.floor(min(x0, x1) / c)), int(math.floor(max(x0, x1) / c))
        iy0, iy1 = int(math.floor(min(y0, y1) / c)), int(math.floor(max(y0, y1) / c))
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                self._cells.setdefault((ix, iy), []).append(item)

    def query(self, x0, y0, x1, y1):
        """区间覆盖到的桶里所有条目（可能有重复，调用方按需去重）。"""
        c = self.cell
        ix0, ix1 = int(math.floor(min(x0, x1) / c)), int(math.floor(max(x0, x1) / c))
        iy0, iy1 = int(math.floor(min(y0, y1) / c)), int(math.floor(max(y0, y1) / c))
        out = []
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                got = self._cells.get((ix, iy))
                if got:
                    out.extend(got)
        return out

    def __len__(self):
        return sum(len(v) for v in self._cells.values())

# ══════════════════════════════════════════════════════════════════════
# NavGeometry：这一帧的地形快照（两边共用）
# ══════════════════════════════════════════════════════════════════════

class NavGeometry:
    """一帧的全场地形。由 window 一次性编译，蜥蜴与蛞蝓猫共用同一份。

    以前两份几何各建各的：TerrainQuery 每 tick 建一次，SurfaceGraph 每只猫
    建一次。现在只有这一个 build()，两边的「可达 / 能不能站 / 挡不挡视线」
    都从同一份 Surface 出发。
    """

    __slots__ = ("win", "WL", "HL", "surfaces", "obstacles", "grid",
                 "surf_grid", "sig", "version", "_by_sid")

    def __init__(self, win, WL, HL):
        self.win = win
        self.WL = float(WL)
        self.HL = float(HL)
        self.surfaces = []
        self.obstacles = []
        self.grid = SpatialGrid()
        self.surf_grid = SpatialGrid()
        self._by_sid = {}
        self.sig = ()
        self.version = int(getattr(win, "_nav_version", 0) or 0)

    # ── 构建 ──
    def _add(self, surf):
        self.surfaces.append(surf)
        self._by_sid[surf.sid] = surf
        if surf.axis == "h":
            self.surf_grid.add(surf.lo, surf.y, surf.hi, surf.y, surf)
        else:
            self.surf_grid.add(surf.x, surf.top, surf.x, surf.bot, surf)
        if surf.solid:
            if surf.axis == "v":
                ob = Obstacle(surf.x, surf.top, surf.x, surf.bot,
                              CAPSULE_PAD, surf.kind)
            else:
                ob = Obstacle(surf.lo, surf.y, surf.hi, surf.y,
                              CAPSULE_PAD, surf.kind)
            self.grid.add(ob.x0, ob.y0, ob.x1, ob.y1, ob)
        return surf

    @classmethod
    def build(cls, win):
        WL = float(getattr(win, "_WL", 0.0) or 0.0)
        HL = float(getattr(win, "_HL", 0.0) or 0.0)
        g = cls(win, WL, HL)
        from ..core import chunkphys
        from ..world.pole import VERTICAL, HORIZONTAL, POLE_RAD
        from ..world.enums import ItemState

        # ① 地板：唯一一块恒在的可站面
        if WL > 1.0 and HL > 1.0:
            g._add(Surface("floor", FLOOR, y=HL, lo=0.0, hi=WL, stand=True))

        # ② 别的窗口露出来的顶边（单向平台）
        for k, (x0, y, x1) in enumerate(chunkphys.platforms() or ()):
            lo, hi = max(min(x0, x1), 0.0), min(max(x0, x1), WL)
            if hi - lo < 1.0:
                continue
            g._add(Surface("plat:%d" % k, PLATFORM, y=y, lo=lo, hi=hi, stand=True))

        # ③ 杆：竖杆（可攀爬竖线）/ 横杆（可站的杆面）
        poles = []
        for pl in getattr(win, "poles", ()) or ():
            if getattr(pl, "state", None) != ItemState.FREE:
                continue
            if getattr(pl, "virtual", False):
                continue
            poles.append(pl)
        for k, pl in enumerate(poles):
            if getattr(pl, "kind", None) == VERTICAL:
                top, bot = min(pl.ay, pl.by), max(pl.ay, pl.by)
                if bot - top < 8.0:
                    continue
                g._add(Surface("vpole:%d" % k, VPOLE, x=pl.bx, top=top, bot=bot,
                               stand=True, climb=CLIMB_POLE, solid=True, pole=pl))
            elif getattr(pl, "kind", None) == HORIZONTAL:
                lo, hi = max(min(pl.ax, pl.bx), 0.0), min(max(pl.ax, pl.bx), WL)
                if hi - lo < 1.0:
                    continue
                g._add(Surface("hpole:%d" % k, HPOLE, y=pl.ay, lo=lo, hi=hi,
                               stand=True, solid=True, pole=pl))

        # ④ 本窗口左右竖边：**不再是地形**（文档三分法）。
        #    旧版把它们做成 WINDOW_EDGE（碰撞 + 可爬 + 顶端可站），
        #    于是「窗口边 = 杆子」这条旧语义一直在给 AI 发假杆。
        #    现在窗口 = 背景区域 + 顶面：这里既不产 surface，也不产 obstacle；
        #    屏幕边框由 chunkphys.aabb_wall_collide / _integrate 的左右边界管。

        # ⑤ 庇护所真墙体的竖条（扁平条不算竖墙）
        for n, (x0, y0, x1, y1) in enumerate(chunkphys.solids() or ()):
            if (y1 - y0) <= (x1 - x0) + 1.0:
                continue
            g._add(Surface("swall:%d:0" % n, SHELTER_WALL, x=x0, top=y0, bot=y1,
                           stand=True, climb=CLIMB_WALL, solid=True))
            g._add(Surface("swall:%d:1" % n, SHELTER_WALL, x=x1, top=y0, bot=y1,
                           stand=True, climb=CLIMB_WALL, solid=True))

        # ⑤c 手绘墙条（用户入口拉出来的墙）：竖墙＝两条可爬墙面，横墙＝顶面可站。
        #     障碍（LOS / 碰撞）已经在下面第 ⑦ 段按 solids() 统一铺过。
        for n, (wx0, wy0, wx1, wy1) in enumerate(getattr(win, "extra_walls", ()) or ()):
            if (wx1 - wx0) <= (wy1 - wy0):
                g._add(Surface("wall:%d:0" % n, SHELTER_WALL, x=wx0, top=wy0,
                               bot=wy1, stand=True, climb=CLIMB_WALL, solid=True))
                g._add(Surface("wall:%d:1" % n, SHELTER_WALL, x=wx1, top=wy0,
                               bot=wy1, stand=True, climb=CLIMB_WALL, solid=True))
            else:
                g._add(Surface("walltop:%d" % n, PLATFORM, y=wy0, lo=wx0, hi=wx1,
                               stand=True, solid=True))

        # ⑤b 背景区域 BackgroundRegion（别人窗口露出来的竖边）。
        #     三分法：背景**不是**墙 —— 不是实体（不挡路 / 不挡视线 / 不参与
        #     脚支撑）、不能站；只有 Background Climb 的品种能附上去。
        #     旧版这里 kind=WALL / solid=True，于是「墙被当杆爬 + 挡住视线」
        #     两个 bug 都由这一处发源。
        for ws in getattr(win, "wall_surfaces", ()) or ():
            for j, (tp, bt) in enumerate(ws.segments):
                g._add(Surface("bg:%d:%d" % (ws.index, j), BACKGROUND, x=ws.x,
                               top=tp, bot=bt, stand=False,
                               climb=CLIMB_BACKGROUND, solid=False, ref=ws))

        # ⑥ 庇护所：屋里地面 / 屋顶 / 门洞（统一 Shelter Navigation）。
        for k, sh in enumerate(getattr(win, "shelters", ()) or ()):
            try:
                lo, hi = sh.interior_span()
                if hi - lo >= 2.0:
                    g._add(Surface("shfloor:%d" % k, SHELTER_FLOOR,
                                   y=sh.interior_floor_y(), lo=lo, hi=hi,
                                   stand=True, shelter=sh))
                rx0, rx1 = sh.roof_span()
                if rx1 - rx0 >= 2.0 and sh.y > 4.0:
                    g._add(Surface("shroof:%d" % k, SHELTER_ROOF, y=sh.y,
                                   lo=rx0, hi=rx1, stand=True, shelter=sh))
                dr = sh.door_rect()
                if dr is not None:
                    d0, _dy0, d1, _dy1 = dr
                    if abs(d1 - d0) >= 2.0:
                        g._add(Surface("shdoor:%d" % k, SHELTER_FLOOR,
                                       y=sh.interior_floor_y(),
                                       lo=min(d0, d1), hi=max(d0, d1),
                                       stand=True, shelter=sh, door=True))
            except Exception:
                continue

        # ⑦ 障碍（LOS / 碰撞共用）：实心地形 + 杆。扁平实心条也要挡视线，
        #    所以这里按 solids() 的矩形铺胶囊，而不是只挑竖条。
        for x0, y0, x1, y1 in chunkphys.solids() or ():
            for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1),
                                     (x1, y1, x0, y1), (x0, y1, x0, y0)):
                ob = Obstacle(ax, ay, bx, by, CAPSULE_PAD, SHELTER_WALL)
                g.obstacles.append(ob)
                g.grid.add(ax, ay, bx, by, ob)
        for pl in poles:
            ob = Obstacle(pl.ax, pl.ay, pl.bx, pl.by, POLE_RAD, "pole")
            g.obstacles.append(ob)
            g.grid.add(pl.ax, pl.ay, pl.bx, pl.by, ob)

        # ── 版本：内容签名驱动，只有导航几何真的变了才 +1 ──
        g.sig = tuple(s.key() for s in g.surfaces)
        if getattr(win, "_nav_sig", None) != g.sig:
            try:
                win._nav_sig = g.sig
                win._nav_version = int(getattr(win, "_nav_version", 0) or 0) + 1
            except Exception:
                pass
        g.version = int(getattr(win, "_nav_version", 0) or 0)
        return g

    # ── 过滤查询（能力表只做过滤，几何不变）──
    def horizontal_surfaces(self, kinds=None):
        if kinds is None:
            return tuple(s for s in self.surfaces if s.axis == "h")
        return tuple(s for s in self.surfaces if s.axis == "h" and s.kind in kinds)

    def vertical_surfaces(self, kinds=None):
        if kinds is None:
            return tuple(s for s in self.surfaces if s.axis == "v")
        return tuple(s for s in self.surfaces if s.axis == "v" and s.kind in kinds)

    def floors(self, caps=None):
        """这位 agent 能站的**水平面**（可站 + 能力过滤）。"""
        allow_shelter = True if caps is None else bool(
            getattr(caps, "can_enter_shelter", True))
        allow_hpole = True if caps is None else bool(
            getattr(caps, "hpole_walk", True))
        out = []
        for s in self.surfaces:
            if s.axis != "h" or not s.stand:
                continue
            if s.kind == HPOLE and not allow_hpole:
                continue
            if s.kind == SHELTER_FLOOR and not allow_shelter and not s.door:
                continue
            out.append(s)
        return tuple(out)

    def verticals(self, caps=None):
        """这位 agent 能攀爬的**竖直线**（能力过滤后）。"""
        out = []
        for s in self.surfaces:
            if s.axis != "v":
                continue
            if caps is not None and not caps.allows_climb(s.climb):
                continue
            out.append(s)
        return tuple(out)

    def climb_surfaces(self, caps=None):
        """元组视图：(x, top, bot, kind)，kind ∈ {pole, wall, background}。"""
        return tuple((s.x, s.top, s.bot, s.climb) for s in self.verticals(caps))

    # ── 旧元组视图（terrain.py 的历史调用方还在用）──
    def walk_floors(self, caps=None):
        return tuple((s.lo, s.y, s.hi) for s in self.floors(caps))

    def vpoles(self):
        return tuple((s.x, s.top, s.bot) for s in self.surfaces if s.kind == VPOLE)

    def hpoles(self):
        return tuple((s.lo, s.y, s.hi) for s in self.surfaces if s.kind == HPOLE)

    def walls(self):
        """**真正的实体墙**：(x, top, bot)。背景区域不在这里（见 backgrounds()）。"""
        return tuple((s.x, s.top, s.bot) for s in self.surfaces
                     if s.kind in (WALL, SHELTER_WALL))

    def backgrounds(self):
        """背景区域（别人窗口露出来的竖边）：(x, top, bot)。

        非实体、不可站；只有 ``caps.climb_background`` 的品种能附上去。
        """
        return tuple((s.x, s.top, s.bot) for s in self.surfaces
                     if s.kind == BACKGROUND)

    # ── 支撑接触（导航 / 物理 / 脚 / 动画共用）──
    def support_contact(self, x, y, caps=None, default=None):
        """x 处、y 之下最近的可站面。没有就返回 default（通常是屏幕地板）。"""
        hl = self.HL if default is None else float(default)
        best = None
        for s in self.floors(caps):
            if s.y < y - FLOOR_SNAP_TOL:
                continue
            if not s.covers_x(x, 4.0):
                continue
            if best is None or s.y < best.y:
                best = s
        if best is not None:
            return SupportContact(best.sid, best.y, best.lo, best.hi,
                                  best.kind, best)
        return SupportContact("floor", hl, 0.0, self.WL, FLOOR, None)

    def floor_under(self, x, y, caps=None):
        return self.support_contact(x, y, caps).y

    # ── 视线 ──
    def los_blocked(self, x0, y0, x1, y1):
        """(x0,y0)-(x1,y1) 之间隔着地形吗（真正的 capsule 相交）。"""
        cand = self.grid.query(min(x0, x1) - CAPSULE_PAD, min(y0, y1) - CAPSULE_PAD,
                               max(x0, x1) + CAPSULE_PAD, max(y0, y1) + CAPSULE_PAD)
        seen = set()
        for ob in cand:
            k = id(ob)
            if k in seen:
                continue
            seen.add(k)
            r = ob.r
            if seg_seg_dist2(x0, y0, x1, y1, ob.x0, ob.y0, ob.x1, ob.y1) <= r * r:
                return True
        return False

    def __repr__(self):
        return "<NavGeometry v%d %d surfaces %d obstacles>" % (
            self.version, len(self.surfaces), len(self.obstacles))


FLOOR_SNAP_TOL = 2.0      # 面比身体高这么点就不算「脚下的地」


def _nav_stamp(win):
    """几何快照的廉价指纹：tick + 版本号 + 各类地形的**条数**。

    只看 tick 会在「同一个 tick 内改地形」（测试、放置流程）时读到过期快照；
    只看版本号又依赖调用方记得 +1。两个一起看，既不会漏也不会白建。
    真正的「导航版本」由 NavGeometry.build 按内容签名给出（见 nav_version），
    寻路图缓存用的是那个，所以这里多建一次也不会让图重建。
    """
    from ..core import chunkphys
    try:
        n_plat = len(chunkphys.platforms() or ())
        n_solid = len(chunkphys.solids() or ())
    except Exception:
        n_plat = n_solid = -1
    return (getattr(win, "_pole_tick", None),
            int(getattr(win, "geometry_version", 0) or 0),
            int(getattr(win, "world_version", 0) or 0),
            n_plat, n_solid,
            len(getattr(win, "poles", ()) or ()),
            len(getattr(win, "wall_surfaces", ()) or ()),
            len(getattr(win, "shelters", ()) or ()))


def nav_geometry(win):
    """这一帧的统一地形快照（同一份指纹下只建一次，两边共用）。"""
    stamp = _nav_stamp(win)
    cache = getattr(win, "_navgeom_cache", None)
    if cache is not None and cache[0] == stamp and cache[1] is not None:
        return cache[1]
    g = NavGeometry.build(win)
    try:
        win._navgeom_cache = (stamp, g)
    except Exception:
        pass
    return g


def nav_version(win):
    """导航几何版本：只在 platform / pole / wall / shelter 变化时 +1。

    文档口径：旧实现用 world_version 当键，新增生物 / 物品状态 / 动画都会让
    整张寻路图重建。寻路图只依赖这一份「导航版本」。
    """
    return int(getattr(win, "_nav_version", 0) or 0)


def segment_capsule_hit(ax, ay, bx, by, ob):
    """线段与一条胶囊障碍相交吗（供外部复用）。"""
    return seg_seg_dist2(ax, ay, bx, by, ob.x0, ob.y0, ob.x1, ob.y1) <= ob.r * ob.r
