"""用户亲手更正过的画像值，不许被对话推断覆盖。

现象（用户能直接看见的那种）
----------------------------
他在画像里点「更正」，把专业改成自己认可的那句话（落库 `source = user_edit`）。
下一轮对话里，① 采集的模型又产出一条同键的 `field_updates`，`_apply_collect`
整行替换，他刚写的那句话就没了 —— 而且**没有任何一处告诉他**：界面还是那份画像，
只是那格的值悄悄变回了系统挑的那一个。他只能再改一次，再被盖一次。

这里钉住四件事：

1. 推断类来源（对话 / 行为推断 / 测评 / 导师 / 简历）对 `user_edit` 的写入被挡，
   原值、原来源、原把握度一个字不变；
2. **权威记录 `record` 仍然覆盖得动**：学信网核验 / 教务导入是出具方，
   挡掉它会让"用户写错了一句自述"变成永久事实；
3. 被挡下的写入要有痕迹：`CollectWriteResult.blocked_by_user_edit` 里有这个键、
   `written` 里没有、日志里有一句能照着查的警告；而且它**不算一次"画像字段更新"**
   （库里没变，却报一次更新，会让影响面传播去重算一份没变的画像）；
4. 这条路没有被堵死：他随时能再「更正」一次，改完仍然算他自己写的。

另外守一条容易被漏掉的：`contracts/collect.py` 把提示词里的中文来源标签翻成枚举
（"来源「对话」"），**中文别名也要按同一个口径被挡** —— 只看英文取值的守卫会在
真模型写中文时整个失效（它一直是按中文提示词回答的）。
"""

from __future__ import annotations

import logging

import pytest

from zhiyin_kernel.enums import ProfileSource

#: "系统替他说 / 替他推的"那几个来源 —— 它们盖不动他亲手写的值。
_INFERRED_SOURCES = (
    ProfileSource.CONVERSATION,
    ProfileSource.BEHAVIOR_INFERENCE,
    ProfileSource.ASSESSMENT,
    ProfileSource.MENTOR,
    ProfileSource.RESUME,
)

#: 他亲手写的那句话（第一次更正时写进去的）。
_HIS_WORDS = "计算机大类（我自己写的）"
#: 模型这一轮想盖上去的那句。
_MODEL_WORDS = "计算机科学与技术"


def _collect_payload(key: str, label: str, value: str, source: object) -> dict:
    """① 采集的一轮产出：模型给出一条同键的字段更新。"""
    return {
        "conclusion": "你说的这句我记下了。",
        "field_updates": [
            {
                "key": key,
                "label": label,
                "value": value,
                "confidence": 0.9,
                "source": source,
                "evidence": ["模型这一轮推出来的"],
            }
        ],
    }


async def _container():
    """整装容器 + 真动态配置（复用权威判定那份装配，见 test_source_authority）。"""
    from tests.test_source_authority import _container as authority_container

    return await authority_container()


async def _profile_field(container, user: str, key: str):
    fields = {field.key: field for field in await container.profile_service.get_fields(user)}
    return fields.get(key)


@pytest.mark.parametrize("source", _INFERRED_SOURCES)
@pytest.mark.asyncio
async def test_an_inferred_update_never_overwrites_what_the_user_wrote(
    source: ProfileSource,
) -> None:
    """推断来源的写入被挡：值还是他写的那句，来源还是「本人填写」。

    注意这里断言的是**原值一个字不变**，而不只是"来源没变"：
    覆盖发生的那一刻值就被换掉了，等他下次打开画像看到的是另一句话。
    """
    container = await _container()
    user = f"user-edit-kept-{source.value}"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)
    before = await _profile_field(container, user, "major")

    result = await container.orchestrator._apply_collect(  # noqa: SLF001 - 直接验这一步
        user, _collect_payload("major", "专业", _MODEL_WORDS, source)
    )

    after = await _profile_field(container, user, "major")
    assert after.value == _HIS_WORDS
    assert after.source is ProfileSource.USER_EDIT
    assert after.confidence == before.confidence  # 自述的把握度也要原样留着
    assert result.blocked_by_user_edit == ("major",)
    assert "major" not in result.written


@pytest.mark.asyncio
async def test_a_chinese_source_alias_is_blocked_the_same_way() -> None:
    """中文来源标签（提示词里给模型看的就是中文）走同一个判定。

    别名映射在契约入口做（`contracts/collect.py::_SOURCE_ALIASES`），所以这里
    要证明的是：等到 `_apply_collect` 判来源时，取的已经是**枚举**，而不是
    那句"对话" —— 否则真模型每次写中文，这道守卫都静默失效。
    """
    container = await _container()
    user = "user-edit-kept-chinese-alias"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)

    result = await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _collect_payload("major", "专业", _MODEL_WORDS, "对话")
    )

    assert (await _profile_field(container, user, "major")).value == _HIS_WORDS
    assert result.blocked_by_user_edit == ("major",)


@pytest.mark.asyncio
async def test_even_a_model_claiming_user_edit_cannot_overwrite() -> None:
    """模型把来源写成 `user_edit` 也挡。

    这条是"白名单"而不是"黑名单"的原因：流水线上的 `source` 是**模型的声明**，
    契约里每个枚举取值它都能写（`FieldUpdate.source` 就是 `ProfileSource`）。
    黑名单漏掉一个取值，用户亲手写的值就被静默盖掉一次 —— 那是这道守卫
    唯一不能出的错；白名单多挡一次只会多一条日志。
    """
    container = await _container()
    user = "user-edit-kept-forged"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)

    result = await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _collect_payload("major", "专业", _MODEL_WORDS, ProfileSource.USER_EDIT)
    )

    assert (await _profile_field(container, user, "major")).value == _HIS_WORDS
    assert result.blocked_by_user_edit == ("major",)


@pytest.mark.asyncio
async def test_the_authoritative_record_still_overwrites() -> None:
    """`record`（学信网核验 / 教务导入）仍然覆盖得动。

    它是出具方本身，比自述更权威：挡掉它会让"用户写错了一句自述"变成永久事实，
    而他自己写的值本来就可能不准确。覆盖之后他仍然能再「更正」一次
    （见下一条测试），所以这条口子不需要关。
    """
    container = await _container()
    user = "user-edit-record-wins"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)

    result = await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _collect_payload("major", "专业", _MODEL_WORDS, ProfileSource.RECORD)
    )

    after = await _profile_field(container, user, "major")
    assert after.value == _MODEL_WORDS
    assert after.source is ProfileSource.RECORD
    assert result.written == ("major",)
    assert result.blocked_by_user_edit == ()


@pytest.mark.asyncio
async def test_the_blocked_write_is_reported_in_the_result_and_the_log(caplog) -> None:
    """被挡下要留痕：结果里有键、日志里有一句能照着查的话。

    没有痕迹的症状是"画像就是没更新"：下一个人只能从编排器一路读到仓储，
    而这件事其实是**设计如此**（不是故障），日志应该一句话说清是哪一格、
    被谁写的值挡下的、要改该走哪条路。
    """
    container = await _container()
    user = "user-edit-blocked-is-logged"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)

    with caplog.at_level(logging.WARNING, logger="zhiyin_business.services.orchestrator"):
        result = await container.orchestrator._apply_collect(  # noqa: SLF001
            user, _collect_payload("major", "专业", _MODEL_WORDS, ProfileSource.CONVERSATION)
        )

    assert result.blocked_by_user_edit == ("major",)
    assert result.written == ()
    assert result.dropped_by_gate == ()
    warnings = [record.getMessage() for record in caplog.records]
    assert any("本人填写" in text and "major" in text for text in warnings), warnings


@pytest.mark.asyncio
async def test_a_field_the_user_never_touched_is_still_written() -> None:
    """反向的一半：他没改过的格子照旧写进去（这道门禁只挡"他亲手写的那些"）。

    顺手把所有字段都挡掉会把正常动线卡死：他刚在对话里说完一句，画像一动不动，
    采集清单还挂着"还差这一条"。
    """
    container = await _container()
    user = "user-edit-untouched-field"

    result = await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _collect_payload("interest", "兴趣", "结构设计", ProfileSource.CONVERSATION)
    )

    field = await _profile_field(container, user, "interest")
    assert field is not None and field.value == "结构设计"
    assert field.source is ProfileSource.CONVERSATION
    assert result.written == ("interest",)
    assert result.blocked_by_user_edit == ()


@pytest.mark.asyncio
async def test_the_user_can_still_correct_after_a_blocked_write() -> None:
    """"他后面亲口改口"这条路没被堵死：被挡下之后，他本人再更正一次照样成立。

    这一点必须钉住：守卫挡的是**推断**，不是他。写 `user_edit` 的路径是
    `DefaultProfileService.correct_field`（`POST /app/profile/fields/{key}`），
    它不经过 `_apply_collect` —— 挡掉的写入不会连带把他的更正路径也锁上。
    """
    container = await _container()
    user = "user-edit-can-correct-again"
    await container.profile_service.correct_field(user, "major", _HIS_WORDS)
    await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _collect_payload("major", "专业", _MODEL_WORDS, ProfileSource.CONVERSATION)
    )

    saved = await container.profile_service.correct_field(user, "major", "软件工程")

    assert saved.value == "软件工程"
    assert saved.source is ProfileSource.USER_EDIT
    # 而且改完仍然挡得住推断：不是"第二次更正之后守卫就失效了"。
    result = await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _collect_payload("major", "专业", _MODEL_WORDS, ProfileSource.CONVERSATION)
    )
    assert result.blocked_by_user_edit == ("major",)
    assert (await _profile_field(container, user, "major")).value == "软件工程"
