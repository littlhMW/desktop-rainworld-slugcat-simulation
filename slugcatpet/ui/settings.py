"""设置窗：猫增删/环境单选/HUD 开关，关窗即写盘。"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QCheckBox, QRadioButton, QButtonGroup, QFrame, QDialog,
                               QGridLayout, QSpinBox, QSlider)
from PySide6.QtCore import Qt, QTimer

from ..cats import REGISTRY, display_order, pickable_variants
from ..i18n import t
from .._paths import log_error, resource_dir
from ..window import MAX_PETS, spawnable_kinds, SPAWN_PERIOD_MIN_S, SPAWN_PERIOD_MAX_S
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
        self.setMinimumWidth(520)          # 两列：矮一点、宽一点
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 14, 16, 14)
        self._outer.setSpacing(10)
        self._body = None
        self._dlg = None                 # 弹窗单例守卫
        self._rebuild()

    def open(self):
        self._drop_stale_dlg()           # 残留句柄：不清理会永久卡住增删
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
        cols = QHBoxLayout(self._body)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(20)
        left = QVBoxLayout()
        right = QVBoxLayout()
        for col in (left, right):
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(8)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        # 左列：猫名单 + 自然生成；右列：环境 + 雨循环 + 友军伤害 + 状态面板
        self._section_cats(left)
        left.addWidget(self._divider())
        self._section_spawn(left)
        left.addStretch(1)
        self._section_env(right)
        right.addWidget(self._divider())
        self._section_storm(right)
        right.addWidget(self._divider())
        self._section_ai(right)
        right.addWidget(self._divider())
        self._section_meow(right)
        self._section_sfx(right)
        right.addWidget(self._divider())
        self._section_hud(right)
        right.addStretch(1)
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
        pets = display_order(p for p in self._window.pets
                             if not getattr(p, "is_pup", False))
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
        # 生成频率：**只有一个滑条**，上面勾了几种都共用这一个间隔（用户规格）。
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(t("settings_spawn_period"))
        lbl.setToolTip(t("settings_spawn_period_tip"))
        row.addWidget(lbl)
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(SPAWN_PERIOD_MIN_S, SPAWN_PERIOD_MAX_S)
        sld.setValue(self._window.spawn_period_s())
        sld.setSingleStep(1)
        sld.setPageStep(5)
        sld.setToolTip(t("settings_spawn_period_tip"))
        val = QLabel(t("settings_spawn_period_val", n=self._window.spawn_period_s()))
        val.setObjectName("dim")
        val.setMinimumWidth(52)
        sld.valueChanged.connect(lambda n, lb=val: self._on_spawn_period(n, lb))
        row.addWidget(sld, 1)
        row.addWidget(val)
        v.addLayout(row)
        self._spawn_slider = sld          # 供测试 / 反向同步读它

    def _on_spawn_period(self, seconds, label=None):
        """滑条动了：改全类型共用的生成间隔，并刷新旁边的秒数标签。"""
        self._window.set_spawn_period_s(seconds)
        if label is not None:
            label.setText(t("settings_spawn_period_val",
                            n=self._window.spawn_period_s()))

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
        """雨循环：开关 + 三个时长（平静期 / 征兆期 / 暴雨期）。"""
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
        cap = QCheckBox(t("settings_storm_block"))
        cap.setChecked(bool(getattr(self._window, "storm_block_clicks", False)))
        cap.setToolTip(t("settings_storm_block_tip"))
        cap.toggled.connect(self._on_storm_block_toggled)
        v.addWidget(cap)
        lethal = QCheckBox(t("settings_storm_lethal"))
        lethal.setChecked(bool(getattr(self._window, "storm_lethal_clicks", False)))
        lethal.setToolTip(t("settings_storm_lethal_tip"))
        lethal.toggled.connect(self._on_storm_lethal_toggled)
        v.addWidget(lethal)
        btn = QPushButton(t("settings_storm_apply"))
        btn.clicked.connect(self._on_storm_apply)
        v.addWidget(btn)

    def _on_storm_toggled(self, checked):
        self._window.set_storm_enabled(checked)

    def _on_storm_block_toggled(self, checked):
        """暴雨是否拦住真实点击：关着的时候暴雨照样穿透，不挡用户干活。"""
        self._window.set_storm_block_clicks(checked)

    def _on_storm_lethal_toggled(self, checked):
        """暴雨中点击是否杀猫（与「拦住点击」分开的第二个开关）。"""
        self._window.set_storm_lethal_clicks(checked)

    def _on_storm_apply(self):
        spins = getattr(self, "_storm_spins", None)
        if not spins:
            return
        self._window.set_storm_durations(
            focus_minutes=spins["focus"].value(),
            warning_minutes=spins["warning"].value(),
            sleep_minutes=spins["sleep"].value())

    def _section_ai(self, v):
        """友军伤害：只决定矛/石头要不要伤到同伴，一点不碰 AI。"""
        v.addWidget(self._header(t("settings_ai_section")))
        chk = QCheckBox(t("settings_friendly_fire_protect"))
        chk.setChecked(bool(getattr(self._window, "friendly_fire_protect", False)))
        chk.setToolTip(t("settings_friendly_fire_protect_tip"))
        chk.toggled.connect(self._on_friendly_fire_toggled)
        v.addWidget(chk)

    def _on_friendly_fire_toggled(self, checked):
        """勾选＝同伴免疫矛/石头的伤害与眩晕（纯伤害结算，AI 照旧避让）。"""
        self._window.set_friendly_fire_protect(checked)

    def _section_meow(self, v):
        """Optional Push To Meow playback and AI-driven probability controls."""
        v.addWidget(self._header(t("settings_meow_section")))
        self._waa_status_label = None
        audio = getattr(self._window, "meows", None)
        chk = QCheckBox(t("settings_meow_enable"))
        chk.setChecked(bool(getattr(audio, "enabled", False)))
        chk.setToolTip(t("settings_meow_tip"))
        chk.toggled.connect(self._on_meow_toggled)
        pets = list(getattr(self._window, "pets", ()))
        only_survivor = (len(pets) == 1
                         and getattr(pets[0], "variant", "") == "survivor")
        enable_row = QHBoxLayout()
        enable_row.addWidget(chk)
        if only_survivor:
            waa = QCheckBox(t("settings_waa_enable"))
            waa.setChecked(bool(getattr(audio, "waa_enabled", False)))
            waa.setToolTip(t("settings_waa_tip"))
            waa.setEnabled(bool(getattr(audio, "waa_supported", False)))
            waa.toggled.connect(self._on_waa_toggled)
            enable_row.addWidget(waa)
        v.addLayout(enable_row)
        status = QLabel(t("settings_meow_ready") if getattr(audio, "available", False)
                        else t("settings_meow_missing"))
        status.setObjectName("dim")
        status.setWordWrap(True)
        v.addWidget(status)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(t("settings_meow_volume")))
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(0, 100)
        value = int(getattr(audio, "volume", 70))
        sld.setValue(value)
        label = QLabel(t("settings_meow_volume_val", n=value))
        label.setObjectName("dim")
        label.setMinimumWidth(42)
        sld.valueChanged.connect(lambda n, lb=label: self._on_meow_volume(n, lb))
        row.addWidget(sld, 1)
        row.addWidget(label)
        v.addLayout(row)
        self._meow_slider = sld
        if only_survivor:
            self._waa_status_label = QLabel(t("settings_waa_" + audio.waa_status))
            self._waa_status_label.setObjectName("dim")
            self._waa_status_label.setWordWrap(True)
            self._waa_status_label.setToolTip(audio.waa_detail)
            v.addWidget(self._waa_status_label)
            if audio.waa_status == "preparing":
                QTimer.singleShot(500, self._refresh_waa_status)

    def _refresh_waa_status(self):
        audio = getattr(self._window, "meows", None)
        label = getattr(self, "_waa_status_label", None)
        if audio is None or label is None or not self.isVisible():
            return
        label.setText(t("settings_waa_" + audio.waa_status))
        label.setToolTip(audio.waa_detail)
        if audio.waa_status == "preparing":
            QTimer.singleShot(500, self._refresh_waa_status)

    def _on_waa_toggled(self, checked):
        audio = getattr(self._window, "meows", None)
        if audio is not None:
            audio.set_waa_enabled(checked)
            self._refresh_waa_status()
            self._write_state()

    def _on_meow_toggled(self, checked):
        self._window.set_meows_enabled(checked)

    def _on_meow_volume(self, value, label=None):
        self._window.set_meows_volume(value)
        if label is not None:
            label.setText(t("settings_meow_volume_val", n=int(value)))

    def _section_sfx(self, v):
        v.addWidget(self._header(t("settings_sfx_section")))
        audio = getattr(self._window, "sfx", None)
        chk = QCheckBox(t("settings_sfx_enable"))
        chk.setChecked(bool(getattr(audio, "enabled", True)))
        chk.setToolTip(t("settings_sfx_tip"))
        chk.toggled.connect(self._window.set_sfx_enabled)
        v.addWidget(chk)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(t("settings_sfx_volume")))
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(0, 100)
        value = int(getattr(audio, "volume", 55))
        sld.setValue(value)
        label = QLabel(t("settings_sfx_volume_val", n=value))
        label.setObjectName("dim")
        label.setMinimumWidth(42)
        sld.valueChanged.connect(lambda n, lb=label: self._on_sfx_volume(n, lb))
        row.addWidget(sld, 1)
        row.addWidget(label)
        v.addLayout(row)

    def _on_sfx_volume(self, value, label=None):
        self._window.set_sfx_volume(value)
        if label is not None:
            label.setText(t("settings_sfx_volume_val", n=int(value)))

    def _section_hud(self, v):
        if self._hud is None:
            return                        # 没有 HUD 就别读它的可见性
        v.addWidget(self._header(t("settings_hud_section")))
        chk = QCheckBox(t("settings_show_hud"))
        chk.setChecked(self._hud.isVisible())
        chk.toggled.connect(self._on_hud_toggled)
        v.addWidget(chk)

    # 增删走卡片弹窗（open()=WindowModal，不 exec）
    def _drop_stale_dlg(self):
        """弹窗句柄只有「还在屏幕上」才算占用。

        窗口被隐藏/被系统收起时 QDialog 不一定发 finished，残留句柄会让
        「添加 / 移除」永远点不动（第 87、91 轮各踩过一次，这里彻底收口）。
        """
        d = self._dlg
        if d is None:
            return None
        if d.isVisible():
            return d
        self._dlg = None
        return None

    def _warn(self, title, text):
        """把失败摆到用户眼前 + 落 error.log（发布版没有控制台）。"""
        try:
            from .dialogs import NoticeDialog
            dlg = NoticeDialog(title, text, t("settings_ok"), parent=self)
            dlg.finished.connect(lambda _r, d=dlg: self._notice_done(d))
            dlg.place_center(self)
            dlg.show()
            self._notice = dlg
        except Exception as exc:
            log_error("settings notice failed: %r" % (exc,))

    def _notice_done(self, dlg):
        if getattr(self, "_notice", None) is dlg:
            self._notice = None
        dlg.deleteLater()

    def _on_add(self):
        if self._drop_stale_dlg() is not None:
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
        if result != QDialog.DialogCode.Accepted:
            return
        idx = dlg.selected_index()
        variant = _VARIANTS[idx] if 0 <= idx < len(_VARIANTS) else None
        why = None
        if variant is None:
            why = "index %r" % (idx,)
        elif self._window.cat_slots_used() >= MAX_PETS:
            why = t("settings_max_pets")
        else:
            try:
                if self._window.add_pet(variant) is None:
                    why = t("settings_add_none")
            except Exception as exc:      # 单只猫建不起来也不能让按钮永远失灵
                why = repr(exc)
        self._rebuild()                   # 无论成败都同步按钮的可用状态
        if why is not None:               # 失败要说出来，不能只 print 到看不见的 stderr
            log_error("add_pet(%s) failed: %s" % (variant, why))
            self._warn(t("settings_add"),
                       t("settings_add_failed", variant=variant_label(variant or ""),
                         why=why))

    def _on_remove(self, pet):
        if self._drop_stale_dlg() is not None:
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
