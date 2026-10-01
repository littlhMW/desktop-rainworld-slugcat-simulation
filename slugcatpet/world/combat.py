# -*- coding: utf-8 -*-
"""CombatTarget：可被投掷物打得中的「目标」统一接口（文档 §7）。

投掷物 ⨯ 目标的几何在 ``world/hitgeom.py``；目标只需要自报 :meth:`CombatTarget.chunks`
（自己身上哪里挨打），``preferred_point()`` / ``hit_radius()`` 默认由它派生。

以前 ``hitgeom.target_chunks()`` 里挂着一条
``chunks → hit_chunks → chunk0/chunk1 → p0/p1 → x/y + seg`` 的降级链：目标不必实现
任何接口，函数一层层猜。排查「命中点又飘了」得先弄清这次走的是第几层。现在每个
目标都真的回答这三个问题，降级链删除；只有「单点 + rad」这种最普通的对象走默认实现。
"""
from __future__ import annotations


class CombatTarget:
    """可命中目标：``chunks()`` 必答，另两个有默认实现。"""

    __slots__ = ()

    def chunks(self):
        """可命中点 ``[(owner, x, y, rad), ...]``；``owner=None`` 表示就是自己。

        默认实现＝「单点 + 半径」：中心在 ``(x, y)``，半径取 ``head_rad``（有就优先）
        或 ``rad``。多质点 / 带头甲 / 带链节的目标自己覆盖。
        """
        x = getattr(self, "x", None)
        y = getattr(self, "y", None)
        if (not isinstance(x, (int, float)) or isinstance(x, bool)
                or not isinstance(y, (int, float)) or isinstance(y, bool)):
            return []
        rad = getattr(self, "head_rad", None)
        if rad is None:
            rad = getattr(self, "rad", 0.0)
        return [(None, float(x), float(y), float(rad or 0.0))]

    def preferred_point(self):
        """最该瞄准的那个点 ``(x, y)``（默认＝第一个可命中点）。"""
        ch = self.chunks()
        if not ch:
            return None
        _owner, x, y, _r = ch[0]
        return (float(x), float(y))

    def hit_radius(self):
        """命中半径（默认＝所有可命中点里最大的那个）。"""
        ch = self.chunks()
        if not ch:
            return 0.0
        return max(float(r) for (_o, _x, _y, r) in ch)
