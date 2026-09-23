"""核心对话页接口（R-API-002 / R-API-003）。

调用链：Controller → Facade → Orchestrator.handle_message
（读黑板 → 环节判定 → 选主理 → 理论链产出 → 行为引导收尾）
"""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.conversation import (
    ConversationMessageView,
    ConversationMaterialView,
    ConversationTurnView,
    MessageRequest,
    SessionListView,
    TaskEnterRequest,
    TaskSessionView,
)
from zhiyin_api.facade import get_facade
from zhiyin_kernel.errors import InvalidRequest

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


"""一份材料的体积上限（2 MB）。

对话里交的多是简历、证书、导出的表格 —— 几十 KB 到几百 KB。到 MB 量级多半是
"另存了一整页"或传错了文件，而且它要作为模型输入的一部分，太长的东西放进去
只会把这一轮淹掉。超了如实说，让他截取相关内容再传。
"""
_MAX_MATERIAL_BYTES = 2_000_000


@router.post("/app/conversation/material", response_model=ApiResponse[ConversationMaterialView])
async def upload_material(request: Request, file: UploadFile = File(...)) -> ApiResponse[ConversationMaterialView]:
    """交一份材料（multipart 上传）。

    为什么材料要**上传**而不是在浏览器里读成文本再塞进消息：

    · 编码（教务/办公软件导出的 GBK 文本）与二进制格式都由服务端统一处理，
      浏览器那一侧不做第二份解码实现；
    · 正文不进对话气泡 —— 回执只有"它是什么"，正文留在服务端、只在用到它的
      那一轮进模型输入。

    读不出来的原因（Excel / 空文件）由文档抽取重载成一句用户能照做的话，
    这一层只负责限大小。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    data = await _read_material(file)
    return ApiResponse(data=await facade.upload_material(user_id, name=file.filename or "", data=data))


async def _read_material(file: UploadFile) -> bytes:
    """读文件字节。多读一个字节用来判断"超没超"，因此超限时不会截断。"""
    data = await file.read(_MAX_MATERIAL_BYTES + 1)
    label = file.filename or "这个文件"
    if len(data) > _MAX_MATERIAL_BYTES:
        raise InvalidRequest(
            f"「{label}」超过 2MB —— 对话里交的材料请截取相关的那一段，"
            "或者只传这件事用得上的部分。"
        )
    if not data:
        raise InvalidRequest(f"「{label}」是空的，换一份再试。")
    return data
