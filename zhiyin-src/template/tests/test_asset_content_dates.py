"""阶段日期里的星期必须按真实日历纠正（模型会写错星期）。"""

from __future__ import annotations

from zhiyin_business.contracts.act import ActOutput
from zhiyin_business.services.asset_content import (
    _normalize_phase_date_range,
    action_plan_from_act,
)
from zhiyin_kernel.assets import ActionPhase, ActionTask


def test_weekday_in_date_range_is_corrected() -> None:
    # 2026-10-17 是周六、2026-10-23 是周五；模型原文写成了"周五/周四"。
    fixed = _normalize_phase_date_range("10月17日（周五）—10月23日（周四）")
    assert fixed == "10月17日（周六）—10月23日（周五）"


def test_unparseable_or_plain_range_is_left_alone() -> None:
    assert _normalize_phase_date_range("本学期第 4—6 周") == "本学期第 4—6 周"
    assert _normalize_phase_date_range("") == ""


def test_action_plan_from_act_normalizes_every_phase() -> None:
    output = ActOutput(
        conclusion="这一周先做一件事。",
        phases=[
            ActionPhase(
                name="第一周",
                date_range="10月17日（周五）—10月19日（周日）",
                tasks=[ActionTask(text="整理项目清单")],
            )
        ],
    )
    plan, _nodes = action_plan_from_act(output, user_id="u1")
    assert plan.phases[0].date_range == "10月17日（周六）—10月19日（周一）"
