"""TypeSafe System One 兼容决策服务适配器。"""

from __future__ import annotations

import asyncio

import httpx
from pydantic import ValidationError

from zhiyin_data_sdk.gateways.decision import (
    DecisionGateway,
    DecisionGatewayError,
    DecisionRequest,
    DecisionResult,
)


class SystemOneDecisionGateway(DecisionGateway):
    """通过 ``POST /v1/systemone`` 调用 Kev。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        base_url: str,
        model: str = "kev-latest",
        timeout_s: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("decision base_url must not be empty")
        if timeout_s <= 0:
            raise ValueError("decision timeout_s must be positive")
        self._model = model.strip() or "kev-latest"
        self._timeout_s = timeout_s
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_s
        )

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        payload = {
            "model": self._model,
            "state": request.state,
            "questions": {
                question_id: question.model_dump(mode="json")
                for question_id, question in request.questions.items()
            },
        }
        async def call() -> DecisionResult:
            response = await self._client.post("/v1/systemone", json=payload)
            response.raise_for_status()
            return DecisionResult.model_validate(response.json())

        try:
            result = await asyncio.wait_for(call(), timeout=self._timeout_s)
        except asyncio.TimeoutError as exc:
            raise DecisionGatewayError("decision service timed out") from exc
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            raise DecisionGatewayError("decision service request failed") from exc

        expected_questions = set(request.questions)
        if set(result.answers) != expected_questions:
            raise DecisionGatewayError("decision response question ids do not match")
        for question_id, question in request.questions.items():
            answer = result.answers[question_id]
            expected_options = set(question.criteria)
            if answer.choice not in expected_options:
                raise DecisionGatewayError("decision response contains an unknown choice")
            if set(answer.probabilities) != expected_options:
                raise DecisionGatewayError(
                    "decision response probability options do not match"
                )
        return result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = ["SystemOneDecisionGateway"]
