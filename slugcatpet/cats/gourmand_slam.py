"""饕餮（美食家）独占：体重坠落攻击（原版 Gourmand 的砸击）。

不爱用矛的饕餮到了危险距离就跳起来，把身体重量压在战斗目标头上：
起跳→向目标横移→下落加速→命中后给伤害与眩晕。比高一次后进冷却。
"""
from __future__ import annotations

import math

from ..behavior import tuning
from ..behavior.action import BAND_NEED, TAG_CHARACTER
from ..core.units import clampf

MAX_TICKS = 150          # 一次砸击的最长时间（卡住也能收尾）


def _height_mult(h: float) -> float:
    """原版 Player.cs:6374-6455 的落高分档 ×0.5/×1/×2/×3/×5，再归一化。

    以「一次满跳（h<100 → ×0.5）」为单位 1.0，于是 h≈53 时倍率 1.0、
    h≈150 时 2.0、h≈400 时 6.0 —— 保持现有平衡，同时越高砸得越狠。
    """
    f = 5.0
    for lim, v in tuning.SLAM_HEIGHT_BANDS:
        if h < lim:
            f = v
            break
    return f / 0.5


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
    fsm._slam_y0 = 0.0
    fsm._slam_peak = 0.0

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
        fsm._slam_y0 = b.chunk1.y      # 起跳时的地面高度（原版 lastGroundY）
        fsm._slam_peak = b.chunk1.y    # 这次砸击的最高点

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
        fsm._slam_peak = min(fsm._slam_peak, b.chunk1.y)
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
            # 腾空后先横移接近：到最高点 / 飞到目标头上 / 兜底超时才下压，
            # 否则刚离地就压下来，根本够不到目标（也就没有落高可言）
            if ((not b.on_floor())
                    and (b.chunk1.vy >= 0.0
                         or abs(dx) <= tuning.SLAM_ARRIVE_R * 0.6
                         or fsm._slam_t > 40)):
                fsm._slam_phase = "drop"
            return
        # 下落：往目标身上压
        b.chunk0.vx += clampf(dx * 0.08, -8.0, 8.0)
        b.chunk1.vx += clampf(dx * 0.08, -8.0, 8.0)
        b.chunk0.vy = max(b.chunk0.vy, tuning.SLAM_DROP_VY)
        b.chunk1.vy = max(b.chunk1.vy, tuning.SLAM_DROP_VY)
        # 必须已经在往下砸：刚离地那几帧还在上升，不能算压中（原版 vel.y < -10 的同一条门槛）
        falling = b.chunk1.vy > 1.0
        if (abs(dx) <= tuning.SLAM_ARRIVE_R and falling
                and b.chunk1.y >= th.y - 60.0):
            # 落高不足：只是落地，不形成震击（用户口径 + 原版 num3 门槛）
            height = max(0.0, fsm._slam_y0 - fsm._slam_peak)
            if height < tuning.SLAM_MIN_HEIGHT:
                finish()
                return
            mult = _height_mult(height)
            try:
                th.hurt(tuning.SLAM_DAMAGE * mult, dvec=(0.0, 1.0), speed=12.0,
                        stun_bonus=tuning.SLAM_STUN_BONUS * mult, hit_head=True,
                        knock_k=0.5)
            except Exception:
                pass
            fsm.win.window._shake_impact(b.chunk1, 0.0, -6.0, 0.6,
                                         b.chunk1.x, b.chunk1.y)
            _slam_aoe(b.chunk1.x, b.chunk1.y, mult)
            finish()

    def _slam_aoe(cx, cy, mult):
        """震击波及：落点 SLAM_AOE_R 内的其他蛞蝓猫一起被震晕（越高越久）。"""
        win = fsm.win.window
        ticks = int(tuning.SLAM_AOE_STUN * mult)
        if ticks <= 0:
            return
        win.add_shockwave(cx, cy, tuning.SLAM_AOE_R * 0.5)
        for other in getattr(win, "pets", ()):
            if other is fsm.win:
                continue
            ob = getattr(other, "body", None)
            if ob is None or getattr(ob, "dead", False):
                continue
            d = min(math.hypot(cx - ob.chunk0.x, cy - ob.chunk0.y),
                    math.hypot(cx - ob.chunk1.x, cy - ob.chunk1.y))
            if d > tuning.SLAM_AOE_R:
                continue
            obeh = getattr(other, "behavior", None)
            if obeh is None:
                continue
            try:
                obeh.apply_stun(ticks)
            except Exception:
                pass

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
