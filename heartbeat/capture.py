"""高心率自动截屏：由用户设定阈值，抓取当前屏幕并留下时间戳索引。

截图本体是普通 PNG，放在配置目录（或用户指定目录）；历史记录只保存
元数据（时间 / 心率 / 状态 / 设备 / 所属会话），因此设置文件不会膨胀。
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QPixmap

from .config import capture_directory


class HighHeartCapture:
    """触发判定：达到阈值 + 持续时长 + 两次截屏最小间隔。"""

    def __init__(self) -> None:
        self._above_since: int | None = None
        self._last_capture: int | None = None

    def reset(self) -> None:
        self._above_since = None
        self._last_capture = None

    def ready(
        self,
        bpm: int,
        now: int,
        threshold: int,
        sustain: int = 0,
        cooldown: int = 0,
    ) -> bool:
        """返回 True 时同时消耗一次触发机会（更新内部时间）。"""
        try:
            bpm = int(bpm)
            threshold = int(threshold)
        except (TypeError, ValueError):
            return False
        if bpm < threshold or threshold <= 0:
            self._above_since = None
            return False
        if self._above_since is None:
            self._above_since = int(now)
        if int(now) - self._above_since < max(0, int(sustain)):
            return False
        if self._last_capture is not None and int(now) - self._last_capture < max(
            0, int(cooldown)
        ):
            return False
        self._last_capture = int(now)
        return True


def capture_screen(
    bpm: int,
    state: str = "",
    device: str = "",
    session: str = "",
    directory: str = "",
) -> dict | None:
    """截取当前主屏幕，返回可持久化的截图索引；失败时返回 None。"""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        screens = QGuiApplication.screens()
        screen = screens[0] if screens else None
    if screen is None:
        return None

    pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        return None

    ts = int(time.time())
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(ts))
    path = capture_directory(directory) / f"hr_{stamp}_{int(bpm)}_{uuid.uuid4().hex[:6]}.png"
    if not pixmap.save(str(path), "PNG"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    return {
        "ts": ts,
        "path": str(path),
        "bpm": int(bpm),
        "state": str(state or ""),
        "device": str(device or ""),
        "session": str(session or ""),
    }


def shot_time(path: str | Path) -> Path:
    """供外部复用：把截图索引转成 Path。"""
    return Path(str(path))
