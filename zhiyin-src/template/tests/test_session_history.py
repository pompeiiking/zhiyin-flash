"""历史会话：列表口径、当前会话、新建会话不串。

2026-10-18 报障：历史会话点开是空的 / 刷新后回到主题选择页 / 新建咨询又回到旧会话。
锁住三件事：
1. 空会话不进历史（否则"刷新后恢复最近会话"会挑中它，看起来像记录丢了）；
2. current_task_id 指向最近一条**有内容**的会话；
3. new_session 真能开新会话，旧会话仍留在历史里可打开。
"""

from __future__ import annotations

import pytest

from zhiyin_kernel.enums import LoopStage, TaskStatus


def _facade():
    from tests.e2e.test_main_path import _container
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)
    return container


async def _record(container, user_id: str, task_id: str, text: str) -> None:
    # Windows 系统时钟粒度约 15.6ms：连续两次写入可能拿到同一个 created_at。
    # 排序键要能区分"先说的"和"后说的"，测试里主动隔开一个时钟 tick。
    import asyncio

    await container.memory_service.record_turn(
        user_id,
        task_id,
        role="user",
        text=text,
        loop_stage=LoopStage.COLLECT,
        client_msg_id=f"m-{task_id}-{abs(hash(text)) % 100000}",
    )
    await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_empty_sessions_are_not_listed_and_current_points_to_content() -> None:
    from zhiyin_api.dto.conversation import TaskEnterRequest

    container = _facade()
    facade = container.facade
    user = "u-history-empty"

    filled = await facade.enter_task(user, TaskEnterRequest(task_code="confused"))
    await _record(container, user, filled.task_id, "我学汉语言文学，喜欢写东西。")
    await _record(container, user, filled.task_id, "我想试试内容运营。")
    # 只点了主题、一句话没说的空会话
    empty = await facade.enter_task(user, TaskEnterRequest(task_code="verify_direction"))

    listing = await facade.list_sessions(user)
    ids = [item.task_id for item in listing.sessions]
    assert filled.task_id in ids
    assert empty.task_id not in ids, "空会话不能出现在历史里"
    assert listing.current_task_id == filled.task_id
    filled_view = next(item for item in listing.sessions if item.task_id == filled.task_id)
    assert filled_view.message_count == 2
    assert "内容运营" in (filled_view.last_message or "")
    assert filled_view.last_message_at is not None


@pytest.mark.asyncio
async def test_new_session_creates_fresh_one_and_keeps_old_history() -> None:
    from zhiyin_api.dto.conversation import TaskEnterRequest

    container = _facade()
    facade = container.facade
    user = "u-history-new"

    old = await facade.enter_task(user, TaskEnterRequest(task_code="confused"))
    await _record(container, user, old.task_id, "旧会话里说过的话。")

    new = await facade.enter_task(
        user, TaskEnterRequest(task_code="confused", new_session=True)
    )
    assert new.task_id != old.task_id, "new_session 必须开一条新会话"
    await _record(container, user, new.task_id, "新会话里说过的话。")

    listing = await facade.list_sessions(user)
    ids = [item.task_id for item in listing.sessions]
    assert new.task_id in ids and old.task_id in ids, "旧会话仍应留在历史里"
    assert listing.current_task_id == new.task_id
    by_id = {item.task_id: item for item in listing.sessions}
    assert by_id[old.task_id].status is TaskStatus.COMPLETED
    assert by_id[new.task_id].status is TaskStatus.ACTIVE
    # 旧会话内容仍可读：点开历史不是空屏
    old_turns = await facade.list_session_turns(user, old.task_id)
    assert [turn.text for turn in old_turns] == ["旧会话里说过的话。"]
    # 再次进入同一入口 = 续接新会话，而不是旧会话
    resumed = await facade.enter_task(user, TaskEnterRequest(task_code="confused"))
    assert resumed.task_id == new.task_id


@pytest.mark.asyncio
async def test_new_session_does_not_affect_other_task_codes() -> None:
    from zhiyin_api.dto.conversation import TaskEnterRequest

    container = _facade()
    facade = container.facade
    user = "u-history-other"

    first = await facade.enter_task(user, TaskEnterRequest(task_code="confused"))
    await _record(container, user, first.task_id, "第一条。")
    other = await facade.enter_task(user, TaskEnterRequest(task_code="verify_direction"))
    await _record(container, user, other.task_id, "另一条。")

    fresh = await facade.enter_task(
        user, TaskEnterRequest(task_code="confused", new_session=True)
    )
    await _record(container, user, fresh.task_id, "第三条。")

    listing = await facade.list_sessions(user)
    by_id = {item.task_id: item for item in listing.sessions}
    assert by_id[other.task_id].status is TaskStatus.ACTIVE, "别的入口不能被顺手结束"
    assert by_id[first.task_id].status is TaskStatus.COMPLETED
