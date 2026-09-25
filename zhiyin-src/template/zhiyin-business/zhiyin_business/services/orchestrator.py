"""编排器默认实现：读黑板 → 判环节 → 选主理 → 产出 → 行为引导。"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import uuid4

from zhiyin_business.contracts import STAGE_CONTRACTS
from zhiyin_business.policies.intel_labels import kind_label, source_name_of
from zhiyin_business.policies.intel_query import intel_topic
from zhiyin_business.contracts.common import (
    AgentBadge,
    BehaviorEventDraft,
    BehaviorGuide,
    ConversationMessage,
    Disclosure,
    IntelRef,
    Renderable,
    TheoryRef,
)
from zhiyin_business.policies.handoff import HandoffPolicy
from zhiyin_business.policies.renderers import validate_renderables
from zhiyin_business.policies.routing_rules import CLARIFY_PROMPT_CODE
from zhiyin_business.policies.routing import IntentPolicy, StagePolicy
from zhiyin_business.policies.teaming import LeadPolicy
from zhiyin_business.ports.blackboard import (
    AssetService,
    BehaviorService,
    BlackboardView,
    ConversationMemoryService,
    ProfileService,
)
from zhiyin_business.ports.orchestrator import (
    HandoffDecision,
    IntentType,
    LeadDecision,
    Orchestrator,
    TurnRequest,
    TurnResult,
)
from zhiyin_business.ports.registry import RegistryService
from zhiyin_business.ports.function import FunctionService
from zhiyin_data_sdk.errors import MissingConfigError
from zhiyin_data_sdk.repositories import TaskSessionRepository
from zhiyin_kernel.blackboard import AssetVersion, TaskSession
from zhiyin_kernel.assets import GapClaim
from zhiyin_kernel import dynamic_config
from zhiyin_business.policies.collection_gate import CollectionGate, evaluate_gate
from zhiyin_kernel.errors import ResourceNotFound
from zhiyin_kernel.enums import (
    AssetType,
    AxisAStage,
    BehaviorEventType,
    LoopStage,
    TaskStatus,
)
from zhiyin_kernel.registry import PromptSpec
from zhiyin_orchestration import (
    AgentEngine,
    AgentRequest,
    DataSourceRequest,
    EventBus,
    ExternalDataSource,
)

logger = logging.getLogger(__name__)

# 取数来源标识（数据，不是依赖）：换数据源只改装配层，本文件不动。
_EXTERNAL_SOURCE = "xuezhi"

# 用户可见文案一律来自动态资源，不在代码里拼。
# 这两个 code 是「换主理告知」的模板与它按环节分条的原因；澄清话术的 code
# 由规则实现持有（它同时是那条策略的一部分），这里复用同一个常量。
_LEAD_CHANGE_PROMPT = "disclosure.lead_change"
_LEAD_CHANGE_REASON_PROMPT = "disclosure.reason.{stage}"
#: 结论变化告知：画像补了新信息、这一版跟着重算过时要说的那句。
#: 它是设计里三种告知（换主理 / 换理论 / 结论变化）的第三种。
_CONCLUSION_CHANGE_PROMPT = "disclosure.conclusion_change"
# 外部事实：哪些环节**主动去取**，哪些环节**只用手上有的**。
#
# 分两档，判据是"没它会不会自己编"：
#
#   · 主动取 —— ② 诊断要有依据、③ 决策要有选项、④ 行动要有样板。
#     这三环少了外部事实，模型只能拿画像硬凑，而"硬凑的岗位要求"看起来和真的一样。
#   · 只读缓存 —— ① 采集问的是"你的情况"，⑤ 复盘问的是"这段时间的事"：
#     外部事实是加分项，不是依据来源。缓存里有就用（例如用户刚开过情报面板），
#     没有就不取，这一轮照常答。
#
# 为什么要把这条线划出来（实测数据）：采集阶段的每个回合都会去爬一遍学职平台
# —— 10 次请求、约 7 秒，而这一轮总共才 15 秒。用户等的就是这几秒，
# 站点也被白打一遍。设计文档 9.3 第 8 步写的是"只在诊断 / 决策 / 行动三个环节取"，
# 代码一度扩到五个环节，现在按文档收回来。
_EXTERNAL_FETCH_STAGES = frozenset(
    {LoopStage.DIAGNOSE, LoopStage.DECIDE, LoopStage.ACT}
)
_EXTERNAL_CACHE_ONLY_STAGES = frozenset({LoopStage.COLLECT, LoopStage.REVIEW})

class DefaultOrchestrator(Orchestrator):
    """职引业务编排器。"""

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
    ) -> None:
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

    async def _fetch_external(
        self,
        *,
        user_id: str,
        message: str,
        profile_fields: Sequence[Any],
        allow_fetch: bool = True,
    ) -> dict[str, Any] | None:
        """这一轮的外部事实。

        `allow_fetch=False`（① 采集 / ⑤ 复盘）时**只读缓存、不打站点**：
        缓存里没有就如实报"这一轮没有外部事实"，而不是让用户等七八秒换一批
        他这一轮用不上的东西。理由与两档划分见 `_EXTERNAL_FETCH_STAGES`。

        两条路，优先走**功能块服务**（生产环境装配的就是它）：

        1. `functions.fetch_external_intel` —— 它自己读画像、按主题取数，
           带 900 秒缓存、按 (人, 主题) 分桶，画像变了会被事件清掉；
        2. 取数原语（`data_sources`）—— 单测里只装它一个时用这条，
           保持"取数是增强，不是硬前置"。

        为什么优先前者：面板与推送走的就是它。两边共用一次取数、一份缓存、
        一个主题口径，用户打开面板看到的那一批，和主理刚才引用的那一批
        才是同一批 —— 否则界面上会出现"两批都叫外部情报、内容却不一样"。

        **主题从画像推**（`intel_topic`），不拿用户原话当检索词：
        他说"嗯"的时候，原话里没有任何领域信息，而画像里有。
        主题为空是合法的 —— 取数侧会退回平台通用数据，而不是拿一句猜的话去查。
        """
        topic = intel_topic(profile_fields)

        if self._functions is not None:
            try:
                items = await self._functions.fetch_external_intel(
                    user_id, topic=topic, limit=8, allow_fetch=allow_fetch
                )
            except Exception:  # noqa: BLE001 - 取不到不算这一轮失败，如实报空
                logger.warning("外部情报取数失败（topic=%s），这一轮按没有处理", topic, exc_info=True)
                items = []
            return {
                "source": _EXTERNAL_SOURCE,
                "records": [item.model_dump(mode="json") for item in items],
                # 只读缓存且没命中 → 如实标注"这一轮没有"，不谎称取过又取不到。
                "degraded": not allow_fetch and not items,
                "topic": topic,
            }

        if self._data_sources is None:
            return None
        if not allow_fetch:
            # 取数原语没有缓存这一层：这一档直接不给事实，也不打站点。
            return {
                "source": _EXTERNAL_SOURCE,
                "records": [],
                "degraded": True,
                "topic": topic,
            }
        external = await self._data_sources.fetch(
            DataSourceRequest(
                source=_EXTERNAL_SOURCE,
                query=message,
                limit=8,
                context={
                    "fields": [
                        field.model_dump(mode="json") for field in profile_fields
                    ],
                    # 主题一并下发：适配器可以据此决定检索词，
                    # 不必自己再从字段里推一遍（口径只在一处）。
                    "topic": topic,
                },
            )
        )
        dumped = external.model_dump(mode="json")
        dumped["topic"] = topic
        return dumped

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
            recent_behaviors=await self._behaviors.recent(user_id, limit=50),
            memories=await self._memories.list_by_user(user_id),
            asset_versions=asset_versions,
            current_stage=session.loop_stage if session else None,
        )

    async def collection_gate(self, user_id: str) -> "CollectionGate":
        """判一次"采集够了吗"（策略来自动态资源，见 `policies/collection_gate.py`）。

        门槛写成一条可数的规则，是为了让"什么时候往下走"不再由模型自由心证 ——
        真实用户遇到的就是反例：他只想聊两句，系统却一条接一条问下去。
        """
        fields = await self._profiles.get_fields(user_id)
        policy = await self._registry.get_collection_policy()
        gate = evaluate_gate(fields, policy)
        logger.info("采集门槛：%s", gate.line)
        return gate

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

    async def enter_task(self, user_id: str, task_code: str) -> TaskSession:
        """进入任务：已有进行中的会话则续接，否则按任务入口建会话。

        未登记的 `task_code` **必须报错**，不能静默建一个名字等于 code 的会话：
        任务码是前端从 `/app/bootstrap` 的 `task_entries` 里取的，拼错的唯一原因
        是前端与动态资源不同步 —— 静默兜底会把这件事盖住，用户看到的是一句
        自己看不懂的「任务名」，而没有任何一处报错。

        `free_chat` 这类**已登记但没有目标环节 / 主理**的入口不受影响：
        它走下面的回落分支（环节 ①、主理由组队规则选）。
        """
        existing = await self._sessions.find_active(user_id, task_code)
        if existing is not None:
            return existing

        entries = {entry.code: entry for entry in await self._registry.list_task_entries()}
        spec = entries.get(task_code)
        if spec is None:
            raise ResourceNotFound(
                f"未登记的任务入口：{task_code}。任务码须取自 /app/bootstrap 的 task_entries"
            )
        task_name = spec.label or task_code

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
        session = await self._sessions.get(request.task_id)
        if session is None:
            session = await self._sessions.create(
                TaskSession(
                    id=request.task_id,
                    user_id=request.user_id,
                    task_code="free_chat",
                    task_name="直接开聊",
                    loop_stage=LoopStage.COLLECT,
                    lead_agent="profile_analyst",
                    status=TaskStatus.ACTIVE,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )
        else:
            # 会话仓储只按 task_id 取（契约如此），归属校验必须在这里做。
            # 不校验的后果是：任何已登录用户只要拿到别人的 task_id，就能读到并
            # 继续推进别人的会话（IDOR）。按"不存在"处理而不是 403 ——
            # 不向调用方暴露"这个 id 确实存在"，也避免前端把它误读成登录态问题。
            _require_owner(session, request.user_id)

        # 幂等：同一条消息重发（双击发送、断网重试）直接返回上一次的答复。
        #
        # 前端每条消息都带 `client_msg_id`，而这条链路上**从来没有人读它** ——
        # 双击一次就是两条轮次 + 两次模型调用：记录里多一段重复的往返，
        # 用户白等一次，钱也白花一次。设计文档 9.3 第 1 步写的正是这一条。
        #
        # 重放的是**主理那一条原文**，不重放"下一步"引导：再推一次同一个问题，
        # 用户会以为又发生了什么（那时他自己已经答过了）。
        if request.client_msg_id:
            replay = await self._replay_reply(request, session)
            if replay is not None:
                return replay

        blackboard = await self.read_blackboard(request.user_id, request.task_id)
        intent = await self._intent_policy.classify(
            message=request.message, blackboard=blackboard
        )
        stage_decision = await self._stage_policy.decide(
            blackboard=blackboard, intent=intent, message=request.message
        )
        if stage_decision.need_clarify or stage_decision.stage is None:
            question = stage_decision.clarify_question or await self._clarify_text()
            result = TurnResult(
                task_id=request.task_id,
                session=session,
                stage=session.loop_stage,
                badge=await self._badge(session.lead_agent, []),
                messages=[
                    ConversationMessage(
                        role="agent", text=question, agent_id=session.lead_agent
                    )
                ],
                guide=BehaviorGuide(
                    kind="question", text=question, question=question
                ),
            )
            # 澄清这一轮**也要落库**：它此前直接 return，既不写逐轮原文、也不记行为、
            # 也不更新会话记忆 —— 用户回头翻这条会话时，这一段是空白的，
            # 而"他说过什么、被问了什么"正好是他判断"这东西有没有在记"的依据。
            await self._remember_turn(request, result, loop_stage=session.loop_stage)
            return result

        stage = stage_decision.stage
        # 采够了就往前走 —— 不等用户说"暗号"。
        #
        # 环节推进原来是**纯关键词**的：用户得说出"帮我分析"这类话才会离开 ①。
        # 而真实场景是"我就想先聊两句"：门槛早就过了，系统还在一条条追问，
        # 于是人在这里失去兴趣走了。现在按策略表判一次 —— 够了就进分析。
        # 门禁只顶掉"没命中意图"的那两种情况（progress / fallback）。
        #
        # 用户**明确**说"我不知道自己适合什么、有点迷茫"时（source=intent），
        # 他就是要回到"了解自己"这一步 —— 那时把他顶去诊断等于不听他说话，
        # 而且他后面补的情况一个字都进不了画像（诊断契约里没有字段更新）。
        # 实测就是这样：有人说了家里希望他求稳，画像里什么都没留下。
        if stage is LoopStage.COLLECT and stage_decision.source != "intent":
            gate = await self.collection_gate(request.user_id)
            if gate.ready:
                logger.info("采集门槛已过（%s），本轮直接进入诊断", gate.line)
                stage = LoopStage.DIAGNOSE
        axis_a = await self.infer_axis_a(request.user_id, request.task_id)
        lead = await self.select_lead(
            request.user_id, request.task_id, axis_a, stage, intent
        )
        disclosure = None
        if lead.lead_agent != session.lead_agent:
            handoff = await self.handoff(
                request.user_id,
                request.task_id,
                stage,
                await self._lead_change_reason(stage, lead.lead_agent),
            )
            disclosure = handoff.disclosure
            session = await self._sessions.get(request.task_id) or session
        else:
            session = await self._sessions.update_stage(
                session.id, stage, lead.lead_agent
            )

        prompt_vars: dict[str, Any] = {
            "user_input": _user_input_with_material(request),
            "task_id": request.task_id,
            "intent": intent.value,
        }
        # 共享状态中虽有画像，模型在长上下文里仍曾说“没拿到你的画像”。
        # 把已存字段提到本轮输入的显眼位置，避免把“缺岗位要求”误说成“没有画像”。
        if blackboard.profile is not None and blackboard.profile.fields:
            prompt_vars["existing_profile_facts"] = [
                {
                    "label": field.label or field.key,
                    "value": field.value,
                    "source": field.source.value,
                }
                for field in blackboard.profile.fields
            ]
        # 最近几条对话必须一并给模型（自己与他各一句）。
        #
        # 少了它，模型手上只有"这一句 + 黑板快照"：它看不到上一轮自己问了什么、用户
        # 答了什么，每一轮都像在对一个刚见面的陌生人开口 —— 接不上话，也认不出
        # "这条上一轮已经问过了"。实测症状就是"像在说梦话"：每句都像那么回事，
        # 但没有一句是在回应你。
        turn_group = await self._turn_group(request.user_id, request.task_id)
        if turn_group:
            prompt_vars["turn_group"] = turn_group
        # 这一轮如果是**点选项**而不是手打，就把那个选项的身份一并给模型。
        #
        # 只发 label 的后果实测过：用户点了「我现在还在念书」，回包又把同一个问题
        # 连同同一组选项问了一遍 —— 因为模型看到的只是一句话，它不知道那是
        # 上一轮自己给的选项之一，也就没有理由把状态往前推。带上 option_id / value
        # 之后，"用户选了什么"是可判定的，不是猜的。
        if request.option_id or request.option_value is not None:
            prompt_vars["chosen_option"] = {
                "option_id": request.option_id or "",
                "value": request.option_value,
                "label": request.message,
            }
        # 把**合法的理论卡清单**一并给模型：`theory_refs` 要填 id，
        # 而模型手上原本没有一份可选的清单，只能照名字编（实测编出过 theo_clover）。
        # 给它 id + 名字，引用才落在真实卡片上；编出来的 id 会在
        # `_known_theory_refs` 那里被剔除并留日志。
        prompt_vars["theory_cards"] = [
            {"id": card.id, "name": card.name, "school": card.school}
            for card in await self._registry.list_theory_cards()
        ]
        # 画像字段的**允许清单**（键 + 中文名）一并给模型。
        #
        # 为什么要给：字段键原来是模型自由发挥的（interest_direction /
        # course_selection_pattern / stuck_point…），而界面上要给用户看中文名、
        # 采集清单与报告维度又都按固定键取值 —— 键一散，这两件事同时坏掉。
        # 给它一份清单，它就知道该往哪条上靠；实在不属于任何一条时，
        # 契约里还留了 label 字段（见下方门禁）。
        prompt_vars["profile_keys"] = [
            {"key": spec.key, "label": spec.label}
            for spec in self._profile_vocabulary()
        ]
        # 主动取 / 只读缓存，两档见 `_EXTERNAL_FETCH_STAGES` 的说明。
        if blackboard.profile is not None and stage in (
            _EXTERNAL_FETCH_STAGES | _EXTERNAL_CACHE_ONLY_STAGES
        ):
            external = await self._fetch_external(
                user_id=request.user_id,
                message=request.message,
                profile_fields=blackboard.profile.fields,
                allow_fetch=stage in _EXTERNAL_FETCH_STAGES,
            )
            if external is not None:
                prompt_vars["external_data"] = external

        result = await self._agent_engine.invoke(
            AgentRequest(
                agent_id=lead.lead_agent,
                stage=stage.value,
                blackboard=blackboard.model_dump(mode="json"),
                prompt_vars=prompt_vars,
                output_schema=STAGE_CONTRACTS[stage].model_json_schema(),
            )
        )

        structured = result.structured or {}
        task_labels: dict[str, str] = {}
        if stage is LoopStage.REVIEW:
            plan = await self._assets.get_action_plan(request.user_id)
            task_labels = {
                task.id: task.text
                for phase in (plan.phases if plan else [])
                for task in phase.tasks
                if task.id and task.text
            }
            if structured:
                structured = _replace_task_ids_in_prose(structured, task_labels)
        # 产出不合法时必须**留痕**：契约没被满足，降级是怎么发生的要能查。
        # 之前这里直接往下走，于是"模型答了、但 JSON 少了字段"这件事
        # 在日志里一个字都没有，表现成"回复永远是同一句"。
        if not result.valid:
            logger.warning(
                "环节产出不符合契约：stage=%s agent=%s errors=%s",
                stage.value,
                lead.lead_agent,
                result.errors,
            )
        # 产出合规就**落成资产**：这一步此前完全缺失 —— 模型把 15 维诊断生成并
        # 通过契约校验之后，正文被直接丢掉，于是报告页恒空、工作台恒无版本。
        stale_before = await self._stale_asset_types(request.user_id)
        changed_assets = await self._persist_stage_output(
            stage, request.user_id, structured, valid=result.valid
        )
        # 这一轮真的把一份"待重算"的资产重算掉了 → **必须显式告知**（结论变化），
        # 否则用户手上那份旧结论被换掉而他不知道。这是设计里三种告知中的一种，
        # 此前只有"换主理"这一种真的会发出。
        if changed_assets and stale_before & {item.asset_type for item in changed_assets}:
            notice = await self._conclusion_change_disclosure()
            if disclosure is None:
                disclosure = notice
            else:
                # 同一轮里既换了主理、又重算了一份旧结论 —— 两件事都得说，
                # 不能因为契约里只有一个位置就只说一件（实测：换主理那句把
                # "结论变了"整个盖住，用户不知道手上的旧结论已经被换掉）。
                disclosure = disclosure.model_copy(
                    update={"text": f"{disclosure.text.rstrip()} {notice.text.strip()}"}
                )
        # ① 采集的产出**不是资产，是画像本身**：这一步此前同样缺失 ——
        # 见 `_apply_collect` 的说明（模型结构化返回的字段被丢掉，画像恒空）。
        #
        # **不看 `result.valid`**：采集这一环的硬指标只有一个 —— 他说的话有没有被记下来。
        # 整份产出别处不合契约（少个字段、格式歪了）不该连累这一条：字段能解析就落库，
        # 其余的问题留在日志里。`_apply_collect` 自己会挑出能解析的部分。
        if stage is LoopStage.COLLECT:
            await self._apply_collect(request.user_id, structured)
        badge = await self._badge(
            lead.lead_agent,
            await self._known_theory_refs(structured.get("theory_refs")),
        )
        guide = _guide(structured.get("guide"), structured)
        # 主理这一轮自己产出的可视件：逐个按 kind 校验（不认识的、形状不对的丢掉留日志）。
        # 模型只挑了"看哪一类"，点位是工具从库里读的 —— 校验在 `policies/renderers.py`。
        model_renderables = validate_renderables(result.renderables)
        wants_chart = _asks_for_chart(request.message)
        renderables = _renderables_for_turn(
            model_renderables,
            stage,
            structured,
            message=request.message,
            profile=await self._profiles.get(request.user_id) if wants_chart else None,
        )
        reply_text = (
            _chart_reply_text(renderables)
            if wants_chart
            else _user_facing_text(structured, guide, result.raw_text, valid=result.valid)
        )
        if stage is LoopStage.REVIEW:
            reply_text = _replace_task_ids_in_prose(reply_text, task_labels)
        messages = [
            ConversationMessage(
                role="agent",
                text=reply_text,
                agent_id=lead.lead_agent,
                theory_refs=badge.theory_refs,
                # 可视件与情报引用都来自**这一轮的实测数据**：可视件由服务端按 kind 填，
                # 引用用这一轮真的取回的外部事实 —— 不是让模型自己编。
                #
                # 两种来源，同一个形状：主理自己调的（它调 `chart.render` 时，
                # 点位是工具从库里读出来的 —— 模型只挑了"画哪一类"，碰不到数值）；
                # 它没点，就补上这一环节默认那张（仍然是实测分值）。
                renderables=renderables,
                intel_refs=_intel_refs(prompt_vars.get("external_data")),
            )
        ]
        await self._remember_turn(
            request,
            TurnResult(
                task_id=request.task_id,
                session=session,
                stage=stage,
                badge=badge,
                messages=messages,
                guide=guide,
            ),
            loop_stage=stage,
            answer_payload={
                "stage": stage.value,
                "intent": intent.value,
                # 点选项与手打要分得开：复盘"用户是怎么答的"时，
                # "点了哪个选项"是行为本身的一部分，丢了就只剩一句文字。
                **({"option_id": request.option_id} if request.option_id else {}),
            },
        )
        # 这一轮可能改了画像（① 采集）、资产（②③④ 产出）或会话状态 —— 工作台那一片失效。
        # 只报"发生了什么"：哪片缓存受影响由动态资源里的策略决定。
        if self._cache is not None:
            for event in ("profile_field_updated", "asset_version_changed", "session_changed"):
                await self._cache.invalidate_for_event(event)
        await self._log_stage_events(
            stage,
            request,
            valid=result.valid,
        )
        return TurnResult(
            task_id=request.task_id,
            session=session,
            stage=stage,
            badge=badge,
            messages=messages,
            disclosure=disclosure,
            guide=guide,
            asset_versions=changed_assets,
        )

    async def _replay_reply(
        self, request: TurnRequest, session: TaskSession
    ) -> Optional[TurnResult]:
        """这条消息是不是答过了？答过就把上次那条原文再给一次。

        只回**主理那一句**，不带 guide：重复的"下一步"会让人以为又发生了什么。
        读不到（老数据没有这个键、或收藏层没接）就返回 None，照常走这一轮 ——
        幂等是省一次调用，不是拦下用户的话。
        """
        try:
            reply = await self._memories.find_reply(
                request.user_id, request.client_msg_id or ""
            )
        except Exception:  # noqa: BLE001 - 幂等查询失败不该拦下这一轮
            logger.warning(
                "幂等查询失败（client_msg_id=%s），按新消息处理",
                request.client_msg_id,
                exc_info=True,
            )
            return None
        if reply is None or not reply.text.strip():
            return None
        logger.info("重复消息（client_msg_id=%s），返回上一次的答复", request.client_msg_id)
        return TurnResult(
            task_id=request.task_id,
            session=session,
            stage=session.loop_stage,
            badge=await self._badge(reply.agent_id or session.lead_agent, []),
            messages=[
                ConversationMessage(
                    role="agent", text=reply.text, agent_id=reply.agent_id or None
                )
            ],
            guide=BehaviorGuide(kind="question", text="", question=None),
        )

    async def _remember_turn(
        self,
        request: TurnRequest,
        result: TurnResult,
        *,
        loop_stage: LoopStage,
        answer_payload: dict[str, Any] | None = None,
    ) -> None:
        """把这一轮记进三本账：会话摘要、逐轮原文、行为日志。

        三条都**不影响回包**：任何一条写不进去都只记日志，让用户这一轮已经说完的话
        不至于白说（与本文件其它落库口径一致）。

        摘要写的是**人话**（他那一句 + 主理那一句），不再是模型的产出 JSON。
        原来那是 `result.raw_text`（一整坨 JSON），实测 12 轮就长到 24.9KB，
        每一轮都随黑板塞回模型：既是白花的 token，也会让模型把五轮前的旧结论
        当成当前的。摘要的用处是"接着上次聊"，那就该是对话本身。
        """
        lead_agent = result.badge.agent_id if result.badge else ""
        spoken = " ".join(
            _single_line(message.text) for message in result.messages if message.text
        )
        try:
            await self._memories.upsert(
                request.user_id,
                request.task_id,
                loop_stage=loop_stage,
                lead_agent=lead_agent,
                summary_delta=f"他：{_single_line(request.message, limit=60)}\n"
                f"主理：{_single_line(spoken, limit=120)}\n",
            )
        except Exception:  # noqa: BLE001
            logger.exception("会话摘要落库失败：task_id=%s", request.task_id)

        # 逐轮原文也要留一份：摘要给模型续接用，原文给"会话列表点进去看历史"
        # 与复盘取证用。少了它，"回到旧会话"只能是空屏。
        try:
            await self._memories.record_turn(
                request.user_id,
                request.task_id,
                role="user",
                text=request.message,
                loop_stage=loop_stage,
                client_msg_id=request.client_msg_id or "",
            )
            for message in result.messages:
                await self._memories.record_turn(
                    request.user_id,
                    request.task_id,
                    role=message.role,
                    text=message.text,
                    loop_stage=loop_stage,
                    agent_id=message.agent_id or "",
                    # 主理那一轮也带上幂等键：下一次重复消息靠它认出"这条答过了"。
                    client_msg_id=request.client_msg_id or "",
                )
        except Exception:  # noqa: BLE001 - 原文落库失败不该让这一轮白答
            logger.exception("对话原文落库失败：task_id=%s", request.task_id)

        # 行为日志：每答一轮就是一次动作。停滞检测、环节推进、复盘时间线都读它。
        try:
            await self._behaviors.log(
                request.user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.ANSWER, payload=dict(answer_payload or {})
                ),
            )
        except Exception:  # noqa: BLE001
            logger.exception("行为日志落库失败：task_id=%s", request.task_id)

    async def _log_stage_events(
        self, stage: LoopStage, request: TurnRequest, *, valid: bool
    ) -> None:
        """把"这一步真的发生了什么"记进行为日志。

        为什么必须记：行为日志是**唯一的事实来源** —— 停滞干预靠它判断"他最近有没有动作"，
        环节推进靠它判断"能不能往下走"，复盘时间线靠它说清"这段时间发生过什么"。
        少记一条，链条上就有一处永远读不到东西，而且不报错。

        这里补的三条此前**都没有生产者**（枚举、干预白名单、轴A 判定里都写着它们，
        而全仓没有一处写）：

        · ② 认领差距：用户在诊断环节点了一个选项，就是认领了那一条差距 ——
          这正是设计里 ②→③ 的衔接点（见 `Report.gap_claims` 与 `GapClaim`）；
        · ⑤ 完成复盘：复盘环节产出了合规结论，才算走过一次复盘；
        · ④ 任务停滞：由停滞 Worker 记（不在这里，见 `workers/active_event.py`）。
        """
        if stage is LoopStage.DIAGNOSE and request.option_id:
            await self._behaviors.log(
                request.user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.GAP_CLAIM,
                    payload={
                        "stage": stage.value,
                        "gap_id": request.option_id,
                        # 原话一起留：报告与复盘要能显示"他认领的是哪一条"，
                        # 只存一个 id 的话，界面上只剩一串没人看得懂的标识。
                        "label": request.message,
                    },
                ),
            )
        if stage is LoopStage.REVIEW and valid:
            await self._behaviors.log(
                request.user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.REVIEW,
                    payload={"stage": stage.value},
                ),
            )

    async def _persist_stage_output(
        self,
        stage: LoopStage,
        user_id: str,
        structured: dict[str, Any],
        *,
        valid: bool,
    ) -> list[AssetVersion]:
        """把合规的环节产出落成资产正文，返回本轮变化的资产版本。

        三条口径：

        1. **只落合规产出**。契约没过就不存 —— 存一份缺字段的报告比不存更坏：
        报告页会把它当成"完整报告"展示给用户，而它连 SWOT 都不齐。
        2. **落库失败不打断对话**。资产写不进去是服务端的事，用户这一轮的话已经答完了；
        这里记日志并继续，让错误出现在日志里而不是用户的屏幕上。
        3. **①采集 / ⑤复盘不产资产**：采集改的是画像（ProfileService 已在写），
        复盘产的是跟踪事件（走 FunctionService），都不该在这里顺手造一个空资产。
        """
        if not valid or not structured:
            return []

        converters = {
            LoopStage.DIAGNOSE: self._save_report,
            LoopStage.DECIDE: self._save_direction_plans,
            LoopStage.ACT: self._save_action_plan,
        }
        saver = converters.get(stage)
        if saver is None:
            return []

        try:
            return await saver(user_id, structured)
        except Exception:  # noqa: BLE001 - 落库失败不能让用户这一轮白说
            logger.exception("环节产出落库失败：stage=%s", stage.value)
            return []

    async def _apply_collect(self, user_id: str, structured: dict[str, Any]) -> None:
        """把 ① 采集这一轮的字段与缺口落进画像。

        为什么必须有这一步
        ------------------
        采集环节的产出**不是资产**，它就是画像本身：模型把
        "兴趣 = 结构设计、把握 0.8、来源 对话" 结构化地返回了，
        此前这里没有任何落库路径 —— 读完就丢。后果是三重的，而且都不报错：

          · 画像面板恒空（用户回答了一堆，界面上还是"进入对话完成首次建档"）；
          · 采集清单恒说"还缺 6 条"（缺口从没被更新过）；
          · ② 诊断照样能凭对话记忆生成 15 维报告（看起来一切正常），
            但那份报告**没有画像依据**，`depends_on_profile_keys` 是空的，
            于是"画像一变就重算受影响资产"这条影响面传播也一并失效。

        落库失败不打断这一轮：用户的话已经答完了，错误进日志即可（与资产落库同一条口径）。
        """
        from zhiyin_business.contracts.collect import CollectOutput, FieldUpdate

        try:
            output = CollectOutput.model_validate(structured)
        except Exception:  # noqa: BLE001
            # 整份不合契约时，**仍然把能解析的字段捞出来**。
            #
            # 这是这一环唯一的硬指标：他说的话有没有被记下来。因为缺了别的字段
            # （比如没写 conclusion、少了一个数组）就把这一轮的画像更新整段丢掉，
            # 代价是用户白说一遍、采集清单还挂着"还差 N 条" —— 而那正是他刚答过的。
            salvaged: list[Any] = []
            for item in structured.get("field_updates") or []:
                if not isinstance(item, dict):
                    continue
                try:
                    salvaged.append(FieldUpdate.model_validate(item))
                except Exception:  # noqa: BLE001 - 这一条解析不了就跳过这一条
                    continue
            if not salvaged:
                logger.warning("① 采集产出里没有可解析的字段，本轮不写画像")
                return
            logger.warning(
                "① 采集产出不合契约，仍从里面救回 %d 条字段更新", len(salvaged)
            )
            output = CollectOutput(field_updates=salvaged)

        allowed = self._allowed_profile_keys()
        dropped: list[str] = []
        written: list[str] = []
        for update in output.field_updates:
            key = self._normalize_profile_key(update.key)
            # **字段门禁**：画像只有一份固定词表（动态资源的采集规则）。
            # 不在表里的键一律不写 —— 放进去的代价不是"多一条记录"，
            # 而是界面上多一条没人认识、也没有中文名的东西，
            # 采集清单与报告维度又都对不上它，整份画像从此不可分析。
            if allowed and key not in allowed:
                dropped.append(update.key)
                continue
            try:
                await self._profiles.update_field(
                    user_id,
                    key,
                    update.value,
                    confidence=update.confidence,
                    source=update.source.value,
                    # 名字跟着字段一起落库：字段键是模型自己起的（interest_direction
                    # 这种），界面没有中文名就只剩一串英文。
                    label=update.label,
                    evidence=list(update.evidence),
                )
            except Exception:  # noqa: BLE001 - 同资产：一条写不进去不该断整轮
                logger.exception("画像字段落库失败：key=%s", update.key)
                continue
            written.append(key)

        # 画像更新本身也是一次**动作**：干预判定要能看见"他刚补了信息"，
        # 否则一个只补画像、不勾任务的人会被判成"好几天没动"。
        # 这条事件类型一直躺在干预白名单里，此前没有任何生产者（实测库里 0 行）。
        for key in written:
            await self._behaviors.log(
                user_id,
                BehaviorEventDraft(
                    event_type=BehaviorEventType.PROFILE_FIELD_UPDATED,
                    payload={"field_key": key, "stage": LoopStage.COLLECT.value},
                ),
            )

        if dropped:
            # 不静默：被门禁挡掉的键要能被发现（多半是提示词需要补一条同义词）
            logger.warning(
                "画像字段门禁挡下不在词表里的键：%s（当前词表 %d 条）",
                sorted(set(dropped)),
                len(allowed),
            )

        # **画像真的变了**才作废那份"外部情报"（它是按画像取的）。
        # 不丢的话，新用户先取过一次空的，补完画像之后十几分钟里界面还是空；
        # 但**每轮都丢**的代价更大：采集阶段每轮都会重爬一遍外部站点（实测 10 次请求、
        # 约 7 秒），而多数轮次一个字段都没改 —— 用户为此白等，站点也被白打。
        if written and self._functions is not None:
            self._functions.drop_intel_cache(user_id)

        if output.remaining_gaps:
            # 缺口与字段走**同一套**归一与词表：它们指的是同一批东西
            # （"还差专业"和"专业已拿到"必须对得上）。只归一字段不归缺口的话，
            # 界面上就会出现"字段叫「学历层次」、缺口叫 education_stage"这种自相矛盾。
            labels = {spec.key: spec.label for spec in self._profile_vocabulary()}
            normalized: list[Any] = []
            for gap in output.remaining_gaps:
                key = self._normalize_profile_key(gap.key)
                if allowed and key not in allowed:
                    continue
                normalized.append(
                    gap.model_copy(
                        update={"key": key, "label": gap.label or labels.get(key, "")}
                    )
                )
            blocked = [
                self._normalize_profile_key(gap.key)
                for gap in output.remaining_gaps
                if allowed and self._normalize_profile_key(gap.key) not in allowed
            ]
            if blocked:
                logger.warning("画像缺口门禁挡下不在词表里的键：%s", sorted(set(blocked)))
            if not normalized:
                # 本轮缺口全被门禁挡下（多半是模型自己发明了键）：
                # **保留上一份清单**，不要用空表覆盖 —— 空表和"没有缺口"
                # 在界面上是同一句话，而那会与采集清单里的"还差 N 条"自相矛盾。
                logger.warning("本轮缺口全部不在词表里，保留上一份清单")
            else:
                try:
                    await self._profiles.replace_gaps(user_id, normalized)
                except Exception:  # noqa: BLE001
                    logger.exception("画像缺口落库失败")

    def _allowed_profile_keys(self) -> set[str]:
        """画像允许的字段键（动态资源里的画像字段词表；读不到时返回空集＝不拦）。

        读不到就不拦：把"配置没装载"变成"用户说的话被丢掉"，比多几条字段坏得多。
        """
        return {
            spec.key for spec in self._profile_vocabulary() if not spec.alias_of
        }

    def _normalize_profile_key(self, key: str) -> str:
        """把模型写的同义词归到规范键上（`grade` → `degree_level`）。

        不做这一步的后果，实测是这样的：同一个意思在不同轮次被写成
        `internship` / `internship_experience` / `experience` 三条，
        画像里三格都占着，而采集清单还在说"实习经历没拿到"。
        """
        raw = (key or "").strip()
        for spec in dynamic_config.snapshot().profile_fields:
            if spec.alias_of and spec.key == raw:
                return spec.alias_of
        return raw

    @staticmethod
    def _profile_vocabulary() -> tuple[Any, ...]:
        """画像字段词表（键 + 中文名），来自装载好的动态配置快照。

        与界面显示名**同一份**：文案包里的 `profile.field.<键>`。
        """
        return dynamic_config.snapshot().profile_fields

    async def _asset_dependencies(self, user_id: str) -> list[str]:
        """这份资产依赖哪些画像字段。

        取当前画像的**全部字段键**：诊断/决策/行动都是拿整份画像得出的结论，
        声称"只依赖其中三个"会让影响面传播漏掉该重算的资产。
        将来若真的按字段片段生成，这里改成从产出里取证据链即可。
        """
        profile = await self._profiles.get(user_id)
        return [field.key for field in (profile.fields if profile else [])]

    async def _save_report(self, user_id: str, structured: dict[str, Any]) -> list[AssetVersion]:
        from zhiyin_business.contracts.diagnose import DiagnoseOutput
        from zhiyin_business.services.asset_content import report_from_diagnose

        output = DiagnoseOutput.model_validate(structured)
        report = report_from_diagnose(output, user_id=user_id)
        # 认领是**用户行为**，不该被重算冲掉：报告里的 gap_claims 是从行为日志
        # 还原出来的快照，而不是模型这一轮的输出。事实来源只有一个（行为日志），
        # 报告只是把"他已经认领了哪几条"摆回正文里给他看得见。
        claims = await self._claimed_gaps(user_id)
        if claims:
            report = report.model_copy(update={"gap_claims": claims})
        version = await self._assets.save_report(
            user_id,
            report,
            depends_on_profile_keys=await self._asset_dependencies(user_id),
            diff_from_previous="② 诊断产出：15 维与 SWOT",
        )
        return [version]

    async def _claimed_gaps(self, user_id: str) -> list[GapClaim]:
        """用户认领过的差距（事实来源是行为日志，见 `_log_stage_events`）。

        读不到就返回空表：认领记录丢了不该让这一轮报告生成失败，
        更不该编一条出来（报告的每一格都要能追回一条真实记录）。
        """
        try:
            behaviors = await self._behaviors.recent(user_id, limit=50)
        except Exception:  # noqa: BLE001
            logger.warning("读取认领记录失败，报告里的差距认领按空处理", exc_info=True)
            return []
        claims: list[GapClaim] = []
        seen: set[str] = set()
        for event in behaviors:
            if event.event_type is not BehaviorEventType.GAP_CLAIM:
                continue
            gap_id = str(event.payload.get("gap_id") or "").strip()
            if not gap_id or gap_id in seen:
                continue
            seen.add(gap_id)
            claims.append(
                GapClaim(
                    gap_id=gap_id,
                    label=str(event.payload.get("label") or ""),
                    claimed_at=event.occurred_at,
                )
            )
        return claims

    async def _save_direction_plans(
        self, user_id: str, structured: dict[str, Any]
    ) -> list[AssetVersion]:
        from zhiyin_business.contracts.decide import DecideOutput
        from zhiyin_business.services.asset_content import direction_plans_from_decide

        output = DecideOutput.model_validate(structured)
        if not output.plans:
            # 一套方案都没有的"决策"不是决策：语义上应当回落到澄清追问，
            # 这里不落库（落一个空方案组会让工作台显示"已有方案"）。
            logger.warning("③ 决策产出里没有方案，未落库（应回落到澄清追问）")
            return []
        plans = direction_plans_from_decide(output, user_id=user_id)
        version = await self._assets.save_direction_plans(
            user_id,
            plans,
            depends_on_profile_keys=await self._asset_dependencies(user_id),
            diff_from_previous=f"③ 决策产出：{len(plans)} 套方向方案",
        )
        return [version]

    async def _save_action_plan(
        self, user_id: str, structured: dict[str, Any]
    ) -> list[AssetVersion]:
        from zhiyin_business.contracts.act import ActOutput
        from zhiyin_business.services.asset_content import action_plan_from_act

        output = ActOutput.model_validate(structured)
        if output.need_recheck_direction:
            # 拆不动就回 ②，不要硬拆 —— 这一条是产出契约里写明的前置判断。
            logger.info("④ 行动产出要求回 ② 复核方向，未落库")
            return []
        plan, nodes = action_plan_from_act(output, user_id=user_id)
        # 关键节点日历：规划师写入、教练读取。先写日历再存计划 ——
        # 顺序反过来的话，`reminders_synced=True` 会在日历还没写进去时就落库。
        if self._functions is not None and nodes:
            for node in nodes:
                await self._functions.write_calendar_node(user_id, node)
            plan = plan.model_copy(update={"reminders_synced": True})
        version = await self._assets.save_action_plan(
            user_id,
            plan,
            depends_on_profile_keys=await self._asset_dependencies(user_id),
            diff_from_previous="④ 行动产出：阶段与任务",
        )
        return [version]

    async def _badge(self, agent_id: str, theory_refs: list[TheoryRef]) -> AgentBadge:
        descriptor = await self._registry.get_agent(agent_id)
        return AgentBadge(
            agent_id=agent_id,
            name=descriptor.name if descriptor else agent_id,
            role_summary=descriptor.role_summary if descriptor else "",
            theory_refs=theory_refs,
        )

    async def _known_theory_refs(self, raw: Any) -> list[TheoryRef]:
        """只保留**真实存在**的理论卡引用。

        为什么要在边界上筛：`theory_refs` 是模型给的。模型手里没有一份"合法 id 清单"，
        于是会照名字编一个（实测拿到过 `theo_clover`，而真卡 id 是 `clover`）。
        前端拿到这种 id 会**如实去请求** `GET /app/theory-cards/theo_clover` → 404，
        用户点开是一张打不开的卡 —— 而它本来就不该出现在界面上。

        筛掉不等于装作没发生：进日志（WARNING），这样"模型在编 id"这件事看得见，
        可以顺着去补提示词或给模型一份清单，而不是静默吞掉。
        """
        refs = _theory_refs(raw)
        if not refs:
            return []
        known = {card.id for card in await self._registry.list_theory_cards()}
        kept: list[TheoryRef] = []
        for ref in refs:
            if ref.theory_id in known:
                kept.append(ref)
            else:
                logger.warning(
                    "理论卡引用不存在，已从徽章里剔除：id=%s（模型可能编了 id）",
                    ref.theory_id,
                )
        return kept

    # ------------------------------------------------------------------
    # 对话回灌：上一轮说了什么
    # ------------------------------------------------------------------

    #: 回灌几轮。规格是"最近三条对话（自己与他各一句）"，一条对话两轮，
    #: 取 6 条正好是三次来回；再多只会把这一轮真正要看的东西挤下去。
    _TURN_GROUP_SIZE = 6
    #: 扫描上限。仓储接口是"按时间正序 + LIMIT"，返回的是**最早**的若干条，
    #: 所以这里只能多取一批再从尾巴上切。上限与前端"点开历史"用的是同一个量级。
    _TURN_GROUP_SCAN = 200
    #: 每行上限。原文里可能有几百字的附件正文（用户传一份简历就是一整篇）。
    _TURN_LINE_MAX = 30

    async def _turn_group(self, user_id: str, task_id: str) -> list[str]:
        """最近几条对话的短行（`他：…` / `职业顾问：…`）。

        取**逐轮原文**（`biz_conversation_turn`），不是累积摘要：摘要里塞的是历次
        产出的 JSON 原文，越到后面越像一坨内部数据，模型读不出"刚才聊到哪"。

        取不到就返回空表 —— 这一轮照常走完，只是"接不上话"这件事会如实留在
        这一轮里，而不是拿一份编出来的对话顶上。
        """
        try:
            turns = await self._memories.list_turns(
                user_id, task_id, limit=self._TURN_GROUP_SCAN
            )
        except Exception:  # noqa: BLE001 - 回灌失败不该吃掉用户这一轮的话
            logger.warning("读取逐轮原文失败：task_id=%s", task_id, exc_info=True)
            return []
        lines: list[str] = []
        for turn in turns[-self._TURN_GROUP_SIZE :]:
            text = _single_line(turn.text, limit=self._TURN_LINE_MAX)
            if not text:
                continue
            who = "他" if turn.role == "user" else await self._spoken_name(turn.agent_id)
            lines.append(f"{who}：{text}")
        return lines

    async def _spoken_name(self, agent_id: str) -> str:
        """agent_id → 用户称呼；取不到就用「主理」顶上。

        与 `_display_name` 不同，这里**不抛**：回灌的是历史，一句称呼缺了，
        不该让用户这一轮已经说完的话白说。
        """
        if not agent_id:
            return "主理"
        descriptor = await self._registry.get_agent(agent_id)
        name = descriptor.name if descriptor else ""
        return name or "主理"

    async def _stale_asset_types(self, user_id: str) -> set[AssetType]:
        """哪些资产的当前版本是"画像变过、还没重算"的。

        读的是三本正文资产的最新版本标记（见 `AssetVersion.needs_recompute`）。
        读不到不算这一轮失败：标记只用来决定"要不要补一句告知"，
        所以异常按"没有待重算的资产"处理并留日志。
        """
        stale: set[AssetType] = set()
        for asset_type in (
            AssetType.REPORT,
            AssetType.DIRECTION_PLAN,
            AssetType.ACTION_PLAN,
        ):
            try:
                latest = await self._assets.get_latest_version(user_id, asset_type)
            except Exception:  # noqa: BLE001
                logger.warning("读取资产待重算标记失败：%s", asset_type.value, exc_info=True)
                continue
            if latest is not None and latest.needs_recompute:
                stale.add(asset_type)
        return stale

    async def _conclusion_change_disclosure(self) -> Disclosure:
        """结论变化告知。文案取自动态资源，缺配置直接抛（不用字面量顶上）。"""
        prompt = await self._required_prompt(_CONCLUSION_CHANGE_PROMPT)
        return Disclosure(kind="conclusion_change", text=prompt.content.strip())

    # ------------------------------------------------------------------
    # 用户可见文案：取自动态资源，代码里不再拼句子
    #
    # 这两段以前都是**写在代码里的字符串**，而且拼接时把内部概念直接带给了用户：
    #   · 换主理的理由写成「进入 collect 环节，改由 career_advisor 主理」——
    #     环节枚举与智能体标识对用户毫无意义，还会让人以为系统漏了翻译；
    #   · 澄清追问写成一句字面量，改一次口径要发一次版。
    # 现在两个占位符都来自数据：接手人的**用户称呼**与该环节的**用户说法**。
    #
    # 三处都**不做兜底**：配置缺了就抛。兜底句看着稳妥，代价是把"少了一条配置"
    # 变成"这一轮回答得有点怪"，等有人察觉时已经不知道该查哪一天。
    # ------------------------------------------------------------------

    async def _clarify_text(self) -> str:
        """全新会话的澄清追问。配置缺失直接抛，不用字面量顶上。"""
        prompt = await self._registry.get_prompt(CLARIFY_PROMPT_CODE)
        if prompt is None or not prompt.content.strip():
            raise MissingConfigError(f"缺少澄清话术配置：{CLARIFY_PROMPT_CODE}")
        return prompt.content.strip()

    async def _lead_change_reason(self, stage: LoopStage, to_agent: str) -> str:
        """换主理时对用户说的那句话：谁接手 + 为什么。"""
        reason_code = _LEAD_CHANGE_REASON_PROMPT.format(stage=stage.value)
        template = await self._required_prompt(_LEAD_CHANGE_PROMPT)
        reason = await self._required_prompt(reason_code)
        to_name = await self._display_name(to_agent)
        # 占位符对不上会在这里抛 KeyError：那是配置错，不是运行故障，不该被吞掉。
        return template.content.format(to_name=to_name, reason=reason.content)

    async def _display_name(self, agent_id: str) -> str:
        """agent_id → 用户称呼。取不到就抛：把标识念给用户听等于没配。"""
        descriptor = await self._registry.get_agent(agent_id)
        if descriptor is None or not descriptor.name:
            raise MissingConfigError(f"智能体展示名缺失：{agent_id}")
        return descriptor.name

    async def _required_prompt(self, code: str) -> PromptSpec:
        prompt = await self._registry.get_prompt(code)
        if prompt is None:
            raise MissingConfigError(f"缺少提示词配置：{code}")
        return prompt


def _guide(raw: Any, structured: dict[str, Any] | None = None) -> BehaviorGuide:
    """本轮该对用户说的那句话。

    这里曾经用一句**写死的**文案兜底（"你愿意先说说现在最卡的那一步吗？"）。
    后果很严重：模型明明答了，只是它的 JSON 少了 `guide` 字段（契约里
    `guide` 是必填，模型经常漏），于是每个回合、无论用户说什么，
    界面上都是同一句话 —— 用起来就像接了个假模型。

    所以兜底的顺序改成"尽量用**模型自己写的内容**"：
      1. 模型给了合法 guide → 直接用；
      2. 没给，但它给了 `remaining_gaps[].suggested_next_action`
         —— 那本来就是模型写的"下一步该问什么"，直接拿它当追问；
      3. 都没有 → 才用系统兜底句，而且措辞要像是系统在说话，不是主理在说话。
    """
    if isinstance(raw, dict):
        try:
            return BehaviorGuide.model_validate(raw)
        except Exception:
            pass

    for gap in (structured or {}).get("remaining_gaps") or []:
        if not isinstance(gap, dict):
            continue
        action = str(gap.get("suggested_next_action") or "").strip()
        if action:
            return BehaviorGuide(kind="question", text=action, question=action)

    return BehaviorGuide(
        kind="question",
        text="这一轮我没能按格式产出内容。你再说一句，我重新试。",
        question="这一轮我没能按格式产出内容。你再说一句，我重新试。",
    )


def _theory_refs(raw: Any) -> list[TheoryRef]:
    if not isinstance(raw, list):
        return []
    refs: list[TheoryRef] = []
    for item in raw:
        if isinstance(item, dict):
            try:
                refs.append(TheoryRef.model_validate(item))
            except Exception:
                continue
    return refs


def _renderables_for_turn(
    from_model: Sequence[Renderable],
    stage: Any,
    structured: dict[str, Any],
    *,
    message: str = "",
    profile: Any = None,
) -> list[Renderable]:
    """这一轮要摆给用户看的可视件：主理自己点的那张，或者这一环节默认那张。

    **只有一种形状**（`Renderable`），前端按 `kind` 分发渲染。
    以前这里另有一条"柱状图专用字段 `chart`"的兼容通道 —— 前端当时只认它。
    现在前端按 kind 走，那条通道就删了：少了"同一张图有两个字段"的歧义
    （改一处漏一处，就会出现"图没变、别处变了"这种说不清的现象）。

    默认那张只从**实测分值**里取点：
      · ② 诊断 —— 画像各维的把握度（"你现在哪一块最薄"一眼能看出来）；
      · ③ 决策 —— 三套方案的匹配度（"三套差多少"比三行字清楚）。
    取不到就不补：宁可没有图，也不要拿编出来的数字画一张。
    """
    kept = list(from_model)
    if any(item.kind == "bars_chart" for item in kept):
        return kept
    if _asks_for_chart(message):
        fields = list(getattr(profile, "fields", []) or [])
        points = [
            {
                "label": str(field.label or field.key)[:12],
                "value": field.confidence,
            }
            for field in fields
            if field.confidence is not None and (field.label or field.key)
        ]
        if len(points) >= 2:
            kept.extend(
                validate_renderables(
                    [{
                        "kind": "bars_chart",
                        "title": "这几项你现在各有多少把握",
                        "payload": {"unit": "%", "points": points[:8]},
                    }]
                )
            )
            if any(item.kind == "bars_chart" for item in kept):
                return kept
    fallback = _default_bars(stage, structured)
    if fallback is not None:
        kept.extend(validate_renderables([fallback.model_dump(mode="json")]))
    return kept


def _asks_for_chart(message: str) -> bool:
    text = message.strip()
    return any(word in text for word in (
        "画个图", "画张图", "画一个图", "画图", "给我一张图",
        "生成图表", "做个图表", "做张图表", "看图表", "看看图表",
        "展示图表", "用图表", "画柱状图", "看柱状图",
        "可视化一下", "做个可视化", "给我可视化", "看看可视化",
    ))


def _chart_reply_text(renderables: list[Renderable]) -> str:
    """明确要图时用已核验图点生成回话，避免模型文字否认已存事实。"""
    labels = list(dict.fromkeys(
        str(point.get("label") or "").strip()
        for chart in renderables
        for point in (chart.payload.get("points") or [])
        if isinstance(point, dict) and str(point.get("label") or "").strip()
    ))
    if not labels:
        return "目前没有足够的可用数据生成图表；补充记录后可以再看。"
    shown = "、".join(labels[:4])
    suffix = f"等 {len(labels)} 项" if len(labels) > 4 else ""
    return f"图表已生成，展示已存记录中的{shown}{suffix}。这张图只呈现这些记录，不代表职业匹配结论。"


def _default_bars(stage: Any, structured: dict[str, Any]) -> Optional[Renderable]:
    """这一环节顺手给的那张柱状图（点全部来自库里已存的分值）。"""
    try:
        if stage is LoopStage.DECIDE:
            points = [
                {
                    "label": str(plan.get("name") or f"方案{i + 1}")[:12],
                    "value": float(plan["match_score"]),
                }
                for i, plan in enumerate(structured.get("plans") or [])
                if isinstance(plan, dict)
                and isinstance(plan.get("match_score"), (int, float))
            ]
            if len(points) >= 2:
                # 标题是**用户要读的**：不写"三套方案"这种内部说法（实测用户看不懂
                # "三条路""三套方案"指的是什么），写他一看就懂的那件事。
                return Renderable(
                    kind="bars_chart",
                    title="各方向和你手上的东西合不合",
                    payload={"unit": "分", "points": points},
                )
        if stage is LoopStage.DIAGNOSE:
            points = [
                {
                    "label": str(item.get("name") or item.get("dimension") or "")[:12],
                    "value": float(item.get("score") or item.get("value") or 0.0),
                }
                for item in (structured.get("gaps") or structured.get("dimensions") or [])
                if isinstance(item, dict)
            ]
            points = [point for point in points if point["label"]]
            if len(points) >= 3:
                return Renderable(
                    kind="bars_chart",
                    title="这几项你现在各有多少把握",
                    payload={"unit": "分", "points": points[:8]},
                )
    except Exception:  # noqa: BLE001 - 画不出图不该影响这一轮回复
        logger.warning("这一轮没能构造默认可视件，跳过", exc_info=True)
    return None


def _intel_refs(external: Any) -> list[IntelRef]:
    """这一轮真的取回的外部事实，做成可点回原页面的引用。

    `external` 是 `DataSourceResult.model_dump()` 之后的样子（见 prompt_vars）。
    没有取到就是空表 —— 不编来源。
    """
    records = (external or {}).get("records") if isinstance(external, dict) else None
    refs: list[IntelRef] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        url = str(record.get("source_url") or "")
        if not url:
            continue
        refs.append(
            IntelRef(
                id=str(record.get("id") or ""),
                title=str(record.get("title") or "")[:60],
                kind_label=kind_label(str(record.get("kind") or "")),
                source_name=source_name_of(url),
                source_url=url,
            )
        )
    return refs[:4]


def _replace_task_ids_in_prose(value: Any, task_labels: dict[str, str]) -> Any:
    """复盘正文用任务文字称呼已登记任务，保留结构中的机器 ID。"""
    if isinstance(value, dict):
        return {
            key: item if key in {"id", "task_id", "option_id", "achievements_unlocked"}
            else _replace_task_ids_in_prose(item, task_labels)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_task_ids_in_prose(item, task_labels) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    for task_id, label in sorted(task_labels.items(), key=lambda pair: len(pair[0]), reverse=True):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(task_id)}(?![A-Za-z0-9_])"
        text = re.sub(pattern, lambda _match, label=label: f"「{label}」", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])[ \t]+(?=「)", "", text)
    return re.sub(r"(?<=」)[ \t]+(?=[\u4e00-\u9fff])", "", text)


def _single_line(text: str, *, limit: int = 0) -> str:
    """把一段原文压成一行：换行与连续空白折成单空格，超长（limit>0）截断。

    回灌给模型的对话必须是短行：用户传一份简历进来，原文就是几百上千字，
    照抄进去会把这一轮真正要看的东西挤出上下文。
    """
    collapsed = " ".join((text or "").split())
    if limit and len(collapsed) > limit:
        return collapsed[:limit] + "…"
    return collapsed


def _prose_of(raw_text: str) -> str:
    """从模型原文里取出"它其实在对人说"的那句话。

    产出不合契约时有两种情况，必须分开对待：
      · 模型根本没答（空、或只有一句报错）→ 只能用系统兜底句；
      · 模型答得好好的，只是没套进 JSON（这是最常见的）→ **把它说的话给用户**。
        以前两种情况都掉进系统兜底句，于是用户连问三次都看到同一句
        "我没能按格式产出" —— 明明台上那个人说得挺清楚。
    """
    text = (raw_text or "").strip()
    if len(text) < 12:
        return ""
    if text.startswith("{") or text.startswith("["):
        # 是 JSON 而不是人话：不值得整段丢给用户
        return ""
    if text.startswith("```"):
        return ""
    return text[:600] + ("…" if len(text) > 600 else "")


def _user_facing_text(
    structured: dict[str, Any], guide: Any, raw_text: str, *, valid: bool = True
) -> str:
    """最短结论进对话流：结论字段 → （产出不合契约时）模型原话 → 行为引导文案。

    五个环节的契约里都有 `conclusion`，它就是"这一轮对他说的一句话结论"。

    顺序不能反：`guide.text` 写的是「为什么现在问这个」（给人看清下一步的由头），
    它**不是**结论。以前没有 conclusion 时这里落到 guide.text，用户读到的每一句
    都是"我为什么要问你"——话都对，但没有一句是在回他。

    原始 JSON 属于长内容，只允许截断兜底，绝不整段给用户。
    """
    for key in ("conclusion", "summary", "headline"):
        value = structured.get(key)
        if isinstance(value, str) and value.strip():
            # 结论可能被模型写成两三行；对话里它得是一行，否则气泡会散开。
            return _single_line(value)
    if not valid:
        prose = _prose_of(raw_text)
        if prose:
            return prose
    text = getattr(guide, "text", "")
    if isinstance(text, str) and text.strip():
        return text.strip()
    raw = (raw_text or "").strip()
    return raw[:200] + ("…" if len(raw) > 200 else "") or "本轮已按当前环节完成分析。"


def _user_input_with_material(request: TurnRequest) -> str:
    """模型看到的用户输入：他说的话 + 这一轮带上来的材料正文。

    **只有模型输入这一条路会拼上正文**：`request.message` 才是落库、也是显示的那一句
    （"我传了一份材料：简历.txt"）。正文进对话流正是用户抱怨过的那件事 ——
    一份简历几百段铺在气泡里，他要读的是主理的回话，不是自己刚交上去的东西。
    """
    text = (request.attachment_text or "").strip()
    if not text:
        return request.message
    label = request.attachment_name or "用户上传的材料"
    head = request.message.strip() or f"我传了一份材料：{label}"
    return f"{head}\n\n【用户上传的材料：{label}】\n{text}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_owner(session: TaskSession, user_id: str) -> None:
    """任务会话的归属校验。

    为什么必须有：`TaskSessionRepository.get(session_id)` 的签名里**没有** user_id
    （它要服务"按 id 取会话"的通用场景），所以越权只能在使用侧拦。少了这一步，
    任何已登录用户只要知道别人的 `task_id`，就能读到并继续推进别人的会话。

    抛 `ResourceNotFound` 而不是 `AccessDenied`：不向调用方确认"这个 id 存在"，
    同时避免前端把它当成登录态失效而弹出登录框。
    """
    if session.user_id != user_id:
        raise ResourceNotFound(f"任务会话不存在：{session.id}")


__all__ = ["DefaultOrchestrator"]
