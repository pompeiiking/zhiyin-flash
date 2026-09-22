"""接口前缀守卫：全站只有一处拼接 `/api/v1`。

为什么值得单独守一条
--------------------
版本段是最容易"多拼一次"的东西：Controller 里写 `/api/v1/...`、前端 baseURL 再加
一次、网关再加一次，结果是 **404 而 OpenAPI 里看着有这条路由**——排查成本极高，
而且在联调时才会暴露。

规则（与 `zhiyin_api/app.py` 的模块 docstring 一致）：
1. 唯一收口在 `zhiyin_api.app.API_PREFIX`，由 `create_app` 统一挂载；
2. Controller 里的路由路径**不得**出现版本段；
3. 所有对外接口都落在该前缀下，唯一例外是运维探针 `/healthz`；
4. 前缀不得嵌套（路径里最多出现一次 `/v1`）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import API_PREFIX, create_app
from zhiyin_boot import Settings

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS_DIR = TEMPLATE_ROOT / "zhiyin-api" / "zhiyin_api" / "controllers"

HEALTHZ_PATH = "/healthz"
"""唯一的非版本化端点：运维探针。"""


def _settings() -> Settings:
    data_dir = TEMPLATE_ROOT / "data"
    return Settings(
        # 本项目不提供 mock 产出：没有真模型就没有智能体引擎。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_data_dir=str(data_dir),
        local_registry_dir=str(data_dir / "registry"),
        local_knowledge_dir=str(data_dir / "knowledge"),
        local_object_dir=str(data_dir / "objects"),
    )


def test_api_prefix_is_v1() -> None:
    assert API_PREFIX == "/api/v1"
    assert Settings().api_prefix == API_PREFIX, (
        "Settings.api_prefix 与 api 层的常量必须一致，"
        "否则 boot 传进去的前缀和路由声明会对不上"
    )


def test_all_business_endpoints_live_under_the_prefix() -> None:
    """配置值与实际挂载值必须一致：所有业务接口都在 Settings.api_prefix 下。"""
    from zhiyin_boot import build_container, wire_application

    settings = _settings()
    container = build_container(settings)
    app = wire_application(container)
    paths = set(app.openapi()["paths"])

    assert paths, "OpenAPI 里必须存在路由"
    for path in paths:
        if path == HEALTHZ_PATH:
            continue  # 运维探针是唯一例外，由下一条测试单独守
        assert path.startswith(settings.api_prefix + "/"), (
            f"接口 {path} 不在版本前缀 {settings.api_prefix} 下。"
            "新增路由请不要自己拼前缀，交给 create_app 统一挂载"
        )


def test_only_healthz_is_outside_the_prefix() -> None:
    """唯一例外是运维探针：它必须存在、且必须在版本命名空间之外。"""
    with TestClient(create_app()) as client:
        assert client.get(HEALTHZ_PATH).status_code == 200
        assert client.get(f"{API_PREFIX}/healthz").status_code == 404, (
            "/healthz 是运维探针，故意不随版本变化；不要在版本前缀下再挂一个"
        )


def test_no_double_version_nesting() -> None:
    """路径里最多出现一次 `/v1`——防止 `/api/v1/api/v1/...` 这类拼接错误。"""
    from zhiyin_boot import build_container, wire_application

    app = wire_application(build_container(_settings()))
    for path in app.openapi()["paths"]:
        assert path.count("/v1") <= 1, f"接口 {path} 出现了重复的版本段"


def test_openapi_and_docs_follow_the_prefix() -> None:
    """OpenAPI 与交互文档同前缀：前端 gen:api 抓的就是对外的那个地址。"""
    app = create_app()
    assert app.openapi_url == f"{API_PREFIX}/openapi.json"
    assert app.docs_url == f"{API_PREFIX}/docs"

    with TestClient(app) as client:
        assert client.get(f"{API_PREFIX}/openapi.json").status_code == 200


@pytest.mark.parametrize("source", sorted(CONTROLLERS_DIR.glob("*.py")))
def test_controllers_do_not_hardcode_a_version_segment(source: Path) -> None:
    """Controller 的路由声明里不得出现版本段。

    这条是"不要在别的地方多嵌套 v1"的机械保证：路由只写业务段
    （`/app/bootstrap`），版本段由 `create_app` 统一加上。
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        decorator_route = (
            isinstance(func, ast.Attribute) and func.attr in {"get", "post", "put", "patch", "delete"}
        )
        if not decorator_route or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if "v1" in first.value or "api/" in first.value:
                offenders.append(f"{source.name}: {first.value}")
    assert not offenders, (
        "Controller 路由里出现了版本段或 api 段（会与前缀重复拼接）：\n  "
        + "\n  ".join(offenders)
    )
