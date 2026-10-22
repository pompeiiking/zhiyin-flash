"""2026-10-22 外部验收五项（#35 / #38 / #39 / #40 / #41）的回归守卫。

这些用例刻意走真实对话动作/采集策略，而不是只测一个纯函数：
问题都发生在「服务端认为成功、用户看到的东西却不对」的边界上。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.test_profile_write_path import _setup, _send, _profile_action
from zhiyin_business.policies.collection import plan_collection
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_kernel import profile_taxonomy as taxonomy
from zhiyin_kernel.blackboard import Profile, ProfileField
from zhiyin_kernel.enums import ProfileSource, ProfileVerification
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound


@pytest.mark.asyncio
async def test_unknown_task_id_is_rejected_and_never_creates_a_session():
    c, s = await _setup(lambda rt: None)
    with pytest.raises(ResourceNotFound) as error:
        await c.orchestrator.handle_message(TurnRequest(
            user_id="u1", task_id="task-ghost-abc", message="你好"))
    assert "重新进入" in str(error.value)
    sessions = await c.orchestrator._sessions.list_by_user("u1")
    assert all(item.id != "task-ghost-abc" for item in sessions)


@pytest.mark.asyncio
async def test_cross_field_supersede_is_rejected_and_old_proposal_survives():
    captured: dict[str, object] = {}

    async def callback(rt):
        first = await rt.action({
            "operation": "profile.update",
            "payload": {"key": "school", "value": "重庆工商大学",
                        "assertion_type": "affirmative_self_statement"},
            "authorization": "proposal",
            "evidence": "学校是重庆工商大学",
        })
        captured["first"] = first
        with pytest.raises(InvalidRequest) as error:
            await rt.action({
                "operation": "profile.update",
                "payload": {"key": "major", "value": "市场营销",
                            "assertion_type": "affirmative_self_statement"},
                "authorization": "proposal",
                "evidence": "专业是市场营销",
                "supersedes_action_id": first["action_id"],
            })
        captured["error"] = str(error.value)

    c, s = await _setup(callback)
    await _send(c, s, "学校是重庆工商大学，专业是市场营销")
    assert "同一字段" in str(captured["error"])
    first = captured["first"]
    from zhiyin_business.services.conversation_ledger import ConversationLedger
    record = await ConversationLedger(c.student_state).read("u1", s.id)
    # 账本里第一条提案仍是可确认状态，没有被跨字段取代。
    assert record["actions"][first["action_id"]]["state"] == "proposed"


@pytest.mark.asyncio
async def test_automatic_batch_profile_writes_do_not_invalidate_each_other():
    """同一轮里写多个不同字段：第一条写入不能把同轮其他字段判成「数据已变化」。"""
    message = "我在重庆工商大学读市场营销，学制四年。"

    async def callback(rt):
        for key, value in (("school", "重庆工商大学"), ("major", "市场营销"), ("duration", "四年")):
            await rt.action(_profile_action({"key": key, "value": value}, evidence=message))

    c, s = await _setup(callback)
    await _send(c, s, message)
    fields = {field.key: field for field in await c.profile_service.get_fields("u1")}
    assert fields["school"].value == "重庆工商大学"
    assert fields["major"].value == "市场营销"
    assert fields["duration"].value == "四年"


@pytest.mark.asyncio
async def test_meta_commentary_report_is_rejected_before_saving_a_version():
    captured: dict[str, str] = {}

    async def callback(rt):
        try:
            await rt.action({
                "operation": "report.save",
                "payload": {"verdict": {"title": "本报告说明", "summary": "本轮更新的是依据，不是结论"}, "swot": {}},
                "authorization": "explicit",
                "evidence": "生成报告",
            })
        except InvalidRequest as error:
            captured["error"] = str(error)

    c, s = await _setup(callback)
    await _send(c, s, "生成报告")
    assert "不是对用户的诊断结论" in captured.get("error", "")
    assert await c.asset_service.get_report("u1") is None


@pytest.mark.asyncio
async def test_valid_report_still_saves_a_draft():
    async def callback(rt):
        await rt.action({
            "operation": "report.save",
            "payload": {
                "verdict": {"title": "方向未收敛，先验证内容与执行能力",
                            "summary": "市场营销大三在读，经历偏内容与执行，建议先用一段真实项目验证方向。"},
                "swot": {},
            },
            "authorization": "explicit",
            "evidence": "生成报告",
        })

    c, s = await _setup(callback)
    await _send(c, s, "生成报告")
    report = await c.asset_service.get_report("u1")
    assert report is not None and report.verdict.title.startswith("方向未收敛")


def test_conversation_value_on_authoritative_field_is_unverified_not_missing():
    now = datetime.now(timezone.utc)
    profile = Profile(id="p1", user_id="u1", updated_at=now, fields=[
        ProfileField(key="major", value="市场营销", confidence=0.9, source=ProfileSource.CONVERSATION,
                     updated_at=now, verification=ProfileVerification.SELF_REPORTED),
    ])
    plan = plan_collection(profile)
    step = next(item for item in plan.steps if item.key == "major")
    assert step.got is False
    assert step.state == "unverified"
    assert step.value == "市场营销"
    assert step.confirmable is True
    assert step.status_text
    assert plan.unverified == 1


@pytest.mark.asyncio
async def test_interest_split_negative_items_and_deduplicates_same_concept():
    message = "我更喜欢写东西和研究人为什么买，不太喜欢天天应酬；不想做销售。"

    async def callback(rt):
        await rt.action(_profile_action({
            "key": "interest",
            "value": ["写东西", "研究人为什么买", "天天应酬", "应酬"],
            "attributes": {"items": [
                {"value": "写东西", "polarity": "like"},
                {"value": "研究人为什么买", "polarity": "like"},
                {"value": "天天应酬", "polarity": "dislike"},
                {"value": "应酬", "polarity": "dislike"},
            ]},
        }, evidence=message))

    c, s = await _setup(callback)
    await _send(c, s, message)
    field = (await c.profile_service.get_fields("u1", ["interest"]))[0]
    assert field.value == ["写东西", "研究人为什么买"]
    dislikes = [item for item in field.attributes["items"] if item["polarity"] == "dislike"]
    assert [item["value"] for item in dislikes] == ["天天应酬"]
    # 纯函数口径也钉住：否定项永远不会回到兴趣的可见值里。
    values, _, _ = taxonomy.merge_preferences(
        "interest", None, ["写东西", "天天应酬"], {"items": [
            {"value": "写东西", "polarity": "like"}, {"value": "天天应酬", "polarity": "dislike"}]})
    assert values == ["写东西"]
