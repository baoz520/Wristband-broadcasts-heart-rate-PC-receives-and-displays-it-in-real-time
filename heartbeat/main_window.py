"""主界面：实时心率、悬浮窗开关、设备管理开关与设备列表。"""

from __future__ import annotations

import time
from collections import deque
from typing import Optional

from PySide6.QtCore import QByteArray, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .ble import DeviceInfo
from .hr import heart_rate_zone
from .theme import ACCENT, MUTED, ZONE_COLORS
from .widgets import (
    BrandMark,
    PulseHeart,
    Sparkline,
    SignalBars,
    StatusPill,
    ToggleSwitch,
    ZoneBadge,
)

STATE_LABEL = {
    "idle": "未连接",
    "connecting": "正在连接…",
    "reconnecting": "正在重连…",
    "connected": "已连接",
    "disconnected": "连接已断开",
    "error": "蓝牙不可用",
}


class ElidedLabel(QLabel):
    """超长设备名自动打点，不撑破布局。"""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._full = text
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: str) -> None:
        if text == self._full:
            return
        self._full = text
        self._apply()

    def _apply(self) -> None:
        width = max(40, self.width())
        elided = QFontMetrics(self.font()).elidedText(
            self._full, Qt.TextElideMode.ElideRight, width
        )
        super().setText(elided)
        self.setToolTip(self._full if elided != self._full else "")

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._apply()
        super().resizeEvent(event)


class DeviceRow(QFrame):
    connectRequested = Signal(str, str)
    disconnectRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DeviceRow")
        self.setFixedHeight(56)
        self.address = ""
        self.name = ""

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 10, 6)
        lay.setSpacing(8)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(1)
        self._name = ElidedLabel("设备")
        self._name.setObjectName("DeviceName")
        left.addWidget(self._name)
        self._meta = ElidedLabel("—")
        self._meta.setObjectName("DeviceMeta")
        left.addWidget(self._meta)
        lay.addLayout(left, 1)

        self._badge = QLabel("广播心率")
        self._badge.setObjectName("Badge")
        self._badge.setVisible(False)
        lay.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignVCenter)

        self._bars = SignalBars()
        lay.addWidget(self._bars, 0, Qt.AlignmentFlag.AlignVCenter)

        self._button = QPushButton("连接")
        self._button.setFixedSize(62, 27)
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self._on_click)
        lay.addWidget(self._button, 0, Qt.AlignmentFlag.AlignVCenter)

        self._connected = False

    def _on_click(self) -> None:
        if self._connected:
            self.disconnectRequested.emit()
        else:
            self.connectRequested.emit(self.address, self.name)

    def update_info(self, info: DeviceInfo, active: str, link_state: str) -> None:
        self.address = info.address
        self.name = info.name
        self._name.set_full_text(info.name)
        self._meta.set_full_text(f"{info.address}   {info.rssi} dBm")
        self._bars.set_rssi(info.rssi)

        if info.hr_adv is not None:
            badge_text = f"广播心率 {info.hr_adv}"
            if self._badge.text() != badge_text:
                self._badge.setText(badge_text)
            self._badge.setVisible(True)
        elif info.has_hr_service:
            self._badge.setText("心率服务")
            self._badge.setVisible(True)
        else:
            self._badge.setVisible(False)

        is_active = bool(active) and info.address == active
        connected = is_active and link_state == "connected"
        busy = is_active and link_state in ("connecting", "reconnecting")
        self._connected = connected

        if connected:
            text, enabled, name = "断开", True, "Danger"
        elif busy:
            text, enabled, name = "连接中", False, "Ghost"
        else:
            text, enabled, name = "连接", True, "Ghost"
        if self._button.text() != text:
            self._button.setText(text)
        if self._button.isEnabled() != enabled:
            self._button.setEnabled(enabled)
        if self._button.objectName() != name:
            self._button.setObjectName(name)
            self._button.style().unpolish(self._button)
            self._button.style().polish(self._button)

        if self.property("connected") != connected:
            self.setProperty("connected", connected)
            self.style().unpolish(self)
            self.style().polish(self)


class MainWindow(QMainWindow):
    floatingToggled = Signal(bool)
    deviceManagementToggled = Signal(bool)
    autoReconnectToggled = Signal(bool)
    historyToggled = Signal(bool)
    connectRequested = Signal(str, str)
    disconnectRequested = Signal()
    scanRequested = Signal()
    minimizedToTray = Signal()

    STATE_TEXT = STATE_LABEL

    def __init__(self, settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self._rows: dict[str, DeviceRow] = {}
        self._devices: list[DeviceInfo] = []
        self._active_address = ""
        self._link_state = "idle"
        self._active_name = ""
        self._last_hr_time = 0.0
        self._last_source = ""
        self._history_mode = True
        self._history_by_device: dict[str, list[list[int]]] = {}
        self._last_seen_address = ""
        self._history: deque[tuple[float, int]] = deque(maxlen=6000)
        self._sessions: list[dict] = []

        self.setWindowTitle("心率监测")
        self.resize(466, 900)
        self.setMinimumSize(420, 640)
        self._build_ui()
        self._restore_state()

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        self.setCentralWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)

        outer.addLayout(self._build_header())
        outer.addWidget(self._build_hero())
        outer.addWidget(self._build_switches())
        self._device_card = self._build_device_panel()
        outer.addWidget(self._device_card)
        outer.addStretch(1)

        self._footer = QLabel("关闭窗口后隐藏到托盘，心率监测仍在后台运行")
        self._footer.setObjectName("Sub")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self._footer)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(11)
        row.addWidget(BrandMark(42))

        col = QVBoxLayout()
        col.setContentsMargins(0, 2, 0, 0)
        col.setSpacing(0)
        title = QLabel("心率监测")
        title.setObjectName("H1")
        col.addWidget(title)
        sub = QLabel("BLE 手环 · 实时广播数据")
        sub.setObjectName("Sub")
        col.addWidget(sub)
        row.addLayout(col, 1)

        self._pill = StatusPill()
        row.addWidget(self._pill, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _build_hero(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Hero")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 15, 20, 15)
        lay.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._hint = QLabel("正在初始化蓝牙…")
        self._hint.setObjectName("Sub")
        top.addWidget(self._hint, 1)
        self._battery = QLabel("")
        self._battery.setObjectName("Battery")
        top.addWidget(self._battery, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(top)

        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(6)

        value_col = QHBoxLayout()
        value_col.setContentsMargins(0, 0, 0, 0)
        value_col.setSpacing(6)
        self._bpm = QLabel("--")
        font = QFont("Bahnschrift", 50)
        font.setWeight(QFont.Weight.Light)
        self._bpm.setFont(font)
        self._bpm.setStyleSheet(f"color: {MUTED};")
        value_col.addWidget(self._bpm, 0, Qt.AlignmentFlag.AlignBottom)
        unit = QLabel("BPM")
        unit.setStyleSheet(f"color: {MUTED}; font-size: 12px; padding-bottom: 12px;")
        value_col.addWidget(unit, 0, Qt.AlignmentFlag.AlignBottom)
        value_col.addStretch(1)
        main_row.addLayout(value_col, 1)

        self._heart = PulseHeart(62)
        main_row.addWidget(self._heart, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(main_row)

        zone_row = QHBoxLayout()
        zone_row.setContentsMargins(0, 0, 0, 0)
        self._zone = ZoneBadge()
        zone_row.addWidget(self._zone, 0, Qt.AlignmentFlag.AlignLeft)
        zone_row.addStretch(1)
        self._source = QLabel("")
        self._source.setObjectName("Sub")
        zone_row.addWidget(self._source, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(zone_row)

        line = QFrame()
        line.setObjectName("Divider")
        lay.addSpacing(4)
        lay.addWidget(line)
        lay.addSpacing(2)

        stats = QHBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(8)
        self._stat_min = self._add_stat(stats, "最低")
        self._stat_avg = self._add_stat(stats, "平均")
        self._stat_max = self._add_stat(stats, "最高")
        lay.addLayout(stats)

        self._spark = Sparkline()
        lay.addSpacing(4)
        lay.addWidget(self._spark)
        return card

    def _add_stat(self, row: QHBoxLayout, label: str) -> QLabel:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        cap = QLabel(label)
        cap.setObjectName("StatLabel")
        box.addWidget(cap)
        value = QLabel("—")
        value.setObjectName("StatValue")
        box.addWidget(value)
        row.addLayout(box, 1)
        return value

    def _build_switches(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 5, 18, 5)
        lay.setSpacing(0)

        row1, self._floating_switch = self._switch_row(
            "悬浮窗", "在桌面置顶显示实时心率", self.settings.floating_visible
        )
        lay.addWidget(row1)
        line = QFrame()
        line.setObjectName("Divider")
        lay.addWidget(line)
        row2, self._device_switch = self._switch_row(
            "设备管理", "扫描手环、连接设备并自动重连", self.settings.device_management
        )
        lay.addWidget(row2)
        divider2 = QFrame()
        divider2.setObjectName("Divider")
        lay.addWidget(divider2)
        row3, self._history_switch = self._switch_row(
            "历史数据", "查看之前连接手环的历史心率", self.settings.history_mode
        )
        lay.addWidget(row3)

        self._floating_switch.toggled.connect(self.floatingToggled.emit)
        self._device_switch.toggled.connect(self._on_device_switch)
        self._history_switch.toggled.connect(self.historyToggled.emit)
        self.set_history_mode(self.settings.history_mode)
        return card

    def _switch_row(self, title: str, desc: str, checked: bool):
        row = QWidget()
        row.setFixedHeight(50)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 5, 0, 5)
        h.setSpacing(10)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        name = QLabel(title)
        name.setObjectName("H2")
        col.addWidget(name)
        sub = QLabel(desc)
        sub.setObjectName("Sub")
        col.addWidget(sub)
        h.addLayout(col, 1)

        switch = ToggleSwitch()
        switch.setChecked(checked)
        h.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return row, switch

    def _build_device_panel(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 0, 0)
        title = QLabel("附近设备")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        self._scan_hint = QLabel("扫描中…")
        self._scan_hint.setObjectName("Sub")
        head.addWidget(self._scan_hint, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        refresh = QPushButton("刷新")
        refresh.setObjectName("Ghost")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.scanRequested.emit)
        head.addWidget(refresh)
        lay.addLayout(head)

        self._device_scroll = QScrollArea()
        self._device_scroll.setWidgetResizable(True)
        self._device_scroll.setFixedHeight(190)
        self._device_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self._device_scroll.setWidget(inner)
        self._device_layout = QVBoxLayout(inner)
        self._device_layout.setContentsMargins(0, 0, 4, 0)
        self._device_layout.setSpacing(6)

        self._empty = QLabel("未发现设备\n请确认手环蓝牙已开启并处于广播状态")
        self._empty.setObjectName("Empty")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._device_layout.addWidget(self._empty)
        self._device_layout.addStretch(1)
        lay.addWidget(self._device_scroll)

        auto_row = QHBoxLayout()
        auto_row.setContentsMargins(2, 2, 0, 0)
        auto_col = QVBoxLayout()
        auto_col.setContentsMargins(0, 0, 0, 0)
        auto_col.setSpacing(0)
        auto_title = QLabel("自动重连")
        auto_title.setObjectName("H2")
        auto_col.addWidget(auto_title)
        auto_sub = QLabel("连接中断后按 2/4/8/16/30 秒重试")
        auto_sub.setObjectName("Sub")
        auto_col.addWidget(auto_sub)
        auto_row.addLayout(auto_col, 1)
        self._auto_switch = ToggleSwitch()
        self._auto_switch.setChecked(self.settings.auto_reconnect)
        self._auto_switch.toggled.connect(self.autoReconnectToggled.emit)
        auto_row.addWidget(self._auto_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(auto_row)

        self._log = QPlainTextEdit()
        self._log.setObjectName("Log")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(56)
        self._log.setMaximumBlockCount(200)
        self._log.setPlaceholderText("运行日志")
        lay.addWidget(self._log)

        self._session_list = QListWidget()
        self._session_list.setObjectName("SessionList")
        self._session_list.setMaximumHeight(92)
        self._session_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; } QListWidget::item { padding: 2px 4px; }"
        )
        self._session_list.setVisible(bool(self._sessions))
        lay.addWidget(self._session_list)

        card.setVisible(self.settings.device_management)
        return card

    # ------------------------------------------------------------------ 状态
    def _restore_state(self) -> None:
        if self.settings.window_geometry:
            try:
                data = QByteArray.fromBase64(self.settings.window_geometry.encode("ascii"))
                self.restoreGeometry(data)
            except Exception:
                pass

    def _on_device_switch(self, checked: bool) -> None:
        self._device_card.setVisible(checked)
        self.deviceManagementToggled.emit(checked)

    def set_floating_switch(self, checked: bool) -> None:
        self._floating_switch.blockSignals(True)
        self._floating_switch.setChecked(checked)
        self._floating_switch.blockSignals(False)

    def set_device_switch(self, checked: bool) -> None:
        self._device_switch.blockSignals(True)
        self._device_switch.setChecked(checked)
        self._device_switch.blockSignals(False)
        self._device_card.setVisible(checked)

    def set_auto_switch(self, checked: bool) -> None:
        self._auto_switch.blockSignals(True)
        self._auto_switch.setChecked(checked)
        self._auto_switch.blockSignals(False)

    def set_history_mode(self, enabled: bool) -> None:
        self._history_mode = bool(enabled)
        self._history_switch.blockSignals(True)
        self._history_switch.setChecked(bool(enabled))
        self._history_switch.blockSignals(False)

    def set_device_history(self, address: str, samples: list) -> None:
        if not address:
            return
        self._history_by_device[address] = [list(x) for x in samples or []]
        self._last_seen_address = address
        self._apply_history()

    def _is_live_fresh(self) -> bool:
        return bool(self._last_hr_time) and (time.monotonic() - self._last_hr_time) <= 15

    def _apply_history(self) -> None:
        if not self._history_mode:
            return
        key = self._active_address or self._last_seen_address
        samples = self._history_by_device.get(key, []) if key else []
        if not samples:
            return
        ts, bpm = samples[-1]
        zone = heart_rate_zone(bpm)
        color = ZONE_COLORS.get(zone, ACCENT)
        points = list(self._spark._points)
        if not points or points[-1][0] != ts or points[-1][1] != bpm:
            self._spark.add(bpm, ts)
        self._bpm.setText(str(bpm))
        self._bpm.setStyleSheet(f"color: {color};")
        self._heart.set_bpm(bpm, color)
        self._zone.set_zone(zone)
        self._source.setText(f"历史 · {zone} · {max(0, int(time.monotonic() - ts))} 秒前")
        self._last_hr_time = ts

    def set_devices(self, devices: list[DeviceInfo]) -> None:
        self._devices = devices
        shown = devices[:12]
        wanted = {d.address for d in shown}
        for address in list(self._rows):
            if address not in wanted:
                row = self._rows.pop(address)
                self._device_layout.removeWidget(row)
                row.deleteLater()

        for info in shown:
            row = self._rows.get(info.address)
            if row is None:
                row = DeviceRow()
                row.connectRequested.connect(self.connectRequested.emit)
                row.disconnectRequested.connect(self.disconnectRequested.emit)
                self._rows[info.address] = row
                self._device_layout.insertWidget(self._device_layout.count() - 2, row)
            row.update_info(info, self._active_address, self._link_state)

        self._empty.setVisible(not shown)
        if self._link_state not in ("connected", "connecting", "reconnecting"):
            self._scan_hint.setText(f"扫描中 · {len(devices)} 台" if devices else "扫描中…")

    def set_link(self, state: str, address: str, name: str) -> None:
        previous = self._active_address
        self._link_state = state
        self._active_address = address if state in ("connected", "connecting", "reconnecting") else ""
        if name:
            self._active_name = name

        if state == "connecting" and address != previous:
            self._reset_metrics()
        if state in ("disconnected", "error"):
            self._last_hr_time = 0.0

        if state == "connected":
            self._pill.set_state("connected", "已连接")
            self._hint.setText("已连接，等待心率数据…")
            self._scan_hint.setText("已连接 · 扫描暂停")
            if address != previous:
                self._reset_metrics()
        elif state == "connecting":
            self._pill.set_state("connecting", STATE_LABEL["connecting"])
            self._hint.setText(f"正在连接 {name}…")
            self._scan_hint.setText("连接中 · 扫描暂停")
        elif state == "reconnecting":
            self._pill.set_state("reconnecting", STATE_LABEL["reconnecting"])
            self._hint.setText("连接中断，正在自动重连…")
            self._scan_hint.setText("重连中 · 扫描暂停")
        elif state == "disconnected":
            self._pill.set_state("disconnected", STATE_LABEL["disconnected"])
            self._hint.setText("连接已断开")
            self._scan_hint.setText("扫描已暂停")
        elif state == "error":
            self._pill.set_state("error", STATE_LABEL["error"])
            self._hint.setText("蓝牙不可用，请检查适配器与系统权限")
            self._scan_hint.setText("扫描异常")
        else:
            self._pill.set_state("idle", STATE_LABEL["idle"])
            self._hint.setText(
                "正在扫描附近设备…" if self._device_switch.isChecked() else "设备管理已关闭"
            )
            self._scan_hint.setText("扫描中…" if self._device_switch.isChecked() else "扫描已暂停")
            if previous:
                self._reset_metrics()

        for row in self._rows.values():
            info = next((d for d in self._devices if d.address == row.address), None)
            if info is not None:
                row.update_info(info, self._active_address, self._link_state)
        if state == "connected":
            self._apply_history()
        self._refresh_hint()

    def push_hr(self, bpm: int, source: str, address: str = "", name: str = "") -> None:
        now = time.monotonic()
        if address:
            self._last_seen_address = address
        if name:
            self._active_name = name
        self._last_hr_time = now
        self._last_source = source
        self._history.append((now, bpm))
        self._spark.add(bpm)
        zone = heart_rate_zone(bpm)
        color = ACCENT
        self._bpm.setText(str(bpm))
        self._bpm.setStyleSheet(f"color: {color};")
        self._heart.set_bpm(bpm, color)
        self._zone.set_zone(zone)
        self._source.setText(source)
        if source == "广播" and self._link_state not in (
            "connected", "connecting", "reconnecting"
        ):
            self._pill.set_state("broadcasting", "广播心率")
        self._update_stats()
        self._refresh_hint()

    def set_battery(self, level: int) -> None:
        self._battery.setText(f"电量 {level}%" if level >= 0 else "")

    def set_scanning(self, scanning: bool, count: int = 0) -> None:
        if scanning:
            self._scan_hint.setText(f"扫描中 · {count} 台" if count else "扫描中…")
        else:
            self._scan_hint.setText("扫描已暂停")

    def append_log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{stamp}] {message}")

    def set_sessions(self, sessions: list) -> None:
        self._sessions = [dict(r) for r in (sessions or [])]
        self._session_list.clear()
        for record in self._sessions:
            item = (
                f"{record.get('name') or record.get('address') or '设备'} · "
                f"{record.get('start')} - {record.get('end')} · "
                f"样本 {record.get('samples')} 条 · 平均 {record.get('avg')} · "
                f"最大 {record.get('max')} · 最后 {record.get('last')}"
            )
            self._session_list.addItem(item)

    def _update_stats(self) -> None:
        cutoff = time.monotonic() - 600
        vals = [v for ts, v in self._history if ts >= cutoff]
        if not vals:
            return
        self._stat_min.setText(str(min(vals)))
        self._stat_avg.setText(str(round(sum(vals) / len(vals))))
        self._stat_max.setText(str(max(vals)))

    def _reset_metrics(self) -> None:
        self._history.clear()
        self._spark.clear()
        self._last_hr_time = 0.0
        self._last_source = ""
        self._bpm.setText("--")
        self._bpm.setStyleSheet(f"color: {MUTED};")
        self._heart.set_bpm(0)
        self._zone.set_zone(None)
        self._source.setText("")
        self._stat_min.setText("—")
        self._stat_avg.setText("—")
        self._stat_max.setText("—")

    def _refresh_hint(self) -> None:
        state = self._link_state
        device_name = self._active_name or "设备"
        if len(device_name) > 18:
            device_name = device_name[:17] + "…"
        if state in ("connecting", "reconnecting"):
            self._hint.setText(STATE_LABEL[state])
            return
        if state == "error":
            self._hint.setText("蓝牙不可用，请检查适配器与系统权限")
            return
        if self._last_hr_time:
            dt = max(0, int(time.monotonic() - self._last_hr_time))
            ago = f"{dt} 秒前" if dt < 60 else f"{dt // 60} 分钟前"
            if dt > 12:
                self._hint.setText(f"{device_name} · 最近一条数据在 {ago}")
            else:
                self._hint.setText(f"{device_name} · {self._last_source} · {ago}")
        elif state == "connected":
            self._hint.setText("已连接，等待心率数据…")

    def _tick(self) -> None:
        self._refresh_hint()
        if self._last_hr_time and time.monotonic() - self._last_hr_time > 15:
            self._heart.set_bpm(0)
            self._apply_history()
            if (
                self._link_state not in ("connected", "connecting", "reconnecting")
                and self._last_source == "广播"
            ):
                self._pill.set_state("idle", "未连接")

    # ------------------------------------------------------------------ 事件
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.hide()
        self.minimizedToTray.emit()
        event.ignore()
