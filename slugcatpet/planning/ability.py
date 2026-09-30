"""能力三问接口：can_touch / can_stay 回 Estimate，make_controller 回执行控制器。"""
from __future__ import annotations
import math

from dataclasses import dataclass

from ..behavior import tuning

# 控制器与执行器共用的状态字符串
RUNNING = "running"
DONE = "done"
GIVEUP = "giveup"
HOLD = "hold"          # 到位持续维持驻留：不重规划/不计超时/不计失败

# PlanExecutor 对消费方的返回值（HOLD 之外与控制器状态同名）
HOLDING = "holding"

# 规划模式
MODE_TOUCH = "touch"
MODE_STAY = "stay"


@dataclass(frozen=True)
class Estimate:
    """粗线性代价：预估耗时 tick / 预估体力开销。

    bonus / play 只在**排序**上有意义：bonus 是「这条方案还有线路之外的好处」
    （娱乐性跳等）的 tick 当量，play 标记这条候选不是「够得到」而是「够不到也想
    试一下」（光标高处的玩耍跳），消费方据此换一套概率与执行口径。
    """
    time_est: float
    energy_est: float
    bonus: float = 0.0
    play: bool = False


@dataclass
class Candidate:
    """一条已过体力门槛的候选方案。"""
    ability_key: str
    time_est: float
    energy_est: float
    _factory: object
    bonus: float = 0.0        # 排序加成（不改进 time_est：执行器的超时预算仍用真实耗时）
    play: bool = False        # True＝娱乐性候选（够不到也想试），不是可达解

    def make_controller(self):
        return self._factory()


class Ability:
    """能力基类；控制器协议：update() -> running|done|giveup，cancel() 清理。"""
    key = ""

    def __init__(self, pet):
        self.pet = pet

    def can_touch(self, goal):
        return None

    def can_stay(self, goal):
        return None

    def can_play(self, goal):
        """娱乐性候选：够不到、但值得「玩一下」时的方案（默认无）。

        与 can_touch 的区别是它**不做可达性判定**：只要求基础物理合法。只有明确
        问 play 的消费方（追鼠标那种玩耍语境）才会拿到它。
        """
        return None

    def make_controller(self, goal):
        raise NotImplementedError


class PointTarget:
    """reach_for 兼容的点目标（.x/.y）。"""
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y


def walk_band(pet):
    """可行走 x 区间 [xmin, xmax] —— 只留**猫自己脚下这一段**。

    庇护所墙体是物理上的真障碍，规划层必须认得：旧版直接给整条世界走带，
    于是「往右直走就到」被当成可行，实际是顶着墙走、重规划还是同一条。
    这里按猫的站立高度把「这一步跨不过去的墙」挖掉，返回含猫的那一段；
    走廊层（庇护所底下那条通路）天然是通的，所以进门不受影响。
    """
    body = pet.body
    xmin = getattr(body, "walk_min", None)
    xmax = getattr(body, "walk_max", None)
    lo = 0.0 if xmin is None else xmin
    hi = pet._WL if xmax is None else xmax
    return walk_span(lo, hi, body.chunk1.x, pet.stand_h())


def walk_span(lo, hi, x, y, solids=None):
    """[lo,hi] 里挖掉高度 y 上的庇护所墙体，返回**含 x** 的那一段。"""
    from ..core import chunkphys
    if hi < lo:
        lo, hi = hi, lo
    rows = chunkphys.cat_solids() if solids is None else solids
    cuts = []
    for (a0, b0, a1, b1) in rows:
        if a1 <= a0 or b1 <= b0:
            continue
        if b1 <= y - tuning.WALK_BODY_H:      # 底边高过猫头：从下面走过去
            continue
        if b0 >= y - tuning.WALK_STEP_UP:     # 顶边离脚面不到一步：是台阶
            continue
        cuts.append((min(a0, a1), max(a0, a1)))
    if not cuts:
        return (lo, hi)
    cuts.sort()
    merged = []
    for a, b in cuts:
        if merged and a <= merged[-1][1] + 0.5:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    cur = lo
    for a, b in merged:
        if x < a:
            return (cur, min(a, hi))
        if x <= b:                            # 猫正卡在墙里（被拖进去）：挑近的一侧
            if x - a <= b - x and a > cur:
                return (cur, a)
            cur = b
            continue
        cur = max(cur, b)
    return (cur, hi)


def reach_assist(pet, goal, gx, gy):
    """近目标探身：距目标 < arm_full_reach*REACH_GATE_K 才伸臂。"""
    body = pet.body
    c0 = body.chunk0
    if math.hypot(gx - c0.x, gy - c0.y) < body.arm_full_reach * tuning.REACH_GATE_K:
        tgt = goal.obj if goal.obj is not None else PointTarget(gx, gy)
        body.reach_for(tgt, "r" if gx >= c0.x else "l")
