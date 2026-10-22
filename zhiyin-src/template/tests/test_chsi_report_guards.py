"""Guards added after a real CHSI verification exposed stale/foreign report risks."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from zhiyin_business.services.ai_tasks import AiTaskService
from zhiyin_data_sdk.gateways.chsi import (
    ChsiField,
    ChsiReport,
    ChsiReportKind,
    ChsiVerifyError,
    ChsiVerifyErrorKind,
)
from zhiyin_infrastructure.chsi.client import is_report_expired, parse_chsi_date
from zhiyin_infrastructure.chsi.gateway import OnlineVerificationGateway
from zhiyin_kernel.academic_time import study_year_from_enrollment
from zhiyin_kernel.blackboard import Profile, ProfileField
from zhiyin_kernel.enums import ProfileSource, ProfileVerification
from zhiyin_kernel.registry import AgentDescriptor, ChsiFieldSpec


EXPIRED_PAGE = """
<div class="m_cnt_m">
  <h4 class="main_title">教育部学籍在线验证报告</h4>
  <table>
    <tr><td>姓名</td><td>张某某</td><td>院校名称</td><td>某某大学</td></tr>
    <tr><td>专业</td><td>土木工程</td><td>学籍状态</td><td>在学</td></tr>
    <tr><td>有效期至</td><td>2020-01-01</td></tr>
  </table>
</div>
<div class="flex-base">学信网</div>
"""


class _ExpiredClient:
    base_url = "https://www.chsi.com.cn"

    async def fetch_report_html(self, code: str) -> tuple[str, str]:
        return EXPIRED_PAGE, "https://www.chsi.com.cn/xlcx/bgcx.jsp"


def test_report_expiry_parser_handles_chinese_and_iso_dates() -> None:
    assert parse_chsi_date("2028年06月30日") == date(2028, 6, 30)
    assert parse_chsi_date("2028-06-30") == date(2028, 6, 30)
    assert is_report_expired("2020-01-01", today=date(2026, 10, 22))
    assert not is_report_expired("2028-06-30", today=date(2026, 10, 22))
    assert not is_report_expired("", today=date(2026, 10, 22))


@pytest.mark.asyncio
async def test_gateway_rejects_an_expired_report_even_when_fields_parse() -> None:
    gateway = OnlineVerificationGateway(_ExpiredClient())  # type: ignore[arg-type]
    with pytest.raises(ChsiVerifyError) as error:
        await gateway.verify("123456789012")
    assert error.value.kind is ChsiVerifyErrorKind.EXPIRED
    assert "过期" in str(error.value)


class _ReportChsi:
    async def verify(self, code: str) -> ChsiReport:
        return ChsiReport(
            code=code,
            kind=ChsiReportKind.ENROLLMENT,
            fields=[
                ChsiField(key="student_name", label="姓名", value="李四"),
                ChsiField(key="student_no", label="学号", value="20240002"),
                ChsiField(key="major", label="专业", value="计算机科学与技术"),
            ],
        )


class _Profiles:
    def __init__(self) -> None:
        self.fields = [
            ProfileField(
                key="student_name",
                value="张三",
                confidence=0.9,
                source=ProfileSource.CONVERSATION,
                updated_at=datetime.now(timezone.utc),
            ),
            ProfileField(
                key="student_no",
                value="20240001",
                confidence=0.9,
                source=ProfileSource.CONVERSATION,
                updated_at=datetime.now(timezone.utc),
            ),
        ]
        self.written: list[str] = []

    async def get(self, user_id: str):
        return None

    async def get_fields(self, user_id: str, keys=None):
        return list(self.fields)

    async def update_field(self, user_id, key, value, **kwargs):
        self.written.append(key)
        raise AssertionError(f"身份不一致时不应写画像：{key}")


class _Registry:
    async def get_agent(self, agent_id: str) -> AgentDescriptor:
        return AgentDescriptor(id=agent_id, name="信息侦查员")

    async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
        return [
            ChsiFieldSpec(key="student_name", label="姓名"),
            ChsiFieldSpec(key="student_no", label="学号"),
            ChsiFieldSpec(key="major", label="专业"),
        ]

    async def list_task_progress(self) -> list:
        return []


@pytest.mark.asyncio
async def test_a_report_for_another_student_is_rejected_before_writing() -> None:
    profiles = _Profiles()
    service = AiTaskService(
        profiles=profiles,  # type: ignore[arg-type]
        behaviors=None,  # type: ignore[arg-type]
        assets=None,  # type: ignore[arg-type]
        chsi=_ReportChsi(),  # type: ignore[arg-type]
        registry=_Registry(),  # type: ignore[arg-type]
    )
    frames = [frame async for frame in service.stream("u1", "bind.chsi", "123456789012")]
    assert "error" in frames[-1]
    assert frames[-1]["error"]["kind"] == "identity_mismatch"
    assert profiles.written == []


class _DerivationReportChsi:
    report_kind = ChsiReportKind.ENROLLMENT

    async def verify(self, code: str) -> ChsiReport:
        return ChsiReport(
            code=code,
            kind=self.report_kind,
            fields=[
                ChsiField(key="major", label="专业名称", value="计算机科学与技术"),
                ChsiField(key="enrolled_at", label="入学日期", value="2024-08-22"),
            ],
        )


class _DerivationRegistry:
    async def get_agent(self, agent_id: str) -> AgentDescriptor:
        return AgentDescriptor(id=agent_id, name="信息侦查员")

    async def list_chsi_fields(self) -> list[ChsiFieldSpec]:
        return [
            ChsiFieldSpec(key="major", label="专业"),
            ChsiFieldSpec(key="enrolled_at", label="入学日期"),
        ]

    async def list_task_progress(self) -> list:
        return []


class _RecordingProfiles:
    """只实现 bind.chsi 用到的画像读写。"""

    def __init__(self, fields: list[ProfileField] | None = None) -> None:
        self.fields = list(fields or [])

    async def get_fields(self, user_id: str, keys=None):
        return list(self.fields)

    async def get(self, user_id: str):
        return Profile(
            id="p1",
            user_id=user_id,
            updated_at=datetime.now(timezone.utc),
            fields=list(self.fields),
        )

    async def update_field(self, user_id, key, value, **kwargs):
        field = ProfileField(
            key=key,
            label=kwargs.get("label", ""),
            value=value,
            confidence=kwargs.get("confidence", 0.0),
            source=kwargs.get("source", ProfileSource.RECORD.value),
            updated_at=datetime.now(timezone.utc),
            evidence=list(kwargs.get("evidence") or []),
            attributes=dict(kwargs.get("attributes") or {}),
            verification=kwargs.get("verification") or ProfileVerification.PENDING,
            origin_ref=kwargs.get("origin_ref", ""),
            valid_to=kwargs.get("valid_to"),
        )
        self.fields = [item for item in self.fields if item.key != key] + [field]
        return field


def _derivation_service(
    profiles: _RecordingProfiles, chsi: object | None = None
) -> AiTaskService:
    return AiTaskService(
        profiles=profiles,  # type: ignore[arg-type]
        behaviors=None,  # type: ignore[arg-type]
        assets=None,  # type: ignore[arg-type]
        chsi=chsi or _DerivationReportChsi(),  # type: ignore[arg-type]
        registry=_DerivationRegistry(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_chsi_derives_the_current_study_year_from_enrollment_date() -> None:
    """报告只有入学日期；界面上的年级必须是「2024-08 入学 → 大三」，不是「大一」。"""
    profiles = _RecordingProfiles()
    service = _derivation_service(profiles)
    frames = [frame async for frame in service.stream("u1", "bind.chsi", "123456789012")]
    assert "result" in frames[-1], frames[-1]

    expected = study_year_from_enrollment("2024-08-22")
    assert expected is not None
    fields = {field.key: field for field in profiles.fields}
    study_year = fields["study_year"]
    assert study_year.value == expected
    assert study_year.source is ProfileSource.RECORD
    assert study_year.verification is ProfileVerification.PENDING
    assert study_year.attributes["derived_from"] == "入学日期 2024-08-22"
    assert study_year.origin_ref.startswith("derived://study_year/enrolled_at=")
    assert study_year.valid_to is not None

    steps = {step.id: step for step in frames[-1]["result"].data.steps}
    assert steps["s2"].got == 2  # 专业 + 入学日期；学习阶段是推算，不在这两步里冒充报告字段
    assert steps["s2b"].got == 1
    assert expected in steps["s2b"].detail
    assert "2024-08-22" in steps["s2b"].detail


@pytest.mark.asyncio
async def test_an_education_report_does_not_derive_a_current_grade() -> None:
    """学历/学位报告是毕业后的证明；拿它的入学日期推「现在大几」会算错。"""

    class _EducationReport(_DerivationReportChsi):
        report_kind = ChsiReportKind.EDUCATION

    profiles = _RecordingProfiles()
    service = _derivation_service(profiles, _EducationReport())
    frames = [frame async for frame in service.stream("u1", "bind.chsi", "123456789012")]
    assert "result" in frames[-1], frames[-1]
    assert "study_year" not in {field.key for field in profiles.fields}
    assert "s2b" not in {step.id for step in frames[-1]["result"].data.steps}


@pytest.mark.asyncio
async def test_chsi_never_overwrites_a_user_confirmed_study_year() -> None:
    profiles = _RecordingProfiles(
        [
            ProfileField(
                key="study_year",
                value="大一",
                confidence=1.0,
                source=ProfileSource.USER_EDIT,
                verification=ProfileVerification.USER_CONFIRMED,
                updated_at=datetime.now(timezone.utc),
            )
        ]
    )
    service = _derivation_service(profiles)
    frames = [frame async for frame in service.stream("u1", "bind.chsi", "123456789012")]
    assert "result" in frames[-1], frames[-1]

    fields = {field.key: field for field in profiles.fields}
    assert fields["study_year"].value == "大一"
    assert fields["study_year"].source is ProfileSource.USER_EDIT
    steps = {step.id: step for step in frames[-1]["result"].data.steps}
    assert steps["s2b"].got == 0
    assert "没有用推算值覆盖" in steps["s2b"].detail


@pytest.mark.asyncio
async def test_chsi_refreshes_its_own_previous_derived_study_year() -> None:
    profiles = _RecordingProfiles(
        [
            ProfileField(
                key="study_year",
                value="大二",
                confidence=0.8,
                source=ProfileSource.RECORD,
                verification=ProfileVerification.PENDING,
                origin_ref="derived://study_year/enrolled_at=2024-08-22",
                updated_at=datetime.now(timezone.utc),
            )
        ]
    )
    service = _derivation_service(profiles)
    frames = [frame async for frame in service.stream("u1", "bind.chsi", "123456789012")]
    assert "result" in frames[-1], frames[-1]
    assert {field.key: field for field in profiles.fields}["study_year"].value == "大三"


def test_an_expired_derived_year_reopens_the_collection_step() -> None:
    """推算值带有效期；过期后不能继续替本人关掉「当前学习阶段」。"""
    from types import SimpleNamespace

    from zhiyin_business.policies.collection import plan_collection

    profile = Profile(
        id="p1",
        user_id="u1",
        updated_at=datetime.now(timezone.utc),
        fields=[
            ProfileField(
                key="study_year",
                value="大三",
                confidence=0.8,
                source=ProfileSource.RECORD,
                updated_at=datetime.now(timezone.utc),
                valid_to=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        ],
    )
    plan = plan_collection(
        profile,
        rules=[
            SimpleNamespace(
                key="study_year",
                label="当前学习阶段",
                source="conversation",
                why="不同阶段的重点不同",
                ask="你现在读大几？",
            )
        ],
    )
    step = next(item for item in plan.steps if item.key == "study_year")
    assert step.got is False
    assert step.state == "missing"
    assert step.ask == "你现在读大几？"


@pytest.mark.asyncio
async def test_sse_error_frames_carry_the_api_code_for_chsi_kinds() -> None:
    """业务层只懂 kind；api 层必须补 code，否则前端无法区分可修正错误。"""
    from zhiyin_api.controllers.ai_controller import _frames

    class _Facade:
        async def run_ai_task(self, user_id: str, key: str, arg: str):
            yield {"error": {"kind": "malformed_code", "message": "这串码的格式不对。"}}

    frames = [frame async for frame in _frames(_Facade(), "u1", "bind.chsi", "12345")]
    assert frames[-1]["error"]["code"] == 1001
    assert frames[-1]["error"]["message"] == "这串码的格式不对。"
