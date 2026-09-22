"""AI 相关 Gateway：模型调用 / 嵌入 / 知识库检索 / 全文与向量检索。

第一期默认实现（见 zhiyin-infrastructure）：
- LLMGateway           → DeepSeekLLMGateway（真模型；本项目不提供 mock 产出）
- EmbedGateway         → LocalHashEmbedder（确定性伪向量，仅用于打通链路）
- KnowledgeGateway     → LocalKnowledgeRepo（本地 JSON）
- SearchGateway        → LocalKeywordSearch（简单关键词匹配）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    """一条模型消息。"""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(description="system / user / assistant")
    content: str


class LLMResult(BaseModel):
    """模型返回。

    structured 是产出契约校验前的原始结构化结果；校验由编排层 AgentEngine 完成，
    校验失败的降级策略由调用方决定。
    """

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    structured: Optional[dict[str, Any]] = None
    model: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    degraded: bool = Field(
        default=False, description="是否走了降级（模型不可用时返回固定结果）"
    )


class LLMGateway(ABC):
    """模型调用 Port。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        json_schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.2,
        timeout_s: float = 60.0,
    ) -> LLMResult:
        """发起一次对话补全。json_schema 非空时要求结构化输出。"""


class EmbedGateway(ABC):
    """文本嵌入 Port。

    独立于 LLMGateway 的原因：嵌入模型与生成模型是两条独立的技术链路
    （不同供应商、不同配额、不同版本策略），而且**向量库必须与嵌入模型同版本**
    （见 `gateways/vector.py` 的模型版本路由）。
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """当前嵌入模型标识。写入与检索向量时都要带上它。"""

    @abstractmethod
    async def embed(
        self, texts: list[str], *, timeout_s: float = 30.0
    ) -> list[list[float]]:
        """批量嵌入。返回顺序必须与入参一一对应（错位会让检索静默错乱）。"""


class KnowledgeHit(BaseModel):
    """知识库命中。"""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str = ""
    snippet: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGateway(ABC):
    """知识库检索 Port。用于给诊断 / 决策 / 行动供事实。"""

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        namespace: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[KnowledgeHit]:
        """按语义检索知识。namespace 如 profession / occupation / policy。"""


class SearchHit(BaseModel):
    """检索命中。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchGateway(ABC):
    """检索 Port。屏蔽关键词 / 向量 / 混合检索的差异（R-SDK-004）。"""

    @abstractmethod
    async def keyword(self, query: str, *, top_k: int = 10) -> list[SearchHit]:
        """关键词检索。"""

    @abstractmethod
    async def vector(
        self, embedding: list[float], *, top_k: int = 10
    ) -> list[SearchHit]:
        """向量检索。当前固定返回空列表，待自有检索实现补齐。"""

    @abstractmethod
    async def hybrid(self, query: str, *, top_k: int = 10) -> list[SearchHit]:
        """混合检索。第一期退化为关键词检索。"""
