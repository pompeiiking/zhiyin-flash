"""依赖装配容器。

本包是**唯一**允许 import 全部层的位置（见 `zhiyin_boot/__init__.py`）。
按能力域拆分，避免单文件同时承担"装配表 + 报告 + 门禁 + 启停"：

    ports.py          有哪些能力位（装配报告的坐标系）
    gateways.py       外部能力用哪套自有本地实现
    repositories.py   数据访问与动态资源
    services.py       编排原语 / 业务服务 / Worker
    __init__.py       Container 数据结构、装配入口、ASGI 装配
    ../report.py      装配报告与分级门禁（不产生副作用）

替换一个能力只改本包，业务代码一行不动。
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from zhiyin_boot.container.gateways import build_gateways
from zhiyin_boot.container.ports import MINIMUM_VIABLE
from zhiyin_boot.container.repositories import (
    build_feature_flags,
    build_repositories,
)
from zhiyin_boot.container.services import (
    build_orchestration,
    build_services,
    build_workers,
)
from zhiyin_boot.settings import Settings
from zhiyin_boot.workers import run_until_cancelled

logger = logging.getLogger(__name__)

@dataclass
class Container:
    """运行时依赖容器。

    Gateways     —— 外部能力（SDK 定义契约，基础设施层实现）
    Repositories —— 数据访问
    Primitives   —— 编排层语义原语（包装上面的 Gateway）
    Services     —— 业务层服务
    Workers      —— 业务层异步执行者（复用本容器）
    Facade       —— BFF 门面
    """

    settings: Settings

    # ---- Gateways ----
    llm: Any
    embedding: Any
    knowledge: Any
    search: Any
    vector: Any
    cache: Any
    object_store: Any
    event_bus: Any
    scheduler: Any
    notifier: Any
    auth: Any
    security: Any
    rate_limit: Any
    external_data: Any
    chsi: Any
    academic: Any = None
    # ---- Repositories ----
    profiles: Optional[Any] = None
    behaviors: Optional[Any] = None
    memories: Optional[Any] = None
    #: 读缓存（业务侧服务）：只放可重建的读模型，策略来自动态资源
    read_cache: Optional[Any] = None
    #: 逐轮对话原文（会话列表点进去看历史用）。与 memories（累积摘要）分开。
    turns: Optional[Any] = None
    assets: Optional[Any] = None
    sessions: Optional[Any] = None
    registry: Optional[Any] = None
    users: Optional[Any] = None
    notes: Optional[Any] = None
    academic_records: Optional[Any] = None
    # 曾经只活在 `DefaultFunctionService` 与 `AiTaskService` 内存里的四类数据：
    # 关键节点日历、跟踪时间线、通知读侧、AI 任务产出。
    calendar: Optional[Any] = None
    track_events: Optional[Any] = None
    notifications: Optional[Any] = None
    ai_task_results: Optional[Any] = None

    # ---- 动态资源 ----
    feature_flags: Any = None

    # ---- AI / RAG ----
    rag: Any = None

    # ---- 编排层语义原语（由 boot 绑定到上面的 gateway）----
    data_sources: Any = None
    event_bus_primitive: Any = None
    scheduler_primitive: Any = None
    notifier_primitive: Any = None
    state_store: Any = None
    agent_engine: Any = None
    workflow_engine: Any = None

    # ---- 业务层服务 ----
    orchestrator: Any = None
    profile_service: Any = None
    behavior_service: Any = None
    memory_service: Any = None
    note_service: Any = None
    academic_service: Any = None
    asset_service: Any = None
    workspace_service: Any = None
    function_service: Any = None
    identity_service: Any = None
    registry_service: Any = None
    ai_task_service: Any = None

    # ---- 业务层 Worker（复用本容器的 Port）----
    workers: list[Any] = field(default_factory=list)

    # ---- BFF 门面 ----
    facade: Any = None

    #: 通用网络搜索适配器。**没配搜索密钥时是 None** —— 它不是必需的网关，
    #: 所以不进 `GATEWAY_PORTS`（那会让"没配搜索"变成"装配不健康"）。
    #: 它只为工具目录服务：有它，主理手上就多一条 `web.search`。
    web_search: Any = None

    extra: dict[str, Any] = field(default_factory=dict)


def build_container(settings: Optional[Settings] = None) -> Container:
    """构造完整容器：Gateways → Repositories → 编排原语 → 服务 → Worker。"""
    settings = settings or Settings.from_env()

    # AI 配置的路由器在装配层构造一次，两份用途共用同一个仓储：
    #   1. 包住 LLM / Embedding 网关（按 scene 路由）；
    #   2. 启动时把库里的配置读出来，覆盖"启动种子值"。
    ai_config: Any = None
    ai_router: Any = None
    if settings.use_postgres:
        from zhiyin_boot.container.gateways import _build_ai_config_repository
        from zhiyin_infrastructure.ai.router import AiModelRouter

        ai_config = _build_ai_config_repository(settings)
        ai_router = AiModelRouter(ai_config)

    # 仓储先建：本地模式下通知的**写侧（LocalNotify）与读侧（NotificationRepository）
    # 必须是同一个存储**，否则又是"发出去了但读不到"。Postgres 模式下两者共用
    # `orc_notification` 表，天然一致；本地模式靠这里把同一个实例传下去。
    repository_values = build_repositories(settings)
    gateway_values = build_gateways(
        settings,
        ai_router=ai_router,
        notifications=repository_values.get("notifications"),
    )
    container = Container(
        settings=settings,
        feature_flags=build_feature_flags(settings),
        **gateway_values,
        **repository_values,
    )
    container.extra["ai_config"] = ai_config
    container.extra["ai_router"] = ai_router
    container.extra["closables"] = [
        value
        for value in [*gateway_values.values(), *repository_values.values()]
        if hasattr(value, "aclose") or hasattr(value, "close")
    ]
    if settings.use_postgres:
        from zhiyin_infrastructure.postgres.database import get_database

        container.extra["closables"].append(get_database(settings.postgres_dsn))
    build_orchestration(container)
    from zhiyin_infrastructure.rag import RagPipeline

    container.rag = RagPipeline(
        embedding=container.embedding,
        vectors=container.vector,
        llm=container.llm,
    )
    build_services(container)
    build_workers(container)

    return container


def assert_minimum_viable(container: Container) -> None:
    """启动前置校验：缺任何一个最低可用部件都直接失败，别让服务带病启动。"""
    missing = [name for name in MINIMUM_VIABLE if getattr(container, name, None) is None]
    if missing:
        raise RuntimeError(f"装配不完整，缺少必需部件：{missing}")


def wire_application(container: Optional[Container] = None) -> Any:
    """把业务服务与 Facade 接上，挂载路由，返回 ASGI 应用。

    顺序固定：
      1. 构造编排原语与服务（已在 build_container 内完成）；
      2. 校验最低可用装配；
      3. 上报装配状态（供 /healthz 与 --check 读取）；
      4. 若 Facade 已实现则装配，否则保持未装配（接口按 DEPENDENCY_UNAVAILABLE 降级）；
      5. 挂载路由，并在 lifespan 中启停调度轮询与 Worker。

    Worker 与调度都在 lifespan 内启动：同进程部署即可用，成长期把同一个 Worker
    用 `python -m zhiyin_boot worker <name>` 独立部署，代码不需要改。
    """
    from zhiyin_api.app import create_app
    from zhiyin_api.facade import configure_facade
    from zhiyin_api.runtime import configure_cache_probe, configure_runtime
    from zhiyin_boot.report import describe_assembly

    container = container or build_container()
    assert_minimum_viable(container)

    report = describe_assembly(container)
    configure_runtime(report)
    # 读缓存自述接进 `/healthz`：装了就报策略与命中率，没装就报空。
    configure_cache_probe(
        container.read_cache.stats if container.read_cache is not None else None
    )

    if container.facade is not None:
        configure_facade(container.facade)

    @contextlib.asynccontextmanager
    async def _lifespan(_: Any):
        stop = asyncio.Event()
        tasks: list[asyncio.Task[Any]] = []

        # 动态配置（环节口径 / 气泡编排 / 采集规则）**读一次**，之后只认快照。
        # 放在收请求之前：读到之前标题是空的，总比显示一个可能过期的旧名字好；
        # 改配置之后由 `POST /app/config/reload` 重新装载，不需要重启。
        if container.registry_service is not None:
            from zhiyin_business.services.dynamic_config import load_snapshot

            await load_snapshot(container.registry_service)

        scheduler = container.scheduler
        start_polling = getattr(scheduler, "start_polling", None)
        if callable(start_polling):
            start_polling()

        interval = container.settings.worker_interval_s
        for worker in container.workers:
            tasks.append(
                asyncio.create_task(run_until_cancelled(worker, interval, stop))
            )

        try:
            yield
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            stop_polling = getattr(scheduler, "stop_polling", None)
            if callable(stop_polling):
                await stop_polling()
            for closable in reversed(container.extra.get("closables", [])):
                close = getattr(closable, "aclose", None) or getattr(
                    closable, "close", None
                )
                if not callable(close):
                    continue
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("关闭资源失败：%s", type(closable).__name__)

    return create_app(
        title=f"{container.settings.app_name} API",
        lifespan=_lifespan,
        # 前缀只有一个来源：Settings.api_prefix（默认 /api/v1）。
        # 换版本改配置即可，路由声明与前端都不用动。
        api_prefix=container.settings.api_prefix,
    )


__all__ = [
    "Container",
    "assert_minimum_viable",
    "build_container",
    "wire_application",
]
