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

    # 5. 折线图：历史样本须以历史模式完整保留（不受 60 秒实时窗口限制）
    import time

    wall = time.time()
    samples = [[int(wall - (30 - i) * 2), 70 + (i * 7) % 22] for i in range(16)]
    window.set_device_history("AA:BB:CC:DD:EE:FF", samples)
    app.processEvents()
    points = list(window._spark._points)
    assert len(points) == 16, f"折线数据点数量错误: {len(points)}"
    assert window._spark._history_mode, "历史数据未使用历史绘制模式"
    # 历史模式的样本按索引绘制，保留原始 Unix 时间戳即可
    assert all(abs(ts - float(orig[0])) < 1 for (ts, _), orig in zip(points, sorted(samples))), (
        "历史样本时间戳被错误改写"
    )

    # 6. "查看历史数据"按钮必须能真正打开历史：旧历史（几小时前）也不能被
    #    60 秒实时窗口过滤掉，必须按历史模式完整绘制在折线图上。
    from heartbeat.app import Controller

    controller = Controller(app)
    controller.window.show()
    app.processEvents()
    addr = "C8:47:8C:1A:2B:3C"
    wall = time.time()
    old_samples = [
        [int(wall - 3 * 3600 + i * 30), 70 + (i * 7) % 22] for i in range(16)
    ]
    controller._history_by_device[addr] = old_samples
    controller.window._history_mode = False
    controller.floating._history_mode = False
    controller.window._history_button.click()
    app.processEvents()
    assert controller.history_mode is True, "历史模式未开启"
    assert controller.window._spark._history_mode, "折线图未进入历史绘制模式"
    assert len(controller.window._spark._points) >= 16, (
        f"历史折线点数不足: {len(controller.window._spark._points)}"
    )
    assert "小时前" in controller.window._spark._axis_labels[0], "时间轴未反映真实时间跨度"
    assert controller.floating._source == "历史", "悬浮窗未切换到历史数据"

    # 7. 标题栏圆形按钮不应绘制焦点方向的方框轮廓
    import inspect

    src = inspect.getsource(TitleButton.paintEvent)
    assert "hasFocus()" not in src, "标题栏按钮仍绘制焦点方框"

    # 8. 每次连接的心率序列必须被记录，并在会话结束时写入持久化数据
    controller._on_heart_rate(70, "心率服务", "AA:BB:CC:DD:EE:FF", "测试手环")
    for bpm in (72, 75, 81, 90, 77):
        controller._on_heart_rate(bpm, "心率服务", "AA:BB:CC:DD:EE:FF", "测试手环")
    assert controller._session is not None and len(controller._session["series"]) == 6, (
        "本次连接的心率序列未被采集"
    )
    assert [x[1] for x in controller._session["series"]] == [70, 72, 75, 81, 90, 77]
    controller._finalize_session()
    assert controller._sessions, "会话结束未写入历史"
    finished = controller._sessions[-1]
    assert len(finished.get("series") or []) == 6, "会话未保存心率曲线"
    assert finished.get("min") == 70 and finished.get("max") == 90

    # 9. "查看历史数据"按钮必须弹出独立的历史记录窗口，逐条显示会话统计与折线
    from heartbeat.history_window import HistoryWindow

    controller.window._history_button.click()
    app.processEvents()
    hw = controller._history_window
    assert hw is not None and isinstance(hw, HistoryWindow), "历史记录窗口未创建"
    assert hw.isVisible(), "历史记录窗口未显示"
    # 每条会话一张卡片，含统计条与折线图（若该会话有曲线数据）
    cards = [w for w in hw.findChildren(SoftCard)]
    assert len(cards) == len(controller._sessions), (
        f"历史卡片数量不符: {len(cards)} vs {len(controller._sessions)}"
    )
    from heartbeat.widgets import Sparkline

    with_series = [r for r in controller._sessions if len(r.get("series") or []) >= 2]
    charts = sum(len(c.findChildren(Sparkline)) for c in cards)
    assert charts >= len(with_series), "会话折线图未渲染"
    assert "次连接" in hw._count.text()

    # 再次点击应复用同一窗口并刷新，而不是创建新窗口
    controller.window._history_button.click()
    app.processEvents()
    assert controller._history_window is hw, "历史窗口被重复创建"
    hw.hide()

    # 空状态窗口：没有会话时显示占位提示
    empty_window = HistoryWindow([])
    assert "0 次连接" in empty_window._count.text()
    assert empty_window._cards_lay.count() == 1, "空状态未显示占位提示"

    # 10. 历史记录删除按钮：卡片有删除键，点击后从会话与视图中移除
    from heartbeat.history_window import SessionCard, session_key

    sample = {
        "address": "AA:BB:CC:DD:EE:FF", "name": "删除测试",
        "start": 1000, "end": 1300, "min": 60, "max": 90, "avg": 75.0,
        "series": [[1000, 60], [1100, 90]],
    }
    card = SessionCard(sample)
    deletes = [b for b in card.findChildren(RaisedButton) if b.text() == "删除"]
    assert len(deletes) == 1, "历史卡片缺少删除按钮"
    controller._sessions = [sample]
    controller.window.set_sessions(controller._sessions)
    controller.show_history_window()
    app.processEvents()
    controller.delete_session(session_key(sample))
    app.processEvents()
    assert controller._sessions == [], "删除后会话未被移除"
    assert all(
        session_key(r) != session_key(sample) for r in controller._history_window._sessions
    ), "删除后历史窗口仍显示该记录"

    # 11. 设置窗口：悬浮窗自定义即时生效并持久化
    from heartbeat.settings_window import SettingsWindow

    controller.show_settings_window()
    app.processEvents()
    settings_win = controller._settings_window
    assert isinstance(settings_win, SettingsWindow), "设置窗口未创建"
    settings_win._opacity_slider.setValue(70)
    settings_win._width_slider.setValue(300)
    settings_win._heart_switch.setChecked(False)
    settings_win.collect()
    app.processEvents()
    assert abs(controller.floating.windowOpacity() - 0.7) < 0.01, "不透明度未生效"
    assert controller.floating.width() == 300, "悬浮窗宽度未生效"
    assert controller.settings.float_show_heart is False, "显示项设置未写入"

    # 12. 游戏检测：进程名匹配与游戏会话心率统计
    from heartbeat.game import GameProcess, match_game

    assert match_game("cs2.exe") == "Counter-Strike 2"
    assert match_game("mygame.exe", ["mygame.exe=我的游戏"]) == "我的游戏"
    assert match_game("unknown.exe") is None
    game = GameProcess(999, "cs2", "", "Counter-Strike 2", True)
    controller._start_game_session(game)
    for bpm in (80, 85, 92, 88):
        controller._record_game_hr(bpm)
    controller._finish_game_session()
    last = controller._sessions[-1]
    assert last.get("game") == "Counter-Strike 2", "游戏会话未保存游戏名"
    assert last.get("min") == 80 and last.get("max") == 92, "游戏心率统计错误"
    assert len(last.get("series") or []) == 4, "游戏心率曲线未保存"

    # 13. Steam 等平台不算游戏；游戏识别覆盖主流进程名 + 安装路径
    from heartbeat.game import BUILTIN_GAMES

    for launcher in (
        "steam.exe", "steamwebhelper.exe", "EpicGamesLauncher.exe",
        "Battle.net.exe", "WeGame.exe", "hoyokit.exe", "javaw.exe",
    ):
        assert match_game(launcher) is None, f"{launcher} 被误判为游戏"
    assert match_game("steam.exe", ["steam.exe=我指定的游戏"]) == "我指定的游戏"
    assert len(BUILTIN_GAMES) >= 150, "内置游戏进程表覆盖不足"
    assert match_game(
        "mystery.exe",
        exe=r"C:\Program Files (x86)\Steam\steamapps\common\My Cool Game\mystery.exe",
    ) == "My Cool Game", "安装路径未识别为游戏"
    assert match_game("MyGame-Win64-Shipping.exe") == "MyGame", "引擎命名未识别"
    assert match_game("javaw.exe", window_title="Minecraft 1.20.4") == "我的世界"

    # 14. 悬浮窗游戏中自动隐藏背景 / 整窗隐藏，退出游戏后恢复
    controller._on_game_float_mode_changed("transparent")
    controller.floating.set_game_info("原神", bpm=88, low=80, high=95)
    assert controller.floating._game_transparent, "隐藏背景模式未生效"
    assert controller.floating._panel._transparent, "悬浮窗底板未隐藏"
    controller.floating.set_game_info("")
    assert not controller.floating._game_transparent, "退出游戏后背景未恢复"

    controller._on_game_float_mode_changed("hidden")
    controller._start_game_session(game)
    controller._sync_game_visibility(True)
    assert not controller.floating.isVisible(), "游戏中悬浮窗未自动隐藏"
    controller._finish_game_session()
    assert controller.floating.isVisible(), "退出游戏后悬浮窗未恢复"
    controller._on_game_float_mode_changed("transparent")
    assert controller.settings.game_float_mode == "transparent", "悬浮窗模式未持久化"

    controller.quit()

    # 关闭测试窗口时不弹模态框（离屏环境下 exec() 行为不稳定）
    settings.close_prompt_enabled = False
    settings.close_default_action = "minimize"
    window.close()
    print("all ui tests passed")


if __name__ == "__main__":
    main()
