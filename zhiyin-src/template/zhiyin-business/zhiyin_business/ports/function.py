"""功能块契约。

功能块 = 能力池外的外围服务：报告全文/导出、关键节点日历、成就体系。
不占主线导航，挂在资产与产出上。

形态：
- 报告全文        → 读资产版本，不重新生成
- 导出            → 预留入口，没有服务端导出时如实返回 available=false
- 日历            → 规划师写入、教练读取
- 成就            → 只由行为日志实时推导，不落表

注：`CalendarNode` 定义在 `zhiyin_kernel.assets`（因为它要落
`key_calendar_node` 表，基础设施层的表清单必须指向契约而不是业务模型），
本模块只做转出，业务规则（规划师写入、教练读取）仍在本层。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_kernel.assets import Achievement, CalendarNode, TrackEvent

__all__ = [
    "CalendarNode",
    "ExportResult",
    "ExternalIntel",
    "FunctionService",
]


class ExternalIntel(BaseModel):
    """一条外部情报（公开渠道取回的事实）。

    它是**事实条目**，不是结论：标题、正文、来源链接、取回时间。
    界面上要能点回原页面 —— "凭什么这么说"在这类信息上就是那个链接。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str = Field(default="", description="机器可读的类别：occupation / career_case / speciality")
    kind_label: str = Field(
        default="",
        description="类别的中文名。界面显示的是它 —— `career_case` 这种内部取值不许外显",
    )
    title: str = ""
    text: str = ""
    source_url: str = ""
    source_name: str = Field(
        default="",
        description=(
            "来源的中文称呼（如「学职平台·学信网」）。界面上给人看的是它；"
            "链接另存 `source_url`，点开才用 —— 直接把网址摆出来，用户读不懂那是哪"
        ),
    )
    fetched_at: str = ""


class ExportResult(BaseModel):
    """导出结果。第一期返回占位。"""

    model_config = ConfigDict(extra="forbid")

    asset_type: str
    format: Literal["pdf", "docx"]
    object_key: Optional[str] = Field(default=None, description="对象存储键")
    available: bool = Field(default=False, description="第一期恒 False，标记为占位")
    message: str = Field(default="第一期仅预留导出入口")


class FunctionService(ABC):
    """功能块服务 Port。"""

    @abstractmethod
    async def get_report_full_text(self, user_id: str, version: Optional[int] = None) -> dict:
        """报告全文视图。读资产版本，不重新生成。"""

    @abstractmethod
    async def export_asset(
        self, user_id: str, asset_type: str, fmt: Literal["pdf", "docx"]
    ) -> ExportResult:
        """导出资产。第一期返回占位结果。"""

    @abstractmethod
    async def list_calendar_nodes(self, user_id: str) -> list[CalendarNode]:
        """读取关键节点日历。"""

    @abstractmethod
    async def fetch_external_intel(
        self,
        user_id: Optional[str] = None,
        *,
        topic: str = "",
        limit: int = 12,
        refresh: bool = False,
        allow_fetch: bool = True,
    ) -> list["ExternalIntel"]:
        """去公开渠道取回外部情报。**不要求登录**。

        `user_id` 是**可选**的：给了就按这个人的专业与方向取（个性化），
        没给就按 `topic` 取，或者取平台上的通用公开数据。

        为什么不能要求登录：情报这一层是**爬公开数据**的 —— 信息源非常广，
        不可能"每个网站都登一次"，而登录态与"能看到哪些公开信息"本来就没有关系。
        登录只影响一件事：能不能按**你**的画像把结果收窄。

        取的是**公开事实**（专业对口的职业、岗位要求、校友案例、公开网页），
        每条都带来源链接与取回时间 —— 没有来源的条目一律不返回。

        `refresh=False` 时允许用缓存：这条链路会打外部站点，用户每开一次界面
        就打一遍既不礼貌也没必要。

        `allow_fetch=False` 时**只读缓存、不打站点**：抓不到新鲜的（或缓存过期了）
        就返回空表。给"有它更好、没它也能答"的环节用 —— ① 采集与 ⑤ 复盘问的是
        "你的情况""这段时间有什么用"，外部事实是锦上添花；而每轮都去爬一遍的代价
        是实打实的（实测一轮 10 次请求、约 7 秒，全落在用户等回复的那几秒里）。
        ② 诊断 / ③ 决策 / ④ 行动没有外部事实会自己编，那三个环节照样主动取。
        """

    @abstractmethod
    def drop_intel_cache(self, user_id: str) -> None:
        """画像变了就丢掉这个人的情报缓存。

        情报是**按画像取**的（专业决定读哪个专业页，方向决定看哪些职业）。
        不丢的后果实测过：新用户还没画像时取过一次（空），补完画像之后的
        15 分钟里界面一直说"没有和你相关的公开信息" —— 而它其实取得到。
        """

    @abstractmethod
    async def write_calendar_node(self, user_id: str, node: CalendarNode) -> CalendarNode:
        """写入节点（规划师写、教练读）。"""

    @abstractmethod
    async def list_achievements(self, user_id: str) -> list[Achievement]:
        """读取成就。只由行为日志驱动解锁，不做登录/浏览型徽章。"""

    @abstractmethod
    async def list_track_events(self, user_id: str) -> list[TrackEvent]:
        """读取跟踪时间线（工作台 ⑤ 层）。"""

    @abstractmethod
    async def record_track_event(
        self, user_id: str, event: str, payload: dict
    ) -> None:
        """记录一条前端上报的体验型事件（经 RegistryService 校验后调用）。

        归属判断（事件是否属于 frontend 通道）在 Facade 完成，本方法只落库。
        """

    @abstractmethod
    async def list_pending_notifications(self, user_id: str) -> list[dict]:
        """主动介入通知出队（陪伴教练经 Notifier 落下的待阅消息）。

        返回 [{id, by, title, body, action, created_at}]；前端浮窗轮询消费。
        """

    @abstractmethod
    async def mark_notification_read(self, user_id: str, message_id: str) -> int:
        """把一条通知标成已读，返回影响条数。

        为什么必须有回执：读侧按"未读"出队，而前端把浮窗关掉**不回执**的话，
        下一次进页面它会再飘一次 —— 用户看到的就是"这条消息怎么又来了、
        我明明关过"。关掉 = 读过，这条链路要闭合。
        """
