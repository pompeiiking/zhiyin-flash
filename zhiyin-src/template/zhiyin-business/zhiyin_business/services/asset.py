"""资产服务实现。"""

from __future__ import annotations

from typing import Optional, Sequence
from uuid import uuid4

from zhiyin_business.contracts.common import AssetUpdateDraft
from zhiyin_business.events import ASSET_VERSION_CHANGED
from zhiyin_business.policies.impact import ImpactPolicy
from zhiyin_business.ports.blackboard import AssetService
from zhiyin_data_sdk.repositories import AssetRepository
from zhiyin_kernel.assets import ActionPlan, DirectionPlan, Report
from zhiyin_kernel.blackboard import AssetVersion
from zhiyin_kernel.enums import AssetType
from zhiyin_orchestration import DomainEvent, EventBus


class DefaultAssetService(AssetService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        assets: AssetRepository,
        event_bus: EventBus,
        impact_policy: ImpactPolicy,
    ) -> None:
        self._assets = assets
        self._event_bus = event_bus
        self._impact_policy = impact_policy

    async def list_versions(
        self, user_id: str, asset_type: AssetType
    ) -> list[AssetVersion]:
        return await self._assets.list_versions(user_id, asset_type)

    async def propagate(
        self, user_id: str, changed_profile_keys: Sequence[str]
    ) -> list[AssetVersion]:
        """影响面传播：只重算受影响片段（版本 +1），未命中的资产不动。

        P0 的"重算"= 增量升版并写 diff 说明（真正的正文重生成由智能体链路
        在对应环节完成）；本方法的职责边界是"什么时候升版、升哪些"。
        """
        candidates = await self._assets.list_affected_assets(
            user_id, changed_profile_keys
        )
        affected = [
            item
            for item in candidates
            if self._impact_policy.select_affected(
                changed_profile_keys=changed_profile_keys, candidates=[item]
            )
        ]
        changed: list[AssetVersion] = []
        for stale in affected:
            changed.append(
                await self.save_version(
                    user_id,
                    AssetUpdateDraft(
                        asset_type=stale.asset_type,
                        depends_on_profile_keys=stale.depends_on_profile_keys,
                        # 这句话会出现在报告页的版本历史里，是给用户看的：
                        # 不列画像字段的内部键（`major` / `skills` 这类英文标识），
                        # 也不写"增量重算"这种只有我们知道什么意思的词。
                        diff_from_previous=(
                            "画像补了新信息，这一版跟着更新"
                            f"（上一版是第 {stale.version} 版）"
                        ),
                        reason="影响面传播",
                    ),
                )
            )
        return changed

    async def save_version(
        self, user_id: str, draft: AssetUpdateDraft
    ) -> AssetVersion:
        latest = await self._assets.get_latest_version(user_id, draft.asset_type)
        version = await self._assets.save_version(
            AssetVersion(
                id=f"av_{uuid4().hex[:12]}",
                user_id=user_id,
                asset_type=draft.asset_type,
                version=(latest.version + 1) if latest else 1,
                created_at=_now(),
                depends_on_profile_keys=draft.depends_on_profile_keys,
                diff_from_previous=draft.diff_from_previous,
            )
        )
        await self._event_bus.publish(
            DomainEvent(
                event_id=f"asset-{version.id}",
                event_type=ASSET_VERSION_CHANGED,
                occurred_at=version.created_at,
                payload={
                    "user_id": user_id,
                    "asset_type": version.asset_type.value,
                    "asset_id": version.id,
                    "to_version": version.version,
                    "diff_from_previous": version.diff_from_previous,
                },
            )
        )
        return version

    async def get_report(
        self, user_id: str, version: Optional[int] = None
    ) -> Optional[Report]:
        return await self._assets.get_report(user_id, version)

    # ---------- 写侧：环节产出 → 资产正文 ----------
    #
    # 这三个方法是"会话里生成出来的东西"唯一的落库入口。少了它们，
    # 模型已经把 15 维诊断生成并校验过了，却没有任何地方存下来 ——
    # 报告页与工作台恒为空，而看起来像"功能没做"。

    async def save_report(
        self,
        user_id: str,
        report: Report,
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        version = await self._next_version(user_id, AssetType.REPORT)
        await self._assets.save_report(
            report.model_copy(update={"user_id": user_id, "version": version})
        )
        return await self.save_version(
            user_id,
            AssetUpdateDraft(
                asset_type=AssetType.REPORT,
                depends_on_profile_keys=list(depends_on_profile_keys),
                diff_from_previous=diff_from_previous,
                reason="环节产出",
            ),
        )

    async def save_direction_plans(
        self,
        user_id: str,
        plans: Sequence[DirectionPlan],
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        await self._assets.save_direction_plans(user_id, list(plans))
        return await self.save_version(
            user_id,
            AssetUpdateDraft(
                asset_type=AssetType.DIRECTION_PLAN,
                depends_on_profile_keys=list(depends_on_profile_keys),
                diff_from_previous=diff_from_previous,
                reason="环节产出",
            ),
        )

    async def save_action_plan(
        self,
        user_id: str,
        plan: ActionPlan,
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        await self._assets.save_action_plan(user_id, plan)
        return await self.save_version(
            user_id,
            AssetUpdateDraft(
                asset_type=AssetType.ACTION_PLAN,
                depends_on_profile_keys=list(depends_on_profile_keys),
                diff_from_previous=diff_from_previous,
                reason="环节产出",
            ),
        )

    async def _next_version(self, user_id: str, asset_type: AssetType) -> int:
        """下一个版本号。

        口径只有这一处：正文的 `version` 与版本行的 `version` 必须由同一个算式得出，
        否则报告页按正文显示的版本和工作台按版本行显示的历史会对不上。
        """
        latest = await self._assets.get_latest_version(user_id, asset_type)
        return (latest.version + 1) if latest else 1

    async def list_direction_plans(self, user_id: str) -> list[DirectionPlan]:
        return await self._assets.list_direction_plans(user_id)

    async def get_action_plan(self, user_id: str) -> Optional[ActionPlan]:
        return await self._assets.get_action_plan(user_id)

    # ---------- 写侧：用户对资产做的动作（不是环节产出的重新生成） ----------
    #
    # ③ 选一套方案、④ 勾掉一个任务 —— 这两件事改的是**已有资产的状态**，
    # 不产生新版本（版本是"内容重算"的单位，不是"用户点了一下"的单位）。
    # 仓储层早就实现了这两个动作，缺的是往上的出口；没有出口时，
    # 界面上"选它"只能是本地状态，刷新即消失。

    async def select_direction_plan(self, user_id: str, plan_id: str) -> DirectionPlan:
        return await self._assets.select_direction_plan(user_id, plan_id)

    async def mark_action_task_done(
        self, user_id: str, task_id: str, *, done: bool = True
    ) -> ActionPlan:
        return await self._assets.mark_task_done(user_id, task_id, done=done)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


__all__ = ["DefaultAssetService"]
