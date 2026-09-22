"""基于 pgvector 的检索实现（关键词 / 向量 / 混合）。"""

from __future__ import annotations

from zhiyin_data_sdk.gateways.ai import (
    EmbedGateway,
    SearchGateway,
    SearchHit,
)
from zhiyin_data_sdk.gateways.vector import VectorGateway
from zhiyin_infrastructure.local.knowledge import LocalKeywordSearch


class VectorSearchGateway(SearchGateway):
    """关键词检索 + pgvector 向量检索。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        embedding: EmbedGateway,
        vectors: VectorGateway,
        data_dir: str,
        namespace: str = "knowledge",
    ) -> None:
        self._embedding = embedding
        self._vectors = vectors
        self._keyword = LocalKeywordSearch(data_dir)
        self._namespace = namespace

    async def keyword(self, query: str, *, top_k: int = 10) -> list[SearchHit]:
        return await self._keyword.keyword(query, top_k=top_k)

    async def vector(
        self, embedding: list[float], *, top_k: int = 10
    ) -> list[SearchHit]:
        hits = await self._vectors.search(
            self._namespace,
            embedding,
            model=self._embedding.model_id,
            top_k=top_k,
        )
        return [
            SearchHit(
                id=hit.source_id or hit.id,
                content=hit.text,
                score=hit.score,
                metadata=hit.metadata,
            )
            for hit in hits
        ]

    async def hybrid(self, query: str, *, top_k: int = 10) -> list[SearchHit]:
        keyword_hits = await self.keyword(query, top_k=top_k)
        vectors = await self._embedding.embed([query])
        if not vectors:
            return keyword_hits
        vector_hits = await self.vector(vectors[0], top_k=top_k)
        return _merge_hits(keyword_hits, vector_hits, top_k)


def _merge_hits(
    keyword_hits: list[SearchHit], vector_hits: list[SearchHit], top_k: int
) -> list[SearchHit]:
    """RRF 融合，避免关键词计分与余弦相似度量纲不可比。"""
    scores: dict[str, float] = {}
    original: dict[str, SearchHit] = {}
    for hits in (keyword_hits, vector_hits):
        deduped: dict[str, SearchHit] = {}
        for hit in hits:
            deduped.setdefault(hit.id, hit)
        for rank, hit in enumerate(deduped.values(), start=1):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (60 + rank)
            original.setdefault(hit.id, hit)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [
        original[item_id].model_copy(update={"score": score})
        for item_id, score in ordered[:top_k]
    ]


__all__ = ["VectorSearchGateway"]
