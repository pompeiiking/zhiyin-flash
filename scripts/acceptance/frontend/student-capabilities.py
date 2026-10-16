"""G01–G12 acceptance against running HTTP + PostgreSQL, using fresh QA accounts.

Run inside the API container: python /tmp/student-capabilities.py.
Only newly registered qa_cap_* users are written. No tokens in evidence output.
The --readback mode verifies the same records and downloads after a restart.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import httpx
from zhiyin_boot.container import build_container
from zhiyin_boot.settings import Settings
from zhiyin_kernel.assets import (
    DirectionPlan,
    Report,
    Verdict,
    Swot,
    ReportDimensionGroup,
    ReportDimensionItem,
)

STATE = Path("/tmp/student-capabilities-private.json")
OUTPUT = Path("/tmp/student-capabilities-results.json")


async def main():
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "environment": "local Docker HTTP + PostgreSQL + JWT; fresh QA accounts only",
        "cases": [],
    }
    clients = []

    async def request(
        client, method, path, body=None, *, expected=200, endpoint=None, binary=False
    ):
        r = await client.request(method, "/api/v1/app" + path, json=body)
        passed = r.status_code == expected
        data = None if binary else r.json()
        if expected == 200 and not binary:
            passed = passed and data.get("code") == 0
        report["cases"].append(
            {
                "endpoint": method + " /api/v1/app" + (endpoint or path),
                "http": r.status_code,
                "expected": expected,
                "passed": passed,
            }
        )
        print(
            method,
            endpoint or path,
            r.status_code,
            "PASS" if passed else "FAIL",
            flush=True,
        )
        assert passed, f"{method} {path}: {r.status_code} {r.text[:300]}"
        return r.content if binary else data.get("data")

    async def login(account, password):
        client = httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=240)
        clients.append(client)
        data = await request(
            client, "POST", "/auth/login", {"account": account, "password": password}
        )
        client.headers["Authorization"] = "Bearer " + data["token"]
        return client

    try:
        if "--readback" in sys.argv:
            private = json.loads(STATE.read_text())
            a = await login(private["account"], private["password"])
            assert (await request(a, "GET", "/preferences"))["quiet_start"] == "23:00"
            assert any(
                t["text"] == "项目第二步"
                for p in (await request(a, "GET", "/plan/action"))["phases"]
                for t in p["tasks"]
            )
            assert (await request(a, "GET", "/reviews"))["items"][0]["applied_at"]
            assert (await request(a, "GET", "/measurements"))["items"]
            assert (await request(a, "GET", "/schedule/semester"))["weeks"] == 20
            assert any(
                n["id"] == private["notice"] and n["status"] == "done"
                for n in await request(a, "GET", "/notifications")
            )
            for fmt, eid in private["exports"].items():
                content = await request(
                    a,
                    "GET",
                    "/assets/download/" + eid,
                    endpoint="/assets/download/{export_id}",
                    binary=True,
                )
                assert (
                    content.startswith(b"%PDF-")
                    if fmt == "pdf"
                    else "项目第二步"
                    in ZipFile(BytesIO(content)).read("word/document.xml").decode()
                )
            if private.get("session_snapshot"):
                snap = await request(
                    a,
                    "GET",
                    "/sessions/" + private["session"] + "/snapshot",
                    endpoint="/sessions/{task_id}/snapshot",
                )
                assert snap == private["session_snapshot"]
            report["restart_readback"] = True
            return

        c = build_container(Settings.from_env())
        suffix = uuid4().hex[:10]
        account, other, password = (
            "qa_cap_" + suffix,
            "qa_cap_other_" + suffix,
            uuid4().hex,
        )
        await c.identity_service.register(account, password, "能力联调")
        await c.identity_service.register(other, password, "隔离联调")
        a, b = await login(account, password), await login(other, password)
        private = {
            "account": account,
            "other": other,
            "password": password,
            "exports": {},
        }
        STATE.write_text(json.dumps(private, ensure_ascii=False))
        prefs = await request(a, "GET", "/preferences")
        prefs.update(quiet_start="23:00", quiet_end="07:00", proactive_reminders=False)
        assert not (await request(a, "PUT", "/preferences", prefs))[
            "proactive_reminders"
        ]
        assert (await request(b, "GET", "/preferences"))["proactive_reminders"]
        plan = await request(
            a,
            "POST",
            "/plan/action/phases",
            {
                "name": "准备阶段",
                "blocking_conditions": ["先明确任务"],
                "handoff_requirements": ["提交作品"],
            },
        )
        pid = plan["phases"][0]["id"]
        plan = await request(
            a, "POST", "/plan/action/phases", {"name": "提交阶段", "depends_on": [pid]}
        )
        second = plan["phases"][1]["id"]
        await request(
            a,
            "PUT",
            "/plan/action/phases/" + second,
            {"name": "提交与跟进", "depends_on": [pid]},
            endpoint="/plan/action/phases/{phase_id}",
        )
        await request(
            a,
            "PUT",
            "/plan/action/phases/" + pid,
            {"name": "循环", "depends_on": [second]},
            expected=422,
            endpoint="/plan/action/phases/{phase_id}",
        )
        monday = datetime.now(timezone.utc).date() - timedelta(
            days=datetime.now(timezone.utc).weekday()
        )
        scheduled = monday.isoformat() + "T08:15:00+08:00"
        body = {
            "text": "整理项目",
            "phase_id": pid,
            "status": "in_progress",
            "progress": 35,
            "scheduled_at": scheduled,
            "estimated_minutes": 60,
        }
        plan = await request(a, "POST", "/plan/action/tasks", body)
        tid = plan["phases"][0]["tasks"][0]["task_id"]
        plan = await request(
            a,
            "POST",
            "/plan/action/tasks",
            {
                "text": "项目第二步",
                "phase_id": pid,
                "parent_task_id": tid,
                "estimated_minutes": 30,
                "scheduled_at": scheduled,
            },
        )
        assert plan["phases"][0]["tasks"][-1]["parent_task_id"] == tid
        await request(
            a, "POST", "/plan/action/tasks", {"text": "提交成果", "phase_id": second}
        )
        assert (await request(a, "GET", "/plan/action"))["phases"][1]["blocked_by"] == [
            pid
        ]
        versions = await request(a, "GET", "/assets/action_plan/versions")
        version = versions[-1]["version"]
        snap = await request(
            a,
            "GET",
            f"/assets/action_plan/versions/{version}/content",
            endpoint="/assets/{asset_type}/versions/{version}/content",
        )
        body.update(status="waiting", waiting_reason="等待反馈")
        await request(
            a,
            "PUT",
            "/plan/action/tasks/" + tid,
            body,
            endpoint="/plan/action/tasks/{task_id}",
        )
        assert (
            await request(
                a,
                "GET",
                f"/assets/action_plan/versions/{version}/content",
                endpoint="/assets/{asset_type}/versions/{version}/content",
            )
            == snap
        )
        await request(
            b,
            "PUT",
            "/plan/action/tasks/" + tid,
            body,
            expected=404,
            endpoint="/plan/action/tasks/{task_id}",
        )
        await request(
            a,
            "GET",
            "/assets/action_plan/versions/999999/content",
            expected=404,
            endpoint="/assets/{asset_type}/versions/{version}/content",
        )
        review = await request(
            a,
            "POST",
            "/reviews",
            {
                "task_id": tid,
                "reason": "达到预期",
                "note": "项目已提交",
                "result": "complete",
            },
        )
        review = await request(
            a,
            "PUT",
            "/reviews/" + review["id"],
            {
                "task_id": tid,
                "reason": "达到预期",
                "note": "补充了执行结果",
                "result": "complete",
            },
            endpoint="/reviews/{review_id}",
        )
        assert len(review["history"]) == 1
        applied = await request(
            a,
            "POST",
            "/reviews/" + review["id"] + "/apply",
            endpoint="/reviews/{review_id}/apply",
        )
        assert applied["applied_at"]
        assert (
            await request(
                a,
                "POST",
                "/reviews/" + review["id"] + "/apply",
                endpoint="/reviews/{review_id}/apply",
            )
        )["applied_at"] == applied["applied_at"]
        assert (await request(a, "GET", "/reviews"))["reasons"]["达到预期"] == 1
        await request(
            b,
            "POST",
            "/reviews/" + review["id"] + "/apply",
            expected=404,
            endpoint="/reviews/{review_id}/apply",
        )
        notice = await c.notifier.push(
            account, title="能力验收提醒", body="验证稍后、完成、恢复与历史"
        )
        private["notice"] = notice.message_id
        await request(a, "GET", "/notifications")
        for state in ["read", "later", "done", "pending", "done"]:
            changed = await request(
                a,
                "PATCH",
                "/notifications/" + notice.message_id,
                {
                    "status": state,
                    "snoozed_until": (
                        datetime.now(timezone.utc) + timedelta(hours=1)
                    ).isoformat()
                    if state == "later"
                    else None,
                },
                endpoint="/notifications/{message_id}",
            )
            assert changed["status"] == state
        assert await request(a, "GET", "/notifications/pending") == []
        await request(
            b,
            "PATCH",
            "/notifications/" + notice.message_id,
            {"status": "pending"},
            expected=404,
            endpoint="/notifications/{message_id}",
        )
        courses = json.dumps(
            [
                {
                    "name": "接口联调课程",
                    "weekday": 1,
                    "start_period": 1,
                    "end_period": 2,
                    "weeks": "1-20",
                    "place": "联调教室",
                }
            ],
            ensure_ascii=False,
        )
        await request(
            a,
            "POST",
            "/academic/import",
            {"courses": courses, "grades": "", "school": "河北大学", "term": "2026秋"},
        )
        await request(a, "GET", "/schedule/semester")
        semester = {
            "first_monday": monday.isoformat(),
            "weeks": 20,
            "periods": [
                {"number": 1, "start": "08:00", "end": "08:45"},
                {"number": 2, "start": "08:55", "end": "09:40"},
            ],
            "weekly_available_minutes": 600,
        }
        await request(a, "PUT", "/schedule/semester", semester)
        workload = await request(
            a,
            "GET",
            "/schedule/workload?start=" + monday.isoformat(),
            endpoint="/schedule/workload",
        )
        assert (
            workload["configured"]
            and workload["weeks"][0]["course_minutes"] == 90
            and workload["conflicts"]
        )
        dv = await c.asset_service.save_direction_plans(
            account,
            [
                DirectionPlan(
                    id="dir_" + suffix,
                    role="main",
                    name="软件开发",
                    target_desc="接口验收方向",
                    fit_reason="验收输入",
                    main_risk="须补实践",
                )
            ],
        )
        weights = await request(a, "GET", "/plan/direction-weights")
        weights.update(major=3)
        await request(a, "PUT", "/plan/direction-weights", weights)
        assert (await request(a, "GET", "/plan/direction-comparison"))["plans"][0][
            "score"
        ] is None
        measurements = [
            {
                "key": key,
                "label": key,
                "value": 60 + i,
                "minimum": 0,
                "maximum": 100,
                "threshold": 50,
                "source": "验收账号本人记录",
                "method": "同一份百分量表",
                "measured_at": datetime.now(timezone.utc).isoformat(),
            }
            for i, key in enumerate(
                [
                    "major",
                    "jobs",
                    "salary",
                    "stability",
                    "location",
                    "opportunity",
                    "feasibility",
                ]
            )
        ]
        batch = {
            "asset_type": "direction_plan",
            "version": dv.version,
            "subject_id": "dir_" + suffix,
            "measurements": measurements,
        }
        await request(a, "POST", "/measurements", batch)
        assert (await request(a, "GET", "/plan/direction-comparison"))["plans"][0][
            "score"
        ] is not None
        rid = "report_" + suffix
        report_model = Report(
            id=rid,
            user_id=account,
            version=1,
            generated_at=datetime.now(timezone.utc),
            verdict=Verdict(title="职业诊断", summary="验收资料"),
            swot=Swot(),
            dimensions=[
                ReportDimensionGroup(
                    group="SELF-PORTRAIT",
                    group_method="能力核验",
                    items=[
                        ReportDimensionItem(
                            index=i,
                            name="维度" + str(i),
                            tag="待验证",
                            conclusion="依据个人资料",
                            evidence="验收账号录入",
                        )
                        for i in range(1, 4)
                    ],
                )
            ],
        )
        rv = await c.asset_service.save_report(account, report_model)
        batch = {
            "asset_type": "report",
            "version": rv.version,
            "subject_id": rid,
            "measurements": [
                {**m, "key": str(i + 1)} for i, m in enumerate(measurements[:3])
            ],
        }
        await request(a, "POST", "/measurements", batch)
        batch["measurements"][0]["value"] = 75
        await request(a, "POST", "/measurements", batch)
        assert (await request(a, "GET", "/measurements"))["history"]
        await request(b, "POST", "/measurements", batch, expected=404)
        for fmt in ["pdf", "docx"]:
            exported = await request(
                a,
                "POST",
                "/assets/export",
                {"asset_type": "action_plan", "format": fmt},
            )
            private["exports"][fmt] = exported["object_key"]
            content = await request(
                a,
                "GET",
                "/assets/download/" + exported["object_key"],
                endpoint="/assets/download/{export_id}",
                binary=True,
            )
            assert (
                content.startswith(b"%PDF-")
                if fmt == "pdf"
                else "项目第二步"
                in ZipFile(BytesIO(content)).read("word/document.xml").decode()
            )
            await request(
                b,
                "GET",
                "/assets/download/" + exported["object_key"],
                expected=404,
                endpoint="/assets/download/{export_id}",
            )
        prefs["material_analysis"] = False
        await request(a, "PUT", "/preferences", prefs)
        response = await a.post("/api/v1/app/brief/today")
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        passed = response.status_code == 200 and any("result" in frame for frame in frames) and not any("error" in frame for frame in frames)
        report["cases"].append({"endpoint": "POST /api/v1/app/brief/today", "http": response.status_code,
            "expected": 200, "passed": passed, "detail": "关闭上传材料来源后，使用其余允许的资料生成简报"})
        assert passed, "restricted analysis failed"
        prefs["material_analysis"] = True
        await request(a, "PUT", "/preferences", prefs)
        boot = await request(a, "GET", "/bootstrap")
        session = await request(
            a, "POST", "/task/enter", {"task_code": boot["task_entries"][0]["code"]}
        )
        sid = session["task_id"]
        private["session"] = sid
        assert (
            await request(
                a,
                "GET",
                "/sessions/" + sid + "/snapshot",
                endpoint="/sessions/{task_id}/snapshot",
            )
            is None
        )
        await request(
            b,
            "GET",
            "/sessions/" + sid + "/snapshot",
            expected=404,
            endpoint="/sessions/{task_id}/snapshot",
        )
        STATE.write_text(json.dumps(private, ensure_ascii=False))
        # The actual configured model, not a stub. A provider failure remains a visible failed case.
        turn = await request(
            a,
            "POST",
            "/conversation/message",
            {
                "task_id": sid,
                "message": "我在河北大学读软件工程大二，想了解后端开发需要准备哪些项目。",
                "client_msg_id": uuid4().hex,
            },
        )
        snap = await request(
            a,
            "GET",
            "/sessions/" + sid + "/snapshot",
            endpoint="/sessions/{task_id}/snapshot",
        )
        assert snap == turn
        private["session_snapshot"] = snap
        STATE.write_text(json.dumps(private, ensure_ascii=False))
        report["model_snapshot_roundtrip"] = True
    finally:
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        for client in clients:
            await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
