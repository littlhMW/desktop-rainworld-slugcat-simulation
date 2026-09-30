# -*- coding: utf-8 -*-
"""所有生物共用的地形查询：地面 / 平台顶 / 竖杆 / 横杆 / 背景墙。

反编译口径：原版一张地图的地形就是 AImap / AItile —— Floor / Wall / Ceiling /
Climb（``verticalBeam`` 竖杆、``horizontalBeam`` 横杆）都在同一张连通图里；
「这条路这只生物能不能走」由 ``CreatureTemplate.AccessibilityResistance`` /
``ConnectionResistance``（AImap.cs:59-77）决定，蜥蜴读的是 LizardPather 给出的
MovementConnection，而不是动作层临时去找一根竖线。

桌宠映射（与蛞蝓猫侧 planning/surface.py 读的是同一批几何）：

===========  ==========================================================
Floor        屏幕地板 + 别的窗口顶边（``chunkphys.platforms()``）
Climb(竖)    ``poles`` 里的竖杆 + 窗口左右竖边露出来的墙段（``world.walls``）
Climb(横)    ``poles`` 里的横杆：能踩在杆面上走
Wall         同上；只有 WallClimber 品种（蓝 / 白 / 鳗鱼蜥）能把它当楼梯
===========  ==========================================================

这一层只回答三个问题：**我周围有哪些地形 / 这块地形怎么上去 / 我的能力表
允不允许用**。真正的位移仍归各自的物理（蜥蜴走 ``_step_wall``，蛞蝓猫走
PoleClimb / HPole）。
"""
from __future__ import annotations

from .enums import ItemState
from .pole import VERTICAL, HORIZONTAL

FLOOR_TOL = 18.0        # 「这块地形的落脚点在我这一层」的容差
ATTACH_TOL = 30.0       # 上墙点离我多近算「走过去就能抓」
GRIP_R = 30.0           # 直接抓线的半径
REACH_PENALTY = 120.0   # 线太远：算上绕路代价
CLIMB_REACH_DEFAULT = 220.0
FLOOR_SNAP = 2.0        # 面比身体高这么点就不算「脚下的地」


class Caps:
    """一只生物的地形能力表（原版 CreatureTemplate / LizardBreedParams）。"""

    __slots__ = ("walk", "jump", "wall_climb", "pole_climb", "wall_jump", "climb_reach")

    def __init__(self, walk=True, jump=True, wall_climb=False, pole_climb=False,
                 wall_jump=False, climb_reach=CLIMB_REACH_DEFAULT):
        self.walk = bool(walk)
        self.jump = bool(jump)
        self.wall_climb = bool(wall_climb)
        self.pole_climb = bool(pole_climb)
        self.wall_jump = bool(wall_jump)
        self.climb_reach = float(climb_reach)

    def __repr__(self):
        return "Caps(walk=%s jump=%s wall=%s pole=%s)" % (
            self.walk, self.jump, self.wall_climb, self.pole_climb)


class TerrainQuery:
    """一次世界快照上的地形查询。每 tick 建一次，全场生物共用同一份。"""

    __slots__ = ("win", "_floors")

    def __init__(self, win):
        self.win = win
        self._floors = None

    # ── 原始地形 ──
    def platforms(self):
        """窗口顶边（可站的平台）：``(x0, y, x1)``。"""
        from ..core import chunkphys
        return tuple(chunkphys.platforms() or ())

    def _poles(self):
        out = []
        for pl in getattr(self.win, "poles", ()) or ():
            if getattr(pl, "state", None) != ItemState.FREE:
                continue                      # 被拿起 / 已消失的杆不是地形
            if getattr(pl, "virtual", False):
                continue                      # 鼠标那截虚杆：不是地形
            out.append(pl)
        return out

    def vpoles(self):
        """竖杆：``(x, top, bot)``（top < bot）。"""
        out = []
        for pl in self._poles():
            if getattr(pl, "kind", None) != VERTICAL:
                continue
            out.append((float(pl.x), min(pl.ay, pl.by), max(pl.ay, pl.by)))
        return tuple(out)

    def hpoles(self):
        """横杆：``(x0, y, x1)`` —— 杆面可以踩。"""
        out = []
        for pl in self._poles():
            if getattr(pl, "kind", None) != HORIZONTAL:
                continue
            out.append((min(pl.ax, pl.bx), float(pl.ay), max(pl.ax, pl.bx)))
        return tuple(out)

    def walls(self):
        """背景墙的**可见**竖段：``(x, top, bot)``。"""
        out = []
        for ws in getattr(self.win, "wall_surfaces", ()) or ():
            for top, bot in ws.segments:
                out.append((float(ws.x), float(top), float(bot)))
        if out:
            return tuple(out)
        for rect in getattr(self.win, "walls", ()) or ():     # 兜底：还没建 surface
            x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
            top, bot = min(y0, y1), max(y0, y1)
            out.append((float(x0), top, bot))
            out.append((float(x1), top, bot))
        return tuple(out)

    def climb_surfaces(self):
        """可攀爬的**竖线**：``(x, top, bot, kind)``，kind ∈ {"pole", "wall"}。

        横杆不在这里 —— 它不是竖线，是脚下的地形（见 walk_floors）。
        """
        out = [(x, t, b, "pole") for x, t, b in self.vpoles()]
        out += [(x, t, b, "wall") for x, t, b in self.walls()]
        return tuple(out)

    # ── 可站的面 ──
    def walk_floors(self):
        """能站在上面的面：屏幕地板 + 窗口顶边 + 横杆杆面 -> ``(x0, y, x1)``。"""
        wl = float(getattr(self.win, "_WL", 0.0) or 0.0)
        hl = float(getattr(self.win, "_HL", 0.0) or 0.0)
        out = [(0.0, hl, wl)]
        for x0, y, x1 in self.platforms():
            out.append((float(x0), float(y), float(x1)))
        for x0, y, x1 in self.hpoles():
            out.append((x0, y, x1))
        return tuple(out)

    def floor_under(self, x, y):
        """x 处、y 之下最近的可站面（没有就退回屏幕地板）。"""
        hl = float(getattr(self.win, "_HL", 0.0) or 0.0)
        best = hl
        for x0, fy, x1 in self.walk_floors():
            if fy < y - FLOOR_SNAP:
                continue                      # 面在我上面：踩不到
            if not (x0 - 4.0 <= x <= x1 + 4.0):
                continue
            if fy < best:
                best = fy
        return best

    # ── 路线 ──
    def route_hint(self, x, y, tx, ty, caps):
        """够不着目标时先问地形：有没有一条「走 → 上墙 / 上杆」的路线。

        返回 ``(mode, sx, top, bot, dir, reason)``；没有可用地形就 None。mode ∈
        ``{"climb_wall", "climb_pole"}``，sx 是上墙点（线所在的 x），(top, bot)
        是这条线的上下端，dir = +1 向上 / -1 向下。
        """
        if caps is None or ty >= y - FLOOR_TOL:
            return None                       # 目标不比我高：直冲 / 跳跃那套
        best = None
        for sx, top, bot, kind in self.climb_surfaces():
            if kind == "wall":
                if not caps.wall_climb:
                    continue                  # 不会爬墙的品种：背景墙不是它的地形
            elif not caps.pole_climb:
                continue
            if top > ty + 12.0:
                continue                      # 线顶还够不着目标那一层
            on_line = top - 12.0 <= y <= bot + 12.0
            foot_here = (bot >= y - ATTACH_TOL) and (bot <= y + ATTACH_TOL)
            if not (on_line or foot_here):
                continue                      # 线底不在我这一层，也还没爬上去
            d = abs(x - sx)
            if d > caps.climb_reach:
                continue
            score = d + (0.0 if d <= GRIP_R else REACH_PENALTY)
            if best is None or score < best[0]:
                best = (score, sx, kind, top, bot)
        if best is None:
            return None
        return ("climb_" + best[2], best[1], best[3], best[4], 1,
                "terrain:%s" % best[2])

    def __repr__(self):
        return "<Terrain floors=%d vpoles=%d hpoles=%d walls=%d>" % (
            len(self.walk_floors()), len(self.vpoles()), len(self.hpoles()),
            len(self.walls()))
