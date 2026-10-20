"""《个人画像设计-2026-10-20》核心契约回归。

锁住三件事（对应设计第 2/4/8 节与验收 P01-P11、P27）：

1. **记录有类别与核实状态**：类别来自受控词表，不由模型自由生成；
   核实状态与来源分开表达，不再用一个置信度分数混合。
2. **各类型有各自的结构与上限**：兴趣可以是多条、经历正文可以长；
   不再用统一的 40 字承载所有记录。
3. **按用途读取**：专业检索只认学习背景里的专业；职业检索只认明确的职业关注；
   普通兴趣绝不拼成职业名称（复现的根因：兴趣描述把专业检索顶掉）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from zhiyin_boot import Settings, build_container
from zhiyin_boot.container import Container
from zhiyin_business.policies.intel_query import intel_topic
from zhiyin_data_sdk.gateways.datasource import DataSourceRequest
from zhiyin_infrastructure.xuezhi import XueZhiDataSourceGateway
from zhiyin_kernel import profile_taxonomy
from zhiyin_kernel.enums import (
    ProfileEntryStatus,
    ProfileEntryType,
    ProfilePurpose,
    ProfileSource,
    ProfileVerification,
)
from zhiyin_kernel.errors import InvalidRequest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
USER = "u-profile-design-2026-10-20"


@pytest.fixture
def container() -> Container:
    return build_container(
        Settings(
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


class _Client:
    """学职平台客户端桩：与真实客户端同形，记录每一次检索词。"""

    def __init__(self, *, linked: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._linked = linked

    @property
    def base_url(self) -> str:
        return "https://xz.chsi.com.cn"

    async def list_specialities(self, *, name: str = "", start: int = 0) -> dict[str, Any]:
        self.calls.append(("speciality", name))
        return {"data": {"pageArray": [{"specId": "S1", "zymc": name}]}}

    async def get_speciality_detail(self, spec_id: str) -> dict[str, Any]:
        if self._linked:
            return {
                "basicVo": {"zymc": "人工智能"},
                "byfzVo": {"expOccList": {"人工智能工程技术人员": {"zhiyId": "O1"}}},
            }
        return {"basicVo": {"zymc": "人工智能"}, "byfzVo": {"expOccList": {}}}

    async def search_occupations(self, *, name: str = "", start: int = 0) -> dict[str, Any]:
        self.calls.append(("occupation", name))
        return {"data": {"zhiyArray": [{"zhiyId": "O1", "title": "人工智能工程技术人员"}]}}

    async def get_occupation_detail(self, occ_id: str) -> dict[str, Any]:
        return {"zhiyId": occ_id, "zhiyname": "人工智能工程技术人员", "occDesc": "设计智能系统"}

    async def search_occupation_cases(self, *, name: str = "", start: int = 0) -> dict[str, Any]:
        self.calls.append(("case", name))
        return {
            "data": {
                "list": [
                    {
                        "caseId": "C1",
                        "caseDesc": "从课程项目到算法岗",
                        "caseCardDesc": "<p>李同学，人工智能专业</p>",
                        "industryName": "信息技术",
                    }
                ]
            }
        }


def _request(fields: list[dict[str, Any]], *, query: str = "") -> DataSourceRequest:
    return DataSourceRequest(source="xuezhi", query=query, limit=8, context={"fields": fields})


# ---------------------------------------------------------------------------
# 记录结构：类别 / 核实状态 / 各自上限
# ---------------------------------------------------------------------------


async def test_major_is_a_learning_background_record_not_an_interest(container: Container) -> None:
    """P01：只提供专业 → 作为学习背景保存与检索，不自动生成兴趣或职业目标。"""
    saved = await container.profile_service.update_field(
        USER, "major", "人工智能", confidence=0.9, source="conversation",
        evidence=["我是人工智能专业"],
    )
    assert saved.entry_type is ProfileEntryType.LEARNING_BACKGROUND
    assert saved.verification is ProfileVerification.SELF_REPORTED
    assert saved.status is ProfileEntryStatus.ACTIVE
    assert saved.entry_version == 1
    fields = await container.profile_service.get_fields(USER)
    assert {field.key for field in fields} == {"major"}
    assert profile_taxonomy.major_terms(fields) == ["人工智能"]
    assert profile_taxonomy.career_focus_terms(fields) == []
    assert intel_topic(fields) == "人工智能"


async def test_interest_is_stored_as_preferences_with_polarity(container: Container) -> None:
    """P09：不喜欢某活动 → 保存具体否定偏好，不概括成“没有兴趣”。"""
    saved = await container.profile_service.update_field(
        USER, "interest", ["调试程序", "和同学一起做项目"], confidence=0.8,
        source=ProfileSource.CONVERSATION.value,
        attributes={"polarity": "dislike", "context": "一次文件读取后数字变成字符串"},
    )
    assert saved.entry_type is ProfileEntryType.INTEREST
    assert saved.value == ["调试程序", "和同学一起做项目"]
    assert saved.attributes["polarity"] == "dislike"
    # 兴趣不参与职业检索词：它不是职业名称，也不是能力证明。
    assert profile_taxonomy.career_focus_terms([saved]) == []
    assert profile_taxonomy.major_terms([saved]) == []


async def test_career_focus_keeps_its_state(container: Container) -> None:
    """P05：想了解算法工程师 → 职业关注为了解状态，不成为已选方向。"""
    saved = await container.profile_service.update_field(
        USER, "target_direction", "算法工程师", confidence=0.8, source="conversation",
        attributes={"state": "exploring"},
    )
    assert saved.entry_type is ProfileEntryType.CAREER_FOCUS
    assert saved.attributes["state"] == "exploring"
    assert profile_taxonomy.career_focus_terms([saved]) == ["算法工程师"]


async def test_type_specific_limits_replace_the_uniform_40_char_rule(container: Container) -> None:
    """第 4 节：不同类别分别限制长度；经历正文与短标签分开。"""
    # 经历正文可以长（12000），专业仍保持短事实的上限（40）。
    saved = await container.profile_service.update_field(
        USER, "experience", "调" * 5000, confidence=0.8, source="conversation"
    )
    assert len(saved.value) == 5000
    with pytest.raises(InvalidRequest):
        await container.profile_service.update_field(
            USER, "major", "专" * (profile_taxonomy.value_limit("major") + 1),
            confidence=0.8, source="conversation",
        )
    # 兴趣是多条偏好：最多 8 条，第 9 条拒绝并说明上限。
    with pytest.raises(InvalidRequest):
        await container.profile_service.update_field(
            USER, "interest", [f"兴趣{i}" for i in range(9)],
            confidence=0.8, source="conversation",
        )


async def test_attributes_are_controlled_not_free_form(container: Container) -> None:
    """类型专属属性来自受控键与取值：模型不能自由扩展一个权限相关字段。"""
    with pytest.raises(InvalidRequest):
        await container.profile_service.update_field(
            USER, "interest", "调试程序", confidence=0.8, source="conversation",
            attributes={"polarity": "love"},  # 只允许 like / dislike / unsure
        )
    with pytest.raises(InvalidRequest):
        await container.profile_service.update_field(
            USER, "major", "人工智能", confidence=0.8, source="conversation",
            attributes={"allowed": "true"},  # 未登记属性一律拒绝
        )


async def test_time_window_is_validated_and_not_filled_with_now(container: Container) -> None:
    """第 11 节：有效范围起止要对得上；未知时间不自动补成当前时间。"""
    now = datetime.now(timezone.utc)
    saved = await container.profile_service.update_field(
        USER, "constraints", "本周只有晚上有空", confidence=0.8, source="conversation",
        attributes={"scope": "本周"},
        valid_from=now, valid_to=now + timedelta(days=7),
    )
    assert saved.entry_type is ProfileEntryType.CONDITION
    assert saved.valid_from is not None and saved.valid_to is not None
    with pytest.raises(InvalidRequest):
        await container.profile_service.update_field(
            USER, "time", "晚上", confidence=0.8, source="conversation",
            valid_from=now + timedelta(days=1), valid_to=now,
        )


async def test_verification_follows_source_and_user_edit_is_confirmed(container: Container) -> None:
    """第 3.1 节：来源是“从哪儿来”，核实状态是“确认到什么程度”。"""
    record = await container.profile_service.update_field(
        USER, "school", "河北大学", confidence=1.0, source=ProfileSource.RECORD.value
    )
    assert record.verification is ProfileVerification.RECORD
    edited = await container.profile_service.correct_field(USER, "school", "河北大学（本部）")
    assert edited.source is ProfileSource.USER_EDIT
    assert edited.verification is ProfileVerification.USER_CONFIRMED
    assert edited.entry_version == record.entry_version + 1


async def test_user_correction_of_a_multi_value_record_does_not_report_a_false_conflict(
    container: Container,
) -> None:
    """兴趣是多值记录：用户更正后回写的是单项列表，不能因此被误判成版本冲突。"""
    await container.profile_service.update_field(
        USER, "interest", ["调试程序"], confidence=0.8, source="conversation"
    )
    edited = await container.profile_service.correct_field(USER, "interest", "把程序跑通")
    assert edited.value == ["把程序跑通"]
    assert edited.verification is ProfileVerification.USER_CONFIRMED


async def test_conflict_and_withdrawn_records_leave_purpose_views(container: Container) -> None:
    """第 7/8 节：冲突/撤回的记录不能继续进入业务读取。"""
    saved = await container.profile_service.update_field(
        USER, "major", "土木工程", confidence=0.9, source="conversation"
    )
    assert profile_taxonomy.records_for_purpose(ProfilePurpose.MAJOR_RETRIEVAL, [saved])
    conflict = saved.model_copy(update={"status": ProfileEntryStatus.CONFLICT})
    withdrawn = saved.model_copy(update={"status": ProfileEntryStatus.WITHDRAWN})
    corrected = saved.model_copy(update={"status": ProfileEntryStatus.CORRECTED})
    assert profile_taxonomy.records_for_purpose(ProfilePurpose.MAJOR_RETRIEVAL, [conflict]) == []
    assert profile_taxonomy.records_for_purpose(ProfilePurpose.MAJOR_RETRIEVAL, [withdrawn]) == []
    assert profile_taxonomy.records_for_purpose(ProfilePurpose.MAJOR_RETRIEVAL, [corrected]) == [corrected]


# ---------------------------------------------------------------------------
# 取数契约：专业独立，兴趣不成为职业名称（P01-P04、P27）
# ---------------------------------------------------------------------------


async def test_major_retrieval_stays_independent_when_interest_is_present() -> None:
    """P02：专业＋“把东西真正跑起来的过程” → 专业检索保留，兴趣不成为职业名称。"""
    client = _Client()
    result = await XueZhiDataSourceGateway(client).fetch(
        _request(
            [
                {"key": "major", "value": "人工智能"},
                {"key": "interest", "value": ["把东西真正跑起来的过程"]},
            ]
        )
    )
    assert not result.degraded
    assert ("speciality", "人工智能") in client.calls
    assert ("occupation", "人工智能") in client.calls
    assert all("把东西真正跑起来的过程" not in term for _, term in client.calls)
    assert result.details["query"] == {"major": ["人工智能"], "career": []}
    assert result.details["counts"]["occupation"] >= 1
    assert result.details["counts"]["career_case"] >= 1
    assert next(r for r in result.records if r.kind == "occupation").metadata["matched_from"] == "search"


async def test_short_interest_phrase_does_not_get_fuzzy_matched_into_occupations() -> None:
    """P03：专业＋“调bug” → 不按“调”模糊查出调香师 / 旅行社计调。"""
    client = _Client()
    result = await XueZhiDataSourceGateway(client).fetch(
        _request(
            [
                {"key": "major", "value": "人工智能"},
                {"key": "interest", "value": ["调bug"]},
            ]
        )
    )
    assert not result.degraded
    assert ("occupation", "调bug") not in client.calls
    assert ("case", "调bug") not in client.calls
    assert result.details["query"]["career"] == []


async def test_interest_alone_never_becomes_a_career_query() -> None:
    """P04：只有兴趣、没有专业 → 不推断专业，也不拿兴趣当职业名称。"""
    client = _Client()
    result = await XueZhiDataSourceGateway(client).fetch(
        _request([{"key": "interest", "value": ["把东西真正跑起来的过程"]}])
    )
    assert client.calls == []
    assert result.records == []
    assert result.details["query"] == {"major": [], "career": []}
    assert result.details["counts"] == {"speciality": 0, "occupation": 0, "career_case": 0}


async def test_explicit_career_focus_drives_occupation_search() -> None:
    """P05/P06：明确的职业关注才成为职业检索词，并与专业结果分开报告。"""
    client = _Client()
    result = await XueZhiDataSourceGateway(client).fetch(
        _request(
            [
                {"key": "major", "value": "人工智能"},
                {"key": "target_direction", "value": "算法工程师"},
                {"key": "interest", "value": ["把东西真正跑起来的过程"]},
            ]
        )
    )
    assert ("occupation", "算法工程师") in client.calls
    assert ("speciality", "人工智能") in client.calls
    assert result.details["query"] == {"major": ["人工智能"], "career": ["算法工程师"]}
    occupation = next(r for r in result.records if r.kind == "occupation")
    assert occupation.metadata["relation"] == "direction"


async def test_official_mapping_is_reported_separately_from_name_search() -> None:
    """P27：区分官方专业映射 / 名称检索；不把“没取到职业”说成平台未收录。"""
    client = _Client(linked=True)
    result = await XueZhiDataSourceGateway(client).fetch(
        _request([{"key": "major", "value": "人工智能"}])
    )
    assert result.details["occupation_sources"] == {"official_mapping": 1, "name_search": 0}
    assert ("occupation", "人工智能") not in client.calls


async def test_intel_status_reports_major_occupation_and_case_counts(container: Container) -> None:
    """第 8 节：专业、职业、案例分别报数；“职业 0 条”不等于平台没有收录。"""
    from zhiyin_business.services.function import DefaultFunctionService
    from zhiyin_data_sdk.gateways.datasource import (
        DataSourceGateway,
        DataSourceRecord,
        DataSourceResult,
    )

    class _OnlySpeciality(DataSourceGateway):
        async def fetch(self, request: Any) -> DataSourceResult:
            return DataSourceResult(
                source="xuezhi",
                records=[
                    DataSourceRecord(
                        id="S1",
                        kind="speciality",
                        title="人工智能",
                        text="专业介绍",
                        source_url="https://xz.chsi.com.cn/speciality",
                    )
                ],
                details={
                    "query": {"major": ["人工智能"], "career": []},
                    "counts": {"speciality": 1, "occupation": 0, "career_case": 0},
                    "occupation_sources": {},
                },
            )

    await container.profile_service.update_field(
        USER, "major", "人工智能", confidence=0.9, source="conversation"
    )
    service = DefaultFunctionService(
        assets=container.asset_service,
        behaviors=container.behavior_service,
        object_store=container.object_store,
        calendar=container.calendar,
        track_events=container.track_events,
        notifications=container.notifications,
        registry=container.registry_service,
        profiles=container.profile_service,
        data_sources=_OnlySpeciality(),
        notifier=None,
    )
    await service.fetch_external_intel(USER, limit=8)
    info = await service.intel_fetch_status(USER)
    assert info["status"] == "ok"
    assert info["counts"] == {"speciality": 1, "occupation": 0, "career_case": 0}
    assert info["query"] == {"major": ["人工智能"], "career": []}
    assert "职业 0 条" in info["message"]

