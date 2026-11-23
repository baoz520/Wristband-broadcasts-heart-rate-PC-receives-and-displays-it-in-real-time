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
