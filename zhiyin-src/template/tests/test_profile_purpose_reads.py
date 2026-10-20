"""用途视图接入读取方的回归（《个人画像设计-2026-10-20》第 8 节）。

锁住四件事：

1. 每个 AI 任务读的是**服务端算好的用途视图**，不再整份扫描画像：
   计划类任务看不到兴趣 / 价值取向 / 补充信息等无关类别。
2. 冲突 / 过期 / 撤回的记录不进入任何业务读取：提示词、`profile.read` 与分析访问。
3. 专业检索用途只含学习背景，普通兴趣不能冒充专业查询。
4. 给模型看的画像文本不再带内部 confidence（“把握：0.87”）：
   它既不是真实性也不是熟练度，模型会把它当成可引用的结论。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from agno.run import RunContext

from zhiyin_business.services.ai_tasks import (
    _PROFILE_PURPOSE,
    _TASK_SPECS,
    AiTaskService,
    _purpose_for,
    _source_audit_lines,
)
from zhiyin_business.services.analysis_access import AnalysisScope
from zhiyin_infrastructure.ai.tools import build_tool_catalog
from zhiyin_kernel import profile_taxonomy
from zhiyin_kernel.blackboard import Profile, ProfileField, ProfileGap
from zhiyin_kernel.enums import (
    ProfileEntryStatus,
    ProfilePurpose,
    ProfileSource,
    ProfileVerification,
)

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
USER = "u-purpose-reads"


def _field(
    key: str,
    value: object,
    *,
    source: ProfileSource = ProfileSource.CONVERSATION,
    status: ProfileEntryStatus = ProfileEntryStatus.ACTIVE,
    verification: ProfileVerification | None = None,
) -> ProfileField:
    """一条记录。confidence 刻意给一个显眼的小数，用来证明它不再进提示词。"""
    return ProfileField(
        key=key,
        value=value,
        confidence=0.87,
        source=source,
        updated_at=NOW,
        verification=verification,
        status=status,
    )


def _profile(*fields: ProfileField, gaps: list[ProfileGap] | None = None) -> Profile:
    return Profile(id="p", user_id=USER, updated_at=NOW, fields=list(fields), gaps=gaps or [])


def _lines(profile: Profile, purpose: ProfilePurpose) -> list[str]:
    return AiTaskService._profile_lines(profile, purpose)


# ---------------------------------------------------------------------------
# 状态：冲突 / 撤回的记录退出读取
# ---------------------------------------------------------------------------


def test_conflict_and_withdrawn_records_leave_every_purpose_read() -> None:
    active = _field("interest", "把东西真正跑起来的过程")
    conflict = _field(
        "target_direction", "后端工程师", status=ProfileEntryStatus.CONFLICT
    )
    withdrawn = _field("skills", "独立调试", status=ProfileEntryStatus.WITHDRAWN)
    profile = _profile(active, conflict, withdrawn)

    for purpose in ProfilePurpose:
        text = "\n".join(_lines(profile, purpose))
        assert "后端工程师" not in text, f"{purpose} 读到了冲突记录"
        assert "独立调试" not in text, f"{purpose} 读到了撤回记录"
    assert "把东西真正跑起来的过程" in "\n".join(
        _lines(profile, ProfilePurpose.CONVERSATION)
    )
    # 来源审计只统计可用记录：撤回/冲突的不能继续当“可引用来源”。
    assert "对话：1 条" in "\n".join(_source_audit_lines(profile))


# ---------------------------------------------------------------------------
# 用途：专业检索不含兴趣；计划类任务看不到无关类别
# ---------------------------------------------------------------------------


def test_major_retrieval_purpose_never_carries_ordinary_interests() -> None:
    major = _field("major", "人工智能", source=ProfileSource.USER_EDIT)
    interest = _field("interest", ["把东西真正跑起来的过程"])
    views = profile_taxonomy.records_for_purpose(
        ProfilePurpose.MAJOR_RETRIEVAL, [major, interest]
    )
    assert [item.key for item in views] == ["major"]
    assert profile_taxonomy.major_terms([major, interest]) == ["人工智能"]
    # 兴趣不是职业名称，也不冒充专业/职业检索词。
    assert profile_taxonomy.career_focus_terms([major, interest]) == []


def test_planning_tasks_only_read_planning_categories() -> None:
    profile = _profile(
        _field("target_direction", "数据分析"),
        _field("skills", "SQL"),
        _field("constraints", "本周只有晚上有空"),
        _field("major", "统计学"),
        _field("interest", "看纪录片"),
        _field("values", "稳定"),
        _field("supplement", "同学在准备考研"),
    )
    planning_text = "\n".join(_lines(profile, _purpose_for("plan.todos")))
    for expected in ("数据分析", "SQL", "本周只有晚上有空", "统计学"):
        assert expected in planning_text
    for unrelated in ("看纪录片", "稳定", "同学在准备考研"):
        assert unrelated not in planning_text, f"计划类任务读到了无关类别：{unrelated}"

    # 每个生成任务都登记了用途；没登记的一律按普通交流处理。
    assert set(_TASK_SPECS) <= set(_PROFILE_PURPOSE)
    assert _purpose_for("not.registered") is ProfilePurpose.CONVERSATION
    assert _PROFILE_PURPOSE["day.advice"] is ProfilePurpose.PLANNING
    assert _PROFILE_PURPOSE["plan.timetable"] is ProfilePurpose.PLANNING


def test_profile_lines_show_category_and_verification_without_confidence() -> None:
    profile = _profile(_field("major", "人工智能"))
    line = _lines(profile, ProfilePurpose.CONVERSATION)[0]
    assert "学习背景" in line and "本人自述" in line
    assert "major：人工智能" in line
    assert "把握" not in line and "0.87" not in line
    assert "更新于 10-20" in line


# ---------------------------------------------------------------------------
# profile.read：类别 / 核实状态 / 来源，没有内部置信度
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_read_text_has_category_verification_and_no_internal_confidence() -> None:
    profile = _profile(
        _field("major", "人工智能"),
        _field("school", "河北大学", source=ProfileSource.RECORD),
        _field(
            "award",
            "结构设计竞赛二等奖",
            source=ProfileSource.RECORD,
            verification=ProfileVerification.VERIFIED,
        ),
        _field("interest", "已撤回的兴趣", status=ProfileEntryStatus.WITHDRAWN),
        gaps=[
            ProfileGap(
                key="internship",
                label="实习经历",
                reason="还没有正式实习记录",
                suggested_next_action="问一句：这学期做过什么项目",
            )
        ],
    )

    async def read_profile(user_id: str) -> Profile:
        return profile

    catalog = build_tool_catalog(profile_reader=read_profile)
    context = RunContext(run_id="r", session_id="s", user_id=USER, dependencies={})
    text = await catalog["profile.read"].handler(context)

    assert "把握" not in text
    assert "0.87" not in text
    assert "学习背景" in text and "本人自述" in text and "来源：对话" in text
    assert "资料记录" in text
    assert "已核验" in text and "来源：客观档案" in text
    assert "已撤回的兴趣" not in text
    # “还缺”这一部分保留。
    assert "还缺" in text and "还没有正式实习记录" in text


# ---------------------------------------------------------------------------
# 分析访问：先过滤撤回/冲突，再按用途与来源权限
# ---------------------------------------------------------------------------


def test_analysis_access_filters_withdrawn_records_before_source_permissions() -> None:
    active_manual = _field("target_direction", "产品经理", source=ProfileSource.USER_EDIT)
    withdrawn_manual = _field(
        "target_direction",
        "旧方向：运营",
        source=ProfileSource.USER_EDIT,
        status=ProfileEntryStatus.WITHDRAWN,
    )
    conflict_record = _field(
        "major", "土木工程", source=ProfileSource.RECORD, status=ProfileEntryStatus.CONFLICT
    )
    academic_record = _field("school", "河北大学", source=ProfileSource.RECORD)
    conversation_interest = _field("interest", "看纪录片")
    profile = _profile(
        active_manual,
        withdrawn_manual,
        conflict_record,
        academic_record,
        conversation_interest,
    )

    # 受限分析（只允许学业资料）：撤回/冲突退出；来源不允许的对话推断也退出；
    # 本人更正的方向与允许来源的学业事实仍可读。
    restricted = AnalysisScope(user_id=USER, sources=frozenset({"academic"}), state=None)
    values = {item.value for item in restricted.profile(profile).fields}
    assert "产品经理" in values
    assert "河北大学" in values
    assert "旧方向：运营" not in values
    assert "土木工程" not in values
    assert "看纪录片" not in values

    # 不受限时撤回/冲突同样不能读到（此前这里原样返回整份画像）。
    unrestricted = AnalysisScope(
        user_id=USER, sources=frozenset({"academic", "material"}), state=None
    )
    values = {item.value for item in unrestricted.profile(profile).fields}
    assert "产品经理" in values and "看纪录片" in values
    assert "旧方向：运营" not in values and "土木工程" not in values
