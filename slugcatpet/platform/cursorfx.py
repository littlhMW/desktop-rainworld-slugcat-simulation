"""光标劫持：落体→底边锁定，替换系统光标为"忙"样式。"""
from __future__ import annotations
import sys
import atexit
import threading

_IS_WIN = sys.platform == "win32"

# 计时单位为 tick（40Hz）；坐标为 Win32 物理像素
T_FALL_GRAV = 1.6
T_CURSOR_LOCK = 200
WATCHDOG_MAX = 400
# 墙钟兜底：一次劫持最多把系统光标夹住这么久。主循环一旦停摆（全屏让位会
# freeze_tick + 隐藏窗口），update() 不再被调用，ClipCursor 就会一直夹着 ——
# 那正是「鼠标位置被重置到屏幕某一点」。超过这个秒数由后台线程强制交还。
CLIP_WATCHDOG_SECONDS = 45.0

_ACTIVE = []             # 活动劫持列表

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    def _clip(x, y):
        r = _RECT(int(x), int(y), int(x) + 1, int(y) + 1)
        return bool(_user32.ClipCursor(ctypes.byref(r)))

    def _unclip():
        _user32.ClipCursor(None)

    _OCR_IDS = (32512, 32513, 32649)   # OCR_NORMAL/IBEAM/HAND
    _IDC_APPSTARTING = 32650           # 系统"忙"光标
    _SPI_SETCURSORS = 0x0057

    _user32.LoadCursorW.restype = ctypes.c_void_p
    _user32.LoadCursorW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    _user32.CopyIcon.restype = ctypes.c_void_p
    _user32.CopyIcon.argtypes = (ctypes.c_void_p,)
    _user32.SetSystemCursor.restype = wintypes.BOOL
    _user32.SetSystemCursor.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    _user32.SystemParametersInfoW.restype = wintypes.BOOL
    _user32.SystemParametersInfoW.argtypes = (wintypes.UINT, wintypes.UINT,
                                              ctypes.c_void_p, wintypes.UINT)

    def _set_busy_cursor():
        """替换系统箭头/文本/链接光标为"忙"样式；需 CopyIcon 因 SetSystemCursor 取走所有权。"""
        src = _user32.LoadCursorW(None, _IDC_APPSTARTING)
        if not src:
            return False
        ok = False
        for ocr in _OCR_IDS:
            h = _user32.CopyIcon(src)
            if h and _user32.SetSystemCursor(h, ocr):
                ok = True
        return ok

    def _restore_cursors():
        """从注册表重载全部系统光标恢复默认（幂等）。"""
        _user32.SystemParametersInfoW(_SPI_SETCURSORS, 0, None, 0)
else:
    def _clip(x, y):
        return False

    def _unclip():
        pass

    def _set_busy_cursor():
        return False

    def _restore_cursors():
        pass


class CursorHijack:
    """光标劫持。坐标 = Win32 物理像素（屏幕全局，已由 window 按 dpr 换算）。"""

    def __init__(self, dev_x, dev_y, screen_w, screen_h, screen_x=0, screen_y=0, mock=False,
                 lock_ticks=T_CURSOR_LOCK, mode="fall", watchdog_max=WATCHDOG_MAX,
                 restore_on_land=False):
        self.mock = mock or not _IS_WIN
        self.x = float(dev_x)
        self.y = float(dev_y)
        self.vy = 0.0
        self.W = screen_w
        self.H = screen_h
        self.x0 = screen_x
        self.y0 = screen_y
        self.bottom = screen_y + screen_h - 2
        self.mode = mode
        self.phase = "hold" if mode == "hold" else "fall"   # fall → lock → done；hold → done
        self.lock_ticks = int(lock_ticks)
        self.lock_t = 0
        self.watchdog = 0
        self.watchdog_max = int(watchdog_max)
        self.restore_on_land = bool(restore_on_land)   # 落到屏幕底边即恢复系统光标
        self.active = True
        self._wd = None
        _ACTIVE.append(self)
        if not self.mock:
            self._arm_watchdog()
            _set_busy_cursor()

    def _arm_watchdog(self):
        """后台墙钟兜底：主循环停摆时也能把光标交还（见 CLIP_WATCHDOG_SECONDS）。"""
        try:
            self._wd = threading.Timer(CLIP_WATCHDOG_SECONDS, _watchdog_fire, (self,))
            self._wd.daemon = True
            self._wd.start()
        except Exception:
            self._wd = None

    def hold_at(self, dev_x, dev_y):
        self.x = float(dev_x)
        self.y = float(dev_y)

    def update(self) -> bool:
        """推进一帧。返回是否仍活动。"""
        if not self.active:
            return False
        self.watchdog += 1
        if self.watchdog >= self.watchdog_max:
            self.release()
            return False

        if self.phase == "fall":
            self.vy += T_FALL_GRAV
            self.y += self.vy
            if self.y >= self.bottom:
                self.y = self.bottom
                self.vy = 0.0
                if self.restore_on_land:          # 超度：落地立刻还回光标，不再锁定
                    self.release()
                    return False
                self.phase = "lock"
                self.lock_t = 0
        elif self.phase == "lock":
            self.lock_t += 1
            if self.lock_t >= self.lock_ticks:
                self.release()
                return False

        self._apply()
        return True

    def _apply(self):
        """把系统光标夹在当前落点（ClipCursor）。

        绝不 SetCursorPos：那会把用户的鼠标**物理拽走**，正是「鼠标位置被重置到
        屏幕某一点」的来源。ClipCursor 失败就只是效果打了折扣，位置不动。
        """
        if self.mock or not self.active:
            return
        x = min(max(self.x, self.x0), self.x0 + self.W - 1)
        y = min(max(self.y, self.y0), self.y0 + self.H - 1)
        try:
            _clip(x, y)
        except Exception:
            pass

    def release(self):
        """释放 ClipCursor。幂等。"""
        if not self.active:
            return
        self.active = False
        self.phase = "done"
        wd, self._wd = self._wd, None
        if wd is not None:
            try:
                wd.cancel()
            except Exception:
                pass
        if not self.mock:
            try:
                _unclip()
            except Exception:
                pass
            try:
                _restore_cursors()
            except Exception:
                pass
        try:
            _ACTIVE.remove(self)
        except ValueError:
            pass


def abort_all():
    """释放所有活动劫持。"""
    for h in list(_ACTIVE):
        h.release()
    if _IS_WIN:
        try:
            _unclip()                              # 兜底
        except Exception:
            pass
        try:
            _restore_cursors()                     # 兜底
        except Exception:
            pass


def _watchdog_fire(hj):
    """后台兜底触发：无条件把这次劫持交还。"""
    try:
        hj.release()
    except Exception:
        pass


def release_others(keep=None):
    """释放除 keep 以外所有活动劫持。

    换新劫持前先清场，免得被顶掉的旧劫持留在 _ACTIVE 里再没人 update / release。
    """
    for h in list(_ACTIVE):
        if h is not keep:
            h.release()


atexit.register(abort_all)
