"""启动前把 AI 配置从库里读回来。

为什么必须发生在 `build_container` **之前**
-----------------------------------------
这里踩过一个死结：网关构造时要求密钥非空（空密钥直接拒绝启动），
而密钥按新口径只存在库里。于是"先建容器再读库"永远走不通 ——
还没读到库就先把服务拒绝了。

顺序只能是：

    读 .env（拿数据库地址与首次种子）
      → 连库、必要时种子、把 llm 与 embedding 两个场景都解析出来
      → 写回 settings
      → 再 build_container（这时密钥、base_url、模型名都已经是真的）

这样装配层拿到的就是**最终值**，不需要"先装一个临时的、启动后再换掉" ——
那种做法会让编排层手里的引用指向旧配置，表现成"改了库没生效"。

**两个场景都要读**（2026-09-22 补）：此前只读了 `llm`，`embedding` 留着 .env 的种子值 ——
于是库里的豆包配置形同虚设：开关关着时 RAG 一直用本地哈希伪嵌入（检索结果等于随机），
开关一开反倒直接拒绝启动（"doubao-ark API key 不能为空"，而密钥明明在库里）。
两者的症状相反，根因是同一个：只读了一半。

没有 PostgreSQL 时整段跳过：纯内存模式本来就没有"库"可言。
"""

from __future__ import annotations

import logging

from zhiyin_boot.settings import Settings

logger = logging.getLogger(__name__)


async def hydrate_ai_config(settings: Settings) -> None:
    """用库里的 AI 配置覆盖 settings 里的种子值。"""
    if not settings.use_postgres:
        return

    from zhiyin_infrastructure.ai.router import AiModelRouter
    from zhiyin_infrastructure.postgres.ai_config import PostgresAiConfigRepository
    from zhiyin_infrastructure.postgres.database import PostgresDatabase

    # ⚠️ 这里**不能**用全局的 `get_database()`。
    #
    # 本函数跑在 `asyncio.run(...)` 的临时事件循环里，而 `get_database()` 会
    # 缓存一个绑定在当前循环上的连接池；等到 uvicorn 用它自己的循环跑起来，
    # 池里的连接还挂在那个已经关掉的循环上 —— 症状是服务能启动、但每个查询都报
    # `Event loop is closed`。所以这里用一次性连接，读完就关，不碰全局池。
    database = PostgresDatabase(settings.postgres_dsn, min_size=1, max_size=1)
    repository = PostgresAiConfigRepository(
        database,
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        embedding_base_url=settings.embedding_base_url,
        embedding_model=settings.embedding_model,
        llm_api_key=settings.llm_api_key,
        embedding_api_key=settings.embedding_api_key,
    )
    try:
        # 表为空时把当前配置（来自 .env）种进去；已有值则原样不动。
        await repository.ensure_seeded()
        router = AiModelRouter(repository)
        resolved = await router.resolve("llm")
        resolved_embedding = await router.resolve("embedding")
    except Exception:
        # 连不上库 / 表结构不对：交给后面的装配与健康检查去报，
        # 这里只是"没读到"，不是一个需要吞掉或改写的错误。
        logger.exception("读取库里的 AI 配置失败，沿用 .env 里的种子值")
        return
    finally:
        await database.aclose()

    if resolved is None:
        # 典型情形：库里还没种、env 里也没密钥。
        # 不在这里抛错 —— 装配层会在构造真模型网关时给出更准确的报错。
        logger.warning("库里没有可用的 llm 路由，沿用 .env 里的种子值")
    else:
        changed = (
            resolved.api_key != settings.llm_api_key
            or resolved.base_url != settings.llm_base_url
            or resolved.model_code != settings.llm_model
        )
        settings.llm_api_key = resolved.api_key
        settings.llm_base_url = resolved.base_url
        settings.llm_model = resolved.model_code
        logger.info(
            "对话模型以数据库为准：%s / %s%s",
            resolved.provider_code,
            resolved.model_code,
            "（与 .env 种子值不同，已覆盖）" if changed else "",
        )

    if resolved_embedding is None:
        # 没配 embedding 路由时不算错：本地哈希嵌入仍能跑通形状（只是检索无意义），
        # 装配层会按开关决定用哪个实现，并在 /healthz 里如实标成 skeleton。
        logger.warning("库里没有可用的 embedding 路由，沿用 .env 里的种子值")
    else:
        changed = (
            resolved_embedding.api_key != settings.embedding_api_key
            or resolved_embedding.base_url != settings.embedding_base_url
            or resolved_embedding.model_code != settings.embedding_model
        )
        settings.embedding_api_key = resolved_embedding.api_key
        settings.embedding_base_url = resolved_embedding.base_url
        settings.embedding_model = resolved_embedding.model_code
        # provider 也要跟着库走：装配层用它挑实现（doubao / ollama），
        # 只覆盖地址与模型名而不覆盖它，就会出现"地址是本地 Ollama、
        # 实现却按豆包的形状挑"这种说不清的组合。
        settings.embedding_provider = resolved_embedding.provider_code
        logger.info(
            "嵌入模型以数据库为准：%s / %s%s",
            resolved_embedding.provider_code,
            resolved_embedding.model_code,
            "（与 .env 种子值不同，已覆盖）" if changed else "",
        )


__all__ = ["hydrate_ai_config"]
