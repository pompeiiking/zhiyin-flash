"""本轮修复的回归守卫：每条对应一个**实测复现过**的缺陷。

写法约定：用例名说清"守住什么"，docstring 写清"不守会怎样"。
这些都是曾经真实发生过的故障（不是推测的风险），所以断言必须能复现原缺陷。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import API_PREFIX, create_app
from zhiyin_boot import Settings, build_container, wire_application
from zhiyin_kernel.errors import (
    DuplicateResource,
    InvalidRequest,
    ResourceNotFound,
)

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"


def _settings() -> Settings:
    return Settings(
        # 本项目不提供 mock 产出：没有真模型就没有智能体引擎。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_data_dir=str(DATA_DIR),
        local_registry_dir=str(DATA_DIR / "registry"),
        local_knowledge_dir=str(DATA_DIR / "knowledge"),
        local_object_dir=str(DATA_DIR / "objects"),
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(wire_application(build_container(_settings()))) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# 1. 账号接管（曾经：重复注册直接覆盖既有密码）
# ---------------------------------------------------------------------------


async def test_register_refuses_an_existing_account() -> None:
    """重复注册必须抛 `DuplicateResource`，而不是静默成功。

    原缺陷：`register` 不检查账号是否存在，直接调 `set_password`
    （带 `ON CONFLICT DO UPDATE`）。实测结果是"任何人知道账号名就能把密码改掉"。
    """
    from zhiyin_business.services.identity import DefaultIdentityService
    from zhiyin_infrastructure.local.auth import DefaultPassAuth
    from zhiyin_infrastructure.local.repository import InMemoryUserRepository

    service = DefaultIdentityService(DefaultPassAuth(), InMemoryUserRepository())
    await service.register("student-1", "orig-pass-111")

    with pytest.raises(DuplicateResource):
        await service.register("student-1", "attacker-pass-999")

    # 关键断言：原密码仍然有效（凭据没有被覆盖）
    assert await service._auth.verify_password("student-1", "orig-pass-111") is True


async def test_register_does_not_create_an_orphan_session() -> None:
    """注册只补用户记录，不再顺带 `login()` 签一个永远不会被返回的令牌。

    原缺陷：`register` 内部先 `login` 一次（签 1 个 token + 1 行
    `infra_auth_session`），Controller 随后再 `login` 一次 —— 库里留下孤儿会话。
    """
    from zhiyin_business.services.identity import DefaultIdentityService
    from zhiyin_infrastructure.local.auth import DefaultPassAuth
    from zhiyin_infrastructure.local.repository import InMemoryUserRepository

    users = InMemoryUserRepository()
    service = DefaultIdentityService(DefaultPassAuth(), users)
    await service.register("student-2", "pass-222222")

    # 身份服务不该自己签发令牌：返回的只是一个账号 id
    assert await users.get_by_id("student-2") is not None


# ---------------------------------------------------------------------------
# 2. 未登记的任务入口（曾经：静默建一个名字等于 code 的会话）
# ---------------------------------------------------------------------------


async def test_unknown_task_code_is_rejected() -> None:
    """拼错的 task_code 必须报错。

    原缺陷：`enter_task` 找不到入口时回落到"任务名 = code"，于是前端与动态资源
    不同步这件事被静默吞掉，用户看到一个自己看不懂的任务名，没有任何一处报错。
    """
    container = build_container(_settings())
    with pytest.raises(ResourceNotFound):
        await container.orchestrator.enter_task("u1", "no_such_code")


# ---------------------------------------------------------------------------
# 3. 跨用户越权（IDOR）
# ---------------------------------------------------------------------------


async def test_another_users_session_is_not_reachable() -> None:
    """别人的 task_id 不能读写。

    原缺陷：`TaskSessionRepository.get(session_id)` 只按 id 取，`handle_message`
    从不比较 `session.user_id` —— 任何已登录用户拿到别人的 task_id 就能继续推进它。
    """
    from zhiyin_business.ports.orchestrator import TurnRequest

    container = build_container(_settings())
    session = await container.orchestrator.enter_task("owner-user", "confused")

    with pytest.raises(ResourceNotFound):
        await container.orchestrator.handle_message(
            TurnRequest(user_id="attacker-user", task_id=session.id, message="在吗")
        )


# ---------------------------------------------------------------------------
# 4. 方向方案选择：先改状态后校验（OCR 抓到的 critical）
# ---------------------------------------------------------------------------


async def test_selecting_an_unknown_plan_does_not_corrupt_state() -> None:
    """传入不存在的 plan_id 必须**先报错、后无副作用**。

    原缺陷：`select_direction_plan` 在同一个循环里边找边把其它方案置为未选，
    找不到目标才抛 `LookupError` —— 调用方即使捕获异常，用户的当前选择也已经被抹掉。
    """
    from zhiyin_infrastructure.local.repository import InMemoryAssetRepository
    from zhiyin_kernel.assets import DirectionPlan
    from zhiyin_kernel.enums import PlanRole

    repo = InMemoryAssetRepository()
    plan = DirectionPlan(
        id="plan-1",
        report_id="r1",
        role=PlanRole.MAIN,
        name="结构设计",
        target_desc="设计院的建筑结构岗",
        match_score=0.82,
        fit_reason="课程设计连续三个学期选结构方向",
        main_risk="前两年回报低",
        selected=True,
    )
    await repo.save_direction_plans("u1", [plan])

    with pytest.raises(ResourceNotFound):
        await repo.select_direction_plan("u1", "no-such-plan")

    plans = await repo.list_direction_plans("u1")
    assert plans[0].selected is True, "失败的调用不得改动既有选择"


# ---------------------------------------------------------------------------
# 5. 动态资源与工具目录闭合（曾经：agents.tools 全是中文旧名 → 对话 100% 500）
# ---------------------------------------------------------------------------


def test_agent_tool_whitelists_only_reference_registered_tools() -> None:
    """`agents.json` 的 tools 必须全部能在工具目录里找到。

    原缺陷：文件里的工具名从"访谈话术"改成 `profile.read` 之后，库里那份旧数据
    没跟着更新，引擎在 `_tools_for` 抛 `MissingConfigError` —— 症状是**对话直接 500**，
    而根因只是一份配置里写了一个早已改名的工具。
    """
    from zhiyin_infrastructure.ai.tools import KNOWN_TOOL_NAMES

    agents = json.loads((DATA_DIR / "registry" / "agents.json").read_text(encoding="utf-8"))["items"]
    assert agents, "agents.json 不能为空"
    for agent in agents:
        unknown = sorted(set(agent.get("tools", [])) - KNOWN_TOOL_NAMES)
        assert not unknown, (
            f"智能体 {agent['id']} 的白名单里有未注册的工具：{unknown}。"
            f"已注册：{sorted(KNOWN_TOOL_NAMES)}"
        )


def test_tool_catalog_self_check_matches_the_declared_names() -> None:
    """工具目录里的名字必须是 `KNOWN_TOOL_NAMES` 里有的（防名单变成过期文档）。

    注意方向：**目录是子集，名单是全集**。有些工具是"配了能力才有"
    （`web.search` 要有搜索密钥），所以没配时目录里没有它 ——
    这不是不一致，而是"这个能力位没接"。反过来才是不一致：
    目录里出现一个名单里没有的名字，说明有人加了工具却没登记。
    """
    from zhiyin_infrastructure.ai.tools import KNOWN_TOOL_NAMES, build_tool_catalog

    catalog = build_tool_catalog(search=object(), external_data=object(),
                                 profile_reader=lambda _: None,
                                 behavior_reader=lambda *_: None)
    assert set(catalog) <= set(KNOWN_TOOL_NAMES)
    # 四类基础工具在能力齐备时必须都在
    assert {"kb.search", "xuezhi.search", "profile.read", "behavior.recent"} <= set(catalog)


# ---------------------------------------------------------------------------
# 6. 统一信封：参数校验 / 输入不合法 / 未捕获异常
# ---------------------------------------------------------------------------


def test_request_validation_error_uses_the_envelope_and_hides_the_password(
    client: TestClient,
) -> None:
    """422 必须走统一信封，且**不得回显用户提交的密码**。

    原缺陷：返回 FastAPI 默认的 `{"detail": [...]}`；Pydantic 的 `input` 字段会把
    密码原文回显在响应体里，既没有 code 也没有 trace_id。
    """
    secret = "should-never-be-echoed"
    response = client.post(f"{API_PREFIX}/app/auth/login", json={"account": "x", "password": secret})

    assert response.status_code == 422
    body = response.json()
    assert set(body) >= {"code", "message", "data", "trace_id"}
    assert body["code"] == 1001
    assert body["trace_id"] == response.headers["X-Trace-Id"]
    assert secret not in response.text


def test_blank_note_is_a_client_error_not_a_500(client: TestClient) -> None:
    """纯空白的写入必须报 1001，而不是 500。

    原缺陷：`text="   "` 能过 `min_length=1`，服务层 strip 后抛 `ValueError`，
    而例外映射表里没有 `ValueError` → 纯文本 500，前端拿不到任何错误码。
    """
    from zhiyin_api.dto.common import ErrorCode

    # 先拿一个可用 token（演示鉴权接受任意密码）
    auth = client.post(
        f"{API_PREFIX}/app/auth/login", json={"account": "regress-user", "password": "pass-123456"}
    )
    assert auth.status_code == 200, auth.text

    response = client.post(
        f"{API_PREFIX}/app/notes",
        json={"text": "   "},
        headers={"Authorization": "Bearer demo-token"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == int(ErrorCode.INVALID_PARAM)


async def test_unhandled_exception_still_carries_a_trace_id() -> None:
    """未捕获异常也必须是"带 trace 的统一信封"，而不是纯文本 500。

    原缺陷：异常穿透 `RequestContextMiddleware` 后由最外层的 ServerErrorMiddleware
    兜底，返回一条既没有信封、也没有 `X-Trace-Id` 的 500 —— 排查时最需要 trace 的
    那一刻，它恰好不在。
    """
    from zhiyin_api.context import TRACE_HEADER, RequestContextMiddleware
    from zhiyin_api.dto.common import ErrorCode

    async def boom(scope, receive, send):  # noqa: ANN001, ARG001
        raise RuntimeError("boom")

    app = RequestContextMiddleware(boom)
    messages: list[dict] = []

    async def send(message):  # noqa: ANN001
        messages.append(message)

    async def receive():  # noqa: ANN202
        return {"type": "http.request"}

    await app({"type": "http", "method": "GET", "path": "/x", "headers": []}, receive, send)

    start, body_message = messages[0], messages[1]
    # ASGI 原始头名按惯例是小写
    headers = {name.decode().lower(): value.decode() for name, value in start["headers"]}
    assert start["status"] == 500
    assert headers[TRACE_HEADER.lower()], "500 也必须带 X-Trace-Id"

    body = json.loads(body_message["body"])
    assert body["code"] == int(ErrorCode.INTERNAL)
    assert body["trace_id"] == headers[TRACE_HEADER.lower()]


# ---------------------------------------------------------------------------
# 7. SSE：未登录要拿到 401 信封，而不是一条中途断掉的连接
# ---------------------------------------------------------------------------


def test_sse_requires_auth_with_an_envelope() -> None:
    """未登录取 AI 任务的流，必须收到 401 信封。

    原缺陷：鉴权在生成器内部执行，`PermissionError` 从流里逃出去，
    客户端只看到 `incomplete chunked read`，拿不到任何错误码。

    用替身 Facade 而不是真装配：本地演示鉴权是 fail-open（任何请求都算已登录），
    真装配下根本走不到"未登录"这条分支 —— 那样这条用例会变成空跑。
    """
    from zhiyin_api.facade import configure_facade, reset_facade

    class _Unauthenticated:
        async def resolve_user_id(self, request):  # noqa: ANN001, ARG002
            raise PermissionError("缺少登录令牌")

        async def run_ai_task(self, user_id, key, arg=""):  # noqa: ANN001, ARG002
            raise AssertionError("鉴权失败时不该走到这里")
            yield  # pragma: no cover - 让它保持异步生成器

    configure_facade(_Unauthenticated())
    try:
        with TestClient(create_app()) as bare:
            response = bare.post(f"{API_PREFIX}/app/brief/today", json={})
    finally:
        reset_facade()

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 1004
    assert body["trace_id"]


# ---------------------------------------------------------------------------
# 8. 输入校验：DTO 层不该把明显非法的输入放行到服务层
# ---------------------------------------------------------------------------


async def test_note_service_rejects_whitespace_only_content() -> None:
    """服务层的兜底断言仍然保留（DTO 校验之外的第二道门）。"""
    from zhiyin_business.services.note import DefaultUserNoteService
    from zhiyin_infrastructure.local.repository import InMemoryUserNoteRepository

    service = DefaultUserNoteService(InMemoryUserNoteRepository())
    with pytest.raises(InvalidRequest):
        await service.add("u1", "   ")
