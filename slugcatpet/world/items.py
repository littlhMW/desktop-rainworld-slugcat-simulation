"""Fruit and stone interaction helpers for ``PetWindow``."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)

from .._paths import log_error
from ..core.units import clampf, inv_lerp, lerp
from ..core.gfxmath import _hsl2rgb
from ..control.hotkey import HK_PLACE_ESC, VK_ESCAPE
from .fruit import PLACE_HANGING_FRAC, make_fruit
from ..rendering.graphics import _ang_from_up
from ..rendering.primitives import (blit, draw_fruit, draw_rope, draw_stone,
                                    draw_stone_trail, draw_pearl, draw_spear,
                                    draw_needle,
                                    draw_scavenger, draw_scavenger_spear,
                                    PEARL_ART_RAD)
from .enums import ItemState
from .terrain import TerrainQuery
from ..behavior.board import board_for
from ..behavior import events as EV
from .slimemold import (SlimeMold, _dirvec as _slime_dir, _lerp_map as _slime_lerp_map,
                        TENDRIL_JAG_K)
from .stone import Stone
from .batfly import BatFly
from .lizard import BREEDS, Lizard, pick_breed, _ang_lerp, lizard_rel, lizard_rel_kind
from .scavenger import separate as separate_scavengers
from .lizard_gfx import draw_lizard
from .squidcada import Squidcada
from .squidcada_gfx import draw_squidcada
from .needleworm import NeedleWorm, AGE_EGG, AGE_SMALL, AGE_BIG
from .needlethread import NeedleThread
from .needleworm_gfx import draw_needleworm, draw_needle_egg
from .pearl import Pearl
from . import weaponphys
from .scavenger import PEARL_SEEK_R, PEARL_TAKE_PAD
from . import hitgeom as HG
from .spear import (Spear, LEN as SPEAR_DRAW_LEN, HALF_W as SPEAR_HALF_W,
                    NEEDLE_FADE_MAX)
from .seedcob import Seed, SeedCob, draw_seed, draw_seedcob
from .karmaflower import (KarmaFlower, DRAG_POP_DIST as KARMA_DRAG_POP,
                         draw_karmaflower)
from .scavenger import (Scavenger, BODY_RAD as SCAV_BODY_RAD,
                        STAND_H as SCAV_STAND_H)
from .pole import POLE_RAD, MIN_LENGTH as POLE_MIN_LENGTH, TOP_MARGIN as POLE_TOP_MARGIN
from ..behavior import tuning
from ..rendering.pixelmode import aa_hint, pen_width


CORPSE_OUT_MARGIN = 14.0     # 尸体整个离开窗口这么多＝被扔出屏幕，直接清除
ERASE_PICK_PAD = 6.0         # 删除模式命中放宽（与拖拽的 GRAB_PAD 同量级）
LAMP_PICK_R = 12.0           # 灯笼按灯泡心算命中半径
PUP_PICK_R = 14.0            # 猫崽在删除模式下的命中半径（约成年的一半）

STALK_ROOT_W = 3.0
STALK_TIP_W = 2.0
STALK_COLOR = (0, 0, 0)
FRUIT_FLESH = (0, 0, 255)
FRUIT_OUTLINE = (0, 0, 0)
STONE_COLOR = (74, 76, 82)
POLE_COLOR = (28, 28, 31)
WALL_MIN_W = 16.0             # 手绘墙矩形的最小宽（拖太窄按它补齐）
WALL_MIN_H = 16.0             # 手绘墙矩形的最小高
WALL_COLOR = (104, 108, 102)  # 手绘墙填充（灰石调，和庇护所墙体同色系）
# 暖灯颜色
LAMP_STICK_COLOR = (0, 0, 0)
LAMP_BULB_FLESH = (255, 255, 255)
LAMP_BULB_OUTLINE = (255, 51, 0)
LAMP_GLOW_COLOR = (255, 51, 0)
LAMP_GLOW_ALPHA = 130
# 蜥蜴之间的关系表现在 lizard.py 的 LIZ_REL / LIZ_BASE_REL（照抄 StaticWorld.cs:3668-3726），
# 由 _lizard_relations 分组后喂给 Lizard.step。
LAMP_TILT_MAX_DEG = 25.0
LAMP_STICK_OUTSET = 40.0
STONE_STUN_SPEED = 8.0
STONE_STUN_TICKS = 80
STUN_SCALE = 3.0                  # 桌面尺度：原版 stun 帧数偏短，整体放长一点
LIZARD_STUN_TICKS = 60            # 被蜥蜴咬到的眩晕 tick（兜底）
# 原版 Lizard.Bite 对 Player 调用 Violence(Bite, 1.5f, 0f)：
#   num  = 1.5 / baseDamageResistance(1) = 1.5 ≥ instantDeathDamageLimit(1) ⇒ 必死
#   num2 = (1.5*30 + 0) / baseStunResistance(1) = 45 ⇒ 未致死时 Stun(45)
BITE_VIOLENCE_DAMAGE = 1.5
# 原版 Player.DeathByBiteMultiplier：僧侣 0、圣徒 100、其余 0.75
PET_BITE_DEATH_MULT = {"monk": 0.0, "saint": 100.0}
PET_BITE_DEATH_MULT_DEFAULT = 0.75
STONE_KNOCKBACK = 0.5
STONE_DRAW_SCALE = 1.0       # 原版 Pebble 贴图 1:1
# 抛石拖尾
STONE_TRAIL_MIN_SPEED = 6.0
STONE_TRAIL_LEN_K = 1.6
STONE_TRAIL_LEN_MAX = 42.0
STONE_TRAIL_HALFW = 3.0
STONE_TRAIL_ALPHA = 90
CURSOR_STUN_PAD = 8.0
CURSOR_STUN_LOCK = 80
# 黏菌颜色
SLIME_HUE_LIGHT = 0.07
SLIME_HUE_DARK = 0.05
SLIME_BODY_L = 0.55
SLIME_OUTLINE_L = 0.25
SLIME_DARK_LO = 0.3
SLIME_DARK_HI = 0.7
SLIME_DRAW_SCALE = 1.0
SLIME_LIGHT_SCALE = 55.0 / 140.0    # 下调防过曝
SLIME_BLOOM_SCALE = 12.0 / 30.0
SLIME_RESTICK_PAD = 50.0
# 触须锯齿单位圆表
_JAG_COS = [math.cos(2.0 * math.pi * i / TENDRIL_JAG_K) for i in range(TENDRIL_JAG_K)]
_JAG_SIN = [math.sin(2.0 * math.pi * i / TENDRIL_JAG_K) for i in range(TENDRIL_JAG_K)]
# 蝙蝠：原版 FlyGraphics 只有 4 片精灵（FlyBody / FlyWing×2 / FlyEyes），没有别的件。
# ApplyPalette（FlyGraphics.cs:207）把 body 与两翅都设成 palette.blackColor，眼睛留白。
BATFLY_BLACK = (0, 0, 0)
BATFLY_EYE_COLOR = (250, 250, 235)
SHOVE_REACH = 22.0
SHOVE_COOLDOWN = 12

# 蝉乌贼 / 珍珠 / 矛 / 拾荒者
SQUIDCADA_GRAB_PAD = 10.0
SQUID_LOOK_R = 320.0          # 蝉乌贼「看谁」的视距（CicadaGraphics.creatureLooker）
NEEDLEWORM_GRAB_PAD = 12.0
# 面条蝇成体的两段攻击（BigNeedleWorm.cs:168 獠牙戳 / :454 突刺）
NW_STAB_DAMAGE = 1.22            # Violence(Stab, 1.22f, 60f) → 1.22 ≥ 蛞蝓猫即死阈值 1
NW_STAB_STUN = 60.0
NW_POKE_DAMAGE = 0.05            # Violence(Stab, 0.05f, 30f)：戳不致命，只晕 + 掉东西
NW_POKE_STUN = 30.0
NW_ATTEMPT_DIST = 120.0          # Weapon.cs:149 closestCritDist < 120f → AttackAttempt
NW_HATCH_GAP = 14.0              # 卵孵出 2 只幼体时左右分开一点
PEARL_GRAB_PAD = 6.0
SPEAR_GRAB_PAD = 8.0
# 玩家用鼠标甩矛：够快就当成原版 Weapon.Thrown 投出去（带伤害、会自然下坠）
SPEAR_PLAYER_THROW_MIN = 9.0     # 松手速度下限（低于此只是放下）
SPEAR_PLAYER_FRC_K = 1.0 / 9.0   # 速度 → frc（0.5..1.0，决定退出投掷的阈值）
SPEAR_PLAYER_POWER_K = 2.0       # 速度 → 出手速度
SPEAR_PLAYER_POWER_MIN = 12.0
SPEAR_PLAYER_POWER_MAX = 44.0
# 飞矛拖尾（同石头那套）
SPEAR_TRAIL_MIN_SPEED = 8.0
SPEAR_TRAIL_LEN_K = 1.5
SPEAR_TRAIL_LEN_MAX = 46.0
SPEAR_TRAIL_HALFW = 1.6
SPEAR_TRAIL_ALPHA = 80
SPEAR_TRAIL_COLOR = (196, 176, 138)   # 木质杆身的拖尾色
SCAVENGER_GRAB_PAD = 14.0
SPEAR_HIT_SPEED = 7.0            # （保留）飞矛最低速度；现按原版只认 Mode.Thrown
SPEAR_HIT_PAD = weaponphys.SPEAR_HIT_PAD
KARMA_HIT_R = 13.0       # 业力花：花瓣最远 13.5，按整个花冠（花头）判命中
SPEAR_COB_PAD = 5.0      # 原版 Weapon.cs:416 thrownBy is Player ⇒ 判定半径 +5f
SPEAR_DMG = 1.0                   # Spear.HitSomething: Violence(Stab, spearDamageBonus=1f, 20f)
SPEAR_STUN_BONUS = 20.0           # 上句里的 stunBonus = 20f
STONE_DMG = 0.01                  # Rock.HitSomething: Violence(Blunt, 0.01f, 45f)
STONE_STUN_BONUS = 45.0           # 上句里的 stunBonus = 45f
# 原版击退：hitChunk.vel += (攻击物 vel * 攻击物 mass * 2) / hitChunk.mass。
# 桌面尺度折算：粉蜥（bodyMass 2.1）挨满速矛（_SPEAR_FLING_CAP=18）时约 1.4 px/tick。
KNOCK_K_PER_MASS = 1.4 * 2.1 / (18.0 * 0.12)
# 拾荒者掷矛初速走原版 Scavenger.ThrowObject → Weapon.Thrown（见 weaponphys）：
#   frc = (Elite || Templar) ? 0.75 : 0.35，初速 = 40 * frc，方向恒为水平


def _slime_body_rgb(dm, l):
    """按 darkMode 算橙系 RGB。"""
    hue = lerp(SLIME_HUE_LIGHT, SLIME_HUE_DARK, dm)
    r, g, b = _hsl2rgb(hue, 1.0, l)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def _slime_saturate(rgb):
    """HSV 满饱和，橙发光用。"""
    mn, mx = min(rgb), max(rgb)
    if mx <= mn:
        return (mx, mx, mx)
    k = mx / (mx - mn)
    return tuple(int(round((c - mn) * k)) for c in rgb)


def _slime_colors(dm):
    """橙系三色：body/outline/glow。"""
    body = _slime_body_rgb(dm, SLIME_BODY_L)
    return body, _slime_body_rgb(dm, SLIME_OUTLINE_L), _slime_saturate(body)


def _slerp2(ax, ay, bx, by, t):
    """两单位向量球面插值。"""
    dot = clampf(ax * bx + ay * by, -1.0, 1.0)
    if dot > 0.9995:                                   # 近平行退化
        return (ax + (bx - ax) * t, ay + (by - ay) * t)
    theta = math.acos(dot)
    s = math.sin(theta)
    return (ax * math.sin((1.0 - t) * theta) / s + bx * math.sin(t * theta) / s,
            ay * math.sin((1.0 - t) * theta) / s + by * math.sin(t * theta) / s)


def _pet_stun_death(damage: float, stun_bonus: float, instant_limit: float = 1.0,
                    dmg_res: float = 1.0, stun_res: float = 1.0):
    """原版 Creature.Violence 对蛞蝓猫模板的结算（Slugcat 抗性 1 / 即死阈值 1）。

    返回 (是否致死, 眩晕 tick)；蛞蝓猫 State 不是 HealthState，所以只走
    num >= instantDeathDamageLimit → Die 与 Stun((int)num2) 两条。
    """
    num = damage / max(1e-6, dmg_res)
    num2 = (damage * 30.0 + stun_bonus) / max(1e-6, stun_res)
    return (num >= instant_limit, int(max(0.0, num2)))


def _pet_bite_death_mult(pet) -> float:
    """原版 Player.DeathByBiteMultiplier（故事模式 0.7 + 难度/5，这里取 0.75）。"""
    return PET_BITE_DEATH_MULT.get(getattr(pet, "variant", None),
                                   PET_BITE_DEATH_MULT_DEFAULT)


# ── 矛大师骨矛吸食（Spear.cs:1041-1087 + Wiki Spearmaster「进食」表）──
# 每口默认 1 格；小生物按表给 0.25 / 0.5。尸体不给（命中前就死了 → flag3）。
NEEDLE_FEED_DEFAULT = 1.0
NEEDLE_FEED_SMALL = 0.5
NEEDLE_FEED_TINY = 0.25
NEEDLE_FEED_COB_CLOSED = 5.0     # 原版 Spear.cs:1102：活针扎中未开荚爆米花 AddFood(5)
NEEDLE_FEED_COB_OPEN = 1.0       # 用户口径：已开荚的再扎只回 1 格


def _needle_feed_amount(obj) -> float:
    """这一口回多少格饱食度（Wiki Spearmaster 表）。

    蝠蝇 0.25；蝉乌贼 / 幼年面条蝇 0.5；其余（蜥蜴 / 拾荒者 / 成体面条蝇 / 同伴）1。
    """
    if isinstance(obj, BatFly):
        return NEEDLE_FEED_TINY
    if isinstance(obj, Squidcada):
        return NEEDLE_FEED_SMALL
    if isinstance(obj, NeedleWorm) and getattr(obj, "age", None) == AGE_SMALL:
        return NEEDLE_FEED_SMALL
    return NEEDLE_FEED_DEFAULT


def _spear_should_protect_pet(sp, victim) -> bool:
    """AI/玩耍用矛的同伴保护：中性或友好关系不允许即死。"""
    owner_body = getattr(sp, "thrower", None)
    if owner_body is None or owner_body is getattr(victim, "body", None):
        return False
    owner_pet = None
    win = getattr(owner_body, "window", None)
    for pet in getattr(win, "pets", ()):
        if getattr(pet, "body", None) is owner_body:
            owner_pet = pet
            break
    if owner_pet is None:
        # 非桌宠投掷者维持原版伤害。
        return False
    beh = getattr(owner_pet, "behavior", None)
    if beh is not None and getattr(beh, "state", None) == "ItemPlay":
        return True
    try:
        from ..behavior.relationship import relations_for
        return relations_for(owner_body).hostility_to(getattr(victim, "body", victim)) < 0.60
    except Exception:
        # 无关系数据时宁可保护同伴，避免误杀。
        return True


def _friendly_throw_protected(win, thrower) -> bool:
    """设置里开了「友军伤害豁免」时：蛞蝓猫投出的矛/石头不伤同伴。

    只有**桌宠**投出的武器被免掉；非桌宠投掷者（拾荒者之类）维持原版结算。
    这只改伤害层，AI 该避让还是避让。
    """
    if not bool(getattr(win, "friendly_fire_protect", False)):
        return False
    if thrower is None:
        return False
    for pet in getattr(win, "pets", ()):
        if getattr(pet, "body", None) is thrower:
            return True
    return False


def _weapon_owner(w):
    """投掷物的掷出者 uid（原版 Weapon.thrownBy；成体面条蝇的 tempLike 记账用）。"""
    owner = getattr(w, "thrower", None)
    return None if owner is None else id(owner)


def _seg_end(ball):
    """本帧扫掠线段终点：插墙/插地会把 x/y 拽回墙内，命中要用真正飞到的位置。

    原版 Weapon.Update 是先逐 chunk 判命中、再 StuckInWall；同帧插墙不该吞掉命中。
    """
    return (getattr(ball, "_seg_x", ball.x), getattr(ball, "_seg_y", ball.y))


def _sweep_circle(ax, ay, bx, by, cx, cy, r):
    """线段 AB 首次穿进圆 (c, r) 的接触点；返回 (t, x, y)，没穿进返回 None。"""
    return HG.sweep_circle(ax, ay, bx, by, cx, cy, r)


def _ball_hit(creature, ball, pad: float = 0.0):
    """扫掠命中生物：返回 (命中的链节, 真实接触点 (x, y), t)；未命中 None。

    全局唯一一套几何（world/hitgeom.py）；AI 预演跑的也是这一个，不再出现
    「AI 说能中、实际插在空气里」。
    """
    return HG.sweep_hit(creature, ball, pad)


def _local_frame(host, px, py, ang_deg):
    """把命中点记成「哪个身体节 + 局部坐标 + 相对角度」。

    只存世界坐标偏移的话，生物弯腰/扭身/甩尾时矛只会跟着平移（像贴上去的）。
    """
    frames = host.stuck_frames()
    best_i, best_d = 0, 1e18
    for i, (fx, fy, _fa) in enumerate(frames):
        d = (fx - px) ** 2 + (fy - py) ** 2
        if d < best_d:
            best_i, best_d = i, d
    fx, fy, fa = frames[best_i]
    th = math.radians(-fa)
    cs, sn = math.cos(th), math.sin(th)
    lx, ly = px - fx, py - fy
    # 转动约定与 tip() 一致：angle=0 向上、顺时针为正、y 向下
    return (host, best_i, fa, lx * cs - ly * sn, lx * sn + ly * cs, (ang_deg - fa) % 360.0)


def _step_stuck_local(sp, sl) -> bool:
    """按「身体节局部坐标」更新插在生物身上的矛；宿主没有这一节时返回 False。"""
    host, idx, fa0, lx, ly, rel = sl
    frames = host.stuck_frames()
    if not (0 <= idx < len(frames)):
        return False
    fx, fy, fa = frames[idx]
    th = math.radians(fa - fa0)
    cs, sn = math.cos(th), math.sin(th)
    sp.last_x, sp.last_y = sp.x, sp.y
    sp.x, sp.y = fx + lx * cs - ly * sn, fy + lx * sn + ly * cs
    sp.last_angle = sp.stuck_angle
    sp.stuck_angle = (rel + fa) % 360.0
    sp.angle_deg = sp.stuck_angle
    return True


def _hit_is_head(creature, x, y, pad: float = 0.0) -> bool:
    """命中点是否落在头节上（原版 hitChunk.index == 0，头有甲、嘴有洞）。"""
    d_head = math.hypot(x - creature.x, y - creature.y) - (creature.head_rad + pad)
    for s in creature.seg:
        if math.hypot(x - s.x, y - s.y) - (s.rad + pad) < d_head:
            return False
    return True


def _cob_hit(cb, sp, pad: float = 0.0):
    """飞矛扫掠线段 vs 爆米花两个 chunk 圆（原版 Weapon.cs:413-416 逐 chunk 判定）。

    返回**真实接触点** (x, y)，未命中 None。走的是全局统一几何；
    AI 预演（fsm._cob_would_hit）调的就是这一个。
    """
    got = HG.sweep_hit(cb, sp, pad)
    return None if got is None else got[1]


def _small_hit(small, sp, pad: float = 0.0):
    """小生物（蝠蝇/蝉乌贼/面条蝇）扫掠命中：返回 (命中点, 真实接触点, t)。

    旧实现没链节的那一支直接返回**这一帧的终点**当命中点，
    鉴于飞行距离每帧四十像素，那个点常常已经在虫子身后了。现在统一走扫掠交点。
    """
    return HG.sweep_hit(small, sp, pad)


def _seg_dist(ax, ay, bx, by, x, y) -> float:
    """点 (x,y) 到线段 AB 的最短距离。投掷物 40px/帧，逐帧位置判定会穿过链节。"""
    return HG.seg_dist(ax, ay, bx, by, x, y)


def _dist_to_path(pts, x, y):
    """点到折线的最短距离（蜥蜴抓取判定用）。"""
    best = 1e9
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 <= 1e-9 else clampf(((x - ax) * dx + (y - ay) * dy) / L2, 0.0, 1.0)
        d = math.hypot(x - (ax + dx * t), y - (ay + dy * t))
        if d < best:
            best = d
    return best


class ItemInteractionMixin:
    # 个数上限已全部取消，can_place_* 恒真（保留接口供 UI 调用）
    _FRUIT_GRAB_PAD = 7.0
    _FRUIT_FLING_CAP = 14.0
    _STONE_GRAB_PAD = 7.0
    _STONE_FLING_CAP = 14.0
    _SLIME_GRAB_PAD = 7.0
    _SLIME_FLING_CAP = 14.0
    _BATFLY_GRAB_PAD = 7.0
    _BATFLY_FLING_CAP = 14.0
    _LIZARD_GRAB_PAD = 10.0
    _LIZARD_FLING_CAP = 14.0
    _PEARL_FLING_CAP = 16.0
    _SPEAR_FLING_CAP = 18.0
    _SEEDCOB_GRAB_PAD = 14.0
    _KARMAFLOWER_GRAB_PAD = 9.0
    # 钉在光标上的矛（猎手怪癖）：命中判定半径 / 甩鼠标脱钉的每 tick 光标位移
    CURSOR_PIN_R = 14.0
    CURSOR_PIN_SLIP_V = 40.0

    def can_place_fruit(self) -> bool:
        return True

    def place_fruit(self, lx, ly):
        if not self.can_place_fruit():
            return None
        f = make_fruit(lx, ly, self._HL, seed=self._fruit_seed, zerog=self.zerog_on)
        self._fruit_seed += 1
        self.fruits.append(f)
        self.world_version += 1
        self._exit_place_mode()
        return f

    def clear_fruits(self):
        for f in self.fruits:
            f.stalk = None
            if f.state == ItemState.CARRIED:
                f.held_by_hand = None
            for pet in self.pets:
                if f is pet.body.carried_fruit:
                    pet.body.release_fruit()
            f.state = ItemState.EATEN
        if self.fruits:
            self.fruits = []
            self.world_version += 1
        self._dragged_fruit = None
        self._drag_last = None
        self._exit_place_mode()

    def _fruit_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for f in self.fruits:
            if f.state not in (ItemState.FREE, ItemState.HANGING):
                continue
            d = math.hypot(cx - f.x, cy - f.y)
            if d <= f.rad + self._FRUIT_GRAB_PAD and d < bestd:
                best, bestd = f, d
        return best

    def _begin_fruit_drag(self, pos) -> bool:
        f = self._fruit_at(pos)
        if f is None:
            return False
        f.stalk = None
        f.held_by_hand = None
        f.state = ItemState.MOUSE
        f.vx = f.vy = 0.0
        f.last_x, f.last_y = pos
        f.x, f.y = pos
        self._dragged_fruit = f
        self._drag_last = tuple(pos)
        return True

    def _step_fruit_drag(self):
        f = self._dragged_fruit
        if f is None:
            return
        if f.state != ItemState.MOUSE:
            self._dragged_fruit = None
            self._drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        f.last_x, f.last_y = f.x, f.y
        if self._drag_last is not None:
            f.vx = cur[0] - self._drag_last[0]
            f.vy = cur[1] - self._drag_last[1]
        f.x, f.y = cur
        self._drag_last = tuple(cur)

    def _end_fruit_drag(self):
        f = self._dragged_fruit
        if f is None:
            return False
        sp = math.hypot(f.vx, f.vy)
        if sp > self._FRUIT_FLING_CAP:
            k = self._FRUIT_FLING_CAP / sp
            f.vx *= k
            f.vy *= k
        if f.state == ItemState.MOUSE:
            f.state = ItemState.FREE
        self._dragged_fruit = None
        self._drag_last = None
        return True

    def can_place_stone(self) -> bool:
        return True

    def place_stone(self, lx, ly):
        if not self.can_place_stone():
            return None
        s = Stone(lx, ly, seed=self._stone_seed)
        self._stone_seed += 1
        self.stones.append(s)
        self.world_version += 1
        self._exit_place_mode()
        return s

    def clear_stones(self):
        for s in self.stones:
            for pet in self.pets:
                if s is getattr(pet.body, "carried_stone", None):
                    rs = getattr(pet.body, "release_stone", None)
                    if rs is not None:
                        rs()
            s.state = ItemState.GONE
        if self.stones:
            self.stones = []
            self.world_version += 1
        self._dragged_stone = None
        self._stone_drag_last = None
        self._exit_place_mode()

    def enter_place_stone_mode(self):
        if not self.can_place_stone():
            return False
        self._place_mode = True
        self._place_kind = "stone"
        self._begin_place_capture()
        return True

    def _stone_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for s in self.stones:
            if s.state != ItemState.FREE:
                continue
            d = math.hypot(cx - s.x, cy - s.y)
            if d <= s.rad + self._STONE_GRAB_PAD and d < bestd:
                best, bestd = s, d
        return best

    def _begin_stone_drag(self, pos) -> bool:
        f = self._stone_at(pos)
        if f is None:
            return False
        f.unfetchable = False
        f.fetch_fails = 0
        f.fling = False
        f.state = ItemState.MOUSE
        f.vx = f.vy = 0.0
        f.last_x, f.last_y = pos
        f.x, f.y = pos
        self._dragged_stone = f
        self._stone_drag_last = tuple(pos)
        return True

    def _step_stone_drag(self):
        f = self._dragged_stone
        if f is None:
            return
        if f.state != ItemState.MOUSE:
            self._dragged_stone = None
            self._stone_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        f.last_x, f.last_y = f.x, f.y
        if self._stone_drag_last is not None:
            f.vx = cur[0] - self._stone_drag_last[0]
            f.vy = cur[1] - self._stone_drag_last[1]
        f.x, f.y = cur
        self._stone_drag_last = tuple(cur)

    def _end_stone_drag(self):
        f = self._dragged_stone
        if f is None:
            return False
        sp = math.hypot(f.vx, f.vy)
        if sp > self._STONE_FLING_CAP:
            k = self._STONE_FLING_CAP / sp
            f.vx *= k
            f.vy *= k
        if f.state == ItemState.MOUSE:
            f.state = ItemState.FREE
            f.fling = True
            f.spin = clampf(f.vx * 2.0, -40.0, 40.0) * lerp(0.05, 1.0, f.room_gravity)
        self._dragged_stone = None
        self._stone_drag_last = None
        return True

    def _step_stone_hit(self):
        for pet in self.pets:
            if pet.behavior is None:
                continue
            b = pet.body
            for s in self.stones:
                if not s.fling or s.state != ItemState.FREE:
                    continue
                if s.thrower is b and s.no_self_t > 0:        # 刚出手，别砸自己
                    continue
                sp = math.hypot(s.vx, s.vy)
                if sp < STONE_STUN_SPEED:
                    continue
                for c in (b.chunk0, b.chunk1):
                    if _seg_dist(s.last_x, s.last_y, s.x, s.y,
                                 c.x, c.y) < s.rad + c.rad:
                        if _friendly_throw_protected(self, getattr(s, "thrower", None)):
                            # 友军伤害豁免：不眩晕也不击退，石头自己弹开。
                            s.deflect(self._stun_rng)
                            s.fling = False
                        elif pet.behavior.apply_stun(int(STONE_STUN_TICKS * STUN_SCALE)):
                            self._friendly_fire(getattr(s, "thrower", None), pet)
                            c.vx += s.vx * STONE_KNOCKBACK
                            c.vy += s.vy * STONE_KNOCKBACK
                            s.deflect(self._stun_rng)
                            s.fling = False
                        break
            for lz in self.lizards:
                if lz.dead or not s.fling or s.state != ItemState.FREE:
                    continue
                if math.hypot(s.vx, s.vy) < STONE_STUN_SPEED:
                    continue
                hit = _ball_hit(lz, s, 2.0)
                if hit is None:
                    continue
                hit_chunk, (hit_x, hit_y), _hit_t = hit
                spd = math.hypot(s.vx, s.vy) or 1.0
                dvec = (s.vx / spd, s.vy / spd)
                killed = lz.hurt(STONE_DMG, dvec=dvec, speed=spd,
                                 stun_bonus=STONE_STUN_BONUS,
                                 hit_head=(hit_chunk is lz),      # 头是第 0 节
                                 knock_k=KNOCK_K_PER_MASS * s.mass)
                if not killed and lz.breed.flips_from_rock:
                    # 原版 Lizard.Violence：source is Rock 且非红蜥 → turnedByRockCounter = 20
                    lz.rock_push = 20
                    lz.rock_push_dir = 1 if s.vx >= 0.0 else -1
                s.deflect(self._stun_rng)
                s.fling = False
                self._shake[0] += 0.5 * (1.0 if s.vx >= 0.0 else -1.0)
                if killed:
                    self._lizard_death_fx(lz)
                EV.emit_for(self, EV.CREATURE_KILLED if killed else EV.CREATURE_HURT,
                            subject=_weapon_owner(s), obj=lz,
                            intensity=1.0 if killed else 0.55,
                            x=hit_x, y=hit_y)
                break
            for sc in self.scavengers:
                if sc.dead or not s.fling or s.state != ItemState.FREE:
                    continue
                if math.hypot(s.vx, s.vy) < STONE_STUN_SPEED:
                    continue
                if _seg_dist(s.last_x, s.last_y, s.x, s.y, sc.x, sc.y) >= s.rad + sc.rad:
                    continue
                _sc_died = sc.hurt(STONE_DMG)
                if _weapon_owner(s) is not None:
                    sc.on_attacked(0.5)
                EV.emit_for(self,
                            EV.CREATURE_KILLED if _sc_died else EV.CREATURE_HURT,
                            subject=_weapon_owner(s), obj=sc,
                            intensity=1.0 if _sc_died else 0.5,
                            x=s.x, y=s.y)
                s.deflect(self._stun_rng)
                s.fling = False
                self._shake[1] += 0.3
                break
            for small in (*self.batflies, *self.squidcadas,
                          *self.needleworms):   # 砸中就打下来
                if small.dead or not s.fling or s.state != ItemState.FREE:
                    continue
                if math.hypot(s.vx, s.vy) < STONE_STUN_SPEED:
                    continue
                if math.hypot(s.x - small.x, s.y - small.y) >= s.rad + small.rad:
                    continue
                small.hurt(STONE_DMG, kx=s.vx * 0.10,
                           ky=min(s.vy * 0.10 - 1.0, -1.0),
                           by=_weapon_owner(s), lethal=False)
                s.deflect(self._stun_rng)
                s.fling = False
                break

    def _step_stone_cursor_hit(self):
        if self.cursor_hijack is not None or self.behavior is None:
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        for s in self.stones:
            if not s.thrown_by_saint or s.state != ItemState.FREE:
                continue
            if math.hypot(s.x - cx, s.y - cy) < s.rad + CURSOR_STUN_PAD:
                self.start_cursor_hijack(cx, cy, lock_ticks=CURSOR_STUN_LOCK)
                s.deflect(self._stun_rng)
                s.thrown_by_saint = False
                break

    # ── 杆子 ──
    def can_place_pole(self, kind) -> bool:
        return True

    def place_pole(self, lx, ly, place_kind):
        from .pole import Pole, VERTICAL, HORIZONTAL, MIN_LENGTH, TOP_MARGIN
        kind = VERTICAL if place_kind == "vpole" else HORIZONTAL
        if not self.can_place_pole(kind):
            return None
        if kind == VERTICAL:
            top = min(max(ly, TOP_MARGIN), self._HL - MIN_LENGTH)
            pl = Pole(VERTICAL, lx, self._HL, lx, top, seed=self._pole_seed)
        else:
            ax = 0.0 if lx < self._WL * 0.5 else self._WL
            end = lx
            if abs(end - ax) < MIN_LENGTH:
                end = ax + (MIN_LENGTH if ax == 0.0 else -MIN_LENGTH)
            pl = Pole(HORIZONTAL, ax, ly, end, ly, seed=self._pole_seed)
        self._pole_seed += 1
        self.poles.append(pl)
        self.world_version += 1
        self.geometry_version += 1
        self._exit_place_mode()
        self.update()
        return pl

    def clear_poles(self):
        from .enums import ItemState as _IS
        for sp in self.spears:            # 矛钉成的杆一并清掉，矛本身回到可拾取
            if sp.pinned:
                sp.enter_free(roll=False)
            sp.pole = None
        for pl in self.poles:
            pl.state = _IS.GONE
        if self.poles:
            self.poles = []
            self.world_version += 1
            self.geometry_version += 1
        self._exit_place_mode()
        self.update()

    def clear_all_items(self, clear_pups=False):
        """清除所有可交互实体。

        clear_pups=True 时连幼崽一起清（「清除可交互实体」按钮）；转生调的是默认值，
        幼崽和成年猫一样整体复活，不该在换雨循环时消失。
        """
        self.clear_fruits()
        self.clear_stones()
        self.clear_slimemolds()
        self.clear_batflies()
        self.clear_lizards()
        self.clear_squidcadas()
        self.clear_needleworms()
        self.clear_pearls()
        self.clear_spears()
        self.clear_scavengers()
        self.clear_seedcobs()
        self.clear_seeds()
        self.clear_karmaflowers()
        self.clear_poles()
        self.clear_walls()
        self.clear_lamp()
        if clear_pups:
            self.clear_pups()

    def clear_world_for_reincarnation(self):
        """全体转生：全体复活那一瞬把场上所有东西一起清空（原版换雨循环＝整房间重置）。

        除了可交互实体，还要清掉「死后原地长业力花」的排期 —— 转生是新循环，
        上一轮尸体的花不该再冒出来。
        """
        self.clear_all_items()
        if getattr(self, "_karma_flower_spawns", None):
            self._karma_flower_spawns = []
        self._dragged_spear = None
        self._spear_drag_last = None

    def enter_place_vpole_mode(self):
        return self.enter_place_pole_mode()

    def enter_place_hpole_mode(self):
        return self.enter_place_pole_mode()

    def enter_place_pole_mode(self):
        """横杆 / 竖杆合并成一个入口（用户口径）：拉一条直线决定这根杆 ——
        横着拉＝横杆，竖着拉＝竖杆；拉动只决定长度与起终点，粗细恒为 POLE_RAD，
        根部不再写死在屏幕边上。"""
        if not self.can_place_pole("pole"):
            return False
        self._place_mode = True
        self._place_kind = "pole"
        self._pole_drag_start = None
        self._begin_place_capture()
        return True

    def _begin_pole_place(self, lx, ly):
        self._pole_drag_start = (lx, ly)

    def _finish_pole_place(self, cur=None):
        if not self._place_mode or self._place_kind not in ("vpole", "hpole", "pole"):
            return None
        st = getattr(self, "_pole_drag_start", None)
        self._pole_drag_start = None
        if st is None:
            return None
        if cur is None:
            cur = self.cursor_logical()
        if cur is None:
            self._exit_place_mode()
            return None
        return self.place_pole_line(st[0], st[1], cur[0], cur[1])

    def place_pole_line(self, x0, y0, x1, y1):
        """按一条线段放杆：|dx| >= |dy| 是横杆，否则是竖杆。

        与旧 place_pole 的区别：起终点就是杆的两端（根部可以是半空），
        长度＝拉出来的距离（不足 MIN_LENGTH 时按方向补到最短）。
        """
        from .pole import Pole, VERTICAL, HORIZONTAL, MIN_LENGTH
        dx, dy = float(x1) - float(x0), float(y1) - float(y0)
        if abs(dx) >= abs(dy):
            kind, y1 = HORIZONTAL, float(y0)
            if abs(dx) < MIN_LENGTH:
                x1 = float(x0) + (MIN_LENGTH if dx >= 0 else -MIN_LENGTH)
        else:
            kind, x1 = VERTICAL, float(x0)
            if abs(dy) < MIN_LENGTH:
                y1 = float(y0) + (MIN_LENGTH if dy >= 0 else -MIN_LENGTH)
        if not self.can_place_pole(kind):
            return None
        x0 = clampf(float(x0), 0.0, self._WL)
        x1 = clampf(float(x1), 0.0, self._WL)
        y0 = clampf(float(y0), 0.0, self._HL)
        y1 = clampf(float(y1), 0.0, self._HL)
        pl = Pole(kind, x0, y0, x1, y1, seed=self._pole_seed)
        self._pole_seed += 1
        self.poles.append(pl)
        self.world_version += 1
        self.geometry_version += 1
        self._exit_place_mode()
        self.update()
        return pl

    def enter_place_wall_mode(self):
        """手绘墙壁入口（用户口径：画一个实心矩形，像庇护所但是实心的）。

        和放庇护所同一套交互：按下定一角 → 拖出矩形 → 松开成墙。整块都是实体，
        进物理层的 solids 表（见 window._refresh_shelter_solids），所以生物 /
        物品 / 猫都撞得到、挡视线，navgeom 还会把左右竖边当可爬墙面、顶面当可站面。
        """
        self._place_mode = True
        self._place_kind = "wall"
        self._wall_drag_start = None
        self._begin_place_capture()
        return True

    def _begin_wall_place(self, lx, ly):
        self._wall_drag_start = (lx, ly)

    def _wall_drag_rect(self):
        """当前拖出来的预览墙矩形（和庇护所一样是任意矩形，不贴地）。"""
        cur = self.cursor_logical()
        if cur is None:
            return None
        st = getattr(self, "_wall_drag_start", None)
        if st is None:
            # 还没按下：光标处给一个默认大小的方块
            w = max(WALL_MIN_W, 90.0)
            h = max(WALL_MIN_H, 90.0)
            x0, y0 = cur[0] - w * 0.5, cur[1] - h * 0.5
        else:
            x0, y0 = min(st[0], cur[0]), min(st[1], cur[1])
            w, h = abs(cur[0] - st[0]), abs(cur[1] - st[1])
            w, h = max(w, WALL_MIN_W), max(h, WALL_MIN_H)
        x0 = clampf(x0, 0.0, max(0.0, self._WL - w))
        y0 = clampf(y0, 0.0, max(0.0, self._HL - h))
        return (x0, y0, min(self._WL, x0 + w), min(self._HL, y0 + h))

    def _finish_wall_place(self, cur=None):
        if not self._place_mode or self._place_kind != "wall":
            return None
        st = getattr(self, "_wall_drag_start", None)
        self._wall_drag_start = None
        if st is None:
            # 没有「按下」就没有框选出来的矩形：忽略这次松开、留在放置模式
            # （和放庇护所同一条规则，工具栏按钮那一下的松开会漏进来）。
            return None
        if cur is None:
            cur = self.cursor_logical()
        if cur is None:
            self._exit_place_mode()
            return None
        return self.place_wall_rect(st[0], st[1], cur[0], cur[1])

    def place_wall_rect(self, x0, y0, x1, y1):
        """按一个矩形放一块实心墙（用户口径：像庇护所但是实心）。

        整块都是实体 —— 进 solids 表（见 window._refresh_shelter_solids），
        生物 / 物品 / 猫都撞得到、挡视线；navgeom 把左右竖边当可爬墙面、
        顶面当可站面。拖出来的两个角随便哪个是起点都行。
        """
        ax, bx = sorted((clampf(float(x0), 0.0, self._WL),
                         clampf(float(x1), 0.0, self._WL)))
        ay, by = sorted((clampf(float(y0), 0.0, self._HL),
                         clampf(float(y1), 0.0, self._HL)))
        if bx - ax < WALL_MIN_W:              # 拖太窄：就地补齐，别放出一根线
            bx = min(self._WL, ax + WALL_MIN_W)
            ax = max(0.0, bx - WALL_MIN_W)
        if by - ay < WALL_MIN_H:
            by = min(self._HL, ay + WALL_MIN_H)
            ay = max(0.0, by - WALL_MIN_H)
        rect = (ax, ay, bx, by)
        walls = getattr(self, "extra_walls", None)
        if walls is None:
            walls = self.extra_walls = []
        walls.append(rect)
        refresh = getattr(self, "_refresh_shelter_solids", None)
        if refresh is not None:
            refresh()
        self.world_version += 1
        self.geometry_version += 1
        self._exit_place_mode()
        self.update()
        return rect

    def _draw_walls(self, p):
        """手绘墙块：灰石实心矩形 + 略深的描边（和庇护所墙体同色系）。"""
        from PySide6.QtCore import QRectF
        edge = QColor(max(0, WALL_COLOR[0] - 40), max(0, WALL_COLOR[1] - 40),
                      max(0, WALL_COLOR[2] - 38))
        p.save()
        p.setBrush(QColor(*WALL_COLOR))
        for (x0, y0, x1, y1) in (getattr(self, "extra_walls", None) or ()):
            rc = QRectF(x0, y0, x1 - x0, y1 - y0)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(rc)
            p.setPen(QPen(edge, pen_width(2.0)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(rc)
            p.setBrush(QColor(*WALL_COLOR))
        p.restore()

    def _draw_wall_hint(self, p):
        """放墙预览：和庇护所一样拖出实心矩形（松手就落成同尺寸的墙块）。"""
        from PySide6.QtCore import QRectF
        rc = self._wall_drag_rect()
        if rc is None:
            return
        x0, y0, x1, y1 = rc
        if x1 - x0 <= 0.0 or y1 - y0 <= 0.0:
            return
        p.save()
        p.setOpacity(0.55)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*WALL_COLOR))
        p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        p.restore()

    def clear_walls(self):
        """清掉手绘墙（和杆子一起在「清除可交互实体」里收掉）。"""
        if getattr(self, "extra_walls", None):
            self.extra_walls = []
            refresh = getattr(self, "_refresh_shelter_solids", None)
            if refresh is not None:
                refresh()
            self.world_version += 1
            self.geometry_version += 1
            self.update()

    def _draw_poles(self, p):
        p.save()
        for pl in self.poles:
            if getattr(pl, "virtual", False):
                continue        # 光标那截：看不见，只是给猫爬的
            if getattr(pl, "from_spear", None) is not None:
                continue        # 插住的矛自己成杆：由矛贴图（_draw_spears）画，别再叠一根杆
            self._draw_pole_rod(p, pl.ax, pl.ay, pl.bx, pl.by, POLE_RAD)
        p.restore()

    def _draw_pole_rod(self, p, ax, ay, bx, by, rad):
        """单层均一色杆体，无描边。"""
        core = QPen(QColor(*POLE_COLOR))
        core.setWidthF(pen_width(rad * 2.0))
        core.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(core)
        p.drawLine(QPointF(ax, ay), QPointF(bx, by))

    def _draw_pole_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        st = getattr(self, "_pole_drag_start", None)
        if st is None:
            # 还没按下：光标处点一小段，示意「从这里拉出一根杆」
            a = QPointF(cx, cy - POLE_MIN_LENGTH * 0.5)
            b = QPointF(cx, cy + POLE_MIN_LENGTH * 0.5)
        else:
            sx, sy = st
            if abs(cx - sx) >= abs(cy - sy):     # 横着拉：横杆
                a = QPointF(sx, sy)
                b = QPointF(cx, sy)
            else:                                 # 竖着拉：竖杆
                a = QPointF(sx, sy)
                b = QPointF(sx, cy)
        p.save()
        p.setOpacity(0.5)
        self._draw_pole_rod(p, a.x(), a.y(), b.x(), b.y(), POLE_RAD)
        p.restore()

    # ── 暖灯 ──
    def _lamp_geom(self, lx, ly):
        """点击点 → 最近边算锚点/灯泡位置/边名。"""
        d = {"top": ly, "bottom": self._HL - ly, "left": lx, "right": self._WL - lx}
        edge = min(d, key=d.get)
        perp = d[edge]                                      # 垂距
        off = perp * math.tan(math.radians(getattr(self, "_lamp_tilt", 0.0)))
        if edge == "top":
            ax, ay = clampf(lx + off, 0.0, self._WL), 0.0
        elif edge == "bottom":
            ax, ay = clampf(lx + off, 0.0, self._WL), self._HL
        elif edge == "left":
            ax, ay = 0.0, clampf(ly + off, 0.0, self._HL)
        else:
            ax, ay = self._WL, clampf(ly + off, 0.0, self._HL)
        vx, vy = ax - lx, ay - ly
        vlen = math.hypot(vx, vy) or 1.0
        ax += vx / vlen * LAMP_STICK_OUTSET
        ay += vy / vlen * LAMP_STICK_OUTSET
        return ax, ay, lx, ly, edge

    def place_lamp(self, lx, ly):
        from .lamp import Lamp
        ax, ay, bx, by, edge = self._lamp_geom(lx, ly)
        if self.lamp is not None:
            self.lamp.state = ItemState.GONE
        self.lamp = Lamp(ax, ay, bx, by, edge, seed=self._lamp_seed)
        self._lamp_seed += 1
        self.world_version += 1
        self.geometry_version += 1
        self._exit_place_mode()
        self.update()
        return self.lamp

    def clear_lamp(self):
        if self.lamp is not None:
            self.lamp.state = ItemState.GONE
            self.lamp = None
            self.world_version += 1
            self.geometry_version += 1
        self._exit_place_mode()
        self.update()

    def enter_place_lamp_mode(self):
        self._place_mode = True
        self._place_kind = "lamp"
        self._lamp_tilt = random.uniform(-LAMP_TILT_MAX_DEG, LAMP_TILT_MAX_DEG)
        self._begin_place_capture()
        return True

    def _draw_lamp_shape(self, p, ax, ay, bx, by, opacity, glow_radius=None):
        """串杆+灯泡+可选暖光。"""
        p.save()
        if opacity < 1.0:
            p.setOpacity(opacity)
        dx, dy = bx - ax, by - ay
        seg_len = math.hypot(dx, dy)
        bulb_rot = 0.0
        if seg_len > 1.0:
            ux, uy = dx / seg_len, dy / seg_len
            root_w = 1.0 + min(seg_len / 190.0, 3.0)
            sx, sy = ax + ux * 5.0, ay + uy * 5.0
            tx, ty = bx + ux * 25.0, by + uy * 25.0
            n = 8
            pts = [(sx + (tx - sx) * i / (n - 1), sy + (ty - sy) * i / (n - 1))
                   for i in range(n)]
            widths = [2.0 * (root_w + (0.5 - root_w) * (i / (n - 1))) for i in range(n)]
            draw_rope(p, pts, widths, color=LAMP_STICK_COLOR)
            bulb_rot = math.degrees(math.atan2(ax - bx, by - ay))
        draw_fruit(p, self.atlas, bx, by, bulb_rot, 3,
                   flesh_color=LAMP_BULB_FLESH, outline_color=LAMP_BULB_OUTLINE,
                   scalex=0.8, scaley=0.9)
        if glow_radius and glow_radius > 1.0:
            grad = QRadialGradient(QPointF(bx, by), glow_radius)
            grad.setColorAt(0.0, QColor(*LAMP_GLOW_COLOR, LAMP_GLOW_ALPHA))
            grad.setColorAt(1.0, QColor(*LAMP_GLOW_COLOR, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(bx, by), glow_radius, glow_radius)
        p.restore()

    def _draw_lamp(self, p):
        lamp = self.lamp
        if lamp is None:
            return
        self._draw_lamp_shape(p, lamp.anchor_x, lamp.anchor_y, lamp.bulb_x, lamp.bulb_y,
                              1.0, glow_radius=lamp.glow_radius())

    def _draw_lamp_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        ax, ay, bx, by, _ = self._lamp_geom(cx, cy)
        self._draw_lamp_shape(p, ax, ay, bx, by, 0.5, glow_radius=None)

    # ── 黏菌 ──
    def can_place_slimemold(self) -> bool:
        return True

    def _slime_edge_anchor(self, lx, ly):
        """点击点 → 最近边锚点+本体位。"""
        d = {"top": ly, "bottom": self._HL - ly, "left": lx, "right": self._WL - lx}
        edge = min(d, key=d.get)
        if edge == "top":
            sx, sy, nx, ny = clampf(lx, 0.0, self._WL), 0.0, 0.0, 1.0
        elif edge == "bottom":
            sx, sy, nx, ny = clampf(lx, 0.0, self._WL), self._HL, 0.0, -1.0
        elif edge == "left":
            sx, sy, nx, ny = 0.0, clampf(ly, 0.0, self._HL), 1.0, 0.0
        else:
            sx, sy, nx, ny = self._WL, clampf(ly, 0.0, self._HL), -1.0, 0.0
        from .slimemold import STUCK_GAP
        return sx, sy, sx + nx * STUCK_GAP, sy + ny * STUCK_GAP

    def place_slimemold(self, lx, ly):
        if not self.can_place_slimemold():
            return None
        sx, sy, bx, by = self._slime_edge_anchor(lx, ly)
        m = SlimeMold(bx, by, seed=self._slimemold_seed)
        m.stick_to(sx, sy)
        self._slimemold_seed += 1
        self.slimemolds.append(m)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return m

    def clear_slimemolds(self):
        for m in self.slimemolds:
            for pet in self.pets:
                if m is pet.body.carried_fruit:      # 复用果子叼持槽
                    pet.body.release_fruit()
            m.state = ItemState.EATEN
        if self.slimemolds:
            self.slimemolds = []
            self.world_version += 1
        self._dragged_slimemold = None
        self._slime_drag_last = None
        self._exit_place_mode()

    def enter_place_slimemold_mode(self):
        if not self.can_place_slimemold():
            return False
        self._place_mode = True
        self._place_kind = "slimemold"
        self._slime_preview = SlimeMold(0.0, 0.0, seed=self._slimemold_seed)   # 预览用真实实例
        self._begin_place_capture()
        return True

    def _slimemold_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for m in self.slimemolds:
            if m.state not in (ItemState.FREE, ItemState.HANGING):
                continue
            d = math.hypot(cx - m.x, cy - m.y)
            if d <= m.rad + self._SLIME_GRAB_PAD and d < bestd:
                best, bestd = m, d
        return best

    def _begin_slimemold_drag(self, pos) -> bool:
        m = self._slimemold_at(pos)
        if m is None:
            return False
        m.stuck_pos = None
        m.held_by_hand = None
        m.state = ItemState.MOUSE
        m.vx = m.vy = 0.0
        m.last_x, m.last_y = pos
        m.x, m.y = pos                       # 触须由 step 弹簧跟随
        self._dragged_slimemold = m
        self._slime_drag_last = tuple(pos)
        return True

    def _step_slimemold_drag(self):
        m = self._dragged_slimemold
        if m is None:
            return
        if m.state != ItemState.MOUSE:
            self._dragged_slimemold = None
            self._slime_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        m.last_x, m.last_y = m.x, m.y
        if self._slime_drag_last is not None:
            m.vx = cur[0] - self._slime_drag_last[0]
            m.vy = cur[1] - self._slime_drag_last[1]
        m.x, m.y = cur                        # 触须由 step 弹簧跟随
        self._slime_drag_last = tuple(cur)

    def _end_slimemold_drag(self):
        m = self._dragged_slimemold
        if m is None:
            return False
        sp = math.hypot(m.vx, m.vy)
        if sp > self._SLIME_FLING_CAP:
            k = self._SLIME_FLING_CAP / sp
            m.vx *= k
            m.vy *= k
        if m.state == ItemState.MOUSE:
            # 够近重粘边，否则落地
            d = {"top": m.y, "left": m.x, "right": self._WL - m.x}
            edge = min(d, key=d.get)
            if d[edge] <= SLIME_RESTICK_PAD:
                sx, sy, _, _ = self._slime_edge_anchor(m.x, m.y)
                m.vx = m.vy = 0.0
                m.stick_to(sx, sy)
            else:
                m.state = ItemState.FREE
        self._dragged_slimemold = None
        self._slime_drag_last = None
        return True

    def _draw_slimemolds(self, p):
        dm = clampf(inv_lerp(SLIME_DARK_LO, SLIME_DARK_HI,
                             getattr(self, "cold_cycle_prog", 0.0)), 0.0, 1.0)
        for m in self.slimemolds:
            self._draw_one_slimemold(p, m, dm)

    def _draw_one_slimemold(self, p, m, dm):
        """单坨黏菌绘制，正式/预览共用。"""
        ts = self._ts
        atlas = self.atlas
        body, outline, glow = _slime_colors(dm)
        x = m.last_x + (m.x - m.last_x) * ts
        y = m.last_y + (m.y - m.last_y) * ts
        vx, vy = _slerp2(m.last_rotation[0], m.last_rotation[1],
                         m.rotation[0], m.rotation[1], ts)
        rot_deg = _ang_from_up(vx, vy) + 180.0
        draw_fruit(p, atlas, x, y, rot_deg, m.bites,
                   flesh_color=body, outline_color=outline,
                   scalex=SLIME_DRAW_SCALE, scaley=SLIME_DRAW_SCALE * 0.85)
        # EATEN 外都画触须
        if m.state != ItemState.EATEN:
            self._draw_slime_tendrils(p, m, body)
        # 高光
        hox = (-2.0 * (1.0 - dm) + vx * (1.0 + dm)) * SLIME_DRAW_SCALE
        hoy = (-2.0 * (1.0 - dm) + vy * (1.0 + dm)) * SLIME_DRAW_SCALE
        hl_t = lerp(0.5, 0.2, dm)
        hlc = (int(lerp(body[0], 255, hl_t)),
               int(lerp(body[1], 255, hl_t)),
               int(lerp(body[2], 255, hl_t)))
        hsx = _slime_lerp_map(m.bites, 3.0, 1.0, 0.25, 0.15) * SLIME_DRAW_SCALE
        hsy = _slime_lerp_map(m.bites, 3.0, 1.0, 0.30, 0.05) * SLIME_DRAW_SCALE
        if atlas.find_atlas("Circle20") is not None:
            blit(p, atlas, "Circle20", x + hox, y + hoy, rot_deg, hsx, hsy, hlc)
        else:
            p.save(); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(*hlc))
            p.translate(x + hox, y + hoy); p.rotate(rot_deg)
            p.scale(hsx * 20.0, hsy * 20.0)
            p.drawEllipse(QPointF(0.0, 0.0), 0.5, 0.5); p.restore()
        # 暗场发光
        if dm > 0.0:
            light_r = _slime_lerp_map(m.bites, 3.0, 1.0, 140.0, 40.0) * SLIME_LIGHT_SCALE
            bloom_r = _slime_lerp_map(m.bites, 3.0, 1.0, 30.0, 10.0) * SLIME_BLOOM_SCALE
            p.save()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            p.setPen(Qt.PenStyle.NoPen)
            for gr, ga in ((light_r, 0.12 * dm), (bloom_r, 0.25 * dm)):
                grad = QRadialGradient(QPointF(x, y), gr)
                a = int(clampf(ga, 0.0, 1.0) * 255)
                c0 = QColor(*glow); c0.setAlpha(a)
                cm = QColor(*glow); cm.setAlpha(a)          # 0.35 前不淡出，更柔
                c1 = QColor(*glow); c1.setAlpha(0)
                grad.setColorAt(0.0, c0); grad.setColorAt(0.35, cm); grad.setColorAt(1.0, c1)
                p.setBrush(QBrush(grad))
                p.drawEllipse(QPointF(x, y), gr, gr)
            p.restore()

    def _draw_slime_tendrils(self, p, m, body):
        """逐根触须画锯齿团；alpha 值当形状种子，非透明度。"""
        ts = self._ts
        T = m.tendrils
        n = len(T)
        polys = m._tendril_polys
        if polys is None:    # 首绘建缓存
            polys = [QPolygonF([QPointF(0.5 * jf[k] * _JAG_COS[k], 0.5 * jf[k] * _JAG_SIN[k])
                                for k in range(TENDRIL_JAG_K)])
                     for jf in m.tendril_jag]
            m._tendril_polys = polys
        bx = m.last_x + (m.x - m.last_x) * ts
        by = m.last_y + (m.y - m.last_y) * ts
        p.save()
        aa_hint(p)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(*body)))
        for idx, t in enumerate(T):
            tx = t[2] + (t[0] - t[2]) * ts
            ty = t[3] + (t[1] - t[3]) * ts
            link = int(t[6])
            if link < 0 or link >= n:
                ax, ay = bx, by
            else:
                pt = T[link]
                ax = pt[2] + (pt[0] - pt[2]) * ts
                ay = pt[3] + (pt[1] - pt[3]) * ts
            dist = math.hypot(ax - tx, ay - ty)
            length = dist + 3.0
            width = lerp(4.0, 1.5, inv_lerp(0.0, t[7] * 3.5, dist) ** 2)
            rot = _ang_from_up(ax - tx, ay - ty)             # 触须→锚点角
            p.save()
            p.translate(tx, ty)
            if rot:
                p.rotate(rot)
            p.translate(0.0, -0.45 * length)                 # anchorY=0.05
            p.scale(width, length)
            p.drawPolygon(polys[idx])
            p.restore()
        p.restore()

    def _draw_slime_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        m = getattr(self, "_slime_preview", None)
        if m is None:
            return
        sx, sy, bx, by = self._slime_edge_anchor(cx, cy)
        m.last_x, m.last_y = m.x, m.y
        m.x, m.y = bx, by
        m.vx = m.vy = 0.0
        if m.stuck_pos is None:                  # 首帧钉锚（顺带把触须铺到本体上）
            m.stick_to(sx, sy)
        else:                                    # 跟随光标：触须刚性跟住 + 锚点更新
            m.carry_tendrils()
            m.stuck_pos = (sx, sy)
            ux, uy = _slime_dir(bx, by, sx, sy)
            m.rotation = (-ux, -uy)
        m.step(self._WL, self._HL)               # 手动推进触须
        dm = clampf(inv_lerp(SLIME_DARK_LO, SLIME_DARK_HI,
                             getattr(self, "cold_cycle_prog", 0.0)), 0.0, 1.0)
        p.save()
        p.setOpacity(0.5)
        self._draw_one_slimemold(p, m, dm)
        p.restore()

    # ── 蝙蝠 ──
    def can_place_batfly(self) -> bool:
        return True

    def place_batfly(self, lx, ly):
        if not self.can_place_batfly():
            return None
        b = BatFly(lx, ly, seed=self._batfly_seed)
        self._batfly_seed += 1
        self.batflies.append(b)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return b

    def clear_batflies(self):
        for b in self.batflies:
            b.stalk = None
            if b.state == ItemState.CARRIED:
                b.held_by_hand = None
            for pet in self.pets:
                if b is pet.body.carried_fruit:      # 复用果子叼持槽
                    pet.body.release_fruit()
            b.state = ItemState.EATEN
        if self.batflies:
            self.batflies = []
            self.world_version += 1
        self._dragged_batfly = None
        self._batfly_drag_last = None
        self._batfly_shove_cd = {}
        self._exit_place_mode()

    def enter_place_batfly_mode(self):
        if not self.can_place_batfly():
            return False
        self._place_mode = True
        self._place_kind = "batfly"
        self._begin_place_capture()
        return True

    def _batfly_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for b in self.batflies:
            if b.state != ItemState.FREE:
                continue
            d = math.hypot(cx - b.x, cy - b.y)
            if d <= b.rad + self._BATFLY_GRAB_PAD and d < bestd:
                best, bestd = b, d
        return best

    def _begin_batfly_drag(self, pos) -> bool:
        b = self._batfly_at(pos)
        if b is None:
            return False
        b.stalk = None
        b.held_by_hand = None
        b.state = ItemState.MOUSE
        b.vx = b.vy = 0.0
        b.last_x, b.last_y = pos
        b.x, b.y = pos
        self._dragged_batfly = b
        self._batfly_drag_last = tuple(pos)
        return True

    def _step_batfly_drag(self):
        b = self._dragged_batfly
        if b is None:
            return
        if b.state != ItemState.MOUSE:
            self._dragged_batfly = None
            self._batfly_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        b.last_x, b.last_y = b.x, b.y
        if self._batfly_drag_last is not None:
            b.vx = cur[0] - self._batfly_drag_last[0]
            b.vy = cur[1] - self._batfly_drag_last[1]
        b.x, b.y = cur
        self._batfly_drag_last = tuple(cur)

    def _end_batfly_drag(self):
        b = self._dragged_batfly
        if b is None:
            return False
        if b.dead and self._out_of_window(b, b.rad):
            b.state = ItemState.GONE           # 尸体被拖出窗口扔了：直接清除
            self._dragged_batfly = None
            self._batfly_drag_last = None
            return True
        sp = math.hypot(b.vx, b.vy)
        if sp > self._BATFLY_FLING_CAP:
            k = self._BATFLY_FLING_CAP / sp
            b.vx *= k
            b.vy *= k
        if b.state == ItemState.MOUSE:
            b.state = ItemState.FREE          # 不粘边，直接 FREE
        self._dragged_batfly = None
        self._batfly_drag_last = None
        return True

    def _step_batfly_shove(self):
        """手动塞蝙蝠进嘴，逐口咬。"""
        cd = getattr(self, "_batfly_shove_cd", None)
        if cd is None:
            cd = self._batfly_shove_cd = {}
        for k in list(cd):
            cd[k] -= 1
            if cd[k] <= 0:
                del cd[k]
        for b in self.batflies:
            key = id(b)
            if b.state != ItemState.MOUSE or b.eaten > 0:
                cd.pop(key, None)             # __slots__ 无法挂属性，用 id 字典
                continue
            if key in cd:
                continue
            for pet in self.pets:
                if pet.behavior is None:
                    continue
                mx, my = pet.gfx.mouth_world()
                if math.hypot(b.x - mx, b.y - my) < SHOVE_REACH:
                    if b.bite():
                        bq = pet.body.food_eat_object(b)   # 食性结算
                        if bq == -1:                      # 圣徒吃荤 → 眩晕
                            pet.body.stun = max(pet.body.stun, tuning.MEAT_SICK_STUN)
                        pet.body.temper_shift(tuning.TEMPER_FEED)
                        pet.body.energy_change(tuning.EN_EAT_RESTORE)
                    cd[key] = SHOVE_COOLDOWN
                    break

    def _draw_batflies(self, p):
        ts = self._ts
        self._batfly_vibe = getattr(self, "_batfly_vibe", 0) + 1
        for b in self.batflies:
            if b.state in (ItemState.EATEN, ItemState.GONE):
                continue
            self._draw_one_batfly(p, b, ts)

    def _draw_one_batfly(self, p, bat, ts):
        """单只蝙蝠：照 FlyGraphics.DrawSprites 摆 4 片精灵（被吃期抽搐）。

        num  = aim(下层体节 → 主体节)              → body / eyes 的 rotation
        翅 i ：a = lerp(lerp(w[i].prev, w[i].cur, ts), 0.5, lerp(0.3, 0, flapDepth))
                a = InverseLerp(0.01, 0.99, a²)，再按转向补偿折翅
                rotation = ±(40 + 150a) + num      （±：i==0 取 -1）
                scaleX   = ±(1 − 0.6·sin(w·π)·(1−steerFold))（flapSpeed<0 时不收窄）
        可见性：bites==3 两翅 / bites>1 一翅（sprite[1] 是 i=0）
        """
        x = bat.last_x + (bat.x - bat.last_x) * ts
        y = bat.last_y + (bat.y - bat.last_y) * ts
        lx = bat.last_lower_x + (bat.lower_x - bat.last_lower_x) * ts
        ly = bat.last_lower_y + (bat.lower_y - bat.last_lower_y) * ts
        if bat.eaten > 0:                             # 仅被吃倒计时抖动
            vf = self._batfly_vibe + (id(bat) & 0x3F)
            ox, oy = (vf % 3) - 1.0, ((vf // 2) % 3) - 1.0
            x += ox; y += oy; lx += ox; ly += oy
        body_ang = _ang_from_up(x - lx, y - ly)
        flap_depth = lerp(bat.last_flap_depth, bat.flap_depth, ts)
        steer = lerp(bat.last_steer, bat.steer, ts)
        p.save()
        aa_hint(p)
        p.setPen(Qt.PenStyle.NoPen)
        # 图层序照 InitiateSprites：body(0) 在底 → 两翅(1,2) → eyes(3) 在顶
        self._draw_batfly_body(p, x, y, body_ang)
        for i in range(2):
            if (i == 0 and bat.bites != 3) or (i == 1 and bat.bites <= 1):
                continue                              # bites: 3两翅 2一翅 1无翅
            wcur = lerp(bat.wings[i][1], bat.wings[i][0], ts)
            a = lerp(wcur, 0.5, lerp(0.3, 0.0, flap_depth))
            steer_fold = 0.0 if (steer < 0.0) == (i == 0) else clampf(abs(steer * 0.85) - 0.1, 0.0, 1.0)
            a = lerp(a, 0.5, steer_fold)
            a = inv_lerp(0.01, 0.99, a * a)
            wing_ang = (-1.0 if i == 0 else 1.0) * (40.0 + 150.0 * a) + body_ang
            sx = 1.0 if bat.flap_speed < 0.0 else 1.0 - 0.6 * math.sin(wcur * math.pi) * (1.0 - steer_fold)
            sx *= (-1.0 if i == 0 else 1.0)
            self._draw_batfly_wing(p, x, y, wing_ang, sx)
        self._draw_batfly_eyes(p, x, y, body_ang)
        p.restore()

    def _draw_batfly_body(self, p, x, y, ang):
        """FlyBody：5×12 身体片（锚点居中）。"""
        blit(p, self.atlas, "FlyBody", x, y, ang, 1.0, 1.0, BATFLY_BLACK, ax=0.5, ay=0.5)

    def _draw_batfly_wing(self, p, x, y, ang, sx):
        """FlyWing：15×15 翅片；原版 InitiateSprites 的 anchorY=0 → ay = 1 - anchorY = 1.0。"""
        blit(p, self.atlas, "FlyWing", x, y, ang, sx, 1.0, BATFLY_BLACK, ax=0.5, ay=1.0)

    def _draw_batfly_eyes(self, p, x, y, ang):
        """FlyEyes：两点白眼，与身体同角。"""
        blit(p, self.atlas, "FlyEyes", x, y, ang, 1.0, 1.0, BATFLY_EYE_COLOR, ax=0.5, ay=0.5)

    def _draw_batfly_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        from PySide6.QtGui import QPainter
        p.save()
        p.setOpacity(0.5)
        aa_hint(p)
        p.setPen(Qt.PenStyle.NoPen)
        self._draw_batfly_body(p, cx, cy, 0.0)
        self._draw_batfly_wing(p, cx, cy, -115.0, -0.9)
        self._draw_batfly_wing(p, cx, cy, 115.0, 0.9)
        self._draw_batfly_eyes(p, cx, cy, 0.0)
        p.restore()

    # ── 蜥蜴 ──
    def can_place_lizard(self) -> bool:
        return True

    def place_lizard(self, lx, ly, breed=None):
        """放下一只蜥蜴；品种按 spawn_weight 加权随机（不再按次序轮换）。

        用放置序号作种子的 PRNG：同一次会话里连续放两只不会再固定成粉/绿/蓝，
        但同一个序号永远抽出同一个品种 —— 渲染黄金帧与测试仍可复现。
        """
        if not self.can_place_lizard():
            return None
        seed = self._lizard_seed
        if breed is None:
            breed = pick_breed(seed)
        lz = Lizard(lx, ly, breed, seed=seed, id=seed)
        self._lizard_seed += 1
        self.lizards.append(lz)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return lz

    def clear_lizards(self):
        for lz in self.lizards:
            lz.die()
        if self.lizards:
            self.lizards = []
            self.world_version += 1
        self._dragged_lizard = None
        self._lizard_preview = None
        self._exit_place_mode()
        self.update()

    def enter_place_lizard_mode(self):
        if not self.can_place_lizard():
            return False
        self._place_mode = True
        self._place_kind = "lizard"
        self._begin_place_capture()
        return True

    def _lizard_at(self, pos):
        """命中测试：到脊柱折线的距离 ≤ 躯干半径 + pad。"""
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for lz in self.lizards:
            if lz.state != ItemState.FREE:
                continue
            d = _dist_to_path(lz.body_path(), cx, cy) - lz.body_rad
            if d <= self._LIZARD_GRAB_PAD and d < bestd:
                best, bestd = lz, d
        return best

    def _begin_lizard_drag(self, pos) -> bool:
        lz = self._lizard_at(pos)
        if lz is None:
            return False
        lz.grab(pos)
        lz.last_x, lz.last_y = pos
        lz.x, lz.y = pos
        self._dragged_lizard = lz
        return True

    def _step_lizard_drag(self):
        """手里的蜥蜴由 Lizard._step_held 跟随光标；这里只清失效引用。"""
        lz = self._dragged_lizard
        if lz is not None and lz.state != ItemState.MOUSE:
            self._dragged_lizard = None

    def _end_lizard_drag(self) -> bool:
        lz = self._dragged_lizard
        if lz is None:
            return False
        if lz.dead and self._out_of_window(lz, lz.body_rad):
            lz.state = ItemState.GONE          # 尸体被拖出窗口扔了：直接清除
            self._dragged_lizard = None
            return True
        sp = math.hypot(lz.vx, lz.vy)
        if sp > self._LIZARD_FLING_CAP:
            k = self._LIZARD_FLING_CAP / sp
            lz.vx *= k
            lz.vy *= k
        lz.release(lz.vx, lz.vy)
        self._dragged_lizard = None
        return True

    def _out_of_window(self, e, rad=None) -> bool:
        """尸体是否已经被扔出窗口（左右/顶边都能出去；底边是地面，不会从下面跑掉）。"""
        r = rad if rad is not None else (getattr(e, "rad", 0.0) or 0.0)
        m = CORPSE_OUT_MARGIN
        return (e.x < -r - m or e.x > self._WL + r + m or e.y < -r - m)

    def _cull_flung_corpses(self):
        """被甩出窗口的尸体直接清除（非蛞蝓猫的才算，猫死了另有守灵/转生逻辑）。

        蛞蝓猫拖到屏幕边丢出去的那具（release_haul(thrown_out=True) 标记过）单独一条
        规则：越过窗口边就删 —— 不看半径/边距，也不靠摩擦减速停在边上（拖着走的尸体
        贴着地面，旧规则下常减速停住 = 「尸体只是在屏幕边缘没删除」）。
        """
        for e in (*self.lizards, *self.squidcadas, *self.batflies,
                  *self.needleworms, *self.scavengers):
            if (not getattr(e, "dead", False) or e.state != ItemState.FREE
                    or e is self._dragged_lizard or e is self._dragged_squidcada
                    or e is self._dragged_batfly
                    or e is self._dragged_needleworm
                    or e is self._dragged_scavenger):
                continue
            if getattr(e, "haul_thrown", False):
                if e.x <= 0.0 or e.x >= self._WL or e.y <= 0.0:
                    e.state = ItemState.GONE
                continue
            rad = getattr(e, "rad", None) or getattr(e, "body_rad", 0.0)
            if self._out_of_window(e, rad):
                e.state = ItemState.GONE

    def _step_lizards(self):
        """推进所有蜥蜴：感知快照 → 各自决策 → 一起执行 → 咬到猫结算。

        原版每只蜥蜴是独立 agent，但看到的是同一个世界。旧版是「A 决策 → A 咬 →
        世界变了 → B 决策」，数组第一只天然占先手（几只也容易像同步抢）。这里改成
        三段：全体先基于同一份快照感知，再各自决定，最后才执行。
        """
        self._step_lizard_drag()
        if not self.lizards:
            return
        cur = self.cursor_logical()
        tick = getattr(self, "_pole_tick", 0)
        # 每只猫带上「死了 / 昏迷」两个标记：蜥蜴靠它们决定叼走、咬死还是追击
        targets = []
        for pet in self.pets:
            beh = pet.behavior
            if beh is None:
                continue
            targets.append((pet, pet.body.chunk0.x, pet.body.chunk0.y,
                            beh.is_dead(), beh.state == "Stunned"))
        blockers = self._lizard_blockers()
        # 地形查询：这一帧一份，全场蜥蜴共用（地面 / 墙 / 竖杆 / 横杆 / 背景墙）
        terrain = self.terrain = TerrainQuery(self)
        surfaces = terrain.climb_surfaces()
        live = [lz for lz in self.lizards
                if not lz.dead and lz.state == ItemState.FREE]
        # 猎物归属快照（文档 §37）：同一 tick 内归属不会变，建一张 {猎物 id → 认领者}
        # 表全场共用，代替「每只蜥蜴 × 每个候选 × 所有同伴」跑 owns()。
        claims = {}
        for lz in live:
            po = lz.prey.obj
            if po is not None and lz.prey.owns(po, tick):
                claims.setdefault(id(po), lz)
        # ① 感知：所有蜥蜴看同一份世界快照。**扫描按 id 错峰降频**（文档 §37 AI
        #    时间片）：平均每 PERCEIVE_EVERY tick 重建一次观察，其余 tick 复用上次
        #    结果；地形 / 遮挡 / 同伴 / 归属这些便宜字段仍然逐 tick 刷新。
        for lz in self.lizards:
            lz._claims = claims
            scan = lz.should_scan(tick)
            if scan:
                prey, threats, others, pack = self._lizard_relations(lz)
            else:
                prey = threats = others = pack = ()
            lz.perceive(self._WL, self._HL, targets=targets, prey=prey,
                        threats=threats, others=others, pack=pack,
                        lizards=live, blockers=blockers,
                        surfaces=surfaces, terrain=terrain, tick=tick, scan=scan)
        # ② 决策；黄蜥在这一步之后广播猎物情报，同伴按自己的序号去包夹
        for lz in self.lizards:
            lz.decide(self._WL, self._HL)
        alerts = [a for a in (lz.offer_alert() for lz in self.lizards)
                  if a is not None]
        for a in alerts:
            for lz in self.lizards:
                if lz.id != a.leader:
                    lz.absorb_alert(a.decayed(tick))
        # ③ 执行：这时才真正改世界
        for lz in self.lizards:
            lz.act(self._WL, self._HL, cursor=cur)
            lz.step_physics(self._WL, self._HL, cursor=cur)
            self._lizard_bite(lz, tick)
            # 蜥蜴的猎物也上认领板（Lizard.intent）：全场只有一份「谁在追什么」
            obj_i, kind_i = lz.intent()
            board_for(self).register_actor(lz, obj_i, kind_i)
        for lz in self.lizards:
            lz.camo_tick(self, tick)          # 白蜥迷彩：低频采背后背景色
        self._cull_flung_corpses()
        self.lizards = [lz for lz in self.lizards if lz.state != ItemState.GONE]

    def _climb_surfaces(self):
        """这一帧可以攀爬的竖线：竖直杆 + 背景墙（非全屏窗口）的左右竖边。

        原版蜥蜴靠 Climb / Wall tile 上下移动；桌宠里这两种 tile 的替身就是
        「立着的杆」和「别人窗口的侧边」。**定义只有一份**，在 world/terrain.py
        的 TerrainQuery 里（和蛞蝓猫侧 planning/surface.py 读的是同一批几何），
        这里退化成门面，供外部（测试 / 探针）调用。
        返回 [(x, y_top, y_bot, kind)]（y_top < y_bot）。
        """
        return TerrainQuery(self).climb_surfaces()

    def _lizard_blockers(self):
        """蜥蜴的视线遮挡物：地形（线段）与体型够大的生物（圆）。

        原版蜥蜴的视觉会被环境影响；桌宠里能挡视线的就是杆、庇护所墙、背景墙、
        窗口竖边和别的生物。线段直接取**共用的 NavGeometry.obstacles**（文档
        §8/§9：旧实现只发了杆子，庇护所墙 / 背景墙 / 窗口竖边在蜥蜴眼里是空气），
        于是「挡不挡视线」和「走不走得过去」用的是同一份几何、同一套 capsule 判交。
        每 tick 建一次快照，整场蜥蜴共用同一份（「同一份世界快照」也就顺带保证了）。
        """
        segs = []
        try:
            geom = TerrainQuery(self).geom
        except Exception:
            geom = None
        if geom is not None and geom.obstacles:
            for ob in geom.obstacles:
                segs.append((ob.x0, ob.y0, ob.x1, ob.y1, max(ob.r, 1.0)))
        else:
            # 极端兜底（没有几何层时）：杆子照旧，至少不比旧版弱
            for pl in self.poles:
                if (getattr(pl, "state", None) != ItemState.FREE
                        or getattr(pl, "virtual", False)):
                    continue
                segs.append((pl.ax, pl.ay, pl.bx, pl.by, 3.0))
        circles = [(lz.x, lz.y, lz.body_rad) for lz in self.lizards
                   if not lz.dead and lz.state == ItemState.FREE]
        for sc in self.scavengers:
            if not sc.dead and sc.state == ItemState.FREE:
                circles.append((sc.x, sc.y, float(getattr(sc, "rad", 14.0))))
        return (tuple(segs), tuple(circles))

    def _lizard_relations(self, lz):
        """按原版关系表（StaticWorld.cs:3668-3726 + LizardAI.ModuleToTrackRelationship）
        把场上对象分成四组：prey(Eats/Attacks) / threats(Afraid) / others(AgressiveRival)
        / pack(Pack)。返回 (prey, threats, others, pack)，每项是 [(obj, 权重)]。"""
        prey, threats, others, pack = [], [], [], []

        def route(kind, w, obj):
            if kind in ("Eats", "Attacks"):
                prey.append((obj, w))
            elif kind == "Afraid":
                threats.append((obj, w))
            elif kind == "Pack":
                pack.append((obj, w))
            elif kind == "AgressiveRival":
                others.append((obj, w))

        for other in self.lizards:
            if other is lz or other is self._dragged_lizard:
                continue
            if other.dead or other.state != ItemState.FREE:
                continue
            route(*lizard_rel(lz.breed.key, other.breed.key), other)
        for sq in self.squidcadas:
            if not sq.dead and sq.state == ItemState.FREE:
                route(*lizard_rel_kind(lz.breed.key, "squidcada"), sq)
        for nw in self.needleworms:
            if nw.dead or nw.state != ItemState.FREE or nw.age not in ("small", "big"):
                continue
            route(*lizard_rel_kind(lz.breed.key,
                                   "noodle_big" if nw.age == "big" else "noodle_small"), nw)
        for sc in self.scavengers:
            if not sc.dead and sc.state == ItemState.FREE:
                route(*lizard_rel_kind(lz.breed.key, "scavenger"), sc)
        return tuple(prey), tuple(threats), tuple(others), tuple(pack)

    def _lizard_prey(self, lz):
        """兼容旧签名：只取猎物那一组。"""
        return self._lizard_relations(lz)[0]

    def _lizard_death_fx(self, lz):
        """蜥蜴被击杀：重震一下（原版会有血花，这里只用震动表示）。"""
        self._shake[0] += 2.0 * lz.facing
        self._shake[1] += 1.4

    def _lizard_bite(self, lz, tick=None):
        """咬合结算：蛞蝓猫 → 眩晕；同类 → 原版 Violence(Bite)；蝉乌贼 → 被吃掉。

        咬倒 / 咬死一只猫就记进这只蜥蜴的 PreyTracker（原版：追到并咬倒的猎物才算
        自己的），别人不能随便接手 —— 路过的蜥蜴只处理没人管的尸体。
        """
        if tick is None:
            tick = getattr(self, "_pole_tick", 0)
        ev = lz.bite_event
        if ev is None:
            return
        lz.bite_event = None
        obj, dmg = ev
        if obj is None:
            return
        sfx = getattr(self, "sfx", None)
        if sfx is not None:
            sfx.play("lizard_bite", 0.9)
        beh = getattr(obj, "behavior", None)
        if beh is not None:
            # 蛞蝓猫：按攻击者数据（biteDamageChance × DeathByBiteMultiplier）掷致死，
            # 否则按 Violence(Bite) 的 num2 眩晕。
            death_chance = lz.breed.bite_damage_chance * _pet_bite_death_mult(obj)
            if death_chance > 0.0 and lz.rng.random() < death_chance:
                beh.kill()
                lz.prey.claim(obj, tick, killed=True)
                self._lizard_strike_ev(lz, obj, EV.CREATURE_KILLED, 1.0, tick)
                self._shake[0] += 2.0 * lz.facing
                self._shake[1] += 1.4
                return
            died, stun = _pet_stun_death(BITE_VIOLENCE_DAMAGE, 0.0)
            stun = int(stun * STUN_SCALE)
            if died:
                # 致死掷骰没过时 num 仍是 1.5 ⇒ 原版这条路也必死；宠物按掷骰结果放行
                if beh.apply_stun(max(LIZARD_STUN_TICKS, stun)):
                    lz.prey.claim(obj, tick, fainted=True)
                    self._lizard_strike_ev(lz, obj, EV.CREATURE_HURT, 0.85, tick)
                    self._shake[0] += 1.6 * lz.facing
                    self._shake[1] += 1.0
                return
            if beh.apply_stun(stun):
                lz.prey.claim(obj, tick, fainted=True)
                self._lizard_strike_ev(lz, obj, EV.CREATURE_HURT, 0.7, tick)
                self._shake[0] += 1.6 * lz.facing
                self._shake[1] += 1.0
            return
        if isinstance(obj, Lizard):               # 同族撕咬（原版 biteDamage * Lerp(0.8,1.2)）
            if obj.dead or dmg <= 0.0:
                return
            dx, dy = obj.x - lz.x, obj.y - lz.y
            d = math.hypot(dx, dy) or 1.0
            killed = obj.hurt(dmg, dvec=(dx / d, dy / d), speed=1.0,
                              stun_bonus=0.0, hit_head=False, knock_k=0.0)
            self._shake[0] += 0.8 * lz.facing
            self._shake[1] += 0.5
            if killed:
                self._lizard_death_fx(obj)
            self._lizard_strike_ev(lz, obj,
                                   EV.CREATURE_KILLED if killed else EV.CREATURE_HURT,
                                   0.9 if killed else 0.6, tick)
            return
        if isinstance(obj, Squidcada):            # 被蜥蜴吃掉（原版 Eats 关系）
            obj.die()
            obj.state = ItemState.EATEN
            self._shake[1] += 0.3
        elif isinstance(obj, Scavenger):          # 原版 LizardTemplate→Scavenger Eats 0.8
            if dmg > 0.0:
                died = obj.hurt(dmg)
                self._lizard_strike_ev(
                    lz, obj, EV.CREATURE_KILLED if died else EV.CREATURE_HURT,
                    0.9 if died else 0.6, tick)
                self._shake[0] += 1.2 * lz.facing
                self._shake[1] += 0.8
        elif isinstance(obj, NeedleWorm):         # 原版 Eats 0.25(成)/0.3(幼)
            if obj.age == AGE_SMALL:
                if obj.bite():                    # SmallNeedleWorm.cs:356 一口一口啃
                    obj.state = ItemState.EATEN
            else:
                obj.hurt(max(1.0, dmg), lethal=True)
                if obj.dead:
                    obj.state = ItemState.EATEN
            self._shake[1] += 0.3

    def _lizard_strike_ev(self, lz, victim, kind, intensity, tick=None):
        """蜥蜴的伤害动作上总线：附近的猫会各自解释（怕 / 恨 / 想救）。"""
        EV.emit_for(self, kind, subject=lz, obj=victim, intensity=intensity,
                    tick=tick)

    def _draw_lizards(self, p):
        ts = self._ts
        for lz in self.lizards:
            draw_lizard(p, self.atlas, lz, ts)

    def _lizard_hint_object(self):
        """放置预览用的一次性蜥蜴（不参与物理，品种跟随下一次放置）。"""
        seed = self._lizard_seed
        got = getattr(self, "_lizard_preview", None)
        if got is None or got[0] != seed:
            lz = Lizard(0.0, 0.0, pick_breed(seed), seed=seed)
            lz.state = ItemState.MOUSE
            got = (seed, lz)
            self._lizard_preview = got
        return got[1]

    @staticmethod
    def _lay_lizard_hint(lz, cx, cy):
        """把预览蜥蜴摆成「头在光标、身体横躺向左」的站姿。"""
        lz.facing = 1
        lz.body_dir = lz.move_dir = 0.0
        lz.chain_dir = 1.0
        lz.head_angle = lz.last_head_angle = 90.0
        # 软体头点：R129 起渲染真的读 head_lx → head_x（头不再是「AI 直接写的
        # 独立点」）。这里不摆它，预览的头就停在构造时的 (head_conn, 0)，也就是
        # 屏幕左上角 —— 用户看到的正是「头在左上角、身体拉伸到鼠标」。
        lz.head_x = lz.head_lx = cx
        lz.head_y = lz.head_ly = cy
        lz.head_vx = lz.head_vy = 0.0
        # 驱动点（链根 x/y）在头后方 head_conn 处：head = x + chain_dir*head_conn。
        x = cx - lz.head_conn
        lz.x = lz.last_x = x
        lz.y = lz.last_y = cy
        for s in lz.seg:
            x -= s.dist
            s.x = s.lx = x
            s.y = s.ly = cy
        for lg in lz.legs:
            seg = lz.seg[0] if not lg.back else (lz.seg[2] if len(lz.seg) > 2 else lz.seg[-1])
            lg.x = lg.lx = seg.x + (8.0 if lg.back else -8.0)
            lg.y = lg.ly = seg.y + lz.body_rad * 2.2
            lg.abs_x, lg.abs_y = lg.x, lg.y
            lg.vx = lg.vy = 0.0
            lg.reaching = False
            lg.snap = False
            lg.grip = 0
            lg.planted = False
            lg.airborne = False
            lg.swing = 0
            lg.plant_dx = lg.plant_dy = 0.0

    def _draw_lizard_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        lz = self._lizard_hint_object()
        self._lay_lizard_hint(lz, cx, cy)
        p.save()
        p.setOpacity(0.5)
        draw_lizard(p, self.atlas, lz, 1.0)
        p.restore()

    def _pup_next_index(self) -> int:
        """下一个要放的幼崽编号（最低空位）：预览和真正生成共用同一个。"""
        used = {p.index for p in self.pets}
        k = 0
        while k in used:
            k += 1
        return k

    def _pup_hint_object(self):
        """放置预览用的一次性幼崽：只有身体 + 图形，不建行为层、不进 self.pets。

        身份用**即将生成的那一只**（``pup-{k}``，k = 预留编号）：体色 / 瞳色 /
        体型都由 ``pup_appearance(_pers_seed(pet_id, ...))`` 决定，旧实现预览用
        "pup-preview" ⇒ 预览和真正落下的那只必然不是同一只（用户报的「预览没有
        显示真实会生成的猫崽外貌」）。
        """
        got = getattr(self, "_pup_preview", None)
        if got is not None:
            return got
        from ..petunit import PetUnit
        from ..window import PUP_VARIANT
        k = getattr(self, "_pup_pending", None)
        if k is None:
            k = self._pup_next_index()
        init_state = {"energy": 1.0, "temper": 0.0, "food": tuning.FOOD_INIT,
                      "karma": tuning.KARMA_INIT, "cold": 0.0}
        try:
            pup = PetUnit(self, k, f"pup-{k}", PUP_VARIANT, init_state,
                          spawn_x=self._WL * 0.5, spawn_y=self._HL, preview=True)
        except Exception as exc:
            log_error("slugpup preview build failed: %r" % (exc,))
            pup = None
        self._pup_preview = pup
        return pup

    def _draw_slugpup_hint(self, p):
        """放猫崽的预览：光标处半透明摆一只幼崽。

        以前这里没有分支，直接掉到兜底那句「画个果子」，于是放猫崽预览出来是
        一个蓝果（用户报的 bug）。
        """
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        pup = self._pup_hint_object()
        if pup is None:
            return
        try:
            pup.body.teleport(cx, cy)
            pup.gfx.update()
            pup._tick_tail()                   # 尾巴跟着摆好，别拖在出生点
            p.save()
            try:
                p.setOpacity(0.5)
                pup.gfx.draw_sprites(p, self.atlas, timeStacker=1.0)
            finally:
                p.restore()
        except Exception as exc:               # 预览画不出来也不能毁掉整帧
            if not getattr(self, "_pup_hint_warned", False):
                self._pup_hint_warned = True
                log_error("slugpup hint draw failed: %r" % (exc,))

    # ── 幼崽（Slugpup）：不是常规蛞蝓猫，从「生物生成」里放 ──
    def can_place_slugpup(self) -> bool:
        from ..window import PUP_MAX
        return sum(1 for p in self.pets if getattr(p, "is_pup", False)) < PUP_MAX

    def place_slugpup(self, lx, ly):
        """放一只幼崽：会自己行动，但不占蛞蝓猫名额、不参与救援、也不被救援。"""
        from ..petunit import PetUnit
        from ..window import PUP_VARIANT
        if not self.can_place_slugpup():
            return None
        k = getattr(self, "_pup_pending", None)
        if k is None or any(p.index == k for p in self.pets):
            k = self._pup_next_index()           # 预留编号被占用了就重挑
        self._pup_pending = None
        self._pup_preview = None
        init_state = {"energy": 1.0, "temper": 0.0, "food": tuning.FOOD_INIT,
                      "karma": tuning.KARMA_INIT, "cold": 0.0}
        pet = PetUnit(self, k, f"pup-{k}", PUP_VARIANT, init_state,
                      spawn_x=lx, spawn_y=ly)
        self.pets.append(pet)
        self._prev_dirty = None
        self._after_pets_changed()
        self._exit_place_mode()
        self.update()
        return pet

    def enter_place_slugpup_mode(self):
        if not self.can_place_slugpup():
            return False
        # 进放置模式就先定下这一只的身份：预览与最终生成共用，取消则丢弃。
        self._pup_pending = self._pup_next_index()
        self._pup_preview = None
        self._place_mode = True
        self._place_kind = "slugpup"
        self._begin_place_capture()
        return True

    def enter_place_fruit_mode(self):
        if not self.can_place_fruit():
            return False
        self._place_mode = True
        self._place_kind = "fruit"
        self._begin_place_capture()
        return True

    def _begin_place_capture(self):
        """进入放置模式，grabMouse 防点击被覆盖窗截走。"""
        hk = getattr(self, "_hotkey_filter", None)
        if hk is not None:
            hk.register(HK_PLACE_ESC, 0, VK_ESCAPE)
        if not self._hwnd:
            self._hwnd = int(self.winId())
        from ..control.mouse import set_passthrough
        set_passthrough(self._hwnd, False)
        self._passthrough = False
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.grabMouse()

    def _exit_place_mode(self):
        if not self._place_mode:
            return
        self._place_mode = False
        self._place_kind = None
        self._slime_preview = None
        self._pole_drag_start = None
        self._wall_drag_start = None
        self._pup_pending = None       # 取消放置：丢掉预留的幼崽身份
        self._pup_preview = None
        hk = getattr(self, "_hotkey_filter", None)
        if hk is not None:
            hk.unregister(HK_PLACE_ESC)
        self.releaseMouse()
        self.unsetCursor()
        self._passthrough = None

    # ── 删除模式：点哪个非蛞蝓猫对象就删哪个 ──
    ERASE_POOLS = ("fruits", "stones", "slimemolds", "batflies", "lizards",
                   "squidcadas", "needleworms", "pearls", "spears",
                   "scavengers", "seedcobs", "seeds", "karmaflowers",
                   "poles")

    def enter_erase_mode(self):
        """删除模式（复用放置模式的光标/ESC/鼠标捕获机制）。

        复刻原版沙箱的「橡皮」：点中哪个物件删哪个；蛞蝓猫不在此模式下被删。
        """
        self._place_mode = True
        self._place_kind = "erase"
        self._begin_place_capture()
        return True

    @staticmethod
    def _erase_dist(obj, cx, cy):
        """命中距离（<=0 表示光标在物体内部）；无法定位的返回 None。"""
        if getattr(obj, "is_pup", False):
            b = getattr(obj, "body", None)              # 幼崽：两根身体节的小圆
            if b is None:
                return None
            return (min(math.hypot(cx - b.chunk0.x, cy - b.chunk0.y),
                        math.hypot(cx - b.chunk1.x, cy - b.chunk1.y))
                    - PUP_PICK_R)
        if hasattr(obj, "snout_n") and getattr(obj, "seg", None):
            # 面条蝇 / 卵：长条物体按整条体节链判定，只测身体中心的话
            # 尾巴 / 吻部点不中（用户报的「单个删除也无法选中」）。
            best = None
            for s in obj.seg:
                d = math.hypot(cx - s.x, cy - s.y) - s.rad
                if best is None or d < best:
                    best = d
            return best
        if hasattr(obj, "bulb_x"):
            return math.hypot(cx - obj.bulb_x, cy - obj.bulb_y) - LAMP_PICK_R
        if hasattr(obj, "body_path"):                  # 蜥蜴这类多节身体
            return _dist_to_path(obj.body_path(), cx, cy) - obj.body_rad
        if hasattr(obj, "ax") and hasattr(obj, "bx"):  # 杆：到线段
            return _seg_dist(obj.ax, obj.ay, obj.bx, obj.by, cx, cy) - POLE_RAD
        if getattr(obj, "x", None) is None:
            return None
        return (math.hypot(cx - obj.x, cy - getattr(obj, "y", 0.0))
                - (getattr(obj, "rad", 0.0) or 0.0))

    def erase_target(self, cx, cy):
        """光标下最该删的那个对象 → (对象, 所在池名)；没有则 None。"""
        for sh in getattr(self, "shelters", ()) or ():
            if sh.contains(cx, cy):
                return (sh, "shelters")      # 庇护所整间删掉
        best, bestd, bestname = None, 1e9, None
        for pet in self.pets:              # 幼崽在删除范围里（成年蛞蝓猫不删）
            if not getattr(pet, "is_pup", False):
                continue
            d = self._erase_dist(pet, cx, cy)
            if d is None or d > ERASE_PICK_PAD or d >= bestd:
                continue
            best, bestd, bestname = pet, d, "pups"
        pools = [(n, getattr(self, n)) for n in self.ERASE_POOLS]
        if self.lamp is not None:
            pools.append(("lamp", (self.lamp,)))
        for name, pool in pools:
            for obj in pool:
                d = self._erase_dist(obj, cx, cy)
                if d is None or d > ERASE_PICK_PAD or d >= bestd:
                    continue
                best, bestd, bestname = obj, d, name
        if best is None:              # 没有实体命中：看看是不是点在墙条上
            for w in (getattr(self, "extra_walls", None) or ()):
                x0, y0, x1, y1 = w
                if (x0 - ERASE_PICK_PAD <= cx <= x1 + ERASE_PICK_PAD
                        and y0 - ERASE_PICK_PAD <= cy <= y1 + ERASE_PICK_PAD):
                    return (w, "walls")
        return None if best is None else (best, bestname)

    def erase_at(self, pos) -> bool:
        """删除模式点击：删掉光标下那一个对象（蛞蝓猫不在删除范围内）。"""
        if pos is None:
            return False
        hit = self.erase_target(pos[0], pos[1])
        if hit is None:
            return False
        obj, name = hit
        if name == "pups":
            self.remove_pup(obj)               # 幼崽：整只卸载（不受最后一只猫的保护）
        elif name == "lamp":
            self.clear_lamp()
        elif name == "walls":
            walls = getattr(self, "extra_walls", None)
            if walls:
                try:
                    walls.remove(obj)
                except ValueError:
                    pass
                refresh = getattr(self, "_refresh_shelter_solids", None)
                if refresh is not None:
                    refresh()
        else:
            pool = getattr(self, name)
            try:
                pool.remove(obj)
            except ValueError:
                pass
            if getattr(obj, "state", None) is not None:
                obj.state = ItemState.GONE
            for attr in ("_dragged_fruit", "_dragged_stone", "_dragged_slimemold",
                         "_dragged_batfly", "_dragged_lizard", "_dragged_squidcada",
                         "_dragged_needleworm", "_dragged_pearl", "_dragged_spear",
                         "_dragged_scavenger", "_dragged_seedcob",
                          "_dragged_karmaflower"):
                if getattr(self, attr, None) is obj:
                    setattr(self, attr, None)
            for pet in self.pets:              # 猫手里 / 背上 / 嘴里的引用一并放开
                release = getattr(pet.body, "release_object", None)
                if release is not None:
                    release(obj)
        self.world_version += 1
        self.geometry_version += 1
        self.update()
        return True

    def _draw_erase_hint(self, p):
        """删除模式光标：准星 + 将被删除对象的外圈。"""
        from PySide6.QtGui import QPen
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(232, 74, 74, 235), 2.0))
        hit = self.erase_target(cx, cy)
        if hit is not None:
            obj = hit[0]
            if hit[1] == "walls":                          # 手绘墙块：4 元 tuple，整块描边
                x0, y0, x1, y1 = obj
                p.drawRect(x0, y0, x1 - x0, y1 - y0)
            elif hasattr(obj, "safe_rect"):                # 庇护所：整间描边
                x0, y0, x1, y1 = obj.safe_rect()
                p.drawRect(x0, y0, x1 - x0, y1 - y0)
            elif getattr(obj, "is_pup", False) and getattr(obj, "body", None) is not None:
                b = obj.body
                rr = PUP_PICK_R + 4.0
                p.drawEllipse(QPointF(b.chunk0.x, b.chunk0.y), rr, rr)
                p.drawEllipse(QPointF(b.chunk1.x, b.chunk1.y), rr, rr)
            elif hasattr(obj, "bulb_x"):
                p.drawEllipse(QPointF(obj.bulb_x, obj.bulb_y), LAMP_PICK_R, LAMP_PICK_R)
            else:
                ox = getattr(obj, "x", None)
                if ox is None:
                    ox, oy = obj.ax, obj.ay
                else:
                    oy = getattr(obj, "y", 0.0)
                rr = max(6.0, float(getattr(obj, "rad", 0.0)
                                    or getattr(obj, "body_rad", 0.0) or 6.0) + 4.0)
                p.drawEllipse(QPointF(ox, oy), rr, rr)
        p.drawLine(QPointF(cx - 7.0, cy), QPointF(cx + 7.0, cy))
        p.drawLine(QPointF(cx, cy - 7.0), QPointF(cx, cy + 7.0))
        p.restore()

    def _draw_fruit_ropes(self, p):
        ts = self._ts
        for f in self.fruits:
            st = f.stalk
            if st is None:
                continue
            pts = [st.stuck_pos]
            for s in st.segs:
                lx = s[2] + (s[0] - s[2]) * ts
                ly = s[3] + (s[1] - s[3]) * ts
                pts.append((lx, ly))
            n = len(pts)
            if n < 2:
                continue
            pts[-1] = (f.last_x + (f.x - f.last_x) * ts,
                       f.last_y + (f.y - f.last_y) * ts)
            widths = [STALK_ROOT_W + (STALK_TIP_W - STALK_ROOT_W) * (i / (n - 1))
                      for i in range(n)]
            draw_rope(p, pts, widths, color=STALK_COLOR)

    def _draw_fruits(self, p):
        ts = self._ts
        for f in self.fruits:
            x = f.last_x + (f.x - f.last_x) * ts
            y = f.last_y + (f.y - f.last_y) * ts
            rx, ry = f.rotation
            rot_deg = _ang_from_up(rx, ry)
            draw_fruit(p, self.atlas, x, y, rot_deg, f.bites,
                       flesh_color=FRUIT_FLESH, outline_color=FRUIT_OUTLINE)

    def _draw_stones(self, p):
        ts = self._ts
        for s in self.stones:
            x = s.last_x + (s.x - s.last_x) * ts
            y = s.last_y + (s.y - s.last_y) * ts
            rot = s.last_rotation + (s.rotation_deg - s.last_rotation) * ts
            # 高速时画拖尾
            if (s.fling or s.thrown_by_saint) and s.state == ItemState.FREE:
                sp = math.hypot(s.vx, s.vy)
                if sp > STONE_TRAIL_MIN_SPEED:
                    length = min(sp * STONE_TRAIL_LEN_K, STONE_TRAIL_LEN_MAX)
                    draw_stone_trail(p, x, y, s.vx / sp, s.vy / sp, length,
                                     STONE_TRAIL_HALFW, STONE_COLOR, STONE_TRAIL_ALPHA)
            if s.vibrate > 0:
                x += (s.vibrate % 3) - 1.0
                y += ((s.vibrate // 2) % 3) - 1.0
            draw_stone(p, self.atlas, x, y, rot, s.frame,
                       color=STONE_COLOR, scale=STONE_DRAW_SCALE)

    def _draw_place_hint(self, p):
        from PySide6.QtGui import QPen

        if self._place_kind == "erase":
            self._draw_erase_hint(p)
            return

        if self._place_kind in ("vpole", "hpole", "pole"):
            self._draw_pole_hint(p)
            return

        if self._place_kind == "wall":
            self._draw_wall_hint(p)
            return

        if self._place_kind == "lamp":
            self._draw_lamp_hint(p)
            return

        if self._place_kind == "slimemold":
            self._draw_slime_hint(p)
            return

        if self._place_kind == "batfly":
            self._draw_batfly_hint(p)
            return

        if self._place_kind == "lizard":
            self._draw_lizard_hint(p)
            return

        if self._place_kind == "slugpup":
            self._draw_slugpup_hint(p)
            return

        if self._place_kind == "squidcada":
            self._draw_squidcada_hint(p)
            return

        if self._place_kind == "needleworm":
            self._draw_needleworm_hint(p)
            return

        if self._place_kind == "pearl":
            self._draw_pearl_hint(p)
            return

        if self._place_kind == "spear":
            self._draw_spear_hint(p)
            return

        if self._place_kind == "scavenger":
            self._draw_scavenger_hint(p)
            return

        if self._place_kind == "seedcob":
            self._draw_seedcob_hint(p)
            return

        if self._place_kind == "karmaflower":
            self._draw_karmaflower_hint(p)
            return

        if self._place_kind == "shelter":
            self._draw_shelter_hint(p)
            return

        stone = (self._place_kind == "stone")
        p.save()
        if not stone and not self.zerog_on:
            pen = QPen(QColor(255, 255, 255, 110), 1.0, Qt.PenStyle.DashLine)
            p.setPen(pen)
            yline = self._HL * PLACE_HANGING_FRAC
            p.drawLine(QPointF(0.0, yline), QPointF(self._WL, yline))
        cur = self.cursor_logical()
        if cur is not None:
            cx, cy = cur
            if 0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL:
                p.setOpacity(0.5)
                if stone:
                    draw_stone(p, self.atlas, cx, cy, 0.0,
                               "Pebble" + str(1 + self._stone_seed % 14),
                               color=STONE_COLOR, scale=STONE_DRAW_SCALE)
                else:
                    draw_fruit(p, self.atlas, cx, cy, 0.0, 3,
                               flesh_color=FRUIT_FLESH, outline_color=FRUIT_OUTLINE)
        p.restore()

    # ── 蝉乌贼（Squidcada）：飞行可抓，力竭落地后才能被叼走 ──
    def can_place_squidcada(self) -> bool:
        return True

    def place_squidcada(self, lx, ly):
        sc = Squidcada(lx, ly, seed=self._squidcada_seed)
        self._squidcada_seed += 1
        self.squidcadas.append(sc)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return sc

    def clear_squidcadas(self):
        for sc in self.squidcadas:
            for pet in self.pets:
                if sc is pet.body.carried_fruit:      # 复用果子叼持槽
                    pet.body.release_fruit()
            sc.state = ItemState.EATEN
        if self.squidcadas:
            self.squidcadas = []
            self.world_version += 1
        self._dragged_squidcada = None
        self._squidcada_preview = None

    def enter_place_squidcada_mode(self):
        self._place_mode = True
        self._place_kind = "squidcada"
        self._begin_place_capture()
        return True

    def _squidcada_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for sc in self.squidcadas:
            if sc.state not in (ItemState.FREE, ItemState.CARRIED):
                continue
            d = math.hypot(cx - sc.x, cy - sc.y)
            if d <= sc.rad + SQUIDCADA_GRAB_PAD and d < bestd:
                best, bestd = sc, d
        return best

    def _begin_squidcada_drag(self, pos) -> bool:
        sc = self._squidcada_at(pos)
        if sc is None:
            return False
        if sc.state == ItemState.CARRIED:
            for pet in self.pets:
                if sc is pet.body.carried_fruit:
                    pet.body.release_fruit()
        sc.held_by_hand = None
        sc.state = ItemState.MOUSE
        sc.vx = sc.vy = 0.0
        sc.last_x, sc.last_y = pos
        sc.x, sc.y = pos
        self._dragged_squidcada = sc
        return True

    def _step_squidcada_drag(self):
        sc = self._dragged_squidcada
        if sc is None:
            return
        if sc.state != ItemState.MOUSE:
            self._dragged_squidcada = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        sc.last_x, sc.last_y = sc.x, sc.y
        sc.x, sc.y = cur
        sc.vx = sc.vy = 0.0

    def _end_squidcada_drag(self) -> bool:
        sc = self._dragged_squidcada
        if sc is None:
            return False
        if sc.dead and self._out_of_window(sc, sc.rad):
            sc.state = ItemState.GONE          # 尸体被拖出窗口扔了：直接清除
            self._dragged_squidcada = None
            return True
        if sc.state == ItemState.MOUSE:
            sc.state = ItemState.FREE
        self._dragged_squidcada = None
        return True

    def _tick_squidcadas(self):
        self._step_squidcada_drag()
        if not self.squidcadas:
            return
        threats = [(pet, pet.body.chunk0.x, pet.body.chunk0.y, self._pet_armed(pet))
                   for pet in self.pets]
        for sc in self.squidcadas:
            sc._impact_cb = self._shake_impact
            sc.step(self._WL, self._HL, threats=threats,
                    look_at=self._squid_look_at(sc),
                    prey=self.batflies)       # 蝉乌贼捕食蝠蝇
        self._cull_flung_corpses()
        self.squidcadas = [sc for sc in self.squidcadas if sc.state != ItemState.EATEN]

    @staticmethod
    def _pet_armed(pet) -> bool:
        """这只猫手上有没有武器（CicadaAI.cs:645 armed）。"""
        b = pet.body
        return (getattr(b, "carried_spear", None) is not None
                or getattr(b, "carried_stone", None) is not None)

    def _squid_look_at(self, sc):
        """CicadaGraphics.creatureLooker：看向视距内最近的生物。"""
        best, bd = None, SQUID_LOOK_R
        for pet in self.pets:
            c0 = pet.body.chunk0
            d = math.hypot(c0.x - sc.x, c0.y - sc.y)
            if d < bd:
                best, bd = (c0.x, c0.y), d
        for lz in self.lizards:
            if lz.dead or lz.state != ItemState.FREE:
                continue
            d = math.hypot(lz.x - sc.x, lz.y - sc.y)
            if d < bd:
                best, bd = (lz.x, lz.y), d
        return best

    def _draw_squidcadas(self, p):
        ts = self._ts
        for sc in self.squidcadas:
            if sc.state in (ItemState.EATEN, ItemState.GONE):
                continue
            draw_squidcada(p, self.atlas, sc, ts)

    def _squidcada_hint_object(self):
        seed = self._squidcada_seed
        got = getattr(self, "_squidcada_preview", None)
        if got is None or got[0] != seed:
            got = (seed, Squidcada(0.0, 0.0, seed=seed))
            self._squidcada_preview = got
        return got[1]

    def _draw_squidcada_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        sc = self._squidcada_hint_object()
        sc.x = sc.last_x = cx
        sc.y = sc.last_y = cy
        sc.vx = sc.vy = 0.0
        sc.dir_x, sc.dir_y = 1.0, 0.0
        sc.rest = 0
        sc.facing = 1
        sc.hd = (1.0, 0.0)
        sc.zx, sc.zy = 1.0, 0.0
        sc.lzx, sc.lzy = 1.0, 0.0
        sc.lay_tentacles()             # 预览不 tick：触须得手动铺到本体前端
        p.save()
        p.setOpacity(0.5)
        draw_squidcada(p, self.atlas, sc, 1.0)
        p.restore()

    # ── 面条蝇（NeedleWorm）：卵 / 幼体 / 成体，出生年龄随机 ──
    def can_place_needleworm(self) -> bool:
        return True

    def place_needleworm(self, lx, ly):
        nw = NeedleWorm(lx, ly, seed=self._needleworm_seed)
        self._needleworm_seed += 1
        if nw.age == AGE_SMALL:               # SmallNeedleWorm.PlaceInRoom：认最近的成体当妈
            nw.mother = self._nearest_nw_adult(nw, self.needleworms)
        self.needleworms.append(nw)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return nw

    def clear_needleworms(self):
        for nw in self.needleworms:
            for pet in self.pets:
                if nw is pet.body.carried_fruit:      # 复用果子叼持槽
                    pet.body.release_fruit()
            nw.state = ItemState.EATEN
        if self.needleworms:
            self.needleworms = []
            self.world_version += 1
        self._dragged_needleworm = None
        self._needleworm_preview = None

    def enter_place_needleworm_mode(self):
        self._place_mode = True
        self._place_kind = "needleworm"
        self._begin_place_capture()
        return True

    def _needleworm_at(self, pos):
        """光标下的面条蝇（含尸体、含已摔出窗外的）。

        命中判定遍历整条体节链：旧实现只测 ``nw.x / nw.y``（身体中心）并且要求
        state ∈ {FREE, CARRIED}，于是长条虫的尾巴 / 吻部点不中、已经躺在地上的
        尸体也选不上 —— 用户报的「无法被拖动 / 单个删除也无法选中」。
        """
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for nw in self.needleworms:
            if nw.state in (ItemState.EATEN, ItemState.GONE):
                continue
            d = 1e18
            for s in nw.seg:
                ds = math.hypot(cx - s.x, cy - s.y) - s.rad
                if ds < d:
                    d = ds
            if d <= NEEDLEWORM_GRAB_PAD and d < bestd:
                best, bestd = nw, d
        return best

    def _begin_needleworm_drag(self, pos) -> bool:
        nw = self._needleworm_at(pos)
        if nw is None:
            return False
        if nw.state == ItemState.CARRIED:
            for pet in self.pets:
                if nw is pet.body.carried_fruit:
                    pet.body.release_fruit()
        nw.held_by_hand = None
        nw.state = ItemState.MOUSE
        nw.vx = nw.vy = 0.0
        nw.last_x, nw.last_y = pos
        nw.x, nw.y = pos
        nw.snap_chain()                 # 整条虫跟手，别只搬身体中心
        self._dragged_needleworm = nw
        return True

    def _step_needleworm_drag(self):
        nw = self._dragged_needleworm
        if nw is None:
            return
        if nw.state != ItemState.MOUSE:
            self._dragged_needleworm = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        nw.last_x, nw.last_y = nw.x, nw.y
        # 与拖蛞蝓猫同一手感：直接跟光标，不做限速延迟。
        nw.x, nw.y = cur
        nw.vx = nw.vy = 0.0
        nw.snap_chain()                 # seg 才是渲染 / 命中用的几何，必须同步

    def _end_needleworm_drag(self) -> bool:
        nw = self._dragged_needleworm
        if nw is None:
            return False
        if nw.dead and self._out_of_window(nw, nw.rad):
            nw.state = ItemState.GONE           # 尸体被拖出窗口扔了：直接清除
            self._dragged_needleworm = None
            return True
        if nw.state == ItemState.MOUSE:
            nw.state = ItemState.FREE
        self._dragged_needleworm = None
        return True

    def _nearest_nw_adult(self, nw, pool=None):
        """最近的成体面条蝇（母亲）——SmallNeedleWorm.PlaceInRoom 语义。"""
        best, bd = None, 1e18
        for m in (self.needleworms if pool is None else pool):
            if m is nw or m.dead or m.age != AGE_BIG:
                continue
            d = math.hypot(m.x - nw.x, m.y - nw.y)
            if d < bd:
                best, bd = m, d
        return best

    def _needleworm_cats(self):
        """组装面条蝇看到的「猫」：位置 + 两节体节 + 是否拿着幼体（BigNeedleWormAI）。"""
        out = []
        for pet in self.pets:
            body = pet.body
            c0, c1 = body.chunk0, body.chunk1
            beh = getattr(pet, "behavior", None)
            held = body.carried_fruit
            out.append({
                "uid": id(pet), "x": c0.x, "y": c0.y,
                "chunks": ((c0.x, c0.y, c0.rad, c0.last_x, c0.last_y),
                           (c1.x, c1.y, c1.rad, c1.last_x, c1.last_y)),
                "dead": bool(beh is not None and beh.is_dead()),
                "saint": getattr(pet, "variant", None) == "saint",
                "body": body, "pet": pet, "other": None,
                # BigNeedleWormAI.UpdateDynamicRelationship：拿着幼体/蛋 → Attacks
                "holds_child": isinstance(held, NeedleWorm) and held.age == AGE_SMALL,
                "holds_me": False, "small": False,
            })
        return out

    def _flying_weapons(self):
        """正在飞的投掷物 (物, 是否致命)：成体面条蝇要闪避 + 记 AttackAttempt。"""
        out = []
        for sp in self.spears:
            if sp.state == ItemState.FREE and getattr(sp, "_thrown", False):
                out.append((sp, True))
        for st in self.stones:
            if (st.state == ItemState.FREE
                    and (getattr(st, "fling", False)
                         or getattr(st, "thrown_by_saint", False))):
                out.append((st, False))
        return out

    def _prune_weapon_seen(self, weapons):
        """每 tick 清一次「已经不在飞的武器」条目（旧实现每只虫各清一遍）。"""
        seen = getattr(self, "_nw_weapon_seen", None)
        if not seen:
            return
        live = {id(w) for w, _ in weapons}
        for key in [k for k in seen if k not in live]:
            del seen[key]                      # __slots__ 挂不了属性：用 id 字典

    def _needleworm_dodge(self, nw, weapons):
        """Weapon.cs:286-294：投掷物每 tick 通知成体（120px 内掠过记一次攻击事件）。"""
        seen = getattr(self, "_nw_weapon_seen", None)
        if seen is None:
            seen = self._nw_weapon_seen = {}
        r2 = NW_ATTEMPT_DIST * NW_ATTEMPT_DIST
        for w, lethal in weapons:
            dx, dy = w.x - nw.x, w.y - nw.y
            if dx * dx + dy * dy > r2:         # 平方比较：省掉每对一次 hypot
                continue
            logged = seen.get(id(w))
            if logged is None:
                logged = seen[id(w)] = set()
            if id(nw) not in logged:
                logged.add(id(nw))
                nw.weapon_attempt(_weapon_owner(w), lethal)
            nw.on_flying_weapon(w.x, w.y, w.vx, w.vy)

    def _needleworm_hit(self, nw, ev, lethal):
        """成体獠牙命中结算：刺 = 1.22 必死；戳 = 0.05 眩晕 + 掉手上东西。"""
        cat, dmg, stun = ev
        other = cat.get("other")
        if other is not None:                  # 同族互刺（StaticWorld：Attacks 0.9）
            other.hurt(dmg, by=id(nw), lethal=True)
            self._shake[0] += 0.8
            self._shake[1] += 0.5
            return
        pet = cat.get("pet")
        beh = getattr(pet, "behavior", None) if pet is not None else None
        if beh is None:
            return
        died, stun_ticks = _pet_stun_death(dmg, stun)
        stun_ticks = int(stun_ticks * STUN_SCALE)
        if died:
            beh.kill()
            self._shake[0] += 2.0 * (1.0 if nw.x >= pet.body.chunk0.x else -1.0)
            self._shake[1] += 1.4
            return
        if beh.apply_stun(max(stun_ticks, LIZARD_STUN_TICKS)):   # apply_stun 自带掉手上东西
            self._shake[0] += 1.2 * (1.0 if nw.x >= pet.body.chunk0.x else -1.0)
            self._shake[1] += 0.8

    def _needleworm_events(self, nw, born):
        """收成体刺/戳事件 + 卵孵化（NeedleEgg：孵出 2 只幼体）。"""
        ev, nw.attack_event = nw.attack_event, None
        if ev is not None:
            self._needleworm_hit(nw, ev, True)
        ev, nw.poke_event = nw.poke_event, None
        if ev is not None:
            self._needleworm_hit(nw, ev, False)
        if nw.hatch_spawn > 0:
            n = nw.hatch_spawn
            nw.hatch_spawn = 0
            nw.state = ItemState.EATEN
            for i in range(n):
                baby = NeedleWorm(nw.x + (i * 2 - (n - 1)) * NW_HATCH_GAP, nw.y,
                                  seed=self._needleworm_seed, age=AGE_SMALL)
                self._needleworm_seed += 1
                baby.follow_cat = True         # wiki：孵出的幼体先跟着蛞蝓猫
                born.append(baby)
            self._shake[1] -= 0.4
            self._shake[0] += 0.6 * (1.0 if nw.x >= self._WL * 0.5 else -1.0)

    def _tick_needleworms(self):
        self._step_needleworm_drag()
        if not self.needleworms:
            return
        cats = self._needleworm_cats()
        adults = [nw for nw in self.needleworms if nw.age == AGE_BIG]
        weapons = self._flying_weapons()
        self._prune_weapon_seen(weapons)
        born = []
        for nw in self.needleworms:
            nw._impact_cb = self._shake_impact
            if nw.age == AGE_SMALL:
                if nw.mother is not None and nw.mother.dead:
                    nw.mother = None
                    nw.mom_seg = -1
                if nw.mother is None:
                    near = self._nearest_nw_adult(nw, adults)
                    # wiki：孵出的幼体先跟着蛞蝓猫，遇到够近的成体才改跟成体；
                    # 直接放置的幼体按 SmallNeedleWorm.PlaceInRoom 认最近的成体当妈。
                    if near is not None and (not nw.follow_cat
                            or math.hypot(near.x - nw.x, near.y - nw.y) < 260.0):
                        nw.mother = near
                        nw.follow_cat = False
            elif nw.age == AGE_BIG:
                self._needleworm_dodge(nw, weapons)
            nw.step(self._WL, self._HL, cats=cats, adults=adults, weapons=weapons)
            self._needleworm_events(nw, born)
        for baby in born:
            self.needleworms.append(baby)
        self._cull_flung_corpses()
        self.needleworms = [nw for nw in self.needleworms
                            if nw.state not in (ItemState.EATEN, ItemState.GONE)]

    def _draw_needleworms(self, p):
        ts = self._ts
        for nw in self.needleworms:
            if nw.state in (ItemState.EATEN, ItemState.GONE):
                continue
            if nw.age == AGE_EGG:
                draw_needle_egg(p, self.atlas, nw, ts)
            else:
                draw_needleworm(p, self.atlas, nw, ts)

    def _needleworm_hint_object(self):
        seed = self._needleworm_seed
        got = getattr(self, "_needleworm_preview", None)
        if got is None or got[0] != seed:
            got = (seed, NeedleWorm(0.0, 0.0, seed=seed))
            self._needleworm_preview = got
        return got[1]

    def _draw_needleworm_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        nw = self._needleworm_hint_object()
        nw.snap_to(cx, cy)             # 预览不 tick：整条链一起搬过去
        nw.facing = 1
        p.save()
        p.setOpacity(0.5)
        if nw.age == AGE_EGG:
            draw_needle_egg(p, self.atlas, nw, 1.0)
        else:
            draw_needleworm(p, self.atlas, nw, 1.0)
        p.restore()

    # ── 珍珠（Pearl）：高弹小球，可拖可掷 ──
    def can_place_pearl(self) -> bool:
        return True

    def place_pearl(self, lx, ly):
        pr = Pearl(lx, ly, seed=self._pearl_seed)
        self._pearl_seed += 1
        self.pearls.append(pr)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return pr

    def clear_pearls(self):
        for pr in self.pearls:
            if pr.state == ItemState.CARRIED and pr.held_by_hand is not None:
                for pet in self.pets:
                    if pr is pet.body.carried_fruit:
                        pet.body.release_fruit()
            pr.state = ItemState.GONE
        if self.pearls:
            self.pearls = []
            self.world_version += 1
        self._dragged_pearl = None
        self._pearl_drag_last = None

    def enter_place_pearl_mode(self):
        self._place_mode = True
        self._place_kind = "pearl"
        self._begin_place_capture()
        return True

    def _pearl_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for pr in self.pearls:
            if pr.state != ItemState.FREE:
                continue
            d = math.hypot(cx - pr.x, cy - pr.y)
            if d <= pr.rad + PEARL_GRAB_PAD and d < bestd:
                best, bestd = pr, d
        return best

    def _begin_pearl_drag(self, pos) -> bool:
        pr = self._pearl_at(pos)
        if pr is None:
            return False
        pr.state = ItemState.MOUSE
        pr.vx = pr.vy = 0.0
        pr.last_x, pr.last_y = pos
        pr.x, pr.y = pos
        self._dragged_pearl = pr
        self._pearl_drag_last = tuple(pos)
        return True

    def _step_pearl_drag(self):
        pr = self._dragged_pearl
        if pr is None:
            return
        if pr.state != ItemState.MOUSE:
            self._dragged_pearl = None
            self._pearl_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        pr.last_x, pr.last_y = pr.x, pr.y
        if self._pearl_drag_last is not None:
            pr.vx = cur[0] - self._pearl_drag_last[0]
            pr.vy = cur[1] - self._pearl_drag_last[1]
        pr.x, pr.y = cur
        self._pearl_drag_last = tuple(cur)

    def _end_pearl_drag(self) -> bool:
        pr = self._dragged_pearl
        if pr is None:
            return False
        sp = math.hypot(pr.vx, pr.vy)
        if sp > self._PEARL_FLING_CAP:
            k = self._PEARL_FLING_CAP / sp
            pr.vx *= k
            pr.vy *= k
        if pr.state == ItemState.MOUSE:
            pr.state = ItemState.FREE
            pr.spin = clampf(pr.vx * 4.0, -60.0, 60.0) * lerp(0.05, 1.0, pr.room_gravity)
        self._dragged_pearl = None
        self._pearl_drag_last = None
        return True

    def _tick_pearls(self):
        self._step_pearl_drag()
        if self.pearls:
            for pr in self.pearls:
                pr._impact_cb = self._shake_impact
                pr.step(self._WL, self._HL)
            self.pearls = [pr for pr in self.pearls if pr.state != ItemState.GONE]

    def _draw_pearls(self, p):
        ts = self._ts
        for pr in self.pearls:
            if pr.state == ItemState.GONE or pr.held_by_hand == "scav":
                continue        # 拾荒者手上的珍珠随它一起画，避免被身挡住
            x = pr.last_x + (pr.x - pr.last_x) * ts
            y = pr.last_y + (pr.y - pr.last_y) * ts
            rot = pr.last_rotation + (pr.rotation_deg - pr.last_rotation) * ts
            draw_pearl(p, self.atlas, x, y, rot, pr.tint, PEARL_ART_RAD, pr.glimmer_at(ts))

    def _draw_pearl_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        pr = self._pearl_hint_object()
        p.save()
        p.setOpacity(0.5)
        draw_pearl(p, self.atlas, cx, cy, 0.0, pr.tint, PEARL_ART_RAD, pr.glimmer_at(1.0))
        p.restore()

    def _pearl_hint_object(self):
        seed = self._pearl_seed
        got = getattr(self, "_pearl_preview", None)
        if got is None or got[0] != seed:
            got = (seed, Pearl(0.0, 0.0, seed=seed))
            self._pearl_preview = got
        return got[1]

    # ── 矛（Spear）：落地即插入立住；掷出可插墙地 ──
    def can_place_spear(self) -> bool:
        return True

    def place_spear(self, lx, ly):
        sp = Spear(lx, ly, seed=self._spear_seed)
        self._spear_seed += 1
        self.spears.append(sp)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return sp

    def clear_spears(self):
        for sp in self.spears:
            pl = sp.pole                            # 钉住的矛＝一截杆：连杆一起撤
            if pl is not None:
                if pl in self.poles:
                    self.poles.remove(pl)
                sp.pole = None
                self.geometry_version += 1
            for sc in self.scavengers:
                if sp is sc.spear:
                    sc.spear = None
            for pet in self.pets:
                if sp is getattr(pet.body, "carried_stone", None):
                    rs = getattr(pet.body, "release_stone", None)
                    if rs is not None:
                        rs()
            sp.enter_gone()
        if self.spears:
            self.spears = []
            self.world_version += 1
        self._dragged_spear = None
        self._spear_drag_last = None
        if self.needle_threads:
            self.needle_threads = []

    def enter_place_spear_mode(self):
        self._place_mode = True
        self._place_kind = "spear"
        self._begin_place_capture()
        return True

    def _spear_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for sp in self.spears:
            if sp.state != ItemState.FREE:
                continue
            # 钉进墙/地成了杆子的矛：鼠标照样能拽住（_begin_spear_drag 里会
            # unstuck，杆实体随之消失 → 恢复成普通矛）。用户口径。
            d = _dist_to_path([sp.butt(), sp.tip()], cx, cy) - SPEAR_HALF_W
            if d <= SPEAR_GRAB_PAD and d < bestd:
                best, bestd = sp, d
        return best

    def _begin_spear_drag(self, pos) -> bool:
        sp = self._spear_at(pos)
        if sp is None:
            return False
        # 钉成杆的 / 插在生物身上的都能拔下来：统一走生命周期入口
        sp.enter_free(roll=False, state=ItemState.MOUSE)
        sp.last_x, sp.last_y = pos
        sp.x, sp.y = pos
        self._dragged_spear = sp
        self._spear_drag_last = tuple(pos)
        return True

    def _step_spear_drag(self):
        sp = self._dragged_spear
        if sp is None:
            return
        if sp.state != ItemState.MOUSE:
            self._dragged_spear = None
            self._spear_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        sp.last_x, sp.last_y = sp.x, sp.y
        if self._spear_drag_last is not None:
            sp.vx = cur[0] - self._spear_drag_last[0]
            sp.vy = cur[1] - self._spear_drag_last[1]
        sp.last_angle = sp.angle_deg
        if abs(sp.vx) + abs(sp.vy) > 0.5:
            sp.angle_deg = math.degrees(math.atan2(sp.vx, -sp.vy))       # 杆顺运动方向
        sp.x, sp.y = cur
        self._spear_drag_last = tuple(cur)

    def _end_spear_drag(self) -> bool:
        """松手：甩得够快＝按原版 Weapon.Thrown 投出去（带伤害、自然下坠），否则放下。"""
        sp = self._dragged_spear
        if sp is None:
            return False
        speed = math.hypot(sp.vx, sp.vy)
        if sp.state == ItemState.MOUSE:
            sp.enter_free(roll=False)
        if speed >= SPEAR_PLAYER_THROW_MIN:
            ux, uy = sp.vx / speed, sp.vy / speed
            power = clampf(speed * SPEAR_PLAYER_POWER_K,
                           SPEAR_PLAYER_POWER_MIN, SPEAR_PLAYER_POWER_MAX)
            frc = clampf(speed * SPEAR_PLAYER_FRC_K, 0.5, 1.0)
            weaponphys.begin_thrown(sp, 1.0 if ux >= 0.0 else -1.0, frc)
            sp.vx = ux * power
            sp.vy = uy * power - weaponphys.LIFT_SPEAR   # 原版出手那一下的小上抬
            sp.angle_deg = sp.last_angle = weaponphys.vel_angle(sp.vx, sp.vy)
            sp.thrower = None
        elif speed > self._SPEAR_FLING_CAP:
            k = self._SPEAR_FLING_CAP / speed
            sp.vx *= k
            sp.vy *= k
        self._dragged_spear = None
        self._spear_drag_last = None
        return True

    def _thrower_pet(self, obj):
        """从「是谁扔的」（体节点）找回那只猫。"""
        if obj is None:
            return None
        for p in self.pets:
            if getattr(p, "body", None) is obj:
                return p
        return None

    def _friendly_fire(self, thrower, victim) -> None:
        """误伤同伴：让扔的人记下「抱歉」。（原版没有，纯性格层）"""
        tp = self._thrower_pet(thrower)
        if tp is None or tp is victim or tp.behavior is None:
            return
        if getattr(victim, "body", None) is None or victim.body.dead:
            return
        tp.behavior.apologize(victim)

    def _spear_needle_feed(self, sp, obj, was_dead: bool = False) -> bool:
        """矛大师的新鲜骨矛扎中活物 → 掷出者回饱食度，然后断开连接。

        反编译 Spear.cs:1041-1087（Spear_NeedleCanFeed + flag && !flag3）：
        必须「尾巴长出来、还连着的针」+ 掷出者是矛大师；尸体不给。
        was_dead 必须是**命中前**的死亡状态（原版 flag3 在 Violence 之前取，
        不然这一矛打死的那只就永远吃不到）。
        一根针只喂一口（喂完 Spear_NeedleDisconnect）。
        """
        if not (getattr(sp, "needle", False) and getattr(sp, "needle_live", False)):
            return False
        if was_dead:                                   # flag3：命中前就是尸体
            return False
        tp = self._thrower_pet(getattr(sp, "thrower", None))
        if tp is None or getattr(tp, "body", None) is None:
            return False
        if not getattr(getattr(tp, "cat", None), "tuning", {}).get("tail_needle"):
            return False                         # 不是矛大师掷的针
        sp.needle_disconnect()
        tp.body.food_eat(_needle_feed_amount(obj))
        return True

    def _spear_needle_feed_cob(self, sp, cb) -> bool:
        """矛大师的活针扎中爆米花 → 掷出者回饱食度（反编译 Spear.cs:1096-1108）。

        未开荚 +5（原版 AddFood(5)）；已开荚 +1（用户口径）。一根针只喂一口：
        喂完 Spear_NeedleDisconnect。开荚与否**不在这里动** —— 以嘴啃爆米花是
        另一条路（fsm._st_eatcob），矛大师没嘴，那边已经按食性拦住。
        """
        if not (getattr(sp, "needle", False) and getattr(sp, "needle_live", False)):
            return False
        tp = self._thrower_pet(getattr(sp, "thrower", None))
        if tp is None or getattr(tp, "body", None) is None:
            return False
        if not getattr(getattr(tp, "cat", None), "tuning", {}).get("tail_needle"):
            return False                         # 不是矛大师掷的针
        sp.needle_disconnect()
        tp.body.food_eat(NEEDLE_FEED_COB_OPEN if cb.opened
                         else NEEDLE_FEED_COB_CLOSED)
        return True

    def _step_spear_hit(self):
        """飞矛扎到猫：眩晕 + 震动；扎到蜥蜴：受伤并插在身上跟着走。"""
        for pet in self.pets:
            if pet.behavior is None or pet.behavior.blocks_interaction():
                continue
            b = pet.body
            for sp in self.spears:
                if sp.state != ItemState.FREE:
                    continue
                if sp.stuck and not sp._seg_new:              # 早先就停住/插住了：不再伤人
                    continue                                  # （同帧刚插住的仍算这一掷）
                if sp.thrower is b and sp.no_self_t > 0:      # 刚出手，别扎自己
                    continue
                if not (sp._thrown or sp._seg_new):           # 原版只有 Mode.Thrown 才判定命中
                    continue
                # 蛞蝓猫走全局统一扫掠（world/hitgeom.py）
                hit = HG.sweep_hit(b, sp, SPEAR_HIT_PAD)
                if hit is not None:
                    # 原版 Spear.HitSomething：Violence(Stab, spearDamageBonus=1, 20)
                    # 蛞蝓猫 num = 1.0 ≥ 即死阈值 1 ⇒ 被矛扎中即死。
                    dmg = float(getattr(sp, "damage", SPEAR_DMG))
                    died, stun = _pet_stun_death(dmg, SPEAR_STUN_BONUS)
                    stun = int(stun * STUN_SCALE)
                    if _friendly_throw_protected(self, getattr(sp, "thrower", None)):
                        pass          # 友军伤害豁免：伤害与眩晕都不给
                    elif _spear_should_protect_pet(sp, pet):
                        # 玩耍/同伴命中仍有撞击与眩晕反馈，但禁止即死。
                        self._friendly_fire(getattr(sp, "thrower", None), pet)
                        self._spear_needle_feed(sp, pet, False)
                        pet.behavior.apply_stun(max(12, min(stun, 70)))
                        sp.vx *= -0.25
                        sp.vy *= 0.25
                    else:
                        self._friendly_fire(getattr(sp, "thrower", None), pet)
                        self._spear_needle_feed(sp, pet, bool(b.dead))
                        if died:
                            pet.behavior.kill()
                        else:
                            pet.behavior.apply_stun(stun)
                    self._shake[0] += 1.6 * (1.0 if sp.vx >= 0.0 else -1.0)
                    self._shake[1] += 1.1
                    sp.pin_tip(hit[1][0], hit[1][1], hit.impact_angle)
                    sp.vx = sp.vy = 0.0
                    break
        for sp in self.spears:
            if sp.stuck_to is not None or sp.state != ItemState.FREE:
                continue
            if sp.stuck and not sp._seg_new:    # 早先就停住/插住了：不再伤人
                continue
            thrown = bool(sp._thrown or sp._seg_new)   # 原版 Mode.Thrown 才判命中
            tossed = (not thrown) and sp.toss_t > 0     # 轻抛只认爆米花（见 TOSS_COB_T）
            if not (thrown or tossed):          # HitWall 后进 Free，不再伤人（原版 Weapon.Update）
                continue
            for lz in (self.lizards if thrown else ()):
                if lz.dead:
                    continue
                hit = _ball_hit(lz, sp, SPEAR_HIT_PAD)
                if hit is None:
                    continue
                hit_chunk, (hit_x, hit_y), _hit_t = hit
                spd = math.hypot(sp.vx, sp.vy) or 1.0
                dvec = (sp.vx / spd, sp.vy / spd)
                head = (hit_chunk is lz)                     # 头是第 0 节
                shielded = head and lz.hit_head_shield(dvec)
                killed = lz.hurt(float(getattr(sp, "damage", SPEAR_DMG)),
                                 dvec=dvec, speed=spd,
                                 stun_bonus=SPEAR_STUN_BONUS, hit_head=head,
                                 knock_k=KNOCK_K_PER_MASS * sp.mass)
                if shielded and not lz.dead:
                    sp.needle_disconnect()       # 头甲弹开：原版这条也走 Mode.Free
                    # 头甲弹开：矛不插入，原速 45% 弹回（原版 directionAndMomentum / 3）
                    sp.vx, sp.vy = -sp.vx * 0.45, -sp.vy * 0.45
                    self._shake[0] += 0.6 * (1.0 if sp.vx >= 0.0 else -1.0)
                    self._shake[1] += 0.4
                    break
                self._spear_needle_feed(sp, lz)          # 骨矛吸食活物
                # 矛尖对齐到真实接触点：矛中心沿杆回退 LEN/2（tip() 的同一套几何）
                sp.pin_tip(hit_x, hit_y, hit.impact_angle)
                sp.stuck_angle = sp.angle_deg
                sp.enter_stuck_to(lz, sp.x - lz.x, sp.y - lz.y,
                                  _local_frame(lz, sp.x, sp.y, sp.angle_deg))
                self._shake[0] += 1.0 * (1.0 if dvec[0] >= 0.0 else -1.0)
                self._shake[1] += 0.6
                if killed:
                    self._lizard_death_fx(lz)
                EV.emit_for(self, EV.CREATURE_KILLED if killed else EV.CREATURE_HURT,
                            subject=_weapon_owner(sp), obj=lz,
                            intensity=1.0 if killed else 0.8,
                            x=hit_x, y=hit_y)
                break
            for sc in (self.scavengers if thrown else ()):
                if sc.dead or sc.state != ItemState.FREE:
                    continue
                sc_hit = HG.sweep_hit(sc, sp, SPEAR_HIT_PAD)
                if sc_hit is None:
                    continue
                spd = math.hypot(sp.vx, sp.vy) or 1.0
                dvec = (sp.vx / spd, sp.vy / spd)
                _sc_died = sc.hurt(float(getattr(sp, "damage", SPEAR_DMG)))
                self._spear_needle_feed(sp, sc)          # 骨矛吸食活物
                if _weapon_owner(sp) is not None:
                    sc.on_attacked(float(getattr(sp, "damage", SPEAR_DMG)))
                EV.emit_for(self,
                            EV.CREATURE_KILLED if _sc_died else EV.CREATURE_HURT,
                            subject=_weapon_owner(sp), obj=sc,
                            intensity=1.0 if _sc_died else 0.75,
                            x=sp.x, y=sp.y)
                sp.stuck_angle = sp.angle_deg      # 原序：记下撞击前的角度
                sp.pin_tip(sc_hit[1][0], sc_hit[1][1], sc_hit.impact_angle)
                sp.enter_stuck_to(sc, sp.x - sc.x, sp.y - sc.y)
                self._shake[0] += 1.0 * (1.0 if dvec[0] >= 0.0 else -1.0)
                self._shake[1] += 0.6
                break
            for cb in self.seedcobs:                          # 矛扎中爆米花 → 开荚 + 插住
                if cb.dead:
                    continue
                hit = _cob_hit(cb, sp, SPEAR_COB_PAD)
                if hit is None:
                    continue
                # 矛大师的活针：先吸一口（未开荚 +5 / 已开荚 +1，Spear.cs:1096-1108）
                was_open = cb.opened
                fed = self._spear_needle_feed_cob(sp, cb)
                if not fed and was_open:
                    continue                  # 已开荚的荚：别的矛直接穿过去（原样）
                if not was_open:
                    cb.open_cob()             # 未开荚：这一扎把荚打开（原版 Spear.cs:1103）
                kx = 1.0 if sp.vx >= 0.0 else -1.0
                sp.stuck_angle = sp.angle_deg
                sp.enter_stuck_to(cb, hit[0] - cb.x, hit[1] - cb.y)
                self._shake[0] += 0.4 * kx
                break
            for kf in (self.karmaflowers if thrown else ()):
                # 矛扎中「还扎根的业力花」＝把花从根上打下来（用户口径，只算矛大师）：
                # 花带着这一矛的力飞出去，掷出者当场记「吃过一朵」——业力花槽直接填满。
                if (getattr(kf, "grow_pos", None) is None
                        or kf.state not in (ItemState.FREE, ItemState.HANGING)):
                    continue                     # 已经离根/被吃掉的：不再判
                if _seg_dist(sp.last_x, sp.last_y, sp.x, sp.y,
                             kf.x, kf.y) >= sp.rad + KARMA_HIT_R:
                    continue
                tp = self._thrower_pet(getattr(sp, "thrower", None))
                if tp is None or not getattr(getattr(tp, "cat", None),
                                             "tuning", {}).get("tail_needle"):
                    continue                     # 只有矛大师打得到（别的猫穿过去）
                kd = math.hypot(sp.vx, sp.vy) or 1.0
                kf.pluck(sp.vx / kd * 4.5, min(sp.vy / kd * 4.5 - 2.0, -1.5))
                tp.body.flower_karma = True      # 视作已食用：业力花槽填满
                for _ in range(6):               # 打落那一下的金色火星
                    a = self._stun_rng.random() * 2.0 - 1.0
                    c = self._stun_rng.random() * 2.0 - 1.0
                    s2 = 2.0 + 8.0 * self._stun_rng.random()
                    self.add_spark(kf.x + a * 4.0, kf.y + c * 4.0,
                                   a * s2, c * s2 - 1.0, True, 22)
                self._shake[0] += 0.5 * (1.0 if sp.vx >= 0.0 else -1.0)
                sp.vx *= 0.4
                sp.vy *= 0.4
                break
            for small in ((*self.batflies, *self.squidcadas,
                           *self.needleworms) if thrown else ()):   # 小生物：一矛带走
                if small.dead or small.state != ItemState.FREE:
                    continue
                if _small_hit(small, sp, SPEAR_HIT_PAD) is None:
                    continue
                kx = sp.vx * 0.10
                ky = min(sp.vy * 0.10 - 1.2, -1.0)
                small.hurt(float(getattr(sp, "damage", SPEAR_DMG)),
                           kx=kx, ky=ky, by=_weapon_owner(sp), lethal=True)
                self._spear_needle_feed(sp, small)       # 骨矛吸食活物
                sp.vx *= 0.55
                self._shake[0] += 0.5 * (1.0 if kx >= 0.0 else -1.0)
                break
        for sp in self.spears:
            sp._seg_new = False          # 这段位移判过了

    def _step_spear_clash(self):
        """空中两矛相撞：两边一起无效弹开（原版 Weapon 之间的碰撞）。

        不插任何东西、不造成伤害，各自进翻滚继续飞 —— 用户点名的
        「在空中与另一只矛相撞」这一条。
        """
        live = [sp for sp in self.spears
                if sp.state == ItemState.FREE and sp.stuck_to is None
                and not sp.stuck and (sp._thrown or sp._seg_new) and sp.moving()]
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                r = a.rad + b.rad + SPEAR_HIT_PAD
                if _seg_dist(a.last_x, a.last_y, a.x, a.y, b.x, b.y) > r:
                    continue
                if _seg_dist(b.last_x, b.last_y, b.x, b.y, a.x, a.y) > r:
                    continue
                dx, dy = a.x - b.x, a.y - b.y
                d = math.hypot(dx, dy) or 1.0
                ux, uy = dx / d, dy / d
                a.bounce_off(ux, uy)
                b.bounce_off(-ux, -uy)
                self._shake[0] += 0.5 * (1.0 if ux >= 0.0 else -1.0)
                self._shake[1] += 0.3

    def _tick_spears(self):
        self._step_spear_drag()
        self._needle_thread_tick()
        if self.spears:
            for sp in self.spears:
                sp.needle_tick()                 # 骨针断线后每 tick 褪一点
                if sp.cursor_pin is not None:    # 钉在光标上：跟着光标走，甩鼠标脱钉
                    if self._step_cursor_pin(sp):
                        continue
                if sp.stuck_to is not None:      # 插在生物身上：跟着它走
                    host, ox, oy = sp.stuck_to
                    if host.state == ItemState.GONE:
                        sp.needle_disconnect(cut=True)   # 宿主被删：线跟着一起没
                        sp.enter_free(roll=False)
                    elif sp.stuck_local is not None and _step_stuck_local(sp, sp.stuck_local):
                        continue                 # 按身体节局部坐标：身体转，矛跟着转
                    else:
                        sp.last_x, sp.last_y = sp.x, sp.y
                        sp.x, sp.y = host.x + ox, host.y + oy
                        continue
                sp._impact_cb = self._shake_impact
                sp.step(self._WL, self._HL)
                if (sp.aim_cursor and sp._thrown and sp.moving()
                        and self._cursor_pin_try(sp)):
                    continue
            self._step_spear_hit()
            self._step_spear_clash()
            self.spears = [sp for sp in self.spears if sp.state != ItemState.GONE]
        self._sync_spear_poles()

    # ── 钉在光标上的矛（猎手怪癖）──
    def _step_cursor_pin(self, sp) -> bool:
        """推进一支钉在光标上的矛；返回 True = 本 tick 这只矛不再走普通物理。"""
        cur = getattr(self, "_cursor_world", None)
        prev = getattr(self, "_cursor_pin_prev", None)
        self._cursor_pin_prev = cur
        ox, oy = sp.cursor_pin
        if cur is None:
            sp.cursor_pin = None
            return False
        vx = 0.0 if prev is None else cur[0] - prev[0]
        vy = 0.0 if prev is None else cur[1] - prev[1]
        if math.hypot(vx, vy) >= self.CURSOR_PIN_SLIP_V:
            # 甩鼠标：钉不住，带着光标这一下的速度脱钉飞出去（再自由落体）
            sp.cursor_pin = None
            sp.last_x, sp.last_y = sp.x, sp.y
            sp.vx, sp.vy = vx, vy
            sp.angle_deg = sp.last_angle = math.degrees(math.atan2(vy, vx))
            sp.enter_free(roll=False)
            return False
        sp.last_x, sp.last_y = sp.x, sp.y
        sp.x, sp.y = cur[0] + ox, cur[1] + oy
        sp._seg_x, sp._seg_y = sp.x, sp.y
        sp._seg_new = False
        return True

    # ── 矛大师的有机细线（Spear.Umbilical，Spear.cs:714）──
    def _thrower_tail_pos(self, sp):
        """掷出者尾巴根的世界坐标（原版 tail[0].pos）；找不到返回 None。"""
        pet = self._thrower_pet(getattr(sp, "thrower", None))
        if pet is None:
            return None
        segs = getattr(getattr(pet, "tail", None), "segs", None)
        if not segs:
            return None
        s = segs[0]
        return (s.x, s.y)

    def _needle_thread_tick(self):
        """活针出手时从尾巴根拉出一条细有机线。

        消失时机：
          ① 拉出后 2 秒开始渐隐、约 3 秒褪尽（用户口径，见 NeedleThread.update）；
          ② 这根针这个实体被删掉（不在 self.spears 里）；
          ③ 下一根活针出现（掷出）—— 线只跟着最新那根活针；
          ④ 这根针褪成黑色 / 线被剪断（needle_fade==0 / needle_thread_cut）。
        针扎中生物 / 插进墙 / 落地都不再**立刻**断线（线照挂到寿命结束）。
        """
        ths = self.needle_threads
        live = {id(sp) for sp in self.spears}
        # ① 针实体被删掉 ② 针已褪成黑色（fade==0）③ 被二次捡起 / 宿主被删
        ths[:] = [t for t in ths
                  if not t.dead and id(t.spear) in live
                  and getattr(t.spear, "needle_fade", 0) > 0
                  and not getattr(t.spear, "needle_thread_cut", False)]
        cands = [sp for sp in self.spears                                   # ②
                 if (getattr(sp, "needle", False)
                     and getattr(sp, "needle_live", False) and sp._thrown
                     and not getattr(sp, "needle_thread_done", False))]
        if cands:
            keep = cands[-1]                       # 最新那根活针
            if not any(t.spear is keep for t in ths):
                for t in ths:                      # 被顶替的旧针：不许回头再补一条线
                    sp0 = getattr(t, "spear", None)
                    if sp0 is not None:
                        sp0.needle_thread_done = True
                ths[:] = []                        # 旧的线让位
                tail = self._thrower_tail_pos(keep)
                if tail is not None:
                    # 每根针一条独立的确定性随机流，不去扰动矛自己的 spin 随机数
                    th = NeedleThread(tail, keep.vx, keep.vy,
                                      random.Random(int(keep._id) * 7919 + 13))
                    th.spear = keep
                    ths.append(th)
        for th in ths:                               # 端点每 tick 钉到尾巴根 / 针尾
            head = self._thrower_tail_pos(th.spear)
            if head is None:
                head = th.last_head                  # 掷出者不在了：线头留在原地
            th.update(head, th.spear.butt())
        keep = []
        for th in ths:                               # 褪尽的线：别再给同一根针重拉
            if th.dead:
                sp = getattr(th, "spear", None)
                if sp is not None:
                    sp.needle_thread_done = True
            else:
                keep.append(th)
        ths[:] = keep

    def _draw_needle_threads(self, p):
        """画在猫与生物之前：细线永远压在它们下面。"""
        for th in self.needle_threads:
            th.draw(p)

    def _cursor_pin_try(self, sp) -> bool:
        """这一 tick 飞过的那一段有没有穿过光标：有就钉上去。"""
        cur = getattr(self, "_cursor_world", None)
        if cur is None:
            return False
        from ..behavior.fetch import _seg_point_dist
        if _seg_point_dist(sp.last_x, sp.last_y, sp._seg_x, sp._seg_y,
                           cur[0], cur[1]) > self.CURSOR_PIN_R:
            return False
        sp.enter_free(roll=False)
        sp.aim_cursor = False
        sp.cursor_pin = (sp.x - cur[0], sp.y - cur[1])
        sp.vx = sp.vy = 0.0
        return True

    # ── 钉住的矛＝对应长度的杆（原版 Spear.cs:435 stuckInWall → horizontal/verticalBeam）──
    def _make_spear_pole(self, sp):
        """给钉住的矛注册一截同长的杆：竖着钉的成竖杆，横着钉的成横杆。

        原版 Spear.Update 把 stuckInWall 的那一格标成 verticalBeam / horizontalBeam ——
        即这枝矛本身就是一截杆。端点取矛的杆尖/杆尾，并裁进窗口（埋进墙里的那截不该
        让猫爬出屏幕）。杆只参与攀爬，不渲染（渲染走矛自己的贴图）。
        """
        from .pole import Pole, VERTICAL, HORIZONTAL
        tx, ty = sp.tip()
        bx, by = sp.butt()
        if abs(ty - by) >= abs(tx - bx):                 # 立着钉 → 竖杆
            x = min(max(sp.x, POLE_RAD), self._WL - POLE_RAD)
            top, bot = (ty, by) if ty <= by else (by, ty)
            pl = Pole(VERTICAL, x, bot, x, top, seed=self._pole_seed)
        else:                                            # 横着钉 → 横杆
            y = min(max(sp.y, POLE_RAD), self._HL - POLE_RAD)
            left, right = (tx, bx) if tx <= bx else (bx, tx)
            pl = Pole(HORIZONTAL, max(left, 0.0), y, min(right, self._WL), y,
                      seed=self._pole_seed)
        self._pole_seed += 1
        pl.from_spear = sp
        self.poles.append(pl)
        self.world_version += 1
        self.geometry_version += 1
        return pl

    def _sync_spear_poles(self):
        """钉住的矛与杆实体保持一致（猫随时能爬上去；拔出/清除即消失）。"""
        # 先扫幽灵杆：矛褪尽成 GONE 的那一 tick 已经从 self.spears 里剔除，
        # 下面那圈就再也看不到它 —— 不扫的话会留下一根**看不见、却还能爬**的杆
        # （骨针成杆后又有了渐隐生命周期，这条从「理论」变成真会走到）。
        live = {id(sp) for sp in self.spears}
        for pl in list(self.poles):
            sp = getattr(pl, "from_spear", None)
            if sp is not None and id(sp) not in live:
                self.poles.remove(pl)
                pl.state = ItemState.GONE
                self.geometry_version += 1
        for sp in self.spears:
            pl = sp.pole
            if pl is not None and (not sp.pinned or sp.state != ItemState.FREE):
                if pl in self.poles:
                    self.poles.remove(pl)
                pl.state = ItemState.GONE
                sp.pole = None
                self.geometry_version += 1
            elif pl is None and sp.pinned and sp.state == ItemState.FREE:
                sp.pole = self._make_spear_pole(sp)

    def _back_spear_set(self):
        """当前被某只猫背在背上的矛（这些要画在猫身体之后）。"""
        out = set()
        for pet in self.pets:
            bs = getattr(pet.body, "back_spear", None)
            if bs is not None:
                out.add(id(bs))
        return out

    def _low_spear_set(self):
        """要画在「蛞蝓猫 + 生物」之前的低层矛：手上拿着的 + 扎在生物身上的。

        扎在地形里成杆的矛不算：那是场景物件，仍画在上层。
        """
        out = set()
        back = self._back_spear_set()
        for sp in self.spears:
            if id(sp) in back:                 # 背上的矛归 _draw_back_spears
                continue
            if sp.held_by is not None or sp.stuck_to is not None:
                out.add(id(sp))
        return out

    def _draw_one_spear(self, p, sp):
        """一支矛的贴图（含掷出拖尾）：低层／上层两处共用同一份几何。"""
        ts = self._ts
        x = sp.last_x + (sp.x - sp.last_x) * ts
        y = sp.last_y + (sp.y - sp.last_y) * ts
        ang = sp.stuck_angle if sp.stuck else _ang_lerp(sp.last_angle, sp.angle_deg, ts)
        if sp._thrown and sp.state == ItemState.FREE:
            spd = math.hypot(sp.vx, sp.vy)
            if spd > SPEAR_TRAIL_MIN_SPEED:
                draw_stone_trail(p, x, y, sp.vx / spd, sp.vy / spd,
                                 min(spd * SPEAR_TRAIL_LEN_K, SPEAR_TRAIL_LEN_MAX),
                                 SPEAR_TRAIL_HALFW, SPEAR_TRAIL_COLOR, SPEAR_TRAIL_ALPHA)
        if getattr(sp, "needle", False):
            # 矛大师的骨针：BioSpear 贴图 + 断线褪色（Spear.cs:1333-1356）
            draw_needle(p, self.atlas, x, y, ang,
                        kind=getattr(sp, "needle_type", 0),
                        fade=float(getattr(sp, "needle_fade", 0)) / NEEDLE_FADE_MAX,
                        live=bool(getattr(sp, "needle_live", False)),
                        pivot_at_tip=bool(sp._thrown or sp.stuck_to is not None),
                        length=SPEAR_DRAW_LEN,
                        pinned=bool(getattr(sp, "pinned", False)),
                        alpha=float(getattr(sp, "needle_alpha", 1.0)))
        else:
            draw_spear(p, self.atlas, x, y, ang, length=SPEAR_DRAW_LEN)

    def _draw_back_spears(self, p):
        """背上的矛：画在猫之前（原版 spearOnBack 归 body 层，不该压在猫身上）。"""
        back = self._back_spear_set()
        for sp in self.spears:
            if id(sp) in back:
                self._draw_one_spear(p, sp)

    def _draw_low_spears(self, p):
        """手上拿的 / 扎在生物身上的矛：画在猫与生物之前。

        用户口径：被拿着的矛、扎进蜥蜴／拾荒者身体的矛，都不该盖住生物本体
        （它们跟着身体走，压在上层看起来就像贴在身上）。
        """
        low = self._low_spear_set()
        for sp in self.spears:
            if id(sp) in low:
                self._draw_one_spear(p, sp)

    def _draw_spears(self, p):
        skip = self._back_spear_set() | self._low_spear_set()
        for sp in self.spears:
            if id(sp) not in skip:
                self._draw_one_spear(p, sp)

    def _draw_spear_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        p.save()
        p.setOpacity(0.5)
        draw_spear(p, self.atlas, cx, cy, 90.0, length=SPEAR_DRAW_LEN)
        p.restore()

    # ── 拾荒者（Scavenger）：持矛巡走，见威胁瞄准投矛 ──
    def can_place_scavenger(self) -> bool:
        return True

    def cat_variant(self) -> str:
        """当前窗口猫的皮（拾荒者的初始好感按 wiki 起始声望表）。"""
        return getattr(self.pets[0], "variant", "saint") if self.pets else "saint"

    def place_scavenger(self, lx, ly):
        sc = Scavenger(lx, ly, seed=self._scavenger_seed, id=self._scavenger_seed,
                       variant=self.cat_variant())
        self._scavenger_seed += 1
        self.scavengers.append(sc)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return sc

    def clear_scavengers(self):
        for sc in self.scavengers:
            if sc.spear is not None and sc.spear not in self.spears:
                sc.spear.state = ItemState.GONE
            sc.die()
        if self.scavengers:
            self.scavengers = []
            self.world_version += 1
        self._dragged_scavenger = None
        self._scavenger_preview = None

    def enter_place_scavenger_mode(self):
        self._place_mode = True
        self._place_kind = "scavenger"
        self._begin_place_capture()
        return True

    def _scavenger_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for sc in self.scavengers:
            if sc.state != ItemState.FREE:
                continue
            d = math.hypot(cx - sc.x, cy - (sc.y - SCAV_STAND_H * 0.5))
            if d <= sc.rad + SCAVENGER_GRAB_PAD and d < bestd:
                best, bestd = sc, d
        return best

    def _begin_scavenger_drag(self, pos) -> bool:
        sc = self._scavenger_at(pos)
        if sc is None:
            return False
        sc.grab(pos)
        sc.last_x, sc.last_y = pos
        sc.x, sc.y = pos
        self._dragged_scavenger = sc
        return True

    def _step_scavenger_drag(self):
        """手里的拾荒者由 Scavenger._step_held 跟随光标；这里只清失效引用。"""
        sc = self._dragged_scavenger
        if sc is not None and sc.state != ItemState.MOUSE:
            self._dragged_scavenger = None

    def _end_scavenger_drag(self) -> bool:
        sc = self._dragged_scavenger
        if sc is None:
            return False
        if sc.dead and self._out_of_window(sc, sc.rad):
            sc.state = ItemState.GONE          # 尸体被拖出窗口扔了：直接清除
            self._dragged_scavenger = None
            return True
        sc.release(0.0, 0.0)
        self._dragged_scavenger = None
        return True

    # ── 爆米花（Popcorn Plant / SeedCob）：吊在天花板，矛或超度开荚弹种子 ──
    def can_place_seedcob(self) -> bool:
        return True

    def place_seedcob(self, lx, ly):
        if not self.can_place_seedcob():
            return None
        cb = SeedCob(lx, ly, seed=self._seedcob_seed, root_y=self._HL)
        self._seedcob_seed += 1
        self.seedcobs.append(cb)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return cb

    def clear_seedcobs(self):
        for cb in self.seedcobs:
            cb.state = ItemState.GONE
        if self.seedcobs:
            self.seedcobs = []
            self.world_version += 1
        self._dragged_seedcob = None

    def clear_seeds(self):
        for s in self.seeds:
            if s.state == ItemState.CARRIED:
                s.held_by_hand = None
                for pet in self.pets:
                    if s is pet.body.carried_fruit:
                        pet.body.release_fruit()
            s.state = ItemState.EATEN
        if self.seeds:
            self.seeds = []
            self.world_version += 1

    def spawn_seed(self, x, y):
        """SeedCob.burst 的回调：弹出一颗可食种子。"""
        s = Seed(x, y, seed=self._seed_seed)
        self._seed_seed += 1
        s.vx = random.uniform(-3.5, 3.5)
        s.vy = random.uniform(-4.5, -1.5)
        s.room_gravity = self.room_gravity
        self.seeds.append(s)
        self.world_version += 1
        return s

    def enter_place_seedcob_mode(self):
        self._place_mode = True
        self._place_kind = "seedcob"
        self._begin_place_capture()
        return True

    def _seedcob_at(self, pos):
        """命中豆荚段（p1→p0）或挂点附近。"""
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for cb in self.seedcobs:
            if cb.state != ItemState.FREE:
                continue
            d = _dist_to_path((cb.p0, cb.p1), cx, cy)
            d = min(d, math.hypot(cx - cb.root_pos[0], cy - cb.root_pos[1]))
            if d <= cb.rad + self._SEEDCOB_GRAB_PAD and d < bestd:
                best, bestd = cb, d
        return best

    def _begin_seedcob_drag(self, pos) -> bool:
        cb = self._seedcob_at(pos)
        if cb is None:
            return False
        self._dragged_seedcob = cb
        return True

    def _step_seedcob_drag(self):
        cb = self._dragged_seedcob
        if cb is None or cb.state != ItemState.FREE:
            self._dragged_seedcob = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        # 只拖不改植株：给豆荚一个拖拽目标，由弹簧自己弹回
        cb.drag_point = (clampf(cur[0], 20.0, self._WL - 20.0),
                         clampf(cur[1], 40.0, self._HL - 10.0))

    def _end_seedcob_drag(self) -> bool:
        if self._dragged_seedcob is None:
            return False
        self._dragged_seedcob.drag_point = None
        self._dragged_seedcob = None
        return True

    def _tick_seedcobs(self):
        self._step_seedcob_drag()
        if self.seedcobs:
            for cb in self.seedcobs:
                cb.root_y = self._HL             # 扎根窗口底边（地面）
                if cb.root_pos[1] != cb.root_y:
                    cb.root_pos = (cb.root_pos[0], cb.root_y)
                cb.step(self._WL, self._HL)
            self.seedcobs = [cb for cb in self.seedcobs if cb.state != ItemState.GONE]
        if self.seeds:
            for s in self.seeds:
                s._impact_cb = self._shake_impact
                s.step(self._WL, self._HL)
            self.seeds = [s for s in self.seeds
                          if s.state not in (ItemState.EATEN, ItemState.GONE)]

    def _draw_seedcobs(self, p):
        for cb in self.seedcobs:
            if cb.state == ItemState.GONE:
                continue
            draw_seedcob(p, self.atlas, cb, self._ts)

    def _draw_seeds(self, p):
        for s in self.seeds:
            if s.state in (ItemState.EATEN, ItemState.GONE,
                           ItemState.CARRIED, ItemState.MOUSE):
                continue
            draw_seed(p, self.atlas, s, self._ts)

    def _seedcob_hint_object(self):
        seed = self._seedcob_seed
        got = getattr(self, "_seedcob_preview", None)
        if got is None or got[0] != seed:
            got = (seed, SeedCob(0.0, 0.0, seed=seed, root_y=self._HL))
            self._seedcob_preview = got
        return got[1]

    def _draw_seedcob_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        cb = self._seedcob_hint_object()
        cb.retarget(cx, cy)
        p.save()
        p.setOpacity(0.5)
        draw_seedcob(p, self.atlas, cb, 1.0)
        p.restore()

    # ── 业力花（Karma Flower）：金色小花；啃 4 口 → 业力花条（隐藏，一格）──
    def can_place_karmaflower(self) -> bool:
        return True

    def place_karmaflower(self, lx, ly):
        """手动放置：和爆米花一致只长在窗口地面上（ly 只用来定位 x），高度固定。"""
        if not self.can_place_karmaflower():
            return None
        kf = KarmaFlower(lx, self._HL, seed=self._karmaflower_seed, ground_y=self._HL)
        self._karmaflower_seed += 1
        self.karmaflowers.append(kf)
        self.world_version += 1
        self._exit_place_mode()
        self.update()
        return kf

    def enter_place_karmaflower_mode(self):
        if not self.can_place_karmaflower():
            return False
        self._place_mode = True
        self._place_kind = "karmaflower"
        self._begin_place_capture()
        return True

    def spawn_karma_flower(self, x, y):
        """直接长出一朵业力花（死亡排期到点后调用）：只长在窗口地面上。"""
        kf = KarmaFlower(x, self._HL, seed=self._karmaflower_seed, ground_y=self._HL)
        self._karmaflower_seed += 1
        self.karmaflowers.append(kf)
        self.world_version += 1
        return kf

    def schedule_karma_flower(self, x, y, delay_ticks: int):
        """排期：delay_ticks 之后在 (x, y) 原地长出一朵业力花。

        原版 Player.PlaceKarmaFlower 只把 karmaFlowerGrowPos 记进存档，等下一个
        雨循环才在房间里长出来；桌宠没有循环，所以按用户口径给一个可见延迟。
        """
        self._karma_flower_spawns.append([float(x), float(y), int(delay_ticks)])

    def clear_karmaflowers(self):
        for kf in self.karmaflowers:
            if kf.state == ItemState.CARRIED:
                for pet in self.pets:
                    if kf is pet.body.carried_fruit:
                        pet.body.release_fruit()
            kf.state = ItemState.GONE
        if self.karmaflowers:
            self.karmaflowers = []
            self.world_version += 1
        self._dragged_karmaflower = None
        self._karmaflower_drag_last = None

    def pending_karma_flowers(self) -> int:
        """还没长出来的业力花（排期数量）。"""
        return len(self._karma_flower_spawns)

    def _karmaflower_at(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        best, bestd = None, 1e9
        for kf in self.karmaflowers:
            if kf.state != ItemState.FREE:
                continue
            d = math.hypot(cx - kf.x, cy - kf.y)
            if d <= kf.rad + self._KARMAFLOWER_GRAB_PAD and d < bestd:
                best, bestd = kf, d
        return best

    def _begin_karmaflower_drag(self, pos) -> bool:
        kf = self._karmaflower_at(pos)
        if kf is None:
            return False
        kf.held_by_hand = None
        kf.state = ItemState.MOUSE
        if kf.grow_pos is None:
            kf.detach_to(pos[0], pos[1])  # 已经断根：像拖物品一样自由拖
        else:
            kf.begin_drag(pos[0], pos[1])  # 还扎在地上：软拖（根不动，花头朝光标歪）
        self._dragged_karmaflower = kf
        self._karmaflower_drag_last = tuple(pos)
        return True

    def _step_karmaflower_drag(self):
        kf = self._dragged_karmaflower
        if kf is None:
            return
        if kf.state != ItemState.MOUSE:
            self._dragged_karmaflower = None
            self._karmaflower_drag_last = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        if kf.grow_pos is not None:        # 扎根：软拖 —— 花头朝光标歪、根不动（茎被抻长＝受力）
            kf.begin_drag(cur[0], cur[1])
            if kf.drag_pull() > KARMA_DRAG_POP:
                kx = ky = 0.0
                if self._karmaflower_drag_last is not None:
                    kx = cur[0] - self._karmaflower_drag_last[0]
                    ky = cur[1] - self._karmaflower_drag_last[1]
                kf.pluck(kx, ky)           # 拉到极限：连根拔起并把拽速继承给花体
                self._karmaflower_drag_last = tuple(cur)
            return
        kf.last_x, kf.last_y = kf.x, kf.y
        if self._karmaflower_drag_last is not None:
            kf.vx = cur[0] - self._karmaflower_drag_last[0]
            kf.vy = cur[1] - self._karmaflower_drag_last[1]
        kf.x, kf.y = cur
        kf.carry_parts()                   # 花瓣/茎整块跟着，不拉丝
        self._karmaflower_drag_last = tuple(cur)

    def _end_karmaflower_drag(self) -> bool:
        kf = self._dragged_karmaflower
        if kf is None:
            return False
        kf.end_drag()
        sp = math.hypot(kf.vx, kf.vy)
        if sp > self._FRUIT_FLING_CAP:
            k = self._FRUIT_FLING_CAP / sp
            kf.vx *= k
            kf.vy *= k
        if kf.state == ItemState.MOUSE:
            kf.state = ItemState.FREE
        self._dragged_karmaflower = None
        self._karmaflower_drag_last = None
        return True

    def _tick_karmaflowers(self):
        self._step_karmaflower_drag()
        if self._karma_flower_spawns:          # 死亡排期到点 → 长花
            left = []
            for sp in self._karma_flower_spawns:
                sp[2] -= 1
                if sp[2] <= 0:
                    self.spawn_karma_flower(sp[0], sp[1])
                else:
                    left.append(sp)
            self._karma_flower_spawns = left
        if self.karmaflowers:
            for kf in self.karmaflowers:
                kf._impact_cb = self._shake_impact
                kf.step(self._WL, self._HL)
            # EATEN 也要清：bites 归零＝4 片花瓣全啃掉，连茎带花整个消失
            # （原版 Consume() 把整株从房间里删掉，不留残茎）
            self.karmaflowers = [kf for kf in self.karmaflowers
                                 if kf.state not in (ItemState.GONE, ItemState.EATEN)]

    def _draw_karmaflowers(self, p):
        for kf in self.karmaflowers:
            if kf.state == ItemState.GONE:
                continue
            draw_karmaflower(p, self.atlas, kf, self._ts)

    def _karmaflower_hint_object(self):
        seed = self._karmaflower_seed
        got = getattr(self, "_karmaflower_preview", None)
        if got is None or got[0] != seed:
            kf = KarmaFlower(0.0, 0.0, seed=seed, ground_y=self._HL)
            for _ in range(140):           # 预览不 tick：解算过生长动画 + 随机初态张开后的样子
                kf.step(self._WL, self._HL)
            got = (seed, kf)
            self._karmaflower_preview = got
        return got[1]

    def _draw_karmaflower_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        kf = self._karmaflower_hint_object()
        dx = clampf(cx, 6.0, self._WL - 6.0) - kf.grow_pos[0]
        dy = self._HL - kf.grow_pos[1]
        kf.shift(dx, dy)                   # 预览图整个挪到光标处（与放置同 seed ⇒ 所见即所得）
        p.save()
        p.setOpacity(0.5)
        draw_karmaflower(p, self.atlas, kf, 1.0)
        p.restore()
        kf.shift(-dx, -dy)

    def _step_scavenger_throws(self):
        """拾荒者的投矛意图 → 生成一枝飞矛（原版 Scavenger.ThrowObject → Weapon.Thrown）。"""
        for sc in self.scavengers:
            ev = sc.throw_event
            if ev is None:
                continue
            sc.throw_event = None
            hx, hy = sc.head_pos()
            dir_x = 1 if ev[0] >= hx else -1
            frc = (weaponphys.FRC_SCAVENGER_ELITE if sc.ivar.get("elite")
                   else weaponphys.FRC_SCAVENGER)
            sp = Spear(hx, hy, seed=self._spear_seed,
                       angle_deg=90.0 if dir_x > 0 else 270.0)
            self._spear_seed += 1
            sp.vx, sp.vy = weaponphys.throw_velocity(sc, dir_x, True, frc)
            weaponphys.begin_thrown(sp, dir_x, frc)
            self.spears.append(sp)

    def _tick_scavengers(self):
        self._step_scavenger_drag()
        if not self.scavengers:
            return
        cur = self.cursor_logical()
        # 原版 ScavengerAI 按「体节」选投掷点：把每个威胁的体节点都传过去
        threats = [(lz, [(lz.x, lz.y)] + [(s.x, s.y) for s in lz.seg], False)
                   for lz in self.lizards if lz.state == ItemState.FREE]
        threats += [(pet, [(pet.body.chunk0.x, pet.body.chunk0.y),
                           (pet.body.chunk1.x, pet.body.chunk1.y)], True)
                    for pet in self.pets]
        self._assign_pearl_targets()
        for sc in self.scavengers:
            sc.step(self._WL, self._HL, threats=threats, cursor=cur)
            # 拾荒者也在同一张认领板上占位：它奔哪颗珍珠，那颗珍珠在猫眼里
            # 就是「有主」的（原版 CollectScore(DataPearl)=10）
            bd = board_for(self)
            live = (not sc.dead) and sc.state == ItemState.FREE
            bd.register_actor(sc, sc.goal_pearl if live else None, "trade")
        separate_scavengers(self.scavengers, self._WL)   # 支配度决定站位
        self._step_scavenger_throws()
        self._step_scavenger_trade()
        self.scavengers = [sc for sc in self.scavengers if sc.state != ItemState.GONE]

    # ── 珍珠交易（原版 ScavengerAI.CollectScore(DataPearl)=10 → bringPearlHome）──
    def nearest_scavenger(self, x):
        """最近的在场上拾荒者（猫拿珍珠去交易的目标）。"""
        best, bd = None, 1e9
        for sc in self.scavengers:
            if sc.dead or sc.state != ItemState.FREE:
                continue
            d = abs(sc.x - x)
            if d < bd:
                best, bd = sc, d
        return best

    def _assign_pearl_targets(self):
        """给还没拿珍珠的拾荒者就近指派地上的珍珠。"""
        free = [pr for pr in self.pearls if pr.state == ItemState.FREE]
        if not free:
            return
        taken = {id(sc.goal_pearl) for sc in self.scavengers if sc.goal_pearl is not None}
        for sc in self.scavengers:
            if sc.goal_pearl is not None or sc.pearl is not None or sc.friendly:
                continue
            if sc.state in ("aim", "flee") or sc.state != ItemState.FREE:
                continue
            best, bd = None, PEARL_SEEK_R
            for pr in free:
                if id(pr) in taken:
                    continue
                d = math.hypot(pr.x - sc.x, pr.y - sc.y)
                if d < bd:
                    best, bd = pr, d
            if best is not None:
                sc.goal_pearl = best
                taken.add(id(best))

    def _step_scavenger_trade(self):
        """捡珍珠 / 收下猫递来的珍珠 / 回礼一根矛。"""
        for sc in self.scavengers:
            # 1) 走到珍珠跟前就捡起来
            gp = sc.goal_pearl
            if gp is not None:
                if gp.state != ItemState.FREE:
                    sc.goal_pearl = None
                elif (math.hypot(gp.x - sc.x, gp.y - sc.y)
                      <= SCAV_BODY_RAD + gp.rad + PEARL_TAKE_PAD):
                    sc.receive_pearl(gp)
                    self._trade_fx(sc, gp)
            # 2) 猫手里举着珍珠凑过来 → 原版 RecognizeCreatureAcceptingGift
            if sc.pearl is None:
                for pet in self.pets:
                    if pet.behavior is None or pet.behavior.blocks_interaction():
                        continue
                    item = pet.body.carried_fruit
                    if not isinstance(item, Pearl):
                        continue
                    c1 = pet.body.chunk1
                    if math.hypot(c1.x - sc.x, c1.y - sc.y) > 46.0:
                        continue
                    pet.body.release_fruit()
                    sc.receive_pearl(item)
                    self._trade_fx(sc, item)
                    break
            # 3) 回礼：在原版是 Scavenger 把手上的东西（矛）让给玩家
            if sc.gift_event:
                sc.gift_event = False
                sp = Spear(sc.x + sc.facing * 14.0, sc.y - 2.0,
                           seed=self._spear_seed, angle_deg=90.0)
                self._spear_seed += 1
                sp.vx = sc.facing * 1.2
                self.spears.append(sp)
                self._trade_fx(sc, None)

    def hand_pearl(self, sc) -> bool:
        """把猫手里的珍珠交给拾荒者（原版 RecognizeCreatureAcceptingGift）。"""
        for pet in self.pets:
            item = pet.body.carried_fruit
            if isinstance(item, Pearl):
                pet.body.release_fruit()
                sc.receive_pearl(item)
                self._trade_fx(sc, item)
                return True
        return False

    def _trade_fx(self, sc, pearl):
        """交易反馈：一圈暖色火花。"""
        rng = self._stun_rng
        cx = pearl.x if pearl is not None else sc.x
        cy = (pearl.y if pearl is not None else sc.y - 10.0)
        for i in range(12):
            a = rng.uniform(0.0, math.tau)
            sp = rng.uniform(1.0, 2.4)
            self.sparks.append([cx, cy, math.cos(a) * sp, math.sin(a) * sp - 0.5,
                                20, 20, 1 if i % 2 else 0])



    def _draw_scavengers(self, p):
        ts = self._ts
        for sc in self.scavengers:
            if sc.state == ItemState.GONE:
                continue
            draw_scavenger(p, self.atlas, sc, ts, sc.body_rgb, sc.head_rgb, sc.eye_rgb)
            if sc.spear is not None:
                draw_scavenger_spear(p, self.atlas, sc, ts)
            if sc.pearl is not None:
                pr = sc.pearl
                draw_pearl(p, self.atlas, pr.x, pr.y, pr.rotation_deg,
                           pr.tint, pr.rad, pr.glimmer_at(ts))

    def _scavenger_hint_object(self):
        seed = self._scavenger_seed
        got = getattr(self, "_scavenger_preview", None)
        if got is None or got[0] != seed:
            sc = Scavenger(0.0, 0.0, seed=seed, variant=self.cat_variant())
            sc.spear = None
            got = (seed, sc)
            self._scavenger_preview = got
        return got[1]

    def _draw_scavenger_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        sc = self._scavenger_hint_object()
        sc.x = sc.last_x = cx
        sc.y = sc.last_y = min(cy, self._HL - SCAV_BODY_RAD)
        p.save()
        p.setOpacity(0.5)
        draw_scavenger(p, self.atlas, sc, 1.0, sc.body_rgb, sc.head_rgb, sc.eye_rgb)
        p.restore()

    # ── 驯服：猫把蝉乌贼递给蜥蜴（原版 FriendTracker.GiftRecieved）──
    def untamed_lizards(self):
        """还没被驯服的蜥蜴。"""
        return [lz for lz in self.lizards if not lz.tamed and lz.state == ItemState.FREE]

    def nearest_untamed_lizard(self, x):
        best, bd = None, 1e9
        for lz in self.untamed_lizards():
            d = abs(lz.x - x)
            if d < bd:
                best, bd = lz, d
        return best

    def tame_ready(self) -> bool:
        """有未驯服蜥蜴 + 场上有够得到的蝉乌贼 → 允许猫为驯服而取物。"""
        if not self.untamed_lizards():
            return False
        return (any(sc.fetch_ready for sc in self.squidcadas)
                or any(nw.fetch_ready for nw in self.needleworms))

    def deliver_gift(self, pet, lz) -> bool:
        """交接礼物：蝉乌贼转给蜥蜴，按原版结算 like（活体 0.6 / 尸体 1.2）。"""
        item = pet.body.carried_fruit
        if item is None or not getattr(item, "is_tame_food", False):
            return False
        alive = not getattr(item, "dead", False)
        item.held_by_hand = None
        item.stalk = None
        item.state = ItemState.EATEN
        pet.body.release_fruit()
        lz.gift_received(alive, pet.id)
        self._gift_fx(lz)
        return True

    def _gift_fx(self, lz):
        """送礼反馈：一小圈彩色火花 + 轻微抖动。"""
        rng = self._stun_rng
        for i in range(10):
            a = rng.uniform(0.0, math.tau)
            sp = rng.uniform(1.2, 2.6)
            self.sparks.append([lz.x, lz.y - 6.0, math.cos(a) * sp, math.sin(a) * sp - 0.6,
                                18, 18, 1 if i % 2 else 0])
        self._shake[1] -= 0.6
