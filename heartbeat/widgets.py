"""自绘控件：便当盒卡片、网格、按钮、开关、心形、走势图与状态胶囊。

材质规则（与便当盒规范一致）：
- Snow `#fafafa` 画布上浮白卡，层级由卡片尺寸而非颜色承担。
- 卡片 24px 圆角、1px 极浅描边、几乎不可见的软投影；hover 上浮并放大 1%。
- 小控件沿用缓存高斯模糊阴影基元，但色值已收敛到浅色便当盒色板。
"""

from __future__ import annotations

import time
from collections import deque
from functools import lru_cache

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
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsScene,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    ACCENT,
    BASE,
    BENTO_BORDER,
    BENTO_CARD,
    BENTO_EDGE,
    BENTO_INK,
    BENTO_SNOW,
    BENTO_SKY,
    BENTO_VIOLET,
    BLURPLE,
    CORAL,
    HIGHLIGHT,
    INK,
    MUTED,
    SHADOW_GREY,
    ZONE_COLORS,
)

# ---------------------------------------------------------------- 阴影基元
# CSS 的 8px 8px 16px 阴影在 Qt 里没有直接的样式表写法，这里用缓存的
# 高斯模糊像素图复刻，保证所有控件使用同一套光源与模糊值。


def rgba(color: str, alpha: int) -> QColor:
    """从 hex 色值构造带透明度的颜色（兼容各版本 PySide6）。"""
    c = QColor(color)
    c.setAlpha(max(0, min(255, int(alpha))))
    return c


@lru_cache(maxsize=160)
def blurred_shape(
    w: int, h: int, radius: int, ox: int, oy: int, blur: int, color: str, alpha: int,
    hollow: bool = False,
):
    """返回 (模糊后的圆角矩形像素图, 四周留白)，供外阴影使用。

    hollow=True 时只保留轮廓带再模糊，避免实心偏移阴影在圆角处露出亮块。
    """
    w, h = max(1, int(w)), max(1, int(h))
    pad = int(blur * 2.6 + max(abs(ox), abs(oy))) + 6
    pm = QPixmap(w + pad * 2, h + pad * 2)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    c.setAlpha(max(0, min(255, alpha)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(c)
    painter.drawRoundedRect(QRectF(pad + ox, pad + oy, w, h), radius, radius)

    if hollow:
        band = max(4.0, blur / 2.0)
        iw, ih = w - band * 2, h - band * 2
        if iw > 0 and ih > 0:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.drawRoundedRect(
                QRectF(pad + ox + band, pad + oy + band, iw, ih),
                max(0.0, radius - band), max(0.0, radius - band),
            )
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.end()

    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(0, 0, pm.width(), pm.height()))
    item = scene.addPixmap(pm)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(max(0.5, float(blur)))
    item.setGraphicsEffect(effect)

    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    target = QPainter(out)
    scene.render(target)
    target.end()
    return out, pad


def mix_color(a: str, b: str, t: float) -> QColor:
    """在两个 hex 颜色间线性插值，用于悬停过渡。"""
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, float(t)))
    return QColor(
        int(ca.red() + (cb.red() - ca.red()) * t),
        int(ca.green() + (cb.green() - ca.green()) * t),
        int(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


def draw_raised(
    painter: QPainter,
    rect: QRectF,
    radius: float,
    *,
    distance: float = 8.0,
    blur: float = 16.0,
    grey_alpha: int = 138,
    white_alpha: int = 182,
    rim: bool = False,
) -> None:
    """凸起：右下冷灰暗影 + 左上高光，最后铺同色基底。"""
    d, b = int(round(distance)), int(round(blur))
    r = int(round(radius))
    w, h = int(round(rect.width())), int(round(rect.height()))
    grey, pad_g = blurred_shape(w, h, r, d, d, b, SHADOW_GREY, grey_alpha, hollow=True)
    white, pad_w = blurred_shape(w, h, r, -d, -d, b, HIGHLIGHT, white_alpha, hollow=True)

    # 阴影只画在圆角轮廓之外，避免高光从圆角切口漏进卡片里形成白色楔形
    margin = max(pad_g, pad_w) + 4
    outer = QPainterPath()
    outer.addRect(rect.adjusted(-margin, -margin, margin, margin))
    surface = QPainterPath()
    surface.addRoundedRect(rect, radius, radius)
    painter.save()
    painter.setClipPath(outer.subtracted(surface))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPixmap(QPointF(rect.x() - pad_g, rect.y() - pad_g), grey)
    painter.drawPixmap(QPointF(rect.x() - pad_w, rect.y() - pad_w), white)
    painter.restore()

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BASE))
    painter.drawRoundedRect(rect, radius, radius)

    # 极淡的同色系描边：新拟物没有实色边框，这层 ultra-light 边缘只补足
    # 卡片与背景之间的轮廓，让"界面边框"可辨又不破坏同色材质。
    if rim:
        edge = QPen(rgba(SHADOW_GREY, 58), 1.0)
        painter.setPen(edge)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


def draw_recessed(painter: QPainter, rect: QRectF, radius: float, *, depth: float = 9.0) -> None:
    """凹陷：沿内缘的左上暗影 + 右下高光，元素本身仍是基底色。"""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BASE))
    painter.drawPath(path)

    painter.save()
    painter.setClipPath(path)
    band = max(4.0, min(depth * 2.4, rect.width() / 2.0, rect.height() / 2.0))
    l, t, rgt, btm = rect.left(), rect.top(), rect.right(), rect.bottom()

    g1 = QLinearGradient(l, t, l, t + band)
    g1.setColorAt(0.0, rgba(SHADOW_GREY, 165))
    g1.setColorAt(1.0, rgba(SHADOW_GREY, 0))
    painter.fillRect(QRectF(l, t, rect.width(), band), QBrush(g1))

    g2 = QLinearGradient(l, t, l + band, t)
    g2.setColorAt(0.0, rgba(SHADOW_GREY, 140))
    g2.setColorAt(1.0, rgba(SHADOW_GREY, 0))
    painter.fillRect(QRectF(l, t, band, rect.height()), QBrush(g2))

    g3 = QLinearGradient(rgt, btm, rgt, btm - band)
    g3.setColorAt(0.0, rgba(HIGHLIGHT, 215))
    g3.setColorAt(1.0, rgba(HIGHLIGHT, 0))
    painter.fillRect(QRectF(l, btm - band, rect.width(), band), QBrush(g3))

    g4 = QLinearGradient(rgt, btm, rgt - band, btm)
    g4.setColorAt(0.0, rgba(HIGHLIGHT, 195))
    g4.setColorAt(1.0, rgba(HIGHLIGHT, 0))
    painter.fillRect(QRectF(rgt - band, t, band, rect.height()), QBrush(g4))
    painter.restore()


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
    bg = QColor("#151b25") if on_dark else QColor(BASE)
    ink = QColor(ACCENT) if on_dark else QColor(INK)
    if on_dark:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    p.setBrush(ink)
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


class HoverAnimator:
    """给 QWidget 子类提供可动画的 hover 进度（0→1）。

    用法：子类声明 ``hover = Property(float, HoverAnimator._get, HoverAnimator._set)``，
    在构造里调用 ``HoverAnimator.setup(self)``，enterEvent/leaveEvent 调用
    ``fade(1.0/0.0)``，paintEvent 读取 ``self.hover`` 做插值。
    """

    DURATION = 180

    @staticmethod
    def setup(owner) -> None:
        owner._hover_value = 0.0
        owner._hover_anim = QPropertyAnimation(owner, b"hover", owner)
        owner._hover_anim.setDuration(HoverAnimator.DURATION)
        owner._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    @staticmethod
    def _get(owner) -> float:
        return getattr(owner, "_hover_value", 0.0)

    @staticmethod
    def _set(owner, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value != getattr(owner, "_hover_value", 0.0):
            owner._hover_value = value
            owner.update()

    @staticmethod
    def fade(owner, target: float) -> None:
        anim = getattr(owner, "_hover_anim", None)
        if anim is None:
            return
        anim.stop()
        anim.setStartValue(HoverAnimator._get(owner))
        anim.setEndValue(max(0.0, min(1.0, float(target))))
        anim.start()


class ToggleSwitch(QAbstractButton):
    """便当盒开关：浅灰轨道 + 白色旋钮，开启填 Sky。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 32)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        HoverAnimator.setup(self)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)
    hover = Property(float, HoverAnimator._get, HoverAnimator._set)

    def enterEvent(self, event) -> None:
        HoverAnimator.fade(self, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        HoverAnimator.fade(self, 0.0)
        super().leaveEvent(event)

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
        return QSize(48, 32)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            p.end()
            return
        radius = min(h / 2.0, 16.0)
        t = self._offset
        on = self.isChecked()
        knob = 24.0
        x = 3.0 + (w - 6.0 - knob) * t
        y = (h - knob) / 2.0

        hv = self.hover
        track = QRectF(0, 0, w, h)
        draw_recessed(p, track, radius, depth=5 + 2 * hv)

        knob_rect = QRectF(x, y, knob, knob)
        draw_raised(
            p, knob_rect, knob / 2.0,
            distance=3.0 + 1.5 * hv, blur=6.0 + 2 * hv,
            grey_alpha=int(95 + 55 * hv), white_alpha=int(190 + 40 * hv),
        )
        fill_color = QColor(BLURPLE) if (on and self.isEnabled()) else QColor(BASE)
        if not self.isEnabled():
            fill_color = QColor("#c3ccd9")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill_color)
        p.drawRoundedRect(knob_rect.adjusted(3, 3, -3, -3), (knob - 6) / 2.0, (knob - 6) / 2.0)
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
            p.setBrush(QColor("#b9c2d0"))
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
    """心率折线图：实时模式显示最近 60 秒；历史模式按索引绘制完整历史。"""

    WINDOW_SECONDS = 60

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._points: deque[tuple[float, int]] = deque()
        self._history_mode = False
        self._axis_labels: tuple[str, str, str] = ("−60 秒", "30 秒", "现在")
        self._dark = False
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_dark(self, dark: bool) -> None:
        """在墨黑锚点卡里改用亮色网格与曲线。"""
        self._dark = bool(dark)
        self.update()

    def add(self, bpm: int, ts: float | None = None) -> None:
        """实时追加一个样本，保持最近 60 秒窗口。"""
        self._history_mode = False
        now = time.monotonic() if ts is None else ts
        self._points.append((now, bpm))
        self._prune(now)
        self.update()

    def set_series(self, samples: list[tuple[float, int]]) -> None:
        """兼容旧接口：作为实时序列设置，按 60 秒窗口过滤。"""
        self._history_mode = False
        self._points.clear()
        now = time.monotonic()
        for ts, bpm in samples:
            if now - ts > self.WINDOW_SECONDS + 4:
                continue
            self._points.append((ts, bpm))
        self.update()

    def set_history(
        self,
        samples: list[tuple[float, int]],
        labels: tuple[str, str, str] | None = None,
    ) -> None:
        """历史模式：保留全部样本，X 轴按索引均匀分布（不受 60 秒窗口限制）。"""
        self._history_mode = True
        self._points = deque(samples)
        self._axis_labels = labels or ("最早", "历史心率", "最新")
        self.update()

    def clear(self) -> None:
        self._points.clear()
        self.update()

    def _prune(self, now: float) -> None:
        if self._history_mode:
            return
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

        grid_pen = QPen(
            rgba("#ffffff", 34) if self._dark else rgba(SHADOW_GREY, 90), 1
        )
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(grid_pen)
        for i in range(3):
            y = plot.top() + plot.height() * (i + 1) / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        vals = [v for _, v in self._points]
        if len(vals) < 2:
            p.setPen(QColor("#cbd5e1" if self._dark else MUTED))
            p.setFont(QFont("Inter", 9))
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
        n = len(self._points)
        if self._history_mode:
            # 历史模式：样本按保存顺序均匀铺满绘图区，与真实时间跨度无关。
            # 这样几小时前甚至几天前的历史也能完整显示。
            span = max(1, n - 1)
            for i, (_ts, v) in enumerate(self._points):
                x = plot.left() + i / span * plot.width()
                pts.append(QPointF(x, y_of(v)))
        else:
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
        fill_color = BENTO_SKY if self._dark else BLURPLE
        grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
        grad.setColorAt(0.0, rgba(fill_color, 70 if self._dark else 40))
        grad.setColorAt(1.0, rgba(fill_color, 6 if self._dark else 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(fill)

        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        pen = QPen(QColor(BENTO_SKY if self._dark else ACCENT), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)

        last = pts[-1]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rgba(fill_color, 90))
        p.drawEllipse(last, 6.0, 6.0)
        p.setBrush(QColor(BENTO_SKY if self._dark else ACCENT))
        p.drawEllipse(last, 3.1, 3.1)

        p.setPen(QColor("#cbd5e1" if self._dark else MUTED))
        p.setFont(QFont("Inter", 8))
        left_label, mid_label, right_label = self._axis_labels
        p.drawText(QPointF(plot.left(), self.height() - 3), left_label)
        p.drawText(
            QRectF(plot.center().x() - 60, self.height() - 14, 120, 12),
            Qt.AlignmentFlag.AlignHCenter,
            mid_label,
        )
        p.drawText(
            QRectF(plot.right() - 60, self.height() - 14, 60, 12),
            Qt.AlignmentFlag.AlignRight,
            right_label,
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
            color = QColor(ACCENT if i < self._level else "#c3ccd9")
            if i < self._level:
                color.setAlpha(230)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y, bar_w, h), 1.4, 1.4)
        p.end()


class SoftPill(QLabel):
    """凹陷胶囊：底色与页面一致，只用 inset 阴影和文字颜色表达状态。"""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self._tone = MUTED
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_tone(self, color: str) -> None:
        if self._tone != color:
            self._tone = color
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            p.end()
            return
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        draw_recessed(p, rect, rect.height() / 2.0, depth=4)
        f = QFont(self.font())
        f.setPointSize(9)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(QColor(self._tone))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class StatusPill(SoftPill):
    STATE_TONES = {
        "idle": MUTED,
        "connecting": "#c08a12",
        "reconnecting": "#c08a12",
        "connected": "#1f9d78",
        "broadcasting": BLURPLE,
        "disconnected": "#dd4a4a",
        "error": "#dd4a4a",
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.set_state("idle", "未连接")

    def set_state(self, state: str, text: str) -> None:
        self.set_tone(self.STATE_TONES.get(state, MUTED))
        self.setText(f"●  {text}")


class ZoneBadge(SoftPill):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.set_zone(None)

    def set_zone(self, zone: str | None) -> None:
        if not zone:
            self.set_tone(MUTED)
            self.setText("等待数据")
            return
        self.set_tone(ZONE_COLORS.get(zone, MUTED))
        self.setText(f"●  {zone}")


class BrandMark(QWidget):
    """标题旁边的同色小方块 + 心形。"""

    def __init__(self, size: int = 44, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._pix = make_heart_pixmap(size // 2)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        draw_raised(p, rect, 13.0, distance=3.0, blur=6.0, grey_alpha=80, white_alpha=190)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BASE))
        p.drawRoundedRect(rect, 13, 13)
        p.drawPixmap(
            (self.width() - self._pix.width()) // 2,
            (self.height() - self._pix.height()) // 2,
            self._pix,
        )
        p.end()


class RaisedButton(QPushButton):
    """便当盒按钮：12px 圆角，主操作墨黑填充，危险操作橙红填充，次要白底浅描边。"""

    hover = Property(float, HoverAnimator._get, HoverAnimator._set)

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pressed = False
        HoverAnimator.setup(self)

    def enterEvent(self, event) -> None:
        HoverAnimator.fade(self, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        HoverAnimator.fade(self, 0.0)
        self._pressed = False
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        # 必须交给 QAbstractButton，否则 clicked 信号不会发出
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            p.end()
            return
        # 便当盒按钮统一 12px 圆角，按下轻微收缩（等效 CSS scale .95）
        r = min(12.0, w / 2.0, h / 2.0)
        pressed = self._pressed or (self.isDown() and self.isEnabled())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        if pressed:
            rect = rect.adjusted(1.5, 1.5, -1.5, -1.5)
        hv = self.hover if self.isEnabled() else 0.0

        danger = bool(self.property("danger"))
        accent = bool(self.property("accent"))
        action = bool(self.property("action"))
        solid = danger or accent or action
        if not self.isEnabled():
            p.setPen(QPen(QColor(BENTO_EDGE), 1.0))
            p.setBrush(QColor(BENTO_SNOW if solid else BENTO_CARD))
        elif solid:
            p.setPen(Qt.PenStyle.NoPen)
            if danger:
                fill = mix_color(CORAL, "#ea580c", hv)
            elif accent:
                fill = mix_color(BENTO_SKY, "#2563eb", hv)
            else:
                fill = mix_color(BENTO_INK, "#3f3f46", hv)
            p.setBrush(fill)
        else:
            # 次要按钮：白底 + 可辨识描边与软影，和卡片边界语言保持一致
            shadow, spad = blurred_shape(
                max(1, w - 2), max(1, h - 2), int(r),
                0, int(3 + 2 * hv), int(8 + 6 * hv), "#000000", int(10 + 10 * hv),
                hollow=True,
            )
            p.drawPixmap(QPointF(rect.x() - spad + 1, rect.y() - spad + 1), shadow)
            p.setPen(QPen(QColor(BENTO_EDGE), 1.0))
            p.setBrush(QColor(BENTO_SNOW if hv > 0.5 else BENTO_CARD))
        p.drawRoundedRect(rect, r, r)

        if self.hasFocus() and self.focusPolicy() != Qt.FocusPolicy.NoFocus:
            p.setPen(QPen(QColor(BENTO_SKY), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), max(0.0, r - 2), max(0.0, r - 2))

        if not self.isEnabled():
            tone = QColor("#a1a1aa")
        elif solid:
            tone = QColor("#ffffff")
        else:
            tone = QColor(BENTO_INK)
        f = QFont(self.font())
        f.setPointSize(13)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(tone)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class SoftCheckBox(QAbstractButton):
    """便当盒勾选框：浅灰圆角槽 + Sky 勾，键盘焦点可见。"""

    hover = Property(float, HoverAnimator._get, HoverAnimator._set)

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(30)
        HoverAnimator.setup(self)

    def sizeHint(self) -> QSize:
        width = QFontMetrics(self.font()).horizontalAdvance(self.text())
        return QSize(28 + width + 8, 30)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def enterEvent(self, event) -> None:
        HoverAnimator.fade(self, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        HoverAnimator.fade(self, 0.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(0.0, (self.height() - 20.0) / 2.0, 20.0, 20.0)
        draw_recessed(p, box, 7.0, depth=4 + 2 * self.hover)
        if self.isChecked():
            mark = QPainterPath()
            mark.moveTo(box.left() + 5.0, box.center().y() + 0.5)
            mark.lineTo(box.left() + 8.5, box.bottom() - 5.0)
            mark.lineTo(box.right() - 4.5, box.top() + 5.0)
            pen = QPen(QColor(BLURPLE), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(mark)
        f = QFont(self.font())
        f.setPointSize(12)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(mix_color(INK, BLURPLE, self.hover))
        p.drawText(
            QRectF(28.0, 0, max(0.0, self.width() - 28.0), self.height()),
            Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
        if self.hasFocus():
            p.setPen(QPen(QColor(BLURPLE), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box.adjusted(-3, -3, 3, 3), 9, 9)
        p.end()


class SoftCard(QFrame):
    """软卡片基类：24px 圆角、柔和投影与 hover 属性，供 BentoCard 复用。"""

    hover = Property(float, HoverAnimator._get, HoverAnimator._set)

    def __init__(
        self,
        parent: QWidget | None = None,
        object_name: str = "SoftCard",
        radius: float = 24.0,
    ):
        super().__init__(parent)
        self._radius = float(radius)
        self._transparent = False
        self.setObjectName(object_name)
        HoverAnimator.setup(self)

    def set_transparent(self, transparent: bool) -> None:
        """隐藏新拟物底板（游戏中悬浮窗用），只保留一层极淡的底色保证文字可读。"""
        transparent = bool(transparent)
        if self._transparent == transparent:
            return
        self._transparent = transparent
        self.update()

    def enterEvent(self, event) -> None:
        HoverAnimator.fade(self, 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        HoverAnimator.fade(self, 0.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            p.end()
            return
        if self._transparent:
            # "隐藏背景"模式：清掉之前绘制的拟物底板，仅留几乎不可见的暗色蒙版，
            # 让心率数字悬在画面上，同时避免浅色文字与明亮游戏画面糊在一起。
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(self.rect(), Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rgba("#0b1220", 42))
            p.drawRoundedRect(
                QRectF(0, 0, w, h), min(self._radius, w / 2.0, h / 2.0),
                min(self._radius, w / 2.0, h / 2.0),
            )
            p.end()
            return
        r = min(self._radius, w / 2.0, h / 2.0)
        hv = self.hover
        # hover：模糊减半 + 2px 上浮，与规范一致
        rect = QRectF(0, -2.0 * hv, w, h)
        draw_raised(
            p, rect, r,
            distance=8.0 - 4.0 * hv,
            blur=16.0 - 8.0 * hv,
            grey_alpha=int(138 + 24 * hv),
            white_alpha=int(182 + 20 * hv),
            rim=True,
        )
        p.end()


class BentoCard(SoftCard):
    """便当盒网格中的卡片：白底 / 墨黑渐变锚点、24px 圆角、极浅描边。

    与基类 SoftCard 的区别：不使用同色材质阴影，而是白卡浮在 Snow 画布上；
    hover 300ms 内上浮 4px、放大 1%、阴影由 2% 扩到 8%。尺寸本身承担层级，
    颜色只用于唯一一张锚点卡。
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        object_name: str = "BentoCard",
        radius: float = 24.0,
        anchor: bool | str = False,
    ):
        super().__init__(parent, object_name=object_name, radius=radius)
        self._anchor = anchor
        # 便当盒规范：300ms ease-out（HoverAnimator 默认是 180ms）
        self._hover_anim.setDuration(300)

    @property
    def is_anchor(self) -> bool:
        return bool(self._anchor)

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._transparent:
            # 兼容悬浮窗隐藏背景模式
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            p.end()
            return

        hv = self.hover
        pad = 7.0
        lift = 4.0 * hv
        grow = 0.01 * hv
        cw, ch = max(1.0, w - pad * 2), max(1.0, h - pad * 2)
        dx, dy = cw * grow / 2.0, ch * grow / 2.0
        rect = QRectF(pad - dx, pad + lift - dy, cw + dx * 2, ch + dy * 2)
        r = min(self._radius, rect.width() / 2.0, rect.height() / 2.0)

        # 静止态就有一层可辨识的软投影，hover 时再扩散；边界由描边 + 阴影共同建立
        shadow, spad = blurred_shape(
            int(rect.width()), int(rect.height()), int(r),
            0, int(6 + 3 * hv), int(14 + 16 * hv),
            "#000000", int(16 + 14 * hv), hollow=True,
        )
        p.drawPixmap(QPointF(rect.x() - spad, rect.y() - spad), shadow)

        if self._anchor:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            if self._anchor == "gradient":
                gradient.setColorAt(0.0, QColor(BENTO_SKY))
                gradient.setColorAt(1.0, QColor(BENTO_VIOLET))
            else:
                gradient.setColorAt(0.0, QColor(BENTO_INK))
                gradient.setColorAt(1.0, QColor("#2f3037"))
            p.setBrush(gradient)
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(QColor(BENTO_CARD))
            # 外边界比规范基准深一档，白卡在 Snow 画布上才有明确轮廓
            p.setPen(QPen(QColor(BENTO_EDGE), 1.0))
        p.drawRoundedRect(rect, r, r)
        p.end()


class BentoGrid(QWidget):
    """响应式便当盒网格：桌面 4 栏 / 平板 2 栏 / 窄屏 1 栏。

    用法：::

        grid = BentoGrid(parent)
        grid.set_placements({
            4: [(card_a, 0, 0, 2, 2), (card_b, 0, 2, 1, 1)],
            2: [(card_a, 0, 0, 2, 2), (card_b, 2, 0, 1, 1)],
            1: [(card_a, 0, 0, 2, 1), (card_b, 2, 0, 1, 1)],
        })

    断点切换时重建布局（而不是只改 stretch），避免旧空列继续占宽度。
    间隙全页统一一个值，默认 16px。
    """

    WIDE_BREAKPOINT = 900
    MEDIUM_BREAKPOINT = 620

    def __init__(
        self,
        parent: QWidget | None = None,
        gap: int = 16,
        wide: int | None = None,
        medium: int | None = None,
    ):
        super().__init__(parent)
        self._gap = int(gap)
        self._wide = int(wide) if wide is not None else self.WIDE_BREAKPOINT
        self._medium = int(medium) if medium is not None else self.MEDIUM_BREAKPOINT
        self._placements: dict[int, list[tuple[QWidget, int, int, int, int]]] = {}
        self._cols = 0
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(self._gap)
        self._grid.setVerticalSpacing(self._gap)
        self._outer.addLayout(self._grid)

    def columns_for(self, width: int | None = None) -> int:
        w = self.width() if width is None else int(width)
        if w >= self._wide:
            return 4
        if w >= self._medium:
            return 2
        return 1

    def set_placements(
        self, placements: dict[int, list[tuple[QWidget, int, int, int, int]]]
    ) -> None:
        self._placements = dict(placements)
        self._apply()

    def count(self) -> int:
        """当前已放置的格子数，便于测试与空状态判断。"""
        return self._grid.count()

    def _apply(self) -> None:
        cols = self.columns_for()
        items = self._placements.get(cols) or []
        old = self._grid
        while old.count():
            item = old.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(self._gap)
        grid.setVerticalSpacing(self._gap)
        last_row = 0
        for widget, row, col, rowspan, colspan in items:
            grid.addWidget(widget, row, col, max(1, rowspan), max(1, colspan))
            last_row = max(last_row, row + max(1, rowspan))
        for column in range(cols):
            grid.setColumnStretch(column, 1)
        grid.setRowStretch(last_row, 1)

        self._outer.removeItem(old)
        self._outer.insertLayout(0, grid)
        old.deleteLater()
        self._grid = grid
        self._cols = cols

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._placements and self.columns_for() != self._cols:
            self._apply()
