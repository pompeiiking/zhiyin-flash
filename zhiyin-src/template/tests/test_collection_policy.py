"""采集策略的守卫：采集必须跟着画像走，而且要先于人可见。

为什么值得钉住
--------------
"动态采集"最容易退化成一句口号：代码里写着按画像走，实际上还是固定取一遍。
所以这里守三件具体的事：

1. 画像里已经有的字段，不再出现在"还缺"里 —— 不问要不要，就是重复采集；
2. 没有源头的字段（课程表 / 成绩单）必须出现在 `blocked` 里 ——
   不标出来，用户只会看到"点了没反应"；
3. 补完之后 `filled_by` 要能说出"少了哪几条" —— 这是闭环里给用户看的那半句。
"""

from __future__ import annotations

from datetime import datetime, timezone

from zhiyin_business.policies.collection import (
    CollectionSource,
    filled_by,
    plan_collection,
    signals_from,
)
from zhiyin_kernel.blackboard import Profile, ProfileField
from zhiyin_kernel.enums import ProfileSource


def _profile(*keys: str) -> Profile:
    now = datetime.now(timezone.utc)
    return Profile(
        id="p1",
        user_id="u1",
        updated_at=now,
        fields=[
            ProfileField(
                key=key,
                value="x",
                confidence=1.0,
                source=ProfileSource.RECORD,
                updated_at=now,
            )
            for key in keys
        ],
    )


def test_empty_profile_needs_everything() -> None:
    plan = plan_collection(None, stage="sprint")
    assert plan.missing > 0
    assert plan.by_source[CollectionSource.CHSI.value] > 0
    assert plan.by_source[CollectionSource.CONVERSATION.value] > 0
    # 学信网核验是空画像时最划算的第一步：一次动作补最多条
    assert plan.next_source() is CollectionSource.CHSI


def test_known_fields_are_no_longer_asked_for() -> None:
    """画像里已经有的，不再算缺口 —— 这是"不问要不要"的机械保证。"""
    before = plan_collection(None, stage="sprint")
    after = plan_collection(_profile("school", "major"), stage="sprint")
    assert after.missing == before.missing - 2
    assert after.by_source[CollectionSource.CHSI.value] == (
        before.by_source[CollectionSource.CHSI.value] - 2
    )


def test_having_a_field_does_not_change_other_sources() -> None:
    plan = plan_collection(_profile("school"), stage="sprint")
    assert plan.by_source[CollectionSource.CONVERSATION.value] == 4


def test_course_and_scores_are_reported_as_blocked_not_missing() -> None:
    """学信网没有课程表与成绩单 —— 必须出现在 blocked 里，而不是装作能取。"""
    plan = plan_collection(None, stage="sprint")
    assert "课程表" in plan.blocked
    assert "成绩单" in plan.blocked
    # 也不该被算进"下一步能走的源头"
    assert plan.next_source() is not CollectionSource.ACADEMIC


def test_stage_changes_the_order_not_the_count() -> None:
    """阶段影响的是"先补哪条"，不是"要补几条"。"""
    sprint = plan_collection(None, stage="sprint")
    explore = plan_collection(None, stage="explore")
    assert sprint.missing == explore.missing
    assert sprint.steps[0].key == "expected_graduation"
    assert explore.steps[0].key == "values"


def test_unavailable_items_never_outrank_actionable_ones() -> None:
    """没有源头的项不能排在最前面挡着能做的事 —— 顺序就是界面上"先做什么"。"""
    plan = plan_collection(None, stage="sprint")
    blocked_at = next(i for i, s in enumerate(plan.steps) if not s.available)
    first_got_at = next(
        (i for i, s in enumerate(plan.steps) if s.got), len(plan.steps)
    )
    actionable = [i for i, s in enumerate(plan.steps) if s.available and not s.got]
    assert actionable, "空画像下必须有能动手的项"
    assert blocked_at > max(actionable)
    assert blocked_at < first_got_at or first_got_at == len(plan.steps)


def test_filled_by_reports_what_this_round_brought_back() -> None:
    """闭环的后半句：取回之后，还差的东西少了哪几条。"""
    before = plan_collection(None, stage="sprint")
    after = plan_collection(_profile("school", "major", "degree_level"), stage="sprint")
    filled = filled_by(before, after)
    assert set(filled) == {"学校", "专业", "层次"}


def test_filled_by_is_empty_when_nothing_changed() -> None:
    plan = plan_collection(None, stage="sprint")
    assert filled_by(plan, plan) == ()


# ---------------------------------------------------------------- 用户自己写的东西


class _Signal:
    """动态资源里那条线索（`user_signals.json` 的一份）。"""

    def __init__(self, keyword: str, key: str, why: str = "", order: int = 0) -> None:
        self.keyword = keyword
        self.key = key
        self.why = why
        self.order = order


_SIGNALS = (
    _Signal("秋招", "expected_graduation", "你写的方向里秋招最看时间", order=1),
    _Signal("考研", "degree_level", "考研和本科就业是两条时间线", order=2),
    _Signal("课表", "courses", "没有课表算不出空档", order=3),
)


def test_notes_push_their_field_to_the_front() -> None:
    """用户写下的东西要压过"按阶段猜的"：他的账比系统的账靠前。"""
    plain = plan_collection(None, stage="explore")
    assert plain.steps[0].key == "values"          # 探索期系统默认先问价值取向

    told = plan_collection(None, stage="explore", notes=("下周三前改完简历，冲秋招",), signals=_SIGNALS)
    assert told.steps[0].key == "expected_graduation"
    assert told.steps[0].heard, "命中的原话片段必须留下来，回执里要引用"
    assert "秋招" in told.steps[0].heard


def test_reason_quotes_the_user_first() -> None:
    """理由必须以"因为你写了…"开头 —— 先引用用户，再说系统的账。"""
    plan = plan_collection(None, stage="sprint", notes=("想冲秋招",), signals=_SIGNALS)
    step = next(s for s in plan.steps if s.key == "expected_graduation")
    assert step.why.startswith("因为你写了「")
    assert "秋招" in step.why


def test_notes_never_rank_above_what_can_be_done() -> None:
    """写了课表也不许把"取不到的东西"顶到能做的事前面 —— 顺序就是行动顺序。"""
    plan = plan_collection(None, stage="sprint", notes=("这学期课表好满",), signals=_SIGNALS)
    courses_at = next(i for i, s in enumerate(plan.steps) if s.key == "courses")
    actionable = [i for i, s in enumerate(plan.steps) if s.available and not s.got]
    assert actionable
    assert courses_at > max(actionable)
    assert "课表" in plan.steps[courses_at].why       # 但理由里要如实说


def test_notes_do_not_touch_fields_that_are_already_known() -> None:
    """已经拿到的字段不会被一句话重新变成待办 —— 重复采集是消耗。"""
    profile = _profile("expected_graduation")
    plan = plan_collection(profile, stage="sprint", notes=("想冲秋招",), signals=_SIGNALS)
    assert all(s.got for s in plan.steps if s.key == "expected_graduation")
    kept = next(s for s in plan.steps if s.key == "expected_graduation")
    assert kept.why.startswith("因为你写了「"), "已经有的那条也留下他自己写过的话"


def test_signals_only_fire_on_words_the_user_actually_wrote() -> None:
    """不猜：没写过就是没写过，宁可少推一条。"""
    assert signals_from(("随便写了点东西",), _SIGNALS) == ()
    assert signals_from((), _SIGNALS) == ()
    assert signals_from(("我打算考研",), _SIGNALS)[0].key == "degree_level"


def test_snippet_is_trimmed_around_the_hit() -> None:
    """引用要短到读得动，两头截断要有省略号交代，不能让用户以为他写的就是那句。"""
    long_note = "我今年大三，家里希望我考研，自己也觉得学历高一点比较稳，所以想早点开始准备专业课"
    plan = plan_collection(None, stage="sprint", notes=(long_note,), signals=_SIGNALS)
    heard = next(s.heard for s in plan.steps if s.heard)
    assert "考研" in heard
    assert len(heard) < len(long_note)
    assert heard.startswith("…") and heard.endswith("…")


# ---------------------------------------------------------------- 线索表本身


def _registry_rows(name: str) -> list[dict]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "data" / "registry" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_signal_row_has_its_own_identity() -> None:
    """每条线索要有自己的身份。

    这是一条**被真实坑过**的守卫：入库时按身份去重，身份若取的是画像字段 `key`，
    那么"秋招 / 校招 / 毕业"这三条（都指向预计毕业）会被合并成一条 ——
    静默丢掉两个词，不报任何错，症状只是"我写了秋招它却不认识"。
    """
    ids = [row.get("id") for row in _registry_rows("user_signals.json")]
    assert all(ids), "线索表每一条都必须有 id（入库的身份）"
    assert len(set(ids)) == len(ids), f"线索表的 id 有重复：{ids}"


def test_every_signal_points_at_a_field_we_actually_collect() -> None:
    """线索指到的字段必须在采集规则里存在。

    指向一个不存在的字段不会报错：策略找不到那一条，于是"因为你写了…"永远不出现，
    看起来像"这条线索没生效"，实际上是表写错了。
    """
    collectable = {row["key"] for row in _registry_rows("collection_rules.json")}
    unknown = sorted(
        {row["key"] for row in _registry_rows("user_signals.json")} - collectable
    )
    assert not unknown, f"这些线索指向了采集清单里没有的字段：{unknown}"


# ---------------------------------------------------------------- 教务系统接通之后


def test_academic_stays_blocked_until_its_gateway_is_wired() -> None:
    """没接通教务系统时，课表必须待在"暂时补不了"那一栏。

    理由不是谨慎：把点不动的按钮排到第一位，用户会以为产品坏了 ——
    而真相是"这条源头还没接"。界面上两者必须长得不一样。
    """
    plan = plan_collection(None, stage="sprint")
    assert "课程表" in plan.blocked
    assert plan.by_source.get("academic") is None
    courses = next(step for step in plan.steps if step.key == "courses")
    assert courses.available is False


def test_academic_becomes_actionable_once_wired() -> None:
    """接通之后：课表从"补不了"变成"授权一次就能取"，而且排在能动手的那一档里。"""
    plan = plan_collection(
        None,
        stage="sprint",
        available_sources=("chsi", "conversation", "academic"),
    )
    assert "课程表" not in plan.blocked
    assert plan.by_source.get("academic") == 2      # 课程表 + 成绩单
    courses = next(step for step in plan.steps if step.key == "courses")
    assert courses.available is True
    # 冲刺阶段最卡的两条是"预计毕业"和"课程表"：接通后它们都在最前面，
    # 顺序仍按环节口径走（毕业时间第一，课表第二）
    assert [step.key for step in plan.steps[:2]] == ["expected_graduation", "courses"]


def test_turning_academic_on_does_not_promote_it_over_a_users_own_words() -> None:
    """用户自己写的仍然压过系统排序：他说了冲秋招，先取的还是毕业时间。"""
    plan = plan_collection(
        None,
        stage="sprint",
        notes=("想冲秋招",),
        signals=(_Signal("秋招", "expected_graduation", order=1),),
        available_sources=("chsi", "conversation", "academic"),
    )
    assert plan.steps[0].key == "expected_graduation"
