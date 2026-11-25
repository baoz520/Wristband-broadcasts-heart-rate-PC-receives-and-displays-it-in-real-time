"""进程选择器：列出当前所有运行进程，让用户直接挑出游戏进程。

选中后把 ``进程名=显示名`` 写进设置的自定义清单，游戏检测器会立即采用
（自定义清单优先级高于内置表与排除项）。
"""

from __future__ import annotations

from PySide6.QtCore import QFileInfo, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileIconProvider,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .chrome import BentoRootPanel, TitleBar
from .game import GENERIC_FOLDERS, _pretty_name, match_game, scan_processes
from .widgets import BentoCard, BentoGrid, RaisedButton


def suggest_display(name: str, exe: str) -> str:
    """根据内置表 / 安装路径给一个默认显示名，用户可在对话框里改。"""
    stem = (name or "").removesuffix(".exe").strip() or "游戏"
    # 已知游戏直接用内置展示名，例如 cs2.exe -> Counter-Strike 2
    known = match_game(name, exe=exe)
    if known and known.lower() != stem.lower():
        return known
    if exe:
        from pathlib import PureWindowsPath

        path = PureWindowsPath(exe.replace("/", "\\"))
        parts = [p for p in path.parts if p and p != path.drive]
        parent = parts[-2] if len(parts) >= 2 else ""
        generic = GENERIC_FOLDERS | {"application", "app", "files", "program files"}
        for candidate in (parent, stem):
            if candidate.lower().strip() in generic:
                continue
            pretty = _pretty_name(candidate)
            if pretty:
                return pretty
    return stem


class ProcessPickerDialog(QDialog):
    """运行进程列表对话框；选中进程后发出 processSelected。"""

    processSelected = Signal(str, str)  # 进程名（含 .exe）, 显示名

    def __init__(self, parent: QWidget | None = None, existing: list[str] | None = None):
        super().__init__(parent)
        self.selected_process: tuple[str, str] | None = None
        self._rows: list[tuple[int, str, str]] = []
        self._existing = {
            (item or "").split("=", 1)[0].strip().lower().removesuffix(".exe")
            for item in (existing or [])
            if (item or "").strip()
        }
        self.setWindowTitle("选择游戏进程")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(720, 600)
        self.setMinimumSize(520, 400)
        self._build_ui()
        self._load_processes()

    # ------------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(BentoRootPanel(self))
        root = self.layout().itemAt(0).widget()

        bar = TitleBar("选择游戏进程", "从当前运行的进程里挑出游戏")
        bar._min_button.hide()
        bar._max_button.hide()
        bar.closeClicked.connect(self.reject)
        root.addWidget(bar)

        # 三张玻璃卡：搜索 / 进程表 / 显示名，统一 16px 间隙
        grid = BentoGrid(root, gap=16, wide=1100, medium=560)
        root._layout.addWidget(grid, 1)

        search_card = BentoCard()
        sl = QVBoxLayout(search_card)
        sl.setContentsMargins(24, 18, 24, 18)
        sl.setSpacing(8)
        tip = QLabel("搜索进程名或安装路径，双击即可添加；添加后立刻被识别为游戏。")
        tip.setObjectName("Sub")
        sl.addWidget(tip)
        self._search = QLineEdit()
        self._search.setObjectName("RecessedInput")
        self._search.setPlaceholderText("搜索进程，例如 cs2、原神、Game")
        self._search.textChanged.connect(self._filter)
        sl.addWidget(self._search)

        table_card = BentoCard()
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(12, 12, 12, 12)
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["进程", "PID", "安装路径"])
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            "QTableWidget { background: transparent; border: none; "
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 12px; color: #ffffff; "
            "selection-background-color: rgba(228,184,99,0.18); selection-color: #e4b863; }"
            "QHeaderView::section { background: rgba(255,255,255,0.04); border: none; "
            "color: #7c9cc4; font-size: 11px; padding: 6px; }"
            "QTableWidget::item { padding: 4px 6px; border: none; }"
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(lambda *_: self._accept())
        tl.addWidget(self._table)

        name_card = BentoCard()
        nl = QVBoxLayout(name_card)
        nl.setContentsMargins(24, 18, 24, 18)
        nl.setSpacing(8)
        name_label = QLabel("显示名称")
        name_label.setObjectName("H2")
        nl.addWidget(name_label)
        self._display_edit = QLineEdit()
        self._display_edit.setObjectName("RecessedInput")
        self._display_edit.setPlaceholderText("游戏中显示的名字，可修改")
        nl.addWidget(self._display_edit)

        placements = [
            (search_card, 0, 0, 1, 2),
            (table_card, 1, 0, 2, 2),
            (name_card, 3, 0, 1, 2),
        ]
        wide_placements = [
            (search_card, 0, 0, 1, 4),
            (table_card, 1, 0, 3, 4),
            (name_card, 4, 0, 1, 4),
        ]
        grid.set_placements({4: wide_placements, 2: placements, 1: placements})

        footer = QHBoxLayout()
        footer.setContentsMargins(16, 4, 16, 14)
        footer.setSpacing(12)
        footer.addStretch(1)
        cancel = RaisedButton("取消")
        cancel.setFixedWidth(96)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        ok = RaisedButton("添加为游戏")
        ok.setProperty("action", True)
        ok.setFixedWidth(140)
        ok.clicked.connect(self._accept)
        footer.addWidget(ok)
        root.addLayout(footer)

    # ------------------------------------------------------------------ 数据
    def _load_processes(self) -> None:
        try:
            processes, _, _ = scan_processes()
        except Exception:
            processes = []
        # 进程名优先、PID 次之，方便找刚启动的游戏
        processes = sorted(processes, key=lambda row: (row[1].lower(), row[0]))
        self._rows = list(processes)
        provider = QFileIconProvider()
        self._table.setRowCount(len(self._rows))
        for row, (pid, name, exe) in enumerate(self._rows):
            normalized = name.lower().removesuffix(".exe")
            label = name
            if normalized in self._existing:
                label = f"{name}（已添加）"
            icon = provider.icon(QFileInfo(exe)) if exe else None
            if icon is not None and icon.isNull():
                icon = None
            cell = QTableWidgetItem(icon, label) if icon else QTableWidgetItem(label)
            cell.setData(Qt.ItemDataRole.UserRole, row)
            cell.setToolTip(exe or name)
            self._table.setItem(row, 0, cell)
            pid_cell = QTableWidgetItem(str(pid))
            pid_cell.setData(Qt.ItemDataRole.UserRole, row)
            self._table.setItem(row, 1, pid_cell)
            path_cell = QTableWidgetItem(exe or "—")
            path_cell.setData(Qt.ItemDataRole.UserRole, row)
            path_cell.setToolTip(exe)
            self._table.setItem(row, 2, path_cell)
        self._filter()
        if self._table.rowCount():
            self._table.selectRow(0)

    def _filter(self) -> None:
        keyword = (self._search.text() or "").strip().lower()
        for row, (_, name, exe) in enumerate(self._rows):
            haystack = f"{name} {exe}".lower()
            self._table.setRowHidden(row, bool(keyword) and keyword not in haystack)

    def _on_selection_changed(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        _, name, exe = self._rows[row]
        self._display_edit.setText(suggest_display(name, exe))

    def _accept(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        _, name, _ = self._rows[row]
        display = (self._display_edit.text() or "").strip() or suggest_display(name, "")
        self.selected_process = (name, display)
        self.processSelected.emit(name, display)
        self.accept()

    def center_on(self, widget: QWidget | None) -> None:
        reference = widget.frameGeometry() if widget is not None else self.frameGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(reference.center())
        self.move(geo.topLeft())
