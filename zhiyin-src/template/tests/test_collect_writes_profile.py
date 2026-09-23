"""① 采集必须写画像：模型结构化返回的字段不许被丢掉。

这一条是端到端跑出来的真缺陷（2026-09-22）：真模型在采集环节老老实实按契约返回了
`field_updates`，而编排器读完就丢 —— 库里 `biz_profile` / `biz_profile_field` 始终是 0 行。
症状不报错、不白屏，只是**画像恒空、采集清单恒说"还缺 6 条"**，
而诊断环节照样能用对话记忆生成一份 15 维报告（`depends_on_profile_keys` 为空，
于是"画像一变就重算资产"的影响面传播也一并失效）。

这里守三件事：

1. 合规的采集产出 → 字段真的进了画像（值、把握、来源、证据都在）；
2. `remaining_gaps` 会被整体替换（不是叠加，否则缺口会越积越多）；
3. 产出不合契约 → 一条都不写（宁可没有，也不半写一份对不上的画像）。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zhiyin_business.contracts.collect import CollectOutput
from zhiyin_kernel.blackboard import ProfileGap
from zhiyin_kernel.enums import ProfileSource


def _collect_payload(*, bad: bool = False) -> dict:
    payload = {
        "conclusion": "你说你二年级就开始做结构方向的课程设计，这条我记下了。",
        "field_updates": [
            {
                "key": "interest",
                "label": "兴趣方向",
                "value": "结构设计",
                "confidence": 0.82,
                "source": "conversation",
                "evidence": ["课程设计连着三个学期都选了结构方向"],
            },
            {
                "key": "target_direction",
                "label": "目标方向",
                "value": "设计院结构设计岗",
                "confidence": 0.66,
                "source": "conversation",
                "evidence": ["他说更想先在设计院做结构设计"],
            },
        ],
        "remaining_gaps": [
            {
                "key": "skills",
                "label": "价值取舍",
                "reason": "还没被真实取舍考验过",
                "suggested_next_action": "给一个二选一的场景让他选",
            }
        ],
        "confidence_overall": 0.74,
        "ready_to_handoff": False,
        "guide": {"kind": "question", "text": "再问一句", "question": "两份工作你更想试哪个？"},
    }
    if bad:
        payload["field_updates"] = [{"key": "interest"}]  # 缺 confidence / source
    return payload


def test_collect_payload_matches_the_contract() -> None:
    """先确认测试用的载荷本身是合规的 —— 否则下面两条会变成空跑。"""
    output = CollectOutput.model_validate(_collect_payload())
    assert len(output.field_updates) == 2
    assert output.field_updates[0].source is ProfileSource.CONVERSATION
    assert output.remaining_gaps[0].key == "skills"


def test_bad_payload_is_rejected_by_the_contract() -> None:
    """不合契约的产出必须校验失败（编排器据此一条不写）。"""
    with pytest.raises(ValidationError):
        CollectOutput.model_validate(_collect_payload(bad=True))


def test_chinese_source_labels_are_accepted() -> None:
    """提示词里写的是中文来源（"来源「对话」"），模型照写也得收。

    不收的后果不是"这条字段没写进去"，而是**整份采集产出**被校验拒绝
    （`FieldUpdate.source` 是枚举）—— 画像静默不更新。所以中文标签要在契约入口翻掉。
    """
    payload = _collect_payload()
    payload["field_updates"][0]["source"] = "对话"
    payload["field_updates"][1]["source"] = "行为推断"
    output = CollectOutput.model_validate(payload)
    assert output.field_updates[0].source is ProfileSource.CONVERSATION
    assert output.field_updates[1].source is ProfileSource.BEHAVIOR_INFERENCE

    payload["field_updates"][0]["source"] = "凭空想的"
    with pytest.raises(ValidationError):
        CollectOutput.model_validate(payload)


@pytest.mark.asyncio
async def test_orchestrator_writes_collect_fields_into_profile() -> None:
    """端到端（内存装配）：一轮采集之后，画像里必须能读到那两个字段。"""
    from tests.e2e.test_main_path import _container  # 复用 e2e 的内存装配
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)
    profiles = container.profile_service
    user = "collect-writes-profile"

    payload = _collect_payload()
    await container.orchestrator._apply_collect(user, payload)  # noqa: SLF001 - 直接验这一步

    fields = {field.key: field for field in await profiles.get_fields(user)}
    assert set(fields) == {"interest", "target_direction"}
    assert fields["interest"].value == "结构设计"
    assert fields["interest"].confidence == pytest.approx(0.82)
    assert fields["interest"].source is ProfileSource.CONVERSATION
    assert fields["interest"].evidence
    # 名字必须跟着字段一起存：字段键是英文短名（interest），界面要显示的是中文名。
    # 名字不落库，画面上就是一串英文 —— 那是这个产品最不该有的样子。
    assert fields["interest"].label == "兴趣方向"
    assert fields["target_direction"].label == "目标方向"

    gaps = await profiles.get_gaps(user)
    assert [gap.key for gap in gaps] == ["skills"]
    assert gaps[0].label == "价值取舍"


@pytest.mark.asyncio
async def test_collect_gaps_are_replaced_not_accumulated() -> None:
    """缺口是**整体替换**：第二轮只剩一条时，库里就该只剩一条。"""
    from tests.e2e.test_main_path import _container
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)
    profiles = container.profile_service
    user = "collect-replaces-gaps"

    await profiles.replace_gaps(
        user,
        [
            ProfileGap(key="a", reason="旧缺口一", suggested_next_action="问 A"),
            ProfileGap(key="b", reason="旧缺口二", suggested_next_action="问 B"),
        ],
    )
    payload = _collect_payload()
    payload["remaining_gaps"] = [
        {"key": "experience", "reason": "只剩这一条", "suggested_next_action": "问它"}
    ]
    await container.orchestrator._apply_collect(user, payload)  # noqa: SLF001

    gaps = await profiles.get_gaps(user)
    assert [gap.key for gap in gaps] == ["experience"]


@pytest.mark.asyncio
async def test_invalid_collect_output_writes_nothing() -> None:
    """不合契约 → 一条都不写（宁可画像没更新，也不要半份对不上的画像）。"""
    from tests.e2e.test_main_path import _container
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)
    profiles = container.profile_service
    user = "collect-invalid"

    await container.orchestrator._apply_collect(user, _collect_payload(bad=True))  # noqa: SLF001
    assert await profiles.get_fields(user) == []


def _vocabulary(*keys: str):
    """装一份画像字段词表（动态资源里那份东西的内存版）。"""
    from zhiyin_kernel import dynamic_config
    from zhiyin_kernel.registry import ProfileFieldSpec

    before = dynamic_config.snapshot()
    dynamic_config.configure(
        dynamic_config.DynamicConfigSnapshot(
            profile_fields=tuple(ProfileFieldSpec(key=k, label=k) for k in keys)
        )
    )
    return before


@pytest.mark.asyncio
async def test_profile_field_gate_drops_keys_outside_the_vocabulary() -> None:
    """字段门禁：词表外的键不写进画像。

    为什么必须有这道门禁：字段键原来由模型自由发挥（实测写出过
    `interest_direction` / `course_selection_pattern`），而界面上要给中文名、
    采集清单与报告维度又按固定键取值 —— 键一散，这三件事同时坏掉，
    画像也就没法往下分析了。
    """
    from tests.e2e.test_main_path import _container
    from zhiyin_boot import wire_application
    from zhiyin_kernel import dynamic_config

    before = _vocabulary("interest")
    try:
        container = _container()
        wire_application(container)
        profiles = container.profile_service
        user = "collect-gate"

        await container.orchestrator._apply_collect(user, _collect_payload())  # noqa: SLF001
        kept = {field.key for field in await profiles.get_fields(user)}
        assert kept == {"interest"}, kept

        # 缺口同理：词表外的缺口不落库，且**不覆盖**上一份清单
        gaps = await profiles.get_gaps(user)
        assert [gap.key for gap in gaps] == []
    finally:
        dynamic_config.configure(before)


@pytest.mark.asyncio
async def test_profile_gate_is_open_when_the_vocabulary_is_missing() -> None:
    """词表没装载时不拦。

    "配置没读到"和"用户说的不算数"是两回事：前者该暴露在别处（标题为空之类），
    把用户刚说的话丢掉是更坏的那个结果。
    """
    from tests.e2e.test_main_path import _container
    from zhiyin_boot import wire_application
    from zhiyin_kernel import dynamic_config

    before = _vocabulary()  # 空词表
    try:
        container = _container()
        wire_application(container)
        profiles = container.profile_service
        user = "collect-open-gate"
        await container.orchestrator._apply_collect(user, _collect_payload())  # noqa: SLF001
        assert {f.key for f in await profiles.get_fields(user)} == {
            "interest",
            "target_direction",
        }
    finally:
        dynamic_config.configure(before)
