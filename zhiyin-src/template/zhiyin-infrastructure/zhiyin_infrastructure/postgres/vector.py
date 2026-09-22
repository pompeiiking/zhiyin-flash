"""PostgreSQL + pgvector 向量存储实现。"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from zhiyin_data_sdk.gateways.vector import VectorGateway, VectorHit, VectorRecord
from zhiyin_infrastructure.postgres.database import PostgresDatabase, get_database


class PostgresVectorGateway(VectorGateway):
    """基于 pgvector 的向量检索实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, dsn: str, *, database: Optional[PostgresDatabase] = None) -> None:
        self._database = database or get_database(dsn)

    async def upsert(
        self, namespace: str, records: Sequence[VectorRecord], *, model: str
    ) -> int:
        if not records:
            return 0
        dimensions = {len(record.vector) for record in records}
        if len(dimensions) != 1:
            raise ValueError("同一批向量必须使用相同维度")
        dimension = dimensions.pop()
        if dimension <= 0:
            raise ValueError("向量维度必须为正数")
        existing_dimension = await self._database.fetchval(
            """
            SELECT vector_dims(embedding) FROM vec_record
            WHERE namespace = $1 AND model = $2
            LIMIT 1
            """,
            namespace,
            model,
        )
        if existing_dimension is not None and int(existing_dimension) != dimension:
            raise ValueError(
                f"向量维度与模型不匹配：existing={existing_dimension}, incoming={dimension}"
            )
        async with (await self._database.pool()).acquire() as connection:
            async with connection.transaction():
                for record in records:
                    await connection.execute(
                        """
                        INSERT INTO vec_record
                            (namespace, id, model, embedding, text, source_id, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                        ON CONFLICT (namespace, id) DO UPDATE SET
                            model = EXCLUDED.model,
                            embedding = EXCLUDED.embedding,
                            text = EXCLUDED.text,
                            source_id = EXCLUDED.source_id,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                        """,
                        namespace,
                        record.id,
                        model,
                        list(record.vector),
                        record.text,
                        record.source_id,
                        _json(record.metadata),
                    )
        return len(records)

    async def search(
        self,
        namespace: str,
        vector: Sequence[float],
        *,
        model: str,
        top_k: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[VectorHit]:
        if not vector:
            return []
        existing_dimension = await self._database.fetchval(
            """
            SELECT vector_dims(embedding) FROM vec_record
            WHERE namespace = $1 AND model = $2
            LIMIT 1
            """,
            namespace,
            model,
        )
        if existing_dimension is not None and int(existing_dimension) != len(vector):
            return []
        query = """
            SELECT id, text, source_id, metadata,
                   1 - (embedding <=> $1) AS score
            FROM vec_record
            WHERE namespace = $2 AND model = $3
              AND ($4::jsonb IS NULL OR metadata @> $4::jsonb)
            ORDER BY embedding <=> $1
            LIMIT $5
        """
        rows = await self._database.fetch(
            query,
            list(vector),
            namespace,
            model,
            _json(filters) if filters else None,
            top_k,
        )
        return [
            VectorHit(
                id=row["id"],
                score=float(row["score"] or 0.0),
                text=row["text"] or "",
                source_id=row["source_id"] or "",
                metadata=_load_json(row["metadata"]),
            )
            for row in rows
        ]

    async def delete(self, namespace: str, ids: Sequence[str]) -> int:
        if not ids:
            return 0
        result = await self._database.execute(
            "DELETE FROM vec_record WHERE namespace = $1 AND id = ANY($2::text[])",
            namespace,
            list(ids),
        )
        return _rowcount(result)

    async def delete_by_source(self, namespace: str, source_id: str) -> int:
        result = await self._database.execute(
            "DELETE FROM vec_record WHERE namespace = $1 AND source_id = $2",
            namespace,
            source_id,
        )
        return _rowcount(result)

    async def clear_namespace(self, namespace: str) -> None:
        await self._database.execute(
            "DELETE FROM vec_record WHERE namespace = $1", namespace
        )

def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _rowcount(result: str) -> int:
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


__all__ = ["PostgresVectorGateway"]
