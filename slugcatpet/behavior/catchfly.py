"""徒手抓飞虫 FlyCatcher：追 → 上手 → 饿了吃掉 / 吃饱了抓着玩再放走。

原版蛞蝓猫（Player）在空中对蝙蝠（Fly）与蝉乌贼（Cicada）的处理是「上手抓」
而不是投掷武器——投掷留给够不到的远处猎物（见 huntfly.FlyHunter）。
抓到之后：饿就啃（Player.BiteEdibleObject → AddFood），饱就拎着玩一会儿，
玩够了松手放生（原版抓着 Fly 把玩、松手它会重新飞走）。
"""
from __future__ import annotations
import math

from ..behavior import tuning
from .fetch import (EAT_INTERVAL, EAT_HOLD_POSE, EAT_CHOMP_POSE, BITE_HEAD_NUDGE,
                    DELIVER_REACH, DELIVER_GAP, DELIVER_TIMEOUT)
from ..cats.personality import DIET_VEGETARIAN, DIET_SPECIAL



class FlyCatcher:
    """四相：chase → hold → (eat) / (play → release)。"""

    def __init__(self, win, rng, fsm):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.rng = rng
        self.fsm = fsm
        self.target = None
        self.phase = "chase"
        self.timer = 0
        self.grab_side = "r"
        self.eat_t = 0
        self._bit = False
        self.play_left = 0
        self.poke_t = 0
        self.jump_cd = 0
        self.deliver_to = None      # 要送去的未驯服蜥蜴

    # ── 工具 ──
    def _c0(self):
        return self.body.chunk0

    def _diet(self):
        return getattr(self.fsm.pers, "diet", None)

    def _candidates(self):
        """半径内的活飞虫（蝙蝠 + 蝉乌贼）。"""
        diet = self._diet()
        if diet in (DIET_VEGETARIAN, DIET_SPECIAL):
            return []                       # 素食/圣徒不主动抓虫吃
        c0 = self._c0()
        out = []
        for f in (*self.win.batflies, *self.win.squidcadas):
            if not getattr(f, "catchable", False):
                continue
            if math.hypot(f.x - c0.x, f.y - c0.y) > tuning.CATCH_SEEK_R:
                continue
            out.append(f)
        return out

    def _grab_dist(self, o):
        c0 = self._c0()
        hx, hy = self.body._carry_pos(self.grab_side)
        return min(math.hypot(c0.x - o.x, c0.y - o.y), math.hypot(hx - o.x, hy - o.y))

    def _pick_side(self, o):
        return "r" if o.x >= self._c0().x else "l"

    # ── 主循环 ──
    def update(self, want) -> str:
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return "idle"
        return m(want)

    def _phase_chase(self, want):
        f = self.target
        if f is None:
            cands = self._candidates()
            if not cands:
                return "revert"
            c0 = self._c0()
            self.target = min(cands, key=lambda o: math.hypot(c0.x - o.x, c0.y - o.y))
            f = self.target
            self.timer = 0
        if not getattr(f, "catchable", False):
            return "revert"
        if self.timer > tuning.CATCH_CHASE_TIMEOUT:
            return "revert"
        self.grab_side = self._pick_side(f)
        c0 = self._c0()
        _mx, mouth_y = self.gfx.mouth_world()
        if f.y < mouth_y - tuning.CATCH_UP_MAX:
            return "revert"                 # 飞太高：够不着，算了
        # 领先一点，走在它下方
        lead_x = f.x + getattr(f, "vx", 0.0) * 6.0
        if abs(lead_x - c0.x) > 10.0:
            self.body.walk_to(lead_x)
        else:
            self.body.stop_walk()
        self.gfx.look_at = (f.x, f.y)
        if self._grab_dist(f) < tuning.CATCH_REACH:
            self.body.stop_walk()
            self.body.grab_fruit(f, self.grab_side)     # 上手抓住
            self.eat_t = 0
            self._bit = False
            self.phase = "hold"
            self.timer = 0
            return "running"
        if self.jump_cd > 0:
            self.jump_cd -= 1
        if (f.y < mouth_y - tuning.CATCH_JUMP_GAP
                and self.body.on_floor() and self.jump_cd <= 0):
            self.jump_cd = tuning.CATCH_JUMP_CD
            self.body.request_jump("stand")              # 跳起来够
        return "running"

    def _phase_hold(self, want):
        f = self.body.carried_fruit
        if f is None:
            return "idle"
        # 手里是活蝉乌贼 + 场上还有没被驯服的蜥蜴 → 送去驯服（原版送礼）
        if (self.deliver_to is None and getattr(f, "is_tame_food", False)
                and not getattr(f, "dead", False)):
            lz = self.win.nearest_untamed_lizard(self._c0().x)
            if lz is not None:
                self.deliver_to = lz
                self.phase = "deliver"
                self.timer = 0
                return "running"
        self.body.stop_walk()
        self.gfx.look_at = (f.x, f.y)
        side = self.grab_side
        self.gfx.hand_aim[side] = (f.x, f.y)
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if not want:
            # 吃饱了：拎着玩，不杀
            self.phase = "play"
            self.play_left = tuning.FLY_PLAY_TICKS
            self.poke_t = 0
            self.body.eat_raise = EAT_HOLD_POSE
            return "running"
        self.eat_t += 1
        phase = min(1.0, self.eat_t / EAT_INTERVAL)
        self.body.eat_raise = EAT_HOLD_POSE + (EAT_CHOMP_POSE - EAT_HOLD_POSE) * math.sin(phase * math.pi)
        if self.eat_t >= EAT_INTERVAL // 2 and not self._bit:
            self._bit = True
            self._bite_head_nudge(f)
            if self.body.bite_carried():
                f.state = "eaten"
                self.body.temper_shift(tuning.TEMPER_FEED)
                self.body.food_eat(getattr(f, "food_value", 1))
                self.body.energy_change(tuning.EN_EAT_RESTORE)
                self.body.release_fruit()
                return "eaten"
        if self.eat_t >= EAT_INTERVAL:
            self.eat_t = 0
            self._bit = False
        return "running"

    def _phase_deliver(self, want):
        """把蝉乌贼送到蜥蜴嘴边：够近就交出（同 FruitFetcher._phase_deliver）。"""
        f = self.body.carried_fruit
        lz = self.deliver_to
        if f is None:
            return "idle"
        if (lz is None or getattr(lz, "tamed", False)
                or getattr(lz, "state", None) != "free"
                or self.timer > DELIVER_TIMEOUT):
            self.deliver_to = None
            self.phase = "hold"
            self.timer = 0
            return "running"
        hx, hy = lz.x, lz.y - getattr(lz, "body_rad", 8.0) * 1.2     # 蜥蜴头侧
        c0 = self._c0()
        d = math.hypot(hx - c0.x, hy - (c0.y - 8.0))
        self.gfx.look_at = (hx, hy)
        self.gfx.hand_aim[self.grab_side] = (f.x, f.y)
        if d <= DELIVER_REACH:
            self.deliver_to = None
            if self.win.deliver_gift(self.win, lz):
                return "delivered"
            self.phase = "hold"
            self.timer = 0
            return "running"
        if d > DELIVER_GAP:
            self.body.walk_to(hx)
        else:
            self.body.stop_walk()
        return "running"

    def _phase_play(self, want):
        f = self.body.carried_fruit
        if f is None:
            return "idle"
        if want:
            self.phase = "hold"          # 又饿了：直接吃掉
            self.timer = 0
            self.eat_t = 0
            self._bit = False
            return "running"
        self.play_left -= 1
        self.poke_t += 1
        self.body.stop_walk()
        self.gfx.look_at = (f.x, f.y)
        side = self.grab_side
        half = max(1, tuning.FLY_PLAY_POKE // 2)
        if self.poke_t % tuning.FLY_PLAY_POKE < half:
            self.gfx.hand_aim[side] = (f.x, f.y - 10.0)    # 举起来晃一晃
            self.body.eat_raise = 0.7
        else:
            self.gfx.hand_aim[side] = (f.x, f.y + 6.0)
            self.body.eat_raise = 0.2
        self.gfx.hand_aim["l" if side == "r" else "r"] = None
        if self.poke_t % tuning.FLY_PLAY_POKE == 0 and self.body.on_floor():
            self.body.request_jump("stand")               # 玩高兴了蹦一下
        if self.play_left <= 0:
            self.release_alive(f)
            return "released"
        return "running"

    def _bite_head_nudge(self, f):
        g = self.gfx
        dx, dy = f.x - g.head.x, f.y - g.head.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            g.head.vx += dx / d * BITE_HEAD_NUDGE
            g.head.vy += dy / d * BITE_HEAD_NUDGE

    def release_alive(self, f) -> None:
        """松手放生：飞虫带一点上抛/侧抛离开。"""
        b = self.body
        b.release_fruit()
        b.eat_raise = 0.0
        f.stalk = None
        f.state = "free"
        f.held_by_hand = None
        f.vx = (1.0 if f.x >= b.chunk0.x else -1.0) * tuning.SPIT_AWAY_VX
        f.vy = tuning.SPIT_UP_VY
        if hasattr(f, "flaps"):
            f.flaps = max(int(getattr(f, "flaps", 0)), 20)
            f.rest = 0
