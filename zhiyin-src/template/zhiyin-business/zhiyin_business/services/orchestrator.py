"""Conversation facade and background business lifecycle.

Live dialogue delegates to DialogueRuntime. Regex routing/writes, forced stage
output, prose-based confirmation and late reply rewrites have been removed.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from weakref import WeakValueDictionary
from zhiyin_business.contracts.common import Disclosure
from zhiyin_business.policies.handoff import HandoffPolicy
from zhiyin_business.policies.routing import IntentPolicy, StagePolicy
from zhiyin_business.policies.teaming import LeadPolicy
from zhiyin_business.ports.blackboard import AssetService, BehaviorService, BlackboardView, ConversationMemoryService, ProfileService
from zhiyin_business.ports.orchestrator import HandoffDecision, IntentType, LeadDecision, Orchestrator, TurnRequest, TurnResult
from zhiyin_business.ports.registry import RegistryService
from zhiyin_business.ports.function import FunctionService
from zhiyin_data_sdk.repositories import TaskSessionRepository
from zhiyin_kernel import dynamic_config
from zhiyin_kernel.blackboard import TaskSession
from zhiyin_kernel.enums import AssetType, AxisAStage, BehaviorEventType, LoopStage, TaskStatus
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_orchestration import AgentEngine, EventBus, ExternalDataSource


def _now():
    return datetime.now(timezone.utc)


def _require_owner(session, user_id):
    if session.user_id != user_id:
        raise ResourceNotFound("会话不存在")


class DefaultOrchestrator(Orchestrator):
    IMPLEMENTATION_STATUS = "wired"
    def __init__(
        self,
        *,
        profiles: ProfileService,
        behaviors: BehaviorService,
        memories: ConversationMemoryService,
        assets: AssetService,
        intent_policy: IntentPolicy,
        stage_policy: StagePolicy,
        lead_policy: LeadPolicy,
        handoff_policy: HandoffPolicy,
        agent_engine: AgentEngine,
        sessions: TaskSessionRepository,
        registry: RegistryService,
        event_bus: EventBus,
        functions: FunctionService | None = None,
        data_sources: ExternalDataSource | None = None,
        read_cache: Any = None,
        student_state=None,
        academic_service=None,
    ) -> None:
        self._student_state = student_state
        self._academic = academic_service
        self._profiles = profiles
        self._behaviors = behaviors
        self._memories = memories
        self._assets = assets
        self._intent_policy = intent_policy
        self._stage_policy = stage_policy
        self._lead_policy = lead_policy
        self._handoff_policy = handoff_policy
        self._agent_engine = agent_engine
        self._sessions = sessions
        self._registry = registry
        self._event_bus = event_bus
        # ④ 行动产出的关键节点要写进日历（规划师写入、教练读取）。
        # 可选：单测里可以只构造编排器本身；缺它就跳过日历登记，
        # 但**不跳过行动计划的落库** —— 计划正文与日历是两件事。
        self._functions = functions
        self._data_sources = data_sources
        # 读缓存（可缺省）：一轮对话可能改了画像、资产、行为 —— 那些都让工作台那一片作废。
        # 注入的是业务侧服务（`ReadCacheService`），这里只报"发生了什么"。
        self._cache = read_cache
        self._turn_locks = WeakValueDictionary()

    @asynccontextmanager
    async def _serialized(self, user_id):
        lock = self._turn_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            async with self._sessions.conversation_lock(user_id):
                yield

    async def read_blackboard(self, user_id: str, task_id: str) -> BlackboardView:
        session = await self._sessions.get(task_id)
        asset_versions = []
        for asset_type in (AssetType.REPORT, AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN):
            versions = await self._assets.list_versions(user_id, asset_type)
            if versions:
                asset_versions.append(versions[-1])
        return BlackboardView(
            user_id=user_id,
            task_id=task_id,
            profile=await self._profiles.get(user_id),
            recent_behaviors=[item for item in await self._behaviors.recent(user_id, limit=50) if item.payload.get("session_id") == task_id],
            memories=await self._memories.list_by_user(user_id),
            asset_versions=asset_versions,
            current_stage=session.loop_stage if session else None,
        )

    async def infer_axis_a(self, user_id: str, task_id: str) -> AxisAStage:
        blackboard = await self.read_blackboard(user_id, task_id)
        profile = blackboard.profile
        fields = {field.key: field for field in (profile.fields if profile else [])}
        if "target_direction" not in fields:
            return AxisAStage.EXPLORE_SELF
        if not any(item.asset_type == AssetType.REPORT for item in blackboard.asset_versions):
            return AxisAStage.VERIFY_DIRECTION
        if any(item.asset_type == AssetType.ACTION_PLAN for item in blackboard.asset_versions):
            if any(
                behavior.event_type == BehaviorEventType.TASK_STALL
                for behavior in blackboard.recent_behaviors
            ):
                return AxisAStage.REPOSITION
            if any(
                behavior.event_type
                in {BehaviorEventType.TASK_DONE, BehaviorEventType.REVIEW}
                for behavior in blackboard.recent_behaviors
            ):
                return AxisAStage.ADAPT
            return AxisAStage.SPRINT_ACTION
        return AxisAStage.VERIFY_DIRECTION

    async def select_lead(
        self,
        user_id: str,
        task_id: str,
        axis_a: AxisAStage,
        stage: LoopStage,
        intent: IntentType,
    ) -> LeadDecision:
        blackboard = await self.read_blackboard(user_id, task_id)
        return await self._lead_policy.select(
            blackboard=blackboard,
            axis_a=axis_a,
            stage=stage,
            intent=intent,
        )

    async def handoff(
        self, user_id: str, task_id: str, to_stage: LoopStage, reason: str
    ) -> HandoffDecision:
        session = await self._sessions.get(task_id)
        if session is None:
            raise ResourceNotFound(f"任务会话不存在：{task_id}")
        _require_owner(session, user_id)
        blackboard = await self.read_blackboard(user_id, task_id)
        axis_a = await self.infer_axis_a(user_id, task_id)
        lead = await self.select_lead(
            user_id, task_id, axis_a, to_stage, IntentType.FREE_CHAT
        )
        decision = self._handoff_policy.decide(
            blackboard=blackboard,
            from_stage=session.loop_stage,
            from_agent=session.lead_agent,
            to_stage=to_stage,
            to_agent=lead.lead_agent,
            reason=reason,
        )
        if decision.disclosure is None:
            decision = decision.model_copy(
                update={
                    "disclosure": Disclosure(
                        kind="lead_change",
                        text=reason,
                        from_agent=session.lead_agent,
                        to_agent=lead.lead_agent,
                    )
                }
            )
        await self._sessions.update_stage(session.id, to_stage, lead.lead_agent)
        return decision

    async def enter_task(
        self, user_id: str, task_code: str, *, new_session: bool = False
    ) -> TaskSession:
        """进入任务：已有进行中的会话则续接，否则按任务入口建会话。

        `new_session=True` 时**不续接**：把同入口还在进行中的旧会话标记完成
        （仍留在左栏历史里可打开），再建一条新的。少了这个分支，「新建咨询」
        永远返回同一条会话 —— 用户以为开了新对话，看到的却是旧内容。

        未登记的 `task_code` **必须报错**，不能静默建一个名字等于 code 的会话：
        任务码是前端从 `/app/bootstrap` 的 `task_entries` 里取的，拼错的唯一原因
        是前端与动态资源不同步 —— 静默兜底会把这件事盖住，用户看到的是一句
        自己看不懂的「任务名」，而没有任何一处报错。

        `free_chat` 这类**已登记但没有目标环节 / 主理**的入口不受影响：
        它走下面的回落分支（环节 ①、主理由组队规则选）。
        """
        existing = await self._sessions.find_active(user_id, task_code)
        if existing is not None and not new_session:
            return existing

        entries = {entry.code: entry for entry in await self._registry.list_task_entries()}
        spec = entries.get(task_code)
        if spec is None:
            raise ResourceNotFound(
                f"未登记的任务入口：{task_code}。任务码须取自 /app/bootstrap 的 task_entries"
            )
        task_name = spec.label or task_code

        if new_session:
            # 旧会话不删除：标成已完成，历史里仍能打开；find_active 只找 active，
            # 之后同一入口的"续接"就会命中这条新会话。
            for item in await self._sessions.list_by_user(
                user_id, statuses=[TaskStatus.ACTIVE]
            ):
                if item.task_code == task_code and item.id != "":
                    await self._sessions.update_status(item.id, TaskStatus.COMPLETED)

        if spec.target_stage is not None:
            stage: LoopStage = spec.target_stage
        else:
            # 直接开聊：没有任务入口可依，回落 ① 采集（与 handle_message 兜底一致）。
            stage = LoopStage.COLLECT

        if spec.lead_agent:
            lead_agent = spec.lead_agent
        else:
            axis_a = await self.infer_axis_a(user_id, task_id="")
            lead = await self.select_lead(
                user_id, task_id="", axis_a=axis_a, stage=stage, intent=IntentType.FREE_CHAT
            )
            lead_agent = lead.lead_agent

        now = _now()
        session = await self._sessions.create(
            TaskSession(
                id=f"task-{uuid4().hex[:12]}",
                user_id=user_id,
                task_code=task_code,
                task_name=task_name,
                loop_stage=stage,
                lead_agent=lead_agent,
                status=TaskStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        return session

    async def handle_message(self, request: TurnRequest) -> TurnResult:
        from zhiyin_business.services.analysis_access import activate, load_scope

        if len(request.message) > 16000 or len(request.attachment_text) > 64000:
            raise InvalidRequest("本轮输入过长，请缩短消息或材料后再发送。")
        if not request.client_msg_id:
            request = request.model_copy(update={"client_msg_id": "server_" + uuid4().hex})

        scope = await load_scope(self._student_state, request.user_id)
        if "material" not in scope.sources and (request.attachment_text or request.attachment_name):
            error = InvalidRequest("上传材料参与分析已关闭，请移除附件后发送，或在资料偏好中开启。")
            error.user_facing = True
            raise error
        with activate(scope):
            async with asyncio.timeout(150):
                async with self._serialized(request.user_id):
                    return await self._handle_message(request)

    async def conversation_control(self, user_id, task_id, **kwargs):
        from zhiyin_business.services.conversation_control import ConversationControl
        return await ConversationControl(self).read(user_id, task_id, **kwargs)

    async def delete_conversation(self, user_id, task_id):
        from zhiyin_business.services.conversation_control import ConversationControl
        await ConversationControl(self).delete(user_id, task_id)

    async def _handle_message(self, request: TurnRequest) -> TurnResult:
        from zhiyin_business.services.dialogue_runtime import DialogueRuntime
        from zhiyin_kernel.streaming import cancellation_channel, capture_progress
        runtime = DialogueRuntime(self)
        runtime.request = request
        with cancellation_channel(runtime.cancelled), capture_progress(runtime.capture):
            try:
                return await runtime.run(request)
            except BaseException:
                if runtime.progress_writes:
                    await asyncio.gather(*runtime.progress_writes, return_exceptions=True)
                record = await runtime.ledger.read(request.user_id, request.task_id)
                if request.client_msg_id in record["runs"] and not record["runs"][request.client_msg_id].get("result"):
                    await runtime.ledger.put_run(request.user_id, request.task_id, request.client_msg_id,
                        state="failed", events=runtime.events[-200:], last_status="本轮中断；操作以记录中的实际回执为准")
                raise

    def _allowed_profile_keys(self) -> set[str]:
        """画像允许的字段键（动态资源里的画像字段词表；读不到时返回空集＝不拦）。

        读不到就不拦：把"配置没装载"变成"用户说的话被丢掉"，比多几条字段坏得多。
        """
        return {
            spec.key for spec in self._profile_vocabulary() if not spec.alias_of
        }

    @staticmethod
    def _profile_vocabulary() -> tuple[Any, ...]:
        """画像字段词表（键 + 中文名），来自装载好的动态配置快照。

        与界面显示名**同一份**：文案包里的 `profile.field.<键>`。
        """
        return dynamic_config.snapshot().profile_fields
