"""真实栈非模型接口巡检：身份、读写、空态、越权和学业文件。"""

from __future__ import annotations

import sys
import uuid

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/v1"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail[:120]))
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail[:120]}", flush=True)


def request(client: httpx.Client, method: str, path: str, **kwargs) -> tuple[int, dict]:
    response = client.request(method, API + path, timeout=45, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return response.status_code, payload


def ok(response: tuple[int, dict]) -> bool:
    return response[0] == 200 and response[1].get("code") == 0


def main() -> int:
    with httpx.Client() as client:
        # /healthz 位于 API 前缀外，单独读取。
        health_response = client.get(BASE + "/healthz", timeout=15)
        health = health_response.json()
        check("健康检查", health_response.status_code == 200 and health.get("status") == "ok")
        spec_response = client.get(API + "/openapi.json", timeout=15)
        spec = spec_response.json()
        check("同版接口契约", len(spec.get("paths", {})) == 44)

        account = "surface-" + uuid.uuid4().hex[:10]
        password = "surface-pass-123456"
        register = request(
            client, "POST", "/app/auth/register", json={"account": account, "password": password}
        )
        token = (register[1].get("data") or {}).get("token")
        check("注册", ok(register) and bool(token))
        if not token:
            return 1
        client.headers["Authorization"] = f"Bearer {token}"
        check("登录", ok(request(
            client, "POST", "/app/auth/login", json={"account": account, "password": password}
        )))
        check("门户", ok(request(client, "GET", "/app/portal")))
        check("启动数据", ok(request(client, "GET", "/app/bootstrap")))
        check("动态配置重载", ok(request(client, "POST", "/app/config/reload", json={})))
        check("工作台空态", ok(request(client, "GET", "/app/workspace")))
        check("会话空态", ok(request(client, "GET", "/app/sessions")))

        note = request(client, "POST", "/app/notes", json={"text": "整理实习经历", "kind": "todo"})
        note_id = (note[1].get("data") or {}).get("id")
        check("笔记新增", ok(note) and bool(note_id))
        check("笔记读取", ok(request(client, "GET", "/app/notes")))
        if note_id:
            check("笔记勾选", ok(request(
                client, "PATCH", f"/app/notes/{note_id}", json={"done": True}
            )))
            check("笔记删除", ok(request(client, "DELETE", f"/app/notes/{note_id}")))

        event_id = "audit-" + uuid.uuid4().hex[:12]
        event = {"event": "home_chat_open", "client_event_id": event_id, "payload": {}}
        first = request(client, "POST", "/app/track", json=event)
        second = request(client, "POST", "/app/track", json=event)
        check("行为事件写入", ok(first))
        check("行为事件重放", ok(second))
        check("行为时间线读取", ok(request(client, "GET", "/app/track/events")))
        check("成就读取", ok(request(client, "GET", "/app/achievements")))
        check("通知读取", ok(request(client, "GET", "/app/notifications/pending")))
        missing_notice = request(client, "POST", "/app/notifications/missing/read", json={})
        check(
            "不存在的通知回执为零",
            ok(missing_notice) and (missing_notice[1].get("data") or {}).get("read") == 0,
        )

        check("情报读取", ok(request(client, "GET", "/app/intel")))
        check("理论卡读取", ok(request(client, "GET", "/app/theory-cards/holland_riasec")))
        check("方向方案空态", ok(request(client, "GET", "/app/plan/directions")))
        check("行动计划空态", ok(request(client, "GET", "/app/plan/action")))
        check("日历空态", ok(request(client, "GET", "/app/calendar")))
        check("报告空态", ok(request(client, "GET", "/app/report/full-text")))
        check("资产版本空态", ok(request(client, "GET", "/app/assets/report/versions")))
        export = request(client, "POST", "/app/assets/export", json={"asset_type": "report"})
        check(
            "未开放的导出如实回告",
            ok(export) and (export[1].get("data") or {}).get("available") is False,
        )
        material = request(
            client, "POST", "/app/conversation/material",
            files={"file": ("notes.txt", b"My internship notes", "text/plain")},
        )
        check("对话材料上传", ok(material))
        invalid_material = request(client, "POST", "/app/conversation/material", data={})
        check("缺文件的材料请求被拒绝", invalid_material[0] == 422)
        academic_text = request(
            client, "POST", "/app/academic/import",
            json={"courses": "课程名称\t星期\t节次\n数据分析\t周一\t1-2节", "term": "2026 秋"},
        )
        check("学业文本导入", ok(academic_text))

        course = (
            "课程名称\t星期\t节次\t地点\t教师\n"
            "数据分析\t周一\t1-2节\tA101\t王老师\n"
        ).encode("utf-8")
        imported = request(
            client, "POST", "/app/academic/import/file",
            files={"courses_file": ("courses.tsv", course, "text/tab-separated-values")},
            data={"term": "2026 秋"},
        )
        check("学业文件导入", ok(imported))
        check("学业删除", ok(request(client, "DELETE", "/app/academic")))

        task_id = ""
        for task_code in (
            "confused", "verify_direction", "undecided", "how_to_act",
            "stuck", "review_due", "free_chat",
        ):
            entered = request(client, "POST", "/app/task/enter", json={"task_code": task_code})
            current_id = (entered[1].get("data") or {}).get("task_id")
            check(f"任务入口 {task_code}", ok(entered) and bool(current_id))
            task_id = task_id or current_id or ""
        invalid_entry = request(client, "POST", "/app/task/enter", json={"task_code": "missing"})
        check("未知任务入口被拒绝", not ok(invalid_entry))
        if task_id:
            check("会话历史读取", ok(request(client, "GET", f"/app/sessions/{task_id}/turns")))
        logout = request(client, "POST", "/app/auth/logout", json={})
        check("登出", ok(logout))
        denied = request(client, "GET", "/app/workspace")
        check("登出后令牌失效", denied[0] == 401)

    passed = sum(success for _, success, _ in results)
    print(f"非模型接口巡检：{passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
