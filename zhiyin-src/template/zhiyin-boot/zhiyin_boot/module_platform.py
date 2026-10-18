"""Assembly adapters: module SDK reuses the existing application business flows."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Literal

from agno.run import RunContext

from pydantic import TypeAdapter
from zhiyin_api.dto.asset import ActionTaskDoneRequest, ActionPlanView, DirectionPlanListView, CalendarNodeView
from zhiyin_api.dto.achievement import AchievementListView, AchievementView
from zhiyin_business.policies.renderers import RendererSpec, register_renderer, renderer_for
from zhiyin_business.services.modules import ModulePlatform
from zhiyin_business.services.module_flows import ModuleFlowService
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
        from zhiyin_business.services.conversation_policy import SENSITIVE
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
    async def read_workspace(run_context: RunContext, area: Literal["profile", "academic", "report", "plan", "directions", "calendar", "notes", "reviews", "achievements"]) -> str:
        """读取当前登录用户的指定业务资料；先选择一个资料领域。"""
        from zhiyin_business.services.analysis_access import current_scope
        user_id = run_context.user_id or ""
        if not user_id:
            raise InvalidRequest("缺少用户身份")
        deps = run_context.dependencies if run_context.dependencies is not None else {}
        deps.setdefault("business_tool_calls", []).append("workspace.read")
        logger.info("业务工具调用：workspace.read area=%s", area)
        scope = current_scope(user_id)
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
            labels = {"profile": "个人画像", "report": "诊断报告", "directions": "方向方案", "calendar": "日历", "notes": "成长记录", "reviews": "复盘记录", "achievements": "完成记录"}
            summary = (f"没有可读取的{labels[area]}。" if value is None or value == []
                       else f"已读取{labels[area]}。本次未能整理成可靠的详细回复，请到对应页面查看。")
        deps.setdefault("business_read_receipts", []).append({"area": area, "text": summary})
        from zhiyin_kernel.privacy import redact_sensitive
        return json.dumps(redact_sensitive({"area": area, "data": value}), ensure_ascii=False,
                          default=lambda x: x.model_dump(mode="json") if hasattr(x, "model_dump") else str(x))

    async def set_task_done(run_context: RunContext, task_id: str, done: bool) -> str:
        """按用户本轮明确要求，将指定的已有行动任务标记完成或取消完成。"""
        from zhiyin_business.services.analysis_access import current_scope
        user_id = run_context.user_id or ""
        deps = run_context.dependencies if run_context.dependencies is not None else {}
        deps.setdefault("business_tool_calls", []).append("workspace.task.set_done")
        logger.info("业务工具调用：workspace.task.set_done")
        receipt = {"executed": False, "reason": "请明确写出任务名称和要标记完成还是取消完成。"}
        deps.setdefault("business_tool_receipts", []).append(receipt)
        message = str(deps.get("user_message") or "")
        if not user_id:
            raise InvalidRequest("缺少用户身份")
        current_scope(user_id)
        plan = await container.asset_service.get_action_plan(user_id)
        tasks = [(task, task.id or f"{phase.name}:{task.text}") for phase in (plan.phases if plan else []) for task in phase.tasks]
        # Never trust the model's identifier: only a unique exact task name in
        # the user's message authorizes a write. Duplicate names are ambiguous.
        named = [(item, identity) for item, identity in tasks if item.text and item.text in message]
        task = None
        if len(named) == 1:
            task, task_id = named[0]
        # The task title is data, not part of the instruction: a title such as
        # "不要忘记核对材料" must not cancel an otherwise explicit request.
        directive = message.replace(task.text, "", 1) if task else message
        negative = bool(re.search(r"不要|不必|无需|暂不|别", directive))
        wants_undo = bool(re.search(r"取消完成|撤销完成|标记为未完成", directive))
        wants_done = bool(re.search(r"标记.{0,8}完成|勾选|完成.{0,4}任务", directive))
        if not task or not task.text or task.text not in message or negative or (not wants_undo if not done else not wants_done or wants_undo):
            return json.dumps(receipt, ensure_ascii=False)
        updated = await container.facade.set_action_task_done(user_id, ActionTaskDoneRequest(task_id=task_id, done=done))
        receipt.update({"executed": True, "task": task.text, "done": done})
        return json.dumps({**receipt, "plan": updated.model_dump(mode="json")}, ensure_ascii=False)

    modules.append(ToolModule(name="workspace", tools=[
        ToolSpec(name="material.read", description="分段读取当前会话已上传材料", handler=read_material),
        ToolSpec(name="workspace.read", description="读取当前用户的真实业务资料", handler=read_workspace),
        ToolSpec(name="workspace.task.set_done", description="用户明确指定任务名称和操作时更新任务完成状态", handler=set_task_done),
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
