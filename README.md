# 心率监测（Windows 桌面）

从蓝牙手环/心率带的广播与标准心率服务（0x180D / 0x2A37）读取心率，并在桌面显示一个置顶悬浮窗。

![主界面](screenshots/main.png)

![悬浮窗](screenshots/floating.png)

## 功能

- **实时心率**：连接手环后订阅标准心率测量特征，逐跳刷新；支持从广播 Service Data 中直接解析心率。
- **悬浮窗开关**：主界面一键显示 / 隐藏桌面置顶悬浮窗。悬浮窗可拖动、锁定位置、右键菜单、双击打开主界面。
- **设备管理开关**：打开后持续扫描附近 BLE 设备；关闭后停止扫描并断开手环，节省电量。
- **设备列表**：显示名称、MAC、RSSI 信号格，标注“广播心率 / 心率服务”，一键连接或断开。
- **自动重连**：断线后按 2 / 4 / 8 / 16 / 30 秒退避重连，可单独关闭。
- **历史数据**：开启「历史数据」开关后，断连或数据过期时，悬浮窗 / 主界面会回退展示该手环最近一次的历史心率；历史数据按手环 MAC 保存（最近 200 条）。
- **后台运行**：关闭窗口后缩到托盘，监测和悬浮窗继续工作；托盘菜单可控制悬浮窗与设备管理。

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
heartbeat/floating.py   悬浮窗
heartbeat/widgets.py    自绘控件
heartbeat/theme.py      配色与样式
heartbeat/config.py     设置持久化（%APPDATA%\HeartbeatMonitor）
```
