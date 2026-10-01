"""重力域规划内核：能力按每猫能力清单（CatCaps）门禁，枚举→体力门槛过滤→耗时升序。"""
from __future__ import annotations
import time

from ..behavior import tuning
from .ability import MODE_STAY, MODE_TOUCH, Candidate
from .cooldown import CooldownRegistry
from .backflip_reach import BackflipReach
from .ceiling_reach import CeilingDropReach
from .climb_reach import ClimbReach
from .hop_reach import HopReach
from .jump_reach import JumpReach
from .pole_reach import PoleDropReach, PoleJumpReach, PoleTongueReach
from .pyro_reach import PyroJumpReach
from .route import edge_for, route_cost
from .tongue_hang_stay import TongueHangStay
from .tongue_reach import TongueReach
from .walk_reach import WalkReach


class Planner:
    """pet 为 PetUnit 鸭子类型：.body/.tongue/.cat 本猫；_WL/_HL/world_version/poles 世界。"""

    def __init__(self, pet, clock=time.monotonic):
        self.pet = pet
        self._cooldown = CooldownRegistry(clock)
        self._ability_cache = None    # 能力实例无状态，懒建后复用
        self._route = None            # 表面图寻路器（懒建）

    def _abilities(self):
        # 能力集按 caps 装配
        if self._ability_cache is not None:
            return self._ability_cache
        caps = self.pet.cat.caps
        out = [WalkReach(self.pet), JumpReach(self.pet),
               PoleJumpReach(self.pet), PoleDropReach(self.pet),
               BackflipReach(self.pet), HopReach(self.pet)]
        if caps.tongue:
            out += [TongueReach(self.pet), ClimbReach(self.pet),
                    PoleTongueReach(self.pet), TongueHangStay(self.pet)]
            if caps.ascension:
                out.append(CeilingDropReach(self.pet))
        if caps.pyro:
            out.append(PyroJumpReach(self.pet))
        # 后空翻（含距离档）与「跳跃寻路」是全员通用动作：原版每只蛞蝓猫都会
        # 后空翻、土狼跳、跳杆，能不能用只取决于轨道够不够，不设 cap。
        self._ability_cache = out
        return out

    def _candidates(self, goal, question, play=False):
        energy = self.pet.body.energy
        out = []
        for ab in self._abilities():
            est = getattr(ab, question)(goal)
            if est is None and play:
                # 娱乐性候选（够不到也跳一下）：只在明确问 play 的语境里生成，
                # 免得取食 / 趋暖 / 救援那些「要真的到得了」的目标被空跳带偏。
                est = ab.can_play(goal)
            if est is None or est.energy_est > energy:
                continue
            out.append(Candidate(ab.key, est.time_est, est.energy_est,
                                 lambda ab=ab, g=goal: ab.make_controller(g),
                                 est.bonus, est.play))
        out.sort(key=self._route_cost)
        return out

    # ── 路线打分：六轴（时间 / 体力 / 风险 / 噪音 / 精度 / 后摇）× 性格 ──
    # 原版生物不会精确追求「最短时间」：谨慎的个体宁可绕路走，急躁 / 勇敢的
    # 才愿意为省几 tick 去赌一个跳跃。六轴表在 planning/route.py，这里只
    # 负责把「这只猫此刻的性格」喂进去 —— 只改**排序**，Candidate.time_est
    # 原样保留（执行器的超时/进度判断仍用真实耗时）。
    def _route_cost(self, c) -> float:
        edge = edge_for(c.ability_key, c.time_est, c.energy_est)
        return route_cost(edge, self._pers()) - c.bonus   # bonus：玩耍这类额外收益

    def _pers(self):
        """当前人格：优先行为层（运行期可能被替换），再回落种族原型。"""
        beh = getattr(self.pet, "behavior", None)
        pers = getattr(beh, "pers", None)
        if pers is None:
            pers = getattr(getattr(self.pet, "cat", None), "personality", None)
        return pers

    def _axis(self, name: str) -> float:
        """取性格轴（0..1）。"""
        from .route import axis as _axis_of
        return _axis_of(self._pers(), name)

    def touch_candidates(self, goal, play=False):
        return self._candidates(goal, "can_touch", play=play)

    def play_jump_plan(self, goal):
        """目标处的玩耍跳方案 (起跳 x, 档位, 方向, 空中 tick, 总 tick)；没有则 None。

        「够不到也跳一下」的执行方拿它当起跳点与方向 —— 而不是把鼠标坐标直接
        当起跳点、再自己比一次高度。
        """
        return JumpReach(self.pet)._play_plan(goal)

    def stay_candidates(self, goal):
        return self._candidates(goal, "can_stay")

    def any_touch(self, goal):
        """存在性早退版 _candidates，不建 Candidate 不排序。"""
        energy = self.pet.body.energy
        for ab in self._abilities():
            est = ab.can_touch(goal)
            if est is None or est.energy_est > energy:
                continue
            return True
        return False

    def can_touch(self, goal):
        return bool(self.touch_candidates(goal))

    def can_stay(self, goal):
        return bool(self.stay_candidates(goal))

    # ── 位移载体（杆）统一入口：Mood / 取食 / 玩杆共用同一份结果 ──
    # 旧版 _climbable_pole_available() 只问「世界上有没有竖杆」：猫在 x=100、
    # 杆在 x=900 也算可爬，于是杆一多就出现「爬上去→发现地面更近→下来→再爬」。
    # 这里把「横距够得着 + 纵向跨度摸得到」合成唯一入口，其它地方不再各写一套 if。
    def transports(self, kinds=("vertical", "horizontal")):
        """世界里可用作位移的杆（不含光标虚杆）。"""
        return [p for p in getattr(self.pet, "poles", ())
                if p.kind in kinds and not getattr(p, "virtual", False)]

    def transport_dx(self, p) -> float:
        """猫到这根杆的横向距离（横杆＝到杆面的距离，杆面上为 0）。"""
        x = self.pet.body.chunk1.x
        if p.kind == "vertical":
            return abs(p.bx - x)
        lo, hi = min(p.ax, p.bx), max(p.ax, p.bx)
        if x < lo:
            return lo - x
        if x > hi:
            return x - hi
        return 0.0

    def transport_in_reach(self, p) -> bool:
        """此刻「够得着」这根杆：横距在够取圈内，且身体高度落在杆的纵向跨度内。"""
        b = self.pet.body
        if p.kind == "vertical":
            if self.transport_dx(p) > tuning.POLE_TRANSPORT_NEAR:
                return False
            top, bot = min(p.ay, p.by), max(p.ay, p.by)
            y = b.chunk1.y
            return top - tuning.POLE_AIRGRAB_PAD <= y <= bot + tuning.POLE_AIRGRAB_PAD
        return (self.transport_dx(p) <= tuning.HPOLE_TRANSPORT_NEAR
                and abs(p.ay - b.chunk1.y) <= tuning.HPOLE_AIRGRAB_Y)

    def reachable_transports(self, kinds=("vertical", "horizontal")):
        """真正能用作位移的杆（Mood / 取食 / 玩杆共用的唯一一份结果）。"""
        return [p for p in self.transports(kinds) if self.transport_in_reach(p)]

    def escape_route(self, threat):
        """威胁下的逃生路线（文档 §六 Escape Goal）。

        威胁是什么由 ThreatField 描述，去哪由 Planner 在导航节点里挑，怎么走由
        RouteExecutor 用**动态代价**执行。FSM 只保留「我要不要逃」这一个决定。
        """
        if self._route is None:
            from .surface import SurfaceRoute
            self._route = SurfaceRoute(self.pet)
        return self._route.plan_escape(threat)

    def surface_route(self, goal):
        """多段寻路：Goal → 表面图 → 最优两段路线。返回 SurfaceHop 或 None。

        单能力候选（walk / jump / hop / polejump…）都是「从现在这里够不够得到」，
        这里补上「先跳到窗口顶边、再从那里够」这一层（见 planning/surface.py）。
        """
        if self._route is None:
            from .surface import SurfaceRoute
            self._route = SurfaceRoute(self.pet)
        return self._route.plan(goal)

    def route_candidate(self, goal, mode=MODE_TOUCH):
        '''多段路线候选：直连能力全给不出方案时的兜底（控制器 = RouteExecutor）。

        与单能力候选共用六轴打分的排序体系；Planner 只负责把它造出来，
        真的逐段执行 / 落地后重规划在 planning/surface.RouteExecutor 里。
        取食（touch）与趋暖 / 救援 / 社交靠近（stay）共用同一份兜底 ——
        导航内核只有这一套，不再每个行为各写一次寻路。
        '''
        plan = self.surface_route(goal)
        if plan is None:
            return None
        from .surface import RouteExecutor
        return Candidate("route", plan.time, plan.energy,
                         lambda: RouteExecutor(self.pet, self, goal, mode))

    def world_version(self):
        return getattr(self.pet, "world_version", 0)

    def on_giveup(self, goal):
        self._cooldown.add(goal.key(), self.world_version())

    def in_cooldown(self, goal):
        return self._cooldown.active(goal.key(), self.world_version())
