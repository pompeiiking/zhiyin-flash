"""智能工作台聚合契约。

工作台按 ①-⑤ 分层展示"活资产"，不做实时对话。
本模块的 View 模型会被 BFF 直接翻译成前端视图，不暴露数据库实体。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.assets import (
    ActionPlan,
    DirectionPlan,
    Report,
    TrackEvent,
)
from zhiyin_kernel.blackboard import AssetVersion, Profile, TaskSession
from zhiyin_kernel.enums import LoopStage
from zhiyin_business.policies.collection import CollectionPlan
from zhiyin_business.contracts.common import TheoryRef


class StagePanel(BaseModel):
    """①-⑤ 中的一层。三态：当前评价 / 理论模型 / 历史与差异。"""

    model_config = ConfigDict(extra="forbid")

    stage: LoopStage
    title: str
    evaluation: str = Field(default="", description="当前评价状态")
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    version: Optional[int] = None
    diff_from_previous: Optional[str] = None
    updated_at: Optional[datetime] = None
    collapsed: bool = False


class DependencyEdge(BaseModel):
    """依赖可视化的一条边（简版）。

    展示画像-报告-方案-计划-行为日志之间的依赖与更新时间。
    """

    model_config = ConfigDict(extra="forbid")

    from_asset: str = Field(description="上游，如 profile.major")
    to_asset: str = Field(description="下游，如 report")
    via_profile_keys: list[str] = Field(default_factory=list)


class WorkspaceView(BaseModel):
    """智能工作台聚合视图。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    profile: Optional[Profile] = None
    report: Optional[Report] = Field(default=None, description="② 诊断与报告")
    report_versions: list[AssetVersion] = Field(default_factory=list)
    direction_plans: list[DirectionPlan] = Field(default_factory=list, description="③ 方案")
    action_plan: Optional[ActionPlan] = Field(default=None, description="④ 计划与日历")
    track_events: list[TrackEvent] = Field(
        default_factory=list, description="⑤ 跟踪与预警 / 教练消息汇总"
    )
    panels: list[StagePanel] = Field(default_factory=list, description="①-⑤ 分层视图")
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    profile_coverage: float = Field(
        default=0.0, ge=0.0, le=1.0, description="画像字段覆盖度（含缺口）"
    )
    profile_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="画像整体置信度"
    )
    collection: Optional[CollectionPlan] = Field(
        default=None,
        description="动态采集策略：还缺什么、去哪儿取、为什么是它",
    )
    profile_labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "画像字段 key → 展示名。来自动态资源的采集规则表（`collection_rules.json`），"
            "与采集清单同一份来源 —— 界面上不把 `major` 这种内部键直接摆给用户看"
        ),
    )
    academic: Optional[Any] = Field(
        default=None,
        description=(
            "教务系统取回来的课表与成绩单（快照）。为 None 表示还没授权过 —— "
            "界面据此说'还没授权'，而不是显示一张空课表"
        ),
    )
    layout: list[Any] = Field(
        default_factory=list,
        description="气泡编排结果（已按当前状态排好序）：顺序与权重由动态资源决定",
    )


class WorkspaceService(ABC):
    """工作台聚合服务 Port。"""

    @abstractmethod
    async def build_view(self, user_id: str) -> WorkspaceView:
        """按 ①-⑤ 聚合活资产，装配工作台视图。"""

    @abstractmethod
    async def list_sessions_summary(self, user_id: str) -> list[StagePanel]:
        """列出该用户各任务会话的环节进度，用于左栏会话列表与工作台分层。"""

    @abstractmethod
    async def list_sessions(self, user_id: str) -> list[TaskSession]:
        """列出该用户的任务会话（读侧转手，供左栏会话列表）。"""
