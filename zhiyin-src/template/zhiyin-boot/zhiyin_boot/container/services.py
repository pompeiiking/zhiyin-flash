"""编排原语、业务服务与 Worker 的装配表。

装配顺序：

    1. build_gateways        基础设施层：外部能力
    2. build_repositories    数据访问
    3. build_orchestration   编排层：把 Gateway 包装成业务层面向的语义原语
    4. build_services        业务层：服务实现（依赖编排层与 Repository）
    5. build_workers         业务层：异步执行者（依赖服务与 Port）

未实现的业务服务保持 None，由装配报告标为 NOT_WIRED —— 这样 `/healthz` 会显式
暴露缺口，不会出现"看起来装好了其实没实现"的假装配。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from zhiyin_boot.container import Container

logger = logging.getLogger(__name__)


def build_orchestration(container: "Container") -> None:
    """构造编排层语义原语。

    这一步是「编排层不再有第二套契约」的落点：编排层的 EventBus / Scheduler /
    Notifier 都是包装 SDK Gateway 的实现，业务层只面向编排层编程。

    取数（DataSources）同理：编排层提供"按来源 + 查询词 + 上下文取数"这一个通用
    操作，业务层任何逻辑要外部数据都走它，不直接认识任何数据源适配器。
    """
    from zhiyin_orchestration import (
        GatewayDataSource,
        GatewayEventBus,
        GatewayNotifier,
        GatewayScheduler,
        MemoryStateStore,
        SequentialWorkflowEngine,
    )

    container.data_sources = GatewayDataSource(container.external_data)
    container.event_bus_primitive = GatewayEventBus(container.event_bus)
    container.scheduler_primitive = GatewayScheduler(
        container.scheduler, container.event_bus_primitive
    )
    container.notifier_primitive = GatewayNotifier(container.notifier)
    container.state_store = MemoryStateStore()
    # 判据只看"用不用真模型"，**不看 env 里有没有密钥** ——
    # 密钥可能存在库里（`infra_ai_provider.config.api_key`，启动时由
    # `bootstrap_ai_config` 填进来）。这里再拦一道 `and llm_api_key`，
    # 换一台只搬了库的机器就会因为 env 里没写密钥而整个退回本地模拟模型：
    # 表面能跑，实际没接模型 —— 那正是"配置入库"最容易假掉的地方。
    if container.settings.use_remote_llm:
        # AI 面向切面（设计文档第六章 6.5）：
        #   基础设施层 = agno 框架维护（模型客户端构建 / 角色映射 / 密钥配置）
        #             + 工具与 MCP 的注册表；
        #   编排层     = 用注入的模型对象组装智能体与工作流；
        #   业务层     = 环节判定 / 组队 / 交接 / AI 任务等业务规则。
        # 依赖守卫禁止编排层 import 基础设施层，因此模型对象在此注入。
        from zhiyin_infrastructure.ai.agno_runtime import AgnoModelRuntime
        from zhiyin_infrastructure.ai.tools import (
            ToolRegistry,
            build_tool_catalog,
        )
        from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine

        runtime = AgnoModelRuntime(
            api_key=container.settings.llm_api_key,
            base_url=container.settings.llm_base_url,
            model=container.settings.llm_model,
        )
        container.extra["agno_runtime"] = runtime
        registry_tools = ToolRegistry()
        container.extra["tool_registry"] = registry_tools
        # 工具目录：把已装配的真实能力包成智能体能调的函数。引擎只拿到
        # 「名字 → 可调用对象」，它不认识实现（依赖守卫不许编排层 import 基础设施）。
        #
        # 读画像 / 读行为用**惰性取服务**：这两个服务在 build_services 里才构造，
        # 而引擎在 build_orchestration 就装配好了。闭包在调用时才读 container，
        # 既避免为了顺序把两段装配揉在一起，也不会拿到"构造时的 None"。
        catalog = build_tool_catalog(
            search=container.search,
            external_data=container.data_sources,
            # 配了搜索密钥才有这条工具；没配就是个 None，工具目录里也就没有它 ——
            # 模型不会以为自己能联网，界面上也不会出现没发生的"正在搜索"。
            web_search=container.web_search,
            profile_reader=_lazy_profile_reader(container),
            behavior_reader=_lazy_behavior_reader(container),
            plan_reader=_lazy_plan_reader(container),
            modules=_product_modules(),
        )
        for spec in catalog.values():
            registry_tools.register(spec)
        container.agent_engine = AgnoAgentEngine(
            model_factory=runtime.create_model,
            registry=container.registry,
            tools={name: spec.handler for name, spec in catalog.items()},
        )
        container.workflow_engine = SequentialWorkflowEngine(container.agent_engine)
    else:
        # 没有真模型就没有智能体引擎 —— **不装 mock**。
        # 以前这里会装一个"本地 Mock 模型"撑住链路，代价是它产出的东西看起来
        # 和真模型一模一样，用户没有任何办法分辨。宁可明确地没有 AI：
        # 编排器与 AI 任务不装配，相关接口如实报缺口（/healthz 能看到）。
        logger.warning(
            "未启用真模型（ZHIYIN_USE_REMOTE_LLM!=1）：不装配智能体引擎，"
            "对话与 AI 任务将如实报为未装配。本项目不提供 mock 产出。"
        )


def _lazy_profile_reader(container: "Container"):
    """读画像的回调。惰性取服务：构造工具时业务服务还没装配好。"""

    async def read(user_id: str):
        service = container.profile_service
        if service is None:
            raise RuntimeError("画像服务未装配，profile.read 工具不可用")
        return await service.get(user_id)

    return read


def _lazy_behavior_reader(container: "Container"):
    """读行为的回调。同上。"""

    async def read(user_id: str, limit: int = 10):
        service = container.behavior_service
        if service is None:
            raise RuntimeError("行为服务未装配，behavior.recent 工具不可用")
        return await service.recent(user_id, limit=limit)

    return read


def _lazy_plan_reader(container: "Container"):
    """读计划与关键节点的回调（`plan.read` 工具用）。

    两份数据来自两个服务（行动计划在资产服务、关键节点在功能块服务），
    在这里合成一份：**工具层不该让模型自己拼两处读** —— 它只要"他手上的计划长什么样"。
    任一服务没装配时如实说没有，而不是抛错：缺能力不该让这一轮对话崩掉。
    """

    async def read(user_id: str) -> dict:
        plan = None
        nodes: list[Any] = []
        directions: list[Any] = []
        if container.asset_service is not None:
            plan = await container.asset_service.get_action_plan(user_id)
            # 已落库的几套方向方案也一并给（规划师与画图都用得上：
            # "他选的是哪一条、几条各差多少"是真实分值，不是模型算的）。
            directions = await container.asset_service.list_direction_plans(user_id)
        if container.function_service is not None:
            nodes = await container.function_service.list_calendar_nodes(user_id)
        return {"plan": plan, "nodes": nodes, "directions": directions}

    return read


def _product_modules() -> tuple[Any, ...]:
    """**产品自己做好的功能模块**在这里登记。

    一个模块 = 后端取数 + 前端一整套渲染，对外表现为"模型能调的一个工具"。
    要加一个模块，三件事（缺一件都会在测试或启动时暴露）：

      1. 写模块类，交出一个 `ToolModule(name=..., tools=[ToolSpec(...)])`
         （工具名带模块前缀，别与内置能力重名）；
      2. 在 `zhiyin_business.policies.renderers` 里注册它的可视件 kind
         （kind 名 + 校验函数）—— 服务端只认注册过的 kind，这是"防止假数据"的门；
      3. 前端按那个 kind 写组件。

    然后把它加进下面这个元组，并把工具名写进 `data/registry/agents.json`
    里能用的角色白名单 —— **模块不自己决定谁能用**，两件事分开各自可审。

    现在还没有外部模块：这一层是把"以后要接的那个套件"先立成明确的落点，
    免得它被塞进某个服务的构造函数里。
    """
    return ()


def build_services(container: "Container") -> None:
    """构造业务层服务。

    顺序：黑板四件套 → Identity + Registry（Facade 硬前置）→ Orchestrator →
    Workspace / Function（读侧聚合）→ Facade。实现落位见
    `zhiyin_business/services/__init__.py` 的落位表。
    """
    from zhiyin_business.policies import (
        DependencyImpactPolicy,
        DisclosureHandoffPolicy,
        KeywordIntentPolicy,
        RegistryLeadPolicy,
        RuleStagePolicy,
    )
    from zhiyin_business.services import (
        DefaultAssetService,
        DefaultAcademicService,
        DefaultBehaviorService,
        DefaultConversationMemoryService,
        DefaultFunctionService,
        DefaultIdentityService,
        DefaultOrchestrator,
        DefaultProfileService,
        DefaultAiTaskService,
        DefaultRegistryService,
        DefaultUserNoteService,
        DefaultWorkspaceService,
    )

    if container.profiles is not None and container.event_bus_primitive is not None:
        container.profile_service = DefaultProfileService(
            container.profiles, container.event_bus_primitive
        )
    if container.behaviors is not None and container.event_bus_primitive is not None:
        container.behavior_service = DefaultBehaviorService(
            container.behaviors, container.event_bus_primitive
        )
    if container.memories is not None:
        # 逐轮原文与累积摘要一起交给记忆服务：摘要给模型续接，原文给会话历史。
        # 文档抽取与对象存储也给它：**用户带上来的材料**归这里收
        # （正文抽出来存对象存储，对话里只留一句"我传了一份材料：xxx"）。
        container.memory_service = DefaultConversationMemoryService(
            container.memories,
            container.turns,
            container.documents,
            container.object_store,
        )
    if container.notes is not None:
        container.note_service = DefaultUserNoteService(container.notes)
    if container.academic_records is not None:
        container.academic_service = DefaultAcademicService(
            container.academic_records,
            container.academic,
            container.profile_service,
        )
    if container.assets is not None and container.event_bus_primitive is not None:
        container.asset_service = DefaultAssetService(
            container.assets,
            container.event_bus_primitive,
            DependencyImpactPolicy(),
        )
    if container.registry is not None and container.feature_flags is not None:
        container.registry_service = DefaultRegistryService(
            container.registry, container.feature_flags
        )
    if container.cache is not None:
        # 读缓存服务：策略来自动态资源（启动装载的那份快照），实现来自 CacheGateway。
        # 注意顺序 —— 它要在 `load_snapshot` 之后才有策略可用，但**即使没有策略也能建**：
        # 那时它退化成"落日 TTL / 不缓存"，而不是让整个装配少一个部件。
        from zhiyin_business.services.read_cache import DefaultReadCacheService

        container.read_cache = DefaultReadCacheService(container.cache)
    if container.auth is not None and container.users is not None:
        container.identity_service = DefaultIdentityService(
            container.auth, container.users
        )

    # 功能块服务要在编排器**之前**建：④ 行动产出的关键节点由它写进日历
    # （规划师写入、教练读取），顺序反了编排器就拿不到它。
    if all(
        item is not None
        for item in (
            container.asset_service,
            container.behavior_service,
            container.object_store,
            container.calendar,
            container.track_events,
            container.notifications,
        )
    ):
        container.function_service = DefaultFunctionService(
            assets=container.asset_service,
            behaviors=container.behavior_service,
            object_store=container.object_store,
            calendar=container.calendar,
            track_events=container.track_events,
            notifications=container.notifications,
            # 成就解锁规则来自动态资源（`badge_rules.json`）：改它不发版。
            registry=container.registry_service,
            # 「外部情报」这条链路：读画像决定查什么 → 学职网取公开事实 → 推一条通知。
            profiles=container.profile_service,
            data_sources=container.data_sources,
            notifier=container.notifier,
            # 通用网络检索也是情报的一个来源：配了搜索服务，"信息源很广"
            # 才真的落到实现上（学职平台 + 公开网页）。
            web_search=container.web_search,
        )

    dependencies = (
        container.profile_service,
        container.behavior_service,
        container.memory_service,
        container.asset_service,
        container.registry_service,
    )
    if container.agent_engine is not None and all(
        item is not None for item in dependencies
    ):
        container.orchestrator = DefaultOrchestrator(
            profiles=container.profile_service,
            behaviors=container.behavior_service,
            memories=container.memory_service,
            assets=container.asset_service,
            # 词表与映射都来自动态资源，所以这两个策略需要读侧服务 ——
            # 写在代码里的关键词表等于把"用户怎么说算同一件事"冻在发版节奏上。
            intent_policy=KeywordIntentPolicy(container.registry_service),
            stage_policy=RuleStagePolicy(container.registry_service),
            lead_policy=RegistryLeadPolicy(container.registry_service),
            handoff_policy=DisclosureHandoffPolicy(),
            agent_engine=container.agent_engine,
            sessions=container.sessions,
            registry=container.registry_service,
            event_bus=container.event_bus_primitive,
            read_cache=container.read_cache,
            functions=container.function_service,
            data_sources=container.data_sources,
        )

    # ---- 读侧聚合：工作台 + 功能块 ----
    read_side = (
        container.profile_service,
        container.asset_service,
        container.memory_service,
        container.behavior_service,
    )
    if all(item is not None for item in read_side):
        container.workspace_service = DefaultWorkspaceService(
            profiles=container.profile_service,
            assets=container.asset_service,
            memories=container.memory_service,
            behaviors=container.behavior_service,
            notes=container.note_service,
            academic_records=container.academic_service,
            sessions=container.sessions,
            # 气泡编排策略在动态资源里，工作台是读侧 —— 把读侧服务传进去，
            # 而不是让工作台自己去猜顺序
            registry=container.registry,
        )
        container.ai_task_service = DefaultAiTaskService(
            profiles=container.profile_service,
            behaviors=container.behavior_service,
            assets=container.asset_service,
            notes=container.note_service,
            academic_records=container.academic_service,
            # 关键节点日历：按天生成建议时要读"那天有什么到期"
            functions=container.function_service,
            chsi=container.chsi,
            registry=container.registry_service,
            # 生成类 AI 任务的唯一内容来源。没有引擎时那些任务直接报错，
            # 不退回拼一段看起来像样的文案 —— 那种做法已经删干净了。
            engine=container.agent_engine,
            results=container.ai_task_results,
        )

    # ---- BFF 门面（前端联调的唯一入口）----
    facade_deps = (
        container.identity_service,
        container.registry_service,
        container.orchestrator,
        container.workspace_service,
        container.asset_service,
        container.function_service,
        container.ai_task_service,
        container.note_service,
        container.academic_service,
    )
    if all(item is not None for item in facade_deps):
        from zhiyin_api.facade.application import DefaultApplicationFacade

        container.facade = DefaultApplicationFacade(
            identity=container.identity_service,
            registry=container.registry_service,
            orchestrator=container.orchestrator,
            workspace=container.workspace_service,
            assets=container.asset_service,
            function=container.function_service,
            ai_tasks=container.ai_task_service,
            notes=container.note_service,
            academic=container.academic_service,
            behaviors=container.behavior_service,
            memories=container.memory_service,
            # 读缓存必须接到**读侧**：只把它交给编排器（写侧失效）的话，
            # 没有任何一次读会经过它 —— `/healthz` 的 hits/misses 会永远是 0，
            # 而"缓存装上了"看起来又是真的。装配一处漏接就是这个症状。
            read_cache=container.read_cache,
        )


def build_workers(container: "Container") -> None:
    """构造业务层 Worker。

    `impact`（影响面传播）与 `active_event`（停滞干预）注册进装配表后，
    由 `wire_application` 的 lifespan 统一启停，也可用
    `python -m zhiyin_boot worker <name>` 独立运行，两者复用同一个 container。
    """
    container.workers = []
    if container.rag is not None and container.settings.use_postgres:
        from zhiyin_infrastructure.rag import JsonKnowledgeDocumentSource
        from zhiyin_infrastructure.postgres.database import get_database
        from zhiyin_infrastructure.postgres.vector_sync_state import (
            PostgresVectorSyncState,
        )
        from zhiyin_infrastructure.workers import VectorSyncWorker

        container.workers.append(
            VectorSyncWorker(
                JsonKnowledgeDocumentSource(container.settings.local_knowledge_dir),
                container.rag,
                PostgresVectorSyncState(get_database(container.settings.postgres_dsn)),
            )
        )

    if container.asset_service is not None and container.event_bus_primitive is not None:
        from zhiyin_business.workers import ImpactPropagationWorker

        container.workers.append(
            ImpactPropagationWorker(
                container.asset_service,
                container.event_bus_primitive,
                # 画像变了，AI 任务的产出也要作废：不然缓存里那份基于旧画像的解读
                # 会被当成最新的用（而缓存现在跨重启，不作废就会一直错下去）。
                ai_tasks=container.ai_task_service,
            )
        )

    if container.behavior_service is not None and container.registry is not None:
        from zhiyin_business.policies.intervention_rules import (
            ThresholdInterventionPolicy,
        )
        from zhiyin_business.workers import ActiveEventWorker

        container.workers.append(
            ActiveEventWorker(
                behaviors=container.behavior_service,
                policy_factory=lambda value: ThresholdInterventionPolicy(
                    stall_threshold_days=int(value.get("stall_threshold_days", 3)),
                    cooldown_hours=int(value.get("cooldown_hours", 48)),
                    max_notifications_per_window=int(
                        value.get("max_notifications_per_window", 2)
                    ),
                    window_days=int(value.get("window_days", 7)),
                ),
                registry=container.registry,
                notifications=container.notifications,
                scheduler=container.scheduler_primitive,
                notifier=container.notifier_primitive,
                user_provider=lambda: list(
                    getattr(container.users, "_users", {}).keys()
                ),
            )
        )


__all__ = ["build_orchestration", "build_services", "build_workers"]
