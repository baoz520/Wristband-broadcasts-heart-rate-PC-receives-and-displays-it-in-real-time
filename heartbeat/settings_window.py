"""设置窗口：便当盒网格中的悬浮窗自定义与游戏检测设置。

无边框 Snow 外壳 + 响应式 BentoGrid：外观与游戏检测各占一张高卡，
自定义进程占一张跨行宽卡。改动即时通过信号交给 Controller，并持久化。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .chrome import BentoRootPanel, TitleBar
from .widgets import BentoCard, BentoGrid, RaisedButton, ToggleSwitch


class _Section(QWidget):
    """设置分组：一张 BentoCard，标题在卡内顶部。"""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        card = BentoCard(self, object_name="BentoCard")
        outer.addWidget(card)
        self.card = card

        self.lay = QVBoxLayout(card)
        self.lay.setContentsMargins(24, 20, 24, 20)
        self.lay.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        self.lay.addWidget(label)
        self.lay.addSpacing(4)

    def add_divider(self) -> None:
        line = QFrame()
        line.setObjectName("Divider")
        self.lay.addWidget(line)


class SettingsWindow(QDialog):
    """设置对话框。"""

    # 悬浮窗设置信号
    floatWidthChanged = Signal(int)
    floatOpacityChanged = Signal(int)
    floatShowHeartChanged = Signal(bool)
    floatShowZoneChanged = Signal(bool)
    floatShowDeviceChanged = Signal(bool)
    # 游戏设置信号
    gameDetectChanged = Signal(bool)
    gameCustomChanged = Signal(list)
    gameRecordChanged = Signal(bool)
    gameShowFloatChanged = Signal(bool)
    gameFloatModeChanged = Signal(str)
    gamePollChanged = Signal(int)

    def __init__(self, settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("设置")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(760, 780)
        self.setMinimumSize(520, 520)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(BentoRootPanel(self))
        root = self.layout().itemAt(0).widget()

        bar = TitleBar("设置", "悬浮窗与游戏检测")
        bar._min_button.hide()
        bar._max_button.hide()
        bar.closeClicked.connect(self.hide)
        self._titlebar = bar
        root.addWidget(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        root.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        body = QVBoxLayout(container)
        body.setContentsMargins(16, 8, 16, 10)
        body.setSpacing(16)
        self._grid = BentoGrid(container, gap=16, wide=1100, medium=560)
        body.addWidget(self._grid)

        # ---------------- 悬浮窗 ----------------
        float_sec = _Section("悬浮窗自定义")
        self._width_slider = self._add_slider_row(float_sec, "悬浮窗宽度", "调整悬浮窗大小", 220, 420, 268)
        self._opacity_slider = self._add_slider_row(float_sec, "不透明度", "40% – 100%", 40, 100, 100)

        sw, self._heart_switch = self._switch("显示心跳图标", "在悬浮窗显示心跳动画", True)
        float_sec.lay.addWidget(sw)
        float_sec.add_divider()
        sw, self._zone_switch = self._switch("显示心率区间", "显示静息 / 燃脂等区间", True)
        float_sec.lay.addWidget(sw)
        float_sec.add_divider()
        sw, self._device_switch = self._switch("显示设备名", "在悬浮窗底部显示设备", True)
        float_sec.lay.addWidget(sw)

        # ---------------- 游戏检测 ----------------
        game_sec = _Section("游戏心率检测")
        sw, self._game_switch = self._switch("启用游戏检测", "检测当前运行的游戏并记录心率", False)
        game_sec.lay.addWidget(sw)
        game_sec.add_divider()
        sw, self._game_record_switch = self._switch("记录为历史会话", "每场游戏单独存入历史记录", True)
        game_sec.lay.addWidget(sw)
        game_sec.add_divider()
        sw, self._game_float_switch = self._switch("悬浮窗显示游戏", "显示当前游戏与游戏内心率", True)
        game_sec.lay.addWidget(sw)
        game_sec.add_divider()

        mode_row = QWidget()
        mode_row.setFixedHeight(56)
        mh = QHBoxLayout(mode_row)
        mh.setContentsMargins(0, 4, 0, 4)
        mh.setSpacing(10)
        mcol = QVBoxLayout()
        mcol.setContentsMargins(0, 0, 0, 0)
        mcol.setSpacing(0)
        mname = QLabel("游戏中悬浮窗")
        mname.setObjectName("H2")
        msub = QLabel("自动控制悬浮窗底板与可见性")
        msub.setObjectName("Sub")
        mcol.addWidget(mname)
        mcol.addWidget(msub)
        mh.addLayout(mcol, 1)
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("隐藏背景，仅留数据", "transparent")
        self._mode_combo.addItem("自动隐藏整个悬浮窗", "hidden")
        self._mode_combo.addItem("保持原样", "normal")
        self._mode_combo.setFixedWidth(160)
        mh.addWidget(self._mode_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        game_sec.lay.addWidget(mode_row)
        game_sec.add_divider()

        self._poll_slider = self._add_slider_row(game_sec, "检测间隔", "秒，越小越灵敏", 2, 10, 4)

        # ---------------- 自定义进程（宽卡） ----------------
        custom_sec = _Section("补充游戏进程")
        tip = QLabel("每行一个进程，支持 进程名=显示名；Steam、壁纸等平台不算游戏")
        tip.setObjectName("Sub")
        tip.setWordWrap(True)
        custom_sec.lay.addWidget(tip)
        self._custom_edit = QLineEdit()
        self._custom_edit.setObjectName("RecessedInput")
        self._custom_edit.setPlaceholderText("例如：mygame.exe=我的游戏")
        custom_sec.lay.addWidget(self._custom_edit)

        pick_row = QHBoxLayout()
        pick_row.setContentsMargins(0, 4, 0, 0)
        pick_row.setSpacing(10)
        self._custom_status = QLabel("")
        self._custom_status.setObjectName("Sub")
        pick_row.addWidget(self._custom_status, 1)
        pick = RaisedButton("从运行进程中添加…")
        pick.setProperty("action", True)
        pick.setFixedWidth(178)
        pick.clicked.connect(self._pick_process)
        pick_row.addWidget(pick, 0, Qt.AlignmentFlag.AlignRight)
        custom_sec.lay.addLayout(pick_row)

        self._grid.set_placements(
            {
                4: [
                    (float_sec, 0, 0, 2, 2),
                    (game_sec, 0, 2, 2, 2),
                    (custom_sec, 2, 0, 1, 4),
                ],
                2: [
                    (float_sec, 0, 0, 2, 1),
                    (game_sec, 0, 1, 2, 1),
                    (custom_sec, 2, 0, 1, 2),
                ],
                1: [
                    (float_sec, 0, 0, 2, 1),
                    (game_sec, 2, 0, 2, 1),
                    (custom_sec, 4, 0, 2, 1),
                ],
            }
        )

        footer = QWidget()
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(0, 0, 0, 0)
        foot.addStretch(1)
        close = RaisedButton("完成")
        close.setProperty("action", True)
        close.setFixedWidth(120)
        close.clicked.connect(self.accept_if_needed)
        foot.addWidget(close)
        foot.addStretch(1)
        root.addWidget(footer)

    def _add_slider_row(self, section: _Section, title: str, desc: str,
                        lo: int, hi: int, default: int) -> QSlider:
        widget = QWidget()
        widget.setFixedHeight(60)
        v = QVBoxLayout(widget)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(2)
        head = QHBoxLayout()
        name = QLabel(title)
        name.setObjectName("H2")
        head.addWidget(name, 1)
        value = QLabel(str(default))
        value.setObjectName("Badge")
        head.addWidget(value, 0)
        v.addLayout(head)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(default)
        slider.setFixedHeight(18)
        slider.valueChanged.connect(lambda val, lbl=value: lbl.setText(str(val)))
        v.addWidget(slider)
        section.lay.addWidget(widget)
        return slider

    def _switch(self, title: str, desc: str, checked: bool):
        row = QWidget()
        row.setFixedHeight(52)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 4, 0, 4)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        name = QLabel(title)
        name.setObjectName("H2")
        sub = QLabel(desc)
        sub.setObjectName("Sub")
        col.addWidget(name)
        col.addWidget(sub)
        h.addLayout(col, 1)
        sw = ToggleSwitch()
        sw.setChecked(checked)
        h.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
        return row, sw

    def _load_values(self) -> None:
        s = self.settings
        self._width_slider.setValue(int(s.float_width))
        self._opacity_slider.setValue(int(s.float_opacity))
        self._heart_switch.setChecked(bool(s.float_show_heart))
        self._zone_switch.setChecked(bool(s.float_show_zone))
        self._device_switch.setChecked(bool(s.float_show_device))
        self._game_switch.setChecked(bool(s.game_detect_enabled))
        self._game_record_switch.setChecked(bool(s.game_record_sessions))
        self._game_float_switch.setChecked(bool(s.game_show_on_float))
        mode_index = self._mode_combo.findData(getattr(s, "game_float_mode", "transparent"))
        self._mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self._poll_slider.setValue(int(s.game_poll_seconds))
        self._custom_edit.setText("\n".join(s.game_custom or []))

    # ---------------------------------------------------------- 进程快捷添加
    def _pick_process(self) -> None:
        """打开进程选择器，用户勾选后直接写入自定义清单并立即生效。"""
        from .process_picker import ProcessPickerDialog

        current = [ln.strip() for ln in self._custom_edit.text().splitlines() if ln.strip()]
        dialog = ProcessPickerDialog(self, current)
        dialog.processSelected.connect(self._add_custom_process)
        dialog.center_on(self)
        dialog.exec()

    def _add_custom_process(self, name: str, display: str = "") -> None:
        """把选中的进程加入自定义清单（去重），并立即应用到检测器。"""
        name = (name or "").strip()
        if not name:
            return
        lines = [ln.strip() for ln in self._custom_edit.text().splitlines() if ln.strip()]
        key = name.lower().removesuffix(".exe")
        entry = f"{name}={display.strip()}" if display.strip() else name
        replaced = False
        for i, line in enumerate(lines):
            proc = line.split("=", 1)[0].strip().lower().removesuffix(".exe")
            if proc == key:
                lines[i] = entry
                replaced = True
                break
        if not replaced:
            lines.append(entry)
        self._custom_edit.setText("\n".join(lines))
        self._custom_status.setText(f"已添加：{display.strip() or name}")
        # collect() 会发出 gameCustomChanged，Controller 立即更新识别清单并保存
        self.collect()

    def collect(self) -> None:
        """把当前界面值写回 settings 并发出即时生效信号。"""
        s = self.settings
        s.float_width = int(self._width_slider.value())
        s.float_opacity = int(self._opacity_slider.value())
        s.float_show_heart = bool(self._heart_switch.isChecked())
        s.float_show_zone = bool(self._zone_switch.isChecked())
        s.float_show_device = bool(self._device_switch.isChecked())
        s.game_detect_enabled = bool(self._game_switch.isChecked())
        s.game_record_sessions = bool(self._game_record_switch.isChecked())
        s.game_show_on_float = bool(self._game_float_switch.isChecked())
        s.game_float_mode = self._mode_combo.currentData() or "transparent"
        s.game_poll_seconds = int(self._poll_slider.value())
        custom = [ln.strip() for ln in self._custom_edit.text().splitlines() if ln.strip()]
        s.game_custom = custom

        self.floatWidthChanged.emit(s.float_width)
        self.floatOpacityChanged.emit(s.float_opacity)
        self.floatShowHeartChanged.emit(s.float_show_heart)
        self.floatShowZoneChanged.emit(s.float_show_zone)
        self.floatShowDeviceChanged.emit(s.float_show_device)
        self.gameDetectChanged.emit(s.game_detect_enabled)
        self.gameCustomChanged.emit(list(custom))
        self.gameRecordChanged.emit(s.game_record_sessions)
        self.gameShowFloatChanged.emit(s.game_show_on_float)
        self.gameFloatModeChanged.emit(s.game_float_mode)
        self.gamePollChanged.emit(s.game_poll_seconds)

    def accept_if_needed(self) -> None:
        self.collect()
        self.hide()

    def center_on(self, widget: QWidget | None) -> None:
        reference = widget.frameGeometry() if widget is not None else self.frameGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(reference.center())
        self.move(geo.topLeft())
