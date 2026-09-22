"""PostgreSQL AI 配置 Repository。"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_infrastructure.postgres.database import PostgresDatabase


class AiProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    protocol: str
    base_url: str = ""
    api_key_env: str = ""
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class AiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_code: str
    model_code: str
    display_name: str = ""
    capability: str = "chat"
    enabled: bool = True


class AiRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: str
    provider_code: str
    model_code: str
    priority: int = 100
    enabled: bool = True


class PostgresAiConfigRepository:
    """AI 供应商 / 模型 / 路由配置。

    这里是 AI 配置的**唯一权威来源**。`.env` 只在第一次开机时充当种子：
    表一旦有了值，之后就以表为准 —— 改配置改库，迁移只搬库，
    换一台机器不需要再对一遍 `.env`。

    密钥也入库（`config.api_key`）。这是刻意的取舍：
    密钥留在 `.env` 里，"配置已入库"就是假的 —— 迁移时照样要人肉搬一次，
    而且只有一台机器知道真正在跑的是什么。`api_key_env` 字段保留成
    **可选覆盖**：某些部署（CI / 临时容器）宁愿用环境变量注入密钥，
    那时把 `api_key_env` 填上即可，它优先于库里的值。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        llm_base_url: str,
        llm_model: str,
        embedding_base_url: str,
        embedding_model: str,
        llm_api_key: str = "",
        embedding_api_key: str = "",
    ) -> None:
        self._db = database
        self._llm_base_url = llm_base_url
        self._llm_model = llm_model
        self._embedding_base_url = embedding_base_url
        self._embedding_model = embedding_model
        # 只在第一次开机（表为空）时写进去，之后不再覆盖
        self._llm_api_key = llm_api_key
        self._embedding_api_key = embedding_api_key
        self._seeded = False
        self._lock = asyncio.Lock()

    async def get_route(self, scene: str) -> Optional[AiRoute]:
        await self.ensure_seeded()
        row = await self._db.fetchrow(
            """
            SELECT scene, provider_code, model_code, priority, enabled
            FROM infra_ai_route
            WHERE scene = $1 AND enabled = TRUE
            ORDER BY priority ASC
            LIMIT 1
            """,
            scene,
        )
        return _route(row) if row else None

    async def get_provider(self, code: str) -> Optional[AiProvider]:
        await self.ensure_seeded()
        row = await self._db.fetchrow(
            """
            SELECT code, name, protocol, base_url, api_key_env, enabled, config
            FROM infra_ai_provider WHERE code = $1
            """,
            code,
        )
        return _provider(row) if row else None

    async def get_model(self, provider_code: str, model_code: str) -> Optional[AiModel]:
        await self.ensure_seeded()
        row = await self._db.fetchrow(
            """
            SELECT provider_code, model_code, display_name, capability, enabled
            FROM infra_ai_model
            WHERE provider_code = $1 AND model_code = $2
            """,
            provider_code,
            model_code,
        )
        return _model(row) if row else None

    async def list_routes(self) -> list[AiRoute]:
        await self.ensure_seeded()
        rows = await self._db.fetch(
            """
            SELECT scene, provider_code, model_code, priority, enabled
            FROM infra_ai_route ORDER BY scene, priority
            """
        )
        return [_route(row) for row in rows]

    async def ensure_seeded(self) -> None:
        """表为空时用当前配置种一遍；已有值就什么都不做。

        公开出来是给**启动流程**调的：配置必须在服务开始接请求之前就落库，
        否则"库里有什么"取决于谁先调了一次模型 —— 这中间的时间差里，
        这套配置实际上还活在进程内存和 `.env` 里。
        """
        if self._seeded:
            return
        async with self._lock:
            if self._seeded:
                return
            count = await self._db.fetchval("SELECT COUNT(*) FROM infra_ai_provider")
            if int(count or 0) > 0:
                self._seeded = True
                return
            await self._upsert_provider(
                AiProvider(
                    code="deepseek",
                    name="DeepSeek",
                    protocol="openai_chat",
                    base_url=self._llm_base_url,
                    api_key_env="ZHIYIN_LLM_API_KEY",
                    config=({"api_key": self._llm_api_key} if self._llm_api_key else {}),
                )
            )
            await self._upsert_model(
                AiModel(
                    provider_code="deepseek",
                    model_code=self._llm_model,
                    display_name="DeepSeek Flash",
                    capability="chat",
                )
            )
            await self._upsert_route(
                AiRoute(
                    scene="llm",
                    provider_code="deepseek",
                    model_code=self._llm_model,
                )
            )
            await self._upsert_provider(
                AiProvider(
                    code="doubao",
                    name="豆包 Ark",
                    protocol="openai_embeddings",
                    base_url=self._embedding_base_url,
                    api_key_env="ZHIYIN_EMBEDDING_API_KEY",
                    config=(
                        {"api_key": self._embedding_api_key}
                        if self._embedding_api_key
                        else {}
                    ),
                )
            )
            await self._upsert_model(
                AiModel(
                    provider_code="doubao",
                    model_code=self._embedding_model,
                    display_name="豆包 Embedding",
                    capability="embedding",
                )
            )
            await self._upsert_route(
                AiRoute(
                    scene="embedding",
                    provider_code="doubao",
                    model_code=self._embedding_model,
                )
            )
            self._seeded = True

    async def _upsert_provider(self, provider: AiProvider) -> None:
        await self._db.execute(
            """
            INSERT INTO infra_ai_provider
                (id, code, name, protocol, base_url, api_key_env, enabled, config, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                protocol = EXCLUDED.protocol,
                base_url = EXCLUDED.base_url,
                api_key_env = EXCLUDED.api_key_env,
                enabled = EXCLUDED.enabled,
                config = EXCLUDED.config,
                updated_at = NOW()
            """,
            f"provider_{provider.code}",
            provider.code,
            provider.name,
            provider.protocol,
            provider.base_url,
            provider.api_key_env,
            provider.enabled,
            _json(provider.config),
        )

    async def _upsert_model(self, model: AiModel) -> None:
        await self._db.execute(
            """
            INSERT INTO infra_ai_model
                (id, provider_code, model_code, display_name, capability, enabled, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (provider_code, model_code) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                capability = EXCLUDED.capability,
                enabled = EXCLUDED.enabled,
                updated_at = NOW()
            """,
            f"model_{model.provider_code}_{model.model_code}",
            model.provider_code,
            model.model_code,
            model.display_name,
            model.capability,
            model.enabled,
        )

    async def _upsert_route(self, route: AiRoute) -> None:
        await self._db.execute(
            """
            INSERT INTO infra_ai_route
                (id, scene, provider_code, model_code, priority, enabled,
                 updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (scene, provider_code, model_code) DO UPDATE SET
                priority = EXCLUDED.priority,
                enabled = EXCLUDED.enabled,
                updated_at = NOW()
            """,
            f"route_{route.scene}_{route.provider_code}_{route.model_code}",
            route.scene,
            route.provider_code,
            route.model_code,
            route.priority,
            route.enabled,
        )


def _provider(row: Any) -> AiProvider:
    return AiProvider(
        code=row["code"],
        name=row["name"],
        protocol=row["protocol"],
        base_url=row["base_url"],
        api_key_env=row["api_key_env"],
        enabled=row["enabled"],
        config=_load_json(row["config"]),
    )


def _model(row: Any) -> AiModel:
    return AiModel(
        provider_code=row["provider_code"],
        model_code=row["model_code"],
        display_name=row["display_name"],
        capability=row["capability"],
        enabled=row["enabled"],
    )


def _route(row: Any) -> AiRoute:
    return AiRoute(
        scene=row["scene"],
        provider_code=row["provider_code"],
        model_code=row["model_code"],
        priority=row["priority"],
        enabled=row["enabled"],
    )


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _load_json(value: Any) -> dict[str, Any]:
    import json

    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


__all__ = ["AiModel", "AiProvider", "AiRoute", "PostgresAiConfigRepository"]

