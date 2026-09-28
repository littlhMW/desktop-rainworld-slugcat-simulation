"""飞虫狩猎 FlyHunter：选猎物→取武器（石/矛）→预判弧线→投掷。

对应原版蛞蝓猫 AI：SlugcatAI 的猎物追踪 + ThrowController 的「捡石打飞行猎物」，
矛伤害同 Spear.damage。update() 返回路由串，与 StoneThrower 同构。
"""
from __future__ import annotations
import math

from ..core.units import clampf
from ..world import weaponphys
from ..cats.personality import DIET_VEGETARIAN, DIET_SPECIAL

GRAB_REACH = 18.0
REACH_GATE_K = 2.0
APPROACH_TIMEOUT = 260
MAX_FAILS = 4
ABANDON_FAILS = 3
THROW_FRAMES = 6

SEEK_R = 260.0          # 主动找猎物的半径
GIVEUP_TICKS = 220      # 追不到就放弃
CIEL_ABOVE_MAX = 190.0  # 猎物不能高过头顶太多
SPEED_STONE = 26.0      # 投石初速
SPEED_SPEAR = 34.0      # 投矛初速
LEAD_ITERS = 6
MIN_FLIGHT = 4.0
MAX_FLIGHT = 26.0
RECOIL = 0.3
AIM_DY_TOL = 9.0        # 出手高度容差：蟹猫只能水平投，得先跳到猎物那一层
AIM_JUMP_CD = 10        # 起跳重试间隔


def _edible(f, diet) -> bool:
    if f.dead or f.state != "free":
        return False
    if getattr(f, "is_meat", False) and diet in (DIET_VEGETARIAN, DIET_SPECIAL):
        return False
    return True


class FlyHunter:
    """四相：select → fetch → aim → throw。"""

    def __init__(self, win, rng, fsm):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.rng = rng
        self.fsm = fsm
        self.target = None
        self.weapon = None          # Stone / Spear
        self.phase = "select"
        self.grab_side = "r"
        self.timer = 0
        self.fails = 0
        self.throw_dir = 1
        self.throw_t = 0
        self.done = False
        self._vel = (0.0, 0.0)

    # ── 工具 ──
    def _c0(self):
        return self.body.chunk0

    def _diet(self):
        return getattr(self.fsm.pers, "diet", None)

    def _flies(self):
        diet = self._diet()
        out = []
        for f in (*self.win.batflies, *self.win.squidcadas,
                  *self.win.needleworms):
            if not _edible(f, diet):
                continue
            c0 = self._c0()
            dx, dy = f.x - c0.x, f.y - c0.y
            if math.hypot(dx, dy) > SEEK_R:
                continue
            if -dy > CIEL_ABOVE_MAX:            # y↓：-dy>0 表示在上方
                continue
            out.append(f)
        return out

    def _grab_dist(self, o):
        c0 = self._c0()
        hx, hy = self.body._carry_pos(self.grab_side)
        return min(math.hypot(c0.x - o.x, c0.y - o.y), math.hypot(hx - o.x, hy - o.y))

    def _pick_side(self, o):
        from ..world.spear import Spear
        return self.body.pick_hand("spear" if isinstance(o, Spear) else "stone") or "r"

    def _ground_stones(self):
        return [s for s in self.win.stones
                if s.state == "free" and not getattr(s, "unfetchable", False)
                and s.at_rest_on_ground(self.win._HL)]

    def _ground_spears(self):
        """可取用的矛：插在地上的（原版可拔出）或刚停下的。"""
        out = []
        for s in self.win.spears:
            if s.state != "free" or s.stuck_to is not None:
                continue
            if getattr(s, "pinned", False):      # 钉成杆的矛：拔不动
                continue
            if s.stuck or (abs(s.vx) < 0.4 and abs(s.vy) < 0.4):
                out.append(s)
        return out

    def _predict(self, f, speed, grav=0.9):
        """迭代预判落点：返回 (t, vx, vy) 或 None（grav = 武器飞行时的等效重力）。"""
        c0 = self._c0()
        lx, ly = c0.x, c0.y - 6.0
        t = MIN_FLIGHT
        tx, ty = f.x, f.y
        for _ in range(LEAD_ITERS):
            tx = f.x + f.vx * t
            ty = f.y + f.vy * t
            d = math.hypot(tx - lx, ty - ly)
            t = clampf(d / speed, MIN_FLIGHT, MAX_FLIGHT)
        tx = f.x + f.vx * t
        ty = f.y + f.vy * t
        vx = (tx - lx) / t
        vy = (ty - ly - 0.5 * grav * t * t) / t  # 矛飞行时重力减半
        if abs(vx) > speed * 1.6 or abs(vy) > speed * 1.6:
            return None
        return t, vx, vy

    # ── 主循环 ──
    def update(self, still_want) -> str:
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return "idle"
        return m(still_want)

    def _phase_select(self, want):
        if not want:
            return "idle"
        flies = self._flies()
        if not flies:
            return "revert_wander"
        c0 = self._c0()
        self.target = min(flies, key=lambda f: math.hypot(c0.x - f.x, c0.y - f.y))
        # 已有武器直接用
        if self.body.carried_stone is not None or self.body.carried_spear is not None:
            self.weapon = self.body.carried_spear or self.body.carried_stone
            held = (self.body.hand_of.get("spear")
                    if self.body.carried_spear is not None
                    else self.body.hand_of.get("stone"))
            self.grab_side = held or self._pick_side(self.target)
            self.phase = "aim"
            self.timer = 0
            return "running"
        best, bestd = None, 1e9
        for o in (*self._ground_spears(), *self._ground_stones()):
            d = math.hypot(c0.x - o.x, c0.y - o.y)
            if d < bestd:
                best, bestd = o, d
        if best is None:
            return "revert_wander"
        self.weapon = best
        self.grab_side = self._pick_side(best)
        self.fails = 0
        self.timer = 0
        self.phase = "fetch"
        return "running"

    def _phase_fetch(self, want):
        o = self.weapon
        if o is None or o.state != "free":
            return "revert_wander" if want else "idle"
        self.grab_side = self._pick_side(o)
        self.body.walk_to(o.x)
        if self._grab_dist(o) < self.body.arm_full_reach * REACH_GATE_K:
            self.body.reach_for(o, self.grab_side)
        if self._grab_dist(o) < GRAB_REACH:
            self.body.stop_walk()
            from ..world.spear import Spear
            if isinstance(o, Spear):
                self.body.grab_spear(o, self.grab_side)
            else:
                self.body.grab_stone(o, self.grab_side)
            self.phase = "aim"
            self.timer = 0
            return "running"
        if abs(self._c0().x - o.x) < GRAB_REACH and self.timer > APPROACH_TIMEOUT:
            self.timer = 0
            self.fails += 1
            if self.fails >= MAX_FAILS:
                o.fetch_fails = getattr(o, "fetch_fails", 0) + 1
                if o.fetch_fails >= ABANDON_FAILS:
                    o.unfetchable = True
                return "revert_wander" if want else "idle"
        return "running"

    def _phase_aim(self, want):
        f = self.target
        if f is None or not _edible(f, self._diet()) or not want:
            return "giveup"
        if self.timer > GIVEUP_TICKS:
            return "giveup"
        self.body.stop_walk()
        self.gfx.look_at = (f.x, f.y)
        c0 = self._c0()
        # 原版 Weapon.Thrown：throwDir = IntVector2(sign(x), 0) —— 玩家只能水平投，
        # 所以先要跳到猎物所在高度，再对齐出手（也允许跳着发射矛/石）。
        speed = SPEED_SPEAR if self.body.carried_spear is not None else SPEED_STONE
        lead_x = f.x + f.vx * clampf(abs(f.x - c0.x) / speed, MIN_FLIGHT, 12.0)
        dx = lead_x - c0.x
        dy = f.y - c0.y
        self.throw_dir = 1 if dx >= 0.0 else -1
        if abs(dy) > AIM_DY_TOL:
            if dy < 0.0 and self.body.on_floor():      # 虫在上方：起跳够高度
                if self.timer % AIM_JUMP_CD == 0:
                    self.body.request_jump("stand")
            elif not self.body.on_floor():
                pass                                   # 跳跃途中：等高度对齐
            elif abs(dx) > 30.0:
                self.body.walk_to(f.x)                 # 虫在下方/同层：先站到它跟前的投掷侧
            return "running"
        if abs(dx) < GRAB_REACH:
            self.body.walk_to(c0.x - self.throw_dir * 60.0)
            return "running"
        self._vel = None                               # 走原版水平初速
        self.phase = "throw"
        self.throw_t = 0
        return "running"

    def _phase_throw(self, want):
        if self.throw_t == 0:
            c0 = self._c0()
            weak, toss = weaponphys.player_throw_mode(
                getattr(self.win, "variant", ""), getattr(self.fsm, "_exhausted", False),
                self.body.carried_spear is not None, False)
            if self.body.carried_spear is not None:
                self.body.throw_spear(self.throw_dir, weaponphys.frc(weak=weak),
                                      recoil=RECOIL, toss=toss)
            else:
                self.body.throw_stone(self.throw_dir, weaponphys.frc(weak=weak),
                                      fling=True, recoil=RECOIL)
            self.gfx.blink = 15
            self._c0().vx -= self.throw_dir * 0.4
        side = self.grab_side
        c0 = self._c0()
        self.gfx.hand_aim[side] = (c0.x + self.throw_dir * 30.0, c0.y)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        self.throw_t += 1
        if self.throw_t >= THROW_FRAMES:
            return "thrown"
        return "running"
