"""设置窗口：玻璃面板网格中的悬浮窗自定义与游戏检测设置。

无边框夜景外壳 + 响应式 BentoGrid：外观与游戏检测各占一张高卡，
自定义进程占一张跨行宽卡。改动即时通过信号交给 Controller，并持久化。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
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
    """设置分组：一张玻璃面板，标题在卡内顶部。"""

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
    # 背景自定义
    backdropChanged = Signal()
    # 高心率截屏（阈值、持续、间隔、目录由用户决定）
    captureSettingsChanged = Signal()

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
        self._heart_switch.toggled.connect(self._on_heart_switch)
        float_sec.add_divider()
        sw, self._zone_switch = self._switch("显示心率区间", "显示当前状态与心率区间", True)
        float_sec.lay.addWidget(sw)
        self._zone_switch.toggled.connect(self._on_zone_switch)
        float_sec.add_divider()
        sw, self._device_switch = self._switch("显示设备名", "在悬浮窗底部显示设备", True)
        float_sec.lay.addWidget(sw)
        self._device_switch.toggled.connect(self._on_device_switch)

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

        # ---------------- 背景自定义（宽卡） ----------------
        bg_sec = _Section("背景自定义")
        tip = QLabel(
            "夜景 / 纯色 / 本地图片；系统会自动压暗浅色背景，保证半透明界面清晰可读"
        )
        tip.setObjectName("Sub")
        tip.setWordWrap(True)
        bg_sec.lay.addWidget(tip)

        bg_row = QWidget()
        bg_row.setFixedHeight(56)
        bh = QHBoxLayout(bg_row)
        bh.setContentsMargins(0, 4, 0, 4)
        bh.setSpacing(10)
        bcol = QVBoxLayout()
        bcol.setContentsMargins(0, 0, 0, 0)
        bcol.setSpacing(0)
        bname = QLabel("背景模式")
        bname.setObjectName("H2")
        bsub = QLabel("默认夜景，或换成自己的颜色 / 图片")
        bsub.setObjectName("Sub")
        bcol.addWidget(bname)
        bcol.addWidget(bsub)
        bh.addLayout(bcol, 1)
        self._bg_combo = QComboBox()
        self._bg_combo.addItem("夜景默认", "night")
        self._bg_combo.addItem("纯色背景", "solid")
        self._bg_combo.addItem("本地图片", "image")
        self._bg_combo.setFixedWidth(160)
        self._bg_combo.currentIndexChanged.connect(self._on_backdrop_control)
        bh.addWidget(self._bg_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        bg_sec.lay.addWidget(bg_row)
        bg_sec.add_divider()

        color_row = QWidget()
        color_row.setFixedHeight(56)
        ch = QHBoxLayout(color_row)
        ch.setContentsMargins(0, 4, 0, 4)
        ch.setSpacing(10)
        ccol = QVBoxLayout()
        ccol.setContentsMargins(0, 0, 0, 0)
        ccol.setSpacing(0)
        cname = QLabel("纯色背景")
        cname.setObjectName("H2")
        csub = QLabel("点击色块打开取色器")
        csub.setObjectName("Sub")
        ccol.addWidget(cname)
        ccol.addWidget(csub)
        ch.addLayout(ccol, 1)
        self._bg_color_swatch = QLabel()
        self._bg_color_swatch.setFixedSize(52, 26)
        self._bg_color_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bg_color_swatch.mousePressEvent = lambda _e: self._choose_bg_color()
        color_btn = RaisedButton("选择颜色")
        color_btn.setFixedWidth(104)
        color_btn.clicked.connect(self._choose_bg_color)
        ch.addWidget(self._bg_color_swatch, 0, Qt.AlignmentFlag.AlignVCenter)
        ch.addWidget(color_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        bg_sec.lay.addWidget(color_row)
        bg_sec.add_divider()

        image_row = QWidget()
        image_row.setFixedHeight(56)
        ih = QHBoxLayout(image_row)
        ih.setContentsMargins(0, 4, 0, 4)
        ih.setSpacing(10)
        icol = QVBoxLayout()
        icol.setContentsMargins(0, 0, 0, 0)
        icol.setSpacing(0)
        iname = QLabel("图片背景")
        iname.setObjectName("H2")
        self._bg_image_label = QLabel("未选择图片")
        self._bg_image_label.setObjectName("Sub")
        icol.addWidget(iname)
        icol.addWidget(self._bg_image_label)
        ih.addLayout(icol, 1)
        image_btn = RaisedButton("选择图片…")
        image_btn.setFixedWidth(104)
        image_btn.clicked.connect(self._choose_bg_image)
        clear_btn = RaisedButton("清除")
        clear_btn.setFixedWidth(72)
        clear_btn.clicked.connect(self._clear_bg_image)
        ih.addWidget(image_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        ih.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        bg_sec.lay.addWidget(image_row)

        self._bg_dim_slider = self._add_slider_row(
            bg_sec, "背景压暗", "0 最亮 · 100 最暗，自动对比度会叠加", 0, 100, 45
        )
        self._bg_dim_slider.valueChanged.connect(self._on_backdrop_control)

        # ---------------- 高心率截屏（宽卡） ----------------
        cap_sec = _Section("高心率截屏")
        tip = QLabel(
            "达到你设定的心率后自动截取当前屏幕，图片带时间戳保存在历史中可查看"
        )
        tip.setObjectName("Sub")
        tip.setWordWrap(True)
        cap_sec.lay.addWidget(tip)

        sw, self._capture_switch = self._switch(
            "启用自动截屏", "达到触发心率时自动保存当前画面", False
        )
        cap_sec.lay.addWidget(sw)
        self._capture_switch.toggled.connect(self._on_capture_control)
        cap_sec.add_divider()

        self._capture_threshold_slider = self._add_slider_row(
            cap_sec, "触发心率", "BPM，达到该值才开始截屏", 80, 200, 120
        )
        self._capture_threshold_slider.valueChanged.connect(self._on_capture_control)
        self._capture_sustain_slider = self._add_slider_row(
            cap_sec, "持续时间", "秒，0 表示达到即截屏", 0, 10, 0
        )
        self._capture_sustain_slider.valueChanged.connect(self._on_capture_control)
        self._capture_cooldown_slider = self._add_slider_row(
            cap_sec, "截屏间隔", "秒，两次截屏之间的最短时间", 5, 180, 30
        )
        self._capture_cooldown_slider.valueChanged.connect(self._on_capture_control)

        folder_row = QWidget()
        folder_row.setFixedHeight(56)
        fh = QHBoxLayout(folder_row)
        fh.setContentsMargins(0, 4, 0, 4)
        fh.setSpacing(10)
        fcol = QVBoxLayout()
        fcol.setContentsMargins(0, 0, 0, 0)
        fcol.setSpacing(0)
        fname = QLabel("保存位置")
        fname.setObjectName("H2")
        self._capture_dir_label = QLabel("默认：配置目录 / captures")
        self._capture_dir_label.setObjectName("Sub")
        fcol.addWidget(fname)
        fcol.addWidget(self._capture_dir_label)
        fh.addLayout(fcol, 1)
        choose_dir = RaisedButton("选择目录…")
        choose_dir.setFixedWidth(104)
        choose_dir.clicked.connect(self._choose_capture_dir)
        reset_dir = RaisedButton("默认")
        reset_dir.setFixedWidth(72)
        reset_dir.clicked.connect(self._reset_capture_dir)
        fh.addWidget(choose_dir, 0, Qt.AlignmentFlag.AlignVCenter)
        fh.addWidget(reset_dir, 0, Qt.AlignmentFlag.AlignVCenter)
        cap_sec.lay.addWidget(folder_row)

        self._grid.set_placements(
            {
                4: [
                    (float_sec, 0, 0, 2, 2),
                    (game_sec, 0, 2, 2, 2),
                    (custom_sec, 2, 0, 1, 4),
                    (bg_sec, 3, 0, 1, 4),
                    (cap_sec, 4, 0, 1, 4),
                ],
                2: [
                    (float_sec, 0, 0, 2, 1),
                    (game_sec, 0, 1, 2, 1),
                    (custom_sec, 2, 0, 1, 2),
                    (bg_sec, 3, 0, 1, 2),
                    (cap_sec, 4, 0, 1, 2),
                ],
                1: [
                    (float_sec, 0, 0, 2, 1),
                    (game_sec, 2, 0, 2, 1),
                    (custom_sec, 4, 0, 2, 1),
                    (bg_sec, 6, 0, 2, 1),
                    (cap_sec, 8, 0, 2, 1),
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
        self._bg_color = str(getattr(s, "background_color", "#0b1322") or "#0b1322")
        self._bg_image = str(getattr(s, "background_image", "") or "")
        mode_index = self._bg_combo.findData(getattr(s, "background_mode", "night"))
        self._bg_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self._bg_dim_slider.setValue(int(getattr(s, "background_dim", 45)))
        self._refresh_backdrop_preview()

        # 截屏控件在载入时暂不触发信号，避免把默认值写回设置
        for widget in (
            self._capture_switch,
            self._capture_threshold_slider,
            self._capture_sustain_slider,
            self._capture_cooldown_slider,
        ):
            widget.blockSignals(True)
        self._capture_switch.setChecked(bool(getattr(s, "capture_enabled", False)))
        self._capture_threshold_slider.setValue(int(getattr(s, "capture_threshold", 120)))
        self._capture_sustain_slider.setValue(int(getattr(s, "capture_sustain", 0)))
        self._capture_cooldown_slider.setValue(int(getattr(s, "capture_cooldown", 30)))
        for widget in (
            self._capture_switch,
            self._capture_threshold_slider,
            self._capture_sustain_slider,
            self._capture_cooldown_slider,
        ):
            widget.blockSignals(False)
        self._refresh_capture_dir()

    # ---------------------------------------------------------- 背景自定义
    def _refresh_backdrop_preview(self) -> None:
        color = getattr(self, "_bg_color", "#0b1322")
        self._bg_color_swatch.setStyleSheet(
            f"background: {color}; border: 1px solid rgba(255,255,255,0.35);"
            "border-radius: 13px;"
        )
        path = getattr(self, "_bg_image", "")
        self._bg_image_label.setText(path or "未选择图片")
        self._bg_image_label.setToolTip(path)

    def _sync_backdrop(self) -> bool:
        s = self.settings
        new = (
            self._bg_combo.currentData() or "night",
            getattr(self, "_bg_color", "#0b1322"),
            getattr(self, "_bg_image", ""),
            int(self._bg_dim_slider.value()),
        )
        old = (
            getattr(s, "background_mode", "night"),
            getattr(s, "background_color", "#0b1322"),
            getattr(s, "background_image", ""),
            getattr(s, "background_dim", 45),
        )
        s.background_mode, s.background_color, s.background_image, s.background_dim = new
        self._refresh_backdrop_preview()
        return new != old

    def _emit_backdrop_if_changed(self) -> None:
        if self._sync_backdrop():
            self.backdropChanged.emit()

    def _on_backdrop_control(self, *_args) -> None:
        self._emit_backdrop_if_changed()

    def _choose_bg_color(self) -> None:
        initial = QColor(getattr(self, "_bg_color", "#0b1322"))
        color = QColorDialog.getColor(initial, self, "选择背景颜色")
        if color.isValid():
            self._bg_color = color.name()
            self._emit_backdrop_if_changed()

    def _choose_bg_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        self._bg_image = path
        # 选了图片必须同时切到图片模式，否则仍按夜景绘制，看起来“没效果”。
        index = self._bg_combo.findData("image")
        if index >= 0:
            self._bg_combo.blockSignals(True)
            self._bg_combo.setCurrentIndex(index)
            self._bg_combo.blockSignals(False)
        self._emit_backdrop_if_changed()

    def _clear_bg_image(self) -> None:
        self._bg_image = ""
        self._emit_backdrop_if_changed()

    # ---------------------------------------------------------- 高心率截屏
    def _refresh_capture_dir(self) -> None:
        path = str(getattr(self.settings, "capture_dir", "") or "")
        self._capture_dir_label.setText(path or "默认：配置目录 / captures")
        self._capture_dir_label.setToolTip(path)

    def _sync_capture(self) -> None:
        s = self.settings
        s.capture_enabled = bool(self._capture_switch.isChecked())
        s.capture_threshold = int(self._capture_threshold_slider.value())
        s.capture_sustain = int(self._capture_sustain_slider.value())
        s.capture_cooldown = int(self._capture_cooldown_slider.value())
        self._refresh_capture_dir()

    def _on_capture_control(self, *_args) -> None:
        self._sync_capture()
        self.captureSettingsChanged.emit()

    def _choose_capture_dir(self) -> None:
        initial = str(getattr(self.settings, "capture_dir", "") or "")
        path = QFileDialog.getExistingDirectory(self, "选择截屏保存目录", initial)
        if not path:
            return
        self.settings.capture_dir = path
        self._refresh_capture_dir()
        self.captureSettingsChanged.emit()

    def _reset_capture_dir(self) -> None:
        self.settings.capture_dir = ""
        self._refresh_capture_dir()
        self.captureSettingsChanged.emit()

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

    def _on_heart_switch(self, checked: bool) -> None:
        self.settings.float_show_heart = bool(checked)
        self.floatShowHeartChanged.emit(bool(checked))

    def _on_zone_switch(self, checked: bool) -> None:
        self.settings.float_show_zone = bool(checked)
        self.floatShowZoneChanged.emit(bool(checked))

    def _on_device_switch(self, checked: bool) -> None:
        self.settings.float_show_device = bool(checked)
        self.floatShowDeviceChanged.emit(bool(checked))

    def collect(self) -> None:
        """把当前界面值写回 settings 并发出即时生效信号。"""
        s = self.settings
        self._emit_backdrop_if_changed()
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
        self._sync_capture()

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
        self.captureSettingsChanged.emit()

    def accept_if_needed(self) -> None:
        self.collect()
        self.hide()

    def center_on(self, widget: QWidget | None) -> None:
        reference = widget.frameGeometry() if widget is not None else self.frameGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(reference.center())
        self.move(geo.topLeft())
