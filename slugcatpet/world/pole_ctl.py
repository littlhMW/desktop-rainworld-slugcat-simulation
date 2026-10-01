# -*- coding: utf-8 -*-
"""竖杆 / 横杆控制器的公共协议（文档 §9）。

物理是分开的（竖杆沿 Y 轴攀爬；横杆沿 X 轴移动 / 吊挂 / 撑起），**协议**统一：
FSM 只认 ``PoleController``，问它 ``kind / pole / update() / release() / jump_off() /
can_handoff() / handoff() / position()``，不必知道手上这台是竖杆机器还是横杆机器。
"""
from __future__ import annotations

from ..behavior import tuning


class PoleController:
    """两种杆控制器的公共外壳：谁接管身体，谁负责解钉 / 收手 / 交还换杆请求。"""

    kind = ""                 # "vertical" / "horizontal"
    handoff_req = None        # 待办的换杆请求 ("h", 横杆, x) / ("v", 竖杆, start)
    air_target = None         # 空中要抓住的那根杆（跳杆用）
    no_handoff = False        # 临时竖杆（爆米花植株）不允许换杆

    # ── 子类必须实现 ──
    def update(self, *args, **kwargs) -> bool:
        """推进一 tick；返回 True＝这条杆上的流程结束（该下杆 / 换杆了）。"""
        raise NotImplementedError

    def _reset_pose(self) -> None:
        """收手 / 收重心（子类各自实现）。"""

    def _extra_release(self) -> None:
        """release 里各自多出来的收尾（子类覆盖）。"""

    # ── 协议本体 ──
    def release(self) -> None:
        """松手：解钉 + 清动画 + 收手。两条杆子上走的是同一件事。"""
        b = self.body
        b.coyote = max(getattr(b, "coyote", 0), tuning.POLE_COYOTE_TICKS)
        b.chunk0.pinned = False
        b.chunk1.pinned = False
        b.on_pole = False
        b.animation = None
        self._extra_release()
        self._reset_pose()

    def jump_off(self) -> bool:
        """带动作跳离这根杆（默认＝向下跳；横杆覆盖成「站杆面起跳」）。"""
        self._jump_down()
        return True

    def can_handoff(self) -> bool:
        """有换杆请求、且这根杆允许换（爆米花那种临时竖杆不允许）。"""
        return bool(self.handoff_req) and not self.no_handoff

    def handoff(self):
        """取走换杆请求（取走即清空）；FSM 拿到就去切另一根杆。"""
        ho, self.handoff_req = self.handoff_req, None
        return ho

    def position(self):
        """这根杆上的身体锚点（胯部世界坐标）：画图 / 面板 / 交接都用它。"""
        b = self.body
        return (float(b.chunk1.x), float(b.chunk1.y))
