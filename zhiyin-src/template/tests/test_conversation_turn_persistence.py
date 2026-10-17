"""用户这一轮先落库：模型失败/中途停止时，刚发的那句话不能凭空消失。

2026-10-18 报障"没保存会话记录"的一条真实路径：发消息后刷新/点停止，
后端还在等模型，轮末的 `_remember_turn` 没走到 —— 修复前刷新后这句话没了。
"""

from __future__ import annotations

import pytest

from tests.test_conversation_asset_confirmation import Engine, send, setup


class BoomEngine(Engine):
    async def invoke(self, request):
        raise RuntimeError("模型超时")


@pytest.mark.asyncio
async def test_user_message_survives_model_failure() -> None:
    c, _, session = await setup()
    c.orchestrator._agent_engine = BoomEngine()
    with pytest.raises(RuntimeError):
        await send(c, session, "这句话发完模型就失败了，也要留在历史里。")
    turns = await c.memory_service.list_turns("u1", session.id)
    assert [turn.role for turn in turns] == ["user"], "失败时至少保住用户这句话"
    assert turns[0].text == "这句话发完模型就失败了，也要留在历史里。"


@pytest.mark.asyncio
async def test_user_message_is_not_written_twice_on_success() -> None:
    c, _, session = await setup()
    await send(c, session, "正常一轮")
    turns = await c.memory_service.list_turns("u1", session.id)
    user_turns = [turn for turn in turns if turn.role == "user"]
    assert len(user_turns) == 1, "成功的一轮也只能有一条用户消息"
    assert len(turns) >= 2, "主理回复仍要落库"
