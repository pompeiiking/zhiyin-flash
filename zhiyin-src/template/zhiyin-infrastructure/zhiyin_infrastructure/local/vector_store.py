"""本地内存向量库（LocalVectorStore）。

真实实现了 `VectorGateway` 的语义（命名空间隔离、按 id 覆盖、余弦相似度检索、
模型版本校验），只是把数据放在进程内存里 —— 与第一期其它 InMemory 实现同一口径。

注意它与 `LocalHashEmbedder` 的分工：库本身是可用实现（`wired`），
"嵌入质量不可用"这件事由嵌入实现的 `skeleton` 状态单独标注。这样
`/healthz` 能准确表达"链路通了、模型还没接"，而不是笼统地说没做好。

实现同一份契约，装配处改一行。
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from zhiyin_data_sdk.gateways.vector import VectorGateway, VectorHit, VectorRecord


class LocalVectorStore(VectorGateway):
    """进程内向量库。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self) -> None:
        # namespace → id → (record, model)
        self._items: dict[str, dict[str, tuple[VectorRecord, str]]] = {}

    async def upsert(
        self, namespace: str, records: Sequence[VectorRecord], *, model: str
    ) -> int:
        bucket = self._items.setdefault(namespace, {})
        for record in records:
            bucket[record.id] = (record.model_copy(deep=True), model)
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
        bucket = self._items.get(namespace, {})
        hits: list[VectorHit] = []
        for record, stored_model in bucket.values():
            # 换嵌入模型后旧向量与新向量不可比，直接跳过而不是给一个错的相似度。
            if stored_model != model:
                continue
            if filters and not _matches(record.metadata, filters):
                continue
            hits.append(
                VectorHit(
                    id=record.id,
                    score=_cosine(vector, record.vector),
                    text=record.text,
                    source_id=record.source_id,
                    metadata=dict(record.metadata),
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]

    async def delete(self, namespace: str, ids: Sequence[str]) -> int:
        bucket = self._items.get(namespace, {})
        removed = 0
        for item_id in ids:
            if bucket.pop(item_id, None) is not None:
                removed += 1
        return removed

    async def delete_by_source(self, namespace: str, source_id: str) -> int:
        bucket = self._items.get(namespace, {})
        removable = [
            item_id
            for item_id, (record, _) in bucket.items()
            if record.source_id == source_id
        ]
        for item_id in removable:
            bucket.pop(item_id, None)
        return len(removable)

    async def clear_namespace(self, namespace: str) -> None:
        self._items.pop(namespace, None)


def _matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(metadata.get(key) == value for key, value in filters.items())


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return dot / (norm_left * norm_right)


__all__ = ["LocalVectorStore"]
