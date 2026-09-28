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
_MIN_W = 60.0          # 太窄的窗口不算平台
_MIN_H = 24.0
_TOP_EPS = 4.0         # 顶边贴到/超出屏幕顶的窗口（最大化）不算平台

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def enabled() -> bool:
    """离屏（无真实桌面）时直接关闭。"""
    return os.environ.get("QT_QPA_PLATFORM") != "offscreen"


def enumerate_tops(own_hwnds, screen_x: float, screen_y: float, scale: float):
    """返回其它可见窗口顶边 [(x0, y0, x1)]，逻辑坐标（y0＝顶边 y）。"""
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
    out = []

    def _visit(hwnd, _lparam):
        try:
            if int(hwnd) in own or not user32.IsWindowVisible(hwnd):
                return True
            if user32.IsIconic(hwnd):
                return True
            ex = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            if ex & (_WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE):
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
            out.append((x0, y0, x1))
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(_ENUM_PROC(_visit), 0)
    except Exception:
        return []
    return out
