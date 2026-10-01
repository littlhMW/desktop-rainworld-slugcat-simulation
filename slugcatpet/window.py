"""全屏透明置顶桌宠窗，固定步长物理+插值渲染。"""
from __future__ import annotations
import os
import sys
_DEBUG_SEEDED = False
import inspect
import random
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QRect, QPoint, QPointF, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QGuiApplication, QCursor, QRegion

from ._paths import log_error
from .behavior import tuning
from .rendering.atlas import AtlasSet
from .rendering.layout import Layout
from .rendering.primitives import blit
from .rendering import pixelmode
from .rendering.pixelmode import aa_hint
from .petunit import PetUnit
from .planning.crowd import TrafficField
from .planning.threat import ThreatField
from .core import chunkphys
from .core.units import clampf, lerp
from .core.water import WaterSurface
from .world.effects import EffectsMixin
from .world.items import ItemInteractionMixin
from .world.enums import ItemState
from .world.rain import RainSystem
from .world.shelter import Shelter, shelter_from_dict, template_of
from .stormcycle import StormCycle
from .rendering import rain_draw
from .rendering import storm_hud

MAX_PETS = 10

# ── 自然生成（设置面板里的「生物列表」）──
NATURAL_SPAWN_TICKS = 900     # 每约 22s 补一只（勾选哪几种就生成哪几种，不限数量）
SPAWN_GROUND_KINDS = frozenset(("seedcob", "karmaflower"))   # 只长在地面上的
# 暂时隐藏的生成入口：代码保留，但不出现在「生物生成」列表与图标盘里。
HIDDEN_PLACE_KINDS = frozenset(("scavenger",))
# 幼崽：不是常规蛞蛓猫（不占蛞蛓猫名额、不进选皮菜单），但仍然是一只会自己行动的实体
PUP_VARIANT = "slugpup"
PUP_MAX = 4                   # 场上幼崽上限（都是完整跟踪仿真，别无限长）
# 自然生成时的落点高度带（占窗口高的比例，y 从上往下算）：
# 会飞的在中层空域，走地的贴着地面，果实 / 灯 / 黏菌可以挂在半空。
SPAWN_Y_BAND = {
    "fruit": (0.15, 0.75),
    "batfly": (0.20, 0.70),
    "squidcada": (0.15, 0.65),
    "needleworm": (0.20, 0.70),
    "lamp": (0.35, 1.00),
    "slimemold": (0.30, 1.00),
    "stone": (0.55, 1.00),
    "spear": (0.55, 1.00),
    "pearl": (0.55, 1.00),
    "lizard": (0.60, 1.00),
    "scavenger": (0.60, 1.00),
    "slugpup": (0.60, 1.00),
}
SPAWN_Y_BAND_DEFAULT = (0.55, 1.00)


def spawnable_kinds() -> tuple:
    """所有 place_<key>(lx, ly) 的类型名 —— 以后新增生物会自动出现在设置列表里。

    只认「前两个参数＝位置」的放置接口：第三位以后必须带默认值（例如
    place_lizard(lx, ly, breed=None) 仍算生物），像 place_pole(lx, ly, kind)
    这种强制要求额外参数的结构类放置不算「生物」，自动排除。
    """
    out = []
    for name, fn in inspect.getmembers(ItemInteractionMixin, inspect.isfunction):
        if not name.startswith("place_"):
            continue
        try:
            params = list(inspect.signature(fn).parameters.values())[1:]   # 去掉 self
        except (TypeError, ValueError):
            continue
        if len(params) < 2:
            continue
        pos = (inspect.Parameter.POSITIONAL_ONLY,
               inspect.Parameter.POSITIONAL_OR_KEYWORD)
        if not all(p.kind in pos and p.default is inspect.Parameter.empty
                   for p in params[:2]):
            continue
        if not all(p.kind in pos and p.default is not inspect.Parameter.empty
                   for p in params[2:]):
            continue
        out.append(name[len("place_"):])
    return tuple(k for k in sorted(out) if k not in HIDDEN_PLACE_KINDS)

STONE_FAST_REDRAW = 3.0    # 速度超此整窗重绘

GRAV_EASE = 0.08              # 重力缓动率（~1s 过渡）

# 地板下渲染余量
GROUND_INSET = 16.0

# 其它窗口顶边＝单向平台：多久重新枚举一次
PLATFORM_REFRESH_TICKS = 30

# 光标＝一小节**悬空**短杆（用户指定的桌宠扩展；原版没有这根杆）：
# 长度＝系统光标本身的大小（杆总长＝光标高度折算到世界坐标），杆心跟着光标跑，
# 端点**不夹窗口顶/底** —— 底部不与屏幕地面相连，所以它是一段悬空的小短杆，
# 而不是通到地面的真竖杆。甩鼠标（本 tick 位移超阈值）能把杆上的猫甩下来。
CURSOR_PX_FALLBACK = 32.0        # 取不到系统光标尺寸时的兜底（标准箭头 32px）
MOUSE_POLE_MIN_HALF = 8.0        # 杆半长下限（逻辑单位；超大画布缩放时别缩没了）
MOUSE_POLE_RELEASE_TICKS = 80    # 松开鼠标后这么久内不当杆（2s @ 40tick/s）
SHELTER_HINT_ICON = 14.0         # 放庇护所：点击前光标处那个图标的边长（逻辑单位，1/4 大小）
# 抓猫／拽东西／正在放东西的时候，光标不是一根杆
_DRAG_ATTRS = ("_dragged_fruit", "_dragged_stone", "_dragged_slimemold",
               "_dragged_batfly", "_dragged_lizard", "_dragged_squidcada",
               "_dragged_needleworm", "_dragged_pearl", "_dragged_spear",
               "_dragged_scavenger", "_dragged_seedcob", "_dragged_karmaflower")


def system_cursor_px() -> float:
    '''系统光标的屏幕像素高度（Windows GetSystemMetrics；取不到回退兜底值）。'''
    try:
        import ctypes
        h = int(ctypes.windll.user32.GetSystemMetrics(14))     # SM_CYCURSOR
        if h > 0:
            return float(h)
    except Exception:
        pass
    return CURSOR_PX_FALLBACK

# 窗口抖动
SHAKE_DECAY = 0.8
SHAKE_MAX = 6.0
SHAKE_GOURMAND_MUL = 1.35     # 饕餮砸出来的震动略夸张一点（用户口径）
FALL_STUN_SPEED = 22.0       # 落地竖直速度超过它 → 摔晕一会儿（≈抖动已经看得见的高度）
FALL_STUN_TICKS = 14          # 基础晕眩时长（40 tick/s → 0.35s）
FALL_STUN_PER_SPEED = 1.1     # 每多 1 px/tick 追加的晕眩 tick
FALL_STUN_MAX = 60            # 晕眩上限（1.5s）
RAIN_SHAKE_MAX = 2.2        # 雨势折算出的每 tick 抖动幅度上限（并入既有 _shake）
SHAKE_EPS = 0.05


def compute_geometry(area: QRect, geo: QRect, canvas_scale: int) -> dict:
    """算地面/窗口几何。"""
    s = canvas_scale or 1
    avail_below = max(0, (geo.y() + geo.height()) - (area.y() + area.height()))
    inset_dev = avail_below if avail_below > 0 else int(round(GROUND_INSET * s))
    return {"WL": area.width() / s, "HL": area.height() / s, "ground_inset": inset_dev,
            "win_w": area.width(), "win_h": area.height() + inset_dev}


def _clamp_chunk_to_bounds(c, WL, HL):
    """chunk 夹进边界（四边都是实体：左右墙 + 上顶 + 下地）。"""
    r = max(c.rad, 1.0)
    if c.x < r:
        c.x = r
        if c.vx < 0:
            c.vx = 0.0
    elif c.x > WL - r:
        c.x = WL - r
        if c.vx > 0:
            c.vx = 0.0
    if c.y + r > HL:
        c.y = HL - r
        if c.vy > 0:
            c.vy = 0.0
    elif c.y - r < 0:
        c.y = r
        if c.vy < 0:
            c.vy = 0.0


def _clamp_item_to_bounds(o, WL, HL):
    """物体夹进边界（四边都是实体）。"""
    r = getattr(o, "rad", 0.0)
    if o.x < r:
        o.x = r
        if o.vx < 0:
            o.vx = 0.0
    elif o.x > WL - r:
        o.x = WL - r
        if o.vx > 0:
            o.vx = 0.0
    if o.y + r > HL:
        o.y = HL - r
        if o.vy > 0:
            o.vy = 0.0
    elif o.y - r < 0:
        o.y = r
        if o.vy < 0:
            o.vy = 0.0


class PetWindow(EffectsMixin, ItemInteractionMixin, QWidget):
    def __init__(self, layout: Layout | None = None, debug: bool | None = None,
                 params=None):
        super().__init__()
        self._params = params or {}
        self.atlas = AtlasSet()
        self.layout_data = layout or Layout.load()
        if debug is None:
            debug = os.environ.get("SLUGCATPET_DEBUG") not in (None, "", "0")
        self.debug = debug
        global _DEBUG_SEEDED
        if debug and not _DEBUG_SEEDED:
            # 调试/测试：只在本进程第一次开窗时固定全局随机流（行为可复现；
            # 之后开的窗口继续同一条流，作息/睡眠时长才不会千篇一律）
            _DEBUG_SEEDED = True
            random.seed(20260928)

        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not self.debug)
        if self.debug:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        s = self.layout_data.canvas_scale
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        geo = screen.geometry()
        geom = compute_geometry(area, geo, s)
        self._area = area                     # 工作区（不含下延带）
        self._scale = s
        self._pixbuf = None
        pixelmode.PIXEL = True          # 全局像素模式：本体风格硬边像素
        self._WL = geom["WL"]
        self._HL = geom["HL"]                  # 地板线=工作区底边，下延后不变
        self._ground_inset = geom["ground_inset"] / s if s else 0.0
        self.resize(geom["win_w"], geom["win_h"])
        self.move(area.x(), area.y())

        # 特效层
        self.sparks = []         # [x,y,vx,vy,life,maxlife,white]
        self.shockwaves = []     # [x,y,r,maxr,life,maxlife,flash]
        self.fx = []
        self.bubbles = []
        self._bubble_rng = random.Random(0xB0BB1E)
        self.cursor_hijack = None
        self._plat_tick = 0
        self._platforms_on = bool(self._params.get("window_platforms", True))
        # 窗口地形/导航缓存：必须在第一次 _refresh_platforms() 之前就有初值，
        # 否则「窗口重置」与各种探针会读到不存在的属性。_win_* 记录「我们自己
        # 放上去的那一份」，用来区分别人（夹具 / 鼠标虚杆）注入的平台与墙段。
        self._nav_version = 0
        self._nav_sig = None
        self._navgeom_cache = None
        self._terrain_graphs = {}
        self._win_tops = None
        self._win_wall_rects = None
        self.walls = []                        # 非全屏窗口的矩形（原始几何）
        self.wall_surfaces = []                # 露出来的可见墙段（world.walls.WallSurface）
        self.wall_version = 0                  # 墙几何变化计数（蜥蜴导航用）
        self.world_version = 0                 # 放/清道具、环境变化时 +1
        self.geometry_version = 0              # 路径前提变更（杆/灯/工作区）时 +1
        self._refresh_platforms()
        self._hud = None
        self._pets_changed_cb = None
        self._open_settings_cb = None
        self._hotkey_filter = None
        self._control_hud = None         # 非 None 即有受控会话

        # 放果子
        self.fruits = []
        self._place_mode = False
        self._place_kind = None
        self._fruit_seed = 0
        self._dragged_fruit = None
        self._drag_last = None

        # 放石头
        self.stones = []
        self._stone_seed = 0
        self._dragged_stone = None
        self._stone_drag_last = None
        self._stun_rng = random.Random(98765)
        # 杆上挤位赛：同一场冲突里所有猫必须取到同一个胜者（否则互推同归于尽）
        self._pole_rng = random.Random(0x9E1770)
        self._pole_contests = {}
        self._pole_tick = 0

        # 放黏菌
        self.slimemolds = []
        self._slimemold_seed = 0
        self._dragged_slimemold = None
        self._slime_drag_last = None
        self._slime_preview = None

        # 放蝙蝠
        self.batflies = []
        self._batfly_seed = 0
        self._dragged_batfly = None
        self._batfly_drag_last = None

        # 放蜥蜴
        self.lizards = []
        self._lizard_seed = 0
        self._dragged_lizard = None
        self._lizard_preview = None

        # 放蝉乌贼
        self.squidcadas = []
        self._squidcada_seed = 0
        self._dragged_squidcada = None
        self._squidcada_preview = None

        # 放面条蝇（卵 / 幼体 / 成体，年龄随机）
        self.needleworms = []
        self._needleworm_seed = 0
        self._dragged_needleworm = None
        self._needleworm_preview = None

        # 放珍珠
        self.pearls = []
        self._pearl_seed = 0
        self._dragged_pearl = None
        self._pearl_drag_last = None
        self._pearl_preview = None

        # 放矛
        self.spears = []
        self._spear_seed = 0
        self.needle_threads = []      # 矛大师活针的有机细线（Spear.Umbilical）
        self._dragged_spear = None
        self._spear_drag_last = None

        # 放拾荒者
        self.scavengers = []
        self._scavenger_seed = 0
        self._dragged_scavenger = None
        self._scavenger_preview = None

        # 放爆米花（Popcorn Plant / SeedCob）
        self.seedcobs = []
        self.seeds = []
        self._seedcob_seed = 0
        self._seed_seed = 0
        self._dragged_seedcob = None
        self._seedcob_preview = None

        # 放业力花（Karma Flower）
        self.karmaflowers = []
        self._karmaflower_seed = 0
        self._dragged_karmaflower = None
        self._karmaflower_drag_last = None
        self._karmaflower_preview = None
        self._karma_flower_spawns = []     # 死亡后待长出的业力花 [[x, y, 剩余 tick], ...]

        # 放杆子
        self.poles = []
        self._pole_seed = 0
        self.extra_walls = []                  # 手绘墙条（矩形 x0,y0,x1,y1）：真碰撞
        # 光标那一小截竖杆（不渲染、不换代、不存档）
        self._cursor_world = None          # 本 tick 的光标（逻辑坐标）；矛钉光标用
        self._cursor_pin_prev = None       # 上一 tick 光标（算甩动速度）
        self._mouse_pole = None
        self._mouse_pole_on = bool(self._params.get("mouse_pole", True))
        self._mouse_pole_prev = None       # 上一 tick 光标位置（算甩动速度）
        self._mouse_pole_vel = None        # 本 tick 光标位移（PoleClimber 读它判甩落）
        self._mouse_pole_suppress = 0      # 松开鼠标后的静默 tick（期间不当杆）
        self._cursor_half = None           # 光标虚杆半长缓存（逻辑单位）
        # 光标劫持总开关（托盘右键可关）。关掉只是不许溪流/工匠去抢系统光标，
        # 指着光标之类的正常工作不受影响。
        self.cursor_hijack_allowed = bool(self._params.get("cursor_hijack", True))

        # 自然生成（设置面板「生物列表」勾选的类型）
        saved_spawn = self._params.get("spawn_kinds")
        kinds = set(saved_spawn) if isinstance(saved_spawn, (list, tuple)) else set()
        self._spawn_kinds = kinds & set(spawnable_kinds())
        self._spawn_timer = NATURAL_SPAWN_TICKS

        # 寒冷系统
        self.blizzard_on = not tuning.COLD_BLIZZARD_DEFAULT_OFF
        self.blizzard_timer = 0
        self.lamp = None
        self._lamp_seed = 0
        self.cold_cycle_prog = 0.0
        # Snow 氛围
        from .world.snow import Snowfall
        self.snow_on = tuning.SNOW_ENABLED
        self._snow = Snowfall(tuning.SNOW_MAX_FLAKES, tuning.SNOW_VIGNETTE_MAX, seed=0x5)

        # 无重力
        self.room_gravity = 1.0
        self.gravity_target = 1.0
        self.zerog_on = False

        # 水环境
        self.water_on = False
        self.water_y = None            # 越小越高；None=无水
        self.water_target = None
        self.water_surface = None

        self._shake = [0.0, 0.0]

        # 雨循环 + 庇护所（默认关闭；设置里开，且至少有一间庇护所才走相位）
        self.rain = RainSystem(self._WL, self._HL)
        self.rain.patterns = rain_draw.make_rain_patterns()
        self.shelters = []
        self.storm = StormCycle(enabled=bool(self._params.get("storm_enabled", False)))
        _st = self._params.get("storm")
        if isinstance(_st, dict):
            self.storm.from_dict(_st)
        self.storm_pressure = 0.0        # 雨前焦虑 0~1（只有闲暇行为读它）
        self.storm_active = False        # 暴雨进行中（StormSeekShelter 的闸）
        self._storm_cycle_seen = 0       # StormCycle.cycle_id 的哨兵：变了就复位第一滴重雨
        self._storm_rng = random.Random(0x57071)   # 私有流：不搅动全局随机数
        # 暴雨鼠标拆成两个独立开关（默认都关，不挡用户干活）：
        #   storm_block_clicks  —— 暴雨期间拦住真实点击（不穿透）
        #   storm_lethal_clicks —— 暴雨里点一下杀一只猫
        # 任务栏那一条（地板线以下的下延带）永远不接管，见 _passthrough_want。
        # 旧版只有一个 storm_capture_clicks，读档时按同一个值迁移过来。
        _old_cap = self._params.get("storm_capture_clicks")
        if _old_cap is not None:
            for _k in ("storm_block_clicks", "storm_lethal_clicks"):
                self._params.setdefault(_k, bool(_old_cap))
        self.storm_block_clicks = bool(self._params.get("storm_block_clicks", False))
        self.storm_lethal_clicks = bool(self._params.get("storm_lethal_clicks", False))
        # 友军伤害：默认关＝保持原本的真实友伤。开着时蛞蝓猫投出的矛/石头
        # 不再对同伴造成伤害与眩晕；只改伤害结算，一点不碰 AI。
        self.friendly_fire_protect = bool(self._params.get("friendly_fire_protect", False))
        self._shelter_drag_start = None
        self._shelter_seed = 0

        self._prev_dirty = None
        self._fx_active_prev = False
        self._fx_active = False
        self.follow_cursor = True
        self.pets = []
        # 共享世界层（文档 §二 的数据流）：危险 / 拥挤各更新一份，所有猫共用。
        # 场是「世界的」，上下文是「每只猫的」——所以这里放世界，NavContext 放猫。
        self.threat_field = ThreatField(self)
        self.traffic_field = TrafficField(self)
        self._all_dead_t = 0        # 全员死亡守灵计时
        self._reincarnate_cleanup_pending = False   # 转生：全体复活那一瞬才清场
        self._build_pets()
        self._restore_world()
        self._restore_shelters()

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_ms = self._clock.elapsed()
        self._t = 0.0
        self._phys_acc = 0.0
        self._ts = 1.0                  # 0..1 插值因子
        self._hwnd = 0
        self._passthrough = None        # None 强制首次同步

        self.anim = QTimer(self)
        self.anim.setTimerType(Qt.TimerType.PreciseTimer)
        self.anim.setInterval(self._INT_FAST)
        self.anim.timeout.connect(self._tick)
        self.anim.start()

    # ── 构建：多宠 ──
    def _build_pets(self):
        """按存档与环境变量建猫。"""
        saved = self._params.get("pets")
        saved = list(saved) if isinstance(saved, list) and saved else None
        n = len(saved) if saved else 1
        env = os.environ.get("SLUGCATPET_PETS")
        if env:
            try:
                n = int(env)
            except ValueError:
                pass
        n = max(1, min(n, MAX_PETS))
        for i in range(n):
            state = saved[i] if saved and i < len(saved) else {}
            init_state = {"energy": state.get("energy", 1.0),
                          "temper": state.get("temper", 0.0),
                          "food": state.get("food", tuning.FOOD_INIT),
                          "karma": state.get("karma", tuning.KARMA_INIT),
                          "cold": state.get("cold", 0.0),
                          "food_quarter": state.get("food_quarter", 0)}
            pet_id = state.get("id") or f"pet-{i}"
            variant = state.get("variant", "saint")
            spawn_x = state.get("x")
            spawn_y = state.get("y")
            if spawn_x is None:                     # 老存档：按序均匀排开
                spawn_x = self._WL * (i + 1) / (n + 1)
            pet = PetUnit(self, i, pet_id, variant, init_state,
                          spawn_x=spawn_x, spawn_y=spawn_y)
            if state.get("dead") and pet.behavior is not None:
                pet.behavior.enter_dead()
            if state.get("face") is not None:
                pet.body.facing = int(state["face"])
            self.pets.append(pet)
            self._give_spawn_gear(pet)
        self._build_pups()

    def _build_pups(self):
        """存档里的幼崽（存在 params['pups']，不占常规蛞蝓猫名额）。"""
        saved = self._params.get("pups")
        if not isinstance(saved, list) or not saved:
            return
        from .petunit import PetUnit as _PU
        for i, state in enumerate(saved[:PUP_MAX]):
            idx = -1 - i
            init_state = {"energy": state.get("energy", 1.0),
                          "temper": state.get("temper", 0.0),
                          "food": state.get("food", tuning.FOOD_INIT),
                          "karma": state.get("karma", tuning.KARMA_INIT),
                          "cold": state.get("cold", 0.0),
                          "food_quarter": state.get("food_quarter", 0)}
            pet = _PU(self, idx, state.get("id") or f"pup-{i}", PUP_VARIANT,
                      init_state, spawn_x=state.get("x", self._WL * 0.5),
                      spawn_y=state.get("y"))
            self.pets.append(pet)

    def cat_slots_used(self) -> int:
        """常规蛞蝓猫名额占用（幼崽不算）。"""
        return sum(1 for p in self.pets if not getattr(p, "is_pup", False))

    def pup_count(self) -> int:
        return sum(1 for p in self.pets if getattr(p, "is_pup", False))

    def _restore_world(self):
        """按存档把环境实体（物品/生物/杆/灯）建回来。"""
        data = self._params.get("world")
        if not data:
            return
        from .persist import restore
        try:
            restore(self, data)
        except Exception as e:
            print("[slugcatpet] world restore failed: %r" % (e,), file=sys.stderr)

    def _restore_shelters(self):
        """按存档把庇护所建回来（旧档没有这一段就是空列表）。"""
        rows = self._params.get("shelters")
        if not isinstance(rows, list):
            return
        out = []
        for d in rows:
            sh = shelter_from_dict(d, self._WL, ground_y=self._HL)
            if sh is not None:
                out.append(sh)
        self.shelters = out
        self._shelter_seed = len(out)

    # ── 单猫兼容别名 ──
    @property
    def body(self):
        return self.pets[0].body if self.pets else None

    @property
    def gfx(self):
        return self.pets[0].gfx if self.pets else None

    @property
    def tail(self):
        return self.pets[0].tail if self.pets else None

    @property
    def tongue(self):
        return self.pets[0].tongue if self.pets else None

    @property
    def behavior(self):
        return self.pets[0].behavior if self.pets else None

    # ── 坐标 ──
    def to_logical(self, dx, dy):
        return dx / self._scale, dy / self._scale

    def cursor_logical(self):
        g = self.mapFromGlobal(QCursor.pos())
        return self.to_logical(g.x(), g.y())

    # ── 动态穿透 ──
    def _passthrough_want(self, cur) -> bool:
        """这一刻窗口该不该鼠标穿透（纯判定；测试直接调它，不碰 Win32）。

        两条硬规则，与暴雨是否接管点击无关：
        1. 下延带（地板线以下那条贴着屏幕底边的带子＝任务栏那一条）永远放行，
           所以暴雨点杀也不可能挡住任务栏 / 托盘右键菜单；
        2. 光标不在窗口上（cur is None）时放行。
        其余照旧：压着猫 / 正拖着东西 / 正在摆放 / 暴雨接管（开关打开时）才不穿透。
        """
        if cur is None:
            return True
        if cur[1] > self._HL:
            return True                  # 下延带＝任务栏：任何情况下都不接管
        from .control.mouse import is_over
        active = any(pet.behavior is not None and pet.behavior.grab.active for pet in self.pets)
        over_body = any(
            ((pet.behavior is None) or not pet.behavior.blocks_interaction())
            and is_over(pet.body, pet.gfx, cur, pad=6.0)
            for pet in self.pets)
        storm_capture = (bool(getattr(self.storm, "active", False))
                         and bool(self.storm_block_clicks))
        dragging_fruit = self._dragged_fruit is not None
        over_fruit = self._fruit_at(cur) is not None
        dragging_stone = self._dragged_stone is not None
        over_stone = self._stone_at(cur) is not None
        dragging_slime = self._dragged_slimemold is not None
        over_slime = self._slimemold_at(cur) is not None
        dragging_batfly = self._dragged_batfly is not None
        over_batfly = self._batfly_at(cur) is not None
        dragging_lizard = self._dragged_lizard is not None
        over_lizard = self._lizard_at(cur) is not None
        dragging_squid = self._dragged_squidcada is not None
        over_squid = self._squidcada_at(cur) is not None
        dragging_nworm = self._dragged_needleworm is not None
        over_nworm = self._needleworm_at(cur) is not None
        dragging_pearl = self._dragged_pearl is not None
        over_pearl = self._pearl_at(cur) is not None
        dragging_spear = self._dragged_spear is not None
        over_spear = self._spear_at(cur) is not None
        dragging_scav = self._dragged_scavenger is not None
        over_scav = self._scavenger_at(cur) is not None
        dragging_cob = self._dragged_seedcob is not None
        over_cob = self._seedcob_at(cur) is not None
        dragging_flower = self._dragged_karmaflower is not None
        over_flower = self._karmaflower_at(cur) is not None
        return not (active or dragging_fruit or over_fruit or dragging_stone or over_stone
                    or dragging_slime or over_slime or dragging_batfly or over_batfly
                    or dragging_lizard or over_lizard or dragging_squid or over_squid
                    or dragging_nworm or over_nworm
                    or dragging_pearl or over_pearl or dragging_spear or over_spear
                    or dragging_scav or over_scav or dragging_cob or over_cob
                    or dragging_flower or over_flower or over_body or storm_capture)

    def _update_passthrough(self):
        if self.debug:
            return
        if self._place_mode:
            return        # 放置模式接管点击，勿翻转
        want = self._passthrough_want(self.cursor_logical())
        if want != self._passthrough:
            self._passthrough = want
            if not self._hwnd:
                self._hwnd = int(self.winId())
            from .control.mouse import set_passthrough
            set_passthrough(self._hwnd, want)

    # ── 帧循环 ──
    _PHYS_DT = 1.0 / 40.0
    _MAX_TICKS = 4             # 防时间螺旋
    _MAX_DT = 0.1
    _INT_FAST = 25           # ms
    _INT_SLOW = 66
    _MOTION_STILL = 1.2
    MAX_FRUITS = 3
    MAX_STONES = 3

    def _scene_moving(self):
        """是否有物体在运动（供帧率自适应）。"""
        if self.room_gravity < 1.0:      # 无重力缓动中，保持高帧
            return True
        if self.water_surface is not None:   # 涨落或波未静，保持高帧
            if self.water_y != self.water_target or self.water_surface.energy() > tuning.WATER_STILL_EPS:
                return True
        for pet in self.pets:
            b = pet.body
            if (abs(b.chunk0.vx) + abs(b.chunk0.vy)
                    + abs(b.chunk1.vx) + abs(b.chunk1.vy)) > self._MOTION_STILL:
                return True
        for f in self.fruits:
            if abs(f.vx) + abs(f.vy) > self._MOTION_STILL:
                return True
        for s in self.stones:
            if abs(s.vx) + abs(s.vy) > self._MOTION_STILL:
                return True
        for m in self.slimemolds:
            if abs(m.vx) + abs(m.vy) > self._MOTION_STILL:
                return True
        for b in self.batflies:
            if abs(b.vx) + abs(b.vy) > self._MOTION_STILL:
                return True
        for lz in self.lizards:
            if (abs(lz.vx) + abs(lz.vy) > self._MOTION_STILL * 0.5
                    or lz.jaw > 0.03 or lz.bite_hold > 0):
                return True
        for sc in self.squidcadas:               # 悬停/扑翅一直在动
            if abs(sc.vx) + abs(sc.vy) > self._MOTION_STILL * 0.5 or sc.rest <= 0:
                return True
        for nw in self.needleworms:              # 面条蝇悬停时也在扑翅
            if abs(nw.vx) + abs(nw.vy) > self._MOTION_STILL * 0.5 or nw.airborne:
                return True
        for pr in self.pearls:
            if abs(pr.vx) + abs(pr.vy) > self._MOTION_STILL:
                return True
        for sp in self.spears:
            if not sp.stuck and abs(sp.vx) + abs(sp.vy) > self._MOTION_STILL:
                return True
        for sc in self.scavengers:
            if (abs(sc.vx) + abs(sc.vy) > self._MOTION_STILL * 0.5
                    or sc.state != ItemState.FREE):
                return True
        for cb in self.seedcobs:                     # 豆荚开合/摇摆在动
            if (abs(cb.v0[0]) + abs(cb.v0[1]) + abs(cb.v1[0]) + abs(cb.v1[1])
                    > self._MOTION_STILL * 0.5 or (cb.opened and cb.open < 0.995)):
                return True
        for sd in self.seeds:
            if abs(sd.vx) + abs(sd.vy) > self._MOTION_STILL:
                return True
        for kf in self.karmaflowers:                 # 花瓣/花茎一直在晃
            if abs(kf.vx) + abs(kf.vy) > self._MOTION_STILL:
                return True
        return False

    def pole_contest_winner(self, pole, cats):
        """杆上挤位赛胜者：同一场冲突里的猫拿到同一个结果（随机但一致）。

        随机只在「都坚持挤」的猫之间发生：只留一只占住位置，其余让路/被挤掉。
        """
        if not cats:
            return None
        key = (id(pole), tuple(sorted(id(c) for c in cats)))
        ent = self._pole_contests.get(key)
        if ent is not None and 0 <= self._pole_tick - ent[0] <= 30:
            return ent[1]
        if len(self._pole_contests) > 64:
            self._pole_contests.clear()
        win = cats[self._pole_rng.randrange(len(cats))]
        self._pole_contests[key] = (self._pole_tick, win)
        return win

    def fetchables(self, pearl_like: float = 1.0, want_karma: bool = False):
        """够取目标：可食物 + 珍珠（+ 需要时加业力花）。

        珍珠不可食，平常只用来跟拾荒者交易（原版货币），故不并入 edibles()。
        场上有拾荒者时一律列出（可以拿去换东西）；此外 pearl_like > 1 的猫
        （溪流）没有拾荒者也会专门去把珍珠叼起来拿着，所以要一起列出来。
        业力花同理：只有还没吃出花条的猫（want_karma）才会把它列进目标。
        """
        if self.pearls and (self.scavengers or pearl_like > 1.0):
            out = [*self.edibles(), *self.pearls]
        else:
            out = list(self.edibles())
        if want_karma and self.karmaflowers:
            out = [*self.karmaflowers, *out]
        return out

    def karma_targets(self):
        """业力花：独立于普通食物的目标链（业力花不是食物，不填饱食度）。"""
        return list(self.karmaflowers)

    def edibles(self):
        """可食物体聚合（果+爆米花种子+黏菌+蝙蝠+蝉乌贼+面条蝇）。"""
        return [*self.fruits, *self.seeds, *self.slimemolds, *self.batflies,
                *self.squidcadas, *self.needleworms]

    def junk_corpses(self):
        """无用且不能吃的尸体（清场目标）：死蜥蜴等。

        能吃的尸体（蝙蝠/蝉乌贼/面条蝇是肉）不进这张表 —— 那是食物不是垃圾；
        正被某只猫拖着的那具也不算（免得两只猫抢同一具）。
        已经被某只猫**认领**（_clear_target 指向它）的那具同样不算：
        尸体搬运只允许一只猫执行，别人一看到就该另找目标。认领是自愈的：
        认领者死了/换目标了，这里顺手把认领作废。
        """
        out = []
        for e in (*self.lizards, *self.squidcadas, *self.batflies,
                  *self.needleworms, *self.scavengers):
            if not getattr(e, "dead", False) or e.state != ItemState.FREE:
                continue
            if getattr(e, "is_meat", False) or getattr(e, "is_edible", False):
                continue
            if getattr(e, "hauled", False):
                continue
            owner = getattr(e, "hauler", None)
            if owner is not None:
                if getattr(owner, "_clear_target", None) is e:
                    continue
                e.hauler = None              # 认领者不在了：作废，尸体重新可被搬运
            out.append(e)
        return out

    def _tick(self):
        now = self._clock.elapsed()
        dt = (now - self._last_ms) / 1000.0
        self._last_ms = now
        if dt <= 0.0:
            return
        if not self.isVisible():
            return
        self._update_passthrough()
        self._advance(min(dt, self._MAX_DT))
        region = self._update_region()
        dragging = self._dragged_fruit is not None or self._dragged_stone is not None
        grabbing = any(pet.behavior is not None and pet.behavior.grab.active for pet in self.pets)
        active = (self._fx_active or dragging or grabbing or self.isActiveWindow()
                  or self._scene_moving())
        want_iv = self._INT_FAST if active else self._INT_SLOW
        if self.anim.interval() != want_iv:
            # Precise 保平滑，Coarse 省功耗
            self.anim.stop()
            self.anim.setTimerType(Qt.TimerType.PreciseTimer if active
                                   else Qt.TimerType.CoarseTimer)
            self.anim.setInterval(want_iv)
            self.anim.start()
        if region is None:
            self.update()
        else:
            self.update(region)

    def _update_region(self):
        """整窗或脏矩形决策（None=整窗）。"""
        # 特效等超出包围盒需整窗刷
        pet_fx = any(pet.behavior is not None and pet.behavior.exclusive_fx() is not None
                     for pet in self.pets)
        fast_stone = any(s.state == ItemState.FREE and (abs(s.vx) + abs(s.vy)) > STONE_FAST_REDRAW
                         for s in self.stones)
        snow_active = self.snow_on and self._snow.active
        shake_active = self._shake[0] != 0.0 or self._shake[1] != 0.0
        door_moving = any(0.0 < sh.close_fac < 1.0 for sh in (self.shelters or ()))
        fx_active = (pet_fx or self.sparks or self.shockwaves or self.fx or self.bubbles
                     or self.cursor_hijack is not None or self._place_mode or fast_stone
                     or snow_active or door_moving
                     or self.rain.active
                     or shake_active)
        # 零重力/蝙蝠已含在 _dirty_rect，不放这里
        self._fx_active = bool(fx_active)
        if fx_active:
            self._prev_dirty = None   # 避免下一帧 united 出错误的小框
            self._fx_active_prev = True
            return None
        if self._fx_active_prev:
            # 特效落沿，再整窗刷一次清残影
            self._fx_active_prev = False
            self._prev_dirty = None
            return None
        r = self._dirty_rect()
        upd = r if self._prev_dirty is None else r.united(self._prev_dirty)
        self._prev_dirty = r
        return upd

    def _advance(self, dt):
        """dt 累加器推进物理，存插值因子。"""
        self._t += dt
        self._phys_acc += dt
        phys_dt = self._PHYS_DT
        ticks = 0
        while self._phys_acc >= phys_dt and ticks < self._MAX_TICKS:
            self._phys_acc -= phys_dt
            ticks += 1
            self._do_tick()
        # 余量/步长，[0,1)
        self._ts = min(self._phys_acc / phys_dt, 1.0)

    # ── 环境让位 ──
    def freeze_tick(self):
        """冻结物理 tick（全屏让位）。

        必须先交还系统光标：tick 一停，``_update_fx`` 里的光标劫持就不再被 update，
        ``ClipCursor`` 会一直夹着 —— 表现就是「鼠标被钉在屏幕上某一点」。
        """
        self._drop_cursor_clip()
        self.anim.stop()

    def resume_tick(self):
        """解冻，重启 tick。"""
        self._last_ms = self._clock.elapsed()
        self.anim.start()

    def _drop_cursor_clip(self):
        """交还系统光标（释放 ClipCursor + 恢复系统光标形状）。幂等。"""
        try:
            self.stop_cursor_hijack()
        except Exception:
            pass
        try:
            from .platform import cursorfx
            cursorfx.abort_all()
        except Exception:
            pass

    def hideEvent(self, e):
        """窗口不可见时 tick 不再推进：任何活动劫持都要当场交还。"""
        self._drop_cursor_clip()
        super().hideEvent(e)

    # ── 环境适应 ──
    def apply_workspace(self, area, geo):
        """工作区变化，重算几何并夹回物体。"""
        self._cursor_half = None        # 换了屏幕/缩放：光标虚杆长度重算
        geom = compute_geometry(area, geo, self._scale)
        self.world_version += 1
        self.geometry_version += 1
        self._area = area
        self._WL = geom["WL"]
        self._HL = geom["HL"]
        self._ground_inset = geom["ground_inset"] / self._scale if self._scale else 0.0
        self.resize(geom["win_w"], geom["win_h"])
        self.move(area.x(), area.y())
        self._reground(geom["WL"], geom["HL"])
        self.rain.set_world(self._WL, self._HL)
        self._prev_dirty = None
        self.update()

    def _reground(self, WL, HL):
        """同步各猫与物体到新地面。"""
        for pet in self.pets:
            margin = pet.layout_data.canvas_w / 2.0
            b = pet.body
            b.W = WL
            b.H = HL
            b._floor_h = HL
            b.walk_min = margin
            b.walk_max = WL - margin
            b.visual_floor_y = HL
            _clamp_chunk_to_bounds(b.chunk0, WL, HL)
            _clamp_chunk_to_bounds(b.chunk1, WL, HL)
            pet.tail.floor_y = HL
            if pet.tongue is not None:
                pet.tongue.floor_y = HL
        for obj in (*self.fruits, *self.seeds, *self.stones, *self.slimemolds,
                    *self.batflies, *self.lizards, *self.squidcadas, *self.pearls,
                    *self.needleworms, *self.spears, *self.scavengers):
            _clamp_item_to_bounds(obj, WL, HL)
        for sh in getattr(self, "shelters", ()) or ():
            sh.WL = WL
            sh.x = min(max(sh.x, 0.0), max(0.0, WL - sh.w))
            sh.y = min(max(sh.y, 0.0), max(0.0, HL - sh.h))
            sh.ground_y = sh.y + sh.h
            sh.center_x = sh.x + sh.w * 0.5
            sh.center_y = sh.y + sh.h * 0.5
            sh._layout()
        self._refresh_shelter_solids()

    def _refresh_platforms(self):
        """其它可见窗口的顶边＝一块平地（窗口本体不挡路）。

        定时自动同步；真正的「窗口重置」入口是 reset_window_geometry()。
        """
        return self._sync_window_terrain()

    @staticmethod
    def _own_hwnds():
        own = set()
        try:
            app = QApplication.instance()
            for w in app.topLevelWidgets():
                try:
                    own.add(int(w.winId()))
                except Exception:
                    pass
        except Exception:
            pass
        return own

    def _drop_nav_caches(self):
        """窗口地形变了：导航快照 / 寻路图缓存全部作废。

        旧实现只改版本号，但 _navgeom_cache / _terrain_graphs 不看版本号就会把
        旧地形编译出来的图继续用下去（用户报的「清了重画才好」就是这个）。
        """
        try:
            self._navgeom_cache = None
            self._terrain_graphs = {}
            self._nav_sig = None
        except Exception:
            pass
        self._nav_version = int(getattr(self, "_nav_version", 0) or 0) + 1

    def _sync_window_terrain(self, force=False):
        """把「桌面窗口」这一层地形重新枚举一遍。

        这是窗口几何的**唯一**生成点：

          * 顶边 → chunkphys.set_platforms（单向平台 TopSurface）
          * 竖边 → self.walls / self.wall_surfaces（BackgroundRegion 的原始矩形）

        只清「我们自己上一次放上去的那一份」：别人（测试夹具 / 鼠标虚杆）注进去的
        平台与墙段不归这里管，开关关掉时也不会被顺手抹掉。旧实现在开关关掉后
        直接 return，于是「关掉窗口平台」之后场上一直挂着一份过期的窗口地形。
        """
        from .platform.winplat import enumerate_tops, enumerate_walls, enabled
        own = self._own_hwnds()
        on = bool(getattr(self, "_platforms_on", False)) and bool(enabled())
        new_tops = ()
        walls = []
        if on:
            try:
                new_tops = enumerate_tops(own, self._area.x(), self._area.y(),
                                          self._scale)
            except Exception:
                new_tops = ()
            try:
                walls = enumerate_walls(own, self._area.x(), self._area.y(),
                                        self._scale, getattr(self, "_WL", 0.0))
            except Exception:
                walls = []
        changed = False

        cur_tops = list(chunkphys.platforms() or ())
        mine_tops = getattr(self, "_win_tops", None)
        mine_tops = mine_tops is not None and cur_tops == list(mine_tops)
        if on:
            set_tops = new_tops
        elif mine_tops or force:
            # 开关关掉：只清我们自己放的那一份。force（「窗口重置」）是用户
            # 显式要求重来一遍，此时连注进来的旧地形一起清，避免留过期窗口地形。
            set_tops = ()
        else:
            set_tops = None            # 不归我们管：不动
        if set_tops is not None and (force or list(set_tops) != cur_tops):
            chunkphys.set_platforms(set_tops)
            self._win_tops = tuple(set_tops)
            # 平台集合真变了：寻路缓存 / 急停判据失效（首次调用早于 __init__ 的赋值）
            self.geometry_version = getattr(self, "geometry_version", 0) + 1
            changed = True

        # 背景区域（非全屏窗口的竖边）：只有 Background Climb 的品种能附上去
        cur_walls = getattr(self, "walls", None)
        mine_walls = getattr(self, "_win_wall_rects", None)
        mine_walls = mine_walls is not None and cur_walls == mine_walls
        if on:
            set_walls = walls
        elif mine_walls or force:
            set_walls = []
        else:
            set_walls = None
        if set_walls is not None and (force or set_walls != cur_walls):
            self.walls = set_walls
            self._win_wall_rects = list(set_walls)
            # 原始矩形 -> 「露出来的」可见段：被前面窗口挡住的段不算地形。
            from .world.walls import build_wall_surfaces
            self.wall_surfaces = build_wall_surfaces(set_walls)
            # 墙面几何变了：单独记一个版本号 —— geometry_version 的既有语义是
            # 「猫的寻路前提」（平台/杆/工作区），不要被蜥蜴的墙几何冲掉缓存。
            self.wall_version = getattr(self, "wall_version", 0) + 1
            changed = True
        # force：即使内容一样也要把版本推一格（手动重置的意义就在于「重来一遍」）
        if force and set_tops is None and set_walls is None:
            changed = True
        if changed:
            self._drop_nav_caches()
        return changed


    def reset_window_geometry(self):
        """**窗口重置**：重新枚举窗口地形（平台顶边 + 背景区域）并丢掉所有导航缓存。

        为什么需要：窗口位置 / Z 序 / 屏幕变化后，旧的平台 + 墙段可能与桌面不一致，
        而导航快照又只认当时算出的那一份；不重置就会出现「杆 / 墙在错位置上」之类
        的怪现象（用户实测：清掉重画一下就好）。现在它是一个显式动作（工具栏
        「重置窗口地形」），「清除可交互实体」之后也会跑一次。
        """
        changed = self._sync_window_terrain(force=True)
        try:
            self._prev_dirty = None
            self.update()
        except Exception:
            pass
        return changed


    def _cursor_half_len(self) -> float:
        """光标虚杆半长（逻辑单位）＝系统光标高度折算成世界坐标的一半。

        屏幕 DIP = 物理像素 / 设备像素比；世界单位 = DIP / canvas_scale。
        于是「屏幕上的那段杆」跟系统光标一样长（用户口径）。
        """
        if self._cursor_half is None:
            try:
                dpr = float(self.devicePixelRatioF()) or 1.0
            except Exception:
                dpr = 1.0
            s = float(self._scale or 1)
            self._cursor_half = max(MOUSE_POLE_MIN_HALF,
                                    system_cursor_px() / dpr / (2.0 * s))
        return self._cursor_half

    def _mouse_pole_busy(self) -> bool:
        """正抓着猫／正拽着东西 → 光标不是杆（免得跟手里的对象打架）。

        覆盖：抓着猫（grab）、12 种鼠标拖拽（物品/生物）、放置模式（_place_mode
        见 _mouse_pole_tick）、以及松手后的静默窗口。
        """
        if self.cursor_hijack is not None:
            return True
        for attr in _DRAG_ATTRS:
            if getattr(self, attr, None) is not None:
                return True
        return any(getattr(getattr(pet, "behavior", None), "grab", None) is not None
                   and pet.behavior.grab.active for pet in getattr(self, "pets", ()))

    def _cursor_play_active(self) -> bool:
        """有猫正在追光标（玩光标），或正挂在光标那截虚杆上 → 光标才当杆。

        平时光标不进 poles（用户口径）：场上一有杆，空中抓杆 / 杆间跳 / 无重力抓杆
        就会顺手把这截杆抓走 —— 猫会莫名其妙跳上去挂在鼠标上。只有玩光标期间
        （ChaseCursor）才把它喂给同一套规划/攀爬逻辑；已经爬上去了就不中途抽走。
        """
        pl = self._mouse_pole
        for pet in getattr(self, "pets", ()):
            bf = getattr(pet, "behavior", None)
            if bf is None:
                continue
            if getattr(bf, "state", None) == "ChaseCursor":
                return True
            pc = getattr(bf, "poleclimb", None)
            if pl is not None and pc is not None and pc.pole is pl:
                return True
        return False

    def _mouse_pole_tick(self, cur) -> None:
        """光标＝一小节竖杆（用户指定的桌宠扩展），只在玩光标时上场。

        原版杆子是房间 tile，没有「跟着鼠标跑的杆」；这里把它做成一段短竖杆
        塞进 poles，规划层（PoleJumpReach / hop_plan / PoleClimber）与真杆完全同源，
        于是追光标的猫会把光标当成可爬、可跳过去抓的杆。
        虚拟杆不渲染、不参与交叉换杆（见 Pole.virtual / cross_point）；
        平时不上场（见 _cursor_play_active），免得别的行为把它当普通地形顺手抓走。
        """
        pl = self._mouse_pole
        if self._mouse_pole_suppress > 0:
            self._mouse_pole_suppress -= 1
        cx, cy = (cur if cur is not None else (None, None))
        # 甩鼠标：记下本 tick 光标位移（虚杆的 PoleClimber 读它决定是否被甩下来）
        prev = self._mouse_pole_prev
        if cx is not None and prev is not None:
            self._mouse_pole_vel = (cx - prev[0], cy - prev[1])
        else:
            self._mouse_pole_vel = None
        self._mouse_pole_prev = None if cx is None else (cx, cy)
        # 非空闲时（拖着猫 / 正拽着东西 / 正在放东西 / 刚松手 2s 内）光标都不是杆：
        # 拖拽时光标就压在对象身上，这根杆会和对象完全重合（猫会去抓自己脚下那根杆）。
        # 空闲下来、光标还在窗口内就照旧出现。
        busy = (self._mouse_pole_suppress > 0 or self._place_mode
                or self._mouse_pole_busy())
        on = (self._mouse_pole_on and not busy and self._cursor_play_active()
              and cx is not None
              and 0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL)
        if not on:
            self._mouse_pole_vel = None
            if pl is not None:
                pl.state = ItemState.GONE
                if pl in self.poles:
                    self.poles.remove(pl)
                self._mouse_pole = None
                self.geometry_version += 1
                self.world_version += 1
            return
        # 悬空定长：端点跟着光标整体平移，不夹到窗口顶/底（底部不接地）
        half = self._cursor_half_len()
        top = cy - half
        bot = cy + half
        if pl is None:
            from .world.pole import Pole, VERTICAL
            pl = Pole(VERTICAL, cx, bot, cx, top)
            pl.virtual = True
            self._mouse_pole = pl
            self.poles.append(pl)
            self.geometry_version += 1
            self.world_version += 1
            return
        # 跟着光标移动：端点每 tick 重写（PoleClimber 每 tick 重读，于是被带着走）
        pl.ax, pl.ay, pl.bx, pl.by = cx, bot, cx, top
        pl.state = ItemState.FREE     # clear_poles 会把它打成 GONE：又出现在场上了就复活
        if pl not in self.poles:      # clear_poles 之类清空过
            self.poles.append(pl)
            self.geometry_version += 1
            self.world_version += 1

    def _do_tick(self):
        """推进一个物理 tick。"""
        self._pole_tick += 1
        self._plat_tick -= 1
        if self._plat_tick <= 0:
            self._plat_tick = PLATFORM_REFRESH_TICKS
            self._refresh_platforms()
        # 抖动衰减，须在 impact 前
        self._shake[0] *= SHAKE_DECAY
        self._shake[1] *= SHAKE_DECAY
        if abs(self._shake[0]) + abs(self._shake[1]) < SHAKE_EPS:
            self._shake[0] = self._shake[1] = 0.0
        cur = self.cursor_logical()
        self._cursor_world = cur          # 矛的「钉在光标上」判定用（见 items._tick_spears）
        self._mouse_pole_tick(cur)

        storm_was_active = bool(self.storm.active)
        self._storm_tick()            # 须在 pet.step 前：雨强/门/积水目标当 tick 生效

        self._zerog_update()
        cycle_prog = self._cold_update_world()
        self._water_update()          # 须在 pet.step 前

        # 危险 / 拥挤：本 tick 先各采一次，之后所有猫的寻路读的都是同一份快照
        self.threat_field.update(self)
        self.traffic_field.update(self)

        for pet in self.pets:
            pet.step(cur, cycle_prog)

        self._rain_push_tick()        # 雨压：暴露在雨里的东西被轻轻往下压

        self._all_dead_tick()
        self._natural_spawn_tick()

        self._tick_fruits()
        self._tick_stones()
        self._tick_slimemolds()
        self._tick_batflies()
        self._tick_lizards()
        self._tick_squidcadas()
        self._tick_needleworms()
        self._tick_pearls()
        self._tick_spears()
        self._tick_scavengers()
        self._tick_seedcobs()
        self._tick_karmaflowers()
        self._water_splash_detect()   # 须在物体积分后

        self._collide_objects()

        if self.lamp is not None:
            self.lamp.step()

        if self.snow_on:
            self._snow.step(self.cold_cycle_prog, self._WL, self._HL)

        self._update_fx()

    def spawn_kinds(self) -> set:
        """当前勾选「自然生成」的类型集合。"""
        return set(self._spawn_kinds)

    def set_spawn_kind(self, key: str, on: bool) -> None:
        """勾/取消一种自然生成（写进 params，存档时一并落盘）。"""
        if key not in spawnable_kinds():
            return
        if on:
            self._spawn_kinds.add(key)
        else:
            self._spawn_kinds.discard(key)
        self._params["spawn_kinds"] = sorted(self._spawn_kinds)

    def _natural_spawn_tick(self) -> None:
        """每 NATURAL_SPAWN_TICKS 按勾选列表补一只（不限数量）。"""
        if not self._spawn_kinds:
            return
        self._spawn_timer -= 1
        if self._spawn_timer > 0:
            return
        self._spawn_timer = NATURAL_SPAWN_TICKS
        key = random.choice(sorted(self._spawn_kinds))
        fn = getattr(self, "place_" + key, None)
        if fn is None:                       # 旧的存档里留了已删掉的类型
            self._spawn_kinds.discard(key)
            return
        x = random.uniform(self._WL * 0.1, self._WL * 0.9)
        if key in SPAWN_GROUND_KINDS:
            y = self._HL
        else:
            lo, hi = SPAWN_Y_BAND.get(key, SPAWN_Y_BAND_DEFAULT)
            y = self._HL * random.uniform(lo, hi)
        try:
            fn(x, y)
        except Exception as e:               # 单个放不下不该拖垮整个桌宠
            print("[slugcatpet] spawn %s failed: %r" % (key, e), file=sys.stderr)

    def _all_dead_tick(self):
        """全员死亡：守灵一段后集体转生（业力已在各自死亡时结算）。

        转生没有灵光特效；清场也从「进入倒计时」挪到「全体复活的那一瞬」——
        倒计时期间世界照旧、尸身还躺在那儿，正是同伴最后一次扒拉救回的机会。
        """
        pets = [p for p in self.pets if p.behavior is not None]
        if not pets:
            self._all_dead_t = 0
            return
        # 猫崽的身份是非蛞蝓猫生物：不进「全员死亡」门槛、也不跟着转世，
        # 死了就是死了（尸身留在场上，等玩家自己处理）。
        gating = [p for p in pets if not getattr(p, "is_pup", False)]
        if not gating:
            self._all_dead_t = 0
            return
        if all(p.behavior.is_dead() for p in gating):
            # 暴雨期间不进入全员转生倒计时；尸体可以等待同伴救援。
            if self.storm_active:
                self._all_dead_t = 0
                return
            if all(p.behavior.is_reincarnating() for p in gating):
                return                      # 倒计时中：不冒白点，也不清场
            self._all_dead_t += 1
            if self._all_dead_t < tuning.ALL_DEAD_GRACE_TICKS:
                return
            self._all_dead_t = 0
            for p in gating:
                p.behavior.begin_reincarnation()
            self._reincarnate_cleanup_pending = True
            return
        self._all_dead_t = 0
        # 清场只等「会转世的那些」醒过来 —— 永久死的猫崽不能把清场卡住。
        if self._reincarnate_cleanup_pending and all(not p.behavior.is_dead()
                                                     for p in gating):
            self._reincarnate_cleanup_pending = False
            # 全体复活＝换雨循环：场上所有东西（生物/物品/杆/花）一起清空
            self.clear_world_for_reincarnation()

    def set_zerog(self, on):
        """开/关无重力；开时摘掉所有果柄。"""
        self.zerog_on = bool(on)
        self.gravity_target = 0.0 if on else 1.0
        if self.zerog_on:
            for f in self.fruits:
                f.stalk = None
                if f.state == ItemState.HANGING:
                    f.state = ItemState.FREE

    def _zerog_update(self):
        """room_gravity 缓动向 target 并注入物体。"""
        rg = self.room_gravity + (self.gravity_target - self.room_gravity) * GRAV_EASE
        if abs(rg - self.gravity_target) < 1e-3:
            rg = self.gravity_target
        self.room_gravity = rg
        for f in self.fruits:
            f.room_gravity = rg
        for s in self.stones:
            s.room_gravity = rg
        for m in self.slimemolds:
            m.room_gravity = rg
        for b in self.batflies:
            b.room_gravity = rg
        for lz in self.lizards:
            lz.room_gravity = rg
        for sc in self.squidcadas:
            sc.room_gravity = rg
        for nw in self.needleworms:
            nw.room_gravity = rg
        for pr in self.pearls:
            pr.room_gravity = rg
        for sp in self.spears:
            sp.room_gravity = rg
        for sc in self.scavengers:
            sc.room_gravity = rg
        for sd in self.seeds:
            sd.room_gravity = rg

    def set_water(self, on):
        """开/关水。"""
        self.water_on = bool(on)
        self.water_target = (self._HL - self._HL * tuning.WATER_FULL_DEPTH) if on else self._HL
        if on and self.water_surface is None:
            self.water_y = self._HL
            self.water_surface = WaterSurface(self._WL, self._HL, tuning.WATER_SPACING)

    def spawn_bubble(self, x, y, vx, vy):
        """生成一个上浮气泡。"""
        if self.water_surface is None or len(self.bubbles) >= tuning.BUBBLE_MAX:
            return
        from .world.bubbles import Bubble
        self.bubbles.append(Bubble(x, y, vx, vy, self._bubble_rng))

    def _water_update(self):
        """water_y 逼近 target 并推进水面。"""
        surf = self.water_surface
        if surf is None:
            return
        rate = self._HL * tuning.WATER_FULL_DEPTH / tuning.WATER_EASE_TICKS
        target = self.water_target
        moving = abs(self.water_y - target) > 1e-6
        if self.water_y < target:
            self.water_y = min(self.water_y + rate, target)
        elif self.water_y > target:
            self.water_y = max(self.water_y - rate, target)
        # 排空到底则释放
        if not self.water_on and self.water_y >= self._HL - 0.5:
            self.water_surface = None
            self.water_y = None
            self.bubbles = []
            for o in (*self.fruits, *self.seeds, *self.stones, *self.slimemolds,
                      *self.batflies, *self.lizards, *self.squidcadas, *self.pearls,
                      *self.needleworms, *self.spears, *self.scavengers):
                o.water_y = None
            for pet in self.pets:
                pet.body.water_surface = None
                pet.body.bubble_cb = None
            return
        surf.base_y = self.water_y
        if moving:                                   # 注满/排空搅面
            if self.water_on:
                surf.waterfall_hit(0.0, self._WL, tuning.WATER_FLOW)
            else:
                surf.drain_affect(0.0, self._WL, tuning.WATER_FLOW)
        surf.step()
        for o in (*self.fruits, *self.seeds, *self.stones, *self.slimemolds,
                  *self.batflies, *self.lizards, *self.squidcadas, *self.pearls,
                  *self.needleworms, *self.spears, *self.scavengers):
            o.water_y = surf.level_at(o.x)
        for pet in self.pets:
            if self.shelters and self.shelter_of(pet.body.chunk1.x, pet.body.chunk1.y):
                pet.body.water_surface = None    # 庇护所是干燥的安全区：不在里面游泳/溺水
                pet.body.bubble_cb = None
                continue
            pet.body.water_surface = surf
            pet.body.bubble_cb = self.spawn_bubble

    def _water_splash_detect(self):
        """穿越水面激起入水溅。"""
        surf = self.water_surface
        if surf is None or surf.splash_stop > 0:
            return
        objs = []
        for pet in self.pets:
            b = pet.body
            objs.append(b.chunk0)
            objs.append(b.chunk1)
        for f in self.fruits:
            if f.state in (ItemState.FREE, ItemState.HANGING):
                objs.append(f)
        for s in self.stones:
            if s.state == ItemState.FREE:
                objs.append(s)
        for m in self.slimemolds:
            if m.state in (ItemState.FREE, ItemState.HANGING):
                objs.append(m)
        for b in self.batflies:
            if b.state == ItemState.FREE:
                objs.append(b)
        for lz in self.lizards:
            if lz.state == ItemState.FREE:
                objs.append(lz)
        for sc in self.squidcadas:
            if sc.state == ItemState.FREE:
                objs.append(sc)
        for nw in self.needleworms:
            if nw.state == ItemState.FREE:
                objs.append(nw)
        for pr in self.pearls:
            if pr.state == ItemState.FREE:
                objs.append(pr)
        for sp in self.spears:
            if sp.state == ItemState.FREE and not sp.stuck:
                objs.append(sp)
        for sc in self.scavengers:
            if sc.state == ItemState.FREE:
                objs.append(sc)
        for sd in self.seeds:
            if sd.state == ItemState.FREE:
                objs.append(sd)
        for o in objs:
            lvl = surf.level_at(o.x)
            vy = o.vy
            if vy > 3.0 and o.last_y < lvl <= o.y:
                pass                                 # 向下穿越（y↓）
            elif vy < -3.0 and o.last_y > lvl >= o.y:
                pass                                 # 向上穿越
            else:
                continue
            impulse = lerp(vy * o.rad * lerp(o.mass, 1.0, 0.3) / 3.0, 10.0, 0.5)
            if abs(impulse) > abs(vy):
                impulse = vy
            surf.splash(o.x, impulse)
            if abs(impulse) > 5.0:
                surf.ripple_ring(o.x)
            surf.splash_stop = 10
            break                                    # 每 tick 只溅一次

    def _pet_of_chunk(self, chunk):
        """这个 BodyChunk 属于哪只猫（不是猫的 chunk → None）。

        撞击回调只拿到 chunk，不拿到主人；这里按 chunk0/chunk1 反查一次。
        只在真的发生硬撞时才走，不在每帧路径上。
        """
        for p in getattr(self, "pets", ()):
            b = getattr(p, "body", None)
            if b is None:
                continue
            if chunk is b.chunk0 or chunk is b.chunk1:
                return p
        return None

    def _fall_stun(self, pet, speed):
        """高处落地摔晕：晕眩时长随落地速度线性加长（用户口径）。

        走 FSM 的 ``apply_stun``（入 Stunned 态、松杆、清手势），没有行为层
        的假对象退回直接写 body.stun。与砸晕/电晕不同，摔晕**不掉手上的东西**
        （``drop_items=False``）、**醒来也不暴怒**（``rage=False``）：不然每次落地
        都把手里的果子/矛扔了、再暴走一两分钟，取食/投掷/社交链会被反复打回原点。
        """
        ticks = int(FALL_STUN_TICKS + (float(speed) - FALL_STUN_SPEED)
                    * FALL_STUN_PER_SPEED)
        ticks = int(clampf(ticks, 1, FALL_STUN_MAX))
        beh = getattr(pet, "behavior", None)
        if beh is not None:
            try:
                beh.apply_stun(ticks, drop_items=False, rage=False)
                return
            except Exception:
                pass
        b = getattr(pet, "body", None)
        if b is not None:
            b.stun = max(int(getattr(b, "stun", 0) or 0), ticks)

    def _shake_impact(self, chunk, direction, speed, strength, ix, iy):
        """地形硬撞回调，累加抖动偏移；够重的落地顺手把这只猫摔晕一会儿。"""
        pet = self._pet_of_chunk(chunk)
        if pet is not None and getattr(getattr(pet, "cat", None), "key", "") == "gourmand":
            ix *= SHAKE_GOURMAND_MUL       # 饕餮的震动略夸张（用户口径）
            iy *= SHAKE_GOURMAND_MUL
        self._shake[0] = clampf(self._shake[0] + ix, -SHAKE_MAX, SHAKE_MAX)
        self._shake[1] = clampf(self._shake[1] + iy, -SHAKE_MAX, SHAKE_MAX)
        down = float(direction[1]) if isinstance(direction, (tuple, list)) else 0.0
        if pet is not None and down > 0.0 and float(speed) >= FALL_STUN_SPEED:
            self._fall_stun(pet, float(speed))
        # 原版 NoiseTracker / ReactToNoise（LizardAI.cs:1741）：撞击地形的响声会引来蜥蜴
        if strength > 0.0 and self.lizards:
            x, y = getattr(chunk, "x", None), getattr(chunk, "y", None)
            if x is not None and y is not None:
                for lz in self.lizards:
                    lz.hear_noise(x, y)

    def _cold_update_world(self):
        """暴风雪三角计时推进，返回 cycle_prog。"""
        cycle_prog = 0.0
        if self.blizzard_on:
            self.blizzard_timer += 1
            if self.blizzard_timer >= tuning.COLD_BLIZZARD_TOTAL:
                self.blizzard_on = False
                self.blizzard_timer = 0
                if self.env_target == "blizzard":     # 自停后目标回落，防被重新点燃
                    self.env_target = "none"
                sp = getattr(self, "_settings_panel", None)
                if sp is not None and hasattr(sp, "refresh_env"):
                    sp.refresh_env()
            else:
                ramp = tuning.COLD_BLIZZARD_RAMP
                hold_end = tuning.COLD_BLIZZARD_TOTAL - ramp
                t = self.blizzard_timer
                if t < ramp:
                    cycle_prog = t / ramp
                elif t < hold_end:
                    cycle_prog = 1.0
                else:
                    cycle_prog = 1.0 - (t - hold_end) / ramp
        self.cold_cycle_prog = cycle_prog
        return cycle_prog

    def _tick_fruits(self):
        """推进放果子物理。"""
        self._step_fruit_drag()
        if self.fruits:
            for f in self.fruits:
                f._impact_cb = self._shake_impact
                f.step(self._WL, self._HL)
            self.fruits = [f for f in self.fruits if f.state != ItemState.EATEN]

    def _tick_stones(self):
        """推进放石头物理。"""
        self._step_stone_drag()
        if self.stones:
            for s in self.stones:
                s._impact_cb = self._shake_impact
                s.step(self._WL, self._HL)
            self._step_stone_hit()
            self._step_stone_cursor_hit()
            self.stones = [s for s in self.stones if s.state != ItemState.GONE]

    def _tick_slimemolds(self):
        """推进放黏菌物理。"""
        self._step_slimemold_drag()
        if self.slimemolds:
            for m in self.slimemolds:
                m._impact_cb = self._shake_impact
                m.step(self._WL, self._HL)
            self.slimemolds = [m for m in self.slimemolds if m.state != ItemState.EATEN]

    def _tick_batflies(self):
        """推进放蝙蝠物理。"""
        self._step_batfly_drag()
        if self.batflies:
            for b in self.batflies:
                b._impact_cb = self._shake_impact
                b.step(self._WL, self._HL)
            self._step_batfly_shove()
            self._cull_flung_corpses()
            self.batflies = [b for b in self.batflies if b.state != ItemState.EATEN]

    def _tick_lizards(self):
        """推进放蜥蜴（入口，便于与其它 _tick_* 并列）。"""
        self._step_lizards()

    def _collide_objects(self):
        """物体间通用碰撞互推。"""
        chunkphys.collide_objects([*(pet.body for pet in self.pets),
                                   *self.fruits, *self.seeds, *self.stones,
                                   *self.slimemolds, *self.pearls])

    # ── 按猫杀死编排 ──
    def request_kill(self, pet):
        """右键「杀死该猫」：无确认，直接杀死。"""
        if pet.behavior is None:
            return
        pet.behavior.kill()

    def _storm_kill_click(self, pos) -> bool:
        """暴雨中点击：随机杀死一只仍活着的成年蛞蝓猫（**不管在不在庇护所**）。

        只跟「暴雨在不在下 + 点杀开关开没开」有关；庇护所不免疫点击。
        """
        if not self.storm.active or not self.storm_lethal_clicks:
            return False
        candidates = [
            p for p in self.pets
            if not getattr(p, "is_pup", False)
            and not getattr(getattr(p, "behavior", None), "is_truly_dead", lambda: False)()
        ]
        if not candidates:
            return False
        self._storm_rng.choice(candidates).behavior.kill()
        return True

    # ── 增删猫 ──
    def add_pet(self, variant="saint"):
        """新增一只猫；满员或怎么都建不起来时返回 None（失败写 error.log）。"""
        if self.cat_slots_used() >= MAX_PETS:
            return None
        used_idx = {p.index for p in self.pets}
        used_id = {p.id for p in self.pets}
        k = 0
        while k in used_idx or f"pet-{k}" in used_id:   # 取首个空缺整数
            k += 1
        margin = self.layout_data.canvas_w / 2.0
        lo, hi = margin, max(margin + 1.0, self._WL - margin)
        pet = None
        for attempt in range(4):        # 换几个落点重试；真建不起来也要留下痕迹
            init_state = {"energy": 1.0, "temper": 0.0, "food": tuning.FOOD_INIT,
                          "karma": tuning.KARMA_INIT, "cold": 0.0}
            spawn_x = clampf(random.uniform(lo, hi), 0.0, self._WL)
            try:
                pet = PetUnit(self, k, f"pet-{k}", variant, init_state, spawn_x=spawn_x)
                break
            except Exception as exc:
                pet = None
                log_error("add_pet(%s) attempt %d failed: %r"
                          % (variant, attempt + 1, exc))
        if pet is None:
            log_error("add_pet(%s) gave up" % (variant,))
            return None
        self.pets.append(pet)
        try:
            self._give_spawn_gear(pet)       # 背矛类的出生装备坏了也不该卡住加猫
        except Exception as exc:
            log_error("_give_spawn_gear(%s) failed: %r" % (variant, exc))
        self._prev_dirty = None
        self._after_pets_changed()
        return pet

    def _give_spawn_gear(self, pet):
        """出生自带装备（原版 Player 按角色带物品）：会背矛的猫背上先来一支。"""
        from .world.spear import Spear
        if not pet.cat.tuning.get("back_spear"):
            return
        if getattr(pet.body, "back_spear", None) is not None:
            return
        sp = Spear(pet.body.chunk0.x + 8.0, pet.body.chunk0.y - 4.0, seed=self._spear_seed)
        self._spear_seed += 1
        self.spears.append(sp)
        pet.body.put_spear_on_back(sp)

    def remove_pet(self, pet):
        """移除一只常规蛞蝓猫，成功返回 True（场上至少留一只**常规**蛞蝓猫）。

        猫崽的身份是非蛞蝓猫生物，不占这个保底名额 —— 否则「1 成年 + 1 幼崽」
        时删掉成年猫会剩下 0 只蛞蝓猫。
        """
        if getattr(pet, "is_pup", False) or pet not in self.pets:
            return False
        adults = [p for p in self.pets if not getattr(p, "is_pup", False)]
        if len(adults) <= 1:
            return False
        return self._remove_pet(pet)

    def remove_pup(self, pet):
        """移除一只幼崽。

        幼崽不占常规蛞蝓猫名额，也不受「场上至少留一只猫」的保护 —— 删除模式
        与「清除可交互实体」都要能把它清掉。
        """
        if not getattr(pet, "is_pup", False) or pet not in self.pets:
            return False
        return self._remove_pet(pet)

    def clear_pups(self) -> int:
        """清掉场上全部幼崽，返回清掉几只。

        只在「清除可交互实体」里用；转生（clear_world_for_reincarnation）不清幼崽，
        而猫崽本来也不转世、不复活 —— 死了就留在场上。
        """
        n = 0
        for pet in list(self.pets):
            if getattr(pet, "is_pup", False) and self.remove_pup(pet):
                n += 1
        return n

    def _remove_pet(self, pet):
        """真正的卸载流程（守卫由 remove_pet / remove_pup 各自决定）。"""
        if getattr(pet, "controlled", False):
            self.stop_control()               # 先退出控制再移除
        self._drop_carried(pet)
        if pet.behavior is not None:          # 收尾行为控制器
            try:
                pet.behavior._break_active_controllers()
                pet.behavior.grab.force_release()
            except Exception:
                pass
        self.pets.remove(pet)
        self._prev_dirty = None
        self._after_pets_changed()
        return True

    def _drop_carried(self, pet):
        """持有物原地转 free —— 果子 / 石头 / 两手各一支的矛 / 背上的矛全都算。"""
        pet.body.drop_all()
    def _after_pets_changed(self):
        hud = self._hud
        if hud is not None and hasattr(hud, "rebuild_rows"):
            hud.rebuild_rows()
        if self._pets_changed_cb is not None:
            try:
                self._pets_changed_cb()
            except Exception:
                pass
        self.update()

    # ── 单猫操作菜单 ──
    def open_cat_menu(self, pet, global_pos):
        from .ui.catmenu import build_cat_menu
        menu = build_cat_menu(pet, self.pets, open_settings=self.open_settings, parent=self)
        menu.exec(global_pos)

    def open_settings(self):
        if self._open_settings_cb is not None:
            self._open_settings_cb()

    # ── 手动操控 ──
    def controlled_pet(self):
        """当前受控猫；无则 None。"""
        for pet in self.pets:
            if getattr(pet, "controlled", False):
                return pet
        return None

    def start_control(self, pet):
        """开始控制该猫。"""
        if pet is None or pet not in self.pets or getattr(pet, "controlled", False):
            return
        beh = pet.behavior
        if beh is None or beh.is_truly_dead() or beh.is_reincarnating() or beh.blocks_interaction():
            return
        self.stop_control()
        from .control.session import enter_control
        from .ui.controlhud import ControlHud
        hud = ControlHud(self, pet)
        enter_control(pet, hud.current_input)
        self._control_hud = hud
        hud.show()      # 须同步执行，勿 QTimer 推迟

    def stop_control(self):
        """退出控制（幂等）。"""
        hud = self._control_hud
        self._control_hud = None
        pet = self.controlled_pet()
        if pet is not None:
            from .control.session import exit_control
            exit_control(pet)
        if hud is not None:
            hud.close()
            hud.deleteLater()

    def _dirty_rect(self):
        """计算全部在场物体的脏矩形，绘制取 last..cur 插值。"""
        xs, ys = [], []

        def put(x, y, lx, ly):
            xs.append(x); ys.append(y)
            xs.append(lx); ys.append(ly)

        for pet in self.pets:
            b, g = pet.body, pet.gfx
            for c in (b.chunk0, b.chunk1):
                put(c.x, c.y, c.last_x, c.last_y)
            put(g.head.x, g.head.y, g.head.lx, g.head.ly)
            for h in g.hands:
                put(h.x, h.y, h.lx, h.ly)
            xs.append(2.0 * b.chunk1.x - g.head.x)       # 镜像极值
            xs.append(2.0 * b.chunk1.last_x - g.head.lx)
            for s_ in pet.tail.segs:
                put(s_.x, s_.y, s_.lx, s_.ly)
            if pet.tongue is not None:
                for px, py in pet.tongue.positions():
                    xs.append(px); ys.append(py)
            rope = getattr(g, "_tongue_rope", None)
            if rope is not None:
                for px, py in rope:
                    xs.append(px); ys.append(py)
        for f in self.fruits:
            r = f.rad
            put(f.x - r, f.y - r, f.last_x - r, f.last_y - r)
            put(f.x + r, f.y + r, f.last_x + r, f.last_y + r)
            if f.stalk is not None:
                for px, py in f.stalk.points():
                    xs.append(px); ys.append(py)
        for st in self.stones:
            r = st.rad
            put(st.x - r, st.y - r, st.last_x - r, st.last_y - r)
            put(st.x + r, st.y + r, st.last_x + r, st.last_y + r)
        for m in self.slimemolds:
            gr = 70.0
            put(m.x - gr, m.y - gr, m.last_x - gr, m.last_y - gr)
            put(m.x + gr, m.y + gr, m.last_x + gr, m.last_y + gr)
            for t in m.tendrils:
                xs.append(t[0]); ys.append(t[1])
        for b in self.batflies:
            wr = 40.0                      # 翅展 pad
            put(b.x - wr, b.y - wr, b.last_x - wr, b.last_y - wr)
            put(b.x + wr, b.y + wr, b.last_x + wr, b.last_y + wr)
            put(b.lower_x - wr, b.lower_y - wr, b.last_lower_x - wr, b.last_lower_y - wr)
            put(b.lower_x + wr, b.lower_y + wr, b.last_lower_x + wr, b.last_lower_y + wr)
        for lz in self.lizards:
            pr = lz.bounding_pad()
            put(lz.x - pr, lz.y - pr, lz.last_x - pr, lz.last_y - pr)
            put(lz.x + pr, lz.y + pr, lz.last_x + pr, lz.last_y + pr)
            put(lz.head_x - pr, lz.head_y - pr, lz.head_lx - pr, lz.head_ly - pr)
            put(lz.head_x + pr, lz.head_y + pr, lz.head_lx + pr, lz.head_ly + pr)
            for s_ in lz.seg:
                put(s_.x - pr, s_.y - pr, s_.lx - pr, s_.ly - pr)
                put(s_.x + pr, s_.y + pr, s_.lx + pr, s_.ly + pr)
        for sc in self.squidcadas:
            pr_ = 40.0                       # 翅展 pad
            put(sc.x - pr_, sc.y - pr_, sc.last_x - pr_, sc.last_y - pr_)
            put(sc.x + pr_, sc.y + pr_, sc.last_x + pr_, sc.last_y + pr_)
        for nw in self.needleworms:
            pr_ = 40.0                       # 体节串 pad
            for s_ in nw.seg:
                put(s_.x - pr_, s_.y - pr_, s_.lx - pr_, s_.ly - pr_)
                put(s_.x + pr_, s_.y + pr_, s_.lx + pr_, s_.ly + pr_)
        for pr in self.pearls:
            r = pr.rad + 6.0
            put(pr.x - r, pr.y - r, pr.last_x - r, pr.last_y - r)
            put(pr.x + r, pr.y + r, pr.last_x + r, pr.last_y + r)
        for sp in self.spears:
            for px, py in (sp.tip(), sp.butt()):
                xs.append(px); ys.append(py)
            xs.append(sp.last_x); ys.append(sp.last_y)
        for sc in self.scavengers:
            gr = sc.bounding_pad()
            put(sc.x - gr, sc.y - gr, sc.last_x - gr, sc.last_y - gr)
            put(sc.x + gr, sc.y + gr, sc.last_x + gr, sc.last_y + gr)
        for cb in self.seedcobs:
            put(cb.p0[0], cb.p0[1], cb.p0l[0], cb.p0l[1])
            put(cb.p1[0], cb.p1[1], cb.p1l[0], cb.p1l[1])
            xs.append(cb.root_pos[0]); ys.append(cb.root_pos[1])
        for sd in self.seeds:
            r = sd.rad + 6.0
            put(sd.x - r, sd.y - r, sd.last_x - r, sd.last_y - r)
            put(sd.x + r, sd.y + r, sd.last_x + r, sd.last_y + r)
        for kf in self.karmaflowers:
            # 花体 + 花瓣 + 茎（茎尾钉在根上，可能比花体低 27px）。漏了它会出现
            # 「花不显示直到猫经过 / 吃完残影还在」——那片区域压根没进重绘。
            pr_ = 34.0                     # 花瓣贴图长 20 + 花环 13.5 + 光斑 18.75
            put(kf.x - pr_, kf.y - pr_, kf.last_x - pr_, kf.last_y - pr_)
            put(kf.x + pr_, kf.y + pr_, kf.last_x + pr_, kf.last_y + pr_)
            for pt_ in kf.petals:
                put(pt_[0], pt_[1], pt_[2], pt_[3])
            for sp_ in kf.stalk_pts:
                put(sp_[0], sp_[1], sp_[2], sp_[3])
        for pl in self.poles:
            if getattr(pl, "virtual", False):
                continue        # 光标杆每帧乱跑，不该撑大脏矩形
            xs.append(pl.ax); xs.append(pl.bx)
            ys.append(pl.ay); ys.append(pl.by)
        lamp = self.lamp
        if lamp is not None:
            gr = lamp.glow_radius()
            xs.append(lamp.anchor_x); xs.append(lamp.bulb_x)
            ys.append(lamp.anchor_y); ys.append(lamp.bulb_y)
            xs.append(lamp.bulb_x - gr); xs.append(lamp.bulb_x + gr)
            ys.append(lamp.bulb_y - gr); ys.append(lamp.bulb_y + gr)
        surf = self.water_surface
        if surf is not None:
            # 仅涨落/波动时并入全宽水带
            if self.water_y != self.water_target or surf.energy() > tuning.WATER_STILL_EPS:
                xs.append(0.0); xs.append(self._WL)
                ys.append(self.water_y - 40.0); ys.append(self._HL + self._ground_inset)
        for sh in (self.shelters or ()):
            # 庇护所整间：门板开合 / 拖动 / 删除都得落在重绘范围里
            bx0, by0, bx1, by1 = sh.safe_rect()
            xs.append(bx0); ys.append(by0); xs.append(bx1); ys.append(by1)
        if storm_hud.visible(self):   # HUD 只跟雨循环走，没有屋子也要重绘
            hx0, hy0, hx1, hy1 = storm_hud.hud_rect(self)
            xs.append(hx0); ys.append(hy0); xs.append(hx1); ys.append(hy1)
        s = self._scale
        pad = 60
        x0 = int((min(xs) - pad) * s); y0 = int((min(ys) - pad) * s)
        x1 = int((max(xs) + pad) * s); y1 = int((max(ys) + pad) * s)
        return QRect(x0, y0, x1 - x0, y1 - y0)

    def _draw_water(self, p):
        """绘制水体与水面高光。庇护所安全区挖洞 —— 里面不进积水。"""
        from PySide6.QtGui import QPolygonF, QPen
        p.save()
        shs = self.shelters or ()
        if shs:
            reg = QRegion(QRect(0, 0, int(self._WL) + 1, int(self._HL) + 48))
            for sh in shs:
                r = sh.safe_rect()
                reg = reg.subtracted(QRegion(QRect(int(r[0]), int(r[1]),
                                                   int(r[2] - r[0]) + 1, int(r[3] - r[1]) + 1)))
            p.setClipRegion(reg, Qt.ClipOperation.IntersectClip)
        surf = self.water_surface
        n = surf.n
        WL = self._WL
        bottom = self._HL + self._ground_inset
        base = surf.base_y
        h = surf.height
        pts = []
        for i in range(n):
            x = surf.point_x(i)
            if x > WL:
                x = WL
            pts.append((x, base + h[i]))
        poly = QPolygonF()
        for x, y in pts:
            poly.append(QPointF(x, y))
        # 水体必须向左右和底部多画一圈；世界震屏时也不会从透明桌宠窗口边缘露白。
        bleed = 24.0
        poly.append(QPointF(WL + bleed, bottom + bleed))
        poly.append(QPointF(-bleed, bottom + bleed))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*tuning.WATER_BODY_RGBA))
        p.drawPolygon(poly)
        if self.bubbles:
            self._draw_bubbles(p)
        # 一次性画折线，防重叠叠 alpha
        pen = QPen(QColor(*tuning.WATER_SURFACE_RGBA))
        pen.setWidthF(2.0)
        p.setPen(pen)
        line = QPolygonF()
        for x, y in pts:
            line.append(QPointF(x, y))
        p.drawPolyline(line)
        p.restore()

    def _draw_bubbles(self, p):
        """绘制溺水气泡。"""
        ts = self._ts
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setOpacity(tuning.BUBBLE_OPACITY)
        for b in self.bubbles:
            x = b.last_x + (b.x - b.last_x) * ts
            y = b.last_y + (b.y - b.last_y) * ts
            sc = b.full_size * tuning.BUBBLE_DRAW_SCALE
            blit(p, self.atlas, "LizardBubble5", x, y, 0.0, sc, sc,
                 tuning.BUBBLE_RGBA, ax=0.5, ay=0.5)
        p.restore()

    def _alpha_pad(self, p):
        """放置模式（庇护所框选等）：给整窗补一层 alpha=1 的底。

        Windows 对分层窗口按像素 alpha 做命中测试，全透明像素上的点击会直接穿到下层
        窗口（桌面/浏览器），窗口收不到 mousePressEvent —— 表现就是「庇护所拖不动」。
        DestinationOver 只改完全透明的像素（补成 alpha=1 的黑，肉眼不可见）；已经画过
        的像素 alpha 基本不变（±1/255），半透明预览依旧保持半透明。
        """
        p.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_DestinationOver)
        p.fillRect(QRectF(0.0, 0.0, float(self.width()), float(self.height())),
                   QColor(0, 0, 0, 1))
        p.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver)

    def paintEvent(self, _):
        # 像素模式：先在 WL×HL 低分辨率缓冲里 1:1 画完，再整数倍最近邻放大到窗口，
        # 得到与本体一致的硬边像素观感。关时直接画到窗口。
        s = self._scale or 1
        bw = max(1, -(-self.width() // s))
        bh = max(1, -(-self.height() // s))
        if pixelmode.PIXEL:
            buf = self._pixbuf
            if buf is None or buf.width() != bw or buf.height() != bh:
                buf = QImage(bw, bh, QImage.Format.Format_ARGB32_Premultiplied)
                self._pixbuf = buf
            # 清屏挪到算出脏区之后：只擦要重画的那块（整窗刷新时才擦整张）

        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            if pixelmode.PIXEL:
                # 只重绘 Qt 标记的脏区（设备像素 → 逻辑像素）
                cr = p.clipBoundingRect()
                bp = QPainter(buf)
                try:
                    bp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                    aa_hint(bp, False)
                    # 空剪辑区 = 无剪辑（Qt 对未设置剪辑的 painter 返回空 QRectF）
                    cw_ok = cr.width() > 0.0 and cr.height() > 0.0
                    if cw_ok and (cr.x() > 0.0 or cr.y() > 0.0
                                  or cr.right() + 1.0 < bw * s or cr.bottom() + 1.0 < bh * s):
                        lx0 = max(0, int(cr.x()) // s)
                        ly0 = max(0, int(cr.y()) // s)
                        lx1 = min(bw, -(-int(cr.right()) // s) + 1)
                        ly1 = min(bh, -(-int(cr.bottom()) // s) + 1)
                        clear = QRectF(lx0, ly0, max(0, lx1 - lx0), max(0, ly1 - ly0))
                        bp.setClipRect(clear)
                        # 只在脏区里擦：CompositionMode_Source 覆盖写透明＝清空，
                        # 脏区外的像素保持上一帧内容不动。
                        bp.setCompositionMode(
                            QPainter.CompositionMode.CompositionMode_Source)
                        bp.fillRect(clear, QColor(0, 0, 0, 0))
                        bp.setCompositionMode(
                            QPainter.CompositionMode.CompositionMode_SourceOver)
                    else:
                        buf.fill(Qt.GlobalColor.transparent)
                    self._paint_world(bp, 1.0, hud=False)
                finally:
                    bp.end()
                p.drawImage(QRect(0, 0, bw * s, bh * s), buf)
                # 雨眠计时器画在放大**之后**：不参与像素化滤镜，
                # 层级最高、且圆点/描边保持清晰
                p.save()
                p.scale(s, s)
                storm_hud.draw_storm_hud(p, self)
                p.restore()
                if self._place_mode:
                    self._alpha_pad(p)
                return
            self._paint_world(p)
            if self._place_mode:
                self._alpha_pad(p)
        finally:
            p.end()

    def _paint_world(self, p, draw_scale=None, hud=True):
        # 图层序：果绳/烟 → 猫身 → 杆/手 → 果石黏菌蝠 → 水 → 灯 → 特效 → 雪
        # 像素模式下缓已是 1:1 逻辑像素，不再乘放大倍率
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        sc = self._scale if draw_scale is None else draw_scale
        p.scale(sc, sc)
        if self._shake[0] or self._shake[1]:
            p.translate(self._shake[0], self._shake[1])

        p.save()
        p.setClipRect(self._ground_clip(), Qt.ClipOperation.IntersectClip)
        if self.fruits:
            self._draw_fruit_ropes(p)

        if self.seedcobs:
            self._draw_seedcobs(p)
        p.restore()

        self._draw_fx_under(p)

        # 暴雨雨幕属于屏幕空间，不跟随世界震屏；安全洞跟随庇护所位置。
        if self.rain.active:
            p.save()
            if self._shake[0] or self._shake[1]:
                p.translate(-self._shake[0], -self._shake[1])
            rain_draw.draw_rain_under(p, self.rain, self.shelters, self._WL, self._HL, self._shake)
            p.restore()

        if self.shelters:
            # 后层（内腔暗底 + 墙体 + 结构）画在猫之前：躲进去的猫仍然看得见，
            # 大门也一并画在猫之前（桌宠里不能让门把躲进去的猫盖住）。
            p.save()
            p.setClipRect(self._ground_clip(), Qt.ClipOperation.IntersectClip)
            self._draw_shelter_backs(p)
            self._draw_shelter_fronts(p)
            p.restore()

        p.save()
        p.setClipRect(self._ground_clip(), Qt.ClipOperation.IntersectClip)

        if self.extra_walls:
            self._draw_walls(p)          # 手绘墙：压在猫下面，和庇护所墙体同层
        if self.spears:
            self._draw_back_spears(p)
            self._draw_low_spears(p)
        if self.needle_threads:          # 活针的细线压在猫与生物之下
            self._draw_needle_threads(p)

        for pet in self.pets:
            fx = pet.behavior.exclusive_fx() if pet.behavior is not None else None
            if fx is not None:
                fx.draw_under(p, self._ts)
            pet.gfx.draw_sprites(p, self.atlas, timeStacker=self._ts)

        if self.poles:
            self._draw_poles(p)
        for pet in self.pets:
            pet.gfx._draw_hand_grips(p, self.atlas, self._ts)

        if self.fruits:
            self._draw_fruits(p)
        if self.stones:
            self._draw_stones(p)
        if self.slimemolds:
            self._draw_slimemolds(p)
        if self.batflies:
            self._draw_batflies(p)
        if self.lizards:
            self._draw_lizards(p)
        if self.pearls:
            self._draw_pearls(p)
        if self.spears:
            self._draw_spears(p)
        if self.seeds:
            self._draw_seeds(p)
        if self.karmaflowers:
            self._draw_karmaflowers(p)
        if self.squidcadas:
            self._draw_squidcadas(p)
        if self.needleworms:
            self._draw_needleworms(p)
        if self.scavengers:
            self._draw_scavengers(p)
        p.restore()


        if self.water_surface is not None:
            self._draw_water(p)

        if self.lamp is not None:
            self._draw_lamp(p)

        self._draw_fx(p)

        if self.rain.active:
            p.save()
            if self._shake[0] or self._shake[1]:
                p.translate(-self._shake[0], -self._shake[1])
            rain_draw.draw_rain_over(p, self.rain, self.shelters, self._WL, self._HL, self._shake)
            p.restore()

        if self.snow_on:
            self._snow.draw(p, self._WL, self._HL, self._scale)

        if self._place_mode:
            p.save()
            p.setClipRect(self._ground_clip(), Qt.ClipOperation.IntersectClip)
            self._draw_place_hint(p)
            p.restore()

        if self.rain.active:
            p.save()
            if self._shake[0] or self._shake[1]:
                p.translate(-self._shake[0], -self._shake[1])
            rain_draw.draw_rain_darkness(p, self.rain, self.shelters, self._WL, self._HL, self._shake)
            p.restore()

        # 左下角固定 HUD：先抵消震屏平移，再画在屏幕（逻辑）坐标上
        if hud:
            if self._shake[0] or self._shake[1]:
                p.translate(-self._shake[0], -self._shake[1])
            storm_hud.draw_storm_hud(p, self)

    def _ground_clip(self):
        """地面线（HL）以下就是任务栏：生物/物体一律裁在线以上，脚踩在线上。

        绘制在裁剪前已经按 shake 平移过，所以裁剪线的设备坐标要减掉这次平移量。
        """
        return QRectF(-1.0e5, -1.0e5, 2.0e5, 1.0e5 + self._HL - self._shake[1])

    def mousePressEvent(self, e):
        if self._place_mode:
            if e.button() == Qt.MouseButton.LeftButton:
                lx, ly = self.to_logical(e.position().x(), e.position().y())
                if self._place_kind == "erase":
                    self.erase_at((lx, ly))       # 删除模式：删完继续留着，可连点
                elif self._place_kind in ("vpole", "hpole", "pole", "wall"):
                    self._begin_pole_place(lx, ly)      # 拉线放杆/放墙：松开时成地形
                elif self._place_kind == "stone":
                    self.place_stone(lx, ly)
                elif self._place_kind == "lamp":
                    self.place_lamp(lx, ly)
                elif self._place_kind == "slimemold":
                    self.place_slimemold(lx, ly)
                elif self._place_kind == "batfly":
                    self.place_batfly(lx, ly)
                elif self._place_kind == "lizard":
                    self.place_lizard(lx, ly)
                elif self._place_kind == "squidcada":
                    self.place_squidcada(lx, ly)
                elif self._place_kind == "needleworm":
                    self.place_needleworm(lx, ly)
                elif self._place_kind == "pearl":
                    self.place_pearl(lx, ly)
                elif self._place_kind == "spear":
                    self.place_spear(lx, ly)
                elif self._place_kind == "scavenger":
                    self.place_scavenger(lx, ly)
                elif self._place_kind == "seedcob":
                    self.place_seedcob(lx, ly)
                elif self._place_kind == "karmaflower":
                    self.place_karmaflower(lx, ly)
                elif self._place_kind == "slugpup":
                    self.place_slugpup(lx, ly)
                elif self._place_kind == "shelter":
                    self._begin_shelter_place(lx, ly)
                else:
                    self.place_fruit(lx, ly)
            elif e.button() == Qt.MouseButton.RightButton:
                self._exit_place_mode()
            return
        if not self.pets:
            return
        if e.button() == Qt.MouseButton.RightButton:
            # 右键命中区同左键抓取
            pos = self.to_logical(e.position().x(), e.position().y())
            from .control.mouse import hit_test, GRAB_PAD
            for pet in self.pets:
                if pet.behavior is not None and pet.behavior.blocks_interaction():
                    continue
                name, _ = hit_test(pet.body, pet.gfx, pos, pad=GRAB_PAD)
                if name is not None:
                    self.open_cat_menu(pet, e.globalPosition().toPoint())
                    return
            return
        if e.button() == Qt.MouseButton.LeftButton:
            pos = self.to_logical(e.position().x(), e.position().y())
            if self._storm_kill_click(pos):
                return
            grabbed = False
            for pet in self.pets:
                if getattr(pet, "controlled", False):
                    continue        # 受控猫禁左键抓取
                if pet.behavior is not None and pet.behavior.on_press(pos):
                    grabbed = True
                    break
            if not grabbed:
                # 蜥蜴体型最大，抓取优先级最高
                if not self._begin_lizard_drag(pos):
                    if not self._begin_scavenger_drag(pos):
                        if not self._begin_seedcob_drag(pos):
                            if not self._begin_squidcada_drag(pos):
                                if not self._begin_needleworm_drag(pos):
                                    if not self._begin_batfly_drag(pos):
                                        if not self._begin_pearl_drag(pos):
                                            if not self._begin_spear_drag(pos):
                                                if not self._begin_fruit_drag(pos):
                                                    if not self._begin_stone_drag(pos):
                                                        if not self._begin_karmaflower_drag(pos):
                                                            self._begin_slimemold_drag(pos)

    def keyPressEvent(self, e):
        if self._place_mode and e.key() == Qt.Key.Key_Escape:
            self._exit_place_mode()
            return
        super().keyPressEvent(e)

    def mouseMoveEvent(self, e):
        # 放庇护所：按下 → 拖 → 松开。万一「按下」那一下没落到窗口上（工具栏抢了
        # 鼠标），只要左键还按着，第一个移动事件就当作起点，拖动照样能框出矩形。
        if self._place_mode and self._place_kind in ("shelter", "vpole", "hpole",
                                                     "pole", "wall"):
            if e.buttons() & Qt.MouseButton.LeftButton:
                lx, ly = self.to_logical(e.position().x(), e.position().y())
                if self._place_kind == "shelter":
                    if self._shelter_drag_start is None:
                        self._shelter_drag_start = (lx, ly)
                elif getattr(self, "_pole_drag_start", None) is None:
                    self._pole_drag_start = (lx, ly)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._place_mode and self._place_kind in ("shelter", "vpole", "hpole",
                                                     "pole", "wall"):
            if e.button() == Qt.MouseButton.LeftButton:
                if self._place_kind == "shelter":
                    self._finish_shelter_place()
                elif self._place_kind == "wall":
                    self._finish_wall_place()
                else:
                    self._finish_pole_place()
            return
        if not self.pets:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._mouse_pole_suppress = MOUSE_POLE_RELEASE_TICKS   # 松手后 2s 不当杆
            for pet in self.pets:
                if pet.behavior is not None:
                    pet.behavior.on_release()
            self._end_fruit_drag()
            self._end_stone_drag()
            self._end_slimemold_drag()
            self._end_batfly_drag()
            self._end_lizard_drag()
            self._end_squidcada_drag()
            self._end_needleworm_drag()
            self._end_pearl_drag()
            self._end_spear_drag()
            self._end_scavenger_drag()
            self._end_seedcob_drag()
            self._end_karmaflower_drag()

    # ── 雨循环 + 庇护所 ──
    def shelter_of(self, x, y):
        """这个点落在哪间庇护所的安全区里（没有就 None）。"""
        for sh in self.shelters:
            if sh.contains(x, y):
                return sh
        return None

    def nearest_shelter(self, x, y=None):
        """离这个点最近的庇护所（雨前焦虑 / 躲雨都用同一份）。"""
        best, bd = None, 1.0e18
        yy = self._HL if y is None else y
        for sh in self.shelters:
            d = sh.distance_to(x, yy)
            if d < bd:
                best, bd = sh, d
        return best

    def _exposure_at(self, x, y):
        """这个点淋不淋得到雨 0~1（庇护所里 0，屋檐下 0.75）。"""
        cov = 0.0
        for sh in self.shelters:
            c = sh.coverage_at(x, y)
            if c > cov:
                cov = c
        return 1.0 - cov

    def _storm_tick(self):
        """雨循环一 tick：门 → 相位 → 雨强 → 震屏 → 积水目标。"""
        for sh in self.shelters:
            sh.step()
        self.storm.step(self.pets, self.shelters)
        if self._storm_cycle_seen != self.storm.cycle_id:
            # 新一轮雨开始：RainSystem 的「第一滴重雨」必须重新算一次
            # （旧实现只在关暴雨时 reset，第二场雨永远等不到那记重音）
            self._storm_cycle_seen = self.storm.cycle_id
            self.rain.reset_cycle()
        self._refresh_shelter_solids()
        self.storm_active = self.storm.active
        self.storm_pressure = self.storm.pressure
        self.rain.step(self.storm.rain_drive, 1.0)
        # 震屏：雨势折算成抖动，仍旧并入既有 self._shake（不另起一套）
        if self.rain.shake > 0.0:
            amp = self.rain.shake * RAIN_SHAKE_MAX
            rng = self._storm_rng
            self._shake[0] = clampf(self._shake[0] + rng.uniform(-amp, amp),
                                    -SHAKE_MAX, SHAKE_MAX)
            self._shake[1] = clampf(self._shake[1] + rng.uniform(-amp, amp),
                                    -SHAKE_MAX, SHAKE_MAX)
        if self.rain.impact and self.rain.impact_xy is not None:
            # 第一滴重雨：一次明显的震屏 + 地面冲击环
            ix, iy = self.rain.impact_xy
            self._shake[1] = clampf(self._shake[1] + SHAKE_MAX * 0.55,
                                    -SHAKE_MAX, SHAKE_MAX)
            self.add_shockwave(ix, iy, 96.0, flash=True)
        self._storm_flood_tick()
        self._storm_lethal_tick()

    def _sheltered(self, x, y):
        """这一点在不在任一庇护所内腔里（避雨 / 变暗 / 暴雨致死共用一套几何）。"""
        if x is None or y is None:
            return False
        for sh in (self.shelters or ()):
            if sh.contains(x, y):
                return True
        return False

    def _storm_lethal_tick(self):
        """暴雨峰值：没躲进庇护所的生物一律死亡（原版在雨里就是这个下场）。

        判据只看**雨强**（rain.intensity），所以集合期猫还在往屋里跑时不会被误杀，
        雨势爬满才收人头。庇护所内部按 Shelter.contains 判定，和避雨挖洞同一套几何。
        蛞蝓猫走环境致死（kill_storm：转世复活、暴雨期间冻结倒计时），
        其他生物直接 die()。
        """
        if self.rain.intensity < tuning.STORM_LETHAL_INTENSITY:
            return
        for pet in list(self.pets):
            beh = getattr(pet, "behavior", None)
            body = getattr(pet, "body", None)
            if beh is None or body is None:
                continue
            if beh.is_truly_dead():
                continue
            if self._sheltered(body.chunk1.x, body.chunk1.y):
                continue
            kill = getattr(beh, "kill_storm", None)
            if kill is not None:
                kill()
        for e in (*self.lizards, *self.batflies, *self.squidcadas,
                  *self.needleworms, *self.scavengers):
            if getattr(e, "state", None) != ItemState.FREE:
                continue
            if getattr(e, "dead", False):
                continue
            if self._sheltered(getattr(e, "x", None), getattr(e, "y", None)):
                continue
            # 蛞蝓猫之外：**留尸**（蜥蜴走 kill()，瘫软在地），不是直接 die() 抹掉。
            # 暴雨只是杀死庇护所外的生物，不该让尸体当场消失。
            k = getattr(e, "kill", None) or getattr(e, "die", None)
            if k is not None:
                k()

    def _storm_flood_tick(self):
        """积水：只改既有 water_target，不重做 flood 系统。"""
        if self.water_on:
            return                        # 手动「涨水」环境优先，别两套抢同一个 target
        f = self.rain.flood
        if f <= 0.001:
            if self.water_surface is not None:
                self.water_target = self._HL
            return
        if self.water_surface is None:
            self.water_y = self._HL
            self.water_surface = WaterSurface(self._WL, self._HL, tuning.WATER_SPACING)
        self.water_target = self._HL - self._HL * tuning.STORM_FLOOD_MAX_HEIGHT_FRAC * f

    def _rain_push_tick(self):
        """雨压：暴露在雨里的生物每 tick 被轻轻往下压（雨滴本身不做碰撞）。"""
        if not self.rain.active:
            return
        push = self.rain.rain_force
        for pet in self.pets:
            b = pet.body
            f = push(self._exposure_at(b.chunk1.x, b.chunk1.y))
            if f > 0.0:
                # SlugcatBody 自己没有 vy，速度在质点上（旧写法 b.vy += f 一淋到雨就 AttributeError）
                for c in b.collision_chunks():
                    c.vy += f
        for e in (*self.lizards, *self.batflies, *self.squidcadas, *self.needleworms):
            if getattr(e, "state", None) != ItemState.FREE:
                continue
            f = push(self._exposure_at(getattr(e, "x", 0.0), getattr(e, "y", 0.0)))
            if f > 0.0:
                e.vy += f

    # ── 暴雨设置 / 存档 ──
    def set_storm_block_clicks(self, on) -> None:
        """暴雨是否拦住真实点击（写进 params，存档时一并落盘）。"""
        self.storm_block_clicks = bool(on)
        self._params["storm_block_clicks"] = self.storm_block_clicks
        self._params.pop("storm_capture_clicks", None)   # 已迁移到新键，清掉旧的
        self._passthrough = None          # 下一帧重算穿透

    def set_storm_lethal_clicks(self, on) -> None:
        """暴雨中点击是否杀猫（与「拦住点击」互相独立）。"""
        self.storm_lethal_clicks = bool(on)
        self._params["storm_lethal_clicks"] = self.storm_lethal_clicks
        self._params.pop("storm_capture_clicks", None)

    def set_friendly_fire_protect(self, on) -> None:
        """友军伤害豁免：开着时蛞蝓猫投出的矛/石头不伤同伴。

        写进 params，存档时一并落盘。只影响伤害/眩晕结算，AI 走位照旧。
        """
        self.friendly_fire_protect = bool(on)
        self._params["friendly_fire_protect"] = self.friendly_fire_protect

    def set_storm_enabled(self, on):
        """开/关雨循环。**不会**自动放庇护所 —— 屋子由工具栏自己框选出来。"""
        on = bool(on)
        self.storm.enabled = on
        self._params["storm_enabled"] = on
        if not on:
            self.storm.reset()
            self.storm_active = False
            self.storm_pressure = 0.0
            for sh in self.shelters:
                sh.start_opening()
        self._prev_dirty = None
        self.update()

    def set_storm_durations(self, focus_minutes=None, warning_minutes=None,
                            sleep_minutes=None):
        self.storm.set_durations(focus_minutes, warning_minutes, sleep_minutes)
        self.update()

    def trigger_storm(self):
        """环境面板「暴雨」：立刻放雨 —— 一旦开始，猫的第一优先级就是进庇护所。

        没有庇护所也能放：雨照常跑完整套（变暗→第一滴→雨幕→震动→积水），只是
        没有安全区可躲，猫不会进庇护所。已经在暴雨里再点一次直接忽略。
        """
        if not self.storm.trigger_storm():
            return False
        self._prev_dirty = None
        self.update()
        return True

    def cancel_storm(self):
        """环境面板切走「暴雨」：收掉手动那一场（自动雨循环交给开关）。"""
        if not self.storm.cancel_manual():
            return False
        for sh in self.shelters:
            sh.start_opening()
        self._prev_dirty = None
        self.update()
        return True

    def storm_state(self):
        """存档用：庇护所 + 雨循环相位（退出时写进 params）。"""
        return {"shelters": [sh.to_dict() for sh in self.shelters],
                "storm": self.storm.to_dict()}

    def clear_shelters(self):
        if self.shelters:
            for sh in self.shelters:
                sh.start_opening()
            self.shelters = []
            self.world_version += 1
            self._refresh_shelter_solids()
            self._prev_dirty = None
            self.update()

    def _draw_shelters(self, p):
        for sh in self.shelters:
            sh.draw(p)

    def _draw_shelter_backs(self, p):
        for sh in self.shelters:
            sh.draw_back(p)

    def _draw_shelter_fronts(self, p):
        atlas = getattr(self, "atlas", None)
        for sh in self.shelters:
            sh.draw_front(p, atlas)

    def _refresh_shelter_solids(self):
        """把庇护所的真墙体同步给物理层（门关到位后入口也变实心）。

        两张表：``solids`` 给生物 / 物品 / 尸体；``cat_solids`` 给蛞蝓猫。
        墙真变了（新建 / 拆掉 / 门关上）就把 geometry_version +1，
        让寻路缓存知道「前提变了」。
        """
        rects, crows = [], []
        for sh in (getattr(self, "shelters", None) or ()):
            try:
                rects.extend(sh.solid_rects())
                crows.extend(sh.cat_solid_rects())
            except Exception:
                pass
        # 手绘墙条：和庇护所墙体走同一张表（生物/物品用 solids，猫用 cat_solids）。
        # 于是真碰撞、挡视线、竖墙可爬（navgeom 从 solids 读竖边）一次到位。
        for w in (getattr(self, "extra_walls", None) or ()):
            rects.append(tuple(w))
            crows.append(tuple(w))
        if (list(rects) != list(chunkphys.solids())
                or list(crows) != list(chunkphys.cat_solids())):
            chunkphys.set_solids(rects, crows)
            self.geometry_version = getattr(self, "geometry_version", 0) + 1

    # ── 摆放庇护所：按下起点 → 拖出矩形 → 松开生成 ──
    def enter_place_shelter_mode(self):
        self._place_mode = True
        self._place_kind = "shelter"
        self._shelter_drag_start = None
        self._begin_place_capture()
        return True

    def _begin_shelter_place(self, lx, ly):
        self._shelter_drag_start = (lx, ly)

    def _shelter_drag_rect(self):
        """当前拖出来的预览庇护所 —— 像资源管理器框选那样，**任意矩形**，不贴地。"""
        cur = self.cursor_logical()
        if cur is None:
            return None
        ticks = int(tuning.STORM_DOOR_TICKS)
        tpl = template_of("large")
        aw, ah = tpl.aspect
        ar = float(ah) / float(aw)
        if self._shelter_drag_start is None:
            # 还没按下：光标处给一个模板比例的默认大小
            h = max(Shelter.MIN_H, 110.0)
            w = max(Shelter.MIN_W, h / ar)
            return Shelter(cur[0] - w * 0.5, cur[1] - h * 0.5, w, h, None, self._WL,
                           seed=self._shelter_seed, door_ticks=ticks, template=tpl)
        sx, sy = self._shelter_drag_start
        cx, cy = cur
        x0, x1 = min(sx, cx), max(sx, cx)
        y0, y1 = min(sy, cy), max(sy, cy)
        # 拖多大就是多大（不再被 760×340 裁掉），只夹到画布内并保底
        dw = min(max(x1 - x0, Shelter.MIN_W), max(Shelter.MIN_W, self._WL))
        dh = min(max(y1 - y0, Shelter.MIN_H), max(Shelter.MIN_H, self._HL))
        return Shelter(x0, y0, dw, dh, None, self._WL,
                       seed=self._shelter_seed, door_ticks=ticks, template=tpl)

    def _finish_shelter_place(self):
        if not self._place_mode or self._place_kind != "shelter":
            return None
        if self._shelter_drag_start is None:
            # 没有「按下」就没有框选出来的矩形。工具栏按钮那一下的松开有时会漏进
            # 窗口（grabMouse 抢在按键中途），旧实现会把这种松开当成一次点击，
            # 当场生成一个固定大小的庇护所 —— 表现就是「拖不动、大小固定」。
            # 这里直接忽略，保持放置模式，等真正的按下-拖-松开。
            return None
        sh = self._shelter_drag_rect()
        self._shelter_drag_start = None
        if sh is None:
            self._exit_place_mode()
            return None
        x, y, wd, ht, tpl = sh.x, sh.y, sh.w, sh.h, sh.template
        self._exit_place_mode()
        return self.add_shelter(x, y, wd, ht, template=tpl)

    def add_shelter(self, x, y, w=None, h=None, template=None, door_ticks=None):
        """按矩形放一间庇护所（工具栏框选松手也走这里）。不给尺寸就用模板比例的默认大小。"""
        tpl = template or template_of("large")
        aw, ah = tpl.aspect
        if w is None:
            w = min(220.0, self._WL * 0.32)
        if h is None:
            h = max(Shelter.MIN_H, float(w) * float(ah) / float(aw))
        if door_ticks is None:
            door_ticks = tuning.STORM_DOOR_TICKS
        sh = Shelter(x, y, w, h, None, self._WL, seed=self._shelter_seed,
                     door_ticks=int(door_ticks), template=tpl)
        self.shelters.append(sh)
        self._shelter_seed += 1
        self.world_version += 1
        self._refresh_shelter_solids()
        self._prev_dirty = None
        self.update()
        return sh

    def _draw_shelter_hint(self, p):
        if self._shelter_drag_start is None:
            self._draw_shelter_cursor_icon(p)   # 还没按下：光标处只显示庇护所图标
            return
        sh = self._shelter_drag_rect()
        if sh is None:
            return
        p.save()
        p.setOpacity(0.55)
        sh.draw(p)
        p.restore()

    def _draw_shelter_cursor_icon(self, p):
        """点击前的预览：光标处一个庇护所图标（wiki 原图）。拖动中仍然画矩形。"""
        cur = self.cursor_logical()
        if cur is None:
            return
        from PySide6.QtCore import QRectF
        from .ui.tabbar import _paint_place_icon

        d = SHELTER_HINT_ICON
        r = QRectF(cur[0] - d * 0.5, cur[1] - d * 0.5, d, d)
        p.save()
        p.setOpacity(0.85)
        _paint_place_icon(p, "shelter", r, getattr(self, "atlas", None))
        p.restore()