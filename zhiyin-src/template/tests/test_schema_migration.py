"""表结构增量守卫：补丁层必须"可重复、只增、指向真表"。

为什么单独守它
--------------
`SCHEMA_SQL` 里的建表语句只对**空库**有效（`CREATE TABLE IF NOT EXISTS`），
老库要靠 `MIGRATION_SQL` 补列 —— 那一层一旦写错，代价是**部署时才发现应用起不来**，
而那时现场已经是一个正在服务的数据库，改错的成本远高于改代码。

这里守三件机械可判的事：

1. 每条补丁都是 `ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`
   （幂等，且不会把"回滚"变成丢数据）；
2. 补丁指向的表必须在 `SCHEMA_SQL` 里真的存在（防拼错表名 —— 拼错了只会在
   部署时报 `relation does not exist`）；
3. 补丁拼在 `SCHEMA_SQL` **最后**（先建表、后补列；顺序反了，空库上会直接失败）。

它不检查"代码里新加的列有没有人来补"—— 那需要拿到真实库结构，属于部署期检查
（`/healthz` 与迁移导入都会执行整份 DDL，缺列会在那里立刻报出来）。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from zhiyin_infrastructure.postgres.schema import MIGRATION_SQL, SCHEMA_SQL

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]

_ADD_COLUMN = re.compile(
    r"^ALTER TABLE (?P<table>\w+)\s+ADD COLUMN IF NOT EXISTS (?P<column>\w+)\s", re.I
)
_CREATE_INDEX = re.compile(r"^CREATE INDEX IF NOT EXISTS \w+\s+ON (?P<table>\w+)", re.I)


def _statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def test_migration_sql_is_idempotent_and_additive() -> None:
    """每条补丁都必须是幂等的"只增"语句。"""
    statements = _statements(MIGRATION_SQL)
    assert statements, "MIGRATION_SQL 是空的——这层守卫会变成空跑"

    for statement in statements:
        if _ADD_COLUMN.match(statement) or _CREATE_INDEX.match(statement):
            continue
        raise AssertionError(
            "MIGRATION_SQL 里出现了非增量语句：\n  "
            f"{statement}\n"
            "只允许 `ALTER TABLE … ADD COLUMN IF NOT EXISTS` 与 "
            "`CREATE INDEX IF NOT EXISTS`；改类型 / 删列 / 重命名会让回滚变成丢数据。"
        )


def test_migration_targets_exist_in_schema() -> None:
    """补丁指向的表必须真的存在于 SCHEMA_SQL。"""
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA_SQL))
    referenced: set[str] = set()
    for statement in _statements(MIGRATION_SQL):
        match = _ADD_COLUMN.match(statement) or _CREATE_INDEX.match(statement)
        assert match is not None  # 上一条用例已经保证
        referenced.add(match.group("table"))

    unknown = sorted(referenced - declared)
    assert not unknown, (
        f"MIGRATION_SQL 指向了 SCHEMA_SQL 里没有的表：{unknown}。"
        "表名拼错在部署时才会报 relation does not exist。"
    )


def test_migrations_run_after_every_create_table() -> None:
    """补丁必须拼在 SCHEMA_SQL 的最后：空库上是"先建表、后补列"。"""
    last_create = SCHEMA_SQL.rfind("CREATE TABLE IF NOT EXISTS")
    first_migration = SCHEMA_SQL.find(_statements(MIGRATION_SQL)[0])
    assert last_create != -1 and first_migration != -1
    assert first_migration > last_create, (
        "MIGRATION_SQL 被拼在建表语句之前了 —— 空库上补丁会先于建表执行，直接失败。"
    )


def test_known_backfill_column_is_declared() -> None:
    """记一笔真实踩过的坑：`biz_calendar_node.related_task_text` 必须在补丁里。

    2026-09-22 部署时就是少了它，应用启动即 UndefinedColumn，只能删卷重导。
    谁把这条补丁删掉，这条用例会拦住 —— 老库会再次起不来。
    """
    assert "related_task_text" in MIGRATION_SQL or "related_task_text" in SCHEMA_SQL
    assert re.search(
        r"ALTER TABLE biz_calendar_node\s+ADD COLUMN IF NOT EXISTS related_task_text",
        MIGRATION_SQL,
    ), "biz_calendar_node.related_task_text 的补丁不见了：老库会再次因为缺列起不来。"


def _migration_script():
    """把 `scripts/migrate_db.py` 当模块载进来（它不是包，import 不进来）。"""
    path = TEMPLATE_ROOT / "scripts" / "migrate_db.py"
    spec = importlib.util.spec_from_file_location("_migrate_db_for_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_table_is_registered_for_migration() -> None:
    """建出来的每一张表都必须登记去留：迁移、或写明为什么不迁。

    这是 2026-09-22 真实踩过的坑：`biz_conversation_turn`（会话逐轮原文）
    是新表，但没进 `USER_TABLES` —— 于是"整机搬家"时它**静默丢掉**，
    界面上表现为"这条会话没有逐轮原文"，而迁移脚本一路成功、没有任何提示。

    判据是"每张表都在某一张清单里"，不是"这张表重不重要"：
    不迁的表也必须写一句为什么（`SKIPPED`），否则下一次加表还是会漏。
    """
    script = _migration_script()
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA_SQL))
    registered = (
        set(script.CONFIG_TABLES)
        | set(script.USER_TABLES)
        | set(script.VECTOR_TABLES)
        | set(script.SKIPPED)
    )

    missing = sorted(declared - registered)
    assert not missing, (
        f"这些表没有登记迁移去留：{missing}。"
        "请加进 CONFIG_TABLES / USER_TABLES / VECTOR_TABLES，"
        "或在 SKIPPED 里写明为什么不迁 —— 不登记的代价是搬家时静默丢数据。"
    )

    stale = sorted(registered - declared)
    assert not stale, (
        f"这些表已经不在 SCHEMA_SQL 里，迁移清单还留着：{stale}。"
        "删表时请同步删除清单条目，否则导入会在部署期报 relation does not exist。"
    )
