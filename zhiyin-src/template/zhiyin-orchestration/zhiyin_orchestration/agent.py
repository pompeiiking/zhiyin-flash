"""Agent 原语：按 agentId + 上下文 + 产出契约调用模型能力，并校验产出契约。

通用性要求：本模块只认识 agent_id、上下文 JSON、JSON Schema，
不认识"建档分析师""采集环节"等业务语义。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentRequest(BaseModel):
    """一次智能体调用请求。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    stage: Optional[str] = Field(
        default=None, description="通用阶段标识，取值由业务层决定；编排层不解释其含义"
    )
    prompt_code: Optional[str] = Field(
        default=None,
        description=(
            "指定提示词条目（按 code 取，如 AI 任务的 task.brief.today）；"
            "为空时按 (agent_id, stage) 取角色提示词"
        ),
    )
    use_tools: bool = Field(
        default=True,
        description=(
            "是否按注册表白名单挂工具。生成类 AI 任务默认不挂（上下文一次备齐、"
            "产出要可复现）；需要自己去取数的任务显式置 True。"
        ),
    )
    blackboard: dict[str, Any] = Field(
        default_factory=dict, description="共享状态快照（已序列化）"
    )
    prompt_vars: dict[str, Any] = Field(
        default_factory=dict, description="提示词变量（画像 JSON、知识检索结果等）"
    )
    output_schema: Optional[dict[str, Any]] = Field(
        default=None, description="产出契约的 JSON Schema，非空则强校验"
    )
    trace_id: Optional[str] = None


class AgentResult(BaseModel):
    """一次智能体调用结果。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    structured: dict[str, Any] = Field(default_factory=dict)
    raw_text: str = ""
    model: str = ""
    valid: bool = Field(default=False, description="是否通过产出契约校验")
    errors: list[str] = Field(default_factory=list)
    degraded: bool = Field(default=False)


class AgentEngine(ABC):
    """智能体引擎 Port。"""

    @abstractmethod
    async def invoke(self, request: AgentRequest) -> AgentResult:
        """调用智能体。实现内部走 LLMGateway，并在返回前完成契约校验。"""
