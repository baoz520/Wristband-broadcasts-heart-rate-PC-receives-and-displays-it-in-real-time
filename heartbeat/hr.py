"""心率数据解析与心率区间计算。

标准蓝牙心率服务：
    服务 0x180D / 特征 0x2A37（Heart Rate Measurement）
    广播包中的 Service Data（UUID 0x180D）也有设备直接携带心率。

部分厂商（华为、小米、佳明等）使用私有广播格式。若你的手环属于这种，
可在 VENDOR_PARSERS 中按公司 ID 注册解析函数，返回 bpm 或 None。
"""

from __future__ import annotations

from typing import Callable, Iterable, Mapping, Optional

HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

VENDOR_PARSERS: dict[int, Callable[[bytes], Optional[int]]] = {}


def uuid_short(uuid: str) -> str:
    """把完整 128 位 UUID 归一化为 4 位短 UUID。"""
    u = uuid.lower().strip()
    if len(u) == 36:
        return u[4:8]
    if u.startswith("0x"):
        return u[2:]
    return u


def is_heart_rate_service(uuids: Iterable[str] | None) -> bool:
    return any(uuid_short(u) == "180d" for u in (uuids or []))


def parse_heart_rate_measurement(data: bytes | bytearray | None) -> Optional[int]:
    """解析 0x2A37 心率测量值。"""
    if not data:
        return None
    buf = bytes(data)
    flags = buf[0]
    if flags & 0x01:
        if len(buf) < 3:
            return None
        bpm = int.from_bytes(buf[1:3], "little")
    else:
        if len(buf) < 2:
            return None
        bpm = buf[1]
    return bpm if 20 <= bpm <= 250 else None


def parse_advertisement(
    service_data: Mapping[str, bytes] | None,
    manufacturer_data: Mapping[int, bytes] | None = None,
) -> Optional[int]:
    """从蓝牙广播中提取心率，兼容标准 0x180D Service Data 与厂商私有格式。"""
    for uuid, payload in (service_data or {}).items():
        if uuid_short(str(uuid)) != "180d" or not payload:
            continue
        bpm = parse_heart_rate_measurement(payload)
        if bpm:
            return bpm
        if len(payload) == 1 and 20 <= payload[0] <= 250:
            return payload[0]

    for company_id, payload in (manufacturer_data or {}).items():
        parser = VENDOR_PARSERS.get(int(company_id))
        if parser is None or not payload:
            continue
        try:
            bpm = parser(bytes(payload))
        except Exception:
            bpm = None
        if bpm and 20 <= bpm <= 250:
            return bpm
    return None


def heart_rate_zone(bpm: int) -> str:
    if bpm <= 0:
        return "静息"
    if bpm < 60:
        return "静息"
    if bpm < 100:
        return "日常"
    if bpm < 130:
        return "燃脂"
    if bpm < 160:
        return "有氧"
    return "峰值"


def rssi_text(rssi: int | None) -> str:
    if rssi is None:
        return "—"
    return f"{rssi} dBm"
