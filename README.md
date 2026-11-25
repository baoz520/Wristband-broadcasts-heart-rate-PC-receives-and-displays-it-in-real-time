# 心率监测（Windows 桌面）

从蓝牙手环/心率带的广播与标准心率服务（0x180D / 0x2A37）读取心率，并在桌面显示一个置顶悬浮窗。

![主界面](screenshots/main.png)

全窗口统一便当盒布局：Snow `#fafafa` 画布 + 白卡 / 唯一墨黑锚点卡，卡片尺寸分主次，统一 16px 间隙与 24px 圆角，hover 300ms 上浮放大；窗口变窄时自动退化为两栏或单栏，顺序不变（[窄屏预览](screenshots/main_narrow.png)）。历史、设置、进程选择器与悬浮窗都采用同一套网格与卡片材质（[历史](screenshots/history.png) · [设置](screenshots/settings.png) · [进程选择](screenshots/process_picker.png)）。

![悬浮窗](screenshots/floating.png)

## 功能

- **实时心率**：连接手环后订阅标准心率测量特征，逐跳刷新；支持从广播 Service Data 中直接解析心率。
- **悬浮窗开关**：主界面一键显示 / 隐藏桌面置顶悬浮窗。悬浮窗可拖动、锁定位置、右键菜单、双击打开主界面。
- **设备管理开关**：打开后持续扫描附近 BLE 设备；关闭后停止扫描并断开手环，节省电量。
- **设备列表**：显示名称、MAC、RSSI 信号格，标注“广播心率 / 心率服务”，一键连接或断开。
- **自动重连**：断线后按 2 / 4 / 8 / 16 / 30 秒退避重连，可单独关闭。
- **历史记录**：点击「查看历史数据」弹出独立的历史记录窗口，逐条显示每次连接的设备、日期、连接时长、最低 / 最高 / 平均心率，并为每次连接绘制心率曲线。每条记录带「删除」按钮，可单条清除。会话与曲线自动持久化，最多保留最近 50 次连接；旧版本无曲线的记录仍显示统计信息。
- **设置**：主界面「设置」按钮打开设置窗口。可自定义悬浮窗宽度、不透明度、心跳图标 / 心率区间 / 设备名的显示；可开启游戏心率检测（见下）。设置即时生效并持久化。
- **进程快捷添加**：游戏检测设置里点「从运行进程中添加…」，会列出当前所有进程（图标、进程名、PID、安装路径），可搜索、双击或点击「添加为游戏」。显示名可改，添加后立即写入自定义清单并生效，无需重启或重新扫描。
- **游戏心率检测**：开启后按设定间隔扫描 Windows 进程。识别方式为内置 150+ 主流游戏进程名 + 安装路径特征（`steamapps\common`、`Epic Games`、`XboxGames` 等）+ Unreal 引擎命名（`xxx-Win64-Shipping.exe`），因此市面上大部分从游戏平台安装的游戏都能识别；设置里还可追加 `进程名=显示名`。**Steam、Epic 启动器、战网、WeGame、米哈游启动器不算游戏进程**，**Wallpaper Engine / Lively 等动态壁纸也不算游戏**（包括 Steam 创意工坊壁纸），只有游戏本体参与统计。识别到游戏后，悬浮窗主数字切换为该场最新心率并显示本场最低–最高区间与游戏名；每场游戏作为一条带游戏图标的记录存入历史，显示游戏时长与心率曲线。关闭游戏或切换游戏时自动结算。无第三方依赖（使用 Windows 原生 API），非 Windows 平台安全跳过。
- **游戏中悬浮窗样式**：设置里可选「隐藏背景，仅留数据」（默认，去掉拟物底板和外阴影，只留亮色数字悬在游戏画面上）、「自动隐藏整个悬浮窗」（退出游戏后自动恢复）或「保持原样」。
- **历史数据开关**：开启后，断连或数据过期时，悬浮窗 / 主界面会回退展示该手环最近一次的历史心率；原始采样按手环 MAC 保存（最近 200 条）。
- **后台运行**：关闭窗口时可选择「最小化」（缩到托盘，监测和悬浮窗继续工作）或「直接关闭」（退出程序）；勾选「不再提示」后记住本次选择，之后点关闭直接执行。托盘菜单的「关闭时询问」可随时恢复询问。
- **自绘标题栏**：最小化 / 最大化 / 关闭均为自绘便当盒风格按钮（无系统原生按钮），支持拖动窗口、双击标题栏最大化、四边拖拽缩放。

## 运行

需要 Windows 10/11、Python 3.10+、蓝牙适配器。

```bat
pip install -r requirements.txt
python main.py
```

或直接双击 `启动心率监测.bat`（使用 pythonw，无控制台窗口）。

## 使用说明

1. 打开手环的蓝牙；部分手环需要在 App 或设备设置里开启“心率广播 / 广播心率”，否则只有连接后才能读到数据。
2. 打开主界面的“设备管理”，在“附近设备”里找到手环，点“连接”。
3. 连接成功后心率会实时刷新，同时可打开“悬浮窗”。
4. 下次启动会自动连接上次设备（需“自动重连”开启）。
5. 点击右上角 **×** 会弹出「最小化 / 直接关闭」选择；勾选「不再提示」后按本次选择直接执行。想恢复询问，请在托盘菜单勾选「关闭时询问」。

## 手环兼容性

大多数手环/心率带暴露标准心率服务 `0x180D`（特征 `0x2A37`），可直接使用。
若设备只提供厂商私有广播格式，可在 `heartbeat/hr.py` 的 `VENDOR_PARSERS` 中注册解析器：

```python
from heartbeat.hr import VENDOR_PARSERS

def parse_my_band(payload: bytes):
    return payload[3]  # 以实际协议为准

VENDOR_PARSERS[0x0157] = parse_my_band   # 公司 ID
```

## 打包为 exe（可选）

```bat
pip install pyinstaller
pyinstaller --noconsole --onefile --name 心率监测 --icon NONE main.py
```

## 文件结构

```
main.py                 入口
heartbeat/app.py        托盘、单实例、模块协同
heartbeat/ble.py        蓝牙扫描 / 连接 / 重连线程
heartbeat/hr.py         心率解析与区间
heartbeat/main_window.py 主界面
heartbeat/chrome.py     自绘标题栏、无边框窗口外壳、关闭确认弹窗
heartbeat/history_window.py 历史记录窗口（逐次连接的统计与曲线、删除）
heartbeat/settings_window.py 设置窗口（悬浮窗自定义、游戏检测）
heartbeat/game.py       Windows 游戏进程检测与图标提取
heartbeat/process_picker.py 运行进程选择器（快捷添加游戏进程）
heartbeat/floating.py   悬浮窗（含自定义外观与游戏态）
heartbeat/widgets.py    便当盒卡片/响应式网格与自绘控件
heartbeat/theme.py      配色与样式
heartbeat/config.py     设置持久化（%APPDATA%\HeartbeatMonitor）
tools/preview.py        离屏渲染界面截图
```

## 自测

```bat
python tests/test_hr.py
python tests/test_ui.py
```
