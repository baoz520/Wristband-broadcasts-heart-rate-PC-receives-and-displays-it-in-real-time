"""集中管理配色与全局样式。"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#ff4d6d"
ACCENT_SOFT = "#ff8fa3"
BG = "#0b0f15"
CARD = "#121820"
CARD_ALT = "#0e141d"
BORDER = "#1d2635"
TEXT = "#e9eef7"
MUTED = "#7f8ea3"
GREEN = "#34d399"
AMBER = "#fbbf24"
RED = "#f87171"

ZONE_COLORS = {
    "静息": "#5aa9ff",
    "日常": "#34d399",
    "燃脂": "#fbbf24",
    "有氧": "#fb923c",
    "峰值": "#ff4d6d",
}

QSS = f"""
QMainWindow, QDialog {{
    background: {BG};
}}
QWidget {{
    color: {TEXT};
}}
QLabel {{
    background: transparent;
}}
QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 18px;
}}
QFrame#Hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #1c1420, stop:0.55 #141820, stop:1 #10151d);
    border: 1px solid #2a2130;
    border-radius: 20px;
}}
QFrame#DeviceRow {{
    background: {CARD_ALT};
    border: 1px solid #1a2331;
    border-radius: 12px;
}}
QFrame#DeviceRow[connected="true"] {{
    background: #201521;
    border: 1px solid #4a2331;
}}
QFrame#Divider {{
    background: #1b2433;
    border: none;
    max-height: 1px;
    min-height: 1px;
}}
QLabel#H1 {{
    font-size: 17px;
    font-weight: 600;
}}
QLabel#H2 {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#Sub {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#CardTitle {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#StatLabel {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#StatValue {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#DeviceName {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#DeviceMeta {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#Empty {{
    color: {MUTED};
    font-size: 12px;
    padding: 18px 10px;
}}
QLabel#Pill {{
    border-radius: 11px;
    padding: 3px 10px;
    font-size: 11px;
}}
QLabel#Badge {{
    background: rgba(255, 77, 109, 0.13);
    color: #ff9aae;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
}}
QLabel#Battery {{
    color: {MUTED};
    font-size: 11px;
}}
QPushButton {{
    background: #1a2330;
    border: 1px solid #273245;
    border-radius: 9px;
    padding: 5px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: #223041;
}}
QPushButton:pressed {{
    background: #16202c;
}}
QPushButton:disabled {{
    color: #5b6879;
    background: #141b24;
    border-color: #1b2431;
}}
QPushButton#Primary {{
    background: {ACCENT};
    border: none;
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: #ff647f;
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid #2a3444;
    color: #c7d1df;
    font-size: 11px;
    padding: 4px 11px;
}}
QPushButton#Ghost:hover {{
    background: #1b2431;
}}
QPushButton#Danger {{
    background: transparent;
    border: 1px solid #48232f;
    color: #ff8fa3;
    font-size: 11px;
    padding: 4px 11px;
}}
QPushButton#Danger:hover {{
    background: #2a1720;
}}
QPushButton#Tiny {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 2px 4px;
}}
QPushButton#Tiny:hover {{
    color: {ACCENT_SOFT};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2a3546;
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3a475c;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
    background: transparent;
}}
QPlainTextEdit#Log {{
    background: #0b1118;
    border: 1px solid #17202c;
    border-radius: 10px;
    color: #8c9aad;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 10px;
    padding: 6px;
    selection-background-color: #3a2230;
}}
QPlainTextEdit#Log QScrollBar:vertical {{
    width: 4px;
}}
QMenu {{
    background: #161d27;
    border: 1px solid #273245;
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 22px 6px 24px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: #232f40;
}}
QMenu::separator {{
    height: 1px;
    background: #273245;
    margin: 4px 8px;
}}
QToolTip {{
    background: #1b2431;
    color: {TEXT};
    border: 1px solid #2b394d;
    padding: 4px 8px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    base_font = QFont()
    base_font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"])
    base_font.setPointSize(9)
    app.setFont(base_font)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(CARD_ALT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(CARD))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor("#1a2330"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1b2431"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
