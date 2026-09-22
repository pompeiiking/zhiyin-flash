"""用户自建内容接口（自建待办 / 写下的目标）。

调用链：Controller → Facade → UserNoteService → Repository。
本文件只接参数、包信封；"空内容不落库""重复不新增"这些判断在服务层，
不在接口层 —— 接口层一旦有判断，别的入口（对话里记一句）就会绕过它。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.note import NoteAck, NoteCreateRequest, NoteDoneRequest, NoteView
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["note"])


@router.get("/app/notes", response_model=ApiResponse[list[NoteView]])
async def list_notes(request: Request) -> ApiResponse[list[NoteView]]:
    """他写下的全部内容（新写的在前）。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_notes(user_id))


@router.post("/app/notes", response_model=ApiResponse[NoteView])
async def add_note(request: Request, body: NoteCreateRequest) -> ApiResponse[NoteView]:
    """写一条。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.add_note(user_id, body))


@router.patch("/app/notes/{note_id}", response_model=ApiResponse[NoteView])
async def set_note_done(
    request: Request, note_id: str, body: NoteDoneRequest
) -> ApiResponse[NoteView]:
    """勾掉 / 取消勾掉一条待办。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.set_note_done(user_id, note_id, body))


@router.delete("/app/notes/{note_id}", response_model=ApiResponse[NoteAck])
async def remove_note(request: Request, note_id: str) -> ApiResponse[NoteAck]:
    """删掉一条。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.remove_note(user_id, note_id))


__all__ = ["router"]
