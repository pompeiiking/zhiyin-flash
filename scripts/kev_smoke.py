"""真实 Kev + 职引 API 联调；会创建一个独立测试账号。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.error
import urllib.request
from uuid import uuid4

import asyncpg

DEFAULT_DSN = "postgresql://zhiyin:zhiyin@127.0.0.1:55432/zhiyin"


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str = "",
    timeout: float = 30.0,
) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {body}") from exc


def _api(
    base_url: str, path: str, payload: dict, *, token: str = "", timeout: float = 60.0
) -> dict:
    envelope = _request_json(
        f"{base_url.rstrip('/')}{path}",
        method="POST",
        payload=payload,
        token=token,
        timeout=timeout,
    )
    if int(envelope.get("code", -1)) != 0:
        raise RuntimeError(f"API failed {path}: {envelope}")
    return envelope["data"]


async def _decisions(dsn: str, user_id: str) -> list[dict]:
    connection = await asyncpg.connect(dsn)
    try:
        rows = await connection.fetch(
            """
            SELECT payload->'payload'->'intent_decision' AS decision
            FROM biz_behavior_log
            WHERE user_id = $1
              AND event_type = 'answer'
              AND payload->'payload' ? 'intent_decision'
            ORDER BY occurred_at ASC
            """,
            user_id,
        )
    finally:
        await connection.close()
    decisions: list[dict] = []
    for row in rows:
        value = row["decision"]
        decisions.append(json.loads(value) if isinstance(value, str) else dict(value))
    return decisions


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--kev", default="http://127.0.0.1:8009")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument(
        "--expect-kev-down",
        action="store_true",
        help="跳过模型状态检查，并验证后端在 Kev 不可用时安全回退",
    )
    args = parser.parse_args()

    if args.expect_kev_down:
        try:
            _request_json(f"{args.kev.rstrip('/')}/v1/models", timeout=3)
        except (OSError, TimeoutError, urllib.error.URLError):
            print("Kev unavailability confirmed; testing backend fallback")
        else:
            raise RuntimeError(
                "Kev is still reachable. Stop the service on port 8009 before "
                "running --expect-kev-down."
            )
    else:
        models = _request_json(f"{args.kev.rstrip('/')}/v1/models", timeout=10)
        card = next(item for item in models["models"] if item["name"] == "kev-latest")
        assert card["device"] == "cpu", card
        assert card["backend"] == "torch", card
        print(f"Kev ready: {card['run']} / {card['device']} / {card['dtype']}")

    health = _request_json(f"{args.api.rsplit('/api/v1', 1)[0]}/healthz", timeout=10)
    print(f"Backend health: {health}")

    suffix = uuid4().hex[:10]
    account = f"kev-smoke-{suffix}"
    login = _api(
        args.api,
        "/app/auth/register",
        {"account": account, "password": f"KevSmoke-{suffix}!"},
    )
    token = login["token"]
    user_id = login["user_id"]
    session = _api(args.api, "/app/task/enter", {"task_code": "free_chat"}, token=token)
    task_id = session["task_id"]

    # 这里必须避开 routing_rules.json 的关键词（例如“复盘”“回顾”），否则
    # “关键词优先”会按设计直接采用规则结果，根本不会调用 Kev。
    # 同时保留明确的“评价既有行动 + 调整后续安排”语义，用来验收 active 采用。
    high_message = "我已经执行原定求职安排一个月，请分析实际效果和不足，并根据结果校准今后的安排。"
    message_id = f"kev-{uuid4().hex}"
    started = time.perf_counter()
    _api(
        args.api,
        "/app/conversation/message",
        {"task_id": task_id, "message": high_message, "client_msg_id": message_id},
        token=token,
        timeout=90,
    )
    wall_ms = round((time.perf_counter() - started) * 1000, 1)
    first = await _decisions(args.dsn, user_id)
    assert len(first) == 1, first

    if args.expect_kev_down:
        assert first[0]["reason"] == "gateway_error", first[0]
        print(f"Kev-down fallback passed in {wall_ms} ms: {first[0]}")
        return

    assert first[0]["source"] == "kev", first[0]
    assert first[0]["candidate"] == "review_due", first[0]
    assert first[0]["adopted"] is True, first[0]
    print(f"Active routing passed in {wall_ms} ms: {first[0]}")

    # 同一个 client_msg_id 重放，既不再调用 Kev，也不新增行为记录。
    _api(
        args.api,
        "/app/conversation/message",
        {"task_id": task_id, "message": high_message, "client_msg_id": message_id},
        token=token,
        timeout=30,
    )
    replayed = await _decisions(args.dsn, user_id)
    assert len(replayed) == 1, replayed
    print("Idempotent replay passed")

    low_message = "目标已经定为产品经理，请把接下来两周拆成每天能完成的步骤。"
    _api(
        args.api,
        "/app/conversation/message",
        {
            "task_id": task_id,
            "message": low_message,
            "client_msg_id": f"kev-{uuid4().hex}",
        },
        token=token,
        timeout=90,
    )
    final = await _decisions(args.dsn, user_id)
    assert len(final) == 2, final
    assert final[-1]["source"] == "kev", final[-1]
    assert final[-1]["adopted"] is False, final[-1]
    print(f"Low-confidence fallback passed: {final[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
