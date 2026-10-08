"""同一个"拿到了没"必须被三处读成同一个答案（issue #26 第三条的收尾）。

现象
----
上一轮把**采集清单**的判定改成了"看来源是否相称"
（`policies/collection.py::_counts_as_got`），但另外两处仍在按"键在不在画像里"算：

· `services/workspace.py::_coverage` —— 画像面板与气泡上的"覆盖 XX%"；
· `policies/collection_gate.py::evaluate_gate` —— 能不能走出 ① 交给主创。

同一个账号于是被说成两件事：采集清单说"还差专业（去学信网核验）"，
画像面板却显示"覆盖 100%"，门槛还按"键在"把他放行。三处都不报错，
用户看到的是自相矛盾的两句话。

这里守四件事：

1. 对话 / 行为推断来源的权威字段**不进覆盖度**（清单、面板、门槛三处一致）；
2. 相称的来源（`record` / `user_edit`）进覆盖度；
3. 非权威字段（兴趣 / 目标方向这类本来就该从对话来的）口径**一个字不变**；
4. `evaluate_gate` 的**阈值语义**没有被顺手改动 —— 用一组构造数据钉住现状
   （floor 的边界、`>=` 的边界、overall 取所有字段均值、策略缺失时的兜底）。

第 4 条尤其重要：对齐之后"覆盖"这个数字会变小，`ready` 因此可能更难达成。
那是一处**产品取舍**（阈值动不动由 Lead 定），守卫测试要保证它不是被代码顺手改掉的。

本文件不碰基线（`tests/test_source_authority.py` 的 19 条）：那 19 条守的是
采集清单本身；这里守的是**另外两个读侧与它对齐**，外加阈值没被动过。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from zhiyin_business.policies.collection import counts_as_got, rule_source_of
from zhiyin_business.policies.collection_gate import evaluate_gate
from zhiyin_business.services.workspace import DefaultWorkspaceService
from zhiyin_kernel.blackboard import Profile, ProfileField, ProfileGap
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.registry import CollectionRuleSpec

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

#: 与 `data/registry/collection_rules.json` 同一份资源。
#: "哪个字段该由谁出具"写在它里面，不是写在这份测试里 —— 它要是被人改了，
#: 下面的判定会静默失效，所以 `test_the_registry_is_the_only_source_of_authority`
#: 先把口径的源头钉住。
def _registry_rules() -> list[CollectionRuleSpec]:
    rows = json.loads(
        (DATA_DIR / "registry" / "collection_rules.json").read_text(encoding="utf-8")
    )
    return [CollectionRuleSpec(**row) for row in rows]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _field(key: str, source: ProfileSource, confidence: float = 1.0) -> ProfileField:
    return ProfileField(
        key=key,
        label=key,
        value="x",
        confidence=confidence,
        source=source,
        updated_at=_now(),
    )


def _profile(*fields: ProfileField, gaps: int = 0) -> Profile:
    return Profile(
        id="p1",
        user_id="u1",
        updated_at=_now(),
        fields=list(fields),
        gaps=[
            ProfileGap(key=f"gap{i}", label="", reason="还没定", suggested_next_action="问一句")
            for i in range(gaps)
        ],
    )


def _coverage(profile: Profile | None, rules=None) -> float:
    return DefaultWorkspaceService._coverage(profile, rules)  # noqa: SLF001 - 这里就是它的守卫


@dataclass
class _RawField:
    """从库里回来的那种字段替身：`source` 可能是字符串而不是枚举。"""

    key: str
    confidence: float
    source: object


#: 构造的策略：真实资源里那一份的形状（阈值也是真实值）。
#: 用它而不是读文件，是为了让"阈值语义"这件事在本文件里可读、可控。
_POLICY = {
    "key_fields": ["major", "interest", "target_direction", "expected_graduation"],
    "coverage_threshold": 0.5,
    "overall_confidence_threshold": 0.5,
    "gap_confidence_floor": 0.45,
}


# --------------------------------------------------------------- 口径的源头


def test_the_registry_is_the_only_source_of_authority() -> None:
    """前提：`major` / `expected_graduation` 登记的是学信网，`interest` 是对话。"""
    rules = _registry_rules()
    assert rule_source_of("major", rules) is not None
    assert rule_source_of("major", rules).value == "chsi"
    assert rule_source_of("expected_graduation", rules).value == "chsi"
    assert rule_source_of("courses", rules).value == "academic"
    assert rule_source_of("interest", rules).value == "conversation"
    # 没登记的键没有"相称来源"可谈（自由生成的字段、以及还没进登记表的新字段）。
    assert rule_source_of("target_direction", rules) is None


# --------------------------------------------------------------- 覆盖度（面板）


def test_a_chat_sourced_major_does_not_raise_coverage() -> None:
    """对话来源的专业不算覆盖：面板不再显示 100%，两条里只有兴趣算拿到。

    对齐前这里是 1.0（键在就算）；对齐后是 0.5 —— 那条没核验的专业在分母里
    仍然占一格（它是缺口），只是不进分子。
    """
    rules = _registry_rules()
    profile = _profile(
        _field("major", ProfileSource.CONVERSATION),
        _field("interest", ProfileSource.CONVERSATION),
    )
    assert _coverage(profile, rules) == 0.5


@pytest.mark.parametrize("source", [ProfileSource.RECORD, ProfileSource.USER_EDIT])
def test_a_matching_source_raises_coverage(source: ProfileSource) -> None:
    """相称的来源算覆盖：学信网核验 / 教务导入写 `record`，用户本人更正写 `user_edit`。"""
    rules = _registry_rules()
    profile = _profile(
        _field("major", source),
        _field("interest", ProfileSource.CONVERSATION),
    )
    assert _coverage(profile, rules) == 1.0


def test_behavior_inference_never_raises_coverage() -> None:
    """行为推断出来的专业同样不算：它不是出具方，哪怕听起来很确定。"""
    rules = _registry_rules()
    profile = _profile(_field("major", ProfileSource.BEHAVIOR_INFERENCE))
    assert _coverage(profile, rules) == 0.0


@pytest.mark.parametrize("source", list(ProfileSource))
def test_non_authoritative_fields_ignore_the_source(source: ProfileSource) -> None:
    """非权威字段口径不变：兴趣这种本来就该从对话来的，键在就算拿到。

    顺手把它们一起收紧会把正常动线卡死 —— 用户刚答完，面板还说这一格是空的。
    """
    rules = _registry_rules()
    assert _coverage(_profile(_field("interest", source)), rules) == 1.0


def test_an_unregistered_key_keeps_the_old_rule() -> None:
    """登记表里没有的键：没有"相称来源"可谈，键在就算拿到（与收紧前一致）。"""
    rules = _registry_rules()
    assert counts_as_got("constraints", _field("constraints", ProfileSource.CONVERSATION), rules=rules)
    assert _coverage(_profile(_field("constraints", ProfileSource.BEHAVIOR_INFERENCE)), rules) == 1.0


def test_the_denominator_still_counts_the_unverified_field() -> None:
    """分母不变：没核验的权威字段仍然占一格（它的身份就是缺口）。

    这条把"不计入覆盖度"钉在**分子**上。要是连分母也一起去掉，覆盖度会虚高：
    两条字段里专业没核验、兴趣拿到了，去掉分母就成了 100%，
    而采集清单同一屏还挂着"还差专业" —— 又是两句话打架。
    """
    rules = _registry_rules()
    profile = _profile(
        _field("major", ProfileSource.CONVERSATION),
        _field("interest", ProfileSource.CONVERSATION),
        gaps=2,
    )
    # 拿到 1 条 /（2 条字段 + 2 条缺口）= 0.25；去掉分母会算成 1/3 = 0.33。
    assert _coverage(profile, rules) == 0.25


def test_empty_profiles_are_still_zero() -> None:
    rules = _registry_rules()
    assert _coverage(None, rules) == 0.0
    assert _coverage(_profile(), rules) == 0.0


# --------------------------------------------------------------- 采集门槛


def test_the_gate_does_not_count_a_chat_sourced_key_field() -> None:
    """门槛的"覆盖"与清单同一口径：对话来源的专业不算拿到，仍在 `missing` 里。

    四条关键字段里只有"兴趣"算拿到（它本来就该从对话来），覆盖 1/4 = 0.25。
    对齐前这一份是 2/4 = 0.5，恰好越过阈值 —— 差别就是"专业"这一格的来源。
    """
    rules = _registry_rules()
    gate = evaluate_gate(
        [
            _RawField("major", 0.9, "conversation"),
            _RawField("interest", 0.9, "conversation"),
        ],
        _POLICY,
        rules=rules,
    )
    assert "major" in gate.missing
    assert gate.coverage == 0.25
    assert not gate.ready


@pytest.mark.parametrize("source", ["record", "user_edit"])
def test_the_gate_counts_a_matching_source(source: str) -> None:
    """相称的来源算拿到；字符串来源（从库里回来的形状）也要认得出来。

    覆盖 2/4 = 0.5 **恰好**等于阈值 0.5 → 放行：阈值那一条比较仍是 `>=`。
    """
    rules = _registry_rules()
    gate = evaluate_gate(
        [
            _RawField("major", 0.9, source),
            _RawField("interest", 0.9, "conversation"),
        ],
        _POLICY,
        rules=rules,
    )
    assert gate.missing == ("target_direction", "expected_graduation")
    assert gate.coverage == 0.5
    assert gate.ready, gate.line


def test_the_gate_keeps_the_old_rule_for_non_authoritative_fields() -> None:
    """兴趣这类字段：来源是什么都不影响（口径一个字没变）。"""
    rules = _registry_rules()
    for source in ProfileSource:
        gate = evaluate_gate(
            [
                _RawField("major", 0.9, "record"),
                _RawField("interest", 0.9, source.value),
                _RawField("target_direction", 0.9, source.value),
                _RawField("expected_graduation", 0.9, "record"),
            ],
            _POLICY,
            rules=rules,
        )
        assert gate.missing == (), (source, gate.line)
        assert gate.ready


def test_the_gate_falls_back_to_the_builtin_table_without_rules() -> None:
    """配置没装载时（`rules=None`）退回内置表，判定不会因此松掉。

    "读不到登记表"不能表现成"权威字段一律算拿到" —— 那等于口径取决于装载时序。
    """
    gate = evaluate_gate(
        [_RawField("major", 0.9, "conversation")], _POLICY, rules=None
    )
    assert "major" in gate.missing


def test_a_chat_only_account_can_flip_from_ready_to_not_ready() -> None:
    """对齐的**代价**，如实钉住：这是本次改动的产品影响，不是 bug。

    只聊过"我是学计算机的、2028 年毕业"的账号：对齐前关键字段覆盖 2/4 = 50% → 放行；
    对齐后这两条都要学信网核验才算，覆盖 0/4 = 0% → 留在 ①。

    阈值一个都没动（`coverage_threshold` 仍是 0.5）。这条变难是**口径**带来的：
    要不要跟着调阈值是产品决定，不由这里顺手改掉。
    """
    rules = _registry_rules()
    before_shaped = [
        _RawField("major", 0.9, "record"),
        _RawField("expected_graduation", 0.9, "record"),
    ]
    after_shaped = [
        _RawField("major", 0.9, "conversation"),
        _RawField("expected_graduation", 0.9, "conversation"),
    ]
    assert evaluate_gate(before_shaped, _POLICY, rules=rules).ready
    flipped = evaluate_gate(after_shaped, _POLICY, rules=rules)
    assert not flipped.ready
    assert set(flipped.missing) == {"major", "expected_graduation", "interest", "target_direction"}
    # 把握度这一维没变：两条都过 floor，翻掉的是覆盖。
    assert flipped.overall == pytest.approx(0.9)


# --------------------------------------------------------------- 阈值语义没动


def test_the_confidence_floor_boundary_is_unchanged() -> None:
    """`gap_confidence_floor` 的边界：恰好等于 floor 算拿到，低一分就不算。

    这里把整体把握阈值一起压低，是为了让"翻不翻"只由 floor 决定 ——
    否则 0.45 的把握会先被 overall 那道门槛拦下，测不到 floor 本身。
    """
    rules = _registry_rules()
    policy = {
        **_POLICY,
        "key_fields": ["interest"],
        "coverage_threshold": 0.5,
        "overall_confidence_threshold": 0.4,
    }

    at_floor = evaluate_gate([_RawField("interest", 0.45, "conversation")], policy, rules=rules)
    assert at_floor.missing == ()
    assert at_floor.ready

    below = evaluate_gate([_RawField("interest", 0.44, "conversation")], policy, rules=rules)
    assert below.missing == ("interest",)
    assert not below.ready


def test_both_thresholds_are_still_required_and_inclusive() -> None:
    """两个阈值仍是"都要过、都取 `>=`"：覆盖够了但把握差一点同样不放行。"""
    rules = _registry_rules()
    policy = {**_POLICY, "key_fields": ["interest", "target_direction"]}

    # 覆盖 1.0、把握恰好 0.5 → 放行。
    ready = evaluate_gate(
        [
            _RawField("interest", 0.5, "conversation"),
            _RawField("target_direction", 0.5, "conversation"),
        ],
        policy,
        rules=rules,
    )
    assert ready.coverage == 1.0
    assert ready.ready

    # 同样的覆盖，把握 0.49 → 不放行（阈值一个都没动）。
    not_ready = evaluate_gate(
        [
            _RawField("interest", 0.49, "conversation"),
            _RawField("target_direction", 0.49, "conversation"),
        ],
        policy,
        rules=rules,
    )
    assert not_ready.coverage == 1.0
    assert not not_ready.ready


def test_overall_is_still_the_mean_over_every_field() -> None:
    """`overall` 的计算没变：所有字段把握度的均值（含非关键字段）。

    非关键字段拉低均值是原有行为 —— 改它属于另一件事，不该混在这次对齐里。
    """
    rules = _registry_rules()
    policy = {**_POLICY, "key_fields": ["interest"]}
    gate = evaluate_gate(
        [
            _RawField("interest", 0.8, "conversation"),
            _RawField("constraints", 0.2, "conversation"),
        ],
        policy,
        rules=rules,
    )
    assert gate.coverage == 1.0
    assert gate.overall == pytest.approx(0.5)
    assert gate.ready  # 0.5 >= 0.5：均值边界仍取 `>=`


def test_a_missing_policy_still_falls_back_instead_of_passing_everyone() -> None:
    """策略读不到：仍用兜底清单（松），但**不能一律放行**。"""
    assert not evaluate_gate([], None).ready
    assert evaluate_gate(
        [
            _RawField("major", 0.9, "record"),
            _RawField("interest", 0.9, "conversation"),
            _RawField("target_direction", 0.9, "conversation"),
        ],
        None,
    ).ready


# --------------------------------------------------------------- 三处一致


def test_three_readers_give_the_same_answer_for_one_field() -> None:
    """同一格画像：清单、面板、门槛三处必须说同一句话。

    这是本次收尾要买的东西。只要有一处还在按"键在"算，
    另外两处的改动就白做 —— 用户仍然会看到"覆盖 100%"和"还差专业"并排。
    """
    rules = _registry_rules()
    key = "major"

    inferred = _field(key, ProfileSource.CONVERSATION)
    assert counts_as_got(key, inferred, rules=rules) is False
    assert _coverage(_profile(inferred), rules) == 0.0
    assert key in evaluate_gate([inferred], _POLICY, rules=rules).missing

    verified = _field(key, ProfileSource.RECORD)
    assert counts_as_got(key, verified, rules=rules) is True
    assert _coverage(_profile(verified), rules) == 1.0
    assert key not in evaluate_gate([verified], _POLICY, rules=rules).missing
