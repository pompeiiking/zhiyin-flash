"""zhiyin-kernel · 共享内核（shared kernel）。

本包是全系统**唯一**的"数据形状"定义处：跨层枚举、身份、黑板数据形状、
资产数据形状、动态资源形状。它横切全部层，因此：

- **零依赖**：不得 import 任何其它 `zhiyin_*` 包（含 data-sdk / business），
  由 `tests/test_architecture.py::test_kernel_has_no_dependencies` 守卫；
- **无行为**：只允许声明数据形状与纯函数式取值，不得写业务逻辑、不得访问 IO；
- 所有层都可以读它，但任何层都不得在这里扩展业务语义。

它曾经叫 `zhiyin_data_sdk.contracts`，名字挂在数据访问包下，导致两处失真：
新人会把 `Profile` / `AssetVersion` 这类领域模型误当成数据访问契约；业务模型
一旦调整就要跨包改动。现在改名归位为独立内核。

历史缺陷（不再回退）：曾出现 `zhiyin-api` 直接 import
`zhiyin_data_sdk.contracts.enums` 的越层依赖，由本包改名后按矩阵放行 api → kernel。

约束：
- DTO 不得直接暴露数据库实体（R-API-007），数据库实体只在 infrastructure
  的 persistence 层出现。

准入规则（只允许三类内容，其余一律拒收）
-----------------------------------------
1. **数据形状**：跨层枚举与 Pydantic 模型（画像 / 资产 / 身份 / 动态资源）；
2. **零依赖的最小接口契约**：只有抽象方法的 ABC，且**没有方法体**
   （例：`Worker` —— 业务层与基础设施层都要用它，而这两层唯一的公共依赖就是内核）；
3. **跨层异常类型**（`errors.py`）：api 层必须能区分「资源不存在 / 未授权 / 输入不合法」，
   而它被禁止 import `zhiyin_data_sdk` 与 `zhiyin_business` —— 这门"错误分类"的语言
   只能放在所有层都能读的内核里。它们只有类属性、没有方法体，不引入任何依赖。

任何带方法体的类都必须离开内核：行为一进来，"所有层都能安全引用的最小内核"
就不再成立。纯 `@property` 取值允许，因为它不引入依赖也不承载业务规则。
该规则由 `tests/test_architecture.py::test_kernel_holds_only_shapes_and_contracts`
用 AST 守卫。
"""

from zhiyin_kernel.enums import (
    AgentRole,
    AgentRuntimeStatus,
    AssetType,
    AxisAStage,
    BehaviorEventType,
    LoopStage,
    NotifyChannel,
    PathFocus,
    PlanRole,
    ProfileSource,
    ReviewAttribution,
    TaskStatus,
    UserRole,
)
from zhiyin_kernel.blackboard import (
    AssetVersion,
    BehaviorLog,
    ConversationMemory,
    Profile,
    ProfileField,
    ProfileGap,
    TaskSession,
)
from zhiyin_kernel.assets import (
    ActionPhase,
    ActionPlan,
    ActionTask,
    Achievement,
    DirectionPlan,
    GapClaim,
    PlanGap,
    Report,
    ReportDimensionGroup,
    ReportDimensionItem,
    Swot,
    TrackEvent,
    Verdict,
)
from zhiyin_kernel.identity import GuestSession, UserAccount
from zhiyin_kernel.dynamic_content import (
    BannerSpec,
    ContentSpec,
    ContentStatus,
    CopySpec,
    FaqSpec,
    MenuSpec,
    RouteSpec,
    TrustBlockSpec,
)
from zhiyin_kernel.errors import (
    AccessDenied,
    DuplicateResource,
    InvalidRequest,
    KernelError,
    ResourceNotFound,
)
from zhiyin_kernel.registry import (
    AgentDescriptor,
    OutputContractSpec,
    PolicyParamSet,
    TaskEntrySpec,
    TheoryCard,
    TrackEventSpec,
)
from zhiyin_kernel.worker import Worker

__all__ = [
    "AgentRole",
    "AgentRuntimeStatus",
    "AssetType",
    "AxisAStage",
    "BehaviorEventType",
    "LoopStage",
    "NotifyChannel",
    "PathFocus",
    "PlanRole",
    "ProfileSource",
    "ReviewAttribution",
    "TaskStatus",
    "UserRole",
    "AssetVersion",
    "BehaviorLog",
    "ConversationMemory",
    "Profile",
    "ProfileField",
    "ProfileGap",
    "TaskSession",
    "ActionPhase",
    "ActionPlan",
    "ActionTask",
    "Achievement",
    "DirectionPlan",
    "GapClaim",
    "PlanGap",
    "Report",
    "ReportDimensionGroup",
    "ReportDimensionItem",
    "Swot",
    "TrackEvent",
    "Verdict",
    "GuestSession",
    "UserAccount",
    "BannerSpec",
    "AccessDenied",
    "DuplicateResource",
    "InvalidRequest",
    "KernelError",
    "ResourceNotFound",
    "ContentSpec",
    "ContentStatus",
    "CopySpec",
    "FaqSpec",
    "MenuSpec",
    "RouteSpec",
    "TrustBlockSpec",
    "AgentDescriptor",
    "OutputContractSpec",
    "PolicyParamSet",
    "TaskEntrySpec",
    "TheoryCard",
    "TrackEventSpec",
    "Worker",
]
