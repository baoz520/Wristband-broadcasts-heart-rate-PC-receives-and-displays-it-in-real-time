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

from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from heartbeat.backdrop import Backdrop  # noqa: E402
from heartbeat.ble import DeviceInfo  # noqa: E402
from heartbeat.config import Settings  # noqa: E402
from heartbeat.floating import FloatingWindow  # noqa: E402
from heartbeat.history_window import HistoryWindow  # noqa: E402
from heartbeat.hr import HeartState  # noqa: E402
from heartbeat.main_window import MainWindow  # noqa: E402
from heartbeat.settings_window import SettingsWindow  # noqa: E402
from heartbeat.theme import apply_theme  # noqa: E402

OUT = ROOT / "screenshots"
PREVIEW_STATE = HeartState("兴奋", "#f0a35e", delta=24.0, baseline=66.0, trend=18.0)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication([])
    apply_theme(app)

    # 演示用高心率截图：不触碰用户真实截图目录
    shot_path = OUT / "demo_high_hr_capture.png"
    shot_canvas = QPixmap(480, 300)
    sp = QPainter(shot_canvas)
    shot_grad = QLinearGradient(0, 0, 480, 300)
    shot_grad.setColorAt(0.0, QColor("#2b3242"))
    shot_grad.setColorAt(1.0, QColor("#101725"))
    sp.fillRect(shot_canvas.rect(), QBrush(shot_grad))
    sp.setPen(QColor("#e4b863"))
    sp.drawText(28, 44, "HEART RATE ALERT")
    sp.setPen(QColor("#ffffff"))
    sp.drawText(28, 92, "148 BPM")
    sp.drawText(28, 128, "状态：兴奋")
    sp.end()
    shot_canvas.save(str(shot_path))
    now_ts = int(time.time())
    demo_shots = [
        {
            "ts": now_ts - 8 * 3600 + 600,
            "path": str(shot_path),
            "bpm": 148,
            "state": "兴奋",
            "device": "Xiaomi Smart Band 8",
            "session": f"C8:47:8C:1A:2B:3C|{now_ts - 8 * 3600}",
        },
        {
            "ts": now_ts - 2 * 3600 + 480,
            "path": str(shot_path),
            "bpm": 152,
            "state": "紧张",
            "device": "Counter-Strike 2",
            "session": f"game:cs2|{now_ts - 2 * 3600}",
        },
    ]

    settings = Settings()
    settings.device_management = True
    settings.floating_visible = True

    window = MainWindow(settings)
    window.resize(980, 820)
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
    window.push_hr(78, "心率服务", state=PREVIEW_STATE)
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

    window.layout().activate()
    QTest.qWait(320)  # 等待窗口淡入结束
    app.processEvents()
    app.processEvents()
    window.grab().save(str(OUT / "main.png"))

    # 窄屏退化：2 栏网格，保留同样的 16px 间隙与卡片顺序
    window.resize(720, 900)
    app.processEvents()
    app.processEvents()
    window.grab().save(str(OUT / "main_narrow.png"))
    window.resize(980, 820)
    app.processEvents()

    floating = FloatingWindow()
    floating.set_link("connected", "C8:47:8C:1A:2B:3C", "Xiaomi Smart Band 8")
    floating.set_hr(78, "心率服务", state=PREVIEW_STATE)
    floating.set_locked(False)
    floating.show()
    QTest.qWait(260)
    app.processEvents()

    canvas = QPixmap(640, 340)
    canvas.fill(QColor("#232a33"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, 0, 310, 340, QColor("#0b0f15"))
    painter.drawPixmap(330, 104, floating.grab())
    painter.end()
    canvas.save(str(OUT / "floating.png"))

    # 悬浮窗游戏态：隐藏拟物底板，只保留亮色数据悬在游戏画面上
    floating.set_game_display_mode("transparent")
    floating.set_game_info("Counter-Strike 2", bpm=118, low=78, high=148)
    app.processEvents()
    game_canvas = QPixmap(640, 340)
    game_canvas.fill(QColor("#1d2b3a"))
    gp = QPainter(game_canvas)
    gp.setRenderHint(QPainter.RenderHint.Antialiasing)
    gp.fillRect(0, 0, 640, 170, QColor("#2c4358"))
    gp.drawPixmap(330, 104, floating.grab())
    gp.end()
    game_canvas.save(str(OUT / "floating_game.png"))
    floating.set_game_info("")

    # 历史记录窗口：演示三次连接的汇总曲线
    demo_sessions = [
        {
            "address": "C8:47:8C:1A:2B:3C", "name": "Xiaomi Smart Band 8",
            "start": int(time.time() - 8 * 3600), "end": int(time.time() - 8 * 3600 + 42 * 60),
            "min": 61, "max": 148, "avg": 88.4, "samples": 210,
            "series": [
                [int(time.time() - 8 * 3600) + i * 12,
                 72 + int(28 * (i % 9 == 0)) + (i * 7) % 19]
                for i in range(40)
            ],
            "state_events": [
                [now_ts - 8 * 3600, "平静"],
                [now_ts - 8 * 3600 + 420, "活跃"],
                [now_ts - 8 * 3600 + 600, "兴奋"],
                [now_ts - 8 * 3600 + 1080, "恢复中"],
            ],
            "screenshots": [demo_shots[0]],
        },
        {
            "address": "F4:12:FA:9D:88:01", "name": "HUAWEI Band 9",
            "start": int(time.time() - 26 * 3600), "end": int(time.time() - 26 * 3600 + 18 * 60),
            "min": 66, "max": 132, "avg": 92.1, "samples": 96,
            "series": [
                [int(time.time() - 26 * 3600) + i * 11, 68 + (i * 11) % 31]
                for i in range(30)
            ],
            "state_events": [
                [now_ts - 26 * 3600, "采集中"],
                [now_ts - 26 * 3600 + 300, "平静"],
            ],
        },
        {
            "address": "D4:36:39:AA:10:7F", "name": "Polar H10",
            "start": int(time.time() - 50 * 3600), "end": int(time.time() - 50 * 3600 + 7 * 60),
            "min": 63, "max": 119, "avg": 80.0, "samples": 40,
            "series": [
                [int(time.time() - 50 * 3600) + i * 10, 65 + (i * 5) % 24]
                for i in range(24)
            ],
            "state_events": [
                [now_ts - 50 * 3600, "平静"],
                [now_ts - 50 * 3600 + 200, "放松"],
            ],
        },
    ]
    # 追加一场游戏记录，验证游戏图标 / 名称 / 时长显示
    demo_sessions.append({
        "address": "game:cs2", "name": "Counter-Strike 2", "game": "Counter-Strike 2",
        "game_process": "cs2", "game_icon": "",
        "start": int(time.time() - 2 * 3600), "end": int(time.time() - 2 * 3600 + 35 * 60),
        "min": 78, "max": 148, "avg": 112.5, "samples": 120,
        "series": [
            [int(time.time() - 2 * 3600) + i * 8, 90 + (i * 13) % 45]
            for i in range(40)
        ],
        "state_events": [
            [now_ts - 2 * 3600, "活跃"],
            [now_ts - 2 * 3600 + 300, "兴奋"],
            [now_ts - 2 * 3600 + 480, "紧张"],
        ],
        "screenshots": [demo_shots[1]],
    })
    history = HistoryWindow(demo_sessions, shots=demo_shots)
    history.show()
    history.layout().activate()
    QTest.qWait(760)  # 等窗口淡入与历史折线描绘完成
    app.processEvents()
    app.processEvents()
    history.grab().save(str(OUT / "history.png"))

    settings = Settings()
    settings_win = SettingsWindow(settings)
    settings_win.show()
    settings_win.layout().activate()
    QTest.qWait(320)
    app.processEvents()
    app.processEvents()
    settings_win.grab().save(str(OUT / "settings.png"))

    # 分别展示背景自定义与新增的高心率截屏卡片
    settings_scroll = settings_win.findChild(QScrollArea)
    if settings_scroll is not None:
        bar = settings_scroll.verticalScrollBar()
        bar.setValue(int(bar.maximum() * 0.62))
        QTest.qWait(120)
        app.processEvents()
        settings_win.grab().save(str(OUT / "settings_background.png"))
        bar.setValue(bar.maximum())
        QTest.qWait(120)
        app.processEvents()
        settings_win.grab().save(str(OUT / "settings_capture.png"))
        bar.setValue(0)

    # 进程选择器：用固定假进程渲染，避免截图里出现用户真实进程
    import heartbeat.process_picker as picker_module
    from heartbeat.process_picker import ProcessPickerDialog

    original_scan = picker_module.scan_processes
    picker_module.scan_processes = lambda: ([
        (1204, "cs2.exe", r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe"),
        (2316, "YuanShen.exe", r"D:\Games\Genshin Impact\YuanShen.exe"),
        (3408, "chrome.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        (4520, "steam.exe", r"C:\Program Files (x86)\Steam\steam.exe"),
    ], 0, "")
    try:
        picker = ProcessPickerDialog(settings_win, ["cs2.exe"])
        picker.show()
        picker.layout().activate()
        QTest.qWait(320)
        app.processEvents()
        app.processEvents()
        picker.grab().save(str(OUT / "process_picker.png"))
    finally:
        picker_module.scan_processes = original_scan

    # 自定义浅色图片背景：验证自动暗罩下半透明界面仍然可读
    bg_canvas = QPixmap(1280, 800)
    bg_painter = QPainter(bg_canvas)
    grad = QLinearGradient(0, 0, 1280, 800)
    grad.setColorAt(0.0, QColor("#f7d9a0"))
    grad.setColorAt(0.5, QColor("#cfe8ff"))
    grad.setColorAt(1.0, QColor("#f6b8c8"))
    bg_painter.fillRect(bg_canvas.rect(), QBrush(grad))
    bg_painter.end()
    bg_path = OUT / "demo_light_bg.png"
    bg_canvas.save(str(bg_path))

    Backdrop.configure("image", "#0b1322", str(bg_path), 45)
    Backdrop.refresh_all()
    QTest.qWait(180)
    window.grab().save(str(OUT / "main_custom_bg.png"))
    history.grab().save(str(OUT / "history_custom_bg.png"))

    from heartbeat.chrome import CloseDialog
    dialog = CloseDialog(window)
    dialog.show()
    QTest.qWait(320)
    dialog.grab().save(str(OUT / "close_dialog.png"))
    Backdrop.configure("night")
    Backdrop.refresh_all()

    print("saved", OUT / "main.png", OUT / "main_narrow.png", OUT / "floating.png",
          OUT / "floating_game.png", OUT / "history.png", OUT / "settings.png",
          OUT / "process_picker.png", OUT / "settings_background.png",
          OUT / "settings_capture.png", OUT / "main_custom_bg.png",
          OUT / "history_custom_bg.png", OUT / "close_dialog.png")


if __name__ == "__main__":
    main()
