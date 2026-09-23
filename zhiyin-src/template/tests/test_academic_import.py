"""课表与成绩单导入：解析、报错分流、落库与画像的守卫（不联网）。

为什么这一层值得守
------------------
导入这条路，用户的体验全压在解析上：他复制一整页课表贴进来，我们读得对，
这件事就成了；读错了，他看到的是一张**看起来正常但不对的课表** ——
比"没导入"更糟，因为他不知道哪几条是错的。

所以这里钉四件事：

1. 表格按**表头**对齐（列序换过也要读对）；
2. 页面按**标签**取值（换版式也要能取到）；
3. 读不出来时给**具体**的错（缺表头 / 只复制了表头 / 版式不认识），
   每一类都对应一件用户能做的事；
4. 读进来的东西真的落到快照、并且把画像摘要更新成"已导入"，
   而清空时**两样一起删**（不然采集清单会一直说"课程表已拿到"）。

fixture 说明：页面结构按厂商公开可见的版式构造（强智 `kbtable` / `dataList`，
正方 `kbList` JSON），表格文本按"从 Excel 复制"的真实形态。
"""

from __future__ import annotations

import json

import pytest

from zhiyin_business.ports.academic import AcademicImportResult
from zhiyin_business.services.academic import DefaultAcademicService
from zhiyin_data_sdk.gateways.academic import (
    AcademicImportError,
    AcademicImportKind,
)
from zhiyin_infrastructure.academic import ManualAcademicImporter
from zhiyin_infrastructure.textfile import decode_text, unsupported_reason
from zhiyin_infrastructure.local.repository import InMemoryAcademicSnapshotRepository
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_infrastructure.academic.parsers import (
    detect_source,
    parse_periods,
    parse_json_courses,
    parse_qz_grades,
    parse_qz_schedule,
    parse_tabular_courses,
    parse_tabular_grades,
    parse_weekday,
    parse_zf_schedule,
    split_table_rows,
)

# ------------------------------------------------------------------ fixtures

QZ_SCHEDULE = """
<html><body>
<select><option selected>2025-2026学年第一学期</option></select>
<table id="kbtable">
  <tr>
    <td>第一节<br>08:00-08:45</td>
    <td><div class="kbcontent">高等数学<br>
        <font title="老师">张三</font><br>
        <font title="周次(节次)">1-16周(1,2节)</font><br>
        <font title="教室">教一楼101</font></div></td>
    <td>&nbsp;</td>
  </tr>
  <tr>
    <td>第三节<br>10:00-10:45</td>
    <td><div class="kbcontent">大学英语<br>
        <font title="老师">李四</font><br>
        <font title="周次(节次)">1-8周(3,4节)</font><br>
        <font title="教室">外语楼205</font></div>
        <div class="kbcontent">体育<br>
        <font title="老师">王五</font><br>
        <font title="周次(节次)">9-16周(3,4节)</font><br>
        <font title="教室">体育馆</font></div></td>
    <td>&nbsp;</td>
  </tr>
</table>
</body></html>
"""

QZ_GRADES = """
<html><body>
<table id="dataList">
  <tr><th>学年学期</th><th>课程名称</th><th>课程性质</th><th>学分</th><th>绩点</th><th>成绩</th></tr>
  <tr><td>2024-2025-1</td><td>高等数学</td><td>必修</td><td>5.0</td><td>3.7</td><td>88</td></tr>
  <tr><td>2024-2025-1</td><td>大学英语</td><td>必修</td><td>3.0</td><td>4.0</td><td>92</td></tr>
</table>
</body></html>
"""

COURSE_TABLE = "课程名称\t星期\t节次\t地点\t教师\n高等数学\t周三\t1-2节\t教一楼101\t张三"
GRADE_TABLE = "课程名称,学分,成绩,绩点\n高等数学,5.0,88,3.7"

ZF_SCHEDULE_JSON = json.dumps(
    {
        "xsxx": {"XH": "2023010234", "XM": "张某某", "XNMC": "2025-2026学年第一学期"},
        "kbList": [
            {
                "kcmc": "结构力学",
                "xm": "赵六",
                "xqj": "3",
                "jcs": "3-4",
                "zcd": "1-16周",
                "cdmc": "土木楼302",
                "xf": "3.5",
                "kcxzmc": "专业必修",
            }
        ],
    },
    ensure_ascii=False,
)

"""用户**真实传过**的一份 JSON：顶层是数组、每门课一个对象，字段名中英混着写。

它此前读不出来 —— 解析器只认正方的 `kbList/kcmc`，认不出就退回表格读法，
于是这份完全正确的文件换来一句"读不出这是课表，去课表页 Ctrl+A 全选复制"。
这一条 fixture 就是那次失败的复现，别再让它退化。
"""
USER_JSON_SCHEDULE = json.dumps(
    [
        {
            "day": "星期二",
            "period": "第1-2节",
            "time": "08:20-10:00",
            "course_name": "计算机通信与网络_01",
            "teacher": "张虹*",
            "weeks": "1-13周",
        },
        {
            "day": "星期三",
            "period": "第3-4节",
            "time": "10:10-11:50",
            "course_name": "高等数学",
            "teacher": "李明",
            "weeks": "1-16周",
            "place": "教一楼101",
        },
    ],
    ensure_ascii=False,
)


# ------------------------------------------------------------------ 小工具


def test_weekday_reads_every_common_writing() -> None:
    assert parse_weekday("周三") == 3
    assert parse_weekday("星期三") == 3
    assert parse_weekday("礼拜天") == 7
    assert parse_weekday("Wed") == 3
    assert parse_weekday("3") == 3
    assert parse_weekday("") == 0


def test_periods_read_ranges_but_refuse_to_guess_from_clock() -> None:
    assert parse_periods("1-2节") == (1, 2)
    assert parse_periods("第3,4节") == (3, 4)
    assert parse_periods("5") == (5, 5)
    # 只有钟点时返回 0：不同学校作息不同，换算出来的节次是编的
    assert parse_periods("10:00-11:40") == (0, 0)
    assert parse_periods("") == (0, 0)


def test_table_rows_split_by_tab_comma_or_double_space() -> None:
    assert split_table_rows("a\tb\n1\t2") == [["a", "b"], ["1", "2"]]
    assert split_table_rows("a,b\n1,2") == [["a", "b"], ["1", "2"]]
    assert split_table_rows("课程名称  星期\n高数  周三") == [["课程名称", "星期"], ["高数", "周三"]]


# ------------------------------------------------------------------ 页面版式


def test_vendor_is_recognised_by_fingerprint_only() -> None:
    assert detect_source(QZ_SCHEDULE) == "qz"
    assert detect_source(ZF_SCHEDULE_JSON) == "zf"
    assert detect_source("某校自研教务的普通页面") == "unknown"


def test_qz_schedule_is_read_from_the_grid() -> None:
    term, courses = parse_qz_schedule(QZ_SCHEDULE)
    assert "学期" in term
    assert [c.name for c in courses] == ["高等数学", "大学英语", "体育"]
    first = courses[0]
    assert first.teacher == "张三"
    assert first.weekday == 1
    # 节次取"周次(节次)"那一格里的 1,2 节 —— 比行号准
    assert (first.start_period, first.end_period) == (1, 2)
    assert first.place == "教一楼101"
    # 一个格子里塞两门课（前后半学期）不能被合并成一条
    assert courses[1].name != courses[2].name


def test_qz_grades_align_by_header_not_by_position() -> None:
    """列序换了也要读对：成绩单串列比读不出来更糟。"""
    shuffled = QZ_GRADES.replace(
        "<tr><th>学年学期</th><th>课程名称</th><th>课程性质</th><th>学分</th><th>绩点</th><th>成绩</th></tr>",
        "<tr><th>课程名称</th><th>成绩</th><th>学分</th><th>绩点</th><th>学年学期</th><th>课程性质</th></tr>",
    ).replace(
        "<tr><td>2024-2025-1</td><td>高等数学</td><td>必修</td><td>5.0</td><td>3.7</td><td>88</td></tr>",
        "<tr><td>高等数学</td><td>88</td><td>5.0</td><td>3.7</td><td>2024-2025-1</td><td>必修</td></tr>",
    )
    grades = parse_qz_grades(shuffled)
    assert grades[0].name == "高等数学"
    assert grades[0].score == "88"
    assert grades[0].point == "3.7"
    assert grades[0].credit == "5.0"


def test_zf_json_is_read_by_field_name() -> None:
    term, courses = parse_zf_schedule(ZF_SCHEDULE_JSON)
    assert "学期" in term
    course = courses[0]
    assert course.name == "结构力学"
    assert (course.weekday, course.start_period, course.end_period) == (3, 3, 4)
    assert course.place == "土木楼302"


def test_a_json_array_of_courses_is_read_by_field_name() -> None:
    """用户自己导出的 JSON（顶层数组、每门课一条）要读得出来。

    字段名按**同义词**认：`course_name` / `kcmc` / `课程名称` 都算课名；
    `day` 认中文星期；`period` 认"第1-2节"。认不出的字段跳过，不猜。
    """
    term, courses = parse_json_courses(USER_JSON_SCHEDULE)
    assert term == ""
    assert [c.name for c in courses] == ["计算机通信与网络_01", "高等数学"]
    first = courses[0]
    assert first.weekday == 2
    assert (first.start_period, first.end_period) == (1, 2)
    assert first.weeks == "1-13周"
    assert first.teacher == "张虹*"
    assert courses[1].place == "教一楼101"


def test_json_wrapped_in_a_container_key_is_read_too() -> None:
    """接口回包常常把数组包在一层里（`data.list` / `kbList` / `items`）。"""
    rows = json.loads(USER_JSON_SCHEDULE)
    _, wrapped = parse_json_courses(json.dumps({"code": 0, "data": {"list": rows}}, ensure_ascii=False))
    assert [c.name for c in wrapped] == ["计算机通信与网络_01", "高等数学"]


def test_a_json_file_with_one_course_is_read_as_one_row() -> None:
    """整份文件就是一条记录（从课表里挑了一条存下来）也要认。"""
    single = json.loads(USER_JSON_SCHEDULE)[0]
    _, courses = parse_json_courses(json.dumps(single, ensure_ascii=False))
    assert [c.name for c in courses] == ["计算机通信与网络_01"]


def test_json_that_reads_nothing_says_so_instead_of_asking_for_a_paste() -> None:
    """合法 JSON 但读不出课：报的是"这段 JSON 里没读出课"，**不是**"去 Ctrl+A 全选复制"。

    用户当时看到的就是后者 —— 他传的明明是 JSON，提示却在教他怎么复制一页课表。
    这种"答非所问"比读不出来更让人放弃。
    """
    with pytest.raises(AcademicImportError) as excinfo:
        parse_json_courses('{"code": 1, "msg": "登录已过期"}')
    message = str(excinfo.value)
    assert "JSON" in message
    assert "全选复制" not in message


# ------------------------------------------------------------------ 表格文本


def test_tabular_courses_are_read_by_header() -> None:
    term, courses = parse_tabular_courses(COURSE_TABLE)
    assert term == ""
    assert courses[0].name == "高等数学"
    assert courses[0].weekday == 3
    assert (courses[0].start_period, courses[0].end_period) == (1, 2)
    assert courses[0].place == "教一楼101"


def test_tabular_courses_accept_a_title_line_before_the_header() -> None:
    """表头不必在第一行 —— 复制出来的内容常常先带一行标题。

    要求"第一行必须是表头"会把最常见的一种贴法判成格式错误，
    而用户手上的原文完全是对的。
    """
    pasted = "2024-2025学年第一学期课表\n" + COURSE_TABLE
    _, courses = parse_tabular_courses(pasted)
    assert [c.name for c in courses] == ["高等数学"]


def test_headerless_rows_are_read_by_row_shape() -> None:
    """没有表头、但每行是「课名 + 时间」时也要能读出来。

    用户从页面上随手复制一段，多半就是这个样子；读不出来就等于白贴一次。
    """
    _, courses = parse_tabular_courses("高等数学\t周三\t1-2节\t教一楼101\n线性代数\t周四\t3-4节\t教二楼203")
    assert [c.name for c in courses] == ["高等数学", "线性代数"]
    assert courses[0].weekday == 3
    assert (courses[0].start_period, courses[0].end_period) == (1, 2)
    assert courses[0].place == "教一楼101"


def test_unreadable_courses_text_says_what_to_do() -> None:
    """实在读不出来时：报 NO_HEADER，而且那句话要给出可执行的下一步。"""
    with pytest.raises(AcademicImportError) as excinfo:
        parse_tabular_courses("随便写点什么\n再随便写一点")
    assert excinfo.value.kind is AcademicImportKind.NO_HEADER
    assert "全选复制" in str(excinfo.value)


def test_tabular_grades_are_read_by_header() -> None:
    grades = parse_tabular_grades(GRADE_TABLE)
    assert grades[0].name == "高等数学"
    assert grades[0].score == "88"


# ------------------------------------------------------------------ 分流与报错


def _importer() -> ManualAcademicImporter:
    return ManualAcademicImporter()


def test_importer_tells_apart_the_four_failure_reasons() -> None:
    importer = _importer()
    with pytest.raises(AcademicImportError) as excinfo:
        importer.parse_courses("")
    assert excinfo.value.kind is AcademicImportKind.EMPTY

    with pytest.raises(AcademicImportError) as excinfo:
        importer.parse_courses("太短了")
    assert excinfo.value.kind is AcademicImportKind.TOO_SHORT

    with pytest.raises(AcademicImportError) as excinfo:
        importer.parse_grades("课程名称\t学分\t成绩\n")
    assert excinfo.value.kind in {
        AcademicImportKind.NO_ROWS,
        AcademicImportKind.TOO_SHORT,
    }


def test_importer_reads_html_json_and_table_in_one_entry() -> None:
    importer = _importer()
    assert importer.parse_courses(QZ_SCHEDULE).source == "qz"
    assert importer.parse_courses(ZF_SCHEDULE_JSON).source == "json"
    assert importer.parse_courses(COURSE_TABLE).source == "table"
    assert importer.parse_grades(QZ_GRADES).source == "qz"
    assert importer.parse_grades(GRADE_TABLE).source == "table"


def test_importer_refuses_to_invent_a_timetable_from_a_strange_page() -> None:
    importer = _importer()
    with pytest.raises(AcademicImportError) as excinfo:
        importer.parse_courses("<html><body>某校自研教务系统欢迎页</body></html>")
    assert excinfo.value.kind is AcademicImportKind.UNRECOGNIZED
    assert "表头" in str(excinfo.value) or "复制" in str(excinfo.value)


def test_formats_are_listed_so_the_ui_can_explain_how_to_import() -> None:
    formats = _importer().formats()
    assert [f.id for f in formats] == ["page", "table", "json"]
    assert all(f.howto for f in formats), "每种形态都要写清怎么拿到它"


# ------------------------------------------------------------------ 上传的文件


def test_a_gbk_file_is_decoded_instead_of_turning_into_mojibake() -> None:
    """教务系统导出的 CSV 有一半是 GBK：按 UTF-8 硬读会变成乱码，
    而乱码不是"读不出"，它会一路走到解析器里报"读不出这是课表"。
    """
    data = COURSE_TABLE.encode("gbk")
    text = decode_text(data)
    assert text == COURSE_TABLE
    _, courses = parse_tabular_courses(text)
    assert courses[0].name == "高等数学"


def test_a_utf8_bom_does_not_hide_the_header() -> None:
    """带 BOM 的 UTF-8：不处理的话表头首字多一个看不见的字符，"课程名称"就认不出来。"""
    importer = _importer()
    text = importer.read_text(b"\xef\xbb\xbf" + COURSE_TABLE.encode("utf-8"), filename="课表.csv")
    assert importer.parse_courses(text).courses[0].name == "高等数学"


def test_binary_office_files_are_refused_with_the_next_step() -> None:
    """Excel 是二进制，解码只能是乱码 —— 当场说清楚该换成什么。"""
    reason = unsupported_reason("2024-2025学年第1学期课表.xlsx")
    assert "CSV" in reason
    importer = _importer()
    with pytest.raises(AcademicImportError) as excinfo:
        importer.read_text(b"PK\x03\x04\x14\x00\x00\x00", filename="课表.xlsx")
    assert "另存为 CSV" in str(excinfo.value)


def test_an_empty_file_says_it_is_empty() -> None:
    importer = _importer()
    with pytest.raises(AcademicImportError) as excinfo:
        importer.read_text(b"", filename="课表.json")
    assert "空" in str(excinfo.value)


# ------------------------------------------------------------------ 落库与画像


class _Profile:
    """最小画像桩：只记「写了什么 / 删了什么」。"""

    def __init__(self) -> None:
        self.fields: dict[str, str] = {}
        self.dropped: list[str] = []

    async def update_field(self, user_id, key, value, *, confidence, source, evidence=None):
        self.fields[key] = value

    async def drop_field(self, user_id, key) -> None:
        self.fields.pop(key, None)
        self.dropped.append(key)


@pytest.mark.asyncio
async def test_import_stores_a_snapshot_and_marks_the_profile() -> None:
    snapshots = InMemoryAcademicSnapshotRepository()
    profile = _Profile()
    service = DefaultAcademicService(snapshots, _importer(), profile)

    result = await service.import_(
        "u1",
        courses_raw=COURSE_TABLE,
        grades_raw=GRADE_TABLE,
        school="某某大学",
    )
    assert isinstance(result, AcademicImportResult)
    assert (result.courses, result.grades) == (1, 1)
    assert result.source == "table"
    assert set(result.wrote_profile) == {"课程表", "成绩单"}

    stored = await service.get("u1")
    assert stored is not None and stored.courses[0].name == "高等数学"
    assert profile.fields["courses"].startswith("1 门课")
    assert "导入" in profile.fields["courses"]


@pytest.mark.asyncio
async def test_importing_only_grades_does_not_claim_a_timetable() -> None:
    """只导成绩时不能顺手把"课程表"标成已拿到 —— 那会让采集清单骗人。"""
    snapshots = InMemoryAcademicSnapshotRepository()
    profile = _Profile()
    service = DefaultAcademicService(snapshots, _importer(), profile)

    await service.import_("u1", grades_raw=GRADE_TABLE)
    assert "courses" not in profile.fields
    assert "scores" in profile.fields


@pytest.mark.asyncio
async def test_importing_a_file_lands_the_same_snapshot_as_pasting_it() -> None:
    """文件入口与粘贴入口必须是**同一个结果**：同一份数据，两处读出来不一样
    就是"换个入口结果变了"，用户无从判断哪个才对。"""
    imported = InMemoryAcademicSnapshotRepository()
    service = DefaultAcademicService(imported, _importer(), _Profile())
    result = await service.import_files(
        "u1",
        courses_file=COURSE_TABLE.encode("gbk"),
        courses_name="课表.csv",
        grades_file=GRADE_TABLE.encode("utf-8"),
        grades_name="成绩.csv",
        school="某某大学",
    )
    assert (result.courses, result.grades) == (1, 1)
    assert result.source == "table"

    stored = await service.get("u1")
    assert stored is not None
    assert stored.courses[0].name == "高等数学"
    assert stored.grades[0].score == "88"
    assert stored.school == "某某大学"


@pytest.mark.asyncio
async def test_an_unreadable_upload_becomes_a_user_fixable_error() -> None:
    """传了 Excel：翻成 InvalidRequest（422 + 原话），不是 500。"""
    service = DefaultAcademicService(InMemoryAcademicSnapshotRepository(), _importer(), None)
    with pytest.raises(InvalidRequest) as excinfo:
        await service.import_files("u1", courses_file=b"PK\x03\x04", courses_name="课表.xlsx")
    assert "另存为 CSV" in str(excinfo.value)


@pytest.mark.asyncio
async def test_unplaced_courses_are_reported_not_silently_dropped() -> None:
    """读不出上课时间的课要**说出来**：悄悄丢掉等于让用户以为课少了。"""
    snapshots = InMemoryAcademicSnapshotRepository()
    service = DefaultAcademicService(snapshots, _importer(), None)
    result = await service.import_("u1", courses_raw="课程名称\t教师\n高等数学\t张三\n大学英语\t李四")
    assert result.courses == 2
    assert result.notes and "没读出上课时间" in result.notes[0]


@pytest.mark.asyncio
async def test_revoke_clears_both_the_snapshot_and_the_profile() -> None:
    """清空必须两样一起删：只删快照的话，采集清单会一直说"课程表已拿到"。"""
    snapshots = InMemoryAcademicSnapshotRepository()
    profile = _Profile()
    service = DefaultAcademicService(snapshots, _importer(), profile)
    await service.import_("u1", courses_raw=COURSE_TABLE, grades_raw=GRADE_TABLE)
    assert await service.get("u1") is not None

    await service.revoke("u1")
    assert await service.get("u1") is None
    assert profile.fields == {}
    assert set(profile.dropped) == {"courses", "scores"}


@pytest.mark.asyncio
async def test_empty_import_is_refused_with_a_reason() -> None:
    """什么都没贴时抛的是 InvalidRequest（＝用户能自己修的一件事），不是 500。

    这一条是被真实反馈逼出来的：原文读不出来时后端抛 AcademicImportError，
    而 api 层没有对应处理器 —— 用户看到的是"500"，明明提示里写着该怎么改。
    """
    service = DefaultAcademicService(InMemoryAcademicSnapshotRepository(), _importer(), None)
    with pytest.raises(InvalidRequest) as excinfo:
        await service.import_("u1")
    assert "贴" in str(excinfo.value)


async def test_unreadable_paste_becomes_a_user_fixable_error() -> None:
    """读不出来 → InvalidRequest（422 + 原话），不再是 500。"""
    service = DefaultAcademicService(InMemoryAcademicSnapshotRepository(), _importer(), None)
    noise = "随手写的一点东西，既不是表格也没有课\n" * 4
    with pytest.raises(InvalidRequest) as excinfo:
        await service.import_("u1", courses_raw=noise)
    message = str(excinfo.value)
    assert message and "500" not in message and "Traceback" not in message
