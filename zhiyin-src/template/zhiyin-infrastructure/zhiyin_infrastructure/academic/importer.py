"""导入解析器：把用户贴进来的文本读成课表与成绩单。

它做三件事，顺序也是用户实际会遇到的顺序：

1. 先看这段东西是什么（空的？太短？HTML？JSON？表格文本？）；
2. HTML / JSON 就按版式走（强智页面、正方接口），认不出再退回表格读法 ——
   别的学校也可能复制出一张带表头的表；
3. 一条都读不出来时报**具体**的错（缺表头 / 只复制了表头 / 版式不认识），
   因为用户能改的正是这几种。

没有网络、没有凭据、没有任何写操作：写入是业务层的事。
"""

from __future__ import annotations

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
    parse_qz_grades,
    parse_qz_schedule,
    parse_tabular_courses,
    parse_tabular_grades,
    parse_zf_grades,
    parse_zf_schedule,
    text_of,
)

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
        howto="如果你能拿到课表/成绩接口返回的那段 JSON（正方新版就是这种），整段贴进来。",
    ),
)


class ManualAcademicImporter(AcademicImportGateway):
    """手动导入的解析实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self) -> None:
        self._last: dict[str, Any] = {}

    def formats(self) -> list[ImportFormat]:
        return list(_FORMATS)

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
                    term, courses = parse_zf_schedule(text)
                    return "json", term, courses
                return "json", "", parse_zf_grades(text)
            except AcademicImportError:
                # JSON 读不出来时不要立刻失败：先当表格再试一次（有人贴的是 JSON 数组）
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


__all__ = ["ManualAcademicImporter"]
