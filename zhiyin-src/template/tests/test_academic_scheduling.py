"""导入回执里的「进了库」与「排进了课表」必须分开说。

为什么值得单独守
---------------
导入这条路有两个结果，而它们**不是同一件事**：

- 课程/成绩写进了快照（`courses` / `grades`）—— 数据是你的了；
- 课表里那几门课真的排得出上课时间（`courses_scheduled`）—— 这一周的空档才算得出。

实测踩过的那一次：用户按自己习惯的写法贴了一张表（列名是"上课时间"、里面写的是
`周三 08:00-09:40`），接口返回 0 错、课程数 +2，界面上写着"导入完成" ——
而课表里一节课都没有。回执只报一个总数时，"完成"这两个字就是假的。

所以这里钉两件事：

1. 回执要分别给出这两个数；
2. 排课的判据（星期 1–7 且节次 ≥ 1）必须与前端画课表的判据**一致** ——
   两处不一样，就会出现"回执说排进去了、日历上查无此课"。
"""

from __future__ import annotations

import pytest

from zhiyin_business.services.academic import DefaultAcademicService
from zhiyin_infrastructure.academic import ManualAcademicImporter
from zhiyin_infrastructure.local.repository import InMemoryAcademicSnapshotRepository

#: 一份"列名齐全"的表格：星期 + 节次都在，应当全部排进课表
SCHEDULABLE = (
    "课程名称\t任课教师\t星期\t节次\t周次\t上课地点\n"
    "高等数学\t张三\t周三\t1-2节\t1-16周\t教一101\n"
    "大学英语\t李四\t周五\t3-4节\t1-16周\t教二205"
)

#: 同一批课，但时间只写了钟点、没有节次 —— 课进得了库，排不进课表
ONLY_CLOCK_TIMES = (
    "课程名称,任课教师,上课时间,上课地点\n"
    "高等数学,张三,周三 08:00-09:40,教一101\n"
    "大学英语,李四,周五 10:00-11:40,教二205"
)


def _service() -> DefaultAcademicService:
    return DefaultAcademicService(
        InMemoryAcademicSnapshotRepository(),
        ManualAcademicImporter(),
        None,
    )


async def test_scheduled_count_matches_the_stored_count_when_times_parse() -> None:
    """时间读出来了：两个数应当相等，且不该留下"要留意"那一句。"""
    result = await _service().import_("u1", courses_raw=SCHEDULABLE)

    assert result.courses == 2
    assert result.courses_scheduled == 2
    assert result.notes == []


async def test_unparsed_times_are_reported_as_not_scheduled() -> None:
    """读得出课程、读不出上课时间：入库 2 门，排课 0 门 —— 回执必须说得出这个差别。"""
    result = await _service().import_("u1", courses_raw=ONLY_CLOCK_TIMES)

    assert result.courses == 2
    assert result.courses_scheduled == 0
    assert result.notes and "没读出上课时间" in result.notes[0]


async def test_partially_parsed_times_are_counted_one_by_one() -> None:
    """一部分排得出、一部分排不出：数字要一条条数，不能四舍五入成"都行"或"都不行"。"""
    mixed = (
        "课程名称\t星期\t节次\n"
        "高等数学\t周三\t1-2节\n"
        "大学英语\t"  # 缺星期与节次
    )
    result = await _service().import_("u1", courses_raw=mixed)

    assert result.courses == 2
    assert result.courses_scheduled == 1
    assert result.notes and "1 门课" in result.notes[0]


@pytest.mark.parametrize("weekday,start,expected", [(0, 1, 0), (8, 1, 0), (3, 0, 0), (3, 1, 1)])
async def test_scheduling_rule_is_the_same_one_the_week_view_uses(
    weekday: int, start: int, expected: int
) -> None:
    """判据与前端 `useDayPlan.of()` 一致：星期落在 1–7、节次 ≥ 1 才算排得进课表。

    两边不一致的样子很具体：回执说"已排进课表"，日历上那一天却是空的。
    """
    from zhiyin_business.services.academic import _scheduled_count
    from zhiyin_data_sdk.gateways.academic import CourseEntry

    courses = [CourseEntry(name="某门课", weekday=weekday, start_period=start)]
    assert _scheduled_count(courses) == expected
