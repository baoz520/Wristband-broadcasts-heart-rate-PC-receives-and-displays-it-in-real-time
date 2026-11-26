"""应用装配：托盘、全局状态、悬浮窗与蓝牙线程的协同。"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .backdrop import Backdrop
from .ble import BleWorker
from .capture import HighHeartCapture, capture_screen
from .config import Settings
from .floating import FloatingWindow
from .hr import HeartStateTracker
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
        Backdrop.configure(
            getattr(self.settings, "background_mode", "night"),
            getattr(self.settings, "background_color", "#0b1322"),
            getattr(self.settings, "background_image", ""),
            getattr(self.settings, "background_dim", 45),
        )
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
        self._state_trackers: dict[str, HeartStateTracker] = {}
        self._capture = HighHeartCapture()
        if not isinstance(getattr(self.settings, "screenshot_events", None), list):
            self.settings.screenshot_events = []
        # 游戏检测状态
        self._game_session: dict | None = None   # 当前正在进行的游戏会话
        self._game_pid: int | None = None
        self._game_name = ""
        self._game_extra: list[str] = list(self.settings.game_custom or [])
        self._game_auto_hidden = False  # 因游戏而临时隐藏悬浮窗，退出游戏后恢复
        self._settings_window = None

        self._build_tray()
        self._wire()
        self._apply_initial_state()

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._tick)
        self._ui_timer.start(1000)

        # 截图文件在文件夹里被手动删除后，软件内也要自动消失
        self._shot_watch_timer = QTimer(self)
        self._shot_watch_timer.timeout.connect(self.prune_missing_shots)
        self._shot_watch_timer.start(2000)

        # 游戏进程检测定时器（默认关闭，设置里可开启）
        self._game_timer = QTimer(self)
        self._game_timer.timeout.connect(self._check_game)
        if self.settings.game_detect_enabled:
            self._game_timer.start(max(2, int(self.settings.game_poll_seconds)) * 1000)

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
        self._act_lock = menu.addAction("锁定悬浮窗位置")
        self._act_lock.setCheckable(True)
        self._act_lock.setChecked(bool(self.settings.floating_locked))
        self._act_lock.setToolTip("锁定后鼠标可穿透悬浮窗；解锁请从托盘操作")
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
        self._act_lock.toggled.connect(self._toggle_floating_lock)
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
        self.window.hrDetectionToggled.connect(self._set_hr_detection)
        self.window.autoReconnectToggled.connect(self._set_auto_reconnect)
        self.window.historyToggled.connect(self._set_history_mode)
        self.window.historyWindowRequested.connect(self.show_history_window)
        self.window.settingsRequested.connect(self.show_settings_window)
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
        self.window.set_hr_detect_switch(self.settings.hr_detection_enabled)
        self.window.set_floating_switch(self.settings.floating_visible)
        self.window.set_device_switch(self.settings.device_management)
        self.window.set_auto_switch(self.settings.auto_reconnect)
        self._act_float.blockSignals(True)
        self._act_float.setChecked(self.settings.floating_visible)
        self._act_float.blockSignals(False)
        self._act_lock.blockSignals(True)
        self._act_lock.setChecked(bool(self.settings.floating_locked))
        self._act_lock.blockSignals(False)
        self._act_devices.blockSignals(True)
        self._act_devices.setChecked(self.settings.device_management)
        self._act_devices.blockSignals(False)
        self._act_close_prompt.blockSignals(True)
        self._act_close_prompt.setChecked(bool(self.settings.close_prompt_enabled))
        self._act_close_prompt.blockSignals(False)

        self.floating.set_locked(self.settings.floating_locked)
        self.floating.set_game_display_mode(
            getattr(self.settings, "game_float_mode", "transparent")
        )
        self.floating.set_appearance(
            width=self.settings.float_width,
            opacity=self.settings.float_opacity,
            show_heart=self.settings.float_show_heart,
            show_zone=self.settings.float_show_zone,
            show_device=self.settings.float_show_device,
        )
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
        if (
            self.settings.hr_detection_enabled
            and self.settings.saved_address
            and self.settings.auto_reconnect
        ):
            QTimer.singleShot(500, self._auto_connect_saved)

    def _auto_connect_saved(self) -> None:
        if (
            self.settings.device_management
            and self.settings.hr_detection_enabled
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
        self.prune_missing_shots()
        if self._history_window is None:
            from .history_window import HistoryWindow

            self._history_window = HistoryWindow(
                self._sessions,
                self.window,
                shots=list(self.settings.screenshot_events),
            )
            self._history_window.setWindowIcon(self.window.windowIcon())
            self._history_window.deleteRequested.connect(self.delete_session)
            self._history_window.shotDeleteRequested.connect(self.delete_shot)
        else:
            self._history_window.set_sessions(list(self._sessions))
            self._history_window.set_shots(list(self.settings.screenshot_events))
        self._history_window.center_on(self.window)
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    def show_settings_window(self) -> None:
        """打开设置窗口并连接即时生效信号。"""
        if self._settings_window is None:
            from .settings_window import SettingsWindow

            self._settings_window = SettingsWindow(self.settings, self.window)
            self._settings_window.setWindowIcon(self.window.windowIcon())
            sw = self._settings_window
            sw.floatWidthChanged.connect(lambda v: self.floating.set_appearance(width=v))
            sw.floatWidthChanged.connect(self._save_settings)
            sw.floatOpacityChanged.connect(lambda v: self.floating.set_appearance(opacity=v))
            sw.floatOpacityChanged.connect(self._save_settings)
            sw.floatShowHeartChanged.connect(lambda v: self.floating.set_appearance(show_heart=v))
            sw.floatShowHeartChanged.connect(self._save_settings)
            sw.floatShowZoneChanged.connect(lambda v: self.floating.set_appearance(show_zone=v))
            sw.floatShowZoneChanged.connect(self._save_settings)
            sw.floatShowDeviceChanged.connect(lambda v: self.floating.set_appearance(show_device=v))
            sw.floatShowDeviceChanged.connect(self._save_settings)
            sw.gameDetectChanged.connect(self._on_game_detect_changed)
            sw.gameCustomChanged.connect(self._on_game_custom_changed)
            sw.gameRecordChanged.connect(self._save_settings)
            sw.gameShowFloatChanged.connect(self._on_game_show_float_changed)
            sw.gameFloatModeChanged.connect(self._on_game_float_mode_changed)
            sw.gamePollChanged.connect(self._on_game_poll_changed)
            sw.backdropChanged.connect(self._on_backdrop_changed)
            sw.captureSettingsChanged.connect(self._on_capture_settings_changed)
        else:
            # 重新打开时把当前设置同步回界面
            self._settings_window._load_values()
        self._settings_window.center_on(self.window)
        self._settings_window.show()
        self._settings_window.raise_()

    def delete_session(self, key: str) -> None:
        """删除一条历史会话（按地址+开始时间定位），并刷新各视图与持久化。"""
        from .history_window import session_key

        before = len(self._sessions)
        self._sessions = [r for r in self._sessions if session_key(r) != key]
        if len(self._sessions) == before:
            return
        self.settings.history_sessions = list(self._sessions)
        # 归属这条会话的截图一并移除，避免历史里留下无法对应的图片。
        removed_shots = [
            shot for shot in self.settings.screenshot_events if shot.get("session") == key
        ]
        self.settings.screenshot_events = [
            shot for shot in self.settings.screenshot_events if shot.get("session") != key
        ]
        for shot in removed_shots:
            try:
                Path(shot.get("path", "")).unlink(missing_ok=True)
            except (OSError, TypeError):
                pass
        self.window.set_sessions(list(self._sessions))
        if self._history_window is not None:
            self._history_window.set_sessions(list(self._sessions))
            self._history_window.set_shots(list(self.settings.screenshot_events))
        self._save_settings()
        self.window.append_log("已删除一条历史记录")

    def _drop_shot(self, path: str) -> bool:
        """从索引和所有会话引用中移除一张截图，但不删除磁盘文件。"""
        path = str(path or "")
        if not path:
            return False
        before = len(self.settings.screenshot_events)
        self.settings.screenshot_events = [
            shot for shot in self.settings.screenshot_events
            if str(shot.get("path", "")) != path
        ]
        for session in self._sessions:
            shots = session.get("screenshots") or []
            if any(str(s.get("path", "")) == path for s in shots):
                session["screenshots"] = [
                    s for s in shots if str(s.get("path", "")) != path
                ]
        if self._session is not None:
            shots = self._session.get("screenshots") or []
            if any(str(s.get("path", "")) == path for s in shots):
                self._session["screenshots"] = [
                    s for s in shots if str(s.get("path", "")) != path
                ]
        return len(self.settings.screenshot_events) != before

    def delete_shot(self, path: str) -> None:
        """删除单张高心率截图：索引、会话引用与磁盘文件一起清理。"""
        path = str(path or "")
        changed = self._drop_shot(path)
        if not changed:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
        self._save_settings()
        self._refresh_shot_views()
        self.window.append_log(f"已删除一张高心率截图：{Path(path).name}")

    def prune_missing_shots(self) -> bool:
        """用户在文件夹里手动删除图片后，把失效索引一并清掉。

        历史窗口显示时按文件是否存在过滤，这里再把索引同步清理，避免
        设置文件长期累积无效记录。返回是否有变更。
        """
        from .history_window import shot_exists

        missing = [
            str(shot.get("path", ""))
            for shot in self.settings.screenshot_events
            if not shot_exists(str(shot.get("path", "")))
        ]
        changed = False
        for path in missing:
            changed = self._drop_shot(path) or changed
        if changed:
            self._save_settings()
            self._refresh_shot_views()
        return changed

    def _refresh_shot_views(self) -> None:
        """截图变动后同步主历史窗口（会话卡内嵌截图一并刷新）。"""
        if self._history_window is not None:
            self._history_window.set_sessions(list(self._sessions))
            self._history_window.set_shots(list(self.settings.screenshot_events))

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._finish_game_session()
        self._save_settings()
        self._ui_timer.stop()
        self.worker.shutdown()
        self.tray.hide()
        self.floating.hide()
        if self._history_window is not None:
            self._history_window.hide()
        self.window.hide()
        self.app.quit()

    def _set_hr_detection(self, enabled: bool) -> None:
        """心率检测总开关：关闭时停止一切心率处理并清空当前显示。"""
        enabled = bool(enabled)
        self.settings.hr_detection_enabled = enabled
        self.window.set_hr_detect_switch(enabled)
        if enabled:
            self.window.append_log("心率检测已开启")
            if (
                self.settings.device_management
                and self._current_state not in ("connected", "connecting", "reconnecting")
            ):
                self.worker.start_scan()
        else:
            self._finalize_session()
            self._session = None
            self.window._clear_current_hr()
            self.window.set_link("idle", "", "")
            self.floating.set_link("idle", "", "")
            self.tray.setToolTip("心率监测 · 检测已关闭")
            self.window.append_log("心率检测已关闭，已停止接收心率数据")
        self._capture.reset()
        self._save_settings()

    def set_floating(self, visible: bool) -> None:
        self.settings.floating_visible = bool(visible)
        self.window.set_floating_switch(visible)
        self._act_float.blockSignals(True)
        self._act_float.setChecked(visible)
        self._act_float.blockSignals(False)
        if visible:
            if self._game_auto_hidden and self.settings.game_detect_enabled:
                # 游戏期间整窗自动隐藏：用户手动打开开关也保持隐藏，退出游戏再恢复
                self._save_settings()
                return
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
            if (
                self.settings.hr_detection_enabled
                and self.settings.auto_reconnect
                and self.settings.saved_address
            ):
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

    def _toggle_floating_lock(self, locked: bool) -> None:
        """托盘菜单锁定/解锁：悬浮窗本身鼠标穿透后只能从这里解除。"""
        self.floating.set_locked(bool(locked))
        self._set_floating_locked(bool(locked))

    def _set_floating_locked(self, locked: bool) -> None:
        self.settings.floating_locked = bool(locked)
        self._act_lock.blockSignals(True)
        self._act_lock.setChecked(bool(locked))
        self._act_lock.blockSignals(False)
        self._save_settings()

    def _save_floating_position(self) -> None:
        self.settings.floating_x = self.floating.x()
        self.settings.floating_y = self.floating.y()
        self._save_settings()

    # ------------------------------------------------------------------ 回调
    def _ensure_session(self, address: str, name: str) -> dict:
        """切换设备时结束上一场，为当前设备建立新的会话容器。"""
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
                # 本次连接中的状态变化与高心率截屏索引。
                "state_events": [],
                "screenshots": [],
            }
        return self._session

    @staticmethod
    def _record_state_change(session: dict, label: str, ts: int) -> None:
        """只在状态真正变化时记一笔，避免每个采样点都写入历史。"""
        events = session.setdefault("state_events", [])
        if events and events[-1][1] == label:
            return
        events.append([int(ts), str(label)])
        if len(events) > 120:
            del events[:-120]

    def _on_heart_rate(self, bpm: int, source: str, address: str, name: str) -> None:
        if not getattr(self.settings, "hr_detection_enabled", True):
            return
        self._last_hr_time = time.monotonic()
        now = int(time.time())

        # 先写入历史，再用同一条序列算状态，保证判断看到的是最新样本。
        samples = self._history_by_device.setdefault(address, [])
        samples.append([now, bpm])
        if len(samples) > 200:
            del samples[:-200]
        tracker = self._state_trackers.setdefault(address, HeartStateTracker())
        state = tracker.update(samples)
        session = self._ensure_session(address, name)
        self._record_state_change(session, state.label, now)

        self.window.push_hr(bpm, source, address, name, state=state)
        self.floating.set_hr(bpm, source, address, name, state=state)
        self.tray.setToolTip(f"心率监测 · {bpm} BPM · {state.label}")
        # 游戏运行时把心率记入当前游戏会话
        if self._game_session is not None:
            self._record_game_hr(bpm, state.label)
            if self.settings.game_show_on_float:
                series = self._game_session.get("series") or []
                vals = [int(x[1]) for x in series if isinstance(x, (list, tuple)) and len(x) >= 2]
                self.floating.set_game_info(
                    self._game_name,
                    bpm=vals[-1] if vals else None,
                    low=min(vals) if vals else None,
                    high=max(vals) if vals else None,
                )

        self.window.set_device_history(address, samples)
        self.floating.set_device_history(address, samples)
        self._maybe_capture(bpm, state.label, address, name, session)

        session["count"] = int(session.get("count") or 0) + 1
        session["sum"] = float(session.get("sum") or 0) + bpm
        session["min"] = bpm if session.get("min") is None else min(int(session["min"]), bpm)
        session["max"] = bpm if session.get("max") is None else max(int(session["max"]), bpm)
        session["last"] = bpm
        # 采样曲线：与全局历史一致用 Unix 秒，限制长度避免持久化文件膨胀。
        series = session.setdefault("series", [])
        series.append([now, int(bpm)])
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
                "state_events": [list(x) for x in (self._session.get("state_events") or [])],
                "screenshots": [dict(x) for x in (self._session.get("screenshots") or [])],
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
        if state == "reconnecting" and self.settings.device_management:
            # 重连等待阶段重新开启扫描，掉线后仍能发现设备并接收广播心率
            self.worker.start_scan()
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

    # ------------------------------------------------------------ 游戏检测
    def _on_game_detect_changed(self, enabled: bool) -> None:
        if enabled:
            self._game_timer.start(max(2, int(self.settings.game_poll_seconds)) * 1000)
            self._check_game()
        else:
            self._game_timer.stop()
            self._finish_game_session(sync_visibility=False)
            self.floating.set_game_info("")
        self._sync_game_visibility(False)
        self._save_settings()

    def _on_game_custom_changed(self, names: list[str]) -> None:
        self._game_extra = list(names or [])
        self._save_settings()

    def _on_game_show_float_changed(self, enabled: bool) -> None:
        self._save_settings()
        if not enabled:
            self.floating.set_game_info("")

    def _on_game_float_mode_changed(self, mode: str) -> None:
        """游戏中悬浮窗显示方式改变后立即生效。"""
        self.settings.game_float_mode = mode
        self.floating.set_game_display_mode(mode)
        self._sync_game_visibility(bool(self._game_session))
        self._save_settings()

    def _sync_game_visibility(self, game_active: bool) -> None:
        """hidden 模式下：游戏运行时隐藏整窗，退出后按用户开关恢复。"""
        should_hide = bool(
            game_active
            and self.settings.game_detect_enabled
            and getattr(self.settings, "game_float_mode", "transparent") == "hidden"
        )
        if should_hide:
            # 即使悬浮窗本来就没显示也记下状态：游戏期间用户打开开关不会被放行
            if self.floating.isVisible():
                self.floating.hide()
            self._game_auto_hidden = True
        elif not should_hide and self._game_auto_hidden:
            self._game_auto_hidden = False
            if self.settings.floating_visible:
                self.floating.show()
                self.floating.raise_()

    def _on_game_poll_changed(self, seconds: int) -> None:
        if self.settings.game_detect_enabled:
            self._game_timer.start(max(2, int(seconds)) * 1000)
        self._save_settings()

    def _on_backdrop_changed(self) -> None:
        """背景切换后重配全局背景并刷新所有半透明界面。"""
        Backdrop.configure(
            self.settings.background_mode,
            self.settings.background_color,
            self.settings.background_image,
            self.settings.background_dim,
        )
        Backdrop.refresh_all()
        self._save_settings()

    def _on_capture_settings_changed(self) -> None:
        """截屏阈值 / 节奏变化后重置持续计时，避免沿用旧触发状态。"""
        self._capture.reset()
        self._save_settings()
        self.window.append_log("高心率截屏设置已更新")

    def _maybe_capture(
        self,
        bpm: int,
        state: str,
        address: str,
        name: str,
        session: dict,
    ) -> None:
        """达到用户设定的心率条件时自动截屏，并把时间戳索引写入历史。"""
        if not getattr(self.settings, "capture_enabled", False):
            return
        if not self._capture.ready(
            bpm,
            int(time.time()),
            int(getattr(self.settings, "capture_threshold", 120)),
            int(getattr(self.settings, "capture_sustain", 0)),
            int(getattr(self.settings, "capture_cooldown", 30)),
        ):
            return
        from .history_window import session_key

        info = capture_screen(
            bpm,
            state=state,
            device=name or address,
            session=session_key(session),
            directory=str(getattr(self.settings, "capture_dir", "") or ""),
        )
        if info is None:
            self.window.append_log("高心率截屏失败：无法读取当前屏幕")
            return
        shots = self.settings.screenshot_events
        shots.append(info)
        # 只保留最近 200 张的索引，避免设置文件无限膨胀；图片本体仍保留在磁盘上。
        if len(shots) > 200:
            del shots[:-200]
        session.setdefault("screenshots", []).append(dict(info))
        self._save_settings()
        self.window.append_log(f"高心率截屏已保存：{bpm} BPM · {state} · {info['path']}")
        if self._history_window is not None:
            self._history_window.set_shots(list(shots))

    def _check_game(self) -> None:
        """轮询当前运行的游戏；进入/退出游戏时开始或结束一场游戏会话。"""
        if not self.settings.game_detect_enabled:
            return
        from .game import active_game, detect_games

        try:
            games = detect_games(self._game_extra)
        except Exception:
            games = []
        game = active_game(games)

        if game is None:
            if self._game_session is not None:
                self._finish_game_session()
            self.floating.set_game_info("")
            self._sync_game_visibility(False)
            return

        if self._game_pid != game.pid or self._game_name != game.display_name:
            # 切换了游戏：先结束上一场，再开始新的一场
            if self._game_session is not None:
                self._finish_game_session(sync_visibility=False)
            self._start_game_session(game)

        # 悬浮窗显示当前游戏与本次心率统计
        if self.settings.game_show_on_float and self._game_session is not None:
            series = self._game_session.get("series") or []
            vals = [int(x[1]) for x in series if isinstance(x, (list, tuple)) and len(x) >= 2]
            self.floating.set_game_info(
                game.display_name,
                bpm=vals[-1] if vals else None,
                low=min(vals) if vals else None,
                high=max(vals) if vals else None,
            )
        elif not self.settings.game_show_on_float:
            self.floating.set_game_info("")
        self._sync_game_visibility(True)

    def _start_game_session(self, game) -> None:
        self._game_pid = game.pid
        self._game_name = game.display_name
        self._game_session = {
            "address": f"game:{game.process}",
            "name": game.display_name,
            "game": game.display_name,
            "game_process": game.process,
            "game_icon": game.exe or "",
            "start": int(time.time()),
            "count": 0,
            "min": None,
            "max": None,
            "sum": 0.0,
            "last": None,
            "series": [],
            "state_events": [],
            "screenshots": [],
        }
        self.window.append_log(f"检测到正在运行：{game.display_name}，开始记录游戏心率")

    def _finish_game_session(self, sync_visibility: bool = True) -> None:
        if not self._game_session:
            self._game_pid = None
            self._game_name = ""
            return
        count = int(self._game_session.get("count") or 0)
        if count > 0 and self.settings.game_record_sessions:
            self._game_session["end"] = int(time.time())
            self._game_session["samples"] = count
            self._game_session["avg"] = round(
                float(self._game_session.get("sum") or 0.0) / count, 1
            )
            record = dict(self._game_session)
            record["state_events"] = [list(x) for x in (record.get("state_events") or [])]
            record["screenshots"] = [dict(x) for x in (record.get("screenshots") or [])]
            self._sessions.append(record)
            if len(self._sessions) > 50:
                self._sessions = self._sessions[-50:]
            self.window.set_sessions(list(self._sessions))
            self.settings.history_sessions = list(self._sessions)
            if self._history_window is not None:
                self._history_window.set_sessions(list(self._sessions))
            self.window.append_log(f"游戏结束：{self._game_name}，已保存本场心率记录")
        self.floating.set_game_info("")
        self._game_session = None
        self._game_pid = None
        self._game_name = ""
        if sync_visibility:
            self._sync_game_visibility(False)

    def _record_game_hr(self, bpm: int, state: str = "") -> None:
        """把一拍心率记入当前游戏会话，并记录状态变化。"""
        if self._game_session is None:
            return
        s = self._game_session
        if state:
            self._record_state_change(s, state, int(time.time()))
        s["count"] = int(s.get("count") or 0) + 1
        s["sum"] = float(s.get("sum") or 0) + bpm
        s["min"] = bpm if s.get("min") is None else min(int(s["min"]), bpm)
        s["max"] = bpm if s.get("max") is None else max(int(s["max"]), bpm)
        s["last"] = bpm
        series = s.setdefault("series", [])
        series.append([int(time.time()), int(bpm)])
        if len(series) > 200:
            del series[:-200]

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
