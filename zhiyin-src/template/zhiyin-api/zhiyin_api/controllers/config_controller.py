"""动态配置的重载入口。

配置在**启动时读一次**，之后只在收到这里的指令时再读 —— 见
`zhiyin_kernel.dynamic_config`。不做"每次请求读库"，因为那样
"刚才还好的行为突然变了"会变得无从解释（没人会想到是有人在改配置）。

这是个运维动作，不是普通用户接口。当前是单机本地部署，所以只要求已登录；
多用户之前必须先有管理员角色（`UserRole.ADMIN` 已定义，但还没有地方签发）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["config"])


@router.post("/app/config/reload", response_model=ApiResponse[dict])
async def reload_config(request: Request) -> ApiResponse[dict[str, Any]]:
    """重新装载动态配置（环节口径 / 气泡编排 / 采集规则）。"""
    facade = get_facade()
    await facade.resolve_user_id(request)  # 需要登录；未登录由统一错误码拦下
    return ApiResponse(data=await facade.reload_dynamic_config())


__all__ = ["router"]
