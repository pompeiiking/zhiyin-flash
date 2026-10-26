"""PostgreSQL 功能开关实现。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from zhiyin_data_sdk.gateways.feature_flag import FeatureFlagGateway
from zhiyin_infrastructure.postgres.database import PostgresDatabase

logger = logging.getLogger(__name__)

#: 落在 `infra_runtime_config` 里的种子版本。只在文件版本更高时重导一次，
#: 之后仍以库为准 —— 这样“产品默认值改了”能随发布生效，而运维在库里的
#: 开关调整不会被每次重启覆盖。
SEED_VERSION_KEY = "feature_flags.seed_version"


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
        await self._remember_version(_read_version(self._seed_path))
        self._seeded = True
        return stale

    async def _ensure_seeded(self) -> None:
        if self._seeded:
            return
        async with self._lock:
            if self._seeded:
                return
            seed = _read_flags(self._seed_path)
            version = _read_version(self._seed_path)
            applied = await self._applied_version()
            if version > applied:
                # 种子升级：文件是发布内容的一部分，产品默认值（例如把已经
                # 实现的导出打开）必须能到达已有库；只在这一刻以文件为准，
                # 之后库里的运维调整继续有效。
                for code, enabled in seed.items():
                    await self._db.execute(
                        """
                        INSERT INTO infra_feature_flag (code, enabled)
                        VALUES ($1, $2)
                        ON CONFLICT (code) DO UPDATE SET enabled = EXCLUDED.enabled
                        """,
                        code,
                        enabled,
                    )
                await self._remember_version(version)
                if applied:
                    logger.warning(
                        "功能开关种子已升级（版本 %s → %s），已按 data/registry/feature_flags.json 重导；"
                        "之后的库内调整仍以库为准。",
                        applied,
                        version,
                    )
            else:
                count = await self._db.fetchval("SELECT COUNT(*) FROM infra_feature_flag")
                if int(count or 0) == 0:
                    for code, enabled in seed.items():
                        await self._db.execute(
                            """
                            INSERT INTO infra_feature_flag (code, enabled)
                            VALUES ($1, $2)
                            ON CONFLICT (code) DO NOTHING
                            """,
                            code,
                            enabled,
                        )
                    await self._remember_version(version)
            self._seeded = True

    async def _applied_version(self) -> int:
        raw = await self._db.fetchval(
            "SELECT value->>'version' FROM infra_runtime_config WHERE key = $1",
            SEED_VERSION_KEY,
        )
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    async def _remember_version(self, version: int) -> None:
        await self._db.execute(
            """
            INSERT INTO infra_runtime_config (key, value, description, updated_at)
            VALUES ($1, $2::jsonb, $3, NOW())
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                description = EXCLUDED.description,
                updated_at = NOW()
            """,
            SEED_VERSION_KEY,
            json.dumps({"version": version}),
            "功能开关种子已应用到的版本",
        )


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


def _read_version(path: Path) -> int:
    """种子版本：没有写 `_version` 的旧文件按 1 算（不会触发意外重导）。"""
    if not path.is_file():
        return 1
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 1
    if not isinstance(raw, dict):
        return 1
    try:
        return int(raw.get("_version", 1))
    except (TypeError, ValueError):
        return 1


__all__ = ["PostgresFeatureFlagGateway", "SEED_VERSION_KEY"]
