"""语气探针：把主理每一轮说给用户的那句话原样打出来，人肉比语气。

对话质量没有机械判据，所以这支脚本不判"像不像人"，只做一件事：用同一组固定话术
跑几轮，把每轮的 `conclusion`（气泡里那句）与 `guide.text`（下一步那行）原样打出来，
让改前改后能并排看。

跑法（默认打本机 8000）：

    python zhiyin-src/template/tests/e2e/voice_probe.py [base_url]

它只新建一个一次性账号，不动任何已有数据；产物是一段可直接贴进对话记录的文本。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE}/api/v1"

#: 一组"真人会怎么说"的话：有情绪、有矛盾、有半截话 —— 电报体最容易在这里露馅。
SCRIPT = [
    "我投了二十多份简历，一个回音都没有，是不是我这个人有问题。",
    "我学的是计算机，大三。其实我更喜欢跟人打交道，但不知道这算不算优势。",
    "家里想让我考公，我自己想去互联网，一想到这个就睡不着。",
    "那你说我先做点什么？我没底，怕又白忙一场。",
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
    account = f"voice-{uuid.uuid4().hex[:8]}"
    registered = call(
        "/app/auth/register", "POST", {"account": account, "password": "pass-123456"}
    )
    token = (registered.get("data") or {}).get("token") or ""
    if not token:
        print("注册失败：", registered)
        return 1
    session = call("/app/task/enter", "POST", {"task_code": "free_chat"}, token).get("data") or {}
    task_id = session.get("task_id") or ""

    print(f"账号 {account} · 会话 {task_id}\n")
    for line in SCRIPT:
        data = (
            call(
                "/app/conversation/message",
                "POST",
                {"task_id": task_id, "message": line},
                token,
            ).get("data")
            or {}
        )
        said = ((data.get("messages") or [{}])[0]).get("text") or "（没有回话）"
        guide = (data.get("guide") or {}).get("text") or ""
        options = [
            item.get("label") for item in ((data.get("guide") or {}).get("options") or [])
        ]
        print(f"【他】{line}")
        print(f"【主理】{said}")
        print(f"【下一步】{guide}")
        if options:
            print("【可点】" + " / ".join(str(item) for item in options))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
