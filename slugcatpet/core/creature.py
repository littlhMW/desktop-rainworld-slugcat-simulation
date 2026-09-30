"""2 BodyChunk 物理体 + 连接 + 运动系统 + 程序化脚。"""
from __future__ import annotations
import math
import random   # 溺水吐泡概率/散射用

from ..behavior import tuning
from ..cats.stats import DEFAULT_STATS
from ..core import chunkphys as cp
from ..core.chunkphys import BodyChunk, solve_conn
from ..core.units import K_VEL, K_IMP, lerp, inv_lerp, clampf
from ..world import weaponphys
from ..world.enums import ItemState

RUN_UPPER = 4.2 * K_VEL
RUN_LOWER = 4.0 * K_VEL
CRAWL_SPEED = 2.5 * K_VEL
CRAWL_SLOW = 1.0 * K_VEL
H_ACCEL = (2.4 * 0.5) * K_IMP
SKID_DAMP = 0.354      # 接地滑停回收率
CRAWL_BACK_DAMP = 0.45  # 匍匐时反向残余动量的额外回收率（别边爬边倒退）

STAND_HEAD = -(1.5 * K_IMP)
STAND_FEET = +(4.5 * K_IMP)
DEF_STAND_HEAD = -(4.0 * K_IMP)
DEF_STAND_FEET = +(4.0 * K_IMP)

FEET_EASE = 0.5

# 唤醒/抗议跳基准
JUMP_STAND_HEAD = -(4.0 * K_IMP)
JUMP_STAND_FEET = -(3.0 * K_IMP)
PROTEST_HEAD = -(2.0 * K_IMP)
PROTEST_FEET = -(1.0 * K_IMP)
PROTEST_BOOST = 4
JUMPBOOST_DECAY = 1.5 * K_VEL
JUMPBOOST_GAIN = 0.3 * K_IMP

CONN_STAND = cp.DIST_STAND
CONN_CRAWL = cp.DIST_CRAWL
HIP_SINK_EASE = 0.06

# 轻抛（Player.TossObject）出手后还能敲开爆米花的帧数：原版轻抛是 Mode.Free，撞到
# SeedCob 只会被推开（SeedCob.HitByWeapon 只由 Mode.Thrown 的 Weapon 触发，而且
# SeedCob.cs:398 还专门把圣徒排除掉）。用户点名要求「圣徒愿意击打爆米花触发」，
# 所以本作只对豆荚开这个口子：轻抛的飞行段算命中。
TOSS_COB_T = 40

WALK_STOP_EPS = 2.0

# AI 直走撞到统一地形后的自动越障：Planner 之外的行为也能翻过低/中等障碍。
TERRAIN_JUMP_AFTER = 8
TERRAIN_JUMP_COOLDOWN = 32

# 窗口边缘＝墙/天花：实体阻挡 + 扶墙下滑 + 蹬墙跳（**墙不可攀爬**，
# 对照 Controls：蛞蝓猫按住前进键只能沿墙下滑，跳起来才是蹬墙跳）
WALL_JUMP_VX = 6.0 * K_VEL          # Player.WallJump：胸 6、胯 5
WALL_JUMP_VX_FEET = 5.0 * K_VEL
WALL_JUMP_VY = 8.0 * K_VEL          # Player.WallJump：胸 8、胯 7
WALL_JUMP_VY_FEET = 7.0 * K_VEL
WALL_JUMP_LOCK = 14                 # 蹬墙后硬直，期内不再吸附
WALL_LEDGE_SLIDE = 0.5 * K_VEL      # 扶墙下滑速度（原版 WallClimb 的缓降）
CEIL_HANG_PAD = 22.0                # 吊顶时胸心离上边缘：伸手够顶、整只猫不出画面
POLE_OFF_VX = 2.0                   # Player.Jump 离杆平跳：胸 chunk vx = 2·朝向
POLE_OFF_VY = 2.0                   # Player.Jump 离杆平跳：胸 chunk vy = +2（y↓ 向下）
CEIL_SHIMMY_SPEED = 1.6 * K_VEL     # 吊顶横向挪动速度

# 零重力蹬窗边推力/速度上限
ZEROG_KICK = 5.4 * K_VEL
ZEROG_HIP_KICK = 5.0 * K_VEL
ZEROG_HEAD_MAX = 5.4 * K_VEL
ZEROG_HIP_MAX = 5.0 * K_VEL
ZEROG_CANJUMP = 12
# 零重力划水：head 沿意图推、hip 反拖
ZEROG_SWIM_PUSH = 0.15 * K_VEL
ZEROG_SWIM_WALL = 0.2 * K_VEL
ZEROG_SWIM_HIP = 0.1 * K_VEL
ZEROG_SWIM_MAX = 2.5 * K_VEL
ZEROG_KICK_LERP = 0.5
ZEROG_KICK_BODYAXIS = 0.25

# 零重力抓杆漂浮
ZEROG_GRAB_DIST = 20.0
ZEROG_POLE_PULL = 0.1
ZEROG_POLE_CLIMB = 1.05 * K_VEL
ZEROG_POLE_HIP = 0.7
ZEROG_POLE_LEAN = 5.0

CARRY_OFF_X = 20.0
CARRY_OFF_Y = 12.0
# 出膛点：Player.ThrowObject → thrownPos = firstChunk.pos + throwDir*10 + (0,4)（游戏 y↑）
THROW_ORIGIN_DX = 10.0
THROW_ORIGIN_DY = 4.0
EAT_BITES_MIN = 1

# 浅水浮沉常量
WATER_FRICTION = 0.96

class SlugcatBody:
    collision_layer = 1              # 与果/黏菌同层互推

    def __init__(self, hip_xy, world_w: float, world_h: float,
                 energy=1.0, temper=0.0, food=None, karma=None, stats=DEFAULT_STATS):
        self.stats = stats               # 种族数值
        hx, hy = hip_xy
        self.W = float(world_w)
        self.H = float(world_h)
        # 躯体尺寸：Player.setPupStatus（Player.cs:4114-4131），幼崾 12 / 成年 17。
        # 轻量种族（幼崾）不只是数值小，骨架真的短一截。
        self._conn_fac = float(getattr(stats, "conn_fac", 1.0) or 1.0)
        self._conn_stand = CONN_STAND * self._conn_fac
        self._conn_crawl = CONN_CRAWL * self._conn_fac
        chunk_mass = (cp.MASS * stats.weight_fac
                      * float(getattr(stats, "mass_fac", 1.0) or 1.0))
        self.chunk0 = BodyChunk(0, hx, hy - self._conn_stand, cp.RAD0, chunk_mass)
        self.chunk1 = BodyChunk(1, hx, hy, cp.RAD1, chunk_mass)
        self.conn_rest = float(self._conn_stand)
        self.conn_type = "Normal"

        self.standing = True            # True=直立 / False=趴
        self.move_dir = 0
        self.walk_target_x = None
        self.walk_speed_target = None
        self._terrain_block_ticks = 0
        self._terrain_jump_cd = 0
        self.dead = False
        self.coyote = 0                 # 土狼窗口剩余 tick（离地后仍可跳）
        self.item_cd = 0                # 上手冷却：拿到东西后还要等几个 tick 才用
        self._jump_pending = None       # None/"stand"/"protest"
        self._jump_hold = None          # 下次跳持跳时长（None=到衰减完）
        self._jump_hold_left = None     # 本次腾空剩余持跳（None=不截断）
        self.jump_boost = 0.0

        self.feet_stuck = None          # 钉脚锚 (x,y) or None
        self.crawl_anchor = None
        self.crawl_pose = 0.0           # 0→1 趴姿混合

        self.crawl_sink = 0.0
        self.hip_sink = 0.0
        self._floor_h = self.H

        self.bodyMode = "Stand"
        self.animation = None
        self._flip_spin = 0             # AI Flip 力矩方向
        self._flip_mult = 2.5           # AI Flip 力矩倍率
        self.on_pole = False
        self.pole_x = 0.0
        self.pole_y = 0.0

        self.facing = 1                 # +1 右 / -1 左
        self.stance = 0.42 * self._conn_stand
        self.foot_lift = 4.0
        self.step_threshold = 0.5 * self._conn_stand
        self.step_speed = 0.18
        self.step_predict = 0.5
        self.lfoot = [hx - self.stance, self.H]
        self.rfoot = [hx + self.stance, self.H]
        self._lstep = {"on": False, "start": 0.0, "goal": 0.0, "lerp": 1.0}
        self._rstep = {"on": False, "start": 0.0, "goal": 0.0, "lerp": 1.0}
        self.stride_phase = 0.0
        self.stride_rate = 0.06
        self._stride_prev_x = None
        self.turn = 0.0                 # 0=正面 .. 1=侧面
        self.turn_rate = 0.12
        self.walk_bob_y = 0.0
        self.walk_bob_amp = 0.0
        self.walk_bob_freq = 1.0

        self.breath = 0.0
        self.last_breath = 0.0           # 上帧呼吸相位
        self.sleeping = False            # 睡眠态：呼吸周期恒 80

        # energy ∈[0,1]，1=满 0=耗尽
        self.energy = float(energy)

        # temper ∈[-1,1]，负疏远正亲密
        self.temper = float(temper)

        # food ∈[0,food_max]，上限/冬眠阈值按种族
        self.food_max = stats.max_food
        self.food_hibernate = stats.food_hibernate
        self.food = int(tuning.FOOD_INIT if food is None else food)
        # 原版 PlayerState.quarterFoodPoints：食物条内部按 1/4 格记账
        self.food_quarter = 0
        # 食性（cats/personality.py 的 DIET_*）：PetUnit 建好 body 后写入，
        # 供 food_eat_object() 按原版 NourishmentOfObjectEaten 结算
        self.diet = None

        # karma_max 随种族，老存档超值在此夹回
        self.karma_max = tuning.KARMA_MAX if stats.karma_cap is None else stats.karma_cap
        self.karma = max(0, min(self.karma_max,
                                int(tuning.KARMA_INIT if karma is None else karma)))
        # 业力花条（原版 reinforcedKarma）：隐藏的「一格」，吃了业力花就满；
        # 满的时候死亡不掉业力、并消耗掉这一格
        self.flower_karma = False

        # cold ∈[0,2]，0.8起抽搐 ≥1可冻死
        self.cold = 0.0
        self.cold_gain = 0.0            # 上一 tick cold 增量

        self.walk_min = None
        self.walk_max = None

        self.suspended = False
        self.hover = False
        self.hover_airfric = 0.788

        # 零重力：window 每 tick 注入 zerog/room_gravity
        self.zerog = False
        self.room_gravity = 1.0
        self.canJump = 0
        self._zerog_kick = False
        self._zerog_wall = (0, 0)
        self._zerog_kick_dir = (0.0, 0.0)
        self.zerog_pole = None
        self.zerog_pole_intent = (0.0, 0.0)

        # 水面波形（None=无水），_wy* 为本 tick 水面高缓存，x 变了现算
        self.water_surface = None
        self._wy0 = self._wy1 = None
        self._wyx0 = self._wyx1 = 0.0

        # 游泳/憋气/淹死；air_frac 是死亡下界统一口径（工匠 0.65 即溺爆）
        self.air_death = tuning.PYRO_DEATH_THRESH if stats.is_artificer else 0.0
        self.air_in_lungs = 1.0
        self.lungs_exhausted = False
        self.drown = 0.0
        self.submersion = 0.0
        self.head_sub = 0.0
        self.hip_sub = 0.0
        self.submerged = False
        self.swimming = False
        self.swim_target = None
        self.swim_mode = None        # "deep"/"surface"/None
        self.swim_cycle = 0.0
        self.swim_input_x = 0
        self.swim_force = 0.0
        self.water_jump_delay = 0
        self.swim_boost_dist = tuning.SWIM_BOOST_DIST
        self._swim_wf = WATER_FRICTION
        self.pyro_drown = False

        # 手动控制：总闸 / 每 tick 输入源 / 10 帧历史环
        self._ctrl_on = False
        self._input_provider = None
        self._ctrl_input = None

        self.impact_cb = None           # 地形撞击回调，None=不触发
        self.carried_fruit = None
        self.hand_of = {}           # 物品种类 -> 「主手」(l/r)；一只手一件，矛可以两只手各一支
        self.carried_stone = None
        # 双手就是两个容器（原版 Player.grasps[2]）。矛是唯一能同种占两格的物件，
        # 所以单独记 side -> spear；carried_spear 只是 hand_of["spear"] 那只手的快照。
        self.hand_spears = {}
        self.carried_spear = None
        self.back_spear = None        # 背后的备用矛（原版 Player.spearOnBack）
        self.stun = 0
        self.arm_aim = {"l": None, "r": None}
        self.hand_pos = {"l": None, "r": None}   # 手上帧世界坐标（graphics 每帧写回）
        self.arm_full_reach = 24.0
        self.eat_raise = 0.0

        # 窗口边缘当墙：-1 左墙 / +1 右墙 / 0 未吸附（只能扶墙下滑，不能爬）
        self.wall_side = 0
        self.wall_cd = 0                # 蹬墙跳硬直
        self.ceil_cling = False         # 上边缘吊挂
        self.ceil_x = 0.0
        self.ceil_y = 0.0
        self.crawl_want = False         # 匍匐欲望（移动时压低身姿）

    @property
    def total_mass(self):
        """两 chunk 质量和。"""
        return self.chunk0.mass + self.chunk1.mass

    def collision_chunks(self):
        """两 body chunk 恒可碰撞。"""
        return (self.chunk0, self.chunk1)

    def clamp_cold(self):
        self.cold = 0.0 if self.cold < 0.0 else (1.0 if self.cold > 1.0 else self.cold)

    @property
    def hip(self):
        return self.chunk1

    @property
    def upper(self):
        return self.chunk0

    def on_floor(self):
        return self.chunk0.on_floor or self.chunk1.on_floor

    def is_moving(self):
        return self.walk_target_x is not None and abs(self.walk_target_x - self.chunk1.x) > WALK_STOP_EPS

    def walk_to(self, x):
        x = float(x)
        if self.walk_min is not None:
            x = min(max(x, self.walk_min), self.walk_max)
        self.walk_target_x = x

    def stop_walk(self):
        self.walk_target_x = None
        self.move_dir = 0

    def set_posture(self, standing: bool):
        self.standing = bool(standing)
        if standing:
            self.crawl_want = False

    def request_jump(self, kind="stand", hold_ticks=None):
        self._jump_pending = kind
        self._jump_hold = hold_ticks

    def tip_launch(self, hold_ticks=None, move_dir=0):
        """离地脉冲起跳（杆顶用）。"""
        c0, c1 = self.chunk0, self.chunk1
        c0.pinned = c1.pinned = False
        self.on_pole = False
        self.animation = None
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self.standing = True
        self._jump_pending = self._jump_hold = None
        self._jump_hold_left = hold_ticks
        c0.vy = self.stats.jump_head
        c1.vy = self.stats.jump_feet
        self.jump_boost = self.stats.jump_boost
        self.walk_target_x = None
        self.move_dir = int(move_dir)

    def pole_jump(self, direction, move_dir=None, up=True):
        """竖杆跳：朝 direction 斜跳出杆（up 决定高度档）。

        up=True 是原版 beam jump（Player.Jump 的 ClimbOnBeam·input.x!=0 分支，
        胸 6/8、胯 5/7）；up=False 是原版「离杆平跳」（同一分支的 input.x==0 /
        y≤0 情形：只给胸 chunk vy=+2 与 vx=2·朝向，胯不动）——于是离杆跳也有
        「往哪边 + 多高」两个参数。"""
        c0, c1 = self.chunk0, self.chunk1
        c0.pinned = c1.pinned = False
        self.on_pole = False
        self.animation = None
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self.standing = True
        self._jump_pending = self._jump_hold = self._jump_hold_left = None
        self.jump_boost = 0.0
        d = 1.0 if direction >= 0 else -1.0
        s = self.stats
        if up:
            c0.vx = s.pole_jump_head_vx * d
            c0.vy = s.pole_jump_head_vy
            c1.vx = s.pole_jump_feet_vx * d
            c1.vy = s.pole_jump_feet_vy
        else:
            c0.vx = POLE_OFF_VX * d
            c0.vy = POLE_OFF_VY
            c1.vx = 0.0
            c1.vy = 0.0
        self.walk_target_x = None
        self.move_dir = int(d if move_dir is None else move_dir)

    def pole_hop(self, direction, move_dir=None, up=True):
        """杆上跳向邻近杆：小冲量斜跳（原版 jump-pole-hopping）。

        pole_jump 是全力 beam jump（横速 stats.pole_jump_head_vx≈6px/tick，一条弧要
        飞 300+px），从杆顶朝 40px 外的邻杆跳出会从它头顶掠过、落到远处地面 —— 邻杆
        跳必须用小冲量（同高有效横距≈tuning.POLE_HOP_MAX_DX）；
        planning.pole_hop 的规划弧与这里同源（jump_arc.get_pole_hop_arc），否则
        「规划说够得着、执行却飞过头」。
        """
        self.pole_jump(direction, move_dir, up=up)
        if not up:
            return                       # up=False 已由 pole_jump 写好离杆平跳冲量
        d = 1.0 if direction >= 0 else -1.0
        c0, c1 = self.chunk0, self.chunk1
        c0.vx = c1.vx = tuning.POLE_HOP_VX * d
        c0.vy = c1.vy = -tuning.POLE_HOP_VY

    def play_hop(self, direction, vx, vy_scale=1.0):
        """玩耍跳：朝 direction、带上横速 vx 的小跳（方向与距离由调用方随机）。

        和 request_jump("stand") 的原地跳不同 —— 原版玩家起跳的横速来自起跳前的
        地面加速，宠物猫没有输入，只能在起跳这一帧把横速直接写进两个 chunk。
        朝向也跟着跳的方向（玩耍时的面向倾向）。
        """
        c0, c1 = self.chunk0, self.chunk1
        d = 1.0 if direction >= 0 else -1.0
        c0.pinned = c1.pinned = False
        self.on_pole = False
        self.animation = None
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self.standing = True
        self._jump_pending = self._jump_hold = self._jump_hold_left = None
        self.facing = int(d)
        self.move_dir = int(d)
        self.walk_target_x = None
        self.coyote = 0
        s = self.stats
        c0.vy = s.jump_head * float(vy_scale)
        c1.vy = s.jump_feet * float(vy_scale)
        c0.vx = c1.vx = float(vx) * d
        self.jump_boost = s.jump_boost

    def backflip_launch(self, direction, boosted=False):
        """站立位后空翻发射。"""
        c0, c1 = self.chunk0, self.chunk1
        c0.pinned = c1.pinned = False
        self.on_pole = False
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self.standing = True
        self._jump_pending = self._jump_hold = self._jump_hold_left = None
        self.jump_boost = self.stats.flip_boost if boosted else 0.0
        d = 1 if int(direction) >= 0 else -1
        s = self.stats
        c0.y -= 6.0
        c1.y -= 6.0
        c0.cx = c0.cy = c1.cx = c1.cy = 0
        c0.vx = s.backflip_vx * d
        c0.vy = s.flip_head if boosted else s.backflip_c0_vy
        c1.vx = s.backflip_vx * d
        c1.vy = s.flip_feet if boosted else s.backflip_c1_vy
        self.animation = "Flip"
        self._flip_spin = -d            # 力矩方向=飞行反向
        self._flip_mult = 2.5           # 滑铲源翻跳
        self.walk_target_x = None
        self.move_dir = d
        self.facing = -d

    def pyro_boost(self, ix, iy, overheat=False):
        """工匠空中爆跳运动学。"""
        c0, c1 = self.chunk0, self.chunk1
        ix = int(ix)
        iy = int(iy)
        if ix != 0:
            c0.vy = max(c0.vy, 0.0) - 8.0    # 清落速再给向上冲量
            c1.vy = max(c1.vy, 0.0) - 7.0
            self.jump_boost = 6.0
        if ix == 0 or iy == 1:
            if overheat:
                c0.vy, c1.vy, self.jump_boost = -16.0, -15.0, 10.0
            else:
                c0.vy, c1.vy, self.jump_boost = -11.0, -10.0, 8.0
        if iy == 1:
            c0.vx = 10.0 * ix
            c1.vx = 8.0 * ix
        else:
            c0.vx = 15.0 * ix
            c1.vx = 13.0 * ix
        self._jump_hold_left = None
        self.animation = "Flip"
        # 力矩键取飞行水平向
        self._flip_spin = ix if ix != 0 else self.facing
        self._flip_mult = 1.0           # 非滑铲源
        self.bodyMode = "Default"

    def release_to_air(self, move_dir=0):
        """松杆/松舌转自由落体。"""
        c0, c1 = self.chunk0, self.chunk1
        c0.pinned = c1.pinned = False
        self.on_pole = False
        self.animation = None
        self.feet_stuck = None
        self.crawl_anchor = None
        self.standing = True
        self.walk_target_x = None
        self.move_dir = int(move_dir)

    def teleport(self, hx, hy, keep_vel=False):
        """整体平移到 hip=(hx,hy)。"""
        dx, dy = hx - self.chunk1.x, hy - self.chunk1.y
        for c in (self.chunk0, self.chunk1):
            c.x += dx; c.y += dy
            c.last_x += dx; c.last_y += dy
            c.last_last_x += dx; c.last_last_y += dy
            if not keep_vel:
                c.vx = c.vy = 0.0
        self.wall_side = 0
        self.ceil_cling = False
        self.chunk0.pinned = False
        for f in (self.lfoot, self.rfoot):
            f[0] += dx
        self.feet_stuck = None
        self.crawl_pose = 0.0

    def die(self):
        self.dead = True
        self.bodyMode = "Dead"
        self.standing = False
        self.walk_target_x = None
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self.suspended = False
        self.hover = False
        self._jump_pending = None
        self._jump_hold = None
        self.drop_all()
        self.stun = 0
        self.zerog_pole = None
        self.wall_side = 0
        self.ceil_cling = False
        self.crawl_want = False
        self.animation = None

    def revive(self):
        self.dead = False
        self.air_in_lungs = 1.0          # 复活重置憋气，防残留标志立即再死
        self.drown = 0.0
        self.lungs_exhausted = False
        self.submerged = False
        self.pyro_drown = False
        self.wall_side = 0
        self.wall_cd = 0
        self.ceil_cling = False

    # ── 窗口边缘＝实体墙/天花（原版房间边界）──
    def wall_hold_x(self, side: int) -> float:
        from .edges import wall_hold_x
        return wall_hold_x(side, self.W)

    def grab_wall(self, side: int) -> bool:
        """扶住左右墙；side=-1 左 / +1 右。

        原版 WallClimb 只能扶着墙往下滑（Player.cs:9599-9614 只有 gravity 的重力项，
        没有任何向上推进），上升只能靠蹬墙跳 —— 所以这里也不叫「爬墙」了。
        """
        if self.dead or self.wall_cd > 0 or not side:
            return False
        self.wall_side = int(side)
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self.walk_target_x = None
        self.move_dir = 0
        self.on_pole = False
        self.ceil_cling = False
        self.animation = "WallClimb"
        self.standing = True
        self.facing = 1 if side > 0 else -1
        x = self.wall_hold_x(self.wall_side)
        for c in (self.chunk0, self.chunk1):
            c.pinned = False
            c.x = x
            c.vx = 0.0
            c.vy = 0.0
        return True

    def release_wall(self):
        self.wall_side = 0
        if self.animation == "WallClimb":
            self.animation = None

    def wall_jump(self, up: bool = True) -> bool:
        """蹬墙跳：朝离墙方向弹开，up=带一次上抛助力。"""
        side = self.wall_side
        if not side:
            return False
        self.release_wall()
        self.wall_cd = WALL_JUMP_LOCK
        c0, c1 = self.chunk0, self.chunk1
        c0.pinned = c1.pinned = False
        c0.vx = -side * WALL_JUMP_VX
        c1.vx = -side * WALL_JUMP_VX_FEET
        c0.vy = -WALL_JUMP_VY
        c1.vy = -WALL_JUMP_VY_FEET
        if up:
            self.jump_boost = 4
        return True

    def grab_ceiling(self, x=None) -> bool:
        """吊挂到上边缘（＝把上边缘当地面/天花）。"""
        if self.dead or self.wall_cd > 0:
            return False
        from .edges import CEIL_EDGE_PAD
        if x is None:
            x = self.chunk0.x
        self.release_wall()
        c0, c1 = self.chunk0, self.chunk1
        self.ceil_cling = True
        self.ceil_x = clampf(float(x), CEIL_EDGE_PAD, self.W - CEIL_EDGE_PAD)
        self.ceil_y = c0.rad + CEIL_HANG_PAD
        self.on_pole = False
        self.suspended = False
        self.animation = "HangFromBeam"
        self.walk_target_x = None
        self.move_dir = 0
        self.feet_stuck = None
        self.crawl_anchor = None
        c0.pinned = True
        c0.x, c0.y = self.ceil_x, self.ceil_y
        c0.vx = c0.vy = 0.0
        c1.pinned = False
        c1.x = self.ceil_x
        c1.y = self.ceil_y + self._conn_stand
        c1.vx = c1.vy = 0.0
        return True

    def ceil_shimmy(self, d: float):
        from .edges import CEIL_EDGE_PAD
        self.ceil_x = clampf(self.ceil_x + d * CEIL_SHIMMY_SPEED,
                             CEIL_EDGE_PAD, self.W - CEIL_EDGE_PAD)

    def release_ceiling(self):
        if not self.ceil_cling:
            return
        self.ceil_cling = False
        self.chunk0.pinned = False
        self.animation = None

    # ── 匍匐 ──
    def set_crawl(self, want: bool):
        """匍匐欲望：移动时压低身姿（bodyMode=Crawl）。"""
        self.crawl_want = bool(want)
        if self.crawl_want:
            self.standing = False

    def put_spear_on_back(self, spear):
        if not getattr(self.stats, "back_spear", False):
            return False
        """把一支矛背到背上（原版 Player.spearOnBack）。

        背上只能挂一支：被顶替的旧矛归还地面（state=FREE），
        否则它会一直保持 CARRIED 却不再属于任何槽位（渲染/物理都会出错）。
        """
        old = self.back_spear
        if old is not None and old is not spear:
            old.state = ItemState.FREE
            old.held_by = None
            old.stuck = False
            old.stuck_to = None
        side = self.spear_side(spear)
        if side is not None:              # 从手里挪到背上：那只手要腾出来，
            self.release_spear(to_free=False, side=side)   # 不然同一根矛会占两个槽
        self.back_spear = spear
        spear.state = ItemState.CARRIED
        spear.held_by = self
        spear.stuck = False
        spear.stuck_to = None

    def take_back_spear(self, side="r"):
        """从背上把矛抽到手里。"""
        sp = self.back_spear
        if sp is None:
            return None
        self.back_spear = None
        # arm=False：这根矛就是自己背上的，不算「刚到手」，
        # 不该重压手上冷却（否则猎手从背上抽出矛来反而丢不出去）。
        if self.grab_spear(sp, side, arm=False):
            return sp
        self.back_spear = sp              # 手上腾不出位置：还背回去，别把矛弄丢
        return None

    def drop_all(self):
        """丢掉手上所有东西（原版丢物品）。"""
        if self.back_spear is not None:
            self.back_spear.state = ItemState.FREE
            self.back_spear.held_by = None
            self.back_spear = None
        for side in list(self.hand_spears):
            self.release_spear(to_free=True, side=side)
        for kind in list(self.hand_of):
            self._release_item(kind, to_free=True)

    def drop_one_item(self, to_free=True):
        """放掉手上优先级最低的一件（两只手都攥着同级东西时用来腾地方）。返回那只手。"""
        items = self.hand_items()
        if not items:
            return None
        side = min(items, key=lambda s: self.ITEM_PRIO.get(self.held_kind(s), 0))
        self._release_item_at(side, to_free=to_free)
        return side

    def set_control_input(self, pkg):
        """push 当前帧进控制输入历史环。"""
        if self._ctrl_input is None:
            from ..control.input import InputBuffer
            self._ctrl_input = InputBuffer()
        self._ctrl_input.push(pkg)
        self._ctrl_on = True

    def step(self):
        self._temper_update()
        if self.item_cd > 0:                 # 上手冷却照常走钟（晕/死/杆上也算）
            self.item_cd -= 1
        if self._input_provider is not None:
            # 晕/死改推零包，防晕醒瞬间吃到晕期边沿
            pkg = self._input_provider()
            if self.stun > 0 or self.dead:
                from ..control.input import InputPackage
                pkg = InputPackage()
            if pkg is not None:
                self.set_control_input(pkg)
        if self.dead:
            self._step_dead()
            return
        # 无水时 no-op
        self._update_submersion()
        self._lung_update()
        swimming = self._should_swim()      # 游泳压过 zerog
        self.swimming = swimming
        if self.hover:
            self._step_hover()
            return
        if self.zerog and not swimming:
            self._step_zerog()
            return
        if swimming:
            self._step_swim()
            return
        if self.stun > 0:
            self.stun -= 1
            self._step_stunned()
            return
        if self.wall_cd > 0:
            self.wall_cd -= 1
        if self.wall_side:
            self._wall_update()
        elif self.ceil_cling:
            self._ceiling_update()
        elif self.on_pole:
            self._pole_update()
        elif not self.suspended:
            self._movement_update()
        else:
            self._suspended_update()
        ws = self.water_surface
        for c, wy, wx in ((self.chunk0, self._wy0, self._wyx0),
                          (self.chunk1, self._wy1, self._wyx1)):
            if ws is not None and c.x != wx:      # x 变了缓存失键，现算
                wy = ws.level_at(c.x)
            c.update(self.W, self._floor_h, impact=self.impact_cb,
                     room_gravity=self.room_gravity, water_y=wy,
                     buoyancy=self.stats.buoyancy, water_friction=WATER_FRICTION)
        self.conn_rest = self._conn_stand if self.standing else self._conn_crawl
        # 控制态滚/滑期连接距=10
        rest = 10.0 if (self._ctrl_on and self._ctrl_roll_direction != 0) else self.conn_rest
        solve_conn(self.chunk0, self.chunk1, rest, ctype=self.conn_type)
        self.chunk0.clamp_inside(self.W, self._floor_h)
        self.chunk1.clamp_inside(self.W, self._floor_h)
        self._gait_update()
        self._breath_update()
        self._apply_carry()
        self._apply_carry_stone()
        self._apply_carry_spear()

    def _step_hover(self):
        ws = self.water_surface
        for c, wy, wx in ((self.chunk0, self._wy0, self._wyx0),
                          (self.chunk1, self._wy1, self._wyx1)):
            if ws is not None and c.x != wx:
                wy = ws.level_at(c.x)
            c.update(self.W, self.H, gravity=0.0, air_friction=self.hover_airfric,
                     impact=self.impact_cb, room_gravity=self.room_gravity, water_y=wy,
                     buoyancy=self.stats.buoyancy, water_friction=WATER_FRICTION)
        solve_conn(self.chunk0, self.chunk1, self.conn_rest, ctype="Normal")
        self.chunk0.clamp_inside(self.W, self.H)
        self.chunk1.clamp_inside(self.W, self.H)
        self._breath_update()

    # 水浸没度/憋气/游泳（y↓）
    def _update_submersion(self):
        """两 chunk 浸没度，无水全 0。"""
        ws = self.water_surface
        if ws is None:
            self.head_sub = self.hip_sub = self.submersion = 0.0
            self._wy0 = self._wy1 = None
            return
        c0, c1 = self.chunk0, self.chunk1
        self._wy0 = wy0 = ws.level_at(c0.x)
        self._wy1 = wy1 = ws.level_at(c1.x)
        self._wyx0 = c0.x
        self._wyx1 = c1.x
        hs = (c0.y + c0.rad - wy0) / (2.0 * c0.rad)
        ps = (c1.y + c1.rad - wy1) / (2.0 * c1.rad)
        self.head_sub = 0.0 if hs < 0.0 else (1.0 if hs > 1.0 else hs)
        self.hip_sub = 0.0 if ps < 0.0 else (1.0 if ps > 1.0 else ps)
        self.submersion = self.head_sub if self.head_sub > self.hip_sub else self.hip_sub

    def _should_swim(self) -> bool:
        """进游泳判据：站浅水不算。"""
        if self.water_surface is None or self.on_pole:
            return False
        if self.submersion <= tuning.SWIM_ENTER:
            return False
        if self.on_floor() and self.head_sub < tuning.SWIM_ENTER:
            return False
        return True

    def _swim_dir(self):
        """朝 swim_target 单位向量，无目标/晕 → (0,0)。"""
        t = self.swim_target
        if t is None or self.stun > 0:
            return 0.0, 0.0
        dx, dy = t[0] - self.chunk0.x, t[1] - self.chunk0.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return 0.0, 0.0
        return dx / d, dy / d

    def _swim_up_still(self) -> bool:
        """直上求生姿势 → 耗气变慢。"""
        t = self.swim_target
        if t is None:
            return False
        dx, dy = t[0] - self.chunk0.x, t[1] - self.chunk0.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return False
        return (dy / d) < -0.5 and abs(dx / d) < 0.3

    @property
    def air_frac(self) -> float:
        """剩余气比例 [0,1]。"""
        d = self.air_death
        if d <= 0.0:
            return self.air_in_lungs
        return max(0.0, (self.air_in_lungs - d) / (1.0 - d))

    def _lung_update(self):
        """憋气/淹死推进。"""
        if self.hover:                                    # 超度悬浮不耗气
            return
        s = self.stats
        c0 = self.chunk0
        if self.head_sub > tuning.SWIM_LUNG_SUBMERGE:     # 头浸没 → 耗气
            if not self.submerged:                        # 刚入水首帧
                self.swim_force = inv_lerp(0.0, 8.0, abs(c0.vx))
                self.swim_cycle = 0.0
            saver = 1.5 if (self.air_frac < s.drown_threshold and self._swim_up_still()) else 1.0
            prev_frac = self.air_frac                      # 供吐泡判定 2/3 跨越
            self.air_in_lungs -= (1.0 / (40.0 * (4.5 if self.lungs_exhausted else 9.0) * saver)) * s.lungs_fac
            self._drown_bubbles(prev_frac)                 # 憋气吐泡
            # 工匠溺爆待触发
            if s.is_artificer and self.air_in_lungs <= tuning.PYRO_DEATH_THRESH:
                self.pyro_drown = True
            # 淹死判定；Rivulet 非溺水免疫但耗气极慢，实际难触发
            if (self.air_in_lungs <= 0.0 and self.head_sub >= 0.999
                    and self.hip_sub > tuning.SWIM_DROWN_SUB_HIP):
                self.air_in_lungs = 0.0
                self.stun = max(self.stun, 10)
                self.drown += tuning.SWIM_DROWN_STEP
                if self.drown >= 1.0:
                    self.die()
            self.submerged = True
        else:                                             # 出水/浅水：换气回满
            if self.submerged and self.air_frac < s.drown_threshold:
                self.lungs_exhausted = True
            if not self.lungs_exhausted and self.air_in_lungs > 0.9:
                self.air_in_lungs = 1.0
            if self.air_in_lungs < 0.0:
                self.air_in_lungs = 0.0
            self.air_in_lungs += 1.0 / (tuning.SWIM_LUNG_RECOVER_EXH if self.lungs_exhausted
                                        else tuning.SWIM_LUNG_RECOVER)
            if self.air_in_lungs >= 1.0:
                self.air_in_lungs = 1.0
                self.lungs_exhausted = False
                self.drown = 0.0
            self.submerged = False
            self.pyro_drown = False       # 撤销工匠溺爆待触发
        if self.air_in_lungs > 1.0:
            self.air_in_lungs = 1.0

    def _emit_bubble(self, x, y, vx, vy):
        """吐泡统一出口，按种族概率门。"""
        if self.bubble_cb is None:
            return
        bf = self.stats.bubble_fac
        if bf < 1.0 and random.random() >= bf:
            return
        self.bubble_cb(x, y, vx, vy)

    def _drown_bubbles(self, prev_frac):
        """憋气吐泡：跌破 2/3 冒首泡，缺氧区按概率连吐。"""
        c0 = self.chunk0
        air = self.air_frac
        vx0 = c0.vx * tuning.BUBBLE_INHERIT_VEL            # 少量继承头速，防飞远
        vy0 = c0.vy * tuning.BUBBLE_INHERIT_VEL
        if prev_frac >= 2.0 / 3.0 > air:                   # 跌破 2/3 首泡
            self._emit_bubble(c0.x, c0.y, vx0, vy0)
        if air < self.stats.drown_threshold:               # 缺氧挣扎区：概率/散射随缺氧加剧
            if (random.random() > air * 2.0 or self.lungs_exhausted) and random.random() > 0.5:
                ang = random.random() * math.tau
                kick = lerp(tuning.BUBBLE_SPAWN_KICK, 0.0, air)
                self._emit_bubble(c0.x, c0.y,
                                  vx0 + math.cos(ang) * kick,
                                  vy0 + math.sin(ang) * kick)

    def _step_swim(self):
        """游泳分流：深泳/浮泳二分。"""
        if self.stun > 0:                    # stun 早 return，此处递减自愈
            self.stun -= 1
        if self.water_jump_delay > 0:        # 冲刺冷却递减
            self.water_jump_delay -= 1
        self.bodyMode = "Swimming"
        self.feet_stuck = None
        self.crawl_anchor = None
        self._floor_h = self.H
        ws = self.water_surface
        c0, c1 = self.chunk0, self.chunk1
        self._decide_swim_mode(ws)
        sdx, _sdy = self._swim_dir()                 # 取泳向水平分量供动画
        self.swim_input_x = 1 if sdx > 0.0 else (-1 if sdx < 0.0 else 0)   # 同 _surface_swim 横游意图阈值
        if self.swim_mode == "deep":
            self._deep_swim()
        else:
            self._surface_swim(ws)
        wf = self._swim_wf
        vmax = tuning.SWIM_VEL_MAX               # 封顶游泳速度，防冲刺穿墙
        for c, wy, wx in ((c0, self._wy0, self._wyx0), (c1, self._wy1, self._wyx1)):
            sp = math.hypot(c.vx, c.vy)
            if sp > vmax:
                k = vmax / sp
                c.vx *= k
                c.vy *= k
            c.update(self.W, self._floor_h, impact=self.impact_cb,
                     room_gravity=self.room_gravity,
                     water_y=wy if c.x == wx else ws.level_at(c.x),
                     buoyancy=self.stats.buoyancy, water_friction=wf)
        self.conn_rest = self._conn_stand
        solve_conn(c0, c1, self.conn_rest, ctype="Normal")
        c0.clamp_inside(self.W, self._floor_h)
        c1.clamp_inside(self.W, self._floor_h)
        self._breath_update()
        self._apply_carry()          # 游泳时也要跟手
        self._apply_carry_stone()
        self._apply_carry_spear()

    def _decide_swim_mode(self, ws):
        """深泳/浮泳二分（y↓）。"""
        c0 = self.chunk0
        wl0 = self._wy0 if c0.x == self._wyx0 else ws.level_at(c0.x)
        diving = self.swim_target is not None and (self.swim_target[1] - c0.y) > 5.0
        prev_surface = (self.swim_mode == "surface")
        below_full = c0.y > wl0 + tuning.SWIM_DEEP_FULL     # y↓ 更深=更大
        depth = tuning.SWIM_DEEP_DIVE_DEPTH if diving else tuning.SWIM_DEEP_DEPTH
        below_entry = c0.y > wl0 + depth
        hip_req = -1.0 if diving else tuning.SWIM_DEEP_HIP_SUB
        if (not prev_surface or diving or below_full) and below_entry and self.hip_sub > hip_req:
            self.swim_mode = "deep"
        else:
            self.swim_mode = "surface"

    def _deep_swim(self):
        """深泳推进。"""
        s = self.stats
        c0, c1 = self.chunk0, self.chunk1
        self.standing = False
        axx, axy = c0.x - c1.x, c0.y - c1.y                # hip→head 体轴
        axl = math.hypot(axx, axy) or 1.0
        ax_u, ay_u = axx / axl, axy / axl
        axis_align = (_dot_norm(c0.vx, c0.vy, ax_u, ay_u) + _dot_norm(c1.vx, c1.vy, ax_u, ay_u)) / 2.0
        swim_x, swim_y = self._swim_dir()
        have_dir = (swim_x != 0.0 or swim_y != 0.0)
        # 冲刺 boost：气足+冷却完+目标远才触发
        boost_ready = self.submerged if s.is_rivulet else (self.air_frac > tuning.SWIM_BOOST_MIN_AIR)
        dist = math.hypot(self.swim_target[0] - c0.x, self.swim_target[1] - c0.y) if self.swim_target else 0.0
        if have_dir and self.water_jump_delay == 0 and boost_ready and dist > self.swim_boost_dist:
            self.swim_cycle = 2.7
            if s.is_rivulet:
                f = 300.0 if (-ay_u) > 0.5 else 50.0       # y↓ 取负为上
                c0.vx += ax_u * f; c0.vy += ay_u * f
            else:
                c0.vx += ax_u * s.swim_boost_force; c0.vy += ay_u * s.swim_boost_force
            self.air_in_lungs -= s.swim_boost_cost
            self.water_jump_delay = s.swim_boost_cd
            self._emit_bubble(c0.x, c0.y,                  # 冲刺发力喷一个泡
                              c0.vx * tuning.BUBBLE_INHERIT_VEL,
                              c0.vy * tuning.BUBBLE_INHERIT_VEL)
        self.swim_cycle += 0.01
        if have_dir:
            axis_turn = _angle_deg(c0.last_x - c1.last_x, c0.last_y - c1.last_y, axx, axy)  # 体轴转速
            force_target = 0.2 + inv_lerp(0.0, 12.0, axis_turn) * 0.8
            if force_target > self.swim_force:
                self.swim_force = lerp(self.swim_force, force_target, 0.7)
            else:
                self.swim_force = lerp(self.swim_force, force_target, 0.05)
            self.swim_cycle += lerp(self.swim_force, 1.0, 0.5) / 10.0
            if 1.0 / 6.0 < self.air_frac < 0.5:
                self.swim_cycle += 0.05
            if c0.cx or c0.cy:                              # 撞墙
                self.swim_force *= 0.5
            stroke_kick = 0.7 * lerp(self.swim_force * s.swim_force_fac, 1.0, 0.5) * self.head_sub
            if self.swim_cycle > 4.0:                       # 相位冲程窗口
                self.swim_cycle = 0.0
            elif self.swim_cycle > 3.0:
                c0.vx += ax_u * stroke_kick; c0.vy += ay_u * stroke_kick
            aim_x, aim_y = swim_x, swim_y                    # 缺氧自救：泳向球插向上
            if self.air_frac < s.drown_threshold:
                t = inv_lerp(s.drown_threshold, 0.0, self.air_frac)
                aim_x, aim_y = _slerp2(aim_x, aim_y, 0.0, -1.0, t)   # 向上 = pet (0,-1)
            k = 0.5 * self.swim_force * lerp(axis_align, 1.0, 0.5) * self.head_sub * s.swim_force_fac
            c0.vx += aim_x * k; c0.vy += aim_y * k          # 方向划水
            c1.vx -= aim_x * (0.1 * self.head_sub); c1.vy -= aim_y * (0.1 * self.head_sub)
            k2 = 0.4 * self.swim_force * axis_align * self.head_sub * s.swim_force_fac
            c0.vx += ax_u * k2; c0.vy += ay_u * k2
            sp = math.hypot(c0.vx, c0.vy)                    # 低速补推
            if sp < 3.0:
                add = 0.2 * inv_lerp(3.0, 1.5, sp)
                c0.vx += aim_x * add; c0.vy += aim_y * add
                sub = 0.1 * inv_lerp(3.0, 1.5, sp)
                c1.vx -= aim_x * sub; c1.vy -= aim_y * sub
        # 游泳水阻，随体轴对齐度插值
        if s.is_rivulet and self.water_jump_delay >= 5:
            self._swim_wf = 0.99
        else:
            self._swim_wf = lerp(0.92, 0.96, axis_align)

    def _surface_swim(self, ws):
        """浮泳推进。"""
        s = self.stats
        c0, c1 = self.chunk0, self.chunk1
        self.canJump = 0
        self.swim_cycle += 0.025
        if s.is_rivulet and self.water_jump_delay >= 5:
            self._swim_wf = 0.999
        else:
            self._swim_wf = 0.96
        self.swim_force *= 0.5
        swim_x, swim_y = self._swim_dir()
        have_dir = (swim_x != 0.0 or swim_y != 0.0)
        iy = 0                                              # 竖直意图：+1 上 / -1 下
        if have_dir:
            if swim_y > 0.5:
                iy = -1                                     # 目标在下(y↓)=潜
            elif swim_y < -0.5:
                iy = 1                                      # 目标在上=浮
        wl0 = self._wy0 if c0.x == self._wyx0 else ws.level_at(c0.x)
        target_head_y = wl0 - tuning.SWIM_SURFACE_HEAD_ABOVE
        if iy > -1 and (-3.0 < c0.vy < 5.0) and self.water_jump_delay == 0:  # 贴水面
            c0.vy *= 0.8
            c1.vy *= 0.8
            c0.vy += clampf((target_head_y - c0.y) * 0.1, -1.5, 0.5)  # 头钳水线上方
            c1.vy += 0.5                                    # 臀略沉保直立浮姿
        elif iy == -1:                                      # 潜
            c0.vy += 0.2
            c1.vy -= 0.1
        elif iy == 1:                                       # 浮
            c0.vy -= 0.5
        ix = 1 if swim_x > 0.0 else (-1 if swim_x < 0.0 else 0)  # 横游意图
        if ix != 0:
            self._swim_accel_h(c0, ix, s.swim_surface_speed)
            hip_drag_mult = 1.5 if s.is_rivulet else 1.0
            c1.vx -= ix * 0.2 * hip_drag_mult
            self.swim_cycle += 1.0 / 30.0

    def _swim_accel_h(self, c, dir_sign, dyn):
        """浮泳横向加速，追顶速 dyn。"""
        if dir_sign < 0:
            step = H_ACCEL
            if c.vx - step < -dyn:
                step = dyn + c.vx
            if step > 0:
                c.vx -= step
        elif dir_sign > 0:
            step = H_ACCEL
            if c.vx + step > dyn:
                step = dyn - c.vx
            if step > 0:
                c.vx += step

    def _step_zerog(self):
        """零重力漂浮推进。"""
        if self.stun > 0:            # stun 早 return，此处递减自愈
            self.stun -= 1
        self.bodyMode = "ZeroG"
        self.feet_stuck = None
        self.crawl_anchor = None
        if self._ctrl_on and self.stun <= 0:
            # 控制态覆盖口：手操输入接管
            from ..control.moves_zerog import ctrl_zerog_update
            ctrl_zerog_update(self)
        rg = self.room_gravity
        c0, c1 = self.chunk0, self.chunk1
        grabbing = self._zerog_pole_grab()    # 贴杆则覆盖自由漂速度
        for c in (c0, c1):
            c.update(self.W, self.H, gravity=cp.GRAVITY * rg,
                     air_friction=cp.AIR_FRICTION, impact=self.impact_cb)
        if not grabbing:
            # 贴窗边开 canJump 窗口，记背离法向
            nx, ny = self._zerog_wall_normal()
            if nx or ny:
                self.canJump = ZEROG_CANJUMP
                self._zerog_wall = (nx, ny)
            if self.canJump > 0:
                if self._zerog_kick:
                    self._do_zerog_kick()
                self.canJump -= 1
        self._zerog_kick = False
        self.conn_rest = self._conn_stand
        solve_conn(c0, c1, self.conn_rest, ctype="Normal")
        c0.clamp_inside(self.W, self.H)
        c1.clamp_inside(self.W, self.H)
        self._breath_update()
        self._apply_carry()          # 零重力叼持也要跟手
        self._apply_carry_stone()
        self._apply_carry_spear()

    def _zerog_pole_grab(self) -> bool:
        """抓杆动力学。"""
        pole = self.zerog_pole
        if pole is None:
            self._zerog_release_pose()
            return False
        c0, c1 = self.chunk0, self.chunk1
        if c0.pinned or c1.pinned:                       # 拖拽中不抓
            self.zerog_pole = None
            self._zerog_release_pose()
            return False
        cx, cy, perp = _closest_on_segment(c0.x, c0.y, pole.ax, pole.ay, pole.bx, pole.by)
        if perp > ZEROG_GRAB_DIST:                       # 漂离超距 → 安全松杆
            self.zerog_pole = None
            self._zerog_release_pose()
            return False
        lx, ly = pole.bx - pole.ax, pole.by - pole.ay    # 杆轴
        ll = math.hypot(lx, ly) or 1.0
        ax_u, ay_u = lx / ll, ly / ll                    # 沿轴单位
        px_u, py_u = -ay_u, ax_u                         # 垂直单位
        # 竖杆 standing=True，横杆 False
        self.animation = "ZeroGPoleGrab"
        self.standing = abs(ay_u) >= abs(ax_u)
        self.pole_x, self.pole_y = cx, cy
        # 越快阻尼越强，粘住杆
        speed = math.hypot(c0.vx, c0.vy)
        damp = lerp(0.7, 0.3, inv_lerp(2.0, 5.0, speed))
        c0.vx *= damp
        c0.vy *= damp
        # 拉向杆线 + 横向 lean
        ix, iy = self.zerog_pole_intent
        lean = ZEROG_POLE_LEAN * (ix * px_u + iy * py_u)
        c0.vx += (cx + px_u * lean - c0.x) * ZEROG_POLE_PULL
        c0.vy += (cy + py_u * lean - c0.y) * ZEROG_POLE_PULL
        # 沿杆滑
        slide = ix * ax_u + iy * ay_u
        c0.vx += ax_u * slide * ZEROG_POLE_CLIMB * self.stats.pole_fac
        c0.vy += ay_u * slide * ZEROG_POLE_CLIMB * self.stats.pole_fac
        # hip 阻尼收拢 + 朝自身杆线垂足回中拉
        c1.vx *= ZEROG_POLE_HIP
        c1.vy *= ZEROG_POLE_HIP
        hcx, hcy, _ = _closest_on_segment(c1.x, c1.y, pole.ax, pole.ay, pole.bx, pole.by)
        c1.vx += (hcx - c1.x) * ZEROG_POLE_PULL
        c1.vy += (hcy - c1.y) * ZEROG_POLE_PULL
        return True

    def _zerog_release_pose(self):
        """松杆复位。"""
        self.animation = None
        self.standing = True

    def _zerog_wall_normal(self):
        """贴墙背离法向 (nx,ny)，无接触 (0,0)。"""
        for c in (self.chunk0, self.chunk1):
            if c.cx or c.cy:
                return (-c.cx, -c.cy)
        return (0, 0)

    def _do_zerog_kick(self):
        """蹬窗边推进。"""
        nx, ny = self._zerog_wall
        d = math.hypot(nx, ny) or 1.0
        ax, ay = nx / d, ny / d                          # 背离墙单位法向
        ix, iy = self._zerog_kick_dir                    # AI 蹬向意图
        kick_x = ix + (ax - ix) * ZEROG_KICK_LERP
        kick_y = iy + (ay - iy) * ZEROG_KICK_LERP
        c0, c1 = self.chunk0, self.chunk1
        hx, hy = c0.x - c1.x, c0.y - c1.y                # hip→head 体轴
        hd = math.hypot(hx, hy) or 1.0
        bx, by = hx / hd, hy / hd
        kick_x = kick_x + (bx - kick_x) * ZEROG_KICK_BODYAXIS
        kick_y = kick_y + (by - kick_y) * ZEROG_KICK_BODYAXIS
        c0.vx += kick_x * ZEROG_KICK; c0.vy += kick_y * ZEROG_KICK
        c1.vx += kick_x * ZEROG_HIP_KICK; c1.vy += kick_y * ZEROG_HIP_KICK
        _clamp_vel_mag(c0, ZEROG_HEAD_MAX)
        _clamp_vel_mag(c1, ZEROG_HIP_MAX)
        c0.vx += ax; c0.vy += ay                         # 脱墙冲量，仅 head
        self.canJump = 0

    def zerog_swim(self, ux, uy, on_wall):
        """零重力划水：head 推、hip 反拖。"""
        c0, c1 = self.chunk0, self.chunk1
        if c0.vx * ux + c0.vy * uy >= ZEROG_SWIM_MAX:    # 到软上限停推
            return
        push = ZEROG_SWIM_WALL if on_wall else ZEROG_SWIM_PUSH
        c0.vx += ux * push
        c0.vy += uy * push
        c1.vx -= ux * ZEROG_SWIM_HIP                     # hip 反向摆动
        c1.vy -= uy * ZEROG_SWIM_HIP

    def request_zerog_kick(self, ux: float = 0.0, uy: float = 0.0):
        """请求下一 tick 蹬窗边。"""
        self._zerog_kick = True
        self._zerog_kick_dir = (ux, uy)

    def _settle_ragdoll_integrate(self):
        self.hip_sink += (1.0 - self.hip_sink) * HIP_SINK_EASE
        self._floor_h = self.H + self.hip_sink * self.crawl_sink
        ws = self.water_surface
        for c in (self.chunk0, self.chunk1):
            wy = ws.level_at(c.x) if ws is not None else None
            c.update(self.W, self._floor_h, air_friction=cp.AIR_FRICTION, impact=self.impact_cb,
                     room_gravity=self.room_gravity, water_y=wy,
                     buoyancy=self.stats.buoyancy, water_friction=WATER_FRICTION)
            if c.on_floor:
                c.vx *= 0.7

    def _step_dead(self):
        self._settle_ragdoll_integrate()
        solve_conn(self.chunk0, self.chunk1, self.conn_rest, ctype="Normal")
        self.chunk0.clamp_inside(self.W, self._floor_h)
        self.chunk1.clamp_inside(self.W, self._floor_h)

    def _step_stunned(self):
        self.bodyMode = "Stunned"
        self.feet_stuck = None
        self.crawl_anchor = None
        self._settle_ragdoll_integrate()
        self.conn_rest = self._conn_stand if self.standing else self._conn_crawl
        solve_conn(self.chunk0, self.chunk1, self.conn_rest, ctype="Normal")
        self.chunk0.clamp_inside(self.W, self._floor_h)
        self.chunk1.clamp_inside(self.W, self._floor_h)
        self._gait_update()
        self._breath_update()

    def _movement_update(self):
        if self._ctrl_on:
            # 控制态覆盖口，惰性 import 防环导
            from ..control.moves import ctrl_movement_update
            return ctrl_movement_update(self)
        if self.crawl_want:
            self.standing = False       # 匍匐欲望：压低身姿爬行
        c0, c1 = self.chunk0, self.chunk1
        if self._terrain_jump_cd > 0:
            self._terrain_jump_cd -= 1
        if self.animation == "Flip" and self._flip_spin != 0:
            # AI 翻跳力矩，触物退出
            from ..control.vmath import perpendicular
            vx, vy = perpendicular(c1.x, c1.y, c0.x, c0.y)
            k = self._flip_spin * (0.38 * self._flip_mult)
            c0.vx += vx * k
            c0.vy += vy * k
            c1.vx -= vx * k
            c1.vy -= vy * k
            self.standing = False
            if c0.cx != 0 or c0.cy != 0 or c1.cx != 0 or c1.cy != 0:
                self.animation = None
                self.standing = c0.y < c1.y
                self._flip_spin = 0
        move_x = 0
        if self.walk_min is not None and self.walk_target_x is not None:
            # 别的窗口挪动会改 walk_min/walk_max，旧目标可能已经落到墙外 →
            # 每 tick 重新夹一次，夹回墙内后「到站」判定自然成立，不会顶着墙跑。
            self.walk_target_x = min(max(self.walk_target_x, self.walk_min),
                                     self.walk_max)
        if self.walk_target_x is not None:
            dx = self.walk_target_x - c1.x
            if abs(dx) > WALK_STOP_EPS:
                move_x = 1 if dx > 0 else -1
                self.facing = move_x
            else:
                self.walk_target_x = None
        else:
            move_x = self.move_dir
            if move_x > 0:
                self.facing = 1
            elif move_x < 0:
                self.facing = -1

        target_sink = 1.0 if not self.standing else 0.0
        self.hip_sink += (target_sink - self.hip_sink) * HIP_SINK_EASE
        self._floor_h = self.H + self.hip_sink * self.crawl_sink

        if self.standing or move_x != 0:
            self.crawl_anchor = None
            self.crawl_pose = max(0.0, self.crawl_pose - 0.08)

        flag = (move_x == 0 and self.standing and c1.on_floor)
        if self.feet_stuck is not None and not flag:
            self.feet_stuck = None
        elif self.feet_stuck is None and flag:
            self.feet_stuck = [c1.x, self.support_y() - c1.rad]
        if self.feet_stuck is not None:
            self.feet_stuck[0] += (c1.x - self.feet_stuck[0]) * FEET_EASE
            self.feet_stuck[1] = self.support_y() - c1.rad
            if not c1.pinned:
                c1.x = self.feet_stuck[0]
                c1.y = self.feet_stuck[1]

        on_ground = self.on_floor()

        # 统一地形越障兜底：chunkphys 的 solid/cat_solid 同时负责碰撞和接触状态。
        # 如果猫确实在向目标走、脚已着地、同一方向的水平接触连续存在，
        # 说明前方是墙/门/障碍，而不是单纯的寻路误差；自动用一次小跳越过去。
        if on_ground and move_x != 0 and not self.on_pole and not self.ceil_cling:
            blocked = (c1.cx == move_x or c0.cx == move_x)
            if blocked:
                self._terrain_block_ticks += 1
            else:
                self._terrain_block_ticks = max(0, self._terrain_block_ticks - 2)
            if (blocked and self._terrain_block_ticks >= TERRAIN_JUMP_AFTER
                    and self._terrain_jump_cd <= 0):
                self.stop_walk()
                self.move_dir = move_x
                self.request_jump("stand", hold_ticks=3)
                self._terrain_jump_cd = TERRAIN_JUMP_COOLDOWN
                self._terrain_block_ticks = 0

        if on_ground:
            self.coyote = tuning.COYOTE_TICKS    # 踩地就续窗口（原版 canJump = 5）
        elif self.coyote > 0:
            self.coyote -= 1
        if not on_ground:
            self.bodyMode = "Default"
        elif self.standing:
            self.bodyMode = "Stand"
        else:
            self.bodyMode = "Crawl"

        dyn0 = RUN_UPPER * self.stats.runspeed_fac      # 顶速×种族因子，不乘加速度
        dyn1 = RUN_LOWER * self.stats.runspeed_fac
        if self.bodyMode == "Stand" and self.jump_boost <= 0.0:
            # 起跳期间不施加（原版 Stand 分离力净值为 0，本式净向下 3，会吃掉升力）
            c0.vy += STAND_HEAD
            c1.vy += STAND_FEET
        elif self.bodyMode == "Default" and self.standing:
            c0.vy += DEF_STAND_HEAD
            c1.vy += DEF_STAND_FEET
        elif self.bodyMode == "Crawl":
            dyn0 = dyn1 = CRAWL_SPEED      # 平地趴行恒速，不乘隧道爬速因子
            # 原版 Player.cs:9126：爬行移动中髋比胸低超过 3px 就逐帧抬起髋，
            # 让整条身体贴着地面走（不然会变成半跪着挪）。
            if (move_x != 0 and c0.on_floor and c1.cx == move_x
                    and c1.y > c0.y + 3.0):
                c1.y -= 1.0
            if (move_x == 0 and c1.on_floor and not c0.pinned and not c1.pinned
                    and self._jump_pending is None):
                self._crawl_pose()

        if self.walk_speed_target is not None:
            dyn0 = min(dyn0, self.walk_speed_target)
            dyn1 = min(dyn1, self.walk_speed_target)
        grounded = c0.on_floor or c1.on_floor
        for c, dyn in ((c0, dyn0), (c1, dyn1)):
            if c.pinned:
                continue
            if move_x < 0:
                step = H_ACCEL
                if c.vx - step < -dyn:
                    step = dyn + c.vx
                if step > 0:
                    c.vx -= step
            elif move_x > 0:
                step = H_ACCEL
                if c.vx + step > dyn:
                    step = dyn - c.vx
                if step > 0:
                    c.vx += step
            if grounded:
                target = max(-dyn, min(dyn, c.vx)) if move_x != 0 else 0.0
                c.vx += (target - c.vx) * SKID_DAMP
            if self.bodyMode == "Crawl":
                opp = 1.0 if self.facing >= 0 else -1.0
                if c.vx * opp < 0.0:
                    c.vx *= CRAWL_BACK_DAMP
        if self._jump_pending is not None and (on_ground or self.coyote > 0):
            self._do_jump(self._jump_pending, move_x, self._jump_hold)
            self._jump_pending = None
            self._jump_hold = None
            self.coyote = 0                 # 窗口一次性

        # 持跳可变跳高：原版 Player.cs:12188 只要求 jumpBoost>0 且按住跳键
        if self.jump_boost > 0:
            if self._jump_hold_left is not None and self._jump_hold_left <= 0:
                self.jump_boost = 0.0
            else:
                if self._jump_hold_left is not None:
                    self._jump_hold_left -= 1
                self.jump_boost -= JUMPBOOST_DECAY
                kick = (self.jump_boost + 1) * JUMPBOOST_GAIN
                c0.vy -= kick
                c1.vy -= kick
                if self.jump_boost < 0:
                    self.jump_boost = 0.0

        if self.walk_min is not None and move_x != 0:
            for c in (c0, c1):
                if c.x < self.walk_min:
                    c.x = self.walk_min
                elif c.x > self.walk_max:
                    c.x = self.walk_max
            if c1.on_floor:
                # 站在地上还朝墙里使劲＝顶着墙空跑（原版撞墙不会原地跑）：收力
                if c1.x <= self.walk_min and move_x < 0:
                    self.move_dir = 0
                elif c1.x >= self.walk_max and move_x > 0:
                    self.move_dir = 0

    def support_y(self) -> float:
        """脚下那块地的 y（工作区地板 or 别人窗口顶边）。"""
        s = self.chunk1.support_y
        return self._floor_h if s is None else s

    def _wall_update(self):
        """扶墙**下滑**（原版 Player.cs:9599-9614 的 WallClimb 分支）。

        原版墙态里没有任何向上推进：贴着实心墙时只按
        LerpMap(wallSlideCounter,0,30,0.8,0) 的重力系数往下滑，
        上升只能靠 WallJump。所以这里只有滑，没有「爬」。
        """
        x = self.wall_hold_x(self.wall_side)
        g = 0.9 * self.room_gravity
        climb = WALL_LEDGE_SLIDE + g      # 净下降速度（底下 vy = climb - g）
        for c in (self.chunk0, self.chunk1):
            c.pinned = False
            c.x = x
            c.vx = 0.0
            c.vy = climb - g
        self.bodyMode = "ClimbingOnBeam"
        self.animation = "WallClimb"
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self.standing = True
        self.facing = 1 if self.wall_side > 0 else -1
        self._floor_h = self.H

    def _ceiling_update(self):
        """吊挂上边缘：胸心钉顶边，下身垂挂，可横向挪动。"""
        c0, c1 = self.chunk0, self.chunk1
        self.ceil_y = c0.rad + CEIL_HANG_PAD
        c0.pinned = True
        c0.x = self.ceil_x
        c0.y = self.ceil_y
        c0.vx = c0.vy = 0.0
        c1.pinned = False
        self.bodyMode = "ClimbingOnBeam"
        self.animation = "HangFromBeam"
        self.on_pole = False
        self.feet_stuck = None
        self.crawl_anchor = None
        self.crawl_pose = 0.0
        self._floor_h = self.H

    def _pole_update(self):
        self.bodyMode = "ClimbingOnBeam"
        self.feet_stuck = None
        self.crawl_anchor = None
        self._floor_h = self.H

    def _suspended_update(self):
        if not self.on_floor():