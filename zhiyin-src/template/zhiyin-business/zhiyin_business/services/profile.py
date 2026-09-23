"""画像服务实现。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import uuid4

from zhiyin_business.events import PROFILE_FIELD_UPDATED
from zhiyin_business.ports.blackboard import ProfileService
from zhiyin_data_sdk.repositories import ProfileRepository
from zhiyin_kernel.blackboard import Profile, ProfileField, ProfileGap
from zhiyin_kernel.enums import ProfileSource
from zhiyin_orchestration import DomainEvent, EventBus

logger = logging.getLogger(__name__)


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
        # 这是**新出现**的一类信息吗？
        #
        # 为什么要在这里判：影响面的判据是"资产声明的依赖字段 ∩ 变更字段"，
        # 而依赖清单是资产**生成那一刻**记下的。一个刚出现的字段不可能在那份清单里
        # （实测：报告生成后才导入的课表，改了它，报告不会被标成"待重算"），
        # 于是"画像里多了一整类信息"这件事对已有结论完全不可见。
        # 交给下游的判据只能是"这个字段对谁都是新的"，所以得在写画像的地方算出来 ——
        # 只有这里知道画像在写之前长什么样。
        #
        # ⚠️ 必须在 upsert **之前**读：写在后面的话读到的就是刚写进去的那条，
        # `is_new` 永远是假（实测：这条判据先写在后面，整条修复静默失效）。
        try:
            known = {item.key for item in await self._profiles.list_fields(user_id)}
        except Exception:  # noqa: BLE001 - 读旧画像失败不该让这次写入失败
            logger.warning("读取既有画像失败，新字段判定按否处理", exc_info=True)
            known = None
        is_new = known is not None and key not in known
        saved = await self._profiles.upsert_field(user_id, field)
        await self._event_bus.publish(
            DomainEvent(
                event_id=f"profile-{uuid4().hex[:12]}",
                event_type=PROFILE_FIELD_UPDATED,
                occurred_at=saved.updated_at,
                payload={
                    "user_id": user_id,
                    "field_key": key,
                    "is_new": is_new,
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
