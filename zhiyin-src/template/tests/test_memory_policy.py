"""记忆策略持久化回归（《个人画像设计-2026-10-20》5.2 节、验收 P13–P18）。

锁住四件事：

1. 账号级 / 会话级开关除了写旧字段，还要留下**带来源、时间、范围**的策略记录；
2. “这条不要记录”既支持按字段键（兼容旧 ``conversation_forgotten_keys``），
   也支持按内容指纹，且不扩大成整个账号都不能记录；
3. 自动写入前由服务端读取有效策略并给出给学生看的原因；
4. 所有更新都是账号状态上的原子读改写，不覆盖偏好 / 其他会话 / 其他用户。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from zhiyin_business.contracts.student import Preferences, PreferencesEdit
from zhiyin_business.services.asset import DefaultAssetService
from zhiyin_business.services.conversation_control import ConversationControl
from zhiyin_business.services.memory_policy import (
    POLICY_FIELDS,
    MemoryPolicyService,
    snapshot_from_state,
)
from zhiyin_business.services.student import StudentService
from zhiyin_infrastructure.local.repository import (
    InMemoryAcademicSnapshotRepository,
    InMemoryAssetRepository,
    InMemoryNotificationRepository,
    InMemoryTaskSessionRepository,
)
from zhiyin_infrastructure.local.student import InMemoryStudentStateRepository
from zhiyin_kernel.blackboard import TaskSession
from zhiyin_kernel.enums import LoopStage
from zhiyin_kernel.errors import InvalidRequest

USER = "u-memory-policy"


@pytest.fixture
def state() -> InMemoryStudentStateRepository:
    return InMemoryStudentStateRepository()


@pytest.fixture
def policy(state: InMemoryStudentStateRepository) -> MemoryPolicyService:
    return MemoryPolicyService(state)


def _session(session_id: str = "s1", user_id: str = USER) -> TaskSession:
    now = datetime.now(timezone.utc)
    return TaskSession(
        id=session_id,
        user_id=user_id,
        task_code="free_chat",
        task_name="咨询对话",
        loop_stage=LoopStage.COLLECT,
        lead_agent="coach",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# 账号级 / 会话级：旧字段 + 策略记录
# ---------------------------------------------------------------------------


async def test_account_switch_records_source_time_and_scope(policy, state) -> None:
    record = await policy.set_account_automatic(USER, False, note="以后不自动记录")
    assert record["scope"] == "account"
    assert record["target"] == "automatic_memory"
    assert record["value"] is False
    assert record["source"] == "user_setting"
    assert record["note"] == "以后不自动记录"
    assert record["session_id"] == ""
    assert record["id"].startswith("mp_")
    # 记录字段是固定的合同：有来源、有时间、可回读。
    assert set(record) == set(POLICY_FIELDS)
    assert datetime.fromisoformat(record["created_at"]).tzinfo is not None

    snapshot = await policy.snapshot(USER)
    assert snapshot["account_automatic"] is False
    assert snapshot["policies"] == [record]

    raw = await state.get(USER)
    assert raw["preferences"]["automatic_memory"] is False


async def test_session_switch_only_affects_that_session(policy, state) -> None:
    record = await policy.set_session_temporary(USER, "s1", True, note="临时会话")
    assert record["scope"] == "session"
    assert record["target"] == "temporary"
    assert record["session_id"] == "s1"
    assert record["source"] == "user_setting"

    assert (await policy.snapshot(USER, "s1"))["session_temporary"] is True
    assert (await policy.snapshot(USER, "s2"))["session_temporary"] is False
    raw = await state.get(USER)
    assert raw["conversation_settings"]["s1"]["temporary"] is True
    assert "s2" not in raw["conversation_settings"]

    with pytest.raises(InvalidRequest):
        await policy.set_session_temporary(USER, "", True)


# ---------------------------------------------------------------------------
# 按内容拒绝：键级 / 内容级
# ---------------------------------------------------------------------------


async def test_deny_key_blocks_only_that_key_and_keeps_legacy_field(policy, state) -> None:
    record = await policy.deny_key(USER, "major", note="这条不要记录")
    assert record["scope"] == "content"
    assert record["target"] == "major"
    assert record["source"] == "conversation"

    snapshot = await policy.snapshot(USER, "s1")
    assert snapshot["denied_keys"] == ["major"]
    assert snapshot["content_denials"] == []
    raw = await state.get(USER)
    assert raw["conversation_forgotten_keys"] == ["major"]

    allowed, reason = await policy.check_auto_write(USER, "s1", "major")
    assert allowed is False
    assert "重新保存" in reason
    # 其他合法记录不受无关扩大限制。
    assert (await policy.check_auto_write(USER, "s1", "interest")) == (True, "")


async def test_deny_content_blocks_only_matching_fingerprint(policy) -> None:
    record = await policy.deny_content(USER, "fp-message-1", note="这段不要记录")
    assert record["scope"] == "content"
    assert record["target"] == "fp-message-1"

    snapshot = await policy.snapshot(USER)
    assert snapshot["content_denials"] == ["fp-message-1"]
    # 内容拒绝不写旧字段：它不是“这一格以后都不能写”。
    assert snapshot["denied_keys"] == []
    assert (await policy.check_auto_write(USER, "", "interest", "fp-message-1")) == (
        False,
        "你说过这条内容不要记录，它不会被自动保存。",
    )
    assert (await policy.check_auto_write(USER, "", "interest", "fp-message-2")) == (
        True,
        "",
    )

    with pytest.raises(InvalidRequest):
        await policy.deny_content(USER, "  ")


# ---------------------------------------------------------------------------
# 自动写入前的服务端检查
# ---------------------------------------------------------------------------


async def test_check_auto_write_reads_account_session_and_content_policies(policy) -> None:
    assert await policy.check_auto_write(USER, "s1", "major") == (True, "")

    await policy.set_session_temporary(USER, "s1", True)
    allowed, reason = await policy.check_auto_write(USER, "s1", "major")
    assert allowed is False and "临时会话" in reason
    assert await policy.check_auto_write(USER, "s2", "major") == (True, "")

    await policy.set_account_automatic(USER, False)
    allowed, reason = await policy.check_auto_write(USER, "s2", "major")
    assert allowed is False and "自动记忆" in reason

    # 账号级重新开启后，仍按会话 / 内容范围分别限制。
    await policy.set_account_automatic(USER, True)
    await policy.deny_key(USER, "major")
    assert (await policy.check_auto_write(USER, "s2", "major"))[0] is False
    assert (await policy.check_auto_write(USER, "s2", "interest"))[0] is True


# ---------------------------------------------------------------------------
# 快照与原子更新：不覆盖其他字段 / 不串用户
# ---------------------------------------------------------------------------


async def test_updates_are_atomic_and_preserve_unrelated_state(policy, state) -> None:
    def seed(current):
        current["preferences"] = {
            "automatic_memory": True,
            "proactive_reminders": False,
            "quiet_start": "22:00",
        }
        current["conversation_settings"] = {"s1": {"temporary": False, "other": 1}}
        current["conversation_forgotten_keys"] = ["old_key"]
        current["record_policies"] = [
            {"id": "mp_existing", "scope": "account", "target": "automatic_memory",
             "value": True, "source": "user_setting", "note": "", "session_id": "",
             "created_at": "2026-10-01T00:00:00+00:00"}
        ]
        return current

    await state.update(USER, seed)
    await policy.set_account_automatic(USER, False)
    await policy.deny_key(USER, "major")
    await policy.set_session_temporary(USER, "s2", True)

    raw = await state.get(USER)
    assert raw["preferences"]["proactive_reminders"] is False
    assert raw["preferences"]["quiet_start"] == "22:00"
    assert raw["conversation_settings"]["s1"] == {"temporary": False, "other": 1}
    assert raw["conversation_settings"]["s2"]["temporary"] is True
    assert raw["conversation_forgotten_keys"] == ["major", "old_key"]
    assert [item["id"] for item in raw["record_policies"]][0] == "mp_existing"
    assert len(raw["record_policies"]) == 4


async def test_users_do_not_read_each_others_policies(policy) -> None:
    await policy.set_account_automatic("u-a", False)
    await policy.deny_key("u-a", "major")

    other = await policy.snapshot("u-b", "s1")
    assert other == {
        "account_automatic": True,
        "session_temporary": False,
        "single_only": False,
        "single_keys": [],
        "denied_keys": [],
        "content_denials": [],
        "policies": [],
    }
    assert await policy.check_auto_write("u-b", "s1", "major") == (True, "")


# ---------------------------------------------------------------------------
# 业务接入：保存偏好时同步账号级记录（不改返回结构）
# ---------------------------------------------------------------------------


def _student_service(state: InMemoryStudentStateRepository) -> StudentService:
    assets = InMemoryAssetRepository()
    return StudentService(
        state=state,
        assets=assets,
        asset_service=DefaultAssetService(
            assets, AsyncMock(), None, student_state=state
        ),
        notifications=InMemoryNotificationRepository(),
        academic=InMemoryAcademicSnapshotRepository(),
        sessions=InMemoryTaskSessionRepository(),
    )


async def test_save_preferences_records_account_policy(state) -> None:
    service = _student_service(state)
    base = await service.preferences(USER)
    body = PreferencesEdit(**base.model_dump(), expected=base).model_copy(
        update={"automatic_memory": False}
    )

    saved = await service.save_preferences(USER, body)
    assert isinstance(saved, Preferences)
    assert saved.automatic_memory is False

    raw = await state.get(USER)
    assert raw["preferences"]["automatic_memory"] is False
    assert len(raw["record_policies"]) == 1
    record = raw["record_policies"][0]
    assert record["scope"] == "account"
    assert record["value"] is False
    assert record["source"] == "user_setting"
    assert record["note"]

    # 保存无关偏好时也同步一条记录：策略状态与这一次保存的值一致。
    body = PreferencesEdit(**saved.model_dump(), expected=saved).model_copy(
        update={"material_analysis": False}
    )
    await service.save_preferences(USER, body)
    raw = await state.get(USER)
    assert len(raw["record_policies"]) == 2
    assert raw["record_policies"][-1]["value"] is False


# ---------------------------------------------------------------------------
# 业务接入：会话设置 PATCH 走统一策略记录，响应形状不变
# ---------------------------------------------------------------------------


class _Owner:
    """Session control 需要的最小持有者：账号状态 + 会话仓储。"""

    def __init__(self, state: InMemoryStudentStateRepository) -> None:
        self._student_state = state
        self._sessions = InMemoryTaskSessionRepository()


async def test_conversation_settings_patch_records_policy_and_keeps_response_shape(
    state,
) -> None:
    owner = _Owner(state)
    await owner._sessions.create(_session("s1"))
    control = ConversationControl(owner)

    response = await control.read(USER, "s1", settings={"temporary": True})
    assert response["settings"] == {"temporary": True}
    assert response["runs"] == [] and response["actions"] == []

    snapshot = await MemoryPolicyService(state).snapshot(USER, "s1")
    assert snapshot["session_temporary"] is True
    assert snapshot["policies"][-1]["scope"] == "session"
    assert snapshot["policies"][-1]["source"] == "user_setting"

    response = await control.read(USER, "s1", settings={"temporary": False})
    assert response["settings"] == {"temporary": False}

    with pytest.raises(InvalidRequest):
        await control.read(USER, "s1", settings={"temporary": "yes"})
    with pytest.raises(InvalidRequest):
        await control.read(USER, "s1", settings={"unknown": True})


# ---------------------------------------------------------------------------
# 纯函数快照：坏数据不拖垮其他设置
# ---------------------------------------------------------------------------


def test_snapshot_ignores_corrupt_policy_entries() -> None:
    snapshot = snapshot_from_state(
        {
            "preferences": {"automatic_memory": False},
            "record_policies": ["bad", {"scope": "content", "target": "fp-1"}],
        },
        "missing-session",
    )
    assert snapshot["account_automatic"] is False
    assert snapshot["session_temporary"] is False
    assert snapshot["content_denials"] == ["fp-1"]
    assert len(snapshot["policies"]) == 1


async def test_writes_recover_from_corrupt_legacy_state(state) -> None:
    """旧 payload 里的坏形状不该让策略写入抛错，也不能把拒绝键拆成单个字符。"""

    def seed(current):
        current["record_policies"] = "broken"
        current["conversation_forgotten_keys"] = "major"
        current["preferences"] = "broken"
        current["conversation_settings"] = "broken"
        return current

    await state.update(USER, seed)
    service = MemoryPolicyService(state)
    assert (await service.snapshot(USER, "s1"))["session_temporary"] is False
    await service.set_account_automatic(USER, False)
    await service.deny_key(USER, "interest")

    raw = await state.get(USER)
    assert raw["preferences"]["automatic_memory"] is False
    assert raw["conversation_forgotten_keys"] == ["interest"]
    snapshot = await service.snapshot(USER)
    assert len(snapshot["policies"]) == 2
    assert snapshot["denied_keys"] == ["interest"]
    assert snapshot["account_automatic"] is False
