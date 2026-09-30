# -*- coding: utf-8 -*-
"""动画意图层：把「这一 tick 想怎么动」和「真正写进图形」分开。

原版每只生物每帧把自己的 lookAt / 表情 / 姿态交给自己的 Graphics 层合成；
桌宠过去是 FSM 各处直接 `gfx.look_at = ...`，同一个 tick 里**谁最后写谁算**。
绝大多数时候没问题，但几处「必须赢」的写法会被后来者盖掉 —— 典型是
「趴下睡觉不许挂醒着的表情」和「死了/被舌头黏着不许摆匍匐」：它们写在
状态处理之前，之后随便哪个分支写一次就被顶掉。

这里给 look / face 加**优先级**：

    高优先级赢；同优先级「后写的赢」

后者与旧的直接赋值语义完全一致，所以没写优先级的地方行为一点不变；只有明确
写成高优先级的地方（睡、死、被舌头黏住）才真的不可被覆盖。

优先级用 Graphics.look()/Graphics.face() 提交，或直接 `gfx.look_at = v`
（等价于 PRIO_ACTION）。Graphics.update() 开头会把优先级重置，于是上一 tick
的高优先级不会漏到下一 tick。
"""
from __future__ import annotations

from dataclasses import dataclass

# ── 被「横杆/吊挂」这档动画接管的肢体姿态（唯一真值源）──────────────────
# 落进这一档时，手和腿的位置都由动画决定：持物只**跟随**那只手，不再自己算
# 第二套锚点。core/creature.py::hands_on_anim 与 rendering/graphics.py 的
# _update_hands / _update_legs 必须读同一份，否则又会退回「动画在动手、持物在
# 拉手」的两套坐标（用户报的「拿矛爬杆矛浮空 / 多出两只手」）。
# 注意：扶墙下滑的 WallClimb 不在其中 —— 它的 bodyMode 也叫 ClimbingOnBeam，
# 但手并没有被 beam 姿态接管。
BEAM_LIMB_ANIMS = ("ClimbOnBeam", "BeamTip", "StandOnBeam",
                   "HangFromBeam", "GetUpOnBeam")

PRIO_NONE = -1        # 本 tick 还没人表态
PRIO_FALLBACK = 0     # 兜底（把 look 清成 None）
PRIO_AMBIENT = 10     # 闲逛扫视 / 环境注意
PRIO_ACTION = 50      # 主动作：取食 / 战斗 / 社交 / 爬杆 / 玩（= 旧的直接赋值）
PRIO_URGENT = 80      # 面敌 / 逃生
PRIO_FORCE = 100      # 睡 / 死 / 被舌头黏住：不可被覆盖


@dataclass
class AnimationIntent:
    """这一 tick 的动画意图（look / face 各带一个优先级）。"""
    look: object = None
    look_prio: int = PRIO_NONE
    look_src: str = ""
    face: object = None
    face_prio: int = PRIO_NONE
    face_src: str = ""


class AnimationController:
    """一只猫的动画意图：`submit` 记意图，`resolve` 合成，写盘由调用方做。"""

    __slots__ = ("intent",)

    def __init__(self):
        self.intent = AnimationIntent()

    # ── 提交 ──
    def reset(self) -> None:
        """新一 tick：清空优先级（值不回滚，仍由写入方自己管）。"""
        it = self.intent
        it.look_prio = it.face_prio = PRIO_NONE
        it.look_src = it.face_src = ""

    def look(self, value, prio: int = PRIO_ACTION, src: str = "") -> None:
        """提交视线目标；优先级不够就丢弃（同优先级 → 后写的赢）。"""
        it = self.intent
        if prio < it.look_prio:
            return
        if prio == it.look_prio and value is it.look:
            return
        it.look = value
        it.look_prio = prio
        it.look_src = src

    def face(self, value, prio: int = PRIO_ACTION, src: str = "") -> None:
        """提交特殊表情开关，规则同 look。"""
        it = self.intent
        if prio < it.face_prio:
            return
        it.face = bool(value)
        it.face_prio = prio
        it.face_src = src

    # ── 合成 ──
    def resolve(self):
        """→ (look 有无人表态, look 值, face 有无人表态, face 值)。"""
        it = self.intent
        return (it.look_prio != PRIO_NONE, it.look,
                it.face_prio != PRIO_NONE, it.face)


def point_of(obj):
    """把「一个东西」解析成 (x, y)；解析不出来就 None。

    必须挑得出**数值**：认领 / 注视的目标常常是另一只 PetUnit，而 PetUnit 的
    `x` 会转发到窗口，拿到的是 QWidget.x() 这个方法 —— 直接拿来减就是 TypeError。
    顺序：点 → 自己的 x/y → 身体的 chunk0/chunk1 → 自己的 chunk0/chunk1。
    """
    if obj is None:
        return None
    if isinstance(obj, (tuple, list)):
        return (float(obj[0]), float(obj[1])) if len(obj) >= 2 else None
    x, y = getattr(obj, "x", None), getattr(obj, "y", None)
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return (float(x), float(y))
    for holder in (getattr(obj, "body", None), obj):
        if holder is None:
            continue
        for name in ("chunk0", "chunk1"):
            c = getattr(holder, name, None)
            if c is None:
                continue
            cx, cy = getattr(c, "x", None), getattr(c, "y", None)
            if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
                return (float(cx), float(cy))
    return None
