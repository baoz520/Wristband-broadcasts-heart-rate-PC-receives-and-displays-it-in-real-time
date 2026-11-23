"""开发用：离屏渲染界面截图（python tools/preview.py）。"""

from __future__ import annotations

import os
import sys
import time
from collections import deque
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from heartbeat.ble import DeviceInfo  # noqa: E402
from heartbeat.config import Settings  # noqa: E402
from heartbeat.floating import FloatingWindow  # noqa: E402
from heartbeat.main_window import MainWindow  # noqa: E402
from heartbeat.theme import apply_theme  # noqa: E402

OUT = ROOT / "screenshots"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication([])
    apply_theme(app)

    settings = Settings()
    settings.device_management = True
    settings.floating_visible = True

    window = MainWindow(settings)
    window.resize(466, 900)
    window.show()

    now = time.monotonic()
    samples = [70, 74, 80, 76, 72, 69, 73, 78, 82, 88, 84, 79, 76, 74,
               77, 81, 86, 90, 85, 80, 78, 75, 73, 76, 80, 84, 87, 83,
               79, 77, 75, 74, 78, 82, 86, 89, 85, 81, 78, 76]
    window._history = deque()

    devices = [
        DeviceInfo("C8:47:8C:1A:2B:3C", "Xiaomi Smart Band 8", -48, True, 76),
        DeviceInfo("F4:12:FA:9D:88:01", "HUAWEI Band 9", -63, True, None),
        DeviceInfo("D4:36:39:AA:10:7F", "Polar H10 9B2C", -71, True, None),
        DeviceInfo("5C:F3:70:22:90:AA", "Amazfit GTR 4", -79, False, None),
        DeviceInfo("00:1A:7D:DA:71:13", "未命名设备", -88, False, None),
    ]
    window.set_devices(devices)
    window.set_link("connected", "C8:47:8C:1A:2B:3C", "Xiaomi Smart Band 8")
    window.set_battery(82)
    window.push_hr(78, "心率服务")
    points = deque(
        (time.monotonic() - (len(samples) - i) * 1.5, bpm)
        for i, bpm in enumerate(samples)
    )
    window._spark._points = deque(points)
    window._history = deque(points)
    window._update_stats()
    window._spark.update()
    window._last_hr_time = time.monotonic() - 2
    window._refresh_hint()
    for msg in (
        "开始扫描附近的蓝牙设备",
        "正在连接 Xiaomi Smart Band 8（C8:47:8C:1A:2B:3C）",
        "已连接 Xiaomi Smart Band 8",
        "已订阅心率测量通知",
        "电量 82%",
    ):
        window.append_log(msg)

    app.processEvents()
    window.grab().save(str(OUT / "main.png"))

    floating = FloatingWindow()
    floating.set_link("connected", "C8:47:8C:1A:2B:3C", "Xiaomi Smart Band 8")
    floating.set_hr(78, "心率服务")
    floating.set_locked(False)
    floating.show()
    app.processEvents()

    canvas = QPixmap(640, 340)
    canvas.fill(QColor("#232a33"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, 0, 310, 340, QColor("#0b0f15"))
    painter.drawPixmap(330, 104, floating.grab())
    painter.end()
    canvas.save(str(OUT / "floating.png"))

    print("saved", OUT / "main.png", OUT / "floating.png")


if __name__ == "__main__":
    main()
