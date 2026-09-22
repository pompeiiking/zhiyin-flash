"""向量检索 Gateway。

为什么现在就要有这个契约
------------------------
检索路径设计（纯向量 / 混合 / 降级）与 `embed_task` / `retrieval_log`
都要挂在一个向量 Port 上。此前 SDK 只有
`SearchGateway.vector(embedding)` 一个孤立的查询方法，没有写入与删除，也没有
模型版本路由是必须保留的契约。

三个不可省略的约定
------------------
1. **namespace 必填**：一期就把"专业库 / 职业库 / 岗位库 / 知识库"分开，
   避免第二期再补命名空间维度（键：`profession` / `occupation` / `job` / `policy`）。
2. **模型版本路由**：向量必须由指定的 embedding 模型产出。写入与检索都必须带上
   `model`，否则换了嵌入模型后新旧向量会混在一个空间里比较，检索结果静默变差。
3. **来源可溯**：命中必须能回到原始文档（`source_id` + `metadata`），
   报告引用要能标出处（R-CRAWL-006）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field


class VectorRecord(BaseModel):
    """一条待写入的向量记录。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="记录 id，通常与源文档 id 一致，便于覆盖重建")
    vector: list[float] = Field(description="嵌入向量")
    text: str = Field(default="", description="原始文本片段，用于回填与展示")
    source_id: str = Field(default="", description="来源文档 id，供报告溯源")
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorHit(BaseModel):
    """一次向量检索命中。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    score: float = 0.0
    text: str = ""
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorGateway(ABC):
    """向量库 Port（写入 / 检索 / 删除）。"""

    @abstractmethod
    async def upsert(
        self, namespace: str, records: Sequence[VectorRecord], *, model: str
    ) -> int:
        """写入或覆盖向量，返回写入条数。同 id 覆盖，保证可重复执行（幂等）。"""

    @abstractmethod
    async def search(
        self,
        namespace: str,
        vector: Sequence[float],
        *,
        model: str,
        top_k: int = 10,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[VectorHit]:
        """按向量相似度检索。`model` 必须与写入时一致。"""

    @abstractmethod
    async def delete(self, namespace: str, ids: Sequence[str]) -> int:
        """按 id 删除，返回删除条数。"""

    @abstractmethod
    async def delete_by_source(self, namespace: str, source_id: str) -> int:
        """按来源文档删除全部 chunk，用于文档重建与删除。"""

    @abstractmethod
    async def clear_namespace(self, namespace: str) -> None:
        """清空一个命名空间，用于"重建索引"这类运维动作。"""


__all__ = ["VectorGateway", "VectorHit", "VectorRecord"]
