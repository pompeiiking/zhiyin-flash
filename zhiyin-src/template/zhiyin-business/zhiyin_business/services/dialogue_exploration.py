"""Bounded working context for one conversation, never a profile or authorization."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zhiyin_business.services.conversation_ledger import digest


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
