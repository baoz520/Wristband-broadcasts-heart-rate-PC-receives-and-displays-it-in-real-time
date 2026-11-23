"""心率解析自测：python tests/test_hr.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heartbeat.hr import (  # noqa: E402
    heart_rate_zone,
    is_heart_rate_service,
    parse_advertisement,
    parse_heart_rate_measurement,
)


def main() -> None:
    assert parse_heart_rate_measurement(bytes([0x00, 72])) == 72
    assert parse_heart_rate_measurement(bytes([0x01, 0x2C, 0x01])) is None
    assert parse_heart_rate_measurement(bytes([0x01, 0x4B, 0x00])) == 75
    assert parse_heart_rate_measurement(bytes([0x00, 0])) is None
    assert parse_heart_rate_measurement(None) is None

    hr_uuid = "0000180d-0000-1000-8000-00805f9b34fb"
    assert is_heart_rate_service([hr_uuid])
    assert is_heart_rate_service(["180d"])
    assert not is_heart_rate_service(["180f"])

    assert parse_advertisement({hr_uuid: bytes([0x00, 88])}) == 88
    assert parse_advertisement({"180d": bytes([0x00, 91])}) == 91
    assert parse_advertisement({hr_uuid: bytes([101])}) == 101
    assert parse_advertisement({"180f": bytes([0x00, 88])}) is None
    assert parse_advertisement({}, {0x1234: bytes([0x00, 50])}) is None

    assert heart_rate_zone(55) == "静息"
    assert heart_rate_zone(75) == "日常"
    assert heart_rate_zone(120) == "燃脂"
    assert heart_rate_zone(145) == "有氧"
    assert heart_rate_zone(170) == "峰值"
    print("all hr tests passed")


if __name__ == "__main__":
    main()
