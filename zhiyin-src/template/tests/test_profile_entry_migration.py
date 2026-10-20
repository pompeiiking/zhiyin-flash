"""旧画像字段迁移的纯函数回归（《个人画像设计-2026-10-20》第 10 节、P28）。

迁移脚本连不连得上 PostgreSQL 由环境决定，但“一行该回填成什么”必须是纯函数：
类别按受控词表、核实状态按来源、已有合法值不覆盖、重复执行 0 差异。这里只测
这一层，不测数据库连接。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "migrate_profile_entries", ROOT / "scripts/migrate_profile_entries.py"
)
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


def _row(key: str, source: str = "conversation", **overrides) -> dict:
    row = {
        "user_id": "u-migrate",
        "key": key,
        "source": source,
        "entry_type": None,
        "verification": None,
        "status": None,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# 已知键 / 未知键：类别由词表决定，未知键落到“补充信息”
# ---------------------------------------------------------------------------


def test_known_keys_use_the_controlled_vocabulary() -> None:
    assert module.desired_backfill("major", "record")["entry_type"] == "learning_background"
    assert module.desired_backfill("interest", "conversation")["entry_type"] == "interest"
    assert module.desired_backfill("experience", "conversation")["entry_type"] == "experience"
    assert module.desired_backfill("target_job", "conversation")["entry_type"] == "career_focus"
    assert module.desired_backfill("time", "conversation")["entry_type"] == "condition"


def test_unknown_and_supplement_keys_are_not_promoted_to_interest() -> None:
    # 认不出的历史键宁可待归类（补充信息），也不猜成兴趣或职业目标。
    assert module.desired_backfill("some_legacy_key", "conversation")["entry_type"] == "supplement"
    assert module.desired_backfill("supplement", "conversation")["entry_type"] == "supplement"
    assert module.desired_backfill("supplement_info", "conversation")["entry_type"] == "supplement"


def test_blank_key_is_supplement_not_a_business_category() -> None:
    assert module.desired_backfill("", "conversation")["entry_type"] == "supplement"


# ---------------------------------------------------------------------------
# 来源 → 核实状态
# ---------------------------------------------------------------------------


def test_source_maps_to_default_verification() -> None:
    assert module.desired_backfill("major", "conversation")["verification"] == "self_reported"
    assert module.desired_backfill("major", "user_edit")["verification"] == "user_confirmed"
    assert module.desired_backfill("major", "record")["verification"] == "record"
    assert module.desired_backfill("major", "resume")["verification"] == "record"
    assert module.desired_backfill("major", "assessment")["verification"] == "pending"
    # 认不出的来源是“待核对”，不伪称已核验。
    assert module.desired_backfill("major", "mystery")["verification"] == "pending"
    assert module.desired_backfill("major", "")["verification"] == "pending"


def test_backfill_status_is_active_and_values_are_plain_strings() -> None:
    desired = module.desired_backfill("major", "conversation")
    assert desired == {
        "entry_type": "learning_background",
        "verification": "self_reported",
        "status": "active",
    }
    assert all(isinstance(value, str) for value in desired.values())


# ---------------------------------------------------------------------------
# 行 → 差异：空值回填、合法值保留、幂等
# ---------------------------------------------------------------------------


def test_empty_row_gets_all_three_columns() -> None:
    diff = module.plan_backfill(_row("major", "conversation"))
    assert diff == {
        "entry_type": "learning_background",
        "verification": "self_reported",
        "status": "active",
    }


def test_already_valid_row_has_no_diff() -> None:
    row = _row(
        "major",
        "conversation",
        entry_type="learning_background",
        verification="self_reported",
        status="active",
    )
    assert module.plan_backfill(row) is None


def test_only_missing_columns_are_filled_and_valid_values_are_kept() -> None:
    # 类别已经人工核对过（哪怕不是词表默认值）就不覆盖；只补空着的核实状态。
    row = _row(
        "major",
        "conversation",
        entry_type="supplement",
        verification="",
        status="active",
    )
    assert module.plan_backfill(row) == {"verification": "self_reported"}


def test_invalid_status_falls_back_to_active() -> None:
    row = _row(
        "major",
        "conversation",
        entry_type="learning_background",
        verification="self_reported",
        status="deleted",
    )
    assert module.plan_backfill(row) == {"status": "active"}


def test_invalid_enum_values_are_repaired_from_the_vocabulary() -> None:
    row = _row(
        "interest",
        "user_edit",
        entry_type="unknown",
        verification="guessed",
        status="active",
    )
    assert module.plan_backfill(row) == {
        "entry_type": "interest",
        "verification": "user_confirmed",
    }


def test_plan_rows_filters_out_clean_rows_and_counts_by_column() -> None:
    rows = [
        _row("major", "conversation"),
        _row(
            "interest",
            "user_edit",
            entry_type="interest",
            verification="user_confirmed",
            status="active",
        ),
        _row("legacy_key", "record"),
    ]
    plans = module.plan_rows(rows)
    assert len(plans) == 2
    summary = module.summarize(plans)
    assert summary["entry_type"]["learning_background"] == 1
    assert summary["entry_type"]["supplement"] == 1
    assert summary["verification"]["self_reported"] == 1
    assert summary["verification"]["record"] == 1
    assert summary["status"]["active"] == 2


def test_second_run_after_apply_has_zero_differences() -> None:
    """迁移可重复执行：把差异合并回行之后，再算一次必须为空。"""
    rows = [
        _row("major", "conversation"),
        _row(
            "legacy_key",
            "record",
            entry_type="supplement",
            verification="record",
            status="active",
        ),
    ]
    first = module.plan_rows(rows)
    assert len(first) == 1
    applied = [({**row, **diff}) for row, diff in module.plan_rows(rows)]
    assert module.plan_rows(applied) == []


def test_cli_defaults_to_dry_run_and_rejects_conflicting_flags() -> None:
    with pytest.raises(SystemExit) as caught:
        module.main(["--help"])
    assert caught.value.code == 0

    with pytest.raises(SystemExit) as caught:
        module.main(["--dsn", "postgresql://example/zhiyin", "--apply", "--dry-run"])
    assert caught.value.code == 2
