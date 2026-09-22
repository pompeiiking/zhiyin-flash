"""埋点上报接口（决策 14：前端通道只负责纯体验型事件）。

调用链：Controller → Facade.track_event（校验事件归属 + 落库口径待实现）。
本文件只接参数、包信封，不写任何事件归属判断。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.track import TrackEventAck, TrackEventRequest
from zhiyin_api.dto.asset import TrackEventView
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["track"])


@router.post("/app/track", response_model=ApiResponse[TrackEventAck])
async def track_event(
    request: Request, body: TrackEventRequest
) -> ApiResponse[TrackEventAck]:
    """前端上报一条埋点事件。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.track_event(user_id, body))


@router.get("/app/track/events", response_model=ApiResponse[list[TrackEventView]])
async def list_track_events(
    request: Request, limit: int = 50
) -> ApiResponse[list[TrackEventView]]:
    """跟踪时间线（复盘环节的载体）。

    与 `/app/track` 是同一份数据的两个方向：那条写（前端埋点），这条读。
    复盘页要回答"这段时间发生过什么"，靠的就是它 —— 此前只有写、没有读。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_track_events(user_id, limit=limit))


__all__ = ["router"]
