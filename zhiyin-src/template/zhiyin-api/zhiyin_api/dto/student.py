"""新增工作台接口的完整响应契约。"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from zhiyin_business.contracts.student import (
    ReviewValues,
    TaskValues,
    MeasurementBatch,
    Measurement,
    DirectionWeights,
)
from zhiyin_kernel.assets import ActionPlan, DirectionPlan, Report


class NotificationStateView(BaseModel):
    id: str
    title: str
    body: str = ""
    occurred_at: str | None = None
    channel: str = ""
    action: dict | None = None
    related_task_id: str | None = None
    status: Literal["pending", "read", "later", "done"]
    snoozed_until: str | None = None


class ReviewRecordView(ReviewValues):
    id: str
    task_text: str
    updated_at: datetime
    applied_at: datetime | None = None
    history: list[dict] = Field(default_factory=list)
    task_snapshot: TaskValues | None = None


class ReviewListView(BaseModel):
    items: list[ReviewRecordView]
    reasons: dict[str, int]


class MeasurementRecordView(MeasurementBatch):
    recorded_at: datetime


class MeasurementListView(BaseModel):
    items: list[MeasurementRecordView]
    history: list[MeasurementRecordView]


class DirectionScoreView(BaseModel):
    id: str
    name: str
    score: float | None = None
    missing: list[str]
    measurements: list[Measurement]
    opportunity: float | None = None
    feasibility: float | None = None


class DirectionComparisonView(BaseModel):
    version: int | None = None
    weights: DirectionWeights
    plans: list[DirectionScoreView]
    method: str


class WorkloadWeekView(BaseModel):
    start: str
    course_minutes: float
    task_minutes: float
    remaining_minutes: float | None = None


class ScheduleConflictView(BaseModel):
    first: str
    second: str
    at: datetime


class WorkloadView(BaseModel):
    configured: bool
    weeks: list[WorkloadWeekView]
    conflicts: list[ScheduleConflictView]
    missing: list[str]
    capacity_method: str | None = None


class AssetSnapshotView(BaseModel):
    asset_type: Literal["direction_plan", "action_plan", "report"]
    version: int
    created_at: datetime
    content: Report | ActionPlan | list[DirectionPlan] | None
