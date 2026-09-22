"""安全与限流的 no-op 实现。

不做加密 / 脱敏 / 限流；接口保留，替换时只换实现。
审计走日志而不是 `print`：`print` 只到标准输出、带不上时间与级别，
出事时既搜不到也留不住。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from zhiyin_data_sdk.gateways.security import RateLimitGateway, SecurityGateway

logger = logging.getLogger(__name__)


class NoopSecurity(SecurityGateway):
    """不加密、不脱敏、仅打印审计日志。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data

    def mask(self, value: str, *, kind: str = "generic") -> str:
        return value

    def audit(self, record: dict[str, Any]) -> None:
        logger.info("审计：%s", record)


class NoopRateLimit(RateLimitGateway):
    """恒放行。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def allow(
        self, key: str, *, limit: Optional[int] = None, window_s: Optional[float] = None
    ) -> bool:
        return True
