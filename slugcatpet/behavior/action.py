# -*- coding: utf-8 -*-
"""统一动作层：ActionSpec 注册表 + 分层仲裁器。

以前「什么时候做某个动作」散在很多地方：主 tick 里一长串 ``if ...:
_transition(...)``、每个角色自己的 ticker、mood 加权表、以及几个特殊动作各自的
触发块。同一个问题（这一刻做什么）有很多个答案，于是出现「代码里明明有、
行为里看不到」和「两套仲裁互相抢」。

这一层把「决定」收进一个注册表：

    ActionSpec(key, band, pre, gate, start, score, tags, cooldown, interrupt)
    ActionArbiter.decide(ctx) -> 本 tick 起手的动作

band（照文档的分类）：

    preempt      角色独有先手（工匠爆跳 / 溪流夺物 / 圣徒超度）。它**不在**主链
                 顺序里：各角色把自己的 ticker 留在原位，在原来的时机点用
                 ``try_action(key, ctx)`` 起手 —— 于是顺序与旧版逐 tick 一致，
                 但「什么时候做」都登记在同一张表上。
    emergency    保命。顺序即优先级（溺/无重力/避水/趋暖），命中即改态。
    need         该做的事（醒醒 / 让路 / 面敌 / 社交 / 进食 / 玩 / 睡）。
    personality  没事的时候想做什么：mood 加权表。由空闲态执行器查询注册表
                 （``pick_weighted`` 复刻 MoodArbiter.select 的同一套掷骰顺序）。

``start(ctx)`` 返回 ``True`` 表示「这一 tick 真的做了」。

链式语义：``decide`` 按 band 顺序、band 内按注册顺序**逐条**评估 ``gate``，
命中就 ``start``，然后继续评估后面的动作 —— 这正是旧版主 tick 里那条
互不互斥的 ``if`` 链的语义（旧版每个 ``if`` 都会被评估），所以把代码搬进注册表
不会改变行为，也不会改变随机数流。``pre(ctx)`` 是「必须无条件先跑的记账」
（冷却回落 / 计数器自增），放在注册表里让整条 tick 的顺序在一处可见。

``choose`` / ``pick`` 是单赢家视角：调试面板和测试用它们问「这只猫此刻最想做
什么」；``pick_weighted`` 是 personality band 的加权随机（唯一真正掷骰的 band）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, FrozenSet

# ── band ──
BAND_PREEMPT = "preempt"
BAND_EMERGENCY = "emergency"
BAND_NEED = "need"
BAND_PERSONALITY = "personality"
BAND_NAV = "nav"

# 主链 band 顺序：保命 → 该做的事（personality 由空闲态执行器查询，
# preempt 由角色 ticker 原位调用，都不在这里）
BAND_ORDER = (BAND_EMERGENCY, BAND_NEED)

# ── 动作标签（给「按类别查询 / 调试面板 / 测试」用）──
TAG_NAV = "nav"              # 位移：走 / 跳 / 爬杆 / 落杆 / 舌钩
TAG_FOOD = "food"            # 进食相关
TAG_INTERACT = "interact"    # 对着某个对象做事
TAG_SOCIAL = "social"        # 社交动作
TAG_PERSONALITY = "pers"     # 性格 / 心情
TAG_EMERGENCY = "emerg"      # 保命
TAG_CHARACTER = "char"       # 角色独有


@dataclass
class ActionContext:
    """一次仲裁要看的全部上下文（都是引用，不复制世界）。"""

    fsm: object
    cursor: tuple | None = None
    skip: set = field(default_factory=set)   # 本 tick 已让开的 key
    fired: list = field(default_factory=list)  # 本 tick 真的做了的 key（顺序）

    @property
    def body(self):
        return self.fsm.body

    @property
    def win(self):
        return self.fsm.win

    @property
    def state(self) -> str:
        return self.fsm.state

    def skip_from(self, band_keys) -> None:
        self.skip.update(band_keys)


@dataclass
class ActionSpec:
    """一个可仲裁的动作：「什么条件做（gate）+ 做的时候干什么（start）」。"""

    key: str
    band: str
    gate: Callable[[ActionContext], bool]
    start: Callable[[ActionContext], bool]
    pre: Callable[[ActionContext], None] | None = None   # 无条件记账（顺序敏感）
    score: Callable[[ActionContext], float] | None = None
    tags: FrozenSet[str] = frozenset()
    cooldown: int = 0          # start 成功后自动压这么多 tick
    interrupt: float = 0.0     # 同级排序键（大的先）；同级按注册顺序
    one_shot: bool = False     # True＝一次性动作（做完即结束，不驻留）

    def weight(self, ctx: ActionContext) -> float:
        if self.score is None:
            return 1.0
        try:
            w = float(self.score(ctx))
        except Exception:
            return 1.0
        return 0.0 if w != w or w < 0.0 else w


class ActionArbiter:
    """注册表 + 仲裁器。一个窗口一只猫一份。"""

    def __init__(self, rng=None):
        self.rng = rng
        self._specs: list[ActionSpec] = []
        self._by_key: dict[str, ActionSpec] = {}
        self._cd: dict[str, int] = {}
        self.last: str | None = None        # 本 tick 起手的动作（调试 / 面板 / 测试）
        self.trace: list[str] = []          # 本 tick 真的做了的动作（按顺序）
        self.errors: list = []              # 被挡下的异常（key, 详情）：不静默

    # ── 注册与查询 ──
    def register(self, spec: ActionSpec) -> ActionSpec:
        assert spec.key not in self._by_key, "重复注册动作：" + spec.key
        self._specs.append(spec)
        self._by_key[spec.key] = spec
        return spec

    def get(self, key) -> ActionSpec | None:
        return self._by_key.get(key)

    def keys(self, band: str | None = None, tag: str | None = None) -> list[str]:
        out = []
        for s in self._specs:
            if band is not None and s.band != band:
                continue
            if tag is not None and tag not in s.tags:
                continue
            out.append(s.key)
        return out

    def band(self, band: str) -> list[ActionSpec]:
        return [s for s in self._specs if s.band == band]

    # ── 冷却 ──
    def arm(self, key: str, ticks: int) -> None:
        if ticks > 0:
            self._cd[key] = max(self._cd.get(key, 0), int(ticks))

    def ready(self, key: str) -> bool:
        return self._cd.get(key, 0) <= 0

    def tick(self) -> None:
        for k, v in list(self._cd.items()):
            if v > 0:
                self._cd[k] = v - 1

    # ── 仲裁 ──
    def _eligible(self, spec: ActionSpec, ctx: ActionContext) -> bool:
        if spec.key in ctx.skip or not self.ready(spec.key):
            return False
        try:
            return bool(spec.gate(ctx))
        except Exception as e:
            self.errors.append((spec.key + ":gate", repr(e)))
            return False

    def eligible(self, band: str, ctx: ActionContext) -> list[ActionSpec]:
        return [s for s in self.band(band) if self._eligible(s, ctx)]

    def _ordered(self, band: str, ctx: ActionContext) -> list[ActionSpec]:
        cands = self.eligible(band, ctx)
        if band == BAND_PERSONALITY:
            # 性格层：按权重随机排序（不放回抽样），谁先谁后每 tick 都不同
            rest = list(cands)
            out = []
            while rest:
                ws = [max(1e-6, s.weight(ctx)) for s in rest]
                total = sum(ws)
                r = (self.rng.random() if self.rng is not None else 0.0) * total
                acc = 0.0
                for i, (s, w) in enumerate(zip(rest, ws)):
                    acc += w
                    if r <= acc:
                        out.append(rest.pop(i))
                        break
                else:
                    out.append(rest.pop())
            return out
        # preempt / emergency / need：interrupt 大的先，同级保持注册顺序
        return sorted(cands, key=lambda s: -s.interrupt)

    def _order_all(self, band: str) -> list[ActionSpec]:
        """本 band 全部动作的现场顺序（interrupt 大的先，同级按注册顺序）。

        不评估 gate：``run_band`` 要先跑 ``pre``（无条件记账）再评估 gate，
        否则依赖记账的 gate 会看到上一 tick 的状态。
        """
        return sorted(self.band(band), key=lambda s: -s.interrupt)

    def choose(self, band: str, ctx: ActionContext) -> ActionSpec | None:
        """单赢家视角：只看不跑（测试 / 面板用）。"""
        order = self._ordered(band, ctx)
        return order[0] if order else None

    def pick(self, band: str, ctx: ActionContext) -> ActionSpec | None:
        return self.choose(band, ctx)

    def run_band(self, band: str, ctx: ActionContext) -> list[ActionSpec]:
        """跑一个 band：按序评估 gate，命中就 start，继续评估后面的（链式）。"""
        fired = []
        order = (self._ordered(band, ctx) if band == BAND_PERSONALITY
                 else self._order_all(band))
        for spec in order:
            if spec.pre is not None:
                spec.pre(ctx)
            if not self._eligible(spec, ctx):
                continue
            try:
                ok = spec.start(ctx)
            except Exception as e:
                self.errors.append((spec.key + ":start", repr(e)))
                continue
            if ok:
                self.last = spec.key
                fired.append(spec)
                ctx.fired.append(spec.key)
                self.trace.append(spec.key)
                if spec.cooldown:
                    self.arm(spec.key, spec.cooldown)
            else:
                ctx.skip.add(spec.key)
        return fired

    def touch(self, band: str, ctx: ActionContext) -> None:
        """只跑一个 band 里全部 spec 的 pre（无条件记账），不做任何决定。"""
        for spec in self._order_all(band):
            if spec.pre is not None:
                try:
                    spec.pre(ctx)
                except Exception:
                    pass

    def try_action(self, key: str, ctx: ActionContext) -> bool:
        """点名跑一个动作（角色 ticker 用）：pre → gate → start。"""
        spec = self._by_key.get(key)
        if spec is None:
            return False
        if spec.pre is not None:
            spec.pre(ctx)
        if not self._eligible(spec, ctx):
            return False
        try:
            ok = bool(spec.start(ctx))
        except Exception:
            ok = False
        if ok:
            self.last = key
            ctx.fired.append(key)
            self.trace.append(key)
            if spec.cooldown:
                self.arm(key, spec.cooldown)
        return ok

    def decide(self, ctx: ActionContext) -> list[ActionSpec]:
        """主 tick 的唯一决策入口：先手 → 保命 → 该做的事。"""
        self.trace = []
        del self.errors[:]
        fired = []
        for band in BAND_ORDER:
            fired.extend(self.run_band(band, ctx))
        if not fired:
            self.last = None
        return fired

    # ── personality band：加权随机（复刻 MoodArbiter.select 的掷骰顺序）──
    def pick_weighted(self, ctx: ActionContext, noise_amp: float) -> ActionSpec | None:
        """合格候选按注册顺序各掷一次 uniform 噪声，再掷一次总权重抽一个。"""
        elig = self.eligible(BAND_PERSONALITY, ctx)
        if not elig:
            return None
        rng = self.rng
        if rng is None:
            return elig[0]
        weights = []
        for s in elig:
            try:
                w = s.score(ctx) if s.score is not None else 1.0
            except Exception:
                w = 1.0
            weights.append(max(0.0, float(w) + rng.uniform(0.0, noise_amp)))
        total = sum(weights)
        if total <= 0.0:
            return None
        r = rng.random() * total
        acc = 0.0
        for s, w in zip(elig, weights):
            acc += w
            if r <= acc:
                return s
        return elig[-1]

    def start_spec(self, spec: ActionSpec, ctx: ActionContext) -> bool:
        ok = bool(spec.start(ctx))
        if ok:
            self.last = spec.key
            ctx.fired.append(spec.key)
            self.trace.append(spec.key)
        return ok


def build_arbiter(rng=None) -> ActionArbiter:
    return ActionArbiter(rng)
