"""主动干预默认规则实现。"""

from __future__ import annotations

from datetime import datetime, timedelta

from zhiyin_business.policies.intervention import InterventionPolicy


class ThresholdInterventionPolicy(InterventionPolicy):
    """按停滞阈值、冷却期与打扰上限判断是否允许干预。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        stall_threshold_days: int,
        cooldown_hours: int,
        max_notifications_per_window: int,
        window_days: int,
    ) -> None:
        self._stall_threshold_days = stall_threshold_days
        self._cooldown_hours = cooldown_hours
        self._max_notifications = max_notifications_per_window
        self._window_days = window_days

    def should_intervene(
        self,
        *,
        days_inactive: int,
        last_notified_at: datetime | None,
        notifications_in_window: int,
        now: datetime,
    ) -> bool:
        if days_inactive < self._stall_threshold_days:
            return False
        if notifications_in_window >= self._max_notifications:
            return False
        if last_notified_at is not None:
            elapsed = now - last_notified_at
            if elapsed < timedelta(hours=self._cooldown_hours):
                return False
        return True


__all__ = ["ThresholdInterventionPolicy"]
