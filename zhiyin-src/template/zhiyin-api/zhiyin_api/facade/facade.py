"""Application Facade 契约。

职责（R-API-004）：
- 编排业务层服务调用，组装 View DTO；
- 转换一律交给 `zhiyin_api/dto/mappers.py`（业务模型 → api DTO），
  本层不内联字段映射，业务模型变更不外溢到前端；
- 不写业务规则，不直接访问数据库 / 模型 / 知识库。

取数通道（api 被禁止 import `zhiyin_data_sdk`，所以只有这两条业务侧出口）
------------------------------------------------------------------------
| 需要的东西 | 出口 |
| --- | --- |
| 我是谁（认证主体 → 本地用户记录） | `business/ports/identity.py::IdentityService` |
| 页面长什么样（菜单 / 路由 / 任务入口 / 文案 / 横幅 / 信任块 / FAQ / 开关） | `business/ports/registry.py::RegistryService` |

因此 Facade 的构造依赖至少包含这两个服务；`bootstrap()` 没有它们就无法返回任何内容。
其余能力（对话 / 工作台 / 资产）分别走 `Orchestrator` 与 `WorkspaceService` / `AssetService`。

装配方式：zhiyin-boot 在启动时调用 configure_facade(实现)，Controller 通过
get_facade() 获取。这样 Controller 不依赖任何具体实现，替换实现无需改接口层。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Optional

from fastapi import Request

from zhiyin_kernel.enums import AssetType
from zhiyin_api.dto.asset import (
    ActionPlanView,
    ActionTaskDoneRequest,
    AssetVersionView,
    CalendarNodeView,
    DirectionPlanListView,
    TrackEventView,
    ExportRequest,
    ExportResultView,
    ReportFullTextView,
)
from zhiyin_api.dto.bootstrap import BootstrapView, TheoryCardView
from zhiyin_api.dto.bootstrap import PortalView
from zhiyin_api.dto.common import CoachNotificationView
from zhiyin_api.dto.conversation import (
    ConversationMessageView,
    ConversationTurnView,
    ConversationMaterialView,
    MessageRequest,
    SessionListView,
    TaskEnterRequest,
    TaskSessionView,
)
from zhiyin_api.dto.workspace import WorkspacePageView
from zhiyin_api.dto.track import TrackEventAck, TrackEventRequest
from zhiyin_api.dto.note import NoteAck, NoteCreateRequest, NoteDoneRequest, NoteView
from zhiyin_api.dto.workspace import (
    AcademicImportAck,
    AcademicImportRequest,
    AcademicImportUpload,
    AcademicRevokeAck,
)


class ApplicationFacade(ABC):
    """BFF 应用门面。"""

    # ---------- 身份 ----------

    @abstractmethod
    async def resolve_user_id(self, request: Request) -> str:
        """解析当前用户。

        实现只做 HTTP → 业务形状的翻译：从请求里取 token，交给业务侧的
        `IdentityService.current_user()`，返回其 `user_id`。**不要**在这里访问
        用户表或鉴权网关（api 层被禁止 import data_sdk）。
        """

    # ---------- 启动 ----------

    @abstractmethod
    async def bootstrap(self, user_id: str) -> BootstrapView:
        """启动装配视图。底层取数全 async，因此本方法也是 async。"""

    @abstractmethod
    async def get_portal(self) -> PortalView:
        """门户内容（**公开，不需要身份**）。

        门户是访客第一眼看到的一页，它的内容全是产品自己的话（文案 / 信任块 /
        横幅 / FAQ / 任务入口 / 开关），与"我是谁"无关 —— 所以这个接口不解析身份。
        此前门户文案写死在前端，是"文案不进代码"这条底线上的最后一处例外。
        """

    @abstractmethod
    async def get_theory_card(self, theory_id: str) -> Optional[TheoryCardView]:
        """理论卡正文（点开理论标签时用）。

        取不到返回 None，前端据此如实说明"这张卡还没配" ——
        理论卡是"一切都能追溯"的可见部分，宁可说没有，也不要显示一张空卡。
        """

    # ---------- 对话 ----------

    @abstractmethod
    async def list_sessions(self, user_id: str) -> SessionListView:
        """左栏会话列表。"""

    @abstractmethod
    async def list_session_turns(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationMessageView]:
        """一条会话的逐轮原文（用户与主理各算一轮），按时间正序。

        为什么要有它：`list_sessions` 只给会话清单，点进去看不到"这条会话发生过什么"。
        逐轮原文此前**完全没有落库**（库里只有累积摘要），所以这不是界面缺一半，
        是数据缺一半。
        """

    @abstractmethod
    async def enter_task(self, user_id: str, body: TaskEnterRequest) -> TaskSessionView:
        """进入任务：判定环节 → 选主理 → 建会话或续接。"""

    @abstractmethod
    async def send_message(
        self, user_id: str, body: MessageRequest
    ) -> ConversationTurnView:
        """处理一轮消息，返回最短结论 + 告知 + 引导 + 管线卡。"""

    @abstractmethod
    async def upload_material(
        self, user_id: str, *, name: str, data: bytes
    ) -> ConversationMaterialView:
        """收下用户在对话里交的一份材料（抽正文 → 存起来）。

        回执**不带正文**：正文只进模型输入，不进对话气泡 —— 用户抱怨的正是
        "传个文件，内容被摊在对话框里"。
        """

    # ---------- 工作台 ----------

    @abstractmethod
    async def get_workspace(self, user_id: str) -> WorkspacePageView:
        """工作台聚合视图。"""

    # ---------- 资产 ----------

    @abstractmethod
    async def list_asset_versions(
        self, user_id: str, asset_type: AssetType
    ) -> list[AssetVersionView]:
        """资产版本列表（含 diff 与依赖字段）。"""

    @abstractmethod
    async def get_report_full_text(
        self, user_id: str, version: Optional[int] = None
    ) -> ReportFullTextView:
        """完整报告页正文。"""

    @abstractmethod
    async def export_asset(self, user_id: str, body: ExportRequest) -> ExportResultView:
        """导出资产（第一期占位）。"""

    # ---------- ③ 决策 / ④ 行动（资产正文 + 用户动作） ----------

    @abstractmethod
    async def get_direction_plans(self, user_id: str) -> DirectionPlanListView:
        """三套方向方案（主攻 / 平行 / 保底）。没有方案时返回空列表。"""

    @abstractmethod
    async def select_direction_plan(
        self, user_id: str, option_id: str
    ) -> DirectionPlanListView:
        """选中一套方案（可撤回：再选另一套就是撤回），返回更新后的全量方案。"""

    @abstractmethod
    async def get_action_plan(self, user_id: str) -> ActionPlanView:
        """行动计划正文（含"现在这一件"）。没有计划时 `has_plan=False`。"""

    @abstractmethod
    async def list_calendar_nodes(self, user_id: str) -> list[CalendarNodeView]:
        """关键节点日历（规划师写入、教练读取）。此前只有写、没有读。"""

    @abstractmethod
    async def list_track_events(
        self, user_id: str, *, limit: int = 50
    ) -> list[TrackEventView]:
        """跟踪时间线（复盘环节的载体）。此前同样只有写、没有读。"""

    @abstractmethod
    async def set_action_task_done(
        self, user_id: str, body: ActionTaskDoneRequest
    ) -> ActionPlanView:
        """勾掉 / 取消勾选一个行动任务，返回更新后的计划。"""

    # ---------- AI 任务（SSE） ----------

    @abstractmethod
    def run_ai_task(self, user_id: str, key: str, arg: str = "") -> AsyncIterator[dict]:
        """执行一个 AI 任务，逐帧 yield 进度 / 终帧。"""

    # ---------- 主动介入通知 ----------

    @abstractmethod
    async def list_pending_notifications(self, user_id: str) -> list[CoachNotificationView]:
        """教练主动介入通知出队（前端浮窗轮询）。"""

    # ---------- 鉴权 ----------

    @abstractmethod
    async def login_account(self, account: str, password: str) -> dict:
        """账号密码登录。"""

    @abstractmethod
    async def register_account(self, account: str, password: str) -> str:
        """注册账号。"""

    @abstractmethod
    async def revoke_token(self, token: str) -> None:
        """撤销令牌（登出）。"""

    # ---------- 埋点 ----------

    @abstractmethod
    async def track_event(
        self, user_id: str, body: TrackEventRequest
    ) -> TrackEventAck:
        """接收前端埋点上报。

        实现要求：先经 `RegistryService.list_track_events()` 校验事件属于
        `channel=frontend`，再决定落库口径（体验型事件存储是后续待办）。
        本层不写事件归属判断，只编排。
        """

    # ---------- 他自己写下的东西（自建待办 / 写下的目标） ----------

    @abstractmethod
    async def revoke_academic(self, user_id: str) -> "AcademicRevokeAck":
        """清空导入的课表与成绩（画像里那两条摘要一起删）。"""

    @abstractmethod
    async def import_academic(
        self, user_id: str, body: "AcademicImportRequest"
    ) -> "AcademicImportAck":
        """导入课表与成绩单（学生自己贴原文）。"""

    @abstractmethod
    async def import_academic_files(
        self, user_id: str, body: "AcademicImportUpload"
    ) -> "AcademicImportAck":
        """导入课表与成绩单（学生自己传文件）。

        与上面那条是**同一个动作的两种入口**：读出来什么、写进哪几条画像摘要，
        两条路必须一致 —— 一致性由业务层保证（都落到 `import_`）。
        """

    @abstractmethod
    async def list_notes(self, user_id: str) -> list["NoteView"]:
        """他写下的全部内容，新写的在前。"""

    @abstractmethod
    async def add_note(self, user_id: str, body: "NoteCreateRequest") -> "NoteView":
        """记下他写的一句话。"""

    @abstractmethod
    async def set_note_done(
        self, user_id: str, note_id: str, body: "NoteDoneRequest"
    ) -> "NoteView":
        """勾掉 / 取消勾掉一条。"""

    @abstractmethod
    async def remove_note(self, user_id: str, note_id: str) -> "NoteAck":
        """删掉一条。"""

    @abstractmethod
    async def reload_dynamic_config(self) -> dict[str, Any]:
        """重新装载动态配置（环节口径 / 气泡编排 / 采集规则）。

        配置的生效时机是**可控的时刻**：启动一次，之后只在收到这个指令时再读。
        不做"每次请求读库"——那种灵活会让"刚才还好的行为突然变了"无从解释。

        ⚠️ 这是个**运维动作**，不是普通用户接口。当前部署是单机本地，
        所以只要求已登录；接入多用户之前必须先有管理员角色（UserRole.ADMIN
        已经定义好了，但还没有任何地方签发它）。
        """


# ---------- 装配与获取 ----------

_facade: Optional[ApplicationFacade] = None


class FacadeNotConfiguredError(RuntimeError):
    """Facade 未装配。

    第一期业务服务尚未实现，接口层会得到本异常；`create_app` 会把它统一映射为
    ErrorCode.DEPENDENCY_UNAVAILABLE：不中断核心调用链，也不静默吞掉。
    """


def configure_facade(facade: ApplicationFacade) -> None:
    """由 zhiyin-boot 在启动时调用。"""
    global _facade
    _facade = facade


def get_facade() -> ApplicationFacade:
    """获取已装配的 Facade。未装配时抛出可识别的异常，避免静默返回空实现。"""
    if _facade is None:
        raise FacadeNotConfiguredError(
            "ApplicationFacade 尚未装配：请在 zhiyin-boot 启动时调用 configure_facade()"
        )
    return _facade


def reset_facade() -> None:
    """清空已装配的 Facade。供测试隔离使用，业务代码不应调用。

    与 `zhiyin_api.runtime.reset_runtime()` 同源：装配是全局注入，测试之间必须
    显式还原，否则"某个用例 wire 过一次"会让后面的用例看到别人的装配状态。
    `tests/conftest.py` 的自动夹具对两者统一还原。
    """
    global _facade
    _facade = None
