"""表结构增量：`SCHEMA_SQL` 之外的那些"只增"改动。

为什么需要这一层
----------------
`SCHEMA_SQL` 全是 `CREATE TABLE IF NOT EXISTS` —— 它能让**空库**长成当前形状，
但改不动**老库**：表已经存在时整段建表语句是空操作，后来代码里新加的列不会出现。

2026-09-22 的实际后果：`biz_calendar_node` 少了 `related_task_text` 一列，
应用启动直接 `UndefinedColumnError` 崩掉；当时唯一的出路是把整个数据卷删掉重导
（数据能回来，但那不是"改表结构"，是"丢掉重来"）。

规矩（三条，都很硬）
--------------------
1. **只增不减**：只加列、加索引；不改类型、不删列、不重命名 ——
   那三种都会让回滚变成数据丢失，而回滚恰恰是最需要它安全的时候。
2. **一律 `IF NOT EXISTS`**：空库与老库跑的是同一段 SQL，重复执行无副作用。
   因此它被拼在 `SCHEMA_SQL` 末尾（先建表、后补列），启动与迁移导入两条路径
   都会执行到，不需要各自记得调一次。
3. **每条都写清楚来由**：哪次改动加的、为什么必须加。这一层是"历史补丁"，
   没有注明来由的补丁，后来的人不敢删也不敢动。

新增一条时，同时在 `tests/test_schema_migration.py` 的期望里加一行说明。
"""

from __future__ import annotations

MIGRATION_SQL = "\n".join(
    [
        # 2026-09-22 —— 行动环节排期要能回指"这件事对应哪条待办原文"，
        # 课表节点因此多了一列。老库建于它之前，缺列会让应用起不来。
        "ALTER TABLE biz_calendar_node "
        "ADD COLUMN IF NOT EXISTS related_task_text TEXT NOT NULL DEFAULT '';",
        # 2026-09-22 —— 画像里直接显示英文字段键（`interest_direction`）：
        # 字段键是模型自己起的，界面没有中文名只能把键摆出来。名字必须跟着数据存，
        # 所以这两个字段各加一列；老库里已有的是空串，界面回落到动态资源里的对照表。
        "ALTER TABLE biz_profile_field "
        "ADD COLUMN IF NOT EXISTS label TEXT NOT NULL DEFAULT '';",
        "ALTER TABLE biz_profile_gap "
        "ADD COLUMN IF NOT EXISTS label TEXT NOT NULL DEFAULT '';",
    ]
)

__all__ = ["MIGRATION_SQL"]
