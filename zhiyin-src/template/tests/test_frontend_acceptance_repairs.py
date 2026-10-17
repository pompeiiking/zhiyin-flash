import pytest
from zhiyin_business.policies.routing_rules import RuleStagePolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType
from zhiyin_business.services.orchestrator import _explicit_plan_request, _contains_personal_disclosure
from zhiyin_business.services.academic import DefaultAcademicService
from zhiyin_infrastructure.academic import ManualAcademicImporter
from zhiyin_infrastructure.local.repository import InMemoryAcademicSnapshotRepository
from zhiyin_kernel.enums import LoopStage

@pytest.mark.asyncio
async def test_explicit_diagnosis_and_profile_update_override_current_action_stage():
    policy = RuleStagePolicy()
    board = BlackboardView(user_id='u', current_stage=LoopStage.ACT)
    for message, expected in [
        ('请根据我的画像和经历，帮我做一次个人发展诊断，说明下一步', LoopStage.DIAGNOSE),
        ('补充经历', LoopStage.COLLECT),
        ('我做过两个数据分析项目，也参加过接口测试实习', LoopStage.COLLECT),
    ]:
        result = await policy.decide(blackboard=board, intent=IntentType.HOW_TO_ACT, message=message)
        assert result.stage == expected
        assert result.source == 'intent'

@pytest.mark.parametrize('message,expected', [
    ('做一次个人发展诊断，说明下一步', False),
    ('不要调整计划', False),
    ('暂不生成行动计划', False),
    ('请制定一份计划，但不要覆盖现有计划', False),
    ('请制定一份计划，不要保存', False),
    ('帮我改一下计划', True),
    ('请帮我制定行动计划', True),
    ('现有行动计划需要重新调整', True),
    # 2026-10-18 深度测试：讨论/草案回合曾被静默写成计划（9 项被改成 5 项）。
    ('如果把第一周的任务都改到周末，会有什么影响？先别改，我只是问问', False),
    ('先拟一个调整方案给我看看，别保存', False),
    ('如果现在改计划，会怎样？', False),
    # 反过来，对上一轮草案的明确确认要能识别（原来 false，导致"确认保存"不生效）。
    ('确认按这个安排保存', True),
    ('就按这个方案执行', True),
    ('如果按这个方案改，帮我保存', True),
])
def test_action_plan_requires_affirmative_request(message, expected):
    assert _explicit_plan_request(message) is expected

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
async def test_business_tools_are_bound_to_current_user_and_explicit_task():
    from types import SimpleNamespace
    from agno.run import RunContext
    from zhiyin_boot.module_platform import product_tools
    from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
    from zhiyin_api.dto.asset import ActionPlanView

    class Assets:
        async def get_action_plan(self, user_id):
            assert user_id == 'current-user'
            return ActionPlan(id='p', phases=[ActionPhase(name='第一阶段', date_range='', tasks=[ActionTask(id='t1', text='整理项目经历')])])
    class Facade:
        def __init__(self): self.calls = []
        async def set_action_task_done(self, user_id, body):
            self.calls.append((user_id, body.task_id, body.done))
            return ActionPlanView(has_plan=True)
    facade = Facade()
    container = SimpleNamespace(extra={'modules': {}}, asset_service=Assets(), facade=facade)
    tools = {spec.name: spec.handler for module in product_tools(container) for spec in module.tools}
    action = tools['workspace.task.set_done']
    denied = RunContext(run_id='run', session_id='session', user_id='current-user', dependencies={'user_message': '先看看任务，不要标记完成'})
    assert '"executed": false' in await action(denied, 't1', True)
    assert not facade.calls
    allowed = RunContext(run_id='run', session_id='session', user_id='current-user', dependencies={'user_message': '请把整理项目经历标记为完成'})
    assert '"executed": true' in await action(allowed, 't1', True)
    assert facade.calls == [('current-user', 't1', True)]
    wrong_name = RunContext(run_id='run', session_id='session', user_id='current-user', dependencies={'user_message': '把另一个任务标记为完成'})
    assert '"executed": false' in await action(wrong_name, 't1', True)
    assert len(facade.calls) == 1
    invented_id = RunContext(run_id='run', session_id='session', user_id='current-user', dependencies={'user_message': '请把整理项目经历标记为完成'})
    assert '"executed": true' in await action(invented_id, 'not-a-real-id', True)
    assert facade.calls[-1] == ('current-user', 't1', True)
    class DuplicateAssets:
        async def get_action_plan(self, user_id):
            return ActionPlan(id='p', phases=[ActionPhase(name='阶段', date_range='', tasks=[
                ActionTask(id='t1', text='整理项目经历'), ActionTask(id='t2', text='整理项目经历')])])
    container.asset_service = DuplicateAssets()
    assert '"executed": false' in await action(invented_id, 't1', True)
    assert len(facade.calls) == 2


@pytest.mark.asyncio
async def test_task_title_negation_is_not_treated_as_instruction():
    from types import SimpleNamespace
    from agno.run import RunContext
    from zhiyin_boot.module_platform import product_tools
    from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
    from zhiyin_api.dto.asset import ActionPlanView

    class Assets:
        async def get_action_plan(self, user_id):
            return ActionPlan(id='p', phases=[ActionPhase(name='阶段', date_range='', tasks=[
                ActionTask(id='t1', text='不要忘记核对材料')])])
    class Facade:
        async def set_action_task_done(self, user_id, body):
            return ActionPlanView(has_plan=True)
    container = SimpleNamespace(extra={'modules': {}}, asset_service=Assets(), facade=Facade())
    action = next(spec.handler for module in product_tools(container) for spec in module.tools
                  if spec.name == 'workspace.task.set_done')
    ctx = RunContext(run_id='r', session_id='s', user_id='u',
                     dependencies={'user_message': '请把不要忘记核对材料标记为完成'})
    assert '"executed": true' in await action(ctx, 't1', True)


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
async def test_failed_model_contract_shows_server_read_receipt():
    from tests.e2e.test_main_path import _container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_orchestration import AgentResult

    class ReadEngine:
        async def invoke(self, request):
            return AgentResult(agent_id=request.agent_id, valid=False,
                business_tool_calls=["workspace.read"],
                business_read_receipts=[{"area": "academic", "text": "成绩记录：\n数据库：79（第二学期）"}])

    container = _container()
    container.orchestrator._agent_engine = ReadEngine()
    session = await container.orchestrator.enter_task("u1", "free_chat")
    result = await container.orchestrator.handle_message(
        TurnRequest(user_id="u1", task_id=session.id, message="请查询我的成绩"))
    assert "数据库：79（第二学期）" in result.messages[0].text

@pytest.mark.asyncio
async def test_mixed_diagnosis_collects_only_facts_quoted_from_current_turn():
    from tests.e2e.test_main_path import _container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_orchestration import AgentResult

    class MixedEngine:
        def __init__(self): self.calls = []
        async def invoke(self, request):
            self.calls.append((request.agent_id, request.use_tools))
            if request.agent_id == "profile_analyst" and request.stage == "collect":
                return AgentResult(agent_id=request.agent_id, valid=True, structured={"field_updates": [
                    {"key": "major", "label": "专业", "value": "计算机", "confidence": 0.9, "source": "conversation", "evidence": ["我的专业是计算机"]},
                    {"key": "experience", "label": "经历", "value": "编造的经历", "confidence": 0.8, "source": "conversation", "evidence": ["并非本轮原话"]},
                ]})
            return AgentResult(agent_id=request.agent_id, valid=False)
    container = _container()
    engine = MixedEngine()
    container.orchestrator._agent_engine = engine
    from zhiyin_kernel.blackboard import ProfileGap
    await container.profile_service.replace_gaps("u1", [
        ProfileGap(key="major", label="专业", reason="缺少", suggested_next_action="补充"),
        ProfileGap(key="experience", label="经历", reason="缺少", suggested_next_action="补充"),
    ])
    session = await container.orchestrator.enter_task("u1", "free_chat")
    await container.orchestrator.handle_message(TurnRequest(
        user_id="u1", task_id=session.id, message="我的专业是计算机，请帮我做一次诊断。"))
    profile = await container.profile_service.get("u1")
    fields = {item.key: item.value for item in profile.fields}
    assert fields["major"] == "计算机"
    assert "experience" not in fields
    assert [gap.key for gap in await container.profile_service.get_gaps("u1")] == ["experience"]
    assert ("profile_analyst", False) in engine.calls

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

@pytest.mark.parametrize("message, expected", [
    ("我做过一个项目，请帮我诊断", True),
    ("我的专业是软件工程，请帮我诊断", True),
    ("我做过一个项目，不要记录到画像", False),
    ("请读取我的画像", False),
])
def test_disclosure_detection_respects_explicit_no_record(message, expected):
    assert _contains_personal_disclosure(message) is expected

@pytest.mark.asyncio
async def test_explicit_do_not_record_blocks_collector_write():
    from tests.e2e.test_main_path import _container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_orchestration import AgentResult

    class CollectEngine:
        async def invoke(self, request):
            return AgentResult(agent_id=request.agent_id, valid=True, structured={"field_updates": [
                {"key": "experience", "label": "经历", "value": "做过项目", "confidence": 0.9, "source": "conversation", "evidence": ["我做过项目"]}]})
    container = _container()
    container.orchestrator._agent_engine = CollectEngine()
    session = await container.orchestrator.enter_task("u1", "free_chat")
    await container.orchestrator.handle_message(TurnRequest(
        user_id="u1", task_id=session.id, message="我做过项目，不要记录到画像。"))
    profile = await container.profile_service.get("u1")
    assert not profile or all(item.key != "experience" for item in profile.fields)
