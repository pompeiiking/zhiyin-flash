"""OpenAI 兼容协议适配器。

DeepSeek 与豆包 Ark 都提供 OpenAI 形状的 HTTP 接口，差异仅在 base_url、
鉴权头和 payload 细节；本模块集中处理这些差异，业务层不感知。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from zhiyin_data_sdk.gateways.ai import (
    EmbedGateway,
    LLMGateway,
    LLMMessage,
    LLMResult,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleLLMGateway(LLMGateway):
    """OpenAI Chat Completions 兼容实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str,
    ) -> None:
        if not api_key:
            raise ValueError(f"{provider_name} API key 不能为空")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._provider_name = provider_name

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.2,
        timeout_s: float = 60.0,
    ) -> LLMResult:
        payload_messages = [message.model_dump() for message in messages]
        response_format: Optional[dict[str, str]] = None
        if json_schema is not None:
            schema_text = json.dumps(json_schema, ensure_ascii=False)
            payload_messages.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "你必须只输出一个合法 JSON 对象，不要输出 Markdown、"
                        "解释或多余文本。输出必须满足以下 JSON Schema："
                        f"{schema_text}"
                    ),
                },
            )
            response_format = {"type": "json_object"}

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": payload_messages,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=_headers(self._api_key),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("LLM 响应体不是 JSON 对象")
        except Exception as exc:  # noqa: BLE001 - 模型不可用时显式降级
            logger.exception(
                "模型调用失败：provider=%s model=%s", self._provider_name, self._model
            )
            return LLMResult(
                model=self._model,
                usage={"provider": self._provider_name, "error": str(exc)},
                degraded=True,
            )

        text = _chat_text(data)
        structured: Optional[dict[str, Any]] = None
        if json_schema is not None and text:
            try:
                parsed = json.loads(text)
                structured = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                structured = None
        return LLMResult(
            text=text,
            structured=structured,
            model=str(data.get("model") or self._model),
            usage=dict(data.get("usage") or {}),
            degraded=False,
        )


class OpenAICompatibleEmbeddingGateway(EmbedGateway):
    """OpenAI Embeddings 兼容实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str,
    ) -> None:
        if not api_key:
            raise ValueError(f"{provider_name} API key 不能为空")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._provider_name = provider_name

    @property
    def model_id(self) -> str:
        return self._model

    async def embed(
        self, texts: list[str], *, timeout_s: float = 30.0
    ) -> list[list[float]]:
        if not texts:
            return []
        response = await _post_embeddings(
            base_url=self._base_url,
            api_key=self._api_key,
            model=self._model,
            texts=texts,
            timeout_s=timeout_s,
            provider_name=self._provider_name,
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"{self._provider_name} 返回缺少 data")
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        vectors = [item.get("embedding") for item in ordered]
        if len(vectors) != len(texts) or any(
            not isinstance(vector, list) for vector in vectors
        ):
            raise RuntimeError(f"{self._provider_name} embedding 返回数量或形状不正确")
        return [[float(value) for value in vector] for vector in vectors]


async def _post_embeddings(
    *,
    base_url: str,
    api_key: str,
    model: str,
    texts: list[str],
    timeout_s: float,
    provider_name: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/embeddings",
            headers=_headers(api_key),
            json={"model": model, "input": texts, "encoding_format": "float"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RuntimeError(
                f"{provider_name} embedding 调用失败："
                f"{exc.response.status_code} {detail}"
            ) from exc
        data = response.json()
    return data if isinstance(data, dict) else {}


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _chat_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


__all__ = [
    "OpenAICompatibleEmbeddingGateway",
    "OpenAICompatibleLLMGateway",
]
