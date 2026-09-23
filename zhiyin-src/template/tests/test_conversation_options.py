"""点选项与手打要分得开：选项的**身份**必须一路传到底。

为什么值得守
-----------
界面上那几个"快速回答"按钮不是随手写的文字，它们是后端上一轮给的
`guide.options`：每条都有稳定的 `option_id` 与机器可读的 `value`。

只把显示文字发回来的后果实测过：用户点了「我现在还在念书」，回包又把同一个问题
连同同一组选项问了一遍 —— 因为模型看到的就是一句话，它不知道那是自己上一轮给的
选项之一，也就没有理由把状态往前推。用户看到的是"点了没反应"。

所以这里钉三件事：

1. 一轮消息**可以**带上选项身份（DTO 收得下，不会 422）；
2. 带上了就**真的送到模型手里**（`prompt_vars.chosen_option`）——
   收下但丢掉，等于什么都没做；
3. 手打的一轮不该凭空多出一个 `chosen_option`（那是"用户选了"的意思，不能猜）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from zhiyin_api.dto.conversation import MessageRequest
from zhiyin_boot import Settings, build_container
from zhiyin_boot.container import Container
from zhiyin_business.policies import (
    DisclosureHandoffPolicy,
    KeywordIntentPolicy,
    RegistryLeadPolicy,
    RuleStagePolicy,
)
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_business.services import DefaultOrchestrator
from zhiyin_orchestration import AgentEngine, AgentRequest, AgentResult

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
USER_ID = "u-option"


@pytest.fixture
def container() -> Container:
    return build_container(
        Settings(
            # 构造真网关不发请求：测试里给一个占位密钥即可。
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
    )


class _RecordingEngine(AgentEngine):
    """引擎桩：只记下这一轮下发的提示词变量，不调模型。"""

    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def invoke(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.agent_id,
            structured={},
            raw_text="先说清楚你现在最卡的是哪一步。",
            valid=True,
        )


def _orchestrator(container: Container, engine: AgentEngine) -> DefaultOrchestrator:
    return DefaultOrchestrator(
        profiles=container.profile_service,
        behaviors=container.behavior_service,
        memories=container.memory_service,
        assets=container.asset_service,
        intent_policy=KeywordIntentPolicy(container.registry_service),
        stage_policy=RuleStagePolicy(container.registry_service),
        lead_policy=RegistryLeadPolicy(container.registry_service),
        handoff_policy=DisclosureHandoffPolicy(),
        agent_engine=engine,
        sessions=container.sessions,
        registry=container.registry_service,
        event_bus=container.event_bus_primitive,
    )


async def _prompt_vars(container: Container, **extra: Any) -> dict[str, Any]:
    engine = _RecordingEngine()
    await _orchestrator(container, engine).handle_message(
        TurnRequest(user_id=USER_ID, task_id="t-option", message="我现在还在念书", **extra)
    )
    return engine.requests[0].prompt_vars


# ------------------------------------------------------------------ DTO


def test_message_request_takes_the_option_identity() -> None:
    """选项身份是**可选**字段：手打的一轮照样合法，点选项的一轮不会被 422 掉。"""
    typed = MessageRequest(task_id="t1", message="我不知道自己适合什么")
    assert typed.option_id is None
    assert typed.option_value is None

    clicked = MessageRequest(
        task_id="t1",
        message="我现在还在念书",
        option_id="o1",
        option_value="studying",
    )
    assert clicked.option_id == "o1"
    assert clicked.option_value == "studying"


# ------------------------------------------------------------------ 编排


async def test_clicked_option_reaches_the_model(container: Container) -> None:
    """点了选项：这一轮的输入变量里要说清"选的是哪一条"。"""
    prompt_vars = await _prompt_vars(
        container,
        option_id="o1",
        option_value="studying",
    )

    chosen = prompt_vars["chosen_option"]
    assert chosen["option_id"] == "o1"
    assert chosen["value"] == "studying"
    # label 也带上：模型读到的是"用户点了『我现在还在念书』"，不是一串机器码
    assert chosen["label"] == "我现在还在念书"


async def test_typed_message_carries_no_chosen_option(container: Container) -> None:
    """手打的一轮不许多出 chosen_option —— 那代表"用户选了"，不能凭一句话猜。"""
    prompt_vars = await _prompt_vars(container)

    assert "chosen_option" not in prompt_vars
