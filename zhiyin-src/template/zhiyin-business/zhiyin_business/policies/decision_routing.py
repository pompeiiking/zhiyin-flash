"""关键词优先、Kev 兜底的意图路由策略。"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from zhiyin_business.policies.routing import IntentDecision, IntentPolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType
from zhiyin_business.ports.registry import RegistryService
from zhiyin_data_sdk.gateways.decision import (
    DecisionChoiceQuestion,
    DecisionGateway,
    DecisionRequest,
)

logger = logging.getLogger(__name__)

_BUSINESS_INTENTS = frozenset(intent.value for intent in IntentType)


class DecisionRoutingConfig(BaseModel):
    """动态资源 ``decision_routing`` 的受校验形状。"""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["off", "shadow", "active"]
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    probability_threshold: float = Field(ge=0.0, le=1.0)
    max_message_chars: int = Field(ge=1)
    instructions: str
    criteria: dict[str, str]

    @model_validator(mode="after")
    def validate_criteria(self) -> "DecisionRoutingConfig":
        required = _BUSINESS_INTENTS | {"unclear"}
        if set(self.criteria) != required:
            raise ValueError("decision routing criteria must match the intent candidates")
        return self


class DecisionRoutingPolicy(IntentPolicy):
    """先执行原关键词规则，仅在未命中时询问 Kev。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        fallback: IntentPolicy,
        decision_gateway: DecisionGateway | None,
        registry: RegistryService,
    ) -> None:
        self._fallback = fallback
        self._gateway = decision_gateway
        self._registry = registry

    async def classify(self, *, message: str, blackboard: BlackboardView) -> IntentType:
        return (
            await self.classify_with_decision(message=message, blackboard=blackboard)
        ).intent

    async def classify_with_decision(
        self,
        *,
        message: str,
        blackboard: BlackboardView,
        skip_model: bool = False,
    ) -> IntentDecision:
        # 明确选项 / 结构化动作优先于关键词与 Kev：
        # 选项绑定的业务意图就是答案，**不再**拿它的展示文案做关键词分类。
        # 实测（ZY-02）：选项「上线限三天，卡住就先往下走」里的"卡住"曾被关键词抢走，
        # 行动一件都没做却直接跳进了复盘。展示文案是给用户读的，不是路由输入。
        if skip_model:
            return self._fallback_result("explicit_option")

        keyword = await self._fallback.classify_with_decision(
            message=message, blackboard=blackboard, skip_model=True
        )
        if keyword.reason == "keyword_match":
            return keyword

        text = (message or "").strip()
        if not text:
            return self._fallback_result("empty_message")

        try:
            flags = await self._registry.feature_flags()
            if not flags.get("decision_intent_routing", False):
                return self._fallback_result("feature_disabled")
            raw_config = await self._registry.get_decision_routing_policy()
            config = DecisionRoutingConfig.model_validate(raw_config)
        except ValidationError:
            logger.warning("decision_routing 配置格式错误，本轮关闭 Kev", exc_info=True)
            return self._fallback_result("invalid_config")
        except Exception:
            logger.warning("读取 decision_routing 配置失败，本轮关闭 Kev", exc_info=True)
            return self._fallback_result("config_error")

        if config.mode == "off":
            return self._fallback_result("mode_off")
        if len(text) > config.max_message_chars:
            return self._fallback_result("message_too_long")
        if self._gateway is None:
            return self._fallback_result("gateway_unconfigured")

        current_stage = (
            blackboard.current_stage.value if blackboard.current_stage is not None else ""
        )
        try:
            response = await self._gateway.decide(
                DecisionRequest(
                    state={"message": text, "current_stage": current_stage},
                    questions={
                        "intent": DecisionChoiceQuestion(
                            instructions=config.instructions,
                            criteria=config.criteria,
                        )
                    },
                )
            )
            answer = response.answers["intent"]
        except Exception:
            logger.warning("Kev 意图分类失败，本轮沿用原流程", exc_info=True)
            return self._fallback_result("gateway_error")

        candidate_probability = answer.probabilities.get(answer.choice, 0.0)
        evidence = {
            "candidate": answer.choice,
            "source": "kev",
            "confidence": answer.confidence,
            "probabilities": answer.probabilities,
            "latency_ms": response.latency_ms,
        }
        if config.mode == "shadow":
            return IntentDecision(
                intent=IntentType.FREE_CHAT,
                adopted=False,
                reason="shadow_mode",
                **evidence,
            )
        if answer.choice not in _BUSINESS_INTENTS:
            return IntentDecision(
                intent=IntentType.FREE_CHAT,
                adopted=False,
                reason="invalid_business_intent",
                **evidence,
            )
        if answer.confidence < config.confidence_threshold:
            return IntentDecision(
                intent=IntentType.FREE_CHAT,
                adopted=False,
                reason="confidence_below_threshold",
                **evidence,
            )
        if candidate_probability < config.probability_threshold:
            return IntentDecision(
                intent=IntentType.FREE_CHAT,
                adopted=False,
                reason="probability_below_threshold",
                **evidence,
            )
        return IntentDecision(
            intent=IntentType(answer.choice),
            adopted=True,
            reason="thresholds_met",
            **evidence,
        )

    @staticmethod
    def _fallback_result(reason: str) -> IntentDecision:
        return IntentDecision(
            intent=IntentType.FREE_CHAT,
            source="fallback",
            adopted=False,
            reason=reason,
        )


__all__ = ["DecisionRoutingConfig", "DecisionRoutingPolicy"]
