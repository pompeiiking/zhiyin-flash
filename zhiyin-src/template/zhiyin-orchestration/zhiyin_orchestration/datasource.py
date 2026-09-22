"""外部数据源原语。

本层只定义通用取数操作；具体数据源由 data_sdk Gateway 实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from zhiyin_data_sdk.gateways.datasource import (
    DataSourceRecord,
    DataSourceRequest,
    DataSourceResult,
)


class ExternalDataSource(ABC):
    """通用外部数据源操作。"""

    @abstractmethod
    async def fetch(self, request: DataSourceRequest) -> DataSourceResult:
        """按来源、查询词与上下文取数。"""


__all__ = [
    "DataSourceRecord",
    "DataSourceRequest",
    "DataSourceResult",
    "ExternalDataSource",
]
