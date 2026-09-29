"""饕餮（美食家）独占：体重坠落攻击（原版 Gourmand 的砸击）。

不爱用矛的饕餮到了危险距离就跳起来，把身体重量压在战斗目标头上：
起跳→向目标横移→下落加速→命中后给伤害与眩晕。比高一次后进冷却。
"""
from __future__ import annotations

from ..behavior import tuning
from ..behavior.action import BAND_NEED, TAG_CHARACTER
from ..core.units import clampf

MAX_TICKS = 150          # 一次砸击的最长时间（卡住也能收尾）


def mount_slam(fsm):
    """挂载 Slam：动作（何时起手）+ 独占状态（怎么砸）。"""
    cat = getattr(fsm.win, "cat", None)
    if cat is None or not cat.tuning.get("slam"):
        return
    # 本模块独占的记账字段：挂载即就位（pre 每 tick 都会跑）
    fsm._slam_cd = 0
    fsm._slam_target = None
    fsm._slam_phase = "rise"
    fsm._slam_t = 0

    def enter():
        b = fsm.body
        th = fsm._threat_lizard()
        if th is None:
            fsm._transition("IdleStand")
            return
        b.stop_walk()
        b.set_posture(True)
        fsm._clear_hands()
        fsm._slam_target = th
        fsm._slam_phase = "rise"
        fsm._slam_t = 0

    def finish():
        b = fsm.body
        b.stop_walk()
        fsm.animation = None
        fsm._slam_target = None
        fsm._slam_cd = tuning.SLAM_CD_TICKS
        fsm._transition("IdleStand" if b.on_floor() else "Airborne")

    def st_slam(cursor, disturbed):
        b = fsm.body
        fsm._slam_t += 1
        th = fsm._slam_target
        if fsm._slam_t > MAX_TICKS or th is None or getattr(th, "dead", False):
            finish()
            return
        tx = th.x
        dx = tx - b.chunk1.x
        if fsm._slam_phase == "rise":
            if b.on_floor() and fsm._slam_t <= 12:
                b.chunk0.vy = min(b.chunk0.vy, tuning.SLAM_RISE_VY)
                b.chunk1.vy = min(b.chunk1.vy, tuning.SLAM_RISE_VY)
            b.chunk0.vx += clampf(dx * 0.05, -6.0, 6.0)
            b.chunk1.vx += clampf(dx * 0.05, -6.0, 6.0)
            if not b.on_floor():
                fsm._slam_phase = "drop"
            return
        # 下落：往目标身上压
        b.chunk0.vx += clampf(dx * 0.08, -8.0, 8.0)
        b.chunk1.vx += clampf(dx * 0.08, -8.0, 8.0)
        b.chunk0.vy = max(b.chunk0.vy, tuning.SLAM_DROP_VY)
        b.chunk1.vy = max(b.chunk1.vy, tuning.SLAM_DROP_VY)
        if abs(dx) <= tuning.SLAM_ARRIVE_R and b.chunk1.y >= th.y - 40.0:
            try:
                th.hurt(tuning.SLAM_DAMAGE, dvec=(0.0, 1.0), speed=12.0,
                        stun_bonus=tuning.SLAM_STUN_BONUS, hit_head=True,
                        knock_k=0.5)
            except Exception:
                pass
            fsm.win.window._shake_impact(b.chunk1, 0.0, -6.0, 0.6,
                                         b.chunk1.x, b.chunk1.y)
            finish()

    def brk():
        b = fsm.body
        b.stop_walk()
        fsm.animation = None
        fsm._slam_target = None

    fsm.register_state("Slam", enter=enter, tick=st_slam, brk=brk, kill_break=brk)

    def pre(ctx):
        if fsm._slam_cd > 0:
            fsm._slam_cd -= 1

    def gate(ctx):
        if fsm._slam_cd > 0 or fsm.grab.active or fsm._hibernating:
            return False
        if fsm.body.swimming or fsm._zerog() or fsm._cold_urgent():
            return False
        if fsm.state not in ("IdleStand", "PostThrowStand", "PostThrowWander"):
            return False
        if not fsm.body.on_floor():
            return False
        th = fsm._threat_lizard()
        if th is None:
            return False
        return abs(th.x - fsm.body.chunk1.x) <= tuning.SLAM_TRIGGER_R

    def start(ctx):
        fsm._break_active_controllers()
        fsm._transition("Slam")
        return True

    fsm.register_action("Slam", BAND_NEED, gate, start, pre=pre,
                        tags=(TAG_CHARACTER,))
