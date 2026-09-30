# -*- coding: utf-8 -*-
"""雨循环：FOCUS → STORM_GATHER → SHELTER_SLEEP → FOCUS。

这一层只管相位 / 计时 / 雨强驱动 / 门的开关 / storm_pressure。渲染在
``rendering/rain_draw``，猫的行为在 ``behavior/fsm`` 的 StormSeekShelter 与
ShelterSleep —— 雨循环自己不碰任何动画。

反编译口径：原版暴雨不是「切到下雨」，而是一段可预期的连续过程 —— 先是长时间
的平静期，最后一小段（征兆期）世界开始不安，接着雨落下来，所有人躲进庇护所。所以这里唯一
推进的就是一条 0→1 的 ``rain_drive`` 曲线，外加「全员进庇护才关门」这条判据。
"""
from __future__ import annotations

from .behavior import tuning
from .world.rain import smoothstep
from .world.shelter import CLOSED, CLOSING, OPENING

FOCUS = "focus"
GATHER = "gather"
SLEEP = "sleep"

TICK_HZ = 40.0


def _minutes_to_ticks(minutes):
    return max(1, int(round(float(minutes) * 60.0 * TICK_HZ)))


def _inside_any(body, shelters):
    for sh in shelters:
        if sh.contains(body.chunk1.x, body.chunk1.y):
            return True
    return False


def _all_inside(pets, shelters):
    """所有活着的猫都进了**任意一间**安全区（真死的算「不用管」）。

    旧实现只认 shelters[0]：场上放两间庇护所时，进了第二间的猫会被判成「还在外面」，
    于是门永远关不上。
    """
    if not shelters:
        return False
    for p in pets:
        beh = getattr(p, "behavior", None)
        body = getattr(p, "body", None)
        if beh is None or body is None:
            continue
        if beh.is_truly_dead():
            continue
        if not _inside_any(body, shelters):
            return False
    return True


class StormCycle:
    """一个窗口一份。默认关闭（设置里开），且必须先有庇护所才会走相位。"""

    def __init__(self, enabled=False, focus_minutes=None, warning_minutes=None,
                 sleep_minutes=None):
        self.enabled = bool(enabled)
        self.manual = False          # 环境面板手动触发的一场雨（跑完自动回到原状）
        self._manual_prev = False    # 手动触发前 enabled 的值，睡眠结束后还原
        self.focus_minutes = float(focus_minutes if focus_minutes is not None
                                   else tuning.STORM_FOCUS_MINUTES)
        self.warning_minutes = float(warning_minutes if warning_minutes is not None
                                     else tuning.STORM_WARNING_MINUTES)
        self.sleep_minutes = float(sleep_minutes if sleep_minutes is not None
                                   else tuning.STORM_SLEEP_MINUTES)
        self.phase = FOCUS
        self.phase_t = 0
        self.settle_t = 0
        self.rain_drive = 0.0
        self.pressure = 0.0
        self.settle_ticks = int(tuning.STORM_SETTLE_TICKS)
        # 每进入一次 GATHER 就 +1：window 靠它探测「新一轮雨」并把 RainSystem 的
        # first_drop_done 复位（旧实现跨周期不复位，第二场雨永远没有第一滴重雨）。
        self.cycle_id = 0
        # 已跑完的雨循环次数（雨眠计时器主圆环的 karma 等级 = 它，1..10 夹紧）。
        # 不跟着 reset() 清 —— 它是这一局的累计成绩，只随存档走。
        self.cycles_done = 0
        self.fade_ticks = max(1, int(tuning.STORM_RAIN_FADE_TICKS))
        self.rise_ticks = max(1, int(tuning.STORM_RAIN_RISE_TICKS))
        self.gather_timeout = _minutes_to_ticks(tuning.STORM_GATHER_TIMEOUT_MINUTES)

    # ── 时长 ──
    @property
    def focus_ticks(self):
        return _minutes_to_ticks(self.focus_minutes)

    @property
    def warning_ticks(self):
        return _minutes_to_ticks(self.warning_minutes)

    @property
    def sleep_ticks(self):
        return _minutes_to_ticks(self.sleep_minutes)

    @property
    def active(self):
        """暴雨进行中（猫必须躲进庇护所的那两段）。

        手动触发的那一场不管 enabled（下完会把开关还原）。
        """
        return (self.enabled or self.manual) and self.phase in (GATHER, SLEEP)

    @property
    def remaining(self):
        return max(0, self.focus_ticks - self.phase_t) if self.phase == FOCUS else 0

    def set_durations(self, focus_minutes=None, warning_minutes=None, sleep_minutes=None):
        if focus_minutes is not None:
            self.focus_minutes = max(0.2, float(focus_minutes))
        if warning_minutes is not None:
            self.warning_minutes = max(0.1, float(warning_minutes))
        if sleep_minutes is not None:
            self.sleep_minutes = max(0.1, float(sleep_minutes))
        self.phase_t = min(self.phase_t, self.focus_ticks)

    def reset(self):
        self.manual = False
        self._manual_prev = False
        self.phase = FOCUS
        self.phase_t = 0
        self.settle_t = 0
        self.rain_drive = 0.0
        self.pressure = 0.0

    def trigger_storm(self):
        """环境面板手动放雨：立刻进入集合相位，优先级第一就是进庇护所。

        手动的这一场跑完（暴雨期结束回到 FOCUS）会把 ``enabled`` 还原成触发前的值
        —— 临时下一场雨不会顺手把整个雨循环打开。
        """
        if self.manual and self.phase in (GATHER, SLEEP):
            return False
        self._manual_prev = bool(self.enabled)
        self.manual = True
        self.phase = GATHER
        self.phase_t = 0
        self.settle_t = 0
        self.pressure = 1.0
        self.rain_drive = max(self.rain_drive, 1.0 / self.rise_ticks)
        self.cycle_id += 1          # 新一轮雨：window 会据此复位 first_drop_done
        return True

    def cancel_manual(self):
        """撕掉手动放的那一场（环境面板切走「暴雨」）。自动雨循环不受影响。"""
        if not self.manual:
            return False
        self.manual = False
        self.enabled = self._manual_prev
        self.phase = FOCUS
        self.phase_t = 0
        self.settle_t = 0
        self.pressure = 0.0
        return True

    # ── 推进 ──
    def step(self, pets, shelters):
        shelters = [sh for sh in (shelters or ()) if sh is not None]
        if not (self.enabled or self.manual):
            # 关掉：雨收回、门打开，但相位不前进。
            # 没有庇护所不再冻结相位 —— 雨照跑，只是没门可关、没安全区可躲。
            self.pressure = 0.0
            self.rain_drive = max(0.0, self.rain_drive - 1.0 / self.fade_ticks)
            for sh in shelters:
                if sh.door_state in (CLOSED, CLOSING):
                    sh.start_opening()
            return
        if self.phase == FOCUS:
            self._step_focus(shelters)
        elif self.phase == GATHER:
            self._step_gather(pets, shelters)
        else:
            self._step_sleep(shelters)

    def _step_focus(self, shelters):
        self.phase_t += 1
        self.settle_t = 0
        warn = self.warning_ticks
        remain = self.focus_ticks - self.phase_t
        if remain <= warn:
            self.pressure = smoothstep(0.0, 1.0,
                                       1.0 - max(0, remain) / float(max(1, warn)))
        else:
            self.pressure = 0.0
        # 上一场暴雨的余量按 fade 收回
        self.rain_drive = max(0.0, self.rain_drive - 1.0 / self.fade_ticks)
        if self.phase_t >= self.focus_ticks:
            self.phase = GATHER
            self.phase_t = 0
            self.settle_t = 0
            self.pressure = 1.0
            self.cycle_id += 1          # 新一轮雨：first_drop_done 该复位了

    def _step_gather(self, pets, shelters):
        self.phase_t += 1
        self.pressure = 1.0
        self.rain_drive = min(1.0, self.rain_drive + 1.0 / self.rise_ticks)
        if not shelters:
            # 没有庇护所：没有门可关，也不该靠 all([]) == True 侥幸过闸。
            # 等雨势爬满（或兜底超时）就直接进暴雨期，绝不卡死在集合段。
            if self.rain_drive >= 1.0 or self.phase_t >= self.gather_timeout:
                self.phase = SLEEP
                self.phase_t = 0
                self.settle_t = 0
            return
        if all(sh.door_closed for sh in shelters):
            self.settle_t += 1
            if self.settle_t >= self.settle_ticks:
                self.phase = SLEEP
                self.phase_t = 0
                self.settle_t = 0
            return
        if any(sh.door_state == CLOSING for sh in shelters):
            return
        if self.phase_t >= self.gather_timeout or _all_inside(pets, shelters):
            for sh in shelters:
                sh.start_closing()

    def _step_sleep(self, shelters):
        # 手动暴雨也必须拥有真实的暴雨时长。旧代码这里每 tick 把 phase_t
        # 重置为 0，导致手动暴雨永远停在 SLEEP，表现成「暴雨番茄钟不结束」。
        self.phase_t += 1
        if self.manual:
            self.pressure = 1.0
            fade_start = max(0, self.sleep_ticks - self.fade_ticks)
            if self.phase_t >= fade_start:
                self.rain_drive = max(0.0, 1.0 - (
                    self.phase_t - fade_start) / float(max(1, self.fade_ticks)))
            else:
                self.rain_drive = 1.0
            for sh in shelters:
                if sh.door_state == OPENING:
                    sh.start_closing()
            if self.phase_t >= self.sleep_ticks:
                self.phase = FOCUS
                self.phase_t = 0
                self.settle_t = 0
                self.pressure = 0.0
                self.rain_drive = 0.0
                self.manual = False
                self.enabled = self._manual_prev
            return

        self.pressure = 1.0
        remain = self.sleep_ticks - self.phase_t
        if remain <= self.fade_ticks:
            # 收尾：雨势淡出的同时把门打开，猫随后自己醒
            self.rain_drive = max(0.0, self.rain_drive - 1.0 / self.fade_ticks)
            for sh in shelters:
                if sh.door_state in (CLOSED, CLOSING):
                    sh.start_opening()
        else:
            self.rain_drive = min(1.0, self.rain_drive + 1.0 / self.rise_ticks)
        if self.phase_t >= self.sleep_ticks:
            self.cycles_done += 1          # 一场雨安全过去：番茄钟 +1 级
            self.phase = FOCUS
            self.phase_t = 0
            self.settle_t = 0
            self.pressure = 0.0

    # ── 左下角 HUD 的原料（只给数据，绘制在 rendering/storm_hud.py） ──
    def hud_info(self, pets=None):
        """雨眠计时器的原料（绘制在 rendering/storm_hud.py）。

        ``ring_total`` / ``ring_remain`` 是主圆环外那一圈小圆点的比例：

        * 征兆期与平静期在视觉上合并成同一个「平静期」环
          —— 整圈 = 整个专注期，进度 = 距这段合并阶段结束还有多久；
          只有最后那段征兆期会闪（``omen``）。
        * 暴雨期（集合段 + 雨眠段）单独一个环，进度 = 距暴雨结束还有多久。

        环境面板手动放的那场仍然不给倒计时。
        """
        if not self.enabled and not self.manual:
            return None
        if self.manual and self.phase in (GATHER, SLEEP):
            return None
        warn = self.warning_ticks
        if self.phase == FOCUS:
            left = max(0, self.focus_ticks - self.phase_t)
            mode = "cycle"
            ring_total = self.focus_ticks
            ring_remain = left
            omen = left <= warn
        else:
            # 暴雨期 = 集合段 + 雨眠段，一个环一路走到雨停
            mode = "storm"
            ring_total = self.gather_timeout + self.sleep_ticks
            if self.phase == GATHER:
                ring_remain = max(0, self.gather_timeout - self.phase_t) + self.sleep_ticks
            else:
                ring_remain = max(0, self.sleep_ticks - self.phase_t)
            omen = False
        need = 0
        first = None
        for p in (pets or ()):
            beh = getattr(p, "behavior", None)
            body = getattr(p, "body", None)
            if body is None or (beh is not None and beh.is_truly_dead()):
                continue
            if first is None:
                first = body          # 计时器固定显示第一只猫的数据
            miss = int(getattr(body, "food_hibernate", 0)) * 4 - (
                int(getattr(body, "food", 0)) * 4
                + int(getattr(body, "food_quarter", 0)))
            if miss > need:
                need = miss
        return {"mode": mode, "seconds": ring_remain / TICK_HZ,
                "phase": self.phase,
                "ring_total": ring_total, "ring_remain": ring_remain,
                "omen": omen, "tick": int(self.phase_t),
                "cycles": int(self.cycles_done),
                "food": int(getattr(first, "food", 0)) if first is not None else 0,
                "food_quarter": int(getattr(first, "food_quarter", 0)) if first is not None else 0,
                "food_max": int(getattr(first, "food_max", 0)) if first is not None else 0,
                "food_hibernate": (int(getattr(first, "food_hibernate", 0))
                                   if first is not None else 0),
                "starvation": (need + 3) // 4,
                "hungry": need > 0,
                "storm": self.phase in (GATHER, SLEEP)}

    # ── 存档 ──
    def to_dict(self):
        return {"enabled": bool(self.enabled), "manual": bool(self.manual),
                "phase": self.phase, "phase_t": int(self.phase_t),
                "cycles_done": int(self.cycles_done),
                "settle_t": int(self.settle_t),
                "rain_drive": float(self.rain_drive),
                "focus_minutes": self.focus_minutes,
                "warning_minutes": self.warning_minutes,
                "sleep_minutes": self.sleep_minutes}

    def from_dict(self, d):
        if not isinstance(d, dict):
            return