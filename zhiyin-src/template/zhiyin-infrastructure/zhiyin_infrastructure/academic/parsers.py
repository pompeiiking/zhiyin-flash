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
   · 正方课表 / 成绩接口的 JSON
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
    probe = (raw or "").strip()
    return probe.startswith("{") and '"' in probe


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
