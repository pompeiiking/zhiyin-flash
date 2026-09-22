"""黑板服务契约。

黑板 = 共享状态：
1. 个人画像（活状态：字段值 + 置信度 + 缺口 + 更新时间线）
2. 行为日志（事件流）
3. 会话记忆（各任务会话摘要）
4. 资产版本与影响面

本模块只定义读写接口与只读视图，不承载跨环节编排逻辑（那属于 Orchestrator /
LoopCoordinator）。所有智能体读写同一份黑板。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.assets import (
    ActionPlan,
    DirectionPlan,
    Report,
)
from zhiyin_business.ports.academic import AcademicImportResult
from zhiyin_data_sdk.gateways.academic import AcademicSnapshot
from zhiyin_kernel.blackboard import (
    AssetVersion,
    BehaviorLog,
    ConversationMemory,
    ConversationTurn,
    Profile,
    ProfileField,
    ProfileGap,
    UserNote,
)
from zhiyin_kernel.enums import AssetType, BehaviorEventType, LoopStage
from zhiyin_business.contracts.common import (
    AssetUpdateDraft,
    BehaviorEventDraft,
)


class BlackboardView(BaseModel):
    """黑板的只读快照。

    每次回复的第一步都是"读黑板"；所有智能体共享同一份。
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str
    task_id: Optional[str] = None
    profile: Optional[Profile] = Field(default=None, description="画像活状态")
    recent_behaviors: list[BehaviorLog] = Field(
        default_factory=list, description="近期行为日志，按时间倒序"
    )
    memories: list[ConversationMemory] = Field(default_factory=list)
    asset_versions: list[AssetVersion] = Field(default_factory=list)
    current_stage: Optional[LoopStage] = None


class ProfileService(ABC):
    """画像活状态读写（R-BIZ-006）。"""

    @abstractmethod
    async def get(self, user_id: str) -> Optional[Profile]:
        """读取完整画像。"""

    @abstractmethod
    async def get_fields(
        self, user_id: str, keys: Optional[Sequence[str]] = None
    ) -> list[ProfileField]:
        """按字段键读取画像字段，用于提示词注入与影响面判定。"""

    @abstractmethod
    async def get_gaps(self, user_id: str) -> list[ProfileGap]:
        """读取缺口清单，用于采集追问与工作台展示。"""

    @abstractmethod
    async def update_field(
        self,
        user_id: str,
        key: str,
        value: object,
        *,
        confidence: float,
        source: str,
        label: str = "",
        evidence: Optional[list[str]] = None,
    ) -> ProfileField:
        """更新单个画像字段。

        必须发布 profile_field_updated 事件，触发影响面传播。

        `label` 是这个字段的中文称呼（如「兴趣方向」）。字段键由模型自由生成，
        界面要显示的是名字 —— 名字必须跟着字段一起存下来，否则画面上就是
        一串 `interest_direction`。
        """

    @abstractmethod
    async def replace_gaps(self, user_id: str, gaps: list[ProfileGap]) -> None:
        """整体替换缺口清单。"""

    @abstractmethod
    async def drop_field(self, user_id: str, key: str) -> None:
        """抹掉一个画像字段。

        撤销教务系统授权时必须用它：采集清单按"字段在不在"判断还缺不缺，
        只是把值清空的话，"课程表 / 成绩单"会永远显示已取到。
        """

    @abstractmethod
    async def overall_confidence(self, user_id: str) -> float:
        """画像整体置信度。采集环节的结束条件依据。"""


class BehaviorService(ABC):
    """行为日志写入与查询。"""

    @abstractmethod
    async def log(self, user_id: str, draft: BehaviorEventDraft) -> BehaviorLog:
        """写入一条行为日志，并发布 behavior_logged 事件。"""

    @abstractmethod
    async def recent(
        self,
        user_id: str,
        *,
        event_types: Optional[Sequence[BehaviorEventType]] = None,
        limit: int = 50,
    ) -> list[BehaviorLog]:
        """读取近期行为日志。"""

    @abstractmethod
    async def days_since_last(
        self, user_id: str, event_type: BehaviorEventType
    ) -> Optional[int]:
        """距某类行为发生过了几天。停滞检测的唯一依据。"""


class ConversationMemoryService(ABC):
    """会话记忆读写（跨会话续接）。"""

    @abstractmethod
    async def get(self, user_id: str, task_id: str) -> Optional[ConversationMemory]:
        """读取会话记忆。"""

    @abstractmethod
    async def upsert(
        self,
        user_id: str,
        task_id: str,
        *,
        loop_stage: LoopStage,
        lead_agent: str,
        summary_delta: str = "",
    ) -> ConversationMemory:
        """更新会话记忆（追加摘要片段）。"""

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[ConversationMemory]:
        """列出用户全部任务会话记忆。"""

    @abstractmethod
    async def record_turn(
        self,
        user_id: str,
        task_id: str,
        *,
        role: str,
        text: str,
        loop_stage: LoopStage,
        agent_id: str = "",
    ) -> ConversationTurn:
        """记一轮对话原文（用户/主理各算一轮）。

        与 `upsert`（累积摘要）分开：摘要给模型续接用，原文给"会话列表点进去看历史"
        与复盘取证用。此前只存摘要，于是用户自己说的话一个字都没有。
        """

    @abstractmethod
    async def list_turns(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationTurn]:
        """按时间正序读一条会话的全部轮次。"""


class UserNoteService(ABC):
    """用户自己写下的东西（自建待办 / 写下的目标）。

    为什么它必须是一个 Port 而不是"前端存本地就行"
    ----------------------------------------------
    这些话不只是给用户自己看的清单，它们是**采集策略的输入**：
    他写了想冲秋招，先取毕业时间就是他的账。策略跑在后端，
    所以这些话必须到后端来 —— 只存在浏览器里，策略就永远读不到，
    回执里那句"因为你写了…"也就永远说不出来。
    """

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[UserNote]:
        """列出他写下的全部内容（新写的在前）。"""

    @abstractmethod
    async def add(
        self, user_id: str, text: str, *, kind: str = "todo"
    ) -> UserNote:
        """记下他写的一句话。空文本不落库，直接返回调用方之前的那条。"""

    @abstractmethod
    async def set_done(self, user_id: str, note_id: str, done: bool) -> Optional[UserNote]:
        """勾掉 / 取消勾掉一条待办。"""

    @abstractmethod
    async def remove(self, user_id: str, note_id: str) -> None:
        """删掉一条。"""

    @abstractmethod
    async def texts(self, user_id: str) -> list[str]:
        """只取文本 —— 采集策略读线索用这个，别把整个对象拖过边界。"""


class AcademicService(ABC):
    """学生自己导入的课表与成绩单。

    一条边界：这里没有"凭据"这个概念 —— 数据是用户自己带进来的，
    我们从没碰过他学校的账号。所以撤销是"清空我导入的东西"，不是"收回授权"。
    """

    @abstractmethod
    async def get(self, user_id: str) -> Optional["AcademicSnapshot"]:
        """读回他的课表与成绩；没取过返回 None（界面据此说"还没授权"）。"""

    @abstractmethod
    async def import_(
        self,
        user_id: str,
        *,
        courses_raw: str = "",
        grades_raw: str = "",
        school: str = "",
        term: str = "",
    ) -> "AcademicImportResult":
        """读用户贴进来的原文，存成一份快照，并把画像摘要更新掉。

        原文读不出来时抛 `AcademicImportError` —— 界面上要按类别给他**具体**的改法
        （缺表头 / 只复制了表头 / 版式不认识），而不是一句"导入失败"。
        """

    @abstractmethod
    async def revoke(self, user_id: str) -> None:
        """清空导入：课表成绩与画像摘要一起删掉，这条重新变回待办。"""


class AssetService(ABC):
    """资产版本与影响面（R-BIZ-012）。

    核心规则：画像字段更新 → 只重算受影响片段 → 版本 +1 → 写 diff。
    禁止整篇重新生成。
    """

    @abstractmethod
    async def list_versions(self, user_id: str, asset_type: AssetType) -> list[AssetVersion]:
        """列出某类资产的历史版本。"""

    @abstractmethod
    async def propagate(self, user_id: str, changed_profile_keys: Sequence[str]) -> list[AssetVersion]:
        """影响面传播。

        由 profile_field_updated 事件触发；返回本轮版本发生变化的资产列表。
        """

    @abstractmethod
    async def save_version(
        self, user_id: str, draft: AssetUpdateDraft
    ) -> AssetVersion:
        """保存一次新版本并发布 asset_version_changed 事件。"""

    # ---------- 资产内容读取（供工作台 / 报告页） ----------

    @abstractmethod
    async def get_report(self, user_id: str, version: Optional[int] = None) -> Optional[Report]:
        """读取诊断报告全文。"""

    @abstractmethod
    async def save_report(
        self,
        user_id: str,
        report: Report,
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        """保存诊断报告正文，并同步升一个版本。

        为什么必须有这条（而不只是仓储上的 `save_report`）：
        **正文与版本号是两个事实来源**。仓储只管存正文，版本行由 `save_version` 写；
        如果调用方各写各的，就会出现"有报告但没有版本记录"或"版本号对不上"——
        工作台按版本行展示历史，报告页按正文展示，两边一错位就没人能对上账。
        这个方法把"分配版本号 → 写正文 → 写版本行并发事件"收在一处。
        """

    @abstractmethod
    async def save_direction_plans(
        self,
        user_id: str,
        plans: Sequence[DirectionPlan],
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        """保存方向方案组（覆盖式），并同步升一个版本。"""

    @abstractmethod
    async def save_action_plan(
        self,
        user_id: str,
        plan: ActionPlan,
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        """保存行动计划，并同步升一个版本。"""

    @abstractmethod
    async def list_direction_plans(self, user_id: str) -> list[DirectionPlan]:
        """读取主攻/平行/保底方案。"""

    @abstractmethod
    async def get_action_plan(self, user_id: str) -> Optional[ActionPlan]:
        """读取行动计划。"""

    @abstractmethod
    async def select_direction_plan(self, user_id: str, plan_id: str) -> DirectionPlan:
        """选中一套方向方案（其余取消选中），返回被选中的那一套。

        选择**可撤回**：再选另一套就是撤回，不需要单独的"撤回"接口 ——
        单独一个撤销动作会让"当前选的是哪套"出现两个事实来源。
        """

    @abstractmethod
    async def mark_action_task_done(
        self, user_id: str, task_id: str, *, done: bool = True
    ) -> ActionPlan:
        """勾掉 / 取消勾选一个行动任务，返回更新后的计划。"""
