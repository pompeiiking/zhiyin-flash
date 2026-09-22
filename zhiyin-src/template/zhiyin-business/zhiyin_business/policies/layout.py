"""控制台气泡的编排：按用户状态决定**顺序、空间、出现与否**。

为什么这件事不能写在前端
------------------------
前端只能看到自己手里那几个字段，它不知道你处在哪个环节、还缺几条、
AI 现在在等什么。而"先看哪一块"恰恰依赖这些 ——

- 冲刺期：毕业时间与行动排前面；
- 探索期：画像与采集排前面；
- 刚核验完学籍：采集块该让位，画像该长大；
- AI 正在等你回话：对话该被递到手上，而不是让你去找入口。

这些判断写死在组件里，就只能靠发版来改，而且**改完还是所有人一个样**。
所以规则本体放动态资源（`data/registry/layout.json` → `biz_registry_item`），
这里只负责"按当前状态把它算成一份顺序"。

纯函数：输入策略与状态，输出排列结果。条件名走白名单，见 `PREDICATES`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from zhiyin_kernel.registry import LayoutPolicy


@dataclass(frozen=True)
class LayoutState:
    """算顺序需要的全部现状。都是**已知事实**，不做推断。"""

    profile_fields: int = 0
    profile_gaps: int = 0
    collection_missing: int = 0
    has_courses: bool = False
    has_action: bool = False
    has_direction_plans: bool = False
    #: 已经开始分析了（走到 ② 诊断及以后，或已经有了报告/方案/计划）。
    #: 这条决定"外部情报"那块什么时候出现 —— 推理还没开始就摆一块空情报，
    #: 用户只会觉得这个产品在硬凑版面。
    reached_analysis: bool = False
    ask_targets_chat: bool = False
    ask_id: str = ""


@dataclass(frozen=True)
class OrderedBlock:
    """排完之后的一块。`why` 会显示给用户 —— 顺序要能解释。"""

    id: str
    label: str
    hint: str
    weight: float
    why: str
    priority: int


"""
条件白名单。

刻意做成"名字 → 一个布尔"的固定表，而不是把表达式写进 JSON：
JSON 里放可执行条件，等于给配置文件开了个执行口子，
改一条配置就能改行为 —— 那是另一类问题（而且更难查）。
新条件在代码里加一行，配置里才有得用。
"""
PREDICATES: dict[str, Callable[[LayoutState], bool]] = {
    "ask_wants_chat": lambda s: s.ask_targets_chat,
    "collection_missing": lambda s: s.collection_missing > 0,
    "has_profile": lambda s: s.profile_fields > 0,
    "has_gaps": lambda s: s.profile_gaps > 0,
    "has_action": lambda s: s.has_action,
    "has_courses": lambda s: s.has_courses,
    "has_direction_plans": lambda s: s.has_direction_plans,
    "reached_analysis": lambda s: s.reached_analysis,
}


def evaluate(policy: LayoutPolicy, state: LayoutState) -> list[OrderedBlock]:
    """按策略与状态算出气泡顺序。返回的列表**已经是最终顺序**。"""
    blocks: list[OrderedBlock] = []
    for block in policy.blocks:
        if block.show_when and not _hit(block.show_when, state):
            continue

        priority = block.base
        # 命中条件就提前。减法是"位"，不是"倍" ——
        # 这样调一个 boost 不会连带把别的块挤到看不懂的位置。
        if block.boost_when and _hit(block.boost_when, state):
            priority -= block.boost
        blocks.append(
            OrderedBlock(
                id=block.id,
                label=block.label or block.id,
                hint=block.hint,
                weight=block.weight,
                why=block.why,
                priority=priority,
            )
        )

    # 同分时按策略里的书写顺序（那本身就是一份人为的重要度）
    order = {b.id: i for i, b in enumerate(policy.blocks)}
    blocks.sort(key=lambda b: (b.priority, order.get(b.id, 999)))
    return blocks


def _hit(name: str, state: LayoutState) -> bool:
    predicate = PREDICATES.get(name)
    if predicate is None:
        # 配置里写了代码不认识的条件：**当作不命中**，并且不报错。
        # 理由是这份配置可能比代码新（先发配置后发版），
        # 让整屏崩掉比少提前一块严重得多；真正的错配由守卫测试兜住。
        return False
    return predicate(state)


def state_of(
    *,
    profile_fields: int,
    profile_gaps: int,
    collection: Any = None,
    action_text: str = "",
    direction_plans: int = 0,
    ask_target: str = "",
    ask_id: str = "",
    reached_analysis: bool = False,
) -> LayoutState:
    """从各处的现状拼一个 LayoutState —— 装配一次，避免每处各算一份。"""
    by_key: Mapping[str, bool] = {}
    if collection is not None:
        by_key = {
            item.key: item.got for item in getattr(collection, "steps", ())
        }
    return LayoutState(
        profile_fields=profile_fields,
        profile_gaps=profile_gaps,
        collection_missing=int(getattr(collection, "missing", 0) or 0),
        has_courses=bool(by_key.get("courses")),
        has_action=bool((action_text or "").strip()),
        # ③ 的三套方案是**资产**：有方案才摆"方向方案"那块。
        # 用条数而不是布尔，是因为"0 条方案"与"还没走 ③"在界面上是同一句话，
        # 而条数顺带能说明"方案被清过"这种异常。
        has_direction_plans=direction_plans > 0,
        reached_analysis=reached_analysis,
        ask_targets_chat=ask_target == "chat",
        ask_id=ask_id,
    )


__all__ = [
    "LayoutState",
    "OrderedBlock",
    "PREDICATES",
    "evaluate",
    "state_of",
]
