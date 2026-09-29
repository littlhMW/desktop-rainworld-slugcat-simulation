# -*- coding: utf-8 -*-
"""蜥蜴 AI 的分层：感知 → 记忆 → 行为效用 → 接近规划 → 动作。

原版 LizardAI 的味道不在参数，而在「目标只是目标」：PreyTracker /
ThreatTracker / AgressionTracker / LurkTracker / NoiseTracker / PackTracker
各自独立收集信息，Behavior 效用决定当前做什么，动作层（走路 / 起跳 / 伏击 /
扑咬）再自己决定怎么靠近。旧版把这三件事压成「选一个坐标 → 朝它飞过去」，
所以看起来像几个优先级状态 + 距离追踪。

这里只放与渲染、物理无关的那几层；lizard.py 负责把结果落到速度和链体上。

**巢穴**：桌宠没有真房间出口，屏幕左右两侧就是两个 VirtualDen。猎物被叼回
巢穴 = 到达后放下并咬死。以后真要接房间 / 管道，只换 DenProvider，不用动
LizardAI —— 它只知道「我有一个 den_pos」。
"""
from __future__ import annotations

import math

from ..core.units import clampf

# ── 虚拟巢穴 ──
DEN_MARGIN = 34.0             # 巢穴落点距屏幕边缘（= 旧 CARRY_CORNER_MARGIN）
DEN_KIND = "virtual_den"
DEN_ARRIVE_R = 22.0           # 距巢穴多近算「到了」

# ── 记忆：原版 forgetDelay 换成置信度（看得见就涨，看不见就衰减）──
CONF_UP = 0.12                # 每帧看见的增益
CONF_DECAY = 0.975            # 看不见时的衰减
CONF_HUNT = 0.55              # 高置信度 → 继续追
CONF_INVESTIGATE = 0.18       # 中置信度 → 去最后看见的位置找
CONF_LOSE = 0.12              # 低于它就彻底忘掉

# ── 视线 ──
LOS_STEP = 10.0               # 视线采样步长（像素）

# ── 猎物归属：原版「咬倒的猎物归我」 ──
PREY_CLAIM_TICKS = 900        # 归属保留时长（搬运中每帧续约）

# ── 巢穴搬运时对竞争者的反应 ──
WARN_R = 150.0                # 竞争者进这个圈就警告
CARRY_HURRY = 1.35            # 被盯上时加速回巢
DOMINANCE_DEFER = 0.06        # 支配度差这么多就认怂退出竞争
SUBMIT_TICKS = 600            # 认怂记忆保留时长
RESPECT_TICKS = 900

# ── 黄蜥 Pack：共享的是「猎物情报」，不是「站在一起」 ──
PACK_ALERT_TICKS = 150        # 情报保鲜
PACK_FLANK = 74.0             # 收到情报后的包夹偏移（避免全挤同一个点）

# ── 接近规划：起跳点 / 落点搜索 ──
JUMP_DY = 30.0                # 目标高出这么多才考虑找起跳点
LAUNCH_SPAN = 96.0            # 起跳点搜索范围（目标两侧）
LAUNCH_STEP = 12.0
LAUNCH_WALL_PAD = 26.0        # 起跳点离墙至少这么远
AIR_TICKS = 140               # 弧线模拟上限
APPROACH_OK = 64.0            # 落点距目标这么近就算「跳过去够得着」
JUMP_ACCEPT = 0.35            # 起跳评分门槛（再乘品种的 jump 倾向）
JUMP_SLACK = 0.90
LURK_MIN_R = 168.0            # 伏击型品种：猎物比这远就原地等

# 每个品种对「怎么靠近」的偏好：同一套 movement utility，只改权重。
# travel=绕路代价 / land=落点误差 / wall=贴墙风险 / angle=接近角度
# jump=起跳倾向（越大越愿意为省路去跳）/ lurk=伏击倾向（白蜥、蝾螈）
APPROACH_PREFS = {
    "pink": dict(travel=0.8, land=1.2, wall=1.5, angle=0.7, jump=0.55, lurk=0.0),
    "green": dict(travel=0.5, land=1.0, wall=1.8, angle=0.5, jump=0.30, lurk=0.0),
    "blue": dict(travel=0.9, land=1.1, wall=0.9, angle=0.8, jump=0.95, lurk=0.10),
    "cyan": dict(travel=0.9, land=1.1, wall=0.9, angle=0.8, jump=0.95, lurk=0.10),
    "white": dict(travel=0.7, land=1.3, wall=1.2, angle=0.9, jump=0.70, lurk=0.90),
    "yellow": dict(travel=0.8, land=1.2, wall=1.3, angle=0.7, jump=0.60, lurk=0.0),
    "red": dict(travel=0.6, land=0.9, wall=2.2, angle=0.4, jump=1.00, lurk=0.0),
    "black": dict(travel=0.8, land=1.2, wall=1.5, angle=0.7, jump=0.50, lurk=0.10),
    "salamander": dict(travel=0.7, land=1.3, wall=1.2, angle=0.9, jump=0.70, lurk=0.90),
}
DEFAULT_PREFS = dict(travel=0.8, land=1.2, wall=1.5, angle=0.7, jump=0.55, lurk=0.0)


def prefs_for(key: str) -> dict:
    """品种 → 接近偏好（同一套 utility，只是权重不同）。"""
    return APPROACH_PREFS.get(key, DEFAULT_PREFS)


# ══ 巢穴 ══
class Den:
    """一个巢穴落点。桌宠里就是屏幕左右两侧的虚拟巢穴。"""

    __slots__ = ("x", "y", "side", "kind")

    def __init__(self, x, y, side=0, kind=DEN_KIND):
        self.x = float(x)
        self.y = float(y)
        self.side = int(side)          # -1 左 / +1 右
        self.kind = kind

    def __repr__(self):
        return "Den(%.0f, %.0f, side=%d, %s)" % (self.x, self.y, self.side, self.kind)


def virtual_dens(WL: float, HL: float, stand_h: float):
    """屏幕左右两个虚拟巢穴（y 取地面）。"""
    y = HL - max(0.0, stand_h)
    return (Den(DEN_MARGIN, y, -1), Den(WL - DEN_MARGIN, y, +1))


def choose_den(WL: float, HL: float, stand_h: float, prey_x: float) -> Den:
    """挑一个巢穴：离猎物更近的那一侧。

    只在**开始搬运**的时候调一次 —— 原版 ReturnPrey 抓到猎物就定下 den，
    之后一路走到底；不能走到屏幕中间又换成另一侧（那会让搬运来回抽风）。
    """
    left, right = virtual_dens(WL, HL, stand_h)
    return left if abs(prey_x - left.x) <= abs(prey_x - right.x) else right


# ══ 感知 ══
class Observation:
    """这一帧「看到的一个东西」：目标 + 位置 + 距离 + 关系权重 + 可见性。"""

    __slots__ = ("obj", "x", "y", "dist", "kind", "weight", "visual", "visible",
                 "los", "dead", "fainted", "stance", "owner", "side")

    def __init__(self, obj, x, y, dist, kind, weight=1.0, visual=1.0,
                 visible=True, dead=False, fainted=False, stance="stand",
                 owner=None, side=0, los=True):
        self.obj = obj
        self.x = float(x)
        self.y = float(y)
        self.dist = float(dist)
        self.kind = kind              # cat / prey / threat / rival / pack
        self.weight = float(weight)
        self.visual = float(visual)   # 视野锥得分（1 = 正前方）
        self.visible = bool(visible)
        self.los = bool(los)          # 视线没被挡（不含视野锥）
        self.dead = bool(dead)
        self.fainted = bool(fainted)
        self.stance = stance          # 猫的姿态（Crawl 更难被盯上）
        self.owner = owner            # 这只猎物已经归谁（别的蜥蜴）——没有则 None
        self.side = int(side)         # 相对自己的左右（-1 左 / +1 右）

    @property
    def score(self) -> float:
        """排序分：距离 / 关系权重（越小越优先）。"""
        return self.dist / max(0.05, self.weight)


def _seg_hit(ax, ay, bx, by, cx, cy, dx, dy) -> bool:
    """线段 AB 与线段 CD 是否相交（标准跨立判定）。"""

    def cross(ox, oy, px, py, qx, qy):
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    d1 = cross(cx, cy, dx, dy, ax, ay)
    d2 = cross(cx, cy, dx, dy, bx, by)
    d3 = cross(ax, ay, bx, by, cx, cy)
    d4 = cross(ax, ay, bx, by, dx, dy)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def prune_blockers(x0, y0, x1, y1, segs=(), circles=(), pad=2.0):
    """排掉「贴着起点或终点」的遮挡物。

    蜥蜴自己的身子、以及**目标本人**就贴在线段两端：不排掉的话谁都看不见谁
    （站在杆子边上的猎物也会被认为被杆子挡住）。
    """
    keep_segs = []
    for seg in segs:
        ax, ay, bx, by, half = seg
        if _seg_circle(x0, y0, ax, ay, bx, by, half + pad):
            continue
        if _seg_circle(x1, y1, ax, ay, bx, by, half + pad):
            continue
        keep_segs.append(seg)
    keep_circles = []
    for (cx, cy, r) in circles:
        if math.hypot(cx - x0, cy - y0) <= r + pad:
            continue
        if math.hypot(cx - x1, cy - y1) <= r + pad:
            continue
        keep_circles.append((cx, cy, r))
    return tuple(keep_segs), tuple(keep_circles)


def los_blocked(x0, y0, x1, y1, segs=(), circles=()) -> bool:
    """两点之间有没有被挡（杆子 / 石堆 / 别的生物）。

    原版视线受环境与目标可接近性影响；桌宠里能挡视线的东西就是杆子（线段）
    和体型够大的生物（圆）。只看线段与障碍相交，不做逐像素采样。
    """
    if not segs and not circles:
        return False
    segs, circles = prune_blockers(x0, y0, x1, y1, segs, circles)
    if not segs and not circles:
        return False
    for (ax, ay, bx, by, half) in segs:
        # 把障碍加粗成 ±half：直接和两段线段求交（half 已折进端点外扩的判断）
        if _seg_hit(x0, y0, x1, y1, ax, ay, bx, by):
            return True
        if half > 0.0:
            # 加粗：以端点为圆心、half 为半径的圆也挡
            for (px, py, rr) in ((ax, ay, half), (bx, by, half)):
                if _seg_circle(x0, y0, x1, y1, px, py, rr):
                    return True
    for (cx, cy, r) in circles:
        if _seg_circle(x0, y0, x1, y1, cx, cy, r):
            return True
    return False


def _seg_circle(x0, y0, x1, y1, cx, cy, r) -> bool:
    """线段到圆心距离 < r。"""
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(cx - x0, cy - y0) < r
    t = clampf(((cx - x0) * dx + (cy - y0) * dy) / L2, 0.0, 1.0)
    return math.hypot(cx - (x0 + t * dx), cy - (y0 + t * dy)) < r


# ══ 记忆（原版 PreyTracker 的 forget 计时换成置信度）══
class Memory:
    """「我上次在哪看见它」：看得见就刷新并加置信，看不见就缓慢衰减。"""

    __slots__ = ("obj", "last_pos", "confidence", "last_seen_tick", "kind")

    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.obj = None
        self.last_pos = None
        self.confidence = 0.0
        self.last_seen_tick = -10 ** 9
        self.kind = ""

    def see(self, obj, pos, tick, kind="cat") -> None:
        if obj is not self.obj:
            self.obj = obj
            self.confidence = 0.30          # 第一次看见：先有个低置信度
        self.last_pos = (float(pos[0]), float(pos[1]))
        self.last_seen_tick = int(tick)
        self.kind = kind
        self.confidence = min(1.0, self.confidence + CONF_UP)

    def miss(self) -> None:
        """这一帧没看见：衰减，但**不立刻清空**（蜥蜴会先去最后看见的地方找）。"""
        if self.obj is None:
            return
        self.confidence *= CONF_DECAY
        if self.confidence < CONF_LOSE:
            self.clear()

    def holds(self, obj=None, tick=None) -> bool:
        if self.obj is None or not self.last_pos:
            return False
        if obj is not None and self.obj is not obj:
            return False
        return self.confidence > CONF_LOSE

    @property
    def hunting(self) -> bool:
        return self.obj is not None and self.confidence >= CONF_HUNT

    @property
    def searching(self) -> bool:
        return (self.obj is not None and self.last_pos is not None
                and CONF_INVESTIGATE <= self.confidence < CONF_HUNT)


# ══ 猎物归属（原版 PreyTracker）══
class PreyTracker:
    """「这只是我的猎物」：咬倒 / 咬死之后归我，直到带回巢穴。

    原版猎物归谁不是全场共享的事实，而是每只蜥蜴自己的记录：追上、咬倒的
    那只才算数。路过的另一只看到一具昏迷的猫，只有在这具猫「没有主人」时才
    会接手。
    """

    __slots__ = ("obj", "state", "killed", "fainted", "claim_tick", "owner")

    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.obj = None
        self.owner = None
        self.state = "none"          # none / hunting / downed / delivered
        self.killed = False
        self.fainted = False
        self.claim_tick = -10 ** 9

    def claim(self, obj, tick, *, fainted=False, killed=False) -> None:
        """咬倒 / 咬死一只猎物 → 归我。"""
        self.obj = self.owner = obj
        self.fainted = bool(fainted)
        self.killed = bool(killed)
        self.claim_tick = int(tick)
        self.state = "downed"

    def hunting(self, obj, tick) -> None:
        """只是盯上了，还没咬倒：记一笔兴趣，但不构成归属。"""
        if self.obj is not obj:
            self.obj, self.owner = obj, None
            self.killed = self.fainted = False
            self.state = "hunting"
        self.claim_tick = int(tick)

    def refresh(self, tick) -> None:
        if self.owner is not None:
            self.claim_tick = int(tick)

    def owns(self, obj, tick) -> bool:
        return (self.owner is not None and self.owner is obj
                and int(tick) - self.claim_tick <= PREY_CLAIM_TICKS)

    def delivered(self, tick) -> None:
        self.state = "delivered"
        self.owner = None
        self.claim_tick = int(tick)

    def release(self) -> None:
        """松口 / 目标没了：归属也跟着作废（否则会一直占着一具不存在的猎物）。"""
        self.clear()


# ══ 社交记忆（原版 SocialMemory：竞争 → 判断支配 → 退让 → 记住）══
class SocialMemory:
    """同族之间的关系：支配度、认怂、敬意、怨气。"""

    __slots__ = ("dominance", "submitted_to", "submit_tick", "respect", "resentment")

    def __init__(self, dominance: float = 0.5):
        self.dominance = float(dominance)
        self.submitted_to = None
        self.submit_tick = -10 ** 9
        self.respect = {}            # id(other) → (值, tick)
        self.resentment = {}         # id(other) → (值, tick)

    def note_respect(self, other, amount: float, tick: int) -> None:
        key = id(other)
        cur = self.respect.get(key, (0.0, tick))[0]
        self.respect[key] = (clampf(cur + amount, 0.0, 1.0), int(tick))

    def note_resentment(self, other, amount: float, tick: int) -> None:
        key = id(other)
        cur = self.resentment.get(key, (0.0, tick))[0]
        self.resentment[key] = (clampf(cur + amount, 0.0, 1.0), int(tick))

    def submit(self, other, tick: int) -> None:
        """认怂：不再主动抢它正在争的东西。"""
        self.submitted_to = other
        self.submit_tick = int(tick)
        self.note_respect(other, 0.35, tick)

    def defers_to(self, other, tick: int) -> bool:
        """现在是否还认怂于它。"""
        if other is None or self.submitted_to is not other:
            return False
        if int(tick) - self.submit_tick > SUBMIT_TICKS:
            self.submitted_to = None
            return False
        return True

    def respect_of(self, other, tick: int) -> float:
        v = self.respect.get(id(other))
        if v is None or int(tick) - v[1] > RESPECT_TICKS:
            return 0.0
        return v[0]

    def resents(self, other, tick: int) -> float:
        v = self.resentment.get(id(other))
        if v is None or int(tick) - v[1] > RESPECT_TICKS:
            return 0.0
        return v[0]

    def prune(self, tick: int) -> None:
        for d in (self.respect, self.resentment):
            for key, (_v, t) in list(d.items()):
                if int(tick) - t > RESPECT_TICKS:
                    del d[key]


# ══ 黄蜥 Pack：猎物情报 ══
class PackAlert:
    """一条「谁在哪看见了猎物」的情报（原版黄蜥群体通信）。"""

    __slots__ = ("x", "y", "obj", "tick", "leader", "confidence")

    def __init__(self, x, y, obj, tick, leader=0, confidence=1.0):
        self.x = float(x)
        self.y = float(y)
        self.obj = obj
        self.tick = int(tick)
        self.leader = int(leader)
        self.confidence = float(confidence)

    def fresh(self, tick: int) -> bool:
        return int(tick) - self.tick <= PACK_ALERT_TICKS

    def decayed(self, tick: int) -> "PackAlert":
        """转发一次就旧一点：消息传得越远越模糊（原版通信也有衰减）。"""
        return PackAlert(self.x, self.y, self.obj, int(tick), self.leader,
                         max(0.2, self.confidence - 0.25))


def flank_offset(lizard_id: int) -> float:
    """包夹偏移：四只黄蜥不要全挤在同一个点（前 / 右 / 左 / 后）。"""
    seq = (0.0, PACK_FLANK, -PACK_FLANK, 2.0 * PACK_FLANK)
    return seq[int(lizard_id) % len(seq)]


# ══ 接近规划 ══
class ApproachPlan:
    """「怎么过去」：直接冲 / 先走到起跳点再跳 / 原地伏击等它靠近。"""

    __slots__ = ("mode", "target", "launch", "expires", "reason", "score")

    def __init__(self, mode, target, launch=None, expires=0, reason="", score=0.0):
        self.mode = mode              # direct / jump / lurk
        self.target = target          # 这一帧要去的点
        self.launch = launch          # 起跳点（mode=jump 时）
        self.expires = int(expires)
        self.reason = reason
        self.score = float(score)

    def alive(self, tick: int) -> bool:
        return int(tick) <= self.expires

    def __repr__(self):
        return "ApproachPlan(%s, %s, launch=%s, %s)" % (
            self.mode, self.target, self.launch, self.reason)


def sim_arc(x0, y0, vx, vy, floor, gravity, air_friction, ticks=AIR_TICKS):
    """从起跳点积分一条跳跃弧（和蜥蜴本体同一套重力/阻力）。"""
    pts = []
    x, y = float(x0), float(y0)
    for _ in range(int(ticks)):
        vx *= air_friction
        vy = (vy + gravity) * air_friction
        x += vx
        y += vy
        pts.append((x, y))
        if y >= floor:
            break
    return pts


def plan_approach(prey_x, prey_y, my_x, my_y, floor_y, WL, reach, prefs,
                  gravity, hop, air_friction, sprint=1.0, base_speed=4.0,
                  tick=0, ttl=20):
    """给「想吃的那个东西」规划一条接近路线。

    同层直接冲（原版也是直线扑），够高就先找起跳点：遍历目标两侧的落点，
    用本体同样的重力模拟弧线，按品种权重给「绕路 / 落点误差 / 贴墙 / 接近角度」
    打分，选最优的那条。伏击型品种（白蜥 / 蝾螈）在猎物还远时原地等。
    """
    prefs = prefs or DEFAULT_PREFS
    dy = my_y - prey_y                      # > 0：猎物在我上方
    if prefs.get("lurk", 0.0) >= 0.5 and abs(prey_x - my_x) > LURK_MIN_R and dy > 8.0:
        return ApproachPlan("lurk", (my_x, my_y), None, tick + ttl, "ambush")
    if dy <= JUMP_DY:
        return ApproachPlan("direct", (prey_x, prey_y), None, tick + ttl, "same level")

    hop = -abs(hop)
    best, best_score = None, None
    lx = prey_x - LAUNCH_SPAN
    while lx <= prey_x + LAUNCH_SPAN + 1e-6:
        px = clampf(lx, LAUNCH_WALL_PAD, max(LAUNCH_WALL_PAD, WL - LAUNCH_WALL_PAD))
        d0 = prey_x - px
        if abs(d0) < 4.0:
            lx += LAUNCH_STEP
            continue
        vx = (1.0 if d0 > 0 else -1.0) * base_speed * 0.8 * sprint
        pts = sim_arc(px, floor_y, vx, hop, floor_y, gravity, air_friction)
        if not pts:
            lx += LAUNCH_STEP
            continue
        min_d = min(math.hypot(qx - prey_x, qy - prey_y) for qx, qy in pts)
        land_x, land_y = pts[-1]
        land_err = math.hypot(land_x - prey_x, land_y - prey_y)
        travel = abs(land_x - px)
        wall_risk = 0.0
        if (px <= LAUNCH_WALL_PAD + 12.0 and vx < 0) or \
           (px >= WL - LAUNCH_WALL_PAD - 12.0 and vx > 0):
            wall_risk = 1.0
        span = max(1.0, abs(prey_x - px))
        angle = clampf(1.0 - abs(land_x - px) / span, 0.0, 1.0)
        score = (prefs.get("travel", 0.8) * travel / 120.0
                 + prefs.get("land", 1.2) * min_d / 80.0
                 + prefs.get("wall", 1.5) * wall_risk
                 - prefs.get("angle", 0.7) * angle)
        ok = (min_d <= reach * 1.6) or (land_err <= APPROACH_OK)
        if ok and (best_score is None or score < best_score):
            best, best_score = (px, floor_y), score
        lx += LAUNCH_STEP
    if best is None:
        return ApproachPlan("direct", (prey_x, prey_y), None, tick + ttl, "no arc")
    limit = JUMP_ACCEPT + JUMP_SLACK * prefs.get("jump", 0.55)
    if best_score > limit:
        return ApproachPlan("direct", (prey_x, prey_y), None, tick + ttl,
                            "arc too costly %.2f > %.2f" % (best_score, limit))
    return ApproachPlan("jump", best, best, tick + ttl, "launch search", best_score)
