"""数据库迁移：把「核心策略」与（可选）用户数据从旧库搬到新库。

为什么需要它
------------
部署到**空库**时，`data/registry/*.json` 会在启动时自动导入，所以动态资源
（文案 / 提示词 / 编排规则 / 环节口径 / 理论卡 / 产出契约 …）能自己长出来。
但下面这几类**长不出来**：

- `infra_ai_provider` / `infra_ai_model` / `infra_ai_route`：模型供应商、模型清单、
  场景到模型的路由，以及**模型密钥**。它们只在首次开机时由 `.env` 播一次种子，
  之后以库为准 —— 运营在库里换过模型，空库就回到默认值了。
- `infra_runtime_config`：装配口径（能力位归属、分级门禁）。
  仓库里改过的文件进不了旧库（那是"以库为准"的代价），旧库里改过的值同样不在文件里。
- `biz_registry_item` / `ai_prompt_template` / `ai_routing_rule`：文件能补回**结构**，
  但补不回**运营在库里改过的内容**（这正是"以库为准"的意思）。

所以迁移的判据不是"这张表重要吗"，而是**这份内容在文件里有没有**。

用法
----
    # 1) 从旧库导出（默认只导"策略与配置"）
    python scripts/migrate_db.py export --dsn postgresql://…/zhiyin --out migration.json

    # 连用户数据一起搬（换机器、保留所有人的进度时用）
    python scripts/migrate_db.py export --dsn … --out migration.json --include-users

    # 2) 导入到新库（目标库的 schema 会自动建）
    python scripts/migrate_db.py import --dsn postgresql://…/zhiyin_new --in migration.json

    # 3) 核对
    python scripts/migrate_db.py verify --dsn postgresql://…/zhiyin_new --in migration.json

导出的文件里**含模型密钥**（`infra_ai_provider.config.api_key`）。它是要给部署用的，
所以默认带上并在开头打印警告；要分享这个文件时加 `--redact-secrets` 把密钥抹掉，
部署时再用 `ZHIYIN_LLM_API_KEY` 补一次。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

# 让脚本不装包也能跑（与 pyproject 的 pythonpath 同一份清单）
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

FORMAT_VERSION = 1

#: 默认迁移：库里的策略与配置（文件补不回来的那部分）
CONFIG_TABLES: tuple[str, ...] = (
    "infra_ai_provider",
    "infra_ai_model",
    "infra_ai_route",
    "infra_runtime_config",
    "infra_feature_flag",
    "biz_registry_item",
    "ai_prompt_template",
    "ai_routing_rule",
)

#: `--include-users` 时一并迁移：用户进度与资产
USER_TABLES: tuple[str, ...] = (
    "biz_user_account",
    "infra_auth_credential",
    "biz_profile",
    "biz_profile_field",
    "biz_profile_gap",
    "biz_behavior_log",
    "biz_conversation_memory",
    "biz_conversation_turn",
    "biz_user_note",
    "biz_academic_snapshot",
    "biz_task_session",
    "biz_asset_version",
    "biz_asset_content",
    "biz_calendar_node",
    "biz_track_event",
    "ai_task_result",
)

#: `--include-vectors` 时迁移：向量数据与同步进度（大，但重建很贵）
VECTOR_TABLES: tuple[str, ...] = (
    "vec_record",
    "infra_vector_sync_state",
)

#: **刻意不迁**的表与理由
SKIPPED: dict[str, str] = {
    "infra_auth_session": "登录令牌是短期凭据：换环境后重新登录即可，搬过去只会带走一串可能已失效的会话",
    "orc_event_outbox": "编排运行态：出站箱里的待投递事件属于旧环境的一次性中间状态",
    "orc_schedule_job": "编排运行态：到点任务由新环境的调度器按当前时间重新排",
    "orc_notification": "编排运行态：旧环境已发出的提醒不该在新环境再弹一次",
}


# ---------------------------------------------------------------------------
# 类型适配：库 → JSON → 库
# ---------------------------------------------------------------------------
#
# 这一段是整份迁移里唯一容易出错的地方，所以口径写得死一点：
#
#   1. **JSON 里只放 JSON 有的东西** —— 没有 JSON 表示的（时间、二进制、向量）
#      一律转成字符串或 base64，靠"回到库里时再 cast"还原。
#   2. **回到库里时，参数一律用 `$n::text::<列类型>`**。
#      直接把参数标成 `$n::timestamptz` 是行不通的：asyncpg 会按 cast 目标
#      推断参数类型，于是要求传 `datetime` 对象，而我们手里是从 JSON 读回来的
#      字符串 —— 报 `expected a datetime.date or datetime.datetime instance`。
#      先落到 `text` 再让 PostgreSQL 自己转，才是"字符串能喂给任何类型"的写法。
#   3. 只有 `bytea` 例外：它走二进制 codec，`::text` 反而会毁掉内容。
#
# 判定类型族用的是 `pg_type.typname`（`jsonb` / `vector` / `bytea` / …），
# 写进 SQL 的 cast 目标用的是 `atttypid::regtype`（`timestamp with time zone` /
# `character varying` / `vector` …）—— 两者不是一回事，所以要都存进迁移文件，
# 导入端不连源库也能自己还原。

_JSON_TYPES = ("json", "jsonb")
_VECTOR_TYPES = ("vector", "halfvec", "sparsevec")


def _family(base_type: str) -> str:
    """列类型 → 类型族。迁移文件里记的是族名，导入端按族还原。"""
    base = base_type.lower()
    if base in _JSON_TYPES:
        return "json"
    if base == "bytea":
        return "binary"
    if base in _VECTOR_TYPES:
        return "vector"
    return "scalar"


def _as_floats(value: Any) -> list[float]:
    """pgvector 的向量值 → 普通浮点列表。

    `register_vector()` 装的是二进制 codec，`vector` 列读回来是 **pgvector 的
    `Vector` 对象**（`halfvec` / `sparsevec` 同理），不是 list，也不是 numpy 数组 ——
    直接迭代会报 `TypeError: 'Vector' object is not iterable`。
    """
    to_list = getattr(value, "to_list", None)
    if callable(to_list):
        return [float(item) for item in to_list()]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return [float(item) for item in tolist()]
    return [float(item) for item in value]


def encode_value(value: Any, family: str) -> Any:
    """库里的值 → 可写进 JSON 的值。"""
    if value is None:
        return None
    if family == "binary":
        return {"__bytes__": base64.b64encode(bytes(value)).decode("ascii")}
    if family == "json":
        # asyncpg 对 json / jsonb 返回字符串，解析成对象存，读起来也方便
        return json.loads(value) if isinstance(value, str) else value
    if family == "vector":
        return _as_floats(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        # numeric 走字符串：JSON 只有双精度浮点，存数字会在第 16 位有效数字上丢精度
        return str(value)
    return value


def decode_value(value: Any, family: str) -> Any:
    """JSON 里的值 → 可以喂给 asyncpg 的值。

    除 `binary` 外一律返回 `str` —— 参数会以 `::text::<列类型>` 的形式交给
    PostgreSQL 转换（见上面第 2 条）。
    """
    if value is None:
        return None
    if family == "binary":
        if isinstance(value, dict) and "__bytes__" in value:
            return base64.b64decode(value["__bytes__"])
        return bytes(value)
    if family == "json":
        return json.dumps(value, ensure_ascii=False, default=str)
    if family == "vector":
        # pgvector 的文本输入格式就是 `[1,2,3]`
        return json.dumps(_as_floats(value))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        # 类型族判定之外还出现结构化值，说明列类型与内容对不上，
        # 与其发一个必然报错的字符串过去，不如在这里说清楚是哪一列。
        raise ValueError(f"标量列收到了结构化值：{value!r}")
    return str(value)


def _cast(sql_type: str, family: str) -> str:
    """给参数加 cast：`$n::text::<列类型>`（`bytea` 例外）。"""
    if family == "binary":
        return f"::{sql_type}"
    return f"::text::{sql_type}"


def redact_dsn(dsn: str) -> str:
    """去掉连接串里的口令，供写进清单（清单会跟着包一起走）。"""
    parts = urlsplit(dsn)
    if "@" not in parts.netloc:
        return dsn
    credentials, host = parts.netloc.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return urlunsplit((parts.scheme, f"{user}:***@{host}", parts.path, parts.query, parts.fragment))


# ---------------------------------------------------------------------------
# 数据库读写
# ---------------------------------------------------------------------------


async def _connect(dsn: str):
    import asyncpg

    from zhiyin_infrastructure.postgres.schema import SCHEMA_SQL

    connection = await asyncpg.connect(dsn)
    # 目标库可能还是空的：schema 由这里建，与应用启动时走的是同一份 DDL
    await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await connection.execute(SCHEMA_SQL)
    try:
        from pgvector.asyncpg import register_vector

        await register_vector(connection)
    except Exception:  # noqa: BLE001 - 没有向量表时不需要 codec
        pass
    return connection


async def _columns(connection: Any, table: str) -> list[dict[str, str]]:
    """列清单：列名 + 写进 SQL 的 cast 目标 + 类型族判定用的真实类型名。

    走 `pg_catalog` 而不是 `information_schema`：后者对 `vector` 这类扩展类型只报
    `USER-DEFINED`，拿它当 cast 目标会拼出 `::USER-DEFINED` 这种必然报错的 SQL。
    `a.atttypid::regtype` 给的是可以直接写进 SQL 的类型名（`text` / `jsonb` /
    `timestamp with time zone` / `vector`），`pg_type.typname` 给的是族判定要的
    原始类型名（`jsonb` / `vector` / `bytea`）。
    """
    rows = await connection.fetch(
        """
        SELECT a.attname AS name,
               a.atttypid::regtype::text AS sql_type,
               t.typname AS base_type
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'public' AND c.relname = $1
          AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        table,
    )
    return [
        {
            "name": row["name"],
            "type": row["sql_type"],
            "family": _family(row["base_type"]),
        }
        for row in rows
    ]


async def export(dsn: str, out: Path, tables: Iterable[str], *, redact: bool) -> dict:
    connection = await _connect(dsn)
    try:
        payload: dict[str, Any] = {
            "format_version": FORMAT_VERSION,
            "exported_at": datetime.now().astimezone().isoformat(),
            "source": redact_dsn(dsn),
            "secrets_redacted": redact,
            "tables": {},
        }
        for table in tables:
            columns = await _columns(connection, table)
            if not columns:
                print(f"  跳过 {table}：目标库里没有这张表")
                continue
            names = [column["name"] for column in columns]
            families = {column["name"]: column["family"] for column in columns}
            rows = await connection.fetch(f"SELECT {', '.join(names)} FROM {table}")
            data = [
                [encode_value(row[name], families[name]) for name in names] for row in rows
            ]
            if redact and table == "infra_ai_provider":
                index = names.index("config") if "config" in names else -1
                if index >= 0:
                    for row in data:
                        if isinstance(row[index], dict):
                            row[index] = {**row[index], "api_key": ""}
            payload["tables"][table] = {"columns": columns, "rows": data}
            print(f"  导出 {table}: {len(data)} 行")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    finally:
        await connection.close()


async def import_(dsn: str, source: Path, *, mode: str) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("format_version") != FORMAT_VERSION:
        raise SystemExit(
            f"迁移文件格式版本不匹配：文件是 {payload.get('format_version')}，"
            f"本脚本支持 {FORMAT_VERSION}"
        )
    connection = await _connect(dsn)
    try:
        summary: dict[str, int] = {}
        # 整段包在一个事务里：迁移只允许"全成"或"什么都没发生"。
        # 半途失败而留下一个删过一半的表，比迁移失败本身更难收拾。
        async with connection.transaction():
            for table, spec in payload["tables"].items():
                columns = spec["columns"]
                names = [column["name"] for column in columns]
                specs = {column["name"]: column for column in columns}
                rows = spec["rows"]

                if mode == "replace":
                    await connection.execute(f"DELETE FROM {table}")

                if rows:
                    placeholders = ", ".join(
                        f"${index + 1}{_cast(specs[name]['type'], specs[name]['family'])}"
                        for index, name in enumerate(names)
                    )
                    statement = (
                        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders}) "
                        "ON CONFLICT DO NOTHING"
                    )
                    values = [
                        tuple(
                            decode_value(value, specs[name]["family"])
                            for name, value in zip(names, row, strict=True)
                        )
                        for row in rows
                    ]
                    await connection.executemany(statement, values)
                summary[table] = len(rows)
                print(f"  导入 {table}: {len(rows)} 行")
        return summary
    finally:
        await connection.close()


async def _row_keys(connection: Any, table: str, columns: list[dict[str, str]]) -> Counter:
    """把目标库里的行按同一套编码规则取回来，用于**逐行**比对而不是只比行数。

    只比行数会漏掉最要命的一类失败：导入语句跑通了、行数也对，但某一列的内容
    是空的 —— 模型密钥就是这么丢的（`api_key` 为空时行数一点不少）。
    """
    names = [column["name"] for column in columns]
    families = {column["name"]: column["family"] for column in columns}
    rows = await connection.fetch(f"SELECT {', '.join(names)} FROM {table}")
    return Counter(
        json.dumps(
            [encode_value(row[name], families[name]) for name in names],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        for row in rows
    )


async def verify(dsn: str, source: Path) -> tuple[dict[str, int], list[str], int]:
    """核对：文件里的每一行是否都真的落进了目标库。

    返回 (各表缺失行数, 问题清单, 库里多出来的行数总计)。
    """
    payload = json.loads(source.read_text(encoding="utf-8"))
    connection = await _connect(dsn)
    try:
        missing: dict[str, int] = {}
        problems: list[str] = []
        extra_total = 0
        for table, spec in payload["tables"].items():
            columns = spec["columns"]
            names = [column["name"] for column in columns]
            families = {column["name"]: column["family"] for column in columns}
            expected = Counter(
                json.dumps(
                    [
                        encode_value(value, families[name])
                        for name, value in zip(names, row, strict=True)
                    ],
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                for row in spec["rows"]
            )
            actual = await _row_keys(connection, table, columns)

            absent = expected - actual
            extra_total += sum((actual - expected).values())
            missing[table] = sum(absent.values())
            if absent:
                problems.append(
                    f"{table}: 有 {sum(absent.values())} 行没进目标库"
                    f"（文件 {sum(expected.values())} 行 / 库 {sum(actual.values())} 行）"
                )
        return missing, problems, extra_total
    finally:
        await connection.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _selected_tables(args: argparse.Namespace) -> list[str]:
    tables = list(CONFIG_TABLES)
    if args.include_users:
        tables += list(USER_TABLES)
    if args.include_vectors:
        tables += list(VECTOR_TABLES)
    return tables


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="migrate_db", description="职引 · 数据库迁移")
    sub = parser.add_subparsers(dest="command", required=True)

    export_parser = sub.add_parser("export", help="从库里导出到 JSON")
    export_parser.add_argument("--dsn", required=True, help="源库连接串")
    export_parser.add_argument("--out", required=True, type=Path, help="输出文件")
    export_parser.add_argument("--include-users", action="store_true", help="连用户数据一起导")
    export_parser.add_argument("--include-vectors", action="store_true", help="连向量数据一起导")
    export_parser.add_argument(
        "--redact-secrets", action="store_true", help="抹掉模型密钥（分享文件时用）"
    )

    import_parser = sub.add_parser("import", help="从 JSON 导入到库")
    import_parser.add_argument("--dsn", required=True, help="目标库连接串")
    import_parser.add_argument("--in", dest="source", required=True, type=Path)
    import_parser.add_argument(
        "--mode",
        choices=("replace", "append"),
        default="replace",
        help="replace（默认）= 先清空目标表再写；append = 直接追加、冲突跳过",
    )

    verify_parser = sub.add_parser("verify", help="逐行核对目标库（不只是行数）")
    verify_parser.add_argument("--dsn", required=True)
    verify_parser.add_argument("--in", dest="source", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "export":
        tables = _selected_tables(args)
        print(f"导出 {len(tables)} 张表 → {args.out}")
        if not args.redact_secrets:
            # 这里刻意用 ASCII：Windows 控制台默认 GBK，emoji 会让 print 直接抛
            # UnicodeEncodeError —— 文件明明已经写好了，命令却以非 0 退出，
            # 用脚本串起来时会误判成"导出失败"（2026-09-22 实测踩到）。
            print(
                "注意：迁移文件里含模型密钥（infra_ai_provider.config.api_key），别把它发给外部"
            )
        payload = asyncio.run(export(args.dsn, args.out, tables, redact=args.redact_secrets))
        print(f"完成：{sum(len(t['rows']) for t in payload['tables'].values())} 行 → {args.out}")
        return 0

    if args.command == "import":
        print(f"从 {args.source} 导入（模式 {args.mode}）")
        summary = asyncio.run(import_(args.dsn, args.source, mode=args.mode))
        print(f"完成：{sum(summary.values())} 行")
        return 0

    missing, problems, extra = asyncio.run(verify(args.dsn, args.source))
    print(f"{'表':32} {'缺失行':>7}")
    print("-" * 42)
    for table, absent in sorted(missing.items()):
        print(f"{table:32} {absent:>7}{'  ← 缺' if absent else ''}")
    if extra:
        # 不是错误：目标库可能自己补种了新内容（种子文件比迁移文件新）。
        print(f"\n提示：目标库里有 {extra} 行不在迁移文件里（通常是目标环境自己补种的内容）。")
    if problems:
        print()
        print("核对未通过：")
        for line in problems:
            print(f"  - {line}")
        return 1
    print()
    print("核对通过：迁移文件里的每一行都逐字落进了目标库。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
