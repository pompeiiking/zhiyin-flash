"""入学日期 → 学习阶段的换算口径。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from zhiyin_kernel.academic_time import (
    parse_academic_date,
    study_year_from_enrollment,
    study_year_valid_to,
)


def test_parse_accepts_the_date_shapes_chsi_uses() -> None:
    assert parse_academic_date("2024-08-22") == date(2024, 8, 22)
    assert parse_academic_date("2024/8/22") == date(2024, 8, 22)
    assert parse_academic_date("2024.08.22") == date(2024, 8, 22)
    assert parse_academic_date("2024年8月22日") == date(2024, 8, 22)
    assert parse_academic_date("2024年08月22日 10:00") == date(2024, 8, 22)


def test_parse_refuses_values_that_are_not_a_full_date() -> None:
    assert parse_academic_date("2024年") is None
    assert parse_academic_date("2024-08") is None
    assert parse_academic_date("2024-02-30") is None
    assert parse_academic_date("") is None
    assert parse_academic_date(None) is None


def test_study_year_advances_on_the_enrollment_anniversary() -> None:
    assert study_year_from_enrollment("2024-08-22", today=date(2024, 9, 1)) == "大一"
    assert study_year_from_enrollment("2024-08-22", today=date(2025, 8, 21)) == "大一"
    assert study_year_from_enrollment("2024-08-22", today=date(2025, 8, 22)) == "大二"
    assert study_year_from_enrollment("2024-08-22", today=date(2026, 10, 22)) == "大三"


def test_spring_semester_does_not_jump_a_grade_at_new_year() -> None:
    """按自然年切会在一月把大二算成大三；周年切分不会。"""
    assert study_year_from_enrollment("2024-08-22", today=date(2026, 1, 10)) == "大二"
    assert study_year_from_enrollment("2024-08-22", today=date(2026, 5, 1)) == "大二"


def test_out_of_range_or_unparseable_enrollment_is_not_guessed() -> None:
    assert study_year_from_enrollment("", today=date(2026, 10, 22)) is None
    assert study_year_from_enrollment("2026-09-01", today=date(2026, 10, 22)) == "大一"
    assert study_year_from_enrollment("2026-12-01", today=date(2026, 10, 22)) is None
    assert study_year_from_enrollment("2019-09-01", today=date(2026, 10, 22)) is None


def test_leap_day_enrollment_uses_the_last_day_of_february() -> None:
    assert study_year_from_enrollment("2024-02-29", today=date(2025, 2, 28)) == "大二"


def test_derived_year_expires_before_the_next_anniversary() -> None:
    valid_to = study_year_valid_to("2024-08-22", today=date(2026, 10, 22))
    assert valid_to == datetime(
        2027, 8, 21, 23, 59, 59, tzinfo=timezone(timedelta(hours=8))
    )
    spring = study_year_valid_to("2024-08-22", today=date(2026, 5, 1))
    assert spring == datetime(
        2026, 8, 21, 23, 59, 59, tzinfo=timezone(timedelta(hours=8))
    )
    assert study_year_valid_to("2019-09-01", today=date(2026, 10, 22)) is None
