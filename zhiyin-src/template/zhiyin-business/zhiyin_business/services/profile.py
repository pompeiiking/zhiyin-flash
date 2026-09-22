"""画像服务实现。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import uuid4

from zhiyin_business.events import PROFILE_FIELD_UPDATED
from zhiyin_business.ports.blackboard import ProfileService
from zhiyin_data_sdk.repositories import ProfileRepository
from zhiyin_kernel.blackboard import Profile, ProfileField, ProfileGap
from zhiyin_kernel.enums import ProfileSource
from zhiyin_orchestration import DomainEvent, EventBus


class DefaultProfileService(ProfileService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, profiles: ProfileRepository, event_bus: EventBus) -> None:
        self._profiles = profiles
        self._event_bus = event_bus

    async def get(self, user_id: str) -> Optional[Profile]:
        return await self._profiles.get(user_id)

    async def get_fields(
        self, user_id: str, keys: Optional[Sequence[str]] = None
    ) -> list[ProfileField]:
        return await self._profiles.list_fields(user_id, keys)

    async def get_gaps(self, user_id: str) -> list[ProfileGap]:
        return await self._profiles.list_gaps(user_id)

    async def update_field(
        self,
        user_id: str,
        key: str,
        value: object,
        *,
        confidence: float,
        source: str,
        label: str = "",
        evidence: Optional[list[str]] = None,
    ) -> ProfileField:
        field = ProfileField(
            key=key,
            label=label,
            value=value,
            confidence=confidence,
            source=ProfileSource(source),
            evidence=evidence or [],
            updated_at=datetime.now(timezone.utc),
        )
        saved = await self._profiles.upsert_field(user_id, field)
        await self._event_bus.publish(
            DomainEvent(
                event_id=f"profile-{uuid4().hex[:12]}",
                event_type=PROFILE_FIELD_UPDATED,
                occurred_at=saved.updated_at,
                payload={
                    "user_id": user_id,
                    "field_key": key,
                    "confidence": confidence,
                    "source": saved.source.value,
                },
            )
        )
        return saved

    async def replace_gaps(self, user_id: str, gaps: list[ProfileGap]) -> None:
        await self._profiles.replace_gaps(user_id, gaps)

    async def drop_field(self, user_id: str, key: str) -> None:
        """删掉一个画像字段（撤销授权时用）。"""
        await self._profiles.delete_field(user_id, key)

    async def overall_confidence(self, user_id: str) -> float:
        fields = await self._profiles.list_fields(user_id)
        if not fields:
            return 0.0
        return sum(field.confidence for field in fields) / len(fields)


__all__ = ["DefaultProfileService"]
