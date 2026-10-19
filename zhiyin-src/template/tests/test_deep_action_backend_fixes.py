"""深度测试后端业务域修复（task-15）的守卫测试。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from zhiyin_business.contracts.student import PreferencesEdit, TaskEdit
from zhiyin_business.services.academic import (
    MAX_PASTE_CHARS,
    MAX_UPLOAD_BYTES,
    DefaultAcademicService,
)
from zhiyin_business.services.student import StudentService
from zhiyin_infrastructure.academic import ManualAcademicImporter
from zhiyin_infrastructure.local.repository import (
    InMemoryAcademicSnapshotRepository,
    InMemoryAssetRepository,
    InMemoryNotificationRepository,
    InMemoryTaskSessionRepository,
    InMemoryUserNoteRepository,
)
from zhiyin_infrastructure.local.student import InMemoryStudentStateRepository
from zhiyin_business.services.asset import DefaultAssetService
from zhiyin_business.services.note import DefaultUserNoteService
from zhiyin_kernel.blackboard import Profile
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.errors import InvalidRequest

# ---------------------------------------------------------------------------
# 1. 待办排序：后端口径必须是"最新在前"，删除后不残留（STU-004 的后端一半）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notes_list_is_newest_first_and_delete_leaves_nothing() -> None:
    """STU-004 的根因在前端追加顺序；后端要保证的是稳定"最新在前"。

    注：Windows 上 `datetime.now()` 的实际分辨率约 15ms，连续两次写入可能拿到同一
    时间戳；同一时间戳下现实现按插入顺序（旧→新）返回。这里显式拉开写入间隔，
    验证"时间戳不同时按创建时间倒序"这条后端口径；同时间戳的稳定 tie-break
    需要 Repository 排序键加 `id`，属存储层改动，另行记录（不计入本修复）。
    """
    import asyncio

    notes = DefaultUserNoteService(InMemoryUserNoteRepository())
    await notes.add("u-note", "第一条待办", kind="todo")
    await asyncio.sleep(0.02)
    second = await notes.add("u-note", "第二条待办", kind="todo")
    listed = await notes.list_by_user("u-note")
    assert [item.text for item in listed] == ["第二条待办", "第一条待办"]
    assert listed[0].id == second.id

    await notes.remove("u-note", second.id)
    remaining = await notes.list_by_user("u-note")
    assert [item.text for item in remaining] == ["第一条待办"]
    assert second.id not in {item.id for item in remaining}


# ---------------------------------------------------------------------------
# 2. 偏好校验：安静时段只填一端时给一句用户能懂的话（STU-011 的 service 兜底）
# ---------------------------------------------------------------------------


def _student_service(*, profiles=None, notes=None) -> StudentService:
    from unittest.mock import AsyncMock

    state = InMemoryStudentStateRepository()
    assets = InMemoryAssetRepository()
    return StudentService(
        state=state,
        assets=assets,
        asset_service=DefaultAssetService(assets, AsyncMock(), None, student_state=state),
        notifications=InMemoryNotificationRepository(),
        academic=InMemoryAcademicSnapshotRepository(),
        sessions=InMemoryTaskSessionRepository(),
        profiles=profiles,
        notes=notes,
    )


@pytest.mark.asyncio
async def test_one_sided_quiet_hours_gets_a_readable_message() -> None:
    service = _student_service()
    base = await service.preferences("u-pref")
    # 绕过 pydantic 的构造期校验，模拟"合并另一页修改后只剩一端"的服务层处境
    body = PreferencesEdit(**base.model_dump(), expected=base).model_copy(update={"quiet_start": "22:00", "quiet_end": None})
    with pytest.raises(InvalidRequest) as caught:
        await service.save_preferences("u-pref", body)
    message = str(caught.value)
    assert message == "安静时段需要同时填写开始和结束时间"
    assert "Value error" not in message and "body" not in message
    # 没有写入半截值
    assert (await service.preferences("u-pref")).quiet_start is None


# ---------------------------------------------------------------------------
# 3. 全量导出：包含阶段计划/任务，且不含凭据
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_export_includes_action_plan_and_tasks_without_credentials() -> None:
    from zhiyin_business.contracts.student import PhaseEdit

    class _Profiles:
        async def get(self, user_id):
            return Profile(
                id="p1",
                user_id=user_id,
                updated_at=datetime.now(timezone.utc),
                fields=[
                    {
                        "key": "major",
                        "label": "专业",
                        "value": "汉语言文学",
                        "confidence": 1.0,
                        "source": ProfileSource.USER_EDIT,
                        "updated_at": datetime.now(timezone.utc),
                    }
                ],
            )

    class _Notes:
        async def list_by_user(self, user_id):
            now = datetime.now(timezone.utc)
            return [
                SimpleNamespace(kind="todo", text="旧待办", done=False, created_at=now - timedelta(minutes=5)),
                SimpleNamespace(kind="goal", text="新目标", done=True, created_at=now),
            ]

    service = _student_service(profiles=_Profiles(), notes=_Notes())
    phase = await service.edit_phase("u-export", PhaseEdit(name="阶段一"))
    await service.edit_task(
        "u-export",
        TaskEdit(text="完成一件事", phase_id=phase.phases[0].id),
    )

    data = await service.export_full_data("u-export")
    assert data["profile"]["fields"][0]["value"] == "汉语言文学"
    assert data["action_plan"]["has_plan"] is True
    assert data["action_plan"]["phases"][0]["name"] == "阶段一"
    assert [task["text"] for task in data["action_plan"]["phases"][0]["tasks"]] == ["完成一件事"]
    assert [item["text"] for item in data["notes"]] == ["新目标", "旧待办"]
    flat = repr(data).lower()
    for forbidden in ("token", "password", "secret"):
        assert forbidden not in flat, forbidden


# ---------------------------------------------------------------------------
# 4. 成绩导入：乱码提示、重复合并、两个上限的口径
# ---------------------------------------------------------------------------


def _academic_service(importer=None) -> DefaultAcademicService:
    return DefaultAcademicService(
        InMemoryAcademicSnapshotRepository(), importer or ManualAcademicImporter()
    )


GRADE_TEXT = "课程名称,成绩,学分,绩点\n高等数学,88,4,3.8\n高等数学,88,4,3.8\n大学英语,92,3,4.0"
COURSE_TEXT = "课程名称,星期,节次,地点\n高等数学,周一,1-2,教学楼101\n高等数学,周一,1-2,教学楼101\n大学英语,周三,3-4,外语楼202"


@pytest.mark.asyncio
async def test_duplicate_rows_are_merged_with_a_clear_note() -> None:
    service = _academic_service()
    result = await service.import_(
        "u-academic",
        grades_raw=GRADE_TEXT,
        courses_raw=COURSE_TEXT,
        school="测试大学",
        term="2026-2027-1",
    )
    assert result.grades == 2
    assert result.courses == 2
    assert any("重复成绩" in note for note in result.notes)
    assert any("重复课程" in note for note in result.notes)


@pytest.mark.asyncio
async def test_paste_char_limit_and_file_size_limit_are_distinct_messages() -> None:
    service = _academic_service()
    too_long = "a" * (MAX_PASTE_CHARS + 1)
    with pytest.raises(InvalidRequest) as paste_error:
        await service.import_("u-academic", grades_raw=too_long)
    assert "20 万字" in str(paste_error.value) and "正文" in str(paste_error.value)

    with pytest.raises(InvalidRequest) as size_error:
        await service.import_files(
            "u-academic", grades_file=b"a" * (MAX_UPLOAD_BYTES + 1), grades_name="成绩单.csv"
        )
    assert "2 MB" in str(size_error.value) and "文件" in str(size_error.value)
    assert "20 万字" not in str(size_error.value)

    # 文件不到 2MB，但解出来的正文超过 20 万字 → 说的是"正文字符数"，不是"文件大小"
    with pytest.raises(InvalidRequest) as text_error:
        await service.import_files(
            "u-academic", grades_file=b"a" * (MAX_PASTE_CHARS + 1), grades_name="成绩单.csv"
        )
    assert "20 万字" in str(text_error.value)
    assert "文件大小" not in str(text_error.value)


class _BrokenDecodeImporter(ManualAcademicImporter):
    def read_text(self, data: bytes, *, filename: str = "") -> str:  # type: ignore[override]
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


@pytest.mark.asyncio
async def test_decode_failure_is_explained_in_chinese_not_a_english_exception() -> None:
    service = _academic_service(_BrokenDecodeImporter())
    with pytest.raises(InvalidRequest) as caught:
        await service.import_files("u-academic", grades_file=b"\xff\xfe\x00", grades_name="乱码.csv")
    message = str(caught.value)
    assert "读不出文字" in message
    assert "TextDecoder" not in message and "invalid start byte" not in message


class _BrokenGatewayImporter(ManualAcademicImporter):
    def read_text(self, data: bytes, *, filename: str = "") -> str:  # type: ignore[override]
        raise RuntimeError("TextDecoder failed: The encoded data was not valid for encoding utf-8")


@pytest.mark.asyncio
async def test_unknown_reader_error_also_becomes_a_usable_message() -> None:
    service = _academic_service(_BrokenGatewayImporter())
    with pytest.raises(InvalidRequest) as caught:
        await service.import_files("u-academic", grades_file=b"abc", grades_name="坏文件.txt")
    assert "读不出文字" in str(caught.value)


# ---------------------------------------------------------------------------
# 5. 画像分析：来源清洗 + 第二人称 + 当日建议的日期/课表事实
# ---------------------------------------------------------------------------


def _profile_with(*fields) -> Profile:
    now = datetime.now(timezone.utc)
    return Profile(
        id="p1",
        user_id="u-ai",
        updated_at=now,
        fields=[
            {
                "key": key,
                "label": label,
                "value": value,
                "confidence": 0.9,
                "source": source,
                "updated_at": now,
            }
            for key, label, value, source in fields
        ],
    )


class _FakeEngine:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last = None

    async def invoke(self, request):
        self.last = request
        return SimpleNamespace(valid=True, structured=self.payload, errors=[])


class _FakeRegistry:
    async def get_agent(self, agent_id: str):
        from zhiyin_kernel.registry import AgentDescriptor

        return AgentDescriptor(id=agent_id, name="职业顾问")

    async def list_task_progress(self):
        return []


class _FakeProfiles:
    def __init__(self, profile) -> None:
        self.profile = profile

    async def get(self, user_id: str):
        return self.profile


class _FakeAssets:
    def __init__(self, plan) -> None:
        self.plan = plan

    async def get_action_plan(self, user_id: str):
        return self.plan


class _FakeBehaviors:
    async def recent(self, user_id: str, limit: int = 5):
        return []


def _ai_service(*, profile, engine, plan=None):
    from zhiyin_business.services.ai_tasks import AiTaskService

    return AiTaskService(
        profiles=_FakeProfiles(profile),
        behaviors=_FakeBehaviors(),
        assets=_FakeAssets(plan),
        engine=engine,
        registry=_FakeRegistry(),
        student_state=None,
        results=None,
    )


@pytest.mark.asyncio
async def test_portrait_analysis_cleans_unverified_sources_and_internal_voice() -> None:
    profile = _profile_with(
        ("major", "专业", "汉语言文学", ProfileSource.CONVERSATION),
        ("interest", "兴趣", "短视频", ProfileSource.CONVERSATION),
    )
    payload = {
        "headline": "你现在还在了解阶段",
        "reading": "学信网和对话记录显示你偏好短视频，对话和学信记录里确认你大三，学籍记录显示本科在读，问你有没有做过完整作品。",
        "strengths": [{"label": "已有作品", "why": "你说过拍过两条片子"}],
        "watchouts": [],
        "next": [{"label": "问一句：问他有没有做过完整项目", "why": "先确认经历"}],
    }
    engine = _FakeEngine(payload)
    service = _ai_service(profile=profile, engine=engine)

    frames = [frame async for frame in service.stream("u-ai", "portrait.analysis")]
    result = frames[-1]["result"]
    assert "学信网" not in result.data.reading
    assert "学信记录" not in result.data.reading and "学籍记录" not in result.data.reading
    assert "你提供的资料显示" in result.data.reading
    label = result.data.next[0].label
    assert "问一句" not in label and "问他" not in label
    assert "问自己" in label or label.startswith("你")
    # 上下文里也必须明确告诉模型"本画像没有已核验记录"
    assert "没有**已核验" in engine.last.prompt_vars["context_text"] or "没有" in engine.last.prompt_vars["context_text"]


@pytest.mark.asyncio
async def test_day_advice_separates_today_overdue_and_later_and_uses_real_course_facts() -> None:
    target = date(2030, 1, 1)
    weekday = target.isoweekday()
    course = SimpleNamespace(
        name="现代汉语", weekday=weekday, start_period=1, end_period=2,
        place="教一楼101", teacher="王老师", weeks="1-16周",
    )
    plan = SimpleNamespace(
        phases=[
            SimpleNamespace(
                name="阶段一",
                tasks=[
                    SimpleNamespace(text="今天到期的事", done=False, due_date=datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)),
                    SimpleNamespace(text="已经逾期的事", done=False, due_date=datetime(2029, 12, 30, 8, 0, tzinfo=timezone.utc)),
                    SimpleNamespace(text="之后才到期的事", done=False, due_date=datetime(2030, 1, 2, 8, 0, tzinfo=timezone.utc)),
                ],
            )
        ]
    )
    payload = {
        "date": target.isoformat(),
        "headline": "先把今天到期的事做完",
        "reading": "这一天有一门课和一件事。",
        "plan": [],
        "watch": "",
    }
    engine = _FakeEngine(payload)
    service = _ai_service(profile=_profile_with(("major", "专业", "汉语言文学", ProfileSource.USER_EDIT)), engine=engine, plan=plan)
    service._academic_records = _FakeAcademicRecords(course)

    frames = [frame async for frame in service.stream("u-ai", "day.advice", "2030-01-01|480")]
    assert "result" in frames[-1]
    context = engine.last.prompt_vars["context_text"]
    assert "不是服务器今天" in context
    assert "今天到期的事" in context and "已经逾期的事" in context
    assert "已逾期 2 天" in context
    assert "之后才到期的事" in context and "不是这一天" in context
    assert "第 1-2 节" in context and "教一楼101" in context

    # 换一个没有课的日期：必须明说"这一天课表没有安排"，不能说课表缺数据
    other = date(2030, 1, 2)
    service._academic_records = _FakeAcademicRecords(course)
    frames = [frame async for frame in service.stream("u-ai", "day.advice", f"{other.isoformat()}|480")]
    context = engine.last.prompt_vars["context_text"]
    assert "这一天课表里没有安排课程" in context
    assert "不代表课表数据缺失" in context


class _FakeAcademicRecords:
    def __init__(self, course) -> None:
        self.course = course

    async def get(self, user_id: str):
        return SimpleNamespace(courses=[self.course], grades=[], imported_at="2030-01-01T00:00:00+00:00")
