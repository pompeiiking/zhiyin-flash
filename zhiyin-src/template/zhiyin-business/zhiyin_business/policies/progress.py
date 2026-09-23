"""按**真实进度**判定环节：资产到了哪一步、用户做过什么。

为什么要有它
------------
环节原来只有一条推进途径：命中意图关键词（`routing_rules.json` 的六条映射），
未命中就"退回当前环节"。后果实测过 —— 一个用户聊了 12 轮，`① 采集 → ② 诊断`
之后就再没动过：他明明已经认领了差距，系统手上却没有任何"可以往下走了"的依据，
只能等他哪天恰好说出"我拿不准"这类词。产品的五环节闭环因此停在第 2 步。

而设计里**每一环的验收锚点本来就是行为**（`assets.py` 的 GapClaim 注释就写着
"诊断 → 决策的衔接点"）：

    ② 诊断  用户认领至少一条差距   → ③ 决策
    ③ 决策  用户选中一套方案       → ④ 行动
    ④ 行动  至少勾掉一个任务       → ⑤ 复盘

本模块把这些锚点翻成可判定的规则。它是**纯函数**：只读黑板快照，不写库、不调模型，
所以既能被单测直接钉住，也不会给每一轮加延迟。

两条纪律
--------
1. **只往前推，不往回拉**：返回的结果比当前环节靠前才采纳（回退由关键词与
   收敛规则负责，例如"我情况变了"命中采集）。否则用户在 ⑤ 复盘时，
   手上那份没勾完的任务会把他反复拽回 ④。
2. **没有信号就不猜**：返回 `None`，交给调用方按原口径处理。宁可停在原地，
   也不要凭半份依据把人推进下一环。
"""

from __future__ import annotations

from typing import Optional

from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_kernel.enums import AssetType, BehaviorEventType, LoopStage


def stage_from_progress(blackboard: BlackboardView) -> Optional[LoopStage]:
    """按资产与行为推出"这一步该在哪一环"；推不出返回 None。

    判定顺序从后往前：走得最远的那件事说了算。
    """
    asset_types = {item.asset_type for item in blackboard.asset_versions}
    events = {item.event_type for item in blackboard.recent_behaviors}

    has_report = AssetType.REPORT in asset_types
    has_plan = AssetType.DIRECTION_PLAN in asset_types
    has_action = AssetType.ACTION_PLAN in asset_types

    chosen = bool(
        events & {BehaviorEventType.DECISION_SELECT, BehaviorEventType.DECISION_RESELECT}
    )
    claimed = BehaviorEventType.GAP_CLAIM in events

    # ④ → ⑤：计划在手、又真的勾掉过任务 → 该回头看这些动作有没有用了。
    if has_action and BehaviorEventType.TASK_DONE in events:
        return LoopStage.REVIEW
    # ③ → ④：方案在手、用户选过一套 → 该把选择拆成今天能做的事。
    if has_plan and chosen:
        return LoopStage.ACT
    # ② → ③：报告在手、用户认领过差距 → 该在几条路里做可撤回的选择。
    if has_report and claimed:
        return LoopStage.DECIDE
    # 报告在手：已经比过一轮，留在诊断（除非关键词把他带去别处）。
    if has_report:
        return LoopStage.DIAGNOSE
    return None


def progresses_to(
    current: Optional[LoopStage], candidate: Optional[LoopStage]
) -> Optional[LoopStage]:
    """把进度结论与当前环节合起来：只有**更靠后**才采纳。

    `current` 为空（全新会话、还没定过位）时，直接采纳候选 —— 那正是
    "从哪一步开始"第一次被决定的时候。
    """
    if candidate is None:
        return None
    if current is None:
        return candidate
    return candidate if _order(candidate) > _order(current) else None


def _order(stage: LoopStage) -> int:
    return list(LoopStage).index(stage)


__all__ = ["progresses_to", "stage_from_progress"]
