"""同一条消息重发不该再跑一遍模型。

背景：前端每条消息都带 `client_msg_id`（`c${Date.now()}`），而这条链路上
**从来没有人读它** —— 双击发送、断网重试都会变成两条轮次 + 两次模型调用：
记录里多一段重复的往返，用户白等一次，钱也白花一次。设计文档 9.3 第 1 步
写的就是"重复消息直接返回上次结果，不重复扣费"。

这里钉三件事：

1. 同一个幂等键 → 不再调用模型，返回上次的原文；
2. 换一个幂等键（用户真的又说了同样的话）→ 照常处理；
3. 没有幂等键（老客户端 / 内部调用）→ 照常处理，不会把消息吞掉。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_boot import Settings, build_container
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_orchestration.agent import AgentEngine, AgentRequest, AgentResult

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"


def _settings() -> Settings:
    return Settings(
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


PAYLOAD = {
    "conclusion": "你说你是学计算机的，这条我记下了。",
    "field_updates": [],
    "remaining_gaps": [],
    "confidence_overall": 0.5,
    "ready_to_handoff": False,
    "guide": {"kind": "question", "text": "下一句问这个", "question": "你做过什么？"},
}


class _CountingEngine(AgentEngine):
    """数一数模型被调了几次。"""

    def __init__(self) -> None:
        self.calls = 0

    async def invoke(self, request: AgentRequest) -> AgentResult:
        self.calls += 1
        return AgentResult(
            agent_id=request.agent_id,
            structured=dict(PAYLOAD),
            valid=True,
        )


@pytest.mark.asyncio
async def test_the_same_message_is_answered_from_the_record() -> None:
    container = build_container(_settings())
    engine = _CountingEngine()
    container.orchestrator._agent_engine = engine  # noqa: SLF001 - 换掉真模型，数调用
    user = "u-idem"

    session = await container.orchestrator.enter_task(user, "confused")
    first = await container.orchestrator.handle_message(
        TurnRequest(
            user_id=user,
            task_id=session.id,
            message="我是学计算机的",
            client_msg_id="c-1",
        )
    )
    assert engine.calls == 1

    # 同一条消息重发：不该再花一次模型调用
    again = await container.orchestrator.handle_message(
        TurnRequest(
            user_id=user,
            task_id=session.id,
            message="我是学计算机的",
            client_msg_id="c-1",
        )
    )
    assert engine.calls == 1, "重复消息又跑了一遍模型：用户白等、账单翻倍"
    assert again.messages[0].text == first.messages[0].text, "重发要返回上次那句原文"
    # 重放不带"下一步"：再推一次同一个问题，用户会以为又发生了什么
    assert not again.guide.question

    # 换一个键 = 用户真的又说了一遍，照常处理
    await container.orchestrator.handle_message(
        TurnRequest(
            user_id=user,
            task_id=session.id,
            message="我是学计算机的",
            client_msg_id="c-2",
        )
    )
    assert engine.calls == 2

    # 没带键（内部调用 / 老客户端）照常处理，不能被吞掉
    await container.orchestrator.handle_message(
        TurnRequest(user_id=user, task_id=session.id, message="你好")
    )
    assert engine.calls == 3


@pytest.mark.asyncio
async def test_a_repeated_message_leaves_no_extra_turns() -> None:
    """重复消息不该在会话历史里留下第二段往返。"""
    container = build_container(_settings())
    container.orchestrator._agent_engine = _CountingEngine()  # noqa: SLF001
    user = "u-idem-turns"

    session = await container.orchestrator.enter_task(user, "confused")
    for _ in range(3):
        await container.orchestrator.handle_message(
            TurnRequest(
                user_id=user,
                task_id=session.id,
                message="我是学计算机的",
                client_msg_id="same",
            )
        )

    turns = await container.memory_service.list_turns(user, session.id)
    assert len(turns) == 2, f"一次提问该只留两轮（他 + 主理），现在是 {len(turns)} 轮"
