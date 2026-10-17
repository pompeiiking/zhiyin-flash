from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from zhiyin_api.app import create_app


@pytest.mark.parametrize("path,feature", [
    ("/app/report/full-text", "report_full_text"),
    ("/app/assets/report/versions/1/content", "report_full_text"),
    ("/app/calendar", "calendar"),
    ("/app/schedule/semester", "calendar"),
    ("/app/achievements", "achievements"),
    ("/app/assets/export", "export"),
    ("/app/assets/download/example", "export"),
])
def test_feature_toggle_applies_without_restart_and_blocks_handler(path, feature):
    called = []
    router = APIRouter()

    @router.get(path)
    def handler():
        called.append(True)
        return {"ok": True}

    registry = SimpleNamespace(feature_flags=AsyncMock(return_value={feature: False}))
    with TestClient(create_app(routers=[router], feature_registry=registry)) as client:
        result = client.get("/api/v1" + path)
        assert result.status_code == 403
        assert result.json()["code"] == 1008
        assert result.headers["X-Trace-Id"] == result.json()["trace_id"]
        assert called == []
        registry.feature_flags.return_value = {feature: True}
        assert client.get("/api/v1" + path).status_code == 200
        assert called == [True]
