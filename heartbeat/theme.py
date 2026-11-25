"""集中管理配色与全局样式（便当盒布局 · Bento grid light）。

画布 Snow `#fafafa`、卡片 Card White `#ffffff`、主文字 Ink `#18181b`；
层级只由卡片尺寸与极淡描边承担。旧的新拟物 token 名保留兼容，
但色值全部收敛到便当盒色板，避免不同窗口出现两套材质。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# ------------------------------------------------------------------ 便当盒 token
BENTO_SNOW = "#fafafa"          # --color-snow：页面画布
BENTO_CARD = "#ffffff"          # --color-card：卡片填充
BENTO_INK = "#18181b"           # --color-ink：标题 / 主按钮 / 锚点卡
BENTO_BORDER = "#f4f4f5"        # 极浅描边
BENTO_SKY = "#3b82f6"           # 主强调与图标底
BENTO_VIOLET = "#8b5cf6"        # 渐变锚点第二强调
BENTO_TANGERINE = "#f97316"     # 数据与提醒（全屏最多一处）

# 兼容旧模块名的别名：控件表面改成白卡，阴影收敛成极淡冷灰。
BASE = BENTO_CARD
SHADOW_GREY = "#e4e4e7"
HIGHLIGHT = "#ffffff"
BLURPLE = BENTO_SKY
CORAL = BENTO_TANGERINE
MINT = "#34d399"
INK = BENTO_INK

ACCENT = BLURPLE               # 心率主色 / 激活态
ACCENT_SOFT = "#93c5fd"        # Sky 的柔和变体（光晕）
BG = BENTO_SNOW
CARD = BENTO_CARD
CARD_ALT = BENTO_SNOW
BORDER = BENTO_BORDER
TEXT = INK
MUTED = "#71717a"              # 次级文字

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

INTER_FONT = '"Inter", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'

QSS = f"""
/* 无边框窗口整体透明；卡片由 BentoCard 自绘，画布统一 Snow */
QMainWindow, QDialog, QFrame#CloseCard {{
    background: transparent;
}}
QWidget {{
    color: {INK};
    font-family: {INTER_FONT};
}}
QFrame#Hero, QFrame#Card {{
    background: {BENTO_CARD};
    border: 1px solid {BENTO_BORDER};
    border-radius: 24px;
}}
QFrame#DeviceRow {{
    background: {BENTO_CARD};
    border: 1px solid {BENTO_BORDER};
    border-radius: 16px;
}}
QFrame#Divider {{
    background: {BENTO_BORDER};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}
QLabel#H1 {{
    font-size: 20px;
    font-weight: 600;
    color: {INK};
}}
QLabel#H2 {{
    font-size: 14px;
    font-weight: 600;
    color: {INK};
}}
QLabel#Sub {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 400;
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {INK};
}}
/* 便当盒锚点卡：墨黑底上的文字统一转亮色 */
QFrame#BentoAnchor QLabel#StatLabel,
QFrame#BentoAnchor QLabel#Sub,
QFrame#BentoAnchor QLabel#Battery {{
    color: rgba(255, 255, 255, 0.65);
}}
QFrame#BentoAnchor QLabel#StatValue {{
    color: {BENTO_CARD};
}}
QLabel#StatLabel {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 400;
}}
QLabel#StatValue {{
    font-size: 16px;
    font-weight: 600;
    color: {INK};
}}
QLabel#DeviceName {{
    font-size: 14px;
    font-weight: 600;
    color: {INK};
}}
QLabel#DeviceMeta {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 400;
}}
QLabel#Empty {{
    color: {MUTED};
    font-size: 14px;
    font-weight: 400;
    padding: 18px 10px;
}}
QLabel#Pill {{
    border-radius: 999px;
    padding: 4px 12px;
}}
QLabel#Badge {{
    background: {BENTO_SNOW};
    color: {BENTO_SKY};
    border: 1px solid {BENTO_BORDER};
    border-radius: 12px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 500;
}}
QLabel#Battery {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 400;
}}
/* 便当盒卡片内操作：墨黑填充、白字、12px 圆角、按下轻微缩放由自绘按钮承担 */
QPushButton {{
    background: {BENTO_INK};
    border: none;
    border-radius: 12px;
    padding: 8px 18px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: rgba(24, 24, 27, 0.80);
}}
QPushButton:pressed {{
    background: {BENTO_INK};
}}
QPushButton:disabled {{
    color: #a1a1aa;
    background: {BENTO_BORDER};
}}
QPushButton#Primary {{
    background: {BENTO_SKY};
    border-radius: 12px;
    padding: 8px 18px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#Ghost {{
    background: {BENTO_SNOW};
    border: 1px solid {BENTO_BORDER};
    border-radius: 12px;
    color: {INK};
    font-size: 12px;
    font-weight: 500;
    padding: 6px 12px;
}}
QPushButton#Tiny {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 2px 4px;
}}
QPushButton#Tiny:hover {{
    color: {BLURPLE};
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
    background: #d4d4d8;
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #a1a1aa;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0px;
    background: transparent;
}}
QPlainTextEdit#Log {{
    background: {BENTO_SNOW};
    border: 1px solid {BENTO_BORDER};
    border-radius: 12px;
    color: {MUTED};
    font-family: "Cascadia Mono", "Consolas";
    font-size: 10px;
    padding: 6px;
}}
QLineEdit#RecessedInput {{
    background: {BENTO_CARD};
    border: 1px solid #e4e4e7;
    border-radius: 12px;
    padding: 8px 12px;
    color: {INK};
    font-size: 14px;
    selection-background-color: {BENTO_SKY};
}}
QLineEdit#RecessedInput:focus {{
    border-color: {BENTO_SKY};
}}
QComboBox {{
    background: {BENTO_CARD};
    border: 1px solid #e4e4e7;
    border-radius: 12px;
    padding: 6px 12px;
    color: {INK};
    font-size: 12px;
}}
QComboBox:hover, QComboBox:focus {{
    border-color: {BENTO_SKY};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {BENTO_CARD};
    border: 1px solid {BENTO_BORDER};
    border-radius: 12px;
    color: {INK};
    selection-background-color: {BENTO_SKY};
    selection-color: #ffffff;
    padding: 4px;
}}
QSlider::groove:horizontal {{
    background: #e4e4e7;
    height: 6px;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {BENTO_SKY};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {BENTO_CARD};
    border: 1px solid #d4d4d8;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    border-color: {BENTO_SKY};
}}
QPlainTextEdit#Log QScrollBar:vertical {{
    width: 4px;
}}
QListWidget#SessionList {{
    background: transparent;
    border: none;
}}
QListWidget#SessionList::item {{
    padding: 3px 6px;
}}
QMenu {{
    background: {BENTO_CARD};
    border: 1px solid {BENTO_BORDER};
    border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 22px 6px 24px;
    border-radius: 8px;
}}
QMenu::item:selected {{
    background: rgba(59, 130, 246, 0.12);
    color: {BENTO_SKY};
}}
QMenu::separator {{
    height: 1px;
    background: {BENTO_BORDER};
    margin: 4px 8px;
}}
QToolTip {{
    background: {BENTO_CARD};
    color: {INK};
    border: 1px solid {BENTO_BORDER};
    border-radius: 12px;
    padding: 6px 10px;
}}
"""

BUTTON_QSS = f"""
QPushButton {{
    background: {BENTO_INK};
    border: none;
    border-radius: 12px;
    padding: 8px 18px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: rgba(24, 24, 27, 0.80);
}}
QPushButton:pressed {{
    background: {BENTO_INK};
}}
QPushButton:disabled {{
    color: #a1a1aa;
    background: {BENTO_BORDER};
}}
QPushButton#Primary {{
    background: {BENTO_SKY};
    border-radius: 12px;
    color: #ffffff;
}}
QPushButton#Tiny {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 2px 4px;
}}
QPushButton#Tiny:hover {{
    color: {BENTO_SKY};
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    base_font = QFont()
    base_font.setFamilies(["Inter", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"])
    base_font.setPointSize(10)
    app.setFont(base_font)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BENTO_SNOW))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Base, QColor(BENTO_CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BENTO_SNOW))
    palette.setColor(QPalette.ColorRole.Text, QColor(INK))
    palette.setColor(QPalette.ColorRole.Button, QColor(BENTO_CARD))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(BENTO_SKY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(BENTO_CARD))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(INK))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
