# -*- coding: utf-8 -*-
"""AimSolution：一次投掷决策的全部结果（文档 §5「最后一个对象」）。

旧实现把一次投掷拆成多个并列查询：``_throw_weapon_at`` → ``_shot_path_clear``
→ ``_shot_velocity`` → ``_shot_arc``，``_shot_would_hit`` 又把同一组初速与弹道
再算一遍，``_launch_weapon`` 再算第三遍 —— 同一帧同一条弹道预演两三次，而且每
多一种投掷物（石头 / 不同猫种）就要在每个分支各补一次判断。

这里只放**结果**：谁 / 从哪 / 往哪 / 弹道 / 打不打得到目标 / 会不会误伤同伴 /
需不需要先起跳 / 朝哪边掷。求解本身留在 FSM 的 ``_solve_shot()``（它要用
``_shot_profile`` 这类只存在于行为层的东西），行为层只读这个对象：

    sol = fsm._solve_shot(tgt)
    if sol.hit_now: launch(sol)
    elif sol.requires_jump: jump()
    elif sol.blocked_by_friend: wait()
"""
from __future__ import annotations


class AimSolution:
    """这一掷的解。构造后不再变化，调用方只读。"""

    __slots__ = ("profile", "direction", "origin", "velocity", "path",
                 "target_hit", "friendly_blocker", "requires_jump",
                 "block_ticks")

    def __init__(self, profile, direction, origin, velocity, path,
                 target_hit=False, friendly_blocker=None, requires_jump=False,
                 block_ticks=0):
        self.profile = profile
        self.direction = 1 if float(direction) >= 0.0 else -1
        self.origin = origin
        self.velocity = velocity
        self.path = list(path or ())
        self.target_hit = bool(target_hit)
        self.friendly_blocker = friendly_blocker
        self.requires_jump = bool(requires_jump)
        # 同伴只看到「自己到目标」那一段（0 = 目标在背后，整段不看）
        self.block_ticks = int(block_ticks)

    @property
    def hit_now(self) -> bool:
        """此刻就能打中、而且不挡同伴 → 直接出手。"""
        return self.target_hit and self.friendly_blocker is None

    @property
    def blocked_by_friend(self) -> bool:
        return self.friendly_blocker is not None

    def __repr__(self):
        return "<AimSolution %s dir=%+d hit=%s block=%s jump=%s>" % (
            self.profile.name, self.direction, self.target_hit,
            getattr(self.friendly_blocker, "uid", self.friendly_blocker),
            self.requires_jump)
