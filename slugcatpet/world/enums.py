"""运行时状态字符串常量。"""
from __future__ import annotations


class ItemState:
    FREE = "free"
    HANGING = "hanging"
    CARRIED = "carried"
    MOUSE = "mouse"
    EATEN = "eaten"
    GONE = "gone"


class SpearLifecycle:
    """矛的**唯一**生命周期口径（文档 §6 / §11）。

    以前「飞 / 插住 / 插生物 / 钉成杆 / 被拿着 / 消失」散落在
    ``_thrown / stuck / stuck_to / pinned / pole / state`` 六个字段里，
    每处代码各判一部分，才出现「黑矛该消失却要鼠标点」「钉成杆的黑针
    永远保留」这类对不上的事。这里只做**只读归一**：谁都不用改现有字段，
    只是「现在算哪一阶段」有一个共同答案。
    """
    FREE = "free"                          # 躺在地上 / 静止的普通矛
    THROWN = "thrown"                      # 正在飞（Mode.Thrown）
    STUCK = "stuck"                        # 插在墙 / 地上
    STUCK_TO_CREATURE = "stuck_to_creature"  # 插在生物身上跟着走
    PINNED_POLE = "pinned_pole"            # 钉成场景杆（pinned 且有 pole）
    CARRIED = "carried"                    # 被拿着
    GONE = "gone"                          # 已消失


class TongueMode:
    IDLE = "idle"
    SHOOTING = "shooting"
    ATTACHED = "attached"
    RETRACTING = "retracting"

