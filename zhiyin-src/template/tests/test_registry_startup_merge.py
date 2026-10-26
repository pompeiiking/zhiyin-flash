"""启动期注册表合并的守卫（2026-10-24 复盘 issue #44 / #43）。

背景：词表类别（collection_rules / copies）只在该类别为空时种子，旧库永远
缺代码新增的字段键 —— 「你现在大几」被"画像里没有这一格"拒掉、职业关注
静默丢失。`ensure_entries` 在启动时按条目补缺（只插缺失键，不动已有内容）；
`conversation.*` 产品提示词则每次启动按文件刷新（提取契约写在提示词里，
旧行会让否定项静默变成普通兴趣）。

这两条都用假数据库驱动真实仓储代码，不需要真实 PostgreSQL。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from zhiyin_infrastructure.postgres.registry import PostgresRegistryRepository
from zhiyin_infrastructure.postgres.feature_flag import (
    SEED_VERSION_KEY,
    PostgresFeatureFlagGateway,
)

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = TEMPLATE_ROOT / "data" / "registry"


class _FakeDatabase:
    """记录 execute 的最小假库：fetch/fetchval 按调用方注入的脚本回答。"""

    def __init__(self, *, fetchval_results=None):
        self.statements: list[tuple[str, tuple]] = []
        self._fetchval_results = list(fetchval_results or [])

    async def execute(self, query, *args):
        self.statements.append((query, args))
        return "INSERT 0 1" if "INSERT INTO" in query else "UPDATE 0"

    async def fetchval(self, query, *args):
        return self._fetchval_results.pop(0) if self._fetchval_results else 0

    async def fetch(self, query, *args):
        return []

    async def fetchrow(self, query, *args):
        return None


def test_ensure_entries_inserts_missing_field_vocabulary():
    """词表文件里的每个键都要有一条 INSERT … ON CONFLICT DO NOTHING。"""

    async def run():
        database = _FakeDatabase()
        repository = PostgresRegistryRepository(database, str(REGISTRY_DIR))
        inserted = await repository.ensure_entries(("collection_rules", "copies"))
        statements = [(query, args) for query, args in database.statements
                      if "INSERT INTO biz_registry_item" in query]
        by_kind: dict[str, set[str]] = {}
        for _query, args in statements:
            by_kind.setdefault(args[0], set()).add(args[1])
        return inserted, by_kind, statements

    inserted, by_kind, statements = asyncio.run(run())
    # 采集清单 15 项（含新加的 study_year），词表 28 键（含 4 个新字段）。
    assert "study_year" in by_kind["collection_rules"]
    assert {"profile.field.study_year", "profile.field.career_focus",
            "profile.field.supplement_info", "profile.field.time"} <= by_kind["copies"]
    # 只插缺失：每条都是 DO NOTHING，没有任何 UPDATE 或 DELETE。
    assert all("ON CONFLICT (kind, code) DO NOTHING" in query for query, _ in statements)
    assert len(inserted) == len(statements)


def test_conversation_memory_prompt_is_refreshed_from_file_on_startup():
    """conversation.memory 承载语义提取契约（极性/否定/字段词表）：
    启动时按文件 upsert；其余 conversation.* 仍只补缺、不覆盖。"""

    async def run():
        # 类别已有内容（fetchval 返回 >0）→ 走"已有类别的产品提示词刷新"分支。
        database = _FakeDatabase(fetchval_results=[24])
        repository = PostgresRegistryRepository(database, str(REGISTRY_DIR))
        await repository._ensure_ai_seeded()
        return [(query, args) for query, args in database.statements
                if "INSERT INTO ai_prompt_template" in query]

    statements = asyncio.run(run())
    upserts = {args[0] for query, args in statements if "DO UPDATE" in query}
    untouched = {args[0] for query, args in statements if "DO NOTHING" in query}
    assert "conversation.memory" in upserts, "提取契约必须随文件刷新"
    assert not (upserts - {"conversation.memory"}), "其余提示词不得被启动覆盖"
    # 允许管理员维护的产品提示词与角色提示词仍是"只补缺、不覆盖"。
    assert {"task.academic.analysis", "disclosure.field_kept_by_user",
            "conversation.main"} <= untouched


def test_structural_kinds_constant_is_wired():
    """启动合并只声明在 registry_bootstrap 一处，且类别正确。"""
    from zhiyin_boot.registry_bootstrap import STRUCTURAL_REGISTRY_KINDS

    assert set(STRUCTURAL_REGISTRY_KINDS) == {"collection_rules", "copies"}


class _FlagDatabase:
    """功能开关网关的假库：按 SQL 形状回答版本与行数。"""

    def __init__(self, *, applied=None, count=0):
        self.applied = applied
        self.count = count
        self.statements: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        self.statements.append((query, args))
        return "INSERT 0 1"

    async def fetchval(self, query, *args):
        if "value->>'version'" in query:
            return self.applied
        if "COUNT(*)" in query:
            return self.count
        return 0

    async def fetch(self, query, *args):
        return []


def _flags_seed(tmp_path: Path, version: int, export: bool) -> Path:
    (tmp_path / "feature_flags.json").write_text(json.dumps({
        "_version": version,
        "items": [{"code": "export", "enabled": export}],
    }), encoding="utf-8")
    return tmp_path


def test_seed_version_upgrade_enables_a_product_default_once():
    """库里的版本落后时按文件重导一次；导完记下版本，之后以库为准。"""

    async def run():
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = _flags_seed(Path(directory), 2, True)
            database = _FlagDatabase(applied="1", count=1)
            gateway = PostgresFeatureFlagGateway(database, str(root))
            await gateway.all()
            return database.statements

    statements = asyncio.run(run())
    flag_upserts = [(query, args) for query, args in statements
                    if "INSERT INTO infra_feature_flag" in query]
    assert flag_upserts and "DO UPDATE SET enabled" in flag_upserts[0][0]
    assert ("export", True) in [args for _query, args in flag_upserts]
    version_writes = [(query, args) for query, args in statements
                      if "infra_runtime_config" in query]
    assert version_writes and json.loads(version_writes[0][1][1]) == {"version": 2}
    assert version_writes[0][1][0] == SEED_VERSION_KEY


def test_same_seed_version_does_not_overwrite_operator_changes():
    """版本相同就不动已有开关 —— 运维在库里关掉的不能被重启重新打开。"""

    async def run():
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = _flags_seed(Path(directory), 2, True)
            database = _FlagDatabase(applied="2", count=1)
            gateway = PostgresFeatureFlagGateway(database, str(root))
            await gateway.all()
            return database.statements

    statements = asyncio.run(run())
    assert not [item for item in statements if "infra_feature_flag" in item[0]]


def test_empty_flag_table_gets_the_seed_and_remembers_its_version():
    async def run():
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = _flags_seed(Path(directory), 2, True)
            database = _FlagDatabase(applied=None, count=0)
            gateway = PostgresFeatureFlagGateway(database, str(root))
            await gateway.all()
            return database.statements

    statements = asyncio.run(run())
    inserts = [args for query, args in statements if "INSERT INTO infra_feature_flag" in query]
    assert ("export", True) in inserts
    assert any("infra_runtime_config" in query for query, _args in statements)
