"""复盘的调整 → 行动计划的结构化落库（实测 ZY-05）。

问题原样：复盘里明确说了「周六上午删掉，只用周二周四」，而行动计划里那三条周六任务
一条都没少 —— 话改了、资产没改，用户第二天打开看到的还是旧计划，
「改了哪几项」也无从核对。

这个模块只做两件确定的事：**删**与**挪**。
新增任务不在这里 —— 那是 ④ 行动环节的产出，复盘越界造任务会让"谁负责这件事"变糊。

命中的写法：任务 id 精确相等，或关键词出现在任务文本里 ——
复盘说的是人话（"周六"），不是 id。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from zhiyin_business.contracts.review import PlanPatch
from zhiyin_kernel.assets import ActionPlan


def _hit(task_id: str, text: str, key: str) -> bool:
    key = (key or "").strip()
    if not key:
        return False
    return task_id == key or key in (text or "")


def _parse_due(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def apply_plan_patch(
    plan: ActionPlan, patch: Optional[PlanPatch]
) -> tuple[ActionPlan, list[str]]:
    """应用复盘调整，返回（新计划, 变更摘要）。

    patch 为空、或一条都没命中时，原样返回且摘要为空 ——
    宁可什么都不改，也不要凭空造一次"已调整"的假象。
    """
    if patch is None:
        return plan, []

    summary: list[str] = []
    phases = []
    for phase in plan.phases:
        tasks = []
        for task in phase.tasks:
            matched = next(
                (key for key in patch.drop_tasks if _hit(task.id, task.text, key)), None
            )
            if matched is not None:
                # 已经做完的事不删：删掉会让"已完成数"下降，
                # 而用户看到的是自己做过的事凭空消失。
                if task.done:
                    summary.append(f"「{task.text}」已完成，保留")
                else:
                    summary.append(f"删掉「{task.text}」")
                    continue
            due: Optional[datetime] = None
            for key, value in patch.reschedule_tasks.items():
                if _hit(task.id, task.text, key):
                    due = _parse_due(value)
                    break
            if due is not None:
                tasks.append(task.model_copy(update={"due_date": due}))
                summary.append(f"「{task.text}」改到 {due.date().isoformat()}")
            else:
                tasks.append(task)

        updated = phase.model_copy(update={"tasks": tasks})
        new_range = next(
            (
                (value or "").strip()
                for key, value in patch.reschedule_phases.items()
                if (phase.name or "").strip() == (key or "").strip()
            ),
            "",
        )
        if new_range:
            updated = updated.model_copy(update={"date_range": new_range})
            summary.append(f"阶段「{phase.name}」改为 {new_range}")
        if not updated.tasks and phase.tasks:
            summary.append(f"阶段「{phase.name}」已无任务，移除")
            continue
        phases.append(updated)

    if not summary:
        return plan, []
    return plan.model_copy(update={"phases": phases}), summary


__all__ = ["apply_plan_patch"]
