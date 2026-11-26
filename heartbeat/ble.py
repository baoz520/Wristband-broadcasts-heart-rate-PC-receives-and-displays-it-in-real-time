"""蓝牙扫描与心率订阅。

BleWorker 在独立线程里跑 asyncio 事件循环：
* 持续扫描 BLE 广播，解析广播中的心率（如果有）；
* 连接设备后订阅标准心率服务 0x2A37，实时推送心率；
* 断线后按 2/4/8/16/30 秒退避自动重连。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QThread, Signal

from .hr import (
    BATTERY_LEVEL_UUID,
    HR_MEASUREMENT_UUID,
    HR_SERVICE_UUID,
    is_heart_rate_service,
    parse_advertisement,
    parse_heart_rate_measurement,
)

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except Exception:  # pragma: no cover - 依赖缺失时给出友好提示
    BleakClient = None  # type: ignore[assignment]
    BleakScanner = None  # type: ignore[assignment]
    BLEDevice = object  # type: ignore[assignment,misc]
    AdvertisementData = object  # type: ignore[assignment,misc]


@dataclass
class DeviceInfo:
    address: str
    name: str
    rssi: int
    has_hr_service: bool = False
    hr_adv: Optional[int] = None
    last_seen: float = field(default_factory=time.monotonic)

    @property
    def source(self) -> str:
        if self.hr_adv is not None:
            return "广播心率"
        if self.has_hr_service:
            return "支持心率服务"
        return "普通设备"


class BleWorker(QThread):
    devicesChanged = Signal(list)      # list[DeviceInfo]
    heartRate = Signal(int, str, str, str)  # bpm, 来源, 地址, 设备名
    linkChanged = Signal(str, str, str)  # 状态, 地址, 名称
    batteryChanged = Signal(int)
    log = Signal(str)

    def __init__(self, auto_reconnect: bool = True, parent=None):
        super().__init__(parent)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None

        self._scanner = None
        self._scanning = False
        self._client = None
        self._conn_task: Optional[asyncio.Task] = None
        self._retry_task: Optional[asyncio.Task] = None
        self._house_task: Optional[asyncio.Task] = None

        self._devices: dict[str, DeviceInfo] = {}
        self._last_emit = 0.0
        self._last_adv_hr: dict[str, tuple[int, float]] = {}
        self._last_battery: Optional[int] = None

        self._want_scan = True
        self._want_address = ""
        self._want_name = ""
        self._connected_address = ""
        self._connected_name = ""
        self._auto_reconnect = auto_reconnect
        self._closing = False

    # ------------------------------------------------------------------ 外部 API
    def start_scan(self) -> None:
        self._want_scan = True
        self._submit(self._ensure_scan())

    def stop_scan(self) -> None:
        self._want_scan = False
        self._submit(self._stop_scan())

    def connect_device(self, address: str, name: str = "") -> None:
        if not address:
            return
        self._want_address = address
        self._want_name = name or address
        self._submit(self._restart_connection())

    def disconnect_device(self) -> None:
        self._want_address = ""
        self._submit(self._drop_connection(notify=True))

    def set_auto_reconnect(self, enabled: bool) -> None:
        self._auto_reconnect = bool(enabled)

    def shutdown(self) -> None:
        self._closing = True
        self._want_scan = False
        self._want_address = ""
        self._submit(self._shutdown())
        if self.isRunning():
            self.wait(5000)

    # ------------------------------------------------------------------ 线程内部
    def _submit(self, coro) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(coro, loop)
                return
            except RuntimeError:
                pass
        if hasattr(coro, "close"):
            coro.close()

    def run(self) -> None:
        if BleakScanner is None:
            self.log.emit("缺少 bleak 依赖，请先执行：pip install bleak PySide6")
            self.linkChanged.emit("error", "", "")
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main())
        except Exception as exc:  # pragma: no cover
            self.log.emit(f"蓝牙线程异常：{exc}")
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                loop.close()
                self._loop = None

    async def _main(self) -> None:
        self._stop_event = asyncio.Event()
        self._house_task = asyncio.create_task(self._housekeeping())
        if self._want_scan:
            await self._ensure_scan()
        if self._want_address:
            await self._restart_connection()
        await self._stop_event.wait()
        await self._cleanup()

    async def _cleanup(self) -> None:
        self._closing = True
        for task in (self._retry_task, self._house_task):
            if task and not task.done():
                task.cancel()
        if self._conn_task and not self._conn_task.done():
            self._conn_task.cancel()
            try:
                await self._conn_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._client is not None:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
            except Exception:
                pass
            self._client = None
        await self._stop_scan(announce=False)

    async def _shutdown(self) -> None:
        self._closing = True
        self._want_scan = False
        if self._stop_event is not None:
            self._stop_event.set()

    # ------------------------------------------------------------------ 扫描
    async def _ensure_scan(self) -> None:
        if self._closing or not self._want_scan or self._scanner is not None:
            return
        try:
            self._scanner = BleakScanner(detection_callback=self._on_detect)
            await self._scanner.start()
            self._scanning = True
            self.log.emit("开始扫描附近的蓝牙设备")
            if not self._want_address and self._client is None:
                self.linkChanged.emit("idle", "", "")
        except Exception as exc:
            self._scanner = None
            self._scanning = False
            self.linkChanged.emit("error", "", "")
            self.log.emit(f"扫描启动失败：{exc}")
            if self._retry_task and not self._retry_task.done():
                return
            self._retry_task = asyncio.create_task(self._retry_scan())

    async def _retry_scan(self) -> None:
        try:
            while not self._closing and self._want_scan and self._scanner is None:
                await asyncio.sleep(5)
                if self._closing:
                    break
                await self._ensure_scan()
        except asyncio.CancelledError:
            pass

    async def _stop_scan(self, announce: bool = True) -> None:
        scanner = self._scanner
        self._scanner = None
        self._scanning = False
        if scanner is not None:
            try:
                await scanner.stop()
            except Exception:
                pass
            if announce:
                self.log.emit("已停止扫描")

    def _on_detect(self, device: BLEDevice, adv: AdvertisementData) -> None:
        try:
            address = device.address
            name = (adv.local_name or device.name or "").strip() or "未命名设备"
            uuids = list(getattr(adv, "service_uuids", None) or [])
            has_hr = is_heart_rate_service(uuids)
            hr_adv = parse_advertisement(
                getattr(adv, "service_data", None),
                getattr(adv, "manufacturer_data", None),
            )
            rssi = int(getattr(adv, "rssi", None) or -127)
            self._devices[address] = DeviceInfo(
                address=address,
                name=name,
                rssi=rssi,
                has_hr_service=has_hr or HR_SERVICE_UUID in [u.lower() for u in uuids],
                hr_adv=hr_adv,
            )
            if hr_adv is not None:
                last = self._last_adv_hr.get(address)
                now = time.monotonic()
                if last is None or (now - last[1] > 1.5) or last[0] != hr_adv:
                    self._last_adv_hr[address] = (hr_adv, now)
                    if not self._want_address or address == self._want_address:
                        self.heartRate.emit(hr_adv, "广播", address, name)
            now = time.monotonic()
            if now - self._last_emit > 0.6:
                self._last_emit = now
                self._emit_devices()
        except Exception:
            pass

    def _emit_devices(self) -> None:
        devices = sorted(
            self._devices.values(),
            key=lambda d: (
                not (d.hr_adv is not None or d.has_hr_service),
                -d.rssi,
            ),
        )
        self.devicesChanged.emit(devices[:20])

    async def _housekeeping(self) -> None:
        try:
            while not self._closing:
                await asyncio.sleep(1.2)
                if self._closing:
                    break
                if self._scanning:
                    cutoff = time.monotonic() - 18
                    stale = [
                        addr for addr, d in self._devices.items()
                        if d.last_seen < cutoff and addr != self._want_address
                    ]
                    for addr in stale:
                        self._devices.pop(addr, None)
                        self._last_adv_hr.pop(addr, None)
                    self._emit_devices()
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------ 连接
    async def _restart_connection(self) -> None:
        address, name = self._want_address, self._want_name
        task = self._conn_task
        self._conn_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if not address or self._closing or self._want_address != address:
            return
        self._conn_task = asyncio.create_task(self._connection_loop(address, name))

    async def _connection_loop(self, address: str, name: str) -> None:
        if self._scanning:
            await self._stop_scan(announce=False)
        attempt = 0
        ever_linked = False
        while not self._closing and self._want_address == address:
            # 重连等待期间恢复扫描：边扫描边等待下一次连接尝试，这样
            # 设备掉线后既能重新发现设备，也能继续接收广播心率。
            if self._scanning:
                await self._stop_scan(announce=False)
            state = "reconnecting" if (attempt > 0 or ever_linked) else "connecting"
            self.linkChanged.emit(state, address, name)
            client = None
            try:
                client = BleakClient(
                    address,
                    disconnected_callback=self._on_disconnected,
                    timeout=20.0,
                )
                if attempt == 0:
                    self.log.emit(f"正在连接 {name}（{address}）")
                await client.connect()
                self._client = client
                self._connected_address = address
                self._connected_name = name
                ever_linked = True
                attempt = 0
                self.linkChanged.emit("connected", address, name)
                self.log.emit(f"已连接 {name}")
                await self._setup_heart_rate(client)
                await self._read_battery(client)
                while (
                    client.is_connected
                    and not self._closing
                    and self._want_address == address
                ):
                    await asyncio.sleep(0.4)
                if client.is_connected:
                    self.log.emit("正在断开连接")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log.emit(f"连接失败：{exc}")
            finally:
                if client is not None:
                    try:
                        if client.is_connected:
                            await client.disconnect()
                    except Exception:
                        pass
                if self._client is client:
                    self._client = None
                    self._connected_address = ""
                    self._connected_name = ""
                self._last_battery = None
                self.batteryChanged.emit(-1)

            if self._closing or self._want_address != address:
                break
            if not self._auto_reconnect:
                break
            attempt += 1
            delay = min(30, 2 ** attempt)
            self.linkChanged.emit("reconnecting", address, name)
            self.log.emit(f"心率连接中断，{delay} 秒后自动重连")
            # 重连等待阶段重新开启扫描（连接尝试前会在循环顶部停掉）。
            if self._want_scan:
                await self._ensure_scan()
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise

        if self._want_address == address and not self._closing:
            self._want_address = ""
            self.linkChanged.emit("disconnected", address, name)
        elif not self._want_address:
            self.linkChanged.emit("idle", "", "")

    async def _setup_heart_rate(self, client) -> None:
        try:
            char = client.services.get_characteristic(HR_MEASUREMENT_UUID)
        except Exception:
            char = None
        if char is None:
            self.log.emit("该设备没有标准心率服务（0x2A37），无法读取实时心率")
            return
        try:
            await client.start_notify(HR_MEASUREMENT_UUID, self._on_hr)
            self.log.emit("已订阅心率测量通知")
        except Exception as exc:
            self.log.emit(f"订阅心率通知失败：{exc}")
        try:
            data = await client.read_gatt_char(HR_MEASUREMENT_UUID)
            bpm = parse_heart_rate_measurement(data)
            if bpm:
                self.heartRate.emit(bpm, "心率服务", self._connected_address, self._connected_name)
        except Exception:
            pass

    async def _read_battery(self, client) -> None:
        try:
            data = await client.read_gatt_char(BATTERY_LEVEL_UUID)
            if data:
                level = int(data[0])
                if level != self._last_battery:
                    self._last_battery = level
                    self.batteryChanged.emit(level)
        except Exception:
            pass

    def _on_hr(self, sender, data: bytearray) -> None:
        bpm = parse_heart_rate_measurement(data)
        if bpm:
            self.heartRate.emit(bpm, "心率服务", self._connected_address, self._connected_name)

    def _on_disconnected(self, client) -> None:
        self.log.emit("设备连接已断开")

    async def _drop_connection(self, notify: bool = True) -> None:
        self._want_address = ""
        task = self._conn_task
        self._conn_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        client = self._client
        self._client = None
        if client is not None:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception:
                pass
            self.batteryChanged.emit(-1)
        if notify:
            self.linkChanged.emit("idle", "", "")
            self.log.emit("已断开连接")
