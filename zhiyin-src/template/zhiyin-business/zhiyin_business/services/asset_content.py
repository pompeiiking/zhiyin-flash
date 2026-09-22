"""环节产出 → 资产内容：把"模型生成的东西"变成"能读的资产"。

为什么需要这一层
----------------
这条链路此前**断在最后一步**：

    DiagnoseOutput（15 维 / SWOT / 结论）
        → 编排器拿到 structured
        → 只取 theory_refs 与 guide 拼一条对话消息   ← 断在这里
        → 其余字段直接丢弃

于是 `Report` 全仓没有一个构造点，`AssetRepository.save_report` 没有任何调用者，
`GET /app/report/full-text` 恒返回空报告、工作台 ②③④⑤ 恒 `version=null` ——
**不是"功能没做"，是生成出来的正文没有落库**。

这一层只做形状翻译（环节契约 → 内核资产），不取数、不做规则判断；
版本号与落库由 `AssetService.save_*` 负责，两者分开才不会出现"两个地方各自编号"。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zhiyin_business.contracts.act import ActOutput
from zhiyin_business.contracts.decide import DecideOutput
from zhiyin_business.contracts.diagnose import DiagnoseOutput
from zhiyin_kernel.assets import (
    ActionPlan,
    CalendarNode,
    DirectionPlan,
    PlanGap,
    Report,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def report_from_diagnose(output: DiagnoseOutput, *, user_id: str) -> Report:
    """② 诊断产出 → 15 维报告。

    字段对应关系（一个都不落）：

    | 环节产出 | 报告字段 | 说明 |
    | --- | --- | --- |
    | `verdict` | `verdict` | 结论直接搬 |
    | `swot` | `swot` | 四象限直接搬 |
    | `dimensions` | `dimensions` | 15 维（自我 6 / 职业 5 / 决策 4） |
    | `facts[].source` | `sources` | 去重后的**事实来源**，报告要能溯源 |
    | `theory_refs[].name` | `methodologies` | 本次用到的方法论 |

    不搬 `gaps` / `evidences` / `confidence_used` / `guide` / `disclosure`：
    前三个属于"诊断过程"，`guide` 与 `disclosure` 属于**这一轮对话**的动作与告知，
    都不是报告正文的一部分 —— 报告是只读资产，不该包含"请用户做某件事"。
    """
    return Report(
        id=_new_id("rpt"),
        user_id=user_id,
        version=0,  # 由 AssetService 统一分配，这里不自己编号
        generated_at=_now(),
        verdict=output.verdict,
        swot=output.swot,
        dimensions=list(output.dimensions),
        sources=_dedupe(item.source for item in output.facts if item.source),
        methodologies=_dedupe(ref.name for ref in output.theory_refs if ref.name),
    )


def direction_plans_from_decide(
    output: DecideOutput, *, user_id: str, report_id: str | None = None
) -> list[DirectionPlan]:
    """③ 决策产出 → 方向方案组（主攻 / 平行 / 保底）。

    `PlanOption.gaps` 是字符串要点，而 `DirectionPlan.gaps` 要求
    `PlanGap{requirement, current_state, suggestion}` 三段 —— 这里**不硬拆字符串**：
    把整条要点放进 `requirement`（"要补什么"），另两段留空。
    硬拆只会造出一堆看起来结构化、实际错位的字段。
    """
    plans: list[DirectionPlan] = []
    for option in output.plans:
        plans.append(
            DirectionPlan(
                id=_new_id("plan"),
                report_id=report_id,
                role=option.role,
                name=option.name,
                target_desc=option.target_desc,
                match_score=option.match_score,
                match_method=output.match_score_method,
                gaps=[PlanGap(requirement=text, current_state="", suggestion="") for text in option.gaps],
                fit_reason=option.fit_reason,
                main_risk=option.main_risk,
            )
        )
    return plans


def action_plan_from_act(
    output: ActOutput, *, user_id: str
) -> tuple[ActionPlan, list[CalendarNode]]:
    """④ 行动产出 → 行动计划 + 关键节点日历条目。

    返回两样东西，因为它们**归两个不同的读侧**：计划本身进 `ActionPlan`，
    关键节点进日历（规划师写入、教练读取、工作台展示）。
    `ActionPlan` 里也确实没有节点字段 —— 形状本身就在拒绝"把日历塞进计划的私有数据"。

    `phases` 在两侧是同一个内核类型（`ActionPhase`），直接搬。
    """
    # 给每条任务分配稳定 id：勾选 / 取消按 id 定位，同一阶段里的同名任务不会互相顶掉。
    phases = [
        phase.model_copy(
            update={
                "tasks": [
                    task.model_copy(update={"id": task.id or _new_id("task")})
                    for task in phase.tasks
                ]
            }
        )
        for phase in output.phases
    ]
    plan = ActionPlan(id=_new_id("act"), plan_id="", phases=phases)
    nodes = [
        CalendarNode(
            node_id=_new_id("cal"),
            user_id=user_id,
            title=item.title,
            due_at=item.due_at,
            source="planner",
            related_task_text=item.related_task_text,
        )
        for item in output.reminders
    ]
    return plan, nodes


def _dedupe(values: Any) -> list[str]:
    """保序去重：报告里的来源清单重复出现同一条会很显眼，而顺序本身有意义。"""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


__all__ = [
    "action_plan_from_act",
    "direction_plans_from_decide",
    "report_from_diagnose",
]
