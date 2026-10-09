"""Assembly adapters: module SDK reuses the existing application business flows."""
from __future__ import annotations

import json
import os

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
                service = container.extra.get("module_platform")
                if service is None:
                    raise InvalidRequest("模块平台尚未装配")
                value = await service.tool(mid, run_context.user_id, deps.get("module_agent_id", ""), input)
                manifest = service.definition(mid).manifest
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
