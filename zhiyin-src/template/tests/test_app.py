"""接口层测试：应用能起来、统一信封生效、未实现能力按约定降级。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import API_PREFIX
from zhiyin_boot import Settings, build_container, wire_application
from zhiyin_api.app import create_app


@pytest.fixture
def settings() -> Settings:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    return Settings(
        # 本项目不提供 mock 产出：没有真模型就没有智能体引擎。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_registry_dir=str(data_dir / "registry"),
        local_knowledge_dir=str(data_dir / "knowledge"),
        local_object_dir=str(data_dir / "objects"),
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = wire_application(build_container(settings))
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_reports_assembly(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assembly = body["assembly"]
    # 已实现的部件必须如实报 wired
    assert assembly["orchestration"]["agent_engine"] == "wired"
    assert assembly["services"]["ai_task_service"] == "wired"
    # 联调期交付的门面必须如实报 wired；剩余缺口（如 vector_sync）仍要列出
    assert assembly["services"]["facade"] == "wired"
    assert assembly["missing"]


def test_openapi_is_served(client: TestClient) -> None:
    """有 app 工厂的直接收益：/docs 与 openapi.json 可用，前端能生成类型。"""
    response = client.get(f"{API_PREFIX}/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    # 业务接口一律在版本前缀下（见 tests/test_api_prefix.py 的守卫）
    assert f"{API_PREFIX}/app/bootstrap" in paths
    assert f"{API_PREFIX}/app/task/enter" in paths
    assert "/healthz" in paths


def test_wired_facade_serves_bootstrap(client: TestClient) -> None:
    """Facade 已装配：bootstrap 返回动态资源数据，而不是 DEPENDENCY_UNAVAILABLE。"""
    response = client.get(f"{API_PREFIX}/app/bootstrap")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    # 统一信封字段齐备（R-API-006）
    assert set(body) >= {"code", "message", "data", "trace_id"}
    data = body["data"]
    assert data["task_entries"], "任务入口必须来自动态资源"
    assert "app.name" in data["copy_bundle"]


def test_healthz_works_without_assembly() -> None:
    """裸 create_app（未走 boot）时 healthz 仍可用，返回空装配报告。"""
    from zhiyin_api.runtime import reset_runtime

    reset_runtime()
    with TestClient(create_app()) as bare:
        response = bare.get("/healthz")
        assert response.status_code == 200
        assert response.json()["assembly"]["gateways"] == {}


def test_academic_import_accepts_an_uploaded_json_file(client: TestClient) -> None:
    """上传入口真的能读懂一份 JSON 文件（每门课一条记录）。

    这是被真实反馈逼出来的一条：用户传的是完全正确的 JSON，界面上却被判"读不出这是课表"。
    现在这条链路上有三个环节合起来保证它能读：multipart 收文件（本用例）、
    按编码解码（GBK / BOM，见 test_academic_import）、按字段名读 JSON。
    """
    payload = json.dumps(
        [
            {
                "day": "星期二",
                "period": "第1-2节",
                "course_name": "计算机通信与网络_01",
                "teacher": "张虹*",
                "weeks": "1-13周",
            },
            {"day": "星期三", "period": "第3-4节", "course_name": "高等数学", "weeks": "1-16周"},
        ],
        ensure_ascii=False,
    ).encode("utf-8")

    response = client.post(
        f"{API_PREFIX}/app/academic/import/file",
        files={"courses_file": ("课表.json", payload, "application/json")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["courses"] == 2
    assert body["data"]["source"] == "json"


def test_academic_import_refuses_an_excel_upload_with_a_next_step(client: TestClient) -> None:
    """传 Excel：422 + 信封 + 一句"另存为 CSV"，不是 500、也不是"读不出这是课表"。"""
    response = client.post(
        f"{API_PREFIX}/app/academic/import/file",
        files={"courses_file": ("课表.xlsx", b"PK\x03\x04\x14\x00", "application/vnd.ms-excel")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 1001
    assert "另存为 CSV" in body["message"]
