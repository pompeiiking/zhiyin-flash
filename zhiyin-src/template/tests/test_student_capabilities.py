from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zipfile import ZipFile
from io import BytesIO

import pytest
from pydantic import ValidationError
from zhiyin_business.services.asset import DefaultAssetService
from zhiyin_business.services.student import StudentService
from zhiyin_infrastructure.local.repository import (
    InMemoryAssetRepository,
    InMemoryNotificationRepository,
    InMemoryAcademicSnapshotRepository,
    InMemoryTaskSessionRepository,
)
from zhiyin_infrastructure.local.student import InMemoryStudentStateRepository
from zhiyin_infrastructure.local.asset_documents import render_asset_document
from zhiyin_kernel.assets import DirectionPlan
from zhiyin_kernel.enums import PlanRole
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_business.contracts.student import (
    TaskEdit,
    PhaseEdit,
    Preferences,
    Semester,
    ReviewEdit,
    NotificationEdit,
    MeasurementBatch,
    Measurement,
    DirectionWeights,
)
from zhiyin_data_sdk.gateways.academic import AcademicSnapshot, CourseEntry


@pytest.fixture
def service():
    state = InMemoryStudentStateRepository()
    assets = InMemoryAssetRepository()
    asset_service = DefaultAssetService(assets, AsyncMock(), None, student_state=state)
    return StudentService(
        state=state,
        assets=assets,
        asset_service=asset_service,
        notifications=InMemoryNotificationRepository(),
        academic=InMemoryAcademicSnapshotRepository(),
        sessions=InMemoryTaskSessionRepository(),
    )


async def phase(service):
    plan = await service.edit_phase("a", PhaseEdit(name="本周"))
    return plan.phases[0].id


@pytest.mark.asyncio
async def test_task_edit_split_state_and_account_isolation(service):
    pid = await phase(service)
    body = TaskEdit(
        text="整理项目",
        phase_id=pid,
        status="in_progress",
        progress=40,
        estimated_minutes=35,
        scheduled_at=datetime.now(timezone.utc),
    )
    plan = await service.edit_task("a", body)
    tid = plan.phases[0].tasks[0].id
    assert plan.phases[0].tasks[0].progress == 40
    with pytest.raises(ResourceNotFound):
        await service.edit_task("b", body, tid)
    split = await service.edit_task(
        "a", TaskEdit(text="整理第一个项目", phase_id=pid, parent_task_id=tid)
    )
    child = split.phases[0].tasks[-1]
    assert child.parent_task_id == tid
    with pytest.raises(InvalidRequest):
        await service.edit_task("a", body.model_copy(update={"parent_task_id": child.id}), tid)
    plan = await service.assets.mark_task_done("a", tid, done=True)
    assert next(t for t in plan.phases[0].tasks if t.id == tid).status == "completed"
    plan = await service.assets.mark_task_done("a", tid, done=False)
    assert next(t for t in plan.phases[0].tasks if t.id == tid).progress == 0


@pytest.mark.asyncio
async def test_phase_cycles_rejected_and_history_is_exact(service):
    first = await phase(service)
    plan = await service.edit_phase("a", PhaseEdit(name="下周", depends_on=[first]))
    second = plan.phases[-1].id
    with pytest.raises(InvalidRequest):
        await service.edit_phase("a", PhaseEdit(name="本周", depends_on=[second]), first)
    old = await service.snapshot("a", "action_plan", 1)
    assert len(old["content"]["phases"]) == 1
    with pytest.raises(ResourceNotFound):
        await service.snapshot("b", "action_plan", 1)
    with pytest.raises(ResourceNotFound):
        await service.snapshot("a", "action_plan", 999)


@pytest.mark.asyncio
async def test_notifications_full_history_snooze_restore(service):
    service.notifications.add("a", {"id": "n1", "title": "任务提醒"})
    later = NotificationEdit(
        status="later", snoozed_until=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    assert (await service.change_notification("a", "n1", later))["status"] == "later"
    assert await service.notifications.list_pending("a") == []
    await service.change_notification("a", "n1", NotificationEdit(status="done"))
    assert (await service.list_notifications("a"))[0]["status"] == "done"
    await service.change_notification("a", "n1", NotificationEdit(status="pending"))
    assert len(await service.notifications.list_pending("a")) == 1
    with pytest.raises(ResourceNotFound):
        await service.change_notification("b", "n1", NotificationEdit(status="done"))
    with pytest.raises(InvalidRequest):
        await service.change_notification(
            "a",
            "n1",
            later.model_copy(
                update={"snoozed_until": datetime.now(timezone.utc) - timedelta(hours=1)}
            ),
        )


@pytest.mark.asyncio
async def test_reviews_apply_and_readback(service):
    pid = await phase(service)
    plan = await service.edit_task("a", TaskEdit(text="任务", phase_id=pid))
    tid = plan.phases[0].tasks[0].id
    review = await service.save_review(
        "a", ReviewEdit(task_id=tid, reason="达到预期", note="已检查成果", result="complete")
    )
    assert not (await service.assets.get_action_plan("a")).phases[0].tasks[0].done
    await service.apply_review("a", review["id"])
    assert (await service.assets.get_action_plan("a")).phases[0].tasks[0].done
    assert (await service.reviews("a"))["reasons"] == {"达到预期": 1}
    assert await service.apply_review("a", review["id"]) == (await service.reviews("a"))["items"][0]
    assert (await service.reviews("b"))["items"] == []


@pytest.mark.asyncio
async def test_preferences_persist_and_actually_gate_analysis(service):
    await service.save_preferences(
        "a", Preferences(proactive_reminders=False, academic_analysis=False)
    )
    assert not await service.can_notify("a")
    assert (await service.preferences("b")).academic_analysis
    assert not (await service.require_analysis_consent("a")).academic_analysis
    await service.require_analysis_consent("b")


@pytest.mark.asyncio
async def test_workload_uses_real_clock_and_overlaps(service):
    pid = await phase(service)
    await service.edit_task(
        "a",
        TaskEdit(
            text="练习",
            phase_id=pid,
            scheduled_at=datetime(2026, 10, 19, 0, 30, tzinfo=timezone.utc),
            estimated_minutes=60,
        ),
    )
    await service.academic.upsert(
        "a",
        AcademicSnapshot(
            courses=[
                CourseEntry(name="数据库", weekday=1, start_period=1, end_period=1, weeks="1-2周")
            ]
        ),
    )
    await service.semester(
        "a",
        Semester(
            first_monday=date(2026, 10, 19),
            periods=[{"number": 1, "start": "08:00", "end": "09:00"}],
            weekly_available_minutes=300,
        ),
    )
    data = await service.workload("a", date(2026, 10, 19))
    assert data["weeks"][0]["course_minutes"] == 60
    assert data["weeks"][0]["task_minutes"] == 60
    assert data["weeks"][0]["remaining_minutes"] == 240
    assert len(data["conflicts"]) == 1


@pytest.mark.asyncio
async def test_weighted_comparison_requires_complete_evidence(service):
    plan = DirectionPlan(
        id="direction",
        role=PlanRole.MAIN,
        name="方向",
        target_desc="目标",
        fit_reason="依据",
        main_risk="风险",
    )
    await service.asset_service.save_direction_plans("a", [plan])
    assert (await service.compare("a"))["plans"][0]["score"] is None
    entries = [
        Measurement(
            key=k,
            label=k,
            value=80,
            source="本人保存的测评结果",
            method="同一量表",
            measured_at=datetime.now(timezone.utc),
        )
        for k in ("major", "jobs", "salary", "stability", "location")
    ]
    await service.save_measurements(
        "a",
        MeasurementBatch(
            asset_type="direction_plan", version=1, subject_id="direction", measurements=entries
        ),
    )
    assert (await service.compare("a"))["plans"][0]["score"] == 0.8
    assert (await service.compare("b"))["plans"] == []
    with pytest.raises(ValidationError):
        DirectionWeights(major=0, jobs=0, salary=0, stability=0, location=0)


@pytest.mark.parametrize(
    "body",
    [
        {"text": "x", "phase_id": "p", "status": "waiting"},
        {"text": "x", "phase_id": "p", "progress": 100},
        {"text": "x", "phase_id": "p", "estimated_minutes": -1},
        {"text": "x", "phase_id": "p", "scheduled_at": "2026-10-19T10:00:00"},
    ],
)
def test_task_validation(body):
    with pytest.raises(ValidationError):
        TaskEdit(**body)


def test_document_export_has_real_content():
    doc = render_asset_document("行动计划", ["完成项目 <复盘> & 归档"], "docx")
    with ZipFile(BytesIO(doc)) as z:
        assert "完成项目 &lt;复盘&gt; &amp; 归档" in z.read("word/document.xml").decode()
    pdf = render_asset_document("行动计划", ["完成项目复盘"], "pdf")
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1000


def test_import_preserves_explicit_period_numbers():
    from zhiyin_infrastructure.academic.parsers import parse_json_courses

    _, courses = parse_json_courses(
        [{"name": "课程", "weekday": 1, "start_period": 1, "end_period": 2, "weeks": "1-16"}]
    )
    assert (courses[0].start_period, courses[0].end_period) == (1, 2)


def test_http_roundtrip_download_and_ownership(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from zhiyin_boot import Settings, build_container, wire_application

    root = Path(__file__).resolve().parents[1]
    container = build_container(
        Settings(
            env="test",
            local_registry_dir=str(root / "data/registry"),
            local_object_dir=str(tmp_path),
            use_remote_llm=True,
            llm_api_key="sk-test",
            llm_base_url="https://example.invalid",
            llm_model="test",
        )
    )

    # Unit boundary: real HTTP/DTO/service/storage, deterministic identity. JWT is covered by the Docker acceptance.
    async def resolve_identity(request):
        return request.headers["Authorization"].removeprefix("Bearer ")

    container.facade.resolve_user_id = resolve_identity
    with TestClient(wire_application(container)) as client:

        def call(method, path, body=None, code=200):
            response = client.request(method, "/api/v1/app" + path, json=body)
            assert response.status_code == code, response.text
            return response.json().get("data")

        client.headers["Authorization"] = "Bearer capability_http"
        plan = call("POST", "/plan/action/phases", {"name": "行动阶段"})
        pid = plan["phases"][0]["id"]
        plan = call(
            "POST",
            "/plan/action/tasks",
            {
                "text": "准备复盘",
                "phase_id": pid,
                "status": "waiting",
                "waiting_reason": "等待反馈",
            },
        )
        tid = plan["phases"][0]["tasks"][0]["task_id"]
        assert plan["next_task"] is None
        assert call("GET", "/plan/action")["phases"][0]["tasks"][0]["status"] == "waiting"
        review = call(
            "POST", "/reviews", {"task_id": tid, "reason": "达到预期", "result": "complete"}
        )
        assert call("POST", f"/reviews/{review['id']}/apply")["applied_at"]
        exported = call("POST", "/assets/export", {"asset_type": "action_plan", "format": "docx"})
        assert exported["available"]
        path = "/api/v1/app/assets/download/" + exported["object_key"]
        response = client.get(path)
        assert response.status_code == 200
        assert "已完成" in ZipFile(BytesIO(response.content)).read("word/document.xml").decode()
        client.headers["Authorization"] = "Bearer capability_other"
        assert client.get(path).status_code == 404
        assert call("GET", "/reviews")["items"] == []
        call("PUT", f"/plan/action/tasks/{tid}", {"text": "越权", "phase_id": pid}, 404)
        call("PUT", "/preferences", {"material_analysis": False})
        from zhiyin_orchestration import AgentResult
        container.ai_task_service._engine = AsyncMock()
        container.ai_task_service._engine.invoke.return_value = AgentResult(
            agent_id="career_advisor", valid=True, structured={"headline": "仍可分析"})
        allowed = client.post("/api/v1/app/brief/today")
        assert allowed.status_code == 200
        assert '"result"' in allowed.text and '"error"' not in allowed.text


@pytest.mark.asyncio
async def test_retry_does_not_replace_newer_session_snapshot(service):
    await service.store_session_snapshot("a", "task", {"guide": "first"}, "one")
    await service.store_session_snapshot("a", "task", {"guide": "second"}, "two")
    await service.store_session_snapshot("a", "task", {"guide": "first"}, "one")
    assert (await service.state.get("a"))["session_snapshots"]["task"]["guide"] == "second"


@pytest.mark.asyncio
async def test_repeated_identical_task_edit_does_not_create_versions(service):
    from zhiyin_kernel.enums import AssetType

    pid = await phase(service)
    body = TaskEdit(text="任务", phase_id=pid)
    plan = await service.edit_task("a", body)
    before = await service.assets.get_latest_version("a", AssetType.ACTION_PLAN)
    await service.edit_task("a", body, plan.phases[0].tasks[0].id)
    after = await service.assets.get_latest_version("a", AssetType.ACTION_PLAN)
    assert before.version == after.version

async def test_reply_snapshots_keep_history_and_reject_other_account(service):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    service.sessions.get = AsyncMock(return_value=SimpleNamespace(user_id='a'))
    first={'messages':[{'role':'agent','agent_id':'x','text':'first','intel_refs':[{'id':'source'}]}]}
    second={'messages':[{'role':'agent','agent_id':'x','text':'second'}]}
    await service.store_session_snapshot('a','task',first,'one')
    await service.store_session_snapshot('a','task',second,'two')
    await service.store_session_snapshot('a','task',{'messages':[]},'one')
    history=await service.conversation_reply_snapshots('a','task')
    assert history['one']==first and history['two']==second
    with pytest.raises(ResourceNotFound):
        await service.conversation_reply_snapshots('b','task')

@pytest.mark.asyncio
async def test_stale_task_edit_does_not_overwrite_newer_fields(service):
    pid = await phase(service)
    original = TaskEdit(text="原任务", phase_id=pid)
    plan = await service.edit_task("a", original)
    tid = plan.phases[0].tasks[0].id
    await service.edit_task("a", TaskEdit(text="甲改标题", phase_id=pid, expected_task=original.model_dump(exclude={"expected_task", "client_request_id"})), tid)
    with pytest.raises(InvalidRequest, match="其他页面更新"):
        await service.edit_task("a", TaskEdit(text="原任务", phase_id=pid, status="waiting", waiting_reason="乙改状态", expected_task=original.model_dump(exclude={"expected_task", "client_request_id"})), tid)
    current = await service.assets.get_action_plan("a")
    assert current.phases[0].tasks[0].text == "甲改标题"
    assert current.phases[0].tasks[0].status == "pending"

@pytest.mark.asyncio
async def test_create_retry_uses_same_identity_without_duplicate_task(service):
    pid = await phase(service)
    body = TaskEdit(text="响应丢失后重试", phase_id=pid, client_request_id="retry-1")
    first = await service.edit_task("a", body)
    second = await service.edit_task("a", body)
    assert len(second.phases[0].tasks) == 1
    assert first.phases[0].tasks[0].id == second.phases[0].tasks[0].id

@pytest.mark.asyncio
async def test_lost_edit_response_can_retry_but_changed_retry_is_rejected(service):
    pid = await phase(service)
    original = TaskEdit(text="原任务", phase_id=pid)
    plan = await service.edit_task("a", original)
    tid = plan.phases[0].tasks[0].id
    edit = TaskEdit(text="新任务", phase_id=pid, expected_task=original.model_dump(exclude={"expected_task", "client_request_id"}))
    await service.edit_task("a", edit, tid)
    replay = await service.edit_task("a", edit, tid)
    assert replay.phases[0].tasks[0].text == "新任务"
    with pytest.raises(InvalidRequest):
        await service.edit_task("a", edit.model_copy(update={"text":"旧页面再次改动"}), tid)

@pytest.mark.asyncio
async def test_changed_creation_retry_does_not_silently_overwrite(service):
    pid = await phase(service)
    body = TaskEdit(text="首次创建", phase_id=pid, client_request_id="same-request")
    await service.edit_task("a", body)
    with pytest.raises(InvalidRequest, match="首次创建已保存"):
        await service.edit_task("a", body.model_copy(update={"text":"重试时改了内容"}))

@pytest.mark.asyncio
async def test_phase_retry_and_stale_edit_preserve_tasks(service):
    body = PhaseEdit(name='原阶段', client_request_id='phase-retry')
    first = await service.edit_phase('a', body)
    pid = first.phases[0].id
    await service.edit_task('a', TaskEdit(text='已有任务', phase_id=pid))
    retried = await service.edit_phase('a', body)
    assert len(retried.phases) == 1
    assert len(retried.phases[0].tasks) == 1
    expected = body.model_dump(exclude={'expected_phase', 'client_request_id'})
    edit = PhaseEdit(name='甲更新阶段', expected_phase=expected)
    await service.edit_phase('a', edit, pid)
    replay = await service.edit_phase('a', edit, pid)
    assert replay.phases[0].name == '甲更新阶段'
    with pytest.raises(InvalidRequest, match='其他页面更新'):
        await service.edit_phase('a', PhaseEdit(name='原阶段', blocking_conditions=['乙输入'], expected_phase=expected), pid)
    current = await service.assets.get_action_plan('a')
    assert current.phases[0].name == '甲更新阶段'
    assert current.phases[0].tasks[0].text == '已有任务'
    with pytest.raises(InvalidRequest, match='首次创建阶段已保存'):
        await service.edit_phase('a', body.model_copy(update={'name':'旧重试'}))


async def test_review_creation_replay_and_changed_retry(service):
    pid = await phase(service)
    plan = await service.edit_task('a', TaskEdit(text='原任务', phase_id=pid))
    body = ReviewEdit(task_id=plan.phases[0].tasks[0].id, reason='时间不足', client_request_id='review-retry')
    first = await service.save_review('a', body)
    assert await service.save_review('a', body) == first
    assert len((await service.reviews('a'))['items']) == 1
    with pytest.raises(InvalidRequest, match='首次复盘已保存'):
        await service.save_review('a', body.model_copy(update={'note': '重试修改'}))


async def test_review_stale_edit_rejected_and_identical_replay_preserves_history(service):
    pid = await phase(service)
    plan = await service.edit_task('a', TaskEdit(text='原任务', phase_id=pid))
    body = ReviewEdit(task_id=plan.phases[0].tasks[0].id, reason='时间不足')
    first = await service.save_review('a', body)
    edit = ReviewEdit(**body.model_dump(exclude={'expected_updated_at', 'note'}), note='甲的新内容', expected_updated_at=first['updated_at'])
    saved = await service.save_review('a', edit, first['id'])
    assert await service.save_review('a', edit, first['id']) == saved
    assert len(saved['history']) == 1
    with pytest.raises(InvalidRequest, match='其他页面更新'):
        await service.save_review('a', edit.model_copy(update={'note': '乙的旧表单'}), first['id'])
    assert (await service.reviews('a'))['items'][0]['note'] == '甲的新内容'


@pytest.mark.parametrize('result', ['complete', 'adjust'])
async def test_review_apply_cannot_overwrite_task_changed_after_review(service, result):
    pid = await phase(service)
    plan = await service.edit_task('a', TaskEdit(text='原任务', phase_id=pid))
    tid = plan.phases[0].tasks[0].id
    review = await service.save_review('a', ReviewEdit(task_id=tid, reason='时间不足', result=result,
        adjustment=TaskEdit(text='复盘中的调整', phase_id=pid) if result == 'adjust' else None))
    await service.edit_task('a', TaskEdit(text='后来更新的任务', phase_id=pid), tid)
    with pytest.raises(InvalidRequest, match='其他页面更新'):
        await service.apply_review('a', review['id'])
    task = (await service.assets.get_action_plan('a')).phases[0].tasks[0]
    assert task.text == '后来更新的任务' and not task.done
    assert not (await service.reviews('a'))['items'][0]['applied_at']
    assert not (await service.state.get('a')).get('review_leases')


async def test_legacy_review_requires_reconfirmation_before_apply(service):
    pid = await phase(service)
    plan = await service.edit_task('a', TaskEdit(text='原任务', phase_id=pid))
    review = await service.save_review('a', ReviewEdit(task_id=plan.phases[0].tasks[0].id, reason='完成', result='complete'))
    def legacy(s):
        s['reviews'][review['id']].pop('task_snapshot')
        return s
    await service.state.update('a', legacy)
    with pytest.raises(InvalidRequest, match='缺少任务原值'):
        await service.apply_review('a', review['id'])
