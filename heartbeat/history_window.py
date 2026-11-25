"""历史记录窗口：逐条展示每次连接的时长与心率统计，并绘制本次连接的心率曲线。

无边框新拟物外壳复用 chrome.RootPanel / TitleBar，滚动区域里每条会话是一张
SoftCard：设备名、连接时段、持续时长、最低/最高/平均心率，以及一段 Sparkline
折线图（历史模式，按采样顺序铺满绘图区，不受实时 60 秒窗口限制）。
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .chrome import BentoRootPanel, RootPanel, TitleBar
from .widgets import RaisedButton, SoftCard, Sparkline, draw_recessed


def _ts_parts(ts: float) -> tuple[str, str]:
    """Unix 秒 -> (年-月-日, 时:分)。"""
    try:
        local = time.localtime(float(ts))
        return time.strftime("%Y-%m-%d", local), time.strftime("%H:%M", local)
    except (ValueError, OverflowError, OSError):
        return "—", "—"


def session_key(record: dict) -> str:
    """会话唯一键：地址 + 开始时间，用于定位要删除的记录。"""
    return f"{record.get('address', '')}|{record.get('start', '')}"


def _fmt_duration(start: float, end: float) -> str:
    """把一段连接时长格式化成易读文字。"""
    seconds = max(0, int(float(end)) - int(float(start)))
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} 分 {sec} 秒" if sec else f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return f"{hours} 小时 {minutes} 分"
    return f"{hours} 小时"


class _StatStrip(QWidget):
    """凹陷的统计条：最低 / 最高 / 平均三列。"""

    def __init__(self, low, high, avg, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(58)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        for label, value in (("最低", low), ("最高", high), ("平均", avg)):
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(1)
            name = QLabel(label)
            name.setObjectName("StatLabel")
            name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            val = QLabel(str(value))
            val.setObjectName("StatValue")
            val.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(name)
            col.addWidget(val)
            lay.addLayout(col, 1)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_recessed(
            p,
            QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0),
            14.0,
            depth=5,
        )
        p.end()


class SessionCard(SoftCard):
    """单次连接的记录卡片。"""

    deleteRequested = Signal(str)

    def __init__(self, record: dict, parent: QWidget | None = None):
        super().__init__(parent, object_name="SoftCard", radius=20.0)
        self._key = session_key(record)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(7)

        start = record.get("start") or 0
        end = record.get("end") or start
        day, start_hm = _ts_parts(start)
        _, end_hm = _ts_parts(end)
        name = record.get("name") or record.get("address") or "设备"
        is_game = bool(record.get("game"))

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        if is_game:
            from .game import game_icon

            icon = game_icon(record.get("game_icon", ""), 28)
            if icon is not None:
                icon_label = QLabel()
                icon_label.setPixmap(icon.pixmap(28, 28))
                icon_label.setFixedSize(28, 28)
                top.addWidget(icon_label, 0)
            badge = QLabel("游戏")
            badge.setObjectName("Badge")
            top.addWidget(badge, 0)
        title = QLabel(name)
        title.setObjectName("H2")
        top.addWidget(title, 1)
        date = QLabel(day)
        date.setObjectName("Sub")
        date.setAlignment(Qt.AlignmentFlag.AlignRight)
        top.addWidget(date, 0)

        delete = RaisedButton("删除", self)
        delete.setProperty("danger", True)
        delete.setFixedSize(52, 28)
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.setToolTip("删除这条历史记录")
        delete.clicked.connect(lambda: self.deleteRequested.emit(self._key))
        top.addWidget(delete, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(top)

        duration_label = "游戏时长" if is_game else "连接时长"
        meta = QLabel(
            f"{start_hm} – {end_hm} · {duration_label} {_fmt_duration(start, end)}"
        )
        meta.setObjectName("Sub")
        lay.addWidget(meta)

        lay.addWidget(
            _StatStrip(
                record.get("min", "—"),
                record.get("max", "—"),
                record.get("avg", "—"),
            )
        )

        series = [
            (float(x[0]), int(x[1]))
            for x in (record.get("series") or [])
            if isinstance(x, (list, tuple)) and len(x) >= 2
        ]
        if len(series) >= 2:
            spark = Sparkline()
            spark.setFixedHeight(92)
            spark.set_history(
                series,
                (f"{start_hm} 开始", f"{len(series)} 次采样", f"{end_hm} 结束"),
            )
            lay.addWidget(spark)
        else:
            placeholder = QLabel("该记录未保存心率曲线（旧版本数据）")
            placeholder.setObjectName("Sub")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setFixedHeight(72)
            lay.addWidget(placeholder)


class HistoryWindow(QDialog):
    """历史记录窗口：显示每次连接的汇总与心率曲线。"""

    deleteRequested = Signal(str)

    def __init__(self, sessions: list[dict] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(560, 760)
        self.setMinimumSize(440, 420)
        self._sessions: list[dict] = []
        self._build_ui()
        self.set_sessions(sessions)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(BentoRootPanel(self))
        root = self.layout().itemAt(0).widget()
        assert isinstance(root, RootPanel)

        bar = TitleBar("历史记录", "每次连接的监测数据")
        bar._min_button.hide()
        bar._max_button.hide()
        bar.closeClicked.connect(self.hide)
        self._count = QLabel("0 次连接")
        self._count.setObjectName("Pill")
        bar.set_trailing(self._count)
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
        self._cards_lay = QVBoxLayout(container)
        self._cards_lay.setContentsMargins(14, 10, 14, 4)
        self._cards_lay.setSpacing(14)

        footer = QWidget()
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(0, 0, 0, 0)
        foot_lay.addStretch(1)
        close = RaisedButton("关闭")
        close.setFixedWidth(120)
        close.clicked.connect(self.hide)
        foot_lay.addWidget(close)
        foot_lay.addStretch(1)
        root.addWidget(footer)

    def set_sessions(self, sessions: list[dict] | None) -> None:
        """用最新的会话列表刷新窗口（最新的排在最前）。"""
        self._sessions = [dict(r) for r in (sessions or [])]
        while self._cards_lay.count():
            item = self._cards_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._count.setText(f"{len(self._sessions)} 次连接")
        if not self._sessions:
            empty = QLabel("还没有历史记录\n连接手环并开始监测后，每次连接都会显示在这里")
            empty.setObjectName("Sub")
            empty.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            empty.setWordWrap(True)
            empty.setContentsMargins(0, 48, 0, 0)
            self._cards_lay.addWidget(empty, 1)
            return

        for record in reversed(self._sessions):
            card = SessionCard(record)
            card.setSizePolicy(
                card.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.Fixed,
            )
            card.deleteRequested.connect(self.deleteRequested.emit)
            self._cards_lay.addWidget(card)
        # 剩余空间交给末尾弹簧，避免单条卡片被拉伸出大片空白
        self._cards_lay.addStretch(1)

    def center_on(self, widget: QWidget | None) -> None:
        reference = widget.frameGeometry() if widget is not None else self.frameGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(reference.center())
        self.move(geo.topLeft())
