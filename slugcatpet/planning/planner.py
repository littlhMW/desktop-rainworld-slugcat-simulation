"""重力域规划内核：能力按每猫能力清单（CatCaps）门禁，枚举→体力门槛过滤→耗时升序。"""
from __future__ import annotations
import time

from ..behavior import tuning
from .ability import Candidate
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

    def _candidates(self, goal, question):
        energy = self.pet.body.energy
        out = []
        for ab in self._abilities():
            est = getattr(ab, question)(goal)
            if est is None or est.energy_est > energy:
                continue
            out.append(Candidate(ab.key, est.time_est, est.energy_est,
                                 lambda ab=ab, g=goal: ab.make_controller(g)))
        out.sort(key=self._route_cost)
        return out

    # ── 路线打分：六轴（时间 / 体力 / 风险 / 噪音 / 精度 / 后摇）× 性格 ──
    # 原版生物不会精确追求「最短时间」：谨慎的个体宁可绕路走，急躁 / 勇敢的
    # 才愿意为省几 tick 去赌一个跳跃。六轴表在 planning/route.py，这里只
    # 负责把「这只猫此刻的性格」喂进去 —— 只改**排序**，Candidate.time_est
    # 原样保留（执行器的超时/进度判断仍用真实耗时）。
    def _route_cost(self, c) -> float:
        edge = edge_for(c.ability_key, c.time_est, c.energy_est)
        return route_cost(edge, self._pers())

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

    def touch_candidates(self, goal):
        return self._candidates(goal, "can_touch")

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

    def world_version(self):
        return getattr(self.pet, "world_version", 0)

    def on_giveup(self, goal):
        self._cooldown.add(goal.key(), self.world_version())

    def in_cooldown(self, goal):
        return self._cooldown.active(goal.key(), self.world_version())
