"""通用外部数据源 Gateway。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataSourceRequest(BaseModel):
    """一次外部数据源取数请求。"""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="数据源标识，如 xuezhi")
    query: str = Field(default="", description="查询词")
    context: dict[str, Any] = Field(
        default_factory=dict, description="调用方上下文，如画像字段快照"
    )
    limit: int = Field(default=5, ge=1, le=20)


class DataSourceRecord(BaseModel):
    """一条外部数据记录。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    title: str = ""
    text: str = ""
    source_url: str = ""
    fetched_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataSourceResult(BaseModel):
    """一次外部数据源取数结果。"""

    model_config = ConfigDict(extra="forbid")

    source: str
    records: list[DataSourceRecord] = Field(default_factory=list)
    degraded: bool = False
    errors: list[str] = Field(default_factory=list)


class DataSourceGateway(ABC):
    """外部数据源 Port。"""

    @abstractmethod
    async def fetch(self, request: DataSourceRequest) -> DataSourceResult:
        """按请求拉取数据。"""


__all__ = [
    "DataSourceGateway",
    "DataSourceRecord",
    "DataSourceRequest",
    "DataSourceResult",
]
