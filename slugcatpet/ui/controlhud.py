"""控制 HUD：受控猫键盘输入窗，失焦暂停。"""
from __future__ import annotations
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QLayout
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QGuiApplication

from ..i18n import t
from ..control.input import InputPackage
from ..control.keymap import load_keymap, key_display_name
from .catmenu import pet_label

WATCH_MS = 200
BOTTOM_MARGIN = 24

_PANEL_QSS = (
    "#ctrlPanel{background:rgba(13,17,23,230);border-radius:14px;border:1px solid rgba(239,243,248,78);}"
    "#ctrlTitle{color:#eef1f4;font-size:13px;font-weight:bold;}"
    "#ctrlKeys{color:#eef1f4;font-size:11px;}"
    "QPushButton{background:rgba(255,255,255,12);color:#eef1f4;border:1px solid rgba(239,243,248,74);"
    "border-radius:8px;font-size:12px;padding:5px 12px;}"
    "QPushButton:hover{background:rgba(255,255,255,30);border-color:rgba(245,248,252,150);}"
    "QPushButton:pressed{background:rgba(245,248,252,224);color:#11151a;}")

_PAUSED_QSS = "color:#eef1f4;font-weight:bold;"


class ControlHud(QWidget):
    """受控会话键盘入口窗，current_input() 供 session provider。"""

    def __init__(self, window, pet):
        super().__init__()
        self._window = window
        self.pet = pet
        self._held = set()      # 当前按住的按键
        self._mouse_pick = False
        self._mouse_throw = False
        self._paused = False
        self._drag = None
        self._keymap = load_keymap()
        # The scene window receives mouse pick/throw clicks while a cat is
        # controlled.  On Windows that activation can move keyboard focus away
        # from this small tool window, which used to make movement silently
        # stop until the HUD was clicked again.  Keep a QApplication-level
        # key filter for the lifetime of the session so movement keys remain
        # live while the scene has focus (Escape still exits from anywhere).
        self._app = QApplication.instance()
        if self._app is not None:
            self._app.installEventFilter(self)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # 勿设 WA_ShowWithoutActivating，键盘唯一入口

        self._build()
        self._place()

        self._watch = QTimer(self)
        self._watch.timeout.connect(self._check_session)
        self._watch.start(WATCH_MS)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        panel = QWidget()
        panel.setObjectName("ctrlPanel")
        panel.setStyleSheet(_PANEL_QSS)
        box = QVBoxLayout(panel)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(6)

        title = QLabel(t("ctrlhud_title", name=pet_label(self.pet, list(self._window.pets))))
        title.setObjectName("ctrlTitle")
        box.addWidget(title)

        k = {a: key_display_name(a).upper() for a in ("left", "right", "up", "down", "jump")}
        self._keys_text = t("ctrlhud_keys",
                            move=k["up"] + k["left"] + k["down"] + k["right"],
                            jump=k["jump"])
        self._keys = QLabel(self._keys_text)
        self._keys.setObjectName("ctrlKeys")
        box.addWidget(self._keys)

        btn = QPushButton(t("ctrlhud_exit"))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # 防空格触发按钮
        btn.clicked.connect(lambda: self._window.stop_control())
        box.addWidget(btn)
        outer.addWidget(panel)

    def _place(self):
        # 默认屏底中央
        self.layout().activate()
        size = self.sizeHint()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - size.width()) // 2
        y = screen.y() + screen.height() - size.height() - BOTTOM_MARGIN
        self.move(x, y)

    # 输入 provider（暂停返零包防冻结）
    def current_input(self) -> InputPackage:
        if self._paused:
            return InputPackage()
        km, held = self._keymap, self._held

        def down(action):
            k = km.get(action)
            return k is not None and k in held

        x = (1 if down("right") else 0) - (1 if down("left") else 0)
        y = (1 if down("up") else 0) - (1 if down("down") else 0)
        # 鼠标动作由主窗口转发为单帧脉冲：右键拾取，左键投掷。
        pckp = down("grab") or self._mouse_pick
        thrw = down("throw") or self._mouse_throw
        self._mouse_pick = self._mouse_throw = False
        return InputPackage(x=x, y=y, jmp=down("jump"), pckp=pckp, thrw=thrw)

    def mouse_action(self, *, pick=False, throw=False):
        """主窗口把受控猫的右/左键动作转进下一物理帧。"""
        self._mouse_pick = self._mouse_pick or bool(pick)
        self._mouse_throw = self._mouse_throw or bool(throw)
        self._set_paused(False)

    def _check_session(self):
        # 会话失效则自关
        if not getattr(self.pet, "controlled", False) or self.pet not in self._window.pets:
            self._window.stop_control()

    def eventFilter(self, watched, event):
        """Capture control keys even when a scene click moved focus to PetWindow.

        ``ControlHud`` is a separate tool window.  A click on the transparent
        scene activates the main window, so relying only on ``keyPressEvent``
        leaves the cat with an apparently dead controller.  The filter is
        scoped to the active control session and consumes only keyboard events;
        all mouse/window events continue through Qt unchanged.
        """
        if (getattr(self.pet, "controlled", False)
                and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)):
            if event.isAutoRepeat():
                return True
            key = int(event.key())
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._window.stop_control()
                    return True
                self._held.add(key)
            else:
                self._held.discard(key)
            self._set_paused(False)
            return True
        return super().eventFilter(watched, event)

    def _set_paused(self, paused: bool):
        if paused == self._paused:
            return
        self._paused = paused
        self._held.clear()
        if paused:
            self._mouse_pick = self._mouse_throw = False
        self._keys.setText(t("ctrlhud_paused") if paused else self._keys_text)
        self._keys.setStyleSheet(_PAUSED_QSS if paused else "")
        self.setWindowOpacity(0.7 if paused else 1.0)

    # 焦点：show 即抢焦（需同步栈内）
    def showEvent(self, e):
        super().showEvent(e)
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._set_paused(False)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._set_paused(True)

    def keyPressEvent(self, e):
        if e.isAutoRepeat():
            return
        if e.key() == Qt.Key.Key_Escape:
            self._window.stop_control()
            return
        self._held.add(int(e.key()))

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        self._held.discard(int(e.key()))

    # 拖动（钳屏内），点击恢焦
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.activateWindow()
            self.setFocus()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            p = ev.globalPosition().toPoint() - self._drag
            x = max(screen.x(), min(screen.x() + screen.width() - self.width(), p.x()))
            y = max(screen.y(), min(screen.y() + screen.height() - self.height(), p.y()))
            self.move(x, y)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        ev.accept()

    def closeEvent(self, ev):
        # The HUD is recreated for each session.  Remove the application
        # filter before Qt destroys it, otherwise a deferred key event could
        # target a stale controller during the next session.
        if self._app is not None:
            try:
                self._app.removeEventFilter(self)
            except RuntimeError:
                pass
        self._held.clear()
        self._mouse_pick = self._mouse_throw = False
        super().closeEvent(ev)
