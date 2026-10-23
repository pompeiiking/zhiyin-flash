"""Shared deterministic dates for institutional online and uploaded reports."""
import re
from datetime import date, datetime, timedelta, timezone

def parse_chsi_date(value: str) -> date | None:
    """解析报告里的日期（中文/短横线/斜杠三种常见写法）；认不出返回 None。"""
    match = re.search(r"(20\d{2})\D{1,4}(\d{1,2})\D{1,4}(\d{1,2})", (value or "").strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def is_report_expired(valid_until: str, *, today: date | None = None) -> bool:
    """报告有效期是否已经过去。

    学信网通常会把过期报告渲染成错误页，但版式变化时不保证；只要报告还
    解析出了字段，就必须再用「有效期至」兜一次，否则过期报告会被按
    `verified=true, confidence=1.0` 写进画像。
    """
    expiry = parse_chsi_date(valid_until)
    if expiry is None:
        return False
    current = today or datetime.now(timezone(timedelta(hours=8))).date()
    return expiry < current
