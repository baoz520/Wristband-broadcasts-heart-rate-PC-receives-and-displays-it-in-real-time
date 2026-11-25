"""自定义背景与对比度策略。

夜景默认背景由代码绘制；用户也可以选择纯色或本地图片。所有半透明玻璃
ui 都通过 Backdrop.paint() 取背景，再按背景亮度自动补一层暗罩，保证白字
与香槟金重点数字在浅色图片上依然可读。
"""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from .theme import CHAMPAGNE, MOONLIGHT, MOON_STEEL, NIGHT

MODES = ("night", "solid", "image")


class Backdrop:
    """全局背景状态（单例类，所有窗口共享）。"""

    mode = "night"
    color = "#0b1322"
    image_path = ""
    dim = 45

    _pixmap: QPixmap | None = None
    _pixmap_key = ""
    _brightness = 0.12

    @classmethod
    def configure(
        cls,
        mode: str | None = None,
        color: str | None = None,
        path: str | None = None,
        dim: int | None = None,
    ) -> None:
        if mode in MODES:
            cls.mode = mode
        if color:
            cls.color = color
        if path is not None:
            cls.image_path = path
        if dim is not None:
            cls.dim = max(0, min(100, int(dim)))
        cls._pixmap_key = ""
        cls._pixmap = None
        cls._brightness = cls._measure_brightness()

    @classmethod
    def _load_pixmap(cls) -> QPixmap | None:
        path = cls.image_path or ""
        if not path or not os.path.isfile(path):
            cls._pixmap = None
            return None
        try:
            key = f"{path}|{os.path.getmtime(path)}|{os.path.getsize(path)}"
        except OSError:
            key = path
        if key != cls._pixmap_key or cls._pixmap is None:
            pm = QPixmap(path)
            cls._pixmap = pm if not pm.isNull() else None
            cls._pixmap_key = key
        return cls._pixmap

    @classmethod
    def _measure_brightness(cls) -> float:
        """返回背景平均亮度 0–1，用于自动决定暗罩强度。"""
        if cls.mode == "solid":
            c = QColor(cls.color)
            if c.isValid():
                return c.lightness() / 255.0
            return 0.12
        if cls.mode == "image":
            pm = cls._load_pixmap()
            if pm is not None:
                img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
                small = img.scaled(
                    32, 32, Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                total = 0
                count = 0
                for y in range(small.height()):
                    for x in range(small.width()):
                        c = QColor(small.pixel(x, y))
                        if c.alpha() == 0:
                            continue
                        total += (
                            c.red() * 299 + c.green() * 587 + c.blue() * 114
                        ) // 1000
                        count += 1
                if count:
                    return total / (255.0 * count)
        return 0.12

    @classmethod
    def paint(cls, painter: QPainter, rect: QRectF) -> None:
        """在已裁剪的圆角区域内绘制背景与自动暗罩。"""
        r = QRectF(rect)
        painter.setPen(Qt.PenStyle.NoPen)

        if cls.mode == "night":
            painter.setBrush(QColor(NIGHT))
            painter.drawRect(r)
            base = max(r.width(), r.height())
            for cx, cy, scale, color, alpha in (
                (r.right() * 0.92, r.top() + r.height() * 0.06, 0.85, MOON_STEEL, 96),
                (r.left() + r.width() * 0.04, r.bottom() - r.height() * 0.04, 0.72, CHAMPAGNE, 60),
                (r.center().x(), r.bottom() + r.height() * 0.12, 0.60, MOONLIGHT, 52),
            ):
                grad = QRadialGradient(QPointF(cx, cy), base * scale)
                c0 = QColor(color)
                c0.setAlpha(alpha)
                c1 = QColor(color)
                c1.setAlpha(0)
                grad.setColorAt(0.0, c0)
                grad.setColorAt(1.0, c1)
                painter.setBrush(grad)
                painter.drawRect(r)
            return

        if cls.mode == "solid":
            painter.setBrush(QColor(cls.color))
            painter.drawRect(r)
        else:
            pm = cls._load_pixmap()
            if pm is not None and r.width() > 0 and r.height() > 0:
                # cover 模式铺满，不变形
                target_ratio = r.width() / r.height()
                src_ratio = pm.width() / pm.height()
                if src_ratio > target_ratio:
                    sw = pm.height() * target_ratio
                    sx = (pm.width() - sw) / 2.0
                    src = QRectF(sx, 0, sw, pm.height())
                else:
                    sh = pm.width() / target_ratio
                    sy = (pm.height() - sh) / 2.0
                    src = QRectF(0, sy, pm.width(), sh)
                painter.drawPixmap(r, pm, src)
            else:
                painter.setBrush(QColor(NIGHT))
                painter.drawRect(r)

        # 自动 + 手动暗罩：目标是把最终背景压到约 24% 亮度，
        # 再叠加用户可调的 dim（45 为中性）。
        brightness = cls._brightness
        auto = max(0.0, 1.0 - 0.24 / max(0.05, brightness))
        alpha = int(auto * 255 + (cls.dim - 45) * 1.8)
        alpha = max(0, min(215, alpha))
        if alpha:
            painter.fillRect(r, QColor(0, 0, 0, alpha))

    @classmethod
    def refresh_all(cls) -> None:
        app = QApplication.instance()
        if app is None:
            return
        for window in app.topLevelWidgets():
            window.update()
            for child in window.findChildren(QWidget):
                child.update()
