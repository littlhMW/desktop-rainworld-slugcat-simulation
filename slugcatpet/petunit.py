"""单只宠物实例。"""
from __future__ import annotations
import math
import random

from .behavior import tuning
from .cats import PUP_VARIANT, get as get_cat_def
from .cats.personality import individualize
from .cats.saint.tongue import Tongue
from .control.vmath import dirvec
from .core.creature import SlugcatBody
from .core import chunkphys
from .rendering.graphics import SlugcatGraphics
from .rendering.layout import Layout
from .core.tail import Tail
from .core.units import clampf, inv_lerp, lerp, K_VEL
from .world.lamp import WARM_INNER, WARM_RADIUS

TAIL_SNAP = 40.0
TONGUE_POINTS = 20
TONGUE_ROOT_W = 1.8
TONGUE_TIP_W = 0.3

ZEROG_ROOM_GRAVITY = 0.5     # 判为零重力的阈值

# 幼崽 / 怪猫的个体性格振幅：比常规种族大得多（同种族的幼崽也不一个模子）
WIDE_SIGMA = {
    "activity": 0.42, "sociability": 0.45, "temper": 0.42, "bravery": 0.45,
    "kindness": 0.45, "patience": 0.45, "risk_tolerance": 0.45,
    "crawl_like": 0.35, "point_like": 0.40, "hurry": 0.40, "wake_like": 0.40,
    "swim_zeal": 0.40, "tongue_curiosity": 0.40,
}
# 怪猫性格重揗：这些状态下才能换脑子（正在抓东西/在杆上就等下一次）
PERS_CHURN_SAFE = ("IdleStand", "Idle", "Wander", "LookAround", "LieDown", "Sleep")
PERS_CHURN_MIN = 1200        # 最短 30s 就重揗一次性格数据
PERS_CHURN_SPAN = 2400       # 最长再多 60s


def _pers_seed(pet_id: str, index: int, variant: str) -> int:
    """个体性格种子：由 (族, id, index) 稳定散列（不用内置 hash，它带随盐）。"""
    h = 0x811C9DC5
    for ch in "%s:%s:%d" % (variant, pet_id, index):
        h = ((h ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
    return h
# 零重力甩尾
ZEROG_TAIL_RATE = 0.08
ZEROG_TAIL_AMP0 = 0.4
ZEROG_TAIL_AMP1 = 0.16


def _taper(n, root_w, tip_w):
    return [root_w + (tip_w - root_w) * (i / (n - 1)) for i in range(n)]


class PetUnit:
    """一只猫，独立身体/图形/行为。"""

    def __init__(self, window, index: int, pet_id: str, variant: str, init_state: dict,
                 spawn_x: float | None = None, spawn_y: float | None = None):
        self.window = window
        self.index = index
        self.id = pet_id
        self.variant = variant
        self.is_pup = (variant == PUP_VARIANT)   # 幼崽：不是常规蛞蛓猫
        self.cat = get_cat_def(variant)     # 种族定义
        # 个体性格：在原型的连续轴上做小幅偏移（原版 IndividualVariation）。
        # 种子只取自 (族, id, index) → 同一只猫每次启动都一样，可复现。
        self.personality = individualize(
            self.cat.personality, _pers_seed(pet_id, index, variant),
            sigma=WIDE_SIGMA if variant == PUP_VARIANT else None)
        self._reincarnate_pending = False
        self._cramp_delay = -1                              # <0 才可再抽
        self._cold_rng = random.Random(0xC01D + index)      # 确定性
        self.controlled = False
        self.behavior = None
        # 怪猫：性格数据一段时间就重掷一次（逻辑混沌）
        self._pers_churn_rng = random.Random(0x1A7C + index * 7919)
        self._pers_churn_t = 0
        self._build(init_state, spawn_x, spawn_y)
        self._attach_behavior()

    def __getattr__(self, name):
        """无此属性则转发到 window。"""
        if name == "window":
            raise AttributeError(name)
        return getattr(self.window, name)

    # ── 构建 ──
    def stand_h(self) -> float:
        """当前站立面高度：窗口地板 or 别人窗口顶边（单向平台）。

        规划层原本一律按窗口地板算起跳/落脚高度，于是站在窗口顶边上的猫
        「旁边那块果子」都算不出够得到（用户口径：被遮挡的窗口段不算地面，
        露出来的顶边就是一块平地）。落地后 chunk1.support_y 就是那块面的 y。

        没有 support_y 时回窗口地板线 body.H（**不是** body._floor_h：那个是
        当前姿势的地板线，匍匐/下滑时会比 H 低几像素，规划层跟着抖）。
        """
        s = self.body.chunk1.support_y
        return self.body.H if s is None else s

    def _build(self, init_state: dict, spawn_x: float | None = None,
               spawn_y: float | None = None):
        w = self.window
        self.layout_data = Layout.for_cat(self.cat)   # 部件摆位
        cx = spawn_x if spawn_x is not None else w._WL / 2.0
        floor_y = w._HL
        self.body = SlugcatBody((cx, floor_y), w._WL, floor_y,
                                energy=init_state.get("energy", 1.0),
                                temper=init_state.get("temper", 0.0),
                                food=init_state.get("food"),
                                karma=init_state.get("karma"),
                                stats=self.cat.stats)
        # 食性（原版 SlugCatClass → NourishmentOfObjectEaten / CanEatMeat）
        self.body.diet = self.personality.diet
        self.body.cold = float(init_state.get("cold", 0.0))
        self.body.visual_floor_y = floor_y
        if spawn_y is not None:                    # 按存档 / 生物生成的位置落地
            self.body.teleport(cx, float(spawn_y))
        # 趴姿悬空几何补偿
        from .core import chunkphys as _cp
        _hips_half_w = w.atlas.source_size("base", "HipsA")[0] / 2.0
        _crawl_draw_raise = 4.0  # Crawl 上抬均值
        self.body.crawl_sink = _cp.RAD1 - _hips_half_w + _crawl_draw_raise
        margin = self.layout_data.canvas_w / 2.0
        self.body.walk_min = margin
        self.body.walk_max = w._WL - margin
        # 原版 npcStats.Wideness / Size：个体固定，驱动幼崽的体/臀/头宽度与尾粗
        self.body.wideness = ((_pers_seed(self.id, self.index, self.variant) % 997)
                              / 996.0)
        self.body.size = ((_pers_seed(self.id, self.index, self.variant) // 997 % 997)
                          / 996.0)
        self.gfx = SlugcatGraphics(self.body, self.layout_data, w.atlas, cat=self.cat)
        # 让站姿先收敛
        for _ in range(40):
            self.body.step()
            self.gfx.update()
        # 尾巴/舌头（caps.tongue 关则不建）
        ax, ay = self.gfx.tail_root_world()
        self.tail = Tail(ax, ay, rad=self.gfx.tail_rad, conn=self.gfx.tail_conn)
        self.tail.floor_y = floor_y
        self._prev_root = (ax, ay)
        if self.cat.caps.tongue:
            mx, my = self.gfx.mouth_world()
            self.tongue = Tongue(mx, my, TONGUE_POINTS,
                                 _taper(TONGUE_POINTS, TONGUE_ROOT_W, TONGUE_TIP_W))
            self.tongue.floor_y = floor_y
            self.tongue.body = self.body        # 供零重力吐舌自推进
        else:
            self.tongue = None
        self.gfx.tail_segs = self.tail.segs
        self.gfx.tongue = self.tongue
        # 鳃（caps.gills 关则不建）
        if self.cat.caps.gills:
            from .cats.rivulet.gills import Gills
            gh = w.atlas.source_size("base", "LizardScaleA3")[1]
            self.gills = Gills(self.body.chunk0.x, self.body.chunk0.y,
                               self.body.chunk1.x, self.body.chunk1.y, gh)
        else:
            self.gills = None
        self.gfx.gills = self.gills
        self.body.impact_cb = w._shake_impact   # 地形硬撞→窗口抖动
        self._zerog_tail_phase = 0.0

    def _revive_burst(self):
        """转世落点：顶部炸开一圈白点 + 一圈冲击环（与圣徒超度同色系）。"""
        w = self.window
        c = self.body.chunk0
        n = 18
        for i in range(n):
            a = math.tau * i / n
            sp = 2.4 + (i % 3) * 0.5
            w.add_spark(c.x, c.y - 8.0, math.cos(a) * sp, math.sin(a) * sp - 1.0,
                        white=True, life=45)
        w.add_shockwave(c.x, c.y - 8.0, 34.0)

    def _attach_behavior(self):
        try:
            from .behavior.fsm import BehaviorFSM
        except Exception:
            self.behavior = None
            return
        self.behavior = BehaviorFSM(self)

    # ── 怪猫：性格数据定时重揗 ───────────────
    def _churn_tick(self):
        """怪猫的「逻辑混沌」：性格数据隔一段时间整份重揗。

        只在安静状态换脑子（抓着东西 / 在杆上 / 正在追捕时不动），换完仍然是
        同一只猫：身体、位置、体征、手里拿的东西都不变，只重建行为层。
        """
        if not self.cat.tuning.get("pers_churn"):
            return
        if self._pers_churn_t > 0:
            self._pers_churn_t -= 1
            return
        beh = self.behavior
        if (beh is None or beh.state not in PERS_CHURN_SAFE
                or getattr(beh.grab, "active", False)):
            self._pers_churn_t = 40          # 忙着呢，稍后再试
            return
        self._pers_churn_t = self._pers_churn_rng.randint(PERS_CHURN_MIN,
                                                          PERS_CHURN_MIN + PERS_CHURN_SPAN)
        self.personality = individualize(self.cat.personality,
                                         self._pers_churn_rng.randrange(1 << 30),
                                         sigma=WIDE_SIGMA)
        self.body.diet = self.personality.diet
        self._attach_behavior()

    def respawn(self, preserve=False):
        """重置本猫（preserve=True 保留体征）。"""
        if self.controlled:              # 先退控制，防丢 provider
            from .control.session import exit_control
            exit_control(self)
        w = self.window
        if preserve:
            b = self.body
            init_state = {"energy": b.energy, "temper": b.temper,
                          "food": b.food, "karma": b.karma}
        else:
            init_state = {"energy": 1.0, "temper": 0.0,
                          "food": tuning.FOOD_INIT, "karma": tuning.KARMA_INIT}
        self._build(init_state)
        self._attach_behavior()
        w._prev_dirty = None             # 强制整窗重绘
        w.update()

    # ── 每 tick 推进 ──
    def step(self, cursor, cycle_prog):
        if self.controlled and self.body.dead:
            # 死须先退控制再转世
            from .control.session import exit_control
            exit_control(self)
        if self._reincarnate_pending:
            self._reincarnate_pending = False
            self.respawn(preserve=True)   # 体征保留，cold 归 0
            self._revive_burst()          # 落点：18 点白圈 + 冲击环
            return
        w = self.window
        b, g = self.body, self.gfx
        if self.controlled:
            # FSM 冻结期同步晕态
            g.stunned = b.stun > 0
            g.look_at = None
        elif self.behavior is not None:
            self.behavior.update(cursor)
        elif w.follow_cursor:
            g.look_at = cursor

        if self.tongue is not None:
            mox, moy = g.mouth_world()
            # 游泳态禁舌，落水自救例外
            escaping = (self.behavior is not None and self.behavior.state == "TongueClimb")
            if b.swimming and not escaping:
                self.tongue.retract()
                self.tongue.update(mox, moy, b.chunk0)
                b.suspended = False
            else:
                self.tongue.update(mox, moy, b.chunk0)
                # 尸体不被舌头吊住
                b.suspended = self.tongue.attached and not b.dead and not b.swimming
        else:
            b.suspended = False

        # water_surface 由 window 每 tick 注入
        rg = w.room_gravity
        b.room_gravity = rg
        b.zerog = rg < ZEROG_ROOM_GRAVITY
        if self.tongue is not None:
            self.tongue.room_gravity = rg

        b.step()
        self._cold_update(cycle_prog)
        g.update()
        if self.gills is not None:
            self.gills.update(b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y,
                              g.look_dir[0], g.look_dir[1],
                              submerged=b.head_sub > 0.5,
                              flat_anchor=g.gills_flat)
        g.update_tongue_rope()
        self._tick_tail()
        self._churn_tick()

    def _cold_update(self, cycle_prog):
        """本猫每 tick 寒冷结算。"""
        w = self.window
        b = self.body

        if b.dead:
            b.cold_gain = 0.0
            return

        blizzard_active = w.blizzard_on and cycle_prog > 0.0
        exposure = tuning.COLD_EXPOSURE

        cold_gain = 0.0
        lamp = w.lamp
        in_warm_zone = False
        d_hip = 0.0
        lamp_range = WARM_RADIUS
        warm_inner = WARM_INNER
        if lamp is not None:
            d_hip = lamp.dist_to(b.chunk1.x, b.chunk1.y)
            in_warm_zone = lamp.in_warm_zone(b.chunk1.x, b.chunk1.y)

        if blizzard_active and not in_warm_zone:
            # (1) 冷度累积
            cg = lerp(0.0, 0.00005, inv_lerp(0.1, 0.95, cycle_prog))
            cg += lerp(0.0, 0.0016, cycle_prog)
            g_div = lerp(9100.0, 5350.0, cycle_prog)
            cg += exposure / g_div
            cg += exposure / 8200.0
            cg = lerp(0.0, cg, inv_lerp(-0.5, 1.0, cycle_prog))
            cg *= inv_lerp(50.0, -10.0, b.total_mass)
            if b.cold > 0.8:
                cg *= 0.5
            cg *= self.personality.cold_gain_fac        # 低=更耐寒
            cg = clampf(cg, -1.0, tuning.COLD_GAIN_CLAMP_HI)             # 勿改
            cold_gain = cg
            b.cold += cg
            # (2) 轻量抽搐
            conscious = b.stun < 10 and not b.dead
            if b.cold >= 0.8 and conscious:
                if cg > tuning.COLD_CRAMP_GAIN_GATE:                     # 勿改
                    if self._cramp_delay < 0:
                        st = int(lerp(5.0, 60.0, b.cold ** 8))   # 满冷→st 60
                        self._cramp_delay = int(self._cold_rng.uniform(
                            300 - b.cold * 240, 500 - b.cold * 200))
                        b.stun = max(b.stun, st)
                else:
                    self._cramp_delay = self._cold_rng.randint(200, 499)
            self._cramp_delay -= 1
            # (3) 冻死
            if b.cold >= 1.0 and b.stun > tuning.COLD_DEATH_STUN and not b.dead:
                if self.behavior is not None and hasattr(self.behavior, "kill_cold"):
                    self.behavior.kill_cold()
        else:
            # 回暖
            if in_warm_zone and b.cold > 0.001:
                f = inv_lerp(lamp_range, warm_inner, d_hip)
                b.cold = max(b.cold - tuning.COLD_LAMP_WARMTH * f, 0.0)
            if b.cold > 1.0:
                b.cold = 1.0
            b.cold = lerp(b.cold, 0.0, tuning.COLD_NATURAL_DECAY)
        b.cold_gain = cold_gain
        b.clamp_cold()

    def _tick_tail(self):
        """尾巴跟随，顺序固定。"""
        b, g = self.body, self.gfx
        rx, ry = g.draw1[0], g.draw1[1]   # 接到臀部渲染位
        if math.hypot(rx - self._prev_root[0], ry - self._prev_root[1]) > TAIL_SNAP:
            self.tail.snap_to(rx, ry)
        # 松弛度：1=下垂摆动，0=贴流线
        if b.chunk0.pinned or b.chunk1.pinned or b.suspended or b.hover:
            looseness = 1.0
        elif b.bodyMode == "Stand":
            vx_norm = abs(b.chunk1.vx) / K_VEL
            looseness = 1.0 - clampf((vx_norm - 1.0) * 0.5, 0.0, 1.0)
        elif b.bodyMode == "Crawl":
            looseness = 1.0
        elif b.bodyMode == "ClimbingOnBeam":
            looseness = 1.0   # 漏此分支尾巴发僵
        elif b.bodyMode == "ZeroG":
            looseness = 1.0   # 漏此分支尾巴发僵
        else:
            looseness = 0.0   # 空中无动画
        # 尾扇出参照点切换
        ref_x, ref_y = b.chunk0.x, b.chunk0.y
        if (b.bodyMode == "Stand"
                and abs(b.chunk0.vx) / K_VEL > 2.0 and abs(b.chunk1.vx) / K_VEL > 2.0):
            ref_x = b.chunk1.x + b.facing * 16.0 * clampf(abs(b.chunk1.vx) / K_VEL - 0.2, 0.0, 1.0)
            ref_y = b.chunk1.y + 4.0
        self.tail.step(rx, ry, b.chunk1.x, b.chunk1.y, ref_x, ref_y, looseness,
                       gravity_norm=self.window.room_gravity)   # 零重力不朝世界下耷拉
        if b.bodyMode == "ZeroG":
            self._apply_zerog_tail_sway(b)
        g._apply_sleep_tail_curl()   # 须在 tail.step 之后
        self._prev_root = (rx, ry)
        if b.animation in ("Roll", "Flip"):
            # 滚/翻尾巴拖尾力
            vx, vy = dirvec(b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y)
            f = 6.0
            for seg in self.tail.segs:
                seg.vx += vx * f
                seg.vy += vy * f
                f /= 1.7

    def _apply_zerog_tail_sway(self, b):
        """零重力甩尾。"""
        self._zerog_tail_phase += ZEROG_TAIL_RATE
        ax, ay = b.chunk0.x - b.chunk1.x, b.chunk0.y - b.chunk1.y   # 体轴
        d = math.hypot(ax, ay) or 1.0
        px, py = -ay / d, ax / d                                    # 垂体轴单位向量
        s = math.sin(self._zerog_tail_phase)
        segs = self.tail.segs
        segs[0].vx += px * ZEROG_TAIL_AMP0 * s
        segs[0].vy += py * ZEROG_TAIL_AMP0 * s
        if len(segs) > 1:
            segs[1].vx += px * ZEROG_TAIL_AMP1 * s
            segs[1].vy += py * ZEROG_TAIL_AMP1 * s

    # ── 舌头 ──
    def fire_tongue(self, tx, ty):
        """朝 (tx,ty) 甩/收舌。"""
        if self.tongue is None:
            return
        if self.tongue.is_idle():
            hx, hy, hit = self._ray_hit_edge(self.body.chunk0.x, self.body.chunk0.y, tx, ty)
            mox, moy = self.gfx.mouth_world()
            self.tongue.shoot(mox, moy, hx, hy, hit)
        else:
            self.tongue.retract()

    def fire_tongue_at(self, px, py) -> bool:
        """直接朝世界点钉舌，返回是否射出。"""
        if self.tongue is None:
            return False
        mox, moy = self.gfx.mouth_world()
        return self.tongue.shoot(mox, moy, px, py, hit=True)

    def fire_tongue_at_obj(self, fruit) -> bool:
        """射舌粘住目标（果子、生物都行），返回是否射出。"""
        if self.tongue is None:
            return False
        mox, moy = self.gfx.mouth_world()
        ok = self.tongue.shoot(mox, moy, fruit.x, fruit.y, hit=True, obj=fruit)
        if ok:
            self._notify_licked(fruit)
        return ok

    def _notify_licked(self, obj) -> None:
        """告诉目标「被舌头黏住了」（原版 PhysicalObject.LickedByPlayer）。

        面条蝇靠它决定生气/送命（见 NeedleWorm.on_licked）；别的生物没有这个
        接口就什么都不发生。
        """
        hook = getattr(obj, "on_licked", None)
        if hook is None:
            return
        cat = None
        for c in self.window._needleworm_cats():
            if c.get("pet") is self:
                cat = c
                break
        hook(cat)

    def _ray_hit_edge(self, mx, my, cx, cy):
        """舌头统一撞窗口边界 + 物理层 SOLIDS（含庇护所墙/门）。"""
        w = self.window
        WL, H = w._WL, w._HL
        dx, dy = cx - mx, cy - my
        d0 = math.hypot(dx, dy)
        ux, uy = (0.0, -1.0) if d0 < 1e-6 else (dx / d0, dy / d0)
        max_d = self.tongue.total
        best = None

        # 窗口上/左/右边缘：沿射线取最近正交点；底边仍由 Tongue.update 的 floor_y 处理。
        eps = 1e-6
        for edge_t in (
            (-(my) / uy if uy < -eps else None),
            (-(mx) / ux if ux < -eps else None),
            ((WL - mx) / ux if ux > eps else None),
        ):
            if edge_t is None or edge_t <= 0.0 or edge_t > max_d:
                continue
            px, py = mx + ux * edge_t, my + uy * edge_t
            if 0.0 <= px <= WL and 0.0 <= py <= H:
                if best is None or edge_t < best:
                    best = edge_t

        # 与 BodyChunk / Spear 完全同源的 SOLIDS：庇护所四墙、关闭的门等。
        # 使用射线-轴对齐矩形的 slab 求交，防止高速舌尖一帧跨过薄墙。
        for x0, y0, x1, y1 in chunkphys.solids():
            tx0, tx1 = -math.inf, math.inf
            ty0, ty1 = -math.inf, math.inf
            if abs(ux) < eps:
                if not (x0 <= mx <= x1):
                    continue
            else:
                a, b = (x0 - mx) / ux, (x1 - mx) / ux
                tx0, tx1 = min(a, b), max(a, b)
            if abs(uy) < eps:
                if not (y0 <= my <= y1):
                    continue
            else:
                a, b = (y0 - my) / uy, (y1 - my) / uy
                ty0, ty1 = min(a, b), max(a, b)
            t0, t1 = max(tx0, ty0), min(tx1, ty1)
            if t1 >= max(0.0, t0) and t1 > 0.0 and t0 <= max_d:
                hit_t = max(0.0, t0)
                if best is None or hit_t < best:
                    best = hit_t

        if best is not None and best <= max_d:
            return mx + ux * best, my + uy * best, True

        ex = clampf(mx + ux * max_d, 0.0, WL)
        ey = clampf(my + uy * max_d, 0.0, H)
        return ex, ey, False
