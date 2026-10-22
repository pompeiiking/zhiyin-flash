"""学籍时间换算：入学日期 → 当前学习阶段。

学信网在线验证报告给出的是**入学日期**，不是「现在大几」。两者之间只差一次
确定性换算：从入学日满一学年就是下一级。这次换算放在内核层，是因为它不依赖
任何 IO，也不能让调用方各自写一份口径 —— 少一次换算，画像里就会永远缺
「当前学习阶段」；口径漂一次，同一个入学日期就会在不同页面显示成两个年级。

边界刻意保守：

* 日期读不出来、入学日期在未来、算出来超出本科 1–4 年，一律返回 `None`，
  由采集清单去问本人，**不猜一个「大一」顶上**；
* 学年按入学日的周年切分（8 月 22 日入学，次年 8 月 22 日升一级），
  不按自然年 1 月 1 日切 —— 寒假跨年时按自然年会多算一级。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

#: 学籍日期按北京时间解释（学信网报告里的日期没有时区）。
CHINA_TZ = timezone(timedelta(hours=8))

#: 画像只支持本科大一到大四（见 `DefaultProfileService.correct_field`）。
MAX_STUDY_YEAR = 4

_STUDY_YEAR_LABELS = {1: "大一", 2: "大二", 3: "大三", 4: "大四"}

_DATE_PATTERN = re.compile(
    r"(?P<year>(?:19|20)\d{2})\D{0,4}(?P<month>\d{1,2})\D{0,4}(?P<day>\d{1,2})"
)


def parse_academic_date(value: object) -> Optional[date]:
    """从学信网常见的日期写法里取一个真实日期；取不到返回 `None`。

    支持 `2024-08-22`、`2024/8/22`、`2024.08.22`、`2024年8月22日`。
    不补默认月份/日期 —— 「2024 年」只说明年份，不能拿来算年级。
    """
    text = str(value or "").strip()
    if not text:
        return None
    match = _DATE_PATTERN.search(text)
    if match is None:
        return None
    try:
        return date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
    except ValueError:
        return None


def _anniversary(year: int, enrolled: date) -> date:
    """入学日在某一年的周年；2 月 29 日入学时，平年按 2 月 28 日算。"""
    try:
        return date(year, enrolled.month, enrolled.day)
    except ValueError:
        return date(year, enrolled.month, 28)


def study_year_from_enrollment(
    enrolled_at: object, *, today: Optional[date] = None
) -> Optional[str]:
    """按入学日期推算当前学习阶段（大一…大四）。

    例：2024-08-22 入学，2026-10-22 时已经过完两个学年、进入第三个学年，
    返回「大三」。2026-05-01 时还没到第二个周年，返回「大二」。
    """
    enrolled = parse_academic_date(enrolled_at)
    current = today or datetime.now(CHINA_TZ).date()
    if enrolled is None or current < enrolled:
        return None
    completed_years = current.year - enrolled.year
    if current < _anniversary(current.year, enrolled):
        completed_years -= 1
    index = completed_years + 1
    return _STUDY_YEAR_LABELS.get(index)


def study_year_valid_to(
    enrolled_at: object, *, today: Optional[date] = None
) -> Optional[datetime]:
    """推算出的年级有效到下一次入学周年之前（北京时间当天 23:59:59）。

    超过这一天，这条推算就不再代表当前年级；画像读侧会把它当作过期记录，
    采集清单重新问本人。写死的「大三」比缺失更糟 —— 它会在一年后仍然被当成事实。
    """
    enrolled = parse_academic_date(enrolled_at)
    current = today or datetime.now(CHINA_TZ).date()
    if enrolled is None or current < enrolled:
        return None
    if study_year_from_enrollment(enrolled, today=current) is None:
        return None
    anniversary = _anniversary(current.year, enrolled)
    if current >= anniversary:
        anniversary = _anniversary(current.year + 1, enrolled)
    boundary = anniversary - timedelta(days=1)
    return datetime.combine(boundary, datetime.min.time(), tzinfo=CHINA_TZ).replace(
        hour=23, minute=59, second=59
    )


__all__ = [
    "CHINA_TZ",
    "MAX_STUDY_YEAR",
    "parse_academic_date",
    "study_year_from_enrollment",
    "study_year_valid_to",
]
