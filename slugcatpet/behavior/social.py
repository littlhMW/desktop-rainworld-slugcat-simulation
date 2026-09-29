# -*- coding: utf-8 -*-
"""蛞蝓猫社交动作词表 + 手势引擎。

这份词表是「社交动作」的唯一事实源（README 的同名段落由它列出）。
每个动作 = 一个手势 + 一个含义；含义决定它被抽中的场合（fsm._pick_social_kind）：

    指向          手持续瞄着对象             指向 / 想要 / 注意
    指指点点      伸手-收回快速 1~5 下        指责 / 强调
    摇醒          抓着对方左右晃 2~4 下         别睡了 / 起来玩（对方随即醒）
    抚摸          手在对象上画折返横线 2~5    喜欢 / 安抚
    拍拍          手在对象上画折返竖线 2~5    喜欢 / 安抚 / 道歉
    复活          用力下按 4~8 下（身体同压） 复活中；按完对象复活
    匍匐行走      趴着挪动                   害怕强敌，正在潜行（只在附近有蜥蜴时）

匍匐族只剩「匍匐行走」一条，而且附近得有蜥蜴才抽得到：遇到同伴 / 鼠标这些
非蜥蜴对象不再有任何匍匐动作（匍匐指指点点、匍匐指向已删除）。

同一套手势引擎同时服务两条路径：
  * 社交欲望态（fsm._st_socialize）：攒满社交欲望 → 走到同伴身边做动作；
  * 平时随手小动作（fsm._act_begin / _act_tick / _act_end）：被挡路、被抢、
    追鼠标、睡醒、空手反击、让路、被指、挣扎等情景直接抽词表起手。
"""
from __future__ import annotations

from collections import OrderedDict

from .tuning import POINT_REPS_MIN, POINT_REPS_MAX


class SocialAction:
    """一个社交动作：键、双语名、双语含义、是否匍匐、手势名。"""

    __slots__ = ("key", "zh", "en", "meaning_zh", "meaning_en", "crouch", "gesture")

    def __init__(self, key, zh, en, meaning_zh, meaning_en, crouch, gesture):
        self.key = key
        self.zh = zh
        self.en = en
        self.meaning_zh = meaning_zh
        self.meaning_en = meaning_en
        self.crouch = bool(crouch)
        self.gesture = gesture


ACTIONS = OrderedDict()


def _add(key, zh, en, meaning_zh, meaning_en, crouch, gesture):
    ACTIONS[key] = SocialAction(key, zh, en, meaning_zh, meaning_en, crouch, gesture)


# 指向 / 指指点点
_add("point", "指向", "Point",
     "指向 / 想要 / 注意", "pointing at / wanting / look here", False, "hold")
_add("scold", "指指点点", "Point-point",
     "指责 / 强调", "scolding / emphasis", False, "scold")
# 喜欢 / 安抚
_add("pet", "抚摸", "Pet",
     "喜欢 / 安抚", "liking / soothing", False, "stroke_h")
_add("pat", "拍拍", "Pat",
     "喜欢 / 安抚", "liking / soothing", False, "stroke_v")
# 复活
_add("revive", "复活", "Revive",
     "正在复活", "reviving", False, "press")
# 匍匐族：只剩「匍匐行走」，只在附近有蜥蜴（强敌）时抽得到
_add("crouch_walk", "匍匐行走", "Crouch-walk",
     "害怕强敌，正在潜行", "afraid of a strong foe, sneaking", True, "walk")

# 旧键别名：被抢东西的指指点点沿用 "protest"
_add("wake", "摇醒", "Wake up",
     "别睡了 / 起来玩（晃完对方就醒）", "stop sleeping / wake up and play",
     False, "none")

ALIASES = {"protest": "scold"}


def action(key):
    """按键取动作（含旧别名）；未知返回 None。"""
    return ACTIONS.get(ALIASES.get(key, key))


def is_crouch(key) -> bool:
    """该动作是否要趴着做。"""
    a = action(key)
    return bool(a is not None and a.crouch)


class PointGesture:
    """指指点点手势：伸出 on_ticks → 收回 off_ticks，重复 reps 次（1~5 下）。"""

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


def social_reps(rng, point_like: float) -> int:
    """指指点点次数：爱指的猫指得久，性格好的猫敷衍两下就收（1~5 下）。"""
    reps = rng.randint(POINT_REPS_MIN, POINT_REPS_MAX)
    if rng.random() > float(point_like):
        reps = max(1, reps - 2)
    return reps


class StrokeGesture:
    """手贴对象来回画线：沿轴折返 reps 次（2~5），每次 on tick。

    offset() 返回本 tick 相对目标点的偏移；采样连续不跳变，
    折返点正好落在 ±span。
    """

    __slots__ = ("reps", "on", "axis", "span", "_t", "_pass")

    def __init__(self, reps, on_ticks, axis="h", span=16.0):
        self.reps = max(1, int(reps))
        self.on = max(1, int(on_ticks))
        self.axis = axis
        self.span = float(span)
        self._t = 0
        self._pass = 0

    @property
    def done(self) -> bool:
        return self._pass >= self.reps

    def offset(self):
        """本 tick 相对目标点的 (dx, dy)。"""
        if self.done:
            return (0.0, 0.0)
        p = self._t / float(self.on)
        u = p if self._pass % 2 == 0 else 1.0 - p
        off = (u * 2.0 - 1.0) * self.span
        return (off, 0.0) if self.axis == "h" else (0.0, off)

    def step(self) -> bool:
        """推进一 tick；返回 True=整段画完。"""
        if self.done:
            return True
        self._t += 1
        if self._t >= self.on:
            self._t = 0
            self._pass += 1
        return self.done


class PressGesture:
    """用力按压：下压 press tick、抬起 rest tick，重复 reps 次（4~8）。"""

    __slots__ = ("reps", "press", "rest", "_left", "_t", "_down")

    def __init__(self, reps, press_ticks, rest_ticks):
        self.reps = max(1, int(reps))
        self.press = max(1, int(press_ticks))
        self.rest = max(0, int(rest_ticks))
        self._left = self.reps
        self._t = 0
        self._down = True

    @property
    def pressing(self) -> bool:
        """本 tick 正在往下用力。"""
        return self._down and self._left > 0

    @property
    def presses_done(self) -> int:
        return self.reps - self._left

    @property
    def done(self) -> bool:
        return self._left <= 0

    def step(self) -> bool:
        """推进一 tick；返回 True=整段按完（含最后一次抬手）。"""
        if self._left <= 0:
            return True
        self._t += 1
        if self._down:
            if self._t >= self.press:
                self._t = 0
                self._down = False
                self._left -= 1
        elif self._t >= self.rest:
            self._t = 0
            self._down = True
        return self._left <= 0
