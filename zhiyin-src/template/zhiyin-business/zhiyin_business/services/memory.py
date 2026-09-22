"""会话记忆服务实现。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from zhiyin_business.ports.blackboard import ConversationMemoryService
from zhiyin_data_sdk.repositories import (
    ConversationMemoryRepository,
    ConversationTurnRepository,
)
from zhiyin_kernel.blackboard import ConversationMemory, ConversationTurn
from zhiyin_kernel.enums import LoopStage


class DefaultConversationMemoryService(ConversationMemoryService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        memories: ConversationMemoryRepository,
        turns: Optional[ConversationTurnRepository] = None,
    ) -> None:
        self._memories = memories
        # 逐轮原文是可选的：只做摘要续接的装配（单测、纯内存最小装配）可以不接它，
        # 那时 record_turn 是空操作，而不是抛错 —— 它不该成为主链路的必需依赖。
        self._turns = turns

    async def get(self, user_id: str, task_id: str) -> Optional[ConversationMemory]:
        return await self._memories.get(user_id, task_id)

    async def upsert(
        self,
        user_id: str,
        task_id: str,
        *,
        loop_stage: LoopStage,
        lead_agent: str,
        summary_delta: str = "",
    ) -> ConversationMemory:
        existing = await self._memories.get(user_id, task_id)
        summary = (existing.summary if existing else "") + summary_delta
        return await self._memories.upsert(
            ConversationMemory(
                id=existing.id if existing else f"mem_{uuid4().hex[:12]}",
                user_id=user_id,
                task_id=task_id,
                loop_stage=loop_stage,
                lead_agent=lead_agent,
                summary=summary,
                last_active_at=datetime.now(timezone.utc),
            )
        )

    async def list_by_user(self, user_id: str) -> list[ConversationMemory]:
        return await self._memories.list_by_user(user_id)

    async def record_turn(
        self,
        user_id: str,
        task_id: str,
        *,
        role: str,
        text: str,
        loop_stage: LoopStage,
        agent_id: str = "",
    ) -> ConversationTurn:
        turn = ConversationTurn(
            id=f"turn_{uuid4().hex[:12]}",
            user_id=user_id,
            task_id=task_id or None,
            role=role,  # type: ignore[arg-type]
            text=text,
            loop_stage=loop_stage,
            agent_id=agent_id,
            created_at=datetime.now(timezone.utc),
        )
        if self._turns is None:
            return turn
        return await self._turns.append(turn)

    async def list_turns(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationTurn]:
        if self._turns is None:
            return []
        return await self._turns.list_by_task(user_id, task_id, limit=limit)


__all__ = ["DefaultConversationMemoryService"]
