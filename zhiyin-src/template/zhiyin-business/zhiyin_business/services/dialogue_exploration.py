"""Bounded working context for one conversation, never a profile or authorization."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_business.services.conversation_ledger import digest

#: These are UI/approval instructions, not self-descriptions. They can be valid
#: user turns, but they must never become evidence for a profile clue.
OPERATION_MESSAGE_HINTS = (
    "生成诊断报告", "报告草稿", "保存草稿", "启用这份报告", "启用这份新报告",
    "设为正式报告", "发起启用审批", "确认执行", "不要生效",
    "生成一份方向方案", "生成方向方案", "方向方案草稿", "启用这份方案",
)


def is_operation_message(message: object) -> bool:
    text = " ".join(str(message or "").split())
    return any(hint in text for hint in OPERATION_MESSAGE_HINTS)


class QuotedStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str = Field(min_length=1, max_length=160)
    quote: str = Field(min_length=1, max_length=400)


class ExplorationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(max_length=240)
    mode: Literal["explore", "answer", "act", "paused"]
    statements: list[QuotedStatement] = Field(default_factory=list, max_length=12)
    hypotheses: list[str] = Field(default_factory=list, max_length=6)
    explored_topics: list[str] = Field(default_factory=list, max_length=8)
    open_questions: list[str] = Field(default_factory=list, max_length=6)
    next_focus: str = Field(default="", max_length=240)


def privacy_stamp(state, session_id):
    return digest({"reset_at": state.get("conversation_memory_reset_at"),
        "forgotten_keys": state.get("conversation_forgotten_keys", []),
        "temporary": state.get("conversation_settings", {}).get(session_id, {}).get("temporary", False)})
