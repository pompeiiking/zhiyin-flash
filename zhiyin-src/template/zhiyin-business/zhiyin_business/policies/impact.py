"""影响面传播规则（R-BIZ-012）。

核心规则：画像字段更新 → 只重算**受影响的**资产片段 → 版本 +1 → 写 diff。
禁止整篇重新生成。

本模块只回答"哪些资产受影响"（重算范围），执行重算的是资产服务 / Worker。
把范围判定与执行分开，是为了让"只重算受影响片段"这条口径可以被独立单测。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from zhiyin_kernel.blackboard import AssetVersion


class ImpactPolicy(ABC):
    """资产重算范围判定规则。"""

    @abstractmethod
    def select_affected(
        self,
        *,
        changed_profile_keys: Sequence[str],
        candidates: Sequence[AssetVersion],
    ) -> list[AssetVersion]:
        """从候选资产中挑出依赖命中变更字段的那些。

        `candidates` 是各资产类型的最新版本；未命中的资产必须原样保留，
        既不重算也不升版本。
        """
