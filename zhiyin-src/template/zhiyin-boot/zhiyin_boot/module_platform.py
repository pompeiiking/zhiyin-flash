"""Assembly adapters: module SDK reuses the existing application business flows."""
from __future__ import annotations

import json
import logging
import os
from typing import Literal

from agno.run import RunContext

from pydantic import TypeAdapter
from zhiyin_api.dto.asset import ActionTaskDoneRequest, ActionPlanView, DirectionPlanListView, CalendarNodeView
from zhiyin_api.dto.achievement import AchievementListView, AchievementView
from zhiyin_business.policies.renderers import RendererSpec, register_renderer, renderer_for
from zhiyin_business.services.modules import ModulePlatform
from zhiyin_business.services.module_flows import ModuleFlowService
from zhiyin_business.services.dialogue_exploration import QuotedStatement
from zhiyin_infrastructure.ai.tools import ToolModule, ToolSpec
from zhiyin_infrastructure.postgres.database import get_database
from zhiyin_infrastructure.postgres.modules import PostgresModuleRepository
from zhiyin_infrastructure.postgres.module_flows import PostgresModuleFlowRepository
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_kernel.modules import ModuleCapability
from zhiyin_modules import discover, inspect_modules


logger = logging.getLogger(__name__)


class ModuleAchievementView(AchievementView):
    label: str


class ModuleAchievementListView(AchievementListView):
    items: list[ModuleAchievementView]


def definitions(container):
    if "modules" not in container.extra:
        container.extra["modules"] = discover()
    return container.extra["modules"]


def product_tools(container):
    modules = []
    async def read_material(run_context: RunContext, material_id: str, offset: int = 0, limit: int = 4000) -> str:
        """按片段读取本会话已上传的材料。material_id 来自本轮材料清单，offset 为字符偏移。"""
        from zhiyin_business.services.analysis_access import current_scope
        from zhiyin_kernel.privacy import SENSITIVE
        user_id = run_context.user_id or ""
        scope = current_scope(user_id)
        if not user_id or (scope is not None and "material" not in scope.sources):
            raise InvalidRequest("本轮未允许使用材料")
        if container.student_service is not None:
            await container.student_service.require_material_analysis(user_id)
        if material_id not in (run_context.dependencies or {}).get("material_ids", []):
            raise InvalidRequest("这份材料不在当前会话的已上传清单中")
        body = await container.memory_service.material_body(user_id, material_id)
        if SENSITIVE.search(body.text):
            return "这份材料包含敏感信息，未交给模型。请脱敏后重新上传。"
        start = max(0, offset)
        return json.dumps({"id": material_id, "name": body.name, "offset": start,
            "total_chars": len(body.text), "text": body.text[start:start + max(1, min(limit, 8000))]}, ensure_ascii=False)
    async def read_workspace(run_context: RunContext, area: Literal["profile", "academic", "report", "plan", "directions", "calendar", "notes", "reviews", "achievements", "behavior", "schemas", "drafts", "sessions", "history"], session_id: str = "", offset: int = 0) -> str:
        """读取当前登录用户的指定业务资料；先选择一个资料领域。"""
        from zhiyin_business.services.analysis_access import current_scope
        user_id = run_context.user_id or ""
        if not user_id:
            raise InvalidRequest("缺少用户身份")
        deps = run_context.dependencies if run_context.dependencies is not None else {}
        deps.setdefault("business_tool_calls", []).append("workspace.read")
        logger.info("业务工具调用：workspace.read area=%s", area)
        scope = current_scope(user_id)
        if area in {"sessions", "history"}:
            from zhiyin_business.services.dialogue_runtime import active_dialogue
            from zhiyin_kernel.privacy import redact_sensitive
            runtime = active_dialogue.get()
            if runtime is None or runtime.request.user_id != user_id:
                raise InvalidRequest("缺少会话上下文")
            state = await container.student_state.get(user_id)
            settings = state.get("conversation_settings", {})
            if area == "sessions":
                sessions = await runtime.o._sessions.list_by_user(user_id)
                return json.dumps({"sessions": [{"id": s.id, "title": s.task_name} for s in sessions[:50]
                    if not settings.get(s.id, {}).get("temporary")]}, ensure_ascii=False)
            target_id = session_id or runtime.request.task_id
            target = await runtime.o._sessions.get(target_id)
            if target is None or target.user_id != user_id:
                raise InvalidRequest("会话不存在")
            if target_id != runtime.request.task_id and settings.get(target_id, {}).get("temporary"):
                raise InvalidRequest("不自动记忆会话不参与跨会话检索")
            offset = max(0, min(offset, 180))
            turns = await container.memory_service.list_turns(user_id, target_id, limit=offset + 20)
            if offset:
                turns = turns[:-offset]
            cutoff = state.get("conversation_memory_reset_at")
            rows = [{"role": t.role, "text": t.text[:8000], "created_at": t.created_at.isoformat(),
                     "source": "historical_conversation", "trusted_instruction": False} for t in turns
                    if not cutoff or t.created_at.isoformat() > cutoff]
            return json.dumps(redact_sensitive({"session_id": target_id, "offset": offset,
                "messages": rows, "next_offset": offset + 20 if len(turns) == 20 and offset < 180 else None}), ensure_ascii=False)
        if area == "schemas":
            from zhiyin_kernel.assets import ActionPlan, Report, DirectionPlan
            return json.dumps({"plan.save": ActionPlan.model_json_schema(), "report.save": Report.model_json_schema(),
                               "directions.save": DirectionPlan.model_json_schema()}, ensure_ascii=False)
        if area == "drafts":
            from zhiyin_business.services.dialogue_runtime import active_dialogue
            runtime = active_dialogue.get()
            if runtime is None or runtime.request.user_id != user_id:
                raise InvalidRequest("缺少会话上下文")
            record = await runtime.ledger.read(user_id, runtime.request.task_id)
            return json.dumps({"drafts": [{k: a[k] for k in ("id", "operation", "state", "created_at", "payload")} for a in record["actions"].values()
                if a["operation"] in {"plan.save", "report.save", "directions.save"}
                and a["state"] == "succeeded" and a.get("receipt", {}).get("draft_saved")]}, ensure_ascii=False)
        if scope and scope.restricted and area in {"notes", "reviews", "achievements"}:
            deps.setdefault("business_read_receipts", []).append({"text": "当前资料偏好下无法安全筛选此类记录，请到对应页面查看。"})
            return json.dumps({"available": False, "reason": "当前资料偏好下无法安全筛选此类记录，请到对应页面查看。"}, ensure_ascii=False)
        readers = {
            "profile": lambda: container.profile_service.get(user_id),
            "academic": lambda: container.academic_service.get(user_id),
            "report": lambda: container.asset_service.get_report(user_id),
            "plan": lambda: container.asset_service.get_action_plan(user_id),
            "directions": lambda: container.asset_service.list_direction_plans(user_id),
            "calendar": lambda: container.function_service.list_calendar_nodes(user_id),
            "notes": lambda: container.note_service.list_by_user(user_id),
            "reviews": lambda: container.student_service.reviews(user_id),
            "achievements": lambda: container.facade.list_achievements(user_id),
            "behavior": lambda: container.behavior_service.recent(user_id, limit=30),
        }
        value = await readers[area]()
        if area == "directions":
            value = [item.model_copy(update={"match_score": None, "match_method": "暂无可核验的量化评分"}) for item in value]
        if area == "academic":
            grades = value.grades if value else []
            lines = [f"{g.name}：{g.score or '未填写成绩'}（{g.term or '未标注学期'}）" for g in grades]
            summary = "成绩记录：\n" + "\n".join(lines) if lines else "没有可读取的成绩记录。"
        elif area == "plan":
            tasks = [t for phase in (value.phases if value else []) for t in phase.tasks]
            lines = [f"{t.text}：{'已完成' if t.done else '未完成'}" for t in tasks]
            summary = "行动任务：\n" + "\n".join(lines) if lines else "没有可读取的行动任务。"
        else:
            labels = {"profile": "个人画像", "report": "诊断报告", "directions": "方向方案", "calendar": "日历", "notes": "成长记录", "reviews": "复盘记录", "achievements": "完成记录", "behavior": "行为记录"}
            summary = (f"没有可读取的{labels[area]}。" if value is None or value == []
                       else f"已读取{labels[area]}。本次未能整理成可靠的详细回复，请到对应页面查看。")
        deps.setdefault("business_read_receipts", []).append({"area": area, "text": summary})
        from zhiyin_kernel.privacy import redact_sensitive
        from zhiyin_business.services.conversation_ledger import digest
        from zhiyin_business.services.dialogue_runtime import serial
        review_required = False
        if area in {"plan", "report", "directions"}:
            from zhiyin_kernel.enums import AssetType
            kind = {"plan": AssetType.ACTION_PLAN, "report": AssetType.REPORT, "directions": AssetType.DIRECTION_PLAN}[area]
            latest = await container.asset_service.get_latest_version(user_id, kind)
            review_required = bool(latest and latest.needs_recompute)
        return json.dumps(redact_sensitive({"area": area, "version": digest(serial(value)), "data": serial(value),
            "review_required": review_required, "source": "current_user_business_data"}), ensure_ascii=False,
                          default=lambda x: x.model_dump(mode="json") if hasattr(x, "model_dump") else str(x))

    async def conversation_action(run_context: RunContext, operation: str, payload: dict,
                                  authorization: Literal["automatic", "explicit", "proposal"] = "proposal",
                                  evidence: str = "", expected_version: str = "", action_id: str = "", supersedes_action_id: str = "") -> str:
        """统一业务操作：profile.update/task.set_done/plan.save/report.save/directions.save/plan.activate/direction.select/memory.forget/action.approve/action.reject。先核对授权，返回真实回执或待确认提案。profile.update 的 payload 可含 key、value、assertion_type、attributes（类型专属受控属性，如兴趣 polarity、职业关注 state）、valid_from/valid_to/event_at（带时区的 ISO 时间）；用户说“只保存这一条”时 authorization=explicit 且 save_scope=single，只放行这一条，不恢复其他自动记录。原话引用与核实状态由服务端按本轮消息生成，不要自报。"""
        from zhiyin_business.services.dialogue_runtime import active_dialogue
        runtime = active_dialogue.get()
        if runtime is None or runtime.request.user_id != run_context.user_id:
            raise InvalidRequest("业务操作缺少当前对话上下文")
        result = await runtime.action({"operation": operation, "payload": payload,
            "authorization": authorization, "evidence": evidence,
            "expected_version": expected_version, "action_id": action_id, "supersedes_action_id": supersedes_action_id})
        return json.dumps(result, ensure_ascii=False, default=str)

    async def record_exploration(run_context: RunContext, goal: str,
                                 mode: Literal["explore", "answer", "act", "paused"],
                                 statements: list[QuotedStatement] | None = None, hypotheses: list[str] | None = None,
                                 explored_topics: list[str] | None = None, open_questions: list[str] | None = None,
                                 next_focus: str = "") -> str:
        """Update bounded conversation working context, not the permanent profile. Quotes require user turn_id from exploration_context. Hypotheses remain unverified. Use only when exploration changes; ordinary factual answers need no call."""
        from zhiyin_business.services.dialogue_runtime import active_dialogue
        runtime = active_dialogue.get()
        if runtime is None or runtime.request.user_id != run_context.user_id:
            raise InvalidRequest("探索记录缺少当前对话上下文")
        result = await runtime.record_exploration({"goal": goal, "mode": mode,
            "statements": [statement.model_dump(mode="json") for statement in statements or []], "hypotheses": hypotheses or [],
            "explored_topics": explored_topics or [], "open_questions": open_questions or [], "next_focus": next_focus})
        return json.dumps(result, ensure_ascii=False)

    async def classify_context(run_context: RunContext, question: str) -> str:
        """可选Kev快速业务分类；只辅助、不授权、不强制切换任务。"""
        from zhiyin_business.services.dialogue_runtime import active_dialogue
        from zhiyin_data_sdk.gateways.decision import DecisionRequest, DecisionChoiceQuestion
        import asyncio
        runtime = active_dialogue.get()
        if runtime is None or runtime.request.user_id != run_context.user_id or container.decision is None:
            return '{"available":false,"reason":"辅助判断不可用，可继续交流"}'
        config = await container.registry_service.get_decision_routing_policy()
        if config.get("mode") == "off":
            return '{"available":false,"reason":"辅助判断已关闭，可直接根据上下文交流"}'
        try:
            async with asyncio.timeout(3):
                result = await container.decision.decide(DecisionRequest(
                    state={"message": runtime.request.message, "question": question[:1000],
                           "history": runtime.history[-12:], "pending_actions": runtime.pending_summary},
                    questions={"intent": DecisionChoiceQuestion(instructions=config["instructions"], criteria=config["criteria"])}))
            if config.get("mode") == "shadow":
                logger.info("Kev影子检查完成：latency_ms=%s", result.latency_ms)
                return '{"available":false,"shadow_only":true,"reason":"影子模式仅观察，不影响当前回答"}'
            return json.dumps({"advisory_only": True, "result": result.model_dump(mode="json")}, ensure_ascii=False)
        except Exception:
            logger.warning("Kev辅助判断未完成，主对话继续", exc_info=True)
            return '{"available":false,"reason":"辅助判断未完成，请根据上下文继续"}'

    async def record_memory_policy(run_context: RunContext, action: Literal["deny_key", "deny_content"], key: str = "", content: str = "") -> str:
        """记录用户对记忆范围的要求：某条字段不要记录，或这条内容不要记录。

        Args:
            action: deny_key=这个字段不要自动记录；deny_content=这条内容及其派生提取不要记录
            key: action=deny_key 时必填的画像字段键
            content: action=deny_content 时可选；为空表示本轮用户消息
        """
        from zhiyin_business.services.dialogue_runtime import active_dialogue
        from zhiyin_business.services.conversation_ledger import digest
        from zhiyin_business.services.memory_policy import MemoryPolicyService

        runtime = active_dialogue.get()
        if runtime is None or runtime.request.user_id != run_context.user_id:
            raise InvalidRequest("记忆策略缺少当前对话上下文")
        policy = MemoryPolicyService(container.student_state)
        if action == "deny_key":
            if not key:
                raise InvalidRequest("要拒绝记录的字段不能为空")
            record = await policy.deny_key(
                run_context.user_id, key, source="conversation", note="用户要求这条不要自动记录"
            )
        else:
            # 内容指纹按“这一轮用户消息”算，与自动写入前的 check_auto_write 同一口径；
            # 同一条消息派生的提取都会被拦住，不影响其他内容。
            fingerprint = digest({"user_id": run_context.user_id, "message": content or runtime.request.message})
            record = await policy.deny_content(
                run_context.user_id, fingerprint, source="conversation", note="用户要求这条内容不要自动记录"
            )
        return json.dumps({"saved": True, "record": record}, ensure_ascii=False, default=str)

    modules.append(ToolModule(name="workspace", tools=[
        ToolSpec(name="material.read", description="分段读取当前会话已上传材料", handler=read_material),
        ToolSpec(name="workspace.read", description="读取当前用户的真实业务资料", handler=read_workspace),
        ToolSpec(name="workspace.action", description="统一业务写入和审批，执行真实变更或返回具体提案", handler=conversation_action),
        ToolSpec(name="workspace.exploration", description="更新本会话探索目标、原话与待核实线索；不写长期画像", handler=record_exploration),
        ToolSpec(name="workspace.memory", description="记录用户对记忆范围的要求：某条字段或某条内容不要自动记录", handler=record_memory_policy),
        ToolSpec(name="workspace.classify", description="按需Kev辅助业务判断，不直接控制对话", handler=classify_context),
    ]))
    for module_id, definition in definitions(container).items():
        if not definition.manifest.tool:
            continue
        kind = f"module.{module_id}"
        if definition.manifest.conversation and renderer_for(kind) is None:
            register_renderer(RendererSpec(kind=kind, label=definition.manifest.name,
                                            source="模块授权数据能力", validate=definition.validate))

        def make_handler(mid, render_kind):
            async def handler(run_context: RunContext, input: dict | None = None) -> str:
                """读取已保存的业务数据，并展示对应功能卡片。"""
                if run_context.dependencies is None:
                    run_context.dependencies = {}
                deps = run_context.dependencies
                # Record the attempt before permission checks or execution. A
                # revoked/failed read must never become a stage asset write.
                deps.setdefault("module_attempts", []).append(mid)
                from zhiyin_business.services.analysis_access import current_scope
                scope = current_scope(run_context.user_id)
                service = container.extra.get("module_platform")
                if service is None:
                    raise InvalidRequest("模块平台尚未装配")
                manifest = service.definition(mid).manifest
                if scope is not None and scope.restricted and not set(manifest.reads) <= {
                    "plan.read", "direction.read", "calendar.read", "achievements.read",
                }:
                    # The four built-in readers below use guarded business reads.
                    # Future capabilities need the same boundary before AI access.
                    return json.dumps({"available": False, "reason": "该模块的数据来源尚不能按当前资料偏好筛选；可在对应页面查看。"}, ensure_ascii=False)
                value = await service.tool(mid, run_context.user_id, deps.get("module_agent_id", ""), input)
                deps.setdefault("module_results", []).append({"module_id": mid, "title": manifest.name,
                    "result": value.model_dump()})
                if manifest.conversation:
                    deps.setdefault("renderables", []).append({"kind": render_kind,
                        "title": manifest.name, "payload": value.model_dump(), "source_refs": []})
                return json.dumps(value.model_dump(), ensure_ascii=False)
            # Agno exposes the Python callable name, not ToolSpec's registry key.
            handler.__name__ = f"module_{mid}_read"
            handler.__doc__ = container.extra["modules"][mid].manifest.description
            return handler

        modules.append(ToolModule(name=module_id, tools=[ToolSpec(name=definition.manifest.tool,
            description=definition.manifest.description, handler=make_handler(module_id, kind))]))
    return tuple(modules)


def build_platform(container):
    if not container.settings.use_postgres or container.facade is None:
        return
    facade = container.facade

    async def set_done(user_id, payload):
        try:
            body = ActionTaskDoneRequest.model_validate(payload)
        except ValueError as exc:
            raise InvalidRequest("任务操作参数错误") from exc
        return await facade.set_action_task_done(user_id, body)

    async def achievements(user_id):
        result = (await facade.list_achievements(user_id)).model_dump(mode="json")
        copies = await container.registry_service.get_copy_bundle()
        # Copy bundle is a mapping in the public registry contract.
        for item in result["items"]:
            item["label"] = copies.get(f"badge.{item['key']}.label", item["key"])
        return result

    empty_input = {"type": "object", "additionalProperties": False}
    readers = {"plan.read": facade.get_action_plan, "achievements.read": achievements,
               "direction.read": facade.get_direction_plans,
               "calendar.read": facade.list_calendar_nodes}
    capabilities = [ModuleCapability(id=key, operation="read", description=description,
        input_schema=empty_input, output_schema=TypeAdapter(output).json_schema()) for key, description, output in (
        ("plan.read", "读取当前用户已保存的行动计划及任务状态", ActionPlanView),
        ("achievements.read", "读取当前用户的完成记录", ModuleAchievementListView),
        ("direction.read", "读取当前用户的方向方案及当前选择", DirectionPlanListView),
        ("calendar.read", "读取当前用户的关键节点日历", list[CalendarNodeView]),
    )]
    capabilities.append(ModuleCapability(id="plan.task.set_done", operation="action",
        description="完成或撤销完成当前用户已有任务，并同步原业务记录", input_schema=ActionTaskDoneRequest.model_json_schema(),
        output_schema=ActionPlanView.model_json_schema()))
    service = ModulePlatform(modules=definitions(container),
        repository=PostgresModuleRepository(get_database(container.settings.postgres_dsn)),
        identity=container.identity_service,
        readers=readers,
        actions={"plan.task.set_done": set_done}, revision=os.environ.get("ZHIYIN_BUILD_REVISION", "working-tree"),
        environment=os.environ.get("ZHIYIN_MODULE_ENV", "local"), inspect=inspect_modules,
        agents=container.registry.list_agents, capabilities=capabilities)
    service.flows = ModuleFlowService(service, PostgresModuleFlowRepository(get_database(container.settings.postgres_dsn), revision=service.revision))
    container.extra["module_platform"] = service
    if container.agent_engine is not None:
        container.agent_engine.module_tool_names = service.tool_names


async def initialize_platform(container):
    service = container.extra.get("module_platform")
    if service is None:
        return
    # Product-owned initial grants. A new third-party module always starts disabled.
    for module_id in ("achievements", "action_progress"):
        if module_id in service.modules:
            manifest = service.definition(module_id).manifest
            await service.repository.seed(module_id, {"enabled": True, "reads": manifest.reads,
                "actions": manifest.actions, "agents": []})
