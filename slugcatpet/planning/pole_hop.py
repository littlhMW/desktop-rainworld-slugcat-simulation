"""杆间跳跃规划：从当前杆位带方向起跳，找一根『跳过去能在空中抓住』的杆。

原版 Controls/Pole_Movement 的 jump-pole-hopping：站在杆上（竖杆顶或横杆面）
朝一侧 beam jump 跳出，飞行中贴到另一根杆就抓住，于是能一路换杆爬到目的地。

弧线取 get_pole_jump_arc（空中松杆位起跳的实测轨迹，一路采到落地）——平地起跳弧
只覆盖「起跳点以上」那段，目标是下方的杆时根本扫不到。
"""
from __future__ import annotations

from ..behavior import tuning
from ..world.pole import VERTICAL
from .jump_arc import get_pole_jump_arc


def pole_hit(pole, x, y, r):
    """点 (x,y) 是否落在杆身抓取范围（r）内。"""
    if getattr(pole, "kind", None) == VERTICAL:
        lo, hi = min(pole.ay, pole.by), max(pole.ay, pole.by)
        return abs(x - pole.x) <= r and lo - r <= y <= hi + r
    lo, hi = min(pole.ax, pole.bx), max(pole.ax, pole.bx)
    return abs(y - pole.ay) <= r and lo - r <= x <= hi + r


def hop_plan(stats, poles, x, y, exclude=None, grab=None):
    """从 (x,y) 起跳：返回 (pole, move_dir, hit_ticks)（最先抓到的那根），没有则 None。"""
    if stats is None or not poles:
        return None
    r = tuning.POLE_AIRGRAB_R if grab is None else grab
    best = None
    for md in (1, -1):
        arc = get_pole_jump_arc(stats, md)
        for p in poles:
            if p is exclude:
                continue
            for i, (px, py) in enumerate(arc.points):
                if pole_hit(p, x + px, y + py, r):
                    if best is None or i < best[0]:
                        best = (i, p, md)
                    break
    if best is None:
        return None
    i, p, md = best
    return (p, md, i + 1)
