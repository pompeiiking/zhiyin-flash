"""用户自建内容（自建待办 / 写下的目标）读写。

它和会话记忆、行为日志并列，但回答的是不同的问题：
行为日志回答"他做了什么"，会话记忆回答"这一轮聊到哪了"，
这张表回答"**他自己写下了什么**" —— 采集策略要引用他的原话，只能从这儿拿。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from zhiyin_kernel.blackboard import UserNote


class UserNoteRepository(ABC):
    """用户自建内容的 Repository。"""

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[UserNote]:
        """列出该用户写下的全部内容，按写入时间倒序。"""

    @abstractmethod
    async def upsert(self, note: UserNote) -> UserNote:
        """写入 / 更新一条。"""

    @abstractmethod
    async def delete(self, user_id: str, note_id: str) -> None:
        """删除一条。"""
