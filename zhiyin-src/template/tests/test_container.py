"""装配层测试：容器能构造、最低可用部件齐全、装配报告如实反映缺口。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from zhiyin_boot import (
    Settings,
    assert_minimum_viable,
    build_container,
    describe_assembly,
    wire_application,
)
from zhiyin_boot.workers import run_background_container
from zhiyin_api.runtime import WIRED


@pytest.fixture
def settings() -> Settings:
    """指向仓库内种子数据的配置，保证测试与本地演示读同一份动态资源。"""
    from pathlib import Path

    template_root = Path(__file__).resolve().parents[1]
    data_dir = template_root / "data"
    return Settings(
        env="test",
        local_data_dir=str(data_dir),
        local_registry_dir=str(data_dir / "registry"),
        local_knowledge_dir=str(data_dir / "knowledge"),
        local_object_dir=str(data_dir / "objects"),
        # 有真模型才有智能体引擎 —— 本项目不提供 mock 产出，
        # 所以"没有模型"的容器应当如实缺 llm 与 agent_engine。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
    )


def test_container_builds(settings: Settings) -> None:
    container = build_container(settings)
    assert_minimum_viable(container)  # 不抛异常即为通过


def test_orchestration_primitives_are_wired(settings: Settings) -> None:
    container = build_container(settings)
    for name in (
        "event_bus_primitive",
        "scheduler_primitive",
        "notifier_primitive",
        "state_store",
        "agent_engine",
        "workflow_engine",
    ):
        assert getattr(container, name) is not None, f"编排原语未装配：{name}"


def test_business_service_depends_on_agent_engine(settings: Settings) -> None:
    container = build_container(settings)
    # 生成类 AI 任务必须复用容器里的同一个 AgentEngine 实例 —— 自己 new 一个
    # 就会出现"两份引擎配置、改了库只有一份生效"。
    assert container.ai_task_service is not None
    assert container.ai_task_service._engine is container.agent_engine


def test_scheduler_gateway_can_publish(settings: Settings) -> None:
    """调度器必须持有事件总线，否则主动事件（停滞检测）永远不触发。"""
    container = build_container(settings)
    assert container.scheduler._event_bus is container.event_bus


async def test_feature_flags_come_from_dynamic_resource(settings: Settings) -> None:
    """功能开关必须来自动态资源，而不是代码里的常量。"""
    container = build_container(settings)
    flags = await container.feature_flags.all()
    assert flags.get("report_full_text") is True
    assert flags.get("export") is False
    assert "mentor" in flags


def test_assembly_report_marks_pending_services(settings: Settings) -> None:
    container = build_container(settings)
    report = describe_assembly(container)

    # 已实现的部分必须是 wired（模型网关是装配好的真网关）
    assert report.orchestration["agent_engine"] == WIRED
    assert report.gateways["llm"] == WIRED

    # 编排器、黑板服务与 BFF 门面已实现（联调期交付），必须如实报 wired
    assert report.services["orchestrator"] == WIRED
    assert report.services["profile_service"] == WIRED
    assert report.services["asset_service"] == WIRED
    assert report.services["workspace_service"] == WIRED
    assert report.services["function_service"] == WIRED
    assert report.services["facade"] == WIRED
    assert report.workers["impact"] == WIRED
    assert report.workers["active_event"] == WIRED
    # vector_sync 依赖 PostgreSQL，本地装配仍缺 → 缺口必须列出
    assert report.missing, "装配报告必须列出缺口"
    assert not report.healthy


def test_wire_application_returns_asgi_app(settings: Settings) -> None:
    container = build_container(settings)
    app = wire_application(container)
    assert app.title.endswith("API")

    # 路由已挂载：用 openapi 断言，避免依赖 starlette 内部的路由表示形式。
    paths = set(app.openapi()["paths"])
    assert "/healthz" in paths
    # 业务路由统一挂在 /api/v1 下，前缀由 create_app 拼接（见 tests/test_api_prefix.py）
    assert "/api/v1/app/bootstrap" in paths
    assert "/api/v1/app/task/enter" in paths


def test_api_lifespan_can_disable_scheduler_and_background_workers(
    settings: Settings,
) -> None:
    """多 API 副本不得各自启动一套定时任务。"""

    class SchedulerSpy:
        started = 0
        stopped = 0

        def start_polling(self) -> None:
            self.started += 1

        async def stop_polling(self) -> None:
            self.stopped += 1

    class EventBusSpy(SchedulerSpy):
        pass

    class WorkerSpy:
        name = "spy"
        calls = 0

        async def run_once(self) -> int:
            self.calls += 1
            return 0

    settings.run_in_process_background = False
    container = build_container(settings)
    event_bus = EventBusSpy()
    scheduler = SchedulerSpy()
    worker = WorkerSpy()
    container.event_bus = event_bus
    container.scheduler = scheduler
    container.workers = [worker]

    with TestClient(wire_application(container)) as client:
        assert client.get("/healthz").status_code == 200

    assert event_bus.started == 0
    assert event_bus.stopped == 0
    assert scheduler.started == 0
    assert scheduler.stopped == 0
    assert worker.calls == 0


def test_api_lifespan_starts_outbox_polling_in_single_instance_mode(
    settings: Settings,
) -> None:
    """单实例模式由 API lifespan 启停 outbox 消费者。"""

    class PollerSpy:
        def __init__(self) -> None:
            self.started = 0
            self.stopped = 0

        def start_polling(self) -> None:
            self.started += 1

        async def stop_polling(self) -> None:
            self.stopped += 1

    settings.run_in_process_background = True
    container = build_container(settings)
    event_bus = PollerSpy()
    scheduler = PollerSpy()
    container.event_bus = event_bus
    container.scheduler = scheduler
    container.workers = []

    with TestClient(wire_application(container)) as client:
        assert client.get("/healthz").status_code == 200
        assert event_bus.started == 1
        assert scheduler.started == 1

    assert event_bus.stopped == 1
    assert scheduler.stopped == 1


async def test_background_container_starts_and_stops_outbox_polling(
    settings: Settings,
) -> None:
    """多副本模式由独立后台进程启停 outbox 消费者。"""

    class PollerSpy:
        def __init__(self) -> None:
            self.started = 0
            self.stopped = 0
            self.running = asyncio.Event()

        def start_polling(self) -> None:
            self.started += 1
            self.running.set()

        async def stop_polling(self) -> None:
            self.stopped += 1

    container = build_container(settings)
    event_bus = PollerSpy()
    scheduler = PollerSpy()
    container.event_bus = event_bus
    container.scheduler = scheduler
    container.registry_service = None
    container.workers = []

    task = asyncio.create_task(run_background_container(container))
    await event_bus.running.wait()
    assert event_bus.started == 1
    assert scheduler.started == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert event_bus.stopped == 1
    assert scheduler.stopped == 1
