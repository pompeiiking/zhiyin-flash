"""G09: real PostgreSQL, HTTP/JWT and configured model; creates one QA account.

Run inside the API container. Evidence contains no password, token or model text.
"""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import httpx
from zhiyin_boot import Settings, build_container
from zhiyin_business.services.analysis_access import activate, load_scope
from zhiyin_kernel.enums import LoopStage


async def main():
    result = {"at": datetime.now(timezone.utc).isoformat(), "environment":
              "local Docker PostgreSQL + HTTP/JWT + configured real model", "cases": []}

    def check(name, passed):
        result["cases"].append({"name": name, "passed": bool(passed)})
        print(name, "PASS" if passed else "FAIL", flush=True)
        assert passed, name

    container = build_container(Settings.from_env())
    account, password = "qa_cap_sources_" + uuid4().hex[:10], uuid4().hex
    await container.identity_service.register(account, password, "资料偏好联调")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000/api/v1/app", timeout=240) as client:
        async def request(method, path, body=None):
            response = await client.request(method, path, json=body)
            response.raise_for_status()
            value = response.json()
            assert value["code"] == 0, path
            return value["data"]

        try:
            auth = await request("POST", "/auth/login", {"account": account, "password": password})
            client.headers["Authorization"] = "Bearer " + auth["token"]
            user = await container.identity_service.current_user(token=auth["token"])
            uid = user.id
            for key, value, source in (
                ("major", "软件工程", "record"),
                ("interest", "LEGACY_SOURCE_SENTINEL", "conversation"),
                ("direction", "后端开发", "user_edit"),
            ):
                await container.profile_service.update_field(uid, key, value, confidence=1, source=source)
            await container.memory_service.upsert(uid, "legacy", loop_stage=LoopStage.COLLECT,
                lead_agent="profile_analyst", summary_delta="LEGACY_SUMMARY_SENTINEL")
            prefs = await request("GET", "/preferences")
            for academic, material in ((False, True), (True, False), (False, False), (True, True)):
                prefs.update(academic_analysis=academic, material_analysis=material)
                await request("PUT", "/preferences", prefs)
                label = f"academic={academic},material={material}"
                scope = await load_scope(container.student_state, uid)
                with activate(scope):
                    fields = await container.profile_service.get_fields(uid)
                    values = {f.key: f.value for f in fields}
                    check(label + ": persisted source filter", ("major" in values) == academic
                          and values.get("direction") == "后端开发"
                          and (("interest" in values) == (academic and material)))
                    if scope.restricted:
                        check(label + ": legacy summary excluded",
                              not await container.memory_service.list_by_user(uid))
                response = await client.post("/brief/today")
                frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                check(label + ": real model terminal result", response.status_code == 200
                      and any("result" in f for f in frames) and not any("error" in f for f in frames))
                response = await client.post("/brief/today")
                frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                check(label + ": same-scope cache", any(f.get("result", {}).get("meta", {}).get("cached") for f in frames))

            prefs.update(academic_analysis=False, material_analysis=True)
            await request("PUT", "/preferences", prefs)
            with activate(await load_scope(container.student_state, uid)):
                await container.profile_service.update_field(uid, "strength", "材料提取的项目能力",
                    confidence=.8, source="conversation")
            # Load from a fresh repository/service instance, not the current scope.
            fresh = build_container(Settings.from_env())
            with activate(await load_scope(fresh.student_state, uid)):
                check("derived profile provenance persists", any(f.key == "strength" for f in
                    await fresh.profile_service.get_fields(uid)))
            prefs.update(material_analysis=False)
            await request("PUT", "/preferences", prefs)
            with activate(await load_scope(fresh.student_state, uid)):
                check("disabling material excludes its new derivation", not any(f.key == "strength" for f in
                    await fresh.profile_service.get_fields(uid)))

            denied = await client.post("/conversation/message", json={"task_id": "unused",
                "message": "读取附件", "material_ids": ["not-loaded"], "client_msg_id": uuid4().hex})
            check("disabled attachment rejected before reading", denied.status_code in (400, 422)
                  and "上传材料参与分析已关闭" in denied.text)
            boot = await request("GET", "/bootstrap")
            session = await request("POST", "/task/enter", {"task_code": boot["task_entries"][0]["code"]})
            turn = await request("POST", "/conversation/message", {
                "task_id": session["task_id"], "message": "我想学习后端开发，请帮我梳理从小项目开始的思路。",
                "client_msg_id": uuid4().hex})
            check("both sources disabled: real conversation works", bool(turn["messages"]))
            with activate(await load_scope(fresh.student_state, uid)):
                check("new restricted turns remain usable after database reload", bool(
                    await fresh.memory_service.list_turns(uid, session["task_id"])))
            check("ordinary reads preserve original profile and history",
                  any(f.key == "interest" for f in await fresh.profile_service.get_fields(uid))
                  and bool(await fresh.memory_service.list_by_user(uid)))
        finally:
            Path("/tmp/analysis-sources-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
