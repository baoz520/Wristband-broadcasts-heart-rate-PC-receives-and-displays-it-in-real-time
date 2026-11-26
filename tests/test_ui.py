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
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from heartbeat import floating as floating_module  # noqa: E402
from heartbeat import settings_window as settings_module  # noqa: E402
from heartbeat.chrome import CloseCard, CloseDialog, TitleButton  # noqa: E402
from heartbeat.config import Settings  # noqa: E402
from heartbeat.main_window import MainWindow  # noqa: E402
from heartbeat.settings_window import SettingsWindow  # noqa: E402
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
        settings.background_mode = "solid"
        settings.background_color = "#123456"
        settings.background_dim = 72
        settings.save()
        reloaded = Settings.load()
        assert reloaded.close_prompt_enabled is False
        assert reloaded.close_default_action == "quit"
        assert reloaded.background_mode == "solid"
        assert reloaded.background_color == "#123456"
        assert reloaded.background_dim == 72
    finally:
        Settings.path = original_path
        temp_path.unlink(missing_ok=True)

    # 3b. 选择图片背景必须同时切到图片模式，否则画面不会变化
    image_path = Path(tempfile.gettempdir()) / "heartbeat_bg_mode_test.png"
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.red)
    image.save(str(image_path))
    picker = SettingsWindow(Settings(background_mode="night"))
    original_picker = settings_module.QFileDialog.getOpenFileName
    settings_module.QFileDialog.getOpenFileName = staticmethod(
        lambda *_args, **_kwargs: (str(image_path), "")
    )
    try:
        picker._choose_bg_image()
    finally:
        settings_module.QFileDialog.getOpenFileName = original_picker
        image_path.unlink(missing_ok=True)
    assert picker.settings.background_mode == "image", "选图后未切换背景模式"
    assert picker.settings.background_image.endswith("heartbeat_bg_mode_test.png")

    # 3c. 锁定悬浮窗时必须应用鼠标穿透，解锁时撤销
    click_through_calls: list[bool] = []
    original_click_through = floating_module._set_native_click_through
    floating_module._set_native_click_through = (
        lambda _widget, enabled: click_through_calls.append(bool(enabled))
    )
    try:
        probe_float = floating_module.FloatingWindow()
        probe_float.set_locked(True)
        probe_float.set_locked(False)
    finally:
        floating_module._set_native_click_through = original_click_through
    assert click_through_calls == [True, False], "锁定/解锁未同步鼠标穿透状态"

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

    # 4b. 动效细节：hover、点击微光、开关回弹与历史曲线描绘都必须有独立动画
    from heartbeat.widgets import HoverAnimator, Sparkline

    assert HoverAnimator.DURATION == 240, "悬停过渡时长未更新"
    assert probe._flash_anim.duration() == 300, "按钮点击反馈缺失"
    probe._play_flash()
    assert probe._flash_anim.endValue() == 0.0, "点击微光未回落"
    toggle = ToggleSwitch()
    assert toggle._anim.duration() == 280, "开关回弹动画缺失"

    spark = Sparkline()
    assert spark.metaObject().indexOfProperty("reveal") >= 0, "折线描绘属性未注册"
    spark.set_history([(1.0, 70), (2.0, 80)])
    assert spark._reveal_anim.endValue() == 1.0, "历史曲线未触发描绘动画"

    from heartbeat.widgets import BentoCard
    card = BentoCard()
    assert card.metaObject().indexOfProperty("flow") >= 0, "液态玻璃流光属性未注册"
    assert card._flow_anim.loopCount() == -1, "液态玻璃流光未循环"
    assert CloseCard().metaObject().indexOfProperty("flow") >= 0, "关闭弹窗未使用液态玻璃"

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
    # 固定使用本用例的设备，避免真实配置里保存的"上次设备"抢走历史焦点
    controller.window._active_address = addr
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
    # 未连接设备时不再用历史心率回填"当前心率"，悬浮窗应显示 --
    assert controller.floating._bpm is None, "断连时悬浮窗仍显示上一次心率"
    assert controller.floating._bpm_label.text() == "--", "断连时悬浮窗心率未清空"
    assert controller.window._bpm.text() == "--", "断连时主界面仍显示上一次心率"

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
    from heartbeat.history_window import HistoryWindow, SessionCard

    controller.window._history_button.click()
    app.processEvents()
    hw = controller._history_window
    assert hw is not None and isinstance(hw, HistoryWindow), "历史记录窗口未创建"
    assert hw.isVisible(), "历史记录窗口未显示"
    # 每条会话一张卡片，含统计条与折线图（若该会话有曲线数据）
    cards = [w for w in hw.findChildren(SessionCard)]
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
    controller.show_settings_window()
    app.processEvents()
    settings_win = controller._settings_window
    assert isinstance(settings_win, SettingsWindow), "设置窗口未创建"
    settings_win._opacity_slider.setValue(70)
    settings_win._width_slider.setValue(300)
    settings_win._heart_switch.setChecked(False)
    assert controller.floating._heart.isHidden(), "心跳图标开关未即时生效"
    settings_win.collect()
    app.processEvents()
    assert abs(controller.floating.windowOpacity() - 0.7) < 0.01, "不透明度未生效"
    assert controller.floating.width() == 300, "悬浮窗宽度未生效"
    assert controller.settings.float_show_heart is False, "显示项设置未写入"

    # 11b. 状态判断结果应直接显示在心率标签上
    from heartbeat.hr import HeartState

    excited = HeartState("兴奋", "#f0a35e", delta=28.0, baseline=65.0, confidence=0.9)
    controller.floating.set_hr(95, "实时", "", "", state=excited)
    assert controller.floating._zone() == "兴奋", "悬浮窗未显示状态"
    controller.window.push_hr(95, "实时", "", "", state=excited)
    assert "兴奋" in controller.window._zone.text(), "主界面未显示状态"

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

    # Wallpaper Engine 等动态壁纸即使在 Steam 目录下也不能算游戏
    wallpaper_paths = [
        r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\bin\wallpaper64.exe",
        r"C:\Program Files (x86)\Steam\steamapps\workshop\content\431960\3124158758\scene.exe",
    ]
    assert match_game("wallpaper64.exe", exe=wallpaper_paths[0]) is None
    assert match_game("scene.exe", exe=wallpaper_paths[1]) is None
    assert match_game("LivelyWallpaper.exe") is None
    assert match_game(
        "scene.exe", exe=wallpaper_paths[1], extra=["scene.exe=我指定的游戏"]
    ) == "我指定的游戏", "自定义清单应能覆盖壁纸排除"

    # 14. 悬浮窗游戏中自动隐藏背景 / 整窗隐藏，退出游戏后恢复
    controller._on_game_float_mode_changed("transparent")
    controller.floating.set_game_info("原神", bpm=88, low=80, high=95)
    assert controller.floating._game_transparent, "隐藏背景模式未生效"
    assert controller.floating._panel._transparent, "悬浮窗底板未隐藏"
    assert controller.floating._panel._shadow is False, "悬浮窗仍然绘制外阴影"
    controller.floating.set_game_info("")
    assert not controller.floating._game_transparent, "退出游戏后背景未恢复"

    controller._on_game_float_mode_changed("hidden")
    # 用户可能已经手动隐藏悬浮窗，测试显式打开以验证"退出游戏后恢复"
    controller.set_floating(True)
    controller._start_game_session(game)
    controller._sync_game_visibility(True)
    assert not controller.floating.isVisible(), "游戏中悬浮窗未自动隐藏"
    controller._finish_game_session()
    assert controller.floating.isVisible(), "退出游戏后悬浮窗未恢复"
    controller._on_game_float_mode_changed("transparent")
    assert controller.settings.game_float_mode == "transparent", "悬浮窗模式未持久化"

    # 15. 进程选择器：列出所有进程、搜索、选中后快捷加入自定义清单并立即生效
    import heartbeat.process_picker as picker_module
    from heartbeat.process_picker import ProcessPickerDialog

    fake_processes = [
        (101, "NewGame.exe", r"D:\Games\NewGame\NewGame.exe"),
        (102, "steam.exe", r"C:\Program Files (x86)\Steam\steam.exe"),
    ]
    original_scan = picker_module.scan_processes
    picker_module.scan_processes = lambda: (list(fake_processes), 0, "")
    try:
        picker = ProcessPickerDialog()
        assert picker._table.rowCount() == 2, "进程列表未列出全部进程"
        picker._search.setText("newgame")
        shown = [r for r in range(picker._table.rowCount()) if not picker._table.isRowHidden(r)]
        assert shown == [0], "进程搜索过滤失败"
        picker._table.selectRow(0)
        assert picker._display_edit.text(), "选中进程后未生成默认显示名"
        picker._display_edit.setText("新游戏")
        picker._accept()
        assert picker.selected_process == ("NewGame.exe", "新游戏"), "选择结果错误"

        settings_win._custom_edit.setText("")
        settings_win._add_custom_process("NewGame.exe", "新游戏")
        assert "NewGame.exe=新游戏" in settings_win._custom_edit.text()
        assert "NewGame.exe=新游戏" in controller._game_extra, "自定义清单未即时生效"
        assert match_game("NewGame.exe", controller._game_extra) == "新游戏"
        settings_win._add_custom_process("NewGame.exe", "新游戏")
        assert settings_win._custom_edit.text().count("NewGame.exe") == 1, "重复添加未去重"
    finally:
        picker_module.scan_processes = original_scan

    # 16. 全窗口玻璃拟态风格：卡片组件、夜景色板与响应式网格
    from heartbeat.theme import (
        BENTO_BORDER,
        BENTO_CARD,
        BENTO_INK,
        BENTO_SKY,
        BENTO_SNOW,
        CHAMPAGNE,
        NIGHT,
    )
    from heartbeat.widgets import BentoCard, BentoGrid

    assert (BENTO_SNOW, BENTO_CARD, BENTO_INK, BENTO_BORDER, BENTO_SKY) == (
        "#0b1322", "#16233a", "#ffffff", "#ffffff", "#e4b863"
    ), "玻璃拟态色板被改动"
    assert CHAMPAGNE == "#e4b863" and NIGHT == "#0b1322", "夜景 / 香槟金基准色被改动"
    assert all(isinstance(card, BentoCard) for card in hw._cards), (
        "历史窗口卡片不是便当盒卡片"
    )
    assert isinstance(settings_win._grid, BentoGrid), "设置窗口未使用便当盒网格"
    assert isinstance(controller.floating._panel, BentoCard), "悬浮窗未换成白卡"
    assert isinstance(picker._table.parent(), BentoCard), "进程表未放进便当盒白卡"
    assert any(
        isinstance(widget, BentoCard)
        for widget in picker.findChildren(BentoCard)
    ), "进程选择器缺少便当盒卡片"
    probe_grid = BentoGrid()
    assert (probe_grid.columns_for(980), probe_grid.columns_for(720),
            probe_grid.columns_for(400)) == (4, 2, 1), "网格断点不正确"

    # 17. 触发节奏由用户决定：未达阈值 / 持续不足 / 冷却中都不截屏
    from heartbeat.capture import HighHeartCapture

    trigger = HighHeartCapture()
    assert not trigger.ready(90, 100, 120, 0, 30)
    assert trigger.ready(130, 100, 120, 0, 30)
    assert not trigger.ready(130, 110, 120, 0, 30)
    assert trigger.ready(130, 140, 120, 0, 30)
    trigger.reset()
    assert not trigger.ready(130, 200, 120, 3, 30)
    assert trigger.ready(130, 203, 120, 3, 30)

    # 18. 设置窗口的截屏阈值 / 持续 / 间隔立即写入配置
    settings_win._capture_switch.setChecked(True)
    settings_win._capture_threshold_slider.setValue(140)
    settings_win._capture_sustain_slider.setValue(2)
    settings_win._capture_cooldown_slider.setValue(10)
    assert controller.settings.capture_enabled is True
    assert controller.settings.capture_threshold == 140
    assert controller.settings.capture_sustain == 2
    assert controller.settings.capture_cooldown == 10

    # 19. 状态变化去重；达到阈值时截屏并连同时间戳写入历史
    probe_events: dict = {"state_events": []}
    controller._record_state_change(probe_events, "平静", 1)
    controller._record_state_change(probe_events, "平静", 2)
    controller._record_state_change(probe_events, "兴奋", 3)
    assert probe_events["state_events"] == [[1, "平静"], [3, "兴奋"]]

    import heartbeat.app as app_module
    import time as _time

    shot_image = Path(tempfile.gettempdir()) / "heartbeat_capture_test.png"
    QImage(80, 50, QImage.Format.Format_RGB32).save(str(shot_image))
    captured: list[tuple[int, dict]] = []
    original_capture = app_module.capture_screen

    def fake_capture(bpm: int, **kwargs):
        captured.append((bpm, kwargs))
        return {
            "ts": int(_time.time()),
            "path": str(shot_image),
            "bpm": bpm,
            "state": kwargs.get("state", ""),
            "device": kwargs.get("device", ""),
            "session": kwargs.get("session", ""),
        }

    controller.settings.capture_threshold = 120
    controller.settings.capture_sustain = 0
    controller.settings.capture_cooldown = 0
    controller.settings.screenshot_events = []
    controller._capture.reset()
    controller._session = None
    app_module.capture_screen = fake_capture
    try:
        controller._on_heart_rate(90, "心率服务", "AA:BB:CC:DD:EE:FF", "测试手环")
        controller._on_heart_rate(145, "心率服务", "AA:BB:CC:DD:EE:FF", "测试手环")
    finally:
        app_module.capture_screen = original_capture
    assert len(captured) == 1 and captured[0][0] == 145, "截屏触发条件错误"
    assert captured[0][1]["state"], "截图未记录当时的状态"
    session = controller._session
    assert session is not None and len(session["screenshots"]) == 1, "截图未写入本次会话"
    assert session["state_events"], "状态变化未写入本次会话"
    controller._finalize_session()
    record = controller._sessions[-1]
    assert record["state_events"] and record["screenshots"], "历史记录缺少状态变化或截图"
    assert controller.settings.screenshot_events, "截图索引未持久化"

    controller.show_history_window()
    app.processEvents()
    hw2 = controller._history_window
    assert len(hw2._gallery._shots) >= 1, "历史窗口未显示截图画廊"
    assert not hw2._gallery.isHidden(), "有截图时画廊被隐藏"
    from PySide6.QtWidgets import QLabel

    state_labels = [w.text() for w in hw2.findChildren(QLabel)]
    assert any("状态变化" in text for text in state_labels), "历史卡片未显示状态变化"

    # 20. 截图删除：每张缩略图有删除按钮，点击后索引 / 会话引用 / 文件一起清理
    from heartbeat.history_window import ShotThumb

    thumb = ShotThumb(str(shot_image))
    removes = [b for b in thumb.findChildren(RaisedButton) if b.text() == "×"]
    assert len(removes) == 1, "截图缩略图缺少删除按钮"
    removed_paths: list[str] = []
    thumb.deleteRequested.connect(removed_paths.append)
    removes[0].click()
    assert removed_paths and removed_paths[0] == str(shot_image), "截图删除信号未发出"

    shot_key = controller.settings.screenshot_events[0]["path"]
    controller.delete_shot(shot_key)
    app.processEvents()
    assert not shot_image.exists(), "删除截图后磁盘文件仍在"
    assert controller.settings.screenshot_events == [], "删除截图后索引未清理"
    assert all(
        not s.get("screenshots")
        for s in controller._sessions
    ), "删除截图后会话引用未清理"
    hw3 = controller._history_window
    assert hw3._gallery._shots == [] and hw3._gallery.isHidden(), "删除截图后画廊仍显示"

    # 21. 文件夹里手动删除图片：软件内自动隐藏并清理失效索引
    orphan = Path(tempfile.gettempdir()) / "heartbeat_orphan_shot.png"
    QImage(40, 30, QImage.Format.Format_RGB32).save(str(orphan))
    controller.settings.screenshot_events = [
        {"ts": int(_time.time()), "path": str(orphan), "bpm": 150}
    ]
    controller._history_window.set_shots(list(controller.settings.screenshot_events))
    assert len(hw3._gallery._shots) == 1, "有效截图未渲染"
    orphan.unlink(missing_ok=True)
    controller.prune_missing_shots()
    app.processEvents()
    assert controller.settings.screenshot_events == [], "失效截图索引未清理"
    assert hw3._gallery._shots == [] and hw3._gallery.isHidden(), "图片删除后软件仍显示"

    # 22. 主界面心率检测开关：关闭后停止处理心率并清空当前显示
    assert controller.window._hr_detect_switch.isChecked(), "心率检测默认应开启"
    controller._set_hr_detection(False)
    assert controller.settings.hr_detection_enabled is False, "检测开关未持久化"
    controller._on_heart_rate(88, "心率服务", "AA:BB:CC:DD:EE:FF", "测试手环")
    assert controller._session is None, "检测关闭后仍在记录心率会话"
    assert controller.window._bpm.text() == "--", "检测关闭后主界面仍显示心率"
    controller._set_hr_detection(True)
    controller._on_heart_rate(88, "心率服务", "AA:BB:CC:DD:EE:FF", "测试手环")
    assert controller.window._bpm.text() == "88", "检测开启后未恢复显示"
    controller._finalize_session()

    # 23. 重连阶段应重新开启扫描：ble 源码必须包含重连时的 _ensure_scan 调用
    import inspect
    from heartbeat.ble import BleWorker

    ble_src = inspect.getsource(BleWorker._connection_loop)
    assert "_ensure_scan()" in ble_src, "重连等待阶段未恢复设备扫描"

    controller.settings.capture_enabled = False
    controller._save_settings()

    controller.quit()

    # 关闭测试窗口时不弹模态框（离屏环境下 exec() 行为不稳定）
    settings.close_prompt_enabled = False
    settings.close_default_action = "minimize"
    window.close()
    print("all ui tests passed")


if __name__ == "__main__":
    main()
