"""AI 模型路由：按场景选择 provider / model。"""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel, ConfigDict

from zhiyin_infrastructure.postgres.ai_config import PostgresAiConfigRepository


class ResolvedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: str
    provider_code: str
    model_code: str
    base_url: str
    api_key: str
    protocol: str


class AiModelRouter:
    """从 PostgreSQL 路由表解析模型配置。

    密钥的取值顺序：**环境变量优先，其次库里的值**。
    反过来的话，"库里那份"会永远赢，运维就没法用环境变量临时覆盖
    （CI、临时容器、本地调试都想改一下就跑）；
    而默认情况下环境变量是空的，所以库仍然是权威来源。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, repository: PostgresAiConfigRepository) -> None:
        self._repository = repository

    async def resolve(self, scene: str) -> Optional[ResolvedModel]:
        route = await self._repository.get_route(scene)
        if route is None:
            return None
        provider = await self._repository.get_provider(route.provider_code)
        model = await self._repository.get_model(route.provider_code, route.model_code)
        if provider is None or model is None or not provider.enabled or not model.enabled:
            return None
        api_key = ""
        if provider.api_key_env:
            api_key = os.getenv(provider.api_key_env, "").strip()
        if not api_key:
            api_key = str(provider.config.get("api_key", "") or "").strip()
        if not api_key:
            return None
        return ResolvedModel(
            scene=scene,
            provider_code=provider.code,
            model_code=model.model_code,
            base_url=provider.base_url,
            api_key=api_key,
            protocol=provider.protocol,
        )


__all__ = ["AiModelRouter", "ResolvedModel"]
