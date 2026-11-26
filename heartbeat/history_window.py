"""历史记录窗口：玻璃面板网格中逐条展示每次连接的心率数据。

每张会话是一张玻璃卡：设备 / 游戏名、连接时段与时长、最低 / 最高 /
平均心率，以及按采样顺序铺满的历史折线图。最新一条跨整行作为大格，
其余成对并排，落单的一条再跨整行——尺寸本身就是层级，不需要用颜色区分。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .chrome import BentoRootPanel, TitleBar
from .hr import STATE_COLORS
from .theme import CHAMPAGNE, GLASS_WHITE, MOON_STEEL, NIGHT_DEEP
from .widgets import BentoCard, BentoGrid, RaisedButton, Sparkline, rgba


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
    """玻璃统计条：最低 / 最高 / 平均三列，浮在会话卡内的轻量小格。"""

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
        # 轻量玻璃格：5% 白填充、白 15% 描边、顶高光 / 底暗缘
        p.setPen(QPen(rgba(GLASS_WHITE, 38), 1.0))
        p.setBrush(rgba(GLASS_WHITE, 13))
        p.drawRoundedRect(rect, 16, 16)
        inset = rect.adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(rgba(GLASS_WHITE, 46), 1.0))
        p.drawLine(
            QPointF(inset.left() + 8, inset.top()),
            QPointF(inset.right() - 8, inset.top()),
        )
        p.setPen(QPen(rgba(NIGHT_DEEP, 90), 1.0))
        p.drawLine(
            QPointF(inset.left() + 8, inset.bottom()),
            QPointF(inset.right() - 8, inset.bottom()),
        )
        p.end()


class ShotThumb(QLabel):
    """截图缩略图：点击用系统默认看图程序打开原图。"""

    def __init__(self, path: str, width: int = 112, height: int = 72):
        super().__init__()
        self._path = str(path or "")
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "border: 1px solid rgba(255,255,255,0.24); border-radius: 10px;"
            "background: rgba(255,255,255,0.06);"
        )
        pixmap = QPixmap(self._path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                width - 6, height - 6,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(pixmap)
        else:
            self.setText("图片不可用")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))
        super().mousePressEvent(event)


def _shot_caption(shot: dict) -> str:
    day, hm = _ts_parts(shot.get("ts", 0))
    return f"{day[5:]} {hm} · {shot.get('bpm', '—')} BPM"


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

        events = [
            item for item in (record.get("state_events") or [])
            if isinstance(item, (list, tuple)) and len(item) >= 2
        ]
        if events:
            parts = []
            for item in events[-8:]:
                _, hm = _ts_parts(item[0])
                label = str(item[1])
                color = STATE_COLORS.get(label, MOON_STEEL)
                parts.append(f"{hm} <span style='color:{color};'>{label}</span>")
            more = " · 更早省略" if len(events) > 8 else ""
            state_line = QLabel("状态变化 · " + " → ".join(parts) + more)
            state_line.setObjectName("Sub")
            state_line.setTextFormat(Qt.TextFormat.RichText)
            state_line.setWordWrap(True)
            lay.addWidget(state_line)

        shots = [
            shot for shot in (record.get("screenshots") or [])
            if isinstance(shot, dict) and shot.get("path")
        ]
        if shots:
            shot_title = QLabel(f"高心率截屏 · {len(shots)} 张（点击查看原图）")
            shot_title.setObjectName("Sub")
            lay.addWidget(shot_title)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            for shot in shots[-4:]:
                thumb = ShotThumb(str(shot["path"]))
                state = str(shot.get("state") or "")
                thumb.setToolTip(
                    f"{_shot_caption(shot)}\n{state}\n{shot['path']}"
                )
                row.addWidget(thumb, 0)
            if len(shots) > 4:
                more_shots = QLabel(f"+{len(shots) - 4}")
                more_shots.setObjectName("Badge")
                row.addWidget(more_shots, 0)
            row.addStretch(1)
            lay.addLayout(row)


class ScreenshotGallery(BentoCard):
    """历史窗口顶部的高心率截图画廊：按时间倒序展示全部截图。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, object_name="ScreenshotGallery", radius=24.0)
        self._shots: list[dict] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        title = QLabel("高心率截屏")
        title.setObjectName("CardTitle")
        head.addWidget(title, 1)
        self._count = QLabel("0 张")
        self._count.setObjectName("Badge")
        head.addWidget(self._count, 0)
        folder_btn = RaisedButton("打开目录")
        folder_btn.setFixedWidth(96)
        folder_btn.clicked.connect(self._open_folder)
        head.addWidget(folder_btn, 0)
        lay.addLayout(head)

        tip = QLabel("点击缩略图查看原图；每张截图都按触发时的心率与时间命名")
        tip.setObjectName("Sub")
        lay.addWidget(tip)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        lay.addLayout(self._grid)
        self.hide()

    def set_shots(self, shots: list[dict] | None) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._shots = [
            dict(shot) for shot in (shots or [])
            if isinstance(shot, dict) and shot.get("path")
        ]
        self.setVisible(bool(self._shots))
        self._count.setText(f"{len(self._shots)} 张")
        for index, shot in enumerate(reversed(self._shots[-12:])):
            cell = QWidget()
            cell_lay = QVBoxLayout(cell)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setSpacing(4)
            thumb = ShotThumb(str(shot["path"]), 120, 78)
            thumb.setToolTip(
                f"{_shot_caption(shot)}\n{shot.get('state', '')}\n{shot['path']}"
            )
            cell_lay.addWidget(thumb, 0, Qt.AlignmentFlag.AlignHCenter)
            caption = QLabel(_shot_caption(shot))
            caption.setObjectName("Sub")
            caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cell_lay.addWidget(caption)
            self._grid.addWidget(cell, index // 4, index % 4)
        if len(self._shots) > 12:
            tail = QLabel(f"还有 {len(self._shots) - 12} 张，可在目录中查看")
            tail.setObjectName("Sub")
            self._grid.addWidget(tail, 3, 0, 1, 4)

    def _open_folder(self) -> None:
        if not self._shots:
            return
        path = Path(str(self._shots[-1].get("path", "")))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


class HistoryWindow(QDialog):
    """历史记录窗口：响应式便当盒网格，显示每次连接的汇总与心率曲线。"""

    deleteRequested = Signal(str)

    def __init__(
        self,
        sessions: list[dict] | None = None,
        parent: QWidget | None = None,
        shots: list[dict] | None = None,
    ):
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
        self.set_shots(shots)

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
        # 列表内容再长也只在滚动区内扩展，不能把底部按钮挤出可视区域。
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setMinimumHeight(120)
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
        self._gallery = ScreenshotGallery(container)
        body.addWidget(self._gallery)
        # 历史窗口默认 2 栏，最大化后可到 4 栏；间隙与其他窗口统一 16px
        self._cards_lay = BentoGrid(body.parent(), gap=16, wide=1100, medium=520)
        body.addWidget(self._cards_lay)

        footer = QWidget()
        footer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        footer.setFixedHeight(56)
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
        root._layout.setStretch(1, 1)  # 标题栏 / 滚动区 / 底栏中的滚动区独占伸缩
        root._layout.setStretch(2, 0)

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

    def set_shots(self, shots: list[dict] | None) -> None:
        """刷新高心率截屏画廊；没有截图时画廊自动隐藏。"""
        self._gallery.set_shots(shots or [])

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
