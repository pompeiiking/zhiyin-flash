"""身份服务实现：认证主体 → 本地用户记录补齐。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from zhiyin_business.ports.identity import IdentityService
from zhiyin_data_sdk.gateways.security import AuthGateway
from zhiyin_data_sdk.repositories import UserRepository
from zhiyin_kernel.enums import UserRole
from zhiyin_kernel.errors import AccessDenied, DuplicateResource
from zhiyin_kernel.identity import UserAccount


class DefaultIdentityService(IdentityService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, auth: AuthGateway, users: UserRepository) -> None:
        self._auth = auth
        self._users = users

    async def current_user(self, *, token: Optional[str] = None) -> UserAccount:
        request = {"token": token} if token else {}
        principal = await self._auth.authenticate(request)
        return await self._ensure(
            principal.user_id,
            nickname=principal.display_name or principal.user_id,
            role=principal.role,
            touch=True,
        )

    async def account(self, user_id: str) -> UserAccount:
        """按 id 取用户记录（已认证过的用户在这里不再走网关）。"""
        return await self._ensure(user_id, nickname=user_id, role=UserRole.STUDENT)

    async def _ensure(
        self,
        user_id: str,
        *,
        nickname: str,
        role: UserRole,
        touch: bool = False,
    ) -> UserAccount:
        """认证主体 → 本地用户记录：没有就建，有就返回（可选刷新最后登录时间）。"""
        user = await self._users.get_by_id(user_id)
        if user is None:
            user = await self._users.create(
                UserAccount(
                    id=user_id,
                    nickname=nickname,
                    role=role,
                    created_at=datetime.now(timezone.utc),
                )
            )
        elif touch:
            await self._users.touch_last_login(user_id, datetime.now(timezone.utc))
        return user

    async def login(self, account: str, password: str) -> dict:
        """账号密码登录：verify_password → issue_token → 补齐用户记录。"""
        verify = getattr(self._auth, "verify_password", None)
        issue = getattr(self._auth, "issue_token", None)
        if verify is None or issue is None:
            raise NotImplementedError("当前 AuthGateway 不支持账号密码登录")
        if not await verify(account, password):
            raise AccessDenied("账号或密码不正确")
        from zhiyin_data_sdk.gateways.security import AuthPrincipal
        from zhiyin_kernel.enums import UserRole

        token = await issue(AuthPrincipal(user_id=account, display_name=account, role=UserRole.STUDENT))
        await self.current_user(token=token)  # 补齐本地用户记录
        return {"token": token, "user_id": account, "role": "student"}

    async def register(self, account: str, password: str, nickname: str = "") -> str:
        """注册一个**新**账号。

        两件事必须同时成立，缺一就是账号接管漏洞：

        1. 先看账号是否已存在 —— 给出「账号已存在」而不是静默成功；
        2. 写密码时走 `create_password`（只创建、不覆盖），而不是 `set_password`
           （它带 `ON CONFLICT DO UPDATE`，用于「重置」）。

        第 1 条负责可读的报错，第 2 条负责并发下也**不可能**覆盖既有凭据 ——
        只靠第 1 条会有 TOCTOU 竞态。守卫见 `tests/test_auth_register.py`。
        """
        create_password = getattr(self._auth, "create_password", None)
        if create_password is None:
            raise NotImplementedError("当前 AuthGateway 不支持注册")
        if await self._users.get_by_id(account) is not None:
            raise DuplicateResource(f"账号已存在：{account}")
        # 真正的互斥在实现里（插入即冲突检测）；这里的检查只为了更早、更好读的报错。
        await create_password(account, password)
        # 只补本地用户记录。**不再顺带 login 一次**：那会白签一个永远不会被返回的
        # 令牌，并在 infra_auth_session 里留下孤儿会话（Controller 随后还会再签一个）。
        await self._ensure(
            account,
            nickname=nickname or account,
            role=UserRole.STUDENT,
        )
        return account


__all__ = ["DefaultIdentityService"]
