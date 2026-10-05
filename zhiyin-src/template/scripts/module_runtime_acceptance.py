"""Run real PostgreSQL lease and optional model acceptance inside an isolated API container."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from uuid import uuid4

from agno.agent import Agent
from agno.run import RunContext

from zhiyin_boot.container import build_container
from zhiyin_boot.settings import Settings
from zhiyin_business.policies.renderers import validate_renderables
from zhiyin_kernel.errors import AccessDenied, DuplicateResource


async def main(model=False):
    if os.environ.get("ZHIYIN_MODULE_ENV") not in {"workbench", "staging"}:
        raise RuntimeError("Acceptance is restricted to isolated environments")
    container = build_container(Settings.from_env())
    results = {}
    try:
        service = container.extra["module_platform"]
        repository = service.repository
        suffix = uuid4().hex
        body = {"commit": "a" * 40, "kind": "check", "request_id": "accept_" + suffix}
        job, duplicate = await asyncio.gather(repository.create_job("acceptance", body), repository.create_job("acceptance", body))
        assert job["id"] == duplicate["id"]
        await repository.approve(job["id"], "acceptance")
        other = await repository.create_job("acceptance", {**body, "request_id": "second_" + suffix})
        try:
            await repository.approve(other["id"], "acceptance")
            raise AssertionError("Concurrent environment release was accepted")
        except DuplicateResource:
            pass
        claims = await asyncio.gather(repository.claim(), repository.claim())
        claimed = next(x for x in claims if x)
        assert sum(x is not None for x in claims) == 1
        assert claimed["id"] == job["id"]
        await repository.update_job(job["id"], claimed["lease"], {"stage": "acceptance", "result": {"marker": suffix}})
        # Expire only this test lease to simulate executor process loss.
        await repository.db.execute("UPDATE biz_module_release SET lease_until=now()-interval '1 second' WHERE id=$1", job["id"])
        resumed = await repository.claim()
        assert resumed["result"]["resuming"] and resumed["result"]["marker"] == suffix
        assert resumed["lease"] != claimed["lease"]
        try:
            await repository.update_job(job["id"], claimed["lease"], {"status": "succeeded"})
            raise AssertionError("Old executor lease was accepted")
        except DuplicateResource:
            pass
        await repository.update_job(job["id"], resumed["lease"], {"status": "succeeded", "stage": "acceptance_only"})
        await repository.approve(other["id"], "acceptance")
        second = await repository.claim()
        await repository.update_job(second["id"], second["lease"], {"status": "succeeded", "stage": "acceptance_only"})
        results["postgres_idempotency_serial_release_lease_recovery_fencing"] = True

        policy = await service.policy("action_progress")
        granted = await service.configure("action_progress", policy.model_copy(update={"enabled": True,
            "reads": ["plan.read"], "actions": ["plan.task.set_done"], "agents": ["path_planner"]}), "acceptance")
        try:
            tool = container.extra["tool_registry"].get("action_progress.read").handler
            deps = {"renderables": [], "module_agent_id": "path_planner"}
            user_id = "tao" if os.environ["ZHIYIN_MODULE_ENV"] == "workbench" else "module_tester"
            context = RunContext(run_id=suffix, user_id=user_id, session_id="module_acceptance", dependencies=deps)
            value = json.loads(await tool(context))
            assert value == (await service.read("action_progress", user_id)).model_dump()
            assert len(validate_renderables(deps["renderables"])) == 1
            results["tool_authorized_data_and_renderable_contract"] = True
            if model:
                deps["renderables"].clear()
                agent = Agent(model=container.extra["agno_runtime"].create_model(temperature=0), tools=[tool],
                              tool_call_limit=1, telemetry=False,
                              instructions="先调用提供的行动计划进度工具一次，再根据实际结果用一句中文说明完成数和总数。")
                answer = await agent.arun("查询我的行动计划进度，务必调用工具。", user_id=user_id,
                                          session_id="accept_" + suffix, dependencies=deps)
                assert deps["renderables"], "Real model did not call the module tool"
                assert len(validate_renderables(deps["renderables"])) == 1
                results["real_model"] = {"model": container.settings.llm_model, "answer": str(answer.content),
                    "renderables": deps["renderables"]}
                embeddings = await container.embedding.embed(["模块行动计划进度验收"])
                assert len(embeddings) == 1 and len(embeddings[0]) == 1024
                results["real_embedding_dimensions"] = len(embeddings[0])
            revoked = await service.configure("action_progress", granted.model_copy(update={"enabled": False}), "acceptance")
            assert await service.tool_names("path_planner") == []
            try:
                await tool(context)
                raise AssertionError("Previously obtained tool bypassed current policy")
            except AccessDenied:
                pass
            granted = revoked
            results["retained_tool_obeys_revocation"] = True
        finally:
            current = await service.policy("action_progress")
            await service.configure("action_progress", policy.model_copy(update={"revision": current.revision}), "acceptance")
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        for value in reversed(container.extra.get("closables", [])):
            close = getattr(value, "aclose", None)
            if close:
                await close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="store_true")
    asyncio.run(main(parser.parse_args().model))
