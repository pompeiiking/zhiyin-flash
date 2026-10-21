"""Shared page/tool import preview contract. Recognition never mutates records."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from zhiyin_data_sdk.gateways.academic import CourseEntry, GradeEntry


class AcademicPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['courses', 'grades']
    material_id: str = Field(default='', max_length=100)
    text: str = Field(default='', max_length=200_000)
    school: str = Field(default='', max_length=120)
    term: str = Field(default='', max_length=40)


class AcademicPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_id: str
    kind: Literal['courses', 'grades']
    school: str
    term: str
    courses: list[CourseEntry] = Field(default_factory=list)
    grades: list[GradeEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    replace_count: int
    expires_at: str
    expected_version: str


class AcademicPreviewCommit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_id: str = Field(min_length=1, max_length=80)
