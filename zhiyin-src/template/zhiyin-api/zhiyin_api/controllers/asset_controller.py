"""资产与导出接口（R-API-005）。

资产接口必须返回版本与 diff，前端据此展示"因更新 X，v1→v2 的差异"。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from zhiyin_api.dto.asset import (
    ActionPlanView,
    ActionTaskDoneRequest,
    AssetVersionView,
    CalendarNodeView,
    DirectionPlanListView,
    ExportRequest,
    ExportResultView,
    ReportFullTextView,
)
from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.facade import get_facade
from zhiyin_kernel.enums import AssetType

router = APIRouter(tags=["asset"])


@router.get(
    "/app/assets/{asset_type}/versions",
    response_model=ApiResponse[list[AssetVersionView]],
)
async def list_asset_versions(
    request: Request, asset_type: AssetType
) -> ApiResponse[list[AssetVersionView]]:
    """资产历史版本列表，含 depends_on 与 diff。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_asset_versions(user_id, asset_type))


@router.get("/app/report/full-text", response_model=ApiResponse[ReportFullTextView])
async def get_report_full_text(
    request: Request, version: int | None = None
) -> ApiResponse[ReportFullTextView]:
    """完整报告页正文。只读资产版本，不重新生成。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.get_report_full_text(user_id, version))


@router.post("/app/assets/export", response_model=ApiResponse[ExportResultView])
async def export_asset(
    request: Request, body: ExportRequest
) -> ApiResponse[ExportResultView]:
    """导出资产。第一期仅预留入口，available 恒 False。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.export_asset(user_id, body))


# --------------------------------------------------------------------------
# ③ 决策 / ④ 行动
#
# 这两个环节的产出**也是资产**（direction_plan / action_plan），此前只有写没有读：
# 模型把三套方案与行动计划生成、落库、升版本，而界面上没有一条路径能把它们读出来 ——
# 于是"决策"与"行动"在用户看来是空的两步。这里补上读侧，以及用户对资产的两个动作
# （选方案 / 勾任务）。动作改的是**已有资产的状态**，不产生新版本。
# --------------------------------------------------------------------------


@router.get("/app/plan/directions", response_model=ApiResponse[DirectionPlanListView])
async def get_direction_plans(request: Request) -> ApiResponse[DirectionPlanListView]:
    """三套方向方案（主攻 / 平行 / 保底）+ 当前选中那一套。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.get_direction_plans(user_id))


@router.post(
    "/app/plan/directions/{option_id}/select",
    response_model=ApiResponse[DirectionPlanListView],
)
async def select_direction_plan(
    request: Request, option_id: str
) -> ApiResponse[DirectionPlanListView]:
    """选中一套方案。选择可撤回 —— 再选另一套就是撤回，没有单独的撤销接口。

    方案 id 不存在时按 1002（资源不存在）返回：前端据此如实说"这套方案已经不在了"，
    而不是把界面停在一个被选中的幽灵方案上。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.select_direction_plan(user_id, option_id))


@router.get("/app/plan/action", response_model=ApiResponse[ActionPlanView])
async def get_action_plan(request: Request) -> ApiResponse[ActionPlanView]:
    """行动计划正文（阶段 / 任务 / 现在这一件）。没有计划时 has_plan=False。"""
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.get_action_plan(user_id))


@router.patch("/app/plan/action/tasks", response_model=ApiResponse[ActionPlanView])
async def set_action_task_done(
    request: Request, body: ActionTaskDoneRequest
) -> ApiResponse[ActionPlanView]:
    """勾掉 / 取消勾选一个行动任务。

    `done=false` 是"勾错了要撤回"：只支持单向勾选的话，用户点错一次就再也回不去。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.set_action_task_done(user_id, body))


@router.get("/app/calendar", response_model=ApiResponse[list[CalendarNodeView]])
async def list_calendar_nodes(request: Request) -> ApiResponse[list[CalendarNodeView]]:
    """关键节点日历（④ 行动环节写进来的节点）。

    此前这张表**只写不读**：库里有节点，界面上没有任何一处能看到 ——
    "规划师写入、教练读取"里的"读取"那一半没有实现。
    """
    facade = get_facade()
    user_id = await facade.resolve_user_id(request)
    return ApiResponse(data=await facade.list_calendar_nodes(user_id))
