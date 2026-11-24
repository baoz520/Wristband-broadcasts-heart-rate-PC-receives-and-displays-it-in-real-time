"""设置持久化（%APPDATA%/HeartbeatMonitor/settings.json）。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "HeartbeatMonitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    floating_visible: bool = True
    device_management: bool = True
    auto_reconnect: bool = True
    saved_address: str = ""
    saved_name: str = ""
    floating_x: int = -1
    floating_y: int = -1
    floating_locked: bool = False
    window_geometry: str = ""
    history_mode: bool = True
    history: dict[str, list[list[int]]] = field(default_factory=dict)
    history_sessions: list[dict] = field(default_factory=list)
    close_minimize_to_tray: bool = True
    close_prompt_enabled: bool = True
    close_default_action: str = "minimize"

    # 悬浮窗自定义
    float_width: int = 268          # 悬浮窗宽度（高度按比例）
    float_opacity: int = 100        # 不透明度 40-100
    float_show_heart: bool = True   # 显示心跳图标
    float_show_zone: bool = True    # 显示心率区间
    float_show_device: bool = True  # 显示设备名

    # 游戏检测
    game_detect_enabled: bool = False       # 是否检测游戏进程
    game_custom: list[str] = field(default_factory=list)  # 自定义进程名（支持 名=展示名）
    game_record_sessions: bool = True       # 游戏期间记录为历史会话
    game_show_on_float: bool = True         # 悬浮窗显示当前游戏
    game_float_mode: str = "transparent"    # 游戏中悬浮窗：normal / transparent / hidden
    game_poll_seconds: int = 4              # 检测轮询间隔

    @classmethod
    def path(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        settings = cls()
        try:
            raw = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return settings
        known = {f.name for f in fields(cls)}
        for key, value in raw.items():
            if key in known and isinstance(value, type(getattr(settings, key))):
                setattr(settings, key, value)
        return settings

    def save(self) -> None:
        try:
            self.path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
