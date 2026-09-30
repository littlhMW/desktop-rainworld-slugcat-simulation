"""设置窗：猫增删/环境单选/HUD 开关，关窗即写盘。"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QCheckBox, QRadioButton, QButtonGroup, QFrame, QDialog,
                               QGridLayout, QSpinBox)
from PySide6.QtCore import Qt

from ..cats import REGISTRY, pickable_variants
from ..i18n import t
from .._paths import resource_dir
from ..window import MAX_PETS, spawnable_kinds
from .catmenu import variant_label, pet_label
from .dialogs import ConfirmDialog, PickDialog

# 幼崽不在「添加蛞蛓猫」里（它走「生物生成」那一栏）
_VARIANTS = pickable_variants()

_CHECK = (resource_dir() / "icons" / "check.svg").as_posix()   # 缺 QtSvg 时退化为高亮块

_QSS = (
    "QWidget{background:rgba(30,34,40,245);color:#e8f5d8;font-size:12px;}"
    "QLabel{color:#e8f5d8;}"
    "#secHeader{color:#aef156;font-size:13px;font-weight:bold;}"
    "#dim{color:#9fc080;}"
    "QPushButton{color:#e8f5d8;background:rgba(60,70,55,255);border:1px solid #4a5a3a;"
    "border-radius:5px;padding:4px 12px;}"
    "QPushButton:enabled:hover{background:rgba(80,100,70,255);}"
    "QPushButton:disabled{color:#777;background:rgba(45,48,52,255);}"
    "QCheckBox{color:#e8f5d8;}"
    "QRadioButton{color:#e8f5d8;spacing:8px;}"
    "QRadioButton::indicator{width:16px;height:16px;border-radius:8px;"
    "border:1px solid #52633f;background:#262b22;}"
    "QRadioButton::indicator:hover{border-color:#7c9a52;}"
    f"QRadioButton::indicator:checked{{border:2px solid #aef156;background:#aef156;"
    f"image:url({_CHECK});}}")


def _spawn_label(key: str) -> str:
    """生物列表标签：直接复用图标盘的 tooltip（缺翻译就退回类型名）。"""
    lbl = t("tip_" + key)
    return key if lbl == "tip_" + key else lbl


class SettingsWindow(QWidget):
    def __init__(self, window, hud, write_state):
        super().__init__()
        self._window = window
        self._hud = hud
        self._write_state = write_state
        window._settings_panel = self    # 供 window 反向同步世界态
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(t("settings_title"))
        self.setStyleSheet(_QSS)
        self.setMinimumWidth(280)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 14, 16, 14)
        self._outer.setSpacing(10)
        self._body = None
        self._dlg = None                 # 弹窗单例守卫
        self._rebuild()

    def open(self):
        if self._dlg is not None and not self._dlg.isVisible():
            self._dlg = None             # 残留句柄：不清理会永久卡住增删
        self._rebuild()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, ev):
        self._write_state()
        super().closeEvent(ev)

    # 内容重建
    def _rebuild(self):
        if self._body is not None:
            self._outer.removeWidget(self._body)
            self._body.setParent(None)
            self._body.deleteLater()
        self._body = QWidget()
        v = QVBoxLayout(self._body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self._section_cats(v)
        v.addWidget(self._divider())
        self._section_spawn(v)
        v.addWidget(self._divider())
        self._section_env(v)
        v.addWidget(self._divider())
        self._section_storm(v)
        v.addWidget(self._divider())
        self._section_hud(v)
        self._outer.addWidget(self._body)
        self.adjustSize()

    @staticmethod
    def _header(text):
        l = QLabel(text)
        l.setObjectName("secHeader")
        return l

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet("background:rgba(120,150,100,90);border:none;")
        return f

    def _section_cats(self, v):
        v.addWidget(self._header(t("settings_cats_section")))
        # 幼崽不是常规蛞蛓猫：不列在蛞蛓猫名单里（它们从生物生成里来）
        pets = [p for p in self._window.pets if not getattr(p, "is_pup", False)]
        can_remove = len(pets) > 1
        for pet in pets:
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(pet_label(pet, pets))
            row.addWidget(name)
            row.addStretch(1)
            rm = QPushButton(t("settings_remove"))
            rm.setEnabled(can_remove)
            if not can_remove:
                rm.setToolTip(t("settings_min_pets"))
            rm.clicked.connect(lambda _c, p=pet: self._on_remove(p))
            row.addWidget(rm)
            v.addLayout(row)
        add = QPushButton(t("settings_add"))
        full = self._window.cat_slots_used() >= MAX_PETS
        add.setEnabled(not full)
        if full:
            add.setToolTip(t("settings_max_pets"))
        add.clicked.connect(self._on_add)
        v.addWidget(add)

    def _section_spawn(self, v):
        """自然生成：勾哪几种，窗口里就自己长出哪几种（列表按代码自动生成）。"""
        v.addWidget(self._header(t("settings_spawn_section")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        on = self._window.spawn_kinds()
        for i, key in enumerate(spawnable_kinds()):
            chk = QCheckBox(_spawn_label(key))
            chk.setChecked(key in on)
            chk.toggled.connect(lambda checked, k=key: self._on_spawn_toggled(k, checked))
            grid.addWidget(chk, i // 2, i % 2)
        v.addLayout(grid)

    def _on_spawn_toggled(self, key, checked):
        self._window.set_spawn_kind(key, checked)

    def _section_env(self, v):
        v.addWidget(self._header(t("settings_env_section")))
        grp = QButtonGroup(self._body)
        self._env_group = grp
        self._env_radios = {}
        current = self._current_env()
        for key, label_key in (("none", "settings_env_none"), ("blizzard", "settings_snow"),
                               ("zerog", "settings_zerog"), ("water", "settings_water"),
                               ("storm", "settings_storm_env")):
            rb = QRadioButton(t(label_key))
            rb.setChecked(key == current)
            rb.toggled.connect(lambda checked, k=key: checked and self._on_env_selected(k))
            grp.addButton(rb)
            v.addWidget(rb)
            self._env_radios[key] = rb

    def _current_env(self):
        """从 window 环境态推导当前单选项。"""
        w = self._window
        st = getattr(w, "storm", None)
        if st is not None and getattr(st, "manual", False):
            return "storm"          # 只跟手动那一场：自动雨循环由开关负责
        if getattr(w, "blizzard_on", False):
            return "blizzard"
        if getattr(w, "zerog_on", False):
            return "zerog"
        if getattr(w, "water_on", False):
            return "water"
        return "none"

    def _on_env_selected(self, key):
        """选中 key 对应环境，互斥关其余（none=全关）。"""
        w = self._window
        if key != "blizzard" and getattr(w, "blizzard_on", False):
            w.blizzard_on = False
            w.blizzard_timer = 0
        if key != "zerog" and getattr(w, "zerog_on", False):
            w.set_zerog(False)
        if key != "water" and getattr(w, "water_on", False):
            w.set_water(False)
        if key != "storm":
            w.cancel_storm()        # 切走「暴雨」= 收掉手动那一场
        if key == "blizzard" and not w.blizzard_on:
            w.blizzard_on = True
            w.blizzard_timer = 0
        elif key == "zerog" and not w.zerog_on:
            w.set_zerog(True)
        elif key == "water" and not w.water_on:
            w.set_water(True)
        elif key == "storm":
            w.trigger_storm()

    def _section_storm(self, v):
        """雨循环：开关 + 三个时长（专注 / 预警 / 睡眠）。"""
        v.addWidget(self._header(t("settings_storm_section")))
        st = self._window.storm
        chk = QCheckBox(t("settings_storm_enable"))
        chk.setChecked(bool(st.enabled))
        chk.toggled.connect(self._on_storm_toggled)
        v.addWidget(chk)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        self._storm_spins = {}
        for row, (key, label_key, lo, hi, val) in enumerate((
                ("focus", "settings_storm_focus_minutes", 1, 600, st.focus_minutes),
                ("warning", "settings_storm_warning_minutes", 1, 120, st.warning_minutes),
                ("sleep", "settings_storm_sleep_minutes", 1, 240, st.sleep_minutes))):
            grid.addWidget(QLabel(t(label_key)), row, 0)
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setValue(int(round(val)))
            grid.addWidget(sp, row, 1)
            self._storm_spins[key] = sp
        v.addLayout(grid)
        btn = QPushButton(t("settings_storm_apply"))
        btn.clicked.connect(self._on_storm_apply)
        v.addWidget(btn)

    def _on_storm_toggled(self, checked):
        self._window.set_storm_enabled(checked)

    def _on_storm_apply(self):
        spins = getattr(self, "_storm_spins", None)
        if not spins:
            return
        self._window.set_storm_durations(
            focus_minutes=spins["focus"].value(),
            warning_minutes=spins["warning"].value(),
            sleep_minutes=spins["sleep"].value())

    def _section_hud(self, v):
        if self._hud is None:
            return                        # 没有 HUD 就别读它的可见性
        chk = QCheckBox(t("settings_show_hud"))
        chk.setChecked(self._hud.isVisible())
        chk.toggled.connect(self._on_hud_toggled)
        v.addWidget(chk)

    # 增删走卡片弹窗（open()=WindowModal，不 exec）
    def _on_add(self):
        if self._dlg is not None:
            return
        if self._window.cat_slots_used() >= MAX_PETS:
            self._rebuild()               # 名额满了：刷新出置灰的按钮
            return
        labels = []
        for variant in _VARIANTS:
            lbl = variant_label(variant)
            if REGISTRY[variant].wip:
                lbl += t("variant_wip_note")     # 占位种族挂提示
            labels.append(lbl)
        dlg = PickDialog(t("settings_pick_title"), t("settings_pick_cat"), labels,
                         t("settings_ok"), t("settings_cancel"), parent=self)
        dlg.finished.connect(lambda r, d=dlg: self._add_finished(d, r))
        self._dlg = dlg
        dlg.place_center(self)
        dlg.open()

    def _add_finished(self, dlg, result):
        self._dlg = None
        dlg.deleteLater()
        if result == QDialog.DialogCode.Accepted:
            idx = dlg.selected_index()
            ok = False
            if 0 <= idx < len(_VARIANTS):
                try:
                    ok = self._window.add_pet(_VARIANTS[idx]) is not None
                except Exception as exc:      # 单只猫建不起来也不能让按钮永远失灵
                    print("add_pet failed:", _VARIANTS[idx], exc)
            if not ok:
                print("add_pet rejected: slots=%d/%d"
                      % (self._window.cat_slots_used(), MAX_PETS))
            self._rebuild()               # 无论成败都同步按钮的可用状态

    def _on_remove(self, pet):
        if self._dlg is not None:
            return
        name = pet_label(pet, list(self._window.pets))
        dlg = ConfirmDialog(t("settings_remove"), t("settings_remove_confirm", name=name),
                            t("settings_remove"), t("settings_cancel"), parent=self)
        dlg.finished.connect(lambda r, p=pet, d=dlg: self._remove_finished(p, d, r))
        self._dlg = dlg
        dlg.place_center(self)
        dlg.open()

    def _remove_finished(self, pet, dlg, result):
        self._dlg = None
        dlg.deleteLater()
        if result == QDialog.DialogCode.Accepted and self._window.remove_pet(pet):
            self._rebuild()

    def _on_hud_toggled(self, checked):
        if self._hud is None:
            return
        if checked != self._hud.isVisible():
            self._hud.toggle_visible()

    def refresh_env(self):
        """同步单选钮到真实环境态（未开窗跳过）。"""
        if not self.isVisible():
            return
        radios = getattr(self, "_env_radios", None)
        if not radios:
            return
        rb = radios.get(self._current_env())
        if rb is not None and not rb.isChecked():
            rb.setChecked(True)   # 互斥自动清其余，幂等
