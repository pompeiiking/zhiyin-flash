"""PostgreSQL outbox 事件总线的跨进程投递语义。"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from zhiyin_business.workers.impact import ImpactPropagationWorker
from zhiyin_infrastructure.postgres.messaging import PostgresEventBus
from zhiyin_orchestration.event import DomainEvent
from zhiyin_orchestration.impl.event_bus import GatewayEventBus


class _FakeConnection:
    def __init__(self, database: "_FakeDatabase") -> None:
        self._database = database

    async def fetch(self, _query: str, batch_size: int, lease_s: float) -> list[dict]:
        now = datetime.now(timezone.utc)
        pending = sorted(
            (
                row
                for row in self._database.rows.values()
                if row["status"] == "pending" and row["available_at"] <= now
            ),
            key=lambda row: (row["available_at"], row["created_at"]),
        )[:batch_size]
        for row in pending:
            row["available_at"] = now + timedelta(seconds=lease_s)
        return [
            {key: row[key] for key in ("id", "event_type", "payload")}
            for row in pending
        ]


class _FakeDatabase:
    """只实现 PostgresEventBus 用到的 SQL 行为，并共享行锁。"""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self._claim_lock = asyncio.Lock()

    async def execute(self, query: str, *args: Any) -> str:
        now = datetime.now(timezone.utc)
        if "INSERT INTO orc_event_outbox" in query:
            event_id, event_type, payload = args
            self.rows[event_id] = {
                "id": event_id,
                "event_type": event_type,
                "payload": payload,
                "status": "pending",
                "available_at": now,
                "created_at": now,
                "published_at": None,
            }
            return "INSERT 0 1"
        if "status = 'published'" in query:
            row = self.rows[args[0]]
            if row["status"] == "pending":
                row["status"] = "published"
                row["published_at"] = now
                return "UPDATE 1"
            return "UPDATE 0"
        if "SET available_at" in query:
            row = self.rows[args[0]]
            if row["status"] == "pending":
                row["available_at"] = now + timedelta(seconds=args[1])
                return "UPDATE 1"
            return "UPDATE 0"
        raise AssertionError(f"未覆盖的 SQL：{query}")

    @asynccontextmanager
    async def transaction(self):  # noqa: ANN201
        async with self._claim_lock:
            yield _FakeConnection(self)


def _event() -> DomainEvent:
    return DomainEvent(
        event_id="domain-event-1",
        event_type="profile_field_updated",
        occurred_at=datetime.now(timezone.utc),
        payload={"user_id": "user-1", "field_key": "career.goal"},
        trace_id="trace-1",
        idempotency_key="profile-user-1-career-goal-v1",
    )


async def test_publish_only_writes_outbox_without_local_dispatch() -> None:
    database = _FakeDatabase()
    gateway = PostgresEventBus(database)  # type: ignore[arg-type]
    bus = GatewayEventBus(gateway)
    received: list[DomainEvent] = []
    bus.subscribe("profile_field_updated", received.append)

    await bus.publish(_event())

    assert received == []
    row = next(iter(database.rows.values()))
    assert row["status"] == "pending"
    assert json.loads(row["payload"])["event_id"] == "domain-event-1"


async def test_independent_consumer_restores_domain_event_and_publishes() -> None:
    database = _FakeDatabase()
    publishing_bus = GatewayEventBus(PostgresEventBus(database))  # type: ignore[arg-type]
    consuming_gateway = PostgresEventBus(database)  # type: ignore[arg-type]
    consuming_bus = GatewayEventBus(consuming_gateway)
    received: list[DomainEvent] = []
    consuming_bus.subscribe("profile_field_updated", received.append)

    await publishing_bus.publish(_event())
    assert await consuming_gateway.poll_once() == 1

    assert len(received) == 1
    assert received[0].event_id == "domain-event-1"
    assert received[0].event_type == "profile_field_updated"
    assert received[0].payload == {"user_id": "user-1", "field_key": "career.goal"}
    assert received[0].trace_id == "trace-1"
    assert received[0].idempotency_key == "profile-user-1-career-goal-v1"
    row = next(iter(database.rows.values()))
    assert row["status"] == "published"
    assert row["published_at"] is not None


async def test_failed_handler_keeps_pending_and_delays_retry() -> None:
    database = _FakeDatabase()
    publisher = GatewayEventBus(PostgresEventBus(database))  # type: ignore[arg-type]
    consumer_gateway = PostgresEventBus(database, retry_delay_s=10)  # type: ignore[arg-type]
    consumer = GatewayEventBus(consumer_gateway)

    async def fail(_event: DomainEvent) -> None:
        raise RuntimeError("boom")

    consumer.subscribe("profile_field_updated", fail)
    await publisher.publish(_event())
    before = datetime.now(timezone.utc)

    assert await consumer_gateway.poll_once() == 0
    row = next(iter(database.rows.values()))
    assert row["status"] == "pending"
    assert row["published_at"] is None
    assert row["available_at"] >= before + timedelta(seconds=9)


async def test_two_consumers_cannot_claim_same_row_concurrently() -> None:
    database = _FakeDatabase()
    publisher = GatewayEventBus(PostgresEventBus(database))  # type: ignore[arg-type]
    first_gateway = PostgresEventBus(database)  # type: ignore[arg-type]
    second_gateway = PostgresEventBus(database)  # type: ignore[arg-type]
    first = GatewayEventBus(first_gateway)
    second = GatewayEventBus(second_gateway)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def handle(_event: DomainEvent) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()

    first.subscribe("profile_field_updated", handle)
    second.subscribe("profile_field_updated", handle)
    await publisher.publish(_event())

    first_poll = asyncio.create_task(first_gateway.poll_once())
    await entered.wait()
    assert await second_gateway.poll_once() == 0
    release.set()

    assert await first_poll == 1
    assert calls == 1


async def test_event_without_subscriber_is_acknowledged() -> None:
    database = _FakeDatabase()
    publisher = GatewayEventBus(PostgresEventBus(database))  # type: ignore[arg-type]
    consumer = PostgresEventBus(database)  # type: ignore[arg-type]

    await publisher.publish(_event())

    assert await consumer.poll_once() == 1
    assert next(iter(database.rows.values()))["status"] == "published"


async def test_cross_process_event_drives_impact_worker_only_on_consumer() -> None:
    class AssetsSpy:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[str], bool]] = []

        async def propagate(
            self, user_id: str, field_keys: list[str], *, mark_all: bool = False
        ) -> None:
            self.calls.append((user_id, field_keys, mark_all))

    class AiTasksSpy:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def invalidate_for_event(self, user_id: str, event_type: str) -> None:
            self.calls.append((user_id, event_type))

    database = _FakeDatabase()
    publisher_gateway = PostgresEventBus(database)  # type: ignore[arg-type]
    consumer_gateway = PostgresEventBus(database)  # type: ignore[arg-type]
    publisher_bus = GatewayEventBus(publisher_gateway)
    consumer_bus = GatewayEventBus(consumer_gateway)
    publisher_assets = AssetsSpy()
    consumer_assets = AssetsSpy()
    consumer_ai = AiTasksSpy()
    publisher_worker = ImpactPropagationWorker(publisher_assets, publisher_bus)
    consumer_worker = ImpactPropagationWorker(
        consumer_assets, consumer_bus, ai_tasks=consumer_ai
    )

    await publisher_bus.publish(_event())
    assert await publisher_worker.run_once() == 0

    assert await consumer_gateway.poll_once() == 1
    assert await consumer_worker.run_once() == 1
    assert publisher_assets.calls == []
    assert consumer_assets.calls == [("user-1", ["career.goal"], False)]
    assert consumer_ai.calls == [("user-1", "profile_field_updated")]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"poll_interval_s": 0}, "poll_interval_s"),
        ({"batch_size": 0}, "batch_size"),
        ({"lease_s": 0}, "lease_s"),
        ({"retry_delay_s": 0}, "retry_delay_s"),
    ],
)
def test_invalid_polling_configuration_is_rejected(
    kwargs: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PostgresEventBus(_FakeDatabase(), **kwargs)  # type: ignore[arg-type]
