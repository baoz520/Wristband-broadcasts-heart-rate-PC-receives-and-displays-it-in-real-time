"""自绘窗口外壳：标题栏三键、可缩放无边框窗口，以及关闭确认对话框。

最小化 / 最大化 / 关闭全部是控件，不再使用系统原生标题栏按钮；
点击关闭会弹出「最小化 / 直接关闭」与「不再提示」勾选框。
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import BLURPLE, CORAL, INK, MUTED
from .widgets import (
    BrandMark,
    HoverAnimator,
    RaisedButton,
    SoftCheckBox,
    draw_raised,
    draw_recessed,
    mix_color,
)

# 窗口四周留给柔和外阴影的透明边距
FRAME_MARGIN = 10
# 触发系统缩放的边缘宽度
RESIZE_EDGE = 8

_TOOLTIPS = {
    "min": "最小化",
    "max": "最大化",
    "restore": "向下还原",
    "close": "关闭",
}


class TitleButton(QAbstractButton):
    """圆形凸起标题栏按钮：最小化 / 最大化 / 还原 / 关闭。"""

    hover = Property(float, HoverAnimator._get, HoverAnimator._set)

    def __init__(self, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(_TOOLTIPS.get(kind, ""))
        HoverAnimator.setup(self)

    @property
    def kind(self) -> str:
        return self._kind

    def set_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.setToolTip(_TOOLTIPS.get(kind, ""))
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
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        r = min(14.0, rect.width() / 2.0, rect.height() / 2.0)
        hv = self.hover if self.isEnabled() else 0.0

        if self.isDown() and self.isEnabled():
            draw_recessed(p, rect, r, depth=3)
        else:
            draw_raised(
                p, rect, r,
                distance=2.5 + 1.5 * hv, blur=5.0 + 3.0 * hv,
                grey_alpha=int(105 + 45 * hv), white_alpha=int(185 + 30 * hv),
                rim=hv > 0.05,
            )

        # 不绘制焦点环：标题栏按钮不需要显式的圆框轮廓，避免圆形按钮外
        # 套一个方向方框的视觉噪声。键盘仍可 Tab 聚焦并回车触发。

        if self._kind == "close":
            tone = mix_color(INK, CORAL, hv)
        else:
            tone = mix_color(INK, BLURPLE, hv)
        if not self.isEnabled():
            tone = QColor(MUTED)
        pen = QPen(tone, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        c = rect.center()

        if self._kind == "min":
            p.drawLine(QPointF(c.x() - 4.5, c.y()), QPointF(c.x() + 4.5, c.y()))
        elif self._kind == "max":
            p.drawRoundedRect(QRectF(c.x() - 4.8, c.y() - 4.8, 9.6, 9.6), 1.6, 1.6)
        elif self._kind == "restore":
            p.drawRoundedRect(QRectF(c.x() - 5.6, c.y() - 3.6, 8.2, 8.2), 1.4, 1.4)
            p.drawRoundedRect(QRectF(c.x() - 2.6, c.y() - 5.6, 8.2, 8.2), 1.4, 1.4)
        else:  # close
            p.drawLine(QPointF(c.x() - 4.2, c.y() - 4.2), QPointF(c.x() + 4.2, c.y() + 4.2))
            p.drawLine(QPointF(c.x() + 4.2, c.y() - 4.2), QPointF(c.x() - 4.2, c.y() + 4.2))
        p.end()


class TitleBar(QFrame):
    """可拖动、双击切换最大化的标题栏。"""

    minimizeClicked = Signal()
    maximizeClicked = Signal()
    closeClicked = Signal()

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(52)
        self.setMouseTracking(True)
        self._drag_origin: QPointF | None = None
        self._maximized = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 4, 12, 4)
        lay.setSpacing(10)

        lay.addWidget(BrandMark(28), 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self._title = QLabel(title)
        self._title.setObjectName("H1")
        col.addWidget(self._title)
        if subtitle:
            self._subtitle = QLabel(subtitle)
            self._subtitle.setObjectName("Sub")
            col.addWidget(self._subtitle)
        lay.addLayout(col, 1)

        self._trailing = QWidget()
        self._trailing.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        self._trailing_lay = QHBoxLayout(self._trailing)
        self._trailing_lay.setContentsMargins(0, 0, 0, 0)
        self._trailing_lay.setSpacing(6)
        lay.addWidget(self._trailing, 0, Qt.AlignmentFlag.AlignVCenter)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        self._min_button = TitleButton("min")
        self._max_button = TitleButton("max")
        self._close_button = TitleButton("close")
        self._min_button.clicked.connect(self.minimizeClicked.emit)
        self._max_button.clicked.connect(self.maximizeClicked.emit)
        self._close_button.clicked.connect(self.closeClicked.emit)
        for btn in (self._min_button, self._max_button, self._close_button):
            buttons.addWidget(btn)
        lay.addLayout(buttons, 0)

    def set_trailing(self, widget: QWidget) -> None:
        self._trailing_lay.addWidget(widget)

    def set_maximized(self, maximized: bool) -> None:
        self._maximized = bool(maximized)
        self._max_button.set_kind("restore" if self._maximized else "max")

    # ------------------------------------------------------------- 拖动
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                try:
                    handle.startSystemMove()
                    self._drag_origin = None
                    event.accept()
                    return
                except Exception:
                    pass
            self._drag_origin = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximizeClicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class RootPanel(QWidget):
    """整窗新拟物卡片：自绘柔和外阴影，边缘可拖动缩放。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN)
        self._layout.setSpacing(0)

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802
        self._layout.addWidget(widget)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(
            FRAME_MARGIN, FRAME_MARGIN,
            max(1.0, self.width() - FRAME_MARGIN * 2),
            max(1.0, self.height() - FRAME_MARGIN * 2),
        )
        draw_raised(
            p, rect, 24.0,
            distance=10.0, blur=20.0, grey_alpha=155, white_alpha=205, rim=True,
        )
        p.end()

    def _edges_at(self, pos) -> Qt.Edges:
        edges = Qt.Edge(0)
        window = self.window()
        if window is None or window.isMaximized():
            return edges
        w, h = self.width(), self.height()
        if pos.x() <= RESIZE_EDGE:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= w - RESIZE_EDGE:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= RESIZE_EDGE:
            edges |= Qt.Edge.TopEdge
        if pos.y() >= h - RESIZE_EDGE:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mousePressEvent(self, event) -> None:  # noqa: N802
        edges = self._edges_at(event.position().toPoint())
        if edges and event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                try:
                    handle.startSystemResize(edges)
                    event.accept()
                    return
                except Exception:
                    pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        edges = self._edges_at(event.position().toPoint())
        left = bool(edges & Qt.Edge.LeftEdge)
        right = bool(edges & Qt.Edge.RightEdge)
        top = bool(edges & Qt.Edge.TopEdge)
        bottom = bool(edges & Qt.Edge.BottomEdge)
        if (left and top) or (right and bottom):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (right and top) or (left and bottom):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif left or right:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif top or bottom:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)


class CloseCard(QFrame):
    """对话框的凸起卡片表面。"""

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        draw_raised(p, rect, 24.0)
        p.end()


class CloseDialog(QDialog):
    """关闭确认框：最小化 / 直接关闭，下方「不再提示」勾选框。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedSize(392, 258)

        self.action: str | None = None
        self.remember = False

        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN, FRAME_MARGIN)

        card = CloseCard(self)
        card.setObjectName("CloseCard")
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 22, 28, 18)
        lay.setSpacing(0)

        title = QLabel("关闭心率监测")
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)

        desc = QLabel("关闭窗口后，你希望如何处理？")
        desc.setObjectName("Sub")
        desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(desc)
        lay.addSpacing(22)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        self._minimize = RaisedButton("最小化")
        self._minimize.setProperty("accent", True)
        self._quit = RaisedButton("直接关闭")
        self._quit.setProperty("danger", True)
        self._minimize.setFixedHeight(42)
        self._quit.setFixedHeight(42)
        self._minimize.setDefault(True)
        self._minimize.clicked.connect(lambda: self._choose("minimize"))
        self._quit.clicked.connect(lambda: self._choose("quit"))
        row.addWidget(self._minimize, 1)
        row.addWidget(self._quit, 1)
        lay.addLayout(row)
        lay.addSpacing(14)

        self._check = SoftCheckBox("不再提示")
        check_row = QHBoxLayout()
        check_row.setContentsMargins(0, 0, 0, 0)
        check_row.addStretch(1)
        check_row.addWidget(self._check, 0, Qt.AlignmentFlag.AlignHCenter)
        check_row.addStretch(1)
        lay.addLayout(check_row)

    def _choose(self, action: str) -> None:
        self.action = action
        self.remember = self._check.isChecked()
        self.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        # 窗口整体透明，卡片自身负责绘制
        return

    def center_on(self, widget: QWidget | None) -> None:
        reference = widget.frameGeometry() if widget is not None else self.frameGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(reference.center())
        self.move(geo.topLeft())
