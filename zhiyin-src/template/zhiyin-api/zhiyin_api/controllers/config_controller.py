"""动态配置的重载入口。

配置在**启动时读一次**，之后只在收到这里的指令时再读 —— 见
`zhiyin_kernel.dynamic_config`。不做"每次请求读库"，因为那样
"刚才还好的行为突然变了"会变得无从解释（没人会想到是有人在改配置）。

这是个运维动作，按数据库中的当前管理员身份校验。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.facade import get_facade
from zhiyin_api.controllers.module_controller import platform, token

router = APIRouter(tags=["config"])


@router.post("/app/config/reload", response_model=ApiResponse[dict])
async def reload_config(request: Request) -> ApiResponse[dict[str, Any]]:
    """重新装载动态配置（环节口径 / 气泡编排 / 采集规则）。"""
    facade = get_facade()
    await platform(request).require(token(request), admin=True)
    return ApiResponse(data=await facade.reload_dynamic_config())


__all__ = ["router"]
