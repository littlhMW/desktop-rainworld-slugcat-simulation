# -*- coding: utf-8 -*-
"""指指点点手势：伸出 on_ticks → 收回 off_ticks，重复 reps 次（3~5 下）。"""
from __future__ import annotations


class PointGesture:
    """一下一下地伸手比划：伸出 → 收回 → 再伸出（原版蛞蝓猫被抢/被挡的抗议）。"""

    __slots__ = ("reps", "on", "off", "_left", "_ext", "_t")

    def __init__(self, reps: int, on_ticks: int, off_ticks: int):
        self.reps = max(1, int(reps))
        self.on = max(1, int(on_ticks))
        self.off = max(1, int(off_ticks))
        self._left = self.reps
        self._ext = True
        self._t = 0

    @property
    def extended(self) -> bool:
        """本 tick 处于「伸出」相（该把手指着目标）。"""
        return self._ext

    @property
    def done(self) -> bool:
        """指完并已收回。"""
        return self._left <= 0

    def step(self) -> bool:
        """推进一 tick；返回 True=整段指指点点结束。"""
        if self._left <= 0:
            return True
        self._t += 1
        if self._t < (self.on if self._ext else self.off):
            return False
        self._t = 0
        if self._ext:
            self._left -= 1        # 这一下指完（连带收回）
            self._ext = False
        else:
            self._ext = True       # 再指一下
        return False
