"""学信网在线验证报告核验。

入口只有两个：`ChsiReportClient`（取数与解析）与
`OnlineVerificationGateway`（实现 data_sdk 的核验契约）。
"""

from zhiyin_infrastructure.chsi.client import ChsiReportClient
from zhiyin_infrastructure.chsi.gateway import OnlineVerificationGateway

__all__ = [
    "ChsiReportClient",
    "OnlineVerificationGateway",
]
