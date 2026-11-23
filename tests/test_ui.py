"""界面行为自测：python tests/test_ui.py

检查自绘标题栏、关闭弹窗与「不再提示」设置的持久化逻辑。
离屏运行，不依赖真实蓝牙硬件。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from heartbeat.chrome import CloseDialog, TitleButton  # noqa: E402
from heartbeat.config import Settings  # noqa: E402
from heartbeat.main_window import MainWindow  # noqa: E402
from heartbeat.theme import apply_theme  # noqa: E402


def main() -> None:
    app = QApplication.instance() or QApplication([])
    apply_theme(app)

    # 1. 主窗口必须是无原生边框的自绘窗口
    settings = Settings()
    window = MainWindow(settings)
    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint, "主窗口仍使用原生标题栏"
    assert hasattr(window, "_titlebar"), "缺少自绘标题栏"
    for attr in ("_min_button", "_max_button", "_close_button"):
        btn = getattr(window._titlebar, attr)
        assert isinstance(btn, TitleButton), f"{attr} 不是自绘按钮"

    # 2. 关闭弹窗包含两个操作与「不再提示」勾选框
    dialog = CloseDialog(window)
    assert dialog._minimize.text() == "最小化"
    assert dialog._quit.text() == "直接关闭"
    assert dialog._check.text() == "不再提示"
    assert not dialog._check.isChecked()

    # 选择「最小化」并勾选不再提示
    dialog._check.setChecked(True)
    dialog._minimize.click()
    assert dialog.action == "minimize"
    assert dialog.remember is True

    dialog2 = CloseDialog(window)
    dialog2._quit.click()
    assert dialog2.action == "quit"
    assert dialog2.remember is False

    # 3. 设置字段可持久化（写入临时文件，不碰真实用户配置）
    temp_path = Path(tempfile.gettempdir()) / "heartbeat_ui_test_settings.json"
    original_path = Settings.path
    Settings.path = classmethod(lambda cls: temp_path)
    try:
        settings.close_prompt_enabled = False
        settings.close_default_action = "quit"
        settings.save()
        reloaded = Settings.load()
        assert reloaded.close_prompt_enabled is False
        assert reloaded.close_default_action == "quit"
    finally:
        Settings.path = original_path
        temp_path.unlink(missing_ok=True)

    # 4. 悬停动画：交互控件必须带可动画的 hover 属性
    from heartbeat.widgets import RaisedButton, SoftCard, SoftCheckBox, ToggleSwitch

    hover_widgets = [
        TitleButton("close"),
        RaisedButton("连接"),
        ToggleSwitch(),
        SoftCheckBox("不再提示"),
        SoftCard(),
        window._history_button,
    ]
    for widget in hover_widgets:
        assert hasattr(widget, "hover"), f"{type(widget).__name__} 缺少 hover 动画属性"
        assert widget.metaObject().indexOfProperty("hover") >= 0, "hover 未注册为 Qt 属性"
        assert getattr(widget, "_hover_anim", None) is not None, "缺少悬停动画"

    # enter/leave 必须把动画目标设为 1.0 / 0.0
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QEnterEvent

    probe = RaisedButton("连接")
    probe.enterEvent(QEnterEvent(QPointF(2, 2), QPointF(2, 2), QPointF(2, 2)))
    assert probe._hover_anim.endValue() == 1.0
    probe.leaveEvent(QEvent(QEvent.Type.Leave))
    assert probe._hover_anim.endValue() == 0.0

    # 5. 折线图：历史样本（Unix 时间戳）须换算到 monotonic 基准才能显示
    import time

    wall = time.time()
    samples = [[int(wall - (30 - i) * 2), 70 + (i * 7) % 22] for i in range(16)]
    window.set_device_history("AA:BB:CC:DD:EE:FF", samples)
    app.processEvents()
    points = list(window._spark._points)
    assert len(points) == 16, f"折线数据点数量错误: {len(points)}"
    ages = [time.monotonic() - ts for ts, _ in points]
    assert 0 <= min(ages) and max(ages) < 90, f"时间戳未换算到 monotonic 基准: {ages}"

    # 6. "查看历史数据"按钮必须能真正打开历史，不再因 Controller 上不存在的
    #    _last_seen_address 字段抛 AttributeError 而中断信号链。
    from heartbeat.app import Controller

    controller = Controller(app)
    controller.window.show()
    app.processEvents()
    addr = "C8:47:8C:1A:2B:3C"
    wall = time.time()
    controller._history_by_device[addr] = [
        [int(wall - (30 - i) * 2), 70 + (i * 7) % 22] for i in range(16)
    ]
    controller.window._history_mode = False
    controller.floating._history_mode = False
    controller.window._history_button.click()
    app.processEvents()
    assert controller.history_mode is True, "历史模式未开启"
    assert len(controller.window._spark._points) == 16, "点击历史按钮后折线未加载"
    assert controller.floating._source == "历史", "悬浮窗未切换到历史数据"

    # 7. 标题栏圆形按钮不应绘制焦点方向的方框轮廓
    import inspect

    src = inspect.getsource(TitleButton.paintEvent)
    assert "hasFocus()" not in src, "标题栏按钮仍绘制焦点方框"

    controller.quit()

    # 关闭测试窗口时不弹模态框（离屏环境下 exec() 行为不稳定）
    settings.close_prompt_enabled = False
    settings.close_default_action = "minimize"
    window.close()
    print("all ui tests passed")


if __name__ == "__main__":
    main()
