"""Gateway 装配表：本地能力 + Redis 缓存 + PostgreSQL/pgvector 向量存储 + 外部数据源。

骨架状态由实现类自己声明（`IMPLEMENTATION_STATUS`），不再靠模块路径猜：
- `wired`    ：真实可用的实现；
- `skeleton` ：形状对、能力占位（如哈希伪嵌入），必须让使用者看见。

外部数据源（`external_data`）只在这里换实现：换数据源 = 换一个 Gateway，
编排层的取数原语与业务调用方都不动。
"""

from __future__ import annotations

from typing import Any

from zhiyin_boot.settings import Settings


def build_gateways(
    settings: Settings, *, ai_router: Any = None, notifications: Any = None
) -> dict[str, Any]:
    """按配置装配 Gateway。默认全走 local（第一期可独立跑通）。"""
    from zhiyin_infrastructure.local.auth import DefaultPassAuth
    from zhiyin_infrastructure.local.cache import InMemoryCache
    from zhiyin_infrastructure.local.embedding import LocalHashEmbedder
    from zhiyin_infrastructure.local.knowledge import (
        LocalKeywordSearch,
        LocalKnowledgeRepo,
    )
    from zhiyin_infrastructure.local.messaging import (
        InMemoryEventBus,
        LocalNotify,
        LocalScheduler,
    )
    from zhiyin_infrastructure.local.object_store import LocalFileStore
    from zhiyin_infrastructure.local.security import NoopRateLimit, NoopSecurity
    from zhiyin_infrastructure.local.vector_store import LocalVectorStore

    event_bus = InMemoryEventBus()
    notifier = LocalNotify(notifications)
    if settings.use_postgres:
        from zhiyin_infrastructure.postgres.database import get_database
        from zhiyin_infrastructure.postgres.messaging import (
            PostgresEventBus,
            PostgresNotifier,
        )

        database = get_database(settings.postgres_dsn)
        event_bus = PostgresEventBus(database)
        notifier = PostgresNotifier(database)
        from zhiyin_infrastructure.postgres.scheduler import PostgresScheduler

        scheduler = PostgresScheduler(database, event_bus)
    else:
        scheduler = LocalScheduler(event_bus)
    # 默认**没有**模型：本项目不提供 mock 产出。只有配了真模型（或在库里
    # 读到可用路由）时，下面才会把它换成真网关；否则 `container.llm` 是 None，
    # 装配报告与最低可用校验都会如实报出来。
    llm: Any = None
    embedding = LocalHashEmbedder()
    if settings.use_remote_llm:
        from zhiyin_infrastructure.ai.deepseek import DeepSeekLLMGateway

        if not settings.llm_api_key:
            # 密钥现在可能存在库里，所以这里不能只说"key 为空"就完事 ——
            # 报错要告诉人**去哪儿找**，否则换一台只搬了库的机器，
            # 看到的就是一句没头没尾的"API key 不能为空"。
            raise RuntimeError(
                "已开启真模型（ZHIYIN_USE_REMOTE_LLM=1）但拿不到 LLM 密钥。\n"
                "  · 正常启动（python -m zhiyin_boot）会先从数据库读配置，"
                "密钥存在 infra_ai_provider.config.api_key；\n"
                "  · 若库里也没有，请在 .env 里补一次 ZHIYIN_LLM_API_KEY"
                "（首次开机种子，之后以库为准）；\n"
                "  · 直接调 build_container() 的脚本不会自动读库，"
                "需要先 await hydrate_ai_config(settings)。"
            )
        llm = DeepSeekLLMGateway(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    if settings.use_remote_embedding:
        embedding = _build_embedding_gateway(settings)

    if settings.use_postgres:
        from zhiyin_infrastructure.ai.router import AiModelRouter
        from zhiyin_infrastructure.ai.routed import (
            RoutedEmbeddingGateway,
            RoutedLLMGateway,
        )

        # 路由器由装配层构造并注入（见 `build_container`）：它同时要被
        # 启动流程用来把**库里的 AI 配置**读出来覆盖种子值，
        # 在这里再造一个，两边就会各持一份状态。
        router = ai_router or AiModelRouter(_build_ai_config_repository(settings))
        if settings.use_remote_llm:
            llm = RoutedLLMGateway(router, llm)
        if settings.use_remote_embedding:
            embedding = RoutedEmbeddingGateway(router, embedding)

    cache = InMemoryCache()
    if settings.use_redis:
        from zhiyin_infrastructure.redis.cache import RedisCacheGateway
        from zhiyin_infrastructure.redis.rate_limit import RedisRateLimit

        cache = RedisCacheGateway(
            settings.redis_url, key_prefix=settings.redis_key_prefix
        )
        # 限流必须共享状态：进程内计数在多实例下等于把额度乘以实例数。
        # 只有接上 Redis 才有真正的限流，所以它是跟着 Redis 一起装的。
        rate_limit: Any = RedisRateLimit(
            settings.redis_url, key_prefix=settings.redis_key_prefix
        )
    else:
        rate_limit = NoopRateLimit()

    # 安全：配了密钥才装真实现（AES-GCM + 脱敏 + 结构化审计）。
    # 没配就是 Noop —— 装配报告会如实说它是骨架，而不是"已装配"。
    security: Any = NoopSecurity()
    if settings.security_key:
        from zhiyin_infrastructure.security.crypto import CryptoSecurity

        security = CryptoSecurity(settings.security_key)

    # 通用网络搜索：没有密钥就不装（`container.web_search` 是 None，
    # 工具目录里也就没有 web.search）—— 不假装能联网。
    web_search: Any = None
    if settings.search_api_key:
        from zhiyin_infrastructure.search.web import BraveWebSearch

        web_search = BraveWebSearch(
            api_key=settings.search_api_key, endpoint=settings.search_endpoint
        )

    vector = LocalVectorStore()
    if settings.use_postgres:
        from zhiyin_infrastructure.postgres.vector import PostgresVectorGateway

        vector = PostgresVectorGateway(settings.postgres_dsn)

    knowledge = LocalKnowledgeRepo(settings.local_knowledge_dir)
    search = LocalKeywordSearch(settings.local_knowledge_dir)
    if settings.use_postgres:
        from zhiyin_infrastructure.rag.knowledge import VectorKnowledgeGateway
        from zhiyin_infrastructure.rag.search import VectorSearchGateway

        knowledge = VectorKnowledgeGateway(embedding=embedding, vectors=vector)
        search = VectorSearchGateway(
            embedding=embedding,
            vectors=vector,
            data_dir=settings.local_knowledge_dir,
        )

    auth = DefaultPassAuth()
    if settings.use_postgres:
        from zhiyin_infrastructure.auth.gateway import JwtAuthGateway
        from zhiyin_infrastructure.postgres.database import get_database

        auth = JwtAuthGateway(
            get_database(settings.postgres_dsn),
            cache=cache,
            secret=settings.auth_jwt_secret,
            ttl_s=settings.auth_token_ttl_s,
        )

    from zhiyin_infrastructure.xuezhi import XueZhiClient, XueZhiDataSourceGateway

    external_data: Any = XueZhiDataSourceGateway(
        XueZhiClient(
            base_url=settings.xuezhi_base_url,
            request_interval_s=settings.xuezhi_request_interval_s,
        )
    )

    # 学信网在线验证报告核验：与学职平台不同，它取的是**用户本人的**学籍/学历，
    # 所以走"用户给码 → 我们核验"的单次请求模式，不做任何账号级拉取。
    from zhiyin_infrastructure.chsi import ChsiReportClient, OnlineVerificationGateway

    chsi: Any = OnlineVerificationGateway(
        ChsiReportClient(
            base_url=settings.chsi_base_url,
            request_interval_s=settings.chsi_request_interval_s,
        )
    )

    # 课表与成绩单：**学生自己导入**，我们不替他登录任何学校系统。
    # 所以这个能力位是一条解析器，不是一条取数通道 —— 没有网络、没有凭据。
    from zhiyin_infrastructure.academic import ManualAcademicImporter

    academic: Any = ManualAcademicImporter()

    # 文档正文抽取：用户带上来的文件 → 文本（编码识别 + 二进制格式拒绝）。
    # 它不联网，也不是"替用户去取数据"——就是把字节读成字。
    from zhiyin_infrastructure.textfile import LocalTextExtractor

    documents: Any = LocalTextExtractor()

    gateways: dict[str, Any] = {
        "llm": llm,
        "embedding": embedding,
        "knowledge": knowledge,
        "search": search,
        "vector": vector,
        "cache": cache,
        "object_store": LocalFileStore(settings.local_object_dir),
        "documents": documents,
        "event_bus": event_bus,
        # 调度器必须能投递事件，否则主动事件（停滞检测）永远不触发。显式注入。
        "scheduler": scheduler,
        "notifier": notifier,
        "auth": auth,
        "security": security,
        "rate_limit": rate_limit,
        "web_search": web_search,
        "external_data": external_data,
        "chsi": chsi,
        "academic": academic,
    }

    return gateways


def _build_embedding_gateway(settings: Settings) -> Any:
    """按 provider 选嵌入实现。

    两家都是 OpenAI 兼容协议，差异只有默认地址与署名，但**署名不是装饰**：
    排查"检索结果不对"时，第一眼看的就是 provider —— 是本地模型算的，还是云端算的，
    决定了要查的是本机 Ollama 还是对方的配额与接入点。

    `provider` 从库里的路由来（`ai_bootstrap` 会把它写回 settings），
    所以换实现只改一行数据，不改代码。
    """
    provider = (settings.embedding_provider or "doubao").strip().lower()
    if provider == "ollama":
        from zhiyin_infrastructure.ai.ollama import OllamaEmbeddingGateway

        return OllamaEmbeddingGateway(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
        )
    from zhiyin_infrastructure.ai.doubao import DoubaoEmbeddingGateway

    return DoubaoEmbeddingGateway(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
    )


def _build_ai_config_repository(settings: Settings) -> Any:
    """构造 AI 配置仓储 —— AI 配置的唯一权威来源。

    启动种子值全部来自 `settings`：第一次开机时它们被写进
    `infra_ai_provider` / `infra_ai_model` / `infra_ai_route`，
    之后就以表为准（见 `container.bootstrap_ai_config`）。
    """
    from zhiyin_infrastructure.postgres.ai_config import PostgresAiConfigRepository
    from zhiyin_infrastructure.postgres.database import get_database

    return PostgresAiConfigRepository(
        get_database(settings.postgres_dsn),
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
        llm_api_key=settings.llm_api_key,
        embedding_api_key=settings.embedding_api_key,
    )


__all__ = ["build_gateways"]
