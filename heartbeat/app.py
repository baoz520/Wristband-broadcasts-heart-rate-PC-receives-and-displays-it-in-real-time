"""应用装配：托盘、全局状态、悬浮窗与蓝牙线程的协同。"""

from __future__ import annotations

import ctypes
import sys
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .ble import BleWorker
from .config import Settings
from .floating import FloatingWindow
from .main_window import MainWindow
from .theme import apply_theme
from .widgets import make_app_icon

SINGLE_INSTANCE_KEY = "XINTIAO.HeartRateMonitor.v1"


class SingleInstance:
    """用本地套接字保证只运行一个实例，第二次启动时唤起已有窗口。"""

    def __init__(self, key: str):
        self._callback = None
        self._server: QLocalServer | None = None
        self.already_running = False

        probe = QLocalSocket()
        probe.connectToServer(key)
        if probe.waitForConnected(250):
            probe.write(b"show")
            probe.flush()
            probe.waitForBytesWritten(250)
            probe.disconnectFromServer()
            self.already_running = True
            return

        QLocalServer.removeServer(key)
        self._server = QLocalServer()
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(key)

    def set_callback(self, callback) -> None:
        self._callback = callback

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            if sock is not None:
                sock.readyRead.connect(lambda s=sock: (s.readAll(), s.deleteLater()))
                sock.disconnected.connect(sock.deleteLater)
                if self._callback:
                    self._callback()


class Controller(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        self.app = app
        self.settings = Settings.load()
        self.settings_saved_on_exit = False

        self.window = MainWindow(self.settings)
        self.floating = FloatingWindow()
        self._history_window = None  # 延迟创建：点击「查看历史数据」时才实例化
        self.worker = BleWorker(self.settings.auto_reconnect, self)

        self._last_hr_time = 0.0
        self._tray_hint_shown = False
        self._quitting = False
        self.history_mode = self.settings.history_mode
        self._history_by_device: dict[str, list[list[int]]] = {
            addr: [list(x) for x in samples] for addr, samples in (self.settings.history or {}).items()
        }
        self._sessions: list[dict] = [dict(r) for r in (self.settings.history_sessions or [])]
        self._session: dict | None = None

        self._build_tray()
        self._wire()
        self._apply_initial_state()

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._tick)
        self._ui_timer.start(1000)

        self.app.aboutToQuit.connect(self._on_about_to_quit)

    # ------------------------------------------------------------------ 构建
    def _build_tray(self) -> None:
        icon = make_app_icon()
        self.app.setWindowIcon(icon)
        self.window.setWindowIcon(icon)
        self.floating.setWindowIcon(icon)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("心率监测")
        menu = QMenu()
        self._act_show = menu.addAction("显示主界面")
        menu.addSeparator()
        self._act_float = menu.addAction("显示悬浮窗")
        self._act_float.setCheckable(True)
        self._act_devices = menu.addAction("设备管理")
        self._act_devices.setCheckable(True)
        self._act_close_prompt = menu.addAction("关闭时询问")
        self._act_close_prompt.setCheckable(True)
        self._act_close_prompt.setChecked(bool(self.settings.close_prompt_enabled))
        self._act_close_prompt.setToolTip("勾选后，点击关闭按钮会先询问最小化还是退出")
        menu.addSeparator()
        self._act_quit = menu.addAction("退出")

        self._act_show.triggered.connect(self.show_main)
        self._act_float.toggled.connect(self.set_floating)
        self._act_devices.toggled.connect(self.set_device_management)
        self._act_close_prompt.toggled.connect(self._set_close_prompt)
        self._act_quit.triggered.connect(self.quit)
        self.tray.setContextMenu(menu)
        self._menu = menu
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _wire(self) -> None:
        self.window.floatingToggled.connect(self.set_floating)
        self.window.deviceManagementToggled.connect(self.set_device_management)
        self.window.autoReconnectToggled.connect(self._set_auto_reconnect)
        self.window.historyToggled.connect(self._set_history_mode)
        self.window.historyWindowRequested.connect(self.show_history_window)
        self.window.connectRequested.connect(self._connect_device)
        self.window.disconnectRequested.connect(self.worker.disconnect_device)
        self.window.scanRequested.connect(self._manual_refresh)
        self.window.minimizedToTray.connect(self._on_minimized)
        self.window.quitRequested.connect(self.quit)
        self.window.saveSettingsRequested.connect(self._save_settings)

        self.floating.openMainRequested.connect(self.show_main)
        self.floating.hideRequested.connect(lambda: self.set_floating(False))
        self.floating.quitRequested.connect(self.quit)
        self.floating.lockChanged.connect(self._set_floating_locked)
        self.floating.movedByUser.connect(self._save_floating_position)

        self.worker.devicesChanged.connect(self.window.set_devices)
        self.worker.heartRate.connect(self._on_heart_rate)
        self.worker.linkChanged.connect(self._on_link_changed)
        self.worker.batteryChanged.connect(self.window.set_battery)
        self.worker.log.connect(self._on_log)

    def _apply_initial_state(self) -> None:
        self.window.set_floating_switch(self.settings.floating_visible)
        self.window.set_device_switch(self.settings.device_management)
        self.window.set_auto_switch(self.settings.auto_reconnect)
        self._act_float.blockSignals(True)
        self._act_float.setChecked(self.settings.floating_visible)
        self._act_float.blockSignals(False)
        self._act_devices.blockSignals(True)
        self._act_devices.setChecked(self.settings.device_management)
        self._act_devices.blockSignals(False)
        self._act_close_prompt.blockSignals(True)
        self._act_close_prompt.setChecked(bool(self.settings.close_prompt_enabled))
        self._act_close_prompt.blockSignals(False)

        self.floating.set_locked(self.settings.floating_locked)
        if self.settings.floating_x >= 0 and self.settings.floating_y >= 0:
            self.floating.move(self.settings.floating_x, self.settings.floating_y)
            self.floating.keep_on_screen()
        else:
            self.floating.show_near_corner()
        if self.settings.floating_visible:
            self.floating.show()

        if self.settings.saved_address:
            self.floating.set_link("idle", self.settings.saved_address, self.settings.saved_name)

        # 启动时把持久化的历史数据装进界面，否则"查看历史数据"在刚打开时是空的
        self.window.set_sessions(list(self._sessions))
        for address, samples in self._history_by_device.items():
            if samples:
                self.window.set_device_history(address, samples)
                self.floating.set_device_history(address, samples)
                break  # 折线图只显示一台设备，优先第一台有数据的
        self.window.append_log("应用已启动，正在准备蓝牙扫描…")

    def start(self) -> None:
        self.window.show()
        self.window.raise_()
        self.worker.start()
        QTimer.singleShot(200, self._startup_ble)

    def _startup_ble(self) -> None:
        if not self.settings.device_management:
            self.window.set_scanning(False)
            return
        self.worker.set_auto_reconnect(self.settings.auto_reconnect)
        self.worker.start_scan()
        if self.settings.saved_address and self.settings.auto_reconnect:
            QTimer.singleShot(500, self._auto_connect_saved)

    def _auto_connect_saved(self) -> None:
        if (
            self.settings.device_management
            and self.settings.saved_address
            and self.settings.auto_reconnect
        ):
            self.window.append_log(
                f"尝试连接上次设备：{self.settings.saved_name or self.settings.saved_address}"
            )
            self.worker.connect_device(self.settings.saved_address, self.settings.saved_name)

    # ------------------------------------------------------------------ 操作
    def show_main(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def show_history_window(self) -> None:
        """打开历史记录窗口；每次打开都用最新的会话列表刷新。"""
        if self._history_window is None:
            from .history_window import HistoryWindow

            self._history_window = HistoryWindow(self._sessions, self.window)
            self._history_window.setWindowIcon(self.window.windowIcon())
        else:
            self._history_window.set_sessions(list(self._sessions))
        self._history_window.center_on(self.window)
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._save_settings()
        self._ui_timer.stop()
        self.worker.shutdown()
        self.tray.hide()
        self.floating.hide()
        if self._history_window is not None:
            self._history_window.hide()
        self.window.hide()
        self.app.quit()

    def set_floating(self, visible: bool) -> None:
        self.settings.floating_visible = bool(visible)
        self.window.set_floating_switch(visible)
        self._act_float.blockSignals(True)
        self._act_float.setChecked(visible)
        self._act_float.blockSignals(False)
        if visible:
            if self.floating.x() < 0 or self.floating.y() < 0:
                self.floating.show_near_corner()
            self.floating.show()
            self.floating.raise_()
            if self.settings.saved_address:
                self.floating.set_link(
                    self._current_state, self.settings.saved_address, self.settings.saved_name
                )
        else:
            self.floating.hide()
        self._save_settings()

    @property
    def _current_state(self) -> str:
        return getattr(self, "_link_state", "idle")

    def set_device_management(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.settings.device_management = enabled
        self.window.set_device_switch(enabled)
        self._act_devices.blockSignals(True)
        self._act_devices.setChecked(enabled)
        self._act_devices.blockSignals(False)

        if enabled:
            if self._current_state not in ("connected", "connecting", "reconnecting"):
                self.worker.start_scan()
            if self.settings.auto_reconnect and self.settings.saved_address:
                if self._current_state not in ("connected", "connecting", "reconnecting"):
                    self.worker.connect_device(
                        self.settings.saved_address, self.settings.saved_name
                    )
        else:
            self.worker.stop_scan()
            self.worker.disconnect_device()
            self.window.set_scanning(False)
            self.window.append_log("设备管理已关闭，停止扫描并断开手环")
        self._save_settings()

    def _set_auto_reconnect(self, enabled: bool) -> None:
        self.settings.auto_reconnect = bool(enabled)
        self.worker.set_auto_reconnect(enabled)
        self.window.set_auto_switch(enabled)
        self._save_settings()

    def _set_close_prompt(self, enabled: bool) -> None:
        """托盘菜单可重新开启「关闭时询问」，避免不再提示后无法改回。"""
        self.settings.close_prompt_enabled = bool(enabled)
        self._save_settings()

    def _set_history_mode(self, enabled: bool) -> None:
        self.history_mode = bool(enabled)
        self.settings.history_mode = bool(enabled)
        self.window.set_history_mode(bool(enabled))
        self.floating.set_history_mode(bool(enabled))
        if enabled:
            # 最近设备地址保存在主窗口上；Controller 本身没有该字段。
            # 依次用窗口的活动/最近地址，最后回退到历史里有数据的最近一台。
            address = (
                getattr(self.window, "_active_address", "")
                or getattr(self.window, "_last_seen_address", "")
            )
            if not address or address not in self._history_by_device:
                samples_with_devices = [
                    (addr, s) for addr, s in self._history_by_device.items() if s
                ]
                address = samples_with_devices[-1][0] if samples_with_devices else ""
            samples = self._history_by_device.get(address, []) if address else []
            if address and samples:
                self.window.set_device_history(address, samples)
                self.window.apply_history_now()
                self.floating.set_device_history(address, samples)
                self.floating.set_hr(None, "历史", address, self.window._active_name or address)
        self._save_settings()

    def _connect_device(self, address: str, name: str) -> None:
        if not self.settings.device_management:
            self.window.append_log("请先打开“设备管理”开关")
            return
        self.settings.saved_address = address
        self.settings.saved_name = name
        self._save_settings()
        self.floating.set_link("connecting", address, name)
        self.worker.connect_device(address, name)

    def _manual_refresh(self) -> None:
        if not self.settings.device_management:
            return
        if self._current_state in ("connected", "connecting", "reconnecting"):
            self.window.append_log("已连接，暂不扫描；断开后可刷新设备列表")
            return
        self.window.append_log("手动刷新：重新扫描附近设备")
        self.worker.start_scan()

    def _resume_scan_if_idle(self) -> None:
        if self._quitting or not self.settings.device_management:
            return
        if self._current_state in ("connected", "connecting", "reconnecting"):
            return
        self.worker.start_scan()

    def _set_floating_locked(self, locked: bool) -> None:
        self.settings.floating_locked = bool(locked)
        self._save_settings()

    def _save_floating_position(self) -> None:
        self.settings.floating_x = self.floating.x()
        self.settings.floating_y = self.floating.y()
        self._save_settings()

    # ------------------------------------------------------------------ 回调
    def _on_heart_rate(self, bpm: int, source: str, address: str, name: str) -> None:
        self._last_hr_time = time.monotonic()
        self.window.push_hr(bpm, source, address, name)
        self.floating.set_hr(bpm, source, address, name)
        self.tray.setToolTip(f"心率监测 · {bpm} BPM")

        samples = self._history_by_device.setdefault(address, [])
        samples.append([int(time.time()), bpm])
        if len(samples) > 200:
            del samples[:-200]
        self.window.set_device_history(address, samples)
        self.floating.set_device_history(address, samples)

        if self._session is None or self._session.get("address") != address:
            self._session = {
                "address": address,
                "name": name or address,
                "start": int(time.time()),
                "count": 0,
                "min": None,
                "max": None,
                "sum": 0.0,
                "last": None,
                # 本次连接的完整心率曲线，供历史记录窗口逐条绘制折线图。
                "series": [],
            }
        self._session["count"] = int(self._session.get("count") or 0) + 1
        self._session["sum"] = float(self._session.get("sum") or 0) + bpm
        self._session["min"] = bpm if self._session.get("min") is None else min(int(self._session["min"]), bpm)
        self._session["max"] = bpm if self._session.get("max") is None else max(int(self._session["max"]), bpm)
        self._session["last"] = bpm
        # 采样曲线：与全局历史一致用 Unix 秒，限制长度避免持久化文件膨胀。
        series = self._session.setdefault("series", [])
        series.append([int(time.time()), int(bpm)])
        if len(series) > 200:
            del series[:-200]

    def _finalize_session(self) -> None:
        if not self._session:
            return
        if not int(self._session.get("count") or 0) > 0:
            self._session = None
            return
        count = int(self._session["count"])
        self._sessions.append(
            {
                "address": self._session.get("address") or "",
                "name": self._session.get("name") or self._session.get("address") or "设备",
                "start": int(self._session.get("start") or time.time()),
                "end": int(time.time()),
                "samples": count,
                "min": int(self._session["min"]),
                "max": int(self._session["max"]),
                "avg": round(float(self._session.get("sum") or 0.0) / count, 1),
                "last": int(self._session.get("last") or 0),
                "series": [list(x) for x in (self._session.get("series") or [])],
            }
        )
        if len(self._sessions) > 50:
            self._sessions = self._sessions[-50:]
        self.window.set_sessions(list(self._sessions))
        self.settings.history_sessions = list(self._sessions)
        self._session = None
        # 历史窗口若已打开，立即刷新以显示刚结束的这次连接
        if self._history_window is not None:
            self._history_window.set_sessions(list(self._sessions))

    def _on_link_changed(self, state: str, address: str, name: str) -> None:
        self._link_state = state
        self.window.set_link(state, address, name)
        self.floating.set_link(state, address, name)
        if state == "connected" and address:
            self.settings.saved_address = address
            self.settings.saved_name = name
            self._save_settings()
            self._last_hr_time = 0.0
        if state == "connected" and address:
            samples = self._history_by_device.get(address, [])
            if samples:
                self.window.set_device_history(address, samples)
                self.floating.set_device_history(address, samples)
        if state in ("disconnected", "idle", "error"):
            self._finalize_session()
        if state == "connected":
            self.tray.setToolTip(f"心率监测 · {name or address}")
        elif state in ("idle", "disconnected", "error"):
            self.tray.setToolTip("心率监测 · 未连接")
            if self.settings.device_management and state != "error":
                QTimer.singleShot(1200, self._resume_scan_if_idle)

    def _on_log(self, message: str) -> None:
        self.window.append_log(message)

    def _on_minimized(self) -> None:
        if not self._tray_hint_shown and self.tray.isVisible():
            self._tray_hint_shown = True
            self.tray.showMessage(
                "心率监测",
                "已隐藏到托盘，心率监测与悬浮窗继续运行。",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )

    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if self.window.isVisible() and not self.window.isMinimized():
                self.window.hide()
            else:
                self.show_main()

    def _tick(self) -> None:
        if self._last_hr_time:
            seconds = max(0, int(time.monotonic() - self._last_hr_time))
            self.floating.tick(seconds)
            if seconds > 15:
                self.floating.set_hr(None)
        elif self._current_state == "connected":
            self.floating.set_hr(None)

    def _save_settings(self) -> None:
        self.settings.window_geometry = bytes(self.window.saveGeometry().toBase64()).decode("ascii")
        if self.floating.isVisible():
            self.settings.floating_x = self.floating.x()
            self.settings.floating_y = self.floating.y()
        self.settings.history = {
            addr: [list(x) for x in samples] for addr, samples in self._history_by_device.items() if samples
        }
        self.settings.history_sessions = list(self._sessions)
        self.settings.save()

    def _on_about_to_quit(self) -> None:
        self._save_settings()
        if not self._quitting:
            self.worker.shutdown()


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "XINTIAO.HeartRateMonitor"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("心率监测")
    app.setApplicationDisplayName("心率监测")
    app.setOrganizationName("XINTIAO")
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)

    guard = SingleInstance(SINGLE_INSTANCE_KEY)
    if guard.already_running:
        return 0

    controller = Controller(app)
    guard.set_callback(controller.show_main)
    controller.start()
    return app.exec()
