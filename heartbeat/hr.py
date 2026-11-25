"""心率数据解析与心率区间计算。

标准蓝牙心率服务：
    服务 0x180D / 特征 0x2A37（Heart Rate Measurement）
    广播包中的 Service Data（UUID 0x180D）也有设备直接携带心率。

部分厂商（华为、小米、佳明等）使用私有广播格式。若你的手环属于这种，
可在 VENDOR_PARSERS 中按公司 ID 注册解析函数，返回 bpm 或 None。
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median, pstdev
from typing import Callable, Iterable, Mapping, Optional, Sequence

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
    """绝对心率区间，仅作数据标注；状态判断请用 HeartStateTracker。"""
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


# 状态色沿用既有玻璃色板，不引入第二套强调色。
STATE_COLORS = {
    "采集中": "#7c9cc4",
    "放松": "#7c9cc4",
    "平静": "#8fb8d8",
    "活跃": "#e4b863",
    "兴奋": "#f0a35e",
    "紧张": "#f87171",
    "恢复中": "#8fb8d8",
}


@dataclass(frozen=True)
class HeartState:
    """相对个人近期基线的状态判断结果。"""

    label: str
    color: str
    delta: float = 0.0      # 当前心率相对基线
    baseline: float = 0.0   # 个人近期基线
    trend: float = 0.0      # 最近一分钟变化
    confidence: float = 0.0


class HeartStateTracker:
    """根据同一设备近期心率判断状态，带基线自适应和切换迟滞。

    心率本身不能确证情绪；这里给出的是“相对你自己最近状态”的倾向：
    用最近约四分钟的中位数作基线，排除最后 20 秒避免当前波动污染基线，
    再结合趋势与波动度区分兴奋（升高且波动大）和紧张（持续升高且波动小）。
    """

    WINDOW_SECONDS = 240.0
    MIN_SAMPLES = 10
    MIN_SPAN = 25.0

    def __init__(self) -> None:
        self._state = HeartState("采集中", STATE_COLORS["采集中"])
        self._streak = 0

    def update(self, samples: Sequence[Sequence[float]]) -> HeartState:
        raw = self._classify(samples)
        if raw.label == self._state.label:
            self._streak = 0
            return self._state
        # 采集中立即显示；强信号可直接切换，弱信号需要连续两次确认，避免闪烁。
        if raw.label == "采集中" or raw.confidence >= 0.82:
            self._state = raw
            self._streak = 0
            return raw
        self._streak += 1
        if self._streak >= 2:
            self._state = raw
            self._streak = 0
        return self._state

    def _classify(self, samples: Sequence[Sequence[float]]) -> HeartState:
        collected: list[tuple[float, float]] = []
        for item in samples or ():
            try:
                ts, value = float(item[0]), float(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            if 35.0 <= value <= 220.0:
                collected.append((ts, value))
        if not collected:
            return HeartState("采集中", STATE_COLORS["采集中"])

        collected.sort(key=lambda pair: pair[0])
        now = collected[-1][0]
        recent = [pair for pair in collected if pair[0] >= now - self.WINDOW_SECONDS]
        if len(recent) < self.MIN_SAMPLES or recent[-1][0] - recent[0][0] < self.MIN_SPAN:
            return HeartState("采集中", STATE_COLORS["采集中"])

        values = [value for _, value in recent]
        # 基线取一分钟以前的中位数，避免刚发生的波动把自己算进基线；
        # 样本不足时退化为去掉最后 20 秒。
        baseline_values = [value for ts, value in recent if ts <= now - 60.0]
        if len(baseline_values) < 6:
            baseline_values = [value for ts, value in recent if ts <= now - 20.0]
        if len(baseline_values) < 6:
            baseline_values = values[:-3]
        if len(baseline_values) < 6:
            return HeartState("采集中", STATE_COLORS["采集中"])
        baseline = median(baseline_values)

        current_values = [value for ts, value in recent if ts >= now - 15.0]
        current = median((current_values or values)[-10:])
        previous_values = [
            value for ts, value in recent if now - 75.0 <= ts <= now - 30.0
        ]
        previous = median(previous_values[-10:]) if previous_values else baseline
        trend = current - previous
        variability = pstdev(values[-40:]) if len(values) >= 4 else 0.0
        delta = current - baseline

        if current >= 160.0 and delta >= 6.0:
            label = "紧张" if variability < 9.0 else "兴奋"
        elif delta >= 22.0:
            label = "紧张" if variability < 8.0 else "兴奋"
        elif delta >= 12.0:
            if trend >= 4.0 and variability >= 6.0:
                label = "兴奋"
            elif trend >= 1.0 and variability < 7.0:
                label = "紧张"
            else:
                label = "活跃"
        elif delta >= 7.0:
            label = "恢复中" if trend <= -4.0 else "活跃"
        elif delta <= -10.0:
            label = "放松"
        elif delta <= -5.0 and trend <= 0.0 and variability <= 6.0:
            label = "放松"
        elif trend <= -5.0 and delta >= 5.0:
            label = "恢复中"
        else:
            label = "平静"

        strength = min(abs(delta), 25.0) / 25.0
        volume = min(len(recent), 120.0) / 120.0
        wiggle = min(variability, 12.0) / 12.0
        confidence = min(1.0, 0.32 + 0.28 * volume + 0.3 * strength + 0.1 * wiggle)
        return HeartState(
            label, STATE_COLORS[label],
            round(delta, 1), round(baseline, 1), round(trend, 1), round(confidence, 2),
        )


def rssi_text(rssi: int | None) -> str:
    if rssi is None:
        return "—"
    return f"{rssi} dBm"
