"""Run one real model diagnosis and record only non-secret routing/source evidence."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    suffix = uuid4().hex[:12]
    with httpx.Client(
        base_url="http://127.0.0.1:8000/api/v1/app", timeout=150
    ) as client:
        def call(method: str, path: str, body=None):
            response = client.request(method, path, json=body)
            response.raise_for_status()
            envelope = response.json()
            assert envelope["code"] == 0, envelope
            return envelope["data"]

        login = call(
            "POST",
            "/auth/register",
            {"account": f"scout-smoke-{suffix}", "password": uuid4().hex},
        )
        client.headers["Authorization"] = "Bearer " + login["token"]
        call(
            "POST",
            "/profile/fields/major",
            {"value": "会计学", "expected_updated_at": None},
        )
        session = call("POST", "/task/enter", {"task_code": "verify_direction"})
        started = perf_counter()
        turn = call(
            "POST",
            "/conversation/message",
            {
                "task_id": session["task_id"],
                "message": "请结合现在能查到的原始来源，判断会计学相关方向；没有材料的能力不要判成短板。",
                "client_msg_id": f"scout-{uuid4().hex}",
            },
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        assert turn["stage"] == "diagnose", turn["stage"]
        messages = turn.get("messages") or []
        assert messages, turn
        reply = messages[-1]
        refs = reply.get("intel_refs") or []
        assert all(item.get("source_url", "").startswith(("http://", "https://")) for item in refs)
        versions = call("GET", "/assets/report/versions")
        report = call("GET", "/report/full-text") if versions else None

    evidence = {
        "stage": turn["stage"],
        "agent_id": reply.get("agent_id"),
        "elapsed_ms": elapsed_ms,
        "reply": reply.get("text", ""),
        "source_urls": [item["source_url"] for item in refs],
        "report_saved": bool(versions),
        "report_sources": (report or {}).get("sources", []),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
