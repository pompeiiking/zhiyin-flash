"""学生端可编辑能力契约。量化记录必须声明来源与量表，不推测空缺值。"""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskValues(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    phase_id: str = Field(min_length=1)
    status: Literal["pending", "in_progress", "waiting", "completed"] = "pending"
    progress: int = Field(default=0, ge=0, le=100)
    waiting_reason: str = Field(default="", max_length=500)
    due_date: datetime | None = None
    scheduled_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    parent_task_id: str | None = None

    @model_validator(mode="after")
    def validate_state(self):
        if not self.text.strip():
            raise ValueError("请填写任务内容")
        if self.status == "waiting" and not self.waiting_reason.strip():
            raise ValueError("请填写等待原因")
        if self.status == "completed":
            self.progress = 100
        elif self.progress == 100:
            raise ValueError("100% 进度请选择已完成")
        for value in (self.due_date, self.scheduled_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("日期时间必须包含时区")
        return self


class TaskEdit(TaskValues):
    expected_task: TaskValues | None = None
    client_request_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class PhaseValues(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    depends_on: list[str] = Field(default_factory=list, max_length=30)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    blocking_conditions: list[str] = Field(default_factory=list, max_length=20)
    handoff_requirements: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def dates(self):
        if not self.name.strip():
            raise ValueError("请填写阶段名称")
        for value in (self.starts_at, self.ends_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("日期时间必须包含时区")
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValueError("结束时间不能早于开始时间")
        return self


class PhaseEdit(PhaseValues):
    expected_phase: PhaseValues | None = None
    client_request_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class Preferences(StrictModel):
    proactive_reminders: bool = True
    quiet_start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"
    academic_analysis: bool = True
    material_analysis: bool = True

    @model_validator(mode="after")
    def times(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("无效的时区") from exc
        if bool(self.quiet_start) != bool(self.quiet_end):
            raise ValueError("安静时段需同时填写开始和结束时间")
        return self


class Period(StrictModel):
    number: int = Field(ge=1, le=30)
    start: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def ordered(self):
        if self.start >= self.end:
            raise ValueError("节次结束时间必须晚于开始时间")
        return self


class Semester(StrictModel):
    first_monday: date
    weeks: int = Field(default=20, ge=1, le=53)
    timezone: str = "Asia/Shanghai"
    periods: list[Period] = Field(min_length=1, max_length=30)
    weekly_available_minutes: int | None = Field(default=None, ge=0, le=10080)

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("无效的时区") from exc
        if self.first_monday.weekday() != 0:
            raise ValueError("请填写第一教学周的周一")
        if len({p.number for p in self.periods}) != len(self.periods):
            raise ValueError("节次编号不能重复")
        ordered = sorted(self.periods, key=lambda p: p.start)
        if any(a.end > b.start for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError("节次时段不能重叠")
        return self


class ReviewValues(StrictModel):
    task_id: str
    reason: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=3000)
    result: Literal["continue", "adjust", "complete"] = "continue"
    adjustment: TaskEdit | None = None

    @model_validator(mode="after")
    def valid(self):
        if not self.reason.strip():
            raise ValueError("请填写复盘原因")
        if self.result == "adjust" and self.adjustment is None:
            raise ValueError("调整任务时请提供调整内容")
        return self


class ReviewEdit(ReviewValues):
    expected_updated_at: datetime | None = None
    expected_task: TaskValues | None = None
    client_request_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class NotificationEdit(StrictModel):
    status: Literal["pending", "read", "later", "done"]
    snoozed_until: datetime | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.status == "later" and (not self.snoozed_until or self.snoozed_until.tzinfo is None):
            raise ValueError("稍后处理需提供包含时区的提醒时间")
        return self


class Measurement(StrictModel):
    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    value: float
    minimum: float = 0
    maximum: float = 100
    threshold: float | None = None
    source: str = Field(min_length=1, max_length=1000)
    method: str = Field(min_length=1, max_length=300)
    measured_at: datetime
    origin: Literal["self_report", "assessment", "external"] = "self_report"

    @model_validator(mode="after")
    def valid(self):
        import math

        if not all(math.isfinite(v) for v in (self.value, self.minimum, self.maximum)):
            raise ValueError("量表值必须为有限数")
        if self.minimum >= self.maximum or not self.minimum <= self.value <= self.maximum:
            raise ValueError("数值必须在有效量表范围内")
        if self.threshold is not None and not self.minimum <= self.threshold <= self.maximum:
            raise ValueError("门槛必须在量表范围内")
        if not self.source.strip() or not self.method.strip() or self.measured_at.tzinfo is None:
            raise ValueError("请提供来源、量表方法和带时区的测量时间")
        return self


class MeasurementBatch(StrictModel):
    asset_type: Literal["report", "direction_plan"]
    version: int = Field(ge=1)
    subject_id: str = Field(min_length=1)
    measurements: list[Measurement] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique(self):
        if len({m.key for m in self.measurements}) != len(self.measurements):
            raise ValueError("同一批次维度不能重复")
        return self


class DirectionWeights(StrictModel):
    major: float = Field(default=1, ge=0, le=100)
    jobs: float = Field(default=1, ge=0, le=100)
    salary: float = Field(default=1, ge=0, le=100)
    stability: float = Field(default=1, ge=0, le=100)
    location: float = Field(default=1, ge=0, le=100)

    @model_validator(mode="after")
    def nonzero(self):
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("至少一项权重需要大于零")
        return self
