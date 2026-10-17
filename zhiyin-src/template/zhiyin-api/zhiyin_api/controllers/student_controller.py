"""学生工作台的持久交互接口；身份全部来自当前令牌。"""

from datetime import date
from fastapi import APIRouter, Request
from zhiyin_api.dto.common import ApiResponse
from zhiyin_api.dto.asset import ActionPlanView
from zhiyin_api.dto.conversation import ConversationTurnView
from zhiyin_api.dto.student import (
    NotificationStateView,
    ReviewListView,
    ReviewRecordView,
    MeasurementListView,
    MeasurementRecordView,
    DirectionComparisonView,
    WorkloadView,
    AssetSnapshotView,
)
from zhiyin_api.dto.mappers import action_plan_view
from zhiyin_api.facade import get_facade
from zhiyin_business.contracts.student import (
    TaskEdit,
    PhaseEdit,
    Preferences,
    Semester,
    ReviewEdit,
    NotificationEdit,
    MeasurementEdit,
    DirectionWeights,
    PreferencesEdit,
    SemesterEdit,
    DirectionWeightsEdit,
)

router = APIRouter(tags=["student-capabilities"])


@router.get("/app/assets/download/{export_id}")
async def download_asset(request: Request, export_id: str):
    from fastapi.responses import Response
    from urllib.parse import quote

    uid, service = await context(request)
    data, record = await service.download(uid, export_id)
    return Response(
        content=data,
        media_type=record["mime"],
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record['filename'])}",
            "Cache-Control": "private, no-store",
        },
    )


async def context(request):
    facade = get_facade()
    return await facade.resolve_user_id(request), facade.student_capabilities()


@router.get("/app/preferences", response_model=ApiResponse[Preferences])
async def preferences(request: Request):
    uid, service = await context(request)
    return ApiResponse(data=await service.preferences(uid))


@router.put("/app/preferences", response_model=ApiResponse[Preferences])
async def save_preferences(request: Request, body: PreferencesEdit):
    uid, service = await context(request)
    return ApiResponse(data=await service.save_preferences(uid, body))


@router.post("/app/plan/action/tasks", response_model=ApiResponse[ActionPlanView])
async def create_task(request: Request, body: TaskEdit):
    uid, service = await context(request)
    return ApiResponse(data=action_plan_view(await service.edit_task(uid, body)))


@router.put("/app/plan/action/tasks/{task_id}", response_model=ApiResponse[ActionPlanView])
async def edit_task(request: Request, task_id: str, body: TaskEdit):
    uid, service = await context(request)
    return ApiResponse(data=action_plan_view(await service.edit_task(uid, body, task_id)))


@router.post("/app/plan/action/phases", response_model=ApiResponse[ActionPlanView])
async def create_phase(request: Request, body: PhaseEdit):
    uid, service = await context(request)
    return ApiResponse(data=action_plan_view(await service.edit_phase(uid, body)))


@router.put("/app/plan/action/phases/{phase_id}", response_model=ApiResponse[ActionPlanView])
async def edit_phase(request: Request, phase_id: str, body: PhaseEdit):
    uid, service = await context(request)
    return ApiResponse(data=action_plan_view(await service.edit_phase(uid, body, phase_id)))


@router.get("/app/notifications", response_model=ApiResponse[list[NotificationStateView]])
async def notifications(request: Request):
    uid, service = await context(request)
    return ApiResponse(data=await service.list_notifications(uid))


@router.patch("/app/notifications/{message_id}", response_model=ApiResponse[NotificationStateView])
async def notification_state(request: Request, message_id: str, body: NotificationEdit):
    uid, service = await context(request)
    return ApiResponse(data=await service.change_notification(uid, message_id, body))


@router.get("/app/reviews", response_model=ApiResponse[ReviewListView])
async def reviews(request: Request):
    uid, service = await context(request)
    return ApiResponse(data=await service.reviews(uid))


@router.post("/app/reviews", response_model=ApiResponse[ReviewRecordView])
async def create_review(request: Request, body: ReviewEdit):
    uid, service = await context(request)
    return ApiResponse(data=await service.save_review(uid, body))


@router.put("/app/reviews/{review_id}", response_model=ApiResponse[ReviewRecordView])
async def edit_review(request: Request, review_id: str, body: ReviewEdit):
    uid, service = await context(request)
    return ApiResponse(data=await service.save_review(uid, body, review_id))


@router.post("/app/reviews/{review_id}/apply", response_model=ApiResponse[ReviewRecordView])
async def apply_review(request: Request, review_id: str):
    uid, service = await context(request)
    return ApiResponse(data=await service.apply_review(uid, review_id))


@router.get(
    "/app/assets/{asset_type}/versions/{version}/content",
    response_model=ApiResponse[AssetSnapshotView],
)
async def asset_snapshot(request: Request, asset_type: str, version: int):
    uid, service = await context(request)
    return ApiResponse(data=await service.snapshot(uid, asset_type, version))


@router.get(
    "/app/sessions/{task_id}/snapshot", response_model=ApiResponse[ConversationTurnView | None]
)
async def session_snapshot(request: Request, task_id: str):
    uid, service = await context(request)
    return ApiResponse(data=await service.session_snapshot(uid, task_id))


@router.get("/app/measurements", response_model=ApiResponse[MeasurementListView])
async def measurements(request: Request):
    uid, service = await context(request)
    return ApiResponse(data=await service.measurements(uid))


@router.post("/app/measurements", response_model=ApiResponse[MeasurementRecordView])
async def save_measurements(request: Request, body: MeasurementEdit):
    uid, service = await context(request)
    return ApiResponse(data=await service.save_measurements(uid, body))


@router.get("/app/plan/direction-weights", response_model=ApiResponse[DirectionWeights])
async def weights(request: Request):
    uid, service = await context(request)
    return ApiResponse(data=await service.weights(uid))


@router.put("/app/plan/direction-weights", response_model=ApiResponse[DirectionWeights])
async def save_weights(request: Request, body: DirectionWeightsEdit):
    uid, service = await context(request)
    return ApiResponse(data=await service.weights(uid, body))


@router.get("/app/plan/direction-comparison", response_model=ApiResponse[DirectionComparisonView])
async def comparison(request: Request):
    uid, service = await context(request)
    return ApiResponse(data=await service.compare(uid))


@router.get("/app/schedule/semester", response_model=ApiResponse[Semester | None])
async def semester(request: Request):
    uid, service = await context(request)
    return ApiResponse(data=await service.semester(uid))


@router.put("/app/schedule/semester", response_model=ApiResponse[Semester])
async def save_semester(request: Request, body: SemesterEdit):
    uid, service = await context(request)
    return ApiResponse(data=await service.semester(uid, body))


@router.get("/app/schedule/workload", response_model=ApiResponse[WorkloadView])
async def workload(request: Request, start: date):
    uid, service = await context(request)
    return ApiResponse(data=await service.workload(uid, start))
