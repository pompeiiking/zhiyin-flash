"""资产版本与影响面读写（asset_version + report / direction_plan / action_plan）。

影响面传播（R-BIZ-012）：
画像字段更新 → list_affected_assets 找出依赖该字段的资产 → 只重算受影响片段
→ save_version(version + 1) → 写 diff。禁止整篇重新生成。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from zhiyin_kernel.assets import (
    ActionPlan,
    DirectionPlan,
    Report,
)
from zhiyin_kernel.blackboard import AssetVersion
from zhiyin_kernel.enums import AssetType


class AssetRepository(ABC):
    """资产 Repository。版本与内容分开管理。"""

    # ---------- 版本 ----------

    @abstractmethod
    async def get_latest_version(self, user_id: str, asset_type: AssetType) -> Optional[AssetVersion]:
        """取某类资产的最新版本记录。"""

    @abstractmethod
    async def list_versions(self, user_id: str, asset_type: AssetType) -> list[AssetVersion]:
        """列出某类资产的全部历史版本，用于工作台展示历史与 diff。"""

    @abstractmethod
    async def save_version(self, version: AssetVersion) -> AssetVersion:
        """保存一次新版本记录。"""

    @abstractmethod
    async def list_affected_assets(
        self, user_id: str, profile_keys: Sequence[str]
    ) -> list[AssetVersion]:
        """找出依赖命中画像字段的最新资产版本。影响面传播的入口。"""

    # ---------- 诊断报告 ----------

    @abstractmethod
    async def get_report(self, user_id: str, version: Optional[int] = None) -> Optional[Report]:
        """读取报告全文。version 为空表示最新版。"""

    @abstractmethod
    async def save_report(self, report: Report) -> Report:
        """保存报告。"""

    # ---------- 方向方案 ----------

    @abstractmethod
    async def list_direction_plans(self, user_id: str) -> list[DirectionPlan]:
        """读取当前主攻/平行/保底三套方案。"""

    @abstractmethod
    async def save_direction_plans(self, user_id: str, plans: list[DirectionPlan]) -> None:
        """整体保存方案组（覆盖式，保证三套一致性）。"""

    @abstractmethod
    async def select_direction_plan(self, user_id: str, plan_id: str) -> DirectionPlan:
        """做出可撤回的选择。"""

    # ---------- 行动计划 ----------

    @abstractmethod
    async def get_action_plan(self, user_id: str) -> Optional[ActionPlan]:
        """读取行动计划。"""

    @abstractmethod
    async def save_action_plan(self, user_id: str, plan: ActionPlan) -> ActionPlan:
        """保存行动计划。"""

    @abstractmethod
    async def mark_task_done(
        self, user_id: str, task_id: str, *, done: bool = True
    ) -> ActionPlan:
        """勾掉 / 取消勾选一个任务，返回更新后的计划。

        `done=False` 是"勾错了要撤回"。只支持单向勾选的话，用户点错一次就再也
        回不去 —— 而行动环节的验收锚点恰恰是"任务勾得动"，不包括"勾错了只能认"。
        """
