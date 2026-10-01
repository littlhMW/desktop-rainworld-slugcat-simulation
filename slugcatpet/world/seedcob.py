"""爆米花（Popcorn Plant / SeedCob）：从天花板垂下的豆荚，被超度/矛打开后弹出可食种子。

对照原版 SeedCob.cs：PlaceInRoom / Update / DrawSprites / ApplyPalette / spawnUtilityFoods。
宠物里没有房间调色板与雨循环，取固定暗色；几何与配色公式照抄，y↓ 与宠物一致。
"""
from __future__ import annotations
import math
import random as _random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath

from ..core.units import clampf, lerp
from .combat import CombatTarget
from ..rendering.primitives import blit
from .fruit import Fruit
from .enums import ItemState
from ..rendering.pixelmode import aa_hint

MIN_CLEAR = 70.0               # 豆荚最低点离地面至少留这么多（原版豆荚不会埋进地里）
# 长度随意：植株**不是杆子**（不许爬），但挂得再高也有办法 —— 蛞蝓猫可以爬到
# 旁边的**真竖杆**同一高度上横着投矛（原版矛只有水平分支，见 fsm._st_eatcob）。
ROOT_Y = -10.0                 # 原版 rootPos = (placedPos.x, -10)：锚在房顶之上；
                               # 宠物里改为锚在窗口底边（地面），从地上长起来
STALK_SEG_MAX = 50
SEED_N_MIN, SEED_N_MAX = 10, 70
LEAF_N_MIN, LEAF_N_MAX = 4, 14
COB_SEGMENTS = 10
COB_FEED_PUSH = 1.2            # 原版 delayedPush = dir * 1.2f
COB_FEED_PUSH_DELAY = 4        # 原版 pushDelay = 4

PALETTE_BLACK = (27, 11, 33)   # 原版 palette.blackColor（与蜥蜴/矛同一取色）
PLANT_COLOR = (86, 104, 58)    # 原版 palette.texture.GetPixel(0,5) 的近似：暗橄榄绿
PALETTE_DARK = 0.0             # 原版 rCam.PaletteDarkness() 的固定替代；
                               # 取 0 = 亮房间：wiki 原版截图/gif 就是这个档，
                               # 豆荚黄 (193,176,108)、高光 (255,252,184) 与之一致
YELLOW_BASE = (230, 212, 128)  # 原版 new Color(0.9, 0.83, 0.5)
SHELL_RED = (255, 0, 0)        # 原版 Color.red

SEED_SPRITE = "JetFishEyeA"
SEED_DOT = "pixel"
SEED_DOT_ALIVE = "tinyStar"
LEAF_SPRITE = "CentipedeLegB"
LEAF_ART_LEN = 26.0            # 原版 scaleY = Distance / 26f


def _deg_to_vec(a: float) -> tuple[float, float]:
    """原版 Custom.DegToVec：0=上、顺时针（y↓）。"""
    r = math.radians(a)
    return (math.sin(r), -math.cos(r))


def _aim(ax: float, ay: float, bx: float, by: float) -> float:
    """原版 AimFromOneVectorToAnother：a→b 的角度（0=上、顺时针）。"""
    return math.degrees(math.atan2(bx - ax, -(by - ay)))


def _perp(dx: float, dy: float) -> tuple[float, float]:
    """原版 PerpendicularVector(v) = (-v.y, v.x) 的 y↓ 等价。"""
    return (-dy, dx)


def _dir(ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)


def _push_from_half(v: float, e: float) -> float:
    """原版 Custom.PushFromHalf(val, pushExponent)。"""
    if v == 0.5:
        return 0.5
    if v < 0.5:
        return _lerp_map(v, 0.0, 0.5, 0.0, 0.5, e)
    return _lerp_map(v, 1.0, 0.5, 1.0, 0.5, e)


def _lerp_map(v: float, a: float, b: float, A: float, B: float, e: float = 1.0) -> float:
    """原版 Custom.LerpMap。"""
    t = (v - a) / (b - a) if b != a else 0.0
    t = clampf(t, 0.0, 1.0) ** e
    return A + (B - A) * t


def _bezier(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (p0[0] * a + p1[0] * b + p2[0] * c + p3[0] * d,
            p0[1] * a + p1[1] * b + p2[1] * c + p3[1] * d)


def _mix(a, b, t):
    t = clampf(t, 0.0, 1.0)
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def yellow_color(dead: bool) -> tuple[int, int, int]:
    """原版 ApplyPalette：yellowColor = Lerp((0.9,0.83,0.5), blackColor, dead ? 0.95+0.5*dark : 0.18+0.7*dark)。"""
    k = (0.95 + 0.5 * PALETTE_DARK) if dead else (0.18 + 0.7 * PALETTE_DARK)
    return _mix(YELLOW_BASE, PALETTE_BLACK, k)


def seed_hi_color(dead: bool) -> tuple[int, int, int]:
    """原版 color2 = yellowColor + 0.3 * Lerp(1, 0.15, dark)；dead 时 Lerp(yellow, plant, 0.75)。"""
    y = yellow_color(dead)
    add = 255.0 * 0.3 * (1.0 + (0.15 - 1.0) * PALETTE_DARK)
    out = (int(clampf(y[0] + add, 0, 255)), int(clampf(y[1] + add, 0, 255)),
           int(clampf(y[2] + add, 0, 255)))
    if dead:
        return _mix(out, PLANT_COLOR, 0.75)
    return out


def seed_dot_color(dead: bool) -> tuple[int, int, int]:
    """原版 SeedSprite(l,2).color = Lerp(Color.red, blackColor, dead ? 0.6 : 0.3)。"""
    return _mix(SHELL_RED, PALETTE_BLACK, 0.6 if dead else 0.3)


class Seed(Fruit):
    """爆米花种子：一口的小食物，物理同果子但更轻更弹。"""
    __slots__ = ()
    is_meat = False                 # 植物性食物（同果子）
    food_class = "plant"            # 食性：植物（SlimeMold.cs，Seed 实现为 bites=1 的黏菌）

    def __init__(self, x: float, y: float, seed: int = 0):
        super().__init__(x, y, seed=seed)
        # 原版 AbstractObjectType.Seed 实现为 SlimeMold(bites=1)：SlimeMold.cs:213-223
        self.rad = 5.0
        self.mass = 0.12
        self.bounce = 0.2
        self.surface_friction = 0.7
        self.buoyancy = 1.1
        self.water_friction = 0.95
        self.bites = 1


def _clamp_placed(y: float, root_y: float) -> float:
    """只把豆荚夹在「不低于离地 MIN_CLEAR」的位置（长度随意）。

    太低会埋进地里；挂多高都行 —— 植株不是杆子，但旁边的真竖杆能爬上去打。
    """
    return min(float(y), float(root_y) - MIN_CLEAR)


class SeedCob(CombatTarget):
    food_class = "plant"            # 食性：植物（原版走 handOnExternalFoodSource 直接啃）
    """爆米花植株：无重力、双质点 + 弹簧固定在挂点，靠 open 动画弹开豆荚。"""
    collision_layer = 0
    is_meat = False

    __slots__ = ("placed", "root_pos", "root_y", "root_dir", "cob_dir", "conn_dist",
                 "stalk_length", "stalk_segments", "cob_segments",
                 "seed_pos", "popped", "leaves", "open", "last_open",
                 "opened", "dead", "rotted", "pop_counter", "state", "rad",
                 "p0", "p0l", "v0", "p1", "p1l", "v1", "_rng", "_id",
                 "push_delay", "delayed_push", "drag_point")

    def __init__(self, x: float, y: float, seed: int = 0, root_y: float | None = None):
        rng = _random.Random(seed)
        self._rng = rng
        self._id = int(seed)
        self.root_y = ROOT_Y if root_y is None else float(root_y)
        self.placed = (float(x), _clamp_placed(y, self.root_y))
        self.root_pos = (float(x), self.root_y)
        d = lerp(60.0, math.dist(self.root_pos, self.placed) / 2.0, 0.3)
        self.conn_dist = d
        self.root_dir = _deg_to_vec(_aim(*self.root_pos, *self.placed) + rng.uniform(-45.0, 45.0))
        self.cob_dir = _deg_to_vec(_aim(*self.placed, *self.root_pos) + rng.uniform(-25.0, 25.0))
        rest1 = (self.placed[0] + self.cob_dir[0] * d, self.placed[1] + self.cob_dir[1] * d)
        self.stalk_length = math.dist(self.root_pos, rest1) + 5.0
        self.stalk_segments = _int_clamp(int(math.dist(self.root_pos, self.placed) / 10.0),
                                         5, STALK_SEG_MAX)
        self.cob_segments = COB_SEGMENTS
        n_seed = _int_clamp(round(d / 2.0), SEED_N_MIN, SEED_N_MAX)
        self.seed_pos = []
        for j in range(n_seed):
            t = j / (n_seed - 1)
            self.seed_pos.append((rng.uniform(-1.0, 1.0) * math.pow(math.sin(t * math.pi), 0.5), t))
        self.popped = [False] * n_seed
        n_leaf = _int_clamp(round(lerp(d / 10.0, 10.0, 0.5)), LEAF_N_MIN, LEAF_N_MAX)
        self.leaves = []
        for _ in range(n_leaf):
            length = rng.uniform(0.5, 1.5) * d * 0.2
            sx = rng.uniform(0.5, 1.5) * lerp(d, 100.0, 0.5) * 0.01 * (-1.0 if rng.random() < 0.5 else 1.0)
            self.leaves.append([[rest1[0], rest1[1]], [rest1[0], rest1[1]], [0.0, 0.0], (sx, 0.0, 0.0, length)])
        self.p0, self.p0l, self.v0 = self.placed, self.placed, [0.0, 0.0]
        self.p1, self.p1l, self.v1 = rest1, rest1, [0.0, 0.0]
        self.open = 0.0
        self.last_open = 0.0
        self.opened = False
        self.dead = False
        self.rotted = False
        self.pop_counter = -1
        self.state = ItemState.FREE
        self.rad = 8.0            # SeedCob.cs:106-107 双 chunk rad 8
        self.push_delay = 0           # 被啃时把豆荚往外弹（原版 delayedPush/pushDelay）
        self.delayed_push = None
        self.drag_point = None        # 鼠标拖拽目标（None＝未拖）

    @property
    def pos(self):
        return self.p0

    @property
    def x(self):
        return self.p0[0]

    @property
    def y(self):
        return self.p0[1]

    def collision_chunks(self):
        return ()

    def chunks(self):
        """可命中点＝两个挂点（文档 §7 CombatTarget；原版 Weapon.cs 逐 chunk 判定）。"""
        return [(None, float(self.p0[0]), float(self.p0[1]), self.rad),
                (None, float(self.p1[0]), float(self.p1[1]), self.rad)]

    # ── 外部食物源（原版 SeedCob.Update 里给 Player 的 handOnExternalFoodSource）──
    def feed_point(self, x: float, y: float):
        """ClosestPointOnLineSegment(bodyChunks[0], bodyChunks[1], pos)。"""
        ax, ay = self.p0
        bx, by = self.p1
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        if l2 <= 1e-9:
            return (ax, ay)
        t = ((x - ax) * dx + (y - ay) * dy) / l2
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        return (ax + dx * t, ay + dy * t)

    def can_feed(self) -> bool:
        """原版 Update:313 的 `!dead && open > 0.8f` —— 开荚后才是可啃食物源。"""
        return bool(self.opened and not self.dead and self.open > 0.8)

    def push_from(self, x: float, y: float) -> None:
        """原版 350-351：被啃时朝远离猫的方向弹一下（延迟 4 tick 生效）。"""
        dx, dy = self.p0[0] - x, self.p0[1] - y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return
        self.delayed_push = (dx / d * COB_FEED_PUSH, dy / d * COB_FEED_PUSH)
        self.push_delay = COB_FEED_PUSH_DELAY

    # ── 原版 Open / spawnUtilityFoods ──
    def open_cob(self) -> None:
        """原版 Open()：被矛击中后开启，稍后逐颗弹出。"""
        if not self.opened:
            self.opened = True
            self.pop_counter = self._rng.randint(30, 60)

    def retarget(self, x: float, y: float) -> None:
        """把挂点与豆荚挪到新落点（拖动植株时用）；开合/已弹状态保留。

        rng 由目标点派生 → 同一位置形状稳定，拖动时不会每帧抖动。
        """
        rng = _random.Random(self._id * 7919 + int(x) * 131 + int(y) * 17)
        self.placed = (float(x), _clamp_placed(y, self.root_y))
        self.root_pos = (float(x), self.root_y)
        d = lerp(60.0, math.dist(self.root_pos, self.placed) / 2.0, 0.3)
        self.conn_dist = d
        self.root_dir = _deg_to_vec(_aim(*self.root_pos, *self.placed) + rng.uniform(-45.0, 45.0))
        self.cob_dir = _deg_to_vec(_aim(*self.placed, *self.root_pos) + rng.uniform(-25.0, 25.0))
        rest1 = (self.placed[0] + self.cob_dir[0] * d, self.placed[1] + self.cob_dir[1] * d)
        self.stalk_length = math.dist(self.root_pos, rest1) + 5.0
        self.stalk_segments = _int_clamp(int(math.dist(self.root_pos, self.placed) / 10.0),
                                         5, STALK_SEG_MAX)
        for lf in self.leaves:
            lf[0][0], lf[0][1] = rest1
            lf[1][0], lf[1][1] = rest1
            lf[2][0] = lf[2][1] = 0.0
        self.p0 = self.p0l = self.placed
        self.p1 = self.p1l = rest1
        self.v0 = [0.0, 0.0]
        self.v1 = [0.0, 0.0]

    def burst(self, win=None) -> None:
        """原版 spawnUtilityFoods()：圣徒超度直接炸开，生成 4 颗种子。"""
        if self.opened and self.dead:
            return
        self.opened = True
        self.dead = True
        self.pop_counter = 1
        self.v0[0] += self._rng.uniform(-2.0, 2.0)
        self.v0[1] += self._rng.uniform(-2.0, 2.0)
        for i in range(4):
            t = i / 5.0
            sx = self.p0[0] + (self.p1[0] - self.p0[0]) * t
            sy = self.p0[1] + (self.p1[1] - self.p0[1]) * t
            if win is not None and hasattr(win, "spawn_seed"):
                win.spawn_seed(sx, sy)

    def step(self, WL: float, HL: float) -> None:
        self.p0l, self.p1l = self.p0, self.p1
        if self.push_delay > 0:                       # 原版 301-311 delayedPush
            self.push_delay -= 1
        elif self.delayed_push is not None:
            px, py = self.delayed_push
            self.v0[0] += px
            self.v0[1] += py
            self.v1[0] += px
            self.v1[1] += py
            self.delayed_push = None
        if self.drag_point is not None:               # 鼠标拖拽：软弹簧拉豆荚，植株不动
            tx, ty = self.drag_point
            self.v0[0] += (tx - self.p0[0]) * 0.12
            self.v0[1] += (ty - self.p0[1]) * 0.12
        # 原版 Update：两质点各自被弹回挂点（弹簧强度随偏离距离变化）
        for p, v, rest, k0, k1, e in ((self.p0, self.v0, self.placed, 2000.0, 150.0, 0.8),
                                      (self.p1, self.v1, (self.placed[0] + self.cob_dir[0] * self.conn_dist,
                                                          self.placed[1] + self.cob_dir[1] * self.conn_dist),
                                      800.0, 50.0, 0.2)):
            dx, dy = rest[0] - p[0], rest[1] - p[1]
            dist = math.hypot(dx, dy)
            inv = _lerp_map(dist, 5.0, 100.0, k0, k1, e)
            if inv > 1e-6:
                v[0] += dx / inv
                v[1] += dy / inv
        # 原版：chunk 与 rootPos 距离不得超过茎长（拖拽时只能来回荡，甩不飞）
        for idx, lim in ((0, self.stalk_length + self.conn_dist),
                         (1, self.stalk_length)):
            pp = self.p0 if idx == 0 else self.p1
            vv = self.v0 if idx == 0 else self.v1
            dx, dy = pp[0] - self.root_pos[0], pp[1] - self.root_pos[1]
            d = math.hypot(dx, dy)
            if d > lim and d > 1e-6:
                k = (d - lim) * 0.2
                np_ = (pp[0] - dx / d * k, pp[1] - dy / d * k)
                vv[0] -= dx / d * k
                vv[1] -= dy / d * k
                if idx == 0:
                    self.p0 = np_
                else:
                    self.p1 = np_
        for p, v in ((self.p0, self.v0), (self.p1, self.v1)):
            v[0] *= 0.9
            v[1] *= 0.9
            p2 = (p[0] + v[0], p[1] + v[1])
            if p is self.p0:
                self.p0 = p2
            else:
                self.p1 = p2
        # 质点间刚性距离（原版 bodyChunkConnections[0].distance）
        d01 = math.dist(self.p0, self.p1)
        if d01 > 1e-6:
            err = d01 - self.conn_dist
            ux, uy = (self.p0[0] - self.p1[0]) / d01, (self.p0[1] - self.p1[1]) / d01
            self.p0 = (self.p0[0] - ux * err * 0.5, self.p0[1] - uy * err * 0.5)
            self.p1 = (self.p1[0] + ux * err * 0.5, self.p1[1] + uy * err * 0.5)
        self.last_open = self.open
        if self.opened:
            self.open = lerp(self.open, 1.0, lerp(0.01, 0.0001, self.open))
        if self.pop_counter > -1:
            self.pop_counter -= 1
            if self.pop_counter < 1:
                for i, was in enumerate(self.popped):
                    if was:
                        continue
                    self.popped[i] = True
                    t = i / max(1, len(self.popped) - 1)
                    if i == len(self.popped) - 1:
                        self.pop_counter = -1
                    else:
                        self.pop_counter = int(pow(1.0 - t, 0.5) * 20.0 * (0.5 + 0.5 * self._rng.random()))
                    break
        # 叶片：弹簧回位 + 摆动
        aim01 = _aim(self.p0[0], self.p0[1], self.p1[0], self.p1[1])
        for j, lf in enumerate(self.leaves):
            lf[1] = list(lf[0])
            lf[0][0] += lf[2][0]
            lf[0][1] += lf[2][1]
            lf[2][0] *= 0.9
            lf[2][1] *= 0.9
            ux, uy = _dir(lf[0][0], lf[0][1], self.p1[0], self.p1[1])
            cur = math.dist(lf[0], self.p1)
            rest_len = lf[3][3]
            k = cur - rest_len
            lf[0][0] += ux * k
            lf[0][1] += uy * k
            lf[2][0] += ux * k
            lf[2][1] += uy * k
            ang = aim01 + lerp(-45.0, 45.0, j / max(1, len(self.leaves) - 1))
            gx, gy = _deg_to_vec(ang)
            lf[2][0] += gx
            lf[2][1] += gy
        self._collide_bounds(WL, HL)

    def _collide_bounds(self, WL: float, HL: float) -> None:
        """边界弹性碰撞：左右墙 + 地面 + 其它窗口顶边。"""
        from ..core.chunkphys import platforms
        tops = platforms()
        r = self.rad
        for name, v in (("p0", self.v0), ("p1", self.v1)):
            p = getattr(self, name)
            if p[0] - r < 0.0 and v[0] < 0.0:
                p = (r, p[1]); v[0] *= -0.4
            elif p[0] + r > WL and v[0] > 0.0:
                p = (WL - r, p[1]); v[0] *= -0.4
            if p[1] + r > HL and v[1] > 0.0:
                p = (p[0], HL - r); v[1] *= -0.4
            if v[1] > 0.0:
                for x0, y0, x1 in tops:
                    if p[1] - v[1] + r > y0 + 0.6 or p[1] + r <= y0:
                        continue
                    if p[0] <= x0 - r or p[0] >= x1 + r:
                        continue
                    p = (p[0], y0 - r)
                    v[1] *= -0.4
                    break
            setattr(self, name, p)


def _int_clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else int(v))


# ── 渲染：对照 SeedCob.DrawSprites / ApplyPalette ──
def _quad(painter, a, b, c, d, rgb):
    """原版三角形网格的一段：a,b = 上一处截面的两侧，c,d = 当前截面两侧。
    多边形须按 a→b→d→c 绕（a→b→c→d 会自交成蝴蝶结）。"""
    path = QPainterPath()
    path.moveTo(QPointF(*a))
    path.lineTo(QPointF(*b))
    path.lineTo(QPointF(*d))
    path.lineTo(QPointF(*c))
    path.closeSubpath()
    painter.setBrush(QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(path)


def draw_seedcob(painter, atlas, cob, ts: float = 1.0, black=PALETTE_BLACK) -> None:
    """画一株爆米花：茎（暗层+亮层）→ 豆荚 → 两片外壳 → 种子 → 叶片。"""
    ts = clampf(ts, 0.0, 1.0)
    p0 = (cob.p0l[0] + (cob.p0[0] - cob.p0l[0]) * ts, cob.p0l[1] + (cob.p0[1] - cob.p0l[1]) * ts)
    p1 = (cob.p1l[0] + (cob.p1[0] - cob.p1l[0]) * ts, cob.p1l[1] + (cob.p1[1] - cob.p1l[1]) * ts)
    root = cob.root_pos
    D = math.dist(root, cob.placed)
    painter.save()
    aa_hint(painter)
    painter.setPen(Qt.PenStyle.NoPen)

    # ── 茎：Bezier 中心线 + 逐段锥形四边形 ──
    c1 = (root[0] + cob.root_dir[0] * D * 0.2, root[1] + cob.root_dir[1] * D * 0.2)
    ux, uy = _dir(p0[0], p0[1], p1[0], p1[1])
    c2 = (p1[0] + ux * D * 0.2, p1[1] + uy * D * 0.2)
    n = cob.stalk_segments
    line = [_bezier(root, c1, c2, p1, i / (n - 1) if n > 1 else 0.0) for i in range(n)]
    rad = [lerp(cob.conn_dist / 14.0, 1.5,
                math.pow(math.sin(math.pow(i / (n - 1) if n > 1 else 0.0, 2.0) * math.pi),
                         0.5)) for i in range(n)]
    # 单条带多边形（原版是顶点色长条网格，逐段四边形会有接缝）
    for j, (mul, off, grad) in enumerate(((1.0, 0.0, False), (0.35, -1.0, True))):
        left, right = [], []
        for i in range(n):
            ax = line[max(0, i - 1)]
            bx = line[min(n - 1, i + 1)]
            nx, ny = _dir(ax[0], ax[1], bx[0], bx[1])
            px, py = _perp(nx, ny)
            hw = rad[i] * mul
            oy = rad[i] * 0.5 * off
            left.append((line[i][0] + px * hw, line[i][1] + py * hw + oy))
            right.append((line[i][0] - px * hw, line[i][1] - py * hw + oy))
        path = QPainterPath()
        path.moveTo(QPointF(*left[0]))
        for q in left[1:]:
            path.lineTo(QPointF(*q))
        for q in reversed(right):
            path.lineTo(QPointF(*q))
        path.closeSubpath()
        if grad:
            g = QLinearGradient(QPointF(*root), QPointF(*p1))
            g.setColorAt(0.0, QColor(*_mix(black, PLANT_COLOR, 0.8)))
            g.setColorAt(1.0, QColor(*_mix(black, PLANT_COLOR, 0.4)))
            painter.setBrush(g)
        else:
            painter.setBrush(QColor(*black))
        painter.drawPath(path)

    # ── 豆荚：p1 → p0 的半径 2 长条，yellowColor ──
    yellow = yellow_color(cob.dead)
    tip_dir = _dir(p0[0], p0[1], p1[0], p1[1])
    prev = (p1[0] + tip_dir[0], p1[1] + tip_dir[1])
    prev_num = 2.0
    cs = cob.cob_segments
    for k in range(cs):
        t = k / (cs - 1) if cs > 1 else 0.0
        cur = (lerp(p1[0], p0[0], t), lerp(p1[1], p0[1], t))
        nx, ny = _dir(prev[0], prev[1], cur[0], cur[1])
        px, py = _perp(nx, ny)
        seg = math.dist(prev, cur) / 5.0 if k > 0 else 0.0
        hw0 = (2.0 + prev_num) * 0.5
        hw1 = 2.0
        _quad(painter,
              (prev[0] - nx * seg - px * hw0, prev[1] - ny * seg - py * hw0),
              (prev[0] - nx * seg + px * hw0, prev[1] - ny * seg + py * hw0),
              (cur[0] + nx * seg - px * hw1, cur[1] + ny * seg - py * hw1),
              (cur[0] + nx * seg + px * hw1, cur[1] + ny * seg + py * hw1),
              yellow)
        prev, prev_num = cur, 2.0

    open_amt = lerp(cob.last_open, cob.open, ts)   # 外壳与种子都要用，先算好

    # ── 种子 ──
    if open_amt > 0.0:
        v15 = _dir(p1[0], p1[1], p0[0], p0[1])
        v16 = _perp(*v15)
        ns = len(cob.seed_pos)
        hi = seed_hi_color(cob.dead)
        dot = seed_dot_color(cob.dead)
        # 逐颗算好位置，再分三趟画：主豆粒 → 高光 → 红点。
        # 原版按 sprite 下标逐颗画（主→高光→点），但豆粒间距只有 ~2px，
        # 下一颗的主豆粒会把上一颗的高光/红点整个盖住；wiki 原版图里豆荚是
        # 「亮色为主 + 一圈黄边 + 密集红点」，按层画才与之一致。
        cells = []
        for i in range(ns):
            sx0, sy0 = cob.seed_pos[i]
            t = sy0 * (math.dist(p1, p0) - 10.0)
            v17 = (p1[0] + v15[0] * t + v16[0] * (sx0 * 3.0),
                   p1[1] + v15[1] * t + v16[1] * (sx0 * 3.0))
            num13 = 1.0 + math.sin(i / (ns - 1) * math.pi if ns > 1 else 0.0)
            if cob.dead:
                num13 *= 0.5
            pop = cob.popped[i]
            v18 = (0.0, 0.0)
            if pop:
                k = math.pow(abs(sx0), _lerp_map(num13, 1.0, 2.0, 1.0, 0.5, 1.0))
                sgn = 1.0 if sx0 >= 0 else -1.0
                v18 = (v16[0] * k * sgn * 3.5 * num13, v16[1] * k * sgn * 3.5 * num13)
            cells.append((v17, v18, num13, pop, sx0))
        for v17, _v18, num13, pop, _sx0 in cells:
            blit(painter, atlas, SEED_SPRITE, v17[0], v17[1], 0.0,
                 num13 if pop else 0.35, num13 if pop else 0.35, yellow)
        for v17, v18, num13, pop, _sx0 in cells:
            if pop:
                blit(painter, atlas, SEED_SPRITE,
                     v17[0] + v18[0] * 0.35, v17[1] + v18[1] * 0.35,
                     0.0, num13 * 0.5, num13 * 0.5, hi)
        for v17, v18, _num13, pop, sx0 in cells:
            dot_frame = SEED_DOT_ALIVE if (pop and not cob.dead) else SEED_DOT
            blit(painter, atlas, dot_frame, v17[0] + v18[0], v17[1] + v18[1],
                 _aim(0.0, 0.0, v15[0], v15[1]),
                 math.pow(1.0 - abs(sx0), 0.2) if pop else 1.0, 1.0, dot)

    # ── 两片外壳：随 open 张开 ──（原版下标在种子之上 ⇒ 必须最后画，
    # 否则种子会盖住红色的壳）
    for l in (0, 1):
        num8 = -1.0 + l * 2.0
        num = 2.0
        base = (p0[0], p0[1])
        d01x, d01y = _dir(p1[0], p1[1], p0[0], p0[1])
        start = (p0[0] + d01x * 7.0, p0[1] + d01y * 7.0)
        num9 = _aim(p0[0], p0[1], p1[0], p1[1])
        cur = p0
        prev = start
        for m in range(cs):
            num10 = m / (cs - 1) if cs > 1 else 0.0
            ang = num9 + num8 * math.pow(open_amt, lerp(1.0, 0.1, num10)) * 50.0 * math.pow(num10, 0.5)
            step = (math.dist(base, p1) * 1.1 + 8.0) / cs
            gx, gy = _deg_to_vec(ang)
            cur = (cur[0] + gx * step, cur[1] + gy * step)
            nx, ny = _dir(prev[0], prev[1], cur[0], cur[1])
            px, py = _perp(nx, ny)
            seg = math.dist(prev, cur) / 5.0
            num12 = lerp(2.0, 6.0,
                         math.pow(math.sin(math.pow(num10, 0.5) * math.pi), 0.5))
            f = 1.0 - m / (cs - 1) if cs > 1 else 1.0
            sh = _mix(black, SHELL_RED, math.pow(max(0.0, f), 2.5) * 0.4)
            w0 = (num12 + num) * 0.5 * (1 - l)
            w1 = num12 * (1 - l)
            z0 = (num12 + num) * 0.5 * l
            z1 = num12 * l
            _quad(painter,
                  (prev[0] - nx * seg - px * w0, prev[1] - ny * seg - py * w0),
                  (prev[0] - nx * seg + px * z0, prev[1] - ny * seg + py * z0),
                  (cur[0] + nx * seg - px * w1, cur[1] + ny * seg - py * w1),
                  (cur[0] + nx * seg + px * z1, cur[1] + ny * seg + py * z1),
                  sh)
            prev = cur
            num = num12
            num9 = _aim(0.0, 0.0, nx, ny)

    # ── 叶片 ──
    for lf in cob.leaves:
        lx = lf[1][0] + (lf[0][0] - lf[1][0]) * ts
        ly = lf[1][1] + (lf[0][1] - lf[1][1]) * ts
        blit(painter, atlas, LEAF_SPRITE, p1[0], p1[1],
             _aim(p1[0], p1[1], lx, ly), lf[3][0],
             math.dist(p1, (lx, ly)) / LEAF_ART_LEN, black, ax=0.5, ay=1.0)
    painter.restore()


def draw_seed(painter, atlas, seed, ts: float = 1.0) -> None:
    """落地的种子：黄珠 + 红点（同豆荚上的种子配色）。"""
    x = seed.last_x + (seed.x - seed.last_x) * ts
    y = seed.last_y + (seed.y - seed.last_y) * ts
    painter.save()
    aa_hint(painter)
    blit(painter, atlas, SEED_SPRITE, x, y, 0.0, 1.0, 1.0, yellow_color(False))
    blit(painter, atlas, SEED_DOT_ALIVE, x, y, 0.0, 1.0, 1.0, seed_dot_color(False))
    painter.restore()
