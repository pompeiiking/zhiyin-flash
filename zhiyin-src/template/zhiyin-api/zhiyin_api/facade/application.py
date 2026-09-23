"""Application Facade 实现。

落位：`api/facade/application.py` —— 接口/前端联调负责人。
依赖：业务层的服务 Port（只调不实现）+ `api/dto/mappers.py`。

职责边界（三条不越界）：
- 不写业务规则（规则在 `business/policies/`，调用在 `business/services/`）；
- 不直接访问 Repository / Gateway（只经业务服务）；
- 只做"编排调用 + 交给 Mapper"，字段映射全部在 `api/dto/mappers.py`。

两个硬前置（构造时必须注入，否则 `/app/bootstrap` 无数据可返回）：
- `IdentityService`：解析当前用户（api 拿不到 `AuthGateway`）；
- `RegistryService`：菜单 / 路由 / 任务入口 / 文案 / 开关（api 拿不到 `RegistryRepository`）。

IO 口径：底层服务全部 async，因此本 Facade 的全部方法都是 `async`
（Controller 侧 `await` 即可）。

装配：`zhiyin_boot.wire_application()` 在启动时调用
`configure_facade(DefaultApplicationFacade(...))`；未装配时 `get_facade()` 抛
`FacadeNotConfiguredError`，由 `create_app` 统一映射为 DEPENDENCY_UNAVAILABLE。
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import Request

from zhiyin_api.dto.asset import (
    ActionPlanView,
    ActionTaskDoneRequest,
    AssetVersionView,
    CalendarNodeView,
    DirectionPlanListView,
    TrackEventView,
    ExportRequest,
    ExportResultView,
    ReportFullTextView,
)
from zhiyin_api.dto.bootstrap import BootstrapView, TheoryCardView
from zhiyin_api.dto.bootstrap import PortalView
from zhiyin_api.dto.common import CoachNotificationView
from zhiyin_api.dto.conversation import (
    ConversationMaterialView,
    ConversationMessageView,
    ConversationTurnView,
    MessageRequest,
    SessionListView,
    TaskEnterRequest,
    TaskSessionView,
)
from zhiyin_api.dto.track import TrackEventAck, TrackEventRequest
from zhiyin_api.dto.note import NoteAck, NoteCreateRequest, NoteDoneRequest, NoteView
from zhiyin_api.dto.workspace import (
    AcademicImportAck,
    AcademicImportRequest,
    AcademicImportUpload,
    AcademicRevokeAck,
    IntelListView,
    WorkspacePageView,
)
from zhiyin_api.dto import mappers
from zhiyin_api.facade.facade import ApplicationFacade
from collections.abc import AsyncIterator

from zhiyin_business.ports.blackboard import AcademicService, AssetService
from zhiyin_business.ports.blackboard import BehaviorService
from zhiyin_business.ports.blackboard import ConversationMemoryService
from zhiyin_business.ports.cache import ReadCacheService, cache_key
from zhiyin_business.contracts.common import BehaviorEventDraft
from zhiyin_kernel.enums import BehaviorEventType
from zhiyin_business.ports.blackboard import UserNoteService
from zhiyin_business.ports.function import FunctionService
from zhiyin_business.ports.ai_tasks import AiTaskService
from zhiyin_business.ports.identity import IdentityService
from zhiyin_business.ports.orchestrator import Orchestrator, TurnRequest
from zhiyin_business.ports.registry import RegistryService
from zhiyin_business.ports.workspace import WorkspaceService
from zhiyin_kernel.enums import AssetType
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound
from zhiyin_kernel.registry import AgentDescriptor

#: 15 维分组的展示名在动态资源里的 code（与 `copies.json` 对齐）。
_REPORT_GROUP_COPY: dict[str, str] = {
    "SELF-PORTRAIT": "report.group.self_portrait",
    "JOB-MARKET": "report.group.job_market",
    "DECISION-RISK": "report.group.decision_risk",
}


class DefaultApplicationFacade(ApplicationFacade):
    """BFF 门面默认实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        identity: IdentityService,
        registry: RegistryService,
        orchestrator: Orchestrator,
        workspace: WorkspaceService,
        assets: AssetService,
        function: FunctionService,
        ai_tasks: AiTaskService,
        notes: Optional[UserNoteService] = None,
        academic: Optional[AcademicService] = None,
        behaviors: Optional[BehaviorService] = None,
        memories: Optional[ConversationMemoryService] = None,
        read_cache: Optional[ReadCacheService] = None,
    ) -> None:
        """构造依赖由 boot 注入。

        身份解析走业务 Port：api 被禁止 import `zhiyin_data_sdk`，拿不到
        `AuthGateway`；由 `DefaultIdentityService` 把它包成业务抽象。

        动态资源同理：菜单 / 路由 / 任务入口 / 文案 / 开关经
        `DefaultRegistryService` 取。其余能力（对话 / 工作台 / 资产）
        分别走 `Orchestrator` 与 `WorkspaceService` / `AssetService` /
        `FunctionService`。
        """
        self._identity = identity
        self._registry = registry
        self._orchestrator = orchestrator
        self._workspace = workspace
        self._assets = assets
        self._function = function
        self._ai_tasks = ai_tasks
        # 他自己写下的东西：它不是"待办清单"这个界面的私事，
        # 采集策略要读它，所以走业务 Port 进来（api 拿不到 data_sdk）。
        self._notes = notes
        # 教务系统取回来的课表与成绩单：绑定任务存、界面读、撤销时删
        self._academic = academic
        # 用户对资产的动作（③ 选方案 / ④ 勾任务）是**业务行为**，要进行为日志：
        # 它是"停滞判定"与"成就解锁"的输入之一。允许缺省（纯 api 单测的装配），
        # 缺省时只做状态变更、不记行为。
        self._behaviors = behaviors
        # 逐轮原文的读侧。缺省时 list_session_turns 返回空列表（纯 api 单测的装配）。
        self._memories = memories
        # 读缓存：可缺省 —— 缺省时 facade 直接读库（缓存不该是必需依赖）。
        self._cache = read_cache

    # ---------- 身份 ----------

    async def resolve_user_id(self, request: Request) -> str:
        """从 Authorization: Bearer <token> 取凭证 → IdentityService → user_id。

        第一期鉴权为"默认通过"（本地演示用户）；无 token 时传空，
        由 AuthGateway 落到游客/演示账号。
        """
        authorization = request.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip() or None
        user = await self._identity.current_user(token=token)
        return user.id

    # ---------- 启动 ----------

    async def get_portal(self) -> PortalView:
        """门户内容（公开）。取数与 bootstrap 同源，只是**不解析身份**。"""
        (
            copy_bundle,
            task_entries,
            trust_blocks,
            banners,
            faqs,
            feature_flags,
        ) = await asyncio.gather(
            self._registry.get_copy_bundle(),
            self._registry.list_task_entries(),
            self._registry.list_trust_blocks(),
            self._registry.list_banners(),
            self._registry.list_faqs(),
            self._registry.feature_flags(),
        )
        agents: dict[str, AgentDescriptor] = {}
        for entry in task_entries:
            if entry.lead_agent and entry.lead_agent not in agents:
                agent = await self._registry.get_agent(entry.lead_agent)
                if agent is not None:
                    agents[entry.lead_agent] = agent
        return mappers.portal_view(
            copy_bundle=copy_bundle,
            task_entries=task_entries,
            agents=agents,
            trust_blocks=trust_blocks,
            banners=banners,
            faqs=faqs,
            feature_flags=feature_flags,
        )

    async def bootstrap(self, user_id: str) -> BootstrapView:
        """Registry 取数 → mappers.bootstrap_view。"""
        (
            copy_bundle,
            menus,
            routes,
            task_entries,
            trust_blocks,
            banners,
            faqs,
            feature_flags,
        ) = await asyncio.gather(
            self._registry.get_copy_bundle(),
            self._registry.list_menus(),
            self._registry.list_routes(),
            self._registry.list_task_entries(),
            self._registry.list_trust_blocks(),
            self._registry.list_banners(),
            self._registry.list_faqs(),
            self._registry.feature_flags(),
        )
        agents: dict[str, AgentDescriptor] = {}
        for entry in task_entries:
            if entry.lead_agent and entry.lead_agent not in agents:
                agent = await self._registry.get_agent(entry.lead_agent)
                if agent is not None:
                    agents[entry.lead_agent] = agent
        return mappers.bootstrap_view(
            copy_bundle=copy_bundle,
            menus=menus,
            routes=routes,
            task_entries=task_entries,
            agents=agents,
            trust_blocks=trust_blocks,
            banners=banners,
            faqs=faqs,
            feature_flags=feature_flags,
            # 身份已经在 resolve_user_id 里认证过一次了；这里只按 id 取记录，
            # 不能再传 token=None 重新认证（真实 JWT 下那会直接把首页打成 401）。
            identity=await self._identity.account(user_id),
        )

    async def get_theory_card(self, theory_id: str) -> Optional[TheoryCardView]:
        """理论卡正文：`RegistryService` 取卡 → Mapper 翻形状。

        按**单卡**取而不是拉全表：理论标签一次只点开一张，
        没必要为了一个标签把 16 张卡的正文都搬过来。
        """
        card = await self._registry.get_theory_card(theory_id)
        if card is None:
            return None
        if self._cache is None:
            return mappers.theory_card_view(card)

        # loader 必须是**可等待**的（契约如此）。写成同步 lambda 的话，
        # `await loader()` 会抛 TypeError —— 而且只在装上了缓存的那条路径上抛，
        # 没装缓存时一切正常，属于"上缓存才炸"的典型。
        async def load() -> TheoryCardView:
            return mappers.theory_card_view(card)

        # 理论卡是动态资源里的静态内容：TTL 长，运维重载时整片失效。
        return await self._cache.get_or_load(
            "theory",
            cache_key(theory_id),
            load,
            model=TheoryCardView,
        )

    # ---------- 对话 ----------

    async def list_sessions(self, user_id: str) -> SessionListView:
        sessions = await self._workspace.list_sessions(user_id)
        views = []
        for session in sessions:
            agent = await self._registry.get_agent(session.lead_agent)
            views.append(
                mappers.task_session_view(
                    session,
                    task_name=session.task_name,
                    lead_agent_name=agent.name if agent else "",
                )
            )
        return mappers.session_list_view(views)

    async def list_session_turns(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationMessageView]:
        """一条会话的逐轮原文（用户与主理各算一轮），按时间正序。

        主理展示名从注册表取：库里存的是 agent_id，而界面要显示名字 ——
        名字会改（改动态资源即可），历史里存一份名字就等于冻结了当时的叫法。
        """
        if self._memories is None:
            return []
        turns = await self._memories.list_turns(user_id, task_id, limit=limit)
        names: dict[str, str] = {}
        messages: list[ConversationMessageView] = []
        for turn in turns:
            agent_name: str | None = None
            if turn.agent_id:
                if turn.agent_id not in names:
                    agent = await self._registry.get_agent(turn.agent_id)
                    names[turn.agent_id] = agent.name if agent else turn.agent_id
                agent_name = names[turn.agent_id]
            messages.append(mappers.conversation_message_view(turn, agent_name=agent_name))
        return messages

    async def enter_task(self, user_id: str, body: TaskEnterRequest) -> TaskSessionView:
        session = await self._orchestrator.enter_task(user_id, body.task_code)
        agent = await self._registry.get_agent(session.lead_agent)
        return mappers.task_session_view(
            session,
            task_name=session.task_name,
            lead_agent_name=agent.name if agent else "",
        )

    async def send_message(
        self, user_id: str, body: MessageRequest
    ) -> ConversationTurnView:
        # 材料正文在这一层取出来拼给编排器：**只有模型输入会用到它**，
        # 落库与显示的仍是 body.message（那一句"我传了一份材料：简历.txt"）。
        # 取不到（id 过期 / 不是他的）时按用户能懂的方式说，不把这一轮吞掉。
        material_name, material_text = await self._load_materials(user_id, body.material_ids)
        turn = await self._orchestrator.handle_message(
            TurnRequest(
                user_id=user_id,
                task_id=body.task_id,
                message=body.message,
                client_msg_id=body.client_msg_id,
                # 选项身份要跟着这一轮走到底：编排器据此告诉模型"用户选的是哪一个"，
                # 而不是让模型从一句 label 里猜（见 MessageRequest 的说明）。
                option_id=body.option_id,
                option_value=body.option_value,
                attachment_name=material_name,
                attachment_text=material_text,
            )
        )
        # 这一轮要是产出了新版资产（② 报告 / ③ 方案 / ④ 计划），
        # 那些**以资产为依据**的模型产出就得重算：报告小结写的是上一版报告的口径、
        # 日历里那天的安排是按上一版计划排的。不清的话，用户刚重排完计划，
        # 点开日历看到的还是旧排法 —— 而且没有任何地方提示它是旧的。
        #
        # 依据是这一轮真实生成的版本列表（`asset_versions`），不是"每轮都清"：
        # 大多数轮次只是聊天，清一次产出的代价是下一次打开真的重算一遍。
        if turn.asset_versions:
            await self._invalidate_user(user_id, "asset_version_changed")
        return mappers.conversation_turn_view(turn)

    async def upload_material(
        self, user_id: str, *, name: str, data: bytes
    ) -> ConversationMaterialView:
        """收下一份材料。读不出正文时抛 `DocumentReadError` 的原话（api 翻成 422）。

        这一层不做解码、也不做存储：那两件事都在业务服务里，
        它们共享同一条"这份材料算不算收下了"的判断。
        """
        memories = self._require_memories()
        # 读不出正文时的原话（"这是 Excel，先另存为 CSV"）由业务服务翻成
        # `InvalidRequest` 往上抛 —— 那一层才知道"读不了"该怎么对用户说。
        material = await memories.put_material(user_id, name=name, data=data)
        return mappers.material_view(material)

    async def _load_materials(self, user_id: str, material_ids: list[str]) -> tuple[str, str]:
        """把这一轮的材料读回来 →（材料名, 正文）。

        多份材料时拼成一份正文（中间留一条分隔），并把名字用「、」连起来 ——
        模型要的是"这段正文是哪几份东西"，不是一份结构化清单。
        """
        if not material_ids:
            return "", ""
        memories = self._require_memories()
        names: list[str] = []
        blocks: list[str] = []
        for material_id in material_ids:
            try:
                body = await memories.material_body(user_id, material_id)
            except LookupError as exc:
                raise InvalidRequest(str(exc)) from exc
            names.append(body.name or material_id)
            blocks.append(body.text)
        return "、".join(names), "\n\n".join(blocks)

    # ---------- 工作台 ----------

    async def get_workspace(self, user_id: str) -> WorkspacePageView:
        """工作台聚合视图（带读缓存）。

        这是全站最重的一次读：画像 + 采集 + 四个资产面板 + 会话记忆 + 课表 + 编排。
        缓存域 `workspace`（TTL 短、上面那几个事件都会让它失效）——
        口径见 `data/registry/policy_params.json` 的 cache 一条。
        """
        if self._cache is None:
            view = await self._workspace.build_view(user_id)
            return mappers.workspace_page_view(view)
        return await self._cache.get_or_load(
            "workspace",
            cache_key(user_id),
            lambda: self._build_workspace_view(user_id),
            model=WorkspacePageView,
        )

    async def _build_workspace_view(self, user_id: str) -> WorkspacePageView:
        return mappers.workspace_page_view(await self._workspace.build_view(user_id))

    # ---------- 资产 ----------

    async def list_asset_versions(
        self, user_id: str, asset_type: AssetType
    ) -> list[AssetVersionView]:
        versions = await self._assets.list_versions(user_id, asset_type)
        views: list[AssetVersionView] = []
        for index, version in enumerate(versions):
            previous = versions[index - 1] if index > 0 else None
            views.append(mappers.asset_version_view(version, previous=previous))
        return views

    async def get_report_full_text(
        self, user_id: str, version: Optional[int] = None
    ) -> ReportFullTextView:
        """完整报告正文（带读缓存）。

        键里带版本号：**同一版本的内容不会变**，所以缓存是安全的；
        资产一升版（`asset_version_changed`）整片失效，旧版本那份也就跟着走了。
        不传版本时用 `latest` 作为键片段 —— 它是"当前版本"这个语义，不是具体数字。
        """
        if self._cache is None:
            return await self._load_report(user_id, version)
        return await self._cache.get_or_load(
            "report",
            cache_key(user_id, version if version is not None else "latest"),
            lambda: self._load_report(user_id, version),
            model=ReportFullTextView,
        )

    async def _load_report(
        self, user_id: str, version: Optional[int]
    ) -> ReportFullTextView:
        data = await self._function.get_report_full_text(user_id, version)
        # 尚无报告资产时 Mapper 返回空正文，前端据此渲染"报告未生成"空态。
        return mappers.report_full_text_view(
            data.get("report"), group_labels=await self._report_group_labels()
        )

    # ---------- ③ 决策 / ④ 行动 ----------

    async def get_direction_plans(self, user_id: str) -> DirectionPlanListView:
        """三套方向方案。还没走完 ③ 时返回空列表 —— 界面据此说"还没有方案"。"""
        plans = await self._assets.list_direction_plans(user_id)
        return mappers.direction_plan_list_view(plans)

    async def select_direction_plan(
        self, user_id: str, option_id: str
    ) -> DirectionPlanListView:
        """选中一套方案：状态变更 + 行为日志，返回更新后的全量方案。

        返回全量而不是被选中的那一套：界面上三套卡要一起重绘（一套亮、两套灭），
        只回一套的话前端还得自己推断另外两套的状态。

        "换一套"记成 `decision_reselect` 而不是又一次 `decision_select`：
        两者对复盘的意义不同 —— 前一个是"他改主意了"，后一个是"他第一次定下来"。
        这个事件类型一直躺在枚举与停滞判定里，此前没有任何生产者。
        """
        previous = next(
            (plan for plan in await self._assets.list_direction_plans(user_id) if plan.selected),
            None,
        )
        chosen = await self._assets.select_direction_plan(user_id, option_id)
        await self._log_behavior(
            user_id,
            (
                BehaviorEventType.DECISION_RESELECT
                if previous is not None and previous.id != chosen.id
                else BehaviorEventType.DECISION_SELECT
            ),
            {"plan_id": chosen.id, "role": chosen.role.value, "name": chosen.name},
        )
        # 选方案不产生新版本，但工作台那份 `plan_panel` 的文案跟着变 —— 缓存要作废
        await self._invalidate_user(user_id, "asset_state_changed")
        plans = await self._assets.list_direction_plans(user_id)
        return mappers.direction_plan_list_view(plans)

    async def get_action_plan(self, user_id: str) -> ActionPlanView:
        """行动计划正文。没有计划时 `has_plan=False`（与"有计划但任务为空"不同）。"""
        return mappers.action_plan_view(await self._assets.get_action_plan(user_id))

    async def list_calendar_nodes(self, user_id: str) -> list[CalendarNodeView]:
        """关键节点日历：④ 行动环节写进去的那些节点，这里读出来。

        写入侧在 FunctionService（规划师写）、读取侧同样走它 ——
        两边必须是同一份数据，否则会出现"计划里说有节点、日历里一条都没有"。
        """
        nodes = await self._function.list_calendar_nodes(user_id)
        return [mappers.calendar_node_view(node) for node in nodes]

    async def list_track_events(
        self, user_id: str, *, limit: int = 50
    ) -> list[TrackEventView]:
        """跟踪时间线：⑤ 复盘环节的载体。

        它是"这段时间发生过什么"的事实清单（里程碑、提醒、警告、教练消息），
        与对话原文分开：对话是过程，这里是结果。此前只有写、没有读。
        """
        events = await self._function.list_track_events(user_id)
        return [mappers.track_event_view(event) for event in events[:limit]]

    async def set_action_task_done(
        self, user_id: str, body: ActionTaskDoneRequest
    ) -> ActionPlanView:
        """勾掉 / 取消勾选一个任务：状态变更 + 行为日志，返回更新后的计划。"""
        plan = await self._assets.mark_action_task_done(
            user_id, body.task_id, done=body.done
        )
        # 只有"真的勾掉"才记行为：`done=false` 是**纠正误点**，不是一条行为信号。
        # 之前这里把取消勾选记成了 TASK_STALL（任务停滞）—— 语义完全相反，
        # 而停滞判定会读行为日志，等于让"点错了"去喂养"他卡住了"的判断。
        if body.done:
            await self._log_behavior(
                user_id,
                BehaviorEventType.TASK_DONE,
                {"task_id": body.task_id},
            )
        # 勾掉一件改的是**计划状态**：读缓存那份要重读，模型算过的那几段也要重算 ——
        # 「今天怎么过」原来是按"这件事还没做完"排的，勾完再看还是那一段就说不通了。
        await self._invalidate_user(user_id, "asset_state_changed")
        return mappers.action_plan_view(plan)

    async def _log_behavior(
        self, user_id: str, event_type: BehaviorEventType, payload: dict[str, Any]
    ) -> None:
        """记一条业务行为。

        没有接行为服务时**静默跳过**（纯 api 单测的装配）：行为日志是旁路，
        卡住它只会让"用户点了没反应"。要确认有没有记上，看行为日志表那一条。
        """
        if self._behaviors is None:
            return
        await self._behaviors.log(
            user_id, BehaviorEventDraft(event_type=event_type, payload=payload)
        )

    async def _invalidate(self, event: str) -> None:
        """按事件失效读缓存（映射在动态资源里，写侧只报"发生了什么"）。

        没有接缓存时是空操作 —— 缓存不是必需依赖，它的缺失只该表现为"多读一次库"。
        """
        if self._cache is None:
            return
        await self._cache.invalidate_for_event(event)

    async def _invalidate_user(self, user_id: str, event: str) -> None:
        """按事件失效这个用户的**两份缓存**：读侧那份，和模型算出来那份。

        为什么要一起做：它们是两种东西 ——
          · 读缓存（Redis，按分片）失效后，下一次读会**照原样重建**，用户看不到差别；
          · 模型产出（`ai_task_result`，按 key 存库）失效后，下一次打开会**真的重算**，
            用户看到的内容才会跟着新事实变。
        只做前者，症状是"库里什么都对、界面上那段话还是旧的"：
        日历里「这一天怎么用」还按没勾掉的任务在排，报告小结还是上一版报告的口气。

        与 `_invalidate` 分开的原因只有一个：模型产出是**按用户**存的，
        必须带上 user_id —— 全站按事件清一遍会把别人的产出也清掉。
        """
        await self._invalidate(event)
        await self._ai_tasks.invalidate_for_event(user_id, event)

    async def _report_group_labels(self) -> dict[str, str]:
        """15 维分组的展示名：分组标识 → 文案。

        文案是**产品口径**，只在 `data/registry/copies.json` 里有一份；
        Facade 负责把它取出来交给 Mapper（Mapper 只做形状翻译、不做取数）。
        取不到就返回空字典，由 Mapper 回落到分组标识。
        """
        bundle = await self._registry.get_copy_bundle()
        return {
            key: bundle[code] for key, code in _REPORT_GROUP_COPY.items() if code in bundle
        }

    async def export_asset(self, user_id: str, body: ExportRequest) -> ExportResultView:
        result = await self._function.export_asset(
            user_id, body.asset_type.value, body.format
        )
        return mappers.export_result_view(result)

    async def get_external_intel(
        self, user_id: Optional[str], *, topic: str = "", refresh: bool = False
    ) -> IntelListView:
        """外部情报：去公开渠道取回事实条目。**不要求登录**。

        登录只影响一件事：能不能按**你**的画像把结果收窄。
        没登录就按 `topic` 取，或者取平台上的通用公开数据 ——
        情报是爬公开数据的，信息源非常广，不可能每个网站都登一次。

        取到的每条都带来源链接，没有来源的条目在服务层就被丢掉了。

        主题没给时**由取数服务按画像推**（`intel_topic`）—— 与对话那条入口
        用同一条规则、同一个缓存桶，所以面板里看到的这一批，就是主理刚引用的那一批。
        """
        items = await self._function.fetch_external_intel(
            user_id, topic=topic, limit=12, refresh=refresh
        )
        return mappers.intel_list_view(items)

    # ---------- AI 任务（SSE） ----------

    async def run_ai_task(self, user_id: str, key: str, arg: str = "") -> AsyncIterator[dict]:
        """执行一个 AI 任务，逐帧 yield 进度 / 终帧（传输约定见设计文档 6.2）。"""
        async for frame in self._ai_tasks.stream(user_id, key, arg):
            yield frame

    # ---------- 主动介入通知 ----------

    async def list_pending_notifications(self, user_id: str) -> list[CoachNotificationView]:
        """未读教练通知（前端浮窗轮询）。形状翻译交给 mapper，Facade 不拼字段。"""
        items = await self._function.list_pending_notifications(user_id)
        return [mappers.coach_notification_view(item) for item in items]

    async def mark_notification_read(self, user_id: str, message_id: str) -> bool:
        """浮窗关掉时回执：这条已经看过了，别再飘一次。"""
        return await self._function.mark_notification_read(user_id, message_id) > 0

    # ---------- 鉴权 ----------

    async def login_account(self, account: str, password: str) -> dict:
        return await self._identity.login(account, password)

    async def register_account(self, account: str, password: str) -> str:
        return await self._identity.register(account, password)

    async def revoke_token(self, token: str) -> None:
        revoke = getattr(self._identity._auth, "revoke_token", None)
        if revoke is not None:
            await revoke(token)

    # ---------- 埋点 ----------

    async def track_event(
        self, user_id: str, body: TrackEventRequest
    ) -> TrackEventAck:
        """先经 Registry 校验事件属于 frontend 通道，再交功能块服务落时间线。"""
        events = {spec.code: spec for spec in await self._registry.list_track_events()}
        spec = events.get(body.event)
        if spec is None or spec.channel != "frontend":
            return TrackEventAck(accepted=False, event=body.event)
        await self._function.record_track_event(user_id, body.event, body.payload)
        # 只失效读缓存：埋点记的是"界面上发生了什么"，它不在任何一段模型产出的依据里，
        # 顺手清产出等于让用户每翻一屏就重算一遍（花钱，也变慢）。
        await self._invalidate("note_changed")
        return TrackEventAck(accepted=True, event=body.event)

    # ---------- 他自己写下的东西 ----------

    async def revoke_academic(self, user_id: str) -> AcademicRevokeAck:
        """清空导入：课表成绩与画像摘要一起删（判断与删除都在业务服务里）。"""
        if self._academic is None:
            return AcademicRevokeAck(revoked=False)
        await self._academic.revoke(user_id)
        await self._invalidate_user(user_id, "academic_changed")
        return AcademicRevokeAck(revoked=True)

    async def import_academic(
        self, user_id: str, body: "AcademicImportRequest"
    ) -> "AcademicImportAck":
        """导入课表与成绩单（用户自己贴的原文）。

        解析不出来时抛 `AcademicImportError`，由 api 层翻成"该改哪里"的提示 ——
        它不是一个内部错误，而是一件用户能自己修的事。
        """
        if self._academic is None:
            raise RuntimeError("导入服务未装配（Container.academic_service）")
        result = await self._academic.import_(
            user_id,
            courses_raw=body.courses,
            grades_raw=body.grades,
            school=body.school,
            term=body.term,
        )
        # 课表进了库，工作台那份缓存（含 academic_panel 与采集清单）必须立刻作废
        # —— 连同"按课表算出来的那一天怎么过"（模型算的，也按课表排的）
        await self._invalidate_user(user_id, "academic_changed")
        return AcademicImportAck(
            school=result.school,
            source=result.source,
            term=result.term,
            courses=result.courses,
            courses_scheduled=result.courses_scheduled,
            grades=result.grades,
            imported_at=result.imported_at,
            notes=list(result.notes),
            wrote_profile=list(result.wrote_profile),
        )

    async def import_academic_files(
        self, user_id: str, body: "AcademicImportUpload"
    ) -> "AcademicImportAck":
        """导入课表与成绩单（用户自己传的文件）。

        与文本入口走同一条业务链路，只是多一步"字节 → 文本"（在业务服务里，
        由网关按编码识别）。回执、报错、缓存作废三件事都和文本入口完全一样 ——
        用户用哪种方式把数据带进来，结果不该有差别。
        """
        if self._academic is None:
            raise RuntimeError("导入服务未装配（Container.academic_service）")
        result = await self._academic.import_files(
            user_id,
            courses_file=body.courses_file,
            grades_file=body.grades_file,
            courses_name=body.courses_name,
            grades_name=body.grades_name,
            courses_raw=body.courses_text,
            grades_raw=body.grades_text,
            school=body.school,
            term=body.term,
        )
        await self._invalidate_user(user_id, "academic_changed")
        return AcademicImportAck(
            school=result.school,
            source=result.source,
            term=result.term,
            courses=result.courses,
            courses_scheduled=result.courses_scheduled,
            grades=result.grades,
            imported_at=result.imported_at,
            notes=list(result.notes),
            wrote_profile=list(result.wrote_profile),
        )

    async def list_notes(self, user_id: str) -> list[NoteView]:
        """他写下的全部内容。"""
        return [mappers.note_view(note) for note in await self._require_notes().list_by_user(user_id)]

    async def add_note(self, user_id: str, body: NoteCreateRequest) -> NoteView:
        """写一条。

        空内容由服务层拒绝（`ValueError`）—— 接口层不替它兜底成一条空待办：
        空待办会变成采集策略里的一条噪音，而它看起来就像用户真的写过。
        """
        note = await self._require_notes().add(user_id, body.text, kind=body.kind)
        await self._invalidate_user(user_id, "note_changed")
        return mappers.note_view(note)

    async def set_note_done(
        self, user_id: str, note_id: str, body: NoteDoneRequest
    ) -> NoteView:
        """勾掉 / 取消勾掉。"""
        note = await self._require_notes().set_done(user_id, note_id, body.done)
        if note is None:
            raise ResourceNotFound(f"没有这条内容：{note_id}")
        await self._invalidate_user(user_id, "note_changed")
        return mappers.note_view(note)

    async def remove_note(self, user_id: str, note_id: str) -> NoteAck:
        """删掉一条。"""
        await self._require_notes().remove(user_id, note_id)
        await self._invalidate_user(user_id, "note_changed")
        return NoteAck(removed=note_id)

    def _require_notes(self) -> UserNoteService:
        """没装配就明确报错，不返回一份"看起来能写"的空实现。"""
        if self._notes is None:
            raise RuntimeError("用户自建内容服务未装配（Container.notes）")
        return self._notes

    def _require_memories(self) -> ConversationMemoryService:
        """同上：记忆服务没装配时明确报错，不让"材料收下了"变成一句空话。"""
        if self._memories is None:
            raise RuntimeError("会话记忆服务未装配（Container.memories）")
        return self._memories

    async def reload_dynamic_config(self) -> dict[str, Any]:
        """重新装载动态配置，并回报这一次装到了什么。"""
        from zhiyin_business.services.dynamic_config import load_snapshot

        snapshot = await load_snapshot(self._registry)
        return {
            "loaded_at": snapshot.loaded_at,
            "source": snapshot.source,
            "stages": len(snapshot.stages),
            "layout_blocks": len(snapshot.layout.blocks) if snapshot.layout else 0,
            "collection_rules": len(snapshot.collection_rules),
            "user_signals": len(snapshot.user_signals),
        }


__all__ = ["DefaultApplicationFacade"]
