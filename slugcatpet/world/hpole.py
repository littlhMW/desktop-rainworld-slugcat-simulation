"""横杆借力控制器：swing→reel→grip→pullup→stand 状态机；update() 返回 True=结束。"""
from __future__ import annotations

import math

from ..behavior import tuning
from .pole import VERTICAL, cross_partner

# 各阶段计时/距离/速度常量
CONN = 17.0
SWAY_TICKS = 55
GRIP_IDEAL = 9.0
GRIP_DIST = 16.0
REEL_RATE = 2.0
REEL_TIMEOUT = 240
HANG_TICKS = 28
PULLUP_TICKS = 22
STAND_HOVER = 5.0
STAND_TICKS = 200
WALK_SPEED = 2.1        # 原版 StandOnBeam: dynamicRunSpeed = 2.1 × runspeedFac
WALK_MARGIN = 14.0
TURN_PERIOD = 20
TURN_PROB = 0.5
JUMP_DOWN_VY = 2.0
AIRGRAB_TIMEOUT = 90
# 原版 HangFromBeam：沿横杆横向攀行（Player.cs 7651-7656）
HANG_WALK_SPEED = 1.6
HANG_EDGE = 6.0
# 原版 StandOnBeam：canJump = 5，站杆面能起跳（Player.cs 7798）
JUMP_OFF_VX = 2.2


class HPoleController:
    def __init__(self, win, pole, rng=None, start=None, start_x=None):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.tongue = win.tongue
        self.pole = pole
        self.rng = rng
        # 换杆请求：("v", 竖杆, "climb") 交叉杆转竖杆
        self.handoff = None
        self.air_target = None       # 带方向跳杆：空中要抓住的那根杆
        self._cross_t = 0            # 在交点附近逗留的 tick 数
        self._cross_roll = None      # 本次经过交点的换杆掷骰结果（离开交点重置）
        # 刚从竖杆换过来时先离开交点，否则会在交点被反复换回去（卡死）
        self._cross_armed = (start != "hang")
        self.phase = "swing" if self.tongue is not None else "airgrab"
        self.timer = 0
        self.giveup = False
        self._walk_dir = 1
        self._stand_t = 0
        self._pause = 0
        self._swing_t = 0
        self.disbalance = 0.0
        self._sway_c = 0.0
        self._wobble_target = 45.0
        self._hang_f = 10          # 原版 HangFromBeam animationFrame（1..20，静止靠 10）
        self._hang_walk = 0        # 悬挂时还要横向爬多少 tick
        self.goal_x = None       # 非 None：站杆面上走到这个 x 就停住（去够东西）
        self.goal_eps = None     # 停位容差（None=tuning.HPOLE_GOAL_EPS；够东西时收紧）
        self.want = None         # 真正的目标点 (x,y)：落在杆面外时按方向/距离跳过间隙
        self._gap_t = 0          # 卡在杆端跳不出去的 tick 数（超时清 want，别原地站死）
        # 锚点固定到杆
        lo, hi = self._extent()
        if self.tongue is not None:
            a = self.tongue.anchor
            ax = a[0] if a is not None else (lo + hi) * 0.5
        else:
            ax = self.body.chunk0.x
        self._anchor = (max(lo + 2.0, min(hi - 2.0, ax)), pole.ay)
        if start == "hang" and pole is not None:
            # 交叉杆从竖杆直接转横杆：就地抓杆，不重走摆荡/引体
            hx = self.body.chunk0.x if start_x is None else start_x
            hx = max(lo + 2.0, min(hi - 2.0, hx))
            self._anchor = (hx, pole.ay)
            self._grip(hx, pole.ay)
            self.phase = "hang"
            self.timer = 0

    # 杆几何
    def _extent(self):
        return min(self.pole.ax, self.pole.bx), max(self.pole.ax, self.pole.bx)

    def _walk_band(self, margin=WALK_MARGIN):
        """杆面可走带：杆端内缩 margin，且不越出窗口。

        越出窗口时下身 chunk 会被窗口边界夹住、上身还在往前挪 —— 连接约束被拉到
        极限，起身（GetUpOnBeam）时会看到下身瞬移。原版杆子永远在房间格内。
        """
        lo, hi = self._extent()
        lo, hi = lo + margin, hi - margin
        wl = getattr(self.win, "_WL", None)
        if wl:
            lo, hi = max(lo, margin), min(hi, float(wl) - margin)
        if hi < lo:
            mid = (lo + hi) * 0.5
            lo = hi = mid
        return lo, hi

    def update(self):
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return True
        return m()

    # 无舌前段：贴杆即抓，超时放弃
    def _phase_airgrab(self):
        b = self.body
        lo, hi = self._extent()
        ax = max(lo + 2.0, min(hi - 2.0, b.chunk0.x))
        ay = self.pole.ay
        if math.hypot(b.chunk0.x - ax, b.chunk0.y - ay) <= GRIP_DIST:
            self._anchor = (ax, ay)
            self._grip(ax, ay)
            self.phase = "hang"
            self.timer = 0
            return False
        if self.timer > AIRGRAB_TIMEOUT:
            self.giveup = True
            return True
        return False

    # 前段：舌头吊杆
    def _phase_swing(self):
        tg = self.tongue
        if tg is None or not tg.attached:         # 舌头掉了 → 放弃
            self.giveup = True
            return True
        tg.anchor = self._anchor  # 固定锚点
        if self.timer > SWAY_TICKS:
            self.phase = "reel"
            self.timer = 0
        return False

    def _phase_reel(self):
        tg = self.tongue
        if tg is None or not tg.attached:
            self.giveup = True
            return True
        ax, ay = self._anchor
        tg.anchor = self._anchor
        tg.set_targets(ideal=GRIP_IDEAL, reel_rate=REEL_RATE)  # 降目标绳长
        if abs(self.body.chunk0.y - ay) <= GRIP_DIST or self.timer > REEL_TIMEOUT:
            self._grip(ax, ay)
            self.phase = "hang"
            self.timer = 0
        return False

    # 换手
    def _grip(self, ax, ay):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        if self.tongue is not None:
            self.tongue.retract()
            self.tongue.reset_config()
        b.suspended = False
        b.on_pole = True
        b.standing = True
        b.animation = "HangFromBeam"
        b.pole_x = ax
        b.pole_y = ay  # 手抓点 y
        b.pole_move = 0
        b.facing = 1 if c0.x >= c1.x else -1
        # 上身钉杆线
        c0.pinned = True
        c0.x = ax
        c0.y = ay
        c0.vx = c0.vy = 0.0
        # 下身解钉自由垂
        c1.pinned = False

    def _phase_hang(self):
        """吊在横杆下：原版 HangFromBeam —— 可沿杆横向攀行（臂摆 20 帧一圈 + 下身侧摆）。

        Player.cs 7631-7713：input.x 推动上身，animationFrame 1..20 循环，
        bodyChunks[1].vel.x 跟着节奏侧摆；input.jmp / input.y>0 → GetUpOnBeam。
        """
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        ax, ay = b.pole_x, self.pole.ay
        lo, hi = self._walk_band(HANG_EDGE)
        # 攀行方向：有目的地就去够，否则按当前朝向前进，走到杆端掉头
        move = 0
        if self.goal_x is not None:
            if abs(self.goal_x - ax) > tuning.HPOLE_GOAL_EPS:
                move = 1 if self.goal_x > ax else -1
        elif self._hang_walk > 0:
            self._hang_walk -= 1
            move = self._walk_dir
        if move != 0:
            nx = ax + HANG_WALK_SPEED * move
            if nx <= lo + HANG_EDGE or nx >= hi - HANG_EDGE:
                nx = max(lo + HANG_EDGE, min(hi - HANG_EDGE, nx))
                self._walk_dir = -move if self.goal_x is None else move
                move = 0
            ax = nx
        b.pole_move = move
        if move != 0:
            self._hang_f += 1
            if self._hang_f > 20:
                self._hang_f = 1
            c1.vx += b.facing * (0.5 + 0.5 * math.sin(
                self._hang_f / 20.0 * 2.0 * math.pi)) * -0.5
        elif self._hang_f > 10:
            self._hang_f -= 1
        elif self._hang_f < 10:
            self._hang_f += 1
        b.pole_x = ax
        c0.pinned = True
        c0.x = ax  # 上身钉杆线
        c0.y = ay
        c0.vx = c0.vy = 0.0
        c1.pinned = False
        vp = self._cross_vpole(ax, ay)
        if vp is None:
            self._cross_t = 0
        else:
            self._cross_t += 1
            if (self._cross_t >= tuning.CROSS_DWELL
                    and self._roll() < tuning.CROSS_SWITCH_PROB):
                self.handoff = ("v", vp, "climb")  # 交点处转竖杆（原版 上+吊杆）
                return True
        if self.timer > HANG_TICKS and move == 0:
            self.phase = "pullup"
            self.timer = 0
            self._pullup_from = (b.chunk1.x, b.chunk1.y)
        return False

    # 引体
    def _phase_pullup(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        b.animation = "GetUpOnBeam"
        ax, ay = b.pole_x, self.pole.ay
        t = min(1.0, self.timer / float(PULLUP_TICKS))
        tt = t * t * (3.0 - 2.0 * t)              # smoothstep
        # 终态：脚钉杆面上，身在其上
        c1.pinned = True
        feet_top_y = ay - STAND_HOVER
        body_top_y = feet_top_y - CONN
        fx0, fy0 = self._pullup_from
        c1.x = ax
        c1.y = fy0 + (feet_top_y - fy0) * tt
        c1.vx = c1.vy = 0.0
        c0.x = ax
        c0.y = ay + (body_top_y - ay) * tt
        c0.vx = c0.vy = 0.0
        if self.timer >= PULLUP_TICKS:
            self.phase = "stand"
            self.timer = 0
            self._stand_t = 0
            b.animation = "StandOnBeam"
            self._walk_dir = 1 if (self.rng is None or self.rng.random() < 0.5) else -1
        return False

    # 站杆面平衡走
    def _phase_stand(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        ay = self.pole.ay
        self._stand_t += 1
        feet_y = ay - STAND_HOVER
        lo, hi = self._walk_band()
        can_walk = hi > lo
        vp = self._cross_vpole(c1.x, ay)
        if vp is None:
            self._cross_t = 0
            self._cross_roll = None
        else:
            if self._cross_t == 0:
                self._cross_roll = self._roll()   # 每次经过交点只掷一次骰子
            self._cross_t += 1
            if (self.goal_x is None and self._cross_t >= tuning.CROSS_DWELL
                    and self._cross_roll is not None
                    and self._cross_roll < tuning.CROSS_SWITCH_PROB):
                self.handoff = ("v", vp, "climb")  # 站在交点上：转到竖杆
                return True
        # 原版要走到交叉格上再按键才换杆；不再主动跑向交点 —— 否则站在横杆上的
        # 猫总会自动跑去爬竖杆，一路爬到竖杆顶（用户反馈的「总往竖杆顶跑」）。
        steer = None
        if self.goal_x is not None:      # 目的地优先：走到位就刹住等抓取
            eps = (tuning.HPOLE_GOAL_EPS if self.goal_eps is None
                   else self.goal_eps)
            if abs(c1.x - self.goal_x) <= eps:
                steer = None
                self._walk_dir = 0
                can_walk = False
                self._pause = 6
            else:
                steer = 1 if self.goal_x > c1.x else -1
        if steer is not None:
            self._pause = 0
        # 低概率：翻到杆下再上来
        if (can_walk and self._pause <= 0 and self.rng is not None
                and self.rng.random() < tuning.HP_HANG_PROB):
            self._enter_swing_under()
            return False
        # 走走停停
        if self._pause > 0:
            self._pause -= 1
            walking = False
        else:
            walking = can_walk
            if (can_walk and self.rng is not None
                    and self.rng.random() < tuning.HP_PAUSE_PROB):
                self._pause = self.rng.randint(tuning.HP_PAUSE_MIN, tuning.HP_PAUSE_MAX)
                walking = False
        if walking:
            if (self._stand_t % TURN_PERIOD == 0 and self.rng is not None
                    and self.rng.random() < TURN_PROB):
                self._walk_dir = -self._walk_dir
            if steer is not None:            # 换杆意图优先于随机掉头
                self._walk_dir = steer
            nx = c1.x + WALK_SPEED * self._walk_dir
            if nx <= lo:
                nx, self._walk_dir = lo, 1
            elif nx >= hi:
                nx, self._walk_dir = hi, -1
            c1.x = nx
            b.facing = 1 if self._walk_dir > 0 else -1
        c1.y = feet_y
        b.pole_move = 1 if walking else 0
        c1.vx = WALK_SPEED * (1.0 if walking else 0.0) * b.facing
        c1.vy = 0.0
        # 走时晃身平衡
        if walking:
            if self._stand_t % tuning.HP_RETARGET_TICKS == 0 and self.rng is not None:
                self._wobble_target = self.rng.uniform(tuning.HP_WOBBLE_MIN, tuning.HP_WOBBLE_MAX)
            target = self._wobble_target
        else:
            target = 0.0
        self.disbalance += (target - self.disbalance) * 0.1
        roll = self.rng.random() if self.rng is not None else 0.5
        self._sway_c += 1.0 + self.disbalance / 40.0 * (1.0 + roll)
        if self._sway_c > tuning.BAL_COUNTER_WRAP:
            self._sway_c -= tuning.BAL_COUNTER_WRAP
        # 平衡摆动只在绘制层加，避免物理层重复偏移
        c0.x = c1.x
        c0.y = feet_y - CONN
        c0.vx = c0.vy = 0.0
        self.gfx.disbalance = self.disbalance
        self.gfx.balance_counter = self._sway_c
        self.gfx.look_at = (c0.x + b.facing * 60.0, c0.y)
        if (self._stand_t > STAND_TICKS and self.want is not None
                and self._gap_jump_to_want()):
            return True                        # 目标在杆面外：带方向/距离跳过间隙
        if self._stand_t > STAND_TICKS and self.goal_x is None:
            # 原版 StandOnBeam canJump=5：站杆面能起跳（向前上跳出去）
            plan = self._hop_candidate()
            if plan is not None and self._roll() < tuning.HP_HOP_PROB:
                self._hop_to(plan)          # 带方向跳到另一根杆，空中抓住（jump-pole-hopping）
                return True
            if self.rng is not None and self.rng.random() < tuning.HP_JUMP_PROB:
                self._jump_off()
            else:
                self._jump_down()
            return True
        return False

    def _hop_candidate(self):
        """站横杆能带方向跳过去抓住的杆（原版 jump-pole-hopping）。返回 hop_plan 元组。

        有目标点 want 时按「落点离目标最近」选杆与方向（斜上/斜下/左右带偏移都能跳）。
        """
        from ..planning.pole_hop import hop_plan
        if self.win is None or self.pole is None:
            return None
        stats = getattr(getattr(self.win, "cat", None), "stats", None)
        c0 = self.body.chunk0
        return hop_plan(stats, list(self.win.poles), c0.x, c0.y, exclude=self.pole,
                        want=self.want)

    def _gap_jump_to_want(self) -> bool:
        """杆面走到头还够不到目标：按目标相对位置带方向/距离跳过间隙。

        三条路，按顺序挑第一条规划得通的（都不掷骰子，规划说行才动）：
          1) 跳过去在空中抓另一根杆（hop_plan，横杆/竖杆都算）
          2) 跳过间隙落到对侧窗口顶边（platform_hop_plan，单向平台）
        目标还在杆面范围内就返回 False（走过去/伸手即可）。
        """
        if self.want is None or self.win is None or self.pole is None:
            return False
        wx, wy = self.want
        lo, hi = self._walk_band()
        if lo <= wx <= hi:
            return False
        c0, c1 = self.body.chunk0, self.body.chunk1
        edge = hi if wx > hi else lo
        if abs(c1.x - edge) > tuning.HPOLE_GOAL_EPS:
            self.goal_x, self.goal_eps = edge, tuning.HPOLE_GOAL_EPS
            return False                       # 先沿杆面走到那一端
        stats = getattr(getattr(self.win, "cat", None), "stats", None)
        if stats is None:
            return False
        from ..core import chunkphys
        from ..planning.pole_hop import hop_plan, platform_hop_plan
        plan = hop_plan(stats, list(self.win.poles), c0.x, c0.y,
                        exclude=self.pole, want=self.want)
        if plan is not None:
            self._hop_to(plan)
            return True
        pf = platform_hop_plan(stats, chunkphys.platforms(), c0.x, c0.y, want=self.want)
        if pf is None:
            self._gap_t += 1                   # 跳不过去：站一会儿再放弃，别永远钉在杆端
            if self._gap_t > tuning.HPOLE_GAP_GIVEUP:
                self.want = None
                self.goal_x = None
            return False
        kind, hold, md, _lx, _ly = pf
        self.goal_x = None
        self.body.facing = 1 if md > 0 else -1
        if kind == "drop":                     # 走出去掉到下面的平台上
            self.body.release_to_air(move_dir=md)
        else:                                  # 带方向/距离跳过去
            self.body.tip_launch(hold_ticks=hold, move_dir=md)
        self.body.chunk0.cy = self.body.chunk1.cy = 0
        self.air_target = None
        self._reset_pose()
        return True

    def _hop_to(self, plan):
        """按实测小跳弧带方向跳出杆面；空中由 FSM 的 _air_pole_grab 抓住目标杆。"""
        b = self.body
        pole, md, _tick = plan
        b.facing = 1 if md > 0 else -1
        self.air_target = pole
        b.pole_hop(md, move_dir=md)
        b.chunk0.cy = b.chunk1.cy = 0   # 已经离杆：别用上一帧的落地标记
        self._reset_pose()

    def _roll(self):
        return self.rng.random() if self.rng is not None else 0.5

    def _vp_near(self, x, y):
        """(交叉的竖杆, 是否压在交点上)；没有交叉竖杆时 (None, False)。"""
        if self.win is None or self.pole is None:
            return None, False
        vp = cross_partner(self.pole, self.win.poles)
        if vp is None or vp.kind != VERTICAL:
            return None, False
        near = (abs(x - vp.x) <= tuning.CROSS_PAD
                and min(vp.ay, vp.by) - tuning.CROSS_PAD <= y
                <= max(vp.ay, vp.by) + tuning.CROSS_PAD)
        return vp, near

    def _cross_vpole(self, x, y):
        """该处是否压在竖杆交点上（原版 tile 的 verticalBeam）。"""
        vp, near = self._vp_near(x, y)
        if vp is None or not near:
            self._cross_armed = True     # 离开交点，重新允许换杆
            return None
        return vp if self._cross_armed else None

    def _enter_swing_under(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        b.animation = "HangFromBeam"
        b.pole_x = c1.x
        b.pole_y = self.pole.ay
        c0.pinned = True
        c0.x = c1.x
        c0.y = self.pole.ay
        c0.vx = c0.vy = 0.0
        c1.pinned = False
        self._swing_t = 0
        self.phase = "swing_under"

    def _phase_swing_under(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = True
        c0.x = b.pole_x
        c0.y = self.pole.ay
        c0.vx = c0.vy = 0.0
        self._swing_t += 1
        c1.vx += 0.4 * (1.0 if (self._swing_t // 14) % 2 == 0 else -1.0)
        if self._swing_t > tuning.HP_HANG_TICKS:
            self.phase = "pullup"
            self.timer = 0
            self._pullup_from = (c1.x, c1.y)
        return False

    def _jump_off(self):
        """站横杆面起跳（原版 StandOnBeam canJump=5）：向前上方跳出。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = False
        c1.pinned = False
        b.on_pole = False
        b.animation = None
        b.standing = True
        b.feet_stuck = None
        b.crawl_anchor = None
        b.crawl_pose = 0.0
        b.walk_target_x = None
        d = 1.0 if b.facing >= 0 else -1.0
        c0.vy = b.stats.jump_head
        c1.vy = b.stats.jump_feet
        c0.vx += d * JUMP_OFF_VX
        c1.vx += d * JUMP_OFF_VX * 0.6
        b.jump_boost = b.stats.jump_boost
        self._reset_pose()

    def _jump_down(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        c0.pinned = False
        c1.pinned = False
        b.on_pole = False
        b.animation = None
        c1.vy += JUMP_DOWN_VY
        c0.vy += JUMP_DOWN_VY
        c0.vx += b.facing * 1.0
        self._reset_pose()

    def _reset_pose(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None
        self.gfx.disbalance = 0.0
        self.body.pole_move = 0

    # 打断清理
    def release(self):
        b = self.body
        b.coyote = max(getattr(b, "coyote", 0), tuning.POLE_COYOTE_TICKS)
        b.chunk0.pinned = False
        b.chunk1.pinned = False
        b.on_pole = False
        b.animation = None
        b.pole_move = 0
        if self.tongue is not None:
            if self.tongue.attached:
                self.tongue.retract()
            self.tongue.reset_config()
        b.suspended = False
        self._reset_pose()
