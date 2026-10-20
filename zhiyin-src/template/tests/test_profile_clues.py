"""待验证线索与画像用户控制（《个人画像设计-2026-10-20》第 3.2、7、9 节）。

这一轮补的是设计里此前没落地的三件事，本文件各钉住一组：

1. **待验证线索独立存储**（3.2）：线索与事实字段分开；同一会话整体替换，
   重跑一次分析不会把同一句理解叠成「反复验证过」；读取画像时一起带出来。
2. **依据变化即失效**（7、P21）：用户更正或删除一条画像信息后，依据它的
   「系统理解」标为失效并写明原因 —— 不能继续当结论用；依据无关的线索不受影响。
3. **用户控制**（9、P22、P23）：用户可以直接删除一条画像信息、否认一条
   「系统的理解」；删除后工作台读不到、缓存/资产被标记待核对；两个账号的
   线索互不可见，也不能用别人的 clue id 否认。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhiyin_api.app import API_PREFIX, create_app
from zhiyin_api.facade import reset_facade
from zhiyin_boot import Settings, build_container, wire_application
from zhiyin_business.services.profile import (
    PROFILE_CLUE_DENIED_REASON,
    PROFILE_CLUE_INVALIDATED_BY_CORRECTION,
    PROFILE_CLUE_INVALIDATED_BY_DELETION,
)
from zhiyin_infrastructure.local.auth import DEMO_USER_ID
from zhiyin_kernel.blackboard import ProfileClue
from zhiyin_kernel.enums import ProfileClueStatus, ProfileSource
from zhiyin_kernel.errors import ResourceNotFound

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clue(
    text: str,
    *,
    session_id: str = "s1",
    field_keys: tuple[str, ...] = (),
    evidence: tuple[str, ...] = (),
) -> ProfileClue:
    """一条待写入的线索：id 留空，由服务端生成（只有本来就属于这个会话的 id 才沿用）。"""
    stamp = _now()
    return ProfileClue(
        id="",
        user_id="",
        session_id=session_id,
        text=text,
        evidence=list(evidence),
        field_keys=list(field_keys),
        source=ProfileSource.ASSESSMENT,
        created_at=stamp,
        updated_at=stamp,
    )


async def _profile_service():
    """直接驱动业务服务的那条装配（同一个 container，同一份动态配置）。"""
    from zhiyin_business.services.dynamic_config import load_snapshot

    container = build_container(_settings())
    await load_snapshot(container.registry_service)
    return container.profile_service


def _wired_app(seed=None):
    """按用例先造数据、再启动应用；返回 (container, app, seed 的返回值)。

    为什么先 seed 再进 TestClient：线索没有面向用户的写入接口（写入来自分析链路），
    但否认/删除/展示都是接口行为 —— 所以先在同一个内存仓储里放好线索，再走 HTTP。
    """
    container = build_container(_settings())
    app = wire_application(container)
    seeded = asyncio.run(seed(container)) if seed is not None else None
    return container, app, seeded


# ---------------------------------------------------------------------------
# 线索读写：按会话整体替换、服务端生成标识
# ---------------------------------------------------------------------------


async def test_clues_are_replaced_per_session_without_duplicates() -> None:
    """同一会话整体替换：重跑分析得到那一次的结果，不是把新旧线索堆起来。"""
    profiles = await _profile_service()
    user = "u-clue-replace"

    stored = await profiles.replace_session_clues(
        user,
        "s1",
        [
            _clue("可能更关注机制与原因", field_keys=("interest",)),
            _clue("可能偏好动手实践", field_keys=("experience",)),
        ],
    )
    assert len(stored) == 2
    # 标识、归属、状态都由服务端定
    assert all(item.id for item in stored)
    assert {item.user_id for item in stored} == {user}
    assert {item.session_id for item in stored} == {"s1"}
    assert {item.status for item in stored} == {ProfileClueStatus.PROPOSED}

    # 重跑同一次分析：这条会话只剩这一次的一批（不追加、不重复）
    again = await profiles.replace_session_clues(
        user, "s1", [_clue("可能更关注机制与原因", field_keys=("interest",))]
    )
    clues = await profiles.get_clues(user)
    assert [item.id for item in clues] == [again[0].id]
    assert len(clues) == 1

    # 别的会话不受影响
    await profiles.replace_session_clues(
        user, "s2", [_clue("可能想先了解算法岗", session_id="s2", field_keys=("target_job",))]
    )
    assert {item.session_id for item in await profiles.get_clues(user)} == {"s1", "s2"}
    # 读取整份画像时也带线索（工作台读的是 profile.clues）
    profile = await profiles.get(user)
    assert profile is not None
    assert len(profile.clues) == 2


# ---------------------------------------------------------------------------
# 依据变化 → 线索失效（设计第 7 节、P21）
# ---------------------------------------------------------------------------


async def test_correcting_a_field_invalidates_only_the_clues_that_depend_on_it() -> None:
    """用户更正专业之后，依据专业的理解失效；不相关的理解保持待验证。"""
    profiles = await _profile_service()
    user = "u-clue-correct"
    await profiles.replace_session_clues(
        user,
        "s1",
        [
            _clue("可能更关注机制与原因", field_keys=("major",)),
            _clue("可能喜欢动手实践", field_keys=("interest",)),
        ],
    )

    await profiles.correct_field(user, "major", "计算机大类")

    clues = {item.text: item for item in await profiles.get_clues(user)}
    dependent = clues["可能更关注机制与原因"]
    assert dependent.status is ProfileClueStatus.INVALID
    assert dependent.invalidated_reason == PROFILE_CLUE_INVALIDATED_BY_CORRECTION
    # 无关线索不能被顺手作废：线索失效要按依据命中，不能整份画像一刀切
    assert clues["可能喜欢动手实践"].status is ProfileClueStatus.PROPOSED


async def test_deleting_a_field_removes_it_and_invalidates_related_clues() -> None:
    """删除一条画像信息后：读不到它，依据它的理解失效并写明原因。"""
    profiles = await _profile_service()
    user = "u-clue-drop"
    await profiles.update_field(
        user,
        "major",
        "人工智能",
        confidence=1.0,
        source=ProfileSource.CONVERSATION.value,
        label="专业",
    )
    await profiles.replace_session_clues(
        user, "s1", [_clue("可能更关注机制与原因", field_keys=("major",))]
    )

    await profiles.drop_field(user, "major")

    assert await profiles.get_fields(user) == []
    clue = (await profiles.get_clues(user))[0]
    assert clue.status is ProfileClueStatus.INVALID
    assert clue.invalidated_reason == PROFILE_CLUE_INVALIDATED_BY_DELETION


async def test_denying_a_clue_keeps_the_others_and_is_idempotent() -> None:
    """否认一条理解：只失效这一条，重复否认不报错，未知 id 明确报不存在。"""
    profiles = await _profile_service()
    user = "u-clue-deny"
    stored = await profiles.replace_session_clues(
        user,
        "s1",
        [_clue("可能适合算法工程师"), _clue("可能喜欢机制与原因")],
    )

    denied = await profiles.deny_clue(user, stored[0].id)
    assert denied.status is ProfileClueStatus.INVALID
    assert denied.invalidated_reason == PROFILE_CLUE_DENIED_REASON

    clues = await profiles.get_clues(user)
    assert len(clues) == 2
    assert [item.id for item in clues if item.status is ProfileClueStatus.PROPOSED] == [
        stored[1].id
    ]

    # 幂等：重复否认仍是成功，且不改写第一次的原因
    again = await profiles.deny_clue(user, stored[0].id)
    assert again.status is ProfileClueStatus.INVALID
    assert again.invalidated_reason == PROFILE_CLUE_DENIED_REASON

    with pytest.raises(ResourceNotFound):
        await profiles.deny_clue(user, "clue_not_exists")


# ---------------------------------------------------------------------------
# 账号隔离（P23）
# ---------------------------------------------------------------------------


async def test_two_users_do_not_see_or_deny_each_others_clues() -> None:
    profiles = await _profile_service()
    first = await profiles.replace_session_clues(
        "u-clue-a", "s1", [_clue("A 的理解", field_keys=("major",))]
    )
    await profiles.replace_session_clues("u-clue-b", "s1", [_clue("B 的理解")])

    assert {item.text for item in await profiles.get_clues("u-clue-a")} == {"A 的理解"}
    assert {item.text for item in await profiles.get_clues("u-clue-b")} == {"B 的理解"}

    # 用别人的 clue id 否认：按"不存在"处理（不能泄露它属于谁，也不能改到它）
    with pytest.raises(ResourceNotFound):
        await profiles.deny_clue("u-clue-b", first[0].id)
    assert [item.status for item in await profiles.get_clues("u-clue-a")] == [
        ProfileClueStatus.PROPOSED
    ]


# ---------------------------------------------------------------------------
# 接口：展示 / 否认 / 删除
# ---------------------------------------------------------------------------


def test_workspace_panel_exposes_clues_separately_from_fields() -> None:
    """工作台把线索放在 profile_panel.clues：与 fields 分开，形状可直接渲染。"""

    async def seed(container) -> None:
        await container.profile_service.replace_session_clues(
            DEMO_USER_ID,
            "s1",
            [_clue("可能更关注机制与原因", field_keys=("interest",), evidence=("我想弄清原因",))],
        )

    _, app, _ = _wired_app(seed)
    with TestClient(app) as client:
        data = client.get(f"{API_PREFIX}/app/workspace").json()["data"]

    panel = data["profile_panel"]
    assert panel["fields"] == []
    assert len(panel["clues"]) == 1
    clue = panel["clues"][0]
    assert clue["text"] == "可能更关注机制与原因"
    assert clue["status"] == "proposed"
    assert clue["field_keys"] == ["interest"]
    assert clue["evidence"] == ["我想弄清原因"]
    assert clue["invalidated_reason"] == ""
    assert clue["id"] and clue["created_at"] and clue["updated_at"]


def test_deny_clue_endpoint_marks_it_invalid() -> None:
    """DELETE /app/profile/clues/{id}：回执是 id，再读工作台看到"已否认 + 原因"。"""
    seeded: dict[str, str] = {}

    async def seed(container) -> None:
        stored = await container.profile_service.replace_session_clues(
            DEMO_USER_ID, "s1", [_clue("可能适合算法工程师")]
        )
        seeded["id"] = stored[0].id

    _, app, _ = _wired_app(seed)
    with TestClient(app) as client:
        response = client.delete(f"{API_PREFIX}/app/profile/clues/{seeded['id']}")
        assert response.status_code == 200, response.text
        assert response.json()["data"] == {"denied": seeded["id"]}

        # 幂等：再点一次仍然成功
        again = client.delete(f"{API_PREFIX}/app/profile/clues/{seeded['id']}")
        assert again.status_code == 200

        data = client.get(f"{API_PREFIX}/app/workspace").json()["data"]
        clue = next(
            item for item in data["profile_panel"]["clues"] if item["id"] == seeded["id"]
        )
        assert clue["status"] == "invalid"
        assert clue["invalidated_reason"] == PROFILE_CLUE_DENIED_REASON

        missing = client.delete(f"{API_PREFIX}/app/profile/clues/clue_missing")
        assert missing.status_code == 404
        assert missing.json()["code"] == 1002


def test_delete_field_endpoint_removes_it_from_the_workspace() -> None:
    """DELETE /app/profile/fields/{key}：删完工作台读不到这一格。"""

    async def seed(container) -> None:
        await container.profile_service.update_field(
            DEMO_USER_ID,
            "major",
            "人工智能",
            confidence=1.0,
            source=ProfileSource.CONVERSATION.value,
            label="专业",
        )

    _, app, _ = _wired_app(seed)
    with TestClient(app) as client:
        # 删之前读得到
        before = client.get(f"{API_PREFIX}/app/workspace").json()["data"]
        assert "major" in {item["key"] for item in before["profile_panel"]["fields"]}

        response = client.delete(f"{API_PREFIX}/app/profile/fields/major")
        assert response.status_code == 200, response.text
        assert response.json()["data"] == {"deleted": "major"}

        after = client.get(f"{API_PREFIX}/app/workspace").json()["data"]
        assert "major" not in {item["key"] for item in after["profile_panel"]["fields"]}


def test_delete_field_endpoint_rejects_a_stale_version() -> None:
    """带"我看到的是哪一版"删除：版本对不上按冲突（409/1003）返回，不静默删。"""

    async def seed(container) -> datetime:
        service = container.profile_service
        await service.update_field(
            DEMO_USER_ID,
            "interest",
            "调试程序",
            confidence=1.0,
            source=ProfileSource.CONVERSATION.value,
        )
        stale = (await service.get_fields(DEMO_USER_ID, ["interest"]))[0].updated_at
        await service.update_field(
            DEMO_USER_ID,
            "interest",
            "动手实践",
            confidence=1.0,
            source=ProfileSource.CONVERSATION.value,
        )
        return stale

    container, app, stale = _wired_app(seed)
    with TestClient(app) as client:
        response = client.delete(
            f"{API_PREFIX}/app/profile/fields/interest",
            params={"expected_updated_at": stale.isoformat()},
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == 1003

        # 冲突之后这一格仍然在，也没有被悄悄删掉（兴趣是多值，规范成列表）
        data = client.get(f"{API_PREFIX}/app/workspace").json()["data"]
        kept = {item["key"]: item for item in data["profile_panel"]["fields"]}
        assert kept["interest"]["value"] == ["动手实践"]


def test_endpoints_degrade_when_the_facade_is_missing() -> None:
    """裸 app（未装配门面）按 1007 降级，而不是 500 —— 与其它接口同一条口径。"""
    reset_facade()
    with TestClient(create_app()) as bare:
        denied = bare.delete(f"{API_PREFIX}/app/profile/clues/clue-1")
        deleted = bare.delete(f"{API_PREFIX}/app/profile/fields/major")
    assert denied.status_code == 503
    assert denied.json()["code"] == 1007
    assert deleted.status_code == 503
    assert deleted.json()["code"] == 1007
