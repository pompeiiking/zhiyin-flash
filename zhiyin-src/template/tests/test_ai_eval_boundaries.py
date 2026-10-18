"""AI 评测脚手架：用 fake engine 离线覆盖边界与安全兜底（B6）。

原则：**不调真实模型**。每个用例给 `AgentEngine.invoke` 一个受控的结构化返回，
断言的是"系统在边界上的行为"（提示词里给了什么约束、产出被清洗/降级成什么、
不该写的时候有没有写），而不是模型文笔好不好。

覆盖的边界（与深度测试/历史缺陷对应）：
假设句、否定指令、无来源、资料范围受限、任务完成假成功、讨论不写计划、
来源虚构、内部口吻、契约半成品、未来到期不能算今天、无课不能称课表缺失。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from zhiyin_business.contracts.ai_tasks import PortraitAnalysis, ReportSummary
from zhiyin_business.services.ai_tasks import AiTaskService
from zhiyin_data_sdk.errors import MissingConfigError
from zhiyin_kernel.blackboard import Profile
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.registry import AgentDescriptor


# ---------------------------------------------------------------------------
# 0. 意图判定（纯函数，不经过模型）：假设句 / 否定 / 完成与恢复 / 报告
# ---------------------------------------------------------------------------


def _orchestrator():
    from zhiyin_business.services import orchestrator

    return orchestrator


def test_hypothetical_question_is_not_an_instruction_to_change_plan() -> None:
    o = _orchestrator()
    assert o._explicit_plan_request("假如把任务都改到周末，会有什么影响？") is False


def test_hypothetical_with_confirm_words_is_still_discussion() -> None:
    o = _orchestrator()
    assert o._explicit_plan_request("如果按这个方案改，会有什么影响") is False


def test_explicit_confirmation_wins_over_hypothetical() -> None:
    o = _orchestrator()
    assert o._explicit_plan_request("如果按这个方案改，确认保存") is True
    assert o._explicit_plan_request("确认按这个安排保存") is True


def test_negation_and_discussion_do_not_write_plan() -> None:
    o = _orchestrator()
    assert o._explicit_plan_request("先别改，我只是问问") is False
    assert o._explicit_plan_request("不要保存计划，先讨论一下") is False
    assert o._explicit_plan_request("看看我的计划") is False
    assert o._wants_view_plan("看看我的计划") is True


def test_negated_profile_write_is_not_a_disclosure() -> None:
    o = _orchestrator()
    assert o._forbids_profile_write("不要把我的经历保存到画像") is True
    assert o._contains_personal_disclosure("不要保存到画像，我只是说说我做过短视频") is False
    assert o._contains_personal_disclosure("我之前做过两个短视频账号") is True


def test_task_done_and_restore_intent() -> None:
    o = _orchestrator()
    assert o._task_operation_intent("第二项做完了") is True
    assert o._task_operation_intent("刚才点错了，撤销完成") is False
    assert o._task_operation_intent("在吗") is None


def test_report_negation_does_not_generate() -> None:
    o = _orchestrator()
    assert o._explicit_report_request("先不要生成报告") is False
    assert o._explicit_report_request("生成一份诊断报告") is True


def test_field_updates_require_evidence_from_this_turn() -> None:
    o = _orchestrator()
    message = "我做过一个校园二手平台，用 Python 写的"
    structured = {
        "field_updates": [
            {"key": "internship", "value": "校园二手平台", "evidence": ["用 Python 写的"]},
            {"key": "major", "value": "计算机", "evidence": ["我在985读计算机"]},  # 本轮没说 → 丢弃
        ]
    }
    result = o._direct_field_updates(structured, message)
    assert [item["key"] for item in result["field_updates"]] == ["internship"]


# ---------------------------------------------------------------------------
# fake engine / fake 依赖
# ---------------------------------------------------------------------------


class _FakeEngine:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.last = None
        self.calls = 0

    async def invoke(self, request):
        self.last = request
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return SimpleNamespace(valid=True, structured=self.payload, errors=[])


class _InvalidEngine(_FakeEngine):
    async def invoke(self, request):
        self.last = request
        self.calls += 1
        return SimpleNamespace(valid=False, structured=None, errors=["missing headline"])


class _FakeRegistry:
    async def get_agent(self, agent_id: str):
        return AgentDescriptor(id=agent_id, name="职业顾问")

    async def list_task_progress(self):
        return []


class _FakeProfiles:
    def __init__(self, profile) -> None:
        self.profile = profile

    async def get(self, user_id: str):
        return self.profile


class _FakeBehaviors:
    async def recent(self, user_id: str, limit: int = 5):
        return []


class _FakeAssets:
    def __init__(self, *, plan=None, directions=None) -> None:
        self.plan = plan
        self.directions = directions or []

    async def get_action_plan(self, user_id: str):
        return self.plan

    async def list_direction_plans(self, user_id: str):
        return self.directions

    async def get_report(self, user_id: str):
        return None


class _FakeState:
    def __init__(self, data: dict) -> None:
        self.data = data

    async def get(self, user_id: str):
        return self.data


class _FakeAcademic:
    def __init__(self, courses=(), grades=()) -> None:
        self.courses = list(courses)
        self.grades = list(grades)

    async def get(self, user_id: str):
        return SimpleNamespace(courses=self.courses, grades=self.grades, imported_at="2030-01-01T00:00:00+00:00")


def _profile(*fields) -> Profile:
    now = datetime.now(timezone.utc)
    return Profile(
        id="p1",
        user_id="u-eval",
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


def _service(*, engine, profile=None, plan=None, directions=None, academic=None, student_state=None) -> AiTaskService:
    return AiTaskService(
        profiles=_FakeProfiles(profile),
        behaviors=_FakeBehaviors(),
        assets=_FakeAssets(plan=plan, directions=directions),
        academic_records=academic,
        engine=engine,
        registry=_FakeRegistry(),
        student_state=student_state,
        results=None,
    )


async def _run(service: AiTaskService, key: str, arg: str = "") -> dict:
    frames = [frame async for frame in service.stream("u-eval", key, arg)]
    assert frames, "没有任何帧"
    return frames[-1]


# ---------------------------------------------------------------------------
# 1. 来源虚构 / 内部口吻（画像分析、报告导读）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portrait_does_not_invent_chsi_source_when_records_are_unverified() -> None:
    profile = _profile(("major", "专业", "汉语言文学", ProfileSource.CONVERSATION))
    engine = _FakeEngine({
        "headline": "你还在了解阶段",
        "reading": "学信网和对话记录显示你偏好短视频。",
        "strengths": [], "watchouts": [],
        "next": [{"label": "问一句：问他有没有做过完整项目", "why": "先确认经历"}],
    })
    result = await _run(_service(engine=engine, profile=profile), "portrait.analysis")
    data = result["result"].data
    assert "学信网" not in data.reading
    assert "你提供的资料显示" in data.reading
    assert "问一句" not in data.next[0].label and "问他" not in data.next[0].label
    context = engine.last.prompt_vars["context_text"]
    assert "没有**已核验" in context or "不得说" in context


@pytest.mark.asyncio
async def test_empty_profile_refuses_to_fabricate_an_analysis() -> None:
    with pytest.raises(Exception) as caught:
        await _run(_service(engine=_FakeEngine({}), profile=None), "portrait.analysis")
    assert "空" in str(caught.value)


@pytest.mark.asyncio
async def test_report_moves_are_cleaned_to_student_second_person() -> None:
    engine = _FakeEngine({
        "headline": "先把卡点拆开",
        "paragraphs": ["学信网显示你基础不错。"],
        "moves": [{"label": "问一句：问他这周先做哪件", "why": "让他自己定"}],
    })
    profile = _profile(("major", "专业", "汉语言文学", ProfileSource.CONVERSATION))
    result = await _run(_service(engine=engine, profile=profile), "report.summary")
    data = result["result"].data
    assert isinstance(data, ReportSummary)
    assert "学信网" not in data.paragraphs[0]
    assert "问一句" not in data.moves[0].label and "问他" not in data.moves[0].label
    assert "让他" not in data.moves[0].why


# ---------------------------------------------------------------------------
# 2. 契约边界：半成品不许放行 / 无依据分数被清空
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_half_baked_contract_is_rejected_not_shown() -> None:
    with pytest.raises(MissingConfigError):
        await _run(_service(engine=_InvalidEngine({}), profile=_profile(("major", "专业", "中文", ProfileSource.USER_EDIT))), "portrait.analysis")


@pytest.mark.asyncio
async def test_dimension_never_presents_invented_scores() -> None:
    field = {
        "key": "interest", "label": "兴趣", "value": "短视频", "confidence": 0.8,
        "source": ProfileSource.CONVERSATION, "updated_at": datetime.now(timezone.utc),
    }
    profile = Profile(id="p", user_id="u-eval", updated_at=datetime.now(timezone.utc), fields=[field])
    engine = _FakeEngine({
        "id": "interest", "name": "兴趣", "conclusion": "偏好短视频",
        "reading": "你说过喜欢搞笑段子", "score": 0.93, "delta": 0.2, "trend": [{"at": "x", "v": 0.9}],
        "next": "", "bench": 0.8,
    })
    result = await _run(_service(engine=engine, profile=profile), "dim", "interest")
    data = result["result"].data
    assert data.score is None and data.bench is None and data.delta is None
    assert data.trend == []


# ---------------------------------------------------------------------------
# 3. 当日建议：未来到期不能算今天 / 无课不能称课表缺失
# ---------------------------------------------------------------------------


def _course_for(target: date) -> SimpleNamespace:
    return SimpleNamespace(
        name="现代汉语", weekday=target.isoweekday(), start_period=1, end_period=2,
        place="教一楼101", teacher="王老师", weeks="1-16周",
    )


@pytest.mark.asyncio
async def test_day_advice_future_due_is_not_reported_as_today() -> None:
    target = date(2030, 5, 8)
    plan = SimpleNamespace(phases=[SimpleNamespace(name="阶段一", tasks=[
        SimpleNamespace(text="今天到期的事", done=False, due_date=datetime(2030, 5, 8, 8, 0, tzinfo=timezone.utc)),
        SimpleNamespace(text="已经逾期的事", done=False, due_date=datetime(2030, 5, 5, 8, 0, tzinfo=timezone.utc)),
        SimpleNamespace(text="以后才到期的事", done=False, due_date=datetime(2030, 5, 10, 8, 0, tzinfo=timezone.utc)),
    ])])
    engine = _FakeEngine({"date": target.isoformat(), "headline": "h", "reading": "r", "plan": [], "watch": ""})
    service = _service(engine=engine, plan=plan, profile=_profile(("major", "专业", "汉语言文学", ProfileSource.USER_EDIT)))
    service._academic_records = _FakeAcademic(courses=[_course_for(target)])
    result = await _run(service, "day.advice", f"{target.isoformat()}|480")
    assert "result" in result
    context = engine.last.prompt_vars["context_text"]
    assert "今天到期的事" in context
    assert "已经逾期的事" in context and "已逾期 3 天" in context
    assert "以后才到期的事" in context and "不是这一天" in context
    assert "第 1-2 节" in context and "教一楼101" in context
    assert "不是服务器今天" in context  # 2030 年不是今天的测试语义


@pytest.mark.asyncio
async def test_day_advice_no_course_day_does_not_claim_missing_timetable() -> None:
    target = date(2030, 5, 8)
    engine = _FakeEngine({"date": target.isoformat(), "headline": "h", "reading": "r", "plan": [], "watch": ""})
    service = _service(engine=engine)
    service._academic_records = _FakeAcademic(courses=[])  # 这一天没有课
    await _run(service, "day.advice", f"{target.isoformat()}|480")
    context = engine.last.prompt_vars["context_text"]
    assert "这一天课表里没有安排课程" in context
    assert "不代表课表数据缺失" in context


# ---------------------------------------------------------------------------
# 4. 资料范围：受限时给模型的上下文必须带"只用允许的事实"这一条
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restricted_scope_prepends_guard_text_to_the_model_context() -> None:
    engine = _FakeEngine({
        "headline": "先把一件小事做完", "because": [], "next": [], "changed": [], "ifYouSkip": "",
    })
    state = _FakeState({"preferences": {"material_analysis": False, "academic_analysis": True}})
    service = _service(engine=engine, profile=_profile(("major", "专业", "汉语言文学", ProfileSource.CONVERSATION)), student_state=state)
    await _run(service, "brief.today")
    context = engine.last.prompt_vars["context_text"]
    assert "按资料偏好" in context and "仅使用以下允许的事实" in context


# ---------------------------------------------------------------------------
# 5. 任务完成"假成功"：简报里待办/目标只能当意向，不能当已完成成果
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brief_context_marks_todos_as_intent_not_achievement() -> None:
    from zhiyin_kernel.assets import ActionPhase, ActionPlan, ActionTask

    plan = ActionPlan(id="p", phases=[ActionPhase(name="准备", date_range="", tasks=[ActionTask(id="t", text="整理项目", done=False)])])
    engine = _FakeEngine({
        "headline": "先把项目推进", "because": [], "next": [], "changed": [], "ifYouSkip": "",
    })
    service = _service(engine=engine, plan=plan, profile=_profile(("major", "专业", "汉语言文学", ProfileSource.CONVERSATION)))
    await _run(service, "brief.today")
    context = engine.last.prompt_vars["context_text"]
    assert "待办、目标是用户意向" in context
    assert "不能据此推断能力" in context


# ---------------------------------------------------------------------------
# 6. 匹配：没有成绩时不编分数、不编岗位要求
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_career_match_without_grades_says_it_is_missing_instead_of_inventing() -> None:
    engine = _FakeEngine({
        "cells": [], "ranking": [],
        "recommend": {"title": "资料还不够做匹配", "body": "先补成绩单与目标岗位要求", "because": []},
    })
    service = _service(engine=engine, academic=_FakeAcademic(courses=[], grades=[]))
    await _run(service, "match.careers")
    context = engine.last.prompt_vars["context_text"]
    # 没有成绩就不该出现任何成绩行；引用里要能看出"未导入"
    assert "他修过的课" not in context and "他的成绩" not in context
