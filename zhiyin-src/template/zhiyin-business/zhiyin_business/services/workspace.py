"""工作台聚合服务实现（读侧）。

读写路径分离的读侧：**本类不写任何状态、不发任何事件**。
允许轻微陈旧，`build_view` 用 `asyncio.gather` 并发聚合，单项失败降级为空值，
不让一个缺口拖垮整个工作台。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from zhiyin_business.ports.blackboard import (
    AssetService,
    BehaviorService,
    ConversationMemoryService,
    ProfileService,
)
from zhiyin_business.ports.workspace import (
    DependencyEdge,
    StagePanel,
    WorkspaceService,
    WorkspaceView,
)
from zhiyin_business.policies.collection import plan_collection
from zhiyin_business.policies.layout import evaluate, state_of
from zhiyin_business.ports.registry import RegistryService
from zhiyin_data_sdk.repositories import TaskSessionRepository
from zhiyin_kernel.assets import Report
from zhiyin_kernel import dynamic_config
from zhiyin_kernel.blackboard import TaskSession
from zhiyin_kernel.enums import AssetType, LoopStage

_log = logging.getLogger(__name__)

# 面板标题来自动态资源（`data/registry/stages.json`）：这里原来也写了一份和
# api mapper 一字不差的表，三处重复就是这么来的。现在只在库里有一份，
# `list_stages()` 读它；读不到时标题留空，让"缺配置"露出来，
# 而不是显示一个可能已经过期的旧名字。
#
# 环节 → 资产类型的映射**同样只在 stages.json 里有一份**（`asset` 字段）；
# 下面的常量只用于"库里没配"时的兜底，不是第二事实来源。
_STAGE_ASSET: dict[LoopStage, AssetType] = {
    LoopStage.DIAGNOSE: AssetType.REPORT,
    LoopStage.DECIDE: AssetType.DIRECTION_PLAN,
    LoopStage.ACT: AssetType.ACTION_PLAN,
}


async def _or(awaitable: Any, empty: Any, *, label: str) -> Any:
    """单项读失败 → 用空值顶上，并留一条日志。

    工作台是"允许轻微陈旧"的读侧：一个缺口不该让整页打不开。但**不静默** ——
    降级必须留痕，否则"这块一直是空的"会被当成产品设计。
    """
    try:
        return await awaitable
    except Exception:  # noqa: BLE001 - 聚合读侧的降级兜底
        _log.warning("工作台聚合：%s 读取失败，已降级为空值", label, exc_info=True)
        return empty


async def _gather_or(*awaitables: Any, empty: tuple, labels: tuple[str, ...]) -> tuple:
    """并发聚合 + 逐项降级：第 i 项失败就用 `empty[i]` 顶上。"""
    results = await asyncio.gather(*awaitables, return_exceptions=True)
    out: list[Any] = []
    for index, item in enumerate(results):
        if isinstance(item, BaseException):
            label = labels[index] if index < len(labels) else f"第 {index} 项"
            _log.warning("工作台聚合：%s 读取失败，已降级为空值（%s）", label, item)
            out.append(empty[index])
        else:
            out.append(item)
    return tuple(out)


class DefaultWorkspaceService(WorkspaceService):
    """工作台聚合默认实现（读侧）。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        profiles: ProfileService,
        assets: AssetService,
        memories: ConversationMemoryService,
        behaviors: BehaviorService,
        notes: "Any | None" = None,
        academic_records: "Any | None" = None,
        sessions: TaskSessionRepository | None = None,
        registry: "RegistryService | None" = None,
    ) -> None:
        self._profiles = profiles
        self._assets = assets
        self._memories = memories
        self._behaviors = behaviors
        # 用户自己写下的东西：采集策略要引用他的原话，只存在浏览器里就读不到
        self._notes = notes
        # 学生自己导入的课表与成绩单（只读）：导入过就展示，没导入就如实说没有
        self._academic_records = academic_records
        self._sessions = sessions
        # 动态资源读侧：气泡编排策略从它取（策略在库里，不在前端）
        self._registry = registry
        # 采集规则读一次就够；它是一个进程内的读侧缓存，不是状态
        self._rules_cache: list[Any] | None = None

    async def build_view(self, user_id: str) -> WorkspaceView:
        # `return_exceptions=True` 是本方法的契约要求（见模块 docstring）：
        # 工作台是聚合读侧，单项失败要降级成空值，不能让一个缺口把整页打成 500。
        # 之前没传它，任一子查询抛错都会中断整个 gather。
        profile, report_versions, plan_versions, action_versions = await _gather_or(
            self._profiles.get(user_id),
            self._assets.list_versions(user_id, AssetType.REPORT),
            self._assets.list_versions(user_id, AssetType.DIRECTION_PLAN),
            self._assets.list_versions(user_id, AssetType.ACTION_PLAN),
            empty=(None, [], [], []),
            labels=("画像", "报告版本", "方向方案版本", "行动计划版本"),
        )
        latest = {
            AssetType.REPORT: report_versions[-1] if report_versions else None,
            AssetType.DIRECTION_PLAN: plan_versions[-1] if plan_versions else None,
            AssetType.ACTION_PLAN: action_versions[-1] if action_versions else None,
        }
        report: Report | None = None
        if latest[AssetType.REPORT] is not None:
            report = await self._assets.get_report(
                user_id, latest[AssetType.REPORT].version
            )
        direction_plans, action_plan = await _gather_or(
            self._assets.list_direction_plans(user_id),
            self._assets.get_action_plan(user_id),
            empty=([], None),
            labels=("方向方案", "行动计划"),
        )
        memories = await _or(self._memories.list_by_user(user_id), [], label="会话记忆")

        panels = await self._build_panels(
            user_id, profile, report, latest, direction_plans, action_plan, memories
        )
        dependencies = self._build_dependencies(latest)

        # 当前所处环节取最近一次会话记忆 —— 采集策略要按"现在走到哪"排优先级：
        # 冲刺阶段最缺的是毕业时间，探索阶段最缺的是价值取向。
        current_stage = (
            max(memories, key=lambda m: m.last_active_at).loop_stage.value
            if memories
            else None
        )
        collection = plan_collection(
            profile,
            stage=current_stage,
            rules=self._collection_rules(),
            notes=await self._note_texts(user_id),
            signals=self._user_signals(),
            available_sources=self._available_sources(),
        )

        # 气泡顺序：把现状交给策略算，前端只负责摆。
        # `ask_targets_chat` 用"还没有今天该做的那件事"近似 ——
        # 那种情况下前端推的下一步一定是对话（要嘛追问、要嘛让你开口）。
        # 真正的 ask 目标要等推理侧回包，属于后续把编排前移一步的事。
        action_text = next(
            (p.evaluation for p in panels if p.stage is LoopStage.ACT), ""
        )
        layout_state = state_of(
            profile_fields=len(profile.fields) if profile else 0,
            profile_gaps=len(profile.gaps) if profile else 0,
            collection=collection,
            action_text=action_text,
            direction_plans=len(direction_plans),
            ask_target="chat" if not action_text.strip() else "",
            # 已经走到分析（② 及以后）：报告 / 方案 / 计划任一存在，或当前环节已越过采集。
            reached_analysis=(
                report is not None
                or bool(direction_plans)
                or action_plan is not None
                or (current_stage or "") in {"diagnose", "decide", "act", "review"}
            ),
        )

        return WorkspaceView(
            user_id=user_id,
            profile=profile,
            report=report,
            report_versions=report_versions,
            direction_plans=direction_plans,
            action_plan=action_plan,
            track_events=[],
            panels=panels,
            dependencies=dependencies,
            profile_coverage=self._coverage(profile),
            profile_confidence=await self._profiles.overall_confidence(user_id),
            # 画像字段的展示名：和采集清单同一份来源（动态资源的采集规则表）。
            # 界面上摆 `major` 这种内部键给用户看，等于把实现细节漏到产品里。
            profile_labels={
                spec.key: (spec.label or spec.key)
                for spec in (self._collection_rules() or ())
            },
            collection=collection,
            academic=await self._academic_snapshot(user_id),
            layout=self._layout(layout_state),
        )

    def _layout(self, state):
        """按快照里的编排策略算顺序；策略缺失时返回空表（前端退回自己的兜底）。"""
        policy = dynamic_config.snapshot().layout
        return evaluate(policy, state) if policy is not None else []

    def _stage_titles(self) -> dict[str, str]:
        """环节标题（`环节id → 标题`），来自快照；没有就返回空表。

        返回**空表**而不是旧名字：标题是给用户看的，
        显示一个可能已经改过的名字，比暂时没有名字更糟 —— 后者会被发现。
        """
        return {
            spec.id: (spec.title or spec.label or "")
            for spec in dynamic_config.snapshot().stages
        }

    def _collection_rules(self):
        """采集规则（快照）。为空时返回 None —— 策略层会退回内置表。"""
        return list(dynamic_config.snapshot().collection_rules) or None

    def _user_signals(self):
        """用户信号线索表（同一份快照）。它和采集规则是一对，要一起热重载。"""
        return list(dynamic_config.snapshot().user_signals) or None

    def _available_sources(self) -> tuple[str, ...]:
        """现在真的取得动数据的源头 —— 跟着装配实况走，不跟着注释走。

        `academic`（课表与成绩）现在是**学生自己导入**：不需要接入任何外部系统，
        所以它永远可用 —— 采集清单里这两条因此是"导入一次就有"，而不是"暂时补不了"。
        """
        return ("chsi", "conversation", "academic")

    async def _academic_snapshot(self, user_id: str):
        """他的课表与成绩单。

        读不到 / 没授权就返回 None —— 界面据此说"还没授权教务系统"，
        而不是渲染一张空课表（空课表和"这学期没课"长得一样，用户分不出来）。
        """
        if self._academic_records is None:
            return None
        try:
            return await self._academic_records.get(user_id)
        except Exception:
            _log.exception("读取教务系统快照失败：工作台按未授权处理")
            return None

    async def _note_texts(self, user_id: str) -> list[str]:
        """他自己写下的话。

        读不到就返回空表，**不编也不猜**：这里一旦退回某个兜底文案，
        回执里就会出现他从没写过的话 —— 那比"这次没有额外理由"更糟。
        """
        if self._notes is None:
            return []
        try:
            return await self._notes.texts(user_id)
        except Exception:
            _log.exception("读取用户自建内容失败：采集策略按没有信号处理")
            return []

    async def list_sessions_summary(self, user_id: str) -> list[StagePanel]:
        memories = await self._memories.list_by_user(user_id)
        titles = self._stage_titles()
        return [
            StagePanel(
                stage=memory.loop_stage,
                title=titles.get(memory.loop_stage.value, ""),
                evaluation=memory.summary[:80],
                updated_at=memory.last_active_at,
            )
            for memory in memories
        ]

    async def list_sessions(self, user_id: str) -> list[TaskSession]:
        if self._sessions is None:
            return []
        return list(await self._sessions.list_by_user(user_id))

    # ---------- 内部聚合 ----------

    async def _build_panels(
        self,
        user_id: str,
        profile,
        report: Report | None,
        latest: dict[AssetType, object],
        direction_plans,
        action_plan,
        memories,
    ) -> list[StagePanel]:
        # 标题来自动态资源（和 api mapper、左栏会话共用同一份）
        titles = self._stage_titles()
        panels: list[StagePanel] = []
        for stage in (
            LoopStage.COLLECT,
            LoopStage.DIAGNOSE,
            LoopStage.DECIDE,
            LoopStage.ACT,
            LoopStage.REVIEW,
        ):
            evaluation = ""
            version = None
            diff = None
            updated_at = None
            if stage == LoopStage.COLLECT:
                if profile is not None:
                    version = profile.version
                    updated_at = profile.updated_at
                    confidence = await self._profiles.overall_confidence(user_id)
                    evaluation = (
                        f"{len(profile.fields)} 个画像字段 · 缺口 {len(profile.gaps)} 条"
                        f" · 整体置信度 {confidence:.2f}"
                    )
            elif stage == LoopStage.REVIEW:
                if memories:
                    evaluation = f"{len(memories)} 条会话记忆可续接"
            else:
                asset_type = _STAGE_ASSET[stage]
                asset_version = latest.get(asset_type)
                if asset_version is not None:
                    version = asset_version.version
                    diff = asset_version.diff_from_previous
                    updated_at = asset_version.created_at
                    if asset_type == AssetType.REPORT and report is not None:
                        evaluation = report.verdict.title
                    elif asset_type == AssetType.DIRECTION_PLAN and direction_plans:
                        selected = next(
                            (p for p in direction_plans if p.selected), direction_plans[0]
                        )
                        evaluation = f"主攻：{selected.name}（匹配 {selected.match_score:.2f}）"
                    elif asset_type == AssetType.ACTION_PLAN and action_plan is not None:
                        done = sum(
                            t.done for phase in action_plan.phases for t in phase.tasks
                        )
                        total = sum(
                            len(phase.tasks) for phase in action_plan.phases
                        )
                        evaluation = f"{len(action_plan.phases)} 个阶段 · 任务 {done}/{total} 已完成"
            panels.append(
                StagePanel(
                    stage=stage,
                    title=titles.get(stage.value, ""),
                    evaluation=evaluation,
                    version=version,
                    diff_from_previous=diff,
                    updated_at=updated_at,
                )
            )
        return panels

    def _build_dependencies(self, latest: dict[AssetType, object]) -> list[DependencyEdge]:
        edges: list[DependencyEdge] = []
        chain: list[tuple[str, str, AssetType]] = [
            ("profile", "report", AssetType.REPORT),
            ("report", "direction_plan", AssetType.DIRECTION_PLAN),
            ("direction_plan", "action_plan", AssetType.ACTION_PLAN),
        ]
        for from_asset, to_asset, asset_type in chain:
            version = latest.get(asset_type)
            edges.append(
                DependencyEdge(
                    from_asset=from_asset,
                    to_asset=to_asset,
                    via_profile_keys=list(version.depends_on_profile_keys)
                    if version is not None
                    else [],
                )
            )
        return edges

    @staticmethod
    def _coverage(profile) -> float:
        """P0 口径：已填字段 /（已填字段 + 缺口）。动态 key_fields 阈值待接。"""
        if profile is None:
            return 0.0
        total = len(profile.fields) + len(profile.gaps)
        return round(len(profile.fields) / total, 2) if total else 0.0


__all__ = ["DefaultWorkspaceService"]
