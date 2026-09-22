"""默认通过登录（DefaultPassAuth）。

第一期行为：任何请求都解析为同一个本地演示用户，不做真实凭证校验。
替换鉴权实现时，只需换掉本模块的实现并在 boot 里改装配。
"""

from __future__ import annotations

from typing import Any

from zhiyin_kernel.enums import UserRole
from zhiyin_kernel.errors import DuplicateResource
from zhiyin_data_sdk.gateways.security import AuthGateway, AuthPrincipal

# 演示用户 id，必须与演示数据（seed）保持一致
DEMO_USER_ID = "demo-user-0001"


class DefaultPassAuth(AuthGateway):
    """默认通过鉴权。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self, demo_user_id: str = DEMO_USER_ID) -> None:
        self._demo_user_id = demo_user_id
        # 演示实现也守「账号只能创建一次」：否则本地模式下注册路径
        # 会给出与真实实现不同的语义，本地跑通过的用例到了联调就翻车。
        self._registered: set[str] = set()

    async def authenticate(self, request: dict[str, Any]) -> AuthPrincipal:
        """恒返回演示用户。"""
        return AuthPrincipal(
            user_id=self._demo_user_id,
            role=UserRole.STUDENT,
            display_name="演示同学",
            is_guest=False,
            raw_claims={"auth": "default_pass", "demo": "true"},
        )

    async def is_authenticated(self, request: dict[str, Any]) -> bool:
        """第一期恒 True。"""
        return True

    async def issue_token(self, principal, *, ttl_s=None) -> str:
        """本地默认实现不签发真实令牌。"""
        return "demo-token"

    async def revoke_token(self, token: str) -> None:
        """本地默认实现无撤销语义。"""

    async def set_password(self, user_id: str, password: str) -> None:
        """本地默认实现不保存密码。"""

    async def create_password(self, user_id: str, password: str) -> None:
        """首次创建；重复创建要与真实实现一样抛冲突。"""
        if user_id in self._registered:
            raise DuplicateResource(f"账号已存在：{user_id}")
        self._registered.add(user_id)

    async def verify_password(self, user_id: str, password: str) -> bool:
        """本地默认实现恒通过。"""
        return True
