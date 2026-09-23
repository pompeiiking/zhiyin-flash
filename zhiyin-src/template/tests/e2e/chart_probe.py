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

    for line in OPENING:
        data = (
            call("/app/conversation/message", "POST", {"task_id": task_id, "message": line}, token).get(
                "data"
            )
            or {}
        )
        print(f"【他】{line}")
        print(f"【主理】{((data.get('messages') or [{}])[0]).get('text') or ''}")
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
    chart = message.get("chart")
    renderables = message.get("renderables") or []
    checks: list[tuple[str, bool, str]] = []
    checks.append(("主理自己画了一张图（没人告诉它调哪个工具）", bool(chart), str(chart)[:80]))
    checks.append(
        (
            "同时出现在可视件列表里（前端按 kind 分发；chart 是兼容字段）",
            any(item.get("kind") == "bars_chart" for item in renderables),
            str([item.get("kind") for item in renderables]),
        )
    )
    points = (chart or {}).get("points") or []
    checks.append(("图至少有两个点", len(points) >= 2, f"{len(points)} 个点"))
    if points:
        pairs = {
            str(point.get("label")): round(float(point.get("value")))
            for point in points
        }
        checks.append(
            (
                "图上的值与画像里的原值逐项相等（不是编的）",
                all(expected.get(label) == value for label, value in pairs.items()),
                f"图={pairs} / 库={expected}",
            )
        )
    checks.append(("标题是用户看得懂的话", bool((chart or {}).get("title")), str((chart or {}).get("title"))))

    print("===== 结果 =====")
    for name, ok, detail in checks:
        print(("  [PASS] " if ok else "  [FAIL] ") + name + f" — {detail}")
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
