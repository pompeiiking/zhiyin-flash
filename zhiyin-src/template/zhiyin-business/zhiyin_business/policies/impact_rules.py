"""影响面传播默认规则实现。"""

from __future__ import annotations

from typing import Sequence

from zhiyin_business.policies.impact import ImpactPolicy
from zhiyin_kernel.blackboard import AssetVersion


class DependencyImpactPolicy(ImpactPolicy):
    """命中依赖字段的资产才进入重算范围。"""

    IMPLEMENTATION_STATUS = "wired"

    def select_affected(
        self,
        *,
        changed_profile_keys: Sequence[str],
        candidates: Sequence[AssetVersion],
    ) -> list[AssetVersion]:
        changed = set(changed_profile_keys)
        return [
            item
            for item in candidates
            if changed & set(item.depends_on_profile_keys)
        ]


__all__ = ["DependencyImpactPolicy"]
