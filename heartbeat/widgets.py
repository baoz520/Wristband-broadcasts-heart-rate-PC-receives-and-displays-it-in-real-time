"""自绘控件：开关、心形、走势图、信号强度、状态胶囊。"""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QAbstractButton, QLabel, QSizePolicy, QWidget

from .theme import ACCENT, MUTED, TEXT, ZONE_COLORS


def heart_path(rect: QRectF) -> QPainterPath:
    """在给定矩形内构造一个心形路径。"""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    path = QPainterPath()
    path.moveTo(x + w / 2, y + h * 0.95)
    path.cubicTo(
        x - w * 0.16, y + h * 0.56,
        x + w * 0.07, y + h * 0.02,
        x + w / 2, y + h * 0.30,
    )
    path.cubicTo(
        x + w * 0.93, y + h * 0.02,
        x + w * 1.16, y + h * 0.56,
        x + w / 2, y + h * 0.95,
    )
    path.closeSubpath()
    return path


def make_heart_pixmap(size: int = 64, on_dark: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if on_dark:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#151b25"))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    inset = size * 0.17
    p.drawPath(heart_path(QRectF(inset, inset * 1.05, size - inset * 2, size - inset * 2.1)))
    p.end()
    return pm


def make_app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_heart_pixmap(s, on_dark=True))
    return icon


class ToggleSwitch(QAbstractButton):
    """iOS 风格开关，带滑动动画。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 28)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        if not self.isVisible():
            self._anim.stop()
            self._offset = 1.0 if checked else 0.0
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(48, 28)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = rect.height() / 2

        off = QColor("#2a3442")
        on = QColor(ACCENT)
        t = self._offset
        track = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
        )
        if not self.isEnabled():
            track.setAlpha(90)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, radius, radius)

        knob_d = rect.height() - 6
        x = rect.x() + 3 + (rect.width() - knob_d - 6) * t
        knob = QRectF(x, rect.y() + 3, knob_d, knob_d)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(knob.translated(0, 1))
        p.setBrush(QColor("#ffffff") if self.isEnabled() else QColor("#9aa6b5"))
        p.drawEllipse(knob)
        p.end()


class PulseHeart(QWidget):
    """跟着 bpm 跳动的心形。"""

    def __init__(self, size: int = 46, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(ACCENT)
        self._bpm = 0
        self._phase = 0.0
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._beat)
        self._anim = QPropertyAnimation(self, b"phase", self)
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim.finished.connect(lambda: self._set_phase(0.0))

    def _get_phase(self) -> float:
        return self._phase

    def _set_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    phase = Property(float, _get_phase, _set_phase)

    def set_bpm(self, bpm: int, color: str | None = None) -> None:
        if color:
            self._color = QColor(color)
        if bpm <= 0:
            if self._bpm > 0:
                self._bpm = 0
                self._timer.stop()
                self._anim.stop()
                self._set_phase(0.0)
            self.update()
            return
        self._bpm = bpm
        self._timer.start(self._interval())
        self.update()

    def _interval(self) -> int:
        return max(300, min(1600, int(60000 / max(1, self._bpm))))

    def _beat(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()
        if self._bpm > 0:
            self._timer.start(self._interval())

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) * 0.42
        scale = 1.0 + 0.16 * self._phase
        rect = QRectF(
            self.width() / 2 - side * scale,
            self.height() / 2 - side * scale * 1.05,
            side * 2 * scale,
            side * 2 * scale,
        )
        if self._bpm <= 0:
            p.setBrush(QColor("#232d3b"))
        else:
            glow = QColor(self._color)
            glow.setAlpha(int(26 + 60 * self._phase))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawPath(heart_path(rect.adjusted(-5, -5, 5, 5)))
            p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(heart_path(rect))
        p.end()


class Sparkline(QWidget):
    """最近 60 秒的心率折线图。"""

    WINDOW_SECONDS = 60

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._points: deque[tuple[float, int]] = deque()
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add(self, bpm: int, ts: float | None = None) -> None:
        now = time.monotonic() if ts is None else ts
        self._points.append((now, bpm))
        self._prune(now)
        self.update()

    def clear(self) -> None:
        self._points.clear()
        self.update()

    def _prune(self, now: float) -> None:
        cutoff = now - self.WINDOW_SECONDS - 4
        while self._points and self._points[0][0] < cutoff:
            self._points.popleft()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        self._prune(now)

        left, right, top, bottom = 2.0, self.width() - 2.0, 8.0, self.height() - 18.0
        plot = QRectF(left, top, max(1.0, right - left), max(1.0, bottom - top))

        # 基线网格
        grid_pen = QPen(QColor("#1d2735"), 1)
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(grid_pen)
        for i in range(3):
            y = plot.top() + plot.height() * (i + 1) / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        vals = [v for _, v in self._points]
        if len(vals) < 2:
            p.setPen(QColor("#4a5769"))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, "等待心率数据…")
            p.end()
            return

        lo = min(vals)
        hi = max(vals)
        lo = min(lo, 60) - 6
        hi = max(hi, 110) + 6
        if hi - lo < 40:
            pad = (40 - (hi - lo)) / 2
            lo -= pad
            hi += pad

        def y_of(v: float) -> float:
            return plot.bottom() - (v - lo) / (hi - lo) * plot.height()

        pts: list[QPointF] = []
        for ts, v in self._points:
            x = plot.right() - (now - ts) / self.WINDOW_SECONDS * plot.width()
            x = max(plot.left(), x)
            pts.append(QPointF(x, y_of(v)))

        fill = QPainterPath()
        fill.moveTo(pts[0].x(), plot.bottom())
        for pt in pts:
            fill.lineTo(pt)
        fill.lineTo(pts[-1].x(), plot.bottom())
        fill.closeSubpath()
        grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
        grad.setColorAt(0.0, QColor(255, 77, 109, 76))
        grad.setColorAt(1.0, QColor(255, 77, 109, 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(fill)

        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        pen = QPen(QColor(ACCENT), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)

        last = pts[-1]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 77, 109, 55))
        p.drawEllipse(last, 6.0, 6.0)
        p.setBrush(QColor(ACCENT))
        p.drawEllipse(last, 3.1, 3.1)

        p.setPen(QColor("#5a687c"))
        p.setFont(QFont("Microsoft YaHei UI", 8))
        p.drawText(QPointF(plot.left(), self.height() - 3), "−60 秒")
        p.drawText(
            QRectF(plot.center().x() - 40, self.height() - 14, 80, 12),
            Qt.AlignmentFlag.AlignHCenter,
            "30 秒",
        )
        p.drawText(
            QRectF(plot.right() - 40, self.height() - 14, 40, 12),
            Qt.AlignmentFlag.AlignRight,
            "现在",
        )
        p.end()


class SignalBars(QWidget):
    """四格信号强度。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._level = 0
        self.setFixedSize(20, 16)

    def set_rssi(self, rssi: int | None) -> None:
        if rssi is None or rssi <= -100:
            level = 0
        elif rssi >= -55:
            level = 4
        elif rssi >= -67:
            level = 3
        elif rssi >= -78:
            level = 2
        else:
            level = 1
        if level != self._level:
            self._level = level
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        bar_w = 3.0
        gap = 2.0
        for i in range(4):
            h = 4 + i * 3.2
            x = i * (bar_w + gap)
            y = 16 - h
            color = QColor(ACCENT if i < self._level else "#2b3545")
            if i < self._level:
                color.setAlpha(230)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y, bar_w, h), 1.4, 1.4)
        p.end()


class StatusPill(QLabel):
    STATE_STYLES = {
        "idle": ("#26303f", "#a9b6c7"),
        "connecting": ("rgba(251, 191, 36, 0.14)", "#fbbf24"),
        "reconnecting": ("rgba(251, 191, 36, 0.14)", "#fbbf24"),
        "connected": ("rgba(52, 211, 153, 0.14)", "#34d399"),
        "broadcasting": ("rgba(90, 169, 255, 0.14)", "#5aa9ff"),
        "disconnected": ("rgba(248, 113, 113, 0.14)", "#f87171"),
        "error": ("rgba(248, 113, 113, 0.14)", "#f87171"),
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Pill")
        self.set_state("idle", "未连接")

    def set_state(self, state: str, text: str) -> None:
        bg, fg = self.STATE_STYLES.get(state, self.STATE_STYLES["idle"])
        self.setStyleSheet(f"background: {bg}; color: {fg};")
        self.setText(f"●  {text}")


class ZoneBadge(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Pill")
        self.set_zone(None)

    def set_zone(self, zone: str | None) -> None:
        if not zone:
            self.setStyleSheet("background: #222c3a; color: #8190a4;")
            self.setText("等待数据")
            return
        color = ZONE_COLORS.get(zone, MUTED)
        self.setStyleSheet(f"background: rgba(255,255,255,0.055); color: {color};")
        self.setText(f"●  {zone}")


class BrandMark(QWidget):
    """标题旁边的渐变小方块 + 心形。"""

    def __init__(self, size: int = 44, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._pix = make_heart_pixmap(size // 2)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor("#311a26"))
        grad.setColorAt(1, QColor("#17202c"))
        p.setPen(QPen(QColor("#3b2836"), 1))
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 13, 13)
        p.drawPixmap(
            (self.width() - self._pix.width()) // 2,
            (self.height() - self._pix.height()) // 2,
            self._pix,
        )
        p.end()
