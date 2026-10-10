"""职业原文、学生证据、推荐采纳与持久任务贯通；不调用付费模型。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from zhiyin_boot import Settings, build_container, wire_application
from zhiyin_business.contracts.ai_tasks import MatchDraft, MatchResult
from zhiyin_business.policies.career_match import ground_match
from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_kernel.enums import AssetType
from zhiyin_orchestration import AgentEngine, AgentResult

SOURCE = {"id": "o-sql", "kind": "occupation", "title": "数据分析师",
          "text": "任职要求：能够使用 SQL 分析数据。需要 Python 编程能力。",
          "source_url": "https://xz.chsi.com.cn/occupation/occudetail.action?id=o-sql",
          "fetched_at": "2026-10-10T09:00:00+00:00"}
DRAFT = {"cells": [{"source_id": "o-sql", "skill": "SQL",
                     "requirement": "能够使用 SQL 分析数据", "student_evidence": ["profile:skills"]},
                    {"source_id": "o-sql", "skill": "Python",
                     "requirement": "需要 Python 编程能力", "student_evidence": ["courses:0"]}]}


def test_evidence_rules_do_not_convert_grades_or_self_reports_to_ability_scores():
    result = ground_match(MatchDraft.model_validate(DRAFT), [SOURCE], {
        "profile:skills": {"text": "自评：使用过 SQL", "kind": "reported"},
        "courses:0": {"text": "Python 程序设计，课程成绩 95", "kind": "studied"},
    })
    assert [cell.status for cell in result.cells] == ["reported", "studied"]
    assert all(cell.need is None and cell.have is None for cell in result.cells)
    assert all(row.fit is None for row in result.ranking)
    assert result.cells[0].source_url == SOURCE["source_url"]
    assert result.actions and "课程只是学习线索" in result.method


def test_fabricated_quotes_sources_and_unrelated_personal_evidence_are_not_used():
    draft = MatchDraft.model_validate({"cells": [
        {"source_id": "fake", "skill": "SQL", "requirement": "能够使用 SQL 分析数据"},
        {"source_id": "o-sql", "skill": "SQL", "requirement": "SQL 必须达到 90 分"},
        DRAFT["cells"][0], DRAFT["cells"][0],
    ]})
    result = ground_match(draft, [SOURCE], {"profile:skills": {"text": "喜欢绘画", "kind": "reported"}})
    assert len(result.cells) == 1 and result.cells[0].status == "unknown"
    assert result.cells[0].student_evidence == []
    assert "待补材料" in result.ranking[0].gap


def test_missing_sources_produce_no_ranking_or_scores():
    result = ground_match(MatchDraft.model_validate(DRAFT), [], {})
    assert result.cells == [] and result.ranking == []
    assert "暂不排序或评分" in result.recommend.body


def test_only_fetch_time_changes_do_not_change_recommendation_identity():
    draft = MatchDraft.model_validate(DRAFT)
    first = ground_match(draft, [SOURCE], {})
    second = ground_match(draft, [{**SOURCE, "fetched_at": "2026-10-10T10:00:00+00:00"}], {})
    assert first.recommendation_id == second.recommendation_id


@pytest.fixture
def wired(tmp_path):
    data = Path(__file__).resolve().parents[1] / "data"
    container = build_container(Settings(use_remote_llm=True, llm_api_key="sk-test", env="test",
        local_data_dir=str(data), local_registry_dir=str(data / "registry"),
        local_knowledge_dir=str(data / "knowledge"), local_object_dir=str(tmp_path)))
    wire_application(container)
    return container


class Engine(AgentEngine):
    def __init__(self):
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        return AgentResult(agent_id=request.agent_id, structured=DRAFT, valid=True)


async def generate(container):
    await container.profile_service.update_field("student", "skills", "使用过 SQL", confidence=.8,
                                                 source="conversation", label="能力自评")
    class Sources:
        async def fetch_external_intel(self, *args, **kwargs):
            return [SimpleNamespace(**SOURCE, model_dump=lambda **kw: dict(SOURCE))]
    engine = Engine()
    container.ai_task_service._engine = engine
    container.ai_task_service._functions = Sources()
    frames = [frame async for frame in container.ai_task_service.stream("student", "match.careers")]
    return MatchResult.model_validate(frames[-1]["result"].data), engine


@pytest.mark.asyncio
async def test_real_sources_and_student_context_reach_matching_then_acceptance_persists(wired):
    result, engine = await generate(wired)
    context = engine.requests[0].prompt_vars["context_text"]
    assert SOURCE["source_url"] in context and "使用过 SQL" in context
    assert engine.requests[0].use_tools is False
    await wired.asset_service.save_action_plan("student", ActionPlan(id="existing", phases=[
        ActionPhase(name="原计划", date_range="本周", tasks=[ActionTask(id="old", text="原任务", done=True)])]))
    view = await wired.facade.accept_career_match("student", result.recommendation_id)
    saved = await wired.asset_service.get_action_plan("student")
    tasks = [task for phase in saved.phases for task in phase.tasks]
    assert view.has_plan and tasks[0].id == "old" and tasks[0].done
    assert [task.text for task in tasks[1:]] == result.actions
    assert all(task.due_date is None for task in tasks[1:])
    assert saved.id == "existing"
    versions = await wired.asset_service.list_versions("student", AssetType.ACTION_PLAN)
    await wired.facade.accept_career_match("student", result.recommendation_id)
    assert await wired.asset_service.get_action_plan("student") == saved
    assert len(await wired.asset_service.list_versions("student", versions[-1].asset_type)) == len(versions)
    with pytest.raises(InvalidRequest):
        await wired.facade.accept_career_match("another-student", result.recommendation_id)
    with pytest.raises(InvalidRequest):
        await wired.facade.accept_career_match("student", "stale-recommendation")


@pytest.mark.asyncio
async def test_academic_change_invalidates_match_and_expired_or_legacy_cache_is_not_used(wired):
    result, _ = await generate(wired)
    cache_key = "match.careers.evidence-v1"
    payload = await wired.ai_task_results.get("student", cache_key)
    payload["meta"]["at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await wired.ai_task_results.put("student", cache_key, payload)
    with pytest.raises(InvalidRequest):
        await wired.ai_task_service.accept_match("student", result.recommendation_id)
    assert await wired.ai_task_service.invalidate_for_event("student", "academic_changed") == 1
    await wired.ai_task_results.put("student", "match.careers", {"data": {"cells": [], "ranking": [{"fit": .9}]}})
    assert await wired.ai_task_service._load_cached("student", cache_key) is None


@pytest.mark.asyncio
async def test_accept_endpoint_returns_saved_task_ids_and_rejects_stale_recommendations(wired, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    result, _ = await generate(wired)
    async def authenticated_student(request):
        return "student"
    monkeypatch.setattr(wired.facade, "resolve_user_id", authenticated_student)
    async with AsyncClient(transport=ASGITransport(app=wire_application(wired)), base_url="http://test") as client:
        response = await client.post(f"/api/v1/app/match/careers/{result.recommendation_id}/accept")
        assert response.status_code == 200
        task_ids = [task["task_id"] for phase in response.json()["data"]["phases"] for task in phase["tasks"]]
        assert task_ids == [f"match_{result.recommendation_id}_{i}" for i in range(len(result.actions))]
        response = await client.post("/api/v1/app/match/careers/obsolete/accept")
        assert response.status_code == 422
