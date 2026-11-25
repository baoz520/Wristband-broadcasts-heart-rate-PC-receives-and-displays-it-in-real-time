"""桌面置顶的实时心率悬浮窗。"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import CHAMPAGNE, MOONLIGHT, ZONE_COLORS
from .widgets import BentoCard, PulseHeart, RaisedButton, animate_show

STATE_TEXT = {
    "idle": "未连接",
    "connecting": "正在连接…",
    "reconnecting": "正在重连…",
    "connected": "已连接",
    "disconnected": "连接已断开",
    "error": "蓝牙不可用",
}

# 游戏中"隐藏背景"模式下改用亮色文字，压在任意游戏画面上都看得清。
TEXT_ON_GAME = "#f8fafc"
TEXT_ON_GAME_MUTED = "#cbd5e1"

# 悬浮窗在游戏中的显示方式
GAME_FLOAT_NORMAL = "normal"          # 保持原样
GAME_FLOAT_TRANSPARENT = "transparent"  # 隐藏拟物底板，只留数据
GAME_FLOAT_HIDDEN = "hidden"           # 整窗自动隐藏


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
        self._game_float_mode = GAME_FLOAT_TRANSPARENT
        self._game_transparent = False

        self._build_ui()

    # ------------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        # 悬浮窗不要外阴影：玻璃面板本身已经足够，阴影只会弄脏桌面背景。
        self._panel = BentoCard(
            self, object_name="FloatPanel", radius=24.0, shadow=False
        )
        root.addWidget(self._panel)

        lay = QHBoxLayout(self._panel)
        lay.setContentsMargins(20, 14, 20, 14)
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
        self._bpm_label.setStyleSheet(f"color: {MOONLIGHT};")
        f = QFont("Bahnschrift", 27)
        f.setWeight(QFont.Weight.DemiBold)
        self._bpm_label.setFont(f)
        self._bpm_label.setFixedHeight(38)
        number_row.addWidget(self._bpm_label, 0, Qt.AlignmentFlag.AlignBottom)

        self._unit = QLabel("BPM", self._panel)
        self._unit.setStyleSheet(f"color: {MOONLIGHT}; font-size: 9px; padding-bottom: 6px;")
        number_row.addWidget(self._unit, 0, Qt.AlignmentFlag.AlignBottom)
        number_row.addStretch(1)
        col.addLayout(number_row)

        self._meta = QLabel("未连接", self._panel)
        self._meta.setStyleSheet(f"color: {MOONLIGHT}; font-size: 10px;")
        col.addWidget(self._meta)

        self._device_label = QLabel("打开主界面选择手环", self._panel)
        self._device_label.setStyleSheet(f"color: {MOONLIGHT}; font-size: 9px;")
        self._device_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        col.addWidget(self._device_label)

        # 游戏透明模式没有底板，用极轻的文字投影保证亮色数字在任何画面上可读。
        for widget in (
            self._heart, self._bpm_label, self._unit, self._meta, self._device_label
        ):
            shadow = QGraphicsDropShadowEffect(widget)
            shadow.setColor(QColor(0, 0, 0, 190))
            shadow.setBlurRadius(8)
            shadow.setOffset(0, 1)
            shadow.setEnabled(False)
            widget.setGraphicsEffect(shadow)

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
        color = self._number_color()
        muted = self._muted_color()
        self._bpm_label.setText(str(bpm) if bpm else "--")
        self._bpm_label.setStyleSheet(f"color: {color if bpm else muted};")
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
                self._bpm_label.setStyleSheet(f"color: {self._muted_color()};")
            else:
                bpm = self._history_value()
                if bpm is None:
                    self._bpm = None
                    self._source = ""
                    self._heart.set_bpm(0)
                    self._bpm_label.setText("--")
                    self._bpm_label.setStyleSheet(f"color: {self._muted_color()};")
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

    # ------------------------------------------------------ 游戏中显示方式
    def set_game_display_mode(self, mode: str) -> None:
        """设置游戏运行时悬浮窗的显示方式：normal / transparent / hidden。

        "hidden" 由 Controller 负责整窗隐藏；这里只处理
        "transparent"（隐藏拟物底板）与恢复。
        """
        self._game_float_mode = mode if mode in (
            GAME_FLOAT_NORMAL, GAME_FLOAT_TRANSPARENT, GAME_FLOAT_HIDDEN
        ) else GAME_FLOAT_NORMAL
        self._apply_game_display_mode()

    def _apply_game_display_mode(self) -> None:
        transparent = bool(
            self._game_name and self._game_float_mode == GAME_FLOAT_TRANSPARENT
        )
        self._game_transparent = transparent
        self._panel.set_transparent(transparent)
        for widget in (
            self._heart, self._bpm_label, self._unit, self._meta, self._device_label
        ):
            effect = widget.graphicsEffect()
            if isinstance(effect, QGraphicsDropShadowEffect):
                effect.setEnabled(transparent)
        self._unit.setStyleSheet(
            f"color: {self._muted_color()}; font-size: 9px; padding-bottom: 6px;"
        )
        self._refresh_meta()
        self.update()

    def _number_color(self) -> str:
        # 游戏透明模式用亮白压在任意画面上；平时关键数字用香槟金
        return TEXT_ON_GAME if self._game_transparent else CHAMPAGNE

    def _muted_color(self) -> str:
        return TEXT_ON_GAME_MUTED if self._game_transparent else MOONLIGHT

    def set_game_info(self, game_name: str = "", bpm: int | None = None,
                      low: int | None = None, high: int | None = None) -> None:
        """悬浮窗展示当前正在运行的游戏与该场心率数据。

        游戏态下主数字切换成该场最新心率，区间行显示该场最低–最高，
        底部显示游戏名——这样一眼看到的就是"玩这款游戏时的心率"。
        """
        name_changed = self._game_name != (game_name or "")
        self._game_name = game_name or ""
        self._game_bpm = bpm
        self._game_low = low
        self._game_high = high
        if name_changed:
            self._apply_game_display_mode()
        # 游戏态下始终显示游戏名行，即使用户隐藏了设备名
        self._device_label.setVisible(bool(self._game_name) or self._show_device)
        number = self._number_color()
        muted = self._muted_color()
        if self._game_name:
            shown = self._game_bpm or self._bpm
            self._bpm_label.setText(str(shown) if shown else "--")
            self._bpm_label.setStyleSheet(f"color: {number if shown else muted};")
            self._heart.set_bpm(shown or 0, number)
        else:
            # 退出游戏态：恢复实时心率显示
            self._bpm_label.setText(str(self._bpm) if self._bpm else "--")
            self._bpm_label.setStyleSheet(
                f"color: {number if self._bpm else muted};"
            )
            self._heart.set_bpm(self._bpm or 0, number)
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
        meta_color = (
            TEXT_ON_GAME_MUTED if self._game_transparent
            else ZONE_COLORS.get(zone, MOONLIGHT)
        )
        self._meta.setStyleSheet(f"color: {meta_color}; font-size: 10px;")

        # 游戏态：底部只显示游戏名，保持清晰不截断
        if self._game_name:
            game_text = f"[游戏] {self._game_name}"
            if len(game_text) > 24:
                game_text = game_text[:23] + "…"
            self._device_label.setText(game_text)
            game_color = TEXT_ON_GAME_MUTED if self._game_transparent else MOONLIGHT
            self._device_label.setStyleSheet(f"color: {game_color}; font-size: 9px;")
        else:
            name = self._device or "打开主界面选择手环"
            if self._source:
                name = f"{name} · {self._source}"
            if len(name) > 22:
                name = name[:21] + "…"
            self._device_label.setText(name)
            name_color = (
                TEXT_ON_GAME_MUTED if self._game_transparent else MOONLIGHT
            )
            self._device_label.setStyleSheet(f"color: {name_color}; font-size: 9px;")

    # ------------------------------------------------------------------ 绘制
    # 外阴影由 BentoCard 自己绘制，避免窗口级再叠一层造成双阴影。

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, lambda: animate_show(self, 220))

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
