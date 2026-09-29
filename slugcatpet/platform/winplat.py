"""其它窗口＝一块平地：枚举可见顶层窗口的顶边，换算成桌宠逻辑坐标。

桌宠始终画在别人窗口之上（always-on-top），不能被人家的窗口体挡住去路，
所以只把别人的**顶边**当单向平台（从上落下即站住），窗口本体不参与碰撞。
"""
from __future__ import annotations
import ctypes
import os
from ctypes import wintypes

# 壳/桌面类：不算平台
_SHELL_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "TrayNotifyWnd", "Button",
    "Windows.UI.Core.CoreWindow", "ForegroundStaging", "MultitaskingViewFrame",
    "TaskListThumbnailWnd", "XamlExplorerHostIslandWindow", "SysShadow",
    "Windows.Internal.Shell.TabProxyWindow", "ApplicationManager_ImmersiveShellWindow",
}
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TRANSPARENT = 0x00000020
_DWMWA_CLOAKED = 14    # DWM 给窗口打的「隐身」标记（UWP 挂起 / 别的虚拟桌面）
_MIN_W = 60.0          # 太窄的窗口不算平台
_MIN_H = 24.0
_TOP_EPS = 4.0         # 顶边贴到/超出屏幕顶的窗口（最大化）不算平台

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def enabled() -> bool:
    """离屏（无真实桌面）时直接关闭。"""
    return os.environ.get("QT_QPA_PLATFORM") != "offscreen"


def _cut_segments(segs, l: float, r: float):
    """从若干区间里减掉 [l, r]（前面窗口盖住的部分）。"""
    out = []
    for a, b in segs:
        if r <= a or l >= b:
            out.append((a, b))
            continue
        if l > a:
            out.append((a, l))
        if r < b:
            out.append((r, b))
    return out


def _cloaked(hwnd) -> bool:
    """DWM 认为这窗口「隐身」了吗（UWP 挂起、被切走的虚拟桌面、被壳藏起来的）。

    这类窗口 IsWindowVisible 仍返回 True，GetWindowRect 给的还是**上次可见时
    的陈旧矩形**（本机实测：挂起的「设置」停在 (328,92)-(1543,1032)）——
    会被当成一块隐形地板，猫一落上去就悬在半空。取不到 dwmapi（老系统）
    就当作没隐身，行为与以前一致。
    """
    try:
        v = wintypes.DWORD(0)
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, _DWMWA_CLOAKED, ctypes.byref(v), 4) != 0:
            return False
        return v.value != 0
    except Exception:
        return False


def enumerate_tops(own_hwnds, screen_x: float, screen_y: float, scale: float):
    """返回其它可见窗口顶边 [(x0, y0, x1)]，逻辑坐标（y0＝顶边 y）。

    被前面窗口挡住的顶边不算地面：只保留「露出来的」那几段
    （桌宠永远画在最上层，挡住的段不能走，否则猫会悬在别人窗口上走）。
    """
    if scale <= 0 or not enabled():
        return []
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return []
    own = set()
    for h in own_hwnds:
        try:
            own.add(int(h))
        except Exception:
            pass
    my_pid = int(ctypes.windll.kernel32.GetCurrentProcessId())
    rects = []          # 按 Z 序（前→后）收集窗口矩形，逻辑坐标

    def _visit(hwnd, _lparam):
        try:
            if int(hwnd) in own or not user32.IsWindowVisible(hwnd):
                return True
            if user32.IsIconic(hwnd):
                return True
            # 自家进程的辅助窗口（托盘提示 / QToolTip / 热键消息窗 / 各种隐藏助手）
            # 永远不会是平台。这些窗口拿不到 winId（隐藏时 winId()==0）也不在
            # topLevelWidgets 里，靠 own 集合漏得掉 → 猫会站上一个「隐形窗口」。
            wpid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if int(wpid.value) == my_pid:
                return True
            if _cloaked(hwnd):      # 挂起的 UWP / 别的虚拟桌面：矩形是陈旧的
                return True
            ex = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            if ex & (_WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE | _WS_EX_TRANSPARENT):
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value in _SHELL_CLASSES:
                return True
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            w = (rect.right - rect.left) / scale
            if w < _MIN_W or (rect.bottom - rect.top) / scale < _MIN_H:
                return True
            x0 = (rect.left - screen_x) / scale
            x1 = (rect.right - screen_x) / scale
            y0 = (rect.top - screen_y) / scale
            if y0 <= _TOP_EPS:                      # 最大化/全屏：顶边在屏幕外
                return True
            rects.append((x0, y0, x1, (rect.bottom - screen_y) / scale))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(_ENUM_PROC(_visit), 0)
    except Exception:
        return []

    return clip_tops(rects)


def clip_tops(rects):
    """按 Z 序（前→后）裁出「露出来的」顶边 [(x0, y0, x1)]，逻辑坐标。

    rects: [(x0, y0, x1, y1)] 前→后。后面的窗口顶边被前面窗口竖直盖住的段不算地面。
    """
    out = []
    for i, (x0, y0, x1, y1) in enumerate(rects):
        segs = [(x0, x1)]
        for j in range(i):                          # 前面的窗口若竖直盖住这条顶边就裁掉
            fl, ft, fr, fb = rects[j]
            if ft <= y0 <= fb:
                segs = _cut_segments(segs, fl, fr)
                if not segs:
                    break
        for a, b in segs:
            if b - a >= _MIN_W:
                out.append((a, y0, b))
    return out
