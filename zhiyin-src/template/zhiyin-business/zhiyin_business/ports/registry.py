"""动态资源读侧契约（业务侧）。

为什么需要这一层（与 `ports/identity.py` 同源的理由）
--------------------------------------------------
`/app/bootstrap`（R-API-001）要一次返回**菜单 / 路由 / 任务入口 / 文案 / 功能开关**，
这些数据全在动态资源里；而取数的契约（`RegistryRepository` / `FeatureFlagGateway`）
定义在 `zhiyin_data_sdk`，**api 层按依赖矩阵不许 import data_sdk**
（`tests/test_architecture.py::test_api_does_not_touch_data_sdk`）。

于是只有两条路：

1. 放宽矩阵，让 api 直连动态资源契约——把已收口的跨层直连重新打开；
2. 由业务层包出一个读侧 Port，api 只面对业务抽象 ← **已采用**

这与 `IdentityService` 是同一类问题的同一个解法：**api 与数据访问契约之间的通道
只允许在业务层开**。两条通道的分工是——

- `IdentityService`：我是谁（认证主体 → 本地用户记录补齐，属业务行为）；
- `RegistryService`：页面长什么样（原文/开关读取，不做组装、不写业务判断）。

边界（很重要）
-------------
- 本 Port **只读**，不提供任何写入动态资源的入口——配置写入属运营后台，不在本期范围；
- 本 Port **不组装页面视图**：返回的是内核形状（`MenuSpec` / `CopySpec` / …）。
  "拼成 `BootstrapView`"是 BFF 的翻译工作，放在 `zhiyin_api/dto/mappers.py`；
- 本 Port **不认识 HTTP**，也不认识任何 data_sdk 类型（参数与返回值必须能在
  `zhiyin_kernel` 里找到）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from zhiyin_kernel.dynamic_content import (
    BannerSpec,
    FaqSpec,
    MenuSpec,
    RouteSpec,
    TrustBlockSpec,
)
from zhiyin_kernel.registry import (
    AgentDescriptor,
    CachePolicy,
    LayoutPolicy,
    PromptSpec,
    RoutingRuleSpec,
    StageSpec,
    TaskEntrySpec,
    UserSignalSpec,
)
from zhiyin_kernel.registry import (
    BadgeRuleSpec,
    ChsiFieldSpec,
    TaskProgressSpec,
    TheoryCard,
)
from zhiyin_kernel.registry import TrackEventSpec


class RegistryService(ABC):
    """动态资源读侧服务（BFF 取数入口）。"""

    # ---------- 首页任务入口 ----------

    @abstractmethod
    async def list_task_entries(self) -> list[TaskEntrySpec]:
        """首页任务入口清单，已按 sort_order 排序。

        文案与路由规则由动态资源下发，前端不得硬编码任务卡。
        """

    @abstractmethod
    async def get_layout_policy(self, code: str = "default") -> Optional[LayoutPolicy]:
        """控制台气泡的编排策略（顺序 / 空间 / 出现条件）。

        **"先看哪一块"是产品判断，不是前端常量**：冲刺期该先看到窗口期，
        探索期该先看到画像缺口，刚核验完学籍采集块就该让位。
        写死在组件里，这些判断就只能靠发版改。
        """

    @abstractmethod
    async def list_stages(self) -> list[StageSpec]:
        """五个环节的展示口径（名称 / 位次 / 资产），已按 order 排序。

        这一份**必须只有一处**：它以前在 api 的 mapper、工作台服务、
        AI 任务的进度文案里各写了一遍，改一处忘一处就前后端不一致。
        """

    @abstractmethod
    async def list_user_signals(self) -> list[UserSignalSpec]:
        """用户信号线索表（已按 order 排序）。

        采集优先级原来只看"还缺什么 + 走到哪一环节"，两条都是系统的视角。
        这一份把**用户自己写过的话**接进来：他写了想冲秋招，先去取毕业时间
        就是他的账。没有这张表，回执就永远说不出"因为你写了…"。
        """

    @abstractmethod
    async def get_cache_policy(self) -> Optional[CachePolicy]:
        """读缓存策略：哪片 TTL 多长、什么事件让它失效。

        为什么它在动态资源而不是 Settings：TTL 是运行参数（改它不发版），
        而"哪个事件该让哪片缓存失效"必须和其它业务规则的参数放在一起 ——
        散在代码里的失效调用，漏一个就是"用户改完画像、界面上还是旧的"。
        """

    @abstractmethod
    async def get_collection_policy(self) -> dict[str, Any]:
        """采集门槛策略（`policy_params` 的 `profile_collection` 一条）。

        它回答"采到什么时候算够了"：关键字段覆盖到多少、整体把握到多少，
        就可以往下一环走。以前这张表**没有任何代码读** —— 门槛实际上由模型
        自由心证，"用户聊两句就想走，它还在一条条追问"就是这么来的。
        读不到返回空字典，调用方按"不拦"处理。
        """

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Optional[AgentDescriptor]:
        """读取智能体描述，用于把 `agent_id` 翻成展示名。

        用途举例：任务入口的"开场主理"、左栏会话的主理名、顶栏徽章。
        取不到时调用方按"展示名回落为 agent_id"处理，**不要**静默编名字。
        """

    # ---------- 理论卡（"一切都能追溯"的可见部分） ----------
    #
    # 16 张理论卡一直躺在 `data/registry/theory_cards.json` 里（名 / 流派 /
    # 通俗说明 / 在本产品里怎么用），数据访问契约也早就有 `get_theory_card`。
    # **缺的只是从这里到 api 的出口** —— 于是前端点开理论标签只看得到 id 与名字。
    # 这两条方法就是那个出口：把已有内容接出来，而不是再造一份。

    @abstractmethod
    async def get_theory_card(self, theory_id: str) -> Optional[TheoryCard]:
        """按 id 取一张理论卡；取不到返回 None，由调用方如实说明。"""

    @abstractmethod
    async def list_theory_cards(
        self, theory_ids: Optional[list[str]] = None
    ) -> list[TheoryCard]:
        """批量取理论卡；`theory_ids` 为空表示取全部。"""

    # ---------- 前端页面内容 ----------

    @abstractmethod
    async def list_menus(self) -> list[MenuSpec]:
        """顶层导航菜单（已过滤停用项、已排序）。"""

    @abstractmethod
    async def list_routes(self) -> list[RouteSpec]:
        """前端路由表。"""

    @abstractmethod
    async def get_copy_bundle(self, bundle: str = "zh-CN") -> dict[str, str]:
        """按文案包读取文案（key → text）。未配置时返回空 dict，由调用方决定回落。"""

    @abstractmethod
    async def list_banners(self) -> list[BannerSpec]:
        """横幅 / 运营位。"""

    @abstractmethod
    async def list_trust_blocks(self) -> list[TrustBlockSpec]:
        """信任背书块（首页"每步都基于职业咨询成熟方法"）。"""

    @abstractmethod
    async def list_faqs(self) -> list[FaqSpec]:
        """常见问题。"""

    # ---------- 埋点事件归属 ----------

    @abstractmethod
    async def list_track_events(self) -> list[TrackEventSpec]:
        """埋点事件归属表（后端派生 / 前端上报）。

        供 Facade 的 `POST /app/track` 实现校验：只有 `channel=frontend` 的事件
        允许从客户端上报，`channel=backend` 的应由后端自行派生。
        """

    # ---------- 产品口径（此前写在业务层代码里，现在进动态资源） ----------

    @abstractmethod
    async def list_badge_rules(self) -> list[BadgeRuleSpec]:
        """成就解锁规则：哪条行为解锁哪个成就。"""

    @abstractmethod
    async def list_task_progress(self) -> list[TaskProgressSpec]:
        """生成类 AI 任务的进度文案。"""

    @abstractmethod
    async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
        """学信网报告字段 → 画像键 + 展示名 + 顺序。"""

    # ---------- AI 提示词与编排规则 ----------

    @abstractmethod
    async def get_prompt(self, code: str) -> Optional[PromptSpec]:
        """按 code 读一条提示词模板。

        业务层要的是**用户可见的那句话**：换主理的告知文案、全新会话的澄清追问。
        它们以前是用字符串拼出来的，拼接时把内部环节名与智能体标识直接写进了
        用户能看到的话里 —— 那不是文案问题，是口径问题。改成从动态资源取。
        """

    @abstractmethod
    async def list_routing_rules(self, kind: Optional[str] = None) -> list[RoutingRuleSpec]:
        """编排判定规则（关键词到意图 / 意图到环节），已按 priority 排序。

        为什么它不是代码：这些词表是**产品语言**。用户说「投了没回音」和
        「投了没人理」是同一件事，加一个词不该走一次发版；而这类说法算「想验证
        方向」还是「卡住了」，是会随产品判断变化的取舍。
        """

    # ---------- 功能开关 ----------

    @abstractmethod
    async def feature_flags(self) -> dict[str, bool]:
        """功能开关快照（报告全文 / 导出 / 日历 / 成就 / 导师 / 演示）。

        前端按开关决定功能块可见性；本方法只读，不改开关。
        """


__all__ = ["RegistryService"]
