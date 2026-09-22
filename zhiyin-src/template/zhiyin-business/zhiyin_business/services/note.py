"""用户自建内容服务实现。

一层薄壳，但有两处判断必须留在服务层而不是 Repository：

1. **空文本不落库**。用户误敲一个回车就在库里留一条空待办，往后每次读
   用户信号都要多扫一条噪音；
2. **文本裁剪与去重**。同一句话写两遍（刷新前重发、双击保存）不该变成两条 ——
   采集策略读的是原话，重复的原话只会让"因为你写了…"显得像复读。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from zhiyin_business.ports.blackboard import UserNoteService
from zhiyin_data_sdk.repositories import UserNoteRepository
from zhiyin_kernel.blackboard import UserNote
from zhiyin_kernel.errors import InvalidRequest

_MAX_TEXT = 200


class DefaultUserNoteService(UserNoteService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, notes: UserNoteRepository) -> None:
        self._notes = notes

    async def list_by_user(self, user_id: str) -> list[UserNote]:
        return await self._notes.list_by_user(user_id)

    async def add(self, user_id: str, text: str, *, kind: str = "todo") -> UserNote:
        cleaned = (text or "").strip()[:_MAX_TEXT]
        if not cleaned:
            raise InvalidRequest("空内容不落库：用户写的东西必须是他说过的话")
        existing = await self._notes.list_by_user(user_id)
        duplicate = next(
            (note for note in existing if note.text == cleaned and note.kind == kind),
            None,
        )
        if duplicate is not None:
            return duplicate
        now = datetime.now(timezone.utc)
        return await self._notes.upsert(
            UserNote(
                id=f"note_{uuid4().hex[:12]}",
                user_id=user_id,
                kind=kind or "todo",
                text=cleaned,
                done=False,
                created_at=now,
                updated_at=now,
            )
        )

    async def set_done(self, user_id: str, note_id: str, done: bool) -> Optional[UserNote]:
        for note in await self._notes.list_by_user(user_id):
            if note.id != note_id:
                continue
            note.done = bool(done)
            return await self._notes.upsert(note)
        return None

    async def remove(self, user_id: str, note_id: str) -> None:
        await self._notes.delete(user_id, note_id)

    async def texts(self, user_id: str) -> list[str]:
        return [note.text for note in await self._notes.list_by_user(user_id)]


__all__ = ["DefaultUserNoteService"]
