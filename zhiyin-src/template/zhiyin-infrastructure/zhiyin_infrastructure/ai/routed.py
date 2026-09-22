"""按数据库路由表动态选择模型的包装 Gateway。"""

from __future__ import annotations

import logging
from typing import Any, Optional

from zhiyin_data_sdk.gateways.ai import EmbedGateway, LLMGateway, LLMMessage, LLMResult
from zhiyin_infrastructure.ai.deepseek import DeepSeekLLMGateway
from zhiyin_infrastructure.ai.doubao import DoubaoEmbeddingGateway
from zhiyin_infrastructure.ai.router import AiModelRouter

logger = logging.getLogger(__name__)


class RoutedLLMGateway(LLMGateway):
    """每次调用按 `llm` 场景路由；路由不可用时回落到默认实现。"""

    def __init__(self, router: AiModelRouter, default: LLMGateway) -> None:
        self._router = router
        self._default = default
        self._cache: dict[tuple[str, str, str, str], LLMGateway] = {}

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.2,
        timeout_s: float = 60.0,
    ) -> LLMResult:
        gateway = await self._resolve()
        return await gateway.chat(
            messages,
            json_schema=json_schema,
            temperature=temperature,
            timeout_s=timeout_s,
        )

    async def _resolve(self) -> LLMGateway:
        try:
            resolved = await self._router.resolve("llm")
        except Exception:
            logger.exception("LLM 路由解析失败，回落到默认模型")
            return self._default
        if resolved is None or resolved.protocol != "openai_chat":
            return self._default
        key = (
            resolved.provider_code,
            resolved.model_code,
            resolved.base_url,
            resolved.api_key,
        )
        gateway = self._cache.get(key)
        if gateway is None:
            gateway = DeepSeekLLMGateway(
                api_key=resolved.api_key,
                base_url=resolved.base_url,
                model=resolved.model_code,
            )
            self._cache[key] = gateway
        return gateway


class RoutedEmbeddingGateway(EmbedGateway):
    """每次调用按 `embedding` 场景路由；路由不可用时回落到默认实现。"""

    def __init__(self, router: AiModelRouter, default: EmbedGateway) -> None:
        self._router = router
        self._default = default
        self._cache: dict[tuple[str, str, str, str], EmbedGateway] = {}
        self._active_model_id = default.model_id

    @property
    def model_id(self) -> str:
        return self._active_model_id

    async def embed(
        self, texts: list[str], *, timeout_s: float = 30.0
    ) -> list[list[float]]:
        gateway = await self._resolve()
        return await gateway.embed(texts, timeout_s=timeout_s)

    async def _resolve(self) -> EmbedGateway:
        try:
            resolved = await self._router.resolve("embedding")
        except Exception:
            logger.exception("Embedding 路由解析失败，回落到默认模型")
            self._active_model_id = self._default.model_id
            return self._default
        if resolved is None or resolved.protocol != "openai_embeddings":
            self._active_model_id = self._default.model_id
            return self._default
        key = (
            resolved.provider_code,
            resolved.model_code,
            resolved.base_url,
            resolved.api_key,
        )
        gateway = self._cache.get(key)
        if gateway is None:
            gateway = DoubaoEmbeddingGateway(
                api_key=resolved.api_key,
                base_url=resolved.base_url,
                model=resolved.model_code,
            )
            self._cache[key] = gateway
        self._active_model_id = resolved.model_code
        return gateway

    async def resolve_model_id(self) -> str:
        """显式解析当前路由模型，避免调用顺序影响 model_id。"""
        await self._resolve()
        return self._active_model_id


__all__ = ["RoutedEmbeddingGateway", "RoutedLLMGateway"]
