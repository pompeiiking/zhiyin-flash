from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import APIRouter
from fastapi.testclient import TestClient

from zhiyin_api.app import create_app


def test_quota_blocks_before_write_and_keeps_trace_and_login():
    router = APIRouter()
    writes = []

    @router.post("/app/conversation/message/stream")
    async def write():
        writes.append(True)
        return {"ok": True}

    limiter = SimpleNamespace(allow_async=AsyncMock(side_effect=[True, False, True]))
    auth = SimpleNamespace(authenticate=AsyncMock(return_value=SimpleNamespace(user_id="alice")))
    app = create_app(routers=[router], rate_limit=limiter, auth=auth)
    with TestClient(app) as client:
        url = "/api/v1/app/conversation/message/stream"
        assert client.post(url, headers={"Authorization": "Bearer first"}).status_code == 200
        denied = client.post(url, headers={"Authorization": "Bearer second"})
        assert denied.status_code == 429
        assert denied.json()["code"] == 1009
        assert denied.json()["trace_id"] == denied.headers["X-Trace-Id"]
        assert denied.headers["Retry-After"] == "3"
        assert len(writes) == 1
        calls = limiter.allow_async.call_args_list
        assert calls[0].args[0] == calls[1].args[0]  # rotating tokens does not reset user quota
        assert "alice" not in calls[0].args[0]
        assert client.get(url).status_code == 405  # reads consume no write quota
        auth.authenticate.return_value = SimpleNamespace(user_id="bob")
        assert client.post(url, headers={"Authorization": "Bearer other"}).status_code == 200
        assert limiter.allow_async.call_args_list[-1].args[0] != calls[0].args[0]


def test_auth_quota_does_not_trust_forwarded_ip_or_supplied_token():
    limiter = SimpleNamespace(allow_async=AsyncMock(return_value=False))
    auth = SimpleNamespace(authenticate=AsyncMock())
    with TestClient(create_app(routers=[], rate_limit=limiter, auth=auth)) as client:
        for host in ("one", "two"):
            response = client.post("/api/v1/app/auth/login", headers={"X-Forwarded-For": host})
            assert response.status_code == 429
        assert limiter.allow_async.call_args_list[0] == limiter.allow_async.call_args_list[1]
        auth.authenticate.assert_not_called()
