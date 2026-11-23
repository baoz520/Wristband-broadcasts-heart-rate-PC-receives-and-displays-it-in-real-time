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

from PySide6.QtCore import Qt  # noqa: E402
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

    # 关闭测试窗口时不弹模态框（离屏环境下 exec() 行为不稳定）
    settings.close_prompt_enabled = False
    settings.close_default_action = "minimize"
    window.close()
    print("all ui tests passed")


if __name__ == "__main__":
    main()
