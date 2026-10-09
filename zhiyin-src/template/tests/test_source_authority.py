"""权威字段的"拿到了没"必须看**来源**，不能只看键在不在画像里（issue #26 第三条）。

现象（结构性根因，比"用户改不动"更深一层）
--------------------------------------------
用户在对话里随口说一句"计算机大类"，① 采集就把 `major` 写进画像（来源「对话」）。
判定"拿到了没"如果只看键在不在画像里，这条就被算成已经拿到 —— 学信网核验从此**不再被要求**、
清单上也不再提示，一句对话就此长得像一条权威记录。

这里钉四件事，每一件对应一种"看起来记下了、其实没核验"的失败：

1. 对话 / 行为推断来源的专业**不算**拿到 —— 它仍在缺口里，学信网核验保持"该做"；
2. 相称的来源算拿到：学信网核验与教务导入写的都是「客观档案」（`record`，
   见 `services/ai_tasks.py` 与 `services/academic.py`），用户本人更正写的是
   「本人填写」（`user_edit`）；
3. **用户本人更正也算拿到** —— 否则他刚改完就一直看到"还差这一条"，上一轮的手动更正是白做；
4. 非权威字段（对话来源的兴趣 / 方向）行为**完全不变** —— 顺手把它们一起收紧，
   正常动线会被卡死（他答了，清单还说"还缺兴趣"）。

规则表用的是真资源（`data/registry/collection_rules.json`），不是模块内置的兜底表：
"哪个字段的权威来源是什么"就写在它里面，这份测试要跟着它走。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from zhiyin_boot import Settings, build_container, wire_application
from zhiyin_business.policies.collection import CollectionSource, plan_collection
from zhiyin_kernel.blackboard import Profile, ProfileField
from zhiyin_kernel.enums import ProfileSource
from zhiyin_kernel.registry import ChsiFieldSpec, CollectionRuleSpec

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _registry_rules() -> list[CollectionRuleSpec]:
    """登记表里的采集规则（真资源），不是 `collection.py` 里那份内置兜底表。"""
    rows = json.loads((DATA_DIR / "registry" / "collection_rules.json").read_text(encoding="utf-8"))
    return [CollectionRuleSpec(**row) for row in rows]


def _profile(*pairs: tuple[str, ProfileSource]) -> Profile:
    now = datetime.now(timezone.utc)
    return Profile(
        id="p1",
        user_id="u1",
        updated_at=now,
        fields=[
            ProfileField(key=key, value="x", confidence=1.0, source=source, updated_at=now)
            for key, source in pairs
        ],
    )


def _step(plan, key: str):
    return next(step for step in plan.steps if step.key == key)


# --------------------------------------------------------------- 判定表的前提


def test_the_registry_is_what_makes_these_fields_authoritative() -> None:
    """守卫的前提：`major` 登记的权威来源就是 `chsi`，课程表是 `academic`。

    这一条要是被人改了而没人知道，下面所有判定会静默失效（字段依然是"键在就算有"）。
    所以先把它钉住：口径的源头在登记表上，不在这份测试里。
    """
    by_key = {spec.key: spec for spec in _registry_rules()}
    assert by_key["major"].source == CollectionSource.CHSI.value
    assert by_key["courses"].source == CollectionSource.ACADEMIC.value
    assert by_key["interest"].source == CollectionSource.CONVERSATION.value


# --------------------------------------------------------------- 推断来源不算拿到


@pytest.mark.parametrize("source", [ProfileSource.CONVERSATION, ProfileSource.BEHAVIOR_INFERENCE])
def test_an_inferred_major_is_still_a_gap(source: ProfileSource) -> None:
    """对话 / 行为推断来的专业**不算**拿到：学信网核验这一步要保持"该做"。

    这就是 #26 第三条的结构性原因 —— 值在画像里不等于这条值已被核验。
    """
    rules = _registry_rules()
    baseline = plan_collection(_profile(), rules=rules)
    plan = plan_collection(_profile(("major", source)), rules=rules)

    assert _step(plan, "major").got is False
    # 缺口一条都没少：`major` 仍然挂在学信网那一格里
    assert (
        plan.by_source[CollectionSource.CHSI.value]
        == baseline.by_source[CollectionSource.CHSI.value]
    )
    assert "专业" not in plan.blocked
    # 下一步仍然是去核验（一次动作补最多条），而不是"没有可做的了"
    assert plan.next_source() is CollectionSource.CHSI
    # 它的动作是"去核验"，不是"回答一句"：不给它挂问题
    assert _step(plan, "major").ask == ""


def test_a_mention_of_the_timetable_is_not_an_import() -> None:
    """课表同理：对话里说"这学期课很满"不等于导入过课表。"""
    plan = plan_collection(
        _profile(("courses", ProfileSource.CONVERSATION)),
        rules=_registry_rules(),
        available_sources=("chsi", "conversation", "academic"),
    )
    assert _step(plan, "courses").got is False
    # 两条教务字段（课程表 / 成绩单）一条都没被顶上
    assert plan.by_source[CollectionSource.ACADEMIC.value] == 2


# --------------------------------------------------------------- 相称的来源算拿到


@pytest.mark.parametrize("source", [ProfileSource.RECORD, ProfileSource.USER_EDIT])
def test_a_matching_source_does_close_the_authoritative_step(source: ProfileSource) -> None:
    """相称的来源算拿到。

    `record`：学信网在线验证（`ai_tasks.py`）与教务导入（`academic.py`）落库时写的就是它 ——
    它就是这个字段登记的权威来源本身。
    `user_edit`：用户一字一句告诉系统的值就是拿到了。
    """
    rules = _registry_rules()
    baseline = plan_collection(_profile(), rules=rules)
    plan = plan_collection(_profile(("major", source)), rules=rules)

    assert _step(plan, "major").got is True
    assert (
        plan.by_source[CollectionSource.CHSI.value]
        == baseline.by_source[CollectionSource.CHSI.value] - 1
    )


class _RawField:
    """来源认不出来的一条画像字段（库里可能留下的旧值 / 历史写法）。"""

    def __init__(self, key: str, source: object) -> None:
        self.key = key
        self.source = source


class _RawProfile:
    def __init__(self, *fields: _RawField) -> None:
        self.fields = list(fields)


def test_an_unreadable_source_never_stands_in_for_an_authoritative_one() -> None:
    """来源读不懂时按"不算拿到"处理。

    来源是一份**声明**，读不懂的声明不能替这条值撑起权威性 ——
    这里宁可多问一次学信网，也不要让一条来历不明的值关上核验动作。
    """
    plan = plan_collection(
        _RawProfile(_RawField("major", "some_legacy_value")), rules=_registry_rules()
    )
    assert _step(plan, "major").got is False


# --------------------------------------------------------------- 非权威字段不变


@pytest.mark.parametrize("source", list(ProfileSource))
def test_conversation_registered_fields_never_look_at_the_source(
    source: ProfileSource,
) -> None:
    """兴趣这类本来就该从对话来的字段：键在画像里就算拿到，**不论来源是什么**。

    收紧它们会把正常动线卡死：用户刚答完"我愿意反复做的是结构设计"，
    清单还说"还缺兴趣"，而他无论怎么答都关不掉这一条。
    """
    plan = plan_collection(_profile(("interest", source)), rules=_registry_rules())
    assert _step(plan, "interest").got is True


def test_conversation_registered_fields_are_still_missing_when_absent() -> None:
    """反向的一半：非权威字段口径不变，指的是"键在就算有"，不是"永远算有"。"""
    plan = plan_collection(
        _profile(("interest", ProfileSource.CONVERSATION)), rules=_registry_rules()
    )
    values = _step(plan, "values")
    assert values.got is False
    assert plan.by_source[CollectionSource.CONVERSATION.value] == 3
    assert values.ask, "没拿到的对话字段仍然要带着那个问题"


# --------------------------------------------------------------- 真实装配下的三条路


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


async def _container():
    """整装容器 + 真动态配置（采集规则 / 字段词表都真的装进来）。"""
    from zhiyin_business.services.dynamic_config import load_snapshot

    container = build_container(_settings())
    wire_application(container)
    await load_snapshot(container.registry_service)
    return container


async def _plan_of(container, user: str, *, stage: str = "explore"):
    return plan_collection(
        await container.profile_service.get(user),
        stage=stage,
        rules=_registry_rules(),
        available_sources=("chsi", "conversation", "academic"),
    )


def _chat_payload(key: str, label: str, value: str) -> dict:
    """① 采集的一轮产出：用户在对话里说的那两句。"""
    return {
        "conclusion": "你说的这句我记下了。",
        "field_updates": [
            {
                "key": key,
                "label": label,
                "value": value,
                "confidence": 0.8,
                "source": "conversation",
                "evidence": ["他这一轮自己说的"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_a_chat_line_about_the_major_does_not_close_the_chsi_step() -> None:
    """端到端复现 #26 的第三句：随口一句"计算机大类"被当成专业已核验。

    值仍然留在画像里（不清、不覆盖 —— 它对判断有价值），但它不算拿到：
    这条字段继续出现在"还差哪几条"里，学信网核验保持"该做"。
    """
    container = await _container()
    user = "authority-chat-major"
    await container.orchestrator._apply_collect(  # noqa: SLF001 - 直接验这一步
        user, _chat_payload("major", "专业", "计算机大类")
    )

    profile = await container.profile_service.get(user)
    assert profile is not None
    assert [field.source for field in profile.fields] == [ProfileSource.CONVERSATION]

    plan = await _plan_of(container, user)
    assert _step(plan, "major").got is False
    assert plan.by_source[CollectionSource.CHSI.value] >= 1


@pytest.mark.asyncio
async def test_a_user_correction_does_close_the_authoritative_step() -> None:
    """用户本人更正之后不能再追着要：他亲手写的值就是拿到了。

    这一条与上面那条是同一个判定的两面 —— 判紧了，上一轮补的手动更正会变成
    "改完还一直显示还差这一条"。
    """
    container = await _container()
    user = "authority-user-edit"
    await container.profile_service.correct_field(user, "major", "计算机大类")

    plan = await _plan_of(container, user)
    assert _step(plan, "major").got is True


@pytest.mark.asyncio
async def test_only_a_real_academic_import_closes_the_courses_step() -> None:
    """教务字段：对话里提过不算，真的从教务系统导入一次才算。"""
    container = await _container()
    user = "authority-academic"
    await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _chat_payload("courses", "课程表", "这学期课挺满")
    )
    assert _step(await _plan_of(container, user), "courses").got is False

    await container.academic_service.import_(
        user,
        courses_raw=("课程名称\t星期\t节次\t地点\t教师\n高等数学\t周三\t1-2节\t教一楼101\t张三"),
    )
    assert _step(await _plan_of(container, user), "courses").got is True


@pytest.mark.asyncio
async def test_the_chsi_verification_closes_what_the_chat_line_could_not() -> None:
    """学信网核验那一趟：写进去的字段来源是「客观档案」，才算真的补上了缺口。

    顺带钉住闭环那半句：`_bind_chsi` 是按"核验前后各算一次采集清单"来说
    "补上了哪几条"的。判定收紧之后，这句话里才真的会出现"专业" ——
    以前它在核验之前就被对话那句顶成"已经有了"，于是核验回执说"还差的东西没变"。
    """
    from zhiyin_business.services.ai_tasks import AiTaskService
    from zhiyin_data_sdk.gateways.chsi import ChsiField, ChsiReport, ChsiReportKind
    from zhiyin_kernel.registry import AgentDescriptor

    class _Chsi:
        async def verify(self, code: str) -> ChsiReport:
            return ChsiReport(
                code=code,
                kind=ChsiReportKind.ENROLLMENT,
                fields=[ChsiField(key="major", label="专业名称", value="计算机科学与技术")],
            )

    class _Registry:
        """只回答 `bind.chsi` 真正会问的两件事。"""

        async def get_agent(self, agent_id: str) -> AgentDescriptor:
            return AgentDescriptor(id=agent_id, name="信息侦查员")

        async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
            return [ChsiFieldSpec(key="major", label="专业")]

        async def list_task_progress(self) -> list:
            return []

    container = await _container()
    user = "authority-chsi"
    await container.orchestrator._apply_collect(  # noqa: SLF001
        user, _chat_payload("major", "专业", "计算机大类")
    )

    service = AiTaskService(
        profiles=container.profile_service,
        behaviors=None,  # type: ignore[arg-type] - bind 这条不读行为日志
        assets=None,  # type: ignore[arg-type]
        chsi=_Chsi(),  # type: ignore[arg-type]
        registry=_Registry(),
    )
    frames = [frame async for frame in service.stream(user, "bind.chsi", "123456789012")]
    assert "result" in frames[-1], frames[-1]

    plan = await _plan_of(container, user)
    assert _step(plan, "major").got is True

    closed_loop = next(step for step in frames[-1]["result"].data.steps if step.id == "s3")
    assert "专业" in closed_loop.detail, closed_loop.detail
