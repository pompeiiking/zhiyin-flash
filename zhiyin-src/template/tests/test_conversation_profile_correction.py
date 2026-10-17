"""对话里本人明确更正学习阶段，必须真的写进画像。

2026-10-18 深度测试：回复称已改（甚至报告也按"大三"写），画像页仍是"大二"。
"""

from __future__ import annotations

import pytest

from tests.test_conversation_asset_confirmation import send, setup


async def _setup_with_year(year: str = "大二"):
    c, engine, session = await setup()
    await c.profile_service.update_field(
        "u1", "study_year", year, confidence=1.0, source="user_edit"
    )
    return c, engine, session


async def _year(c) -> str:
    fields = await c.profile_service.get_fields("u1", ["study_year"])
    return str(fields[0].value) if fields else ""


@pytest.mark.asyncio
async def test_natural_correction_is_persisted() -> None:
    c, _, session = await _setup_with_year("大二")
    result = await send(c, session, "我现在已经大三了，不是大二。我是计算机专业，想找数据分析实习。")
    assert await _year(c) == "大三"
    assert any("已按你这次说明更新画像" in message.text for message in result.messages)


@pytest.mark.asyncio
async def test_explicit_correction_is_persisted() -> None:
    c, _, session = await _setup_with_year("大四")
    await send(c, session, "把当前学习阶段改成研究生，其他信息都别动。")
    assert await _year(c) == "研究生"


@pytest.mark.asyncio
async def test_hypothetical_statement_is_not_written() -> None:
    c, _, session = await _setup_with_year("大二")
    await send(c, session, "如果我大三了呢，是不是就能投实习了？")
    assert await _year(c) == "大二"


async def _field(c, key: str) -> str:
    fields = await c.profile_service.get_fields("u1", [key])
    return str(fields[0].value) if fields else ""


@pytest.mark.asyncio
async def test_explicit_major_and_school_correction_is_persisted() -> None:
    c, _, session = await _setup_with_year("大二")
    await c.profile_service.update_field(
        "u1", "major", "计算机科学与技术", confidence=1.0, source="user_edit"
    )
    await send(c, session, "把专业改成汉语言文学，其他信息别动。")
    await send(c, session, "帮我把学校改成北京大学。")
    assert await _field(c, "major") == "汉语言文学"
    assert await _field(c, "school") == "北京大学"


@pytest.mark.asyncio
async def test_chat_recorded_experience_is_appended_not_overwritten() -> None:
    c, _, session = await _setup_with_year("大三")
    await c.profile_service.update_field(
        "u1", "experience", "校内数据分析社团", confidence=1.0, source="user_edit"
    )
    await send(c, session, "我参加过全国大学生数学建模竞赛，帮我记到项目经历里。")
    value = await _field(c, "experience")
    assert "校内数据分析社团" in value
    assert "数学建模" in value

