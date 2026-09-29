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

    # ── 路线打分：耗时 × 动作风险（按性格）──
    # 原版生物不会精确追求「最短时间」：谨慎的个体宁可绕路走，急躁 / 勇敢的
    # 才愿意为省几 tick 去赌一个跳跃。这里给每种动作一个风险系数，再按性格
    # （bravery 越高越不在乎风险）缩放成排序用的代价 —— 只改**排序**，
    # Candidate.time_est 原样保留（执行器的超时/进度判断仍用真实耗时）。
    _ROUTE_RISK = {
        "walk": 0.0, "tongue": 0.15, "tonguehang": 0.15, "climb": 0.20,
        "hop": 0.25, "poledrop": 0.25, "poletongue": 0.30, "jump": 0.45,
        "polejump": 0.50, "ceildrop": 0.60, "backflip": 0.70, "pyrojump": 0.90,
    }

    def _route_cost(self, c) -> float:
        fac = 1.15 - 0.9 * self._bravery()           # 谨慎 ←→ 莽
        risk = self._ROUTE_RISK.get(c.ability_key, 0.3)
        return c.time_est * (1.0 + tuning.ROUTE_RISK_W * risk * fac)

    def _bravery(self) -> float:
        """本猫的勇敢度：优先取行为层当前的人格（运行期可能被替换）。"""
        beh = getattr(self.pet, "behavior", None)
        pers = getattr(beh, "pers", None)
        if pers is None:
            pers = getattr(getattr(self.pet, "cat", None), "personality", None)
        try:
            return min(1.0, max(0.0, float(getattr(pers, "bravery", 0.5))))
        except (TypeError, ValueError):
            return 0.5

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
