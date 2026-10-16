"""四个年级的本地验收账号：真实 HTTP 操作 + 领域服务资产写入。

在现有后端容器中执行，旁放 student-personas.json。必须显式 --write 并提供
STUDENT_SEED_PASSWORD；只创建 student1..4，不覆盖已有账号。状态文件支持续跑。
对话由当前后端生成；报告、方向、计划和时间线是可重复的测试夹具。
"""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from zhiyin_boot.container import build_container
from zhiyin_boot.settings import Settings
from zhiyin_kernel.assets import (
    ActionPhase,
    ActionPlan,
    ActionTask,
    CalendarNode,
    DirectionPlan,
    PlanGap,
    Report,
    ReportDimensionGroup,
    ReportDimensionItem,
    Swot,
    TrackEvent,
    Verdict,
)
from zhiyin_kernel.blackboard import ProfileGap
from zhiyin_kernel.enums import AssetType

HERE = Path(__file__).resolve().parent
PERSONAS = json.loads((HERE / "student-personas.json").read_text(encoding="utf-8"))
ALLOWED = {"student1", "student2", "student3", "student4"}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--state", default="/tmp/student-seed-state.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--phase",
        choices=["all", "base", "chat", "assets", "finalize", "verify"],
        default="all",
    )
    args = parser.parse_args()
    if not args.write or not os.environ.get("STUDENT_SEED_PASSWORD"):
        parser.error("必须指定 --write 并设置 STUDENT_SEED_PASSWORD")
    if args.base_url not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        parser.error("此夹具只允许连接本机后端")
    assert {p["account"] for p in PERSONAS} == ALLOWED
    state_path = Path(args.state)
    state = (
        json.loads(state_path.read_text())
        if state_path.exists()
        else {"accounts": {}, "done": {}}
    )
    c = build_container(Settings.from_env())
    clients = {}

    def persist():
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def once(key, factory):
        if key in state["done"]:
            return state["done"][key]
        result = await factory()
        state["done"][key] = result
        persist()
        return result

    async def req(uid, method, path, **kwargs):
        response = await clients[uid].request(method, "/api/v1/app" + path, **kwargs)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 0:
            raise RuntimeError(f"{uid} {path}: {body.get('message')}")
        return body["data"]

    async def base(p):
        uid, year = p["account"], p["year"]
        fields = {
            "school": "河北大学",
            "major": p["major"],
            "degree_level": "本科",
            "enrollment_status": "在读",
            "duration": "4年",
            "study_mode": "全日制",
            "enrolled_at": f"{2027 - year}-09-01",
            "expected_graduation": f"{2031 - year}-06",
            "interest": p["interest"],
            "skills": p["skills"],
            "experience": p["experience"],
            "values": p["values"],
        }
        for key, value in fields.items():
            await once(
                f"{uid}/profile/{key}",
                lambda k=key, v=value: req(
                    uid, "POST", f"/profile/fields/{k}", json={"value": v}
                ),
            )
        courses = [
            dict(
                name=name,
                weekday=i % 5 + 1,
                start_period=1 + (i // 5) * 4,
                end_period=2 + (i // 5) * 4,
                period=f"{1 + (i // 5) * 4}-{2 + (i // 5) * 4}节",
                weeks="1-16",
                place=f"教学楼{1 + i % 3}-{201 + i * 3}",
                credit=str(2 + i % 3),
                category="专业课" if i < 4 else "公共课",
            )
            for i, name in enumerate(p["courses"])
        ]
        grades = []
        for i, name in enumerate(p["past_courses"]):
            completed_terms = max(1, (year - 1) * 2)
            semester = i * completed_terms // len(p["past_courses"])
            start = 2027 - year + semester // 2
            score = 76 + (i * 7 + year * 3) % 21
            grades.append(
                dict(
                    name=name,
                    term=f"{start}-{start + 1}-{1 + semester % 2}",
                    credit=str(1 + i % 4),
                    score=str(score),
                    point=f"{max(1, (score - 50) / 10):.1f}",
                    kind="必修",
                )
            )
        await once(
            f"{uid}/academic-v2",
            lambda: req(
                uid,
                "POST",
                "/academic/import",
                json={
                    "courses": json.dumps(courses, ensure_ascii=False),
                    "grades": json.dumps(grades, ensure_ascii=False),
                    "school": "河北大学",
                    "term": "2026-2027-1",
                },
            ),
        )
        notes = [(text, "todo") for phase in p["phases"] for text in phase[1]]
        notes += [(text, "goal") for text in p["goals"]]
        for i, (text, kind) in enumerate(notes):
            note = await once(
                f"{uid}/note/{i}",
                lambda t=text, k=kind: req(
                    uid, "POST", "/notes", json={"text": t, "kind": k}
                ),
            )
            if i < year + 3:
                await once(
                    f"{uid}/note-done/{i}",
                    lambda n=note: req(
                        uid, "PATCH", f"/notes/{n['id']}", json={"done": True}
                    ),
                )
        print(uid, "基础资料、课表成绩、28条待办目标已写入", flush=True)

    async def chat(p):
        uid = p["account"]
        tasks = [
            (
                "confused",
                "想梳理自己的优势和短板",
                p["projects"][0],
                p["reflections"][0],
            ),
            (
                "verify_direction",
                f"想验证{p['roles'][0]}是否适合自己",
                p["projects"][1],
                p["reflections"][1],
            ),
            (
                "undecided",
                f"想比较{p['roles'][0]}与{p['roles'][1]}",
                p["projects"][2],
                p["reflections"][2],
            ),
            (
                "how_to_act",
                "想把近期目标变成能执行的周计划",
                p["target"],
                p["constraint"],
            ),
            ("stuck", "想复盘最近的卡点并调整节奏", p["reflections"][3], p["next"]),
        ]
        for code, intent, experience, reflection in tasks:
            entered = await once(
                f"{uid}/session/{code}",
                lambda: req(uid, "POST", "/task/enter", json={"task_code": code}),
            )
            task_id = entered["task_id"]
            content = (
                f"{p['name']}的学习与项目记录\n河北大学，{p['major']}，大{p['year']}\n"
                + "\n".join(p["projects"] + p["reflections"])
            )
            material = await once(
                f"{uid}/material/{code}",
                lambda: req(
                    uid,
                    "POST",
                    "/conversation/material",
                    files={"file": (f"{intent}.txt", content.encode(), "text/plain")},
                ),
            )
            messages = [
                f"我是{p['name']}，河北大学{p['major']}大{p['year']}在读。{intent}。{p['experience']}。{p['values']}。{p['constraint']}。请结合我上传的记录来分析，不用再次询问已经说明的基本信息。",
                f"再补充一个具体情况：{experience}。目前我最希望{p['target']}，但{p['risk']}。希望你把已有依据和还需要验证的部分区分开。",
                f"我的补充想法是：{reflection}。我愿意先做“{p['next']}”。请给我一个这周能完成的小步骤和完成标准，暂时不扩大范围。",
            ]
            for i, message in enumerate(messages):
                key = f"{uid}/message/{code}/{i}"

                async def send(text=message, idx=i, id_key=key):
                    data = await req(
                        uid,
                        "POST",
                        "/conversation/message",
                        json={
                            "task_id": task_id,
                            "message": text,
                            "client_msg_id": str(
                                uuid5(
                                    NAMESPACE_URL, "student-fixtures-20261016/" + id_key
                                )
                            ),
                            "material_ids": [material["material_id"]]
                            if idx == 0
                            else [],
                        },
                    )
                    if not data.get("messages"):
                        raise RuntimeError(f"{id_key}: 后端没有返回消息")
                    return {"stage": data["stage"], "messages": len(data["messages"])}

                await once(key, send)
                print(uid, code, f"咨询{i + 1}/3完成", flush=True)

    async def assets(p):
        uid = p["account"]
        now = datetime.now(timezone(timedelta(hours=8)))
        due_anchor = now.replace(hour=20, minute=0, second=0, microsecond=0)
        deps = [
            "major",
            "interest",
            "skills",
            "experience",
            "values",
            "courses",
            "scores",
        ]

        async def save_gap():
            await c.profile_service.replace_gaps(
                uid,
                [
                    ProfileGap(
                        key="experience",
                        label="下一步验证",
                        reason=p["gap"],
                        suggested_next_action=p["next"],
                    )
                ],
            )

        await once(f"{uid}/gaps", save_gap)
        # 正文通过资产服务写入，版本与正文一致；不写假 AI 对话。
        facts = [
            ("兴趣倾向", p["interest"], p["projects"][0]),
            ("能力基础", p["skills"], "已导入课程与成绩记录，结合本人能力自评"),
            ("价值排序", p["values"], "个人目标与咨询中的选择偏好"),
            ("经历积累", p["experience"], p["projects"][1]),
            (
                "学习方式",
                "适合用小项目验证理解，再通过复盘补齐知识",
                p["reflections"][1],
            ),
            ("时间资源", p["constraint"], "本学期课表与个人时间安排"),
            ("主要方向", p["roles"][0], p["target"]),
            ("并行选项", p["roles"][1], "保留另一条路径，通过体验比较投入与反馈"),
            ("可迁移能力", "将已有课程训练转化为可展示的任务成果", p["projects"][2]),
            ("证据完整度", p["gap"], "目前的作品与经历仍有待补充的环节"),
            ("近期验证", p["next"], "以产出与反馈衡量进展，不凭主观匹配分数下结论"),
            ("执行风险", p["risk"], p["reflections"][3]),
            ("选择成本", "先做低成本验证，每周复盘是否继续投入", p["constraint"]),
            ("支持资源", "利用同伴反馈、学院活动和导师交流", p["projects"][1]),
            (
                "调整条件",
                "连续两周无法推进时，缩小任务并重新安排时间",
                p["reflections"][0],
            ),
        ]
        for version in (1, 2):

            async def save_report(v=version):
                groups = []
                for name, start, end, method in [
                    ("SELF-PORTRAIT", 0, 6, "依据自述、课程和项目记录梳理个人条件"),
                    (
                        "JOB-MARKET",
                        6,
                        11,
                        "将可选方向与现有能力逐项比较，外部岗位条件仍需核实",
                    ),
                    (
                        "DECISION-RISK",
                        11,
                        15,
                        "结合时间预算、约束与复盘记录设置验证节点",
                    ),
                ]:
                    groups.append(
                        ReportDimensionGroup(
                            group=name,
                            group_method=method,
                            items=[
                                ReportDimensionItem(
                                    index=i + 1,
                                    name=facts[i][0],
                                    tag="待验证" if i in (9, 10, 11) else "已有依据",
                                    conclusion=facts[i][1],
                                    evidence=facts[i][2],
                                )
                                for i in range(start, end)
                            ],
                        )
                    )
                report = Report(
                    id=f"{uid}-report-{v}",
                    user_id=uid,
                    version=v,
                    generated_at=now,
                    verdict=Verdict(
                        title=f"{p['name']}的阶段方向梳理",
                        summary=(
                            p["target"]
                            if v == 1
                            else f"以{p['roles'][0]}为近期重点。{p['next']}，完成后根据反馈调整。"
                        ),
                    ),
                    swot=Swot(
                        strength=[p["skills"], p["experience"]],
                        weakness=[p["gap"]],
                        opportunity=[
                            f"利用本学期课程推进{p['target']}",
                            "通过同伴与导师反馈验证选择",
                        ],
                        risk=[p["risk"], p["constraint"]],
                    ),
                    dimensions=groups,
                    sources=[
                        "本人填写的画像",
                        "导入的课程与成绩",
                        "项目记录与阶段复盘",
                    ],
                    methodologies=["个人条件梳理", "方向对比", "短周期行动验证"],
                )
                result = await c.asset_service.save_report(
                    uid,
                    report,
                    depends_on_profile_keys=deps,
                    diff_from_previous="形成阶段基线"
                    if v == 1
                    else "补充项目依据，并明确下一步验证动作",
                )
                return result.version

            await once(f"{uid}/fixture-report/{version}", save_report)

        async def save_directions():
            plans = [
                DirectionPlan(
                    id=f"{uid}-direction-{i}",
                    report_id=f"{uid}-report-2",
                    role=role,
                    name=name,
                    target_desc=p["target"]
                    if i == 0
                    else f"通过一次具体体验评估{name}的投入与反馈",
                    gaps=[
                        PlanGap(
                            requirement=p["gap"],
                            current_state=p["experience"],
                            suggestion=p["next"],
                        )
                    ],
                    fit_reason=p["interest"] if i == 0 else p["skills"],
                    main_risk=p["risk"] if i == 0 else "与主线争用时间，需要控制投入",
                )
                for i, (name, role) in enumerate(
                    zip(p["roles"], ["main", "parallel", "fallback"])
                )
            ]
            result = await c.asset_service.save_direction_plans(
                uid,
                plans,
                depends_on_profile_keys=deps,
                diff_from_previous="按主攻、并行与保底整理三条路径",
            )
            return result.version

        await once(f"{uid}/fixture-directions", save_directions)

        async def save_plan():
            phases = []
            for pi, (name, texts) in enumerate(p["phases"]):
                tasks = [
                    ActionTask(
                        id=f"{uid}-task-{pi * 6 + ti}",
                        text=text,
                        due_date=due_anchor
                        + timedelta(
                            days=(0 if ti == 4 else -1)
                            if pi == 0 and ti in (4, 5)
                            else pi * 14 + ti * 2 - 7
                        ),
                    )
                    for ti, text in enumerate(texts)
                ]
                phases.append(
                    ActionPhase(
                        name=name,
                        date_range=f"{(now + timedelta(days=pi * 14 - 7)):%m.%d}—{(now + timedelta(days=pi * 14 + 6)):%m.%d}",
                        tag="本周" if pi == 0 else "后续",
                        tasks=tasks,
                    )
                )
            result = await c.asset_service.save_action_plan(
                uid,
                ActionPlan(
                    id=f"{uid}-action",
                    plan_id=f"{uid}-direction-0",
                    phases=phases,
                    reminders_synced=True,
                ),
                depends_on_profile_keys=deps,
                diff_from_previous="按课程空档拆分为四阶段、24个可执行任务",
            )
            return result.version

        await once(f"{uid}/fixture-action", save_plan)
        await once(
            f"{uid}/select-direction",
            lambda: req(uid, "POST", f"/plan/directions/{uid}-direction-0/select"),
        )
        for i in range(p["year"] + 3):
            await once(
                f"{uid}/action-done/{i}",
                lambda idx=i: req(
                    uid,
                    "PATCH",
                    "/plan/action/tasks",
                    json={"task_id": f"{uid}-task-{idx}", "done": True},
                ),
            )

        async def calendar():
            # 与行动计划使用同一任务和截止时间，避免日历里出现另一套安排。
            plan = await c.asset_service.get_action_plan(uid)
            for phase in plan.phases:
                for task in phase.tasks:
                    await c.function_service.write_calendar_node(
                        uid,
                        CalendarNode(
                            node_id=f"calendar-{task.id}",
                            user_id=uid,
                            title=task.text,
                            due_at=task.due_date,
                            source="planner",
                            related_task_text=task.text,
                        ),
                    )
            return sum(len(p.tasks) for p in plan.phases)

        await once(f"{uid}/calendar", calendar)
        for i, text in enumerate(
            [*p["projects"], *p["reflections"], *p["goals"], p["next"]]
        ):

            async def timeline(idx=i, detail=text):
                kind = (
                    "milestone_done"
                    if idx < 3
                    else "semester_review"
                    if idx < 7
                    else "coach_message"
                )
                await c.track_events.append_event(
                    uid,
                    TrackEvent(
                        id=f"{uid}-timeline-{idx}",
                        user_id=uid,
                        type=kind,
                        title=["项目进展记录", "阶段复盘", "下一阶段安排"][
                            0 if idx < 3 else 1 if idx < 7 else 2
                        ],
                        detail=detail,
                        occurred_at=now - timedelta(days=24 - idx * 2),
                    ),
                )

            await once(f"{uid}/timeline/{i}", timeline)
        for i, (title, body) in enumerate(
            [
                ("本周计划已整理", p["phases"][1][1][0]),
                ("下一步验证", p["next"]),
                ("阶段复盘提醒", p["reflections"][-1]),
                ("方向选择已记录", f"目前优先推进{p['roles'][0]}"),
                ("课程与项目安排", p["constraint"]),
                ("资料整理提醒", p["gap"]),
            ]
        ):

            async def notice(t=title, b=body):
                return (await c.notifier.push(uid, title=t, body=b)).message_id

            mid = await once(f"{uid}/notification/{i}", notice)
            if i < 3:
                await once(
                    f"{uid}/notification-read/{i}",
                    lambda m=mid: req(uid, "POST", f"/notifications/{m}/read"),
                )
        await c.facade._invalidate_user(uid, "asset_state_changed")
        print(uid, "报告版本、方向、行动计划、日历、复盘和通知已写入", flush=True)

    async def finalize(p):
        """导入事件处理完后，再按当前资料保存可直接验收的最终资产。"""
        uid = p["account"]
        latest = [
            await c.asset_service.get_latest_version(uid, t)
            for t in (AssetType.REPORT, AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN)
        ]
        if not any(v and v.needs_recompute for v in latest):
            return
        report = await c.asset_service.get_report(uid)
        profile = await c.profile_service.get(uid)
        fields = {f.key: f.value for f in profile.fields}
        assert fields["major"] == p["major"] and fields["school"] == "河北大学"
        report = report.model_copy(
            update={
                "id": f"{uid}-report-final-{report.version + 1}",
                "generated_at": datetime.now(timezone.utc),
                "verdict": report.verdict.model_copy(
                    update={
                        "summary": f"以{p['roles'][0]}为近期重点。{p['next']}。已核对本学期课程和阶段安排。"
                    }
                ),
            }
        )
        deps = [
            "major",
            "interest",
            "skills",
            "experience",
            "values",
            "courses",
            "scores",
        ]
        await c.asset_service.save_report(
            uid,
            report,
            depends_on_profile_keys=deps,
            diff_from_previous="导入事件处理后复核课程、个人条件与近期行动",
        )
        plans = await c.asset_service.list_direction_plans(uid)
        await c.asset_service.save_direction_plans(
            uid,
            [plan.model_copy(update={"report_id": report.id}) for plan in plans],
            depends_on_profile_keys=deps,
            diff_from_previous="依据复核后的报告确认三条方向，保留选择",
        )
        plan = await c.asset_service.get_action_plan(uid)
        phases = [phase.model_copy(update={"tag": phase.name}) for phase in plan.phases]
        await c.asset_service.save_action_plan(
            uid,
            plan.model_copy(update={"phases": phases}),
            depends_on_profile_keys=deps,
            diff_from_previous="核对课程与阶段标签，保留已完成任务和截止日期",
        )
        await c.facade._invalidate_user(uid, "asset_state_changed")
        print(uid, "最终资产已复核，保留全部完成状态", flush=True)

    async def verify(p):
        uid = p["account"]
        data = {}
        for key, path in {
            "bootstrap": "/bootstrap",
            "workspace": "/workspace",
            "sessions": "/sessions",
            "notes": "/notes",
            "report": "/report/full-text",
            "directions": "/plan/directions",
            "action": "/plan/action",
            "calendar": "/calendar",
            "timeline": "/track/events",
            "notifications": "/notifications/pending",
            "achievements": "/achievements",
            "report_versions": "/assets/report/versions",
            "direction_versions": "/assets/direction_plan/versions",
            "action_versions": "/assets/action_plan/versions",
        }.items():
            data[key] = await req(uid, "GET", path)
        counts = {
            "account": uid,
            "name": p["name"],
            "year": p["year"],
            "major": p["major"],
            "http_reads": len(data),
        }
        counts["notes"] = len(data["notes"])
        counts["calendar"] = len(data["calendar"])
        counts["timeline"] = len(data["timeline"])
        counts["notifications"] = len(data["notifications"])
        counts["sessions"] = len(data["sessions"]["sessions"])
        turns = []
        for session in data["sessions"]["sessions"]:
            turns.append(await req(uid, "GET", f"/sessions/{session['task_id']}/turns"))
        counts["user_messages"] = sum(m["role"] == "user" for t in turns for m in t)
        counts["assistant_messages"] = sum(
            m["role"] == "agent" for t in turns for m in t
        )
        academic = data["workspace"]["academic_panel"]
        counts["courses"] = len(academic["courses"])
        counts["grades"] = len(academic["grades"])
        counts["directions"] = len(data["directions"]["plans"])
        tasks = [task for phase in data["action"]["phases"] for task in phase["tasks"]]
        counts["action_tasks"] = len(tasks)
        counts["completed_tasks"] = sum(task["done"] for task in tasks)
        counts["completed_notes"] = sum(note["done"] for note in data["notes"])
        counts["report_dimensions"] = sum(
            len(s["items"]) for s in data["report"]["sections"]
        )
        counts["report_versions"] = len(data["report_versions"])
        counts["latest_assets_fresh"] = all(
            not max(data[key], key=lambda v: v["version"])["needs_recompute"]
            for key in ("report_versions", "direction_versions", "action_versions")
        )
        assert counts["latest_assets_fresh"], (
            "画像更新影响尚未处理完成，请稍后执行 finalize 再 verify"
        )
        counts["behavior_records"] = len(
            await c.behavior_service.recent(uid, limit=500)
        )
        counts["unlocked_achievements"] = data["achievements"]["unlocked"]
        assert data["bootstrap"]["identity"]["nickname"] == p["name"]
        assert data["bootstrap"]["identity"]["role"] == "student"
        assert counts["sessions"] >= 5 and counts["user_messages"] >= 15
        assert counts["assistant_messages"] >= 15
        assert counts["notes"] == 28 and counts["completed_notes"] == p["year"] + 3
        assert counts["courses"] == len(p["courses"])
        assert all(
            course["weekday"] > 0 and course["start_period"] > 0
            for course in academic["courses"]
        )
        assert counts["grades"] == len(p["past_courses"])
        assert counts["directions"] == 3
        assert data["directions"]["selected_id"] == f"{uid}-direction-0"
        assert (
            counts["action_tasks"] == 24 and counts["completed_tasks"] == p["year"] + 3
        )
        assert counts["calendar"] >= 24 and counts["timeline"] >= 12
        assert counts["report_dimensions"] == 15 and counts["report_versions"] >= 2
        assert all(task["task_id"].startswith(uid + "-task-") for task in tasks)
        assert any(not task["done"] for task in tasks)
        assert any(not note["done"] for note in data["notes"])
        for version in (1, 2):
            report_version = state["done"][f"{uid}/fixture-report/{version}"]
            old = await req(
                uid, "GET", "/report/full-text", params={"version": report_version}
            )
            assert sum(len(s["items"]) for s in old["sections"]) == 15
        # 用另一个账号的会话 ID 读取，必须拒绝或者返回空列表。
        other = "student1" if uid != "student1" else "student2"
        other_task = state["done"][f"{other}/session/confused"]["task_id"]
        cross = await clients[uid].get(f"/api/v1/app/sessions/{other_task}/turns")
        cross_data = cross.json()
        assert (
            cross.status_code in (403, 404)
            or cross_data.get("code") != 0
            or cross_data.get("data") == []
        )
        counts["cross_account_isolation"] = True
        counts["http_reads"] += len(turns) + 3
        counts["verified_at"] = datetime.now(timezone.utc).isoformat()
        counts["conversation_payloads"] = turns
        counts["readback"] = data
        state.setdefault("verification", {})[uid] = counts
        persist()
        print(
            uid,
            "所有页面读取成功",
            {
                k: v
                for k, v in counts.items()
                if k not in {"readback", "conversation_payloads"}
            },
            flush=True,
        )

    try:
        # 遇到同名的既有用户就停止，不重置密码、不接管资料。
        for p in PERSONAS:
            uid = p["account"]
            exists = await c.users.get_by_id(uid)
            if exists and uid not in state["accounts"]:
                raise RuntimeError(f"已有账号 {uid} 不属于本次状态清单，停止写入")
        for p in PERSONAS:
            uid = p["account"]
            if uid not in state["accounts"]:
                await c.identity_service.register(
                    uid, os.environ["STUDENT_SEED_PASSWORD"], p["name"]
                )
                state["accounts"][uid] = {
                    "name": p["name"],
                    "year": p["year"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                persist()
            client = httpx.AsyncClient(base_url=args.base_url, timeout=300)
            clients[uid] = client
            login = await req(
                uid,
                "POST",
                "/auth/login",
                json={"account": uid, "password": os.environ["STUDENT_SEED_PASSWORD"]},
            )
            client.headers["Authorization"] = "Bearer " + login["token"]
        for phase, fn in [
            ("base", base),
            ("chat", chat),
            ("assets", assets),
            ("finalize", finalize),
            ("verify", verify),
        ]:
            if args.phase not in {"all", phase}:
                continue
            # 各账号顺序推进；不同账号的咨询可并行，避免相互覆盖会话状态。
            results = await asyncio.gather(
                *(fn(p) for p in PERSONAS), return_exceptions=True
            )
            errors = [
                f"{p['account']}: {type(r).__name__}: {r}"
                for p, r in zip(PERSONAS, results)
                if isinstance(r, Exception)
            ]
            if errors:
                raise RuntimeError("; ".join(errors))
    finally:
        for uid, client in clients.items():
            try:
                await req(uid, "POST", "/auth/logout")
            finally:
                await client.aclose()
        for obj in reversed(c.extra.get("closables", [])):
            close = getattr(obj, "aclose", None)
            if close:
                await close()


if __name__ == "__main__":
    asyncio.run(main())
