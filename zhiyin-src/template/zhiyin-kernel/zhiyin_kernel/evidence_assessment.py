"""Display-only model assessments; never a substitute for verification or authorization."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class EvidenceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "processing", "evaluated", "insufficient", "stale", "failed"] = "pending"
    score: float | None = Field(default=None, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    sources: dict[str, str] = Field(default_factory=dict)
    assessed_at: datetime | None = None
    entry_version: int | None = None
    input_hash: str = ""
    prompt_version: str = ""
    model: str = ""
