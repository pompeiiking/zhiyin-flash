"""启动时把动态资源导进库，并核对必须有的内容。

为什么不能只在"第一次读"时懒加载
--------------------------------
种子原来挂在读接口上：谁读谁触发导入。后果是——新装、或新加一类动态资源之后，
**表建出来了但是空的**，直到有人真的读它；而"有人读"发生在用户发出第一条消息的
那一刻。在那之前，任何直接查库的人看到的都是一张空表，而且分不清它是"还没导"
还是"本来就没有配置"。

这个症状已经真实发生过一次：`ai_prompt_template` 与 `ai_routing_rule` 两张表
建出来了、0 行，查库的人以为表根本没建。

所以启动时显式导一次，并且**核对必须有的内容**：缺了就报错，不做"空着也能跑"的
兜底。缺一条提示词的表现是"这个环节突然不说人话了"——不报错、不留痕，
等有人察觉时已经不知道该查哪一天。

种子只是**首次导入**：某一类库里已经有内容（哪怕只有一行），就不再覆盖，
之后以库为准。这样运营在库里改过的口径不会被启动时的种子冲掉。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from zhiyin_boot.settings import Settings

logger = logging.getLogger(__name__)

REQUIRED_PROMPTS: tuple[str, ...] = (
    "core.system",
    "guide.closing",
    "router.clarify",
    "disclosure.lead_change",
    "disclosure.conclusion_change",
    "flow.proactive",
)
"""少任何一条，对应能力就是"能跑但不对"，所以启动即拦。

**这里只放真有调用方的那几条。** 意图 / 环节 / 主理三条判定曾经各有一条
`router.*` 提示词躺在这里接受门禁保护，而全仓没有一处代码调用它们 ——
门禁在为一份没人用的配置站岗，接手的人会以为"模型判定这条链路是活的"。
现在判定全部是规则（关键词映射 + 进度规则 + 注册表组队），三条提示词已删。
新增提示词时同时给出调用点，再把它加进来。
"""


class RegistryContentError(RuntimeError):
    """动态资源内容缺失或自相矛盾。启动阶段直接抛，不降级。"""


async def hydrate_registry_content(settings: Settings, *, resync: bool = False) -> None:
    """连库 → 按类别补种 → **对账** → 核对必需内容。

    `resync=True` 时以文件为准强制重导（运维动作：`python -m zhiyin_boot --resync-registry`）。
    默认只对账不改数据，因为"库里那份可能是运营改过的"是既有口径。

    用**一次性连接**（不用全局连接池）：本函数跑在 `asyncio.run` 的临时事件循环里，
    全局池会绑在那个循环上，uvicorn 起来后每个查询都报 `Event loop is closed`。
    """
    if not settings.use_postgres:
        # 纯本地模式直接读 JSON 文件，本来就没有"入库"这一步。
        return

    from zhiyin_infrastructure.postgres.database import PostgresDatabase
    from zhiyin_infrastructure.postgres.registry import PostgresRegistryRepository

    database = PostgresDatabase(settings.postgres_dsn, min_size=1, max_size=1)
    try:
        repository = PostgresRegistryRepository(database, settings.local_registry_dir)
        if resync:
            # 强制重导：`resync()` 是 upsert **加删除文件里已经没有的条目**。
            # 只 upsert 的话，"以文件为准"只兑现一半 —— 删掉的那条会永远留在库
            # 和迁移文件里，继续下发到前端。
            await repository.resync()
            logger.warning(
                "动态资源已按 data/registry/*.json 强制重导（--resync-registry）；"
                "**正在运行的实例仍持有旧的进程内快照** —— 重启它，"
                "或调用 POST /app/config/reload，新的文案 / 词表 / 规则才会生效"
            )
            # 功能开关不在 biz_registry_item 里（它在 infra_feature_flag，且首次导入是
            # "表空才种"），所以必须单独重导一次，否则删掉一条开关只对文件生效。
            from zhiyin_infrastructure.postgres.feature_flag import (
                PostgresFeatureFlagGateway,
            )

            removed = await PostgresFeatureFlagGateway(
                database, settings.local_registry_dir
            ).resync()
            if removed:
                logger.warning("功能开关重导：库里多出的 %s 已按文件删除", removed)
        await repository.ensure_seeded()
        drift = await detect_registry_drift(repository, settings.local_registry_dir)
        if drift:
            if resync:
                logger.info("对账完成：%s 处差异已按文件修正", len(drift))
            else:
                # 不静默：库优先是刻意设计，但"改好的文件进不了环境"必须留痕，
                # 否则下一次又是"代码是对的、跑起来是坏的"。
                for line in drift:
                    logger.warning("动态资源与 %s 不一致：%s", "data/registry", line)
                logger.warning(
                    "以上差异不会自动生效（以库为准）。确认要以文件为准时执行："
                    "python -m zhiyin_boot --resync-registry"
                )
        problems = await check_registry_content(repository)
        if problems:
            raise RegistryContentError(
                "动态资源内容不完整，拒绝启动：\n  - " + "\n  - ".join(problems)
            )
        logger.info("动态资源已入库并核对通过")
    finally:
        await database.aclose()


async def check_registry_content(repository) -> list[str]:
    """核对必需内容，返回问题清单（空表示通过）。

    只查**缺了会静默变坏**的那几类：提示词、编排规则、环节展示口径。
    缺一个智能体的角色提示词，用户看到的是"这个环节突然不太会说话"；
    缺一条环节的交接原因，换主理时用户只看到半句话。
    """
    problems: list[str] = []

    prompts = await repository.list_prompts()
    codes = {item.code for item in prompts}
    missing = sorted(code for code in REQUIRED_PROMPTS if code not in codes)
    if missing:
        problems.append(f"缺少编排必需的提示词：{missing}")

    agents = await repository.list_agents()
    with_role = {item.agent_id for item in prompts if item.layer == "role"}
    without = sorted(item.id for item in agents if item.id not in with_role)
    if without:
        problems.append(f"以下智能体没有角色提示词：{without}")

    stages = await repository.list_stages()
    missing_reasons = sorted(
        f"disclosure.reason.{stage.id}"
        for stage in stages
        if f"disclosure.reason.{stage.id}" not in codes
    )
    if missing_reasons:
        problems.append(f"缺少按环节的交接原因：{missing_reasons}")

    rules = await repository.list_routing_rules()
    intents = {item.intent for item in rules if item.kind == "intent"}
    mapped = {item.intent for item in rules if item.kind == "stage"}
    unmapped = sorted(intents - mapped)
    if unmapped:
        problems.append(f"以下意图没有映射到环节，命中它的用户会停在原地：{unmapped}")
    if not intents:
        problems.append("编排规则为空：关键词到意图的映射一条都没有")

    return problems


async def detect_registry_drift(repository: Any, registry_dir: str) -> list[str]:
    """库里的动态资源 vs `data/registry/*.json`：返回人类可读的差异清单。

    为什么必须有这一步
    ------------------
    「以库为准 + 种子只导一次」是刻意的设计（运营在库里改过的口径不该被启动冲掉），
    但它有一个没有出口的后果：**仓库里改好的数据永远进不了已经导过一次的环境**。
    本次审计实测到的三处漂移各自对应一个线上级故障：

    - `agents.tools` 5/5 条还是中文旧名 → 智能体引擎取不到工具 → **对话 100% 500**；
    - 提示词库 19 条 / 文件 26 条（缺 7 条 `task.*`）→ 8 个 AI 任务全部无提示词；
    - 库里门禁仍引用已删除的能力位 `loop` → **M2 门禁永久不通过**。

    而仓库里所有守卫读的都是文件，所以一条都不会红。

    这里只**报告**不改数据（`resync=True` 时才由调用方强制重导）：对账的职责是
    让「改了文件但没生效」这件事在启动日志里出现，而不是替人做决定。
    """
    snapshot = await repository.raw_snapshot()
    diff: list[str] = []
    fingerprints = repository.fingerprint

    for kind, filename in repository.seed_files().items():
        path = Path(registry_dir) / filename
        if not path.is_file():
            diff.append(f"{kind}：文件缺失 {path}")
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        file_map = {_item_key(item): fingerprints(item) for item in items}
        db_map = snapshot.get(kind, {})

        missing = sorted(set(file_map) - set(db_map))
        if missing:
            diff.append(f"{kind}：文件有、库里没有 {missing}")
        stale = sorted(key for key in set(file_map) & set(db_map) if file_map[key] != db_map[key])
        if stale:
            diff.append(f"{kind}：库中内容与文件不一致 {stale}")

    return diff


def _item_key(item: dict[str, Any]) -> str:
    """动态资源条目的稳定键。三套键名（code / id / key）是既成事实，这里统一认掉。"""
    for name in ("code", "id", "key"):
        value = item.get(name)
        if value:
            return str(value)
    return json.dumps(item, ensure_ascii=False, sort_keys=True)[:64]


__all__ = [
    "REQUIRED_PROMPTS",
    "RegistryContentError",
    "check_registry_content",
    "detect_registry_drift",
    "hydrate_registry_content",
]
