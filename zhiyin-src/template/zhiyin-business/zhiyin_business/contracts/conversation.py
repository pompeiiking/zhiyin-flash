"""A conversation answer is independent of report/plan generation contracts."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from zhiyin_business.contracts.collect import FieldUpdate
from zhiyin_business.contracts.common import BehaviorGuide, TheoryRef
from zhiyin_kernel.blackboard import ProfileGap


class ConversationFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Literal["time_budget", "direction", "preference", "location", "other"]
    value: str = Field(max_length=600)
    evidence: str = Field(min_length=3, max_length=1600, description="必须逐字引用本轮用户消息，并包含 value 原文。只保存用户明确的持续约束和偏好；本轮未更正则不要重写旧值。")


class ConversationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion: str = Field(description="直接回答用户本轮问题，篇幅、段落和条目按问题需要决定。")
    guide: BehaviorGuide | None = None
    theory_refs: list[TheoryRef] = Field(default_factory=list)
    field_updates: list[FieldUpdate] = Field(default_factory=list, description="仅提取本轮明确自述，每条 evidence 必须逐字引用本轮输入；没有新事实则为空。")
    remaining_gaps: list[ProfileGap] | None = None
    memory_updates: list[ConversationFact] = Field(default_factory=list, max_length=5)
