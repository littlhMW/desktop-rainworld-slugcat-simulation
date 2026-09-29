# -*- coding: utf-8 -*-
"""暴雨番茄钟：FOCUS → STORM_GATHER → SHELTER_SLEEP → FOCUS。

这一层只管相位 / 计时 / 雨强驱动 / 门的开关 / storm_pressure。渲染在
``rendering/rain_draw``，猫的行为在 ``behavior/fsm`` 的 StormSeekShelter 与
ShelterSleep —— 番茄钟自己不碰任何动画。

反编译口径：原版暴雨不是「切到下雨」，而是一段可预期的连续过程 —— 先是长时间
的专注，最后一小段世界开始不安，接着雨落下来，所有人躲进庇护所。所以这里唯一
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


def _all_inside(pets, sh):
    """所有活着的猫都进了安全区（真死的算「不用管」）。"""
    for p in pets:
        beh = getattr(p, "behavior", None)
        body = getattr(p, "body", None)
        if beh is None or body is None:
            continue
        if beh.is_truly_dead():
            continue
        if not sh.contains(body.chunk1.x, body.chunk1.y):
            return False
    return True


class StormCycle:
    """一个窗口一份。默认关闭（设置里开），且必须先有庇护所才会走相位。"""

    def __init__(self, enabled=False, focus_minutes=None, warning_minutes=None,
                 sleep_minutes=None):
        self.enabled = bool(enabled)
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
        """暴雨进行中（猫必须躲进庇护所的那两段）。"""
        return self.enabled and self.phase in (GATHER, SLEEP)

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
        self.phase = FOCUS
        self.phase_t = 0
        self.settle_t = 0
        self.rain_drive = 0.0
        self.pressure = 0.0

    # ── 推进 ──
    def step(self, pets, shelters):
        sh = shelters[0] if shelters else None
        if not self.enabled or sh is None:
            # 关掉 / 还没放庇护所：雨收回、门打开，但相位不前进
            self.pressure = 0.0
            self.rain_drive = max(0.0, self.rain_drive - 1.0 / self.fade_ticks)
            if sh is not None and sh.door_state in (CLOSED, CLOSING):
                sh.start_opening()
            return
        if self.phase == FOCUS:
            self._step_focus(sh)
        elif self.phase == GATHER:
            self._step_gather(pets, sh)
        else:
            self._step_sleep(sh)

    def _step_focus(self, sh):
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

    def _step_gather(self, pets, sh):
        self.phase_t += 1
        self.pressure = 1.0
        self.rain_drive = min(1.0, self.rain_drive + 1.0 / self.rise_ticks)
        if sh.door_closed:
            self.settle_t += 1
            if self.settle_t >= self.settle_ticks:
                self.phase = SLEEP
                self.phase_t = 0
                self.settle_t = 0
            return
        if sh.door_state == CLOSING:
            return
        if self.phase_t >= self.gather_timeout or _all_inside(pets, sh):
            sh.start_closing()

    def _step_sleep(self, sh):
        self.phase_t += 1
        self.pressure = 1.0
        remain = self.sleep_ticks - self.phase_t
        if remain <= self.fade_ticks:
            # 收尾：雨势淡出的同时把门打开，猫随后自己醒
            self.rain_drive = max(0.0, self.rain_drive - 1.0 / self.fade_ticks)
            if sh.door_state in (CLOSED, CLOSING):
                sh.start_opening()
        else:
            self.rain_drive = min(1.0, self.rain_drive + 1.0 / self.rise_ticks)
        if self.phase_t >= self.sleep_ticks:
            self.phase = FOCUS
            self.phase_t = 0
            self.settle_t = 0
            self.pressure = 0.0

    # ── 存档 ──
    def to_dict(self):
        return {"enabled": bool(self.enabled),
                "phase": self.phase, "phase_t": int(self.phase_t),
                "settle_t": int(self.settle_t),
                "rain_drive": float(self.rain_drive),
                "focus_minutes": self.focus_minutes,
                "warning_minutes": self.warning_minutes,
                "sleep_minutes": self.sleep_minutes}

    def from_dict(self, d):
        if not isinstance(d, dict):
            return
        self.enabled = bool(d.get("enabled", self.enabled))
        if d.get("phase") in (FOCUS, GATHER, SLEEP):
            self.phase = d["phase"]
        try:
            self.phase_t = max(0, int(d.get("phase_t", 0)))
            self.settle_t = max(0, int(d.get("settle_t", 0)))
            self.rain_drive = max(0.0, min(1.0, float(d.get("rain_drive", 0.0))))
        except Exception:
            pass
        self.set_durations(d.get("focus_minutes"), d.get("warning_minutes"),
                           d.get("sleep_minutes"))