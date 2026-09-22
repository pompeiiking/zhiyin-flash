"""装配口径的运行时配置：启动读一次，从 `infra_runtime_config` 取。

装的是两份**以前运行时直接读文件**的配置：

    assembly.ownership  能力位 → 负责人（给缺口标归属）
    assembly.gates      分级门禁（CI 用 --check --phase=N 卡口）

为什么不放在动态资源（`biz_registry_item`）：那批是**页面读侧**的东西
（菜单 / 文案 / 环节名），随请求被读；这两份是**启动装配口径**，
在服务起来之前就要定下来，而且 `--check` 也要能读到。

和 AI 配置同一条规矩：文件只是**首次种子**，写进库之后以库为准 ——
换一台机器只搬数据库。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from zhiyin_boot.settings import Settings

logger = logging.getLogger(__name__)

OWNERSHIP_KEY = "assembly.ownership"
GATES_KEY = "assembly.gates"

_SEEDS: tuple[tuple[str, str, str], ...] = (
    (OWNERSHIP_KEY, "ownership.json", "能力位归属：装配报告的缺口按它标注负责人"),
    (GATES_KEY, "assembly_gates.json", "分级门禁：CI 用 --check --phase=N 卡口"),
)

#: 读到的配置。空表示"还没装载"，由 report 层退回读文件。
_store: dict[str, Any] = {}


def get(key: str) -> Optional[Any]:
    return _store.get(key)


async def hydrate_runtime_config(settings: Settings, *, resync: bool = False) -> None:
    """连库、必要时用 JSON 种子补齐、**对账**、读进内存。

    `resync=True` 时以文件为准覆盖库里的值（`--resync-registry`）。
    默认只对账不改：库里那份可能是运维改过的，但"文件改了却不生效"必须留痕 ——
    门禁定义就是这么漂移的：文件里已删掉的能力位 `loop`，库里还留着，
    于是 `--check --phase=2` 在任何导过一次的库上永久报"门禁引用了未登记的能力位"。

    用**一次性连接**（不用全局连接池）：本函数跑在 `asyncio.run` 的临时事件循环里，
    全局池会绑在那个循环上，uvicorn 起来后每个查询都报 `Event loop is closed`。
    """
    if not settings.use_postgres:
        return
    from zhiyin_infrastructure.postgres.database import PostgresDatabase
    from zhiyin_infrastructure.postgres.runtime_config import (
        PostgresRuntimeConfigRepository,
    )

    database = PostgresDatabase(settings.postgres_dsn, min_size=1, max_size=1)
    try:
        repository = PostgresRuntimeConfigRepository(database)
        seeds = [
            (key, _read_seed(settings.local_registry_dir, filename), desc)
            for key, filename, desc in _SEEDS
        ]
        if resync:
            for key, value, desc in seeds:
                await repository.put(key, value, description=desc)
            logger.warning("装配口径已按 data/registry 强制重导（--resync-registry）")
        await repository.ensure_seeded(seeds)
        for key, seed_value, _desc in seeds:
            value = await repository.get(key)
            if value is None:
                continue
            _store[key] = value
            if not resync and _content_of(value) != _content_of(seed_value):
                logger.warning(
                    "装配口径 %s 与 data/registry 里的种子不一致（当前以库为准）。"
                    "确认要以文件为准时执行：python -m zhiyin_boot --resync-registry",
                    key,
                )
        logger.info(
            "装配口径已从数据库装载：%s",
            "、".join(sorted(_store)) or "（无）",
        )
    except Exception:
        # 读不到就退回读文件（report 层有兜底），不阻断启动：
        # 装配报告是给人看的，不该因为它打不开服务。
        logger.exception("读取装配口径失败，将退回读种子文件")
    finally:
        await database.aclose()


def _content_of(value: Any) -> Any:
    """去掉纯说明字段后的可比内容。

    `_note` 每次改文档都会变，把它算进差异会让告警天天响 —— 那种噪声会让人
    很快学会忽略这条日志，而它本来要报的是"真配置没生效"。
    """
    if isinstance(value, dict):
        return {key: _content_of(item) for key, item in value.items() if key != "_note"}
    if isinstance(value, list):
        return [_content_of(item) for item in value]
    return value


def _read_seed(registry_dir: str, filename: str) -> Any:
    path = Path(registry_dir) / filename
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


__all__ = ["GATES_KEY", "OWNERSHIP_KEY", "get", "hydrate_runtime_config"]
