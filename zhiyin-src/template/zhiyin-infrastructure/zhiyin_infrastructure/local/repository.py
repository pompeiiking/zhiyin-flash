"""内存 Repository 实现（第一期默认）。

用途：让业务层与前端能端到端联调。
实现原则：行为保持一致（含版本 +1、只追加、影响面匹配），
否则切真后会暴露契约之外的差异。

约定：
- 返回值一律是 `deepcopy` 出来的快照，避免调用方改内存对象绕过 Repository 语义；
- `behavior_log` 只允许追加，不提供任何 UPDATE 路径（行为日志是唯一事实来源）；
- 资产版本单调递增：传入的 version 若不大于当前最新版本，会被提升为 latest+1，
  以保证「影响面传播 → 版本 +1」这条验收口径在任何调用顺序下都成立。

异步口径：契约里的公开方法在本文件里也全部是 `async`，但内部**没有**任何真 IO
（纯内存字典），因此私有辅助函数（`_ensure` / `_by_type` / `_require` / `_load`）
保持同步，不需要为了"看起来异步"而层层 await。切换实现时，
方法签名不变，只把 `await` 换成真实查询。

TODO：按自有基础设施演进。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import uuid4

from zhiyin_kernel.assets import ActionPlan, CalendarNode, DirectionPlan, Report, TrackEvent
from zhiyin_kernel.blackboard import (
    AssetVersion,
    BehaviorLog,
    ConversationMemory,
    ConversationTurn,
    Profile,
    ProfileField,
    ProfileGap,
    TaskSession,
    UserNote,
)
from zhiyin_kernel.dynamic_content import (
    BannerSpec,
    CopySpec,
    FaqSpec,
    MenuSpec,
    RouteSpec,
    TrustBlockSpec,
)
from zhiyin_kernel.enums import (
    AssetType,
    BehaviorEventType,
    LoopStage,
    TaskStatus,
)
from zhiyin_kernel.identity import UserAccount
from zhiyin_kernel.registry import (
    AgentDescriptor,
    BadgeRuleSpec,
    ChsiFieldSpec,
    CollectionRuleSpec,
    LayoutPolicy,
    OutputContractSpec,
    PolicyParamSet,
    PromptSpec,
    RoutingRuleSpec,
    StageSpec,
    TaskEntrySpec,
    TaskProgressSpec,
    TheoryCard,
    TrackEventSpec,
    UserSignalSpec,
)
from zhiyin_kernel.errors import ResourceNotFound
from zhiyin_data_sdk.repositories import (
    AcademicSnapshotRepository,
    AssetRepository,
    BehaviorRepository,
    ConversationMemoryRepository,
    ConversationTurnRepository,
    ProfileRepository,
    RegistryRepository,
    TaskSessionRepository,
    UserNoteRepository,
    UserRepository,
)
from zhiyin_data_sdk.repositories import (
    AiTaskResultRepository,
    CalendarNodeRepository,
    NotificationRepository,
    TrackEventRepository,
)
from zhiyin_data_sdk.gateways.academic import AcademicSnapshot


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _snapshot(model):
    """返回深拷贝快照，隔离内存对象与调用方。"""
    return model.model_copy(deep=True)


class InMemoryProfileRepository(ProfileRepository):
    """画像活状态（profile / profile_field / profile_gap）。"""

    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = {}

    async def get(self, user_id: str) -> Optional[Profile]:
        profile = self._profiles.get(user_id)
        return _snapshot(profile) if profile is not None else None

    async def save(self, profile: Profile) -> Profile:
        stored = _snapshot(profile)
        stored.updated_at = _now()
        self._profiles[profile.user_id] = stored
        return _snapshot(stored)

    async def upsert_field(self, user_id: str, field: ProfileField) -> ProfileField:
        profile = self._ensure(user_id)
        incoming = _snapshot(field)
        incoming.updated_at = _now()
        for index, existing in enumerate(profile.fields):
            if existing.key == incoming.key:
                profile.fields[index] = incoming
                break
        else:
            profile.fields.append(incoming)
        profile.version += 1
        profile.updated_at = _now()
        return _snapshot(incoming)

    async def delete_field(self, user_id: str, key: str) -> None:
        profile = self._ensure(user_id)
        kept = [field for field in profile.fields if field.key != key]
        if len(kept) != len(profile.fields):
            profile.fields = kept
            profile.version += 1
            profile.updated_at = _now()

    async def list_fields(
        self, user_id: str, keys: Optional[Sequence[str]] = None
    ) -> list[ProfileField]:
        profile = self._profiles.get(user_id)
        if profile is None:
            return []
        wanted = set(keys) if keys else None
        return [
            _snapshot(item)
            for item in profile.fields
            if wanted is None or item.key in wanted
        ]

    async def list_gaps(self, user_id: str) -> list[ProfileGap]:
        profile = self._profiles.get(user_id)
        return [_snapshot(item) for item in profile.gaps] if profile else []

    async def replace_gaps(self, user_id: str, gaps: list[ProfileGap]) -> None:
        profile = self._ensure(user_id)
        profile.gaps = [_snapshot(item) for item in gaps]
        profile.version += 1
        profile.updated_at = _now()

    def _ensure(self, user_id: str) -> Profile:
        profile = self._profiles.get(user_id)
        if profile is None:
            profile = Profile(
                id=_new_id("prf"), user_id=user_id, updated_at=_now()
            )
            self._profiles[user_id] = profile
        return profile


class InMemoryBehaviorRepository(BehaviorRepository):
    """行为日志。只追加，不提供 UPDATE（契约要求）。"""

    def __init__(self) -> None:
        self._logs: list[BehaviorLog] = []

    async def append(self, log: BehaviorLog) -> BehaviorLog:
        stored = _snapshot(log)
        if not stored.id:
            stored.id = _new_id("bhv")
        self._logs.append(stored)
        return _snapshot(stored)

    async def list_by_user(
        self,
        user_id: str,
        *,
        event_types: Optional[Sequence[BehaviorEventType]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[BehaviorLog]:
        wanted = set(event_types) if event_types else None
        matched = [
            item
            for item in self._logs
            if item.user_id == user_id
            and (wanted is None or item.event_type in wanted)
            and (since is None or item.occurred_at >= since)
            and (until is None or item.occurred_at <= until)
        ]
        matched.sort(key=lambda item: item.occurred_at, reverse=True)
        return [_snapshot(item) for item in matched[:limit]]

    async def last_occurred_at(
        self, user_id: str, event_type: BehaviorEventType
    ) -> Optional[datetime]:
        times = [
            item.occurred_at
            for item in self._logs
            if item.user_id == user_id and item.event_type == event_type
        ]
        return max(times) if times else None


class InMemoryConversationMemoryRepository(ConversationMemoryRepository):
    """会话记忆。唯一键 (user_id, task_id)；task_id 可为空（自由会话）。"""

    def __init__(self) -> None:
        self._memories: dict[tuple[str, Optional[str]], ConversationMemory] = {}

    async def get(self, user_id: str, task_id: str) -> Optional[ConversationMemory]:
        memory = self._memories.get((user_id, task_id))
        return _snapshot(memory) if memory is not None else None

    async def upsert(self, memory: ConversationMemory) -> ConversationMemory:
        stored = _snapshot(memory)
        if not stored.id:
            stored.id = _new_id("mem")
        stored.last_active_at = _now()
        self._memories[(memory.user_id, memory.task_id)] = stored
        return _snapshot(stored)

    async def list_by_user(self, user_id: str) -> list[ConversationMemory]:
        items = [
            memory for (uid, _), memory in self._memories.items() if uid == user_id
        ]
        items.sort(key=lambda item: item.last_active_at, reverse=True)
        return [_snapshot(item) for item in items]

    async def delete(self, user_id: str, task_id: str) -> None:
        self._memories.pop((user_id, task_id), None)


class InMemoryConversationTurnRepository(ConversationTurnRepository):
    """逐轮对话原文：内存实现。只追加，不改写历史。"""

    def __init__(self) -> None:
        self._turns: list[ConversationTurn] = []

    async def append(self, turn: ConversationTurn) -> ConversationTurn:
        stored = _snapshot(turn)
        if not stored.id:
            stored.id = _new_id("turn")
        self._turns.append(stored)
        return _snapshot(stored)

    async def list_by_task(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationTurn]:
        items = [
            turn
            for turn in self._turns
            if turn.user_id == user_id and (turn.task_id or "") == (task_id or "")
        ]
        items.sort(key=lambda item: item.created_at)
        return [_snapshot(item) for item in items][-limit:]

    async def find_reply_by_client_msg_id(
        self, user_id: str, client_msg_id: str
    ) -> Optional[ConversationTurn]:
        if not client_msg_id:
            return None
        matched = [
            turn
            for turn in self._turns
            if turn.user_id == user_id
            and turn.client_msg_id == client_msg_id
            and turn.role == "agent"
        ]
        if not matched:
            return None
        matched.sort(key=lambda item: item.created_at)
        return _snapshot(matched[-1])


class InMemoryUserNoteRepository(UserNoteRepository):
    """用户自建内容：内存实现，语义与 Postgres 版一致（更新即改 updated_at）。"""

    def __init__(self) -> None:
        self._notes: dict[str, UserNote] = {}

    async def list_by_user(self, user_id: str) -> list[UserNote]:
        items = [note for note in self._notes.values() if note.user_id == user_id]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [_snapshot(item) for item in items]

    async def upsert(self, note: UserNote) -> UserNote:
        stored = _snapshot(note)
        if not stored.id:
            stored.id = _new_id("note")
        stored.updated_at = _now()
        self._notes[stored.id] = stored
        return _snapshot(stored)

    async def delete(self, user_id: str, note_id: str) -> None:
        existing = self._notes.get(note_id)
        if existing is not None and existing.user_id == user_id:
            self._notes.pop(note_id, None)


class InMemoryAcademicSnapshotRepository(AcademicSnapshotRepository):
    """教务系统快照：内存实现，语义与 Postgres 版一致（重新取数即替换）。"""

    def __init__(self) -> None:
        self._snapshots: dict[str, AcademicSnapshot] = {}

    async def get(self, user_id: str) -> Optional[AcademicSnapshot]:
        snapshot = self._snapshots.get(user_id)
        return _snapshot(snapshot) if snapshot is not None else None

    async def upsert(self, user_id: str, snapshot: AcademicSnapshot) -> AcademicSnapshot:
        stored = _snapshot(snapshot)
        self._snapshots[user_id] = stored
        return _snapshot(stored)

    async def delete(self, user_id: str) -> None:
        self._snapshots.pop(user_id, None)


class InMemoryAssetRepository(AssetRepository):
    """资产版本与内容。版本单调递增，影响面按 depends_on_profile_keys 匹配。"""

    def __init__(self) -> None:
        self._versions: list[AssetVersion] = []
        self._reports: dict[str, list[Report]] = {}
        self._plans: dict[str, list[DirectionPlan]] = {}
        self._action_plans: dict[str, ActionPlan] = {}

    # ---------- 版本 ----------

    async def get_latest_version(
        self, user_id: str, asset_type: AssetType
    ) -> Optional[AssetVersion]:
        matched = self._by_type(user_id, asset_type)
        return _snapshot(matched[-1]) if matched else None

    async def list_versions(self, user_id: str, asset_type: AssetType) -> list[AssetVersion]:
        return [_snapshot(item) for item in self._by_type(user_id, asset_type)]

    async def save_version(self, version: AssetVersion) -> AssetVersion:
        stored = _snapshot(version)
        if not stored.id:
            stored.id = _new_id("av")
        latest = self._by_type(stored.user_id, stored.asset_type)
        floor = latest[-1].version if latest else 0
        # 版本必须单调递增；调用方传小值时提升，保证「版本 +1」口径不被破坏。
        stored.version = max(stored.version, floor + 1)
        stored.created_at = _now()
        self._versions.append(stored)
        return _snapshot(stored)

    async def list_affected_assets(
        self, user_id: str, profile_keys: Sequence[str]
    ) -> list[AssetVersion]:
        changed = set(profile_keys)
        latest_by_type: dict[AssetType, AssetVersion] = {}
        for item in self._versions:
            if item.user_id == user_id:
                latest_by_type[item.asset_type] = item

        affected = [
            item
            for item in latest_by_type.values()
            if changed & set(item.depends_on_profile_keys)
        ]
        affected.sort(key=lambda item: (item.asset_type.value, item.version))
        return [_snapshot(item) for item in affected]

    async def mark_needs_recompute(
        self, user_id: str, asset_type: AssetType, *, reason: str
    ) -> Optional[AssetVersion]:
        matched = self._by_type(user_id, asset_type)
        if not matched:
            return None
        latest = matched[-1]
        # 原地改最新那一版：不追加版本、不动正文，只把"这版是旧的"如实记下来。
        marker = latest.model_copy(
            update={"needs_recompute": True, "recompute_reason": reason}
        )
        # 按**身份**替换，不按 `==`：Pydantic 的相等是按字段比，两条内容一样的
        # 版本会互相顶掉（旧版被改新、新版原样留着），这种错不报错、只错数据。
        for index, item in enumerate(self._versions):
            if item is latest:
                self._versions[index] = marker
                break
        return _snapshot(marker)

    # ---------- 诊断报告 ----------

    async def get_report(self, user_id: str, version: Optional[int] = None) -> Optional[Report]:
        reports = self._reports.get(user_id) or []
        if not reports:
            return None
        if version is None:
            return _snapshot(reports[-1])
        # 指定版本没有正文时退到"不晚于它的最新一版"：影响面传播留下的空版本
        # （只有版本行、没有正文）点了不该是空白页 —— 见 mark_needs_recompute。
        candidates = [item for item in reports if item.version <= version]
        return _snapshot(candidates[-1]) if candidates else None

    async def save_report(self, report: Report) -> Report:
        stored = _snapshot(report)
        if not stored.id:
            stored.id = _new_id("rpt")
        history = self._reports.setdefault(stored.user_id, [])
        if history:
            stored.version = max(stored.version, history[-1].version + 1)
        history.append(stored)
        return _snapshot(stored)

    # ---------- 方向方案 ----------

    async def list_direction_plans(self, user_id: str) -> list[DirectionPlan]:
        return [_snapshot(item) for item in self._plans.get(user_id, [])]

    async def save_direction_plans(self, user_id: str, plans: list[DirectionPlan]) -> None:
        stored: list[DirectionPlan] = []
        for plan in plans:
            item = _snapshot(plan)
            if not item.id:
                item.id = _new_id("plan")
            stored.append(item)
        self._plans[user_id] = stored

    async def select_direction_plan(self, user_id: str, plan_id: str) -> DirectionPlan:
        """选中一个方向方案，其余取消选中。

        顺序很关键：**先确认目标存在，再落状态变更**。
        此前是"在同一个循环里边找边把其它方案置为未选"，于是传入一个不存在的
        `plan_id` 时，用户的当前选择会先被抹掉、然后才抛异常 —— 调用方即使捕获了
        异常，数据也已经被改坏（且内存实现没有回滚）。
        """
        plans = self._plans.get(user_id, [])
        target = next((item for item in plans if item.id == plan_id), None)
        if target is None:
            raise ResourceNotFound(f"方向方案不存在：{plan_id}")

        now = _now()
        for item in plans:
            if item is target:
                item.selected = True
                item.selected_at = now
            else:
                item.selected = False
                item.selected_at = None
        return _snapshot(target)

    # ---------- 行动计划 ----------

    async def get_action_plan(self, user_id: str) -> Optional[ActionPlan]:
        plan = self._action_plans.get(user_id)
        return _snapshot(plan) if plan is not None else None

    async def save_action_plan(self, user_id: str, plan: ActionPlan) -> ActionPlan:
        stored = _snapshot(plan)
        if not stored.id:
            stored.id = _new_id("act")
        self._action_plans[user_id] = stored
        return _snapshot(stored)

    async def mark_task_done(
        self, user_id: str, task_id: str, *, done: bool = True
    ) -> ActionPlan:
        plan = self._action_plans.get(user_id)
        if plan is None:
            raise ResourceNotFound(f"行动计划不存在：{user_id}")
        for phase in plan.phases:
            for task in phase.tasks:
                # 优先按任务 id 定位（新数据）；老数据没有 id，回落到
                # 「阶段名:任务文本」与"裸任务文本"两种历史口径。
                if task_id in {task.id, _task_key(phase.name, task.text), task.text}:
                    task.done = done
                    task.done_at = _now() if done else None
                    return _snapshot(plan)
        raise ResourceNotFound(f"行动任务不存在：{task_id}")

    # ---------- 内部 ----------

    def _by_type(self, user_id: str, asset_type: AssetType) -> list[AssetVersion]:
        matched = [
            item
            for item in self._versions
            if item.user_id == user_id and item.asset_type == asset_type
        ]
        matched.sort(key=lambda item: item.version)
        return matched


def _task_key(phase_name: str, text: str) -> str:
    return f"{phase_name}:{text}"


class InMemoryTaskSessionRepository(TaskSessionRepository):
    """任务会话。可拆可续的持久化载体。"""

    def __init__(self) -> None:
        self._sessions: dict[str, TaskSession] = {}

    async def get(self, session_id: str) -> Optional[TaskSession]:
        session = self._sessions.get(session_id)
        return _snapshot(session) if session is not None else None

    async def find_active(self, user_id: str, task_code: str) -> Optional[TaskSession]:
        for session in self._sessions.values():
            if (
                session.user_id == user_id
                and session.task_code == task_code
                and session.status == TaskStatus.ACTIVE
            ):
                return _snapshot(session)
        return None

    async def list_by_user(
        self, user_id: str, statuses: Optional[Sequence[TaskStatus]] = None
    ) -> list[TaskSession]:
        wanted = set(statuses) if statuses else None
        matched = [
            item
            for item in self._sessions.values()
            if item.user_id == user_id and (wanted is None or item.status in wanted)
        ]
        matched.sort(key=lambda item: item.updated_at, reverse=True)
        return [_snapshot(item) for item in matched]

    async def create(self, session: TaskSession) -> TaskSession:
        stored = _snapshot(session)
        if not stored.id:
            stored.id = _new_id("tsk")
        self._sessions[stored.id] = stored
        return _snapshot(stored)

    async def update_stage(
        self, session_id: str, stage: LoopStage, lead_agent: str
    ) -> TaskSession:
        session = self._require(session_id)
        session.loop_stage = stage
        session.lead_agent = lead_agent
        session.updated_at = _now()
        return _snapshot(session)

    async def update_status(self, session_id: str, status: TaskStatus) -> TaskSession:
        session = self._require(session_id)
        session.status = status
        session.updated_at = _now()
        return _snapshot(session)

    def _require(self, session_id: str) -> TaskSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ResourceNotFound(f"任务会话不存在：{session_id}")
        return session


class InMemoryUserRepository(UserRepository):
    """用户与登录会话。第一期只有本地演示用户。"""

    def __init__(self) -> None:
        self._users: dict[str, UserAccount] = {}

    async def get_by_id(self, user_id: str) -> Optional[UserAccount]:
        user = self._users.get(user_id)
        return _snapshot(user) if user is not None else None

    async def get_by_phone(self, phone: str) -> Optional[UserAccount]:
        for user in self._users.values():
            if user.phone == phone:
                return _snapshot(user)
        return None

    async def create(self, user: UserAccount) -> UserAccount:
        stored = _snapshot(user)
        if not stored.id:
            stored.id = _new_id("usr")
        self._users[stored.id] = stored
        return _snapshot(stored)

    async def touch_last_login(self, user_id: str, at: datetime) -> None:
        user = self._users.get(user_id)
        if user is None:
            raise ResourceNotFound(f"用户不存在：{user_id}")
        user.last_login_at = at

class LocalJsonRegistryRepository(RegistryRepository):
    """动态资源：第一期读本地 JSON。

    文件位置：`{data_dir}/{agents,theory_cards,output_contracts,task_entries,
    policy_params,menus,routes,copies,banners,trust_blocks,faqs}.json`
    文件内容支持两种形状：顶层数组，或 `{"items": [...]}`。

    设计意图：页面文案、任务入口、智能体、理论卡、
    产出契约、规则参数都必须是**动态资源**。放 JSON 而不是写进代码，是为了在第一期
    就能验证"改配置不发版"这条口径。

    前端页面内容（菜单 / 路由 / 文案 / 横幅 / 信任块 / FAQ）的取数口径统一在本类：
    只返回 `status == "enabled"` 且按 `sort_order` 升序——上下线与排序是数据语义，
    散到每个调用方各写一遍必然漂移。
    """

    FILES: dict[str, str] = {
        "agents": "agents.json",
        "theory_cards": "theory_cards.json",
        "output_contracts": "output_contracts.json",
        "task_entries": "task_entries.json",
        "policy_params": "policy_params.json",
        "menus": "menus.json",
        "routes": "routes.json",
        "copies": "copies.json",
        "banners": "banners.json",
        "trust_blocks": "trust_blocks.json",
        "faqs": "faqs.json",
        "track_events": "track_events.json",
        # AI 提示词与编排规则：它们曾经没有来源（只能写在装配代码里），
        # 现在与其他动态资源同一套读法。
        "prompts": "prompts.json",
        "routing_rules": "routing_rules.json",
        # 编排与展示口径：环节、气泡编排、采集规则、用户信号。
        # ⚠️ 这四类此前只在 Postgres 实现里有读方法，本地实现缺了它们 ——
        # 而 `dynamic_config` 用 `except Exception` 兜底，于是本地模式下
        # 环节标题全空、气泡编排退化、采集规则回落代码内置表，
        # 且 `--check` 依然全绿（它只读文件，不读这条链路）。
        "stages": "stages.json",
        "layout": "layout.json",
        "collection_rules": "collection_rules.json",
        "user_signals": "user_signals.json",
        # 产品口径：成就规则 / AI 任务进度文案 / 学信网字段清单。
        # 它们此前写在业务层代码里（`_BADGE_RULES` / `_PROGRESS_NOTES` /
        # `_CHSI_PROFILE_KEYS`）—— 都是"改一次要发一次版"的口径。
        "badge_rules": "badge_rules.json",
        "task_progress": "task_progress.json",
        "chsi_fields": "chsi_fields.json",
    }

    def __init__(self, data_dir: str = "data/registry") -> None:
        self._data_dir = data_dir
        self._cache: dict[str, list[dict[str, Any]]] = {}

    # ---------- 智能体 ----------

    async def get_agent(self, agent_id: str) -> Optional[AgentDescriptor]:
        for raw in self._load("agents"):
            if raw.get("id") == agent_id:
                return AgentDescriptor.model_validate(raw)
        return None

    async def list_agents(self) -> list[AgentDescriptor]:
        return [AgentDescriptor.model_validate(raw) for raw in self._load("agents")]

    # ---------- 理论卡 ----------

    async def get_theory_card(self, theory_id: str) -> Optional[TheoryCard]:
        for raw in self._load("theory_cards"):
            if raw.get("id") == theory_id:
                return TheoryCard.model_validate(raw)
        return None

    async def list_theory_cards(
        self, theory_ids: Optional[list[str]] = None
    ) -> list[TheoryCard]:
        wanted = set(theory_ids) if theory_ids else None
        cards = [TheoryCard.model_validate(raw) for raw in self._load("theory_cards")]
        if wanted is None:
            return cards
        return [card for card in cards if card.id in wanted]

    # ---------- 产出契约 ----------

    async def get_output_contract(
        self, agent_id: str, stage: LoopStage
    ) -> Optional[OutputContractSpec]:
        """按 `(agent_id, stage)` 查找。`id` 只是标识，不参与查找。"""
        wanted = stage.value if isinstance(stage, LoopStage) else str(stage)
        for raw in self._load("output_contracts"):
            if raw.get("agent_id") == agent_id and raw.get("stage") == wanted:
                return OutputContractSpec.model_validate(raw)
        return None

    # ---------- 首页任务入口 ----------

    async def list_task_entries(self) -> list[TaskEntrySpec]:
        entries = [TaskEntrySpec.model_validate(raw) for raw in self._load("task_entries")]
        entries.sort(key=lambda item: item.sort_order)
        return entries

    # ---------- 环节口径与编排（此前本地实现缺这四类，导致静默降级） ----------

    async def get_layout_policy(self, code: str) -> Optional[LayoutPolicy]:
        """按 code 取气泡编排策略。取不到返回 None（调用方决定怎么解释"没配"）。"""
        for raw in self._load("layout"):
            if raw.get("code") == code:
                return LayoutPolicy.model_validate(raw)
        return None

    async def list_stages(self) -> list[StageSpec]:
        """五个环节的展示口径，按 order 升序。"""
        items = [StageSpec.model_validate(raw) for raw in self._load("stages")]
        items.sort(key=lambda item: item.order)
        return items

    async def list_collection_rules(self) -> list[CollectionRuleSpec]:
        """采集规则，按 order 升序（同档内越小的越先）。"""
        items = [CollectionRuleSpec.model_validate(raw) for raw in self._load("collection_rules")]
        items.sort(key=lambda item: item.order)
        return items

    async def list_user_signals(self) -> list[UserSignalSpec]:
        """用户信号：用户自己写下的话 → 哪个画像字段变成前提。"""
        items = [UserSignalSpec.model_validate(raw) for raw in self._load("user_signals")]
        items.sort(key=lambda item: item.order)
        return items

    async def list_badge_rules(self) -> list[BadgeRuleSpec]:
        """成就解锁规则。顺序由 sort_order 决定。"""
        items = [BadgeRuleSpec.model_validate(raw) for raw in self._load("badge_rules")]
        items.sort(key=lambda item: item.sort_order)
        return items

    async def list_task_progress(self) -> list[TaskProgressSpec]:
        """生成类 AI 任务的进度文案。"""
        items = [TaskProgressSpec.model_validate(raw) for raw in self._load("task_progress")]
        items.sort(key=lambda item: item.sort_order)
        return items

    async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
        """学信网字段清单（写哪些、叫什么、什么顺序）。"""
        items = [ChsiFieldSpec.model_validate(raw) for raw in self._load("chsi_fields")]
        items.sort(key=lambda item: item.order)
        return items

    # ---------- 规则参数 ----------

    async def get_policy_params(self, code: str) -> Optional[PolicyParamSet]:
        for raw in self._load("policy_params"):
            if raw.get("code") == code:
                return PolicyParamSet.model_validate(raw)
        return None

    # ---------- 前端页面内容 ----------

    async def list_menus(self) -> list[MenuSpec]:
        return self._content("menus", MenuSpec)

    async def list_routes(self) -> list[RouteSpec]:
        return self._content("routes", RouteSpec)

    async def get_copy_bundle(self, bundle: str = "zh-CN") -> dict[str, str]:
        items = self._content("copies", CopySpec, bundle=bundle)
        return {item.code: item.text for item in items}

    async def list_banners(self) -> list[BannerSpec]:
        return self._content("banners", BannerSpec)

    async def list_trust_blocks(self) -> list[TrustBlockSpec]:
        return self._content("trust_blocks", TrustBlockSpec)

    async def list_faqs(self) -> list[FaqSpec]:
        return self._content("faqs", FaqSpec)

    async def list_track_events(self) -> list[TrackEventSpec]:
        items = [TrackEventSpec.model_validate(raw) for raw in self._load("track_events")]
        return sorted(items, key=lambda item: item.code)

    # ---------- AI 提示词与编排规则 ----------

    async def get_prompt(self, code: str) -> Optional[PromptSpec]:
        """按 code 取一条提示词。`code` 是稳定标识，不按位置找。"""
        for raw in self._load("prompts"):
            if raw.get("code") == code:
                spec = PromptSpec.model_validate(raw)
                return spec if spec.status == "enabled" else None
        return None

    async def list_prompts(
        self,
        *,
        layer: Optional[str] = None,
        agent_id: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[PromptSpec]:
        items = [PromptSpec.model_validate(raw) for raw in self._load("prompts")]
        items = [item for item in items if item.status == "enabled"]
        if layer is not None:
            items = [item for item in items if item.layer == layer]
        if agent_id is not None:
            items = [item for item in items if item.agent_id == agent_id]
        if stage is not None:
            items = [item for item in items if item.stage == stage]
        items.sort(key=lambda item: item.sort_order)
        return items

    async def list_routing_rules(
        self, kind: Optional[str] = None
    ) -> list[RoutingRuleSpec]:
        items = [
            RoutingRuleSpec.model_validate(raw) for raw in self._load("routing_rules")
        ]
        items = [item for item in items if item.status == "enabled"]
        if kind is not None:
            items = [item for item in items if item.kind == kind]
        # 稳定排序：序号相同时按 id，保证同一份配置每次读出来的顺序一致。
        items.sort(key=lambda item: (item.sort_order, item.id))
        return items

    # ---------- 内部 ----------

    def _content(self, key: str, model, *, bundle: Optional[str] = None):
        """读一类前端动态内容：过滤停用项 + 按 sort_order 排序。

        `bundle` 只为文案包（copies）使用：多语言文案共表，按包过滤。
        """
        items = [model.model_validate(raw) for raw in self._load(key)]
        if bundle is not None:
            items = [item for item in items if getattr(item, "bundle", bundle) == bundle]
        items = [item for item in items if item.status == "enabled"]
        items.sort(key=lambda item: item.sort_order)
        return items

    def _load(self, key: str) -> list[dict[str, Any]]:
        if key in self._cache:
            return self._cache[key]
        import json
        from pathlib import Path

        path = Path(self._data_dir) / self.FILES[key]
        if not path.is_file():
            self._cache[key] = []
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else raw
        self._cache[key] = list(items)
        return self._cache[key]

    def reload(self) -> None:
        """清缓存，用于演示"改配置后热加载"。"""
        self._cache.clear()


class InMemoryCalendarNodeRepository(CalendarNodeRepository):
    """关键节点日历：内存实现，语义与 Postgres 版一致（同 node_id 覆盖）。"""

    def __init__(self) -> None:
        self._nodes: dict[str, list[CalendarNode]] = {}

    async def list_nodes(self, user_id: str) -> list[CalendarNode]:
        items = list(self._nodes.get(user_id, ()))
        # 没有 due_at 的排最后：它们还没被排进时间轴，不该插在已排定的前面。
        items.sort(key=lambda item: (item.due_at is None, item.due_at or _now()))
        return [_snapshot(item) for item in items]

    async def upsert_node(self, user_id: str, node: CalendarNode) -> CalendarNode:
        stored = _snapshot(node)
        stored.user_id = user_id
        nodes = self._nodes.setdefault(user_id, [])
        nodes[:] = [item for item in nodes if item.node_id != stored.node_id]
        nodes.append(stored)
        return _snapshot(stored)

    async def delete_node(self, user_id: str, node_id: str) -> int:
        nodes = self._nodes.get(user_id)
        if not nodes:
            return 0
        before = len(nodes)
        nodes[:] = [item for item in nodes if item.node_id != node_id]
        return before - len(nodes)


class InMemoryTrackEventRepository(TrackEventRepository):
    """跟踪时间线：只追加。"""

    def __init__(self) -> None:
        self._events: dict[str, list[TrackEvent]] = {}

    async def list_events(self, user_id: str, *, limit: int = 50) -> list[TrackEvent]:
        items = sorted(
            self._events.get(user_id, ()),
            key=lambda item: item.occurred_at or _now(),
            reverse=True,
        )
        return [_snapshot(item) for item in items[: max(limit, 0)]]

    async def append_event(self, user_id: str, event: TrackEvent) -> TrackEvent:
        stored = _snapshot(event)
        stored.user_id = user_id
        if not stored.id:
            stored.id = _new_id("track")
        if stored.occurred_at is None:
            stored.occurred_at = _now()
        self._events.setdefault(user_id, []).append(stored)
        return _snapshot(stored)


class InMemoryNotificationRepository(NotificationRepository):
    """通知读侧：内存实现。

    它只服务"纯本地模式"（没有 Postgres 时通知本来也只在本进程里）。
    Postgres 模式下读的是 `orc_notification`，与写侧同一张表。
    """

    def __init__(self) -> None:
        self._messages: dict[str, list[dict[str, Any]]] = {}

    def add(self, user_id: str, message: dict[str, Any]) -> None:
        """写侧入口（`LocalNotify` 推消息时调）。"""
        self._messages.setdefault(user_id, []).append(dict(message))

    def store(self, user_id: str) -> list[dict[str, Any]]:
        """原始列表（含已读）。调试与单测用，业务读侧请走 `list_pending`。"""
        return self._messages.get(user_id, ())

    async def list_pending(self, user_id: str) -> list[dict]:
        return [dict(item) for item in self._messages.get(user_id, ()) if not item.get("read_at")]

    async def mark_read(self, user_id: str, message_id: str) -> int:
        changed = 0
        for item in self._messages.get(user_id, ()):
            if item.get("id") == message_id and not item.get("read_at"):
                item["read_at"] = _now().isoformat()
                changed += 1
        return changed

    async def last_sent_at(self, user_id: str) -> Optional[datetime]:
        stamps = [
            datetime.fromisoformat(str(item["occurred_at"]))
            for item in self._messages.get(user_id, ())
            if item.get("occurred_at")
        ]
        return max(stamps) if stamps else None

    async def count_since(self, user_id: str, since: datetime) -> int:
        return sum(
            1
            for item in self._messages.get(user_id, ())
            if item.get("occurred_at")
            and datetime.fromisoformat(str(item["occurred_at"])) >= since
        )


class InMemoryAiTaskResultRepository(AiTaskResultRepository):
    """AI 任务产出：内存实现（语义与 Postgres 版一致）。"""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    async def get(self, user_id: str, task_key: str) -> Optional[dict[str, Any]]:
        value = self._items.get((user_id, task_key))
        return json.loads(json.dumps(value)) if value is not None else None

    async def put(self, user_id: str, task_key: str, payload: dict[str, Any]) -> None:
        self._items[(user_id, task_key)] = json.loads(json.dumps(payload))

    async def delete_prefix(self, user_id: str, prefix: str = "") -> int:
        doomed = [key for key in self._items if key[0] == user_id and key[1].startswith(prefix)]
        for key in doomed:
            self._items.pop(key, None)
        return len(doomed)


__all__ = [
    "InMemoryAiTaskResultRepository",
    "InMemoryAssetRepository",
    "InMemoryAcademicSnapshotRepository",
    "InMemoryBehaviorRepository",
    "InMemoryCalendarNodeRepository",
    "InMemoryConversationMemoryRepository",
    "InMemoryNotificationRepository",
    "InMemoryProfileRepository",
    "InMemoryTaskSessionRepository",
    "InMemoryTrackEventRepository",
    "InMemoryUserNoteRepository",
    "InMemoryUserRepository",
    "LocalJsonRegistryRepository",
]
