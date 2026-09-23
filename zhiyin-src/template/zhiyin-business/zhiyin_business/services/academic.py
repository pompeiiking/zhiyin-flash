"""课表与成绩单的导入服务：解析 → 落快照 → 更新画像摘要。

为什么这三步要在一个服务里：它们共享同一条判断 —— **这份数据算不算拿到了**。
拆开的话，采集清单（按画像字段判断缺不缺）、课表界面（按快照判断有没有）、
导入回执（按解析结果判断读到了几条）会各自算一遍，迟早不一致。

入口有两个：粘贴的原文（`import_`）与上传的文件（`import_files`）。
后者只多一步"字节 → 文本"，之后走的是**同一条**链路 —— 同一份数据，
用哪种方式带进来，落库的结果必须一样。

一条边界写在这里：这里没有凭据。数据是用户自己贴进来的，
我们从没碰过他学校的账号 —— 所以"清空"是清空他导入的东西，不是收回授权。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from zhiyin_business.ports.academic import AcademicImportResult
from zhiyin_business.ports.blackboard import AcademicService, ProfileService
from zhiyin_data_sdk.gateways.academic import (
    AcademicImportError,
    AcademicImportGateway,
    AcademicImportKind,
    AcademicSnapshot,
)
from zhiyin_data_sdk.repositories import AcademicSnapshotRepository
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.errors import InvalidRequest

"""画像里那两条摘要叫什么。课表与成绩单的明细在快照里，画像只放一句能读懂的话。"""
_PROFILE_LABEL: dict[str, str] = {
    "courses": "课程表",
    "scores": "成绩单",
}


class DefaultAcademicService(AcademicService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        snapshots: AcademicSnapshotRepository,
        importer: AcademicImportGateway,
        profiles: Optional[ProfileService] = None,
    ) -> None:
        self._snapshots = snapshots
        self._importer = importer
        self._profiles = profiles

    async def get(self, user_id: str) -> Optional[AcademicSnapshot]:
        return await self._snapshots.get(user_id)

    async def import_(
        self,
        user_id: str,
        *,
        courses_raw: str = "",
        grades_raw: str = "",
        school: str = "",
        term: str = "",
    ) -> AcademicImportResult:
        courses_text = (courses_raw or "").strip()
        grades_text = (grades_raw or "").strip()
        source = ""
        parsed_term = term.strip()
        courses = []
        grades = []
        try:
            if not courses_text and not grades_text:
                raise AcademicImportError(
                    "还没贴内容 —— 课表或成绩单，贴一份就能导入。",
                    kind=AcademicImportKind.EMPTY,
                )
            if courses_text:
                parsed = self._importer.parse_courses(courses_text)
                source = parsed.source
                parsed_term = parsed_term or parsed.term
                courses = parsed.courses
            if grades_text:
                grade_parsed = self._importer.parse_grades(grades_text)
                source = source or grade_parsed.source
                grades = grade_parsed.grades
        except AcademicImportError as exc:
            # "这份原文我读不出来"是**用户能自己修的事**（换个复制方式、连表头一起复制），
            # 不是服务器故障。原样往上抛的话 api 层没有对应的处理器，用户看到的是 500 ——
            # 明明手上有解法的提示，却被包成"服务器错误"。翻成 InvalidRequest，
            # api 会按 422 + 原话返回，界面照原样显示那句"该改哪里"。
            raise InvalidRequest(str(exc)) from exc

        notes = _notes_for(courses)
        snapshot = AcademicSnapshot(
            school=school.strip(),
            source=source,
            term=parsed_term,
            courses=courses,
            grades=grades,
            imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            note="；".join(notes),
        )
        saved = await self._snapshots.upsert(user_id, snapshot)
        wrote = await self._write_summaries(user_id, saved)
        return AcademicImportResult(
            school=saved.school,
            source=saved.source,
            term=saved.term,
            courses=len(saved.courses),
            courses_scheduled=_scheduled_count(saved.courses),
            grades=len(saved.grades),
            imported_at=saved.imported_at,
            notes=notes,
            wrote_profile=[_PROFILE_LABEL.get(key, key) for key in wrote],
        )

    async def import_files(
        self,
        user_id: str,
        *,
        courses_file: Optional[bytes] = None,
        grades_file: Optional[bytes] = None,
        courses_name: str = "",
        grades_name: str = "",
        courses_raw: str = "",
        grades_raw: str = "",
        school: str = "",
        term: str = "",
    ) -> AcademicImportResult:
        """文件入口：解码之后走**同一条**导入链路（落快照 + 写画像摘要）。

        文件优先于同一栏里的文本：用户选了文件，那就是他要导的东西；
        两边都读一遍会得到"哪一条算数"这个问题，而它没有诚实的答案。

        没选文件、也没贴文本时，交给 `import_` 去说那句"还没贴内容" ——
        这里不另写一份判定，两处各判一次迟早会不一致。
        """
        return await self.import_(
            user_id,
            courses_raw=self._decode_or_explain(courses_file, courses_name) or courses_raw,
            grades_raw=self._decode_or_explain(grades_file, grades_name) or grades_raw,
            school=school,
            term=term,
        )

    def _decode_or_explain(self, data: Optional[bytes], filename: str) -> str:
        """一份文件 → 一段文本；没给文件就返回空串（解码细节在网关里）。

        "读不了这个文件"（Excel 那种二进制、空文件）与"读不出这段原文"是同一类事：
        **用户能自己改**。所以这里翻成 `InvalidRequest`，让 api 按 422 + 原话返回，
        界面照原样显示那句"另存为 CSV / 换一份"。不翻的话用户看到的是 500。
        """
        if not data:
            return ""
        try:
            return self._importer.read_text(data, filename=filename)
        except AcademicImportError as exc:
            raise InvalidRequest(str(exc)) from exc

    async def revoke(self, user_id: str) -> None:
        """清空导入：快照与画像摘要一起删。

        只删快照的话，采集清单里"课程表 / 成绩单"会一直显示已拿到 ——
        用户再也回不到导入入口。那是"看起来清掉了"，不是清掉。
        """
        await self._snapshots.delete(user_id)
        if self._profiles is None:
            return
        for key in _PROFILE_LABEL:
            await self._profiles.drop_field(user_id, key)

    async def _write_summaries(self, user_id: str, snapshot: AcademicSnapshot) -> list[str]:
        """把"拿到了什么、什么时候拿的"写成画像里的一句话。"""
        if self._profiles is None:
            return []
        written: list[str] = []
        for key, summary in (
            ("courses", _summary("门课", snapshot.term, len(snapshot.courses), snapshot.imported_at)),
            ("scores", _summary("门成绩", snapshot.term, len(snapshot.grades), snapshot.imported_at)),
        ):
            if not summary:
                continue
            await self._profiles.update_field(
                user_id,
                key,
                summary,
                # 它来自学校系统导出的原始记录（用户自己带进来的），不是我们推断的
                confidence=1.0,
                source=ProfileSource.RECORD.value,
                evidence=["用户导入的课表/成绩单原文"],
            )
            written.append(key)
        return written


def _summary(unit: str, term: str, count: int, imported_at: str) -> str:
    """一条都不到就不写摘要：写"0 门课"会让采集清单以为这条已经有了。"""
    if count <= 0:
        return ""
    when = imported_at[:10] if imported_at else ""
    prefix = f"{term} · " if term else ""
    tail = f"（{when} 导入）" if when else "（自己导入）"
    return f"{prefix}{count} {unit}{tail}"


def _notes_for(courses) -> list[str]:
    """读的时候发现的问题要**说出来**，但不能因此拒绝整份导入。"""
    unplaced = len(courses) - _scheduled_count(courses)
    if unplaced:
        return [f"有 {unplaced} 门课没读出上课时间，不会排进课表格子（其余照常导入）"]
    return []


def _scheduled_count(courses) -> int:
    """读出了上课时间（星期 + 节次）的课数 —— 也就是**真会出现在课表里**的那些。

    判据与前端画课表的判据一致（`useDayPlan.of` 也要求 weekday 1–7 且 start_period ≥ 1）：
    两处不一样的话，回执说"已排进课表"而日历上查无此课，用户只能认为产品在说谎。
    """
    return sum(
        1
        for course in courses
        if 1 <= course.weekday <= 7 and course.start_period >= 1
    )


__all__ = ["DefaultAcademicService"]
