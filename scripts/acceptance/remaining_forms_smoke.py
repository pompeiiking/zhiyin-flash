"""Real HTTP/JWT/PostgreSQL checks using a disposable account, without printing secrets."""
import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    checks = []
    with httpx.Client(base_url="http://127.0.0.1:8000/api/v1/app", timeout=30) as client:
        def call(method, path, body=None, status=200):
            response = client.request(method, path, json=body)
            assert response.status_code == status, (path, response.status_code, response.text)
            return response.json().get("data")

        login = call("POST", "/auth/register", {"account": "forms-" + uuid4().hex[:12], "password": uuid4().hex})
        client.headers["Authorization"] = "Bearer " + login["token"]
        for path, first, second, conflict in [
            ("/preferences", {"quiet_start": "20:00", "quiet_end": "08:00"}, {"material_analysis": False}, {"quiet_start": "21:00", "quiet_end": "08:00"}),
            ("/plan/direction-weights", {"major": 3}, {"salary": 4}, {"major": 5}),
        ]:
            original = call("GET", path)
            call("PUT", path, {**original, **first, "expected": original})
            merged = call("PUT", path, {**original, **second, "expected": original})
            assert all(merged[k] == v for k, v in {**first, **second}.items())
            call("PUT", path, {**original, **conflict, "expected": original}, status=409)
            assert call("GET", path) == merged
            # Lost-response replay must not restore the fields changed in another tab.
            assert call("PUT", path, {**original, **first, "expected": original}) == merged
            checks.append(path + ": independent merge, conflict rejection and replay")
        semester = {"first_monday": "2026-10-12", "weeks": 20, "periods": [{"number": 1, "start": "08:00", "end": "08:45"}], "expected": None}
        saved = call("PUT", "/schedule/semester", semester)
        assert call("PUT", "/schedule/semester", semester) == saved
        call("PUT", "/schedule/semester", {**semester, "weeks": 18}, status=409)
        checks.append("semester: concurrent first creation rejected, replay stable")
        original = call("POST", "/profile/fields/major", {"value": "软件工程", "expected_updated_at": None})
        body = {"value": "计算机科学", "expected_updated_at": original["updated_at"]}
        saved = call("POST", "/profile/fields/major", body)
        assert call("POST", "/profile/fields/major", body) == saved
        call("POST", "/profile/fields/major", {**body, "value": "其他专业"}, status=409)
        checks.append("profile: stale edit rejected, retry returns same version")
        def upload(data):
            response = client.post("/conversation/material", files={"file": ("测试.txt", data, "text/plain")})
            assert response.status_code == 200, response.text
            return response.json()["data"]["material_id"]
        material = upload("真实接口重复上传验收".encode())
        assert upload("真实接口重复上传验收".encode()) == material
        assert upload("内容改变".encode()) != material
        checks.append("upload: identical retry deduplicated, different content separated")
        call("POST", "/auth/logout")
        response = client.post("/profile/fields/major", json={"value": "过期请求", "expected_updated_at": saved["updated_at"]})
        assert response.status_code == 401
        checks.append("expired session: write refused")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"checks": checks, "passed": len(checks)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(checks)} real HTTP checks passed")


if __name__ == "__main__":
    main()
