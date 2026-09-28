"""Fruit and stone interaction helpers for ``PetWindow``."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)

from ..core.units import clampf, inv_lerp, lerp
from ..core.gfxmath import _hsl2rgb
from ..control.hotkey import HK_PLACE_ESC, VK_ESCAPE
from .fruit import PLACE_HANGING_FRAC, make_fruit
from ..rendering.graphics import _ang_from_up
from ..rendering.primitives import (blit, draw_fruit, draw_rope, draw_stone,
                                    draw_stone_trail, draw_pearl, draw_spear,
                                    draw_scavenger, draw_scavenger_spear)
from .enums import ItemState
from .slimemold import (SlimeMold, _dirvec as _slime_dir, _lerp_map as _slime_lerp_map,
                        TENDRIL_JAG_K)
from .stone import Stone
from .batfly import BatFly
from .lizard import BREEDS, Lizard, _ang_lerp
from .lizard_gfx import draw_lizard
from .squidcada import Squidcada
from .squidcada_gfx import draw_squidcada
from .pearl import Pearl
from .spear import Spear, LEN as SPEAR_DRAW_LEN, HALF_W as SPEAR_HALF_W
from .scavenger import (Scavenger, BODY_RAD as SCAV_BODY_RAD,
                        STAND_H as SCAV_STAND_H)
from .pole import POLE_RAD, MIN_LENGTH as POLE_MIN_LENGTH, TOP_MARGIN as POLE_TOP_MARGIN
from ..behavior import tuning


STALK_ROOT_W = 3.0
STALK_TIP_W = 2.0
STALK_COLOR = (0, 0, 0)
FRUIT_FLESH = (0, 0, 255)
FRUIT_OUTLINE = (0, 0, 0)
STONE_COLOR = (74, 76, 82)
POLE_COLOR = (28, 28, 31)
# 暖灯颜色
LAMP_STICK_COLOR = (0, 0, 0)
LAMP_BULB_FLESH = (255, 255, 255)
LAMP_BULB_OUTLINE = (255, 51, 0)
LAMP_GLOW_COLOR = (255, 51, 0)
LAMP_GLOW_ALPHA = 130
LAMP_TILT_MAX_DEG = 25.0
LAMP_STICK_OUTSET = 40.0
STONE_STUN_SPEED = 8.0
STONE_STUN_TICKS = 80
LIZARD_STUN_TICKS = 60            # 被蜥蜴咬到的眩晕 tick
STONE_KNOCKBACK = 0.5
STONE_DRAW_SCALE = 0.7
# 抛石拖尾
STONE_TRAIL_MIN_SPEED = 6.0
STONE_TRAIL_LEN_K = 1.6
STONE_TRAIL_LEN_MAX = 42.0
STONE_TRAIL_HALFW = 3.0
STONE_TRAIL_ALPHA = 90
CURSOR_STUN_PAD = 8.0
CURSOR_STUN_LOCK = 80
# 黏菌颜色
SLIME_HUE_LIGHT = 0.07
SLIME_HUE_DARK = 0.05
SLIME_BODY_L = 0.55
SLIME_OUTLINE_L = 0.25
SLIME_DARK_LO = 0.3
SLIME_DARK_HI = 0.7
SLIME_DRAW_SCALE = 1.0
SLIME_LIGHT_SCALE = 55.0 / 140.0    # 下调防过曝
SLIME_BLOOM_SCALE = 12.0 / 30.0
SLIME_RESTICK_PAD = 50.0
# 触须锯齿单位圆表
_JAG_COS = [math.cos(2.0 * math.pi * i / TENDRIL_JAG_K) for i in range(TENDRIL_JAG_K)]
_JAG_SIN = [math.sin(2.0 * math.pi * i / TENDRIL_JAG_K) for i in range(TENDRIL_JAG_K)]
# 蝙蝠
BATFLY_BLACK = (0, 0, 0)
BATFLY_EYE_COLOR = (250, 250, 235)
BATFLY_WING_COLOR = (0, 0, 0, 160)
BATFLY_BODY_HALF_W = 2.7
BATFLY_BODY_HALF_H = 3.3
BATFLY_ABDOMEN_MIN = 4.0
BATFLY_ABDOMEN_MAX = 6.0
BATFLY_WING_LEN = 12.5
BATFLY_WING_W = 6.0
BATFLY_EYE_RAD = 0.5
BATFLY_EYE_DX = 0.92
BATFLY_EYE_DY = 1.35
SHOVE_REACH = 22.0
SHOVE_COOLDOWN = 12

# 蝉乌贼 / 珍珠 / 矛 / 拾荒者
SQUIDCADA_GRAB_PAD = 10.0
PEARL_GRAB_PAD = 6.0
SPEAR_GRAB_PAD = 8.0
SCAVENGER_GRAB_PAD = 14.0
SPEAR_HIT_SPEED = 7.0            # 飞矛扎猫的最低速度
SPEAR_HIT_PAD = 6.0
SPEAR_THROW_SPEED = 11.0         # 拾荒者掷矛初速
SPEAR_THROW_LIFT = 1.5           # 掷出时的上抬
# 翅本地多边形（锚在本体，向 -y 伸展）
_BATFLY_WING_PTS = [
    (0.0, 0.0),
    (BATFLY_WING_W, -BATFLY_WING_LEN * 0.4),
    (BATFLY_WING_W * 0.55, -BATFLY_WING_LEN * 0.85),
    (0.0, -BATFLY_WING_LEN),
    (-BATFLY_WING_W * 0.22, -BATFLY_WING_LEN * 0.45),
]
# 形状/颜色缓存：身路径按 abdomen 量化
_BATFLY_WING_POLY = None
_BATFLY_BODY_PATHS: dict[int, "QPainterPath"] = {}
_BATFLY_BLACK_C = QColor(*BATFLY_BLACK)
_BATFLY_WING_C = QColor(*BATFLY_WING_COLOR)
_BATFLY_EYE_C = QColor(*BATFLY_EYE_COLOR)


def _slime_body_rgb(dm, l):
    """按 darkMode 算橙系 RGB。"""
    hue = lerp(SLIME_HUE_LIGHT, SLIME_HUE_DARK, dm)
    r, g, b = _hsl2rgb(hue, 1.0, l)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def _slime_saturate(rgb):
    """HSV 满饱和，橙发光用。"""
    mn, mx = min(rgb), max(rgb)
    if mx <= mn:
        return (mx, mx, mx)
    k = mx / (mx - mn)
    return tuple(int(round((c - mn) * k)) for c in rgb)


def _slime_colors(dm):
    """橙系三色：body/outline/glow。"""
    body = _slime_body_rgb(dm, SLIME_BODY_L)
    return body, _slime_body_rgb(dm, SLIME_OUTLINE_L), _slime_saturate(body)


def _slerp2(ax, ay, bx, by, t):
    """两单位向量球面插值。"""
    dot = clampf(ax * bx + ay * by, -1.0, 1.0)
    if dot > 0.9995:                                   # 近平行退化
        return (ax + (bx - ax) * t, ay + (by - ay) * t)
    theta = math.acos(dot)
    s = math.sin(theta)
    return (ax * math.sin((1.0 - t) * theta) / s + bx * math.sin(t * theta) / s,
            ay * math.sin((1.0 - t) * theta) / s + by * math.sin(t * theta) / s)


def _dist_to_path(pts, x, y):
    """点到折线的最短距离（蜥蜴抓取判定用）。"""
    best = 1e9
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 <= 1e-9 else clampf(((x - ax) * dx + (y - ay) * dy) / L2, 0.0, 1.0)
        d = math.hypot(x - (ax + dx * t), y - (ay + dy * t))
        if d < best:
            best = d
    return best


class ItemInteractionMixin:
    # 个数上限已全部取消，can_place_* 恒真（保留接口供 UI 调用）
    _FRUIT_GRAB_PAD = 7.0
    _FRUIT_FLING_CAP = 14.0
    _STONE_GRAB_PAD = 7.0
    _STONE_FLING_CAP = 14.0
    _SLIME_GRAB_PAD = 7.0
    _SLIME_FLING_CAP = 14.0
    _BATFLY_GRAB_PAD = 7.0
    _BATFLY_FLING_CAP = 14.0
    _LIZARD_GRAB_PAD = 10.0
    _LIZARD_FLING_CAP = 14.0
    _PEARL_FLING_CAP = 16.0
    _SPEAR_FLING_CAP = 18.0

    def can_place_fruit(self) -> bool:
        return True

    def place_fruit(self, lx, ly):
        if not self.can_place_fruit():
            return None
        f = make_fruit(lx, ly, self._HL, seed=self._fruit_seed, zerog=self.zerog_on)
        self._fruit_seed += 1
        self.fruits.append(f)
        self.world_version += 1
        self._exit_place_mode()
        return f

    def clear_fruits(self):
        for f in self.fruits:
            f.stalk = None
            if f.state == ItemState.CARRIED:
                f.held_by_hand = None
            for pet in self.pets:
                if f is pet.body.carried_fruit:
                    pet.body.release_fruit()
            f.state = ItemState.EATEN
        if self.fruits:
            self.fruits = []
            self.world_version += 1
        self._dragged_fruit = None
        self._drag_last = None
        self._exit_place_mode()

    def _fruit_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for f in self.fruits:
            if f.state not in (ItemState.FREE, ItemState.HANGING):
                continue
            d = math.hypot(cx - f.x, cy - f.y)
            if d <= f.rad + self._FRUIT_GRAB_PAD and d < bestd:
                best, bestd = f, d
        return best

    def _begin_fruit_drag(self, pos) -> bool:
        f = self._fruit_at(pos)
        if f is None:
            return False
        f.stalk = None
        f.held_by_hand = None
        f.state = ItemState.MOUSE
        f.vx = f.vy = 0.0
        f.last_x, f.last_y = pos
        f.x, f.y = pos
        self._dragged_fruit = f
        self._drag_last = tuple(pos)
        return True

    def _step_fruit_drag(self):
        f = self._dragged_fruit
        if f is None:
            return
        if f.state != ItemState.MOUSE:
            self._dragged_fruit = None
            self._drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        f.last_x, f.last_y = f.x, f.y
        if self._drag_last is not None:
            f.vx = cur[0] - self._drag_last[0]
            f.vy = cur[1] - self._drag_last[1]
        f.x, f.y = cur
        self._drag_last = tuple(cur)

    def _end_fruit_drag(self):
        f = self._dragged_fruit
        if f is None:
            return False
        sp = math.hypot(f.vx, f.vy)
        if sp > self._FRUIT_FLING_CAP:
            k = self._FRUIT_FLING_CAP / sp
            f.vx *= k
            f.vy *= k
        if f.state == ItemState.MOUSE:
            f.state = ItemState.FREE
        self._dragged_fruit = None
        self._drag_last = None
        return True

    def can_place_stone(self) -> bool:
        return True

    def place_stone(self, lx, ly):
        if not self.can_place_stone():
            return None
        s = Stone(lx, ly, seed=self._stone_seed)
        self._stone_seed += 1
        self.stones.append(s)
        self.world_version += 1
        self._exit_place_mode()
        return s

    def clear_stones(self):
        for s in self.stones:
            for pet in self.pets:
                if s is getattr(pet.body, "carried_stone", None):
                    rs = getattr(pet.body, "release_stone", None)
                    if rs is not None:
                        rs()
            s.state = ItemState.GONE
        if self.stones:
            self.stones = []
            self.world_version += 1
        self._dragged_stone = None
        self._stone_drag_last = None
        self._exit_place_mode()

    def enter_place_stone_mode(self):
        if not self.can_place_stone():
            return False
        self._place_mode = True
        self._place_kind = "stone"
        self._begin_place_capture()
        return True

    def _stone_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for s in self.stones:
            if s.state != ItemState.FREE:
                continue
            d = math.hypot(cx - s.x, cy - s.y)
            if d <= s.rad + self._STONE_GRAB_PAD and d < bestd:
                best, bestd = s, d
        return best

    def _begin_stone_drag(self, pos) -> bool:
        f = self._stone_at(pos)
        if f is None:
            return False
        f.unfetchable = False
        f.fetch_fails = 0
        f.fling = False
        f.state = ItemState.MOUSE
        f.vx = f.vy = 0.0
        f.last_x, f.last_y = pos
        f.x, f.y = pos
        self._dragged_stone = f
        self._stone_drag_last = tuple(pos)
        return True

    def _step_stone_drag(self):
        f = self._dragged_stone
        if f is None:
            return
        if f.state != ItemState.MOUSE:
            self._dragged_stone = None
            self._stone_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        f.last_x, f.last_y = f.x, f.y
        if self._stone_drag_last is not None:
            f.vx = cur[0] - self._stone_drag_last[0]
            f.vy = cur[1] - self._stone_drag_last[1]
        f.x, f.y = cur
        self._stone_drag_last = tuple(cur)

    def _end_stone_drag(self):
        f = self._dragged_stone
        if f is None:
            return False
        sp = math.hypot(f.vx, f.vy)
        if sp > self._STONE_FLING_CAP:
            k = self._STONE_FLING_CAP / sp
            f.vx *= k
            f.vy *= k
        if f.state == ItemState.MOUSE:
            f.state = ItemState.FREE
            f.fling = True
            f.spin = clampf(f.vx * 2.0, -40.0, 40.0) * lerp(0.05, 1.0, f.room_gravity)
        self._dragged_stone = None
        self._stone_drag_last = None
        return True

    def _step_stone_hit(self):
        for pet in self.pets:
            if pet.behavior is None:
                continue
            b = pet.body
            for s in self.stones:
                if not s.fling or s.state != ItemState.FREE:
                    continue
                sp = math.hypot(s.vx, s.vy)
                if sp < STONE_STUN_SPEED:
                    continue
                for c in (b.chunk0, b.chunk1):
                    if math.hypot(s.x - c.x, s.y - c.y) < s.rad + c.rad:
                        if pet.behavior.apply_stun(STONE_STUN_TICKS):
                            c.vx += s.vx * STONE_KNOCKBACK
                            c.vy += s.vy * STONE_KNOCKBACK
                            s.deflect(self._stun_rng)
                            s.fling = False
                        break

    def _step_stone_cursor_hit(self):
        if self.cursor_hijack is not None or self.behavior is None:
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        for s in self.stones:
            if not s.thrown_by_saint or s.state != ItemState.FREE:
                continue
            if math.hypot(s.x - cx, s.y - cy) < s.rad + CURSOR_STUN_PAD:
                self.start_cursor_hijack(cx, cy, lock_ticks=CURSOR_STUN_LOCK)
                s.deflect(self._stun_rng)
                s.thrown_by_saint = False
                break

    # ── 杆子 ──
    def can_place_pole(self, kind) -> bool:
        return True

    def place_pole(self, lx, ly, place_kind):
        from .pole import Pole, VERTICAL, HORIZONTAL, MIN_LENGTH, TOP_MARGIN
        kind = VERTICAL if place_kind == "vpole" else HORIZONTAL
        if not self.can_place_pole(kind):
            return None
        if kind == VERTICAL:
            top = min(max(ly, TOP_MARGIN), self._HL - MIN_LENGTH)
            pl = Pole(VERTICAL, lx, self._HL, lx, top, seed=self._pole_seed)
        else:
            ax = 0.0 if lx < self._WL * 0.5 else self._WL
            end = lx
            if abs(end - ax) < MIN_LENGTH:
                end = ax + (MIN_LENGTH if ax == 0.0 else -MIN_LENGTH)
            pl = Pole(HORIZONTAL, ax, ly, end, ly, seed=self._pole_seed)
        self._pole_seed += 1
        self.poles.append(pl)
        self.world_version += 1
        self.geometry_version += 1
        self._exit_place_mode()
        self.update()
        return pl

    def clear_poles(self):
        from .enums import ItemState as _IS
        for pl in self.poles:
            pl.state = _IS.GONE
        if self.poles:
            self.poles = []
            self.world_version += 1
            self.geometry_version += 1
        self._exit_place_mode()
        self.update()

    def clear_all_items(self):
        """清除所有可交互实体。"""
        self.clear_fruits()
        self.clear_stones()
        self.clear_slimemolds()
        self.clear_batflies()
        self.clear_lizards()
        self.clear_squidcadas()
        self.clear_pearls()
        self.clear_spears()
        self.clear_scavengers()
        self.clear_poles()
        self.clear_lamp()

    def enter_place_vpole_mode(self):
        return self._enter_place_pole_mode("vpole", "vertical")

    def enter_place_hpole_mode(self):
        return self._enter_place_pole_mode("hpole", "horizontal")

    def _enter_place_pole_mode(self, place_kind, pole_kind):
        if not self.can_place_pole(pole_kind):
            return False
        self._place_mode = True
        self._place_kind = place_kind
        self._begin_place_capture()
        return True

    def _draw_poles(self, p):
        p.save()
        for pl in self.poles:
            if getattr(pl, "mimic", None) is not None:
                continue
            self._draw_pole_rod(p, pl.ax, pl.ay, pl.bx, pl.by, POLE_RAD)
        p.restore()

    def _draw_pole_rod(self, p, ax, ay, bx, by, rad):
        """单层均一色杆体，无描边。"""
        core = QPen(QColor(*POLE_COLOR))
        core.setWidthF(rad * 2.0)
        core.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(core)
        p.drawLine(QPointF(ax, ay), QPointF(bx, by))

    def _draw_pole_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        if self._place_kind == "vpole":
            top = min(max(cy, POLE_TOP_MARGIN), self._HL - POLE_MIN_LENGTH)
            a = QPointF(cx, self._HL)
            b = QPointF(cx, top)
        else:
            ax = 0.0 if cx < self._WL * 0.5 else self._WL
            end = cx
            if abs(end - ax) < POLE_MIN_LENGTH:
                end = ax + (POLE_MIN_LENGTH if ax == 0.0 else -POLE_MIN_LENGTH)
            a = QPointF(ax, cy)
            b = QPointF(end, cy)
        p.save()
        p.setOpacity(0.5)
        self._draw_pole_rod(p, a.x(), a.y(), b.x(), b.y(), POLE_RAD)
        p.restore()

    # ── 暖灯 ──
    def _lamp_geom(self, lx, ly):
        """点击点 → 最近边算锚点/灯泡位置/边名。"""
        d = {"top": ly, "bottom": self._HL - ly, "left": lx, "right": self._WL - lx}
        edge = min(d, key=d.get)
        perp = d[edge]                                      # 垂距
        off = perp * math.tan(math.radians(getattr(self, "_lamp_tilt", 0.0)))
        if edge == "top":
            ax, ay = clampf(lx + off, 0.0, self._WL), 0.0
        elif edge == "bottom":
            ax, ay = clampf(lx + off, 0.0, self._WL), self._HL
        elif edge == "left":
            ax, ay = 0.0, clampf(ly + off, 0.0, self._HL)
        else:
            ax, ay = self._WL, clampf(ly + off, 0.0, self._HL)
        vx, vy = ax - lx, ay - ly
        vlen = math.hypot(vx, vy) or 1.0
        ax += vx / vlen * LAMP_STICK_OUTSET
        ay += vy / vlen * LAMP_STICK_OUTSET
        return ax, ay, lx, ly, edge

    def place_lamp(self, lx, ly):
        from .lamp import Lamp
        ax, ay, bx, by, edge = self._lamp_geom(lx, ly)
        if self.lamp is not None:
            self.lamp.state = ItemState.GONE
        self.lamp = Lamp(ax, ay, bx, by, edge, seed=self._lamp_seed)
        self._lamp_seed += 1
        self.world_version += 1
        self.geometry_version += 1
        self._exit_place_mode()
        self.update()
        return self.lamp

    def clear_lamp(self):
        if self.lamp is not None:
            self.lamp.state = ItemState.GONE
            self.lamp = None
            self.world_version += 1
            self.geometry_version += 1
        self._exit_place_mode()
        self.update()

    def enter_place_lamp_mode(self):
        self._place_mode = True
        self._place_kind = "lamp"
        self._lamp_tilt = random.uniform(-LAMP_TILT_MAX_DEG, LAMP_TILT_MAX_DEG)
        self._begin_place_capture()
        return True

    def _draw_lamp_shape(self, p, ax, ay, bx, by, opacity, glow_radius=None):
        """串杆+灯泡+可选暖光。"""
        p.save()
        if opacity < 1.0:
            p.setOpacity(opacity)
        dx, dy = bx - ax, by - ay
        seg_len = math.hypot(dx, dy)
        bulb_rot = 0.0
        if seg_len > 1.0:
            ux, uy = dx / seg_len, dy / seg_len
            root_w = 1.0 + min(seg_len / 190.0, 3.0)
            sx, sy = ax + ux * 5.0, ay + uy * 5.0
            tx, ty = bx + ux * 25.0, by + uy * 25.0
            n = 8
            pts = [(sx + (tx - sx) * i / (n - 1), sy + (ty - sy) * i / (n - 1))
                   for i in range(n)]
            widths = [2.0 * (root_w + (0.5 - root_w) * (i / (n - 1))) for i in range(n)]
            draw_rope(p, pts, widths, color=LAMP_STICK_COLOR)
            bulb_rot = math.degrees(math.atan2(ax - bx, by - ay))
        draw_fruit(p, self.atlas, bx, by, bulb_rot, 3,
                   flesh_color=LAMP_BULB_FLESH, outline_color=LAMP_BULB_OUTLINE,
                   scalex=0.8, scaley=0.9)
        if glow_radius and glow_radius > 1.0:
            grad = QRadialGradient(QPointF(bx, by), glow_radius)
            grad.setColorAt(0.0, QColor(*LAMP_GLOW_COLOR, LAMP_GLOW_ALPHA))
            grad.setColorAt(1.0, QColor(*LAMP_GLOW_COLOR, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(bx, by), glow_radius, glow_radius)
        p.restore()

    def _draw_lamp(self, p):
        lamp = self.lamp
        if lamp is None:
            return
        self._draw_lamp_shape(p, lamp.anchor_x, lamp.anchor_y, lamp.bulb_x, lamp.bulb_y,
                              1.0, glow_radius=lamp.glow_radius())

    def _draw_lamp_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        ax, ay, bx, by, _ = self._lamp_geom(cx, cy)
        self._draw_lamp_shape(p, ax, ay, bx, by, 0.5, glow_radius=None)

    # ── 黏菌 ──
    def can_place_slimemold(self) -> bool:
        return True

    def _slime_edge_anchor(self, lx, ly):
        """点击点 → 最近边锚点+本体位。"""
        d = {"top": ly, "bottom": self._HL - ly, "left": lx, "right": self._WL - lx}
        edge = min(d, key=d.get)
        if edge == "top":
            sx, sy, nx, ny = clampf(lx, 0.0, self._WL), 0.0, 0.0, 1.0
        elif edge == "bottom":
            sx, sy, nx, ny = clampf(lx, 0.0, self._WL), self._HL, 0.0, -1.0
        elif edge == "left":
            sx, sy, nx, ny = 0.0, clampf(ly, 0.0, self._HL), 1.0, 0.0
        else:
            sx, sy, nx, ny = self._WL, clampf(ly, 0.0, self._HL), -1.0, 0.0
        from .slimemold import STUCK_GAP
        return sx, sy, sx + nx * STUCK_GAP, sy + ny * STUCK_GAP

    def place_slimemold(self, lx, ly):
        if not self.can_place_slimemold():
            return None
        sx, sy, bx, by = self._slime_edge_anchor(lx, ly)
        m = SlimeMold(bx, by, seed=self._slimemold_seed)
        m.stick_to(sx, sy)
        self._slimemold_seed += 1
        self.slimemolds.append(m)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return m

    def clear_slimemolds(self):
        for m in self.slimemolds:
            for pet in self.pets:
                if m is pet.body.carried_fruit:      # 复用果子叼持槽
                    pet.body.release_fruit()
            m.state = ItemState.EATEN
        if self.slimemolds:
            self.slimemolds = []
            self.world_version += 1
        self._dragged_slimemold = None
        self._slime_drag_last = None
        self._exit_place_mode()

    def enter_place_slimemold_mode(self):
        if not self.can_place_slimemold():
            return False
        self._place_mode = True
        self._place_kind = "slimemold"
        self._slime_preview = SlimeMold(0.0, 0.0, seed=self._slimemold_seed)   # 预览用真实实例
        self._begin_place_capture()
        return True

    def _slimemold_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for m in self.slimemolds:
            if m.state not in (ItemState.FREE, ItemState.HANGING):
                continue
            d = math.hypot(cx - m.x, cy - m.y)
            if d <= m.rad + self._SLIME_GRAB_PAD and d < bestd:
                best, bestd = m, d
        return best

    def _begin_slimemold_drag(self, pos) -> bool:
        m = self._slimemold_at(pos)
        if m is None:
            return False
        m.stuck_pos = None
        m.held_by_hand = None
        m.state = ItemState.MOUSE
        m.vx = m.vy = 0.0
        m.last_x, m.last_y = pos
        m.x, m.y = pos                       # 触须由 step 弹簧跟随
        self._dragged_slimemold = m
        self._slime_drag_last = tuple(pos)
        return True

    def _step_slimemold_drag(self):
        m = self._dragged_slimemold
        if m is None:
            return
        if m.state != ItemState.MOUSE:
            self._dragged_slimemold = None
            self._slime_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        m.last_x, m.last_y = m.x, m.y
        if self._slime_drag_last is not None:
            m.vx = cur[0] - self._slime_drag_last[0]
            m.vy = cur[1] - self._slime_drag_last[1]
        m.x, m.y = cur                        # 触须由 step 弹簧跟随
        self._slime_drag_last = tuple(cur)

    def _end_slimemold_drag(self):
        m = self._dragged_slimemold
        if m is None:
            return False
        sp = math.hypot(m.vx, m.vy)
        if sp > self._SLIME_FLING_CAP:
            k = self._SLIME_FLING_CAP / sp
            m.vx *= k
            m.vy *= k
        if m.state == ItemState.MOUSE:
            # 够近重粘边，否则落地
            d = {"top": m.y, "left": m.x, "right": self._WL - m.x}
            edge = min(d, key=d.get)
            if d[edge] <= SLIME_RESTICK_PAD:
                sx, sy, _, _ = self._slime_edge_anchor(m.x, m.y)
                m.vx = m.vy = 0.0
                m.stick_to(sx, sy)
            else:
                m.state = ItemState.FREE
        self._dragged_slimemold = None
        self._slime_drag_last = None
        return True

    def _draw_slimemolds(self, p):
        dm = clampf(inv_lerp(SLIME_DARK_LO, SLIME_DARK_HI,
                             getattr(self, "cold_cycle_prog", 0.0)), 0.0, 1.0)
        for m in self.slimemolds:
            self._draw_one_slimemold(p, m, dm)

    def _draw_one_slimemold(self, p, m, dm):
        """单坨黏菌绘制，正式/预览共用。"""
        ts = self._ts
        atlas = self.atlas
        body, outline, glow = _slime_colors(dm)
        x = m.last_x + (m.x - m.last_x) * ts
        y = m.last_y + (m.y - m.last_y) * ts
        vx, vy = _slerp2(m.last_rotation[0], m.last_rotation[1],
                         m.rotation[0], m.rotation[1], ts)
        rot_deg = _ang_from_up(vx, vy) + 180.0
        draw_fruit(p, atlas, x, y, rot_deg, m.bites,
                   flesh_color=body, outline_color=outline,
                   scalex=SLIME_DRAW_SCALE, scaley=SLIME_DRAW_SCALE * 0.85)
        # EATEN 外都画触须
        if m.state != ItemState.EATEN:
            self._draw_slime_tendrils(p, m, body)
        # 高光
        hox = (-2.0 * (1.0 - dm) + vx * (1.0 + dm)) * SLIME_DRAW_SCALE
        hoy = (-2.0 * (1.0 - dm) + vy * (1.0 + dm)) * SLIME_DRAW_SCALE
        hl_t = lerp(0.5, 0.2, dm)
        hlc = (int(lerp(body[0], 255, hl_t)),
               int(lerp(body[1], 255, hl_t)),
               int(lerp(body[2], 255, hl_t)))
        hsx = _slime_lerp_map(m.bites, 3.0, 1.0, 0.25, 0.15) * SLIME_DRAW_SCALE
        hsy = _slime_lerp_map(m.bites, 3.0, 1.0, 0.30, 0.05) * SLIME_DRAW_SCALE
        if atlas.find_atlas("Circle20") is not None:
            blit(p, atlas, "Circle20", x + hox, y + hoy, rot_deg, hsx, hsy, hlc)
        else:
            p.save(); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(*hlc))
            p.translate(x + hox, y + hoy); p.rotate(rot_deg)
            p.scale(hsx * 20.0, hsy * 20.0)
            p.drawEllipse(QPointF(0.0, 0.0), 0.5, 0.5); p.restore()
        # 暗场发光
        if dm > 0.0:
            light_r = _slime_lerp_map(m.bites, 3.0, 1.0, 140.0, 40.0) * SLIME_LIGHT_SCALE
            bloom_r = _slime_lerp_map(m.bites, 3.0, 1.0, 30.0, 10.0) * SLIME_BLOOM_SCALE
            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.setPen(Qt.PenStyle.NoPen)
            for gr, ga in ((light_r, 0.12 * dm), (bloom_r, 0.25 * dm)):
                grad = QRadialGradient(QPointF(x, y), gr)
                a = int(clampf(ga, 0.0, 1.0) * 255)
                c0 = QColor(*glow); c0.setAlpha(a)
                cm = QColor(*glow); cm.setAlpha(a)          # 0.35 前不淡出，更柔
                c1 = QColor(*glow); c1.setAlpha(0)
                grad.setColorAt(0.0, c0); grad.setColorAt(0.35, cm); grad.setColorAt(1.0, c1)
                p.setBrush(QBrush(grad))
                p.drawEllipse(QPointF(x, y), gr, gr)
            p.restore()

    def _draw_slime_tendrils(self, p, m, body):
        """逐根触须画锯齿团；alpha 值当形状种子，非透明度。"""
        ts = self._ts
        T = m.tendrils
        n = len(T)
        polys = m._tendril_polys
        if polys is None:    # 首绘建缓存
            polys = [QPolygonF([QPointF(0.5 * jf[k] * _JAG_COS[k], 0.5 * jf[k] * _JAG_SIN[k])
                                for k in range(TENDRIL_JAG_K)])
                     for jf in m.tendril_jag]
            m._tendril_polys = polys
        bx = m.last_x + (m.x - m.last_x) * ts
        by = m.last_y + (m.y - m.last_y) * ts
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(*body)))
        for idx, t in enumerate(T):
            tx = t[2] + (t[0] - t[2]) * ts
            ty = t[3] + (t[1] - t[3]) * ts
            link = int(t[6])
            if link < 0 or link >= n:
                ax, ay = bx, by
            else:
                pt = T[link]
                ax = pt[2] + (pt[0] - pt[2]) * ts
                ay = pt[3] + (pt[1] - pt[3]) * ts
            dist = math.hypot(ax - tx, ay - ty)
            length = dist + 3.0
            width = lerp(4.0, 1.5, inv_lerp(0.0, t[7] * 3.5, dist) ** 2)
            rot = _ang_from_up(ax - tx, ay - ty)             # 触须→锚点角
            p.save()
            p.translate(tx, ty)
            if rot:
                p.rotate(rot)
            p.translate(0.0, -0.45 * length)                 # anchorY=0.05
            p.scale(width, length)
            p.drawPolygon(polys[idx])
            p.restore()
        p.restore()

    def _draw_slime_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        m = getattr(self, "_slime_preview", None)
        if m is None:
            return
        sx, sy, bx, by = self._slime_edge_anchor(cx, cy)
        m.x, m.y = bx, by
        if m.stuck_pos is None:                  # 首帧钉锚
            m.stick_to(sx, sy)
        else:                                    # 后续弹簧跟随
            m.stuck_pos = (sx, sy)
            ux, uy = _slime_dir(bx, by, sx, sy)
            m.rotation = (-ux, -uy)
        m.step(self._WL, self._HL)               # 手动推进触须
        dm = clampf(inv_lerp(SLIME_DARK_LO, SLIME_DARK_HI,
                             getattr(self, "cold_cycle_prog", 0.0)), 0.0, 1.0)
        p.save()
        p.setOpacity(0.5)
        self._draw_one_slimemold(p, m, dm)
        p.restore()

    # ── 蝙蝠 ──
    def can_place_batfly(self) -> bool:
        return True

    def place_batfly(self, lx, ly):
        if not self.can_place_batfly():
            return None
        b = BatFly(lx, ly, seed=self._batfly_seed)
        self._batfly_seed += 1
        self.batflies.append(b)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return b

    def clear_batflies(self):
        for b in self.batflies:
            b.stalk = None
            if b.state == ItemState.CARRIED:
                b.held_by_hand = None
            for pet in self.pets:
                if b is pet.body.carried_fruit:      # 复用果子叼持槽
                    pet.body.release_fruit()
            b.state = ItemState.EATEN
        if self.batflies:
            self.batflies = []
            self.world_version += 1
        self._dragged_batfly = None
        self._batfly_drag_last = None
        self._batfly_shove_cd = {}
        self._exit_place_mode()

    def enter_place_batfly_mode(self):
        if not self.can_place_batfly():
            return False
        self._place_mode = True
        self._place_kind = "batfly"
        self._begin_place_capture()
        return True

    def _batfly_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for b in self.batflies:
            if b.state != ItemState.FREE:
                continue
            d = math.hypot(cx - b.x, cy - b.y)
            if d <= b.rad + self._BATFLY_GRAB_PAD and d < bestd:
                best, bestd = b, d
        return best

    def _begin_batfly_drag(self, pos) -> bool:
        b = self._batfly_at(pos)
        if b is None:
            return False
        b.stalk = None
        b.held_by_hand = None
        b.state = ItemState.MOUSE
        b.vx = b.vy = 0.0
        b.last_x, b.last_y = pos
        b.x, b.y = pos
        self._dragged_batfly = b
        self._batfly_drag_last = tuple(pos)
        return True

    def _step_batfly_drag(self):
        b = self._dragged_batfly
        if b is None:
            return
        if b.state != ItemState.MOUSE:
            self._dragged_batfly = None
            self._batfly_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        b.last_x, b.last_y = b.x, b.y
        if self._batfly_drag_last is not None:
            b.vx = cur[0] - self._batfly_drag_last[0]
            b.vy = cur[1] - self._batfly_drag_last[1]
        b.x, b.y = cur
        self._batfly_drag_last = tuple(cur)

    def _end_batfly_drag(self):
        b = self._dragged_batfly
        if b is None:
            return False
        sp = math.hypot(b.vx, b.vy)
        if sp > self._BATFLY_FLING_CAP:
            k = self._BATFLY_FLING_CAP / sp
            b.vx *= k
            b.vy *= k
        if b.state == ItemState.MOUSE:
            b.state = ItemState.FREE          # 不粘边，直接 FREE
        self._dragged_batfly = None
        self._batfly_drag_last = None
        return True

    def _step_batfly_shove(self):
        """手动塞蝙蝠进嘴，逐口咬。"""
        cd = getattr(self, "_batfly_shove_cd", None)
        if cd is None:
            cd = self._batfly_shove_cd = {}
        for k in list(cd):
            cd[k] -= 1
            if cd[k] <= 0:
                del cd[k]
        for b in self.batflies:
            key = id(b)
            if b.state != ItemState.MOUSE or b.eaten > 0:
                cd.pop(key, None)             # __slots__ 无法挂属性，用 id 字典
                continue
            if key in cd:
                continue
            for pet in self.pets:
                if pet.behavior is None:
                    continue
                mx, my = pet.gfx.mouth_world()
                if math.hypot(b.x - mx, b.y - my) < SHOVE_REACH:
                    if b.bite():
                        pet.body.food_eat(1)
                        pet.body.temper_shift(tuning.TEMPER_FEED)
                        pet.body.energy_change(tuning.EN_EAT_RESTORE)
                    cd[key] = SHOVE_COOLDOWN
                    break

    def _draw_batflies(self, p):
        ts = self._ts
        self._batfly_vibe = getattr(self, "_batfly_vibe", 0) + 1
        for b in self.batflies:
            if b.state in (ItemState.EATEN, ItemState.GONE):
                continue
            self._draw_one_batfly(p, b, ts)

    def _draw_one_batfly(self, p, bat, ts):
        """单只蝙蝠绘制，被吃期抽搐。"""
        x = bat.last_x + (bat.x - bat.last_x) * ts
        y = bat.last_y + (bat.y - bat.last_y) * ts
        lx = bat.last_lower_x + (bat.lower_x - bat.last_lower_x) * ts
        ly = bat.last_lower_y + (bat.lower_y - bat.last_lower_y) * ts
        if bat.eaten > 0:                             # 仅被吃倒计时抖动
            vf = self._batfly_vibe + (id(bat) & 0x3F)
            ox, oy = (vf % 3) - 1.0, ((vf // 2) % 3) - 1.0
            x += ox; y += oy; lx += ox; ly += oy
        body_ang = _ang_from_up(x - lx, y - ly)
        abdomen = clampf(math.hypot(x - lx, y - ly),
                         BATFLY_ABDOMEN_MIN, BATFLY_ABDOMEN_MAX)
        flap_depth = bat.last_flap_depth + (bat.flap_depth - bat.last_flap_depth) * ts
        steer = lerp(bat.last_steer, bat.steer, ts)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(2):
            if (i == 0 and bat.bites != 3) or (i == 1 and bat.bites <= 1):
                continue                              # bites: 3两翅 2一翅 1无翅
            wcur = lerp(bat.wings[i][1], bat.wings[i][0], ts)
            a = lerp(wcur, 0.5, lerp(0.3, 0.0, flap_depth))
            steer_fold = 0.0 if (steer < 0.0) == (i == 0) else clampf(abs(steer * 0.85) - 0.1, 0.0, 1.0)
            a = lerp(a, 0.5, steer_fold)
            a = inv_lerp(0.01, 0.99, a * a)
            # 折角压缩到 40~145°，防读作垂臂
            wing_ang = (-1.0 if i == 0 else 1.0) * (40.0 + 105.0 * a) + body_ang
            sx = 1.0 if bat.flap_speed < 0.0 else 1.0 - 0.6 * math.sin(wcur * math.pi) * (1.0 - steer_fold)
            sx *= (-1.0 if i == 0 else 1.0)
            self._draw_batfly_wing(p, x, y, wing_ang, sx)
        self._draw_batfly_body(p, x, y, body_ang, abdomen)
        self._draw_batfly_eyes(p, x, y, body_ang)
        p.restore()

    def _draw_batfly_body(self, p, x, y, ang, abdomen):
        """连续水滴身绘制。"""
        q = int(round(abdomen * 8.0))         # 1/8px 量化，路径按档缓存
        path = _BATFLY_BODY_PATHS.get(q)
        if path is None:
            hw = BATFLY_BODY_HALF_W
            yh = -BATFLY_BODY_HALF_H              # 头端
            ym = -BATFLY_BODY_HALF_H * 0.3        # 最宽处
            yt = q / 8.0                          # 腹尖
            path = QPainterPath()
            path.moveTo(0.0, yh)
            # 头圆→最宽→软尖→最宽→头圆，四段贝塞尔
            path.cubicTo(hw * 1.05, yh + (ym - yh) * 0.2, hw, ym - 0.5, hw, ym)
            path.cubicTo(hw, ym + (yt - ym) * 0.6, hw * 0.45, yt - 1.0, 0.0, yt)
            path.cubicTo(-hw * 0.45, yt - 1.0, -hw, ym + (yt - ym) * 0.6, -hw, ym)
            path.cubicTo(-hw, ym - 0.5, -hw * 1.05, yh + (ym - yh) * 0.2, 0.0, yh)
            path.closeSubpath()
            _BATFLY_BODY_PATHS[q] = path
        p.save()
        p.translate(x, y)
        if ang:
            p.rotate(ang)
        p.setBrush(_BATFLY_BLACK_C)
        p.drawPath(path)
        p.restore()

    def _draw_batfly_wing(self, p, x, y, ang, sx):
        global _BATFLY_WING_POLY
        if _BATFLY_WING_POLY is None:
            _BATFLY_WING_POLY = QPolygonF([QPointF(px, py) for px, py in _BATFLY_WING_PTS])
        p.save()
        p.translate(x, y)
        if ang:
            p.rotate(ang)
        p.scale(sx, 1.0)
        p.setBrush(_BATFLY_WING_C)
        p.drawPolygon(_BATFLY_WING_POLY)
        p.restore()

    def _draw_batfly_eyes(self, p, x, y, ang):
        p.save()
        p.translate(x, y)
        if ang:
            p.rotate(ang)
        p.setBrush(_BATFLY_EYE_C)
        p.drawEllipse(QPointF(-BATFLY_EYE_DX, -BATFLY_EYE_DY), BATFLY_EYE_RAD, BATFLY_EYE_RAD)
        p.drawEllipse(QPointF(BATFLY_EYE_DX, -BATFLY_EYE_DY), BATFLY_EYE_RAD, BATFLY_EYE_RAD)
        p.restore()

    def _draw_batfly_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        from PySide6.QtGui import QPainter
        p.save()
        p.setOpacity(0.5)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        self._draw_batfly_wing(p, cx, cy, -115.0, -0.9)
        self._draw_batfly_wing(p, cx, cy, 115.0, 0.9)
        self._draw_batfly_body(p, cx, cy, 0.0, 10.0)
        self._draw_batfly_eyes(p, cx, cy, 0.0)
        p.restore()

    # ── 蜥蜴 ──
    def can_place_lizard(self) -> bool:
        return True

    def place_lizard(self, lx, ly):
        """放下一只蜥蜴；品种按放置次序轮换，保证九种都见得到。"""
        if not self.can_place_lizard():
            return None
        seed = self._lizard_seed
        lz = Lizard(lx, ly, BREEDS[seed % len(BREEDS)], seed=seed, id=seed)
        self._lizard_seed += 1
        self.lizards.append(lz)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return lz

    def clear_lizards(self):
        for lz in self.lizards:
            lz.die()
        if self.lizards:
            self.lizards = []
            self.world_version += 1
        self._dragged_lizard = None
        self._lizard_preview = None
        self._exit_place_mode()
        self.update()

    def enter_place_lizard_mode(self):
        if not self.can_place_lizard():
            return False
        self._place_mode = True
        self._place_kind = "lizard"
        self._begin_place_capture()
        return True

    def _lizard_at(self, pos):
        """命中测试：到脊柱折线的距离 ≤ 躯干半径 + pad。"""
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for lz in self.lizards:
            if lz.state != ItemState.FREE:
                continue
            d = _dist_to_path(lz.body_path(), cx, cy) - lz.body_rad
            if d <= self._LIZARD_GRAB_PAD and d < bestd:
                best, bestd = lz, d
        return best

    def _begin_lizard_drag(self, pos) -> bool:
        lz = self._lizard_at(pos)
        if lz is None:
            return False
        lz.grab(pos)
        lz.last_x, lz.last_y = pos
        lz.x, lz.y = pos
        self._dragged_lizard = lz
        return True

    def _step_lizard_drag(self):
        """手里的蜥蜴由 Lizard._step_held 跟随光标；这里只清失效引用。"""
        lz = self._dragged_lizard
        if lz is not None and lz.state != ItemState.MOUSE:
            self._dragged_lizard = None

    def _end_lizard_drag(self) -> bool:
        lz = self._dragged_lizard
        if lz is None:
            return False
        sp = math.hypot(lz.vx, lz.vy)
        if sp > self._LIZARD_FLING_CAP:
            k = self._LIZARD_FLING_CAP / sp
            lz.vx *= k
            lz.vy *= k
        lz.release(lz.vx, lz.vy)
        self._dragged_lizard = None
        return True

    def _step_lizards(self):
        """推进所有蜥蜴：物理/AI + 咬到猫结算。"""
        self._step_lizard_drag()
        if not self.lizards:
            return
        cur = self.cursor_logical()
        targets = [(pet, pet.body.chunk0.x, pet.body.chunk0.y)
                   for pet in self.pets if pet.behavior is not None]
        for lz in self.lizards:
            lz.step(self._WL, self._HL, targets=targets, cursor=cur)
            self._lizard_bite(lz)

    def _lizard_bite(self, lz):
        """蜥蜴咬到猫：眩晕（apply_stun 内部已扣脾气）+ 轻微震动。"""
        ev = lz.bite_event
        if ev is None:
            return
        lz.bite_event = None
        obj, _dmg = ev
        beh = getattr(obj, "behavior", None)
        if beh is None:
            return
        if beh.apply_stun(LIZARD_STUN_TICKS):
            self._shake[0] += 1.6 * lz.facing
            self._shake[1] += 1.0

    def _draw_lizards(self, p):
        ts = self._ts
        for lz in self.lizards:
            draw_lizard(p, self.atlas, lz, ts)

    def _lizard_hint_object(self):
        """放置预览用的一次性蜥蜴（不参与物理，品种跟随下一次放置）。"""
        seed = self._lizard_seed
        got = getattr(self, "_lizard_preview", None)
        if got is None or got[0] != seed:
            lz = Lizard(0.0, 0.0, BREEDS[seed % len(BREEDS)], seed=seed)
            lz.state = ItemState.MOUSE
            got = (seed, lz)
            self._lizard_preview = got
        return got[1]

    @staticmethod
    def _lay_lizard_hint(lz, cx, cy):
        """把预览蜥蜴摆成「头在光标、身体横躺向左」的站姿。"""
        lz.x = lz.last_x = cx
        lz.y = lz.last_y = cy
        lz.head_angle = lz.last_head_angle = 90.0
        lz.facing = 1
        x = cx
        for s in lz.seg:
            x -= s.dist
            s.x = s.lx = x
            s.y = s.ly = cy
        for lg in lz.legs:
            seg = lz.seg[0] if not lg.back else (lz.seg[2] if len(lz.seg) > 2 else lz.seg[-1])
            lg.x = lg.lx = seg.x + (8.0 if lg.back else -8.0)
            lg.y = lg.ly = seg.y + lz.body_rad * 2.2
            lg.lift = 0.0

    def _draw_lizard_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        lz = self._lizard_hint_object()
        self._lay_lizard_hint(lz, cx, cy)
        p.save()
        p.setOpacity(0.5)
        draw_lizard(p, self.atlas, lz, 1.0)
        p.restore()

    def enter_place_fruit_mode(self):
        if not self.can_place_fruit():
            return False
        self._place_mode = True
        self._place_kind = "fruit"
        self._begin_place_capture()
        return True

    def _begin_place_capture(self):
        """进入放置模式，grabMouse 防点击被覆盖窗截走。"""
        hk = getattr(self, "_hotkey_filter", None)
        if hk is not None:
            hk.register(HK_PLACE_ESC, 0, VK_ESCAPE)
        if not self._hwnd:
            self._hwnd = int(self.winId())
        from ..control.mouse import set_passthrough
        set_passthrough(self._hwnd, False)
        self._passthrough = False
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.grabMouse()

    def _exit_place_mode(self):
        if not self._place_mode:
            return
        self._place_mode = False
        self._place_kind = None
        self._slime_preview = None
        hk = getattr(self, "_hotkey_filter", None)
        if hk is not None:
            hk.unregister(HK_PLACE_ESC)
        self.releaseMouse()
        self.unsetCursor()
        self._passthrough = None

    def _draw_fruit_ropes(self, p):
        ts = self._ts
        for f in self.fruits:
            st = f.stalk
            if st is None:
                continue
            pts = [st.stuck_pos]
            for s in st.segs:
                lx = s[2] + (s[0] - s[2]) * ts
                ly = s[3] + (s[1] - s[3]) * ts
                pts.append((lx, ly))
            n = len(pts)
            if n < 2:
                continue
            pts[-1] = (f.last_x + (f.x - f.last_x) * ts,
                       f.last_y + (f.y - f.last_y) * ts)
            widths = [STALK_ROOT_W + (STALK_TIP_W - STALK_ROOT_W) * (i / (n - 1))
                      for i in range(n)]
            draw_rope(p, pts, widths, color=STALK_COLOR)

    def _draw_fruits(self, p):
        ts = self._ts
        for f in self.fruits:
            x = f.last_x + (f.x - f.last_x) * ts
            y = f.last_y + (f.y - f.last_y) * ts
            rx, ry = f.rotation
            rot_deg = _ang_from_up(rx, ry)
            draw_fruit(p, self.atlas, x, y, rot_deg, f.bites,
                       flesh_color=FRUIT_FLESH, outline_color=FRUIT_OUTLINE)

    def _draw_stones(self, p):
        ts = self._ts
        for s in self.stones:
            x = s.last_x + (s.x - s.last_x) * ts
            y = s.last_y + (s.y - s.last_y) * ts
            rot = s.last_rotation + (s.rotation_deg - s.last_rotation) * ts
            # 高速时画拖尾
            if (s.fling or s.thrown_by_saint) and s.state == ItemState.FREE:
                sp = math.hypot(s.vx, s.vy)
                if sp > STONE_TRAIL_MIN_SPEED:
                    length = min(sp * STONE_TRAIL_LEN_K, STONE_TRAIL_LEN_MAX)
                    draw_stone_trail(p, x, y, s.vx / sp, s.vy / sp, length,
                                     STONE_TRAIL_HALFW, STONE_COLOR, STONE_TRAIL_ALPHA)
            if s.vibrate > 0:
                x += (s.vibrate % 3) - 1.0
                y += ((s.vibrate // 2) % 3) - 1.0
            draw_stone(p, self.atlas, x, y, rot, s.frame,
                       color=STONE_COLOR, scale=STONE_DRAW_SCALE)

    def _draw_place_hint(self, p):
        from PySide6.QtGui import QPen

        if self._place_kind in ("vpole", "hpole"):
            self._draw_pole_hint(p)
            return

        if self._place_kind == "lamp":
            self._draw_lamp_hint(p)
            return

        if self._place_kind == "slimemold":
            self._draw_slime_hint(p)
            return

        if self._place_kind == "batfly":
            self._draw_batfly_hint(p)
            return

        if self._place_kind == "lizard":
            self._draw_lizard_hint(p)
            return

        if self._place_kind == "squidcada":
            self._draw_squidcada_hint(p)
            return

        if self._place_kind == "pearl":
            self._draw_pearl_hint(p)
            return

        if self._place_kind == "spear":
            self._draw_spear_hint(p)
            return

        if self._place_kind == "scavenger":
            self._draw_scavenger_hint(p)
            return

        stone = (self._place_kind == "stone")
        p.save()
        if not stone and not self.zerog_on:
            pen = QPen(QColor(255, 255, 255, 110), 1.0, Qt.PenStyle.DashLine)
            p.setPen(pen)
            yline = self._HL * PLACE_HANGING_FRAC
            p.drawLine(QPointF(0.0, yline), QPointF(self._WL, yline))
        cur = self.cursor_logical()
        if cur is not None:
            cx, cy = cur
            if 0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL:
                p.setOpacity(0.5)
                if stone:
                    draw_stone(p, self.atlas, cx, cy, 0.0,
                               "Pebble" + str(1 + self._stone_seed % 14),
                               color=STONE_COLOR, scale=STONE_DRAW_SCALE)
                else:
                    draw_fruit(p, self.atlas, cx, cy, 0.0, 3,
                               flesh_color=FRUIT_FLESH, outline_color=FRUIT_OUTLINE)
        p.restore()

    # ── 蝉乌贼（Squidcada）：飞行可抓，力竭落地后才能被叼走 ──
    def can_place_squidcada(self) -> bool:
        return True

    def place_squidcada(self, lx, ly):
        sc = Squidcada(lx, ly, seed=self._squidcada_seed)
        self._squidcada_seed += 1
        self.squidcadas.append(sc)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return sc

    def clear_squidcadas(self):
        for sc in self.squidcadas:
            for pet in self.pets:
                if sc is pet.body.carried_fruit:      # 复用果子叼持槽
                    pet.body.release_fruit()
            sc.state = ItemState.EATEN
        if self.squidcadas:
            self.squidcadas = []
            self.world_version += 1
        self._dragged_squidcada = None
        self._squidcada_preview = None

    def enter_place_squidcada_mode(self):
        self._place_mode = True
        self._place_kind = "squidcada"
        self._begin_place_capture()
        return True

    def _squidcada_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for sc in self.squidcadas:
            if sc.state not in (ItemState.FREE, ItemState.CARRIED):
                continue
            d = math.hypot(cx - sc.x, cy - sc.y)
            if d <= sc.rad + SQUIDCADA_GRAB_PAD and d < bestd:
                best, bestd = sc, d
        return best

    def _begin_squidcada_drag(self, pos) -> bool:
        sc = self._squidcada_at(pos)
        if sc is None:
            return False
        if sc.state == ItemState.CARRIED:
            for pet in self.pets:
                if sc is pet.body.carried_fruit:
                    pet.body.release_fruit()
        sc.held_by_hand = None
        sc.state = ItemState.MOUSE
        sc.vx = sc.vy = 0.0
        sc.last_x, sc.last_y = pos
        sc.x, sc.y = pos
        self._dragged_squidcada = sc
        return True

    def _step_squidcada_drag(self):
        sc = self._dragged_squidcada
        if sc is None:
            return
        if sc.state != ItemState.MOUSE:
            self._dragged_squidcada = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        sc.last_x, sc.last_y = sc.x, sc.y
        sc.x, sc.y = cur
        sc.vx = sc.vy = 0.0

    def _end_squidcada_drag(self) -> bool:
        sc = self._dragged_squidcada
        if sc is None:
            return False
        if sc.state == ItemState.MOUSE:
            sc.state = ItemState.FREE
        self._dragged_squidcada = None
        return True

    def _tick_squidcadas(self):
        self._step_squidcada_drag()
        if not self.squidcadas:
            return
        threats = [(pet, pet.body.chunk0.x, pet.body.chunk0.y) for pet in self.pets]
        for sc in self.squidcadas:
            sc._impact_cb = self._shake_impact
            sc.step(self._WL, self._HL, threats=threats)
        self.squidcadas = [sc for sc in self.squidcadas if sc.state != ItemState.EATEN]

    def _draw_squidcadas(self, p):
        ts = self._ts
        for sc in self.squidcadas:
            if sc.state in (ItemState.EATEN, ItemState.GONE):
                continue
            draw_squidcada(p, self.atlas, sc, ts)

    def _squidcada_hint_object(self):
        seed = self._squidcada_seed
        got = getattr(self, "_squidcada_preview", None)
        if got is None or got[0] != seed:
            got = (seed, Squidcada(0.0, 0.0, seed=seed))
            self._squidcada_preview = got
        return got[1]

    def _draw_squidcada_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        sc = self._squidcada_hint_object()
        sc.x = sc.last_x = cx
        sc.y = sc.last_y = cy
        sc.vx = sc.vy = 0.0
        sc.dir_x, sc.dir_y = 1.0, 0.0
        sc.rest = 0
        p.save()
        p.setOpacity(0.5)
        draw_squidcada(p, self.atlas, sc, 1.0)
        p.restore()

    # ── 珍珠（Pearl）：高弹小球，可拖可掷 ──
    def can_place_pearl(self) -> bool:
        return True

    def place_pearl(self, lx, ly):
        pr = Pearl(lx, ly, seed=self._pearl_seed)
        self._pearl_seed += 1
        self.pearls.append(pr)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return pr

    def clear_pearls(self):
        for pr in self.pearls:
            if pr.state == ItemState.CARRIED and pr.held_by_hand is not None:
                for pet in self.pets:
                    if pr is pet.body.carried_fruit:
                        pet.body.release_fruit()
            pr.state = ItemState.GONE
        if self.pearls:
            self.pearls = []
            self.world_version += 1
        self._dragged_pearl = None
        self._pearl_drag_last = None

    def enter_place_pearl_mode(self):
        self._place_mode = True
        self._place_kind = "pearl"
        self._begin_place_capture()
        return True

    def _pearl_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for pr in self.pearls:
            if pr.state != ItemState.FREE:
                continue
            d = math.hypot(cx - pr.x, cy - pr.y)
            if d <= pr.rad + PEARL_GRAB_PAD and d < bestd:
                best, bestd = pr, d
        return best

    def _begin_pearl_drag(self, pos) -> bool:
        pr = self._pearl_at(pos)
        if pr is None:
            return False
        pr.state = ItemState.MOUSE
        pr.vx = pr.vy = 0.0
        pr.last_x, pr.last_y = pos
        pr.x, pr.y = pos
        self._dragged_pearl = pr
        self._pearl_drag_last = tuple(pos)
        return True

    def _step_pearl_drag(self):
        pr = self._dragged_pearl
        if pr is None:
            return
        if pr.state != ItemState.MOUSE:
            self._dragged_pearl = None
            self._pearl_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        pr.last_x, pr.last_y = pr.x, pr.y
        if self._pearl_drag_last is not None:
            pr.vx = cur[0] - self._pearl_drag_last[0]
            pr.vy = cur[1] - self._pearl_drag_last[1]
        pr.x, pr.y = cur
        self._pearl_drag_last = tuple(cur)

    def _end_pearl_drag(self) -> bool:
        pr = self._dragged_pearl
        if pr is None:
            return False
        sp = math.hypot(pr.vx, pr.vy)
        if sp > self._PEARL_FLING_CAP:
            k = self._PEARL_FLING_CAP / sp
            pr.vx *= k
            pr.vy *= k
        if pr.state == ItemState.MOUSE:
            pr.state = ItemState.FREE
            pr.spin = clampf(pr.vx * 4.0, -60.0, 60.0) * lerp(0.05, 1.0, pr.room_gravity)
        self._dragged_pearl = None
        self._pearl_drag_last = None
        return True

    def _tick_pearls(self):
        self._step_pearl_drag()
        if self.pearls:
            for pr in self.pearls:
                pr._impact_cb = self._shake_impact
                pr.step(self._WL, self._HL)
            self.pearls = [pr for pr in self.pearls if pr.state != ItemState.GONE]

    def _draw_pearls(self, p):
        ts = self._ts
        for pr in self.pearls:
            if pr.state == ItemState.GONE:
                continue
            x = pr.last_x + (pr.x - pr.last_x) * ts
            y = pr.last_y + (pr.y - pr.last_y) * ts
            rot = pr.last_rotation + (pr.rotation_deg - pr.last_rotation) * ts
            draw_pearl(p, x, y, rot, pr.tint, pr.rad)

    def _draw_pearl_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        pr = self._pearl_hint_object()
        p.save()
        p.setOpacity(0.5)
        draw_pearl(p, cx, cy, 0.0, pr.tint, pr.rad)
        p.restore()

    def _pearl_hint_object(self):
        seed = self._pearl_seed
        got = getattr(self, "_pearl_preview", None)
        if got is None or got[0] != seed:
            got = (seed, Pearl(0.0, 0.0, seed=seed))
            self._pearl_preview = got
        return got[1]

    # ── 矛（Spear）：落地即插入立住；掷出可插墙地 ──
    def can_place_spear(self) -> bool:
        return True

    def place_spear(self, lx, ly):
        sp = Spear(lx, ly, seed=self._spear_seed)
        self._spear_seed += 1
        self.spears.append(sp)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return sp

    def clear_spears(self):
        for sp in self.spears:
            for sc in self.scavengers:
                if sp is sc.spear:
                    sc.spear = None
            for pet in self.pets:
                if sp is getattr(pet.body, "carried_stone", None):
                    rs = getattr(pet.body, "release_stone", None)
                    if rs is not None:
                        rs()
            sp.state = ItemState.GONE
        if self.spears:
            self.spears = []
            self.world_version += 1
        self._dragged_spear = None
        self._spear_drag_last = None

    def enter_place_spear_mode(self):
        self._place_mode = True
        self._place_kind = "spear"
        self._begin_place_capture()
        return True

    def _spear_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for sp in self.spears:
            if sp.state != ItemState.FREE:
                continue
            d = _dist_to_path([sp.butt(), sp.tip()], cx, cy) - SPEAR_HALF_W
            if d <= SPEAR_GRAB_PAD and d < bestd:
                best, bestd = sp, d
        return best

    def _begin_spear_drag(self, pos) -> bool:
        sp = self._spear_at(pos)
        if sp is None:
            return False
        sp.unstuck()
        sp.state = ItemState.MOUSE
        sp.last_x, sp.last_y = pos
        sp.x, sp.y = pos
        self._dragged_spear = sp
        self._spear_drag_last = tuple(pos)
        return True

    def _step_spear_drag(self):
        sp = self._dragged_spear
        if sp is None:
            return
        if sp.state != ItemState.MOUSE:
            self._dragged_spear = None
            self._spear_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        sp.last_x, sp.last_y = sp.x, sp.y
        if self._spear_drag_last is not None:
            sp.vx = cur[0] - self._spear_drag_last[0]
            sp.vy = cur[1] - self._spear_drag_last[1]
        sp.last_angle = sp.angle_deg
        if abs(sp.vx) + abs(sp.vy) > 0.5:
            sp.angle_deg = math.degrees(math.atan2(sp.vx, -sp.vy))       # 杆顺运动方向
        sp.x, sp.y = cur
        self._spear_drag_last = tuple(cur)

    def _end_spear_drag(self) -> bool:
        sp = self._dragged_spear
        if sp is None:
            return False
        speed = math.hypot(sp.vx, sp.vy)
        if speed > self._SPEAR_FLING_CAP:
            k = self._SPEAR_FLING_CAP / speed
            sp.vx *= k
            sp.vy *= k
        if sp.state == ItemState.MOUSE:
            sp.state = ItemState.FREE
        self._dragged_spear = None
        self._spear_drag_last = None
        return True

    def _step_spear_hit(self):
        """飞矛扎到猫：眩晕 + 震动（同抛石）。"""
        for pet in self.pets:
            if pet.behavior is None or pet.behavior.blocks_interaction():
                continue
            b = pet.body
            for sp in self.spears:
                if sp.stuck or sp.state != ItemState.FREE:
                    continue
                if math.hypot(sp.vx, sp.vy) < SPEAR_HIT_SPEED:
                    continue
                for c in (b.chunk0, b.chunk1):
                    if math.hypot(sp.x - c.x, sp.y - c.y) < sp.rad + c.rad + SPEAR_HIT_PAD:
                        if pet.behavior.apply_stun(LIZARD_STUN_TICKS):
                            self._shake[0] += 1.2 * (1.0 if sp.vx >= 0.0 else -1.0)
                            self._shake[1] += 0.8
                        sp.vx = sp.vy = 0.0
                        break

    def _tick_spears(self):
        self._step_spear_drag()
        if self.spears:
            for sp in self.spears:
                sp._impact_cb = self._shake_impact
                sp.step(self._WL, self._HL)
            self._step_spear_hit()
            self.spears = [sp for sp in self.spears if sp.state != ItemState.GONE]

    def _draw_spears(self, p):
        ts = self._ts
        for sp in self.spears:
            x = sp.last_x + (sp.x - sp.last_x) * ts
            y = sp.last_y + (sp.y - sp.last_y) * ts
            ang = sp.stuck_angle if sp.stuck else _ang_lerp(sp.last_angle, sp.angle_deg, ts)
            draw_spear(p, x, y, ang, length=SPEAR_DRAW_LEN)

    def _draw_spear_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        p.save()
        p.setOpacity(0.5)
        draw_spear(p, cx, cy, 90.0, length=SPEAR_DRAW_LEN)
        p.restore()

    # ── 拾荒者（Scavenger）：持矛巡走，见威胁瞄准投矛 ──
    def can_place_scavenger(self) -> bool:
        return True

    def place_scavenger(self, lx, ly):
        sc = Scavenger(lx, ly, seed=self._scavenger_seed, id=self._scavenger_seed)
        self._scavenger_seed += 1
        self.scavengers.append(sc)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return sc

    def clear_scavengers(self):
        for sc in self.scavengers:
            if sc.spear is not None and sc.spear not in self.spears:
                sc.spear.state = ItemState.GONE
            sc.die()
        if self.scavengers:
            self.scavengers = []
            self.world_version += 1
        self._dragged_scavenger = None
        self._scavenger_preview = None

    def enter_place_scavenger_mode(self):
        self._place_mode = True
        self._place_kind = "scavenger"
        self._begin_place_capture()
        return True

    def _scavenger_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for sc in self.scavengers:
            if sc.state != ItemState.FREE:
                continue
            d = math.hypot(cx - sc.x, cy - (sc.y - SCAV_STAND_H * 0.5))
            if d <= sc.rad + SCAVENGER_GRAB_PAD and d < bestd:
                best, bestd = sc, d
        return best

    def _begin_scavenger_drag(self, pos) -> bool:
        sc = self._scavenger_at(pos)
        if sc is None:
            return False
        sc.grab(pos)
        sc.last_x, sc.last_y = pos
        sc.x, sc.y = pos
        self._dragged_scavenger = sc
        return True

    def _step_scavenger_drag(self):
        """手里的拾荒者由 Scavenger._step_held 跟随光标；这里只清失效引用。"""
        sc = self._dragged_scavenger
        if sc is not None and sc.state != ItemState.MOUSE:
            self._dragged_scavenger = None

    def _end_scavenger_drag(self) -> bool:
        sc = self._dragged_scavenger
        if sc is None:
            return False
        sc.release(0.0, 0.0)
        self._dragged_scavenger = None
        return True

    def _step_scavenger_throws(self):
        """拾荒者的投矛意图 → 生成一枝飞矛。"""
        for sc in self.scavengers:
            ev = sc.throw_event
            if ev is None:
                continue
            sc.throw_event = None
            hx, hy = sc.head_pos()
            sp = Spear(hx, hy, seed=self._spear_seed,
                       angle_deg=math.degrees(math.atan2(ev[0] - hx, -(ev[1] - hy))))
            self._spear_seed += 1
            dx, dy = ev[0] - hx, ev[1] - hy
            d = math.hypot(dx, dy) or 1.0
            sp.vx = dx / d * SPEAR_THROW_SPEED
            sp.vy = dy / d * SPEAR_THROW_SPEED - SPEAR_THROW_LIFT
            self.spears.append(sp)

    def _tick_scavengers(self):
        self._step_scavenger_drag()
        if not self.scavengers:
            return
        cur = self.cursor_logical()
        threats = [(lz, lz.x, lz.y) for lz in self.lizards if lz.state == ItemState.FREE]
        threats += [(pet, pet.body.chunk0.x, pet.body.chunk0.y) for pet in self.pets]
        for sc in self.scavengers:
            sc.step(self._WL, self._HL, threats=threats, cursor=cur)
        self._step_scavenger_throws()
        self.scavengers = [sc for sc in self.scavengers if sc.state != ItemState.GONE]

    def _draw_scavengers(self, p):
        ts = self._ts
        for sc in self.scavengers:
            if sc.state == ItemState.GONE:
                continue
            draw_scavenger(p, sc, ts, sc.body_rgb, sc.head_rgb, sc.eye_rgb)
            if sc.spear is not None:
                draw_scavenger_spear(p, sc, ts)

    def _scavenger_hint_object(self):
        seed = self._scavenger_seed
        got = getattr(self, "_scavenger_preview", None)
        if got is None or got[0] != seed:
            sc = Scavenger(0.0, 0.0, seed=seed)
            sc.spear = None
            got = (seed, sc)
            self._scavenger_preview = got
        return got[1]

    def _draw_scavenger_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        sc = self._scavenger_hint_object()
        sc.x = sc.last_x = cx
        sc.y = sc.last_y = min(cy, self._HL - SCAV_BODY_RAD)
        p.save()
        p.setOpacity(0.5)
        draw_scavenger(p, sc, 1.0, sc.body_rgb, sc.head_rgb, sc.eye_rgb)
        p.restore()

    # ── 驯服：猫把蝉乌贼递给蜥蜴（原版 FriendTracker.GiftRecieved）──
    def untamed_lizards(self):
        """还没被驯服的蜥蜴。"""
        return [lz for lz in self.lizards if not lz.tamed and lz.state == ItemState.FREE]

    def nearest_untamed_lizard(self, x):
        best, bd = None, 1e9
        for lz in self.untamed_lizards():
            d = abs(lz.x - x)
            if d < bd:
                best, bd = lz, d
        return best

    def tame_ready(self) -> bool:
        """有未驯服蜥蜴 + 场上有够得到的蝉乌贼 → 允许猫为驯服而取物。"""
        if not self.untamed_lizards():
            return False
        return any(sc.fetch_ready for sc in self.squidcadas)

    def deliver_gift(self, pet, lz) -> bool:
        """交接礼物：蝉乌贼转给蜥蜴，按原版结算 like（活体 0.6 / 尸体 1.2）。"""
        item = pet.body.carried_fruit
        if item is None or not getattr(item, "is_tame_food", False):
            return False
        alive = not getattr(item, "dead", False)
        item.held_by_hand = None
        item.stalk = None
        item.state = ItemState.EATEN
        pet.body.release_fruit()
        lz.gift_received(alive, pet.id)
        self._gift_fx(lz)
        return True

    def _gift_fx(self, lz):
        """送礼反馈：一小圈彩色火花 + 轻微抖动。"""
        rng = self._stun_rng
        for i in range(10):
            a = rng.uniform(0.0, math.tau)
            sp = rng.uniform(1.2, 2.6)
            self.sparks.append([lz.x, lz.y - 6.0, math.cos(a) * sp, math.sin(a) * sp - 0.6,
                                18, 18, 1 if i % 2 else 0])
        self._shake[1] -= 0.6
