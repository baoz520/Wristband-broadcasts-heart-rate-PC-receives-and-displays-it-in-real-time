"""桌面置顶的实时心率悬浮窗。"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import ACCENT, BASE, MUTED, SHADOW_GREY, ZONE_COLORS
from .widgets import PulseHeart, RaisedButton, SoftCard, blurred_shape

STATE_TEXT = {
    "idle": "未连接",
    "connecting": "正在连接…",
    "reconnecting": "正在重连…",
    "connected": "已连接",
    "disconnected": "连接已断开",
    "error": "蓝牙不可用",
}


class FloatingWindow(QWidget):
    openMainRequested = Signal()
    hideRequested = Signal()
    quitRequested = Signal()
    lockChanged = Signal(bool)
    movedByUser = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("心率悬浮窗")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(268, 122)

        self._state = "idle"
        self._device = ""
        self._bpm: Optional[int] = None
        self._source = ""
        self._seconds_ago = -1
        self._locked = False
        self._dragging = False
        self._drag_offset = QPoint()
        self._address = ""
        self._history_mode = True
        self._history_by_device: dict[str, list[list[int]]] = {}
        # 外观自定义状态
        self._show_zone = True
        self._show_device = True
        # 当前游戏状态
        self._game_name = ""
        self._game_bpm: Optional[int] = None
        self._game_low: Optional[int] = None
        self._game_high: Optional[int] = None

        self._build_ui()

    # ------------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        self._panel = SoftCard(self, object_name="FloatPanel", radius=20.0)
        root.addWidget(self._panel)

        lay = QHBoxLayout(self._panel)
        lay.setContentsMargins(16, 12, 14, 12)
        lay.setSpacing(12)

        self._heart = PulseHeart(46, self._panel)
        lay.addWidget(self._heart, 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        lay.addLayout(col, 1)

        number_row = QHBoxLayout()
        number_row.setContentsMargins(0, 0, 0, 0)
        number_row.setSpacing(5)
        self._bpm_label = QLabel("--", self._panel)
        self._bpm_label.setStyleSheet(f"color: {MUTED};")
        f = QFont("Bahnschrift", 27)
        f.setWeight(QFont.Weight.DemiBold)
        self._bpm_label.setFont(f)
        self._bpm_label.setFixedHeight(38)
        number_row.addWidget(self._bpm_label, 0, Qt.AlignmentFlag.AlignBottom)

        unit = QLabel("BPM", self._panel)
        unit.setStyleSheet(f"color: {MUTED}; font-size: 9px; padding-bottom: 6px;")
        number_row.addWidget(unit, 0, Qt.AlignmentFlag.AlignBottom)
        number_row.addStretch(1)
        col.addLayout(number_row)

        self._meta = QLabel("未连接", self._panel)
        self._meta.setStyleSheet("color: #9aa8bb; font-size: 10px;")
        col.addWidget(self._meta)

        self._device_label = QLabel("打开主界面选择手环", self._panel)
        self._device_label.setStyleSheet("color: #5f6d80; font-size: 9px;")
        self._device_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        col.addWidget(self._device_label)

        self._close = RaisedButton("×", self)
        self._close.setFixedSize(20, 20)
        self._close.setToolTip("隐藏悬浮窗")
        self._close.clicked.connect(self.hideRequested.emit)
        self._close.move(self.width() - 34, 16)
        self._close.raise_()

    # ------------------------------------------------------------------ 数据
    def set_history_mode(self, enabled: bool) -> None:
        self._history_mode = bool(enabled)

    def set_device_history(self, address: str, samples: list) -> None:
        if not address:
            return
        self._history_by_device[address] = list(samples or [])
        self._refresh_meta()
        self.update()

    def _history_value(self) -> Optional[int]:
        if not self._history_mode:
            return None
        samples = self._history_by_device.get(self._address, []) if self._address else []
        if not samples:
            return None
        ts, bpm = samples[-1]
        self._bpm = bpm
        self._source = "历史"
        # 历史样本用 Unix 时间戳存储，这里直接用 wall clock 计算"多久之前"
        self._seconds_ago = max(0, int(time.time() - float(ts)))
        return bpm

    def set_hr(self, bpm: Optional[int], source: str = "", address: str = "", name: str = "") -> None:
        self._address = address or self._device
        if name:
            self._device = name
        history_bpm: Optional[int] = None
        if bpm is None:
            history_bpm = self._history_value()
            bpm = history_bpm
        self._bpm = bpm
        if bpm is None:
            self._source = ""
            self._seconds_ago = 0
        elif history_bpm is not None:
            self._source = "历史"
        else:
            self._source = source if source else "心率服务"
            self._seconds_ago = 0
        color = ACCENT
        self._bpm_label.setText(str(bpm) if bpm else "--")
        self._bpm_label.setStyleSheet(f"color: {color if bpm else MUTED};")
        self._heart.set_bpm(bpm or 0, color)
        self._refresh_meta()
        self.update()

    def set_link(self, state: str, address: str = "", name: str = "") -> None:
        self._state = state
        self._device = name or address
        if address:
            self._address = address
        self._refresh_meta()
        if state != "connected":
            if not self._history_mode:
                self._bpm = None
                self._source = ""
                self._heart.set_bpm(0)
                self._bpm_label.setText("--")
                self._bpm_label.setStyleSheet(f"color: {MUTED};")
            else:
                bpm = self._history_value()
                if bpm is None:
                    self._bpm = None
                    self._source = ""
                    self._heart.set_bpm(0)
                    self._bpm_label.setText("--")
                    self._bpm_label.setStyleSheet(f"color: {MUTED};")
        elif self._bpm is None:
            self.set_hr(None, self._source, self._address, self._device)
        self.setToolTip(f"{self._device}\n{address}" if address else self._device)

    def tick(self, seconds_since_data: int) -> None:
        self._seconds_ago = seconds_since_data
        self._refresh_meta()

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._close.setVisible(not locked)
        self.update()

    # ---------------------------------------------------------- 外观自定义
    def set_appearance(
        self,
        *,
        width: int | None = None,
        opacity: int | None = None,
        show_heart: bool | None = None,
        show_zone: bool | None = None,
        show_device: bool | None = None,
    ) -> None:
        """应用悬浮窗自定义设置，立即生效。"""
        if width is not None:
            width = max(220, min(420, int(width)))
            # 高度随宽度按比例变化，保持内容不挤压
            height = int(round(122 * width / 268))
            self.setFixedSize(width, height)
            self._close.move(self.width() - 34, 16)
        if opacity is not None:
            self.setWindowOpacity(max(0.4, min(1.0, int(opacity) / 100.0)))
        if show_heart is not None:
            self._heart.setVisible(bool(show_heart))
        if show_zone is not None:
            self._show_zone = bool(show_zone)
        if show_device is not None:
            self._device_label.setVisible(bool(show_device) or bool(self._game_name))
        self._refresh_meta()
        self.update()

    def set_game_info(self, game_name: str = "", bpm: int | None = None,
                      low: int | None = None, high: int | None = None) -> None:
        """悬浮窗展示当前正在运行的游戏与该场心率数据。

        游戏态下主数字切换成该场最新心率，区间行显示该场最低–最高，
        底部显示游戏名——这样一眼看到的就是"玩这款游戏时的心率"。
        """
        self._game_name = game_name or ""
        self._game_bpm = bpm
        self._game_low = low
        self._game_high = high
        # 游戏态下始终显示游戏名行，即使用户隐藏了设备名
        self._device_label.setVisible(bool(self._game_name) or self._show_device)
        if self._game_name:
            shown = self._game_bpm or self._bpm
            self._bpm_label.setText(str(shown) if shown else "--")
            self._bpm_label.setStyleSheet(f"color: {ACCENT if shown else MUTED};")
            self._heart.set_bpm(shown or 0, ACCENT)
        else:
            # 退出游戏态：恢复实时心率显示
            self._bpm_label.setText(str(self._bpm) if self._bpm else "--")
            self._bpm_label.setStyleSheet(
                f"color: {ACCENT if self._bpm else MUTED};"
            )
            self._heart.set_bpm(self._bpm or 0, ACCENT)
        self._refresh_meta()
        self.update()

    def _zone(self) -> str:
        if not self._bpm:
            return "静息"
        from .hr import heart_rate_zone

        return heart_rate_zone(self._bpm)

    def _refresh_meta(self) -> None:
        parts: list[str] = []
        if self._game_name:
            # 游戏态：区间行展示该场最低–最高心率
            if self._game_low is not None and self._game_high is not None:
                parts.append(f"本场 {self._game_low}–{self._game_high} BPM")
            else:
                parts.append("本场心率")
        elif self._bpm:
            if self._show_zone:
                parts.append(self._zone())
            if self._seconds_ago >= 0:
                if self._seconds_ago < 60:
                    parts.append(f"{self._seconds_ago} 秒前")
                else:
                    parts.append(f"{self._seconds_ago // 60} 分钟前")
        elif self._state == "connected":
            parts.append("等待心率数据")
        else:
            parts.append(STATE_TEXT.get(self._state, self._state))
        self._meta.setText(" · ".join(parts))
        zone = (
            self._zone()
            if self._bpm and self._show_zone and not self._game_name
            else ""
        )
        self._meta.setStyleSheet(
            f"color: {ZONE_COLORS.get(zone, MUTED)}; font-size: 10px;"
        )

        # 游戏态：底部只显示游戏名，保持清晰不截断
        if self._game_name:
            game_text = f"[游戏] {self._game_name}"
            if len(game_text) > 24:
                game_text = game_text[:23] + "…"
            self._device_label.setText(game_text)
            self._device_label.setStyleSheet("color: #6d5dfc; font-size: 9px;")
        else:
            name = self._device or "打开主界面选择手环"
            if self._source:
                name = f"{name} · {self._source}"
            if len(name) > 22:
                name = name[:21] + "…"
            self._device_label.setText(name)
            self._device_label.setStyleSheet("color: #5f6d80; font-size: 9px;")

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        # 与页面同一光源的柔和灰影，避免纯黑阴影破坏材质感
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pm, pad = blurred_shape(
            self.width() - 22, self.height() - 22, 20,
            4, 7, 12, SHADOW_GREY, 85,
        )
        p.drawPixmap(QPointF(11 - pad, 11 - pad), pm)
        p.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._close.move(self.width() - 34, 16)
        super().resizeEvent(event)

    # ------------------------------------------------------------------ 交互
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._locked:
            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._dragging = False
            self.movedByUser.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.openMainRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        act_open = menu.addAction("打开主界面")
        menu.addSeparator()
        act_lock = menu.addAction("锁定位置")
        act_lock.setCheckable(True)
        act_lock.setChecked(self._locked)
        act_hide = menu.addAction("隐藏悬浮窗")
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        chosen = menu.exec(event.globalPos())
        if chosen == act_open:
            self.openMainRequested.emit()
        elif chosen == act_hide:
            self.hideRequested.emit()
        elif chosen == act_lock:
            self.set_locked(act_lock.isChecked())
            self.lockChanged.emit(act_lock.isChecked())
        elif chosen == act_quit:
            self.quitRequested.emit()

    def show_near_corner(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 28, geo.top() + 96)

    def keep_on_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.move(40, 40)
            return
        geo = screen.availableGeometry()
        x = max(geo.left(), min(self.x(), geo.right() - self.width()))
        y = max(geo.top(), min(self.y(), geo.bottom() - self.height()))
        self.move(x, y)
