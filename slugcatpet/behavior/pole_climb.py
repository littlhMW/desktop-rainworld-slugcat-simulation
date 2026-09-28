"""竖杆攀爬控制器：approach→climb→tip→摔落/下杆，每 tick 调 update(want_dismount)，返回 True=结束。"""
from __future__ import annotations
import math

from ..behavior import tuning
from ..world.pole import VERTICAL, cross_partner

# 竖杆攀爬参数
ARRIVE_EPS = 26.0
APPROACH_TIMEOUT = 400
CLIMB_TIMEOUT = 1200
GRAV = 0.9
SIDE_OFF = 5.0
TIP_ENTER_PAD = 3.0
TIP_TIMEOUT = 1200
DESCEND_TIMEOUT = 400
ARC_R = 17.0


class PoleClimber:
    def __init__(self, win, pole, rng=None, start=None):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.pole = pole
        self.phase = "approach"
        self.timer = 0
        self.tip_ticks = 0
        self.giveup = False
        self.rng = rng
        self.disbalance = 0.0
        self.balance_counter = 0.0
        # 换杆请求：("h", 横杆, 交点x) 交叉杆转横 / ("v", 竖杆, None) 跳向另一根杆
        self.handoff = None
        self._cross_t = 0            # 在交点附近逗留的 tick 数
        if start == "climb" and pole is not None:
            self._grab()          # 交叉杆从横杆直接转竖杆，不重走 approach

    def _roll(self):
        return self.rng.random() if self.rng is not None else 0.5

    def update(self, want_dismount=False):
        self.timer += 1
        b = self.body
        c1 = b.chunk1

        if self.phase == "approach":
            b.walk_to(self.pole.x)
            d = abs(c1.x - self.pole.x)
            top, bot = min(self.pole.ay, self.pole.by), max(self.pole.ay, self.pole.by)
            if d < ARRIVE_EPS and c1.on_floor:
                self._grab()
            elif (not c1.on_floor and d < tuning.POLE_AIRGRAB_R
                  and top - tuning.POLE_AIRGRAB_PAD <= c1.y <= bot + tuning.POLE_AIRGRAB_PAD):
                self._grab()      # jump-pole-hopping：空中贴杆即抓
            elif self.timer > APPROACH_TIMEOUT:
                self.giveup = True
                return True
            return False

        if self.phase == "climb":
            self._drive_climb()
            hp = self._cross_hpole()
            if hp is None:
                self._cross_t = 0
            else:
                self._cross_t += 1
                if (self._cross_t >= tuning.CROSS_DWELL
                        and self._roll() < tuning.CROSS_SWITCH_PROB):
                    self.handoff = ("h", hp, self.pole.x)   # 交点处转横杆
                    return True
            if c1.y <= self.pole.top_y + TIP_ENTER_PAD or self.timer > CLIMB_TIMEOUT:
                self._enter_tip()
            return False

        if self.phase == "tip":
            return self._drive_tip(want_dismount)

        if self.phase == "descend":
            return self._drive_descend()

        return False

    def _grab(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        b.stop_walk()
        b.standing = True
        b.on_pole = True
        b.animation = "ClimbOnBeam"
        b.pole_x = self.pole.x
        b.facing = 1 if c0.x >= self.pole.x else -1
        c0.vx = c0.vy = 0.0
        self.phase = "climb"

    def _drive_climb(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        tx = self.pole.x + b.facing * SIDE_OFF
        c0.vx = 0.0
        c0.x = (c0.x + tx) / 2.0
        c1.x = (c1.x * 7.0 + tx) / 8.0
        c0.vy *= 0.5
        c0.vy += -1.0 * b.stats.pole_fac    # 爬升推进×种族因子，抗重力项不缩放
        c0.vy += -(1.0 + GRAV)
        c1.vy += (1.0 - GRAV)

    def _enter_tip(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        b.animation = "BeamTip"
        self.pole.has_been_climbed = True
        c1.pinned = True
        c1.x = self.pole.x
        c1.y = self.pole.top_y
        c1.vx = c1.vy = 0.0
        c0.pinned = True
        c0.vx = c0.vy = 0.0
        self.disbalance = 0.0
        self.balance_counter = 0.0
        self.gfx.disbalance = 0.0
        self.gfx.balance_counter = 0.0
        self.phase = "tip"
        self.tip_ticks = 0

    def _drive_tip(self, want_dismount):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        px, top = self.pole.x, self.pole.top_y
        self.tip_ticks += 1
        c1.x = px
        c1.y = top
        # disbalance 随机游走
        if self._roll() < tuning.BAL_FLAIL_PROB:
            self.disbalance += tuning.BAL_FLAIL_TIP
        else:
            self.disbalance -= tuning.BAL_RECOVER
        self.disbalance = max(0.0, min(tuning.BAL_MAX, self.disbalance))
        self.balance_counter += 1.0 + self.disbalance / 40.0 * (1.0 + self._roll())
        if self.balance_counter > tuning.BAL_COUNTER_WRAP:
            self.balance_counter -= tuning.BAL_COUNTER_WRAP
        sway = math.sin(self.balance_counter / tuning.BAL_COUNTER_WRAP * 2.0 * math.pi)
        lean = sway * (self.disbalance + 20.0) * tuning.BAL_SWAY_X
        lean = max(-ARC_R + 1.0, min(ARC_R - 1.0, lean))
        c0.x = px + lean
        c0.y = top - math.sqrt(max(1.0, ARC_R * ARC_R - lean * lean))
        c0.vx = c1.vx = 0.0
        self.gfx.disbalance = self.disbalance
        self.gfx.balance_counter = self.balance_counter
        # 主动下杆：爬下或跳下
        if self.tip_ticks > tuning.TIP_MIN_TICKS:
            # 玩耍：杆顶观望，附近有别的杆就跳过去（原版 jump-pole-hopping）
            other = self._hop_candidate()
            if other is not None and self._roll() < tuning.POLE_TIP_HOP_PROB:
                self._hop_to(other)
                return True
        if self.tip_ticks > tuning.TIP_MIN_TICKS and want_dismount:
            other = self._hop_candidate()
            if other is not None and self._roll() < tuning.POLE_HOP_PROB:
                self._hop_to(other)                     # 体力见底：宁可跳杆
                return True
            if self._roll() < tuning.TIP_DISMOUNT_CLIMB_PROB:
                self._begin_descend()
                return False
            self._jump_down()
            return True
        # 失衡摔落
        if ((self.disbalance >= tuning.TIP_FALL_DISBALANCE
             and self._roll() < tuning.TIP_FALL_PROB)
                or self.tip_ticks > TIP_TIMEOUT):
            self._fall(lean)
            return True
        return False

    def _cross_hpole(self):
        """胸口附近有横杆交叉 → 可换到横杆（原版 ClimbOnBeam 侧向 HangFromBeam）。"""
        if self.win is None or self.pole is None:
            return None
        hp = cross_partner(self.pole, self.win.poles)
        if hp is None:
            return None
        c0 = self.body.chunk0
        return hp if abs(c0.y - hp.ay) <= tuning.CROSS_PAD else None

    def _hop_candidate(self):
        """最近的可跳目标竖杆。"""
        if self.win is None:
            return None
        best, bd = None, tuning.POLE_HOP_SEEK_R
        for p in self.win.poles:
            if p is self.pole or p.kind != VERTICAL:
                continue
            d = math.hypot(p.bx - self.pole.x, p.by - self.pole.top_y)
            if d < bd:
                best, bd = p, d
        return best

    def _hop_to(self, other):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = False
        c1.pinned = False
        b.on_pole = False
        b.animation = None
        d = 1.0 if other.x > self.pole.x else -1.0
        c0.vx += d * tuning.POLE_HOP_VX
        c1.vx += d * tuning.POLE_HOP_VX * 0.75
        c0.vy -= tuning.POLE_HOP_VY
        c1.vy -= tuning.POLE_HOP_VY * 0.85
        self.handoff = ("v", other, None)
        self._reset_pose()

    def _begin_descend(self):
        b = self.body
        b.chunk0.pinned = False
        b.chunk1.pinned = False
        b.animation = "ClimbOnBeam"
        self.phase = "descend"
        self.timer = 0
        self.gfx.disbalance = 0.0

    def _drive_descend(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        tx = self.pole.x + b.facing * SIDE_OFF
        c0.vx = 0.0
        c0.x = (c0.x + tx) / 2.0
        c1.x = (c1.x * 7.0 + tx) / 8.0
        c0.vy *= 0.5
        c0.vy += 1.0
        c1.vy += 1.0
        return b.on_floor() or self.timer > DESCEND_TIMEOUT

    def _fall(self, lean):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = False
        c1.pinned = False
        b.on_pole = False
        b.animation = None
        d = 1.0 if lean >= 0 else -1.0
        c0.vx += d * 3.5
        c1.vx += d * 1.5
        c0.vy -= 0.5
        self._reset_pose()

    def _jump_down(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = False
        c1.pinned = False
        b.on_pole = False
        b.animation = None
        c1.vy += 2.0
        c0.vy += 2.0
        c0.vx += b.facing * 1.0
        self._reset_pose()

    def _reset_pose(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self.gfx.disbalance = 0.0

    def release(self):
        self.body.chunk0.pinned = False
        self.body.chunk1.pinned = False
        self.body.on_pole = False
        self.body.animation = None
        self._reset_pose()
