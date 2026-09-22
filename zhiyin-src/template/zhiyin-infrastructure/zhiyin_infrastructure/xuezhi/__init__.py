"""学职平台数据接入。"""

from zhiyin_infrastructure.xuezhi.client import XueZhiClient
from zhiyin_infrastructure.xuezhi.gateway import XueZhiDataSourceGateway

__all__ = [
    "XueZhiClient",
    "XueZhiDataSourceGateway",
]
