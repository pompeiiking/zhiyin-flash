"""对话得像在跟人说话：**先接住他刚说的那句**，而不是接着念自己的提纲。

背景（一次真实的用户反馈：跟智能体对话，他说的话感觉像做梦一样，根本没有对话性）：

模型是通的、角色提示词也齐，但两件事一起把它变成了「对着空气说话」：

1. **它看不到对话。** 每轮给模型的上下文只有「用户这一句 + 黑板快照」，而黑板里的
   `memories.summary` 是历次**产出的 JSON 原文**拼接，越到后面越像一坨内部数据 ——
   上一轮它自己问了什么、用户答了什么，一个字都没有。于是它接不上话，也认不出
   「这条上一轮已经问过了」。逐轮原文其实一直在落库（`biz_conversation_turn`），
   只是从来没有回灌给模型。
2. **它说的话被换掉了。** 四个环节（①③④⑤）的产出契约里没有「对他说的一句话结论」
   这个字段，`_user_facing_text` 因此落到 `guide.text` —— 而收尾规范定义 guide.text
   写的是「为什么现在问这个」。用户读到的每一句都是「我为什么要问你」，而不是
   「我看到了什么」。实测连问三轮，气泡里依次是「先定你现在站在哪一步…」
   「差距有几条，先动哪一条得你点头」这一类的句子：每句都像那么回事，没有一句在回他。

这里把两件事都钉住：契约必须给结论留位置；模型必须拿到最近几条对话。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_boot import Settings, build_container
from zhiyin_business.contracts import STAGE_CONTRACTS
from zhiyin_business.contracts.common import BehaviorGuide
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_business.services.orchestrator import _single_line, _user_facing_text
from zhiyin_kernel.enums import LoopStage
from zhiyin_orchestration.agent import AgentEngine, AgentRequest, AgentResult

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"


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


class _RecordingEngine(AgentEngine):
    """引擎替身：把这一轮真正给模型的输入留下来。"""

    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def invoke(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.agent_id,
            structured={"conclusion": "你说想找互联网方向，这条我记下了。"},
            valid=True,
        )


# ---------------------------------------------------------------------------
# 1. 结论必须有落点
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", list(LoopStage))
def test_every_stage_has_a_place_for_the_spoken_line(stage: LoopStage) -> None:
    """五个环节的契约里都要有 `conclusion`（那一句人话的落点）。

    但**不硬性必填** —— 这一条改过口径，理由是代价：
    必填意味着模型偶尔漏一次就"整轮作废"，于是用户刚说的那段话、画像该落的那几个字段
    一起丢掉，他还要重说一遍。宁可偶尔退到 guide 那句话（现在的 guide 也要求是人话），
    也不要丢掉数据。

    只加给其中几个不行：漏掉的那一环，气泡又只剩 guide，用户在那个环节突然又听不懂人话。
    """
    schema = STAGE_CONTRACTS[stage].model_json_schema()
    assert "conclusion" in schema.get("properties", {}), stage
    assert "conclusion" not in schema.get("required", []), (
        f"{stage} 的 conclusion 又变成必填了 —— 硬性必填会让漏一次字段就整轮作废、丢数据"
    )
    assert "guide" not in schema.get("required", []), (
        f"{stage} 的 guide 是必填 —— 没想好下一步时应当允许它给 null"
    )


def test_the_bubble_is_the_conclusion_not_the_reason_for_asking() -> None:
    """该显示结论时显示结论；`guide.text` 是「为什么现在问这个」，不能顶上来。"""
    guide = BehaviorGuide(
        kind="options",
        text="先定你现在站在哪一步，后面挑专业、挑经历才问得准。",
        options=[],
    )
    text = _user_facing_text(
        {"conclusion": "你说想找互联网方向，先看你动手做过什么。"},
        guide,
        "",
        valid=True,
    )
    assert text == "你说想找互联网方向，先看你动手做过什么。"
    assert text != guide.text, "气泡里显示的仍是「我为什么要问你」"


def test_a_multiline_conclusion_is_collapsed_to_one_line() -> None:
    """结论被写成两三行时收成一行 —— 否则气泡会散开一大片。"""
    guide = BehaviorGuide(kind="question", text="为什么问", question="为什么问")
    text = _user_facing_text(
        {"conclusion": "你说先投产品岗。\n\n那就先把那 3 条职责抄下来。 "},
        guide,
        "",
        valid=True,
    )
    assert "\n" not in text
    assert text == "你说先投产品岗。 那就先把那 3 条职责抄下来。"


def test_single_line_trims_only_when_asked() -> None:
    """压行是通用的：给了上限才截断，没给上限就只是折成一行。"""
    assert _single_line("  第一行\n第二行  ") == "第一行 第二行"
    trimmed = _single_line("一" * 60, limit=40)
    assert trimmed.endswith("…")
    assert len(trimmed) == 41


# ---------------------------------------------------------------------------
# 2. 最近几条对话必须喂给模型
# ---------------------------------------------------------------------------


def _container():
    return build_container(_settings())


@pytest.mark.asyncio
async def test_the_model_is_given_the_last_few_turns() -> None:
    """第二轮开始，prompt_vars 里必须有最近几条对话。

    原缺陷：`biz_conversation_turn` 一直在写，却没有任何一处读回给模型 ——
    模型手上只有「这一句 + 黑板」，所以每一轮都像第一次见面。
    """
    container = _container()
    engine = _RecordingEngine()
    container.orchestrator._agent_engine = engine  # noqa: SLF001 - 换掉真模型，留证

    session = await container.orchestrator.enter_task("u-turn-group", "confused")
    await container.orchestrator.handle_message(
        TurnRequest(user_id="u-turn-group", task_id=session.id, message="我学的是计算机")
    )
    await container.orchestrator.handle_message(
        TurnRequest(user_id="u-turn-group", task_id=session.id, message="我大三了")
    )

    assert len(engine.requests) == 2
    first, second = engine.requests
    assert "turn_group" not in first.prompt_vars, (
        "第一轮没有上文：空表不该占一个字段位，"
        "免得模型把「最近没聊过」当成一件要交代的事"
    )
    turns = second.prompt_vars["turn_group"]
    assert any("我学的是计算机" in line for line in turns), (
        "上一轮用户说的话没进上下文：模型接不上话，回复就会像在说梦话"
    )
    assert any(line.startswith("他：") for line in turns)


@pytest.mark.asyncio
async def test_turn_group_stays_short_when_the_user_pastes_a_document() -> None:
    """回灌的是短行，不是原始记录：附件正文可能有几千字。

    用户传一份简历进来，原话就是整篇正文。照抄进上下文会把这一轮真正要看的东西
    挤出去，而这一轮该看的恰恰是画像与外部事实。
    """
    container = _container()
    engine = _RecordingEngine()
    container.orchestrator._agent_engine = engine  # noqa: SLF001

    session = await container.orchestrator.enter_task("u-long-turn", "confused")
    await container.orchestrator.handle_message(
        TurnRequest(
            user_id="u-long-turn",
            task_id=session.id,
            message="【我传了一份材料：简历.md】" + "教育背景与项目经历。" * 400,
        )
    )
    await container.orchestrator.handle_message(
        TurnRequest(user_id="u-long-turn", task_id=session.id, message="我大三了")
    )

    turns = engine.requests[-1].prompt_vars["turn_group"]
    assert turns, "上一轮的话应当被回灌"
    assert all(len(line) <= 60 for line in turns), (
        "回灌的行必须被截断：整篇附件正文进上下文会把这一轮的判断依据挤掉"
    )
    assert turns[0].endswith("…"), "长正文应当被截断，而不是整段照抄"
