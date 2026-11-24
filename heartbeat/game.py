"""游戏进程检测（Windows 原生 API，无需 psutil 等第三方依赖）。

- 用 Toolhelp32Snapshot 枚举进程，用 GetForegroundWindow 找到当前前台进程，
  从而识别"正在玩"的游戏而不是随便一个在后台的游戏。
- 内置常见游戏进程名清单，也可以在设置里追加自定义进程名。
- 游戏图标用 Qt 的 QFileIconProvider 从可执行文件提取，Windows 上即应用图标。

非 Windows 平台所有检测函数安全返回空结果，便于测试与导入。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

# 进程名（小写，不含 .exe）-> 展示名
BUILTIN_GAMES: dict[str, str] = {
    "cs2": "Counter-Strike 2",
    "csgo": "CS:GO",
    "valorant": "VALORANT",
    "lol": "英雄联盟",
    "league of legends": "英雄联盟",
    "dota2": "Dota 2",
    "pubg": "绝地求生",
    "tpp": "绝地求生",
    "apex": "Apex 英雄",
    "r5apex": "Apex 英雄",
    "overwatch": "守望先锋",
    "wow": "魔兽世界",
    "yuanshen": "原神",
    "genshinimpact": "原神",
    "starrail": "崩坏：星穹铁道",
    "hoyokit": "米哈游启动器",
    "zzz": "绝区零",
    "wuthering waves": "鸣潮",
    "naraka": "永劫无间",
    "minecraft": "我的世界",
    "javaw": "我的世界",
    "roblox": "Roblox",
    "fortnite": "堡垒之夜",
    "gta5": "GTA V",
    "eldenring": "艾尔登法环",
    "sekiro": "只狼",
    "blackmist": "黑神话：悟空",
    "b1": "黑神话：悟空",
    "aimlab": "Aim Lab",
    "steam": "Steam",
    "epicgameslauncher": "Epic 客户端",
}


@dataclass
class GameProcess:
    """一个被识别为游戏的进程。"""

    pid: int
    process: str
    exe: str
    display_name: str
    foreground: bool = False

    @property
    def key(self) -> str:
        return self.process


def match_game(process_name: str, extra: list[str] | None = None) -> str | None:
    """把进程名映射到游戏展示名；自定义清单优先（可覆盖内置名）。"""
    name = (process_name or "").lower().removesuffix(".exe").strip()
    if not name:
        return None
    for item in extra or []:
        custom = (item or "").strip()
        if not custom:
            continue
        # 自定义项支持 "进程名=展示名" 或纯进程名
        if "=" in custom:
            proc, label = custom.split("=", 1)
            if proc.strip().lower().removesuffix(".exe") == name:
                return label.strip() or proc.strip()
        elif custom.lower().removesuffix(".exe") == name:
            return custom
    return BUILTIN_GAMES.get(name)


def _win_api():
    """返回 (kernel32, user32, ctypes, wintypes, Entry)；非 Windows 全为 None。"""
    if sys.platform != "win32":
        return None, None, None, None, None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESSENTRY32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    return kernel32, user32, ctypes, wintypes, PROCESSENTRY32W


def _exe_path(kernel32, ctypes, wintypes, pid: int) -> str:
    """取进程可执行文件全路径（用于提取图标）。"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value if ok else ""
    finally:
        kernel32.CloseHandle(handle)


def scan_processes() -> tuple[list[tuple[int, str, str]], int]:
    """返回 ([(pid, 进程名, exe路径)], 前台进程 pid)。"""
    api = _win_api()
    if api is None:
        return [], 0
    kernel32, user32, ctypes, wintypes, Entry = api
    TH32CS_SNAPPROCESS = 0x2

    # 前台进程
    foreground_pid = 0
    try:
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            foreground_pid = int(pid.value or 0)
    except Exception:
        pass

    processes: list[tuple[int, str, str]] = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (None, 0, -1):
        return [], foreground_pid
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            pid = int(entry.th32ProcessID)
            name = entry.szExeFile
            if name:
                processes.append((pid, name, ""))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)

    # 只给可能是游戏的进程查 exe 路径，避免开销过大
    result: list[tuple[int, str, str]] = []
    for pid, name, _ in processes:
        exe = ""
        if match_game(name) is not None or (name.lower().endswith(".exe")):
            exe = _exe_path(kernel32, ctypes, wintypes, pid)
        result.append((pid, name, exe))
    return result, foreground_pid


def detect_games(extra: list[str] | None = None) -> list[GameProcess]:
    """返回当前运行的游戏，前台游戏排在最前。"""
    processes, foreground_pid = scan_processes()
    games: list[GameProcess] = []
    for pid, name, exe in processes:
        display = match_game(name, extra)
        if not display:
            continue
        games.append(
            GameProcess(
                pid=pid,
                process=name.lower().removesuffix(".exe"),
                exe=exe,
                display_name=display,
                foreground=(pid == foreground_pid),
            )
        )
    games.sort(key=lambda g: (not g.foreground, g.display_name))
    return games


def active_game(games: list[GameProcess]) -> GameProcess | None:
    """优先前台游戏，否则取第一个。"""
    if not games:
        return None
    return games[0]


def game_icon(exe: str, size: int = 32):
    """从 exe 提取应用图标；失败返回 None。"""
    if not exe:
        return None
    try:
        from pathlib import Path

        from PySide6.QtCore import QFileInfo
        from PySide6.QtWidgets import QFileIconProvider

        if not Path(exe).exists():
            return None
        icon = QFileIconProvider().icon(QFileInfo(exe))
        return icon if not icon.isNull() else None
    except Exception:
        return None
