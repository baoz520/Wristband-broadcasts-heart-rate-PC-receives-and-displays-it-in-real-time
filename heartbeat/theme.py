"""集中管理配色与全局样式（玻璃拟态 · Glassmorphism dark）。

玻璃拟态的本质是光学：夜景底 + 大半径柔光斑提供可模糊的内容，面板本身
只用 8%–14% 的白，靠顶边白色内高光 / 底边深色内暗缘 / 外层深阴影三层
同时存在读出厚度。全站唯一强调色是香槟金，只给主 CTA 与关键数字。
旧 token 名保留兼容，色值全部收敛到这套夜景色板。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# ------------------------------------------------------------------ 玻璃拟态 token
NIGHT_DEEP = "#060a13"          # 最深一层底
NIGHT = "#0b1322"               # 默认页面底
NIGHT_STEEL = "#16233a"         # 次级面板 / 输入框底
MOON_STEEL = "#33517a"          # 结构线 / 图表对比
MOONLIGHT = "#7c9cc4"           # 高光文字 / 图标 / 数据点
CHAMPAGNE = "#e4b863"           # 全站唯一强调：主 CTA 与关键数字
GLASS_WHITE = "#ffffff"         # 玻璃填充与描边的来源（始终带 alpha）

# 兼容旧模块名的别名：旧名保留，色值换成夜景玻璃色板
BASE = NIGHT_STEEL
SHADOW_GREY = MOON_STEEL
HIGHLIGHT = GLASS_WHITE
BLURPLE = CHAMPAGNE
CORAL = "#f87171"               # 危险操作：柔和红，不作强调
MINT = "#34d399"
INK = GLASS_WHITE

ACCENT = CHAMPAGNE              # 心率主色 / 关键数字
ACCENT_SOFT = MOONLIGHT
BG = NIGHT
CARD = NIGHT_STEEL
CARD_ALT = NIGHT
BORDER = GLASS_WHITE
TEXT = GLASS_WHITE
MUTED = MOONLIGHT

GREEN = "#34d399"
AMBER = CHAMPAGNE
RED = "#f87171"

# 便当盒时代的名字继续保留，供组件与测试引用
BENTO_SNOW = NIGHT
BENTO_CARD = NIGHT_STEEL
BENTO_INK = GLASS_WHITE
BENTO_BORDER = GLASS_WHITE      # 玻璃描边基准色，实际用 15% alpha
BENTO_EDGE = GLASS_WHITE
BENTO_EDGE_HOVER = CHAMPAGNE
BENTO_SKY = CHAMPAGNE
BENTO_VIOLET = MOONLIGHT
BENTO_TANGERINE = CHAMPAGNE

ZONE_COLORS = {
    "静息": "#7c9cc4",
    "日常": "#8fb8d8",
    "燃脂": CHAMPAGNE,
    "有氧": "#f0a35e",
    "峰值": "#f87171",
}

INTER_FONT = (
    '"Inter", "SF Pro Display", "PingFang SC", "Microsoft YaHei UI", '
    '"Microsoft YaHei", "Segoe UI", sans-serif'
)

QSS = f"""
/* 无边框窗口整体透明；夜景底与光斑由 BentoRootPanel 自绘 */
QMainWindow, QDialog, QFrame#CloseCard {{
    background: transparent;
}}
QWidget {{
    color: {GLASS_WHITE};
    font-family: {INTER_FONT};
}}
QFrame#Hero, QFrame#Card, QFrame#DeviceRow {{
    background: transparent;
    border: none;
}}
QFrame#Divider {{
    background: rgba(255, 255, 255, 0.10);
    border: none;
    max-height: 1px;
    min-height: 1px;
}}
QLabel#H1 {{
    font-size: 20px;
    font-weight: 600;
    color: {GLASS_WHITE};
}}
QLabel#H2 {{
    font-size: 14px;
    font-weight: 500;
    color: {GLASS_WHITE};
}}
QLabel#Sub {{
    color: {MOONLIGHT};
    font-size: 12px;
    font-weight: 400;
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {GLASS_WHITE};
}}
/* 锚点卡上的次级文字统一月光钢，主数字由调用处着香槟金 */
QFrame#BentoAnchor QLabel#CardTitle,
QFrame#BentoAnchor QLabel#Sub,
QFrame#BentoAnchor QLabel#Battery {{
    color: {MOONLIGHT};
}}
QFrame#BentoAnchor QLabel#StatValue {{
    color: {GLASS_WHITE};
}}
QLabel#StatLabel {{
    color: {MOONLIGHT};
    font-size: 12px;
    font-weight: 500;
}}
QLabel#StatValue {{
    font-size: 28px;
    font-weight: 600;
    color: {GLASS_WHITE};
}}
QLabel#DeviceName {{
    font-size: 14px;
    font-weight: 500;
    color: {GLASS_WHITE};
}}
QLabel#DeviceMeta {{
    color: {MOONLIGHT};
    font-size: 12px;
    font-weight: 400;
}}
QLabel#Empty {{
    color: {MOONLIGHT};
    font-size: 14px;
    font-weight: 400;
    padding: 18px 10px;
}}
QLabel#Pill {{
    border-radius: 999px;
    padding: 4px 12px;
}}
QLabel#Badge {{
    background: rgba(255, 255, 255, 0.08);
    color: {MOONLIGHT};
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
}}
QLabel#Battery {{
    color: {MOONLIGHT};
    font-size: 12px;
    font-weight: 400;
}}
/* 原生按钮兜底样式；主要按钮由 RaisedButton 自绘玻璃 / 香槟金 CTA */
QPushButton {{
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 16px;
    padding: 8px 18px;
    color: {GLASS_WHITE};
    font-size: 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.30);
}}
QPushButton:pressed {{
    background: rgba(255, 255, 255, 0.10);
}}
QPushButton:disabled {{
    color: {MOON_STEEL};
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.08);
}}
QPushButton#Primary {{
    background: {CHAMPAGNE};
    border: none;
    border-radius: 999px;
    padding: 14px 28px;
    color: {NIGHT_DEEP};
    font-size: 16px;
    font-weight: 600;
}}
QPushButton#Ghost {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    color: {MOONLIGHT};
    font-size: 12px;
    font-weight: 500;
    padding: 6px 12px;
}}
QPushButton#Tiny {{
    background: transparent;
    border: none;
    color: {MOONLIGHT};
    padding: 2px 4px;
}}
QPushButton#Tiny:hover {{
    color: {CHAMPAGNE};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
/* 滚动条：深夜轨 + 月光钢圆角滑块，hover / pressed 三态 */
QScrollBar:vertical {{
    background: rgba(255, 255, 255, 0.03);
    width: 9px;
    margin: 3px 1px 3px 0;
    border-radius: 4px;
}}
QScrollBar::groove:vertical {{
    background: transparent;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {MOON_STEEL};
    border-radius: 4px;
    min-height: 32px;
    margin: 0 1px;
}}
QScrollBar::handle:vertical:hover {{
    background: {MOONLIGHT};
}}
QScrollBar::handle:vertical:pressed {{
    background: {CHAMPAGNE};
}}
QScrollBar:horizontal {{
    background: rgba(255, 255, 255, 0.03);
    height: 9px;
    margin: 0 3px 1px 3px;
    border-radius: 4px;
}}
QScrollBar::groove:horizontal {{
    background: transparent;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {MOON_STEEL};
    border-radius: 4px;
    min-width: 32px;
    margin: 1px 0;
}}
QScrollBar::handle:horizontal:hover {{
    background: {MOONLIGHT};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {CHAMPAGNE};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    height: 0px;
    width: 0px;
    background: transparent;
    border: none;
}}
QPlainTextEdit#Log {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    color: {MOONLIGHT};
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
    padding: 8px;
}}
QPlainTextEdit#Log QScrollBar:vertical,
QListWidget#SessionList QScrollBar:vertical {{
    width: 7px;
    margin: 4px 1px 4px 0;
}}
QPlainTextEdit#Log QScrollBar::handle:vertical,
QListWidget#SessionList QScrollBar::handle:vertical {{
    background: {MOON_STEEL};
    border-radius: 3px;
    min-height: 28px;
    margin: 0 1px;
}}
QPlainTextEdit#Log QScrollBar::handle:vertical:hover,
QListWidget#SessionList QScrollBar::handle:vertical:hover {{
    background: {MOONLIGHT};
}}
QLineEdit#RecessedInput {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 14px;
    padding: 12px 16px;
    color: {GLASS_WHITE};
    font-size: 14px;
    selection-background-color: {CHAMPAGNE};
    selection-color: {NIGHT_DEEP};
}}
QLineEdit#RecessedInput:focus {{
    border: 2px solid rgba(255, 255, 255, 0.40);
    padding: 11px 15px;
}}
QComboBox {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 14px;
    padding: 8px 12px;
    color: {GLASS_WHITE};
    font-size: 12px;
}}
QComboBox:hover, QComboBox:focus {{
    border-color: rgba(255, 255, 255, 0.40);
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {NIGHT_STEEL};
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 14px;
    color: {GLASS_WHITE};
    selection-background-color: rgba(228, 184, 99, 0.22);
    selection-color: {CHAMPAGNE};
    padding: 4px;
}}
QSlider::groove:horizontal {{
    background: rgba(255, 255, 255, 0.10);
    height: 5px;
    border-radius: 3px;
    margin: 2px 0;
}}
QSlider::sub-page:horizontal {{
    background: {CHAMPAGNE};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {GLASS_WHITE};
    border: 1px solid rgba(255, 255, 255, 0.30);
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {CHAMPAGNE};
    border-color: {CHAMPAGNE};
}}
QSlider::handle:horizontal:pressed {{
    background: {GLASS_WHITE};
}}
QListWidget#SessionList {{
    background: transparent;
    border: none;
}}
QListWidget#SessionList::item {{
    padding: 3px 6px;
    border-radius: 8px;
    color: {MOONLIGHT};
}}
QListWidget#SessionList::item:selected {{
    background: rgba(228, 184, 99, 0.16);
    color: {CHAMPAGNE};
}}
QTableWidget {{
    background: transparent;
    border: none;
    color: {GLASS_WHITE};
    selection-background-color: rgba(228, 184, 99, 0.18);
    selection-color: {CHAMPAGNE};
}}
QHeaderView::section {{
    background: rgba(255, 255, 255, 0.04);
    border: none;
    color: {MOONLIGHT};
    font-size: 11px;
    padding: 6px;
}}
QMenu {{
    background: {NIGHT_STEEL};
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 14px;
    padding: 6px;
    color: {GLASS_WHITE};
}}
QMenu::item {{
    padding: 6px 22px 6px 24px;
    border-radius: 8px;
}}
QMenu::item:selected {{
    background: rgba(228, 184, 99, 0.18);
    color: {CHAMPAGNE};
}}
QMenu::separator {{
    height: 1px;
    background: rgba(255, 255, 255, 0.10);
    margin: 4px 8px;
}}
QToolTip {{
    background: {NIGHT_STEEL};
    color: {GLASS_WHITE};
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    padding: 6px 10px;
}}
"""

BUTTON_QSS = f"""
QPushButton {{
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 16px;
    padding: 8px 18px;
    color: {GLASS_WHITE};
    font-size: 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.30);
}}
QPushButton:disabled {{
    color: {MOON_STEEL};
    background: rgba(255, 255, 255, 0.04);
}}
QPushButton#Primary {{
    background: {CHAMPAGNE};
    border: none;
    border-radius: 999px;
    padding: 14px 28px;
    color: {NIGHT_DEEP};
}}
QPushButton#Tiny {{
    background: transparent;
    border: none;
    color: {MOONLIGHT};
    padding: 2px 4px;
}}
QPushButton#Tiny:hover {{
    color: {CHAMPAGNE};
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    base_font = QFont()
    base_font.setFamilies([
        "Inter", "SF Pro Display", "PingFang SC", "Microsoft YaHei UI",
        "Microsoft YaHei", "Segoe UI",
    ])
    base_font.setPointSize(10)
    app.setFont(base_font)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(NIGHT))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(GLASS_WHITE))
    palette.setColor(QPalette.ColorRole.Base, QColor(NIGHT_STEEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(NIGHT))
    palette.setColor(QPalette.ColorRole.Text, QColor(GLASS_WHITE))
    palette.setColor(QPalette.ColorRole.Button, QColor(NIGHT_STEEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(GLASS_WHITE))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(CHAMPAGNE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(NIGHT_DEEP))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(NIGHT_STEEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(GLASS_WHITE))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(MOON_STEEL))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
