"""业力花（KarmaFlower.cs）：金色四瓣 + 6 节软茎；啃 4 口 → 业力加固。

原版数据（反编译 KarmaFlower.cs）：
  bodyChunks[0].rad = 2（MSC 5）；gravity 0.6 / airFriction 0.93 / bounce 0.2
  surfaceFriction 0.7 / waterFriction 0.95 / buoyancy 0.9 / collisionLayer 0
  petals = Part[4]：锚在 pos + rotation*5.25，绕 90 度排布、半径 9.75，
                    单瓣最远 13.5；贴图 KarmaPetal(6x20) anchorY=0，
                    scaleY = Distance/20、scaleX = 0.375
  stalk  = Part[6]：ConnectStalkSegment 段长 5；n=2..5 用 ±dir*2.3 互相拉直
  花环   = EndGameCircle(32x32) 铺在 4 片花瓣尖之间（QuadGridMesh）
  扎根   = TryRoot：往下 4 格找到实心地面 → growPos / hoverPos(+18~36) / hoverDirAdd(±25)
  颜色   = RainWorld.GoldRGB = (0.529, 0.365, 0.184)；
           stalkColor = Lerp(palette.blackColor, palette.fogColor, 0.3)
  吃     = bites = 4（每口少一片花瓣），FoodPoints = 0（不填饱食度）
"""

from __future__ import annotations

import math
import random as _random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF, QRadialGradient, QTransform

from ..core.chunkphys import apply_water
from ..core.units import clampf, inv_lerp, lerp
from ..rendering.pixelmode import aa_hint, pen_width
from ..rendering.primitives import blit
from .enums import ItemState
from .fruit import Fruit, _perp

# ── 原版常数 ──
RAD = 2.0                     # bodyChunks[0].rad（非 MSC）
GRAVITY = 0.6
AIR_FRICTION = 0.93
BOUNCE = 0.2
SURFACE_FRICTION = 0.7
WATER_FRICTION = 0.95
BUOYANCY = 0.9
BITES = 4                     # 原版 bites = 4
PETAL_N = 4
STALK_N = 6
STALK_SEG = 5.0               # ConnectStalkSegment 段长
PETAL_OFF = 5.25              # 花瓣根沿 rotation 的偏移
PETAL_REACH = 9.75            # 花瓣绕轴半径
PETAL_MAX = 13.5              # 单瓣最远距
PETAL_ART_LEN = 20.0          # 原版 scaleY = Distance / 20f
PETAL_SCALE_X = 0.375         # 原版 scaleX = 0.375
HOVER_SPRING = 20.0           # 原版 vel += (hoverPos - pos) / 20f
HOVER_DY_MIN, HOVER_DY_MAX = 18.0, 36.0
HOVER_DX = 7.0
ROOT_DX = 9.0
ROOT_MAX_DROP = 64.0          # TryRoot 只往下找 4 格（4x16px）
DAMP_AIR = 0.95               # Part.Update：vel *= 0.95
TELEPORT_JUMP = 24.0          # 单 tick 位移超过它按「瞬移」处理：部件整块跟着走
DAMP_WATER = 0.7
DROOP = 0.4                   # 悬空时茎端下垂力
STIFF = 2.3                   # n=2..5 的 ±dir*2.3 拉直
SPRING_DIV_LO = 3.0           # 原版弹簧分母：vel 用 3..30、pos 用 3..60
SPRING_DIV_MID = 30.0
SPRING_DIV_HI = 60.0

PETAL_SPRITE = "KarmaPetal"   # 6x20，anchorY = 0
RING_SPRITE = "EndGameCircle"  # 32x32
GOLD_RGB = (135, 93, 47)      # RainWorld.GoldRGB
STALK_TIP_RGB = (47, 39, 58)  # Lerp(blackColor, fogColor, 0.3) 近似
GLOW_OUTER_RGB = (20, 40, 82)  # HSL2RGB(AntiGold.hue, .6, .2)
# Futile_White 是 8x8：原版 sprite.scale = K/16 ⇒ 直径 = 8K/16 = K/2
#   EffectSprite(0) K=75 ⇒ 直径 37.5、半径 18.75；EffectSprite(1/2) K=40 ⇒ 半径 10
GLOW_R_OUT = 18.75
GLOW_R_IN = 10.0


def _deg_to_vec(a: float) -> tuple[float, float]:
    """原版 Custom.DegToVec 的 y↓ 等价：0=上、顺时针。"""
    r = math.radians(a)
    return (math.sin(r), -math.cos(r))


def _aim(ax: float, ay: float, bx: float, by: float) -> float:
    """原版 AimFromOneVectorToAnother 的 y↓ 等价。"""
    return math.degrees(math.atan2(bx - ax, -(by - ay)))


def _vec_deg(vx: float, vy: float) -> float:
    return _aim(0.0, 0.0, vx, vy)


def _dir(ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)


def _lerp_map(v: float, a: float, b: float, A: float, B: float) -> float:
    """原版 Custom.LerpMap（e=1）。"""
    t = (v - a) / (b - a) if b != a else 0.0
    t = clampf(t, 0.0, 1.0)
    return A + (B - A) * t


def _flatten(vx: float, vy: float, axis_deg: float, fac: float) -> tuple[float, float]:
    """原版 Custom.FlattenVectorAlongAxis(vec, axis, fac)。

    原版实现：RotateAroundOrigo(vec, axis) -> vec.y *= fac -> RotateAroundOrigo(vec, -axis)。
    """
    px, py = _deg_to_vec(_vec_deg(vx, vy) + axis_deg)
    py *= fac
    return _deg_to_vec(_vec_deg(px, py) - axis_deg)


class KarmaFlower(Fruit):
    """一朵业力花：扎根时悬在根上方晃，抓起瞬间断根；啃 4 口加固业力。"""

    __slots__ = ("grow_pos", "hover_pos", "hover_dir_add", "petals",
                 "stalk_pts", "face_camera", "movement")
    is_meat = False
    is_karma = True                 # 吃了只加业力花条，不填饱食度
    food_value = 0                  # 原版 FoodPoints = 0

    def __init__(self, x: float, y: float, seed: int = 0, ground_y: float | None = None):
        super().__init__(x, y, seed=seed)
        self.rad = RAD
        self.mass = 0.05
        self.gravity = GRAVITY
        self.air_friction = AIR_FRICTION
        self.bounce = BOUNCE
        self.surface_friction = SURFACE_FRICTION
        self.water_friction = WATER_FRICTION
        self.buoyancy = BUOYANCY
        self.bites = BITES
        self.grow_pos: tuple[float, float] | None = None
        self.hover_pos = (float(x), float(y))
        self.hover_dir_add = 0.0
        self.movement = 0.0
        self.petals = [[float(x), float(y), float(x), float(y), 0.0, 0.0]
                       for _ in range(PETAL_N)]
        self.stalk_pts = [[float(x), float(y), float(x), float(y), 0.0, 0.0]
                          for _ in range(STALK_N)]
        rng = _random.Random(seed)          # 原版 game.SeededRandom
        self.face_camera = rng.uniform(0.2, 0.8)
        if ground_y is not None:
            self.try_root(ground_y, rng)

    # ── 扎根（原版 TryRoot）──
    def try_root(self, ground_y: float, rng=None) -> bool:
        """脚下 4 格内有实心地面就扎根并悬在 hover_pos；否则自由落体。"""
        if float(ground_y) - self.y > ROOT_MAX_DROP:
            return False
        r = rng if rng is not None else _random.Random(int(self.x) * 31 + int(self.y))
        # 原版：growPos 落在实心地面那格的上沿，hoverPos = growPos + (18~36) 向上
        gp = (self.x + r.uniform(-ROOT_DX, ROOT_DX), float(ground_y))
        self.grow_pos = gp
        self.hover_pos = (gp[0] + r.uniform(-HOVER_DX, HOVER_DX),
                          gp[1] - r.uniform(HOVER_DY_MIN, HOVER_DY_MAX))
        self.hover_dir_add = r.uniform(-25.0, 25.0)
        self.detach_to(self.hover_pos[0], self.hover_pos[1])
        return True

    def detach_to(self, x: float, y: float) -> None:
        """把花体硬放到 (x,y) 并把花瓣/茎一起收拢过去（原版 HardSetPosition + ResetParts）。"""
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        if self.grow_pos is not None:
            a = _aim(self.grow_pos[0], self.grow_pos[1], self.x, self.y) + self.hover_dir_add
            self.rotation = _deg_to_vec(a)
        for pt in self.petals:
            pt[0], pt[1] = self.x, self.y
            pt[2], pt[3] = self.x, self.y
            pt[4] = pt[5] = 0.0
        for sp in self.stalk_pts:
            sp[0], sp[1] = self.x, self.y
            sp[2], sp[3] = self.x, self.y
            sp[4] = sp[5] = 0.0

    def detach_root(self) -> None:
        """断根（原版被抓住 / 被武器命中时 growPos = null）。"""
        self.grow_pos = None

    def _carry_shift(self) -> None:
        """被手/鼠标瞬移搬动（一 tick 跨几十像素）时，把花瓣和茎整块平移。

        否则弹簧项吃到的「体速度」= 一整帧的位移，部件会被甩到几屏外，
        渲染出来就是拉丝/爆炸。
        """
        dx, dy = self.x - self.last_x, self.y - self.last_y
        if dx * dx + dy * dy <= TELEPORT_JUMP * TELEPORT_JUMP:
            return
        for pt in self.petals:
            pt[0] += dx
            pt[1] += dy
            pt[2] += dx
            pt[3] += dy
        for sp in self.stalk_pts:
            sp[0] += dx
            sp[1] += dy
            sp[2] += dx
            sp[3] += dy
        self.last_x, self.last_y = self.x, self.y

    # ── 物理 ──
    def step(self, WL: float, HL: float) -> None:
        if self.state in (ItemState.CARRIED, ItemState.MOUSE):
            if self.grow_pos is not None:
                # 被手/鼠标拿起的瞬间连根拔起（原版 DetatchStalk）：整株连茎一起走，
                # 地上不留残茎；之后茎靠自己的弹簧/重力继续甩
                self.detach_root()
            self._carry_shift()
            self._contact_floor = False
            self._parts_step()          # 花体被手/鼠标搬，只有花瓣与茎在跟
            return
        self.last_x, self.last_y = self.x, self.y
        if self.state == ItemState.EATEN:
            return
        for pt in self.petals:
            pt[2], pt[3] = pt[0], pt[1]
        for sp in self.stalk_pts:
            sp[2], sp[3] = sp[0], sp[1]

        self.vy += self.gravity * self.room_gravity
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        self.x += self.vx
        self.y += self.vy
        self._collide(WL, HL)

        if self.grow_pos is not None:
            # 原版 growPos 分支：base.Update 已扣过一次重力，这里的 +gravity 是把它抵消
            # （Unity y↑ 写 += gravity；我们 y↓ 所以写 -= ）
            self.vy -= self.gravity * self.room_gravity
            self.vx *= 0.7
            self.vy *= 0.7
            self.vx += (self.hover_pos[0] - self.x) / HOVER_SPRING
            self.vy += (self.hover_pos[1] - self.y) / HOVER_SPRING
            a = _aim(self.grow_pos[0], self.grow_pos[1], self.x, self.y) + self.hover_dir_add
            self.rotation = _deg_to_vec(a)
        else:
            if not self._contact_floor:
                # 原版：没碰到任何东西时朝向慢慢倒向茎的方向
                dx = self.x - self.stalk_pts[2][0]
                dy = self.y - self.stalk_pts[2][1]
                nx = self.rotation[0] + dx
                ny = self.rotation[1] + dy
                d = math.hypot(nx, ny)
                if d > 1e-9:
                    self.rotation = (nx / d, ny / d)
            else:
                # 原版 ContactPoint.y < 0：沿 +x 速度侧倾，横速减到 0.8
                rx, ry = self.rotation
                px, py = _perp(rx, ry)
                k = 0.1 * self.vx
                nx, ny = rx - px * k, ry - py * k
                d = math.hypot(nx, ny)
                if d > 1e-9:
                    self.rotation = (nx / d, ny / d)
                self.vx *= 0.8

        self.movement = inv_lerp(0.0, 12.0, math.hypot(self.x - self.last_x,
                                                       self.y - self.last_y))
        self._parts_step()

    def _submerged(self) -> bool:
        return self.water_y is not None and self.y + self.rad > self.water_y

    def _connect(self, i: int) -> None:
        """原版 ConnectStalkSegment(i)。"""
        if i == 0:
            p = self.stalk_pts[0]
            dx, dy = _dir(p[0], p[1], self.x, self.y)
            k = STALK_SEG - math.hypot(self.x - p[0], self.y - p[1])
            p[0] -= k * dx
            p[1] -= k * dy
            p[4] -= k * dx
            p[5] -= k * dy
            return
        a = self.stalk_pts[i]
        b = self.stalk_pts[i - 1]
        dx, dy = _dir(a[0], a[1], b[0], b[1])
        k = (STALK_SEG - math.hypot(b[0] - a[0], b[1] - a[1])) * 0.5
        vx, vy = dx * k, dy * k
        a[0] -= vx
        a[1] -= vy
        a[4] -= vx
        a[5] -= vy
        b[0] += vx
        b[1] += vy
        b[4] += vx
        b[5] += vy

    def _spring(self, pt, tx: float, ty: float, scale: float, clamp: bool) -> None:
        """原版花瓣/茎的弹簧项（val = dot(朝向花心, 朝向目标)）。"""
        px, py = self.x, self.y
        dpx, dpy = px - pt[0], py - pt[1]
        dtx, dty = px - tx, py - ty
        np = math.hypot(dpx, dpy)
        nt = math.hypot(dtx, dty)
        val = 0.0
        if np > 1e-9 and nt > 1e-9:
            val = (dpx / np) * (dtx / nt) + (dpy / np) * (dty / nt)
        k = _lerp_map(val, 1.0, -1.0, 0.0, 1.0) * scale
        bvx = self.x - self.last_x
        bvy = self.y - self.last_y
        pt[4] += (bvx - pt[4]) * k
        pt[5] += (bvy - pt[5]) * k
        d1 = _lerp_map(val, -1.0, 1.0, SPRING_DIV_LO, SPRING_DIV_MID)
        d2 = _lerp_map(val, -1.0, 1.0, SPRING_DIV_LO, SPRING_DIV_HI)
        pt[4] += (tx - pt[0]) / d1 * scale
        pt[5] += (ty - pt[1]) / d1 * scale
        pt[0] += (tx - pt[0]) / d2 * scale
        pt[1] += (ty - pt[1]) / d2 * scale
        if clamp:
            dx, dy = _dir(pt[0], pt[1], self.x, self.y)
            d = math.hypot(self.x - pt[0], self.y - pt[1])
            if d > PETAL_MAX:
                over = PETAL_MAX - d
                pt[0] -= over * dx
                pt[1] -= over * dy
                pt[4] -= over * dx
                pt[5] -= over * dy

    def _parts_step(self) -> None:
        """原版 Update 里的花瓣/花茎 verlet 段落，顺序照抄。"""
        damp = DAMP_WATER if self._submerged() else DAMP_AIR
        for pt in self.petals:
            pt[0] += pt[4]
            pt[1] += pt[5]
            pt[4] *= damp
            pt[5] *= damp
        for j, sp in enumerate(self.stalk_pts):
            sp[0] += sp[4]
            sp[1] += sp[5]
            sp[4] *= damp
            sp[5] *= damp
            if self.grow_pos is None:
                sp[5] += inv_lerp(0.0, STALK_N - 1, j) * DROOP    # 原版 vel.y -= ，y↓ 取反
        rot_deg = _vec_deg(self.rotation[0], self.rotation[1])
        rx, ry = self.rotation
        for i in range(PETAL_N):
            fx, fy = _flatten(*_deg_to_vec(rot_deg + 90.0 * i), rot_deg, self.face_camera)
            self._spring(self.petals[i],
                         self.x + rx * PETAL_OFF + fx * PETAL_REACH,
                         self.y + ry * PETAL_OFF + fy * PETAL_REACH, 1.0, True)
        for k in range(STALK_N):
            self._connect(k)
        for k in range(STALK_N - 1, -1, -1):
            self._connect(k)
        for l in range(PETAL_N):        # 原版 l < 4
            self._spring(self.stalk_pts[l],
                         self.x - rx * (3.0 + l) * 5.0,
                         self.y - ry * (3.0 + l) * 5.0,
                         inv_lerp(4.0, 0.0, float(l)), False)
        for _ in range(2):
            for k in range(STALK_N):
                self._connect(k)
            for k in range(STALK_N - 1, -1, -1):
                self._connect(k)
        if self.grow_pos is not None:
            last = self.stalk_pts[STALK_N - 1]
            last[0], last[1] = self.grow_pos
            last[4] = last[5] = 0.0
        for n in range(2, STALK_N):
            a = self.stalk_pts[n]
            b = self.stalk_pts[n - 2]
            dx, dy = _dir(b[0], b[1], a[0], a[1])
            a[4] += dx * STIFF
            a[5] += dy * STIFF
            b[4] -= dx * STIFF
            b[5] -= dy * STIFF


# ── 绘制 ──
def _blit_petal(painter, atlas, spr, x, y, ang, d) -> None:
    """花瓣贴图：锚在花心、朝花瓣质点伸出（等价原版 FSprite.anchorY = 0）。

    blit 的 ay=0 是「贴图顶边贴锚点、朝 +local-y 生长」，而 ang=0 在我们的 y↓
    坐标里是正上方 —— 用 ay=0 每片花瓣都会朝 180° 反向长（花瓣位置全错、
    末端接不到花环、花看起来忽大忽小）。ay=1 才是「底边贴锚点、朝 -local-y
    生长」，和 Unity 的 anchorY=0 同向。
    """
    blit(painter, atlas, spr, x, y, ang, PETAL_SCALE_X, d / PETAL_ART_LEN,
         GOLD_RGB, ax=0.5, ay=1.0)


def _draw_ring(painter, atlas, quad) -> None:
    """原版 TriangleMesh.QuadGridMesh 把 EndGameCircle 铺在 4 个花瓣尖之间。

    quadToQuad 对退化四边形（花瓣被啃光、或被弹簧挤成一条线）会解出奇异矩阵，
    把 32x32 的花环贴图整块拉爆 —— 先按面积判据挡掉。
    """
    area = 0.0
    for i in range(4):
        ax, ay = quad[i]
        bx, by = quad[(i + 1) % 4]
        area += ax * by - bx * ay
    if abs(area) < 4.0:
        return
    key = atlas.find_atlas(RING_SPRITE)
    if key is None:
        return
    w, h = atlas.source_size(key, RING_SPRITE)
    pm = atlas.sprite(key, RING_SPRITE, QColor(*GOLD_RGB))
    src = QPolygonF([QPointF(0.0, 0.0), QPointF(w, 0.0),
                     QPointF(w, h), QPointF(0.0, h)])
    dst = QPolygonF([QPointF(*quad[0]), QPointF(*quad[1]),
                     QPointF(*quad[2]), QPointF(*quad[3])])
    tr = QTransform()
    if not QTransform.quadToQuad(src, dst, tr):
        return
    painter.save()
    painter.setTransform(tr, True)
    painter.drawImage(0, 0, pm.toImage())
    painter.restore()


def _draw_stalk(painter, atlas, kf, ts: float) -> None:
    """花体 → stalk[0..5] 的细长条，颜色从金色渐变到暗根部。"""
    pts = [(kf.last_x + (kf.x - kf.last_x) * ts, kf.last_y + (kf.y - kf.last_y) * ts)]
    for sp in kf.stalk_pts:
        pts.append((sp[2] + (sp[0] - sp[2]) * ts, sp[3] + (sp[1] - sp[3]) * ts))
    painter.save()
    aa_hint(painter)
    n = len(pts)
    for i in range(n - 1):
        t = i / float(n - 1)
        col = QColor(*[int(GOLD_RGB[k] + (STALK_TIP_RGB[k] - GOLD_RGB[k]) * t)
                       for k in range(3)])
        pen = painter.pen()
        pen.setColor(col)
        pen.setWidthF(pen_width(1.5))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(*pts[i]), QPointF(*pts[i + 1]))
    painter.restore()


def _draw_glow(painter, x: float, y: float, movement: float, bites: int) -> None:
    """原版三张 Futile_White 光斑（Foreground / GrabShaders 容器，是「灯光」）。

    EffectSprite(0) 外圈暗青 = HSL2RGB(AntiGold.hue, .6, .2)，alpha 0.4*(1-movement)*fade
                    —— 只有静止时才亮；EffectSprite(1/2) 内圈金色，alpha 0.7/0.8*fade。
    灯光用 Plus（加色）叠加，才不会把花瓣糊掉。
    """
    t = inv_lerp(0.0, float(BITES), float(bites))
    fade = 0.5 + 0.5 * t
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    layers = ((GLOW_R_OUT, GLOW_OUTER_RGB, 0.4 * (1.0 - movement) * fade),
              (GLOW_R_IN, GOLD_RGB, 0.7 * fade),
              (GLOW_R_IN, GOLD_RGB, 0.8 * fade))
    for radius, rgb, alpha in layers:
        if alpha <= 0.01:
            continue
        c = QColor(*rgb)
        c.setAlphaF(min(1.0, alpha))
        c2 = QColor(*rgb)
        c2.setAlphaF(0.0)
        g = QRadialGradient(QPointF(x, y), radius * fade)
        g.setColorAt(0.0, c)
        g.setColorAt(1.0, c2)
        painter.setBrush(g)
        painter.drawEllipse(QPointF(x, y), radius * fade, radius * fade)
    painter.restore()


def draw_karmaflower(painter, atlas, kf, ts: float = 1.0) -> None:
    """画一朵业力花：光斑 → 花茎 → 花瓣（bites 决定还剩几片）→ 花环。"""
    ts = clampf(ts, 0.0, 1.0)
    x = kf.last_x + (kf.x - kf.last_x) * ts
    y = kf.last_y + (kf.y - kf.last_y) * ts
    _draw_stalk(painter, atlas, kf, ts)
    quad = []
    gx, gy, gn = x, y, 1.0
    for i in range(PETAL_N):
        pt = kf.petals[i]
        px = pt[2] + (pt[0] - pt[2]) * ts
        py = pt[3] + (pt[1] - pt[3]) * ts
        if i < kf.bites:
            d = math.hypot(px - x, py - y)
            _blit_petal(painter, atlas, PETAL_SPRITE, x, y, _aim(x, y, px, py), d)
            ux, uy = _dir(x, y, px, py)
            quad.append((px + ux * 2.0, py + uy * 2.0))
            gx += px
            gy += py
            gn += 1.0
        else:
            quad.append((x, y))
    _draw_ring(painter, atlas, quad)
    # 原版：光斑中心 = (花心 + 各花瓣) 的重心
    _draw_glow(painter, gx / gn, gy / gn, kf.movement, kf.bites)