"""行为日志服务实现。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import uuid4

from zhiyin_business.contracts.common import BehaviorEventDraft
from zhiyin_business.events import BEHAVIOR_LOGGED
from zhiyin_business.ports.blackboard import BehaviorService
from zhiyin_data_sdk.repositories import BehaviorRepository
from zhiyin_kernel.blackboard import BehaviorLog
from zhiyin_kernel.enums import BehaviorEventType
from zhiyin_orchestration import DomainEvent, EventBus


class DefaultBehaviorService(BehaviorService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, behaviors: BehaviorRepository, event_bus: EventBus) -> None:
        self._behaviors = behaviors
        self._event_bus = event_bus

    async def log(self, user_id: str, draft: BehaviorEventDraft) -> BehaviorLog:
        saved = await self._behaviors.append(
            BehaviorLog(
                id=f"bhv_{uuid4().hex[:12]}",
                user_id=user_id,
                event_type=draft.event_type,
                occurred_at=datetime.now(timezone.utc),
                payload=draft.payload,
                related_asset_ids=draft.related_asset_ids,
            )
        )
        await self._event_bus.publish(
            DomainEvent(
                event_id=f"behavior-{saved.id}",
                event_type=BEHAVIOR_LOGGED,
                occurred_at=saved.occurred_at,
                payload={
                    "user_id": user_id,
                    "event_type": saved.event_type.value,
                    "payload": saved.payload,
                },
            )
        )
        return saved

    async def recent(
        self,
        user_id: str,
        *,
        event_types: Optional[Sequence[BehaviorEventType]] = None,
        limit: int = 50,
    ) -> list[BehaviorLog]:
        return await self._behaviors.list_by_user(
            user_id, event_types=event_types, limit=limit
        )

    async def days_since_last(
        self, user_id: str, event_type: BehaviorEventType
    ) -> Optional[int]:
        last = await self._behaviors.last_occurred_at(user_id, event_type)
        if last is None:
            return None
        return max((datetime.now(timezone.utc) - last).days, 0)


__all__ = ["DefaultBehaviorService"]
