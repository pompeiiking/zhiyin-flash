"""业务服务接口（Port）与只读视图。

本包只放**接口与共享读模型**，是团队并行开发前必须冻结的那一层：

- 调用方对着 Port 编程，实现方对着 Port 交付，双方不需要等对方完成；
- 具体实现放在 `services/`，业务规则放在 `policies/`；
- 本包不 import `services/` 与 `policies/`（方向是 services → policies → ports）。

命名说明：本目录原名 `domain/`，但里面装的全是 ABC 与读模型、没有领域行为，
名字与内容不符；已改为 `ports/`。
"""

from zhiyin_business.ports.orchestrator import (
    HandoffDecision,
    IntentType,
    LeadDecision,
    Orchestrator,
    StageDecision,
    TurnRequest,
    TurnResult,
)
from zhiyin_business.ports.blackboard import (
    AssetService,
    BehaviorService,
    BlackboardView,
    ConversationMemoryService,
    ProfileService,
)
from zhiyin_business.ports.workspace import WorkspaceService, WorkspaceView
from zhiyin_business.ports.function import FunctionService
from zhiyin_business.ports.identity import IdentityService
from zhiyin_business.ports.registry import RegistryService

__all__ = [
    "HandoffDecision",
    "IntentType",
    "LeadDecision",
    "Orchestrator",
    "StageDecision",
    "TurnRequest",
    "TurnResult",
    "AssetService",
    "BehaviorService",
    "BlackboardView",
    "ConversationMemoryService",
    "ProfileService",
    "WorkspaceService",
    "WorkspaceView",
    "FunctionService",
    "IdentityService",
    "RegistryService",
]
