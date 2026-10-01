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
from ..planning.navgraph import anchor_key
from .terrain import ROUTE_ONE_WAY, ROUTE_RETURNABLE, ROUTE_SAFE

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

# ── AI 时间片（文档 §37）──
# 感知不必每 tick 重建：每只蜥蜴按 id 错开，平均每 PERCEIVE_EVERY tick 扫描一次，
# 其余 tick 复用上次的观察（只刷新地形 / 遮挡 / 同伴 / 归属这些便宜字段）。
# 物理、攻击碰撞、抓取仍然逐 tick。8 只蜥蜴自然分成 0,4→tick0 / 1,5→tick1 的错峰。
PERCEIVE_EVERY = 3

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
ARRIVE_X = 14.0                # 地形路线的「这一段走到了」横向容差

# ── 路线哲学（文档 §5）：行为先给意图，路线类型由这里决定 ──
def route_kinds(intent, prefs=None):
    """行为意图 → 路线类型链（从严到松，TerrainQuery 取第一个成立的）。

    原版蜥蜴的路径代价本来就分场景：追猎物可以单向（掉了就掉了），
    叼着猎物回巢必须留退路（原版 CarryObject 不会往死角钻），逃跑必须安全，
    伏击型只肯走有退路的路。旧实现一律 RETURNABLE，于是上层要么拿到路线、
    要么直接没有 —— 「路线哲学」这一层等于不存在（文档 §5/§19）。
    """
    p = prefs or DEFAULT_PREFS
    if intent == "hunt":
        # 伏击型（白蜥 / 蝾螈）追猎物也要留退路；冲刺型愿意走单向
        return ((ROUTE_RETURNABLE, ROUTE_ONE_WAY)
                if p.get("lurk", 0.0) >= 0.5
                else (ROUTE_ONE_WAY, ROUTE_RETURNABLE))
    if intent == "carry":
        return (ROUTE_SAFE, ROUTE_RETURNABLE)      # 叼着猎物：不冒险、留退路
    if intent == "flee":
        return (ROUTE_SAFE, ROUTE_RETURNABLE, ROUTE_ONE_WAY)
    if intent in ("pack", "flank"):
        return (ROUTE_ONE_WAY, ROUTE_RETURNABLE)   # 包夹：只要过得去
    if intent == "investigate":
        return (ROUTE_RETURNABLE, ROUTE_ONE_WAY)   # 去看看：保守
    return (ROUTE_RETURNABLE,)


# ── 动态目标：plan 不能比观察活得更久（文档 §12）──
TARGET_DRIFT = 24.0           # 目标漂移超过这么远就立刻重规划，不等 TTL

# ── 包夹 / 伏击：都从统一地形里挑点，而不是坐标偏移（文档 §14/§15）──
STAND_SAMPLE = 36.0           # 面上采样落点的间距
PACK_SLOT_R = 260.0           # 包夹点离猎物最远这么远
PACK_SLOT_MIN = 44.0          # 也不能贴脸
AMBUSH_R = 420.0              # 伏击点搜索半径
AMBUSH_MIN_R = 70.0           # 太近就不算伏击
AMBUSH_WAIT_R = 190.0         # 猎物进这个圈就扑（伏击点为这个距离优化）
AMBUSH_CONE = 0.25            # 落在猎物视野正前方这么多以内就不算伏击点

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
                 "los", "dead", "fainted", "stance", "claimed_by", "side")

    def __init__(self, obj, x, y, dist, kind, weight=1.0, visual=1.0,
                 visible=True, dead=False, fainted=False, stance="stand",
                 claimed_by=None, side=0, los=True):
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
        # 这只猎物已经被**别的蜥蜴**认领了吗（文档 §18：owner 改名 claimed_by，
        # 免得和 PreyTracker 自己那份归属记录同名却语义不同）——没有则 None。
        self.claimed_by = claimed_by
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


def prune_side(x, y, segs=(), circles=(), pad=2.0):
    """只按**一端**（起点或终点）裁剪遮挡物，返回保留项的下标集合。

    `prune_blockers` 的两端裁剪互相独立（不碰起点 **且** 不碰终点才留下），所以
    可以拆开缓存：起点那边每只蜥蜴一 tick 只算一次，终点那边每个目标一 tick 只算
    一次；两个下标集合取交集就和逐对跑一遍 `prune_blockers` 等价。文档 §37。
    """
    keep_segs = []
    for i, (ax, ay, bx, by, half) in enumerate(segs):
        if _seg_circle(x, y, ax, ay, bx, by, half + pad):
            continue
        keep_segs.append(i)
    keep_circles = []
    for i, (cx, cy, r) in enumerate(circles):
        if math.hypot(cx - x, cy - y) <= r + pad:
            continue
        keep_circles.append(i)
    return (frozenset(keep_segs), frozenset(keep_circles))


def los_blocked_idx(x0, y0, x1, y1, segs, circles, start_keep, end_keep) -> bool:
    """用两端各自裁好的下标集合做视线判定（避免重复跑 `prune_blockers`）。"""
    ks, kc = start_keep
    es, ec = end_keep
    for i, (ax, ay, bx, by, half) in enumerate(segs):
        if i not in ks or i not in es:
            continue
        if _seg_hit(x0, y0, x1, y1, ax, ay, bx, by):
            return True
        if half > 0.0:
            for (px, py, rr) in ((ax, ay, half), (bx, by, half)):
                if _seg_circle(x0, y0, x1, y1, px, py, rr):
                    return True
    for i, (cx, cy, r) in enumerate(circles):
        if i not in kc or i not in ec:
            continue
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
        """这一帧没看见：衰减，但**不立刻清空**（蜥蜴会先去最后看见的地方找）。

        时间片（文档 §37）下跳过感知的那几 tick 也各调用一次 —— 一次 = 一 tick，
        所以有效衰减速率和逐帧跑时完全一致，不需要按 stride 补偿。
        """
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

    # 「归属」只有一份记录：obj + state（文档 §18：删掉与 obj 恒等的 owner）。
    __slots__ = ("obj", "state", "killed", "fainted", "claim_tick")

    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.obj = None
        self.state = "none"          # none / hunting / downed / delivered
        self.killed = False
        self.fainted = False
        self.claim_tick = -10 ** 9

    def claim(self, obj, tick, *, fainted=False, killed=False) -> None:
        """咬倒 / 咬死一只猎物 → 归我。"""
        self.obj = obj
        self.fainted = bool(fainted)
        self.killed = bool(killed)
        self.claim_tick = int(tick)
        self.state = "downed"

    def hunting(self, obj, tick) -> None:
        """只是盯上了，还没咬倒：记一笔兴趣，但不构成归属。"""
        if self.obj is not obj:
            self.obj, self.state = obj, "hunting"
            self.killed = self.fainted = False
        self.claim_tick = int(tick)

    def refresh(self, tick) -> None:
        if self.owned():
            self.claim_tick = int(tick)

    def owned(self) -> bool:
        """咬倒了都还没交出去 = 这只真的归我（hunting 只是兴趣）。"""
        return self.obj is not None and self.state == "downed"

    def owns(self, obj, tick) -> bool:
        return (self.owned() and self.obj is obj
                and int(tick) - self.claim_tick <= PREY_CLAIM_TICKS)

    def delivered(self, tick) -> None:
        self.state = "delivered"
        self.claim_tick = int(tick)

    def release(self) -> None:
        """松口 / 目标没了：归属也跟着作废（否则会一直占着一具不存在的猎物）。"""
        self.clear()


class PreyState(PreyTracker):
    """「猎物这条链」的**唯一状态对象**（文档 §17）。

    旧版把同一条链（看到 → 追踪 → 咬倒 → 占有 → 叼住 → 回巢 → 放下 → 守卫）拆在
    PreyTracker + target/target_obj + carry_obj/carry_body/carry_den + guard_obj +
    mem 里，于是到处是「A is not None and B is not None」这种组合判断。现在只有一个
    对象，并且链走到哪一步由 `phase` 一处说了算：

        idle   没在管猎物
        track  盯上了（target_obj 非空）
        downed 咬倒了、还没叼起来（原版 PreyTracker.owned）
        carry  嘴里叼着（原版 CarryObject 非空）
        guard  放下之后在巢穴边守着

    继承 PreyTracker：归属那一段（obj/state/killed/fainted/claim_tick 与
    claim/hunting/refresh/owns/owned/delivered/release）一个字节都没改，
    所以 `self.prey.xxxx` 那些老调用照旧可用。
    """

    __slots__ = ("target", "target_obj", "carry_obj", "carry_body", "carry_corner",
                 "carry_den", "guard_obj", "guard_t", "mem")

    def __init__(self):
        super().__init__()
        # 导航目标点（可以只是「记忆里的位置」，不一定还有 target_obj）
        self.target = None
        self.target_obj = None
        # 回巢：carry_obj 是嘴里那只，carry_body 是它的身体（被钉住跟着嘴走），
        # carry_den 是**开始搬运时锁定的那个巢穴**（原版 ReturnPrey 的 den，定了
        # 就不换），carry_corner 只是它的左右符号。
        self.carry_obj = None
        self.carry_body = None
        self.carry_den = None
        self.carry_corner = 0
        # 刚送回巢穴的猎物：守一小会儿（原版回巢进食）
        self.guard_obj = None
        self.guard_t = 0
        # 「我上次在哪看见它」（原版 forgetCounter 换成置信度）
        self.mem = Memory()

    @property
    def carrying(self) -> bool:
        """嘴里正叼着东西（原版 CarryObject 非空）。"""
        return self.carry_body is not None

    @property
    def chasing(self) -> bool:
        """盯上了或叼着（原版 PreyTracker 有目标 / CarryObject 非空）。

        伪装、玩耍这类「我要不要装作没事」的判据用它 —— 只是守在巢穴边（guard）
        不算 chasing。
        """
        return self.target_obj is not None or self.carry_body is not None

    @property
    def phase(self) -> str:
        """这条链走到哪一步 —— 链上状态的唯一判据。"""
        if self.carry_body is not None:
            return "carry"
        if self.owned():
            return "downed"
        if self.guard_obj is not None:
            return "guard"
        if self.target_obj is not None:
            return "track"
        return "idle"

    @property
    def busy(self) -> bool:
        """手里有活（追着 / 占着 / 叼着 / 守着）：还要不要开始新的取食行为。"""
        return self.phase != "idle"

    def reset(self) -> None:
        """整条链归零（换目标 / 被吓跑 / 清零重来）：不只是归属那一段。"""
        self.clear()
        self.target = None
        self.target_obj = None
        self.carry_obj = None
        self.carry_body = None
        self.carry_den = None
        self.carry_corner = 0
        self.guard_obj = None
        self.guard_t = 0


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

    __slots__ = ("x", "y", "obj", "tick", "leader", "confidence", "hops")

    def __init__(self, x, y, obj, tick, leader=0, confidence=1.0, hops=0):
        self.x = float(x)
        self.y = float(y)
        self.obj = obj
        self.tick = int(tick)      # **第一次被看见**的 tick（原始时间戳，不随转发刷新）
        self.leader = int(leader)
        self.confidence = float(confidence)
        self.hops = int(hops)      # 被转发了多少次

    def fresh(self, tick: int) -> bool:
        return int(tick) - self.tick <= PACK_ALERT_TICKS

    def decayed(self, tick: int) -> "PackAlert":
        """转发一次就旧一点：消息传得越远越模糊（原版通信也有衰减）。

        `tick` 只用来兼容旧调用签名。**时间戳不再改成「现在」** —— 旧实现
        每次转发都把 tick 刷成当前 tick，于是 `fresh()` 永远成立，一条早就过期
        的情报能在群体里无限转发（文档 §16）。现在原始 tick 保留，衰减只体现在
        confidence 与 hops 上。
        """
        return PackAlert(self.x, self.y, self.obj, self.tick, self.leader,
                         max(0.2, self.confidence - 0.25), self.hops + 1)


def flank_offset(lizard_id: int) -> float:
    """包夹偏移：四只黄蜥不要全挤在同一个点（前 / 右 / 左 / 后）。"""
    seq = (0.0, PACK_FLANK, -PACK_FLANK, 2.0 * PACK_FLANK)
    return seq[int(lizard_id) % len(seq)]


def stand_anchors(terrain, caps, cx, cy, r, step=STAND_SAMPLE):
    """落点候选：统一地形里「能站的面」上采样出来的锚点（文档 §14/§15）。

    包夹点与伏击点都不再是「目标坐标 + X 偏移」：它们必须先是一块真的能站的
    地形，否则蜥蜴会朝着半空中的假点走。
    """
    out = []
    if terrain is None:
        return out
    for s in terrain.geom.floors(caps):
        if abs(s.y - cy) > r:
            continue
        lo = max(s.lo, cx - r)
        hi = min(s.hi, cx + r)
        if hi < lo:
            continue
        n = max(1, int((hi - lo) / step) + 1)
        for i in range(n + 1):
            x = lo + (hi - lo) * i / n
            if math.hypot(x - cx, s.y - cy) <= r:
                out.append((float(x), float(s.y)))
    return out


def _dir_of(dx, dy):
    n = math.hypot(dx, dy)
    return (1.0, 0.0) if n < 1e-6 else (dx / n, dy / n)


def pack_slots(terrain, caps, prey_x, prey_y, dir_x=1.0, dir_y=0.0, n=4):
    """黄蜥包夹点：猎物的前 / 后 / 左右（文档 §14）。

    原版 YellowAI.Pack 的成员拿到的是一条**路线**上的相对位置，不是「同一个
    目标点 + X 偏移」—— 那样四只黄蜥只会排成一列。这里先从统一地形里挑出猎物
    周围真正能站的落点，再按「前 / 后 / 侧向」挑四个，各成员自己按路线代价取
    最划算的那个（见 lizard._pack_tick），于是才是围过去。
    """
    pts = stand_anchors(terrain, caps, prey_x, prey_y, PACK_SLOT_R)
    if not pts:
        return ()
    dx, dy = _dir_of(dir_x, dir_y)
    cand = []
    for (px, py) in pts:
        rx, ry = px - prey_x, py - prey_y
        d = math.hypot(rx, ry)
        if d < PACK_SLOT_MIN:
            continue
        cand.append((px, py, d, rx * dx + ry * dy, -rx * dy + ry * dx))
    if not cand:
        return ()
    picks = [max(cand, key=lambda t: t[3] - 0.02 * abs(t[4])),      # 前：猎物去路
             max(cand, key=lambda t: -t[3] - 0.02 * abs(t[4])),      # 后：背侧
             max(cand, key=lambda t: t[4] - 0.02 * t[3]),            # 左
             max(cand, key=lambda t: -t[4] - 0.02 * t[3])]           # 右
    want = max(1, int(n))
    out, seen = [], set()
    for (px, py, _d, _f, _s) in picks[:want]:
        k = anchor_key(px, py)
        if k in seen:
            continue
        seen.add(k)
        out.append((px, py))
    if len(out) < want:
        # 平地上「左 / 右」没有独立分量（猎物方向就是横向）：退一步沿面把剩下的
        # 名额补成互不相邻的点 —— 总之不能让四只黄蜥挤在同一个位置。
        for (px, py, _d, _f, _s) in sorted(cand, key=lambda t: -t[3]):
            if len(out) >= want:
                break
            if all(math.hypot(px - qx, py - qy) >= PACK_SLOT_MIN for qx, qy in out):
                out.append((px, py))
    return tuple(out) or ((picks[0][0], picks[0][1]),)


def pack_slot_for(slots, lizard_id):
    """没有路线代价可算时的兜底分配：按 id 错开，别全挤在一个点。"""
    if not slots:
        return None
    return slots[int(lizard_id) % len(slots)]


def ambush_point(terrain, caps, my_x, my_y, prey_x, prey_y, dir_x=1.0, dir_y=0.0,
                 r=AMBUSH_R):
    """白蜥伏击点（文档 §15）：猎物看不见我、我够得着、最好在它的必经路上。

    「猎物看不见我」在原版靠 LurkTracker + 遮挡；这里用三条可判定的条件打分：
      ① 落点在猎物**行进方向的后 / 侧方**（不在它的视野正前方）；
      ② 落点与猎物之间有遮挡（杆 / 墙把视线切断 —— 真正「躲起来」）；
      ③ 离我近、离猎物约一个扑咬距离（AMBUSH_WAIT_R），过去不绕。
    返回 (x, y)；没有可用地形就 None（此时旧行为：原地等）。
    """
    pts = stand_anchors(terrain, caps, prey_x, prey_y, r)
    if not pts:
        return None
    dx, dy = _dir_of(dir_x, dir_y)
    best, bs = None, None
    for (px, py) in pts:
        rx, ry = px - prey_x, py - prey_y
        d = math.hypot(rx, ry)
        if d < AMBUSH_MIN_R:
            continue
        fwd = (rx * dx + ry * dy) / d
        if fwd > AMBUSH_CONE:
            continue                      # 正对着猎物的去路：是拦截，不是伏击
        hidden = 1.0 if terrain.los_blocked(px, py, prey_x, prey_y) else 0.0
        near_me = math.hypot(px - my_x, py - my_y)
        score = (0.9 * fwd + 0.004 * abs(d - AMBUSH_WAIT_R) - 0.8 * hidden
                 + 0.002 * near_me)
        if bs is None or score < bs:
            best, bs = (px, py), score
    return best


# ══ 接近规划 ══
class ApproachPlan:
    """「怎么过去」：直接冲 / 先走到起跳点再跳 / 原地伏击等它靠近。"""

    __slots__ = ("mode", "target", "launch", "expires", "reason", "score", "climb",
                 "legs", "anchor")

    def __init__(self, mode, target, launch=None, expires=0, reason="", score=0.0,
                 climb=None, legs=(), anchor=None):
        self.mode = mode              # direct / jump / lurk / climb_wall / climb_pole
        self.target = target          # 这一帧要去的点
        self.launch = launch          # 起跳点（mode=jump 时）
        self.expires = int(expires)
        self.reason = reason
        self.score = float(score)
        # mode=climb_* 时：(上墙点 x, 线顶, 线底, 向上=1/向下=-1)
        self.climb = climb
        # 地形层给的整条多段路线（terrain.Leg 的元组）；当前段恒为 legs[0]。
        # 有它时动作层照这一段走，走完下一 tick 重新问图 —— 于是「走到哪、
        # 从哪起跳」永远按当前位置算，不会拿旧节点的坐标硬冲。
        self.legs = tuple(legs or ())
        # 规划时目标在哪：动态目标漂走了就该重规划（文档 §12 的 target_drift）
        self.anchor = None if anchor is None else (float(anchor[0]), float(anchor[1]))

    def alive(self, tick: int) -> bool:
        return int(tick) <= self.expires

    def drifted(self, tx, ty, r=TARGET_DRIFT) -> bool:
        """目标从我规划时的位置漂走够远了吗（只看直接追人的那几种 plan）。"""
        if self.anchor is None:
            return False
        return math.hypot(float(tx) - self.anchor[0],
                          float(ty) - self.anchor[1]) > r

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


def _plan_from_legs(legs, my_x, tick, ttl, reason, anchor=None, force=False):
    """把地形层给的多段路线折成动作层认识的 ApproachPlan（当前段 = legs[0]）。

    反编译口径：原版蜥蜴拿到的是 LizardPather 给的 MovementConnection 序列，
    它只执行当前那一条，走完再要下一条。这里照做：

      walk / drop  → mode=direct + 目标点（动作层朝目标点走，落差交给重力）
      climb_*      → mode=climb_* + climb=(x, top, bot, dir)（交给 _step_wall）
      jump / hop   → mode=jump + launch=(起跳点)（交给 _approach_tick）

    全是 walk 段时返回 None：那说明目标本来就在同一层，直冲那套更好，
    也免得猫站在锚点（走完的终点）上不动 —— 除非 ``force``（Flee / Pack 这种
    自己要去某个「地形验证过的落点」的行为，平地也要照路线走）。
    """
    if not legs:
        return None
    i = 0
    while (i < len(legs) - 1 and legs[i].mode == "walk"
           and abs(legs[i].x - my_x) <= ARRIVE_X):
        i += 1                             # 已经站在这段走路的终点上：换下一段
    legs = tuple(legs[i:])
    if all(lg.mode == "walk" for lg in legs):
        if not force:
            return None
        return ApproachPlan("direct", (legs[-1].x, legs[-1].y), None, tick + ttl,
                            reason, 0.0, legs=legs, anchor=anchor)
    leg = legs[0]
    if leg.mode in ("climb_wall", "climb_pole", "climb_background"):
        return ApproachPlan(leg.mode, (leg.x, leg.y), None, tick + ttl, reason,
                            0.0, climb=(leg.x, leg.top, leg.bot, leg.up), legs=legs,
                            anchor=anchor)
    if leg.mode in ("jump", "hop"):
        return ApproachPlan("jump", (leg.tx, leg.ty), (leg.x, leg.y),
                            tick + ttl, reason, 0.0, legs=legs, anchor=anchor)
    gx, gy = leg.x, leg.y
    if leg.mode == "drop" and leg.tx is not None:
        gx, gy = leg.tx, leg.ty           # 掉下去：朝落点走，剩下的交给重力
    return ApproachPlan("direct", (gx, gy), None, tick + ttl, reason, 0.0,
                        legs=legs, anchor=anchor)


def _terrain_route(terrain, caps, my_x, my_y, prey_x, prey_y, tick, ttl,
                   kind=None, avoid=None, force=False):
    """问地形层：有没有一条正式的移动连接（MovementConnection）。

    反编译口径：原版蜥蜴拿到的是 LizardPather 给的 MovementConnection
    （Floor→Wall→Climb / Beam→Beam），不是动作层临时找一根竖线。这里先把
    整条多段路线（走 / 爬 / 跳 / 掉 / 换杆）折成 ApproachPlan；图里没有可用
    路线时，退回旧的单段「走 → 上墙 / 上杆」提示，保证不丢能力。

    ``kind``（文档 §5）是**这个行为**要的路线哲学（SAFE / RETURNABLE /
    ONE_WAY / RISKY / DEAD_END，可给一串从严到松）；``avoid`` 是导航黑名单。
    """
    if terrain is None or caps is None:
        return None
    route = terrain.route(my_x, my_y, prey_x, prey_y, caps, kind=kind, avoid=avoid)
    if route is not None:
        plan = _plan_from_legs(route.legs, my_x, tick, ttl,
                               "navgraph:%s" % route.kind,
                               anchor=(prey_x, prey_y), force=force)
        if plan is not None:
            plan.score = float(route.cost)     # score 在这里就是这条路的代价
            return plan
    hint = terrain.route_hint(my_x, my_y, prey_x, prey_y, caps)
    if hint is None:
        return None
    mode, sx, top, bot, up, reason = hint
    return ApproachPlan(mode, (sx, my_y), None, tick + ttl, reason, 0.0,
                        climb=(sx, top, bot, up))


def _launch_search(prey_x, prey_y, floor_y, WL, prefs, reach, hop, gravity,
                   air_friction, sprint, base_speed, cx=None, span=LAUNCH_SPAN):
    """起跳点搜索（Jump Executor 的本地那一半，文档 §6）。

    遍历目标两侧的落点，用本体同样的重力模拟弧线，按品种权重给「绕路 /
    落点误差 / 贴墙 / 接近角度」打分。它只回答「这一跳从哪儿起跳」，
    「该不该往那边跳、去哪个面」是统一导航图的事。
    """
    hop = -abs(hop)
    c = float(prey_x if cx is None else cx)
    best, best_score = None, None
    lx = c - span
    while lx <= c + span + 1e-6:
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
        sp = max(1.0, abs(prey_x - px))
        angle = clampf(1.0 - abs(land_x - px) / sp, 0.0, 1.0)
        score = (prefs.get("travel", 0.8) * travel / 120.0
                 + prefs.get("land", 1.2) * min_d / 80.0
                 + prefs.get("wall", 1.5) * wall_risk
                 - prefs.get("angle", 0.7) * angle)
        ok = (min_d <= reach * 1.6) or (land_err <= APPROACH_OK)
        if ok and (best_score is None or score < best_score):
            best, best_score = (px, floor_y), score
        lx += LAUNCH_STEP
    return best, best_score


def plan_approach(prey_x, prey_y, my_x, my_y, floor_y, WL, reach, prefs,
                  gravity, hop, air_friction, sprint=1.0, base_speed=4.0,
                  tick=0, ttl=20, terrain=None, caps=None, route_kind=None,
                  avoid=None, prey_dir=(1.0, 0.0)):
    """给「想吃的那个东西」规划一条接近路线。

    **职责（文档 §6）**：统一导航图先决定「去哪个面、怎么跨区域」—— 它给出的
    climb / jump / drop 边就是正式 MovementConnection，Jump 不再是压过它的一条
    heuristic；本函数只管两件局部的事：

      ① 同层目标直线扑（原版也是直线扑）；
      ② 那条 jump 边**具体从哪儿起跳**，交给 sim_arc() 在原地挑。

    旧版顺序反了：先自己试跳，试不出来才问图 —— 于是永远有两套 planner 打架。
    伏击型品种（白蜥 / 蝾螈）现在会用统一地形挑一个真正的伏击点（文档 §15），
    而不是只决定「不追」。
    """
    prefs = prefs or DEFAULT_PREFS
    dy = my_y - prey_y                      # > 0：猎物在我上方
    if prefs.get("lurk", 0.0) >= 0.5 and abs(prey_x - my_x) > LURK_MIN_R and dy > 8.0:
        seat = ambush_point(terrain, caps, my_x, my_y, prey_x, prey_y,
                            prey_dir[0], prey_dir[1])
        if seat is None:
            return ApproachPlan("lurk", (my_x, my_y), None, tick + ttl, "ambush",
                                anchor=(prey_x, prey_y))
        return ApproachPlan("lurk", seat, None, tick + ttl, "ambush:seat",
                            anchor=(prey_x, prey_y))
    if dy <= JUMP_DY:
        return ApproachPlan("direct", (prey_x, prey_y), None, tick + ttl,
                            "same level", anchor=(prey_x, prey_y))

    # ① 统一导航图先说：它会产生 walk / climb / jump / drop / hop 边
    nav = _terrain_route(terrain, caps, my_x, my_y, prey_x, prey_y, tick, ttl,
                         kind=route_kind, avoid=avoid)
    limit = JUMP_ACCEPT + JUMP_SLACK * prefs.get("jump", 0.55)
    if nav is not None and nav.mode != "direct":
        if nav.mode == "jump" and nav.launch is not None:
            # 图的 jump 边负责「往那边跳」，起跳点由本地弧线细化
            best, score = _launch_search(prey_x, prey_y, nav.launch[1], WL, prefs,
                                         reach, hop, gravity, air_friction, sprint,
                                         base_speed, cx=nav.launch[0],
                                         span=LAUNCH_SPAN * 0.5)
            if best is not None and score <= limit:
                return ApproachPlan("jump", best, best, tick + ttl,
                                    "navgraph:jump-edge", score,
                                    anchor=(prey_x, prey_y))
        return nav
    # ② 图里没有可用连接：局部起跳弧（同层够得着的跨层小跳）
    best, best_score = _launch_search(prey_x, prey_y, floor_y, WL, prefs, reach,
                                      hop, gravity, air_friction, sprint,
                                      base_speed)
    if best is not None and best_score <= limit:
        return ApproachPlan("jump", best, best, tick + ttl, "arc:launch",
                            best_score, anchor=(prey_x, prey_y))
    if nav is not None:
        return nav
    return ApproachPlan("direct", (prey_x, prey_y), None, tick + ttl, "no arc",
                        anchor=(prey_x, prey_y))
