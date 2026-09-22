"""外部数据源原语实现：委托给 data_sdk Gateway。"""

from __future__ import annotations

from zhiyin_data_sdk.gateways.datasource import (
    DataSourceGateway,
    DataSourceRequest,
    DataSourceResult,
)
from zhiyin_orchestration.datasource import ExternalDataSource


class GatewayDataSource(ExternalDataSource):
    """把通用取数操作落到数据源 Gateway。"""

    def __init__(self, gateway: DataSourceGateway) -> None:
        self._gateway = gateway

    async def fetch(self, request: DataSourceRequest) -> DataSourceResult:
        return await self._gateway.fetch(request)


__all__ = ["GatewayDataSource"]
