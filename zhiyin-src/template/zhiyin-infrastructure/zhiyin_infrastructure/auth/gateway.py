"""基于 JWT + PostgreSQL + Redis 的鉴权实现。"""

from __future__ import annotations

import hashlib
import hmac
import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import jwt

from zhiyin_data_sdk.gateways.cache import CacheGateway
from zhiyin_data_sdk.gateways.security import AuthGateway, AuthPrincipal
from zhiyin_kernel.enums import UserRole
from zhiyin_kernel.errors import AccessDenied, DuplicateResource, InvalidRequest
from zhiyin_infrastructure.postgres.database import PostgresDatabase

_REVOKED_NAMESPACE = "auth_revoked"
_PASSWORD_ITERATIONS = 390000
logger = logging.getLogger(__name__)


class JwtAuthGateway(AuthGateway):
    """JWT 鉴权实现。

    令牌本身无状态；登录会话和撤销状态落 PostgreSQL，撤销标记缓存到 Redis。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        cache: Optional[CacheGateway] = None,
        secret: str,
        algorithm: str = "HS256",
        issuer: str = "zhiyin-flash",
        ttl_s: int = 86400,
    ) -> None:
        if not secret:
            raise ValueError("auth secret 不能为空")
        self._db = database
        self._cache = cache
        self._secret = secret
        self._algorithm = algorithm
        self._issuer = issuer
        self._ttl_s = ttl_s

    async def authenticate(self, request: dict[str, Any]) -> AuthPrincipal:
        token = _extract_token(request)
        if not token:
            raise AccessDenied("缺少登录令牌")
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            raise AccessDenied("登录令牌无效") from exc

        session_id = str(claims.get("jti") or "")
        user_id = str(claims.get("sub") or "")
        if not session_id or not user_id:
            raise AccessDenied("登录令牌缺少主体信息")

        if self._cache is not None:
            try:
                revoked = await self._cache.get(_REVOKED_NAMESPACE, session_id)
                if revoked == "1":
                    raise AccessDenied("登录令牌已撤销")
            except AccessDenied:
                raise
            except Exception:
                logger.warning("鉴权撤销缓存不可用，回退到 PostgreSQL 会话判断")

        session = await self._db.fetchrow(
            """
            SELECT revoked_at, expires_at, token_hash
            FROM infra_auth_session
            WHERE id = $1 AND user_id = $2
            """,
            session_id,
            user_id,
        )
        if session is None or session["revoked_at"] is not None:
            raise AccessDenied("登录会话不存在或已撤销")
        if session["expires_at"] <= datetime.now(timezone.utc):
            raise AccessDenied("登录会话已过期")
        if not hmac.compare_digest(session["token_hash"], _token_hash(token)):
            raise AccessDenied("登录令牌与会话不匹配")

        return AuthPrincipal(
            user_id=user_id,
            role=UserRole(str(claims.get("role") or UserRole.STUDENT.value)),
            display_name=str(claims.get("name") or ""),
            is_guest=bool(claims.get("is_guest", False)),
            raw_claims=dict(claims),
        )

    async def is_authenticated(self, request: dict[str, Any]) -> bool:
        try:
            await self.authenticate(request)
        except Exception:
            return False
        return True

    async def issue_token(
        self, principal: AuthPrincipal, *, ttl_s: Optional[int] = None
    ) -> str:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_s or self._ttl_s)
        session_id = uuid4().hex
        claims = {
            "sub": principal.user_id,
            "role": principal.role.value,
            "name": principal.display_name,
            "is_guest": principal.is_guest,
            "iss": self._issuer,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": session_id,
        }
        token = jwt.encode(claims, self._secret, algorithm=self._algorithm)
        await self._db.execute(
            """
            INSERT INTO infra_auth_session
                (id, user_id, token_hash, expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            session_id,
            principal.user_id,
            _token_hash(token),
            expires_at,
            now,
        )
        return token

    async def revoke_token(self, token: str) -> None:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                options={"verify_exp": False},
            )
        except jwt.PyJWTError:
            return
        session_id = str(claims.get("jti") or "")
        if not session_id:
            return
        await self._db.execute(
            """
            UPDATE infra_auth_session
            SET revoked_at = NOW()
            WHERE id = $1 AND revoked_at IS NULL
            """,
            session_id,
        )
        if self._cache is not None:
            exp = int(claims.get("exp") or 0)
            ttl = max(exp - int(datetime.now(timezone.utc).timestamp()), 1)
            try:
                await self._cache.set(_REVOKED_NAMESPACE, session_id, "1", ttl_s=ttl)
            except Exception:
                logger.warning("撤销缓存写入失败，已由 PostgreSQL 会话状态兜底")

    async def set_password(self, user_id: str, password: str) -> None:
        if not password:
            raise InvalidRequest("密码不能为空")
        salt = secrets.token_hex(16)
        password_hash = await asyncio.to_thread(
            _password_hash, password, salt, _PASSWORD_ITERATIONS
        )
        await self._db.execute(
            """
            INSERT INTO infra_auth_credential
                (user_id, password_hash, password_salt, iterations, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                password_salt = EXCLUDED.password_salt,
                iterations = EXCLUDED.iterations,
                updated_at = NOW()
            """,
            user_id,
            password_hash,
            salt,
            _PASSWORD_ITERATIONS,
        )

    async def create_password(self, user_id: str, password: str) -> None:
        """首次设置密码：冲突即拒，绝不覆盖既有凭据。

        用 `ON CONFLICT DO NOTHING + RETURNING` 在**一条语句**里完成
        「不存在则创建、已存在则失败」——「先 SELECT 再 INSERT」在并发注册下
        两个请求会同时通过检查，后一个仍然覆盖前一个的密码。
        """
        if not user_id:
            raise InvalidRequest("账号不能为空")
        if not password:
            raise InvalidRequest("密码不能为空")
        salt = secrets.token_hex(16)
        password_hash = await asyncio.to_thread(
            _password_hash, password, salt, _PASSWORD_ITERATIONS
        )
        created = await self._db.fetchval(
            """
            INSERT INTO infra_auth_credential
                (user_id, password_hash, password_salt, iterations, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id) DO NOTHING
            RETURNING user_id
            """,
            user_id,
            password_hash,
            salt,
            _PASSWORD_ITERATIONS,
        )
        if not created:
            raise DuplicateResource(f"账号已存在：{user_id}")

    async def verify_password(self, user_id: str, password: str) -> bool:
        row = await self._db.fetchrow(
            """
            SELECT password_hash, password_salt, iterations
            FROM infra_auth_credential
            WHERE user_id = $1
            """,
            user_id,
        )
        if row is None:
            return False
        expected = row["password_hash"]
        actual = await asyncio.to_thread(
            _password_hash, password, row["password_salt"], row["iterations"]
        )
        return hmac.compare_digest(expected, actual)


def _extract_token(request: dict[str, Any]) -> str:
    token = str(request.get("token") or "").strip()
    if token:
        return token
    header = request.get("authorization") or request.get("Authorization") or ""
    headers = request.get("headers")
    if not header and isinstance(headers, dict):
        header = headers.get("authorization") or headers.get("Authorization") or ""
    header = str(header).strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _password_hash(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()


__all__ = ["JwtAuthGateway"]
