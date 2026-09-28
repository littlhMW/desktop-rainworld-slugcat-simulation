"""窗口四边＝实体墙/地面（原版房间边界等价）。

坐标系 y↓：左/右边缘＝竖直墙，下边缘＝地面，上边缘＝天花板（可攀附吊挂）。
原版本体里房间边界由 Room 的 tile 层提供（Solid/Floor/Ceiling），
宠物没有 tile 世界，直接把窗口四边当作 Solid 处理；
本模块只做「谁贴在哪面墙/天花上」的查询，供 FSM 与生物 AI 使用。
"""
from __future__ import annotations

WALL_TOUCH_PAD = 3.0     # chunk 圆心离边缘多近算贴墙
CEIL_TOUCH_PAD = 3.0
WALL_HUG_PAD = 18.0      # 攀墙时髋心离墙距离：手够得到墙、又不把身体画出屏
CEIL_EDGE_PAD = 10.0     # 吊顶时胸心离左右边缘的余量


def wall_side(chunk, WL: float, pad: float = WALL_TOUCH_PAD) -> int:
    """单个 chunk 贴墙侧：-1 左墙 / +1 右墙 / 0 不在墙上。"""
    cx = getattr(chunk, "cx", 0)
    if cx < 0:
        return -1
    if cx > 0:
        return 1
    x = getattr(chunk, "x", 0.0)
    r = getattr(chunk, "rad", 0.0) or 0.0
    if x - r <= pad:
        return -1
    if x + r >= WL - pad:
        return 1
    return 0


def on_wall(body, WL: float, pad: float = WALL_TOUCH_PAD) -> int:
    """两 chunk 任一贴墙 → 返回墙侧；否则 0。"""
    for c in body.collision_chunks():
        s = wall_side(c, WL, pad)
        if s:
            return s
    return 0


def on_ceiling(body, pad: float = CEIL_TOUCH_PAD) -> bool:
    """是否贴到上边缘（撞顶或已顶到）。"""
    for c in body.collision_chunks():
        if getattr(c, "cy", 0) < 0:
            return True
        if c.y - c.rad <= pad:
            return True
    return False


def near_ceiling(body, reach: float) -> bool:
    """胸心离上边缘在 reach 之内（够得着吊挂）。"""
    c0 = body.collision_chunks()[0]
    return c0.y - c0.rad <= reach


def wall_hold_x(side: int, WL: float, pad: float = WALL_HUG_PAD) -> float:
    return pad if side < 0 else WL - pad
