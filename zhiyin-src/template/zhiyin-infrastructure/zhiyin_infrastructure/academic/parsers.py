"""把"学生手上那份东西"读成课表与成绩单（纯函数，不联网）。

为什么这一层是产品的关键面
--------------------------
导入这条路，用户的体验全压在这里：他复制一整页课表贴进来，我们读得对，
这件事就成了；读错了，他看到的是一张乱掉的课表 —— 比"没导入"更糟，
因为他不知道哪些是对的。

所以两条规矩：

1. **认不出来就说认不出来**，不返回空表（空表和"这学期没课"在界面上是两回事）；
2. **按名字取值，不按位置取值**。表格按表头对齐列（列序换过也读得对），
   页面按标签取值（`<font title="老师">`、`kcmc` 这类名字），换版式最多影响某一条。

支持四种形态，因为用户手上就这几种：
   · 强智课表页 / 成绩页的整页复制（HTML）
   · 正方课表 / 成绩接口的 JSON（kbList 那套固定字段名）
   · 用户自己导出的 JSON —— 顶层是数组、每门课一条，字段名各系统不同
   · 任何系统复制出来的表格文本（制表符 / 逗号分隔，带表头）
"""

from __future__ import annotations

import html as html_module
import json
import re
from typing import Any, Optional

from zhiyin_data_sdk.gateways.academic import (
    AcademicImportError,
    AcademicImportKind,
    CourseEntry,
    GradeEntry,
)

_TAG = re.compile(r"(?s)<[^>]+>")
_SCRIPT_OR_STYLE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_WS = re.compile(r"[\s\u00a0\u3000]+")


def text_of(fragment: str) -> str:
    """把一段 HTML 的正文取出来：去标签、去多余空白、还原实体。"""
    plain = _TAG.sub(" ", fragment or "")
    plain = html_module.unescape(plain)
    return _WS.sub(" ", plain).strip()


def _cells(row_html: str) -> list[str]:
    return re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html or "")


def _rows(table_html: str) -> list[str]:
    return re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", table_html or "")


def _first_group(pattern: str, text: str, default: str = "") -> str:
    hit = re.search(pattern, text or "", re.S | re.I)
    if not hit:
        return default
    captured = hit.group(1) if hit.re.groups else hit.group(0)
    return (captured or "").strip()


# ------------------------------------------------------------------ 形态识别

def looks_like_html(raw: str) -> bool:
    probe = (raw or "").lstrip()[:200].lower()
    return probe.startswith("<") or "<table" in probe or "<html" in probe


def looks_like_json(raw: str) -> bool:
    """JSON 的两种开头都要认：对象 `{…}` 与数组 `[…]`。

    此前只认 `{`：**导出的 JSON 常常是数组**（一门课一个对象，整体包成 `[…]`），
    于是那种文件连"这是 JSON"都算不上，被丢给表格读法，
    最后报的是"读不出这是课表，请在课表页 Ctrl+A 全选复制" ——
    用户手上的东西明明是对的，提示却在让他换一种复制方式。
    """
    probe = (raw or "").strip()
    return (probe.startswith("{") or probe.startswith("[")) and '"' in probe


"""页面指纹：出现其中之一就按那套版式读。

指纹写在代码里而不是配置里，因为它和解析器是**同一件事的两面**：
认成强智就要走强智的解析器。指纹能配、解析器不能配的话，
配置一改就会变成"认成 A、按 B 解析"，那是最难查的一类错。
"""
_FINGERPRINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "qz",
        # kbcontent 是课表格里那块；dataList 是成绩表 —— 两张页面上各出现一个
        ("jsxsd", "教务网络管理系统", "xk/LoginToXk", "xskb_list.do", "kbcontent", "datalist"),
    ),
    ("zf", ("zftable", "xtgl/login_slogin", "login_getPublicKey", "kbList", "jcs")),
)


def detect_source(raw: str) -> str:
    """认出这段内容来自哪套系统的版式。认不出返回 unknown（不猜）。"""
    probe = (raw or "").lower()
    for source, needles in _FINGERPRINTS:
        if any(needle.lower() in probe for needle in needles):
            return source
    return "unknown"


# ------------------------------------------------------------------ 通用字段

"""星期：中文习惯太多，全都认（周一 / 星期一 / 礼拜一 / 一 / 数字 / Mon）。"""
_WEEKDAY_CHARS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
}
_WEEKDAY_WORDS = {
    "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7,
}
_CLOCK = re.compile(r"\d{1,2}\s*[:：]\s*\d{2}")


def parse_weekday(raw: str) -> int:
    """把"周三 / 星期三 / 3 / Wed"读成 1..7；读不出来返回 0（不猜）。"""
    text = (raw or "").strip()
    if not text:
        return 0
    lowered = text.lower()
    for word, value in _WEEKDAY_WORDS.items():
        if word in lowered:
            return value
    hit = re.search(r"(周|星期|礼拜)\s*([一二三四五六日天])", text)
    if hit:
        return _WEEKDAY_CHARS.get(hit.group(2), 0)
    # 只有数字时：1-7 才认（"8" 可能是别的列，不猜）
    numbers = re.findall(r"\d+", text)
    if len(numbers) == 1 and 1 <= int(numbers[0]) <= 7:
        return int(numbers[0])
    return 0


def parse_periods(raw: str) -> tuple[int, int]:
    """把"1-2节 / 第3,4节 / 5 / 1~2节"读成（起, 止）。

    只有钟点（10:00-11:40）而没有节次时返回 (0, 0)：不同学校作息表不一样，
    换算出来的节次是编的 —— 编出来的节次会让"空档"全错。
    """
    text = _CLOCK.sub(" ", raw or "")
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return 0, 0
    start = int(numbers[0])
    end = int(numbers[-1]) if len(numbers) > 1 else start
    if start < 1 or start > 20 or end < start or end > 20:
        return 0, 0
    return start, end


# ------------------------------------------------------------------ 强智（页面）

_QZ_BLOCK = re.compile(r"(?is)<div[^>]*class=[\"']?kbcontent", re.I)
_QZ_FONT = re.compile(
    r"(?is)<font\b[^>]*title=[\"']?(?P<title>[^\"'>]+)[\"']?[^>]*>(?P<value>.*?)</font>"
)


def _clean_block(block: str) -> str:
    plain = re.sub(r"(?is)<br\s*/?>", "\n", block or "")
    plain = _TAG.sub(" ", plain)
    plain = html_module.unescape(plain)
    return "\n".join(line.strip() for line in plain.splitlines() if line.strip())


def parse_qz_schedule(html: str) -> tuple[str, list[CourseEntry]]:
    """强智课表页 →（学期说明, 课程表）。

    页面是一张"节次 × 星期"的网格，单元格里是 `kbcontent` 块。
    课名在第一行，其余信息在带 `title` 的 `<font>` 上（老师 / 周次 / 教室）。
    """
    term = _first_group(r"(?is)<option[^>]*selected[^>]*>\s*([^<]*学期[^<]*)", html)
    table = _first_group(r"(?is)<table[^>]*id=[\"']?kbtable[\"']?.*?</table>", html)
    target = table or html

    courses: list[CourseEntry] = []
    for row in _rows(target):
        period_from, period_to = _period_range(row) or (0, 0)
        for day_index, cell in enumerate(_cells(row)):
            for block in _split_blocks(cell):
                entry = _qz_course(block, day=day_index, start=period_from, end=period_to)
                if entry is not None:
                    courses.append(entry)

    if not courses:
        raise AcademicImportError(
            "这张课表页里没读出一门课 —— 多半是只复制了一小块。"
            "整页复制（含「第一节」「星期一」那一行那一列）成功率最高。",
            kind=AcademicImportKind.NO_ROWS,
            detail="kbtable 里没有 kbcontent",
        )
    return term, courses


def _period_range(row_html: str) -> Optional[tuple[int, int]]:
    """这一行是第几节到第几节 —— 从行首那个节次单元格读。

    坑：格子里的文字是"第一节 08:00-08:45"，直接抓数字会得到 (1, 45)，
    课就变成 1 到 45 节了，而且不报错。所以先把时间抹掉再读节次。
    """
    cells = _cells(row_html)
    head = _CLOCK.sub(" ", text_of(cells[0] if cells else ""))
    numbers = re.findall(r"\d+", head)
    if numbers:
        return int(numbers[0]), int(numbers[-1])
    chinese = [_WEEKDAY_CHARS[ch] for ch in head if ch in _WEEKDAY_CHARS]
    if chinese:
        # 这里的汉字是"第一节"里的序数，不是星期 —— 只取前两个数字
        return chinese[0], chinese[-1]
    return None


def _split_blocks(cell_html: str) -> list[str]:
    """一个单元格里可能塞了多门课（前后半学期）：按 kbcontent 的首尾切开。"""
    marks = [match.start() for match in _QZ_BLOCK.finditer(cell_html or "")]
    if not marks:
        return []
    marks.append(len(cell_html))
    return [cell_html[marks[i] : marks[i + 1]] for i in range(len(marks) - 1)]


def _qz_course(block: str, *, day: int, start: int, end: int) -> Optional[CourseEntry]:
    lines = _clean_block(block).splitlines()
    if not lines:
        return None
    name = lines[0].strip()
    if not name or name in {"&nbsp;", "\u3000"}:
        return None

    teacher = weeks = place = ""
    for title, value in _QZ_FONT.findall(block):
        key = text_of(title)
        val = text_of(value)
        if "老师" in key or "教师" in key:
            teacher = val
        elif "周次" in key or "节次" in key:
            weeks = val
        elif "教室" in key or "地点" in key:
            place = val
    if not teacher:
        teacher = lines[1] if len(lines) > 1 else ""
    if not place:
        place = lines[-1] if len(lines) > 2 else ""

    # "周次(节次)"那一格通常连节次一起给了（"1-16周(1,2节)"），它比行号准
    parsed = _periods_in(weeks)
    if parsed:
        start, end = parsed

    return CourseEntry(
        name=name,
        teacher=teacher,
        weekday=day,
        start_period=start,
        end_period=end,
        weeks=weeks,
        place=place,
    )


def _periods_in(weeks: str) -> Optional[tuple[int, int]]:
    hit = re.search(r"[（(]\s*(\d+)\s*[,，\-~]\s*(\d+)\s*节", weeks or "")
    if not hit:
        return None
    return int(hit.group(1)), int(hit.group(2))


"""强智成绩表的列名。不同版本列序不同，所以按表头对齐。"""
_QZ_GRADE_HEADERS: dict[str, str] = {
    "学年": "term",
    "学期": "term",
    "学年学期": "term",
    "课程名称": "name",
    "课程名": "name",
    "学分": "credit",
    "成绩": "score",
    "绩点": "point",
    "课程性质": "category",
    "课程属性": "kind",
}


def parse_qz_grades(html: str) -> list[GradeEntry]:
    table = _first_group(r"(?is)<table[^>]*id=[\"']?dataList[\"']?.*?</table>", html)
    if not table:
        raise AcademicImportError(
            "这张成绩页里没找到成绩表 —— 确认整页复制，包括表头那一行。",
            kind=AcademicImportKind.NO_ROWS,
            detail="dataList 未找到",
        )
    rows = _rows(table)
    if not rows:
        raise AcademicImportError("成绩表里没有行。", kind=AcademicImportKind.NO_ROWS)
    header = [text_of(cell) for cell in _cells(rows[0])]
    mapping = {
        index: _QZ_GRADE_HEADERS[name]
        for index, name in enumerate(header)
        if name in _QZ_GRADE_HEADERS
    }
    if "name" not in mapping.values():
        raise AcademicImportError(
            "成绩表的表头认不出来 —— 把表头那一行（课程名称 / 成绩 / 学分）一起复制进来。",
            kind=AcademicImportKind.NO_HEADER,
            detail=" · ".join(header[:8]),
        )

    grades: list[GradeEntry] = []
    for row in rows[1:]:
        values = [text_of(cell) for cell in _cells(row)]
        if not any(values):
            continue
        item: dict[str, str] = {}
        for index, field in mapping.items():
            if index < len(values):
                item[field] = values[index]
        if item.get("name"):
            grades.append(GradeEntry(**item))
    if not grades:
        raise AcademicImportError(
            "表头认出来了，但一条成绩都没读到 —— 多半只复制了表头。",
            kind=AcademicImportKind.NO_ROWS,
        )
    return grades


# ------------------------------------------------------------------ JSON
#
# JSON 有两个来源，界面上都叫「接口 JSON」：
#
#   1. **某个系统的固定版式**（正方：`kbList` + `kcmc/xqj/jcs…`）；
#   2. **用户自己导出的通用形状**：顶层是数组、每门课一个对象，
#      字段名各校各版不同（`course_name` / `kcmc` / `课程名称`…）。
#
# 第 2 种此前读不出来 —— 解析器只认 `kbList`，认不出就退回表格读法，
# 报的是"读不出这是课表，去课表页 Ctrl+A 全选复制"。用户传上来一份**完全正确**
# 的 JSON，看到的却是一句让他换复制方式的提示。这一层现在按**字段名**读：
# 认不出的键名跳过，认得出的一条条落下来，一条都读不出时再如实说读不出。

"""容器键：记录数组常常包在某个键里面。键名归一化后再比（见 `_normalize_key`）。"""
_RECORD_KEYS: tuple[str, ...] = (
    "kblist",
    "kb_list",
    "items",
    "cjlist",
    "rows",
    "records",
    "list",
    "courses",
    "courselist",
    "gradelist",
    "data",
    "result",
    "results",
    "content",
)

"""
字段同义词。**中英文都收**：学校自己导出的 JSON 里，"课程名称"和 `course_name`
一样常见，收一半就等于对一半用户报"读不出"。

顺序即优先级：同一行里同时有 `period` 和 `time` 时取 `period` ——
`time` 常常只是钟点（08:20-10:00），而钟点换算成节次是编的（见 `parse_periods`）。
"""
_COURSE_JSON_KEYS: dict[str, tuple[str, ...]] = {
    "name": (
        "kcmc", "course_name", "coursename", "course", "name", "title",
        "课程名称", "课程名", "课程", "科目",
    ),
    "teacher": (
        "xm", "jsxm", "teacher", "teacher_name", "instructor",
        "教师", "老师", "任课教师", "授课教师",
    ),
    "weekday": (
        "xqj", "weekday", "week_day", "day", "day_of_week", "week",
        "星期", "星期几", "周几", "上课星期",
    ),
    "period": (
        "jcs", "jcor", "jcs2", "period", "periods", "section", "sections",
        "节次", "上课节次", "时间", "上课时间", "time",
    ),
    "weeks": ("zcd", "zcmc", "weeks", "week_text", "周次", "上课周次"),
    "place": (
        "cdmc", "jxdd", "place", "location", "room", "classroom",
        "地点", "教室", "上课地点", "上课教室",
    ),
    "credit": ("xf", "credit", "学分"),
    "category": (
        "kcxzmc", "kclbmc", "category", "course_type",
        "课程性质", "课程类别", "类别", "性质",
    ),
}

_GRADE_JSON_KEYS: dict[str, tuple[str, ...]] = {
    "name": ("kcmc", "course_name", "coursename", "course", "name", "课程名称", "课程名", "课程"),
    "credit": ("xf", "credit", "学分"),
    "score": ("cj", "zcj", "score", "grade", "成绩", "总成绩", "分数"),
    "point": ("jd", "gpoint", "point", "gpa", "绩点"),
    "category": ("kcxzmc", "kclbmc", "category", "课程性质", "课程类别", "类别"),
    "kind": ("kcsx", "kcxz", "kind", "课程属性", "必修选修", "属性"),
    "term": ("xnmmc", "xn", "xqmmc", "xqm", "term", "学期", "学年学期", "学年"),
}


def parse_json_courses(payload: Any) -> tuple[str, list[CourseEntry]]:
    """读课表 JSON →（学期, 课程表）。

    两个读法按可靠性排序：**固定版式优先**（正方 `kbList` 的字段名是确定的），
    认不出再按通用字段名逐条读。两种都读不出才报错 —— 报错也要说清是"没有可读的记录"
    还是"记录的字段名一个都不认识"。
    """
    data = _load_json(payload)
    if isinstance(data, dict) and any(key in data for key in ("kbList", "kb_list")):
        try:
            return parse_zf_schedule(data)
        except AcademicImportError:
            pass

    rows = _record_rows(data) or _lone_record(data, _COURSE_JSON_KEYS["name"])
    courses = [course for course in (_course_from_json_row(row) for row in rows) if course]
    if not courses:
        raise AcademicImportError(
            "这段 JSON 里没读出课 —— 每门课要是一条带课名的记录"
            "（课名字段常见的是「课程名称 / kcmc / course_name」）。"
            "如果这是接口返回的整包数据，整段复制过来再试一次。",
            kind=AcademicImportKind.NO_ROWS if rows else AcademicImportKind.UNRECOGNIZED,
            detail=f"rows={len(rows)}",
        )
    return _term_from_json(data, rows), courses


def parse_json_grades(payload: Any) -> list[GradeEntry]:
    """读成绩 JSON。同 `parse_json_courses`：固定版式优先，认不出再按字段名读。"""
    data = _load_json(payload)
    if isinstance(data, dict) and any(key in data for key in ("items", "cjList")):
        try:
            return parse_zf_grades(data)
        except AcademicImportError:
            pass

    rows = _record_rows(data) or _lone_record(data, _GRADE_JSON_KEYS["name"])
    grades = [grade for grade in (_grade_from_json_row(row) for row in rows) if grade]
    if not grades:
        raise AcademicImportError(
            "这段 JSON 里没读出成绩 —— 每条要是一行带课名的记录"
            "（录名字段常见的是「课程名称 / kcmc / course_name」，成绩是「成绩 / cj / score」）。",
            kind=AcademicImportKind.NO_ROWS if rows else AcademicImportKind.UNRECOGNIZED,
            detail=f"rows={len(rows)}",
        )
    return grades


def _record_rows(data: Any, *, depth: int = 2) -> list[dict[str, Any]]:
    """从 JSON 里取出「一条记录一个对象」的数组。

    只看**形状**（是不是一串对象），不看键名叫什么 —— 键名是各系统自己起的，
    认键名就等于只支持我们见过的那几种。往下一层找是为了
    `{"code":0,"data":{"list":[…]}}` 这类包了一层的返回；深度给 2 层就够，
    再深就不是"记录数组"，而是别的东西了（继续找会把无关的数组当成课表）。
    """
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict) or depth <= 0:
        return []

    normalized = _normalized_keys(data)
    for key in _RECORD_KEYS:
        value = normalized.get(key)
        if not isinstance(value, list):
            continue
        rows = [row for row in value if isinstance(row, dict)]
        if rows:
            return rows

    # 键名不在上面那张表里：看谁的值是"一串对象"，多个候选就取最长的那条
    candidates = [
        [row for row in value if isinstance(row, dict)]
        for value in data.values()
        if isinstance(value, list)
    ]
    candidates = [rows for rows in candidates if rows]
    if candidates:
        return max(candidates, key=len)

    for value in data.values():
        if isinstance(value, dict):
            rows = _record_rows(value, depth=depth - 1)
            if rows:
                return rows
    return []


def _normalize_key(key: str) -> str:
    """键名归一化：`course_name` / `courseName` / `Course-Name` 认成同一个键。"""
    return re.sub(r"[\s_\-.]", "", (key or "").strip().lower())


def _lone_record(data: Any, name_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    """整份 JSON 就是**一条**记录时的兜底：把那个对象自己当成一行。

    有人从课表里挑一条存下来，文件里就一个对象（没有数组）。它有课名字段，
    形状上就是一条记录 —— 认它，比让他"再导出一次完整课表"有用。
    """
    if isinstance(data, dict) and _pick_json(data, name_keys):
        return [data]
    return []


def _normalized_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {_normalize_key(str(key)): value for key, value in row.items()}


def _pick_json(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    """按同义词取一个字段值。取不到返回空串 —— **不按位置硬套**。"""
    normalized = _normalized_keys(row)
    for key in keys:
        value = normalized.get(_normalize_key(key))
        if isinstance(value, (list, tuple)):
            value = " ".join(str(part) for part in value if part not in (None, ""))
        if value is None or value == "":
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _pick_json_many(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    """把多个字段拼成一句（学年 + 学期号 = 学期）—— 只在这里拼，别处不拼。"""
    normalized = _normalized_keys(row)
    parts: list[str] = []
    for key in keys:
        value = normalized.get(_normalize_key(key))
        if value is None or value == "" or isinstance(value, (list, dict)):
            continue
        text = str(value).strip()
        if text and text not in parts:
            parts.append(text)
    return " ".join(parts)


def _course_from_json_row(row: dict[str, Any]) -> Optional[CourseEntry]:
    name = _pick_json(row, _COURSE_JSON_KEYS["name"])
    if not name:
        return None
    start, end = parse_periods(_pick_json(row, _COURSE_JSON_KEYS["period"]))
    return CourseEntry(
        name=name,
        teacher=_pick_json(row, _COURSE_JSON_KEYS["teacher"]),
        weekday=parse_weekday(_pick_json(row, _COURSE_JSON_KEYS["weekday"])),
        start_period=start,
        end_period=end,
        weeks=_pick_json(row, _COURSE_JSON_KEYS["weeks"]),
        place=_pick_json(row, _COURSE_JSON_KEYS["place"]),
        credit=_pick_json(row, _COURSE_JSON_KEYS["credit"]),
        category=_pick_json(row, _COURSE_JSON_KEYS["category"]),
    )


def _grade_from_json_row(row: dict[str, Any]) -> Optional[GradeEntry]:
    name = _pick_json(row, _GRADE_JSON_KEYS["name"])
    if not name:
        return None
    return GradeEntry(
        term=_pick_json_many(row, _GRADE_JSON_KEYS["term"]),
        name=name,
        credit=_pick_json(row, _GRADE_JSON_KEYS["credit"]),
        score=_pick_json(row, _GRADE_JSON_KEYS["score"]),
        point=_pick_json(row, _GRADE_JSON_KEYS["point"]),
        category=_pick_json(row, _GRADE_JSON_KEYS["category"]),
        kind=_pick_json(row, _GRADE_JSON_KEYS["kind"]),
    )


def _term_from_json(data: Any, rows: list[dict[str, Any]]) -> str:
    """学期：先看记录里有没有，再看整包数据的头部。

    读不到就留空 —— 界面上写"本学期"也比编一个学期名好。
    """
    for row in rows:
        term = _pick_json_many(row, _GRADE_JSON_KEYS["term"])
        if term:
            return term
    if isinstance(data, dict):
        return _pick_json_many(data, _GRADE_JSON_KEYS["term"])
    return ""


def _load_json(payload: Any) -> Any:
    """把 JSON 原文读成对象 / 数组。不是合法 JSON 时如实报错（不猜）。"""
    if not isinstance(payload, str):
        return payload
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AcademicImportError(
            "这段 JSON 不完整（括号或引号没闭合）—— 确认整段复制过来。",
            kind=AcademicImportKind.UNRECOGNIZED,
            detail=str(exc),
        ) from exc


# ------------------------------------------------------------------ 正方（JSON）


def parse_zf_schedule(payload: Any) -> tuple[str, list[CourseEntry]]:
    """正方课表接口 →（学期, 课程表）。它直接给 JSON：`kbList` 是课。"""
    data = _as_json(payload)
    items = data.get("kbList") or data.get("kb_list") or []
    if not isinstance(items, list):
        raise AcademicImportError("这段 JSON 里没有课表数组（kbList）。", kind=AcademicImportKind.UNRECOGNIZED)
    info = data.get("xsxx") or {}
    if not isinstance(info, dict):
        info = {}
    term = ""
    for key in ("XNMC", "XNM", "xnmc", "xnm"):
        value = info.get(key) or data.get(key)
        if value:
            term = str(value).strip()
            break

    courses: list[CourseEntry] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        name = _pick(raw, "kcmc", "courseName")
        if not name:
            continue
        start, end = parse_periods(_pick(raw, "jcs", "jcor", "jcs2"))
        courses.append(
            CourseEntry(
                name=name,
                teacher=_pick(raw, "xm", "teacher", "jsxm"),
                weekday=parse_weekday(_pick(raw, "xqj", "weekday")),
                start_period=start,
                end_period=end,
                weeks=_pick(raw, "zcd", "zcmc", "weeks"),
                place=_pick(raw, "cdmc", "jxdd", "place"),
                credit=_pick(raw, "xf", "credit"),
                category=_pick(raw, "kcxzmc", "kclbmc"),
            )
        )
    if not courses:
        raise AcademicImportError(
            "课表数组是空的 —— 换成课表页整页复制试试。", kind=AcademicImportKind.NO_ROWS
        )
    return term, courses


def parse_zf_grades(payload: Any) -> list[GradeEntry]:
    data = _as_json(payload)
    items = data.get("items") or data.get("cjList") or []
    if not isinstance(items, list):
        raise AcademicImportError("这段 JSON 里没有成绩数组（items）。", kind=AcademicImportKind.UNRECOGNIZED)
    grades: list[GradeEntry] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        name = _pick(raw, "kcmc", "courseName")
        if not name:
            continue
        term = " ".join(
            part for part in (_pick(raw, "xnmmc"), _pick(raw, "xqmmc")) if part
        )
        grades.append(
            GradeEntry(
                term=term,
                name=name,
                credit=_pick(raw, "xf", "credit"),
                score=_pick(raw, "cj", "zcj", "score"),
                point=_pick(raw, "jd", "gpoint"),
                category=_pick(raw, "kcxzmc", "kclbmc"),
                kind=_pick(raw, "kcsx", "kcxz"),
            )
        )
    if not grades:
        raise AcademicImportError("成绩数组是空的。", kind=AcademicImportKind.NO_ROWS)
    return grades


def _as_json(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise AcademicImportError(
                "这不是合法 JSON —— 确认复制完整。",
                kind=AcademicImportKind.UNRECOGNIZED,
                detail=str(exc),
            ) from exc
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _pick(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


# ------------------------------------------------------------------ 表格文本

"""表头 → 内部字段。用户复制出来的表头五花八门，所以同义词要收全。"""
_COURSE_HEADERS: dict[str, str] = {
    "课程名称": "name", "课程名": "name", "课程": "name", "科目": "name",
    "教师": "teacher", "老师": "teacher", "任课教师": "teacher", "授课教师": "teacher",
    "星期": "weekday", "周几": "weekday", "上课星期": "weekday", "星期几": "weekday",
    "节次": "period", "上课节次": "period", "时间": "period", "上课时间": "period",
    "地点": "place", "教室": "place", "上课地点": "place", "上课教室": "place",
    "周次": "weeks", "上课周次": "weeks",
    "学分": "credit",
    "课程性质": "category", "课程类别": "category", "类别": "category", "性质": "category",
}

_GRADE_HEADERS: dict[str, str] = {
    "学年学期": "term", "学期": "term", "学年": "term",
    "课程名称": "name", "课程名": "name", "课程": "name",
    "学分": "credit",
    "成绩": "score", "总成绩": "score", "分数": "score",
    "绩点": "point",
    "课程性质": "category", "课程类别": "category",
    "课程属性": "kind", "必修选修": "kind", "属性": "kind",
}


def split_table_rows(raw: str) -> list[list[str]]:
    """把粘贴进来的表格文本切成行列。制表符优先，其次逗号，最后两个以上空格。

    分隔符按**前几行里第一行带分隔符的**来判断，不按第一行：
    粘贴内容常常先带一行标题（"XX大学 2024-2025 学年第一学期课表"），
    那一行里既没有制表符也没有逗号 —— 拿它当样本会把整张表按"两个空格"切，
    于是表头认不出来、一节课都读不到。
    """
    lines = [line.rstrip("\r") for line in (raw or "").splitlines()]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return []
    head = lines[:8]
    sample = next((line for line in head if "\t" in line), "")
    if not sample:
        sample = next((line for line in head if "," in line), lines[0])
    if "\t" in sample:
        separator: str | re.Pattern[str] = "\t"
    elif "," in sample:
        separator = ","
    else:
        separator = re.compile(r"\s{2,}")

    def _split(line: str) -> list[str]:
        return [cell.strip() for cell in re.split(separator, line.strip())]

    return [_split(line) for line in lines]


def _header_map(header: list[str], table: dict[str, str]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for index, name in enumerate(header):
        key = table.get(html_module.unescape(name or "").strip())
        if key and key not in mapping.values():
            mapping[index] = key
    return mapping


def parse_tabular_courses(raw: str) -> tuple[str, list[CourseEntry]]:
    """表格文本 → 课程表。

    两条路，先严后宽：

    1. **有表头**（表头不一定在第一行 —— 粘贴内容常常先带一行标题，比如
       "XX大学 2024-2025 学年第一学期课表"）：按名字对齐列，列序换过也读得对；
    2. **没有表头**：按"每行第一格是课名，行内找得到星期 / 节次"读。
       用户从页面上随手复制一段时多半长这样 —— 要求表头必须在第一行，
       等于把最常见的贴法判成"格式不对"，而"贴了没反应"比"读得不够全"更让人放弃。
    """
    rows = split_table_rows(raw)
    if len(rows) < 2:
        raise AcademicImportError(
            "内容太短了 —— 至少要两行（一行是课，一行是它的时间）。",
            kind=AcademicImportKind.NO_ROWS,
        )

    header_index, mapping = _find_course_header(rows)
    if mapping is None:
        loose = _courses_without_header(rows)
        if loose:
            return "", loose
        raise AcademicImportError(
            "读不出这是课表。最省事的办法：在课表页 Ctrl+A 全选复制，"
            "连表头那一行（「课程名称」）一起贴进来。",
            kind=AcademicImportKind.NO_HEADER,
            detail=" · ".join(rows[0][:8]),
        )

    courses: list[CourseEntry] = []
    for row in rows[header_index + 1 :]:
        item: dict[str, str] = {}
        for index, field in mapping.items():
            if index < len(row):
                item[field] = row[index]
        name = (item.get("name") or "").strip()
        if not name:
            continue
        start, end = parse_periods(item.get("period", ""))
        courses.append(
            CourseEntry(
                name=name,
                teacher=item.get("teacher", ""),
                weekday=parse_weekday(item.get("weekday", "")),
                start_period=start,
                end_period=end,
                weeks=item.get("weeks", ""),
                place=item.get("place", ""),
                credit=item.get("credit", ""),
                category=item.get("category", ""),
            )
        )
    if not courses:
        loose = _courses_without_header(rows)
        if loose:
            return "", loose
        raise AcademicImportError(
            "表头认出来了，但一节课都没读到 —— 多半只复制了一部分，整页再复制一次试试。",
            kind=AcademicImportKind.NO_ROWS,
        )
    return "", courses


#: 表头行之前最多扫几行（"XX大学 2024-2025 学年第一学期课表"这类标题行）
_HEADER_SCAN_LIMIT = 8


def _find_course_header(rows: list[list[str]]) -> tuple[int, Optional[dict[int, str]]]:
    """在前几行里找表头。找到返回（行号, 列映射），找不到返回（-1, None）。

    为什么不是"第一行必须是表头"：学生们复制出来的一段常常带着一行标题，
    有时还带一行空行。把"表头在第一行"当成硬条件，就等于把最常见的贴法判成格式错误。
    """
    for index, row in enumerate(rows[:_HEADER_SCAN_LIMIT]):
        mapping = _header_map(row, _COURSE_HEADERS)
        if "name" in mapping.values():
            return index, mapping
    return -1, None


_PLACE_HINT = re.compile(r"(楼|室|馆|教|机房|中心|区)")


def _courses_without_header(rows: list[list[str]]) -> list[CourseEntry]:
    """没有表头时按行读：第一格是课名，其余格里找星期 / 节次 / 地点 / 教师。

    只认**读得出来**的那几项，读不出来就留空 —— 不按位置硬套。
    硬套位置会在换一所学校时把"地点"填成"老师"，那比空着更糟。
    """
    courses: list[CourseEntry] = []
    for row in rows:
        cells = [cell.strip() for cell in row if cell and cell.strip()]
        if len(cells) < 2:
            continue
        name = cells[0]
        if name in _COURSE_HEADERS or parse_weekday(name):
            continue
        weekday = 0
        start = end = 0
        place = ""
        teacher = ""
        for cell in cells[1:]:
            if not weekday and not re.search(r"节", cell):
                maybe = parse_weekday(cell)
                if maybe:
                    weekday = maybe
                    continue
            if not start:
                s, e = parse_periods(cell)
                if s and re.search(r"节|课", cell):
                    start, end = s, e
                    continue
            if not place and _PLACE_HINT.search(cell):
                place = cell
                continue
            if not teacher and 2 <= len(cell) <= 12 and not re.search(r"\d", cell):
                teacher = cell
        if weekday or start:
            courses.append(
                CourseEntry(
                    name=name,
                    teacher=teacher,
                    weekday=weekday,
                    start_period=start,
                    end_period=end,
                    place=place,
                )
            )
    return courses


def parse_tabular_grades(raw: str) -> list[GradeEntry]:
    """表格文本 → 成绩单。表头同样**不必在第一行**（前面常有标题行）。"""
    rows = split_table_rows(raw)
    if len(rows) < 2:
        raise AcademicImportError(
            "内容太短了 —— 至少要两行（一行是课，一行是成绩）。",
            kind=AcademicImportKind.NO_ROWS,
        )
    header_index = -1
    mapping: dict[int, str] = {}
    for index, row in enumerate(rows[:_HEADER_SCAN_LIMIT]):
        candidate = _header_map(row, _GRADE_HEADERS)
        if "name" in candidate.values():
            header_index, mapping = index, candidate
            break
    if header_index < 0:
        raise AcademicImportError(
            "读不出这是成绩单。在成绩页 Ctrl+A 全选复制，"
            "连表头那一行（「课程名称」）一起贴进来。",
            kind=AcademicImportKind.NO_HEADER,
            detail=" · ".join(rows[0][:8]),
        )
    grades: list[GradeEntry] = []
    for row in rows[header_index + 1 :]:
        item: dict[str, str] = {}
        for index, field in mapping.items():
            if index < len(row):
                item[field] = row[index]
        if (item.get("name") or "").strip():
            grades.append(GradeEntry(**item))
    if not grades:
        raise AcademicImportError(
            "表头认出来了，但一条成绩都没读到 —— 多半只复制了一部分，整页再复制一次试试。",
            kind=AcademicImportKind.NO_ROWS,
        )
    return grades


__all__ = [
    "detect_source",
    "looks_like_html",
    "looks_like_json",
    "parse_periods",
    "parse_json_courses",
    "parse_json_grades",
    "parse_qz_grades",
    "parse_qz_schedule",
    "parse_tabular_courses",
    "parse_tabular_grades",
    "parse_weekday",
    "parse_zf_grades",
    "parse_zf_schedule",
    "split_table_rows",
    "text_of",
]
