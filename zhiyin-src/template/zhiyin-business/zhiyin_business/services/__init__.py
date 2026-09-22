"""业务层服务实现。

分工口径：

- `ports/` 放接口（冻结），`policies/` 放规则，`services/` 放**实现**；
- 从这里开始真正依赖 `zhiyin-orchestration`（AgentEngine / EventBus / Scheduler）
  与 `zhiyin-data-sdk`（Repository / Gateway）。

服务落位表（按模块归属切列，一人一列互不阻塞）。
**每个格子都是一个真实文件**，且**都已经交付实现**（`IMPLEMENTATION_STATUS = "wired"`），
由 `tests/test_shell_completeness.py` 守住"表格 ↔ 目录"一致 —— 新增服务时表格与文件
必须同时改，否则测试直接失败。
仍然自报骨架的是基础设施侧的 5 个网关（见 `/healthz` 的 `assembly.skeletons`）。

| 服务 | 文件 | 类 | 依赖 | 优先级 | 状态 |
| --- | --- | --- | --- | --- | --- |
| Orchestrator | `orchestrator.py` | `DefaultOrchestrator` | 黑板四件套 + `policies/` + AgentEngine | P0 | 已交付 |
| Profile 服务 | `profile.py` | `DefaultProfileService` | ProfileRepository、EventBus | P0 | 已交付 |
| Behavior 服务 | `behavior.py` | `DefaultBehaviorService` | BehaviorRepository、EventBus | P0 | 已交付 |
| Memory 服务 | `memory.py` | `DefaultConversationMemoryService` | ConversationMemoryRepository | P0 | 已交付 |
| 自建内容服务 | `note.py` | `DefaultUserNoteService` | UserNoteRepository | P1 | 已交付 |
| 教务系统服务 | `academic.py` | `DefaultAcademicService` | AcademicSnapshotRepository | P1 | 已交付 |
| AI 任务服务 | `ai_tasks.py` | `AiTaskService` | 画像 / 行为 / 资产 Port | P0 | 已交付 |
| Asset 服务 | `asset.py` | `DefaultAssetService` | AssetRepository、EventBus + `policies/impact.py` | P0 | 已交付 |
| 环节产出 → 资产正文 | `asset_content.py` | `report_from_diagnose` / `direction_plans_from_decide` / `action_plan_from_act` | 内核资产模型 | P0 | 已交付 |
| Workspace 服务 | `workspace.py` | `DefaultWorkspaceService` | 读侧聚合（Profile / Asset / Memory） | P1 | 已交付 |
| Function 服务 | `function.py` | `DefaultFunctionService` | ObjectStore、日历 | P1 | 已交付 |
| Identity 服务 | `identity.py` | `DefaultIdentityService` | AuthGateway、UserRepository | P0 | 已交付 |
| Registry 服务 | `registry.py` | `DefaultRegistryService` | RegistryRepository、FeatureFlagGateway | P0 | 已交付 |
| 动态配置装载 | `dynamic_config.py` | `load_snapshot` | RegistryService → `kernel.dynamic_config` | P1 | 已交付 |
| 读缓存 | `read_cache.py` | `DefaultReadCacheService` | CacheGateway + `kernel.dynamic_config` 策略 | P1 | 已交付 |

> Identity 服务是 api 与数据访问契约之间的通道之一：api 层被禁止 import
> `zhiyin_data_sdk`，因此 Facade 拿不到 `AuthGateway`；由本服务把它包成业务 Port
> （`business/ports/identity.py::IdentityService`）。它是 Facade 的硬前置——
> Facade 一装配就会调它。

> Registry 服务是同一类问题的第二个通道（`business/ports/registry.py`）：
> `/app/bootstrap` 需要的菜单 / 路由 / 任务入口 / 文案 / 功能开关全在动态资源里，
> 而取数契约在 `zhiyin_data_sdk`，api 同样拿不到。它是 Facade 的另一个硬前置。
> 两条通道的分工：Identity 管"我是谁"，Registry 管"页面长什么样"。

实现顺序建议：黑板四件套（Profile / Behavior / Memory / Asset）→ Identity + Registry
（这两个是 Facade 的硬前置，Facade 一装配就会调它们）→ Facade（前端随即可以联调）
→ Orchestrator → Workspace / Function。Orchestrator 的前置是 4 项口径定稿，
未定稿不要动手（见 `orchestrator.py` 的 docstring）。
"""

from zhiyin_business.services.academic import DefaultAcademicService
from zhiyin_business.services.ai_tasks import AiTaskService as DefaultAiTaskService
from zhiyin_business.services.asset import DefaultAssetService
from zhiyin_business.services.behavior import DefaultBehaviorService
from zhiyin_business.services.function import DefaultFunctionService
from zhiyin_business.services.identity import DefaultIdentityService
from zhiyin_business.services.memory import DefaultConversationMemoryService
from zhiyin_business.services.note import DefaultUserNoteService
from zhiyin_business.services.orchestrator import DefaultOrchestrator
from zhiyin_business.services.profile import DefaultProfileService
from zhiyin_business.services.registry import DefaultRegistryService
from zhiyin_business.services.workspace import DefaultWorkspaceService

__all__ = [
    "DefaultAcademicService",
    "DefaultAiTaskService",
    "DefaultAssetService",
    "DefaultBehaviorService",
    "DefaultConversationMemoryService",
    "DefaultFunctionService",
    "DefaultIdentityService",
    "DefaultOrchestrator",
    "DefaultProfileService",
    "DefaultRegistryService",
    "DefaultUserNoteService",
    "DefaultWorkspaceService",
]
