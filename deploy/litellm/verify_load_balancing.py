"""Verify the internal LiteLLM route without exposing provider credentials."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

REQUEST_COUNT = 20
CONCURRENCY = 8
URL = "http://127.0.0.1:4000/v1/chat/completions"


def _request_once(number: int, master_key: str) -> tuple[int, str]:
    payload = json.dumps(
        {
            "model": "deepseek-flash",
            "messages": [{"role": "user", "content": f"Reply only with OK. Check {number}."}],
            "temperature": 0,
            "max_tokens": 2,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {master_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
            return response.status, response.headers.get("x-litellm-model-id", "")
    except urllib.error.HTTPError as error:
        error.read()
        return error.code, error.headers.get("x-litellm-model-id", "")
    except (urllib.error.URLError, TimeoutError):
        return 599, ""


def main() -> int:
    master_key = os.getenv("LITELLM_MASTER_KEY", "").strip()
    if not master_key:
        print("LITELLM_MASTER_KEY is unavailable inside the proxy container.", file=sys.stderr)
        return 2

    results: list[tuple[int, str]] = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(_request_once, number, master_key) for number in range(REQUEST_COUNT)]
        for future in as_completed(futures):
            results.append(future.result())

    statuses = Counter(status for status, _ in results)
    deployments = Counter(model_id for status, model_id in results if status == 200 and model_id)
    print(f"HTTP status counts: {dict(sorted(statuses.items()))}")
    print(f"Deployment counts: {dict(sorted(deployments.items()))}")

    if statuses != Counter({200: REQUEST_COUNT}):
        print("Load-balancing verification failed: not every request returned HTTP 200.", file=sys.stderr)
        return 1
    if len(deployments) != 4:
        print(
            f"Load-balancing verification failed: expected 4 deployment IDs, got {len(deployments)}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
