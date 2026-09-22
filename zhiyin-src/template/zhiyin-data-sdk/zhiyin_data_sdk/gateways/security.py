"""鉴权 / 安全 / 限流 Gateway —— 第一期的"默认通过层"。

第一期约束：
- AuthGateway       → DefaultPassAuth：固定演示用户，不校验真实凭证
- SecurityGateway   → NoopSecurity：不加密、不脱敏、不审计
- RateLimitGateway  → NoopRateLimit：恒放行

替换真实实现（JWT / 加密 / 限流）时只替换 Adapter，不改业务代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import UserRole


class AuthPrincipal(BaseModel):
    """已认证主体。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    role: UserRole = UserRole.STUDENT
    display_name: str = ""
    is_guest: bool = False
    raw_claims: dict[str, Any] = Field(default_factory=dict)


class AuthGateway(ABC):
    """鉴权 Port。"""

    @abstractmethod
    async def authenticate(self, request: dict[str, Any]) -> AuthPrincipal:
        """从请求中解析身份。第一期返回固定演示用户。"""

    @abstractmethod
    async def is_authenticated(self, request: dict[str, Any]) -> bool:
        """是否已认证。"""

    @abstractmethod
    async def issue_token(
        self, principal: AuthPrincipal, *, ttl_s: Optional[int] = None
    ) -> str:
        """签发登录令牌。"""

    @abstractmethod
    async def revoke_token(self, token: str) -> None:
        """撤销登录令牌。"""

    @abstractmethod
    async def create_password(self, user_id: str, password: str) -> None:
        """**首次**设置密码；账号已存在时抛 `DuplicateResource`，绝不覆盖。

        与 `set_password` 的分工必须保留：

        - 这条是「创建」，注册路径走它 —— 否则「重复注册」会变成
          「把别人的密码改掉」，任何人只要知道账号名就能接管账号；
        - `set_password` 是「设置 / 重置」，只允许在已确认身份之后调用。

        「先查再写」会有 TOCTOU 竞态（两个并发注册同时通过存在性检查），
        所以实现必须用「插入即冲突检测」（`ON CONFLICT DO NOTHING` + 影响行数），
        而不是在实现里另做一次 `SELECT`。
        """

    @abstractmethod
    async def set_password(self, user_id: str, password: str) -> None:
        """设置 / 重置用户密码（允许覆盖）。注册路径不要用它。"""

    @abstractmethod
    async def verify_password(self, user_id: str, password: str) -> bool:
        """校验用户密码。"""


class SecurityGateway(ABC):
    """安全 Port。第一期全部 no-op。"""

    @abstractmethod
    def encrypt(self, data: bytes) -> bytes:
        """加密。第一期原样返回。"""

    @abstractmethod
    def decrypt(self, data: bytes) -> bytes:
        """解密。第一期原样返回。"""

    @abstractmethod
    def mask(self, value: str, *, kind: str = "generic") -> str:
        """脱敏。第一期原样返回。"""

    @abstractmethod
    def audit(self, record: dict[str, Any]) -> None:
        """审计。第一期仅本地日志。"""


class RateLimitGateway(ABC):
    """限流 Port。第一期恒放行。"""

    @abstractmethod
    def allow(
        self, key: str, *, limit: Optional[int] = None, window_s: Optional[float] = None
    ) -> bool:
        """是否放行。第一期恒 True。"""
