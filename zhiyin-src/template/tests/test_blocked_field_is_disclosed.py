"""被「本人填写」挡下的那一笔，必须当面说给用户听。

现象（用户能直接感受到的那种）
--------------------------------
他在对话里说"我专业其实是软件工程"，系统什么都没改 —— 因为专业那一格是他自己在
画像里点「更正」写下的，推断不许覆盖它（见 `test_user_edit_is_not_overwritten.py`，
挡下本身是**设计如此**）。问题是这件事**只有日志知道**：他看到的是一轮正常的回复，
画像一个字没动，也没有任何解释。从他的角度看就是"我说了它不听"，于是他再说一次、
再被挡一次，最后不再说。

这里钉三件事：

1. 撞上时，`handle_message` 的返回值里带上这条告知，**文案里出现那个字段的中文名**
   （他看得到的是「专业」，不是 `major`）；
2. 没撞上时**不出现** —— 不能每轮都念一遍，否则这句话会变成背景噪音，
   真正被挡的那一轮反而没人注意；
3. 文案说清三件事：那句没写进画像、因为这一格是他自己填的、要以他说的为准就去
   画像里点「更正」。他的更正路径没有被堵死。

字段中文名走既有映射（画像词表中的 `profile.field.<键>`）：代码里不拼英文键、
也不在测试里钉字面量，否则词表改一次文案就对不上。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_boot import Settings, build_container
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_business.services.dynamic_config import load_snapshot
from zhiyin_kernel.enums import LoopStage, ProfileSource
from zhiyin_orchestration.agent import AgentEngine, AgentRequest, AgentResult

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"

#: 他亲手写下的那句话（画像里点「更正」落库的来源是 `user_edit`）。
_HIS_WORDS = "计算机大类（我自己写的）"
#: 模型这一轮想盖上去的那句 —— 用户刚说的话。
_MODEL_WORDS = "软件工程"


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


def _collect_payload(*fields: dict) -> dict:
    """① 采集这一轮的产出（模型的结构化返回）。"""
    return {
        "conclusion": "你说的是软件工程，这条我记下了。",
        "field_updates": list(fields),
        "remaining_gaps": [],
        "confidence_overall": 0.6,
        "ready_to_handoff": False,
        "guide": {"kind": "question", "text": "还缺一条", "question": "你做过什么？"},
    }


def _update(key: str, label: str, value: str, source: str = "conversation") -> dict:
    return {
        "key": key,
        "label": label,
        "value": value,
        "confidence": 0.9,
        "source": source,
        "evidence": ["他这一轮自己说的"],
    }


class _StubEngine(AgentEngine):
    """换掉真模型：这一轮它返回什么，完全由用例决定。"""

    def __init__(self, structured: dict) -> None:
        self._structured = structured

    async def invoke(self, request: AgentRequest) -> AgentResult:
        return AgentResult(
            agent_id=request.agent_id, structured=dict(self._structured), valid=True
        )


async def _container(engine: _StubEngine):
    """整装容器 + 真动态配置（画像词表真的装进来，才有中文名可用）。"""
    container = build_container(_settings())
    await load_snapshot(container.registry_service)
    container.orchestrator._agent_engine = engine  # noqa: SLF001 - 换掉真模型
    return container


async def _turn(container, user: str, message: str):
    session = await container.orchestrator.enter_task(user, "confused")
    return await container.orchestrator.handle_message(
        TurnRequest(user_id=user, task_id=session.id, message=message)
    )


def _label_of(key: str) -> str:
    """这个词在画像里的中文名（与界面同一份：文案包的 `profile.field.<键>`）。"""
    import json

    copies = json.loads((DATA_DIR / "registry" / "copies.json").read_text(encoding="utf-8"))
    for item in copies["items"]:
        if item["code"] == f"profile.field.{key}":
            return item["text"]
    raise AssertionError(f"文案包里没有这个字段的中文名：{key}")


@pytest.mark.asyncio
async def test_a_blocked_write_is_told_to_the_user_with_the_chinese_field_name() -> None:
    """撞上「本人填写」时：告知里要说清是哪一格，而且用中文名说。"""
    container = await _container(
        _StubEngine(_collect_payload(_update("major", "专业", _MODEL_WORDS)))
    )
    user = "field-kept-disclosed"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)

    result = await _turn(container, user, "我专业其实是软件工程")

    # 前提：这一轮真的落在①采集（否则这条告知的由来就不是那道门禁）
    assert result.stage is LoopStage.COLLECT, f"这一轮不在采集：{result.stage}"
    assert result.disclosure is not None, (
        "他自己填过的格子被挡下了，用户却什么都不知道 —— "
        "从他的角度看就是「我说了它不听」"
    )
    text = result.disclosure.text
    assert _label_of("major") in text, f"告知里没说出是哪一格：{text!r}"
    assert "major" not in text, f"告知里念了英文键：{text!r}"
    # 三件事要齐：没写进画像 / 因为这一格是他自己填的 / 去哪儿改
    assert "画像" in text and "更正" in text, f"告知没有给出改的出口：{text!r}"

    # 顺带钉住那句挡下的原值：说了不改，就是真的不改
    fields = {field.key: field for field in await container.profile_service.get_fields(user)}
    assert fields["major"].value == _HIS_WORDS
    assert fields["major"].source is ProfileSource.USER_EDIT


@pytest.mark.asyncio
async def test_nothing_is_said_when_no_write_was_blocked() -> None:
    """没撞上就一个字都不说 —— 每轮都念一遍，这句话就没人会注意了。"""
    container = await _container(_StubEngine(_collect_payload()))
    user = "field-kept-silent"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)

    result = await _turn(container, user, "我专业其实是软件工程")

    assert result.stage is LoopStage.COLLECT
    assert result.disclosure is None, (
        f"这一轮没有任何写入被挡下，却还在说这句：{result.disclosure!r}"
    )


@pytest.mark.asyncio
async def test_a_field_he_never_touched_is_written_without_any_notice() -> None:
    """反向的一半：他没填过的格子照旧写进去，而且**不当成"被挡"来告知**。

    只挡不写会让正常动线卡死（他说完，画像一动不动），而多报一句"没写进画像"
    与事实相反 —— 这一格确实写进去了。
    """
    container = await _container(
        _StubEngine(_collect_payload(_update("interest", "兴趣", "跟人打交道")))
    )
    user = "field-kept-written"

    result = await _turn(container, user, "我愿意反复做的是跟人打交道")

    assert result.disclosure is None, f"没被挡却说没写进画像：{result.disclosure!r}"
    fields = {field.key: field for field in await container.profile_service.get_fields(user)}
    assert fields["interest"].value == "跟人打交道"


@pytest.mark.asyncio
async def test_both_notices_are_said_when_a_handoff_happens_in_the_same_turn() -> None:
    """同一轮里既换了主理、又挡下一次写入：两件事都得说，不能只留一个位置。

    契约里只有一个 `disclosure`，先前「结论变化」与「换主理」同轮时就吃过这个亏
    （实测：换主理那句把"结论变了"整个盖住），这里沿用同一条拼接口径。
    """
    container = await _container(
        _StubEngine(_collect_payload(_update("major", "专业", _MODEL_WORDS)))
    )
    user = "field-kept-with-handoff"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)
    session = await container.orchestrator.enter_task(user, "confused")
    # 制造"主理真的换了"：会话上挂一个不是这一轮选出来的那个主理
    await container.orchestrator._sessions.update_stage(  # noqa: SLF001
        session.id, LoopStage.COLLECT, "career_advisor"
    )

    result = await container.orchestrator.handle_message(
        TurnRequest(user_id=user, task_id=session.id, message="我专业其实是软件工程")
    )

    assert result.disclosure is not None
    assert "接手" in result.disclosure.text, (
        f"换主理那句被挤掉了（契约只有一个位置，不能只说一件）：{result.disclosure.text!r}"
    )
    assert _label_of("major") in result.disclosure.text, (
        f"被挡下的那句被挤掉了：{result.disclosure.text!r}"
    )
