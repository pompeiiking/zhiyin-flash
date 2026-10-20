"""旧画像字段回填 ``entry_type`` / ``verification`` / ``status``。

为什么需要它
------------
《个人画像设计-2026-10-20》第 10 节、验收 P28：结构化记录字段上线后，历史
``biz_profile_field`` 行里 ``entry_type`` / ``verification`` 可能为空，``status``
可能是空串或非法值。读侧虽然会按词表兜底推导类别，但库里一直空着意味着：

- 无法按用途视图稳定筛选（每次读都要再推一遍，且不同读侧各写一份口径）；
- 迁移差异没有预览、重跑和回退依据，不敢批量执行。

这里先**预览差异**，确认后再 ``--apply`` 写回。规则只有一条：**字段键 → 类别**
按 ``profile_taxonomy.entry_type_of``，**来源 → 核实状态**按
``profile_taxonomy.verification_for``，状态补成 ``active``；已经合法的值不覆盖，
所以脚本可以重复执行，第二次差异为 0。

用法
----
    # 预览（默认 dry-run，不写库；省略 --dsn 时读环境里的连接配置）
    python scripts/migrate_profile_entries.py --dsn postgresql://…/zhiyin

    # 写回
    python scripts/migrate_profile_entries.py --dsn … --apply

    # 只处理前 500 行（大表分批）
    python scripts/migrate_profile_entries.py --dsn … --limit 500

回退：迁移只改这三列，写回前按 ``user_id`` + ``key`` 可逐行还原原值
（用 ``--limit`` 分批时请先导出对应行）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

# 让脚本不装包也能跑（与 pyproject 的 pythonpath 同一份清单）。
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
from zhiyin_kernel.enums import (  # noqa: E402
    ProfileEntryStatus,
    ProfileEntryType,
    ProfileVerification,
)

#: 回填涉及的三列（差异里的键也只用这三个）。
BACKFILL_COLUMNS: tuple[str, ...] = ("entry_type", "verification", "status")

#: 预览里最多打印多少条样例：迁移要能一眼核对，不是把整表倒在终端上。
SAMPLE_LIMIT = 10


def _enum_or_none(enum_cls, raw: Any):
    """把库里的字符串转成枚举；空值 / 非法值都算“需要回填”。"""
    if raw is None:
        return None
    try:
        return enum_cls(raw)
    except (ValueError, TypeError):
        return None


def desired_backfill(key: str, source: str) -> dict[str, str]:
    """一行画像字段应回填到的值（纯函数，测试只依赖这一层）。"""
    entry_type = profile_taxonomy.entry_type_of(key)
    return {
        "entry_type": entry_type.value,
        "verification": profile_taxonomy.verification_for(source).value,
        "status": ProfileEntryStatus.ACTIVE.value,
    }


def plan_backfill(row: Mapping[str, Any]) -> Optional[dict[str, str]]:
    """一行 → 需要写回的列；没有差异返回 ``None``。

    只回填空值或非法值，不覆盖库里已经合法的值：迁移不是“把所有人的记录
    按今天的词表重新分类”，那会把已经人工核对过的类别冲掉。
    """
    key = str(row.get("key") or "")
    source = str(row.get("source") or "")
    desired = desired_backfill(key, source)
    updates: dict[str, str] = {}
    for column, enum_cls in (
        ("entry_type", ProfileEntryType),
        ("verification", ProfileVerification),
    ):
        if _enum_or_none(enum_cls, row.get(column)) is None:
            updates[column] = desired[column]
    if _enum_or_none(ProfileEntryStatus, row.get("status")) is None:
        updates["status"] = desired["status"]
    return updates or None


def plan_rows(rows: Iterable[Mapping[str, Any]]) -> list[tuple[Mapping[str, Any], dict[str, str]]]:
    """把候选行变成 (row, 差异) 列表；无差异的行被过滤掉。"""
    plans: list[tuple[Mapping[str, Any], dict[str, str]]] = []
    for row in rows:
        diff = plan_backfill(row)
        if diff:
            plans.append((row, diff))
    return plans


def summarize(plans: Iterable[tuple[Mapping[str, Any], dict[str, str]]]) -> dict[str, Counter]:
    """按类别 / 核实状态 / 状态统计差异，供预览和写回后核对。"""
    summary: dict[str, Counter] = {
        "entry_type": Counter(),
        "verification": Counter(),
        "status": Counter(),
    }
    for _row, diff in plans:
        for column in BACKFILL_COLUMNS:
            if column in diff:
                summary[column][diff[column]] += 1
    return summary


def _format_row(row: Mapping[str, Any], diff: dict[str, str]) -> str:
    user_id = str(row.get("user_id") or "")
    key = str(row.get("key") or "")
    source = str(row.get("source") or "")
    changes = " · ".join(f"{column}={value}" for column, value in diff.items())
    return f"  {user_id} / {key} / {source} → {changes}"


def print_preview(
    rows: int,
    plans: list[tuple[Mapping[str, Any], dict[str, str]]],
) -> None:
    """打印扫描数、分类计数与少量样例（写回前预览用）。"""
    print(f"扫描画像字段 {rows} 行；{len(plans)} 行需要回填")
    if not plans:
        print("没有差异：所有行的 entry_type / verification / status 都已合法。")
        return
    summary = summarize(plans)
    labels = {
        "entry_type": "按类别",
        "verification": "按核实状态",
        "status": "按状态",
    }
    for column in BACKFILL_COLUMNS:
        counts = summary[column]
        if not counts:
            continue
        detail = " · ".join(
            f"{_enum_label(column, value)} {count}"
            for value, count in counts.most_common()
        )
        print(f"{labels[column]}：{detail}")
    print(f"样例（最多 {SAMPLE_LIMIT} 行）：")
    for row, diff in plans[:SAMPLE_LIMIT]:
        print(_format_row(row, diff))


def _enum_label(column: str, value: str) -> str:
    """预览里优先用中文名；认不出的值原样显示，不编一个。"""
    if column == "entry_type":
        return profile_taxonomy.entry_type_label(value)
    labels = (
        profile_taxonomy.VERIFICATION_LABELS
        if column == "verification"
        else profile_taxonomy.STATUS_LABELS
    )
    enum_cls = ProfileVerification if column == "verification" else ProfileEntryStatus
    try:
        return labels[enum_cls(value)]
    except ValueError:
        return value


def _resolve_dsn(dsn: str) -> str:
    if dsn:
        return dsn
    from zhiyin_boot.settings import Settings

    resolved = Settings.from_env().postgres_dsn
    if not resolved:
        raise SystemExit("请用 --dsn 指定 PostgreSQL 连接串。")
    return resolved


async def run(dsn: str, *, apply: bool, limit: int = 0) -> int:
    """读取候选行、预览差异；``apply=True`` 时在事务里写回。"""
    import asyncpg

    # 候选行：三列里任一为空，或值不在受控词表里。``--limit`` 限制的是候选行，
    # 大表分批时不会因为“前 N 行恰好都是干净的”而漏掉后面的差异。
    candidates = (
        "WHERE entry_type IS NULL OR entry_type = '' "
        "   OR verification IS NULL OR verification = '' "
        "   OR status IS NULL OR status = '' "
        "   OR NOT (entry_type = ANY($1::text[])) "
        "   OR NOT (verification = ANY($2::text[])) "
        "   OR NOT (status = ANY($3::text[]))"
    )
    params: list[Any] = [
        [item.value for item in ProfileEntryType],
        [item.value for item in ProfileVerification],
        [item.value for item in ProfileEntryStatus],
    ]
    statement = (
        "SELECT user_id, key, source, entry_type, verification, status "
        "FROM biz_profile_field " + candidates + " ORDER BY user_id, key"
    )
    if limit > 0:
        statement += " LIMIT $4"
        params.append(limit)
    connection = None
    try:
        connection = await asyncpg.connect(dsn)
        rows = await connection.fetch(statement, *params)
        plans = plan_rows(rows)
        print_preview(len(rows), plans)
        if not apply:
            return 0
        if not plans:
            print("已确认：没有可写回的差异。")
            return 0

        async with connection.transaction():
            for row, diff in plans:
                # 未出现在 diff 里的列保持原值：只改需要回填的那几格。
                merged = {
                    column: diff.get(column, row.get(column))
                    for column in BACKFILL_COLUMNS
                }
                await connection.execute(
                    "UPDATE biz_profile_field "
                    "SET entry_type=$1, verification=$2, status=$3 "
                    "WHERE user_id=$4 AND key=$5",
                    merged["entry_type"],
                    merged["verification"],
                    merged["status"],
                    row["user_id"],
                    row["key"],
                )
        print(f"已写回 {len(plans)} 行。再次执行本脚本应为 0 差异。")
        return 0
    except Exception as exc:  # noqa: BLE001 - 运维脚本：如实报告连库/表结构问题
        print(f"迁移未完成：{exc}", file=sys.stderr)
        return 2
    finally:
        if connection is not None:
            await connection.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_profile_entries",
        description="回填 biz_profile_field 的 entry_type / verification / status（默认 dry-run）",
    )
    parser.add_argument("--dsn", default="", help="PostgreSQL 连接串；省略时读环境配置")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览差异，不写库（默认行为）",
    )
    parser.add_argument("--apply", action="store_true", help="把差异写回数据库")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多扫描多少行，0 表示全部（大表分批时使用）",
    )
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply 与 --dry-run 只能选一个")
    if args.limit < 0:
        parser.error("--limit 不能为负数")
    dsn = _resolve_dsn(args.dsn)
    return asyncio.run(run(dsn, apply=args.apply, limit=args.limit))


if __name__ == "__main__":
    sys.exit(main())
