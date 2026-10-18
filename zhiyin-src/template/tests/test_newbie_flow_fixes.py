"""2026-10-17 新人全流程测试里修掉的三类问题，各留一条回归。

1. 采集门槛不能被"回答式 intent"永久挡住（用户在答问题，不是要求回到采集）；
2. 资产创建提议要在同一会话里保留，不因中间插一句别的话而消失；
3. 图片/二进制材料必须在上传阶段明确拒绝，不能"成功"后给模型一串乱码。
"""

from unittest.mock import AsyncMock

import pytest

from tests.test_conversation_asset_confirmation import Engine, send, setup
from zhiyin_business.policies.collection_gate import CollectionGate
from zhiyin_business.policies.routing import IntentDecision
from zhiyin_business.policies.routing_rules import RuleStagePolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType
from zhiyin_business.contracts.diagnose import DiagnoseOutput
from zhiyin_business.services.orchestrator import _ASSET_OFFERS, _repair_diagnose_evidence
from zhiyin_data_sdk.gateways.documents import DocumentReadError
from zhiyin_infrastructure.textfile import LocalTextExtractor
from zhiyin_kernel.enums import LoopStage


@pytest.mark.asyncio
async def test_answer_style_intent_allows_collection_gate_to_advance():
    """「我做过…」是回答，不是要求留在采集：门槛必须仍然能推进。

    如果没有这个标记，采集门槛的 `source != "intent"` 会把这句回答当成
    "用户要留在采集"，于是新手连续答 30+ 轮也进不了诊断。
    """
    policy = RuleStagePolicy()
    board = BlackboardView(user_id="u", current_stage=LoopStage.COLLECT)
    decision = await policy.decide(
        blackboard=board,
        intent=IntentType.FREE_CHAT,
        message="我做过两个数据分析项目，也参加过接口测试实习",
    )
    assert decision.stage is LoopStage.COLLECT
    assert decision.source == "intent"
    assert decision.allow_gate_advance is True


@pytest.mark.asyncio
async def test_explicit_confused_still_keeps_user_in_collect():
    """用户明确说"我不清楚自己适合什么"时，门槛不许把他顶去诊断。"""
    policy = RuleStagePolicy()
    board = BlackboardView(user_id="u", current_stage=LoopStage.DIAGNOSE)
    decision = await policy.decide(
        blackboard=board,
        intent=IntentType.CONFUSED,
        message="我还是不清楚自己适合什么",
    )
    # 这条判定不是"回答式 intent"，因此不允许采集门槛顶掉它。
    assert decision.allow_gate_advance is False


@pytest.mark.asyncio
async def test_pending_offer_expires_after_unrelated_message_in_same_session():
    """换话题后的“可以”不构成对旧报告提议的授权。"""
    c, _, session = await setup(ready=True)
    first = await send(c, session, "聊聊我的情况")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["report"])
    # 中间插一句与确认无关的话：旧实现会把"上一条主理消息"顶掉，提议随之消失
    await send(c, session, "今天我有点累，先随便聊聊")
    assert await c.asset_service.get_report("u1") is None
    result = await send(c, session, "可以")
    assert await c.asset_service.get_report("u1") is None
    assert "诊断报告已生成" not in result.messages[0].text


@pytest.mark.asyncio
async def test_pending_report_offer_accepts_explicit_report_request():
    """用户直接说「帮我生成诊断报告」也算确认，不必先猜中「可以」。"""
    c, _, session = await setup(ready=True)
    first = await send(c, session, "聊聊我的情况")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["report"])
    result = await send(c, session, "帮我生成一份诊断报告吧")
    assert await c.asset_service.get_report("u1") is not None
    assert "诊断报告已生成" in result.messages[0].text


@pytest.mark.asyncio
async def test_offer_is_not_confirmed_in_another_session():
    """另一条会话里说「可以」仍不构成授权（提议按会话绑定）。"""
    c, _, session = await setup(ready=True)
    first = await send(c, session, "聊聊我的情况")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["report"])
    other = await c.orchestrator.enter_task("u1", "confused")
    await send(c, other, "可以")
    assert await c.asset_service.get_report("u1") is None


@pytest.mark.asyncio
async def test_collection_gate_advances_on_answer_after_gate_ready():
    """门槛已过 + 用户只是在回答问题 → 本轮应进入下一环节。"""
    c, _, session = await setup(IntentType.FREE_CHAT, ready=True)
    # 让策略判定成"回答式 intent"，且门槛 ready
    c.orchestrator._intent_policy.classify_with_decision = AsyncMock(
        return_value=IntentDecision(intent=IntentType.FREE_CHAT)
    )
    c.orchestrator.collection_gate = AsyncMock(
        return_value=CollectionGate(True, 1.0, 0.8, ())
    )
    result = await send(c, session, "我之前做过两个小项目，也参加过实习")
    assert result.stage is not LoopStage.COLLECT


@pytest.mark.asyncio
async def test_collection_advances_after_round_limit_even_if_gate_not_ready():
    """门槛一直不过时，也不能让用户在①无限答题：8 轮后带缺口进入诊断。"""
    c, _, session = await setup(IntentType.FREE_CHAT, ready=False)
    for index in range(8):
        await c.memory_service.record_turn(
            "u1", session.id, role="user", text=f"第 {index} 轮回答",
            loop_stage=LoopStage.COLLECT,
        )
    result = await send(c, session, "我平时喜欢写东西")
    assert result.stage is not LoopStage.COLLECT


def test_unsafe_diagnose_output_is_repaired_instead_of_rejected():
    """模型的"未提供→短板"应被就地修成待验证，而不是整份报告生成失败。"""
    structured = {
        "verdict": {"title": "先核对", "summary": "先核对现有情况。"},
        "swot": {"strength": [], "weakness": ["没有提供项目材料"], "opportunity": [], "risk": []},
        "dimensions": [
            {
                "group": "SELF-PORTRAIT",
                "group_method": "能力三核",
                "items": [
                    {
                        "index": 1,
                        "name": "能力结构",
                        "tag": "短板",
                        "conclusion": "资料里没看到相关证据",
                        "evidence": "资料未提供",
                    }
                ],
            }
        ],
        "gaps": [
            {
                "gap_id": "g1",
                "requirement": "经历证据",
                "current_state": "未提供实习经历",
                "suggestion": "补充一段实习或项目",
            }
        ],
        "guide": None,
    }
    repaired = _repair_diagnose_evidence(structured)
    output = DiagnoseOutput.model_validate(repaired)
    assert output.dimensions[0].items[0].tag == "待验证"
    assert output.swot.weakness == []
    assert "未提供" not in output.gaps[0].current_state


class UnsafeDiagnoseEngine(Engine):
    """诊断产出把"未提供"写成短板/弱项的真实模型样子。"""

    async def invoke(self, request):
        from zhiyin_orchestration import AgentResult

        if request.stage == "diagnose":
            body = {
                "conclusion": "先核对现有情况。",
                "verdict": {"title": "先核对", "summary": "根据现有情况继续了解。"},
                "swot": {"strength": [], "weakness": ["没有提供项目材料"], "opportunity": [], "risk": []},
                "dimensions": [
                    {
                        "group": "SELF-PORTRAIT",
                        "group_method": "能力三核",
                        "items": [
                            {
                                "index": 1,
                                "name": "能力结构",
                                "tag": "短板",
                                "conclusion": "资料里没看到相关证据",
                                "evidence": "资料未提供",
                            }
                        ],
                    }
                ],
                "gaps": [],
                "guide": {"kind": "question", "text": "继续了解"},
            }
            return AgentResult(agent_id=request.agent_id, valid=True, structured=body)
        return await super().invoke(request)


@pytest.mark.asyncio
async def test_report_generation_survives_unsafe_model_output():
    """真实模型写成"未提供即短板"时，报告仍应生成（先修补再校验）。"""
    c, _, session = await setup(ready=True)
    c.orchestrator._agent_engine = UnsafeDiagnoseEngine()
    first = await send(c, session, "聊聊我的情况")
    assert first.messages[0].text.endswith(_ASSET_OFFERS["report"])
    result = await send(c, session, "可以")
    assert await c.asset_service.get_report("u1") is not None
    assert "诊断报告已生成" in result.messages[0].text


def test_png_material_is_rejected_at_upload_stage():
    extractor = LocalTextExtractor()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 64
    with pytest.raises(DocumentReadError) as excinfo:
        extractor.extract_text(png, filename="qa-1x1.png")
    message = str(excinfo.value)
    assert "暂不支持直接读取图片" in message
    assert "TXT" in message or "文字" in message


def test_binary_without_suffix_is_rejected_by_content_sniff():
    extractor = LocalTextExtractor()
    payload = (b"\x00\x01\x02\x03\x04\x05" * 40) + b"tail"
    with pytest.raises(DocumentReadError) as excinfo:
        extractor.extract_text(payload, filename="upload")
    assert "二进制" in str(excinfo.value)


def test_plain_text_still_reads():
    extractor = LocalTextExtractor()
    assert extractor.extract_text("课程名称\t成绩\n数据结构\t90".encode("utf-8"), filename="grades.txt")
