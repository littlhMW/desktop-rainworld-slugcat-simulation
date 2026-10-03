# -*- coding: utf-8 -*-
"""守望者（Watcher）种族定义：标准杂食（7 / 4），深蓝紫体色 + 发光 + 伪装。

数值反编译出处：
  SlugcatStats.cs:115-166  SlugcatFoodMeter → (7, 4)
  SlugcatStats.cs:268-273  throwingSkill 1 / lungsFac 0.8
  PlayerGraphics.cs:3830   DefaultSlugcatColor = HSL2RGB(0.63055557, 0.54, 0.2)
  PlayerGraphics.cs:3600-3602  ApplyPalette 里守望者/夜猫还有一层压黑：
                           color2 = Lerp(palette.blackColor,
                                         HSL2RGB(0.63055557, 0.54, 0.5),
                                         Lerp(0.08, 0.04, palette.darkness))
                           取 darkness=0 → 黑底掺 8% 紫 → RGB(5,7,16)（几乎黑的深紫）
  PlayerGraphics.cs:3873   DefaultBodyPartColorHex → [body, "FFFFFF"]（眼=白=不染色）
  PlayerGraphics.cs:2672   InitializeLongerWatcherTail：尾段连接 6 / 10.5 / 10.5 / 10.5
                           （普通猫 4 / 7 / 7 / 7）—— 尾巴更长
  Player.cs:2568-2610      camoLimit 1600（涟漪等级不足时）/ enterIntoCamoDuration 80 /
                           exitOutOfCamoDuration 40 / 耗尽后有一段强制解除的疲劳

桌宠简化：涟漪等级、传送点、泪隙这些子系统不存在，所以实装「发光 + 伪装 + 追光浮游」：
  * 发光 —— 自身一圈冷光（wiki：首遇陀螺后开始发光）
  * 伪装 —— 站住不动且附近没有威胁时进入半透明隐身，蜥蜴更难盯上它；
             电量按原版 1600 tick 上限，耗尽强制解除并进入数秒疲劳
  * 追光浮游 —— 安静时偶尔高跳，在最高点闭眼、渐隐并缓慢追随鼠标约 4 秒；
                以蓝紫扰动环表现能力，不改变圣徒的超度状态
"""
from __future__ import annotations

import math

from dataclasses import replace

from ..core.units import clampf
from .base import CatCaps, CatDef
from .personality import DEFAULT_PERSONALITY
from .stats import DEFAULT_STATS

# Watcher 专属「追光浮游」玩耍：这是桌宠中的轻量化实现，不会改变圣徒的
# Ascension 状态。40Hz 下浮空保持 4 秒，起跳阶段仍使用正常物理，鼠标拖动、
# 碰撞和落地因此不会被伪造的传送位置吞掉。
WATCH_FLOAT_TICKS = 160
WATCH_FLOAT_COOLDOWN = 1200
WATCH_FLOAT_CHANCE = 0.0008
WATCH_LAUNCH_VY = -17.5
WATCH_LAUNCH_VX_MAX = 5.5
WATCH_LAUNCH_MIN_RISE = 48.0


class WatcherFloatFX:
    """守望者浮空期间的蓝紫扭曲火焰环。"""

    def __init__(self, fsm):
        self.fsm = fsm
        self.phase = 0.0

    def _center(self):
        b = self.fsm.body
        c0, c1 = b.chunk0, b.chunk1
        return (0.5 * (c0.x + c1.x), 0.5 * (c0.y + c1.y))

    def draw_under(self, p, ts=1.0):
        # 柔和底光让身体渐隐时仍能读出轮廓。
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QRadialGradient, QBrush
        from ..rendering.pixelmode import aa_hint
        x, y = self._center()
        p.save()
        aa_hint(p)
        radius = 38.0 + 4.0 * math.sin(self.phase * 1.7)
        grad = QRadialGradient(QPointF(x, y), radius)
        grad.setColorAt(0.0, QColor(92, 92, 255, 80))
        grad.setColorAt(0.56, QColor(114, 50, 220, 38))
        grad.setColorAt(1.0, QColor(40, 22, 120, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(x, y), radius, radius)
        p.restore()

    def draw(self, p):
        # 多段扰动曲线组成环状火焰，避开昂贵的路径布尔运算。
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QPainterPath, QPen
        from ..rendering.pixelmode import aa_hint
        x, y = self._center()
        p.save()
        aa_hint(p)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for ring, (base_r, color, width, alpha) in enumerate((
                (26.0, (116, 104, 255), 1.8, 190),
                (32.0, (177, 74, 238), 1.2, 145))):
            path = QPainterPath()
            count = 28
            for i in range(count + 1):
                a = math.tau * i / count
                wobble = (2.7 * math.sin(self.phase * 2.1 + a * 3.0 + ring)
                          + 1.6 * math.sin(self.phase * 3.7 - a * 5.0))
                r = base_r + wobble
                q = QPointF(x + math.cos(a) * r, y + math.sin(a) * r)
                if i == 0:
                    path.moveTo(q)
                else:
                    path.lineTo(q)
            p.setPen(QPen(QColor(*color, alpha), width))
            p.drawPath(path)
        p.restore()


class WatcherFloat:
    """起跳→最高点隐身→延迟追光标→落回正常物理的 4 秒状态。"""

    def __init__(self, fsm):
        self.fsm = fsm
        self.fx = WatcherFloatFX(fsm)
        self.phase = "launch"
        self.timer = 0
        self.float_timer = 0
        self.apex_y = None
        self.lag_x = float(fsm.body.chunk1.x)
        self.lag_y = float(fsm.body.chunk1.y)
        self.target_x = self.lag_x
        self.alpha = 0.0
        self.rise_y = float(fsm.body.chunk1.y)

    def enter(self):
        fsm, b = self.fsm, self.fsm.body
        c0, c1 = b.chunk0, b.chunk1
        self.rise_y = c1.y
        b.set_posture(True)
        b.stop_walk()
        b.suspended = False
        b.hover = False
        b.on_pole = False
        b.wall_side = 0
        b.ceil_cling = False
        c0.pinned = c1.pinned = False
        cur = fsm.cursor
        move_x = 0
        if cur is not None:
            self.target_x = float(cur[0])
            d = max(-WATCH_LAUNCH_VX_MAX,
                    min(WATCH_LAUNCH_VX_MAX, (self.target_x - c1.x) * 0.025))
            c0.vx = c1.vx = d
            move_x = 1 if d > 0.05 else (-1 if d < -0.05 else 0)
        else:
            c0.vx = c1.vx = 0.0
        # 走内部起跳路径清掉 feet_stuck / coyote 等接地锁，再把高度提升到
        # 守望者的高跳档；直接改速度会被站立态的脚钉住逻辑吃掉。
        b._do_jump("stand", move_x, hold_ticks=8)
        c0.vy = WATCH_LAUNCH_VY
        c1.vy = WATCH_LAUNCH_VY * 0.92
        fsm.gfx.watcher_float_alpha = 0.0

    def _at_apex(self):
        b = self.fsm.body
        c0, c1 = b.chunk0, b.chunk1
        rise = self.rise_y - c1.y
        # 两节速度均已过顶，并且确实离开地面，避免低矮地板误触发。
        return (rise >= WATCH_LAUNCH_MIN_RISE and c0.vy >= -0.25
                and c1.vy >= -0.25)

    def _begin_float(self):
        b = self.fsm.body
        c0, c1 = b.chunk0, b.chunk1
        self.phase = "float"
        self.float_timer = 0
        self.apex_y = 0.5 * (c0.y + c1.y)
        self.lag_x = 0.5 * (c0.x + c1.x)
        self.lag_y = self.apex_y
        b.hover = True
        c0.vx = c1.vx = c0.vy = c1.vy = 0.0

    def tick(self):
        fsm, b, g = self.fsm, self.fsm.body, self.fsm.gfx
        self.timer += 1
        self.fx.phase += 0.11
        if self.phase == "launch":
            g.look_at = fsm.cursor
            if self._at_apex():
                self._begin_float()
            return False
        self.float_timer += 1
        cur = fsm.cursor
        if cur is not None:
            self.target_x = float(cur[0])
        # 明显延迟、极慢靠近光标的水平追踪；上下只作轻柔的落后摆动。
        self.lag_x += (self.target_x - self.lag_x) * 0.012
        bob = math.sin(max(0.0, self.float_timer - 12.0) * 0.065) * 9.0
        target_y = float(self.apex_y) + bob
        self.lag_y += (target_y - self.lag_y) * 0.08
        cx = 0.5 * (b.chunk0.x + b.chunk1.x)
        cy = 0.5 * (b.chunk0.y + b.chunk1.y)
        vx = max(-2.2, min(2.2, (self.lag_x - cx) * 0.07))
        vy = max(-1.5, min(1.5, (self.lag_y - cy) * 0.07))
        b.chunk0.vx = b.chunk1.vx = vx
        b.chunk0.vy = b.chunk1.vy = vy
        # 最高点闭眼并缓慢隐身，尾段提前渐显。
        fade_in = min(1.0, self.float_timer / 32.0)
        fade_out = min(1.0, max(0.0, (WATCH_FLOAT_TICKS - self.float_timer) / 28.0))
        self.alpha = min(fade_in, fade_out)
        g.watcher_float_alpha = self.alpha
        g.camo = self.alpha
        g.blink = 3
        g.look_at = fsm.cursor
        if self.float_timer >= WATCH_FLOAT_TICKS:
            return True
        return False

    def finish(self):
        b, g = self.fsm.body, self.fsm.gfx
        b.hover = False
        b.chunk0.vy += 1.0
        b.chunk1.vy += 1.0
        g.camo = 0.0
        self.fsm._camo_level = 0.0
        g.watcher_float_alpha = 0.0
        g.blink = 0

    def abort(self):
        self.finish()

# 伪装（Player.cs:2568-2610 + wiki Controls）
CAMO_MAX = 1600          # camoLimit：涟漪等级不足时的原版上限
CAMO_ENTER = 80          # enterIntoCamoDuration：进入伪装的渐隐 tick
CAMO_EXIT = 40           # exitOutOfCamoDuration：退出伪装的渐显 tick
CAMO_REGEN = 3           # 没隐身时每 3 tick 回 1 点（桌宠简化）
CAMO_FATIGUE = 240       # 电量耗尽后的疲劳（≈6 s 内不能再伪装）
CAMO_NEAR_THREAT = 260.0  # 这个距离内有威胁就不进入伪装
CAMO_SHAKE_MAX = 2.2     # 被鼠标抓着时：光标位移超过这个幅度就藏不住（剧烈摇晃）
CAMO_SHAKE_DECAY = 0.72  # 晃动幅度的衰减（松开鼠标后 ~10 tick 回落）


def _fsm_mount(fsm):
    """守望者：伪装电量 + 半透明隐身 + 追光浮游玩耍。"""
    fsm._camo_charge = CAMO_MAX
    fsm._camo_level = 0.0
    fsm._camo_fatigue = 0
    fsm._camo_regen = 0
    fsm._camo_shake = 0.0
    fsm._watcher_float = None
    fsm._watcher_float_cd = 180
    # A higher-priority action can leave WatcherFloat through the common FSM
    # transition path without calling its break callback.  Keep a one-tick
    # hand-off flag so that path cannot leave hover/camo/FX ownership behind.
    fsm._watcher_float_abort_pending = False

    def camo_tick():
        g, b = fsm.gfx, fsm.body
        # 浮游状态自己驱动渐隐，避免普通伪装电量在同一帧覆盖视觉值。
        wf = getattr(fsm, "_watcher_float", None)
        if wf is not None:
            g.camo = float(getattr(wf, "alpha", 0.0))
            return
        if fsm._camo_fatigue > 0:
            fsm._camo_fatigue -= 1
        th = fsm._threat_lizard()
        near = th is not None and abs(th.x - b.chunk1.x) < CAMO_NEAR_THREAT
        # 被鼠标抓着也会试着隐身；但 GrabController.drag 把光标位移写进被抓那
        # 一节的 vx/vy，甩得越猛这个值越大 —— 剧烈摇晃就藏不住（原版被甩的猫
        # 同样维持不了伪装）。
        held = fsm.grab.active
        cur = 0.0
        if held and fsm.grab.chunk is not None:
            c = fsm.grab.chunk
            cur = math.hypot(float(getattr(c, "vx", 0.0)), float(getattr(c, "vy", 0.0)))
        fsm._camo_shake = max(cur, fsm._camo_shake * CAMO_SHAKE_DECAY)
        idle = (fsm.state == "IdleStand" and b.on_floor() and not b.is_moving())
        can = (fsm._camo_fatigue <= 0 and fsm._camo_charge > 0
               and (held or idle) and fsm._camo_shake < CAMO_SHAKE_MAX
               and not b.swimming and not fsm._zerog() and not near)
        if can:
            fsm._camo_charge -= 1
            if fsm._camo_charge <= 0:            # 电量耗尽：强制解除 + 疲劳
                fsm._camo_charge = 0
                fsm._camo_fatigue = CAMO_FATIGUE
                g.blink = 8
        elif fsm._camo_fatigue <= 0:             # 沒隐身时慢慢回电
            fsm._camo_regen += 1
            if fsm._camo_regen >= CAMO_REGEN:
                fsm._camo_regen = 0
                fsm._camo_charge = min(CAMO_MAX, fsm._camo_charge + 1)
        step = (1.0 / CAMO_ENTER) if can else -(1.0 / CAMO_EXIT)
        fsm._camo_level = clampf(fsm._camo_level + step, 0.0, 1.0)
        g.camo = fsm._camo_level

    fsm.register_ticker(camo_tick)

    # 追光浮游属于「偶尔玩耍」而不是保命动作：仅在安静、落地、未被抓时
    # 抽签，且设冷却避免多只守望者在同一帧一起起飞。
    from ..behavior.action import BAND_PREEMPT, TAG_CHARACTER

    def float_gate(ctx):
        if fsm.state != "IdleStand" or fsm.grab.active:
            return False
        b = fsm.body
        if not b.on_floor() or b.swimming or fsm._zerog():
            return False
        if fsm._threat_lizard() is not None:
            return False
        cur = ctx.cursor
        if cur is None:
            return False
        if getattr(fsm.win, "cursor_cat_attention_allowed", True) is False:
            return False
        # 每 180 tick 至少留出一次机会；用个体 RNG 保持可复现。
        if fsm._watcher_float_cd > 0:
            return False
        return fsm.rng.random() < WATCH_FLOAT_CHANCE

    def float_start(ctx):
        fsm._watcher_float = WatcherFloat(fsm)
        fsm._watcher_float.enter()
        fsm._watcher_float_cd = WATCH_FLOAT_COOLDOWN
        fsm._transition("WatcherFloat")
        return True

    fsm.register_action("WatcherFloat", BAND_PREEMPT, gate=float_gate,
                        start=float_start, tags=(TAG_CHARACTER,))

    def float_tick():
        wf = getattr(fsm, "_watcher_float", None)
        if fsm._watcher_float_cd > 0:
            fsm._watcher_float_cd -= 1
        # WatcherFloat is an external state whose controller normally owns the
        # body.  If another action changed state directly, release the stale
        # controller before it can keep writing velocities or camo values.
        if fsm.state != "WatcherFloat":
            if wf is not None:
                wf.abort()
                fsm._watcher_float = None
            fsm._watcher_float_abort_pending = False
            return
        if fsm._watcher_float_abort_pending:
            fsm._watcher_float_abort_pending = False
            if wf is not None:
                wf.abort()
                fsm._watcher_float = None
            # A break callback may be invoked without a following transition
            # (for example during external cleanup).  Restore interaction and
            # give the normal FSM a safe state on the next tick.
            fsm._transition("Airborne" if not fsm.body.on_floor() else "IdleStand")
            return
        if wf is None:
            # A missing controller while still in this state is stale state,
            # not a fresh action opportunity (the gate requires IdleStand).
            fsm._transition("Airborne" if not fsm.body.on_floor() else "IdleStand")
            return
        if wf.tick():
            wf.finish()
            fsm._watcher_float = None
            fsm._transition("Airborne")

    fsm.register_ticker(float_tick)

    def float_break():
        wf = getattr(fsm, "_watcher_float", None)
        if wf is not None:
            wf.abort()
        fsm._watcher_float = None
        fsm._watcher_float_abort_pending = True

    fsm.register_state("WatcherFloat", enter=lambda: None,
                       tick=lambda cursor, disturbed: None,
                       brk=float_break, kill_break=float_break,
                       fx=lambda: (getattr(fsm, "_watcher_float", None).fx
                                   if getattr(fsm, "_watcher_float", None) is not None
                                   else None))
    fsm._interaction_blockers.add("WatcherFloat")


WATCHER_DEF = CatDef(
    key="watcher",
    # ApplyPalette（PlayerGraphics.cs:3600-3602）压黑后的守望者体色：
    # Lerp(black, HSL2RGB(0.63055557, 0.54, 0.5), 0.08) → (5, 7, 16)　几乎黑的深紫
    body_color=(5, 7, 16),
    eye_color=(255, 255, 255),    # DefaultBodyPartColorHex → FFFFFF（白＝不染色）
    frames={
        "head": ("base", "HeadA"),
        "face": ("base", "FaceA"),
        "face_blink": ("base", "FaceB"),
        "legs_walk": ("base", "LegsA"),
        "legs_crawl": ("base", "LegsACrawling"),
        "legs_air": ("base", "LegsAAir0"),
    },
    layout_file="watcher.json",
    atlas_keys=("base",),
    caps=CatCaps(tongue=False, ascension=False),
    stats=replace(DEFAULT_STATS, max_food=7, food_hibernate=4,
                  throwing_skill=1, lungs_fac=0.8),
    # 守望者：孤僻（不喜欢任何互动、喜欢远离其他猫、也不喜欢救人），一般勇敢
    personality=replace(DEFAULT_PERSONALITY, activity=0.35, stamina=1.0,
                        sociability=0.05, temper=0.35, crawl_like=0.5,
                        point_like=0.05, bravery=0.5, kindness=0.05,
                        play_style="sit", hurry=0.25, wake_like=0.05,
                        risk_tolerance=0.35, patience=0.85),
    # InitializeLongerWatcherTail（PlayerGraphics.cs:2672-2678）：尾巴更长
    visual={"tail_conn": (6.0, 10.5, 10.5, 10.5),
            "glow": (150, 190, 255)},
    tuning={},
    fsm_mount=_fsm_mount,
    wip=False,
)
