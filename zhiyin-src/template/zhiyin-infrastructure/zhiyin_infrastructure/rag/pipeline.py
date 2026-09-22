"""最小可用的 RAG 管线实现。"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_data_sdk.gateways.ai import EmbedGateway, LLMGateway, LLMMessage
from zhiyin_data_sdk.gateways.vector import VectorGateway, VectorRecord


class RagHit(BaseModel):
    """一次向量检索命中。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    score: float = 0.0
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagResult(BaseModel):
    """一次 RAG 问答结果。"""

    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[RagHit] = Field(default_factory=list)
    answer: str = ""
    model: str = ""
    degraded: bool = False


class RagPipeline:
    """文本切块 → 嵌入 → 向量检索 → 上下文问答。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        embedding: EmbedGateway,
        vectors: VectorGateway,
        llm: Optional[LLMGateway] = None,
        chunk_size: int = 400,
        chunk_overlap: int = 80,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须为正数")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")
        self._embedding = embedding
        self._vectors = vectors
        self._llm = llm
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embedding_degraded = (
            getattr(type(embedding), "IMPLEMENTATION_STATUS", "wired") == "skeleton"
        )

    @property
    def model_id(self) -> str:
        return self._embedding.model_id

    async def resolve_model_id(self) -> str:
        resolver = getattr(self._embedding, "resolve_model_id", None)
        if callable(resolver):
            return await resolver()
        return self._embedding.model_id

    async def index_text(
        self,
        namespace: str,
        doc_id: str,
        text: str,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """把一个文档切块、嵌入并写入向量库。"""
        chunks = _split_text(text, self._chunk_size, self._chunk_overlap)
        if not chunks:
            return 0
        vectors = await self._embedding.embed(chunks)
        records = [
            VectorRecord(
                id=f"{doc_id}::{index}",
                vector=vector,
                text=chunk,
                source_id=doc_id,
                metadata={
                    **(metadata or {}),
                    "doc_id": doc_id,
                    "chunk_index": index,
                },
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        await self._vectors.delete_by_source(namespace, doc_id)
        return await self._vectors.upsert(
            namespace, records, model=self._embedding.model_id
        )

    async def retrieve(
        self, namespace: str, query: str, *, top_k: int = 5
    ) -> list[RagHit]:
        """按查询文本检索上下文。"""
        vectors = await self._embedding.embed([query])
        if not vectors:
            return []
        hits = await self._vectors.search(
            namespace,
            vectors[0],
            model=self._embedding.model_id,
            top_k=top_k,
        )
        return [
            RagHit(
                id=hit.id,
                text=hit.text,
                score=hit.score,
                source_id=hit.source_id,
                metadata=hit.metadata,
            )
            for hit in hits
        ]

    async def answer(
        self,
        namespace: str,
        query: str,
        *,
        top_k: int = 5,
        timeout_s: float = 60.0,
    ) -> RagResult:
        """检索上下文并调用 LLM 生成回答。"""
        hits = await self.retrieve(namespace, query, top_k=top_k)
        if self._llm is None:
            return RagResult(query=query, hits=hits, degraded=True)

        context = "\n\n".join(
            f"[{index}] {hit.text}" for index, hit in enumerate(hits, start=1)
        )
        result = await self._llm.chat(
            [
                LLMMessage(
                    role="system",
                    content=(
                        "你只能依据给定上下文回答。上下文没有的信息必须明确说"
                        "“上下文未提供”，不要编造。回答保持简洁。"
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=f"上下文：\n{context}\n\n问题：{query}",
                ),
            ],
            temperature=0.0,
            timeout_s=timeout_s,
        )
        return RagResult(
            query=query,
            hits=hits,
            answer=result.text,
            model=result.model,
            degraded=result.degraded or self._embedding_degraded,
        )


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end >= len(normalized):
            break
        start += step
    return chunks


__all__ = ["RagHit", "RagPipeline", "RagResult"]
