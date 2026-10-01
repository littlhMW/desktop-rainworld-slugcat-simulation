# -*- coding: utf-8 -*-
"""逃生方向解算（文档 §4「CrawlAway 拆成 EscapeSolver」）。

以前匍匐逃跑每帧自己重算 ``CRAWL_AWAY_STEP``：只看威胁在左还是在右，根本
不知道 ThreatField 的「左边危险、右边安全」。这里把「往哪边挪」抽出来，输出
``movement_dir / posture / face``；CrawlAway 只负责「以趴姿执行 movement_dir」，
不再兼职逃跑算法。

硬规则（文档 §4）：``on_pole / on_hpole / airborne`` 不进入 CrawlAway，所以
这里只解算地面匍匐，杆上逃生走杆自己的那几个动作。
"""
from __future__ import annotations

DEFAULT_STEP = 60.0


class EscapePlan:
    """一次逃生解算的结果：往哪走、什么姿态、身体朝哪。"""

    __slots__ = ("movement_dir", "posture", "face")

    def __init__(self, movement_dir: float, posture: str, face: int):
        self.movement_dir = float(movement_dir)
        self.posture = str(posture)      # "crawl" / "walk"
        self.face = int(face)            # 身体朝向：+1 右 / -1 左

    def __repr__(self):
        return "EscapePlan(dir=%+.0f, %s, face=%+d)" % (
            self.movement_dir, self.posture, self.face)


def _danger(field, x, y) -> float:
    """这个位置的危险度；没有危险表时返回 0（退回旧的左右口径）。"""
    if field is None:
        return 0.0
    try:
        return float(field.danger_at(x, y))
    except Exception:
        return 0.0


def solve_escape(body, threat, field=None, step=DEFAULT_STEP) -> EscapePlan:
    """威胁在侧时往**危险度更低**的一侧挪，脸仍然朝着威胁。

    ``threat`` 是这一次躲避锁定的那一只（不逐帧换人，否则 away 会翻号）。
    给了 ``field``（ThreatField）就比左右两侧的真实危险度；没给就退回
    「躲开威胁那一侧」的旧口径。
    """
    bx = float(body.chunk1.x)
    by = float(body.chunk1.y)
    tx = float(getattr(threat, "x", bx))
    face = 1 if tx >= bx else -1
    if field is None:
        movement_dir = -float(face)
    else:
        d_l = _danger(field, bx - float(step), by)
        d_r = _danger(field, bx + float(step), by)
        if abs(d_r - d_l) < 1e-6:
            movement_dir = -float(face)      # 两侧一样危险：按威胁在侧躲
        else:
            movement_dir = 1.0 if d_r < d_l else -1.0
    return EscapePlan(movement_dir, "crawl", face)
