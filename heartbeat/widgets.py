"""自绘控件：玻璃面板、网格、按钮、开关、心形、走势图与状态胶囊。

材质规则（与玻璃拟态规范一致）：
- 夜景底 + 柔光斑提供可模糊内容；面板只用 8%–14% 的白，绝不成实心块。
- 三层光必须同时存在：外层深阴影、顶边白色内高光、底边深色内暗缘。
- hover 500ms：填充升到 14%、描边升到 30%、阴影扩散并上浮 2px。
- 香槟金只给主 CTA 与关键数字，其余颜色都来自夜景色板。
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
    QRadialGradient,
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
    CHAMPAGNE,
    CORAL,
    GLASS_WHITE,
    MOON_STEEL,
    MOONLIGHT,
    MUTED,
    NIGHT,
    NIGHT_DEEP,
    NIGHT_STEEL,
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

    hollow=True 时模糊后挖掉卡片本体，只留下外侧柔影，避免玻璃内部发黑。
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

    if hollow:
        # 模糊完成后再挖掉卡片本体：外侧保留自然下投的柔影，
        # 内侧完全透明，不会在玻璃卡片里透出一圈发黑的暗晕。
        clearer = QPainter(out)
        clearer.setRenderHint(QPainter.RenderHint.Antialiasing)
        clearer.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        clearer.setPen(Qt.PenStyle.NoPen)
        clearer.setBrush(QColor(0, 0, 0, 255))
        clearer.drawRoundedRect(QRectF(pad, pad, w, h), radius, radius)
        clearer.end()

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
    """玻璃凸起：外深阴影 + 8% 白填充 + 顶高光 / 底暗缘 + 15% 白描边。

    参数名沿用旧版以便所有调用点平滑迁移；实际色值来自玻璃拟态色板。
    """
    r = max(0.0, float(radius))
    # 外层深阴影：参数由调用点给出，最小 6px 保证厚度可辨
    d = max(2, int(round(distance)))
    b = max(6, int(round(blur)))
    shadow, pad = blurred_shape(
        max(1, int(rect.width())), max(1, int(rect.height())),
        int(r), 0, d, b, NIGHT_DEEP, max(90, grey_alpha), hollow=True,
    )
    painter.drawPixmap(QPointF(rect.x() - pad, rect.y() - pad), shadow)

    # 玻璃填充：始终半透明，绝不超过 15%
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(rgba(GLASS_WHITE, 20))
    painter.drawRoundedRect(rect, r, r)

    # 顶边 1px 白色内高光 / 底边 1px 深色内暗缘
    inset = rect.adjusted(1.5, 1.5, -1.5, -1.5)
    edge_x = r * 0.45
    if inset.width() > edge_x * 2:
        painter.setPen(QPen(rgba(GLASS_WHITE, 56), 1.0))
        painter.drawLine(
            QPointF(inset.left() + edge_x, inset.top()),
            QPointF(inset.right() - edge_x, inset.top()),
        )
        painter.setPen(QPen(rgba(NIGHT_DEEP, 90), 1.0))
        painter.drawLine(
            QPointF(inset.left() + edge_x, inset.bottom()),
            QPointF(inset.right() - edge_x, inset.bottom()),
        )

    # 1px 白色 15% 外描边（hover 时调用点可自行加亮）
    painter.setPen(QPen(rgba(GLASS_WHITE, 38 if not rim else 46), 1.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)


def draw_recessed(painter: QPainter, rect: QRectF, radius: float, *, depth: float = 9.0) -> None:
    """夜景凹槽：深墨底 + 左上内暗影 + 右下微光，用于轨道与输入槽。"""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(NIGHT_DEEP))
    painter.drawPath(path)

    painter.save()
    painter.setClipPath(path)
    band = max(4.0, min(depth * 2.4, rect.width() / 2.0, rect.height() / 2.0))
    l, t, rgt, btm = rect.left(), rect.top(), rect.right(), rect.bottom()

    for grad, fill_rect in (
        (QLinearGradient(l, t, l, t + band), QRectF(l, t, rect.width(), band)),
        (QLinearGradient(l, t, l + band, t), QRectF(l, t, band, rect.height())),
    ):
        grad.setColorAt(0.0, rgba(NIGHT_DEEP, 210))
        grad.setColorAt(1.0, rgba(NIGHT_DEEP, 0))
        painter.fillRect(fill_rect, QBrush(grad))

    for grad, fill_rect in (
        (QLinearGradient(rgt, btm, rgt, btm - band), QRectF(l, btm - band, rect.width(), band)),
        (QLinearGradient(rgt, btm, rgt - band, btm), QRectF(rgt - band, t, band, rect.height())),
    ):
        grad.setColorAt(0.0, rgba(GLASS_WHITE, 38))
        grad.setColorAt(1.0, rgba(GLASS_WHITE, 0))
        painter.fillRect(fill_rect, QBrush(grad))
    painter.restore()

    painter.setPen(QPen(rgba(GLASS_WHITE, 30), 1.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


def paint_liquid_glass(
    painter: QPainter,
    rect: QRectF,
    radius: float,
    *,
    hover: float = 0.0,
    flow: float = 0.0,
    anchor: bool = False,
    shadow: bool = True,
) -> None:
    """液态玻璃材质：折射渐变 + 流动高光 + 曲面边缘光。

    与旧版平铺白填充不同，这里让光线沿对角线缓慢流过整块玻璃，
    并用渐变描边模拟厚透镜的折射边缘。hover 只放大同一束光，不引入新颜色。
    """
    r = min(float(radius), rect.width() / 2.0, rect.height() / 2.0)
    hv = max(0.0, min(1.0, float(hover)))
    flow = max(0.0, min(1.0, float(flow)))

    if shadow:
        shadow_pm, pad = blurred_shape(
            max(1, int(rect.width())), max(1, int(rect.height())), int(r),
            0, 16, int(40 + 24 * hv), NIGHT_DEEP, int(88 + 16 * hv), hollow=True,
        )
        painter.drawPixmap(QPointF(rect.x() - pad, rect.y() - pad), shadow_pm)

    painter.save()
    clip = QPainterPath()
    clip.addRoundedRect(rect, r, r)
    painter.setClipPath(clip)
    painter.setPen(Qt.PenStyle.NoPen)

    if anchor:
        painter.setBrush(QColor(NIGHT_DEEP))
        painter.drawRect(rect)
        glow = QRadialGradient(
            rect.right(), rect.top(), max(1.0, rect.width() * 0.95)
        )
        glow.setColorAt(0.0, rgba(CHAMPAGNE, 52 + int(18 * hv)))
        glow.setColorAt(1.0, rgba(CHAMPAGNE, 0))
        painter.setBrush(glow)
        painter.drawRect(rect)
    else:
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, rgba(GLASS_WHITE, int(30 + 20 * hv)))
        base.setColorAt(0.42, rgba(GLASS_WHITE, int(13 + 12 * hv)))
        base.setColorAt(0.72, rgba(MOON_STEEL, int(14 + 8 * hv)))
        base.setColorAt(1.0, rgba(GLASS_WHITE, int(24 + 16 * hv)))
        painter.setBrush(base)
        painter.drawRect(rect)

    # 一条缓慢扫过的白色光带，就是“液态”的来源
    band = max(48.0, rect.width() * 0.42)
    x = rect.left() + (rect.width() + band) * flow - band
    sheen = QLinearGradient(QPointF(x, rect.top()), QPointF(x + band, rect.bottom()))
    sheen.setColorAt(0.0, rgba(GLASS_WHITE, 0))
    sheen.setColorAt(0.5, rgba(GLASS_WHITE, int(18 + 20 * hv)))
    sheen.setColorAt(1.0, rgba(GLASS_WHITE, 0))
    painter.setBrush(sheen)
    painter.drawRect(rect)
    painter.restore()

    # 曲面边缘：左上亮、右下冷，像一块有厚度的透镜
    edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
    edge.setColorAt(0.0, rgba(GLASS_WHITE, int(66 + 28 * hv)))
    edge.setColorAt(0.5, rgba(GLASS_WHITE, int(30 + 20 * hv)))
    edge.setColorAt(1.0, rgba(MOON_STEEL, int(48 + 20 * hv)))
    painter.setPen(QPen(QBrush(edge), 1.1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), r, r)

    inset = rect.adjusted(1.5, 1.5, -1.5, -1.5)
    ex = r * 0.45
    if inset.width() > ex * 2:
        painter.setPen(QPen(rgba(GLASS_WHITE, int(62 + 26 * hv)), 1.0))
        painter.drawLine(
            QPointF(inset.left() + ex, inset.top()),
            QPointF(inset.right() - ex, inset.top()),
        )
        painter.setPen(QPen(rgba(NIGHT_DEEP, 105), 1.0))
        painter.drawLine(
            QPointF(inset.left() + ex, inset.bottom()),
            QPointF(inset.right() - ex, inset.bottom()),
        )


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
    bg = QColor(NIGHT_STEEL)
    ink = QColor(CHAMPAGNE)
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


def make_app_pixmap(size: int = 256) -> QPixmap:
    """与 EXE 图标一致：深蓝圆角底 + 香槟金心形 + 心电脉搏。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    outer = QRectF(size * 0.035, size * 0.035, size * 0.93, size * 0.93)
    p.setPen(QPen(QColor(CHAMPAGNE), max(1.0, size * 0.019)))
    p.setBrush(QColor(NIGHT))
    p.drawRoundedRect(outer, size * 0.22, size * 0.22)

    inner = QRectF(size * 0.075, size * 0.075, size * 0.85, size * 0.85)
    p.setPen(QPen(rgba(GLASS_WHITE, 34), max(1.0, size * 0.007)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(inner, size * 0.19, size * 0.19)

    heart = QRectF(size * 0.18, size * 0.16, size * 0.64, size * 0.67)
    grad = QLinearGradient(heart.topLeft(), heart.bottomLeft())
    grad.setColorAt(0.0, QColor("#ffdc96"))
    grad.setColorAt(1.0, QColor(CHAMPAGNE))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawPath(heart_path(heart))

    points = [
        (0.19, 0.56), (0.34, 0.56), (0.40, 0.47), (0.46, 0.65),
        (0.53, 0.41), (0.60, 0.56), (0.81, 0.56),
    ]
    path = QPainterPath()
    path.moveTo(size * points[0][0], size * points[0][1])
    for x, y in points[1:]:
        path.lineTo(size * x, size * y)
    pen = QPen(QColor(NIGHT_DEEP), max(2.0, size * 0.043))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.end()
    return pm


def make_app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_app_pixmap(s))
    return icon


class HoverAnimator:
    """给 QWidget 子类提供可动画的 hover 进度（0→1）。

    用法：子类声明 ``hover = Property(float, HoverAnimator._get, HoverAnimator._set)``，
    在构造里调用 ``HoverAnimator.setup(self)``，enterEvent/leaveEvent 调用
    ``fade(1.0/0.0)``，paintEvent 读取 ``self.hover`` 做插值。
    """

    DURATION = 240

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


def animate_show(widget: QWidget, duration: int = 260) -> None:
    """窗口首次出现时淡入，不改变用户自定义的不透明度。"""
    if widget is None or getattr(widget, "_entry_anim_done", False):
        return
    widget._entry_anim_done = True
    end = widget.windowOpacity()
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    widget._entry_anim = anim


class ToggleSwitch(QAbstractButton):
    """玻璃开关：夜景凹槽轨道 + 玻璃旋钮，开启填香槟金。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 32)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(280)
        curve = QEasingCurve(QEasingCurve.Type.OutBack)
        curve.setOvershoot(1.25)
        self._anim.setEasingCurve(curve)
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
        fill_color = QColor(CHAMPAGNE) if (on and self.isEnabled()) else QColor(MOON_STEEL)
        if not self.isEnabled():
            fill_color = QColor(NIGHT_STEEL)
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
            p.setBrush(QColor(MOON_STEEL))
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
    reveal = Property(float, lambda self: self._reveal, lambda self, v: self._set_reveal(v))

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._points: deque[tuple[float, int]] = deque()
        self._history_mode = False
        self._axis_labels: tuple[str, str, str] = ("−60 秒", "30 秒", "现在")
        self._dark = False
        self._reveal = 1.0
        self._reveal_anim = QPropertyAnimation(self, b"reveal", self)
        self._reveal_anim.setDuration(680)
        self._reveal_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _set_reveal(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value != self._reveal:
            self._reveal = value
            self.update()

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
        self._reveal_anim.stop()
        self._reveal_anim.setStartValue(0.0)
        self._reveal_anim.setEndValue(1.0)
        self._reveal_anim.start()
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

        grid_pen = QPen(rgba(MOON_STEEL, 110), 1)
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(grid_pen)
        for i in range(3):
            y = plot.top() + plot.height() * (i + 1) / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        vals = [v for _, v in self._points]
        if len(vals) < 2:
            p.setPen(QColor(MUTED))
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

        # 历史曲线从左向右描绘；实时曲线保持完整，避免每帧重播动画。
        p.save()
        if self._reveal < 1.0:
            reveal_w = plot.width() * self._reveal
            p.setClipRect(QRectF(plot.left(), plot.top(), reveal_w, plot.height()))

        fill = QPainterPath()
        fill.moveTo(pts[0].x(), plot.bottom())
        for pt in pts:
            fill.lineTo(pt)
        fill.lineTo(pts[-1].x(), plot.bottom())
        fill.closeSubpath()
        fill_color = CHAMPAGNE
        grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
        grad.setColorAt(0.0, rgba(fill_color, 58 if self._dark else 40))
        grad.setColorAt(1.0, rgba(fill_color, 6 if self._dark else 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(fill)

        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        pen = QPen(QColor(CHAMPAGNE), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)

        last = pts[-1]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rgba(fill_color, 80))
        p.drawEllipse(last, 6.0, 6.0)
        p.setBrush(QColor(CHAMPAGNE))
        p.drawEllipse(last, 3.1, 3.1)
        p.restore()

        p.setPen(QColor(MUTED))
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
            color = QColor(CHAMPAGNE if i < self._level else MOON_STEEL)
            if i < self._level:
                color.setAlpha(230)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, y, bar_w, h), 1.4, 1.4)
        p.end()


class SoftPill(QLabel):
    """夜景凹槽胶囊：深墨底 + 内阴影，文字用月光钢表达状态。"""

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
        "idle": MOONLIGHT,
        "connecting": CHAMPAGNE,
        "reconnecting": CHAMPAGNE,
        "connected": "#34d399",
        "broadcasting": CHAMPAGNE,
        "disconnected": "#f87171",
        "error": "#f87171",
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
    """标题旁的玻璃小方块 + 香槟金心形。"""

    def __init__(self, size: int = 44, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._pix = make_heart_pixmap(size // 2)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        draw_raised(p, rect, 13.0, distance=4.0, blur=10.0, grey_alpha=110, white_alpha=190)
        p.drawPixmap(
            (self.width() - self._pix.width()) // 2,
            (self.height() - self._pix.height()) // 2,
            self._pix,
        )
        p.end()


class RaisedButton(QPushButton):
    """玻璃按钮：主 CTA 香槟金胶囊，危险操作柔和红，次要按钮玻璃材质。"""

    hover = Property(float, HoverAnimator._get, HoverAnimator._set)
    flash = Property(float, lambda self: self._flash, lambda self, v: self._set_flash(v))

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pressed = False
        self._flash = 0.0
        self._flash_anim = QPropertyAnimation(self, b"flash", self)
        self._flash_anim.setDuration(300)
        self._flash_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        HoverAnimator.setup(self)

    def _set_flash(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value != self._flash:
            self._flash = value
            self.update()

    def _play_flash(self) -> None:
        self._flash_anim.stop()
        self._flash_anim.setStartValue(1.0)
        self._flash_anim.setEndValue(0.0)
        self._flash_anim.start()

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
            self._play_flash()
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
        danger = bool(self.property("danger"))
        cta = bool(self.property("accent")) or bool(self.property("action"))
        # 规范：按钮 16px 圆角，主 CTA 用 999px 全圆角胶囊
        r = min(h / 2.0, 999.0) if cta else min(16.0, w / 2.0, h / 2.0)
        pressed = self._pressed or (self.isDown() and self.isEnabled())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        if pressed:
            rect = rect.adjusted(1.5, 1.5, -1.5, -1.5)
        hv = self.hover if self.isEnabled() else 0.0
        if cta and hv > 0:
            rect.translate(0, -1.0 * hv)  # CTA hover 上浮 1px

        if not self.isEnabled():
            p.setPen(QPen(rgba(GLASS_WHITE, 24), 1.0))
            p.setBrush(rgba(GLASS_WHITE, 10))
        elif danger:
            p.setPen(QPen(rgba(CORAL, 110), 1.0))
            p.setBrush(rgba(CORAL, int(28 + 28 * hv + 30 * self._flash)))
        elif cta:
            # 香槟金光晕：hover 时扩到 25% 金色，由 hover 属性平滑驱动
            glow, gpad = blurred_shape(
                max(1, int(rect.width())), max(1, int(rect.height())), int(r),
                0, 6, 20, CHAMPAGNE, int(40 + 55 * hv), hollow=True,
            )
            p.drawPixmap(QPointF(rect.x() - gpad, rect.y() - gpad), glow)
            gold = QColor(CHAMPAGNE)
            gold.setAlpha(min(255, int(230 + 25 * hv)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gold)
        else:
            # 次要按钮：8% → 14% 白填充、15% → 30% 白描边
            p.setPen(QPen(rgba(GLASS_WHITE, int(38 + 38 * hv)), 1.0))
            p.setBrush(rgba(GLASS_WHITE, int(20 + 15 * hv + 24 * self._flash)))
        p.drawRoundedRect(rect, r, r)

        # 点击瞬间一层极淡白光扫过，300ms 内退去，给出轻盈的触感反馈
        if self.isEnabled() and self._flash > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rgba(GLASS_WHITE, int(42 * self._flash)))
            p.drawRoundedRect(rect, r, r)

        # 玻璃按钮的顶边高光 / 底边暗缘（CTA 是实心胶囊，不需要）
        if not cta and not danger and self.isEnabled() and rect.width() > r * 2:
            inner = rect.adjusted(1.5, 1.5, -1.5, -1.5)
            p.setPen(QPen(rgba(GLASS_WHITE, 56), 1.0))
            p.drawLine(
                QPointF(inner.left() + r * 0.45, inner.top()),
                QPointF(inner.right() - r * 0.45, inner.top()),
            )
            p.setPen(QPen(rgba(NIGHT_DEEP, 90), 1.0))
            p.drawLine(
                QPointF(inner.left() + r * 0.45, inner.bottom()),
                QPointF(inner.right() - r * 0.45, inner.bottom()),
            )

        if not self.isEnabled():
            tone = QColor(MOON_STEEL)
        elif cta:
            tone = QColor(NIGHT_DEEP)
        elif danger:
            tone = QColor(CORAL)
        else:
            tone = QColor(GLASS_WHITE)
        f = QFont(self.font())
        f.setPointSize(13)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(tone)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


class SoftCheckBox(QAbstractButton):
    """玻璃勾选框：夜景凹槽 + 香槟金勾，键盘焦点可见。"""

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
            pen = QPen(QColor(CHAMPAGNE), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(mark)
        f = QFont(self.font())
        f.setPointSize(12)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(mix_color(GLASS_WHITE, CHAMPAGNE, self.hover))
        p.drawText(
            QRectF(28.0, 0, max(0.0, self.width() - 28.0), self.height()),
            Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
        if self.hasFocus():
            p.setPen(QPen(QColor(CHAMPAGNE), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box.adjusted(-3, -3, 3, 3), 9, 9)
        p.end()


class SoftCard(QFrame):
    """玻璃卡片基类：24px 圆角、三层光与 hover 属性，供 BentoCard 复用。"""

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
        """完全隐藏底板（游戏中悬浮窗用），只保留心率数据与文字阴影。"""
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
            # "隐藏背景"模式：清除底板与阴影，真正只留文字悬在游戏画面上。
            # 文字可读性由浮动窗里的轻量投影负责，这里不再画任何蒙版。
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(self.rect(), Qt.GlobalColor.transparent)
            p.end()
            return
        r = min(self._radius, w / 2.0, h / 2.0)
        hv = self.hover
        # hover：玻璃填充与描边由 draw_raised 按进度插值，整块上浮 2px
        rect = QRectF(0, -2.0 * hv, w, h)
        draw_raised(
            p, rect, r,
            distance=8.0 - 4.0 * hv,
            blur=16.0 - 8.0 * hv,
            grey_alpha=int(92 + 18 * hv),
            white_alpha=int(182 + 20 * hv),
            rim=True,
        )
        p.end()


class BentoCard(SoftCard):
    """液态玻璃面板：折射渐变 + 流动高光 + 曲面边缘光。

    hover 500ms 内同一束光增强、整块上浮 2px；锚点卡仍是深墨底 +
    香槟金微光。shadow=False 用于悬浮窗等不需要外阴影的场景。
    """

    flow = Property(float, lambda self: self._flow, lambda self, v: self._set_flow(v))

    def __init__(
        self,
        parent: QWidget | None = None,
        object_name: str = "BentoCard",
        radius: float = 24.0,
        anchor: bool | str = False,
        shadow: bool = True,
    ):
        super().__init__(parent, object_name=object_name, radius=radius)
        self._anchor = anchor
        self._shadow = bool(shadow)
        # 玻璃规范：500ms 慢过渡，OutCubic 起手快、收尾稳
        self._hover_anim.setDuration(500)
        self._flow = 0.0
        self._flow_anim = QPropertyAnimation(self, b"flow", self)
        self._flow_anim.setDuration(7200)
        self._flow_anim.setStartValue(0.0)
        self._flow_anim.setEndValue(1.0)
        self._flow_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._flow_anim.setLoopCount(-1)
        # 每张卡错开相位，避免整屏高光同步扫过
        self._flow_anim.setCurrentTime((id(self) % 97) * 74)
        self._flow_anim.start()

    def _set_flow(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value != self._flow:
            self._flow = value
            self.update()

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
        pad = 12.0
        lift = 2.0 * hv
        rect = QRectF(pad, pad + lift, max(1.0, w - pad * 2), max(1.0, h - pad * 2))

        paint_liquid_glass(
            p, rect, self._radius,
            hover=hv, flow=self._flow,
            anchor=bool(self._anchor), shadow=self._shadow,
        )
        p.end()
        return



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
