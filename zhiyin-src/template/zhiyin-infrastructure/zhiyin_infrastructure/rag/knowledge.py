"""基于向量库的知识检索实现。

一条硬规矩：**嵌入器是骨架时，检索如实返回空**。

本地哈希伪嵌入（`LocalHashEmbedder`，`IMPLEMENTATION_STATUS = "skeleton"`）能把链路
跑通，但向量之间没有语义：`ORDER BY embedding <=> query` 排出来的是随机次序。
把它当知识喂给模型，模型会一本正经地引用一条不相干的职业或理论 ——
那比"这次没检索到"糟得多，而且从输出上看不出来。

所以这里按项目一贯的口径处理：**宁可如实说没有，也不端出看起来对的内容**。
`/healthz` 里 `embedding=skeleton` 与这里返回空是同一件事的两种表述，
配上日志里那句原因，排查时不会误以为"知识库是空的"。

同理，**嵌入服务不可达时也返回空**：本机 Ollama 没开、云端配额用完、网络断，
都不该让用户那一轮对话整体失败 —— 检索只是给答案补依据，不是主链路。
失败会连同原因进日志（`WARNING`），排查时看得见；界面拿到的是"这次没有依据"，
而不是一个假装有依据的答案。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from zhiyin_data_sdk.gateways.ai import EmbedGateway, KnowledgeGateway, KnowledgeHit
from zhiyin_data_sdk.gateways.vector import VectorGateway

logger = logging.getLogger(__name__)


class VectorKnowledgeGateway(KnowledgeGateway):
    """把查询嵌入后用 pgvector 检索知识。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        embedding: EmbedGateway,
        vectors: VectorGateway,
        default_namespace: str = "knowledge",
    ) -> None:
        self._embedding = embedding
        self._vectors = vectors
        self._default_namespace = default_namespace

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        namespace: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[KnowledgeHit]:
        if getattr(self._embedding, "IMPLEMENTATION_STATUS", "wired") == "skeleton":
            logger.warning(
                "知识检索跳过：嵌入器还是骨架（%s，model=%s）——"
                "哈希伪向量的相似度没有语义，返回的是随机排序。"
                "配好真嵌入（见 /healthz 的 gateways.embedding）即自动恢复。",
                type(self._embedding).__name__,
                getattr(self._embedding, "model_id", "?"),
            )
            return []
        try:
            vectors = await self._embedding.embed([query])
        except Exception as exc:  # noqa: BLE001 - 检索降级为空，原因进日志
            logger.warning("知识检索失败，本轮按“没有依据”处理：%s", exc)
            return []
        if not vectors:
            return []
        try:
            hits = await self._vectors.search(
                namespace or self._default_namespace,
                vectors[0],
                model=self._embedding.model_id,
                top_k=top_k,
                filters=filters,
            )
        except Exception as exc:  # noqa: BLE001 - 同上
            logger.warning("向量库检索失败，本轮按“没有依据”处理：%s", exc)
            return []
        return [
            KnowledgeHit(
                doc_id=hit.source_id or hit.id,
                title=str(hit.metadata.get("title") or hit.metadata.get("name") or ""),
                snippet=hit.text,
                score=hit.score,
                metadata=hit.metadata,
            )
            for hit in hits
        ]


__all__ = ["VectorKnowledgeGateway"]
