"""旧画像字段别名迁移的纯函数测试（P28）。

迁移脚本本身跑真实库；这里锁住“哪些旧键有规范目标、何时创建/合并/记为冲突”，
避免以后把旧“目标”自动提升成已选，或把不同值静默合并。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1]
SCRIPT = TEMPLATE / "scripts" / "migrate_profile_aliases.py"


def _module():
    spec = importlib.util.spec_from_file_location("_alias_migration_for_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(user_id: str, key: str, value, **extra):
    return {
        "user_id": user_id,
        "key": key,
        "label": "",
        "value": value,
        "confidence": 0.8,
        "source": "conversation",
        "evidence": [],
        "updated_at": None,
        "entry_type": None,
        "attributes": {},
        "verification": None,
        "status": "active",
        "origin_ref": "",
        "valid_from": None,
        "valid_to": None,
        "event_at": None,
        "entry_version": 1,
        "superseded_by": "",
        **extra,
    }


def test_known_aliases_only():
    module = _module()
    assert module.target_for("career_goal") == ("target_direction", {"state": "exploring"})
    assert module.target_for("preferred_city") == ("city", {})
    assert module.target_for("personality") is None
    assert module.target_for("motivation") is None


def test_alias_creates_target_and_keeps_goal_as_exploring():
    module = _module()
    plans = module.plan_rows([_row("u1", "career_goal", "算法工程师")])
    assert len(plans) == 1
    plan = plans[0]
    assert plan["action"] == "create"
    assert plan["target_key"] == "target_direction"
    # 旧“目标”不能自动成为已选方向。
    assert plan["attributes"]["state"] == "exploring"


def test_same_value_merges_instead_of_adding_a_record():
    module = _module()
    plans = module.plan_rows([
        _row("u1", "strengths", ["沟通"]),
        _row("u1", "skills", ["沟通"]),
    ])
    assert [plan["action"] for plan in plans] == ["merge_same"]


def test_different_value_is_kept_as_conflict_proposal():
    module = _module()
    plans = module.plan_rows([
        _row("u1", "strengths", ["沟通"]),
        _row("u1", "skills", ["编程"]),
    ])
    assert [plan["action"] for plan in plans] == ["conflict"]
    # 当前值不被旧键覆盖。
    assert plans[0]["current"]["value"] == ["编程"]
    assert plans[0]["row"]["value"] == ["沟通"]


def test_summary_counts_actions_and_unknown_keys_are_ignored():
    module = _module()
    plans = module.plan_rows([
        _row("u1", "career_goal", "产品经理"),
        _row("u1", "personality", "内向"),
        _row("u2", "constraint", "家里希望稳定"),
        _row("u2", "constraints", "家里希望稳定"),
    ])
    assert len(plans) == 2
    assert module.summarize(plans) == {"create": 1, "merge_same": 1}
