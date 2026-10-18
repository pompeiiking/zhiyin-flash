"""任务会话读写（task_session）。

可拆可续的持久化载体：记录"当前在哪一环节、主理是谁"，而不是"报告是否生成"。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Optional, Sequence

from zhiyin_kernel.blackboard import TaskSession
from zhiyin_kernel.enums import LoopStage, TaskStatus


class TaskSessionRepository(ABC):
    """任务会话 Repository。"""

    @asynccontextmanager
    async def conversation_lock(self, user_id: str):
        """Production repositories override this to serialize across workers."""
        yield

    @abstractmethod
    async def get(self, session_id: str) -> Optional[TaskSession]:
        """按 id 读取任务会话。"""

    @abstractmethod
    async def find_active(self, user_id: str, task_code: str) -> Optional[TaskSession]:
        """查找某任务的进行中会话，用于"续接"而非"重建"。"""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, statuses: Optional[Sequence[TaskStatus]] = None
    ) -> list[TaskSession]:
        """列出用户的任务会话，用于左栏并行会话列表。"""

    @abstractmethod
    async def create(self, session: TaskSession) -> TaskSession:
        """创建任务会话。"""

    @abstractmethod
    async def update_stage(
        self, session_id: str, stage: LoopStage, lead_agent: str
    ) -> TaskSession:
        """推进环节并切换主理（交接的落库动作）。"""

    @abstractmethod
    async def update_status(self, session_id: str, status: TaskStatus) -> TaskSession:
        """更新会话状态。"""

    @abstractmethod
    async def rename(self, session_id: str, task_name: str) -> TaskSession:
        """会话改名（只改展示名，不动环节/消息）。"""

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """删除会话行；逐轮原文由记忆服务另行清理。"""
