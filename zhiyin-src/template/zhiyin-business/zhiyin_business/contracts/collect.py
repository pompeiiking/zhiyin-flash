"""① 采集建模产出契约。

验收锚点：目标不是"问完 6 个问题"，而是"画像置信度提升"。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from zhiyin_kernel.blackboard import ProfileGap
from zhiyin_kernel.enums import ProfileSource
from zhiyin_business.contracts.common import (
    BehaviorGuide,
    Disclosure,
    TheoryRef,
)


#: 提示词里给模型看的是**中文标签**（"他直接说的：来源「对话」，把握高"），
#: 而契约取值是英文枚举。模型照着提示词写中文是合理行为 —— 在契约入口收下来，
#: 否则整份采集产出会被判"不符合契约"，画像就此静默不更新
#: （端到端实测：五轮对话之后 `biz_profile_field` 仍是 0 行）。
_SOURCE_ALIASES = {
    "简历": "resume",
    "对话": "conversation",
    "测评": "assessment",
    "行为推断": "behavior_inference",
    "导师建议": "mentor",
    "客观档案": "record",
    "官方档案": "record",
    "记录": "record",
}


class FieldUpdate(BaseModel):
    """一次采集对画像字段的更新。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="字段键，沿用输入里给的键；新字段用英文短名")
    label: str = Field(
        default="",
        description=(
            "这个字段用中文怎么称呼（例：专业 / 兴趣方向 / 实习经历）。"
            "**必须填**：字段键会进库，但界面上给用户看的是这个名字"
        ),
    )
    value: object = Field(description="字段值，结构由画像 schema 决定")
    confidence: float = Field(ge=0.0, le=1.0)
    source: ProfileSource
    evidence: list[str] = Field(default_factory=list)

    @field_validator("source", mode="before")
    @classmethod
    def _accept_chinese_source(cls, value: object) -> object:
        """把提示词里的中文来源标签翻成枚举取值（未命中就原样交给枚举报错）。"""
        if isinstance(value, str):
            hit = _SOURCE_ALIASES.get(value.strip())
            if hit is not None:
                return hit
        return value


class CollectOutput(BaseModel):
    """① 采集建模的产出契约。"""

    model_config = ConfigDict(extra="forbid")

    conclusion: str = Field(
        default="",
        description=(
            "这一轮对他说的话：2 到 4 句，每句不超过 40 字。先用一句人话接住他的意思"
            "（顺着说、认下事实或点出矛盾都行，**不必逐字复述**），再说这一轮你看清了什么。"
            "**不要**汇报你记了什么（「这条我记下了」），也不要写成「我为什么要问他这个」"
            "这类场外话 —— 他读到的应该是一个人在跟他说话。"
        )
    )
    field_updates: list[FieldUpdate] = Field(default_factory=list)
    remaining_gaps: list[ProfileGap] = Field(default_factory=list)
    confidence_overall: float = Field(
        default=0.0, ge=0.0, le=1.0, description="画像整体置信度，用于判定是否可交接"
    )
    ready_to_handoff: bool = Field(
        default=False, description="是否达到目标环节所需最低置信度"
    )
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    guide: BehaviorGuide | None = Field(
        default=None,
        description=(
            "下一步：一次一问的追问。**可以不给** —— 这一轮没想好下一个问题、"
            "或者干脆先顺着他说两句，就给 null。系统会退到用你写的话收尾，"
            "不会因为缺这个字段判整轮作废（缺字段就作废，代价是这一轮他说的话白说）"
        ),
    )
    disclosure: Disclosure | None = None
