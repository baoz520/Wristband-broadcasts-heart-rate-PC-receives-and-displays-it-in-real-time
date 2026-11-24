"""游戏进程检测（Windows 原生 API，无需 psutil 等第三方依赖）。

识别策略（按优先级）：
1. 用户在设置里添加的自定义进程（可覆盖任何内置判定）；
2. 内置主流游戏进程名表（覆盖 Steam / Epic / Riot / 战网 / 国服等常见游戏）；
3. 可执行文件安装路径特征（steamapps\\common、Epic Games、XboxGames 等），
   这样即使进程名不在清单里，绝大多数从游戏平台安装的游戏也能识别；
4. Unreal 等引擎的 ``xxx-Win64-Shipping.exe`` 命名特征；
5. 前台窗口标题补充（例如java启动的 Minecraft）。

Steam、Epic 启动器、战网、WeGame、米哈游启动器，以及 Wallpaper Engine /
Lively 等动态壁纸（含 Steam 创意工坊壁纸）都**不算游戏进程**，会被显式排除；
只有真正的游戏本体才进入统计。

非 Windows 平台所有检测函数安全返回空结果，便于测试与导入。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

# 进程名（小写，不含 .exe）-> 展示名。
# 这里只列游戏本体；平台 / 启动器统一放进 NON_GAME_PROCESSES。
BUILTIN_GAMES: dict[str, str] = {
    # ---- Valve / Steam 经典射击与 MOBA ----
    "cs2": "Counter-Strike 2",
    "csgo": "CS:GO",
    "dota2": "Dota 2",
    "dota": "Dota 2",
    "half-life2": "半条命 2",
    "hl2": "半条命 2",
    "portal2": "传送门 2",
    "gmod": "Garry's Mod",
    "team fortress 2": "军团要塞 2",
    "tf2": "军团要塞 2",
    # ---- Riot ----
    "valorant": "VALORANT",
    "lol": "英雄联盟",
    "league of legends": "英雄联盟",
    "wildrift": "英雄联盟手游",
    # ---- 战术 / 竞技射击 ----
    "pubg": "绝地求生",
    "tpp": "绝地求生",
    "pubg lite": "PUBG Lite",
    "apex": "Apex 英雄",
    "r5apex": "Apex 英雄",
    "overwatch": "守望先锋",
    "ow": "守望先锋",
    "overwatch2": "守望先锋 2",
    "rainbow6": "彩虹六号：围攻",
    "r6": "彩虹六号：围攻",
    "siege": "彩虹六号：围攻",
    "fortnite": "堡垒之夜",
    "paladins": "帕拉丁",
    "titanfall2": "泰坦陨落 2",
    "titanfall": "泰坦陨落",
    "splitgate": "Splitgate",
    "thefinals": "THE FINALS",
    "finals": "THE FINALS",
    "destiny2": "命运 2",
    "destiny": "命运",
    "hunt": "猎杀：对决",
    "hunt showdown": "猎杀：对决",
    "escape from tarkov": "逃离塔科夫",
    "eft": "逃离塔科夫",
    "tarkov": "逃离塔科夫",
    "arena breakout": "暗区突围",
    "delta force": "三角洲行动",
    "deltaforce": "三角洲行动",
    # ---- 暴雪 / 经典网游 ----
    "wow": "魔兽世界",
    "wowclassic": "魔兽世界怀旧服",
    "diablo3": "暗黑破坏神 3",
    "diablo4": "暗黑破坏神 4",
    "starcraft2": "星际争霸 2",
    "sc2": "星际争霸 2",
    "warcraft3": "魔兽争霸 3",
    "wc3": "魔兽争霸 3",
    "hearthstone": "炉石传说",
    "heroes of the storm": "风暴英雄",
    "ffxiv": "最终幻想 14",
    "ff14": "最终幻想 14",
    "final fantasy xiv": "最终幻想 14",
    "guildwars2": "激战 2",
    "gw2": "激战 2",
    "eso": "上古卷轴 Online",
    "albiononline": "阿尔比恩 Online",
    "blackdesert": "黑色沙漠",
    "bdo": "黑色沙漠",
    "lostark": "失落的方舟",
    "newworld": "新世界",
    "runescape": "RuneScape",
    "maplestory": "冒险岛",
    "tibia": "Tibia",
    # ---- 米哈游 / 国产二次元 ----
    "yuanshen": "原神",
    "genshin": "原神",
    "genshinimpact": "原神",
    "starrail": "崩坏：星穹铁道",
    "hsr": "崩坏：星穹铁道",
    "zzz": "绝区零",
    "zenlesszonezero": "绝区零",
    "honkai3rd": "崩坏 3",
    "bh3": "崩坏 3",
    "wuthering waves": "鸣潮",
    "wutheringwaves": "鸣潮",
    "neverness to everness": "异环",
    # ---- 国产网游 / 单机 ----
    "naraka": "永劫无间",
    "naraka bladepoint": "永劫无间",
    "crossfire": "穿越火线",
    "cf": "穿越火线",
    "dnf": "地下城与勇士",
    "dnfn": "地下城与勇士",
    "dungeonfighter": "地下城与勇士",
    "jx3": "剑网 3",
    "jx3hd": "剑网 3",
    "wuxian": "逆水寒",
    "nishuihan": "逆水寒",
    "mhxy": "梦幻西游",
    "ffo": "自由幻想",
    "tlbb": "天龙八部",
    "hok": "王者荣耀",
    "honor of kings": "王者荣耀",
    "yhz": "永劫无间",
    "blackmist": "黑神话：悟空",
    "b1": "黑神话：悟空",
    "blackmythwukong": "黑神话：悟空",
    "wukong": "黑神话：悟空",
    "phantom blade zero": "影之刃零",
    # ---- 开放世界 / RPG ----
    "minecraft": "我的世界",
    "terraria": "泰拉瑞亚",
    "stardew": "星露谷物语",
    "stardewvalley": "星露谷物语",
    "gta5": "GTA V",
    "gtaiv": "GTA IV",
    "rdr2": "荒野大镖客：救赎 2",
    "reddeadredemption2": "荒野大镖客：救赎 2",
    "watchdogs2": "看门狗 2",
    "watchdogs": "看门狗",
    "cyberpunk2077": "赛博朋克 2077",
    "cyberpunk": "赛博朋克 2077",
    "witcher3": "巫师 3",
    "witcher": "巫师 3",
    "skyrim": "上古卷轴 5",
    "tesv": "上古卷轴 5",
    "fallout4": "辐射 4",
    "fallout76": "辐射 76",
    "fallout3": "辐射 3",
    "falloutnv": "辐射：新维加斯",
    "eldenring": "艾尔登法环",
    "sekiro": "只狼",
    "darksouls3": "黑暗之魂 3",
    "darksouls": "黑暗之魂",
    "dsr": "黑暗之魂：重制版",
    "liesofp": "匹诺曹的谎言",
    "nioh2": "仁王 2",
    "wolong": "卧龙：苍天陨落",
    "nms": "无人深空",
    "nomanssky": "无人深空",
    "subnautica": "深海迷航",
    "subnauticabelowzero": "深海迷航：零度之下",
    "valheim": "英灵神殿",
    "palworld": "幻兽帕鲁",
    "enshrouded": "雾锁王国",
    "satisfactory": "幸福工厂",
    "no man's sky": "无人深空",
    # ---- 合作 / 派对 ----
    "amongus": "Among Us",
    "fallguys": "糖豆人",
    "rocketleague": "火箭联盟",
    "roblox": "Roblox",
    "deeprockgalactic": "深岩银河",
    "helldivers2": "绝地潜兵 2",
    "risk of rain 2": "雨中冒险 2",
    "ror2": "雨中冒险 2",
    "vampire survivors": "吸血鬼幸存者",
    "vampiresurvivors": "吸血鬼幸存者",
    "human fall flat": "人类一败涂地",
    "humanfallflat": "人类一败涂地",
    "overcooked2": "胡闹厨房 2",
    "moving out": "胡闹搬家",
    "goose goose duck": "鹅鸭杀",
    # ---- 体育 / 竞速 ----
    "f1 2023": "F1 2023",
    "f1 2024": "F1 2024",
    "ets2": "欧洲卡车模拟 2",
    "american truck simulator": "美国卡车模拟",
    "ats": "美国卡车模拟",
    "beamng": "BeamNG.drive",
    "beamngdrive": "BeamNG.drive",
    "forza": "极限竞速",
    "forzahorizon4": "极限竞速：地平线 4",
    "forzahorizon5": "极限竞速：地平线 5",
    "fh4": "极限竞速：地平线 4",
    "fh5": "极限竞速：地平线 5",
    "assettocorsa": "Assetto Corsa",
    "acc": "Assetto Corsa Competizione",
    "dirt 5": "尘埃 5",
    "nfs": "极品飞车",
    "need for speed": "极品飞车",
    # ---- 策略 / 建造 ----
    "civilization6": "文明 6",
    "civ6": "文明 6",
    "civ7": "文明 7",
    "civilization7": "文明 7",
    "total war": "全面战争",
    "totalwar": "全面战争",
    "age of empires iv": "帝国时代 4",
    "aoe4": "帝国时代 4",
    "aoede": "帝国时代 2 决定版",
    "company of heroes 3": "英雄连 3",
    "coh3": "英雄连 3",
    "xcom2": "幽浮 2",
    "eu4": "欧陆风云 4",
    "hoi4": "钢铁雄心 4",
    "ck3": "十字军之王 3",
    "victoria3": "维多利亚 3",
    "stellaris": "群星",
    "rimworld": "环世界",
    "factorio": "异星工厂",
    "oxygen not included": "缺氧",
    "oni": "缺氧",
    "planet zoo": "动物园之星",
    "planet coaster": "过山车之星",
    "cities skylines": "城市：天际线",
    "cities2": "城市：天际线 2",
    "cities skylines 2": "城市：天际线 2",
    "msfs": "微软模拟飞行",
    "flightsimulator": "微软模拟飞行",
    # ---- 格斗 / 动作 ----
    "tekken7": "铁拳 7",
    "tekken8": "铁拳 8",
    "streetfighter6": "街头霸王 6",
    "sf6": "街头霸王 6",
    "mk1": "真人快打 1",
    "mk11": "真人快打 11",
    "mortal kombat": "真人快打",
    "dbfz": "龙珠斗士 Z",
    "guiltygear": "罪恶装备",
    "brawlhalla": "英灵乱战",
    "doom": "毁灭战士",
    "doometernal": "毁灭战士：永恒",
    "doom2016": "毁灭战士 4",
    "halo": "光环",
    "haloinfinite": "光环：无限",
    "borderlands3": "无主之地 3",
    "borderlands2": "无主之地 2",
    "borderlands": "无主之地",
    "hollowknight": "空洞骑士",
    "ori": "奥日与黑暗森林",
    "ori2": "奥日与精灵意志",
    "celeste": "蔚蓝",
    "cuphead": "茶杯头",
    "deadcells": "死亡细胞",
    "hades": "哈迪斯",
    "hades2": "哈迪斯 2",
    "teardown": "Teardown 拆除",
    "hypercharge": "Hypercharge: Unboxed",
    # ---- 其他引擎常见进程 ----
    "aimlab": "Aim Lab",
    "kovaak": "Kovaak's FPS Aim Trainer",
    "osu": "osu!",
}

# 平台 / 启动器 / 反作弊 / 系统进程：即使名字看起来像游戏也不算游戏。
# 自定义清单（game_custom）优先级更高，用户明确添加时仍然可以识别。
NON_GAME_PROCESSES: set[str] = {
    "steam", "steamwebhelper", "steamservice", "steamerrorreporter",
    "epicgameslauncher", "epicgames", "egl", "epic online services",
    "battlenet", "battle.net", "battle.net browser", "agent",
    "riotclient", "riotclientservices", "riot client", "riotgames",
    "origin", "uplay", "ubisoft connect", "upc",
    "hoyokit", "hoyolauncher", "mihoyo launcher", "hoyolab",
    "wegame", "tgp", "qq", "qqgamelauncher", "wechat", "wechatweb",
    "gog galaxy", "galaxyclient", "galaxy", "amazon games", "amazongames",
    "xboxapp", "xbox gamingservices", "gamingservices", "gamingservices2",
    "gameoverlayui", "discord", "discordptb", "overlay", "obs64",
    "easyanticheat", "easyanticheat_windows", "battleye", "beservice",
    "vanguard", "vgtray", "vgcconfigservice", "killeranticheat", "ace",
    "unrealcefsubprocess", "crashreportclient", "crashreporter",
    "javaw", "java",  # Java 本体不是游戏；Minecraft 由路径/窗口标题识别
    "explorer", "svchost", "rundll32", "dllhost", "conhost", "dwm",
    "chrome", "msedge", "firefox", " opera", "brave", "360browser",
    "powershell", "cmd", "python", "pythonw", "node", "code",
}

# 动态壁纸 / 桌面美化工具：不是游戏，也不能靠"安装路径在 Steam 下"误判成游戏。
# Wallpaper Engine 的壁纸本体在 steamapps\workshop\content\431960 下，进程名五花八门，
# 因此既排除进程名前缀，也排除它的安装与创意工坊路径。
WALLPAPER_PROCESS_PREFIXES: tuple[str, ...] = (
    "wallpaper", "webwallpaper", "livelywallpaper", "rainmeter", "deskscape",
)
WALLPAPER_PROCESSES: set[str] = {
    "lively", "lively wallpaper", "deskscenes", "pushwallpaper",
}
WALLPAPER_PATH_MARKERS: tuple[str, ...] = (
    "steamapps\\workshop\\content\\431960",  # Wallpaper Engine 的 Steam AppID
    "steamapps\\common\\wallpaper_engine",
    "\\wallpaper engine\\",
    "\\wallpaper_engine\\",
    "\\lively wallpaper\\",
    "\\lively\\wallpapers\\",
    "\\deskscenes\\",
)

# 这些安装路径特征说明程序来自游戏平台 / 游戏目录，即使进程名陌生也识别为游戏。
GAME_PATH_MARKERS: tuple[str, ...] = (
    "steamapps\\common",
    "\\epic games\\",
    "\\gog galaxy\\games\\",
    "\\battle.net\\",
    "\\riot games\\",
    "\\xboxgames\\",
    "\\ubisoft\\",
    "\\ubisoft connect\\",
    "\\ea games\\",
    "\\rockstar games\\",
    "\\tencent\\games\\",
    "\\netease\\games\\",
    "\\mihoYo\\",
    "\\games\\",
    "\\game\\",
    "\\gameloop\\",
)

# 从路径里取游戏名时，忽略这些通用目录名。
GENERIC_FOLDERS: set[str] = {
    "bin", "bin64", "binary", "win64", "win32", "win", "game", "games",
    "engine", "content", "runtime", "launcher", "common", "steamapps",
    "epic games", "xboxgames", "binaries", "shipping", "release",
}

# 只有这些通用运行时进程允许靠窗口标题兜底识别为游戏（Steam 等永远不允许）。
TITLE_FALLBACK_PROCESSES: set[str] = {"javaw", "java"}

# 前台窗口标题关键词（用于 javaw 等通用进程的兜底识别）。
TITLE_GAME_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("minecraft", "我的世界"),
    ("英雄联盟", "英雄联盟"),
    ("league of legends", "英雄联盟"),
    ("原神", "原神"),
    ("genshin impact", "原神"),
    ("崩坏：星穹铁道", "崩坏：星穹铁道"),
    ("绝区零", "绝区零"),
    ("永劫无间", "永劫无间"),
    ("黑神话", "黑神话：悟空"),
    ("counter-strike", "Counter-Strike"),
    ("dota 2", "Dota 2"),
)


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


def _normalize(process_name: str) -> str:
    return (process_name or "").lower().removesuffix(".exe").strip()


def _pretty_name(raw: str) -> str | None:
    """把目录名 / 引擎进程名转成可读游戏名。"""
    if not raw:
        return None
    text = raw.strip()
    for suffix in (
        "-win64-shipping", "_win64_shipping", "-win32-shipping",
        "-shipping", "_win64", "_win32", "-win64", "-x64",
    ):
        if text.lower().endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.replace("_", " ").replace("-", " ").strip()
    if not text or text.lower() in GENERIC_FOLDERS or len(text) < 3:
        return None
    if text.isascii():
        text = " ".join(word[:1].upper() + word[1:] for word in text.split())
    return text


def _game_from_path(exe: str) -> str | None:
    """根据可执行文件所在目录推断游戏名。"""
    if not exe:
        return None
    path = exe.replace("/", "\\").lower()
    for marker in GAME_PATH_MARKERS:
        idx = path.find(marker)
        if idx < 0:
            continue
        tail = path[idx + len(marker) :].strip("\\")
        parts = [p for p in tail.split("\\") if p]
        # 跳过 bin / win64 这类通用子目录，取上一层的游戏名
        for part in parts[:-1]:
            if part not in GENERIC_FOLDERS:
                return _pretty_name(part)
        return _pretty_name(parts[-1]) if parts else None
    return None


def _is_wallpaper(name: str, exe: str = "") -> bool:
    """判断是不是动态壁纸 / 桌面美化进程（Wallpaper Engine、Lively 等）。"""
    if any(name.startswith(prefix) for prefix in WALLPAPER_PROCESS_PREFIXES):
        return True
    if name in WALLPAPER_PROCESSES:
        return True
    if exe:
        path = exe.replace("/", "\\").lower()
        if any(marker in path for marker in WALLPAPER_PATH_MARKERS):
            return True
    return False


def _game_from_title(title: str) -> str | None:
    if not title:
        return None
    lowered = title.lower()
    for keyword, display in TITLE_GAME_KEYWORDS:
        if keyword.lower() in lowered:
            return display
    return None


def match_game(
    process_name: str,
    extra: list[str] | None = None,
    exe: str = "",
    window_title: str = "",
) -> str | None:
    """把进程映射到游戏展示名；自定义清单优先（可覆盖内置名与排除项）。

    ``exe`` 与 ``window_title`` 是可选兜底：进程名不在内置表里时，用安装
    路径和前台窗口标题识别，从而覆盖市面上大部分游戏。
    """
    name = _normalize(process_name)
    stem = (process_name or "").removesuffix(".exe").strip()
    if not name:
        return None

    for item in extra or []:
        custom = (item or "").strip()
        if not custom:
            continue
        if "=" in custom:
            proc, label = custom.split("=", 1)
            if _normalize(proc) == name:
                return label.strip() or proc.strip()
        elif _normalize(custom) == name:
            return custom

    # 壁纸进程优先排除（自定义清单在上面已优先处理，仍可强制指定）
    if _is_wallpaper(name, exe):
        return None
    if name in NON_GAME_PROCESSES:
        # javaw 是通用运行时：只有前台标题明确是某个游戏时才算游戏
        if name in TITLE_FALLBACK_PROCESSES:
            return _game_from_title(window_title)
        return None
    if name in BUILTIN_GAMES:
        return BUILTIN_GAMES[name]

    # 引擎命名：xxx-Win64-Shipping.exe 基本都是游戏本体
    if any(
        tok in name
        for tok in ("-win64-shipping", "_win64_shipping", "-shipping", "win64-shipping")
    ):
        derived = _pretty_name(stem)
        if derived:
            return derived

    from_path = _game_from_path(exe)
    if from_path:
        return from_path
    return _game_from_title(window_title)


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
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    return kernel32, user32, ctypes, wintypes, PROCESSENTRY32W


def _exe_path(kernel32, ctypes, wintypes, pid: int) -> str:
    """取进程可执行文件全路径（用于路径特征识别与图标提取）。"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value if ok else ""
    except Exception:
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _foreground(user32, ctypes, wintypes):
    """返回 (前台 pid, 前台窗口标题)。"""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0, ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = int(user32.GetWindowTextLengthW(hwnd) or 0)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or ""
        return int(pid.value or 0), title
    except Exception:
        return 0, ""


def scan_processes() -> tuple[list[tuple[int, str, str]], int, str]:
    """返回 ([(pid, 进程名, exe路径)], 前台进程 pid, 前台窗口标题)。"""
    api = _win_api()
    if api is None:
        return [], 0, ""
    kernel32, user32, ctypes, wintypes, Entry = api
    TH32CS_SNAPPROCESS = 0x2

    foreground_pid, foreground_title = _foreground(user32, ctypes, wintypes)

    processes: list[tuple[int, str, str]] = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (None, 0, -1):
        return [], foreground_pid, foreground_title
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

    # 查 exe 路径用于路径特征识别与图标；跳过已知系统进程以控制开销。
    result: list[tuple[int, str, str]] = []
    for pid, name, _ in processes:
        normalized = _normalize(name)
        if normalized in NON_GAME_PROCESSES or normalized.startswith("svchost"):
            exe = ""
        else:
            exe = _exe_path(kernel32, ctypes, wintypes, pid)
        result.append((pid, name, exe))
    return result, foreground_pid, foreground_title


def detect_games(extra: list[str] | None = None) -> list[GameProcess]:
    """返回当前运行的游戏，前台游戏排在最前。"""
    processes, foreground_pid, foreground_title = scan_processes()
    games: list[GameProcess] = []
    for pid, name, exe in processes:
        title = foreground_title if pid == foreground_pid else ""
        display = match_game(name, extra, exe, title)
        if not display:
            continue
        games.append(
            GameProcess(
                pid=pid,
                process=_normalize(name),
                exe=exe,
                display_name=display,
                foreground=(pid == foreground_pid),
            )
        )
    # 同一游戏可能同时有启动器与本体进程，按进程名 + 展示名去重
    seen: set[tuple[str, str]] = set()
    unique: list[GameProcess] = []
    for game in games:
        key = (game.process, game.display_name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(game)
    unique.sort(key=lambda g: (not g.foreground, g.display_name))
    return unique


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
