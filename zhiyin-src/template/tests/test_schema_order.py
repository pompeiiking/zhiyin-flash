"""建表顺序守卫：整份 `SCHEMA_SQL` 必须能在**一片空白的数据库**上从头跑通。

为什么值得守
------------
`SCHEMA_SQL` 是四段 DDL 按 `infra → business → orchestration → vector` 拼起来的
（见 `postgres/schema/__init__.py`），应用启动与 `scripts/migrate_db.py` 都把它
**整段丢给数据库执行一次**。于是段与段之间存在一条隐含约束：

    任何 ALTER / DELETE / INSERT / UPDATE / 建索引 / 外键 引用到的表，
    都必须在**它前面**已经被 CREATE 出来。

这条约束在**已经有表的库**上完全看不出来 —— 表早就在了，语句怎么写都能跑。
它只在空库上暴露，而空库恰好是"新环境部署"的默认起点。

本次实测到一次：`DELETE FROM biz_registry_item ...`（收敛早期误收容进通用表的
`prompts` / `routing_rules` 两类）原先写在 **infra 段**，而 `biz_registry_item`
是 **business 段**建的。在已有库上一路平安；换成空库启动，第一句建表就中断：

    asyncpg.exceptions.UndefinedTableError: relation "biz_registry_item" does not exist

也就是**服务在空库上根本起不来**。而仓库里所有测试与 CI 走的都是内存实现
（不连库），所以没有任何一条会红 —— 这类"只在部署时才炸"的顺序错误必须由
静态顺序校验挡住，不能靠人记得。

本文件因此不连数据库，只做机械可判的一件事：按拼接后的真实顺序扫一遍语句，
记下每张表出现的时刻，再检查后续语句引用的表是否已经建过。
"""

from __future__ import annotations

import re

# 建表：出现之后，这张表就可以被后面的语句引用
_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)")

# 「引用一张应该已经存在的表」的六种写法。刻意逐条列出而不是用宽泛的
# `ON \w+` —— 后者会撞上 CREATE TABLE 里的 `ON DELETE CASCADE`。
_REFERENCES: tuple[re.Pattern[str], ...] = (
    re.compile(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS \w+\s+ON\s+(\w+)"),
    re.compile(r"ALTER TABLE (\w+)"),
    re.compile(r"DELETE FROM (\w+)"),
    re.compile(r"INSERT INTO (\w+)"),
    re.compile(r"UPDATE (\w+) SET"),
    re.compile(r"REFERENCES (\w+)\s*\("),
)


def _statements(sql: str) -> list[str]:
    """按真实执行顺序切出语句。

    先去掉 `--` 行注释（库里只有整行注释与行尾注释，没有把 `--` 写进字符串字面量
    的地方），再按 `;` 切开、丢掉纯注释留下的空段 —— 与应用交给数据库的那一段
    完全一致，注释不该影响判断。
    """
    without_comments = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return [chunk.strip() for chunk in without_comments.split(";") if chunk.strip()]


def test_every_referenced_table_is_created_first() -> None:
    """SCHEMA_SQL 里不允许出现"先引用、后创建"。"""
    from zhiyin_infrastructure.postgres.schema import SCHEMA_SQL

    created: set[str] = set()
    problems: list[str] = []

    for index, statement in enumerate(_statements(SCHEMA_SQL), start=1):
        flat = " ".join(statement.split())

        for pattern in _REFERENCES:
            for name in pattern.findall(flat):
                if name not in created:
                    problems.append(
                        f"第 {index} 条语句引用了还没建的表 `{name}`：{flat[:90]}…"
                    )

        # 引用检查放在建表登记之前：CREATE TABLE 里的 REFERENCES 指向的是别人，
        # 不能因为"自己这条语句会建表"就被放行。
        match = _CREATE.search(flat)
        if match:
            created.add(match.group(1))

    assert not problems, (
        "SCHEMA_SQL 在空库上会中断 —— 以下语句引用了比它更晚才创建的表：\n  - "
        + "\n  - ".join(problems)
        + "\n\n修法只有两种：把这条语句挪到建表之后（按段落归属选对文件），"
        "或者删掉它。改完请对着一个**空库**真跑一次建表。"
    )


def test_schema_sql_creates_the_whole_catalog() -> None:
    """顺带钉住"每张声明的表都真的被建出来"，防止上面的扫描被写空后静默通过。"""
    from zhiyin_infrastructure.postgres.schema import SCHEMA_SQL

    created = [name for name in _CREATE.findall(SCHEMA_SQL)]
    assert len(created) >= 25, f"SCHEMA_SQL 里的建表语句只剩 {len(created)} 条，疑似被截断"
    duplicates = sorted({name for name in created if created.count(name) > 1})
    assert not duplicates, f"同一张表被建了两次：{duplicates}"
