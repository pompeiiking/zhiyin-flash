"""zhiyin-orchestration · 编排层。

职责：提供**通用**编排原语 —— Agent / Workflow / EventBus / Schedule / State /
Notify。本层必须保持通用性，不得出现职引业务语义（R-ORC-001）：
代码中不允许出现"五环节""画像""职业顾问""差距认领"等词。

依赖方向：只允许依赖 zhiyin-data-sdk。

用法：本包顶层导出契约（ABC + 数据模型）与第一期默认实现（impl 中的 Gateway* 系列）。
`zhiyin-boot` 负责把实现装配到契约上，业务层只面向契约编程。
"""

from zhiyin_orchestration.agent import AgentEngine, AgentRequest, AgentResult
from zhiyin_orchestration.errors import (
    ContractViolationError,
    OrchestrationError,
    StateConflictError,
    WorkflowFailedError,
)
from zhiyin_orchestration.event import DomainEvent, EventBus, EventHandler
from zhiyin_orchestration.datasource import (
    DataSourceRecord,
    DataSourceRequest,
    DataSourceResult,
    ExternalDataSource,
)
from zhiyin_orchestration.impl import (
    SCHEDULE_TICK_EVENT,
    AgnoAgentEngine,
    GatewayDataSource,
    GatewayEventBus,
    GatewayNotifier,
    GatewayScheduler,
    MemoryStateStore,
    SequentialWorkflowEngine,
    validate_schema,
)
from zhiyin_orchestration.notify import Notifier, NotifyDelivery, NotifyMessage
from zhiyin_orchestration.schedule import ScheduleSpec, Scheduler
from zhiyin_orchestration.state import StateRecord, StateStore
from zhiyin_orchestration.workflow import (
    WorkflowEngine,
    WorkflowResult,
    WorkflowSpec,
    WorkflowStep,
)

__all__ = [
    # ---- 契约 ----
    "AgentEngine",
    "AgentRequest",
    "AgentResult",
    "DomainEvent",
    "DataSourceRecord",
    "DataSourceRequest",
    "DataSourceResult",
    "EventBus",
    "EventHandler",
    "Notifier",
    "ExternalDataSource",
    "NotifyDelivery",
    "NotifyMessage",
    "ScheduleSpec",
    "Scheduler",
    "StateRecord",
    "StateStore",
    "WorkflowEngine",
    "WorkflowResult",
    # ---- 实现（引擎只有这一个：全量基于 agno） ----
    "AgnoAgentEngine",
    "WorkflowSpec",
    "WorkflowStep",
    # ---- 异常 ----
    "ContractViolationError",
    "OrchestrationError",
    "StateConflictError",
    "WorkflowFailedError",
    # ---- 第一期默认实现 ----
    "SCHEDULE_TICK_EVENT",
    "GatewayDataSource",
    "GatewayEventBus",
    "GatewayNotifier",
    "GatewayScheduler",
    "MemoryStateStore",
    "SequentialWorkflowEngine",
    "validate_schema",
]
