"""采集门槛：什么时候算"采够了"。

这条策略以前**没有任何代码读**（`policy_params.profile_collection` 躺着三行参数），
于是"够不够"由模型自由心证 —— 真实用户遇到的就是：他只想聊两句，
系统一条接一条地问下去，问到人走了。

这里守四件事：

1. 关键字段覆盖够、整体把握够 → 放行；
2. 少一条关键字段 → 不放行，且**说得清还差哪条**；
3. 字段都在、但把握太低（全是猜的）→ 同样不放行；
4. 策略读不到 → 用兜底（松但不放空），而不是"一律放行"跳过整个采集环节。
"""

from __future__ import annotations

from dataclasses import dataclass

from zhiyin_business.policies.collection_gate import evaluate_gate


@dataclass
class _Field:
    key: str
    confidence: float


POLICY = {
    "key_fields": ["major", "interest", "target_direction", "expected_graduation"],
    "coverage_threshold": 0.5,
    "overall_confidence_threshold": 0.5,
    "gap_confidence_floor": 0.45,
}


def test_ready_when_coverage_and_confidence_pass() -> None:
    gate = evaluate_gate(
        [_Field("major", 0.9), _Field("interest", 0.8)], POLICY
    )
    assert gate.ready, gate.line
    assert gate.coverage == 0.5
    assert gate.missing == ("target_direction", "expected_graduation")


def test_not_ready_when_a_key_field_is_missing() -> None:
    gate = evaluate_gate([_Field("major", 0.9)], POLICY)
    assert not gate.ready
    assert "interest" in gate.missing


def test_low_confidence_does_not_count_as_having_it() -> None:
    """字段在、但把握低于底线＝还没拿到：不然模型随手写一条就能"过关"。"""
    gate = evaluate_gate(
        [_Field("major", 0.2), _Field("interest", 0.2), _Field("target_direction", 0.2)],
        POLICY,
    )
    assert not gate.ready
    # 三条低把握的字段都不算"拿到了"，加上那条压根没写的，四条全在缺口里
    assert set(gate.missing) == {
        "major", "interest", "target_direction", "expected_graduation",
    }


def test_missing_policy_falls_back_but_still_requires_something() -> None:
    """策略读不到时：用兜底清单（松），但**不能一律放行** ——

    "一律放行"等于配置缺失直接表现为"跳过整个采集环节"，那比卡住人更坏：
    用户会在什么都没有的情况下被推进分析。
    """
    empty = evaluate_gate([], None)
    assert not empty.ready
    assert empty.missing  # 兜底清单里仍有关键字段

    enough = evaluate_gate(
        [_Field("major", 0.9), _Field("interest", 0.9)], None
    )
    assert enough.ready
