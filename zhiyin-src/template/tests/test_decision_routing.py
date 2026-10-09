"""Kev 意图路由：关键词优先、阈值采用与安全回退。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from zhiyin_business.policies.decision_routing import DecisionRoutingPolicy
from zhiyin_business.policies.routing import IntentDecision, IntentPolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType
from zhiyin_data_sdk.gateways.decision import (
    DecisionChoiceAnswer,
    DecisionGateway,
    DecisionGatewayError,
    DecisionRequest,
    DecisionResult,
)
from zhiyin_kernel.enums import LoopStage


CRITERIA = {
    "confused": "confused",
    "verify_direction": "verify",
    "undecided": "undecided",
    "how_to_act": "act",
    "stuck": "stuck",
    "review_due": "review",
    "free_chat": "chat",
    "unclear": "unclear",
}


class NoKeywordPolicy(IntentPolicy):
    async def classify(self, *, message: str, blackboard: BlackboardView) -> IntentType:
        return IntentType.FREE_CHAT

    async def classify_with_decision(
        self, *, message: str, blackboard: BlackboardView, skip_model: bool = False
    ) -> IntentDecision:
        return IntentDecision(
            intent=IntentType.FREE_CHAT,
            source="fallback",
            reason="no_keyword_match",
        )


class KeywordPolicy(NoKeywordPolicy):
    async def classify_with_decision(
        self, *, message: str, blackboard: BlackboardView, skip_model: bool = False
    ) -> IntentDecision:
        return IntentDecision(
            intent=IntentType.STUCK,
            candidate="stuck",
            source="keyword",
            adopted=True,
            reason="keyword_match",
        )


@dataclass
class FakeRegistry:
    enabled: bool = True
    mode: str = "active"

    async def feature_flags(self) -> dict[str, bool]:
        return {"decision_intent_routing": self.enabled}

    async def get_decision_routing_policy(self) -> dict:
        return {
            "mode": self.mode,
            "confidence_threshold": 0.55,
            "probability_threshold": 0.70,
            "max_message_chars": 6000,
            "instructions": "classify",
            "criteria": CRITERIA,
        }


class FakeGateway(DecisionGateway):
    def __init__(
        self,
        *,
        choice: str = "review_due",
        confidence: float = 0.8,
        probability: float = 0.8,
        fail: bool = False,
    ) -> None:
        self.choice = choice
        self.confidence = confidence
        self.probability = probability
        self.fail = fail
        self.calls = 0

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        self.calls += 1
        if self.fail:
            raise DecisionGatewayError("down")
        remaining = (1.0 - self.probability) / (len(CRITERIA) - 1)
        probabilities = {key: remaining for key in CRITERIA}
        probabilities[self.choice] = self.probability
        return DecisionResult(
            model="kev-latest",
            answers={
                "intent": DecisionChoiceAnswer(
                    type="choice",
                    choice=self.choice,
                    confidence=self.confidence,
                    probabilities=probabilities,
                )
            },
            latency_ms=15.0,
        )


def _board() -> BlackboardView:
    return BlackboardView(user_id="u1", task_id="t1", current_stage=LoopStage.ACT)


def _policy(
    gateway: FakeGateway,
    *,
    registry: FakeRegistry | None = None,
    fallback: IntentPolicy | None = None,
) -> DecisionRoutingPolicy:
    return DecisionRoutingPolicy(
        fallback=fallback or NoKeywordPolicy(),
        decision_gateway=gateway,
        registry=registry or FakeRegistry(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_active_adopts_only_when_both_thresholds_pass() -> None:
    gateway = FakeGateway()
    decision = await _policy(gateway).classify_with_decision(
        message="请复盘过去一个月", blackboard=_board()
    )
    assert decision.intent is IntentType.REVIEW_DUE
    assert decision.adopted is True
    assert decision.reason == "thresholds_met"

    low = await _policy(FakeGateway(confidence=0.54)).classify_with_decision(
        message="请复盘", blackboard=_board()
    )
    assert low.intent is IntentType.FREE_CHAT
    assert low.reason == "confidence_below_threshold"

    low_probability = await _policy(FakeGateway(probability=0.69)).classify_with_decision(
        message="请复盘", blackboard=_board()
    )
    assert low_probability.reason == "probability_below_threshold"


@pytest.mark.asyncio
async def test_keyword_and_explicit_option_skip_kev() -> None:
    gateway = FakeGateway()
    keyword = await _policy(gateway, fallback=KeywordPolicy()).classify_with_decision(
        message="我卡住了", blackboard=_board()
    )
    assert keyword.intent is IntentType.STUCK
    assert gateway.calls == 0

    skipped = await _policy(gateway).classify_with_decision(
        message="第二个", blackboard=_board(), skip_model=True
    )
    assert skipped.reason == "explicit_option"
    assert gateway.calls == 0


@pytest.mark.asyncio
async def test_explicit_option_is_not_hijacked_by_its_own_wording() -> None:
    """明确选项的展示文案里带关键词，也不能被关键词抢走。

    实测（ZY-02）原样：选项「上线限三天，卡住就先往下走」里的"卡住"被关键词命中，
    结果行动一件都没做就跳进了复盘。展示文案是给用户读的，不是路由输入 ——
    明确选项 / 结构化动作的意图优先于关键词与 Kev。
    """
    gateway = FakeGateway()
    hijacked = await _policy(gateway, fallback=KeywordPolicy()).classify_with_decision(
        message="上线限三天，卡住就先往下走", blackboard=_board(), skip_model=True
    )
    assert hijacked.reason == "explicit_option"
    assert hijacked.intent is not IntentType.STUCK
    assert gateway.calls == 0


class CalibratedRegistry(FakeRegistry):
    """按"校准后"的配置返回 —— 用来证明新旋钮真的能改变采用结果。"""

    def __init__(self, **overrides) -> None:
        super().__init__()
        self._overrides = overrides

    async def get_decision_routing_policy(self) -> dict:
        config = await super().get_decision_routing_policy()
        config.update(self._overrides)
        return config


@pytest.mark.asyncio
async def test_per_intent_threshold_can_adopt_where_the_global_one_would_not() -> None:
    """全局阈值挡掉的候选，给该意图一档专属阈值后可以采用（ZY-01 的机制）。"""
    gateway = FakeGateway(choice="review_due", confidence=0.46, probability=0.53)

    blocked = await _policy(
        FakeGateway(choice="review_due", confidence=0.46, probability=0.53)
    ).classify_with_decision(message="请复盘这两周", blackboard=_board())
    assert blocked.adopted is False and blocked.reason == "confidence_below_threshold"

    adopted = await _policy(
        gateway,
        registry=CalibratedRegistry(
            confidence_thresholds={"review_due": 0.40},
            probability_thresholds={"review_due": 0.50},
        ),
    ).classify_with_decision(message="请复盘这两周", blackboard=_board())
    assert adopted.adopted is True and adopted.intent is IntentType.REVIEW_DUE


@pytest.mark.asyncio
async def test_stage_prior_admits_the_expected_intent_at_a_lower_bar() -> None:
    """候选与当前环节的预期意图一致时，可用更低的门槛 —— 报告里 how_to_act 的实测值。"""
    gateway = FakeGateway(choice="how_to_act", confidence=0.1674, probability=0.2715)

    blocked = await _policy(
        FakeGateway(choice="how_to_act", confidence=0.1674, probability=0.2715)
    ).classify_with_decision(message="接下来两周怎么安排", blackboard=_board())
    assert blocked.adopted is False

    board = BlackboardView(user_id="u1", task_id="t1", current_stage=LoopStage.ACT)
    adopted = await _policy(
        gateway,
        registry=CalibratedRegistry(
            stage_prior={"act": "how_to_act"},
            stage_prior_confidence=0.15,
            stage_prior_probability=0.25,
        ),
    ).classify_with_decision(message="接下来两周怎么安排", blackboard=board)
    assert adopted.adopted is True and adopted.intent is IntentType.HOW_TO_ACT


@pytest.mark.asyncio
async def test_top2_margin_rejects_a_close_call() -> None:
    """两个候选贴得很近时不当成确定判断（间距默认 0，不配置就不启用）。"""
    gateway = FakeGateway(choice="review_due", confidence=0.6, probability=0.3)

    adopted_by_default = await _policy(
        FakeGateway(choice="review_due", confidence=0.6, probability=0.3),
        registry=CalibratedRegistry(
            confidence_thresholds={"review_due": 0.5},
            probability_thresholds={"review_due": 0.2},
        ),
    ).classify_with_decision(message="看看进展", blackboard=_board())
    assert adopted_by_default.adopted is True

    rejected = await _policy(
        gateway,
        registry=CalibratedRegistry(
            confidence_thresholds={"review_due": 0.5},
            probability_thresholds={"review_due": 0.2},
            top2_margin=0.25,
        ),
    ).classify_with_decision(message="看看进展", blackboard=_board())
    assert rejected.adopted is False and rejected.reason == "top2_margin_too_small"


@pytest.mark.asyncio
async def test_shadow_unclear_disabled_too_long_and_failure_fall_back() -> None:
    gateway = FakeGateway()
    shadow = await _policy(
        gateway, registry=FakeRegistry(mode="shadow")
    ).classify_with_decision(message="请复盘", blackboard=_board())
    assert shadow.adopted is False and shadow.reason == "shadow_mode"
    assert gateway.calls == 1

    unclear = await _policy(FakeGateway(choice="unclear")).classify_with_decision(
        message="随便聊聊", blackboard=_board()
    )
    assert unclear.reason == "invalid_business_intent"

    disabled_gateway = FakeGateway()
    disabled = await _policy(
        disabled_gateway, registry=FakeRegistry(enabled=False)
    ).classify_with_decision(message="请复盘", blackboard=_board())
    assert disabled.reason == "feature_disabled" and disabled_gateway.calls == 0

    too_long = await _policy(FakeGateway()).classify_with_decision(
        message="x" * 6001, blackboard=_board()
    )
    assert too_long.reason == "message_too_long"

    failed = await _policy(FakeGateway(fail=True)).classify_with_decision(
        message="请复盘", blackboard=_board()
    )
    assert failed.reason == "gateway_error"


@pytest.mark.asyncio
async def test_orchestrator_logs_decision_once_for_an_idempotent_message() -> None:
    from pathlib import Path

    from zhiyin_boot import Settings, build_container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_orchestration.agent import AgentEngine, AgentRequest, AgentResult

    class CountingPolicy(NoKeywordPolicy):
        def __init__(self) -> None:
            self.calls = 0

        async def classify_with_decision(
            self,
            *,
            message: str,
            blackboard: BlackboardView,
            skip_model: bool = False,
        ) -> IntentDecision:
            self.calls += 1
            return IntentDecision(
                intent=IntentType.REVIEW_DUE,
                candidate="review_due",
                source="kev",
                adopted=True,
                reason="thresholds_met",
                confidence=0.9,
                probabilities={"review_due": 0.92, "unclear": 0.08},
                latency_ms=12.0,
            )

    class RecordingStagePolicy:
        def __init__(self, delegate) -> None:
            self.delegate = delegate
            self.intents: list[IntentType] = []

        async def decide(self, *, blackboard, intent, message):
            self.intents.append(intent)
            return await self.delegate.decide(
                blackboard=blackboard, intent=intent, message=message
            )

    class Engine(AgentEngine):
        async def invoke(self, request: AgentRequest) -> AgentResult:
            return AgentResult(
                agent_id=request.agent_id,
                structured={
                    "conclusion": "收到。",
                    "field_updates": [],
                    "remaining_gaps": [],
                    "confidence_overall": 0.5,
                    "ready_to_handoff": False,
                    "guide": {
                        "kind": "question",
                        "text": "继续吗？",
                        "question": "继续吗？",
                    },
                },
                valid=True,
            )

    template = Path(__file__).resolve().parents[1]
    data = template / "data"
    container = build_container(
        Settings(
            use_remote_llm=True,
            llm_api_key="sk-test",
            env="test",
            local_data_dir=str(data),
            local_registry_dir=str(data / "registry"),
            local_knowledge_dir=str(data / "knowledge"),
            local_object_dir=str(data / "objects"),
        )
    )
    policy = CountingPolicy()
    stage_policy = RecordingStagePolicy(container.orchestrator._stage_policy)  # noqa: SLF001
    container.orchestrator._intent_policy = policy  # noqa: SLF001
    container.orchestrator._stage_policy = stage_policy  # noqa: SLF001
    container.orchestrator._agent_engine = Engine()  # noqa: SLF001
    session = await container.orchestrator.enter_task("u-kev-idem", "free_chat")
    request = TurnRequest(
        user_id="u-kev-idem",
        task_id=session.id,
        message="请看看我最近的进展",
        client_msg_id="same-kev-message",
    )

    await container.orchestrator.handle_message(request)
    await container.orchestrator.handle_message(request)

    assert policy.calls == 1
    assert stage_policy.intents == [IntentType.REVIEW_DUE]
    answers = [
        event
        for event in await container.behavior_service.recent("u-kev-idem", limit=20)
        if event.event_type.value == "answer"
    ]
    assert len(answers) == 1
    assert answers[0].payload["intent_decision"]["candidate"] == "review_due"
