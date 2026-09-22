"""五环节产出契约集合。

这五个模型就是"产出契约"的业务侧定义。编排层只持有它们的 JSON Schema
（OutputContractSpec.json_schema）做通用校验，不感知业务字段含义，
从而同时满足 R-ORC-001（编排层无业务语义）与 R-ORC-002（必须校验产出契约）。
"""

from zhiyin_business.contracts.common import (
    AgentBadge,
    AssetUpdateDraft,
    BehaviorEventDraft,
    BehaviorGuide,
    ConversationMessage,
    Disclosure,
    Evidence,
    GuideOption,
    GuideReminder,
    GuideTask,
    TheoryRef,
)
from zhiyin_business.contracts.collect import CollectOutput, FieldUpdate
from zhiyin_business.contracts.diagnose import (
    DiagnoseGap,
    DiagnoseOutput,
    FactItem,
)
from zhiyin_business.contracts.decide import DecideOutput, PlanOption
from zhiyin_business.contracts.act import ActOutput, NodeReminder
from zhiyin_business.contracts.review import (
    ProgressSnapshot,
    ReviewOutput,
)
from zhiyin_kernel.enums import LoopStage

STAGE_CONTRACTS: dict[LoopStage, type] = {
    LoopStage.COLLECT: CollectOutput,
    LoopStage.DIAGNOSE: DiagnoseOutput,
    LoopStage.DECIDE: DecideOutput,
    LoopStage.ACT: ActOutput,
    LoopStage.REVIEW: ReviewOutput,
}
"""环节 → 产出契约。**这是唯一一份**。

它以前在三个地方各写了一遍：编排器的 `_SCHEMAS`、Loop 协调器的
`STAGE_OUTPUT_CONTRACTS`、以及文档。三份里的任何一份加一个环节，另外两份都不会动 ——
而症状是"某个环节的产出没被校验"，不会报错。所以收敛到契约包这一处：
环节与契约的对应关系属于契约本身，不属于任何一个调用方。
"""

__all__ = [
    "AgentBadge",
    "AssetUpdateDraft",
    "BehaviorEventDraft",
    "BehaviorGuide",
    "ConversationMessage",
    "Disclosure",
    "Evidence",
    "GuideOption",
    "GuideReminder",
    "GuideTask",
    "TheoryRef",
    "CollectOutput",
    "FieldUpdate",
    "DiagnoseGap",
    "DiagnoseOutput",
    "FactItem",
    "DecideOutput",
    "PlanOption",
    "ActOutput",
    "NodeReminder",
    "ProgressSnapshot",
    "ReviewOutput",
    "STAGE_CONTRACTS",
]
