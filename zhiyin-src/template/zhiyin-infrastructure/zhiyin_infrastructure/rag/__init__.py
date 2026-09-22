"""基础设施层 RAG 管线。

职责边界：切块、嵌入、向量写入、向量检索、上下文拼装与模型调用。
不承载职引业务语义。
"""

from zhiyin_infrastructure.rag.pipeline import RagHit, RagPipeline, RagResult
from zhiyin_infrastructure.rag.documents import (
    JsonKnowledgeDocumentSource,
    KnowledgeDocument,
)
from zhiyin_infrastructure.rag.knowledge import VectorKnowledgeGateway
from zhiyin_infrastructure.rag.search import VectorSearchGateway

__all__ = [
    "JsonKnowledgeDocumentSource",
    "KnowledgeDocument",
    "RagHit",
    "RagPipeline",
    "RagResult",
    "VectorKnowledgeGateway",
    "VectorSearchGateway",
]
