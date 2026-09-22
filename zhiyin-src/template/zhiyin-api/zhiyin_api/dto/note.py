"""用户自建内容 DTO（自建待办 / 写下的目标）。

它是**用户的原话**在本系统的唯一入口。之所以要过接口而不是只存浏览器：
采集策略跑在后端，他写下的"想冲秋招"必须在后端读得到，
回执里那句"因为你写了…"才引用得上他自己的字。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteView(BaseModel):
    """一条他写下的内容。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str = Field(description="todo / goal")
    text: str = Field(description="用户的原话")
    done: bool = False
    created_at: datetime


class NoteCreateRequest(BaseModel):
    """写下一条。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200, description="用户的原话")
    kind: str = Field(default="todo", description="todo / goal")


class NoteDoneRequest(BaseModel):
    """勾掉 / 取消勾掉。"""

    model_config = ConfigDict(extra="forbid")

    done: bool


class NoteAck(BaseModel):
    """删除回执。"""

    model_config = ConfigDict(extra="forbid")

    removed: str


__all__ = ["NoteAck", "NoteCreateRequest", "NoteDoneRequest", "NoteView"]
