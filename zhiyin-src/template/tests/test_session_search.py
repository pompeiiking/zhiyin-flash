"""历史会话全文检索（2026-10-25 用户要求 B 方案）的回归。

链路：逐轮原文仓储 search_by_text → 记忆服务 → facade.search_sessions
→ GET /app/sessions/search。命中会话带片段（原文窗口），标题命中的
会话也在结果里；逐轮仓储不支持检索时退化为只搜标题。
"""

from __future__ import annotations

import pytest

from tests.e2e.test_main_path import _container


@pytest.mark.asyncio
async def test_session_search_matches_turn_text_and_returns_snippet():
    c = _container()
    from zhiyin_business.services.dynamic_config import load_snapshot
    await load_snapshot(c.registry_service)
    session = await c.orchestrator.enter_task("u1", "free_chat")
    await c.memory_service.record_turn("u1", session.id, role="user",
        text="我想了解算法工程师需要准备什么", loop_stage=session.loop_stage,
        client_msg_id="m1")
    await c.memory_service.record_turn("u1", session.id, role="agent",
        text="可以先从你的项目经历聊起。", loop_stage=session.loop_stage,
        client_msg_id="m2")

    view = await c.facade.search_sessions("u1", "算法工程师")
    matched = [s for s in view.sessions if s.task_id == session.id]
    assert len(matched) == 1, "正文命中的会话必须在结果里"
    snippet = (view.matches or {}).get(session.id, "")
    assert "算法工程师" in snippet
    assert snippet.strip() != "算法工程师", "片段应是原文窗口，不是只有关键词"

    # 不命中的关键词：空结果
    empty = await c.facade.search_sessions("u1", "不存在的关键词")
    assert not empty.sessions


@pytest.mark.asyncio
async def test_session_search_title_match_without_text_hit():
    c = _container()
    from zhiyin_business.services.dynamic_config import load_snapshot
    await load_snapshot(c.registry_service)
    session = await c.orchestrator.enter_task("u1", "free_chat")
    await c.memory_service.record_turn("u1", session.id, role="user",
        text="随便聊聊", loop_stage=session.loop_stage,
        client_msg_id="m1")
    await c.workspace_service.rename_session("u1", session.id, "考研方向梳理")

    view = await c.facade.search_sessions("u1", "考研")
    assert [s.task_id for s in view.sessions] == [session.id]
    # 标题命中、正文未命中：没有片段，前端回退显示最后一句
    assert (view.matches or {}).get(session.id) is None


@pytest.mark.asyncio
async def test_session_search_empty_keyword_returns_full_list():
    c = _container()
    from zhiyin_business.services.dynamic_config import load_snapshot
    await load_snapshot(c.registry_service)
    session = await c.orchestrator.enter_task("u1", "free_chat")
    await c.memory_service.record_turn("u1", session.id, role="user",
        text="想了解算法工程师", loop_stage=session.loop_stage,
        client_msg_id="m1")

    plain = await c.facade.list_sessions("u1")
    searched = await c.facade.search_sessions("u1", "  ")
    assert [s.task_id for s in searched.sessions] == [s.task_id for s in plain.sessions]
    assert searched.matches is None
