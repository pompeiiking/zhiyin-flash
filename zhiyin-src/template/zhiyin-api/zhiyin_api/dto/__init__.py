"""API DTO 集合。

前端只依赖本包的模型；业务层模型变化由 `dto/mappers.py` 吸收，
避免"数据库字段变更影响前端"（R-API-007）。
"""

from zhiyin_api.dto.common import (
    AgentBadgeView,
    ApiResponse,
    BehaviorGuideView,
    DisclosureView,
    ErrorCode,
    GuideOptionView,
    GuideReminderView,
    GuideTaskView,
    TheoryRefView,
)
from zhiyin_api.dto.bootstrap import (
    BannerView,
    BootstrapView,
    FaqView,
    MenuView,
    RouteView,
    TaskEntryView,
    TheoryCardView,
    TrustBlockView,
)
from zhiyin_api.dto.conversation import (
    ConversationMessageView,
    ConversationTurnView,
    MessageRequest,
    PipelineCardView,
    SessionListView,
    TaskEnterRequest,
    TaskSessionView,
)
from zhiyin_api.dto.workspace import (
    DependencyEdgeView,
    ProfileFieldView,
    ProfileGapView,
    ProfilePanelView,
    StagePanelView,
    WorkspacePageView,
)
from zhiyin_api.dto.asset import (
    AssetVersionView,
    ExportRequest,
    ExportResultView,
    ReportDimensionItemView,
    ReportFullTextView,
    ReportSectionView,
    ReportTocItemView,
)
from zhiyin_api.dto.track import TrackEventAck, TrackEventRequest

__all__ = [
    "ApiResponse",
    "ErrorCode",
    "AgentBadgeView",
    "BehaviorGuideView",
    "DisclosureView",
    "GuideOptionView",
    "GuideReminderView",
    "GuideTaskView",
    "TheoryRefView",
    "BootstrapView",
    "BannerView",
    "FaqView",
    "MenuView",
    "RouteView",
    "TaskEntryView",
    "TheoryCardView",
    "TrustBlockView",
    "ConversationMessageView",
    "ConversationTurnView",
    "MessageRequest",
    "PipelineCardView",
    "SessionListView",
    "TaskEnterRequest",
    "TaskSessionView",
    "DependencyEdgeView",
    "ProfileFieldView",
    "ProfileGapView",
    "ProfilePanelView",
    "StagePanelView",
    "WorkspacePageView",
    "AssetVersionView",
    "ExportRequest",
    "ExportResultView",
    "ReportFullTextView",
    "ReportTocItemView",
    "ReportSectionView",
    "ReportDimensionItemView",
    "TrackEventAck",
    "TrackEventRequest",
]
