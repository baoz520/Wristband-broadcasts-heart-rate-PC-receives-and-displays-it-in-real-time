"""历史记录窗口：便当盒网格中逐条展示每次连接的心率数据。

每张会话是一张 BentoCard：设备 / 游戏名、连接时段与时长、最低 / 最高 /
平均心率，以及按采样顺序铺满的历史折线图。最新一条跨整行作为大格，
其余成对并排，落单的一条再跨整行——尺寸本身就是层级，不需要用颜色区分。
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .chrome import BentoRootPanel, TitleBar
from .theme import BENTO_BORDER, BENTO_SNOW
from .widgets import BentoCard, BentoGrid, RaisedButton, Sparkline


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
    """浅色统计条：最低 / 最高 / 平均三列，便当盒白卡里的雪色小格。"""

    def __init__(self, low, high, avg, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(60)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
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
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        p.setPen(QPen(QColor(BENTO_BORDER), 1.0))
        p.setBrush(QColor(BENTO_SNOW))
        p.drawRoundedRect(rect, 12, 12)
        p.end()


class SessionCard(BentoCard):
    """单次连接的记录卡片（便当盒白卡）。"""

    deleteRequested = Signal(str)

    def __init__(self, record: dict, parent: QWidget | None = None):
        super().__init__(parent, object_name="BentoCard", radius=24.0)
        self._key = session_key(record)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

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
        delete.setFixedSize(58, 30)
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
            placeholder.setObjectName("Empty")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setFixedHeight(72)
            lay.addWidget(placeholder)


class HistoryWindow(QDialog):
    """历史记录窗口：响应式便当盒网格，显示每次连接的汇总与心率曲线。"""

    deleteRequested = Signal(str)

    def __init__(self, sessions: list[dict] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(760, 800)
        self.setMinimumSize(520, 420)
        self._sessions: list[dict] = []
        self._cards: list[QWidget] = []
        self._build_ui()
        self.set_sessions(sessions)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(BentoRootPanel(self))
        root = self.layout().itemAt(0).widget()
        assert isinstance(root, BentoRootPanel)

        bar = TitleBar("历史记录", "每次连接的监测数据")
        bar._min_button.hide()
        bar._max_button.hide()
        bar.closeClicked.connect(self.hide)
        self._count = QLabel("0 次连接")
        self._count.setObjectName("Badge")
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
        body = QVBoxLayout(container)
        body.setContentsMargins(16, 8, 16, 10)
        body.setSpacing(16)
        # 历史窗口默认 2 栏，最大化后可到 4 栏；间隙与其他窗口统一 16px
        self._cards_lay = BentoGrid(body.parent(), gap=16, wide=1100, medium=520)
        body.addWidget(self._cards_lay)

        footer = QWidget()
        foot_lay = QHBoxLayout(footer)
        foot_lay.setContentsMargins(0, 0, 0, 0)
        foot_lay.addStretch(1)
        close = RaisedButton("关闭")
        close.setProperty("action", True)
        close.setFixedWidth(120)
        close.clicked.connect(self.hide)
        foot_lay.addWidget(close)
        foot_lay.addStretch(1)
        root.addWidget(footer)

    def _placements_for(self, cols: int) -> list[tuple[QWidget, int, int, int, int]]:
        """每种列数都给一套完整 placement，缩放窗口时才能真的重排。"""
        total = len(self._cards)
        if not total:
            return []
        per_row = max(1, cols // 2)
        placements: list[tuple[QWidget, int, int, int, int]] = []
        # 最新一条跨整行作大格，尺寸就是层级
        placements.append((self._cards[0], 0, 0, 2, cols))
        row, slot = 2, 0
        for index in range(1, total):
            if cols == 1:
                placements.append((self._cards[index], row, 0, 2, 1))
                row += 2
                continue
            if slot >= 2:
                slot = 0
                row += 2
            if slot == 1 and index == total - 1:
                # 落单卡片跨整行，避免一行只剩半张卡
                placements.append((self._cards[index], row, 0, 2, cols))
            else:
                placements.append(
                    (self._cards[index], row, slot * per_row, 2, per_row)
                )
            slot += 1
        return placements

    def _relayout(self) -> None:
        self._cards_lay.set_placements(
            {cols: self._placements_for(cols) for cols in (4, 2, 1)}
        )
        self._grid_cols = self._cards_lay.columns_for()

    def set_sessions(self, sessions: list[dict] | None) -> None:
        """用最新的会话列表刷新窗口（最新的排在最前）。"""
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._sessions = [dict(r) for r in (sessions or [])]
        self._count.setText(f"{len(self._sessions)} 次连接")

        if not self._sessions:
            empty = BentoCard()
            label = QLabel("还没有历史记录\n连接手环并开始监测后，每次连接都会显示在这里")
            label.setObjectName("Sub")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            label.setWordWrap(True)
            lay = QVBoxLayout(empty)
            lay.setContentsMargins(24, 24, 24, 24)
            lay.addWidget(label)
            self._cards = [empty]
        else:
            for record in reversed(self._sessions):
                card = SessionCard(record)
                card.deleteRequested.connect(self.deleteRequested.emit)
                self._cards.append(card)
        self._relayout()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_cards_lay") and self._cards_lay.columns_for() != getattr(
            self, "_grid_cols", None
        ):
            self._grid_cols = self._cards_lay.columns_for()
            self._relayout()

    def center_on(self, widget: QWidget | None) -> None:
        reference = widget.frameGeometry() if widget is not None else self.frameGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(reference.center())
        self.move(geo.topLeft())
