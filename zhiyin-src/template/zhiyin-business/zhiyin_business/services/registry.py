"""动态资源读侧服务实现。"""

from __future__ import annotations

import logging
from typing import Optional

from zhiyin_business.ports.registry import RegistryService
from zhiyin_data_sdk.gateways.feature_flag import FeatureFlagGateway
from zhiyin_data_sdk.repositories import RegistryRepository
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
    CachePolicy,
    ChsiFieldSpec,
    PromptSpec,
    RoutingRuleSpec,
    TaskEntrySpec,
    TaskProgressSpec,
    TheoryCard,
    TrackEventSpec,
)


logger = logging.getLogger(__name__)


class DefaultRegistryService(RegistryService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self, registry: RegistryRepository, feature_flags: FeatureFlagGateway
    ) -> None:
        self._registry = registry
        self._feature_flags = feature_flags

    async def list_task_entries(self) -> list[TaskEntrySpec]:
        return await self._registry.list_task_entries()

    async def get_agent(self, agent_id: str) -> Optional[AgentDescriptor]:
        return await self._registry.get_agent(agent_id)

    async def get_theory_card(self, theory_id: str) -> Optional[TheoryCard]:
        """取一张理论卡。直通数据访问契约，业务层不做二次解释。"""
        return await self._registry.get_theory_card(theory_id)

    async def list_theory_cards(
        self, theory_ids: Optional[list[str]] = None
    ) -> list[TheoryCard]:
        return await self._registry.list_theory_cards(theory_ids)

    async def list_menus(self) -> list[MenuSpec]:
        return await self._registry.list_menus()

    async def list_routes(self) -> list[RouteSpec]:
        return await self._registry.list_routes()

    async def get_layout_policy(self, code: str = "default"):
        """气泡编排策略：读侧直通动态资源，业务层不做二次解释。"""
        return await self._registry.get_layout_policy(code)

    async def list_stages(self):
        """五个环节的展示口径。"""
        return await self._registry.list_stages()

    async def list_collection_rules(self):
        """采集规则：缺什么、去哪儿取、为什么。"""
        return await self._registry.list_collection_rules()

    async def list_user_signals(self):
        """用户信号：用户自己写下的话里的线索词，用来把某条数据顶到前面。"""
        return await self._registry.list_user_signals()

    async def get_cache_policy(self):
        """读缓存策略（`policy_params` 的 cache 一条）。

        参数是通用键值对，这里做一次**形状校验**：参数集是动态资源，
        写错一个字段名不该等到运行缓存时才炸 —— 校验不过就当没有策略，
        读侧退回"不缓存、直接读库"（缓存本就不该是必需依赖）。
        """
        params = await self._registry.get_policy_params("cache")
        if params is None or not params.value:
            return None
        try:
            return CachePolicy.model_validate(params.value)
        except Exception:
            logger.exception("读缓存策略格式不对，本次按「不缓存」处理")
            return None

    async def get_collection_policy(self) -> dict:
        """采集门槛策略（`policy_params` 的 profile_collection 一条）。

        读不到就返回空字典 —— 调用方按"不拦"处理。把"配置没读到"变成
        "用户被卡在采集里出不来"，是更坏的那个结果。
        """
        params = await self._registry.get_policy_params("profile_collection")
        if params is None or not isinstance(params.value, dict):
            return {}
        return dict(params.value)

    async def get_copy_bundle(self, bundle: str = "zh-CN") -> dict[str, str]:
        return await self._registry.get_copy_bundle(bundle)

    async def list_banners(self) -> list[BannerSpec]:
        return await self._registry.list_banners()

    async def list_trust_blocks(self) -> list[TrustBlockSpec]:
        return await self._registry.list_trust_blocks()

    async def list_faqs(self) -> list[FaqSpec]:
        return await self._registry.list_faqs()

    async def list_track_events(self) -> list[TrackEventSpec]:
        return await self._registry.list_track_events()

    async def list_badge_rules(self) -> list[BadgeRuleSpec]:
        """成就解锁规则：读侧直通动态资源。"""
        return await self._registry.list_badge_rules()

    async def list_task_progress(self) -> list[TaskProgressSpec]:
        """AI 任务进度文案。"""
        return await self._registry.list_task_progress()

    async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
        """学信网字段清单（写哪些、叫什么、什么顺序）。"""
        return await self._registry.list_chsi_fields()

    async def get_prompt(self, code: str) -> Optional[PromptSpec]:
        """提示词 / 用户可见文案模板：读侧直通，业务层不做二次解释。"""
        return await self._registry.get_prompt(code)

    async def list_routing_rules(
        self, kind: Optional[str] = None
    ) -> list[RoutingRuleSpec]:
        """编排判定规则。排序与启用过滤由数据层负责，业务层不再排一遍。"""
        return await self._registry.list_routing_rules(kind)

    async def feature_flags(self) -> dict[str, bool]:
        return await self._feature_flags.all()


__all__ = ["DefaultRegistryService"]
