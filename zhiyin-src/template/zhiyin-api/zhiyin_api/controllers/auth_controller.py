"""鉴权端点：注册 / 登录 / 登出 / 当前用户。

登录后前端把 `token` 放进 `Authorization: Bearer <token>`；
未携带 token 访问业务端点 → 身份服务抛 PermissionError → 统一映射
ErrorCode.UNAUTHORIZED(1004)，由前端引导到登录页。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from zhiyin_api.dto.common import ApiResponse, ErrorCode
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["auth"])


class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str = Field(min_length=2, max_length=64, description="账号（即用户 ID）")
    password: str = Field(min_length=6, max_length=128)


class LoginResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    user_id: str
    role: str


@router.post("/app/auth/register", response_model=ApiResponse[LoginResult])
async def register(body: AuthRequest) -> ApiResponse[LoginResult]:
    """注册并直接登录（返回 token）。"""
    facade = get_facade()
    try:
        await facade.register_account(body.account, body.password)
        result = await facade.login_account(body.account, body.password)
    except ValueError as exc:
        return ApiResponse(code=ErrorCode.CONFLICT, message=str(exc), data=None)
    except PermissionError as exc:
        return ApiResponse(code=ErrorCode.UNAUTHORIZED, message=str(exc), data=None)
    return ApiResponse(data=result)


@router.post("/app/auth/login", response_model=ApiResponse[LoginResult])
async def login(body: AuthRequest) -> ApiResponse[LoginResult]:
    """账号密码登录，签发 JWT。"""
    facade = get_facade()
    try:
        result = await facade.login_account(body.account, body.password)
    except LookupError as exc:
        return ApiResponse(code=ErrorCode.NOT_FOUND, message=str(exc), data=None)
    except PermissionError as exc:
        return ApiResponse(code=ErrorCode.UNAUTHORIZED, message=str(exc), data=None)
    return ApiResponse(data=result)


@router.post("/app/auth/logout", response_model=ApiResponse[dict])
async def logout(request: Request) -> ApiResponse[dict]:
    """登出：撤销当前令牌（吊销表落库）。"""
    facade = get_facade()
    token = (request.headers.get("Authorization", "").removeprefix("Bearer ").strip()) or None
    if token:
        revoke = getattr(facade, "revoke_token", None)
        if revoke is not None:
            await revoke(token)
    return ApiResponse(data={"logged_out": True})


__all__ = ["router"]
