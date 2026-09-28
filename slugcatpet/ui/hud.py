"""状态面板 HUD：每猫一行体征，可拖动可隐藏。"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFrame, QLayout,
                               QScrollArea, QSizePolicy)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

from .hudrow import PetRow

REFRESH_MS = 200

_PANEL_QSS = (
    "#hudPanel{background:rgba(30,34,40,235);border-radius:10px;border:1px solid #4a5a3a;}"
    "QLabel{color:#e8f5d8;font-size:12px;}"
    "#hudName{color:#9fc080;font-size:12px;}"
    "#hudVal{color:#cfe8b8;font-size:11px;}"
    "#hudRowName{color:#aef156;font-size:13px;font-weight:bold;}")


class HudPanel(QWidget):
    def __init__(self, pet, params=None):
        super().__init__()
        self.pet = pet    # PetWindow
        self.params = params if params is not None else {}
        self._drag = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._build()
        self._place()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        # 定时器由 toggle_visible 控制启停

        self.hide()

    def _pets(self):
        return getattr(self.pet, "pets", None) or [self.pet]

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)   # 尺寸随内容自适应
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
        self._scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;width:8px;margin:0;}"
            "QScrollBar::handle:vertical{background:rgba(150,180,120,150);"
            "border-radius:4px;min-height:24px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}")
        self._scroll.setMaximumHeight(self._max_view_h())
        pbox.addWidget(self._scroll)
        self._rows = []
        self._build_rows()
        self._fit_scroll()

    def _fit_scroll(self):
        """行区高度跟着行数走，直到撞上屏高上限才变滚动。"""
        self._vbox.activate()
        want = self._rows_host.sizeHint().height() + 4
        self._scroll.setFixedHeight(min(max(want, 40), self._max_view_h()))

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
                w.setParent(None)
                w.deleteLater()
        self._rows = []
        self._build_rows()
        self._fit_scroll()
        self._refresh()
        self._place()

    def _place(self):
        # 只做屏内定位（尺寸已自适应）
        self._panel.layout().activate()
        size = self.sizeHint()
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
            self._place()

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
