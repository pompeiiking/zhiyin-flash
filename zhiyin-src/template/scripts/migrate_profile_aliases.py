"""旧画像字段别名迁移（《个人画像设计-2026-10-20》P28）。

背景
----
正式结构化上线前，模型自由生成过一批字段键（``career_goal`` / ``weaknesses`` /
``constraint`` / ``preferred_city`` …）。读侧虽然按词表兜底把它们归到「补充信息」，
但值本身没有迁到规范键上：同一个意思仍以旧键存在，用途视图和界面都读不到它。

本脚本只迁移**明确有规范对应**的旧键，规则：
- ``career_goal`` / ``career_interest`` → ``target_direction``，但只记为
  ``state=exploring``，不把旧“目标”自动提升为“已选”；
- ``interests`` / ``interest_direction`` → ``interest``；
- ``weaknesses`` → ``weakness``、``strengths`` → ``skills``；
- ``constraint`` → ``constraints``、``preferred_city`` → ``city``；
- ``grade`` → ``study_year``。
其余认不出的键不猜，继续按「补充信息」保留。

安全边界
--------
- 默认 dry-run；``--apply`` 前先把受影响的旧行/目标行/新建版本写进备份 JSON；
- 同值合并、异值记为 ``conflict`` 提案，不覆盖当前值；
- 重复执行第二次 0 差异；
- ``--restore 备份文件`` 按备份回退（删新版本、恢复旧键与目标原值）。

用法
----
    python scripts/migrate_profile_aliases.py --dsn …            # 预览
    python scripts/migrate_profile_aliases.py --dsn … --apply    # 迁移（写备份）
    python scripts/migrate_profile_aliases.py --dsn … --restore profile-aliases-backup.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

_TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
for _sub in (
    "zhiyin-kernel",
    "zhiyin-data-sdk",
    "zhiyin-business",
    "zhiyin-orchestration",
    "zhiyin-infrastructure",
    "zhiyin-boot",
):
    sys.path.insert(0, str(_TEMPLATE_ROOT / _sub))

from zhiyin_kernel import profile_taxonomy  # noqa: E402
from zhiyin_kernel.enums import ProfileEntryStatus, ProfileSource  # noqa: E402

#: 旧键 → (规范键, 迁移附加属性)。只收“明确同一件事”的键；认不出的留给补充信息。
ALIAS_TARGETS: dict[str, tuple[str, dict[str, Any]]] = {
    "career_goal": ("target_direction", {"state": "exploring"}),
    "career_interest": ("target_direction", {"state": "exploring"}),
    "interests": ("interest", {}),
    "interest_direction": ("interest", {}),
    "weaknesses": ("weakness", {}),
    "strengths": ("skills", {}),
    "constraint": ("constraints", {}),
    "preferred_city": ("city", {}),
    "grade": ("study_year", {}),
}

COLUMNS = (
    "user_id, key, label, value, confidence, source, evidence, updated_at, "
    "entry_type, attributes, verification, status, origin_ref, valid_from, "
    "valid_to, event_at, entry_version, superseded_by"
)


def target_for(key: str) -> tuple[str, dict[str, Any]] | None:
    """旧键 → 规范键与附加属性；不是别名返回 None。"""
    return ALIAS_TARGETS.get((key or "").strip())


def _decode(row: Mapping[str, Any]) -> dict[str, Any]:
    """JSONB 列从 asyncpg 读出来是字符串；还原成 Python 值再比较/写回。"""
    decoded = dict(row)
    for field in ("value", "attributes", "evidence"):
        raw = decoded.get(field)
        if isinstance(raw, str):
            try:
                decoded[field] = json.loads(raw)
            except ValueError:
                pass
    return decoded


def plan_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """把旧键行排成迁移动作（纯函数，便于测试）。

    动作类型：
      - ``create``：规范键不存在，复制旧值；
      - ``merge_same``：规范键已存在且值相同，只删旧键；
      - ``conflict``：规范键已存在但值不同，保留当前值并追加冲突提案。
    """
    by_key = {(str(row["user_id"]), str(row["key"])): _decode(row) for row in rows}
    original_by_key = dict(by_key)
    plans: list[dict[str, Any]] = []
    for (user_id, key), row in list(by_key.items()):
        target = target_for(key)
        if target is None:
            continue
        target_key, extra = target
        current = by_key.get((user_id, target_key))
        value = row.get("value")
        if current is None:
            action = "create"
        elif current.get("value") == value:
            action = "merge_same"
        else:
            action = "conflict"
        plans.append(
            {
                "action": action,
                "user_id": user_id,
                "alias_key": key,
                "target_key": target_key,
                "attributes": {**(row.get("attributes") or {}), **extra},
                "row": dict(row),
                "current": dict(current) if current else None,
                "target_before": original_by_key.get((user_id, target_key)),
            }
        )
        # Later aliases for the same user/target must see the planned creation.
        # Otherwise two `create` upserts silently discard the first value.
        if action == "create":
            by_key[(user_id, target_key)] = {
                **dict(row), "key": target_key,
                "attributes": {**(row.get("attributes") or {}), **extra},
            }
    return plans


def summarize(plans: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan["action"]] = counts.get(plan["action"], 0) + 1
    return counts


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "key": row["key"],
        "label": row.get("label") or "",
        "value": row.get("value"),
        "confidence": row.get("confidence") or 0.0,
        "source": row.get("source") or ProfileSource.CONVERSATION.value,
        "evidence": row.get("evidence") or [],
        "updated_at": row.get("updated_at"),
        "entry_type": row.get("entry_type"),
        "attributes": row.get("attributes") or {},
        "verification": row.get("verification"),
        "status": row.get("status") or ProfileEntryStatus.ACTIVE.value,
        "origin_ref": row.get("origin_ref") or "",
        "valid_from": row.get("valid_from"),
        "valid_to": row.get("valid_to"),
        "event_at": row.get("event_at"),
        "entry_version": row.get("entry_version") or 1,
        "superseded_by": row.get("superseded_by") or "",
    }


def _dt(value: Any) -> Any:
    """备份 JSON 里的时间字符串 → datetime；已是时间对象就原样返回。"""
    if isinstance(value, str) and value:
        from datetime import datetime

        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value


async def _insert_field(connection: Any, payload: dict[str, Any]) -> None:
    await connection.execute(
        f"INSERT INTO biz_profile_field ({COLUMNS}) VALUES "
        "($1,$2,$3,$4::jsonb,$5,$6,$7::jsonb,$8,$9,$10::jsonb,$11,$12,$13,$14,$15,$16,$17,$18) "
        "ON CONFLICT (user_id,key) DO UPDATE SET "
        "label=EXCLUDED.label, value=EXCLUDED.value, confidence=EXCLUDED.confidence, "
        "source=EXCLUDED.source, evidence=EXCLUDED.evidence, updated_at=EXCLUDED.updated_at, "
        "entry_type=EXCLUDED.entry_type, attributes=EXCLUDED.attributes, "
        "verification=EXCLUDED.verification, status=EXCLUDED.status, origin_ref=EXCLUDED.origin_ref, "
        "valid_from=EXCLUDED.valid_from, valid_to=EXCLUDED.valid_to, event_at=EXCLUDED.event_at, "
        "entry_version=EXCLUDED.entry_version, superseded_by=EXCLUDED.superseded_by",
        payload["user_id"], payload["key"], payload["label"], _json(payload["value"]),
        payload["confidence"], payload["source"], _json(payload["evidence"]), _dt(payload["updated_at"]),
        payload["entry_type"], _json(payload["attributes"]), payload["verification"],
        payload["status"], payload["origin_ref"], _dt(payload["valid_from"]), _dt(payload["valid_to"]),
        _dt(payload["event_at"]), payload["entry_version"], payload["superseded_by"],
    )


async def _insert_revision(connection: Any, plan: dict[str, Any], revision_id: str) -> None:
    row = plan["row"]
    await connection.execute(
        """
        INSERT INTO biz_profile_field_revision
            (id,user_id,key,label,value,attributes,confidence,source,verification,status,
             evidence,origin_ref,valid_from,valid_to,event_at,entry_version,created_at,
             replaced_at,change_reason)
        VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8,$9,'conflict',$10::jsonb,$11,
                $12,$13,$14,$15,NOW(),NULL,$16)
        """,
        revision_id, plan["user_id"], plan["target_key"], row.get("label") or "",
        _json(row.get("value")), _json(plan["attributes"]), row.get("confidence") or 0.0,
        row.get("source") or ProfileSource.CONVERSATION.value, row.get("verification"),
        _json(row.get("evidence") or []), row.get("origin_ref") or "",
        row.get("valid_from"), row.get("valid_to"), row.get("event_at"),
        (row.get("entry_version") or 1) + 1, "旧字段别名迁移：与当前记录不一致，等待核对",
    )


async def run(dsn: str, *, apply: bool, backup_path: Path | None = None) -> int:
    import asyncpg
    from uuid import uuid4

    connection = await asyncpg.connect(dsn)
    try:
        rows = [dict(row) for row in await connection.fetch(f"SELECT {COLUMNS} FROM biz_profile_field")]
        plans = plan_rows(rows)
        print(f"扫描字段 {len(rows)} 行；识别旧别名 {len(plans)} 条：{summarize(plans)}")
        for plan in plans[:10]:
            print(
                f"  {plan['user_id']} / {plan['alias_key']} → {plan['target_key']} "
                f"（{plan['action']}）：{plan['row'].get('value')!r}"
            )
        if not apply:
            return 0
        if not plans:
            print("已确认：没有可迁移的旧别名。")
            return 0
        backup_path = backup_path or Path("profile-aliases-backup.json")
        backup = {
            "plans": [
                {
                    "action": plan["action"],
                    "user_id": plan["user_id"],
                    "alias_key": plan["alias_key"],
                    "target_key": plan["target_key"],
                    "alias_row": _row_payload(plan["row"]),
                    "target_before": _row_payload(plan["target_before"]) if plan["target_before"] else None,
                    "revision_id": (
                        f"rev_{uuid4().hex[:12]}" if plan["action"] == "conflict" else None
                    ),
                }
                for plan in plans
            ]
        }
        backup_path.write_text(_json(backup), encoding="utf-8")
        async with connection.transaction():
            for item in backup["plans"]:
                plan = next(
                    p for p in plans
                    if p["user_id"] == item["user_id"] and p["alias_key"] == item["alias_key"]
                )
                if plan["action"] == "create":
                    payload = _row_payload(plan["row"])
                    payload.update(
                        key=plan["target_key"],
                        entry_type=profile_taxonomy.entry_type_of(plan["target_key"]).value,
                        attributes=plan["attributes"],
                        verification=payload["verification"] or profile_taxonomy.verification_for(payload["source"]).value,
                    )
                    await _insert_field(connection, payload)
                elif plan["action"] == "conflict":
                    await _insert_revision(connection, plan, item["revision_id"])
                await connection.execute(
                    "DELETE FROM biz_profile_field WHERE user_id=$1 AND key=$2",
                    plan["user_id"], plan["alias_key"],
                )
        print(f"已迁移 {len(plans)} 条旧别名；备份：{backup_path}")
        print("再次执行应为 0 条。")
        return 0
    finally:
        await connection.close()


async def restore(dsn: str, backup_path: Path) -> int:
    import asyncpg

    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            for item in backup.get("plans", []):
                if item.get("revision_id"):
                    await connection.execute(
                        "DELETE FROM biz_profile_field_revision WHERE id=$1", item["revision_id"]
                    )
                target_before = item.get("target_before")
                if target_before is None:
                    await connection.execute(
                        "DELETE FROM biz_profile_field WHERE user_id=$1 AND key=$2",
                        item["user_id"], item["target_key"],
                    )
                else:
                    await _insert_field(connection, target_before)
                await _insert_field(connection, item["alias_row"])
        print(f"已按 {backup_path} 回退 {len(backup.get('plans', []))} 条。")
        return 0
    finally:
        await connection.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="migrate_profile_aliases")
    parser.add_argument("--dsn", default="", help="PostgreSQL 连接串；省略时读环境配置")
    parser.add_argument("--apply", action="store_true", help="写回（默认只预览）")
    parser.add_argument("--backup", default="profile-aliases-backup.json", help="apply 前的备份文件")
    parser.add_argument("--restore", default="", help="按备份文件回退，不执行迁移")
    args = parser.parse_args(argv)
    dsn = args.dsn
    if not dsn:
        from zhiyin_boot.settings import Settings

        dsn = Settings.from_env().postgres_dsn
        if not dsn:
            parser.error("请用 --dsn 指定 PostgreSQL 连接串")
    if args.restore:
        return asyncio.run(restore(dsn, Path(args.restore)))
    return asyncio.run(run(dsn, apply=args.apply, backup_path=Path(args.backup)))


if __name__ == "__main__":
    sys.exit(main())
