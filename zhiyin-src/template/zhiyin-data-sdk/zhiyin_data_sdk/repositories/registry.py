"""动态资源读取（agent_registry / theory_card / output_contract / task_entry /
policy_params / app_menu / app_route / app_copy / app_banner / app_trust_block /
app_faq）。

第一期允许实现为本地 JSON / YAML，但接口形状不变，统一标记 TODO(第二期) 接
自有动态资源存储。

两类动态资源各有归属，不要混：
- **内容型动态资源**（本文件）：智能体 / 理论卡 / 产出契约 / 任务入口 / 规则参数 /
  前端页面内容（菜单 / 路由 / 文案 / 横幅 / 信任块 / FAQ）；
- **配置型动态资源**（开关）：见 `zhiyin_data_sdk.gateways.feature_flag`——
  它读得极频繁、写入极少，与内容读取的访问特征不同。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from zhiyin_kernel.enums import LoopStage
from zhiyin_kernel.dynamic_content import (
    BannerSpec,
    FaqSpec,
    MenuSpec,
    RouteSpec,
    TrustBlockSpec,
)
from zhiyin_kernel.registry import (
    AgentDescriptor,
    BadgeRuleSpec,
    ChsiFieldSpec,
    OutputContractSpec,
    PolicyParamSet,
    PromptSpec,
    RoutingRuleSpec,
    TaskEntrySpec,
    TaskProgressSpec,
    TheoryCard,
    TrackEventSpec,
)


class RegistryRepository(ABC):
    """动态资源 Repository。"""

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Optional[AgentDescriptor]:
        """读取智能体描述。"""

    @abstractmethod
    async def list_agents(self) -> list[AgentDescriptor]:
        """列出全部智能体。"""

    @abstractmethod
    async def get_theory_card(self, theory_id: str) -> Optional[TheoryCard]:
        """读取理论卡。"""

    @abstractmethod
    async def list_theory_cards(self, theory_ids: Optional[list[str]] = None) -> list[TheoryCard]:
        """批量读取理论卡，用于理论标签展开。"""

    @abstractmethod
    async def get_output_contract(
        self, agent_id: str, stage: LoopStage
    ) -> Optional[OutputContractSpec]:
        """按 `(agent_id, stage)` 读取产出契约。

        查找键是这一对，不是契约 id：一个智能体可以承担多个环节
        （职业顾问同时负责 ②诊断 与 ③决策），按 id 查会表达不出这种情形，
        也会让"哪个契约属于哪个环节"变成隐式约定。实现方必须按该键索引。
        """

    @abstractmethod
    async def list_task_entries(self) -> list[TaskEntrySpec]:
        """读取首页任务入口清单（动态文案）。"""

    @abstractmethod
    async def get_policy_params(self, code: str) -> Optional[PolicyParamSet]:
        """读取业务规则的参数集（阈值 / 冷却期 / 打扰上限等）。

        规则实现在 `zhiyin_business/policies/`，参数一律来自动态资源；
        读不到时实现方返回 None（由调用方决定回落口径），不要静默造默认值。
        """

    # ---------- 前端页面内容（R-API-001） ----------
    #
    # 为什么这些读接口在"动态资源 Repository"而不是 api 层直接读 JSON：
    # `zhiyin-api` 被依赖矩阵禁止 import `zhiyin_data_sdk`（见
    # `tests/test_architecture.py::test_api_does_not_touch_data_sdk`），
    # BFF 只能通过业务侧的 `business/ports/registry.py::RegistryService` 取数。
    # 这里只负责"按 code / sort_order 读出形状"，不做任何组装。
    #
    # 口径：只返回 `status == "enabled"` 的内容，并已按 `sort_order` 升序排好——
    # 上下线与排序是**数据语义**，让每个调用方各写一遍必然漂移。

    @abstractmethod
    async def list_menus(self) -> list[MenuSpec]:
        """顶层导航菜单（已过滤停用项、已按 sort_order 排序）。"""

    @abstractmethod
    async def list_routes(self) -> list[RouteSpec]:
        """前端路由表。"""

    @abstractmethod
    async def get_copy_bundle(self, bundle: str = "zh-CN") -> dict[str, str]:
        """按文案包读取文案（key → text）。

        前端不得硬编码展示文案；BFF 把整包下发给前端，由前端按 key 取用。
        返回空 dict 表示该包未配置——调用方据此决定是否回落，不要静默编文案。
        """

    @abstractmethod
    async def list_banners(self) -> list[BannerSpec]:
        """横幅 / 运营位。"""

    @abstractmethod
    async def list_trust_blocks(self) -> list[TrustBlockSpec]:
        """信任背书块（首页"每步都基于职业咨询成熟方法"单条主线）。"""

    @abstractmethod
    async def list_faqs(self) -> list[FaqSpec]:
        """常见问题。"""

    # ---------- 埋点事件归属（决策 14：后端派生为主 + 前端上报为辅） ----------

    @abstractmethod
    async def list_track_events(self) -> list[TrackEventSpec]:
        """埋点事件归属表（后端派生 / 前端上报）。

        供 `POST /app/track` 与埋点实现校验"这个事件该由谁记"。
        """

    # ---------- 产品口径：成就规则 / 进度文案 / 学信网字段 ----------

    @abstractmethod
    async def list_badge_rules(self) -> list[BadgeRuleSpec]:
        """成就解锁规则：哪条行为解锁哪个成就（已按 sort_order 排序）。"""

    @abstractmethod
    async def list_task_progress(self) -> list[TaskProgressSpec]:
        """生成类 AI 任务的进度文案，按 code 取用。"""

    @abstractmethod
    async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
        """学信网报告字段 → 画像键 + 展示名（已按 order 排序）。"""

    # ---------- AI 提示词与编排规则（AI 面向切面的读侧） ----------
    #
    # 这一类与其他动态资源的访问特征不同：它在**每一次模型调用前**都会被读一次，
    # 是热路径。因此实现方必须按 (layer, agent_id, stage) 建立索引后再取，
    # 不要每次全量加载再过滤。

    @abstractmethod
    async def get_prompt(self, code: str) -> Optional[PromptSpec]:
        """按 code 读取一条提示词模板。取不到返回 None，由调用方决定回落口径。

        **不要静默编一条默认提示词**：提示词缺席时模型会用通用聊天的方式回答，
        而症状是"这个环节突然不说人话了"，比直接报错难查得多。
        """

    @abstractmethod
    async def list_prompts(
        self,
        *,
        layer: Optional[str] = None,
        agent_id: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[PromptSpec]:
        """按归属读取提示词，只返回启用项。

        三个条件都是可选的窄化，不是精确匹配的组合键：调用方通常先按
        `agent_id` 取该角色的全部条目，再自己按 `stage` 挑一条。
        """

    @abstractmethod
    async def list_routing_rules(
        self, kind: Optional[str] = None
    ) -> list[RoutingRuleSpec]:
        """编排判定规则，已按 `priority` 升序、只返回启用项。

        `kind` 取 `intent` / `stage` / `lead`；为空表示全部返回。
        排序是数据语义（越小越先判定），不要让每个调用方各排一遍。
        """
