"""AI 配置必须真的由数据库承载。

这一组守卫对应一次真实的失败：`infra_ai_provider` / `infra_ai_model` /
`infra_ai_route` 三张表建好了、仓储也接上了，但**真正跑模型的那条路**
（Agno 运行时）直接从 `.env` 读密钥与模型名 —— 于是表一直是空的，
配置只活在环境变量里，"配置入库"是句空话。

守三层：
1. 表为空时按种子落库（第一次开机）；
2. 表有值之后**不再覆盖**（改库不会被 env 冲掉）；
3. 密钥的取值顺序：env 覆盖 > 库里的值。
"""

from __future__ import annotations

import pytest

from zhiyin_infrastructure.postgres.ai_config import (
    AiProvider,
    PostgresAiConfigRepository,
)


class _FakeDb:
    """够用的内存替身：只实现仓储用到的那几个方法。"""

    def __init__(self) -> None:
        self.providers: dict[str, dict] = {}
        self.models: dict[tuple[str, str], dict] = {}
        self.routes: dict[tuple[str, str, str], dict] = {}

    async def fetchval(self, query: str, *args):
        if "infra_ai_provider" in query:
            return len(self.providers)
        return 0

    async def execute(self, query: str, *args) -> str:
        if "infra_ai_provider" in query:
            _, code, name, protocol, base_url, api_key_env, enabled, config = args[:8]
            self.providers[code] = {
                "code": code, "name": name, "protocol": protocol,
                "base_url": base_url, "api_key_env": api_key_env,
                "enabled": enabled, "config": _load(config),
            }
        elif "infra_ai_model" in query:
            _, provider_code, model_code, display_name, capability, enabled = args[:6]
            self.models[(provider_code, model_code)] = {
                "provider_code": provider_code, "model_code": model_code,
                "display_name": display_name, "capability": capability,
                "enabled": enabled,
            }
        elif "infra_ai_route" in query:
            _, scene, provider_code, model_code, priority, enabled = args[:6]
            self.routes[(scene, provider_code, model_code)] = {
                "scene": scene, "provider_code": provider_code, "model_code": model_code,
                "priority": priority, "enabled": enabled,
            }
        return "OK"

    async def fetchrow(self, query: str, *args):
        if "infra_ai_provider" in query:
            return self.providers.get(args[0]) if self.providers else None
        if "infra_ai_model" in query:
            return self.models.get((args[0], args[1]))
        if "infra_ai_route" in query:
            for row in self.routes.values():
                if row["scene"] == args[0] and row["enabled"]:
                    return row
        return None

    async def fetch(self, query: str, *args):
        return list(self.routes.values())


def _load(raw):
    import json

    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _repo(db, *, key: str) -> PostgresAiConfigRepository:
    return PostgresAiConfigRepository(
        db,  # type: ignore[arg-type]
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        embedding_base_url="https://ark.example/api/v3",
        embedding_model="doubao-embedding",
        llm_api_key=key,
        embedding_api_key="",
    )


@pytest.mark.asyncio
async def test_empty_tables_get_seeded_with_the_api_key() -> None:
    """第一次开机：供应商 / 模型 / 路由都落库，**密钥也在库里**。"""
    db = _FakeDb()
    await _repo(db, key="sk-test-key").ensure_seeded()

    assert set(db.providers) == {"deepseek", "doubao"}
    assert db.providers["deepseek"]["config"]["api_key"] == "sk-test-key"
    assert ("deepseek", "deepseek-flash") in db.models
    assert ("llm", "deepseek", "deepseek-flash") in db.routes
    assert ("embedding", "doubao", "doubao-embedding") in db.routes


@pytest.mark.asyncio
async def test_existing_rows_are_never_overwritten_by_env() -> None:
    """表里已有值：env 只是种子，不许把库里的配置冲掉。"""
    db = _FakeDb()
    db.providers["deepseek"] = {
        "code": "deepseek", "name": "库里改过的名字", "protocol": "openai_chat",
        "base_url": "https://db.example", "api_key_env": "", "enabled": True,
        "config": {"api_key": "sk-from-db"},
    }
    await _repo(db, key="sk-from-env").ensure_seeded()

    assert db.providers["deepseek"]["base_url"] == "https://db.example"
    assert db.providers["deepseek"]["config"]["api_key"] == "sk-from-db"
    assert "doubao" not in db.providers, "已有配置时不该再种一遍"


@pytest.mark.asyncio
async def test_api_key_prefers_env_then_database(monkeypatch) -> None:
    """取值顺序：环境变量 > 库。默认 env 为空，所以库是权威。"""
    from zhiyin_infrastructure.ai.router import AiModelRouter

    class _Repo:
        async def get_route(self, scene):
            from zhiyin_infrastructure.postgres.ai_config import AiRoute

            return AiRoute(scene=scene, provider_code="deepseek", model_code="m1")

        async def get_provider(self, code):
            return AiProvider(
                code=code, name="x", protocol="openai_chat",
                base_url="https://db.example", api_key_env="ZHIYIN_TEST_KEY",
                config={"api_key": "sk-from-db"},
            )

        async def get_model(self, provider_code, model_code):
            from zhiyin_infrastructure.postgres.ai_config import AiModel

            return AiModel(provider_code=provider_code, model_code=model_code)

    monkeypatch.delenv("ZHIYIN_TEST_KEY", raising=False)
    resolved = await AiModelRouter(_Repo()).resolve("llm")  # type: ignore[arg-type]
    assert resolved is not None and resolved.api_key == "sk-from-db"
    assert resolved.base_url == "https://db.example"

    monkeypatch.setenv("ZHIYIN_TEST_KEY", "sk-from-env")
    resolved = await AiModelRouter(_Repo()).resolve("llm")  # type: ignore[arg-type]
    assert resolved is not None and resolved.api_key == "sk-from-env"
