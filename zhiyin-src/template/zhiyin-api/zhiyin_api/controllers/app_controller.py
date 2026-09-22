"""启动与身份入口（R-API-001 / R-API-008）。

第一期鉴权为"默认通过"：由 Facade 注入的 AuthGateway 返回本地演示用户，
后续替换真实鉴权时本文件不需要改动。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from zhiyin_api.dto.bootstrap import BootstrapView, TheoryCardView
from zhiyin_api.dto.bootstrap import PortalView
from zhiyin_api.dto.common import ApiResponse, CoachNotificationView
from zhiyin_api.facade import get_facade
from zhiyin_kernel.errors import ResourceNotFound

router = APIRouter(tags=["app"])


@router.get("/app/portal", response_model=ApiResponse[PortalView])
async def portal() -> ApiResponse[PortalView]:
    """门户内容 —— **公开接口，不解析身份**。

    门户是访客第一眼看到的那一页，内容全是产品自己的话（文案 / 信任块 / 横幅 /
    FAQ / 任务入口 / 开关）。它不需要知道"你是谁"，所以这里不调
    `resolve_user_id` —— 那是全站唯一一个不要求登录的业务读接口。

    为什么要开这个口子：门户文案此前写死在前端 `data/portal.ts`，
    改一句主张要发一次前端版本 —— 那是本仓"文案不进代码"这条底线上的最后一处例外。
    """
    facade = get_facade()
    return ApiResponse(data=await facade.get_portal())


@router.get("/app/bootstrap", response_model=ApiResponse[BootstrapView])
async def bootstrap(request: Request) -> ApiResponse[BootstrapView]:
    """启动装配：菜单 / 路由 / 任务入口 / 文案 / 功能开关。

    前端启动只请求一次即可渲染首页。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.bootstrap(user_id))


@router.get("/app/notifications/pending", response_model=ApiResponse[list[CoachNotificationView]])
async def list_pending_notifications(request: Request) -> ApiResponse[list[CoachNotificationView]]:
    """教练主动介入通知出队（前端浮窗轮询消费）。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_pending_notifications(user_id))


@router.post("/app/notifications/{message_id}/read", response_model=ApiResponse[dict])
async def mark_notification_read(request: Request, message_id: str) -> ApiResponse[dict]:
    """把一条通知标成已读。

    浮窗关掉时前端调它。不调的话，读侧按"未读"出队，用户下次进页面
    还会看到同一条 —— "我明明关过"就是这么来的。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    ok = await facade.mark_notification_read(user_id, message_id)
    return ApiResponse(data={"read": ok})


@router.get("/app/theory-cards/{theory_id}", response_model=ApiResponse[TheoryCardView])
async def get_theory_card(request: Request, theory_id: str) -> ApiResponse[TheoryCardView]:
    """理论卡正文：点开理论标签时拉一次。

    内容是**动态资源**（`data/registry/theory_cards.json`），改它不发版。
    取不到按 1002（资源不存在）返回 —— 前端据此如实说"这张卡还没配"，
    而不是渲染一张只有标题的空卡（那看起来像加载失败）。
    """
    facade = get_facade()
    await facade.resolve_user_id(request)
    card = await facade.get_theory_card(theory_id)
    if card is None:
        raise ResourceNotFound(f"理论卡不存在：{theory_id}")
    return ApiResponse(data=card)
