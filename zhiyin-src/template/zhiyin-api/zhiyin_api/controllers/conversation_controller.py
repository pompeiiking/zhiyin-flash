"""核心对话页接口（R-API-002 / R-API-003）。

调用链：Controller → Facade → Orchestrator.handle_message
（读黑板 → 环节判定 → 选主理 → 理论链产出 → 行为引导收尾）
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.conversation import (
    ConversationMessageView,
    ConversationTurnView,
    MessageRequest,
    SessionListView,
    TaskEnterRequest,
    TaskSessionView,
)
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["conversation"])


@router.get("/app/sessions", response_model=ApiResponse[SessionListView])
async def list_sessions(request: Request) -> ApiResponse[SessionListView]:
    """左栏会话列表（并行任务会话，按任务/环节命名）。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_sessions(user_id))


@router.get(
    "/app/sessions/{task_id}/turns",
    response_model=ApiResponse[list[ConversationMessageView]],
)
async def list_session_turns(
    request: Request, task_id: str, limit: int = 200
) -> ApiResponse[list[ConversationMessageView]]:
    """一条会话的逐轮原文。

    会话列表点进去要能看见"这条会话发生过什么" —— 此前只有一张清单，
    因为逐轮原文压根没落库（库里只有累积摘要）。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_session_turns(user_id, task_id, limit=limit))


@router.post("/app/task/enter", response_model=ApiResponse[TaskSessionView])
async def enter_task(
    request: Request, body: TaskEnterRequest
) -> ApiResponse[TaskSessionView]:
    """从首页任务入口进入微循环。

    编排器判定目标环节与主理；已存在进行中的同一任务时执行"续接"而非重建。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.enter_task(user_id, body))


@router.post("/app/conversation/message", response_model=ApiResponse[ConversationTurnView])
async def send_message(
    request: Request, body: MessageRequest
) -> ApiResponse[ConversationTurnView]:
    """发送一轮消息，返回最短结论 + 显式告知 + 行为引导 + 管线卡。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.send_message(user_id, body))
