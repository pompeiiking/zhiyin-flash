"""端到端：让主理**自己决定**给用户画张图，并核对图上的数字确实来自库里。

这是"接入 + 校验 + 防假数据"三件事的合体验收：

  1. 先聊两轮，让画像里有两项以上的真实把握度；
  2. 然后直接问"能不能给我画个图看看"——**不告诉它调哪个工具**，看它自己怎么接；
  3. 核对回包里的图：点位数、标签、数值是否与 `/app/workspace` 里那份画像对得上。

第 3 步是重点。图能画出来只说明接通了；**数值与库里的原值逐项相等**才说明它不是编的。

跑法：

    python zhiyin-src/template/tests/e2e/chart_probe.py [base_url]
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"

OPENING = [
    "我是计算机专业的大三学生，正在准备找实习。",
    "我做过一个推荐系统的课设，还写过一个数据可视化的大屏。",
    "我现在想看看自己各项情况到底清楚了没有。",
]


def call(path: str, method: str = "GET", body: dict | None = None, token: str = "") -> dict:
    request = urllib.request.Request(
        API + path,
        method=method,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"code": exc.code, "message": exc.read().decode()[:200]}


def main() -> int:
    account = f"chart-{uuid.uuid4().hex[:8]}"
    token = (
        call("/app/auth/register", "POST", {"account": account, "password": "pass-123456"}).get(
            "data"
        )
        or {}
    ).get("token") or ""
    if not token:
        print("注册失败")
        return 1
    task_id = (
        call("/app/task/enter", "POST", {"task_code": "free_chat"}, token).get("data") or {}
    ).get("task_id") or ""
    print(f"账号 {account} · 会话 {task_id}\n")

    premature_charts = []
    profile_contradictions = []
    for line in OPENING:
        known_before = (
            ((call("/app/workspace", token=token).get("data") or {}).get("profile_panel") or {})
            .get("fields") or []
        )
        data = (
            call("/app/conversation/message", "POST", {"task_id": task_id, "message": line}, token).get(
                "data"
            )
            or {}
        )
        print(f"【他】{line}")
        reply = str(((data.get("messages") or [{}])[0]).get("text") or "")
        print(f"【主理】{reply}")
        if known_before and re.search(r"没拿到.{0,3}画像|没有.{0,3}画像|画像.{0,5}空白", reply):
            profile_contradictions.append(reply)
        if "数据可视化的大屏" in line:
            message = (data.get("messages") or [{}])[0]
            premature_charts = [
                item for item in message.get("renderables") or []
                if item.get("kind") == "bars_chart"
            ]
        print()

    # 画像里现在有几项真实把握度（图上的数字必须与它逐项相等）
    fields = (
        (call("/app/workspace", token=token).get("data") or {}).get("profile_panel") or {}
    ).get("fields") or []
    expected = {
        str(item.get("label") or item.get("key")): round(float(item.get("confidence") or 0) * 100)
        for item in fields
        if item.get("confidence") is not None
    }
    print(f"库里这份画像（{len(expected)} 项）：{expected}\n")

    asked = "能不能给我画个图，让我看看现在各项情况把握得怎么样？"
    data = (
        call("/app/conversation/message", "POST", {"task_id": task_id, "message": asked}, token).get(
            "data"
        )
        or {}
    )
    print(f"【他】{asked}")
    print(f"【主理】{((data.get('messages') or [{}])[0]).get('text') or ''}\n")

    message = (data.get("messages") or [{}])[0]
    renderables = message.get("renderables") or []
    chart = next(
        (item for item in renderables if item.get("kind") == "bars_chart"), None
    )
    checks: list[tuple[str, bool, str]] = []
    checks.append(("已有画像时不说没有画像", not profile_contradictions, str(profile_contradictions)))
    checks.append(("项目名称不会误触发画图", not premature_charts, str(premature_charts)))
    checks.append(
        ("主理自己画了一张图（没人告诉它调哪个工具）", bool(chart), str([item.get("kind") for item in renderables]))
    )
    checks.append(
        (
            "这张图就是可视件本身（前端按 kind 分发，没有第二条通道）",
            all(set(item) <= {"kind", "title", "payload", "source_refs"} for item in renderables),
            str(sorted({key for item in renderables for key in item})),
        )
    )
    points = ((chart or {}).get("payload") or {}).get("points") or []
    checks.append(("图至少有两个点", len(points) >= 2, f"{len(points)} 个点"))
    if points:
        pairs = {
            str(point.get("label")): round(float(point.get("value")) * 100)
            for point in points
        }
        checks.append(
            (
                "图上的值与画像里的原值逐项相等（不是编的）",
                all(expected.get(label) == value for label, value in pairs.items()),
                f"图={pairs} / 库={expected}",
            )
        )
        reply = str(message.get("text") or "")
        checks.append(
            (
                "图表回复只概述已存图点",
                reply.startswith("图表已生成，展示已存记录中的")
                and all(label in reply for label in list(pairs)[:4]),
                reply,
            )
        )
    checks.append(("标题是用户看得懂的话", bool((chart or {}).get("title")), str((chart or {}).get("title"))))

    print("===== 结果 =====")
    for name, ok, detail in checks:
        print(("  [PASS] " if ok else "  [FAIL] ") + name + f" — {detail}")
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
