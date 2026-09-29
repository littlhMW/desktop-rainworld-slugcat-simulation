"""物理内核：显式速度质点 + 连接约束 + 轴对齐碰撞。坐标系 y↓，常量换算见 core.units。"""
from __future__ import annotations
import math

from .units import K_IMP, K_VEL, clampf, damp60, lerp

RAD0 = 9.0            # chest
RAD1 = 8.0            # hips
MASS = 0.35
DIST_STAND = 17.0
DIST_CRAWL = 17.0

GRAVITY = 0.9 * K_IMP            # y↓
AIR_FRICTION = damp60(0.999)
BOUNCE = 0.1
WEIGHT_SYMMETRY = 0.5
ELASTICITY = 1.0
SURFACE_FRICTION = 0.5
MAX_STRETCH = 1.5    # pinned 端硬上限，rest×此值

STOP_THRESH = (1.0 + 9.0 * (1.0 - BOUNCE)) * K_VEL
TANGENTIAL = min(max(SURFACE_FRICTION * 2.0, 0.0), 1.0)

# 单个 chunk 的速度上限（px/tick）：约束求解在极端重叠下会往速度里灌很大的冲量
# （两个 chunk 被硬挤在一起 → 位置修正量大 → 下一 tick 又被别的约束挤回来，逐帧
# 累加），表现就是「像炮弹一样被发射出去」。正常动作（杆跳 6、工匠爆跳 15、被矛
# 击退 ~10、从屏幕顶自由落体到底 ~38）都远在阈值以内，只有失控才会被削。
MAX_CHUNK_SPEED = 60.0
MAX_CHUNK_SPEED_SQ = MAX_CHUNK_SPEED * MAX_CHUNK_SPEED

IMPACT_THRESHOLD = 1.0 * K_VEL
IMPACT_SHAKE_MOMENTUM = 7.0 * K_VEL
IMPACT_STRENGTH_KNEE = 30.0 * K_VEL


def apply_water(obj, water_y, buoyancy: float, water_friction, room_gravity: float,
                air_friction: float, immunity: float = 0.0) -> None:
    """水管线，重力后积分前调用。"""
    r = obj.rad
    sub = 0.0
    if water_y is not None and obj.y + r > water_y:      # 最低点入水
        sub = (obj.y + r - water_y) / (2.0 * r)
        if sub > 1.0:
            sub = 1.0
    if sub <= 0.0:
        obj.vx *= air_friction
        obj.vy *= air_friction
        return
    if obj.vx > -obj.vy * 5.0 and abs(obj.vx) > 10.0 and obj.vy > 0.0 and sub < 0.5:
        obj.vy *= -0.5                                    # 打水漂
        obj.vx *= 0.75
        return
    obj.vy -= buoyancy * room_gravity * sub              # 浮力，y↓取负
    wf = water_friction if water_friction is not None else air_friction
    spd = math.hypot(obj.vx, obj.vy)
    inner = lerp(wf * immunity, wf, (1.0 / max(1.0, spd - 10.0)) ** 0.5)
    k = lerp(air_friction, inner, sub)                   # 空气↔水阻插值
    obj.vx *= k
    obj.vy *= k


class BodyChunk:
    """BodyChunk：显式速度质点 + 圆-墙碰撞。坐标 y 向下。"""
    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "last_last_x", "last_last_y",
                 "rad", "mass", "index", "cx", "cy", "lcx", "lcy", "pinned",
                 "collide_with_objects", "support_y")

    def __init__(self, index: int, x: float, y: float, rad: float, mass: float):
        self.index = index
        self.x = self.last_x = self.last_last_x = x
        self.y = self.last_y = self.last_last_y = y
        self.vx = self.vy = 0.0
        self.rad = rad
        self.mass = mass
        self.cx = self.cy = 0      # 本帧接触 (±1/0)
        self.lcx = self.lcy = 0    # 上帧接触，边沿检测用
        self.pinned = False        # 外部定位，不积分不撞
        self.collide_with_objects = True   # 通用 chunk 碰撞开关
        self.support_y = None      # 本 tick 脚下那块地的 y（地板 or 别人窗口顶边）

    @property
    def on_floor(self) -> bool:
        return self.cy == 1     # y↓，+1=着地

    def update(self, W: float, H: float, gravity: float = GRAVITY,
               air_friction: float = AIR_FRICTION, impact=None,
               room_gravity: float = 1.0, water_y=None, buoyancy: float = 1.0,
               water_friction=None, water_immunity: float = 0.0) -> None:
        """推进一帧。"""
        if self.vx != self.vx:
            self.vx = 0.0
        if self.vy != self.vy:
            self.vy = 0.0
        self._cap_speed()
        if self.pinned:
            # kinematic，只维护快照
            self.last_last_x, self.last_last_y = self.last_x, self.last_y
            self.last_x, self.last_y = self.x, self.y
            self.lcx, self.lcy = self.cx, self.cy
            self.cx = self.cy = 0
            return
        self.vy += gravity * room_gravity
        apply_water(self, water_y, buoyancy, water_friction, room_gravity, air_friction, water_immunity)
        self.last_last_x, self.last_last_y = self.last_x, self.last_y
        self.last_x, self.last_y = self.x, self.y
        self.x += self.vx
        self.y += self.vy
        self.lcx, self.lcy = self.cx, self.cy
        self.cx = self.cy = 0
        # 碰撞：竖直优先 → 水平
        self._collide(W, H, impact)
        # 重力/水黄、约束求解、碰撞都会往里灌速度，出去前再封一次，
        # 保证 update() 返回时 hypot(vx,vy) 恒 ≤ MAX_CHUNK_SPEED。
        self._cap_speed()

    def _cap_speed(self) -> None:
        """单 chunk 速度封顶（深度重叠时约束求解会逐帧灌速度，必须兜住）。"""
        sp2 = self.vx * self.vx + self.vy * self.vy
        if sp2 > MAX_CHUNK_SPEED_SQ:
            k = MAX_CHUNK_SPEED / math.sqrt(sp2)
            self.vx *= k
            self.vy *= k

    def clamp_inside(self, W: float, H: float) -> None:
        """位置边界夹（安全网）。"""
        if self.pinned:
            return
        r = max(self.rad, 1.0)
        if self.x < r:
            self.x = r
        elif self.x > W - r:
            self.x = W - r
        if self.y < r:
            self.y = r
        elif self.y > H - r:
            self.y = H - r

    def _collide(self, W: float, H: float, impact) -> None:
        r = max(self.rad, 1.0)
        self.support_y = None
        # 竖直优先
        if self.y + r > H and self.vy > 0:
            self.y = H - r
            self.support_y = H
            if self.vy > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (0, 1), abs(self.vy), self.lcy < 1, impact)
            self.cy = 1
            self.vy = -abs(self.vy) * BOUNCE
            if self.vy > -STOP_THRESH:
                self.vy = 0.0
            self.vx *= TANGENTIAL
        elif self.y - r < 0 and self.vy < 0:
            self.y = r
            if -self.vy > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (0, -1), abs(self.vy), self.lcy > -1, impact)
            self.cy = -1
            self.vy = abs(self.vy) * BOUNCE
            if self.vy < STOP_THRESH:
                self.vy = 0.0
            self.vx *= TANGENTIAL
        # 水平其次
        if self.x + r > W and self.vx > 0:
            self.x = W - r
            if self.vx > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (1, 0), abs(self.vx), self.lcx < 1, impact)
            self.cx = 1
            self.vx = -abs(self.vx) * BOUNCE
            if self.vx > -STOP_THRESH:
                self.vx = 0.0
            self.vy *= TANGENTIAL
        elif self.x - r < 0 and self.vx < 0:
            self.x = r
            if -self.vx > IMPACT_THRESHOLD and impact is not None:
                _fire_impact(self, (-1, 0), abs(self.vx), self.lcx > -1, impact)
            self.cx = -1
            self.vx = abs(self.vx) * BOUNCE
            if self.vx < STOP_THRESH:
                self.vx = 0.0
            self.vy *= TANGENTIAL
        # 其它窗口顶边＝单向平台
        if _oneway_platform(self, r, BOUNCE, TANGENTIAL, impact, self.lcy < 1):
            self.cy = 1
        # 实心墙体（庇护所）：真碰撞（猫用开放门洞带那一张表）
        _solid_blocks(self, r, CAT_SOLIDS, impact, self.lcy < 1, self.lcy > -1,
                      self.lcx)


def _fire_impact(c: BodyChunk, direction, speed: float, first_contact: bool, impact) -> None:
    """地形撞击：首次接触边沿 + 动量超阈值时触发。"""
    if not first_contact:
        return
    momentum = speed * c.mass
    if momentum <= IMPACT_SHAKE_MOMENTUM:
        return
    strength = max((momentum - IMPACT_STRENGTH_KNEE) / 50.0, 0.0)
    ix = direction[0] * momentum * 0.1
    iy = direction[1] * momentum * 0.1
    impact(c, direction, speed, strength, ix, iy)


def solve_conn(a: BodyChunk, b: BodyChunk, rest: float = DIST_STAND,
               wsym: float = WEIGHT_SYMMETRY, elasticity: float = ELASTICITY,
               ctype: str = "Normal", max_stretch: float = MAX_STRETCH) -> None:
    """单遍半隐式约束求解，pinned 端不被推走。"""
    dx, dy = b.x - a.x, b.y - a.y
    d = math.hypot(dx, dy) or 1e-6
    if ctype == "Pull" and not (d > rest):
        return
    if ctype == "Push" and not (d < rest):
        return
    ux, uy = dx / d, dy / d
    corr = (rest - d) * elasticity  # >0 推开，<0 拉拢
    ca = corr * wsym
    cb = corr * (1.0 - wsym)
    ap, bp = a.pinned, b.pinned
    if ap and bp:
        return
    if ap:                                  # a 钉死，b 吃 (1-wsym)
        b.x += ux * cb
        b.y += uy * cb
        b.vx += ux * cb * K_IMP
        b.vy += uy * cb * K_IMP
    elif bp:                                # b 钉死，a 吃 wsym
        a.x -= ux * ca
        a.y -= uy * ca
        a.vx -= ux * ca * K_IMP
        a.vy -= uy * ca * K_IMP
    else:                                   # 都自由，按 wsym 分
        a.x -= ux * ca
        a.y -= uy * ca
        a.vx -= ux * ca * K_IMP
        a.vy -= uy * ca * K_IMP
        b.x += ux * cb
        b.y += uy * cb
        b.vx += ux * cb * K_IMP
        b.vy += uy * cb * K_IMP

    # 硬上限，仅单端 pinned 时触发
    if max_stretch is not None and (ap != bp):
        limit = rest * max_stretch
        dx, dy = b.x - a.x, b.y - a.y
        d = math.hypot(dx, dy)
        if d > limit:
            ux, uy = dx / d, dy / d
            if ap:                          # a 钉死，拉 b 到上限
                b.x = a.x + ux * limit
                b.y = a.y + uy * limit
            else:                           # b 钉死，拉 a
                a.x = b.x - ux * limit
                a.y = b.y - uy * limit


# ── 其它窗口顶边＝单向平台（窗口本体不挡路，只能从上方落上去）──
PLATFORMS: list = []          # [(x0, y0, x1)] 逻辑坐标，y0＝顶边
SOLIDS: list = []             # [(x0, y0, x1, y1)] 实心 AABB（庇护所真墙体）
CAT_SOLIDS: list = []         # 同 SOLIDS（文档口径：猫只能走入口）
CAT_PASS_SHELTER = False      # 暴雨集合期临时放行：桌宠猫不会绕到入口那一侧


def set_platforms(rects) -> None:
    """由 window 定时刷新：其它窗口的顶边。"""
    global PLATFORMS
    PLATFORMS = list(rects or ())


def platforms() -> list:
    return PLATFORMS


def set_solids(rects, cat_rects=None) -> None:
    """由 window 每 tick 刷新：庇护所的墙（左墙/顶/外墙/内墙/关上的门）。

    ``rects`` 给生物 / 物品 / 尸体（真房间）；``cat_rects`` 给蛞蝓猫 ——
    ``cat_rects`` 现在与它同表（真四壁 + 入口缺口）；单独留着是为了以后按角色改
        （例如暴雨集合期的放行开关 ``set_cat_shelter_pass``）。
    """
    global SOLIDS, CAT_SOLIDS
    SOLIDS = list(rects or ())
    CAT_SOLIDS = list(cat_rects) if cat_rects is not None else list(SOLIDS)


def solids() -> list:
    return SOLIDS


def cat_solids() -> list:
    return CAT_SOLIDS


def set_cat_shelter_pass(on) -> None:
    """暴雨集合期允许猫穿过庇护所墙体。

    原版猫从入口（ShelterDoor.cs:1170-1200 提取出的方位）走进屋；桌宠里猫
    只会在水平面上朝目标直走，绕不到入口那一侧，会一直顶在背面的墙上，
    番茄钟就卡在集合阶段。所以只在「暴雨真的落下、猫在赶路」这段放行，
    平时四壁对猫完全实心（文档要求）。
    """
    global CAT_PASS_SHELTER
    CAT_PASS_SHELTER = bool(on)


def cat_shelter_pass() -> bool:
    return CAT_PASS_SHELTER


def _solid_blocks(obj, r: float, table, impact=None, prev_floor: bool = False,
                  prev_ceil: bool = False, prev_x: float = 0.0) -> bool:
    """圆 vs 实心 AABB：取最小穿透轴推出（竖直优先）。

    这是庇护所墙体的真碰撞。``BodyChunk`` 用 ``cx/cy/support_y`` 记接触，
    物品用 ``_contact_floor`` / ``_contact_x`` / ``_contact_ceil``：两套都写。
    """
    if not table:
        return False
    if table is CAT_SOLIDS and CAT_PASS_SHELTER:
        return False
    hit = False
    bounce = getattr(obj, "bounce", BOUNCE)
    stop = 1.0 + 9.0 * (1.0 - bounce)
    for (x0, y0, x1, y1) in table:
        if x1 <= x0 or y1 <= y0:
            continue
        if obj.x + r <= x0 or obj.x - r >= x1:
            continue
        if obj.y + r <= y0 or obj.y - r >= y1:
            continue
        p_left = (obj.x + r) - x0
        p_right = x1 - (obj.x - r)
        p_top = (obj.y + r) - y0
        p_bot = y1 - (obj.y - r)
        m = min(p_left, p_right, p_top, p_bot)
        if m <= 0.0:
            continue
        hit = True
        if m == p_top:
            obj.y = y0 - r
            if obj.vy > 0.0:
                if impact is not None:
                    _fire_impact(obj, (0, 1), abs(obj.vy), prev_floor, impact)
                obj.vy = -abs(obj.vy) * bounce
                if obj.vy > -stop:
                    obj.vy = 0.0
            _set_floor(obj, y0)
        elif m == p_bot:
            obj.y = y1 + r
            if obj.vy < 0.0:
                obj.vy = abs(obj.vy) * bounce
                if obj.vy < stop:
                    obj.vy = 0.0
            _set_ceil(obj)
        elif m == p_left:
            obj.x = x0 - r
            if obj.vx > 0.0:
                obj.vx = -abs(obj.vx) * bounce
            _set_contact_x(obj, 1)
        else:
            obj.x = x1 + r
            if obj.vx < 0.0:
                obj.vx = abs(obj.vx) * bounce
            _set_contact_x(obj, -1)
    return hit


def _set_floor(obj, y0: float) -> None:
    if hasattr(obj, "cy"):
        obj.cy = 1
    if hasattr(obj, "support_y"):
        obj.support_y = y0
    if hasattr(obj, "_contact_floor"):
        obj._contact_floor = True


def _set_ceil(obj) -> None:
    if hasattr(obj, "cy") and getattr(obj, "cy", 0) != 1:
        obj.cy = -1
    if hasattr(obj, "_contact_ceil"):
        obj._contact_ceil = True


def _set_contact_x(obj, v: int) -> None:
    if hasattr(obj, "cx"):
        obj.cx = v
    if hasattr(obj, "_contact_x"):
        obj._contact_x = v


def _oneway_platform(obj, r: float, bounce: float, tang: float, impact=None,
                     first_contact: bool = True) -> bool:
    """落到某个窗口顶边就站住；只对「上一步还在顶边上方」生效。"""
    if not PLATFORMS or obj.vy <= 0.0:
        return False
    prev_bottom = obj.y - obj.vy + r
    for x0, y0, x1 in PLATFORMS:
        if prev_bottom > y0 + 0.6 or obj.y + r <= y0:
            continue
        if obj.x <= x0 - r or obj.x >= x1 + r:
            continue
        obj.y = y0 - r
        if hasattr(obj, "support_y"):
            obj.support_y = y0
        if impact is not None and abs(obj.vy) > IMPACT_THRESHOLD:
            _fire_impact(obj, (0, 1), abs(obj.vy), first_contact, impact)
        obj.vy = -abs(obj.vy) * bounce
        if obj.vy > -(1.0 + 9.0 * (1.0 - bounce)):
            obj.vy = 0.0
        obj.vx *= tang
        return True
    return False


def aabb_wall_collide(obj, WL, HL, impact=None, open_sides=False):
    """圆-墙 4 面碰撞，竖直优先。

    open_sides=True：左右与顶边不挡（只有底边仍是地面）。
    尸体用这个模式 —— 被甩出窗口就该飞出去，不再弹回来。
    """
    r = obj.rad
    tang = clampf(obj.surface_friction * 2.0, 0.0, 1.0)   # 切向摩擦
    stop = 1.0 + 9.0 * (1.0 - obj.bounce)                 # 低弹性→高阈值，撞墙即停
    has_ceil = hasattr(obj, "_contact_ceil")
    prev_floor, prev_x = obj._contact_floor, obj._contact_x
    prev_ceil = obj._contact_ceil if has_ceil else False
    obj._contact_floor = False
    obj._contact_x = 0
    if has_ceil:
        obj._contact_ceil = False
    # 竖直优先
    if obj.y + r > HL and obj.vy > 0:
        obj.y = HL - r
        if impact is not None:
            _fire_impact(obj, (0, 1), abs(obj.vy), not prev_floor, impact)
        obj._contact_floor = True
        obj.vy = -abs(obj.vy) * obj.bounce
        if obj.vy > -stop:
            obj.vy = 0.0
        obj.vx *= tang
    elif obj.y - r < 0 and not open_sides:
        # 顶边同底边一样是实体：被拖上来/顶上来也夹回窗口内
        obj.y = r
        if impact is not None and obj.vy < 0:
            _fire_impact(obj, (0, -1), abs(obj.vy), not prev_ceil, impact)
        if has_ceil:
            obj._contact_ceil = True
        obj.vy = abs(obj.vy) * obj.bounce if obj.vy < 0 else 0.0
        if obj.vy < stop:
            obj.vy = 0.0
        obj.vx *= tang
    # 水平其次（open_sides：尸体不挡左右，直接飞出去）
    if not open_sides:
        if obj.x + r > WL and obj.vx > 0:
            obj.x = WL - r
            if impact is not None:
                _fire_impact(obj, (1, 0), abs(obj.vx), prev_x < 1, impact)
            obj._contact_x = 1
            obj.vx = -abs(obj.vx) * obj.bounce
            if obj.vx > -stop:
                obj.vx = 0.0
            obj.vy *= tang
        elif obj.x - r < 0 and obj.vx < 0:
            obj.x = r
            if impact is not None:
                _fire_impact(obj, (-1, 0), abs(obj.vx), prev_x > -1, impact)
            obj._contact_x = -1
            obj.vx = abs(obj.vx) * obj.bounce
            if obj.vx < stop:
                obj.vx = 0.0
            obj.vy *= tang
    # 其它窗口顶边＝单向平台（从上方落下即站住）
    if not open_sides and _oneway_platform(obj, r, obj.bounce, tang, impact, not prev_floor):
        obj._contact_floor = True
    # 实心墙体（庇护所）：真碰撞（尸体 open_sides 时不挡）
    if not open_sides:
        _solid_blocks(obj, r, SOLIDS, impact, not prev_floor, not prev_ceil,
                      prev_x)


def _aabb_of(chunks):
    """实体所有 chunk 的包围盒（已含各自半径）；没有可碰 chunk 返回 None。"""
    x0 = y0 = float("inf")
    x1 = y1 = float("-inf")
    for c in chunks:
        r = c.rad
        cx, cy = c.x, c.y
        if cx - r < x0:
            x0 = cx - r
        if cy - r < y0:
            y0 = cy - r
        if cx + r > x1:
            x1 = cx + r
        if cy + r > y1:
            y1 = cy + r
    if x0 > x1:
        return None
    return (x0, y0, x1, y1)


_GRID_BRUTE_LIMIT = 8          # 实体少到这个数：建网格比两两枚举还贵
_GRID_MIN_CELL = 24.0
_GRID_MAX_INSERTS = 4096       # 个别超大实体（长绳）会让格子数爆掉：直接退回暴力


def _broadphase_pairs(objs, groups):
    """返回需要精算的 (i, j)，**按 (i, j) 升序**；返回 None 表示「直接两两暴力」。

    顺序必须与两两暴力枚举一致 —— 位置修正是逐对顺序施加的，顺序换了结果就变。
    网格只用来剔除「包围盒都不相交」的实体对：两个 chunk 圆相交 ⇒ 两个包围盒
    相交 ⇒ 一定落在同一个格子里，所以被剔除的那些对原本也是空转。

    实体少、或者挤得太密（候选对几乎等于暴力对数）时，建网格纯属白付开销，
    这两种情况都返回 None 交给调用方跑朴素的 i<j 双重循环。
    """
    n = len(objs)
    if n <= _GRID_BRUTE_LIMIT:
        return None
    boxes = [_aabb_of(g) for g in groups]
    spans = sorted(max(b[2] - b[0], b[3] - b[1]) for b in boxes if b is not None)
    if not spans:
        return []
    cell = max(_GRID_MIN_CELL, spans[len(spans) // 2])
    grid: dict[tuple, list] = {}
    inserted = 0
    for i, b in enumerate(boxes):
        if b is None:
            continue
        gx0 = int(b[0] // cell)
        gy0 = int(b[1] // cell)
        gx1 = int(b[2] // cell)
        gy1 = int(b[3] // cell)
        inserted += (gx1 - gx0 + 1) * (gy1 - gy0 + 1)
        if inserted > _GRID_MAX_INSERTS:
            return None
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                grid.setdefault((gx, gy), []).append(i)
    cand = 0
    for cellobjs in grid.values():
        m = len(cellobjs)
        if m > 1:
            cand += m * (m - 1) // 2
    if cand * 2 >= n * (n - 1):      # 剔不掉一半：网格收益抵不过建网格+排序
        return None
    seen = set()
    out = []
    for cellobjs in grid.values():
        m = len(cellobjs)
        if m < 2:
            continue
        for a in range(m):
            ia = cellobjs[a]
            for c in range(a + 1, m):
                ib = cellobjs[c]
                i, j = (ia, ib) if ia < ib else (ib, ia)
                key = i * n + j
                if key in seen:
                    continue
                seen.add(key)
                out.append((i, j))
    out.sort()
    return out


def collide_objects(entities) -> None:
    """通用 chunk 碰撞 pass，层 0 不自碰。"""
    buckets: dict[int, list] = {}
    for e in entities:
        layer = e.collision_layer
        if layer == 0:
            continue
        buckets.setdefault(layer, []).append(e)
    for objs in buckets.values():
        n = len(objs)
        if n < 2:
            continue
        groups = [o.collision_chunks() for o in objs]   # 每实体取一次，含本 tick 豁免
        pairs = _broadphase_pairs(objs, groups)
        if pairs is None:                                # 朴素两两枚举
            for i in range(n):
                gi = groups[i]
                oi = objs[i]
                for j in range(i + 1, n):
                    _collide_pair(oi, objs[j], gi, groups[j])
            continue
        for i, j in pairs:
            _collide_pair(objs[i], objs[j], groups[i], groups[j])


PEN_SLOP = 0.4          # 允许的浅重叠：贴在一起的两只猫不再抖
MAX_PEN_PUSH = 3.0      # 单帧位置修正上限：深穿插时也不会一帧弹飞


def _collide_pair(a, b, a_chunks, b_chunks) -> None:
    """一对同层实体的 chunk 圆重叠推开。

    位置：按质量分摊分离（带 slop 与单帧上限），**不再把修正量当冲量**——
    原版 BodyChunk 互推只有位置分离，把穿透深度写进速度会让贴在一起的两只猫
    越挤越快（顶端互挤→剧烈弹射）。
    速度：只按完全非弹性消掉互相接近的分量（无弹性碰撞）。
    """
    for ca in a_chunks:
        if not ca.collide_with_objects:
            continue
        for cb in b_chunks:
            if not cb.collide_with_objects:
                continue
            rad_sum = ca.rad + cb.rad
            dx, dy = cb.x - ca.x, cb.y - ca.y
            dist = math.hypot(dx, dy)
            if dist >= rad_sum:
                continue
            # 果/石/矛等物件把自己当 chunk 暴露，没有 pinned 字段
            pin_a = bool(getattr(ca, "pinned", False))
            pin_b = bool(getattr(cb, "pinned", False))
            if pin_a and pin_b:
                continue
            if dist < 1e-9:                     # 完全重合：退化取横向
                ux, uy, dist = 1.0, 0.0, 0.0
            else:
                ux, uy = dx / dist, dy / dist
            pen = rad_sum - dist                # 穿透深度
            if pen > PEN_SLOP:
                push = min(pen - PEN_SLOP, MAX_PEN_PUSH)
                if pin_a:
                    ka, kb = 0.0, 1.0
                elif pin_b:
                    ka, kb = 1.0, 0.0
                else:
                    tot = ca.mass + cb.mass
                    ka, kb = cb.mass / tot, ca.mass / tot   # 轻的挪得多
                ca.x -= ux * push * ka
                ca.y -= uy * push * ka
                cb.x += ux * push * kb
                cb.y += uy * push * kb
            rel = (cb.vx - ca.vx) * ux + (cb.vy - ca.vy) * uy
            if rel >= 0.0:
                continue
            ma, mb = max(ca.mass, 1e-6), max(cb.mass, 1e-6)
            inv_a = 0.0 if pin_a else 1.0 / ma
            inv_b = 0.0 if pin_b else 1.0 / mb
            inv = inv_a + inv_b
            if inv <= 0.0:
                continue
            j = -rel / inv
            ca.vx -= ux * j * inv_a
            ca.vy -= uy * j * inv_a
            cb.vx += ux * j * inv_b
            cb.vy += uy * j * inv_b
