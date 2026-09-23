"""导入解析器：把用户贴进来的文本读成课表与成绩单。

它做三件事，顺序也是用户实际会遇到的顺序：

1. 先看这段东西是什么（空的？太短？HTML？JSON？表格文本？）；
2. HTML / JSON 就按版式走（强智页面、正方接口），认不出再退回表格读法 ——
   别的学校也可能复制出一张带表头的表；
3. 一条都读不出来时报**具体**的错（缺表头 / 只复制了表头 / 版式不认识），
   因为用户能改的正是这几种。

入口有两个，走的是同一条解析链：**粘贴的文本**与**上传的文件**。
文件那一侧先在这里解码（UTF-8 / GBK / 带 BOM 都能读，见 `textfile.py`），
解码后的文本一模一样地进解析 —— 同一个用户，用哪种方式把数据带进来，
读出来的结果必须相同。

没有网络、没有凭据、没有任何写操作：写入是业务层的事。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from zhiyin_data_sdk.gateways.academic import (
    AcademicImportError,
    AcademicImportGateway,
    AcademicImportKind,
    CourseImport,
    GradeImport,
    ImportFormat,
)
from zhiyin_infrastructure.academic.parsers import (
    detect_source,
    looks_like_html,
    looks_like_json,
    parse_json_courses,
    parse_json_grades,
    parse_qz_grades,
    parse_qz_schedule,
    parse_tabular_courses,
    parse_tabular_grades,
    text_of,
)
from zhiyin_infrastructure.textfile import decode_text, unsupported_reason

_MIN_LENGTH = 20

_FORMATS: tuple[ImportFormat, ...] = (
    ImportFormat(
        id="page",
        label="教务系统页面整页复制",
        howto="在你学校的课表页上 Ctrl+A 全选、Ctrl+C 复制，整段贴进来。"
        "正方、强智两套主流版式都能直接读。",
    ),
    ImportFormat(
        id="table",
        label="表格（Excel / WPS / 网页表格）",
        howto="连表头那一行一起选中复制。表头要有「课程名称」；"
        "课表再带上星期、节次、地点，成绩单带上学分、成绩。",
    ),
    ImportFormat(
        id="json",
        label="接口返回的 JSON",
        howto="课表/成绩接口返回的那段 JSON（正方新版就是这种），整段贴进来；"
        "也可以把导出的 .json 文件直接传上来。每门课一条记录的数组同样能读。",
    ),
)


class ManualAcademicImporter(AcademicImportGateway):
    """手动导入的解析实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self) -> None:
        self._last: dict[str, Any] = {}

    def formats(self) -> list[ImportFormat]:
        return list(_FORMATS)

    # ---------------------------------------------------------------- 文件

    def read_text(self, data: bytes, *, filename: str = "") -> str:
        """把上传的文件读成文本（编码识别 + 二进制格式当场拒绝）。

        两条边界：

        1. 空文件与"读不了的后缀"都在这里就说清楚 —— 让它们走到解析器的话，
           用户看到的是"读不出这是课表"，而真正的原因是他传的是一张 Excel。
        2. 解码是**尽力而为，不抛异常**：解不出来也要给他一段文本，
           由解析器按内容说"读不出"。半份能读的内容比一句"文件坏了"有用得多。
        """
        reason = unsupported_reason(filename)
        if reason:
            raise AcademicImportError(reason, kind=AcademicImportKind.UNRECOGNIZED, detail=filename)
        text = decode_text(data)
        if not text.strip():
            label = filename or "这个文件"
            raise AcademicImportError(
                f"「{label}」是空的 —— 重新导出一份，或者把表格选中复制、粘贴进来。",
                kind=AcademicImportKind.EMPTY,
                detail=filename,
            )
        return text

    # ---------------------------------------------------------------- 课表

    def parse_courses(self, raw: str) -> CourseImport:
        text = self._guard(raw, what="课表")
        source, term, courses = self._read(text, kind="courses")
        self._remember(source, courses=len(courses))
        return CourseImport(source=source, term=term, courses=courses)

    # ---------------------------------------------------------------- 成绩

    def parse_grades(self, raw: str) -> GradeImport:
        text = self._guard(raw, what="成绩单")
        source, _term, grades = self._read(text, kind="grades")
        self._remember(source, grades=len(grades))
        return GradeImport(source=source, grades=grades)

    # ---------------------------------------------------------------- 内里

    def _guard(self, raw: str, *, what: str) -> str:
        text = (raw or "").strip()
        if not text:
            raise AcademicImportError(f"还没有{what}内容。", kind=AcademicImportKind.EMPTY)
        if len(text) < _MIN_LENGTH:
            raise AcademicImportError(
                f"这段{what}太短了，不像是一份完整的表。",
                kind=AcademicImportKind.TOO_SHORT,
                detail=f"len={len(text)}",
            )
        return text

    def _read(self, text: str, *, kind: str) -> tuple[str, str, list[Any]]:
        """按形态分流。返回（来源, 学期, 条目）。"""
        if looks_like_json(text):
            try:
                if kind == "courses":
                    term, courses = parse_json_courses(text)
                    return "json", term, courses
                return "json", "", parse_json_grades(text)
            except AcademicImportError:
                # **合法的 JSON 读不出课**：那句错已经是最具体的一句，直接抛。
                # 退回表格读法只会更糟 —— 它看到的是一行行 `"day": "星期二",`，
                # 最后报"把表头（课程名称）一起复制进来"，而用户手里根本没有表格。
                if _is_valid_json(text):
                    raise
                # 不是合法 JSON（只是碰巧以 `{` 开头的一段文本）：继续当表格试一次
                pass

        if looks_like_html(text):
            source = detect_source(text)
            if source == "qz":
                if kind == "courses":
                    term, courses = parse_qz_schedule(text)
                    return "qz", term, courses
                return "qz", "", parse_qz_grades(text)
            if source == "zf":
                # 正方新版是 JSON，但成绩页也有 HTML 版；先试表格读法
                pass
            # 别的系统（或认不出的版式）：把正文抽出来当表格读，读不出来再放弃
            try:
                return self._read_table(text_of(text), kind=kind)
            except AcademicImportError as exc:
                raise AcademicImportError(
                    "这一页的版式我还认不出来。可以试试：在课表/成绩页上"
                    "把那张表连表头一起选中复制，或者导出成 Excel 再整列复制。",
                    kind=AcademicImportKind.UNRECOGNIZED,
                    detail=exc.detail or f"source={source}",
                ) from exc

        return self._read_table(text, kind=kind)

    def _read_table(self, text: str, *, kind: str) -> tuple[str, str, list[Any]]:
        if kind == "courses":
            term, courses = parse_tabular_courses(text)
            return "table", term, courses
        return "table", "", parse_tabular_grades(text)

    def _remember(self, source: str, **counts: int) -> None:
        self._last = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source,
            **counts,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "formats": [item.id for item in _FORMATS],
            "last_import": dict(self._last),
            "mode": "manual_import",
        }


def _is_valid_json(raw: str) -> bool:
    """这段文本本身是不是合法 JSON —— 判断"该不该继续按表格试一遍"。"""
    try:
        json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    return True


__all__ = ["ManualAcademicImporter"]
