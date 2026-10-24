"""报告/方向/计划版本记录的视图装配守卫。

背景（2026-10-24 排查"版本记录有问题"）：画像变更把**当时**的最新版标成
待重算；此后重算只新增版本行，旧行上的 `needs_recompute` 没有任何机制清除，
版本记录里于是越积越多"待重新核对"的历史行。收口点在视图装配：
标记只允许出现在当前版本上。
"""

from __future__ import annotations

from datetime import datetime, timezone

from zhiyin_api.facade.application import _without_resolved_stale
from zhiyin_kernel.blackboard import AssetVersion
from zhiyin_kernel.enums import AssetType


def _version(number: int, *, stale: bool = False) -> AssetVersion:
    return AssetVersion(
        id=f"av_{number}",
        user_id="a",
        asset_type=AssetType.REPORT,
        version=number,
        created_at=datetime.now(timezone.utc),
        needs_recompute=stale,
        recompute_reason="画像补了新信息，这一版还是旧的" if stale else "",
    )


def test_history_rows_drop_the_stale_marker_only_current_keeps_it() -> None:
    latest = 3
    assert _without_resolved_stale(_version(3, stale=True), latest).needs_recompute is True
    assert _without_resolved_stale(_version(2, stale=True), latest).needs_recompute is False
    assert _without_resolved_stale(_version(2, stale=True), latest).recompute_reason == ""
    # 本来就干净的行原样返回（同一对象，不做无谓拷贝）
    fresh = _version(1)
    assert _without_resolved_stale(fresh, latest) is fresh


def test_stale_marker_survives_when_there_is_no_newer_version() -> None:
    """没有更高版本时（空列表防御 / 单行列表），标记按当前版本保留。"""
    only = _version(1, stale=True)
    assert _without_resolved_stale(only, 1).needs_recompute is True
    assert _without_resolved_stale(only, None).needs_recompute is True
