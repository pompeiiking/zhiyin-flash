"""真实服务上的九项页面 AI 任务冒烟测试；只输出结构与状态，不记录令牌或原文。"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api/v1"


def call(path: str, *, body: dict | None = None, token: str = "") -> tuple[int, str]:
    request = urllib.request.Request(
        API + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method="GET" if body is None else "POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def terminal(raw: str) -> dict:
    for line in reversed(raw.splitlines()):
        if line.startswith("data: "):
            frame = json.loads(line[6:])
            if "result" in frame or "error" in frame:
                return frame
    return {}


def main() -> int:
    account = "ai-audit-" + uuid.uuid4().hex[:10]
    status, raw = call(
        "/app/auth/register", body={"account": account, "password": "audit-pass-123456"}
    )
    token = (json.loads(raw).get("data") or {}).get("token") if status == 200 else None
    if not token:
        print("注册失败", status)
        return 1
    status, _ = call(
        "/app/academic/import",
        token=token,
        body={
            "courses": "课程名称\t星期\t节次\t地点\t教师\n数据分析\t周一\t1-2节\tA101\t王老师",
            "grades": "",
            "term": "2026 秋",
        },
    )
    if status != 200:
        print("学业导入失败", status)
        return 1
    status, raw = call("/app/task/enter", token=token, body={"task_code": "confused"})
    task_id = (json.loads(raw).get("data") or {}).get("task_id") if status == 200 else None
    if not task_id:
        print("进入采集失败", status)
        return 1
    status, _ = call(
        "/app/conversation/message",
        token=token,
        body={
            "task_id": task_id,
            "message": "我大三，学过数据分析，想找实习但还没想清岗位方向。",
        },
    )
    if status != 200:
        print("采集对话失败", status)
        return 1
    status, raw = call("/app/workspace", token=token)
    workspace = json.loads(raw).get("data") or {} if status == 200 else {}
    gaps = (workspace.get("profile_panel") or {}).get("gaps") or []
    gap_key = gaps[0].get("key") if gaps else "experience"
    cases = [
        ("brief.today", "/app/brief/today", {}),
        ("dim", "/app/dimensions/courses", {}),
        ("portrait.analysis", "/app/portrait/analysis", {}),
        ("day.advice", f"/app/day/{date.today().isoformat()}/advice", {"arg": "480"}),
        ("gap", f"/app/gaps/{gap_key}/clarify", {}),
        ("report.summary", "/app/report/summary", {}),
        ("plan.timetable", "/app/plan/timetable", {}),
        ("plan.todos", "/app/plan/todos/suggestions", {}),
        ("match.careers", "/app/match/careers", {}),
    ]
    passed = 0
    for name, path, body in cases:
        status, raw = call(path, body=body, token=token)
        frame = terminal(raw) if status == 200 else {}
        result = frame.get("result") or {}
        error = frame.get("error") or {}
        ok = status == 200 and bool(result) and not error
        passed += ok
        print(
            f"{'PASS' if ok else 'FAIL'} {name} HTTP={status} "
            f"data={type(result.get('data')).__name__} "
            f"error_code={error.get('code', '-')}",
            flush=True,
        )
    print(f"九项任务：{passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
