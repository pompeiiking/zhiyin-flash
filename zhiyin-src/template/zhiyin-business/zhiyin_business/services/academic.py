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
import logging
import re
from typing import Optional
from functools import wraps

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

logger = logging.getLogger(__name__)

"""画像里那两条摘要叫什么。课表与成绩单的明细在快照里，画像只放一句能读懂的话。"""
_PROFILE_LABEL: dict[str, str] = {
    "courses": "课程表",
    "scores": "成绩单",
}

"""两个上限，两条不同的口径 —— 提示文案必须对得上用户卡在哪一条：

- `MAX_UPLOAD_BYTES`：**文件大小**。用户看到的是"这个文件 3 MB"，改法是"只保留表格另存"；
- `MAX_PASTE_CHARS`：**正文字符数**。用户看到的是"我贴了 30 万字"，改法是"删掉无关部分"。

混成一句（"内容过大"）时，用户不知道是把文件压小还是把文字删短（深度测试 D9）。
"""
MAX_UPLOAD_BYTES = 2_000_000
MAX_PASTE_CHARS = 200_000

_DECODE_MESSAGE = (
    "这个文件读不出文字（编码无法识别，可能不是文本文件）。"
    "请在 Excel/记事本里另存为 UTF-8 或 GBK 的 TXT/CSV 再上传，或者把表格内容选中复制、粘贴进来。"
)


def academic_mutation(method):
    @wraps(method)
    async def call(self, user_id, *args, **kwargs):
        async with self._snapshots.write_lock(user_id):
            return await method(self, user_id, *args, **kwargs)
    return call


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
        snapshot = await self._snapshots.get(user_id)
        if not snapshot or not self._profiles or not hasattr(self._profiles, "get") or not any(not row.term for row in snapshot.grades):
            return snapshot
        # Older imports kept the grade term only in their generated profile
        # summary. Recover it only from that identifiable import record.
        profile = await self._profiles.get(user_id)
        field = next((f for f in (profile.fields if profile else [])
                      if f.key == "scores" and f.source == ProfileSource.RECORD), None)
        match = re.fullmatch(r"(.+?) · \d+ 门成绩（.*导入）", str(field.value)) if field else None
        if not match:
            return snapshot
        return snapshot.model_copy(update={"grades": [
            row if row.term else row.model_copy(update={"term": match.group(1)})
            for row in snapshot.grades
        ]})

    @academic_mutation
    async def import_(
        self,
        user_id: str,
        *,
        courses_raw: str = "",
        grades_raw: str = "",
        school: str = "",
        term: str = "",
        expected_version: str = "",
    ) -> AcademicImportResult:
        courses_text = (courses_raw or "").strip()
        grades_text = (grades_raw or "").strip()
        if len(courses_text) + len(grades_text) > MAX_PASTE_CHARS:
            total = len(courses_text) + len(grades_text)
            raise InvalidRequest(
                f"粘贴的正文有 {total} 个字，超过 {MAX_PASTE_CHARS} 字（20 万字）上限 —— "
                "请只保留表头与课表/成绩行，删掉页面上的其他文字后再试；文件上传请确认文件没有夹带无关内容。"
            )
        existing = await self.get(user_id)
        if expected_version:
            from zhiyin_business.services.academic_preview import academic_version, AcademicPreviewChanged
            if academic_version(existing) != expected_version:
                raise AcademicPreviewChanged("课表或成绩已经变化，请重新预览后确认。")
        source = existing.source if existing else ""
        parsed_term = term.strip() or (existing.term if existing else "")
        courses = list(existing.courses) if existing else []
        grades = list(existing.grades) if existing else []
        updated: set[str] = set()
        dropped_courses = 0
        dropped_grades = 0
        try:
            if not courses_text and not grades_text:
                raise AcademicImportError(
                    "还没贴内容 —— 课表或成绩单，贴一份就能导入。",
                    kind=AcademicImportKind.EMPTY,
                )
            if courses_text:
                parsed = self._importer.parse_courses(courses_text)
                source = parsed.source
                parsed_term = term.strip() or parsed.term or parsed_term
                courses, dropped_courses = _dedupe_courses(parsed.courses)
                updated.add("courses")
            if grades_text:
                grade_parsed = self._importer.parse_grades(grades_text)
                if not courses_text:
                    source = grade_parsed.source
                # The snapshot term belongs to the latest import, so keep the
                # grade's own term on each row before a later course import.
                # An unspecified term must not inherit an unrelated course term.
                grades = [row.model_copy(update={"term": row.term or term.strip()})
                          for row in grade_parsed.grades]
                grades, dropped_grades = _dedupe_grades(grades)
                updated.add("scores")
        except AcademicImportError as exc:
            # "这份原文我读不出来"是**用户能自己修的事**（换个复制方式、连表头一起复制），
            # 不是服务器故障。原样往上抛的话 api 层没有对应的处理器，用户看到的是 500 ——
            # 明明手上有解法的提示，却被包成"服务器错误"。翻成 InvalidRequest，
            # api 会按 422 + 原话返回，界面照原样显示那句"该改哪里"。
            raise InvalidRequest(str(exc)) from exc

        notes = _notes_for(courses)
        if dropped_courses:
            notes.insert(
                0,
                f"已按“课程名 + 星期 + 节次 + 周次”合并 {dropped_courses} 条重复课程记录（保留先出现的一条）",
            )
        if dropped_grades:
            notes.insert(
                0,
                f"已按“课程名 + 学期 + 成绩 + 学分 + 绩点”合并 {dropped_grades} 条重复成绩记录（保留先出现的一条）",
            )
        snapshot = AcademicSnapshot(
            school=school.strip() or (existing.school if existing else ""),
            source=source,
            term=parsed_term,
            courses=courses,
            grades=grades,
            imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            note="；".join(notes),
        )
        saved = await self._snapshots.upsert(user_id, snapshot)
        wrote = await self._write_summaries(user_id, saved, updated)
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
        for data, name in ((courses_file, courses_name), (grades_file, grades_name)):
            if data and len(data) > MAX_UPLOAD_BYTES:
                # 这一条说的是**文件大小**：改法是"只保留表格另存"，不是"删掉几段文字"。
                raise InvalidRequest(
                    f"「{name or '上传的文件'}」这个文件有 {len(data) / 1_000_000:.1f} MB，"
                    f"超过 2 MB 上限 —— 请只保留课表/成绩表，另存为 TXT 或 CSV 后再上传。"
                )
        courses_text = self._decode_or_explain(courses_file, courses_name) or courses_raw
        grades_text = self._decode_or_explain(grades_file, grades_name) or grades_raw
        for text, name in ((courses_text, courses_name), (grades_text, grades_name)):
            if len(text) > MAX_PASTE_CHARS:
                # 这一条说的是**正文字符数**（文件可能不到 2 MB，但解出来是超长文本）。
                raise InvalidRequest(
                    f"「{name or '上传的文件'}」解出来的正文有 {len(text)} 个字，"
                    f"超过 {MAX_PASTE_CHARS} 字（20 万字）上限 —— 请只保留表头与数据行后再上传。"
                )
        return await self.import_(
            user_id,
            courses_raw=courses_text,
            grades_raw=grades_text,
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
        except (UnicodeError, LookupError, ValueError):
            # 解码器抛出的原话（如 "The encoded data was not valid for encoding utf-8"）
            # 是给开发者看的。用户能做的只有换一种导出形式 —— 说那句。
            logger.warning("文件解码失败（%s，%d 字节）", filename or "未提供文件名", len(data), exc_info=True)
            raise InvalidRequest(_DECODE_MESSAGE) from None
        except Exception:  # noqa: BLE001 - 读文件失败不能把英文异常原文抛到界面上
            logger.warning("文件读取失败（%s）", filename or "未提供文件名", exc_info=True)
            raise InvalidRequest(_DECODE_MESSAGE) from None

    @academic_mutation
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

    async def revoke_courses(self, user_id: str) -> None:
        """只撤回课程；成绩属于另一块用户资料，不能被顺带删除。"""
        await self._revoke_part(user_id, "courses")

    async def revoke_grades(self, user_id: str) -> None:
        """只撤回成绩；课表仍继续服务日历与时间安排。"""
        await self._revoke_part(user_id, "scores")

    @academic_mutation
    async def _revoke_part(self, user_id: str, key: str) -> None:
        snapshot = await self._snapshots.get(user_id)
        if snapshot is not None:
            courses = [] if key == "courses" else list(snapshot.courses)
            grades = [] if key == "scores" else list(snapshot.grades)
            if courses or grades:
                update = {"courses": courses, "grades": grades}
                if key == "courses":
                    update["note"] = ""
                await self._snapshots.upsert(user_id, snapshot.model_copy(update=update))
            else:
                await self._snapshots.delete(user_id)
        if self._profiles is not None:
            await self._profiles.drop_field(user_id, key)

    async def _write_summaries(
        self, user_id: str, snapshot: AcademicSnapshot, updated: set[str]
    ) -> list[str]:
        """把"拿到了什么、什么时候拿的"写成画像里的一句话。"""
        if self._profiles is None:
            return []
        written: list[str] = []
        grade_terms = {row.term for row in snapshot.grades}
        grade_term = next(iter(grade_terms)) if len(grade_terms) == 1 else ""
        for key, summary in (
            ("courses", _summary("门课", snapshot.term, len(snapshot.courses), snapshot.imported_at)),
            ("scores", _summary("门成绩", grade_term, len(snapshot.grades), snapshot.imported_at)),
        ):
            if key not in updated or not summary:
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


"""重复行的合并口径。

为什么按"整行相同"合并、而不是按课程名：同一门课重修会有两条**分数不同**的成绩，
按课程名去重会把重修记录吞掉。按整行相同合并只处理"同一份表贴了两遍 / 文件里
复制粘贴重复了一段"这种真正的重复，保留先出现的一条。
"""
_COURSE_KEY_FIELDS = ("name", "weekday", "start_period", "end_period", "weeks", "place")
_GRADE_KEY_FIELDS = ("term", "name", "score", "credit", "point", "category", "kind")


def _row_key(row, fields: tuple[str, ...]) -> tuple[str, ...]:
    parts: list[str] = []
    for field in fields:
        value = getattr(row, field, "")
        parts.append(str(value if value is not None else "").strip())
    return tuple(parts)


def _dedupe(rows, fields: tuple[str, ...]):
    seen: set[tuple[str, ...]] = set()
    kept = []
    dropped = 0
    for row in rows:
        key = _row_key(row, fields)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(row)
    return kept, dropped


def _dedupe_courses(courses):
    return _dedupe(courses, _COURSE_KEY_FIELDS)


def _dedupe_grades(grades):
    return _dedupe(grades, _GRADE_KEY_FIELDS)


__all__ = ["DefaultAcademicService"]
