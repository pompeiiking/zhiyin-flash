"""API 通用 DTO：统一响应、错误码，以及跨页面复用的对话构件。

`trace_id` 由 `zhiyin_api.context` 的请求上下文兜底填充：Controller 与 Facade
都不需要传它，也不允许自己生成（生成点只有 `create_app` 挂载的中间件一处）。
这样"契约里有 trace_id、链路上没人生产"这类静默空值不可能再出现。

**为什么徽章 / 告知行 / 行为引导 / 理论引用也在这里**：它们同时出现在对话回包、
管线卡、工作台面板里。此前这四个形状在 DTO 里都是 `dict[str, Any]`——契约上写着
"有这个字段"，但没人知道里面是什么。前端只能靠手写一份同形接口，两边各自维护；
字段名一旦漂移（后端 `theory_id`、前端读 `id`），编译期与运行期都不报错，
只是理论标签点开是空的。现在逐字段声明，前端类型由 `npm run gen:api` 生成。
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_api.context import current_trace_id

T = TypeVar("T")


class ErrorCode(IntEnum):
    """统一错误码。前端据此提示，不解析后端文案。"""

    OK = 0
    INVALID_PARAM = 1001          # 参数校验失败
    NOT_FOUND = 1002              # 资源不存在
    CONFLICT = 1003               # 版本冲突 / 重复提交
    UNAUTHORIZED = 1004           # 未登录，需触发登录拦截
    GUEST_LIMIT = 1005            # 游客采集超过 2 问
    STAGE_UNCERTAIN = 1006        # 环节判定不确定，已回落澄清追问
    DEPENDENCY_UNAVAILABLE = 1007 # 模型 / 知识库不可用（已降级）
    INTERNAL = 1999


class TheoryRefView(BaseModel):
    """理论引用。前端据此渲染「理论标签」，点开取 `GET /app/theory-cards/{id}` 的正文。

    这里只有 id / 展示名 / 所属环节：**正文不随引用一起下发**（一次回复可能引三五个
    理论，正文按需取）。标签本身可点开，靠的就是 id 与接口路径对得上。
    """

    model_config = ConfigDict(extra="forbid")

    theory_id: str = Field(description="理论卡 id，与 /app/theory-cards/{theory_id} 对应")
    name: str = Field(description="展示名，如 霍兰德 RIASEC")
    stage: str = Field(default="", description="所属环节标识")


class AgentBadgeView(BaseModel):
    """主理徽章：此刻是谁在帮我、依据哪些理论。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    role_summary: str = ""
    theory_refs: list[TheoryRefView] = Field(default_factory=list)


class GuideOptionView(BaseModel):
    """行为引导 · 可点选项。"""

    model_config = ConfigDict(extra="forbid")

    option_id: str
    label: str
    value: Any = None


class GuideTaskView(BaseModel):
    """行为引导 · 小任务。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    text: str
    due_date: Optional[datetime] = None


class GuideReminderView(BaseModel):
    """行为引导 · 提醒。"""

    model_config = ConfigDict(extra="forbid")

    title: str
    due_at: Optional[datetime] = None
    detail: str = ""


class BehaviorGuideView(BaseModel):
    """行为引导：一轮回复的收尾。四选一，禁止空转寒暄。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["question", "options", "task", "reminder"]
    text: str = ""
    question: Optional[str] = None
    options: list[GuideOptionView] = Field(default_factory=list)
    task: Optional[GuideTaskView] = None
    reminder: Optional[GuideReminderView] = None


class DisclosureView(BaseModel):
    """显式告知行：换主理 / 换理论依据 / 结论变化。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["lead_change", "theory_change", "conclusion_change"]
    text: str
    theory_refs: list[TheoryRefView] = Field(default_factory=list)
    from_agent: Optional[str] = None
    to_agent: Optional[str] = None


class CoachNotificationView(BaseModel):
    """教练主动介入的通知（前端浮窗轮询消费）。

    形状由两个读侧实现共同决定：`InMemoryNotificationRepository`（本地消息表）与
    `PostgresNotificationRepository`（`orc_notification`）。两边都至少有
    id / title / body / channel / occurred_at，本地那份还多带 user_id 这类调试字段。

    因此这里用 `extra="ignore"` 而不是 `forbid`：**多出来的字段不该让这个接口报 500**，
    但 `id` / `title` 缺了前端就没法渲染，仍需强制。

    此前这个接口的返回类型是裸 `list`，前端只能猜字段（它猜的是 `by`——
    后端从来没有这个字段），于是每条通知署名永远为空。现在逐字段声明。
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    body: str = ""
    channel: str = Field(default="", description="通知渠道：in_app / email / sms")
    action: Optional[dict[str, Any]] = Field(default=None, description="可点的动作")
    related_task_id: Optional[str] = None
    occurred_at: Optional[str] = Field(default=None, description="ISO8601 时间串")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应信封。

    对应 Wanwu 平台的 code == 0 成功口径，便于前端统一拦截。
    """

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode = ErrorCode.OK
    message: str = "ok"
    data: Optional[T] = None
    trace_id: str = Field(
        default_factory=current_trace_id,
        description="链路追踪 id，由 BFF 生成并回写 X-Trace-Id 响应头；日志排查用",
    )
