"""对话里不允许出现"写死的回复冒充模型回复"。

背景（一次真实的用户反馈："这明显是mock而不是真正接入的AI"）：

模型是通的、也确实在分析对话，但两条路径会把它换掉，而且**都不留痕**：

1. 意图关键词没命中 → 直接返回一句写死的澄清追问，**连模型都不调**。
   「我今天投了三家设计院，还没回音」这种极具体的输入，0.0 秒回同一句话。
2. 模型产出不符合契约（常见：JSON 少了必填的 `guide`）→ 用写死的
   "你愿意先说说现在最卡的那一步吗？" 顶上。

两条合起来的效果就是：用户说什么都收到同一句，很自然地判断成假模型。
这里把"不许再这么干"钉住。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_business.policies.routing_rules import RuleStagePolicy
from zhiyin_business.ports.orchestrator import IntentType
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.services.orchestrator import _guide
from zhiyin_kernel.enums import LoopStage
from zhiyin_infrastructure.local.repository import LocalJsonRegistryRepository

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _policy() -> RuleStagePolicy:
    """澄清话术现在来自动态资源，不再写在方法体里 —— 所以策略要带读侧。"""
    return RuleStagePolicy(LocalJsonRegistryRepository(str(DATA_DIR / "registry")))


def _blackboard(stage: LoopStage | None) -> BlackboardView:
    return BlackboardView(user_id="u1", current_stage=stage)


@pytest.mark.asyncio
async def test_unmatched_intent_continues_in_the_current_stage() -> None:
    """关键词没命中 ≠ 用户意思不清楚：退回当前环节，交给模型。"""
    decision = await _policy().decide(
        blackboard=_blackboard(LoopStage.COLLECT),
        intent=IntentType.FREE_CHAT,
        message="我今天投了三家设计院，还没回音",
    )
    assert decision.need_clarify is False
    assert decision.stage is LoopStage.COLLECT


@pytest.mark.asyncio
async def test_clarify_only_when_there_is_no_stage_at_all() -> None:
    """全新会话、连环节都没定过，才需要先澄清一句。"""
    decision = await _policy().decide(
        blackboard=_blackboard(None),
        intent=IntentType.FREE_CHAT,
        message="在吗",
    )
    assert decision.need_clarify is True
    assert decision.clarify_question


@pytest.mark.asyncio
async def test_clarify_text_comes_from_config_not_from_code() -> None:
    """澄清话术必须是配置里的那一句：改文案不该发版，也不该在代码里再写一份。"""
    registry = LocalJsonRegistryRepository(str(DATA_DIR / "registry"))
    prompt = await registry.get_prompt("router.clarify")
    assert prompt is not None
    decision = await RuleStagePolicy(registry).decide(
        blackboard=_blackboard(None),
        intent=IntentType.FREE_CHAT,
        message="在吗",
    )
    assert decision.clarify_question == prompt.content


def test_guide_falls_back_to_the_models_own_words() -> None:
    """模型漏了 guide 字段时，用**它自己写的**下一步建议，而不是写死的句子。"""
    structured = {
        "field_updates": [],
        "remaining_gaps": [
            {"key": "basic_context", "reason": "画像为空", "suggested_next_action": "先确认一句身份状态，不追问细节。"}
        ],
    }
    guide = _guide(structured.get("guide"), structured)
    assert guide.text == "先确认一句身份状态，不追问细节。"
    assert "最卡的那一步" not in guide.text


def test_guide_uses_the_model_guide_when_present() -> None:
    structured = {"guide": {"kind": "question", "text": "模型自己写的话", "question": "模型自己写的话"}}
    guide = _guide(structured.get("guide"), structured)
    assert guide.text == "模型自己写的话"


def test_last_resort_line_admits_it_is_a_system_line() -> None:
    """什么都没有时，兜底句必须读起来像系统在说话，不能装成主理的回答。"""
    guide = _guide(None, {"field_updates": []})
    assert "没能按格式产出" in guide.text


@pytest.mark.asyncio
async def test_missing_prompt_raises_instead_of_falling_back() -> None:
    """配置缺失必须抛错，不许用兜底句顶上。

    兜底句看着稳妥，代价是把"少了一条配置"变成"今天它回答得有点怪"：
    不报错、不留痕，等有人察觉时已经不知道该查哪一天。所以规则是 ——
    配置缺了就抛，且抛出的错带 code，排查时能直接定位到是哪一条没了。
    """
    from zhiyin_data_sdk.errors import MissingConfigError
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine

    class _EmptyRegistry:
        async def get_prompt(self, code):
            return None

        async def list_prompts(self, *, layer=None, agent_id=None, stage=None):
            return []

    engine = AgnoAgentEngine(model_factory=lambda: None, registry=_EmptyRegistry())
    with pytest.raises(MissingConfigError) as missing:
        await engine._prompt_bundle("profile_analyst", "collect")
    assert missing.value.code == "MISSING_CONFIG"

    # 连读侧都没接上时同样抛，而不是"没有提示词也照跑"
    bare = AgnoAgentEngine(model_factory=lambda: None)
    with pytest.raises(MissingConfigError):
        await bare._prompt_bundle("profile_analyst", "collect")


@pytest.mark.asyncio
async def test_orchestrator_raises_when_clarify_copy_is_missing() -> None:
    """澄清话术缺配置时抛错，不再回落到一句写死的字面量。"""
    from zhiyin_business.services.orchestrator import DefaultOrchestrator
    from zhiyin_data_sdk.errors import MissingConfigError

    class _EmptyRegistry:
        async def get_prompt(self, code):
            return None

    orchestrator = DefaultOrchestrator.__new__(DefaultOrchestrator)
    orchestrator._registry = _EmptyRegistry()
    with pytest.raises(MissingConfigError):
        await orchestrator._clarify_text()
