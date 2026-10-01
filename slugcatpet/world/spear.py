"""矛 Spear：可放置/拖拽/投掷的长杆（原版 Weapon + Spear）。y↓。

尺寸与物理全部取反编译原值：
  Spear.cs:286-295  bodyChunks[0] rad 5 / mass 0.07；airFriction 0.999；gravity 0.9；
                    bounce 0.4；surfaceFriction 0.4；collisionLayer 2；waterFriction 0.98；
                    buoyancy 0.4
  可视杆长 = 原版 SmallSpear 贴图 53px（锚点在杆中点，同 FSprite anchorY 0.5）
投掷走 world.weaponphys 的 frc 模型；飞行时重力减半；撞墙按原版概率插住。
"""
from __future__ import annotations
import math
import random as _random

from ..core import chunkphys                     # 庇护所墙体扫掠要用 chunkphys.solids()
from ..core.chunkphys import aabb_wall_collide, apply_water
from . import trajectory as traj
from . import weaponphys as wp
from .enums import ItemState

NEEDLE_FADE_MAX = 400    # 断线后「白 → 黑」的时长（原版 spearmasterNeedle_fadecounter_max，约 10 秒）
NEEDLE_BLACK_HOLD = 240   # 全黑之后先保持约 6 秒，再开始整体渐隐
NEEDLE_ALPHA_FADE = 80    # 整体渐隐（alpha 1→0）的时长，约 2 秒；褪尽才真的 GONE
LEN = 53.0               # 杆长（原版 SmallSpear 贴图可视长度）
HALF_W = 1.6             # 杆的半宽（贴图实测 3px）
RAD = wp.SPEAR_RAD       # Spear.cs:287 bodyChunks[0].rad（唯一真值在 weaponphys）
MASS = 0.07              # Spear.cs:287 bodyChunks[0].mass
GRAVITY = 0.9
AIR_FRICTION = 0.999
BOUNCE = 0.4
SURFACE_FRICTION = 0.4
BUOYANCY = 0.4
WATER_FRICTION = 0.98
SPEAR_MOVE_MIN = 1.0     # 单 tick 位移小于此值＝这矛没在动，不判定命中
SPEAR_FLIGHT_TURN = 0.25  # 飞行中矛身朝向追随速度的速率（平飞段之后才生效）
STUCK_SINK = 7.0         # 插进墙地的深度（原版 stuckInWall 取格心）
FLOOR_EMBED_STEEP = 2.0  # 落地时竖向位移/横向位移超过此值 = 近乎垂直扎进地面（原版 ContactPoint == throwDir）
EMBED_AXIS_COS = 0.866   # 成杆判定：矛轴（尾→尖）与表面法线夹角 < 30 度才算「尖头扎进去」（原版 ContactPoint == throwDir）

SPEAR_SHAFT = (94, 78, 60)
SPEAR_TIP = (206, 206, 198)


def _solid_sweep(x0, y0, x1, y1, r):
    """扫过物理 SOLIDS，返回最近 (t, nx, ny)。"""
    dx, dy = x1 - x0, y1 - y0
    best = None
    eps = 1e-9
    for ax0, ay0, ax1, ay1 in chunkphys.solids():
        ax0 -= r; ay0 -= r; ax1 += r; ay1 += r
        tx0, tx1 = -math.inf, math.inf
        ty0, ty1 = -math.inf, math.inf
        if abs(dx) < eps:
            if not (ax0 <= x0 <= ax1): continue
        else:
            a, b = (ax0 - x0) / dx, (ax1 - x0) / dx
            tx0, tx1 = min(a, b), max(a, b)
        if abs(dy) < eps:
            if not (ay0 <= y0 <= ay1): continue
        else:
            a, b = (ay0 - y0) / dy, (ay1 - y0) / dy
            ty0, ty1 = min(a, b), max(a, b)
        t0, t1 = max(tx0, ty0), min(tx1, ty1)
        if t1 < max(0.0, t0) or t0 > 1.0: continue
        t = max(0.0, t0)
        if best is not None and t >= best[0]: continue
        if abs(t - tx0) < abs(t - ty0):
            nx = -1.0 if dx > 0.0 else 1.0; ny = 0.0
        else:
            nx = 0.0; ny = -1.0 if dy > 0.0 else 1.0
        best = (t, nx, ny)
    return best

def _embed_steep(sp, nx: float, ny: float) -> bool:
    """这根矛是不是「尖头正对着这个面扎进去」（原版 ContactPoint == throwDir）。

    用矛自己的杆轴（杆尾 → 杆尖）跟表面法线比：只有轴线近乎垂直于表面（尖头
    朝墙里）才允许钉成杆。横着拍上去、从上往下蹭到顶面的都不算 —— 旧实现是
    「顶面无条件插住 + 没掷出的也插住」，于是矛碰到任何墙面都必定变成杆
    （用户报的「矛到墙壁总是必定成为杆子」）。
    """
    a = math.radians(sp.stuck_angle if sp.stuck else sp.angle_deg)
    tx, ty = math.sin(a), -math.cos(a)          # 杆尾 → 杆尖
    nl = math.hypot(nx, ny)
    if nl <= 1e-9:
        return False
    return abs(tx * nx + ty * ny) / nl >= EMBED_AXIS_COS


def _ang_lerp(a: float, b: float, k: float) -> float:
    """角度插值（走最短弧）。"""
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d * k


class Spear:
    """矛：单点质点 + 朝向；插住后不再模拟（原版 Mode.StuckInWall）。"""
    collision_layer = 2

    __slots__ = ("x", "y", "vx", "vy", "last_x", "last_y", "rad", "mass", "gravity",
                 "_f1", "_seg_new", "_seg_x", "_seg_y",
                 "air_friction", "bounce", "surface_friction", "buoyancy", "water_friction",
                 "water_y", "room_gravity",
                 "state", "angle_deg", "last_angle", "spin", "spinning", "stuck", "stuck_angle",
                 "_id", "_rng", "_contact_floor", "_contact_ceil", "_contact_x", "_impact_cb",
                 "_thrown", "_throw_dir", "_exit_spd", "_throw_x", "_throw_y",
                  "always_stick",
                 "collide_with_objects", "held_by", "embedded", "stuck_to", "stuck_local", "_still",
                 "thrower", "no_self_t", "pinned", "pole", "toss_t",
                 "aim_cursor", "cursor_pin", "needle", "needle_live",
                 "needle_type", "needle_fade", "needle_fade_wait", "needle_alpha",
                 "damage", "needle_thread_cut", "needle_thread_done",
                 "needle_world")

    def __init__(self, x: float, y: float, seed: int = 0, angle_deg: float = 90.0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad, self.mass, self.gravity = RAD, MASS, GRAVITY
        self._f1 = False             # 掷出后的第一帧：last_* 保留出手前的位置
        self._seg_new = False        # 本帧这段位移还没判过命中
        self._seg_x, self._seg_y = float(x), float(y)   # 本帧真正飞到的位置（插墙回摆之前）
        self.air_friction, self.bounce, self.surface_friction = AIR_FRICTION, BOUNCE, SURFACE_FRICTION
        self.buoyancy, self.water_friction = BUOYANCY, WATER_FRICTION
        self.water_y = None
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.angle_deg = self.last_angle = float(angle_deg)
        self.spin = 0.0
        self.spinning = False          # Spear.spinning：翻滚中（控制触地收势）
        self._still = 0                # stillCounter：spinning 期间连续静止帧
        self.stuck = False
        self.stuck_angle = float(angle_deg)
        self.embedded = STUCK_SINK
        self._id = int(seed)
        self._rng = _random.Random(int(seed) * 3571 + 11)
        self._contact_floor = False
        self._contact_ceil = False
        self._contact_x = 0
        self._impact_cb = None
        self._thrown = False
        self.always_stick = False    # Weapon.alwaysStickInWalls（滑铲掷出的矛必定插墙）
        self._throw_dir = 0
        self._exit_spd = 0.0
        self._throw_x = self._throw_y = 0.0
        self.collide_with_objects = True
        self.thrower = None            # 谁扔的（前 no_self_t 帧不插自己）
        self.no_self_t = 0
        self.held_by = None            # 拾荒者手上
        self.stuck_to = None           # 插在生物身上的 (obj, dx, dy)；由 items 层维护
        self.stuck_local = None        # (obj, 节号, 基准角, lx, ly, 相对角)；跟着身体节转
        self.pinned = False            # 钉成杆子（原版 stuckInWall → beam），不能再被拾取
        self.pole = None               # 由 items 层注册的杆实体（钉住时非 None）
        # 轻抛（原版 Player.TossObject，圣徒投矛走这条）刚出手的剩余帧数：原版轻抛是
        # Mode.Free，什么都打不动；本作用户点名要圣徒能敲开爆米花，只对豆荚开这个口子。
        self.toss_t = 0
        # 猎手朝鼠标掷的矛：命中光标就钉在光标上（cursor_pin = 相对光标的偏移），
        # 甩鼠标（光标一 tick 位移够大）会被甩下来，自由落体。
        self.aim_cursor = False
        self.cursor_pin = None
        # 矛大师的骨矛（Spear.spearmasterNeedle / spearmasterNeedle_hasConnection）：
        # needle=这根是尾巴长出来的针；needle_live=还连着尾巴（活性在）。
        # 只有还活着的针扎中活物才回饱食度；落地/插墙/扎中东西就断开。
        self.needle = False
        self.needle_live = False
        self.damage = 1.0                     # spearDamageBonus（原版默认 1f）
        self.needle_type = 0                  # BioSpear1..3（Spear_makeNeedle 的 type）
        self.needle_fade = NEEDLE_FADE_MAX    # ① 白 → 黑的剩余计数（原版 fadecounter）
        self.needle_fade_wait = 0             # ② 全黑之后保持的剩余 tick
        self.needle_alpha = 1.0               # ③ 整体不透明度：黑化走完才从 1 渐隐到 0
        # 线必须**立刻**断（不等褪色）：二次被捡 / 扎中的宿主被删
        self.needle_thread_cut = False
        # 这条尾巴细线已经「拉出 → 渐隐完」：别再给同一根针重拉一条（否则永不消失）
        self.needle_thread_done = False
        # 这根针有没有离过手（掷出去过）。刚长出来直接递到主人手里时是 False：
        # 那不算「二次捡起」，线还在。
        self.needle_world = False

    @property
    def pos(self):
        return (self.x, self.y)

    def collision_chunks(self):
        if (self.stuck or self._thrown
                or self.state in (ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE)):
            self.collide_with_objects = False      # 原版 ChangeMode(Thrown/Stuck) → collisionLayer 0
            return ()
        self.collide_with_objects = True
        return (self,)

    def moving(self) -> bool:
        """这一 tick 是否真的在动（原版 Weapon 只有 Thrown/飞行的段才判命中）。"""
        return math.hypot(self.x - self.last_x, self.y - self.last_y) >= SPEAR_MOVE_MIN

    def tip(self):
        """尖端坐标（角度 0=上，y↓）。"""
        a = math.radians(self.stuck_angle if self.stuck else self.angle_deg)
        return (self.x + math.sin(a) * LEN * 0.5, self.y - math.cos(a) * LEN * 0.5)

    def butt(self):
        a = math.radians(self.stuck_angle if self.stuck else self.angle_deg)
        return (self.x - math.sin(a) * LEN * 0.5, self.y + math.cos(a) * LEN * 0.5)

    def pin_tip(self, hx: float, hy: float, angle_deg=None) -> None:
        """把矛**尖**摆到真实接触点（撞到东西的同一 tick 用）。

        旧实现只把速度清零、位置留在「这一帧飞到的终点」：40px/帧 的位移让
        矛看起来插在目标身后的空气里（用户报的「矛插在空气上」）。
        """
        from .hitgeom import tip_align
        if angle_deg is not None:
            # 命中瞬间矛头就是顺着弹道方向的（原版 setRotation = throwDir）：
            # 把渲染角也锁到 impact angle，矛尖才真的贴住接触点（文档 §6）。
            self.angle_deg = self.last_angle = float(angle_deg) % 360.0
        tip_align(self, hx, hy, LEN, angle_deg)
        self.last_x, self.last_y = self.x, self.y
        self._seg_x, self._seg_y = self.x, self.y

    def needle_disconnect(self, cut: bool = False) -> None:
        """Spear_NeedleDisconnect：活性没了（针从白褪成黑色，不能再吸食）。

        cut=True 额外把尾巴上那条有机线**当场**剪断（二次被捡 / 宿主被删）。
        默认 False：线先跟着针一起褪色，等针真变黑（fade==0）才消失。
        """
        if self.needle_live:
            self.needle_live = False
            self.needle_fade = NEEDLE_FADE_MAX
            self.needle_fade_wait = NEEDLE_BLACK_HOLD
            self.needle_alpha = 1.0
        if cut:
            self.needle_thread_cut = True

    def needle_tick(self) -> None:
        """断线骨针的三段生命周期：白 → 黑 → 黑保持 → 整体渐隐 → 真的消失。

        反编译 Spear.cs:1333-1356 只按 fadecounter/400 把颜色从白 Lerp 到黑，
        没有 alpha；本作按用户口径补上「渐隐到 0 才消失」—— 旧实现是黑到
        fade==0 的那一 tick 直接 GONE（用户实测「视觉上一会儿突然消失」）。
        钉成竖/横杆的针照样跑完整条生命周期（黑化 → 保持 → 渐隐 → GONE）：
        旧实现在这里对 pinned 早退，那根针就永远停在黑针，直到鼠标把它拔下来
        （用户实测「卡住直到被点击才会直接消失」）。针 GONE 之后由 items 侧
        `_sync_spear_poles()` 把对应场景杆一起撤掉。
        """
        if not self.needle or self.needle_live:
            return
        if (self.state in (ItemState.CARRIED, ItemState.MOUSE)
                or self.held_by is not None):
            # 只在**真的被持有**时暂停：手里 / 鼠标拖着 / 被谁拿着。
            # 旧实现连「扎在生物身上」（stuck_to）也一并挡住，于是那根针的整个
            # 生命周期被冻住：白针永远不变黑（用户报的「部分白矛不褪色」），
            # 已经变黑的针要等鼠标把它拔下来（stuck_to 清空）才能继续褪到消失
            # （「部分黑矛本应自动消失，却需鼠标点击」）。
            return
        if self.needle_fade > 0:                  # ① 白 → 黑
            self.needle_fade -= 1
            return
        if self.needle_fade_wait > 0:             # ② 全黑之后停留
            self.needle_fade_wait -= 1
            return
        if self.needle_alpha > 0.0:               # ③ 整体渐隐到 0 才真消失
            self.needle_alpha = max(0.0, self.needle_alpha
                                    - 1.0 / max(1.0, float(NEEDLE_ALPHA_FADE)))
        if self.needle_alpha <= 0.0:
            self.needle_alpha = 0.0
            self.enter_gone()
            self.held_by = None

    def stick(self, WL: float, wall: int) -> None:
        """掷进左右墙（wall=±1）：杆横着插住、杆尖埋进墙里，成为一截同长的横杆。

        地面插矛不走这里（原版 ContactPoint.y 分支标 verticalBeam），见
        rest_on_ground（斜插，可拾取）与 embed_vertical（垂直、成竖杆、不可拾取）。
        """
        self.enter_stuck(pinned=True, stuck_angle=90.0 if wall > 0 else 270.0)
        self.x = (WL - LEN * 0.5 + self.embedded) if wall > 0 else (LEN * 0.5 - self.embedded)
        self._sync_interp()

    def embed_in_bar(self, nx: float, ny: float, x: float, y: float) -> None:
        """刺进「墙壁条」（庇护所框 / 窗台 / 其它实心地形）。

        用户口径：庇护所的框就是一条条墙壁，像杆子被定义成杆子一样 —— 有碰撞、
        可以被扎矛。接触点 (x, y) 是这一 tick 扫掠到的落点，杆尖朝表面里埋进去。
        角度约定见 tip()：0=上 90=右 180=下 270=左。
        """
        if abs(nx) >= abs(ny):
            ang = 90.0 if nx < 0.0 else 270.0      # 侧墙：杆尖指向墙内
        else:
            ang = 180.0 if ny < 0.0 else 0.0       # 顶面朝下扎 / 底面朝上扎
        self.angle_deg = self.last_angle = ang
        self.enter_stuck(pinned=True)
        a = math.radians(ang)
        dx, dy = math.sin(a), -math.cos(a)
        self.x = x - dx * (LEN * 0.5 - self.embedded)
        self.y = y - dy * (LEN * 0.5 - self.embedded)
        self._sync_interp()

    def lifecycle(self) -> str:
        """这只矛现在处于哪个生命周期阶段（文档 §6「统一 SpearLifecycle」）。

        只读归一：不改任何字段，只把 ``state / _thrown / stuck / stuck_to /
        pinned / pole`` 六个散字段收成一个答案，插针的淡出与场景杆的保留
        各自按这个答案判，不再各读一半字段。
        """
        from .enums import SpearLifecycle
        if self.state == ItemState.GONE:
            return SpearLifecycle.GONE
        if self.state in (ItemState.CARRIED, ItemState.MOUSE):
            return SpearLifecycle.CARRIED
        if self.stuck_to is not None:
            return SpearLifecycle.STUCK_TO_CREATURE
        if self.pinned and self.pole is not None:
            return SpearLifecycle.PINNED_POLE
        if self.stuck:
            return SpearLifecycle.STUCK
        if self._thrown:
            return SpearLifecycle.THROWN
        return SpearLifecycle.FREE

    # ---- 第153轮 生命周期：唯一状态写入 -------------------------------------
    # `state / stuck / pinned / _thrown / stuck_to / stuck_local / toss_t`
    # 以前由矛自己、items 层、猫、拾荒者各写一半，才会出现 stuck=True 且
    # _thrown=True、拔出来还留着 stuck_to 这类中间组合。现在这些字段
    # **只**由下面五个进入方法成组写。`pole` / `held_by` 不在这里动：
    # 它们是杆实体 / 持有者的句柄（见 items._sync_spear_poles）。

    def enter_free(self, roll: bool = True, state: str = ItemState.FREE) -> None:
        """唯一「自由身」入口：掷完 / 弹开 / 被拔下 / 被拿着 / 脱钉 / 轻放。

        roll=True 走原版 Weapon.Update 退出 Thrown 的 SetRandomSpin（落地会
        自己收势插地）；roll=False 用于「当场静止」（被拾取、轻放、脱钉）。
        """
        if self.stuck or self.stuck_to is not None or self._thrown:
            self.needle_disconnect()               # 原版退出 Stuck / Thrown → 断连接
        self.state = state
        self.stuck = False
        self.pinned = False
        self.stuck_to = None
        self.stuck_local = None
        self._thrown = False
        self._exit_spd = 0.0
        self.toss_t = 0
        self.cursor_pin = None
        self.embedded = STUCK_SINK
        self.spinning = bool(roll)
        self._still = 0
        self.spin = (wp.spear_random_spin(self._rng, self.room_gravity)
                     if roll else 0.0)

    def enter_thrown(self) -> None:
        """唯一「掷出」入口（weaponphys.begin_thrown 的 Spear 分支）。"""
        self.stuck = False
        self.pinned = False
        self.stuck_to = None
        self.stuck_local = None
        self._thrown = True
        self.toss_t = 0
        self.cursor_pin = None
        self.spinning = False
        self._still = 0
        self.spin = 0.0

    def enter_stuck(self, pinned: bool = False, stuck_angle=None) -> None:
        """唯一「插住」入口：墙 / 地 / 横挂。

        stick / embed_in_bar / rest_on_ground / lodge_in_surface /
        embed_vertical 都走这里；落点与朝向由调用者先摆好。stuck_angle
        传 None ＝ 就地取当前 angle_deg（保持插住那一刻的角度）。
        """
        self.needle_disconnect()
        self.stuck = True
        self.pinned = bool(pinned)
        self.stuck_to = None
        self.stuck_local = None
        self._thrown = False
        self.toss_t = 0
        self.cursor_pin = None
        self.vx = self.vy = 0.0
        self.spin = 0.0
        self.spinning = False
        self._still = 0
        self.stuck_angle = (self.angle_deg if stuck_angle is None
                            else float(stuck_angle))

    def enter_stuck_to(self, host, dx: float, dy: float, local=None) -> None:
        """唯一「扎在生物身上」入口（items 层：蜥蜴 / 拾荒者 / 爆米花）。"""
        self.stuck = True
        self.pinned = False
        self.stuck_to = (host, float(dx), float(dy))
        self.stuck_local = local
        self._thrown = False
        self.toss_t = 0
        self.cursor_pin = None
        self.vx = self.vy = 0.0
        self.spin = 0.0
        self.spinning = False
        self._still = 0

    def enter_gone(self) -> None:
        """唯一「消失」入口。"""
        self.state = ItemState.GONE
        self.stuck = False
        self.pinned = False
        self.stuck_to = None
        self.stuck_local = None
        self._thrown = False
        self.toss_t = 0
        self.cursor_pin = None
        self.vx = self.vy = 0.0

    def _enter_free(self) -> None:
        """Weapon.Update 退出 Thrown：SetRandomSpin + ChangeMode(Free)。"""
        self.enter_free()

    def rest_on_ground(self, HL: float) -> None:
        """Spear.Update(Free+spinning) 的收势：停转、速度清零、杆尖朝下插进地面。

        原版：rotation = DegToVec(Lerp(-50,50,rand)+180) —— 杆尖向地，杆身斜插出地面。
        位置不跳变（只在杆尖越到地面线以下时把整根杆抬回来），所以落地不抖也不穿地。
        """
        self.angle_deg = self.last_angle = 180.0 + self._rng.uniform(-50.0, 50.0)
        self.enter_stuck(pinned=False)
        self._seat_on_floor(HL)
        self._sync_interp()

    def lodge_in_surface(self) -> None:
        """斜擦进墙：就地停住（保持撞上时的角度），不成杆、可以拔出来再投。

        原版只有 ContactPoint == throwDir 的那一掷会把格子变成 beam；斜面掠过
        的矛只是「插在上面」。这里 pinned 保持 False，所以不会有杆实体。
        """
        self.enter_stuck(pinned=False)
        self._sync_interp()

    def _sync_interp(self) -> None:
        """停住的矛不再走 step：把插值基准（last_*）钉到当前位姿。

        绘制按 last→cur 插值；停住的物体若 last 停在上一 tick，就会每帧在
        「上一 tick 的位置 ↔ 最终位置」之间来回画 —— 用户看到的「矛抖抖抖」。
        """
        self.last_x = self.x
        self.last_y = self.y
        self.last_angle = self.angle_deg

    def bounce_off(self, nx, ny, k: float = 0.45) -> None:
        """撞到「无法刺入的东西」：沿法线原速反弹并进入翻滚（原版 Weapon.HitWall
        的无效弹开）。两矛空中相撞也走这条：不插任何东西，各自弹开继续飞。
        """
        spd = math.hypot(self.vx, self.vy)
        d = self.vx * nx + self.vy * ny
        if d < 0.0:                              # 只在「正撞上去」时反射
            self.vx -= 2.0 * d * nx
            self.vy -= 2.0 * d * ny
        self.vx *= k
        self.vy *= k
        if self._impact_cb is not None and spd > 0.0:
            self._impact_cb(self, (nx, ny), spd, 1.0, 0.0, 0.0)
        self._enter_free()

    def _flight_far(self) -> bool:
        """是否已飞出「平飞段」（出手后先抵消重力飞一段，之后自然下落）。"""
        return math.hypot(self.x - self._throw_x, self.y - self._throw_y) >= wp.SPEAR_FLIGHT_FLAT_PX

    def _seat_on_floor(self, HL: float) -> None:
        """杆尖若越到地面线（HL）以下，把整根杆抬回去让杆尖正好触地。

        地面线以下就是任务栏，露出去就是「垂到任务栏下」；杆尖抵线看起来才像插进地里。
        """
        a = math.radians(self.stuck_angle)
        over = (self.y + abs(math.cos(a)) * LEN * 0.5) - HL
        if over > 0.0:
            self.y -= over
            if self.last_y > self.y:
                self.last_y = self.y

    def embed_vertical(self, HL: float) -> None:
        """杆身竖直钉进地面（原版 Spear 撞地：ContactPoint == throwDir 才插住）。

        原版把这种矛所在的格子标成 verticalBeam —— 即「对应长度的竖杆」，
        所以这里把杆摆正、扎进地里，由 items 层注册成一截竖杆；钉住后不再能拾取。
        """
        self.angle_deg = self.last_angle = 180.0     # 杆尖朝下
        self.enter_stuck(pinned=True)
        self.y = HL - LEN * 0.5                      # 杆尖抵住地面线
        self._sync_interp()

    def step(self, WL: float, HL: float) -> None:
        if self.stuck or self.state in (ItemState.MOUSE, ItemState.CARRIED):
            return
        if self.state == ItemState.GONE:
            return
        if self.toss_t > 0:
            self.toss_t -= 1
        if self._f1:
            self._f1 = False             # 原版 firstFrameTraceFromPos：第一帧从出手前扫起
        else:
            self.last_x, self.last_y = self.x, self.y
        self.last_angle = self.angle_deg
        if self.no_self_t > 0:
            self.no_self_t -= 1
        # 掷出：出手后先平飞一段（上抬抵掉重力），过了 SPEAR_FLIGHT_FLAT_PX 回落到
        # 原版 Spear.Update 的 vel.y += 0.45f（半重力自然下落）。没掷出的照常吃满重力。
        # 重力（掷出的矛过了平飞段只吃半重力）走 world/trajectory：AI 预演
        # 调的是同一个函数，不再有第二套弹道。
        self.vy += traj.SPEAR_PROFILE.gravity_delta(
            self.x, self.y, self._throw_x, self._throw_y,
            self._thrown, self.room_gravity)
        self.angle_deg = (self.angle_deg + self.spin) % 360.0
        # 掷出的矛过了平飞段开始自然下落：矛身朝向改为跟随速度方向（矛头在前），
        # 而不是出手后把角度永久锁死 —— 否则下坠的矛看起来还是一条水平线。
        if self._thrown and self._flight_far() and not self.stuck:
            want = wp.vel_angle(self.vx, self.vy)
            if abs(want - self.angle_deg) > 1e-6:
                self.angle_deg = _ang_lerp(self.angle_deg, want, SPEAR_FLIGHT_TURN) % 360.0
        apply_water(self, self.water_y, self.buoyancy, self.water_friction,
                    self.room_gravity, self.air_friction)
        # 摩擦 + 位移只走 trajectory.advance：AI 预演（traj.preview）调的是同一个
        # 函数，改摩擦 / 入水不会只改一半（文档 §1「advance 成为唯一积分」）。
        # apply_water 已经在上面乘过 air_friction，这里传 1.0 免得乘两次。
        self.x, self.y, self.vx, self.vy = traj.advance(
            self.x, self.y, self.vx, self.vy, 1.0)
        self._seg_x, self._seg_y = self.x, self.y   # 插墙会把 x/y 拽回墙内，命中要用飞到的位置
        # 这一帧的位移算不算「掷出去的那一段」（原版 Weapon.Update 只判 Mode.Thrown）：
        # 刚出手/正在飞/这一帧刚插住的都算；躺地上漂移的、被捡起来的不算 → 不伤人。
        self._seg_new = bool(self._thrown) and self.moving()
        step_x, step_y = self.x - self.last_x, self.y - self.last_y   # 本 tick 落地方向
        # 实心体扫掠必须在 aabb_wall_collide 之前算：它会把矛推出墙面，推出去以后
        # 就再也扫不到「撞上了」这件事，会被当成撞屏幕边去走 stick()（把矛瞬移到边上）。
        solid_hit = _solid_sweep(self.last_x, self.last_y, self.x, self.y, self.rad)
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if solid_hit is not None:
            t, nx, ny = solid_hit
            self.x = self.last_x + (self.x - self.last_x) * max(0.0, t - 1e-4)
            self.y = self.last_y + (self.y - self.last_y) * max(0.0, t - 1e-4)
            self._contact_x = int(nx) if nx else 0
            self._contact_floor = ny > 0.0
            self._contact_ceil = ny < 0.0
            # 墙壁条（庇护所框 / 窗台）可以被扎矛，但「钉成杆」要按角度判：
            # 只有**掷出的矛尖头正对着**扎进这个面才算（原版 ContactPoint ==
            # throwDir）。旧实现是「顶面无条件插住」+「没掷出的也插住」——于是
            # 矛碰到任何墙面都必定变成杆（用户报的「矛到墙壁总是必定成为杆子」）。
            if not self._thrown:
                self.lodge_in_surface()      # 掉落 / 蹭上去的：贴着停住，不成杆
                return
            if not wp.stick_roll(self, self._rng):
                self.bounce_off(nx, ny)      # 插不住：原版无效弹开 + 随机翻滚
                return
            if _embed_steep(self, nx, ny):
                self.embed_in_bar(nx, ny, self.x, self.y)
            else:
                self.lodge_in_surface()      # 斜擦进墙：可拔出，不是杆
            return
        if self._thrown:
            if self._contact_floor:
                # 撞到地面平面即停止物理（原地收势插地）；捡起时 unstuck() 恢复正常。
                # 近乎垂直落下（原版 ContactPoint == throwDir）→ 钉住成竖杆，不再可拾取。
                if step_y > abs(step_x) * FLOOR_EMBED_STEEP:
                    self.embed_vertical(HL)
                else:
                    self.rest_on_ground(HL)
                return
            if self._contact_ceil:
                # 顶边也是平面：不弹，直接清掉竖直速度交给重力落回
                self.vy = 0.0
                self._enter_free()
                return
            if self._contact_x == self._throw_dir:  # Weapon.Update: ContactPoint == throwDir
                if wp.stick_roll(self, self._rng):
                    self.stick(WL, self._throw_dir)
                else:
                    self._enter_free()              # Weapon.HitWall：弹开 + 随机翻滚
            elif wp.exit_check(self):
                self._enter_free()
            return
        # Mode.Free（Spear.cs:470-492）
        moved = math.hypot(self.x - self.last_x, self.y - self.last_y)
        if self.spinning:
            # 翻滚中：触地 或 连续 20 帧几乎不动 → 收势插地
            if moved < 4.0 * self.room_gravity:
                self._still += 1
            else:
                self._still = 0
            if self._contact_floor or self._still > 20:
                self.rest_on_ground(HL)
        elif moved > 6.0:
            # 未翻滚且位移够大 → 起转（SetRandomSpin 后 spinning=True，之后转速固定）
            self.spinning = True
            self._still = 0
            self.spin = wp.spear_random_spin(self._rng, self.room_gravity)
