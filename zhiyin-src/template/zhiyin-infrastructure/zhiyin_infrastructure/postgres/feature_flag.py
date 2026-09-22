"""PostgreSQL 功能开关实现。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from zhiyin_data_sdk.gateways.feature_flag import FeatureFlagGateway
from zhiyin_infrastructure.postgres.database import PostgresDatabase


class PostgresFeatureFlagGateway(FeatureFlagGateway):
    """从 `infra_feature_flag` 读取功能开关；首次访问时从 JSON 种子导入。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase, registry_dir: str) -> None:
        self._db = database
        self._seed_path = Path(registry_dir) / "feature_flags.json"
        self._seeded = False
        self._lock = asyncio.Lock()

    async def all(self) -> dict[str, bool]:
        await self._ensure_seeded()
        rows = await self._db.fetch(
            "SELECT code, enabled FROM infra_feature_flag ORDER BY code"
        )
        return {row["code"]: bool(row["enabled"]) for row in rows}

    async def is_enabled(self, code: str, default: bool = False) -> bool:
        await self._ensure_seeded()
        value = await self._db.fetchval(
            "SELECT enabled FROM infra_feature_flag WHERE code = $1", code
        )
        return bool(value) if value is not None else default

    async def resync(self) -> list[str]:
        """按 `feature_flags.json` 强制重导：逐条 upsert，并**删除文件里已经没有的**。

        为什么需要单独一个方法：首次导入是"表空才种"（见 `_ensure_seeded`），
        所以**删掉一条开关在库里永远不会生效** —— 文件里没了、库里还在，
        它还会跟着迁移文件搬进下一个环境，并被 `/app/bootstrap` 下发给前端。
        这就是"文件是对的、跑起来是旧的"里最难查的一种：
        它不报错，只是让下一个人以为那条开关还有人用。

        返回被删掉的开关码，供 `--resync-registry` 如实打印。
        """
        wanted = _read_flags(self._seed_path)
        for code, enabled in wanted.items():
            await self._db.execute(
                """
                INSERT INTO infra_feature_flag (code, enabled)
                VALUES ($1, $2)
                ON CONFLICT (code) DO UPDATE SET enabled = EXCLUDED.enabled
                """,
                code,
                enabled,
            )
        rows = await self._db.fetch("SELECT code FROM infra_feature_flag")
        stale = sorted(row["code"] for row in rows if row["code"] not in wanted)
        if stale:
            await self._db.execute(
                "DELETE FROM infra_feature_flag WHERE code = ANY($1::text[])", stale
            )
        self._seeded = True
        return stale

    async def _ensure_seeded(self) -> None:
        if self._seeded:
            return
        async with self._lock:
            if self._seeded:
                return
            count = await self._db.fetchval("SELECT COUNT(*) FROM infra_feature_flag")
            if int(count or 0) == 0:
                for code, enabled in _read_flags(self._seed_path).items():
                    await self._db.execute(
                        """
                        INSERT INTO infra_feature_flag (code, enabled)
                        VALUES ($1, $2)
                        ON CONFLICT (code) DO NOTHING
                        """,
                        code,
                        enabled,
                    )
            self._seeded = True


def _read_flags(path: Path) -> dict[str, bool]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    items = raw.get("items")
    if isinstance(items, list):
        return {
            str(item["code"]): bool(item.get("enabled", False))
            for item in items
            if isinstance(item, dict) and "code" in item
        }
    return {
        str(key): bool(value)
        for key, value in raw.items()
        if not str(key).startswith("_") and isinstance(value, bool)
    }


__all__ = ["PostgresFeatureFlagGateway"]
