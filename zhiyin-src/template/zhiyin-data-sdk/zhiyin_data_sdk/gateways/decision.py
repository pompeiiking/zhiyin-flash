"""System One 决策模型的传输契约。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionChoiceQuestion(BaseModel):
    """一个受限候选集合上的选择题。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["choice"] = "choice"
    instructions: str
    criteria: dict[str, str]

    @model_validator(mode="after")
    def validate_criteria(self) -> "DecisionChoiceQuestion":
        if not 1 <= len(self.criteria) <= 255:
            raise ValueError("choice criteria must contain 1 to 255 options")
        if any(not str(key).strip() for key in self.criteria):
            raise ValueError("choice criteria keys must not be empty")
        return self


class DecisionRequest(BaseModel):
    """发给决策模型的状态和具名问题。"""

    model_config = ConfigDict(extra="forbid")

    state: dict[str, Any]
    questions: dict[str, DecisionChoiceQuestion]


class DecisionChoiceAnswer(BaseModel):
    """System One choice 回答。"""

    model_config = ConfigDict(extra="ignore")

    type: Literal["choice"]
    choice: str
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float]

    @model_validator(mode="after")
    def validate_probabilities(self) -> "DecisionChoiceAnswer":
        if self.choice not in self.probabilities:
            raise ValueError("choice must be present in probabilities")
        if any(value < 0.0 or value > 1.0 for value in self.probabilities.values()):
            raise ValueError("probabilities must be between 0 and 1")
        return self


class DecisionResult(BaseModel):
    """经过适配器校验后的决策响应。"""

    model_config = ConfigDict(extra="ignore")

    model: str
    answers: dict[str, DecisionChoiceAnswer]
    latency_ms: float | None = Field(default=None, ge=0.0)


class DecisionGatewayError(RuntimeError):
    """决策服务不可用或响应不符合契约。"""


class DecisionGateway(ABC):
    """外部决策模型网关。"""

    @abstractmethod
    async def decide(self, request: DecisionRequest) -> DecisionResult:
        """执行一组具名决策；失败时抛出 ``DecisionGatewayError``。"""


__all__ = [
    "DecisionChoiceAnswer",
    "DecisionChoiceQuestion",
    "DecisionGateway",
    "DecisionGatewayError",
    "DecisionRequest",
    "DecisionResult",
]
