"""集中管理配色与全局样式（新拟物派 · Neumorphism light）。"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# ------------------------------------------------------------------ 新拟物派 token
BASE = "#e0e5ec"            # --color-base：页面与所有元素的共同基底
SHADOW_GREY = "#b8bcc2"     # --color-shadow-grey：右下阴影色
HIGHLIGHT = "#ffffff"       # --color-highlight：左上高光色
BLURPLE = "#3b82f6"         # 便当盒 Sky：主行动与选中态（旧名保留兼容）
CORAL = "#ff6b6b"           # --color-coral：警示与删除
MINT = "#4ecdc4"            # --color-mint：成功与数据正向
INK = "#3d4451"             # --color-text：深色文字只出现在内容层

ACCENT = BLURPLE            # 心率主色 / 激活态（紫罗兰）
ACCENT_SOFT = "#93c5fd"     # Sky 的柔和变体（光晕）
BG = BASE
CARD = BASE
CARD_ALT = BASE
BORDER = SHADOW_GREY
TEXT = INK
MUTED = "#6f7a90"           # 界面层中灰文字

GREEN = "#34d399"
AMBER = "#fbbf24"
RED = "#f87171"

# --------------------------------------------------------------- 便当盒 token
BENTO_SNOW = "#fafafa"          # 页面画布
BENTO_CARD = "#ffffff"          # 卡片填充
BENTO_INK = "#18181b"           # 锚点卡 / 主文字
BENTO_BORDER = "#f4f4f5"        # 极浅描边
BENTO_SKY = BLURPLE             # 主强调（沿用全局 ACCENT）
BENTO_VIOLET = "#8b5cf6"        # 渐变第二强调
BENTO_TANGERINE = "#f97316"     # 数据提醒（全屏最多一处）

ZONE_COLORS = {
    "静息": "#5aa9ff",
    "日常": "#34d399",
    "燃脂": "#fbbf24",
    "有氧": "#fb923c",
    "峰值": "#ff4d6d",
}

INTER_FONT = '"Inter", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'

QSS = f"""
/* 无边框窗口整体透明；新拟物卡片由自绘控件铺基底并画阴影 */
QMainWindow, QDialog, QFrame#CloseCard {{
    background: transparent;
}}
QWidget {{
    color: {INK};
}}
QFrame#Hero, QFrame#Card {{
    background: {BASE};
    border: none;
    border-radius: 24px;
}}
QFrame#DeviceRow {{
    background: {BENTO_SNOW};
    border: 1px solid {BENTO_BORDER};
    border-radius: 16px;
}}
QFrame#Divider {{
    background: {SHADOW_GREY};
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
    background: {BASE};
    color: {BLURPLE};
    border: none;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 500;
}}
QLabel#Battery {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 400;
}}
QPushButton {{
    background: {BASE};
    border: none;
    border-radius: 16px;
    padding: 6px 16px;
    color: {INK};
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:pressed {{
    background: #d5dbe8;
}}
QPushButton:disabled {{
    color: #9aa3b5;
    background: #d8deea;
}}
QPushButton#Primary {{
    background: {BLURPLE};
    border: none;
    border-radius: 16px;
    padding: 6px 16px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#Ghost {{
    background: {BASE};
    border: none;
    border-radius: 16px;
    color: {INK};
    font-size: 11px;
    font-weight: 500;
    padding: 4px 11px;
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
    background: {SHADOW_GREY};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #9aa3b5;
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
    background: {BASE};
    border: 2px solid {SHADOW_GREY};
    border-radius: 12px;
    padding: 6px 10px;
    color: {INK};
    font-size: 12px;
    selection-background-color: {BLURPLE};
}}
QLineEdit#RecessedInput:focus {{
    border-color: {BLURPLE};
}}
QComboBox {{
    background: {BASE};
    border: 2px solid {SHADOW_GREY};
    border-radius: 12px;
    padding: 5px 10px;
    color: {INK};
    font-size: 11px;
}}
QComboBox:hover, QComboBox:focus {{
    border-color: {BLURPLE};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {BASE};
    border: 1px solid {SHADOW_GREY};
    border-radius: 10px;
    color: {INK};
    selection-background-color: {BLURPLE};
    selection-color: #ffffff;
    padding: 4px;
}}
QSlider::groove:horizontal {{
    background: {SHADOW_GREY};
    height: 6px;
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {BLURPLE};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {BASE};
    border: 2px solid {SHADOW_GREY};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    border-color: {BLURPLE};
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
    background: {BASE};
    border: none;
    border-radius: 14px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 22px 6px 24px;
    border-radius: 8px;
}}
QMenu::item:selected {{
    background: rgba(59, 130, 246, 0.14);
    color: {BLURPLE};
}}
QMenu::separator {{
    height: 1px;
    background: {SHADOW_GREY};
    margin: 4px 8px;
}}
QToolTip {{
    background: {BASE};
    color: {INK};
    border: none;
    border-radius: 10px;
    padding: 4px 8px;
}}
"""

BUTTON_QSS = f"""
QPushButton {{
    background: {BASE};
    border: none;
    border-radius: 16px;
    padding: 6px 16px;
    color: {INK};
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #d8deea;
}}
QPushButton:pressed {{
    background: #d0d7e6;
}}
QPushButton:disabled {{
    color: #9aa3b5;
    background: #d8deea;
}}
QPushButton#Primary {{
    background: {BLURPLE};
    border: none;
    border-radius: 16px;
    padding: 6px 16px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
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
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    base_font = QFont()
    base_font.setFamilies(["Inter", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"])
    base_font.setPointSize(10)
    app.setFont(base_font)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BASE))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Base, QColor(BASE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BASE))
    palette.setColor(QPalette.ColorRole.Text, QColor(INK))
    palette.setColor(QPalette.ColorRole.Button, QColor(BASE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(BLURPLE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(BASE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(INK))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
