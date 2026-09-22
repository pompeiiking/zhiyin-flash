"""画像字段的**展示名**守卫：界面上不许出现英文内部键。

为什么单开一条
--------------
字段键是模型自己起的（`interest_direction` / `course_selection_pattern`），
只有采集规则里那 14 个标准键有中文名。实测截图里，画像面板 6 条有 5 条在显示英文，
用户看到的就是"一堆英文字段直接暴露"。

名字的两级来源、以及"最后一级是兜底不是正常路径"，是这个文件要钉住的口径：

1. 字段自带的 `label`（模型写画像时一起给）—— 首选；
2. 动态资源的采集规则表（标准键、老数据）—— 兜底；
3. 都没有 → 才轮到字段键本身。
"""

from __future__ import annotations

from datetime import datetime, timezone

from zhiyin_api.dto.mappers import workspace_page_view
from zhiyin_business.ports.workspace import WorkspaceView
from zhiyin_kernel.blackboard import Profile, ProfileField, ProfileGap
from zhiyin_kernel.enums import ProfileSource


def _field(key: str, label: str) -> ProfileField:
    return ProfileField(
        key=key,
        label=label,
        value="结构设计",
        confidence=0.8,
        source=ProfileSource.CONVERSATION,
        updated_at=datetime.now(timezone.utc),
    )


def _view(*fields: ProfileField, gaps: list[ProfileGap] | None = None) -> WorkspaceView:
    return WorkspaceView(
        user_id="u1",
        profile=Profile(
            id="p1",
            user_id="u1",
            fields=list(fields),
            gaps=gaps or [],
            updated_at=datetime.now(timezone.utc),
        ),
        # 动态资源里的采集规则：标准键的中文名
        profile_labels={"major": "专业", "interest": "兴趣"},
    )


def test_field_label_wins_over_the_rules_table() -> None:
    """模型给的名字优先 —— 它认得自己起的那个键是什么意思。"""
    view = _view(_field("interest_direction", "兴趣方向"))
    panel = workspace_page_view(view).profile_panel
    assert panel.fields[0].label == "兴趣方向"


def test_rules_table_covers_standard_keys_and_old_rows() -> None:
    """老数据没有 label：标准键必须靠动态资源里的对照表兜住，不能露英文。"""
    view = _view(_field("major", ""))
    panel = workspace_page_view(view).profile_panel
    assert panel.fields[0].label == "专业"


def test_unknown_key_without_label_falls_back_to_the_key_not_a_made_up_name() -> None:
    """两级都没有时回落到键本身。

    这是**刻意的**：编一个像模像样的中文名，比露出一串英文更坏 ——
    后者会被发现并修掉，前者会被当成真名字一直传下去。
    """
    view = _view(_field("some_model_invented_key", ""))
    panel = workspace_page_view(view).profile_panel
    assert panel.fields[0].label == ""


def test_gap_label_is_carried_too() -> None:
    """缺口同样会显示给用户：它也得有中文名。"""
    gap = ProfileGap(
        key="internship_experience",
        label="实习经历",
        reason="实习经历是方向判断里最硬的一条证据",
        suggested_next_action="问一句有没有实习过",
    )
    view = _view(gaps=[gap])
    panel = workspace_page_view(view).profile_panel
    assert panel.gaps[0].label == "实习经历"
