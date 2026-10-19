"""Validated legacy Kev configuration schema; dialogue uses on-demand advice."""

from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhiyin_business.ports.orchestrator import IntentType

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
    # 以下是"按证据校准"用的旋钮，**默认全部等于全局阈值**，
    # 也就是不配置就与原来完全一致（实测 ZY-01：五个正确候选全被阈值挡掉，
    # 而报告明确要求"不要凭单轮样例直接降阈值"）。
    confidence_thresholds: dict[str, float] = Field(default_factory=dict)
    probability_thresholds: dict[str, float] = Field(default_factory=dict)
    #: top1 与 top2 的最小间距；0 表示不启用（接近的两个候选不该被当成确定判断）
    top2_margin: float = Field(default=0.0, ge=0.0, le=1.0)
    #: 当前环节 → 该环节的预期意图。候选与之一致时，用下面两档更低的门槛
    stage_prior: dict[str, str] = Field(default_factory=dict)
    stage_prior_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stage_prior_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_criteria(self) -> "DecisionRoutingConfig":
        required = _BUSINESS_INTENTS | {"unclear"}
        if set(self.criteria) != required:
            raise ValueError("decision routing criteria must match the intent candidates")
        for key in (*self.confidence_thresholds, *self.probability_thresholds):
            if key not in required:
                raise ValueError(f"threshold override for unknown intent: {key}")
        for stage, intent in self.stage_prior.items():
            if intent not in required:
                raise ValueError(f"stage prior points at unknown intent: {stage}->{intent}")
        return self
