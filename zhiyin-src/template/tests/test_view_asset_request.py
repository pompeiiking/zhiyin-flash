"""“我想看一下我的报告/计划”：没有产物时应直接生成，而不是只回一句去页面看。"""

import pytest

from tests.test_conversation_asset_confirmation import send, setup
from zhiyin_business.ports.orchestrator import IntentType
from zhiyin_business.services.orchestrator import (
    _wants_view_plan,
    _wants_view_report,
)


@pytest.mark.parametrize(
    "message",
    [
        "我想看一下我的诊断报告",
        "打开我的报告",
        "我的报告在哪里",
        "看看评估报告",
    ],
)
def test_view_report_phrases_are_recognized(message):
    assert _wants_view_report(message)


@pytest.mark.parametrize(
    "message",
    ["我想看一下我的计划", "打开阶段计划", "我的行动计划在哪", "看看我的计划"],
)
def test_view_plan_phrases_are_recognized(message):
    assert _wants_view_plan(message)


@pytest.mark.parametrize("message", ["不要打开报告", "先别看看计划"])
def test_view_negation_is_not_recognized(message):
    assert not _wants_view_report(message)
    assert not _wants_view_plan(message)


@pytest.mark.asyncio
async def test_view_missing_report_asks_before_generating():
    c, engine, session = await setup(IntentType.FREE_CHAT)
    await c.profile_service.update_field(
        "u1", "study_year", "大三", confidence=1.0, source="user_edit"
    )
    result = await send(c, session, "我想看一下我的诊断报告")
    # 查看不等于授权生成：没有报告时先问，不先落库、不先进入诊断。
    assert await c.asset_service.get_report("u1") is None
    text = "\n".join(message.text for message in result.messages)
    assert "还没有诊断报告" in text and "生成" in text
