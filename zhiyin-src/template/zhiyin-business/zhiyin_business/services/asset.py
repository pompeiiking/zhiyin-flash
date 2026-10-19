"""资产服务实现。"""

from __future__ import annotations

from zhiyin_business.services.unit_of_work import atomic_repository
from zhiyin_business.services.unit_of_work import transaction
from contextlib import asynccontextmanager
from functools import wraps

from collections import Counter, defaultdict
import re
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
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_orchestration import DomainEvent, EventBus


def asset_mutation(method):
    @wraps(method)
    async def call(self, user_id, *args, **kwargs):
        async with self.mutation_scope(user_id):
            return await method(self, user_id, *args, **kwargs)
    return call


class DefaultAssetService(AssetService):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        assets: AssetRepository,
        event_bus: EventBus,
        impact_policy: ImpactPolicy,
        student_state=None,
    ) -> None:
        self._student_state = student_state
        self._assets = assets
        self._event_bus = event_bus
        self._impact_policy = impact_policy

    @asynccontextmanager
    async def mutation_scope(self, user_id):
        async with self._assets.write_lock(user_id):
            async with transaction(self._assets):
                yield

    async def list_versions(self, user_id: str, asset_type: AssetType) -> list[AssetVersion]:
        return await self._assets.list_versions(user_id, asset_type)

    async def get_latest_version(
        self, user_id: str, asset_type: AssetType
    ) -> Optional[AssetVersion]:
        return await self._assets.get_latest_version(user_id, asset_type)

    async def propagate(
        self,
        user_id: str,
        changed_profile_keys: Sequence[str],
        *,
        mark_all: bool = False,
    ) -> list[AssetVersion]:
        """影响面传播：标出受影响的资产，未命中的不动。

        **只标记，不升版**（改口径，理由见下）。返回被标记的最新版本。

        `mark_all=True` 用于**新出现的字段**：它不可能出现在任何资产生成时记下的
        依赖清单里（清单是那一刻的画像快照），但"画像里多了一整类信息"确实让已有结论
        都值得重新看一遍。判"新不新"的地方在 `DefaultProfileService`，只有那里
        知道画像在写之前长什么样。

        原来的做法是"命中就升一版，并写一句「画像补了新信息，这一版跟着更新」"，
        而正文其实一个字都没重算（真正的重算在下一次进入该环节时由智能体链路完成）。
        实测后果有两个，都落在用户眼前：

          · 报告页的版本下拉里多出一版写着"跟着更新"，点开是**空白页**（那一版
            只有版本行、没有正文）；
          · 用户被告知"跟着改了"，打开一看没变 —— 这是最不该出现的一类信号：
            不报错，但说的是假的。

        现在版本号只在**真的重算并校验过**时才 +1（见 `_persist_stage_output`），
        画像一变只是把那一版标成"待重算"，并给出一句实话。用户下一次进入那个环节，
        重算发生、新版本落地、标记自然消失，同时有一句显式告知说清"这一版是重算过的"。
        """
        if mark_all:
            candidates = []
            for asset_type in (
                AssetType.REPORT,
                AssetType.DIRECTION_PLAN,
                AssetType.ACTION_PLAN,
            ):
                latest = await self._assets.get_latest_version(user_id, asset_type)
                if latest is not None:
                    candidates.append(latest)
            affected = candidates
        else:
            candidates = await self._assets.list_affected_assets(user_id, changed_profile_keys)
            affected = [
                item
                for item in candidates
                if self._impact_policy.select_affected(
                    changed_profile_keys=changed_profile_keys, candidates=[item]
                )
            ]
        # 依赖链是 profile → report → direction_plan → action_plan。
        # 只按画像字段命中的话，报告被标“待重算”后，方向/计划仍显示 false：
        # 用户会看到“报告过期、计划却是当前”，两页互相矛盾。上游一过期待，
        # 下游已有版本也一并标待核对（只标已有版本，不升版）。
        affected_types = {item.asset_type for item in affected}
        # 报告可能在本轮之前就已经是“待重算”（例如方向选择先标记过），
        # 这次画像变更没重新命中它，但下游仍然必须跟着待核对。
        if AssetType.REPORT not in affected_types:
            report_latest = await self._assets.get_latest_version(user_id, AssetType.REPORT)
            if report_latest is not None and report_latest.needs_recompute:
                affected_types.add(AssetType.REPORT)
        if AssetType.DIRECTION_PLAN not in affected_types:
            direction_latest = await self._assets.get_latest_version(
                user_id, AssetType.DIRECTION_PLAN
            )
            if direction_latest is not None and direction_latest.needs_recompute:
                affected_types.add(AssetType.DIRECTION_PLAN)
        downstream: list[AssetType] = []
        if AssetType.REPORT in affected_types:
            downstream.extend([AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN])
        if AssetType.DIRECTION_PLAN in affected_types:
            downstream.append(AssetType.ACTION_PLAN)
        for asset_type in downstream:
            if asset_type in affected_types:
                continue
            latest = await self._assets.get_latest_version(user_id, asset_type)
            if latest is not None:
                affected.append(latest)
                affected_types.add(asset_type)
        # 一句话说清"为什么这一版过期了"，用户看得懂，也不出现画像字段的英文键。
        reason = "画像补了新信息，这一版还是旧的，等你回到这一步我再重算"
        changed: list[AssetVersion] = []
        for stale in affected:
            marked = await self._assets.mark_needs_recompute(
                user_id, stale.asset_type, reason=reason
            )
            if marked is not None:
                changed.append(marked)
        # 这里**不发** `asset_version_changed`：没有新版本，说"版本变了"会让工作台
        # 与通知去追一条并不存在的新版。也不需要清读缓存 —— 正文没变，
        # "待重算"这个标记只有编排器会读（重算那一轮由它如实告知用户）。
        return changed

    async def mark_asset_stale(
        self, user_id: str, asset_type: AssetType, *, reason: str
    ) -> AssetVersion | None:
        """把某一类资产的最新一版标成待核对（不升版、不重算正文）。

        用于“用户做了一个不进画像、但会让旧结论失效的动作”，例如切换已选方向：
        报告里写的是上一个方向，必须让前端知道要重新核对，不能继续标“当前版本”。
        """
        return await self._assets.mark_needs_recompute(user_id, asset_type, reason=reason)

    @atomic_repository("_assets")
    async def save_version(
        self, user_id: str, draft: AssetUpdateDraft, *, snapshot_content=None, analysis_sources=None
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
        await self._save_snapshot(user_id, version, snapshot_content, analysis_sources)
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

    async def _save_snapshot(self, user_id, version, snapshot_content=None, analysis_sources=None):
        if self._student_state is None:
            return
        if snapshot_content is not None:
            content = snapshot_content
        elif version.asset_type == AssetType.DIRECTION_PLAN:
            content = [
                p.model_dump(mode="json") for p in await self._assets.list_direction_plans(user_id)
            ]
        elif version.asset_type == AssetType.ACTION_PLAN:
            plan = await self._assets.get_action_plan(user_id)
            content = plan.model_dump(mode="json") if plan else None
        else:
            return

        def change(s):
            s.setdefault("asset_snapshots", {})[f"{version.asset_type.value}:{version.version}"] = {
                "asset_type": version.asset_type.value,
                "version": version.version,
                "created_at": version.created_at.isoformat(),
                "content": content,
            }
            return s

        await self._student_state.update(user_id, change)
        from zhiyin_business.services.analysis_access import current_scope
        scope = current_scope(user_id)
        if scope is not None and snapshot_content is not None:
            kind = {AssetType.REPORT: "report", AssetType.DIRECTION_PLAN: "directions",
                    AssetType.ACTION_PLAN: "plan"}[version.asset_type]
            await scope.record(kind, content, sources=analysis_sources)
            await scope.record("version", version, sources=analysis_sources)

    async def get_report(self, user_id: str, version: Optional[int] = None) -> Optional[Report]:
        return await self._assets.get_report(user_id, version)

    # ---------- 写侧：环节产出 → 资产正文 ----------
    #
    # 这三个方法是"会话里生成出来的东西"唯一的落库入口。少了它们，
    # 模型已经把 15 维诊断生成并校验过了，却没有任何地方存下来 ——
    # 报告页与工作台恒为空，而看起来像"功能没做"。

    @asset_mutation
    async def save_report(
        self,
        user_id: str,
        report: Report,
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        version = await self._next_version(user_id, AssetType.REPORT)
        saved = report.model_copy(update={"user_id": user_id, "version": version})
        await self._assets.save_report(saved)
        return await self.save_version(
            user_id,
            AssetUpdateDraft(
                asset_type=AssetType.REPORT,
                depends_on_profile_keys=list(depends_on_profile_keys),
                diff_from_previous=diff_from_previous,
                reason="环节产出",
            ),
            snapshot_content=saved.model_dump(mode="json"),
        )

    @asset_mutation
    async def save_direction_plans(
        self,
        user_id: str,
        plans: Sequence[DirectionPlan],
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        # 方向名不是“记一件事”：曾经把“明早九点 · 实训材料提醒”写成了主攻方向。
        # 明显的提醒/日程文本在落库前拦掉，避免再污染方向方案与职业探索。
        invalid = [
            plan.name
            for plan in plans
            if re.search(r"(提醒|闹钟|明早|今天|明天|上午|下午|晚上|周[一二三四五六日天])", plan.name or "")
            and not re.search(r"(方向|运营|工程|设计|教师|考研|就业|升学|产品|分析|开发)", plan.name or "")
        ]
        if invalid:
            raise InvalidRequest("方向方案里混进了日程/提醒内容，请重新生成方向后再保存。")
        await self._assets.save_direction_plans(user_id, list(plans))
        return await self.save_version(
            user_id,
            AssetUpdateDraft(
                asset_type=AssetType.DIRECTION_PLAN,
                depends_on_profile_keys=list(depends_on_profile_keys),
                diff_from_previous=diff_from_previous,
                reason="环节产出",
            ),
            snapshot_content=[p.model_dump(mode="json") for p in plans],
        )

    @asset_mutation
    async def save_action_plan(
        self,
        user_id: str,
        plan: ActionPlan,
        *,
        depends_on_profile_keys: Sequence[str] = (),
        diff_from_previous: Optional[str] = None,
    ) -> AssetVersion:
        previous = await self._assets.get_action_plan(user_id)
        from zhiyin_business.services.analysis_access import ALL_SOURCES, current_scope
        scope = current_scope(user_id)
        # Preserved phase/task metadata can itself contain old derived text.
        # Keep that user data, but do not falsely label the merged plan as clean.
        analysis_sources = (ALL_SOURCES if scope and previous is not None
                            and not scope.allows("plan", previous) else None)
        merged = self._inherit_task_state(previous, plan)
        if previous is not None:
            merged = merged.model_copy(update={"id": previous.id})
        # 内容没变就不升版（实测 ZY-07：单账号攒出 18 个行动计划版本，
        # 差异说明还都是同一句「④ 行动产出：阶段与任务」）。
        # 升版是"内容重算"的单位：用户回一句"做完了"，改的是状态，不该产生新版本。
        if previous is not None and merged == previous:
            latest = await self._assets.get_latest_version(user_id, AssetType.ACTION_PLAN)
            if latest is not None:
                return latest
        await self._assets.save_action_plan(user_id, merged)
        return await self.save_version(
            user_id,
            AssetUpdateDraft(
                asset_type=AssetType.ACTION_PLAN,
                depends_on_profile_keys=list(depends_on_profile_keys),
                diff_from_previous=diff_from_previous,
                reason="环节产出",
            ),
            snapshot_content=merged.model_dump(mode="json"),
            analysis_sources=analysis_sources,
        )

    @staticmethod
    def _inherit_task_state(previous: Optional[ActionPlan], plan: ActionPlan) -> ActionPlan:
        """重排计划时继承已有完成状态（按稳定任务 id 对齐）。

        实测（ZY-04 / ZY-03）：行动环节每轮都会重写整份计划，`done` 于是被重置 ——
        用户明明部署完、README 写完、同学也点开过了，页面仍显示 0/11。
        计划内容重算是允许的，但「这件事我已经做完了」是用户的事实，不随重算消失。
        因此：同 id 的任务若此前已完成，这里把 `done` / `done_at` 带过来；
        计划里新出现的任务按未完成计，旧计划不再包含的任务自然消失。
        """
        if previous is None:
            return plan
        previous_tasks = {
            task.id: task for phase in previous.phases for task in phase.tasks if task.id
        }
        # 旧计划可能使用随机 id 或旧的位置哈希。只有两侧都唯一的同名任务
        # 才能按文字对齐；重复任务必须按 id，避免把另一件事误标为完成。
        previous_by_text = defaultdict(list)
        for phase in previous.phases:
            for task in phase.tasks:
                previous_by_text[(phase.name.strip(), task.text.strip())].append(task)
        new_counts = Counter(
            (phase.name.strip(), task.text.strip()) for phase in plan.phases for task in phase.tasks
        )
        phases = []
        changed = False
        for phase in plan.phases:
            tasks = []
            for task in phase.tasks:
                old = previous_tasks.get(task.id) if task.id else None
                key = (phase.name.strip(), task.text.strip())
                candidates = previous_by_text.get(key, [])
                if old is None and new_counts[key] == 1 and len(candidates) == 1:
                    old = candidates[0]
                updates = {}
                if old is not None:
                    updates.update(
                        {
                            key: getattr(old, key)
                            for key in (
                                "status",
                                "progress",
                                "waiting_reason",
                                "scheduled_at",
                                "estimated_minutes",
                                "parent_task_id",
                            )
                        }
                    )
                    if old.id and old.id != task.id:
                        updates["id"] = old.id
                    if old.done:
                        updates.update(done=True, done_at=old.done_at)
                if updates:
                    tasks.append(task.model_copy(update=updates))
                    changed = True
                else:
                    tasks.append(task)
            old_phase = next(
                (
                    p
                    for p in previous.phases
                    if (phase.id and p.id == phase.id) or p.name == phase.name
                ),
                None,
            )
            metadata = (
                {
                    k: getattr(old_phase, k)
                    for k in (
                        "id",
                        "depends_on",
                        "starts_at",
                        "ends_at",
                        "blocking_conditions",
                        "handoff_requirements",
                    )
                }
                if old_phase
                else {}
            )
            if metadata:
                changed = True
            phases.append(phase.model_copy(update={**metadata, "tasks": tasks}))
        return plan.model_copy(update={"phases": phases}) if changed else plan

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

    @asset_mutation
    async def select_direction_plan(self, user_id: str, plan_id: str) -> DirectionPlan:
        return await self._assets.select_direction_plan(user_id, plan_id)

    @asset_mutation
    async def mark_action_task_done(
        self, user_id: str, task_id: str, *, done: bool = True
    ) -> ActionPlan:
        return await self._assets.mark_task_done(user_id, task_id, done=done)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


__all__ = ["DefaultAssetService"]
