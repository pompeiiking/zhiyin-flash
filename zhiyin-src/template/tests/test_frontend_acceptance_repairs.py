import pytest
from zhiyin_business.services.academic import DefaultAcademicService
from zhiyin_infrastructure.academic import ManualAcademicImporter
from zhiyin_infrastructure.local.repository import InMemoryAcademicSnapshotRepository



@pytest.mark.asyncio
async def test_grade_term_survives_later_course_import():
    service = DefaultAcademicService(InMemoryAcademicSnapshotRepository(), ManualAcademicImporter())
    await service.import_('u', grades_raw='课程名称\t成绩\t学分\n数据结构\t90\t4', term='2025-2026第二学期')
    await service.import_('u', courses_raw='课程名称\t星期\t开始节次\t结束节次\n数据库\t1\t1\t2', term='2026-2027第一学期')
    snapshot = await service.get('u')
    assert snapshot.term == '2026-2027第一学期'
    assert snapshot.grades[0].term == '2025-2026第二学期'

@pytest.mark.asyncio
async def test_missing_grade_term_does_not_inherit_course_term():
    service = DefaultAcademicService(InMemoryAcademicSnapshotRepository(), ManualAcademicImporter())
    await service.import_('u', courses_raw='课程名称\t星期\t开始节次\t结束节次\n数据库\t1\t1\t2', term='课表学期')
    await service.import_('u', grades_raw='课程名称\t成绩\t学分\n数据结构\t90\t4')
    assert (await service.get('u')).grades[0].term == ''






@pytest.mark.asyncio
async def test_review_achievement_reflects_saved_reviews_without_applying():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from zhiyin_api.facade.application import DefaultApplicationFacade
    from zhiyin_kernel.assets import Achievement

    badge = Achievement(id="review", user_id="u", badge_key="first_review")
    function = SimpleNamespace(list_achievements=AsyncMock(return_value=[badge]))
    student = SimpleNamespace(reviews=AsyncMock(return_value={"items": [
        {"updated_at": "2026-10-17T08:00:00+00:00", "history": []}
    ]}))
    facade = SimpleNamespace(_function=function, _student=student)
    result = await DefaultApplicationFacade.list_achievements(facade, "u")
    assert result.unlocked == 1
    assert result.items[0].unlocked
    assert result.items[0].unlocked_at.isoformat() == "2026-10-17T08:00:00+00:00"
    assert (await DefaultApplicationFacade.list_achievements(facade, "u")).unlocked == 1

@pytest.mark.asyncio
async def test_business_read_receipt_uses_real_grade_records():
    from types import SimpleNamespace
    from agno.run import RunContext
    from zhiyin_boot.module_platform import product_tools
    from zhiyin_data_sdk.gateways.academic import AcademicSnapshot, GradeEntry

    class Academic:
        async def get(self, user_id):
            assert user_id == "current-user"
            return AcademicSnapshot(grades=[GradeEntry(name="数据库", score="79", term="第二学期")])
    async def unused(*args):
        return None
    service = SimpleNamespace(get=unused, get_action_plan=unused, list_direction_plans=unused,
        list_calendar_nodes=unused, list_by_user=unused, reviews=unused, list_achievements=unused)
    container = SimpleNamespace(extra={"modules": {}}, profile_service=service, academic_service=Academic(),
        asset_service=service, function_service=service, note_service=service, student_service=service)
    read = next(spec.handler for module in product_tools(container) for spec in module.tools if spec.name == "workspace.read")
    ctx = RunContext(run_id="run", session_id="session", user_id="current-user", dependencies={})
    await read(ctx, "academic")
    assert ctx.dependencies["business_read_receipts"] == [{"area": "academic", "text": "成绩记录：\n数据库：79（第二学期）"}]



@pytest.mark.asyncio
async def test_prompt_seed_never_overwrites_existing_prompt():
    import json
    from pathlib import Path
    from unittest.mock import AsyncMock
    from zhiyin_infrastructure.postgres.registry import PostgresRegistryRepository

    database = AsyncMock()
    repo = PostgresRegistryRepository(database, Path("data/registry"))
    items = json.loads(Path("data/registry/prompts.json").read_text(encoding="utf-8"))["items"]
    for code in ("task.academic.analysis", "disclosure.field_kept_by_user"):
        item = next(item for item in items if item["code"] == code)
        await repo._insert_missing_prompt(item)
    assert database.execute.await_count == 2
    assert all("ON CONFLICT (code) DO NOTHING" in call.args[0] for call in database.execute.await_args_list)
