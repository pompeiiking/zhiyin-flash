"""Repository 接口集合。

约定（R-SDK-001）：
- 业务层只通过 Repository 访问数据，禁止直接写 SQL。
- 所有方法参数与返回值均为共享内核（`zhiyin_kernel`）中的模型，不得出现 ORM 实体。
- 实现由 zhiyin-infrastructure 提供（自有本地实现）。

IO 口径：**所有公开方法一律 `async`**。Repository 是 IO 边界，同步方法会在接
网络存储时阻塞事件循环；本地实现同样是 async，只是内部没有真 IO，
这样换实现时调用方一行不用改。纯内存的私有辅助函数保持同步。
"""

from zhiyin_data_sdk.repositories.profile import ProfileRepository
from zhiyin_data_sdk.repositories.academic import AcademicSnapshotRepository
from zhiyin_data_sdk.repositories.behavior import BehaviorRepository
from zhiyin_data_sdk.repositories.memory import (
    ConversationMemoryRepository,
    ConversationTurnRepository,
)
from zhiyin_data_sdk.repositories.asset import AssetRepository
from zhiyin_data_sdk.repositories.session import TaskSessionRepository
from zhiyin_data_sdk.repositories.registry import RegistryRepository
from zhiyin_data_sdk.repositories.identity import UserRepository
from zhiyin_data_sdk.repositories.note import UserNoteRepository
from zhiyin_data_sdk.repositories.function import (
    CalendarNodeRepository,
    NotificationRepository,
    TrackEventRepository,
)
from zhiyin_data_sdk.repositories.ai_tasks import AiTaskResultRepository

__all__ = [
    "AcademicSnapshotRepository",
    "ProfileRepository",
    "BehaviorRepository",
    "ConversationMemoryRepository",
    "ConversationTurnRepository",
    "AssetRepository",
    "TaskSessionRepository",
    "RegistryRepository",
    "CalendarNodeRepository",
    "TrackEventRepository",
    "NotificationRepository",
    "AiTaskResultRepository",
    "UserRepository",
    "UserNoteRepository",
]
