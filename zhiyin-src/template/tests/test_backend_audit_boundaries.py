"""Regression probes for reachable backend failure and concurrency branches."""
import asyncio

import pytest

from tests.e2e.test_main_path import _container
from tests.test_academic_import import QZ_SCHEDULE, QZ_GRADES
from zhiyin_business.services.academic import DefaultAcademicService
from zhiyin_infrastructure.academic import ManualAcademicImporter
from zhiyin_infrastructure.local.repository import InMemoryAcademicSnapshotRepository
from zhiyin_infrastructure.xuezhi.client import _extract_result_json
from zhiyin_infrastructure.xuezhi.client import XueZhiClient
from zhiyin_infrastructure.xuezhi.parsing import matched_occupations, speciality_text
from zhiyin_orchestration import DomainEvent
from zhiyin_orchestration.impl.event_bus import GatewayEventBus
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from zhiyin_business.services.memory import DefaultConversationMemoryService
from zhiyin_infrastructure.local.object_store import LocalFileStore
from zhiyin_infrastructure.local.repository import InMemoryConversationMemoryRepository
from zhiyin_infrastructure.textfile import LocalTextExtractor
from hashlib import sha256
import json

from zhiyin_business.services.function import DefaultFunctionService
from zhiyin_data_sdk.gateways.datasource import DataSourceResult, DataSourceRecord


def intel_service():
    c = _container()
    return DefaultFunctionService(assets=c.asset_service, behaviors=c.behavior_service,
        object_store=c.object_store, calendar=c.calendar, track_events=c.track_events,
        notifications=c.notifications)


async def test_intel_status_without_direction_remembers_failed_upstream():
    service = intel_service()
    service._data_sources = AsyncMock()
    service._data_sources.fetch.return_value = DataSourceResult(source="xuezhi", degraded=True, errors=["timeout"])
    await service.fetch_external_intel("audit-user", topic="AI")
    status = await service.intel_fetch_status("audit-user", topic="AI")
    assert status["status"] == "failed"


async def test_intel_cache_separates_account_topic_and_limit():
    service = intel_service()
    service._data_sources = AsyncMock()
    service._data_sources.fetch.return_value = DataSourceResult(source="xuezhi")
    await service.fetch_external_intel("a|b", topic="c", limit=1)
    await service.fetch_external_intel("a", topic="b|c", limit=1)
    await service.fetch_external_intel("a", topic="b|c", limit=8)
    assert service._data_sources.fetch.await_count == 3


async def test_intel_invalidation_clears_only_exact_owner_and_their_status():
    service = intel_service()
    service._data_sources = AsyncMock()
    service._data_sources.fetch.return_value = DataSourceResult(source="xuezhi")
    await service.fetch_external_intel("a", topic="c")
    await service.fetch_external_intel("a|b", topic="c")
    service.drop_intel_cache("a")
    await service.fetch_external_intel("a|b", topic="c")
    assert service._data_sources.fetch.await_count == 2
    assert (await service.intel_fetch_status("a", topic="c"))["status"] == "unknown"


async def test_concurrent_intel_failures_do_not_leak_between_requests():
    service = intel_service()
    failed = asyncio.Event()
    async def fetch(request):
        if request.query == "failed":
            failed.set()
            raise RuntimeError("synthetic failure")
        await failed.wait()
        return DataSourceResult(source="xuezhi")
    service._data_sources = AsyncMock()
    service._data_sources.fetch.side_effect = fetch
    # Pause failed request while the successful request resets/reads status.
    original_major = service.profile_major
    async def major(user):
        await asyncio.sleep(0)
        return await original_major(user)
    service.profile_major = major
    await asyncio.gather(service.fetch_external_intel("a", topic="failed"),
                         service.fetch_external_intel("b", topic="healthy"))
    assert (await service.intel_fetch_status("a", topic="failed"))["status"] == "failed"
    assert (await service.intel_fetch_status("b", topic="healthy"))["status"] == "empty"


async def test_intel_keeps_partial_results_and_reports_degradation():
    service = intel_service()
    service._data_sources = AsyncMock()
    service._data_sources.fetch.return_value = DataSourceResult(source="xuezhi", degraded=True,
        records=[DataSourceRecord(id="audit", kind="occupation", title="AI", source_url="https://xz.chsi.com.cn/")])
    items = await service.fetch_external_intel("a", topic="AI")
    status = await service.intel_fetch_status("a", topic="AI")
    assert len(items) == 1 and status["status"] == "ok" and status["degraded"]


async def test_web_search_failure_is_not_a_healthy_empty_result():
    service = intel_service()
    service._web_search = AsyncMock()
    service._web_search.search.side_effect = RuntimeError("synthetic outage")
    await service.fetch_external_intel("a", topic="AI")
    assert (await service.intel_fetch_status("a", topic="AI"))["status"] == "failed"


async def test_imported_summary_accepts_an_api_valid_long_term():
    c = _container()
    term = "2025-2026学年第一学期（联合培养与跨校课程安排）"
    assert len(term) <= 40
    result = await c.academic_service.import_("audit-long-term", courses_raw=QZ_SCHEDULE, term=term)
    assert result.courses == 3
    fields = await c.profile_service.get_fields("audit-long-term")
    field = next(f for f in fields if f.key == "courses")
    assert term in field.value


class YieldingSnapshots(InMemoryAcademicSnapshotRepository):
    async def get(self, user_id):
        result = await super().get(user_id)
        await asyncio.sleep(0)
        return result


async def test_concurrent_course_and_grade_imports_preserve_both_inputs():
    snapshots = YieldingSnapshots()
    service = DefaultAcademicService(snapshots, ManualAcademicImporter())
    await asyncio.gather(service.import_("u", courses_raw=QZ_SCHEDULE),
                         service.import_("u", grades_raw=QZ_GRADES))
    saved = await snapshots.get("u")
    assert len(saved.courses) == 3 and len(saved.grades) == 2


async def test_revoke_grades_cannot_overwrite_a_concurrent_course_import():
    snapshots = YieldingSnapshots()
    service = DefaultAcademicService(snapshots, ManualAcademicImporter())
    await service.import_("u", courses_raw=QZ_SCHEDULE, grades_raw=QZ_GRADES)
    await asyncio.gather(service.import_("u", courses_raw=QZ_SCHEDULE.replace("高等数学", "新课程")),
                         service.revoke_grades("u"))
    saved = await snapshots.get("u")
    assert saved.grades == []
    assert saved.courses[0].name == "新课程"


@pytest.mark.parametrize("page", ["<html>请登录</html>", "resultJson: {invalid}", "resultJson: {\"x\": 1"])
def test_xuezhi_broken_or_login_page_is_not_a_successful_empty_detail(page):
    with pytest.raises(RuntimeError):
        _extract_result_json(page)


def test_xuezhi_vocational_mapping_uses_its_actual_top_level_shape():
    detail = {"basicVo": {"zymc": "人工智能技术应用"}, "byfzVo": {},
              "expOccList": {"人工智能工程技术人员": {"zhiyId": "O1", "specOccProportion": "20"}}}
    assert matched_occupations(detail) == [("人工智能工程技术人员", "O1")]
    assert "人工智能工程技术人员" in speciality_text(detail)


async def test_event_retry_after_gateway_failure_is_not_suppressed_as_a_duplicate():
    gateway = AsyncMock()
    gateway.publish.side_effect = [RuntimeError("outbox unavailable"), None]
    bus = GatewayEventBus(gateway)
    event = DomainEvent(event_id="audit-event", event_type="audit", occurred_at=datetime.now(timezone.utc),
                        payload={}, idempotency_key="same-event")
    with pytest.raises(RuntimeError):
        await bus.publish(event)
    await bus.publish(event)
    await bus.publish(event)
    assert gateway.publish.await_count == 2


async def test_same_key_parallel_event_retries_only_publish_one_success():
    gateway = AsyncMock()
    gateway.publish.side_effect = [RuntimeError("outbox unavailable"), None]
    bus = GatewayEventBus(gateway)
    event = DomainEvent(event_id="audit-event", event_type="audit", occurred_at=datetime.now(timezone.utc),
                        payload={}, idempotency_key="same-event")
    outcomes = await asyncio.gather(*(bus.publish(event) for _ in range(5)), return_exceptions=True)
    assert sum(isinstance(outcome, RuntimeError) for outcome in outcomes) == 1
    assert gateway.publish.await_count == 2


async def test_material_ids_never_cross_accounts_with_colliding_cleaned_names(tmp_path):
    store = LocalFileStore(str(tmp_path))
    memory = DefaultConversationMemoryService(InMemoryConversationMemoryRepository(),
        documents=LocalTextExtractor(), object_store=store)
    material = await memory.put_material("audit/account", name="sample.txt", data=b"synthetic audit material")
    own = await memory.material_body("audit/account", material.material_id)
    assert own.text == "synthetic audit material"
    with pytest.raises(LookupError):
        await memory.material_body("audit_account", material.material_id)


async def test_versioned_object_keys_cannot_walk_into_another_user_namespace(tmp_path):
    store = LocalFileStore(str(tmp_path))
    attacker = store.build_key("one/../other", "report", 1, "txt")
    victim = store.build_key("other", "report", 1, "txt")
    await store.put(attacker, b"synthetic attacker value")
    assert await store.stat(victim) is None


def test_user_namespaces_remain_distinct_on_case_insensitive_filesystems(tmp_path):
    store = LocalFileStore(str(tmp_path))
    assert store.build_key("User", "report", 1, "txt").casefold() != store.build_key("user", "report", 1, "txt").casefold()


@pytest.mark.parametrize("encoding", ["utf-8", "gbk"])
async def test_legacy_material_is_migrated_only_after_owner_bound_digest_verification(tmp_path, encoding):
    store = LocalFileStore(str(tmp_path))
    memory = DefaultConversationMemoryService(InMemoryConversationMemoryRepository(),
        documents=LocalTextExtractor(), object_store=store)
    owner, name, text = "old/account", "sample.txt", "合成旧材料"
    material_id = "mat_" + sha256(owner.encode() + b"\0" + name.encode() + b"\0" + text.encode(encoding)).hexdigest()
    old = store.legacy_named_key(owner, "conversation_material", material_id, "txt")
    await store.put(old, json.dumps({"name": name, "text": text}).encode())
    with pytest.raises(LookupError):
        await memory.material_body("old_account", material_id)
    result = await memory.material_body(owner, material_id)
    assert result.text == text
    assert await store.stat(store.build_named_key(owner, "conversation_material", material_id, "txt"))
    assert await store.stat(old)  # No legacy object is removed by this read/migration.


@pytest.mark.parametrize("payload", ["", "[]", "null", "<html>login</html>"])
async def test_xuezhi_invalid_json_shape_is_reported_as_failure(payload):
    client = XueZhiClient()
    client._get_text = AsyncMock(return_value=payload)
    with pytest.raises(RuntimeError):
        await client.search_occupations(name="人工智能")


async def test_failed_major_endpoint_does_not_hide_available_occupation_records():
    from tests.test_data_sources import _StubXueZhiClient
    from zhiyin_infrastructure.xuezhi.gateway import XueZhiDataSourceGateway
    from zhiyin_data_sdk.gateways.datasource import DataSourceRequest

    class Client(_StubXueZhiClient):
        async def list_specialities(self, **kwargs):
            raise RuntimeError("synthetic speciality endpoint failure")

    result = await XueZhiDataSourceGateway(Client()).fetch(DataSourceRequest(source="xuezhi", query="人工智能"))
    assert result.degraded and result.errors
    assert any(r.kind == "occupation" and r.id == "O1" for r in result.records)
