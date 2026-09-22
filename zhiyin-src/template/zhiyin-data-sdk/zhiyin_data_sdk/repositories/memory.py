"""会话记忆读写与查询（conversation_memory）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from zhiyin_kernel.blackboard import ConversationMemory, ConversationTurn


class ConversationMemoryRepository(ABC):
    """会话记忆 Repository。用于跨会话续接与摘要注入提示词。"""

    @abstractmethod
    async def get(self, user_id: str, task_id: str) -> Optional[ConversationMemory]:
        """按用户 + 任务读取会话记忆。"""

    @abstractmethod
    async def upsert(self, memory: ConversationMemory) -> ConversationMemory:
        """写入 / 更新会话记忆。"""

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[ConversationMemory]:
        """列出该用户全部任务会话记忆，用于左栏会话列表。"""

    @abstractmethod
    async def delete(self, user_id: str, task_id: str) -> None:
        """删除会话记忆。"""


class ConversationTurnRepository(ABC):
    """逐轮对话原文（`biz_conversation_turn`）。

    与记忆分开的理由见 `ConversationTurn` 的 docstring：
    记忆是给模型续接用的累积摘要，这里要的是"他当时到底怎么说的"。
    """

    @abstractmethod
    async def append(self, turn: ConversationTurn) -> ConversationTurn:
        """追加一轮（只追加、不修改：历史不该被后来的改写覆盖）。"""

    @abstractmethod
    async def list_by_task(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationTurn]:
        """按时间正序列出一条会话的全部轮次。"""
