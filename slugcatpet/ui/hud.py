"""状态面板 HUD：每猫一行体征，可拖动可隐藏。"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
                               QScrollArea, QSizeGrip, QSizePolicy, QToolButton)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

from ..i18n import t
from ..cats import display_order
from .hudrow import PetRow

REFRESH_MS = 200

_PANEL_QSS = (
    "#hudPanel{background:rgba(30,34,40,235);border-radius:10px;border:1px solid #4a5a3a;}"
    "QLabel{color:#e8f5d8;font-size:12px;}"
    "#hudName{color:#9fc080;font-size:12px;}"
    "#hudVal{color:#cfe8b8;font-size:11px;}"
    "#hudRowName{color:#aef156;font-size:13px;font-weight:bold;}"
    "#hudTitle{color:#9fc080;font-size:11px;}"
    "#hudClose{color:#cfe8b8;background:transparent;border:none;font-size:13px;"
    "font-weight:bold;padding:0 4px;}"
    "#hudClose:hover{color:#ffffff;background:rgba(190,90,80,180);border-radius:4px;}")


class _ResizeGrip(QSizeGrip):
    """右下角把手：只有**真的拖它**才算用户改过大小。

    窗口第一次 show() 也会发 resizeEvent，如果照单全收，面板就会把自己
    自适应出来的尺寸记成「用户尺寸」，以后再也不会跟着行数长缩了。
    """

    def __init__(self, hud):
        super().__init__(hud)
        self._hud = hud

    def mousePressEvent(self, ev):
        self._hud._user_dragging = True
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self._hud._user_dragging = False


class HudPanel(QWidget):
    def __init__(self, pet, params=None):
        super().__init__()
        self.pet = pet    # PetWindow
        self.params = params if params is not None else {}
        self._drag = None
        self._building = True
        self._auto_fitting = False
        self._user_dragging = False
        # 用户自己拖过大小就一直沿用它；从没拖过就按行数自适应
        self._user_size = self._load_size()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._build()
        if self._user_size is not None:
            self.resize(self._user_size[0], self._user_size[1])
        self._place()
        self._building = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        # 定时器由 toggle_visible 控制启停

        self.hide()

    def _load_size(self):
        """读回用户拖出来的面板尺寸（没存过 → None＝跟着内容自适应）。"""
        try:
            w = int(self.params.get("hud_w") or 0)
            h = int(self.params.get("hud_h") or 0)
        except (TypeError, ValueError):
            return None
        if w <= 0 or h <= 0:
            return None
        return (max(180, w), max(90, h))

    def _pets(self):
        # 猫崽的身份是非蛞蝓猫生物：不进状态面板（它们仍在场景里活动）。
        pets = getattr(self.pet, "pets", None) or [self.pet]
        return display_order(p for p in pets if not getattr(p, "is_pup", False))

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._panel = QWidget()
        self._panel.setObjectName("hudPanel")
        # 普通 QWidget 不画 QSS 背景 → 必须开 WA_StyledBackground，否则面板是透的
        self._panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._panel.setStyleSheet(_PANEL_QSS)
        pbox = QVBoxLayout(self._panel)
        pbox.setContentsMargins(10, 8, 10, 8)
        pbox.setSpacing(0)
        outer.addWidget(self._panel)

        # 行容器塞进滚动区：猫多到超过屏高时可以滚，不再被任务栏切掉
        self._rows_host = QWidget()
        self._vbox = QVBoxLayout(self._rows_host)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(6)
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._rows_host)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        # 滚动区视口/内容默认用调色板底色（浅灰）铺满，会把面板底色盖掉 → 全部透明
        self._rows_host.setAutoFillBackground(False)
        self._scroll.setAutoFillBackground(False)
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea > QWidget > QWidget{background:transparent;}"
            "QScrollBar:vertical{background:transparent;width:8px;margin:0;}"
            "QScrollBar::handle:vertical{background:rgba(150,180,120,150);"
            "border-radius:4px;min-height:24px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}")
        self._scroll.setMaximumHeight(self._max_view_h())
        head = QWidget()
        hbox = QHBoxLayout(head)
        hbox.setContentsMargins(0, 0, 0, 3)
        hbox.setSpacing(6)
        title = QLabel(t("hud_title"))
        title.setObjectName("hudTitle")
        hbox.addWidget(title)
        hbox.addStretch(1)
        self._close_btn = QToolButton(head)
        self._close_btn.setObjectName("hudClose")
        self._close_btn.setText("\u2715")           # ✕
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip(t("hud_close_tip"))
        self._close_btn.clicked.connect(self.toggle_visible)
        hbox.addWidget(self._close_btn)
        pbox.addWidget(head)
        pbox.addWidget(self._scroll)
        self._rows = []
        self._build_rows()
        self._fit_scroll()
        # 右下角拉伸手柄：面板能自己拖大小（没拖过时仍按行数自适应）
        self._grip = _ResizeGrip(self)
        self._grip.setFixedSize(16, 16)
        self._grip.setToolTip(t("hud_resize_tip"))
        self._sync_grip()
        self._grip.raise_()

    def _fit_scroll(self):
        """行区高度：没拖过大小就跟着行数走，拖过就让它填满面板。"""
        self._vbox.activate()
        want = self._rows_host.sizeHint().height() + 4
        if self._user_size is not None:
            self._scroll.setMinimumHeight(40)
            self._scroll.setMaximumHeight(self._max_view_h())
            return
        self._scroll.setFixedHeight(min(max(want, 40), self._max_view_h()))
        self._auto_fitting = True
        try:
            self.adjustSize()
        finally:
            self._auto_fitting = False

    def _sync_grip(self):
        """把手贴住右下角。"""
        grip = getattr(self, "_grip", None)
        if grip is None:
            return
        grip.move(max(0, self.width() - grip.width()),
                  max(0, self.height() - grip.height()))

    @staticmethod
    def _max_view_h() -> int:
        """行区最高不超过屏幕可用高度（留点余量给任务栏与窗口边）。"""
        scr = QGuiApplication.primaryScreen().availableGeometry()
        return max(160, scr.height() - 96)

    def _build_rows(self):
        for i, pet_unit in enumerate(self._pets()):
            if i > 0:
                self._vbox.addWidget(self._divider())
            row = PetRow(pet_unit, self)
            self._vbox.addWidget(row)
            self._rows.append(row)
        self._vbox.addStretch(1)          # 面板拉大时行不跟着摊开

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet("background:rgba(120,150,100,90);border:none;")
        return f

    def rebuild_rows(self):
        """增删猫后重排行。"""
        while self._vbox.count():
            item = self._vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                # 可见子控件直接解除 parent 会短暂变成独立顶层窗口。
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._rows = []
        self._build_rows()
        self._fit_scroll()
        self._refresh()
        self._place()

    def _place(self):
        # 只做屏内定位（尺寸自己管：没拖过＝内容自适应，拖过＝用户尺寸）
        self._panel.layout().activate()
        size = self.size()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = self.params.get("hud_x")
        y = self.params.get("hud_y")
        if x is None or y is None:
            x = screen.x() + 24
            y = screen.y() + 24
        x = max(screen.x(), min(screen.x() + screen.width() - size.width(), int(x)))
        y = max(screen.y(), min(screen.y() + screen.height() - size.height(), int(y)))
        self.move(x, y)
        self.params["hud_x"] = x
        self.params["hud_y"] = y

    def toggle_visible(self):
        # 实时记显隐（退出时查不到）
        if self.isVisible():
            self.hide()
            self._timer.stop()      # 隐藏期不空转
            self.params["hud_visible"] = False
        else:
            self.show()
            self.raise_()
            self._refresh()
            self._timer.start(REFRESH_MS)
            self.params["hud_visible"] = True

    def _refresh(self):
        if not self.isVisible():
            return
        replot = False
        for row in self._rows:
            replot = row.refresh() or replot
        if replot:
            self._fit_scroll()
            self._place()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._sync_grip()
        if self._building or self._auto_fitting:
            return
        size = (self.width(), self.height())
        if self._user_size == size:
            return
        if self._user_size is None and not self._user_dragging:
            return          # 自动贴合 / 首次显示给的尺寸：不算用户拖的
        # 用户拉过之后：按这个尺寸走，行区改成填满面板（装不下就滚动）
        self._user_size = size
        self.params["hud_w"], self.params["hud_h"] = size
        self._scroll.setMinimumHeight(40)
        self._scroll.setMaximumHeight(self._max_view_h())

    # 面板背景拖动整窗，行内由 PetRow 自理
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            p = ev.globalPosition().toPoint() - self._drag
            x = max(screen.x(), min(screen.x() + screen.width() - self.width(), p.x()))
            y = max(screen.y(), min(screen.y() + screen.height() - self.height(), p.y()))
            self.move(x, y)
            self.params["hud_x"] = x
            self.params["hud_y"] = y
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        ev.accept()
