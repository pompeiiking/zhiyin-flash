"""智能工作台接口（R-API-004）。

按 ①-⑤ 聚合返回活资产，不做实时对话。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.workspace import (
    AcademicImportAck,
    AcademicImportRequest,
    AcademicRevokeAck,
    IntelListView,
    WorkspacePageView,
)
from zhiyin_api.facade import get_facade

router = APIRouter(tags=["workspace"])


@router.get("/app/workspace", response_model=ApiResponse[WorkspacePageView])
async def get_workspace(request: Request) -> ApiResponse[WorkspacePageView]:
    """工作台聚合视图：画像 / 报告 / 方案 / 计划 / 跟踪 + 功能块。

    进入工作台属于持久化行为，游客在此处被登录拦截。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.get_workspace(user_id))


@router.post("/app/academic/import", response_model=ApiResponse[AcademicImportAck])
async def import_academic(
    request: Request, body: AcademicImportRequest
) -> ApiResponse[AcademicImportAck]:
    """导入课表与成绩单（学生自己贴原文）。

    这条路是产品有意选的：不做替学生登录学校系统，也不经手他校内账号的密码。
    用户的体验压在解析上 —— 贴进来的东西读不出来时，回执要说清楚**改哪里**。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.import_academic(user_id, body))


@router.delete("/app/academic", response_model=ApiResponse[AcademicRevokeAck])
async def revoke_academic(request: Request) -> ApiResponse[AcademicRevokeAck]:
    """清空导入的课表与成绩（画像里那两条摘要一起删）。

    只清快照不删摘要的话，采集清单会一直显示"课程表已拿到"，
    用户再也回不到导入入口 —— 那是"看起来清掉了"。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.revoke_academic(user_id))


async def _optional_user(request: Request) -> str | None:
    """**尽力**认人：认得出就个性化，认不出就按公开取数。

    情报这一层是爬公开数据的，登录态与"能看到哪些公开信息"本来就没有关系 ——
    所以这里吞掉鉴权失败，而不是把未登录的人挡在门外。
    """
    from zhiyin_kernel.errors import AccessDenied

    try:
        return await get_facade().resolve_user_id(request)
    except AccessDenied:
        return None


@router.get("/app/intel", response_model=ApiResponse[IntelListView])
async def get_intel(request: Request, q: str = "") -> ApiResponse[IntelListView]:
    """外部情报：公开事实（学职平台 + 通用网络检索）。

    **不要求登录**：登了录就按你的画像收窄，没登录就按 `?q=` 或平台通用数据取。
    每条都带来源链接 —— 这类信息"凭什么这么说"就是那个链接，
    所以取不到来源的条目在服务层就被丢掉了，不会返回。
    """
    facade = get_facade()
    user_id = await _optional_user(request)
    return ApiResponse(data=await facade.get_external_intel(user_id, topic=q))


@router.post("/app/intel/refresh", response_model=ApiResponse[IntelListView])
async def refresh_intel(request: Request, q: str = "") -> ApiResponse[IntelListView]:
    """现在去取一次（用户主动点）。同样**不要求登录**。

    只在这条路上推通知：后台顺带取到的东西不弹 ——
    浮窗要留给"值得打断他"的事，而"他自己刚点的"就是值得回一句的事。
    （未登录时没有收件人，自然也不推。）
    """
    facade = get_facade()
    user_id = await _optional_user(request)
    return ApiResponse(data=await facade.get_external_intel(user_id, topic=q, refresh=True))
