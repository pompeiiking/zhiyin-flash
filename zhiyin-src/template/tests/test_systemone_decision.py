"""System One 网关：请求形状、响应校验与总超时。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from zhiyin_data_sdk.gateways.decision import (
    DecisionChoiceQuestion,
    DecisionGatewayError,
    DecisionRequest,
)
from zhiyin_infrastructure.ai.systemone import SystemOneDecisionGateway


def _request() -> DecisionRequest:
    return DecisionRequest(
        state={"message": "请帮我复盘", "current_stage": "act"},
        questions={
            "intent": DecisionChoiceQuestion(
                instructions="classify",
                criteria={"review_due": "review", "unclear": "unclear"},
            )
        },
    )


@pytest.mark.asyncio
async def test_systemone_gateway_sends_expected_request_and_validates_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert request.url.path == "/v1/systemone"
        assert body["model"] == "kev-latest"
        assert body["state"] == {"message": "请帮我复盘", "current_stage": "act"}
        return httpx.Response(
            200,
            json={
                "model": "kev-latest",
                "answers": {
                    "intent": {
                        "type": "choice",
                        "choice": "review_due",
                        "confidence": 0.9,
                        "probabilities": {"review_due": 0.92, "unclear": 0.08},
                    }
                },
                "latency_ms": 12.5,
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://kev.local"
    )
    gateway = SystemOneDecisionGateway(base_url="http://kev.local", client=client)
    result = await gateway.decide(_request())
    assert result.answers["intent"].choice == "review_due"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        {
            "type": "choice",
            "choice": "unknown",
            "confidence": 0.9,
            "probabilities": {"review_due": 0.9, "unclear": 0.1},
        },
        {
            "type": "choice",
            "choice": "review_due",
            "confidence": 0.9,
            "probabilities": {"review_due": 1.2, "unclear": -0.2},
        },
    ],
)
async def test_systemone_gateway_rejects_invalid_answers(answer: dict) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"model": "kev-latest", "answers": {"intent": answer}},
        )
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://kev.local"
    ) as client:
        gateway = SystemOneDecisionGateway(base_url="http://kev.local", client=client)
        with pytest.raises(DecisionGatewayError):
            await gateway.decide(_request())


@pytest.mark.asyncio
async def test_systemone_gateway_converts_http_and_total_timeout_to_gateway_error() -> None:
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(500)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(slow_handler), base_url="http://kev.local"
    ) as client:
        gateway = SystemOneDecisionGateway(
            base_url="http://kev.local", timeout_s=0.01, client=client
        )
        with pytest.raises(DecisionGatewayError, match="timed out"):
            await gateway.decide(_request())


@pytest.mark.asyncio
async def test_systemone_gateway_converts_non_success_status() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://kev.local"
    ) as client:
        gateway = SystemOneDecisionGateway(base_url="http://kev.local", client=client)
        with pytest.raises(DecisionGatewayError, match="request failed"):
            await gateway.decide(_request())


@pytest.mark.asyncio
async def test_systemone_gateway_converts_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Kev unavailable", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://kev.local"
    ) as client:
        gateway = SystemOneDecisionGateway(base_url="http://kev.local", client=client)
        with pytest.raises(DecisionGatewayError, match="request failed"):
            await gateway.decide(_request())
