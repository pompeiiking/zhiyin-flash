"""KEV 采用策略：分意图阈值、top1/top2 间距、阶段先验（实测 ZY-01）。

原本的问题：五个核心自然表达的第一候选全部正确，但**一个都没被采用** ——
固定的 0.55 / 0.70 双阈值把它们全挡掉了，业务跳转于是主要靠关键词。

报告的建议是"用人工标注集做概率校准，不要凭单轮样例直接降阈值"。
所以这里修的是**机制**，不是数值：把门槛变成可配置的，并让每条回退都留下原因 ——
校准于是变成改配置 + 看日志分布，而不是改代码、更不是拍脑袋。

默认（不配置任何新键）行为与原来完全一致。
"""

from __future__ import annotations

from zhiyin_business.policies.decision_routing import DecisionRoutingConfig


def test_defaults_keep_the_original_semantics() -> None:
    config = DecisionRoutingConfig(
        mode="active",
        confidence_threshold=0.55,
        probability_threshold=0.70,
        max_message_chars=6000,
        instructions="classify",
        criteria={
            "confused": "x", "verify_direction": "x", "undecided": "x", "how_to_act": "x",
            "stuck": "x", "review_due": "x", "free_chat": "x", "unclear": "x",
        },
    )
    assert config.confidence_thresholds == {}
    assert config.probability_thresholds == {}
    assert config.top2_margin == 0.0
    assert config.stage_prior == {}
    assert config.stage_prior_confidence is None
    assert config.stage_prior_probability is None


def test_unknown_intent_in_overrides_is_rejected() -> None:
    """配错了要当场报错，不能让一条笔误静默失效。"""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DecisionRoutingConfig(
            mode="active",
            confidence_threshold=0.55,
            probability_threshold=0.70,
            max_message_chars=6000,
            instructions="classify",
            criteria={
                "confused": "x", "verify_direction": "x", "undecided": "x", "how_to_act": "x",
                "stuck": "x", "review_due": "x", "free_chat": "x", "unclear": "x",
            },
            confidence_thresholds={"not_an_intent": 0.3},
        )

    with pytest.raises(ValidationError):
        DecisionRoutingConfig(
            mode="active",
            confidence_threshold=0.55,
            probability_threshold=0.70,
            max_message_chars=6000,
            instructions="classify",
            criteria={
                "confused": "x", "verify_direction": "x", "undecided": "x", "how_to_act": "x",
                "stuck": "x", "review_due": "x", "free_chat": "x", "unclear": "x",
            },
            stage_prior={"act": "not_an_intent"},
        )
