"""定向切换 Kev 意图路由，不触碰其它动态资源。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "zhiyin-src" / "template" / "data" / "registry"
DEFAULT_BACKUP = Path(__file__).with_name("kev-config-backup.json")
DEFAULT_DSN = "postgresql://zhiyin:zhiyin@127.0.0.1:55432/zhiyin"


def _seed_item(filename: str, code: str) -> dict:
    raw = json.loads((REGISTRY_DIR / filename).read_text(encoding="utf-8"))
    for item in raw.get("items", []):
        if item.get("code") == code:
            return item
    raise RuntimeError(f"seed item not found: {filename}:{code}")


async def _read_current(connection: asyncpg.Connection) -> dict:
    flag = await connection.fetchrow(
        "SELECT enabled FROM infra_feature_flag WHERE code = $1",
        "decision_intent_routing",
    )
    policy = await connection.fetchrow(
        """
        SELECT payload, status, sort_order
        FROM biz_registry_item
        WHERE kind = $1 AND code = $2
        """,
        "policy_params",
        "decision_routing",
    )
    payload = policy["payload"] if policy else None
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "feature_flag": {
            "exists": flag is not None,
            "enabled": bool(flag["enabled"]) if flag else False,
        },
        "policy": {
            "exists": policy is not None,
            "payload": payload,
            "status": str(policy["status"]) if policy else None,
            "sort_order": int(policy["sort_order"]) if policy else None,
        },
    }


async def _restore(connection: asyncpg.Connection, backup: dict) -> None:
    flag = backup["feature_flag"]
    if flag["exists"]:
        await connection.execute(
            """
            INSERT INTO infra_feature_flag (code, enabled, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (code) DO UPDATE
            SET enabled = EXCLUDED.enabled, updated_at = NOW()
            """,
            "decision_intent_routing",
            flag["enabled"],
        )
    else:
        await connection.execute(
            "DELETE FROM infra_feature_flag WHERE code = $1",
            "decision_intent_routing",
        )

    policy = backup["policy"]
    if policy["exists"]:
        await connection.execute(
            """
            INSERT INTO biz_registry_item
                (kind, code, payload, status, sort_order, updated_at)
            VALUES ($1, $2, $3::jsonb, $4, $5, NOW())
            ON CONFLICT (kind, code) DO UPDATE
            SET payload = EXCLUDED.payload,
                status = EXCLUDED.status,
                sort_order = EXCLUDED.sort_order,
                updated_at = NOW()
            """,
            "policy_params",
            "decision_routing",
            json.dumps(policy["payload"], ensure_ascii=False),
            policy.get("status") or "enabled",
            int(policy.get("sort_order") or 0),
        )
    else:
        await connection.execute(
            "DELETE FROM biz_registry_item WHERE kind = $1 AND code = $2",
            "policy_params",
            "decision_routing",
        )


async def _set_mode(
    connection: asyncpg.Connection, mode: str, backup_path: Path
) -> None:
    if not backup_path.exists():
        backup_path.write_text(
            json.dumps(await _read_current(connection), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"原配置已备份：{backup_path}")

    policy = _seed_item("policy_params.json", "decision_routing")
    policy["value"]["mode"] = mode
    enabled = mode != "off"
    async with connection.transaction():
        await connection.execute(
            """
            INSERT INTO infra_feature_flag (code, enabled, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (code) DO UPDATE
            SET enabled = EXCLUDED.enabled, updated_at = NOW()
            """,
            "decision_intent_routing",
            enabled,
        )
        await connection.execute(
            """
            INSERT INTO biz_registry_item
                (kind, code, payload, status, sort_order, updated_at)
            VALUES ($1, $2, $3::jsonb, $4, $5, NOW())
            ON CONFLICT (kind, code) DO UPDATE
            SET payload = EXCLUDED.payload,
                status = EXCLUDED.status,
                sort_order = EXCLUDED.sort_order,
                updated_at = NOW()
            """,
            "policy_params",
            "decision_routing",
            json.dumps(policy, ensure_ascii=False),
            str(policy.get("status", "confirmed")),
            int(policy.get("sort_order", 0) or 0),
        )
    print(f"Kev 意图路由已切换为 {mode}；重启后端或调用配置重载后生效。")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("active", "shadow", "off", "restore"))
    parser.add_argument(
        "--dsn", default=os.getenv("ZHIYIN_POSTGRES_DSN", DEFAULT_DSN)
    )
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    args = parser.parse_args()
    args.backup.parent.mkdir(parents=True, exist_ok=True)

    connection = await asyncpg.connect(args.dsn)
    try:
        if args.mode == "restore":
            if not args.backup.is_file():
                raise RuntimeError(f"backup not found: {args.backup}")
            backup = json.loads(args.backup.read_text(encoding="utf-8"))
            async with connection.transaction():
                await _restore(connection, backup)
            print("已恢复接入前的 Kev 开关和策略配置。")
        else:
            await _set_mode(connection, args.mode, args.backup)
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
