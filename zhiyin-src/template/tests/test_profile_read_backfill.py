"""画像读回来时：**头行不在、字段行在**，也要算"有画像"。

为什么值得守
------------
画像存两张表：`biz_profile`（头：归谁、整体版本、整体更新时间）与
`biz_profile_field`（字段：值 + 把握 + 来源 + 证据）。**字段行才是事实**，
头行只是容器 —— 但只有头行被当成"这份画像存在"，于是同一份数据出现两种读法：

    · 工作台（按字段行算覆盖与把握）→ 3 项已记录、覆盖 75%；
    · AI 任务（`profiles.get()`）→ 拿不到头行 ⇒ None ⇒ "画像中没有维度 major"。

界面上就是：画像页左边列着"专业 · 0.95"，右边正中间写着
"这一步没算完：这一条现在还没有可看的内容。"（2026-09-22 实测）

触发条件不是凭空来的：迁移只搬了字段行、或早年的写入没建头行，库就是这样。
一旦这样，工作台、AI 任务、影响面传播三处对"画像变没变"的判断会全部错开。

所以这条守的是**读回来只有一种解释**：字段行在 = 画像在。补在仓库那一层，
所有读法共享；这里用纯函数断它，不连库。
"""

from __future__ import annotations

from datetime import datetime, timezone

from zhiyin_infrastructure.postgres.repository import _assemble_profile
from zhiyin_kernel.blackboard import ProfileField, ProfileGap
from zhiyin_kernel.enums import ProfileSource


def _field(key: str, when: datetime) -> ProfileField:
    return ProfileField(
        key=key,
        label="专业",
        value="土木工程",
        confidence=0.95,
        source=ProfileSource("conversation"),
        evidence=["我说过学土木"],
        updated_at=when,
    )


def test_head_row_missing_but_fields_present_still_reads_as_a_profile() -> None:
    when = datetime(2026, 9, 22, 8, 33, 30, tzinfo=timezone.utc)
    profile = _assemble_profile("u1", None, [_field("major", when)], [])

    assert profile is not None, "有字段行就是有画像，不能返回 None"
    assert [f.key for f in profile.fields] == ["major"]
    # 整体更新时间取最实的一条：界面上"更新于"读的就是它
    assert profile.updated_at == when


def test_gaps_alone_also_count_as_a_profile() -> None:
    """只有缺口、还没有字段（刚聊完一轮还没落字段）也算建过档。"""
    profile = _assemble_profile(
        "u1",
        None,
        [],
        [
            ProfileGap(
                key="expected_graduation",
                label="预计毕业",
                reason="还不知道你哪年毕业",
                suggested_next_action="问一句你什么时候毕业",
            )
        ],
    )

    assert profile is not None
    assert profile.fields == []


def test_two_empty_tables_still_mean_no_profile() -> None:
    """什么行都没有 = 真的还没建档。补出空画像会让"还没开始"看起来像"已经有画像"。"""
    assert _assemble_profile("u1", None, [], []) is None


def test_head_row_wins_when_it_exists() -> None:
    """头行在的时候按头行读：版本号与整体更新时间以它为准。"""
    head = {
        "profile_id": "p-1",
        "version": 7,
        "updated_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
    }
    profile = _assemble_profile(
        "u1", head, [_field("major", datetime(2026, 9, 22, tzinfo=timezone.utc))], []
    )

    assert profile is not None
    assert (profile.id, profile.version) == ("p-1", 7)
    assert profile.updated_at == head["updated_at"]
