"""业务契约的通用构件。

三条全局设计约束（业务底线）在本模块固化为模型：
1. 长内容不进对话流 —— 契约里只出现"最短结论"，全文走资产；
2. 换主理必须显式告知 —— Disclosure 是各环节产出的必填项之一；
3. 每轮以行为引导收尾 —— BehaviorGuide 是各环节产出的必填项之一。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.enums import AssetType, BehaviorEventType


class TheoryRef(BaseModel):
    """理论引用。用于"理论可点开"。"""

    model_config = ConfigDict(extra="forbid")

    theory_id: str = Field(description="理论卡 id，指向 theory_card")
    name: str = Field(description="展示名，如 霍兰德 RIASEC")
    stage: str = Field(default="", description="所属环节标识")


class Evidence(BaseModel):
    """证据引用。产出必须可追溯（可解释性是硬要求）。"""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(description="被支撑的结论")
    source: str = Field(default="", description="来源，如 画像字段 / 知识库文档 / JD")
    detail: str = ""


class GuideOption(BaseModel):
    """行为引导 · 选项。"""

    model_config = ConfigDict(extra="forbid")

    option_id: str
    label: str
    value: Any = None


class GuideTask(BaseModel):
    """行为引导 · 小任务。颗粒度要求"今天/本周勾得掉"。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    text: str
    due_date: Optional[datetime] = None


class GuideReminder(BaseModel):
    """行为引导 · 提醒。"""

    model_config = ConfigDict(extra="forbid")

    title: str
    due_at: Optional[datetime] = None
    detail: str = ""


class BehaviorGuide(BaseModel):
    """行为引导收尾。

    结尾必须是四选一：一个追问 / 一组选项 / 一个小任务 / 一条提醒。
    禁止空转寒暄与无下一步的总结。
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["question", "options", "task", "reminder"]
    text: str = Field(description="引导文案")
    question: Optional[str] = Field(default=None, description="kind=question 时的追问")
    options: list[GuideOption] = Field(default_factory=list, description="kind=options 时")
    task: Optional[GuideTask] = Field(default=None, description="kind=task 时")
    reminder: Optional[GuideReminder] = Field(default=None, description="kind=reminder 时")


class Disclosure(BaseModel):
    """显式告知。三种场合：换主理 / 换理论依据 / 结论变化。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["lead_change", "theory_change", "conclusion_change"]
    text: str = Field(description="对用户说明原因的一句话")
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    from_agent: Optional[str] = None
    to_agent: Optional[str] = None


class AgentBadge(BaseModel):
    """主理徽章。顶栏与对话气泡展示"现在是谁在帮我、依据什么"。"""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    role_summary: str = ""
    theory_refs: list[TheoryRef] = Field(default_factory=list)


class ChartPoint(BaseModel):
    """图上的一个点。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    value: float


class ChartSpec(BaseModel):
    """主理在对话里给的一张图。

    为什么由**服务端按真实数据生成**，而不是让模型自由写图表规格：
    模型写的数字没人能核对（它连画像里有几条都常常说错）。这里只允许
    用服务端手上已有的实测值（画像各维把握、方案匹配度…），图上的每个点
    都能追回它来自哪条数据。
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["bars"] = "bars"
    title: str = ""
    unit: str = ""
    points: list[ChartPoint] = Field(default_factory=list)


class IntelRef(BaseModel):
    """对话里引用的一条外部情报。

    它让"这句话凭什么"能点回原页面 —— 与理论卡引用是同一套道理：
    引用只给 id 与展示名，正文与原链接按需展开。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = ""
    kind_label: str = ""
    source_name: str = ""
    source_url: str = ""


class Renderable(BaseModel):
    """一个**可视件**：这一轮要摆到用户眼前的一块界面。

    为什么要有它（而不是继续加 `chart` 这种专用字段）：
    产品会不断做出新的"功能模块" —— 后端一段取数逻辑 + 前端一整套渲染效果。
    每做一个就往契约里加一个字段（chart / timeline / matrix / …），
    模型侧、服务端、前端三处都要跟着改，而且**模型看得见的字段会越来越杂**。

    所以这里把"可视件"抽象成一种东西：

    · `kind` 决定前端用哪个组件画（也是服务端的白名单键，见 `policies/renderers.py`）；
    · `payload` 是那个组件要的数据，**由服务端校验**，模型碰不到数值；
    · `source_refs` 是"这些数据哪来的"，能点回原页面 —— 与结论可溯源是同一条口径。

    新增一个模块 = 注册一种 kind（服务端校验）+ 写一个前端组件 + 把它挂成工具。
    契约这边**不用再动**。
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="渲染件类型，前端按它选组件")
    title: str = Field(default="", description="给用户看的一句话标题")
    payload: dict[str, Any] = Field(default_factory=dict, description="组件要的数据")
    source_refs: list[IntelRef] = Field(
        default_factory=list, description="数据来源，可点回原页面；没有来源就留空"
    )


class ConversationMessage(BaseModel):
    """对话消息。长内容不进对话流，这里只放最短结论。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["agent", "user", "system"]
    text: str
    agent_id: Optional[str] = None
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    #: 这一轮主理顺手给的图（真实数据，见 `ChartSpec`）；没有就是 None
    chart: Optional[ChartSpec] = None
    #: 这一轮主理调工具产出的**可视件**（图 / 时间线 / 对比表…）。
    #: `chart` 是其中最常见的一种，单独留着是为了不让已经在渲染它的前端白改。
    renderables: list[Renderable] = Field(default_factory=list)
    #: 这一轮用到的外部情报来源（可点回原页面）；没有就是空表
    intel_refs: list[IntelRef] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class BehaviorEventDraft(BaseModel):
    """待写入的行为日志草稿。

    环节产出里声明要记什么行为，由黑板服务统一落库。
    """

    model_config = ConfigDict(extra="forbid")

    event_type: BehaviorEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    related_asset_ids: list[str] = Field(default_factory=list)


class AssetUpdateDraft(BaseModel):
    """待写入的资产更新草稿。可由影响面传播产生。"""

    model_config = ConfigDict(extra="forbid")

    asset_type: AssetType
    depends_on_profile_keys: list[str] = Field(default_factory=list)
    diff_from_previous: Optional[str] = None
    reason: str = Field(default="", description="为什么更新，用于生成 diff 文案")
