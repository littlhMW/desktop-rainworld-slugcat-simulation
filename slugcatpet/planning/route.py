# -*- coding: utf-8 -*-
"""路线代价：把「一条路」拆成时间 / 体力 / 风险 / 噪音 / 精度 / 后摇六个轴。

原版生物不追求最短时间：谨慎的个体宁可绕远走，急躁或勇敢的才愿意为省几 tick
去赌一个跳跃。过去 Planner 只按 time_est 排序，于是「理论上更快」就等于
「应该跳」，「走路更快」就等于「完全不跳」——那是能力查询器，不是规划器。

这里给每种动作一条 RouteEdge（六个轴），再按性格折成排序代价：

    route_cost = time
               + energy    * w_energy
               + risk      * w_risk
               + noise     * w_noise
               + precision * w_precision
               + recovery  * w_recovery

只改**排序**：Candidate.time_est 原样保留，执行器的超时与进度判断仍用真实耗时。

另外给出 landing_safe()：可接受落点不是整块平台，而是**内缩一圈**的那段
（平台宽 100 只认 12..88）。「理论上能跳过去」和「AI 愿意跳」是两回事，
这一层就是那个区别。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..behavior import tuning

# 落点安全边距：落点离平台边缘至少这么远（原版 AI 不会贴着边落地）
LAND_SAFETY_MARGIN = 12.0

# 各轴的「tick 当量」：把 0..1 的轴值折成和耗时同量级的数
ENERGY_TICKS = 10.0
NOISE_TICKS = 8.0
PRECISION_TICKS = 22.0
RECOVERY_TICKS = 9.0


@dataclass(frozen=True)
class RouteEdge:
    """一条路线候选在六个轴上的取值（time 由 Estimate 提供）。"""
    kind: str
    time: float
    energy: float = 0.0
    risk: float = 0.0
    noise: float = 0.0
    precision: float = 0.0
    recovery: float = 0.0


# 每种动作的非时间轴（沿用原版对「这个动作有多难」的直觉）
ROUTE_EDGE = {
    "walk": dict(risk=0.00, noise=0.05, precision=0.00, recovery=0.05),
    "tongue": dict(risk=0.15, noise=0.10, precision=0.45, recovery=0.15),
    "tonguehang": dict(risk=0.15, noise=0.10, precision=0.40, recovery=0.20),
    "climb": dict(risk=0.20, noise=0.05, precision=0.25, recovery=0.20),
    "hop": dict(risk=0.25, noise=0.20, precision=0.45, recovery=0.30),
    "poledrop": dict(risk=0.25, noise=0.15, precision=0.50, recovery=0.30),
    "poletongue": dict(risk=0.30, noise=0.15, precision=0.55, recovery=0.30),
    "jump": dict(risk=0.45, noise=0.25, precision=0.55, recovery=0.35),
    "polejump": dict(risk=0.50, noise=0.25, precision=0.60, recovery=0.40),
    "ceildrop": dict(risk=0.60, noise=0.30, precision=0.65, recovery=0.45),
    "backflip": dict(risk=0.70, noise=0.35, precision=0.70, recovery=0.55),
    "drop": dict(risk=0.15, noise=0.15, precision=0.20, recovery=0.15),
    "climb_pole": dict(risk=0.20, noise=0.05, precision=0.25, recovery=0.20),
    "pole_beam": dict(risk=0.50, noise=0.25, precision=0.60, recovery=0.40),
    "finish": dict(risk=0.05, noise=0.05, precision=0.10, recovery=0.05),
    "pyrojump": dict(risk=0.90, noise=0.85, precision=0.60, recovery=0.60),
}
_EDGE_DEFAULT = dict(risk=0.30, noise=0.15, precision=0.40, recovery=0.25)


def axis(pers, name: str, default: float = 0.5) -> float:
    """取性格轴 0..1（pers 可为 None）。"""
    if pers is None:
        return default
    try:
        return min(1.0, max(0.0, float(getattr(pers, name, default))))
    except (TypeError, ValueError):
        return default


def weights(pers) -> dict:
    """性格 → 六轴权重（时间轴恒 1.0，其余是「多少 tick 当量」的系数）。"""
    risk_tol = axis(pers, "risk_tolerance")
    hurry = axis(pers, "hurry")
    patience = axis(pers, "patience")
    activity = axis(pers, "activity")
    return {
        "time": 1.0,
        # 风险：与旧版 time*(1 + ROUTE_RISK_W*risk*fac) 同一条曲线
        "risk": tuning.ROUTE_RISK_W * (1.15 - 1.2 * risk_tol),
        # 体力：好动的猫不在乎多花点力气
        "energy": 0.30 * (1.10 - 0.6 * activity),
        # 噪音：谨慎的猫怕吵（吵会引来捕食者）
        "noise": 0.10 * (1.10 - 1.0 * risk_tol),
        # 精度：怕冒险 / 性子急的猫都不喜欢需要卡帧的动作
        "precision": 0.20 * (1.15 - 1.2 * risk_tol) + 0.08 * hurry,
        # 后摇：赶时间的猫最讨厌落地要重新站稳
        "recovery": 0.15 * (0.60 + 1.2 * hurry) * (1.10 - 0.3 * patience),
    }


def edge_for(key: str, time: float, energy: float = 0.0) -> RouteEdge:
    """由能力 key + 预估耗时/体力造一条 RouteEdge。"""
    spec = ROUTE_EDGE.get(key, _EDGE_DEFAULT)
    return RouteEdge(key, float(time), float(energy), spec["risk"], spec["noise"],
                     spec["precision"], spec["recovery"])


def route_cost(edge: RouteEdge, pers=None) -> float:
    """六轴加权总代价（只用于排序）。

    风险按**耗时比例**折算（旧版就是这条曲线：`time * (1 + W*risk*fac)`）——
    省的这点时间值不值得赌，取决于这段路有多长。其余四轴是附加量。
    """
    w = weights(pers)
    base = edge.time * (1.0 + edge.risk * w["risk"])
    return (base
            + edge.energy * ENERGY_TICKS * w["energy"]
            + edge.noise * NOISE_TICKS * w["noise"]
            + edge.precision * PRECISION_TICKS * w["precision"]
            + edge.recovery * RECOVERY_TICKS * w["recovery"])


def landing_safe(land_x: float, x0: float, x1: float,
                 margin: float = LAND_SAFETY_MARGIN) -> bool:
    """落点是否落在平台**内缩一圈**的安全段里（平台太窄时按中线判）。"""
    if x1 < x0:
        x0, x1 = x1, x0
    if x1 - x0 <= 2.0 * margin:
        mid = 0.5 * (x0 + x1)
        return abs(land_x - mid) <= max(1.0, (x1 - x0) * 0.5)
    return x0 + margin <= land_x <= x1 - margin
