"""知识检索的诚实性守卫：嵌入器是骨架时不许返回"看起来像命中"的内容。

为什么值得单守
--------------
本地哈希伪嵌入能把 RAG 链路跑通，但向量之间没有语义 ——
`ORDER BY embedding <=> query` 排出来的是随机次序。把它当依据喂给模型，
模型会一脸认真地引用一条不相干的职业或理论，而**从输出上看不出来**。

这条守卫钉住三件事：

1. `IMPLEMENTATION_STATUS != "wired"` 的嵌入器 → 检索返回空，且**不碰向量库**；
2. 真嵌入（wired）→ 照常检索，最后仍然按 `top_k` 收口；
3. 没有 `IMPLEMENTATION_STATUS` 属性的实现当作 wired（不误伤第三方实现）。
"""

from __future__ import annotations

from typing import Any

import pytest

from zhiyin_data_sdk.gateways.ai import EmbedGateway, KnowledgeHit
from zhiyin_data_sdk.gateways.vector import VectorGateway, VectorHit
from zhiyin_infrastructure.rag.knowledge import VectorKnowledgeGateway


class _Embedding(EmbedGateway):
    """可控的嵌入器：`status` 决定它是不是骨架。"""

    def __init__(
        self, status: str | None = "wired", dim: int = 4, *, fails: bool = False
    ) -> None:
        self.IMPLEMENTATION_STATUS = status  # type: ignore[assignment]
        self._dim = dim
        self._fails = fails
        self.calls = 0

    @property
    def status(self) -> str | None:
        return self.IMPLEMENTATION_STATUS

    @property
    def model_id(self) -> str:
        return "test-model"

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self._fails:
            raise RuntimeError("embedding 服务不可达（模拟 Ollama 没开）")
        return [[0.1] * self._dim for _ in texts]


class _Vectors(VectorGateway):
    def __init__(self, *, fails: bool = False) -> None:
        self.calls = 0
        self._fails = fails

    async def upsert(self, namespace: str, items: Any) -> int:  # pragma: no cover
        return 0

    async def search(
        self,
        namespace: str,
        vector: list[float],
        *,
        model: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        self.calls += 1
        if self._fails:
            raise RuntimeError("向量库不可达")
        return [
            VectorHit(
                id=f"d{i}",
                source_id=f"d{i}",
                text=f"片段 {i}",
                score=1.0 - i * 0.1,
                metadata={},
            )
            for i in range(top_k)
        ]

    async def delete(self, namespace: str, ids: list[str]) -> int:  # pragma: no cover
        return 0

    async def delete_by_source(self, namespace: str, source_id: str) -> int:  # pragma: no cover
        return 0

    async def clear_namespace(self, namespace: str) -> None:  # pragma: no cover
        return None


@pytest.mark.asyncio
async def test_skeleton_embedder_makes_search_return_nothing() -> None:
    """骨架嵌入器 → 返回空，而且**不去查向量库**（查了也只能是随机序）。"""
    embedding = _Embedding(status="skeleton")
    vectors = _Vectors()
    gateway = VectorKnowledgeGateway(embedding=embedding, vectors=vectors)

    assert await gateway.search("霍兰德是什么") == []
    assert vectors.calls == 0, "骨架嵌入器下不应该去查向量库"


@pytest.mark.asyncio
async def test_wired_embedder_still_searches() -> None:
    """真嵌入照常检索 —— 这条守卫不能把正常路径一起挡掉。"""
    embedding = _Embedding(status="wired")
    vectors = _Vectors()
    gateway = VectorKnowledgeGateway(embedding=embedding, vectors=vectors)

    hits = await gateway.search("霍兰德是什么", top_k=3)
    assert len(hits) == 3
    assert all(isinstance(hit, KnowledgeHit) for hit in hits)
    assert vectors.calls == 1 and embedding.calls == 1


@pytest.mark.asyncio
async def test_implementation_without_status_is_treated_as_wired() -> None:
    """没声明状态的实现按 wired 处理：不误伤接入方自己的实现。"""
    embedding = _Embedding(status=None)
    vectors = _Vectors()
    gateway = VectorKnowledgeGateway(embedding=embedding, vectors=vectors)

    assert await gateway.search("霍兰德", top_k=2)
    assert vectors.calls == 1


@pytest.mark.asyncio
async def test_embedding_failure_degrades_to_empty() -> None:
    """嵌入服务不可达 → 本轮按"没有依据"处理，不把整轮对话打挂。

    本机 Ollama 没开、云端配额用完、网络断，都属于这一种：检索只是给答案补依据，
    不是主链路。界面上是"这次没有依据"，日志里有原因。
    """
    gateway = VectorKnowledgeGateway(
        embedding=_Embedding(fails=True), vectors=_Vectors()
    )
    assert await gateway.search("霍兰德是什么") == []


@pytest.mark.asyncio
async def test_vector_store_failure_degrades_to_empty() -> None:
    """向量库不可达同样降级为空，而不是抛给调用方。"""
    gateway = VectorKnowledgeGateway(
        embedding=_Embedding(), vectors=_Vectors(fails=True)
    )
    assert await gateway.search("霍兰德是什么") == []
