"""Version-pinned module DAGs with explicit, single terminal business actions."""
from __future__ import annotations

import copy
import hashlib
import json

from zhiyin_data_sdk.repositories.module_flows import ModuleFlowRepository
from zhiyin_kernel.errors import AccessDenied, DuplicateResource, InvalidRequest
from zhiyin_kernel.modules import ModuleFlowDefinition, ModuleFlowDraft, ModuleFlowRunRequest
from zhiyin_business.services.module_contracts import resolve_binding, schema_at_path, validate_bindings, validate_contract


class ModuleFlowService:
    def __init__(self, platform, repository: ModuleFlowRepository):
        self.platform, self.repository = platform, repository

    def validate(self, definition: ModuleFlowDefinition, *, pin=False):
        definition = definition.model_copy(deep=True)
        nodes = {node.id: node for node in definition.nodes}
        if len(nodes) != len(definition.nodes):
            raise InvalidRequest("工作流节点编号不能重复")
        def source_schema(reference):
            source, separator, pointer = reference.partition("/")
            if source == "$input":
                schema = definition.input_schema
            else:
                upstream = self.platform.definition(nodes[source].module_id).manifest.output_schema
                schema = {"type": "object", "$defs": upstream.get("$defs", {}), "additionalProperties": False,
                    "properties": {"data": upstream, "sources": {"type": "array", "items": {"type": "string"}},
                        "empty": {"type": "boolean"}, "module_version": {"type": "string"}, "trace": {"type": "array"}}}
            return schema_at_path(schema, pointer.split("/") if separator else [], reference)
        dependencies = {}
        actions = []
        for node in definition.nodes:
            module = self.platform.verify_version(node.module_id, node.module_version)
            if pin:
                node.module_version = module.manifest.version
            if node.operation == "action":
                actions.append(node.id)
                if not node.action or node.action not in module.manifest.actions:
                    raise InvalidRequest(f"节点 {node.id} 引用了模块未声明的操作")
            elif node.action:
                raise InvalidRequest("读取节点不能声明业务操作")
            deps = set()
            for field, reference in node.bindings.items():
                if not field or field in {"user_id", "actor", "account"}:
                    raise InvalidRequest("绑定目标不合法，用户身份由平台注入")
                source = reference.split("/", 1)[0]
                if source == "$input":
                    continue
                if source not in nodes or source == node.id:
                    raise InvalidRequest(f"节点 {node.id} 的绑定来源不存在或引用自身")
                deps.add(source)
            dependencies[node.id] = deps
            if node.operation == "read":
                target = module.manifest.input_schema
            else:
                capability = next((item for item in self.platform.capabilities if item.id == node.action), None)
                target = capability.input_schema if capability else {"type": "object"}
            validate_bindings(target, node.input, node.bindings, source_schema)
        if len(actions) > 1:
            raise InvalidRequest("首版工作流只允许一个末端业务操作")
        if actions and any(actions[0] in deps for deps in dependencies.values()):
            raise InvalidRequest("业务操作必须是末端节点，操作后回读由平台负责")
        pending, ordered = dict(nodes), []
        while pending:
            ready = [node for node in pending.values() if dependencies[node.id].issubset({item.id for item in ordered})]
            if not ready:
                raise InvalidRequest("工作流依赖形成循环")
            # All read-only computation must complete before the one write.
            reads = [node for node in ready if node.operation == "read"]
            ready = reads or ready
            for node in ready:
                ordered.append(node)
                pending.pop(node.id)
        definition.nodes = ordered
        return definition

    async def save(self, draft: ModuleFlowDraft, actor, *, admin=False):
        if draft.expected_revision:
            current = await self.repository.get(draft.id)
            if current["owner"] != actor and not admin:
                raise AccessDenied("只能修改自己创建的工作流")
        definition = self.validate(ModuleFlowDefinition(input_schema=draft.input_schema, nodes=draft.nodes))
        value = draft.model_dump()
        value.update(definition.model_dump())
        return await self.repository.save(value, actor)

    async def publish(self, workflow_id, revision, actor, *, admin=False):
        current = await self.repository.get(workflow_id)
        if current["owner"] != actor and not admin:
            raise AccessDenied("只能发布自己创建的工作流")
        definition = self.validate(ModuleFlowDefinition.model_validate(current["definition"]), pin=True)
        return await self.repository.publish(workflow_id, revision, definition.model_dump(), actor)

    async def unpublish(self, workflow_id, revision, actor, *, admin=False):
        current = await self.repository.get(workflow_id)
        if current["owner"] != actor and not admin:
            raise AccessDenied("只能暂停自己创建的工作流")
        # A stale or missing module is precisely why an owner may need to pause
        # publication; removing the public pointer never invokes its code.
        return await self.repository.unpublish(workflow_id, revision, actor)

    async def run(self, workflow_id, user_id, body: ModuleFlowRunRequest, *, published=False, admin=False):
        current = await self.repository.get(workflow_id, published=published)
        if not published and current["owner"] != user_id and not admin:
            raise AccessDenied("只能调试自己创建的工作流")
        if body.expected_revision is not None and body.expected_revision != current["revision"]:
            raise DuplicateResource("工作流版本已变化")
        definition = self.validate(ModuleFlowDefinition.model_validate(current["definition"]), pin=True)
        validate_contract(definition.input_schema, body.input, "workflow.input")
        writes = any(node.operation == "action" for node in definition.nodes)
        if writes and (body.mode != "live" or not body.confirm_actions):
            raise AccessDenied("业务操作需要真实数据模式，并明确确认 confirm_actions")
        if published and body.mode != "live":
            raise AccessDenied("用户工作流只允许真实数据模式")
        if body.mode == "live":
            # Check current policy even for a duplicate request whose persisted
            # receipt would otherwise bypass the module execution checks.
            for node in definition.nodes:
                policy = await self.platform.enabled_policy(node.module_id)
                manifest = self.platform.definition(node.module_id).manifest
                if set(manifest.reads) - set(policy.reads):
                    raise AccessDenied("工作流模块的数据授权已撤销")
                if node.operation == "action" and node.action not in policy.actions:
                    raise AccessDenied("工作流模块的业务操作授权已撤销")
        digest = hashlib.sha256(json.dumps({"revision": current["revision"], "definition": definition.model_dump(),
            "request": body.model_dump(exclude={"request_id"})}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        run, created = await self.repository.begin_run(workflow_id, current["revision"], user_id, body.request_id, digest, body.mode)
        if not created:
            # A running receipt can represent an interrupted write. Never replay
            # it automatically: the durable trace is the recovery evidence.
            return run
        for node in definition.nodes:
            entry = {"node_id": node.id, "module_id": node.module_id, "module_version": node.module_version,
                     "operation": node.operation, "status": "running"}
            run["trace"].append(entry)
            await self.repository.update_run(run)
            try:
                inputs = copy.deepcopy(node.input)
                for field, reference in node.bindings.items():
                    inputs[field] = copy.deepcopy(resolve_binding(reference, body.input, run["outputs"]))
                entry["input"] = inputs
                if node.operation == "action":
                    # Reuse the latest query input for this module. Action
                    # payloads have a different schema from module query input.
                    readback_input = next((copy.deepcopy(previous["input"]) for previous in reversed(run["trace"])
                        if previous.get("module_id") == node.module_id and previous.get("operation") == "read"
                        and previous.get("status") == "succeeded"), {})
                    validate_contract(self.platform.definition(node.module_id).manifest.input_schema, readback_input, "action.readback_input")
                    # Persist before calling business logic. A connection loss
                    # after this point is explicitly an uncertain write.
                    entry["action_started"] = True
                    await self.repository.update_run(run)
                    await self.platform.execute_action(node.module_id, user_id, node.action, inputs, expected_version=node.module_version)
                    run["action_committed"] = True
                    await self.repository.update_run(run)
                    value = await self.platform.invoke(node.module_id, user_id, readback_input, expected_version=node.module_version)
                else:
                    value = await self.platform.invoke(node.module_id, user_id, inputs,
                        expected_version=node.module_version, mode=body.mode, preview=not published)
                run["outputs"][node.id] = value.model_dump(mode="json")
                entry.update(status="succeeded", result=value.model_dump(mode="json"))
                await self.repository.update_run(run)
            except Exception as exc:
                entry.update(status="failed", error=str(exc))
                if entry.get("action_started") and not run["action_committed"]:
                    entry["effect_uncertain"] = True
                run.update(status="failed", error=f"节点 {node.id} 失败：{exc}")
                return await self.repository.update_run(run)
        run["status"] = "succeeded"
        return await self.repository.update_run(run)
