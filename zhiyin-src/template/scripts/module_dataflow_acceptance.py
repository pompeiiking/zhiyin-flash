"""Mandatory real-data gates for every candidate module, including disabled ones.

Run only against a disposable candidate PostgreSQL/Redis environment. No model
credentials are needed. The executor must discard that environment afterwards.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
from uuid import uuid4

from agno.run import RunContext

from zhiyin_boot.container import build_container
from zhiyin_boot.settings import Settings
from zhiyin_business.services.module_contracts import resolve_binding
from zhiyin_kernel.assets import ActionPlan, ActionPhase, ActionTask
from zhiyin_kernel.errors import AccessDenied, InvalidRequest
from zhiyin_kernel.modules import ModuleFlowDraft, ModuleFlowRunRequest


async def main(module_id=None, output=None):
    if os.environ.get("ZHIYIN_MODULE_ENV") not in {"candidate", "integration"} or os.environ.get("ZHIYIN_DATAFLOW_ISOLATED") != "1":
        raise RuntimeError("Dataflow acceptance requires a disposable candidate DB and ZHIYIN_DATAFLOW_ISOLATED=1")
    container = build_container(Settings.from_env())
    report = {"passed": False, "gates": [], "assertions": [], "modules": {}, "preview": {}, "dataflow": {}}
    originals, restoration_errors = {}, []
    service = container.extra["module_platform"]
    report["revision"] = service.revision
    actor = "dataflow_acceptance"
    selected = [module_id] if module_id else list(service.modules)
    suffix = uuid4().hex[:12]
    users = [f"df_{suffix}_one", f"df_{suffix}_two"]
    report["preview_user_id"] = users[0]
    reads = []

    def assertion(name, condition):
        if not condition:
            raise AssertionError(name)
        report["assertions"].append({"id": name, "passed": True})

    def record_read(capability, handler):
        async def read(user_id):
            value = await handler(user_id)
            reads.append({"capability": capability, "user": "first" if user_id == users[0] else "second" if user_id == users[1] else "unexpected"})
            return value
        return read

    async def configure(mid, **changes):
        policy = await service.policy(mid)
        return await service.configure(mid, policy.model_copy(update=changes), actor)

    async def snapshot(uid):
        plan = (await container.facade.get_action_plan(uid)).model_dump(mode="json")
        fields = [field.model_dump(mode="json") for field in await container.profile_service.get_fields(uid)]
        notes = [note.model_dump(mode="json") for note in await container.facade.list_notes(uid)]
        return {"plan": plan, "profile": fields, "notes": notes}

    try:
        if not container.settings.use_postgres:
            raise RuntimeError("Real PostgreSQL is mandatory")
        assertion("platform_release_empty_queue_real_sql", await service.repository.claim() is None)
        for mid in selected:
            service.definition(mid)
        agent_ids = [agent.id for agent in await service.agents()]
        assertion("registered_agent_available", bool(agent_ids))
        for mid in service.modules:
            originals[mid] = (await service.policy(mid)).model_copy(deep=True)
        for mid, definition in service.modules.items():
            await configure(mid, enabled=True, reads=definition.manifest.reads,
                actions=definition.manifest.actions, agents=[agent_ids[0]] if definition.manifest.tool else [])
        for uid in users:
            await container.identity_service.register(uid, uuid4().hex, uid)
            await container.asset_service.save_action_plan(uid, ActionPlan(id=f"plan_{uid}", phases=[
                ActionPhase(name=f"phase_{uid}", date_range="synthetic", tasks=[
                    ActionTask(id=f"first_{uid}", text=f"synthetic_{uid}_completed", done=True),
                    ActionTask(id=f"second_{uid}", text=f"synthetic_{uid}_pending", done=False)])]))
        service.readers = {key: record_read(key, handler) for key, handler in service.readers.items()}
        for index, mid in enumerate(selected):
            definition = service.definition(mid)
            manifest = definition.manifest
            declaration = json.loads((definition.root / manifest.dataflow).read_text(encoding="utf-8")) if manifest.dataflow else {}
            inputs = declaration.get("input", definition.fixture("normal").get("input", {}))
            item = {"version": manifest.version, "kind": manifest.kind, "inputs": {}, "fixtures": {}, "live": {}, "reads": [], "passed": False}
            report["modules"][mid] = item
            before = [await snapshot(uid) for uid in users]
            for fixture in ("normal", "empty"):
                fixture_inputs = definition.fixture(fixture).get("input", inputs)
                item["inputs"][fixture] = copy.deepcopy(fixture_inputs)
                value = await service.invoke(mid, users[0], fixture_inputs, mode="fixture", fixture=fixture, preview=True, expected_version=manifest.version)
                item["fixtures"][fixture] = value.model_dump(mode="json")
                for check in declaration.get("fixture_assertions", []):
                    if check["fixture"] == fixture:
                        assertion(f"{mid}.fixture.{fixture}.{check['path']}",
                            resolve_binding("value" + check["path"], {}, {"value": value.model_dump()}) == check["equals"])
            try:
                error_inputs = definition.fixture("error").get("input", inputs)
                item["inputs"]["error"] = copy.deepcopy(error_inputs)
                await service.invoke(mid, users[0], error_inputs, mode="fixture", fixture="error", preview=True)
            except InvalidRequest as exc:
                item["fixture_error"] = str(exc)
                assertion(f"{mid}.fixture.error_reported", True)
            else:
                raise AssertionError(f"{mid}: error fixture was not rejected")
            start = len(reads)
            for label, uid, other in (("first", users[0], users[1]), ("second", users[1], users[0])):
                at = len(reads)
                value = await service.invoke(mid, uid, inputs, expected_version=manifest.version)
                item["live"][label] = value.model_dump(mode="json")
                assertion(f"{mid}.{label}.sdk_identity", all(call["user"] == label for call in reads[at:]))
                assertion(f"{mid}.{label}.no_other_user_data", other not in json.dumps(value.model_dump()))
            item["reads"] = copy.deepcopy(reads[start:])
            assertion(f"{mid}.declared_reads_executed", set(manifest.reads).issubset({call["capability"] for call in item["reads"]}))
            for check in declaration.get("live_assertions", []):
                assertion(f"{mid}.live.{check['path']}", resolve_binding("value" + check["path"], {}, {"value": item["live"]["first"]}) == check["equals"])
            assertion(f"{mid}.readonly_preserves_business_data", before == [await snapshot(uid) for uid in users])
            if manifest.tool:
                handler = container.extra["tool_registry"].get(manifest.tool).handler
                deps = {"module_agent_id": agent_ids[0], "module_results": [], "module_attempts": [], "renderables": []}
                context = RunContext(run_id=suffix, session_id=suffix, user_id=users[0], dependencies=deps)
                returned = json.loads(await handler(context, input=inputs))
                assertion(f"{mid}.registered_skill_returns_result", returned["data"] == item["live"]["first"]["data"] and bool(deps["module_results"]))
                if not manifest.conversation:
                    assertion(f"{mid}.headless_skill_has_no_card", not deps["renderables"])
            workflow_id = f"df_{suffix}_{index}"
            nodes = [{"id": "component", "module_id": mid, "module_version": manifest.version, "input": inputs}]
            upstream = declaration.get("upstream")
            if upstream:
                upstream_module = service.definition(upstream["module_id"])
                nodes.insert(0, {"id": "upstream", "module_id": upstream["module_id"],
                    "module_version": upstream_module.manifest.version, "input": upstream.get("input", {})})
                nodes[-1]["bindings"] = upstream["bindings"]
            draft = ModuleFlowDraft(id=workflow_id, name=f"Acceptance {mid}", nodes=nodes)
            await service.flows.save(draft, users[0])
            await service.flows.publish(workflow_id, 1, users[0])
            run_body = ModuleFlowRunRequest(mode="live", input={}, request_id=f"df_run_{suffix}_{index}")
            run = await service.flows.run(workflow_id, users[0], run_body, published=True)
            assertion(f"{mid}.published_workflow_consumes_output", run["status"] == "succeeded" and run["outputs"]["component"]["data"] == item["live"]["first"]["data"])
            assertion(f"{mid}.persistent_trace", bool((await service.flows.repository.runs(workflow_id, users[0]))[0]["trace"]))
            replay = await service.flows.run(workflow_id, users[0], run_body, published=True)
            assertion(f"{mid}.request_deduplicated", run["id"] == replay["id"])
            report["dataflow"][mid] = run
            report["preview"][mid] = item["fixtures"]["normal"]
            for action in manifest.actions:
                if action != "plan.task.set_done":
                    raise AssertionError(f"No platform acceptance scenario registered for action {action}")
                task = (await container.facade.get_action_plan(users[0])).phases[0].tasks[1]
                second_before = await snapshot(users[1])
                action_draft = ModuleFlowDraft(id=workflow_id, name=f"Action acceptance {mid}", expected_revision=1, nodes=[
                    {"id": "component", "module_id": mid, "module_version": manifest.version, "input": inputs},
                    {"id": "complete", "module_id": mid, "module_version": manifest.version, "operation": "action",
                     "action": action, "input": {"done": True}, "bindings": {"task_id": "$input/task_id"}}])
                await service.flows.save(action_draft, users[0])
                await service.flows.publish(workflow_id, 2, users[0])
                action_body = ModuleFlowRunRequest(mode="live", confirm_actions=True, input={"task_id": task.task_id},
                    request_id=f"df_action_{suffix}_{index}", expected_revision=2)
                action_run = await service.flows.run(workflow_id, users[0], action_body, published=True)
                assertion(f"{mid}.action_workflow_committed", action_run["status"] == "succeeded" and action_run["action_committed"])
                report["dataflow"][mid] = action_run
                assertion(f"{mid}.action_request_deduplicated", (await service.flows.run(workflow_id, users[0], action_body, published=True))["id"] == action_run["id"])
                after = await container.facade.get_action_plan(users[0])
                assertion(f"{mid}.action_real_readback", after.phases[0].tasks[1].done)
                assertion(f"{mid}.action_other_user_unchanged", await snapshot(users[1]) == second_before)
                item["action_result"] = (await service.invoke(mid, users[0], inputs)).model_dump(mode="json")
                await service.execute_action(mid, users[0], action, {"task_id": task.task_id, "done": False}, expected_version=manifest.version)
            await configure(mid, enabled=False)
            try:
                await service.invoke(mid, users[0], inputs)
            except AccessDenied:
                assertion(f"{mid}.disabled_denies_runtime", True)
            else:
                raise AssertionError(f"{mid}: disabled module executed")
            await configure(mid, enabled=True)
            item["passed"] = True
        report["gates"] = [{"id": "module_dataflow", "passed": True, "modules": selected}]
        report["passed"] = True
    except Exception as exc:
        report["error"] = str(exc)
        report["gates"].append({"id": "module_dataflow", "passed": False, "error": str(exc)})
        raise
    finally:
        for mid, policy in originals.items():
            try:
                current = await service.policy(mid)
                await service.configure(mid, policy.model_copy(update={"revision": current.revision}), actor)
            except Exception as exc:
                restoration_errors.append({"module": mid, "error": str(exc)})
        report["configuration_restored"] = not restoration_errors
        if restoration_errors:
            report.update(passed=False, restoration_errors=restoration_errors)
        if output:
            Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("ZHIYIN_DATAFLOW_REPORT=" + json.dumps(report, ensure_ascii=False))
        for closable in reversed(container.extra.get("closables", [])):
            close = getattr(closable, "aclose", None)
            if close:
                await close()
        if restoration_errors:
            raise RuntimeError("Failed to restore candidate module policy")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module")
    parser.add_argument("--output")
    args = parser.parse_args()
    asyncio.run(main(args.module, args.output))
