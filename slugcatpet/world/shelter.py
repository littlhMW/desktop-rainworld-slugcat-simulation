# -*- coding: utf-8 -*-
"""庇护所：**模板驱动的真几何** —— 房间形状来自原版庇护所房间的逐 tile 提取。

反编译口径（每个字段都能追到源码，见 ``rainworld_dump/shelters/*.json``）：

* 原版庇护所是一个房间（48x35 tile），可走区域（terrain==Air）只有两段：
  一间 **chamber** + 一条 **corridor**；corridor 尽头是 ``Terrain==ShortcutEntrance``
  的入口 tile（``ShelterDoor`` 构造函数按 ``Custom.fourDirections`` 找第一个非
  Solid 邻居得到 ``dir``，即「从入口指向房内」）。
* 门的实体位置 ``pZero = MiddleOfTile(入口tile) + dir * 60``（3 tile），
  关门时把 ``closeTiles[n] = 入口tile + dir*(n+2)``（n=0..3）这 4 个 tile 变成
  Solid —— 也就是**门封住的是走廊**，不是 chamber 的墙。
* 墙体不是贴图：原版墙就是 ``Room.Tile.Terrain == Solid``，由房间 tile 渲染器
  用材质/调色板画出来；庇护所**没有**"墙的 PNG"。所以桌宠这边墙用实心矩形画，
  门的 42 张 sprite 才是真贴图（见 ``rendering/shelter_gate.py``）。
* 门开合：``Close()`` → ``closeSpeed = 0.003125``（320 tick 关到底）；
  开场 ``openUpTicks = 350``（350 tick 开到底）。

桌宠适配（都标了来源）：
* 原版 corridor 高 1 tile，猫是匍匐钻过去的；桌宠的猫不匍匐，所以走廊放宽到
  ``TUNNEL_H`` tile（[APPROXIMATION]），并把它放在地面高度上，猫走着就能进门。
* 任意矩形：底边 ``y + h`` 就是这间庇护所自己的地板（不再强制贴桌面地面），
  像资源管理器框选那样拉出来的矩形直接就是庇护所。
  底边这一条也是真墙（底墙），只在入口那一列缺一块；猫进了屋就站在底墙上。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

from ..planning import point_goal
from .pole import POLE_RAD

OPEN = "open"
CLOSING = "closing"
CLOSED = "closed"
OPENING = "opening"

# ── 反编译常量（ShelterDoor.cs） ──
TILE = 20.0                    # 原版 tile 边长：posZ = (13 + 21*number) * 20
DOOR_CLOSE_TICKS = 320         # Close(): closeSpeed = 0.003125 → 1/0.003125
DOOR_OPEN_TICKS = 350          # openUpTicks = 350f
DOOR_SPRITES = 42              # InitiateSprites: new FSprite[42]
DOOR_PZERO_TILES = 3.0         # pZero = MiddleOfTile(entrance) + dir * 60f
DOOR_CLOSE_TILES = 4           # closeTiles[4] = 入口 + dir*(2..5)
TUNNEL_H = 2                   # [APPROXIMATION] 原版 1 tile，桌宠猫不匍匐

# 墙厚 = 2 倍杆宽（杆画出来就是 2*POLE_RAD 宽）。固定像素值，不再跟着贴图 tile 走。
WALL_PX = POLE_RAD * 4.0

# 配色：RW 庇护所是灰褐色金属（原版走 ColoredSprite3 + 房间调色板）
_FRAME = (62, 58, 52, 236)
_METAL = (104, 99, 90, 255)
_METAL_HI = (138, 131, 118, 255)
_METAL_LO = (74, 70, 64, 255)
_INNER = (34, 31, 28, 255)
_DOOR = (88, 84, 78, 255)
_DOOR_HI = (152, 146, 132, 255)
_RUST = (124, 92, 58, 255)
_RIVET = (176, 170, 156, 255)


def _clampf(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _lerp(a, b, t):
    return a + (b - a) * t


def ease(t):
    """门板的缓动：起步慢、中段快、收尾慢。"""
    t = _clampf(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True)
class ShelterTemplate:
    """一间庇护所的真实形状（tile 为单位）。

    chamber_w/h、tunnel_len 来自对 77 间原版庇护所房间的逐 tile 统计
    （``slugcatpet/rwdump/shelter.py`` → ``shelter_geometry.json``）；``door_side``
    是那批房间入口方位的多数值，**不是按屏幕中线猜的**。
    """

    key: str
    chamber_w: int
    chamber_h: int
    tunnel_len: int
    door_side: str                    # "right" / "left"：入口在 chamber 的哪一边
    wall: int = 1
    tunnel_h: int = TUNNEL_H
    close_ticks: int = DOOR_CLOSE_TICKS
    open_ticks: int = DOOR_OPEN_TICKS
    source: str = ""
    tag: str = "[EXACT SOURCE]"

    def to_dict(self):
        return {"key": self.key, "chamber_w": self.chamber_w,
                "chamber_h": self.chamber_h, "tunnel_len": self.tunnel_len,
                "tunnel_h": self.tunnel_h, "wall": self.wall,
                "door_side": self.door_side, "close_ticks": self.close_ticks,
                "open_ticks": self.open_ticks, "source": self.source,
                "tag": self.tag}

    @property
    def aspect(self):
        """足迹宽高比（拖拽预览按它锁比例，保证"拖出的就是真矩形"）。"""
        return (2 * self.wall + self.chamber_w + self.tunnel_len,
                self.wall + self.chamber_h)


# 两套模板都来自真实房间统计（rwdump/shelter.py，去重后 77 间）：
#   3x3 chamber + 5 tile 走廊 —— 34 间；横向入口 15 间里「左 11 / 右 4」→ left
#   6x5 chamber + 5 tile 走廊 —— 31 间；横向入口 31 间里「左 15 / 右 16」→ right
# door_side 的算法：ShelterDoor.cs:1170-1200 的 dir 是「入口 tile → 第一个非 Solid
# 邻居」，方向朝屋内；取反才是入口所在边。竖向入口（小房间 19 间 / 大房间 0 间）
# 在桌宠里没法贴地面，不参与多数值。
SHELTER_TEMPLATES = {
    "small": ShelterTemplate(
        key="small", chamber_w=3, chamber_h=3, tunnel_len=5, door_side="left",
        source="rwdump/shelter.py：34 间 3x3 房间的入口方位统计（左 11 / 右 4）",
        tag="[EXACT SOURCE]"),
    "large": ShelterTemplate(
        key="large", chamber_w=6, chamber_h=5, tunnel_len=5, door_side="right",
        source="rwdump/shelter.py：31 间 6x5 房间的入口方位统计（左 15 / 右 16）",
        tag="[EXACT SOURCE]"),
}


def template_of(name):
    return SHELTER_TEMPLATES.get(name) or SHELTER_TEMPLATES["large"]


def _ilin(a, b, v):
    """Mathf.InverseLerp：把 v 从 [a,b] 映射到 [0,1]。"""
    if a == b:
        return 0.0
    return _clampf((v - a) / (b - a), 0.0, 1.0)


class DoorPhases:
    """原版 ``ShelterDoor.DoorGraphic`` 的门部件相位（纯逻辑，无 Qt）。

    ``DrawSprites`` 读的是 ``segmentPairs / pistons / covers / pumps`` 的
    [cur, prev, rnd] 三元组，随机偏移在 ``Reset()`` 里抽一次；这里用庇护所自己的
    ``seed`` 起一条私有随机流，保证每扇门手感不同、但同一扇门跨 tick 稳定。
    """

    def __init__(self, seed=0):
        rng = random.Random(0x5D001 ^ (int(seed) * 2654435761 & 0xFFFFFFFF))
        self.seg = [[0.0, 0.0, rng.random() * 0.5] for _ in range(5)]
        self.pis = [[0.0, 0.0, rng.random() * 0.8] for _ in range(2)]
        self.cov = [[0.0, 0.0, rng.random() * 0.5] for _ in range(4)]
        self.pum = [[0.0, 0.0, rng.random() * 0.5] for _ in range(8)]
        self.flaps_open = 1.0
        self.pistons_closed = 0.0
        self.segments = 0.0
        self.pistons = 0.0
        self.covers = 0.0
        self.cylinders = 0.0
        self.pumps_enter = 0.0
        self.pumps_exit = 0.0
        self.segment_alpha = 1.0

    def step(self, closed):
        c = _clampf(closed, 0.0, 1.0)
        # 全部来自 DoorGraphic 的只读属性
        self.flaps_open = _ilin(0.04, 0.0, c)
        self.pistons_closed = _ilin(0.2, 0.1, c)
        self.segments = _ilin(0.2, 0.38, c)
        self.pistons = _ilin(0.38, 0.41, c)
        self.covers = _ilin(0.41, 0.51, c)
        self.cylinders = _ilin(0.53, 0.61, c)
        self.pumps_enter = _ilin(0.59, 0.7, c)
        self.pumps_exit = _ilin(0.75, 1.0, c)
        for s in self.seg:
            s[1] = s[0]
            s[0] = _ilin(s[2], s[2] + 0.5, self.segments)
        for q in self.pis:
            q[1] = q[0]
            q[0] = _ilin(q[2], 1.0, max(self.pistons, self.pistons_closed))
        for v in self.cov:
            v[1] = v[0]
            v[0] = _ilin(v[2], v[2] + 0.5, self.covers)
        for m in self.pum:
            m[1] = m[0]
            m[0] = _ilin(m[2], 1.0, self.pumps_enter)
        # DrawSprites: alpha = 1 - 4 * InverseLerp(0.78, 0.61, Closed) / 30
        self.segment_alpha = 1.0 - 4.0 * _ilin(0.78, 0.61, c) / 30.0

    def seg_lerp(self, i, ts):
        s = self.seg[i]
        return _lerp(s[1], s[0], ts)

    def piston_lerp(self, i, ts):
        s = self.pis[i]
        return _lerp(s[1], s[0], ts)

    def cover_lerp(self, i, ts):
        s = self.cov[i]
        return _lerp(s[1], s[0], ts)

    def pump_lerp(self, i, ts):
        s = self.pum[i]
        return _lerp(s[1], s[0], ts)


class Shelter:
    """一间庇护所：``(x, y, w, h)`` 就是真矩形，底边 ``y + h`` 是它自己的地板（地板上铺一条底墙）。"""

    MIN_W = 60.0
    MAX_W = 760.0
    MIN_H = 44.0
    MAX_H = 340.0

    def __init__(self, x, y, w, h, ground_y=None, WL=0.0, seed=0, door_ticks=None,
                 template=None, door_side=None):
        self.w = _clampf(float(w), self.MIN_W, self.MAX_W)
        self.h = _clampf(float(h), self.MIN_H, self.MAX_H)
        self.x = float(x)
        self.y = float(y)
        # 任意矩形：地板就是自己的底边，跟桌面地面无关（ground_y 参数只为旧调用兼容）
        self.ground_y = self.y + self.h
        self.WL = float(WL)
        self.seed = int(seed)
        self.template = template if isinstance(template, ShelterTemplate) \
            else template_of(template)
        self.door_side = door_side if door_side in ("left", "right") \
            else self.template.door_side
        self.door_ticks = int(door_ticks) if door_ticks \
            else int(self.template.close_ticks)
        self.open_ticks = max(1, int(self.template.open_ticks))
        self.center_x = self.x + self.w * 0.5
        self.center_y = self.y + self.h * 0.5
        self.door_state = OPEN
        self.close_fac = 0.0          # 0=全开 1=全关（原版 closedFac）
        self.eaves = 18.0
        self._rivets = [(0.12, 0.10), (0.88, 0.10), (0.12, 0.88), (0.88, 0.88)]
        self.phases = DoorPhases(self.seed)
        self._layout()
        self.phases.step(self.close_fac)

    # ── 几何：全部由模板比例 + 真实矩形推出 ──
    def _layout(self):
        tpl = self.template
        self.tile = max(4.0, (self.h - WALL_PX) / float(max(1, tpl.chamber_h)))
        t = self.tile
        wall = self.wall_px
        # 走廊长度：先按模板给，宽度不够就压缩（chamber 宽按模板值兜底）
        tun = tpl.tunnel_len * t
        cw = self.w - 2.0 * wall - tun
        if cw < tpl.chamber_w * t:
            cw = tpl.chamber_w * t
            tun = max(t, self.w - 2.0 * wall - cw)
        cw = max(t, cw)
        tun = max(t * 0.5, tun)
        self.tunnel_len_px = tun
        self.chamber_w_px = cw
        # 纵向：roof 占 wall tile，chamber 高由 h 决定，走廊从地面往上 tunnel_h tile
        self.tunnel_h_px = min(tpl.tunnel_h * t, self.h - self.wall_px)
        # 从左到右：左墙 | chamber | 走廊 | 外墙上段（入口缺口在它下面）
        self.left_wall = (self.x, self.y, self.x + wall, self.ground_y)
        cx0 = self.x + wall
        cx1 = cx0 + cw
        self.chamber = (cx0, self.ground_y - tpl.chamber_h * t, cx1, self.ground_y)
        if self.door_side == "right":
            self.tunnel = (cx1, self.ground_y - self.tunnel_h_px,
                           self.x + self.w - wall, self.ground_y)
            self.outer_wall = (self.x + self.w - wall, self.y,
                               self.x + self.w, self.ground_y - self.tunnel_h_px)
            self.entrance = (self.x + self.w - wall, self.ground_y - self.tunnel_h_px,
                             self.x + self.w, self.ground_y)
        else:
            self.tunnel = (self.x + wall, self.ground_y - self.tunnel_h_px,
                           cx0, self.ground_y)
            self.outer_wall = (self.x, self.y, self.x + wall,
                               self.ground_y - self.tunnel_h_px)
            self.entrance = (self.x, self.ground_y - self.tunnel_h_px,
                             self.x + wall, self.ground_y)
        self.roof = (self.x, self.y, self.x + self.w, self.y + wall)
        # 底墙（地板）：贴底边那一条，**入口那一列留空**
        # —— 猫 / 物件只能从入口进出，跟上面三面墙同一套碰撞。
        fy0 = self.ground_y - wall
        if self.door_side == "right":
            self.floor = (self.x, fy0, self.x + self.w - wall, self.ground_y)
        else:
            self.floor = (self.x + wall, fy0, self.x + self.w, self.ground_y)
        # 内墙：chamber 与走廊之间、走廊上沿之上的那一段
        if self.door_side == "right":
            self.inner_wall = (cx1, self.y + wall, cx1 + wall,
                               self.ground_y - self.tunnel_h_px)
        else:
            self.inner_wall = (cx0 - wall, self.y + wall, cx0,
                               self.ground_y - self.tunnel_h_px)
        self._inner_walls = [self.inner_wall] if \
            self.inner_wall[3] - self.inner_wall[1] > 1.0 else []
        # 门面中心（原版 pZero）：入口 tile 中点 + dir * 60
        ex0, ey0, ex1, ey1 = self.entrance
        ecx = (ex0 + ex1) * 0.5
        # ShelterDoor.cs:1170-1200：dir = 从 entrance tile 沿 fourDirections 取第一个
        # 非 Solid 邻居 —— 也就是走廊那一侧，**指向屋内**；pZero = MiddleOfTile(entrance)
        # + dir * 60 落在走廊中间，closeTiles 也铺在走廊上（entrance + dir*(n+2)）。
        # 这里 dir_x 记的是「朝屋外」的方向（门在哪边），dir 取它的相反数。
        sgn = 1.0 if self.door_side == "right" else -1.0
        self.dir_x = sgn                       # 门朝屋外的那一侧
        # 门机构整幅画布 140×126（ShelterGate 图集的 sourceSize，游戏里 1:1 不缩放）。
        # 桌宠的庇护所可以比一间房小，按「高度塞得下」等比缩，最大 1:1。
        self.door_scale = _clampf(self.h * 0.92 / 126.0, 0.30, 1.0)
        # 原版 pZero = MiddleOfTile(entrance) + dir * 60，dir 指向屋内（见上）。
        # 桌宠的门洞可能比一间房小，+60 后夹在庇护所里，保证机构不会甩到墙外。
        self.p_zero = (_clampf(ecx - sgn * 60.0, self.x + 2.0,
                               self.x + self.w - 2.0), (ey0 + ey1) * 0.5)

    @property
    def wall_px(self):
        return WALL_PX

    @property
    def door_t(self):
        """门板进度（兼容旧字段：0=开 1=关）。"""
        return self.close_fac

    @door_t.setter
    def door_t(self, v):
        self.close_fac = _clampf(float(v), 0.0, 1.0)

    # ── 几何查询 ──
    def safe_rect(self):
        """整间庇护所（含墙与门洞）的包围盒 —— 雨幕/变暗/积水按它挖洞。"""
        return (self.x, self.y, self.x + self.w, self.ground_y)

    def interior_rects(self):
        """可站人的内腔：chamber + 走廊（门关上时走廊也算屋里）。"""
        return (self.chamber, self.tunnel)

    def wall_rects(self):
        """碰撞墙（不含门）：左墙 / 顶 / 外墙上段 / 内墙 / 底墙（入口那一列留空）。"""
        out = [self.left_wall, self.roof, self.outer_wall, self.floor]
        out.extend(self._inner_walls)
        return out

    def solid_rects(self):
        """墙 + （门关到一定程度后）入口缺口。给生物 / 物品 / 尸体用。"""
        out = list(self.wall_rects())
        if self.close_fac > 0.5:
            out.append(self.entrance)
        return out

    def cat_solid_rects(self):
        """蛞蝓猫用的实心墙体 —— 与生物 / 物品**完全一致**。

        文档口径：入口处底墙 ``███████      ███████``，猫只能从入口进出，
        不能穿其它三面墙。所以这里不再给猫开地面旁路，直接复用 ``solid_rects()``
        （门关到位后入口那一块也变实心）。
        """
        return self.solid_rects()

    def roof_edge(self):
        """顶边＝单向平台（(x0, y0, x1)）。"""
        return (self.x, self.y, self.x + self.w)

    def door_rect(self):
        return self.entrance

    def entry_x(self):
        """入口内侧那一点（走廊中点，朝里收一点）。"""
        tx0, ty0, tx1, ty1 = self.tunnel
        mid = (tx0 + tx1) * 0.5
        return mid

    def entry_goal(self, radius=26.0):
        return point_goal(self.entry_x(), self.ground_y, radius=radius,
                          contact="body")

    def distance_to(self, px, py):
        r = self.safe_rect()
        dx = max(r[0] - px, 0.0, px - r[2])
        dy = max(r[1] - py, 0.0, py - r[3])
        return (dx * dx + dy * dy) ** 0.5

    # ── 语义 ──
    def contains(self, px, py):
        """在不在"屋里"（内腔任一矩形；脚下两像素容差）。"""
        if px is None or py is None:
            return False
        for x0, y0, x1, y1 in self.interior_rects():
            if x0 - 2.0 <= px <= x1 + 2.0 and y0 - 4.0 <= py <= y1 + 6.0:
                return True
        return False

    def coverage_at(self, px, py):
        """挡雨系数：外面 0 / 屋檐下 0.25 / 里面 1.0。"""
        if px is None or py is None:
            return 0.0
        if self.contains(px, py):
            return 1.0
        m = self.eaves
        if (self.x - m <= px <= self.x + self.w + m
                and py >= self.y - m and py <= self.ground_y + m):
            return 0.25
        return 0.0

    def stand_on_roof(self, px, py):
        return (self.x <= px <= self.x + self.w
                and abs(py - self.y) <= 6.0)

    # ── 门 ──
    @property
    def door_closed(self):
        return self.door_state == CLOSED

    def start_closing(self):
        if self.door_state in (OPEN, OPENING):
            self.door_state = CLOSING

    def start_opening(self):
        if self.door_state in (CLOSED, CLOSING):
            self.door_state = OPENING

    def step(self):
        self.phases.step(self.close_fac)
        if self.door_state == CLOSING:
            self.close_fac = min(1.0, self.close_fac + 1.0 / float(self.door_ticks))
            if self.close_fac >= 1.0:
                self.door_state = CLOSED
        elif self.door_state == OPENING:
            self.close_fac = max(0.0, self.close_fac - 1.0 / float(self.open_ticks))
            if self.close_fac <= 0.0:
                self.door_state = OPEN

    def panel_rects(self):
        """两块门板的当前矩形 (left, right)。开着时缩在门框两侧，关时合成一扇。"""
        dx0, dy0, dx1, dy1 = self.entrance
        pw = (dx1 - dx0) * 0.5
        dcx = (dx0 + dx1) * 0.5
        t = ease(self.close_fac)
        lx = _lerp(dx0 - pw, dcx - pw, t)
        rx = _lerp(dx1, dcx, t)
        return ((lx, dy0, lx + pw, dy1), (rx, dy0, rx + pw, dy1))

    # ── 绘制：拆三层（后墙 / 生物 / 前墙+门） ──
    def draw(self, p):
        """兼容旧接口：整间一次画完（= back + front）。"""
        self.draw_back(p)
        self.draw_front(p)

    def draw_back(self, p):
        """猫身之后：20% 灰底 + **简单黑色边框**（墙体 / 顶 / 内墙）。"""
        from PySide6.QtGui import QColor
        from PySide6.QtCore import QRectF, Qt

        p.setPen(Qt.PenStyle.NoPen)
        # 背景：20% 灰纯色（alpha = 0.2），屋里的猫仍然看得清
        p.setBrush(QColor(128, 128, 128, 51))
        x0, y0, x1, y1 = self.safe_rect()
        p.drawRect(QRectF(x0, y0, self.w, self.h))
        # 只画黑色墙体 —— 入口那块留白，猫从缺口进出
        p.setBrush(QColor(0, 0, 0, 255))
        for (a, b, c, d) in self.wall_rects():
            p.drawRect(QRectF(a, b, c - a, d - b))
        # 门关到一半以上：入口也封成黑的（挡住里面的猫）
        if self.close_fac > 0.5:
            dx0, dy0, dx1, dy1 = self.entrance
            p.drawRect(QRectF(dx0, dy0, dx1 - dx0, dy1 - dy0))

    def draw_front(self, p, atlas=None):
        """猫身前：原版 ShelterGate_* 大门。图集缺失时退回一块纯黑门板。"""
        if atlas is not None:
            from ..rendering import shelter_gate
            if shelter_gate.draw_door(p, atlas, self):
                return
        from PySide6.QtGui import QColor
        from PySide6.QtCore import QRectF, Qt

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 255))
        for (px0, py0, px1, py1) in self.panel_rects():
            if px1 - px0 > 0.5:
                p.drawRect(QRectF(px0, py0, px1 - px0, py1 - py0))

    # ── 存档 ──
    def to_dict(self):
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "ground_y": self.ground_y, "seed": self.seed,
                "door_side": self.door_side, "door_state": self.door_state,
                "door_t": self.close_fac, "door_ticks": self.door_ticks,
                "template": self.template.key}

    def dump_geometry(self):
        """调试/测试用：这间庇护所的真实几何快照。"""
        return {"tile": self.tile, "footprint": self.safe_rect(),
                "chamber": self.chamber, "tunnel": self.tunnel,
                "entrance": self.entrance, "roof": self.roof,
                "floor": self.floor,
                "outer_wall": self.outer_wall, "inner_wall": self.inner_wall,
                "p_zero": self.p_zero, "dir_x": self.dir_x,
                "door_side": self.door_side, "template": self.template.key}


def shelter_from_dict(d, WL, ground_y=None):
    """从存档建回（旧档缺字段一律有默认值）。"""
    if not isinstance(d, dict):
        return None
    h = float(d.get("h", 80.0))
    y = d.get("y")
    if y is None:
        # 更老的档只有 ground_y（底边贴桌面地面）
        y = float(d.get("ground_y", ground_y if ground_y is not None else 0.0)) - h
    try:
        sh = Shelter(float(d.get("x", 0.0)), float(y),
                     float(d.get("w", 140.0)), h,
                     None, WL, seed=int(d.get("seed", 0) or 0),
                     door_ticks=int(d.get("door_ticks", 0) or 0),
                     template=d.get("template") if isinstance(d.get("template"), str) else None)
    except Exception:
        return None
    side = d.get("door_side")
    if side in ("left", "right"):
        sh.door_side = side
        sh._layout()
    st = d.get("door_state")
    if st in (OPEN, CLOSING, CLOSED, OPENING):
        sh.door_state = st
    try:
        sh.close_fac = _clampf(float(d.get("door_t", 0.0)), 0.0, 1.0)
    except Exception:
        sh.close_fac = 0.0
    return sh
