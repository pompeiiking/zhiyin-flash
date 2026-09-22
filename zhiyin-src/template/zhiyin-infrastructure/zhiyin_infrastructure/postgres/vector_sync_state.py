"""向量同步去重状态。"""

from __future__ import annotations

from zhiyin_infrastructure.postgres.database import PostgresDatabase


class PostgresVectorSyncState:
    """记录每个文档最后一次同步的模型与内容哈希。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def needs_sync(
        self, source_id: str, *, model: str, content_hash: str
    ) -> bool:
        row = await self._db.fetchrow(
            """
            SELECT model, content_hash
            FROM infra_vector_sync_state
            WHERE source_id = $1
            """,
            source_id,
        )
        if row is None:
            return True
        return row["model"] != model or row["content_hash"] != content_hash

    async def mark_synced(
        self, source_id: str, *, model: str, content_hash: str
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO infra_vector_sync_state
                (source_id, model, content_hash, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (source_id) DO UPDATE SET
                model = EXCLUDED.model,
                content_hash = EXCLUDED.content_hash,
                updated_at = NOW()
            """,
            source_id,
            model,
            content_hash,
        )


__all__ = ["PostgresVectorSyncState"]
