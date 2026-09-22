"""运行时配置仓储（`infra_runtime_config`）。

这张表一直空着、也没有消费者 —— 建了没用起来。它该装的是**运维口径的配置**：
不属于业务数据（用户画像那些）、也不属于动态资源（菜单文案那些），
但换一台机器必须一起搬走。装配报告的"能力位归属"和"分级门禁"就是典型：
它们以前各自是一个 JSON 文件，**运行时直接读文件**，不搬文件就丢配置。

值整体存 JSONB：这些配置本来就是结构化的文档，
拆成列反而会逼着代码去认识它们的内部形状。
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from zhiyin_infrastructure.postgres.database import PostgresDatabase


class PostgresRuntimeConfigRepository:
    """键值型运行时配置。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get(self, key: str) -> Optional[Any]:
        row = await self._db.fetchrow(
            "SELECT value FROM infra_runtime_config WHERE key = $1", key
        )
        if row is None:
            return None
        return _loads(row["value"])

    async def put(self, key: str, value: Any, *, description: str = "") -> None:
        await self._db.execute(
            """
            INSERT INTO infra_runtime_config (key, value, description, updated_at)
            VALUES ($1, $2::jsonb, $3, NOW())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                description = EXCLUDED.description,
                updated_at = NOW()
            """,
            key,
            json.dumps(value, ensure_ascii=False),
            description,
        )

    async def ensure_seeded(self, seeds: Iterable[tuple[str, Any, str]]) -> None:
        """表里没有的键才写入 —— 已有值**永不覆盖**。

        和 AI 配置同一个口径：`.env` / 文件只是**首次种子**，
        之后以库为准。反过来（每次启动都用文件覆盖）等于把文件又变成了权威，
        改了库重启就丢。
        """
        for key, value, description in seeds:
            existing = await self._db.fetchval(
                "SELECT COUNT(*) FROM infra_runtime_config WHERE key = $1", key
            )
            if int(existing or 0) > 0:
                continue
            await self.put(key, value, description=description)


def _loads(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


__all__ = ["PostgresRuntimeConfigRepository"]
