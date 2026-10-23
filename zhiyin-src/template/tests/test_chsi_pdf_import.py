"""Synthetic reports exercise the pipeline; they do not replace real-PDF acceptance."""
import asyncio
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from zhiyin_business.contracts.chsi_import import ChsiPdfConfirm
from zhiyin_business.services.chsi_import import ChsiPdfImportService
from zhiyin_business.services.profile import DefaultProfileService
from zhiyin_data_sdk.gateways.chsi import ChsiReport, ChsiField, ChsiReportKind
from zhiyin_infrastructure.chsi.pdf import ChsiPdfReader
from zhiyin_infrastructure.local.chsi_imports import InMemoryChsiImportRepository
from zhiyin_infrastructure.local.repository import InMemoryProfileRepository
from zhiyin_kernel.enums import ProfileVerification
from zhiyin_kernel.errors import InvalidRequest, DuplicateResource, ResourceNotFound
from zhiyin_kernel.registry import ChsiFieldSpec


def pdf_bytes(lines=None, pages=1, encrypted=False):
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    output = io.BytesIO()
    doc = canvas.Canvas(output, encrypt='secret' if encrypted else None)
    default = ['教育部学籍在线验证报告', '姓名：张三', '学校名称：测试大学', '专业名称：计算机科学与技术',
               '学号：20240001', '入学日期：2024-09-01', '有效期至：2099-12-31',
               '证件号码：123456789012345678', '在线验证码：A123456789012345']
    for _ in range(pages):
        doc.setFont('STSong-Light', 12)
        for index, line in enumerate(default if lines is None else lines):
            doc.drawString(40, 800 - index * 25, line)
        doc.showPage()
    doc.save()
    return output.getvalue()


class Events:
    def __init__(self): self.events = []
    async def publish(self, event): self.events.append(event)


class Registry:
    async def list_chsi_fields(self):
        return [ChsiFieldSpec(key=key, label=key) for key in
                ['student_name', 'student_no', 'school', 'major', 'enrolled_at']]


class Reader:
    def __init__(self, **values):
        self.values = {'student_name': '张三', 'student_no': '20240001', 'school': '测试大学',
                       'major': '计算机科学与技术', 'enrolled_at': '2024-09-01'} | values
        self.expiry = '2099-12-31'
    async def read(self, data):
        return ChsiReport(acquisition='pdf', kind=ChsiReportKind.ENROLLMENT, valid_until=self.expiry,
            fields=[ChsiField(key=key, label=key, value=value) for key, value in self.values.items()])


def setup(reader=None):
    repo, events = InMemoryProfileRepository(), Events()
    profiles = DefaultProfileService(repo, events)
    records = InMemoryChsiImportRepository(repo)
    return ChsiPdfImportService(profiles, records, reader or Reader(), Registry()), repo, events


def request(preview, **kwargs):
    return ChsiPdfConfirm(preview_id=preview.preview_id,
        selected_keys=[field.key for field in preview.fields if field.selected],
        ownership_confirmed=True, **kwargs)


async def test_real_subprocess_extracts_text_and_drops_private_identifiers():
    report = await ChsiPdfReader().read(pdf_bytes())
    assert report.value_of('school') == '测试大学'
    assert report.value_of('major') == '计算机科学与技术'
    assert report.acquisition == 'pdf' and report.valid_until == '2099-12-31'
    serialized = report.model_dump_json()
    assert '123456789012345678' not in serialized
    assert 'A123456789012345' not in serialized
    assert not report.verified_at and not report.code


@pytest.mark.parametrize('data', [b'not pdf', b'%PDF-broken', b'x' * 2_000_001], ids=['not-pdf','broken','oversize'])
async def test_invalid_pdf(data):
    with pytest.raises(InvalidRequest): await ChsiPdfReader().read(data)


@pytest.mark.parametrize('kwargs', [dict(pages=4), dict(encrypted=True), dict(lines=[]),
    dict(lines=['教育部学历证书电子注册备案表']), dict(lines=['教育部学籍在线验证报告', '姓名：张三'])])
async def test_wrong_reports_rejected(kwargs):
    with pytest.raises(InvalidRequest): await ChsiPdfReader().read(pdf_bytes(**kwargs))


async def test_pdf_timeout_terminates_child():
    with pytest.raises(InvalidRequest, match='超时'):
        await ChsiPdfReader(timeout=0.001).read(pdf_bytes())


async def test_pdf_table_labels_and_school_name_suffix_are_not_confused():
    report = await ChsiPdfReader().read(pdf_bytes(lines=[
        '教育部学籍在线验证报告', '姓名：张三    性别：男',
        '院校名称：测试职业学校', '专业名称：学校管理', '学制：4年    类型：普通高等教育',
        '学习形式：普通全日制', '入学日期：2024-09-01', '有效期至：2099年12月31日']))
    assert report.value_of('school') == '测试职业学校'
    assert report.value_of('major') == '学校管理'
    assert report.value_of('duration') == '4年'


async def test_preview_confirm_selective_and_idempotent_no_online_calls():
    service, repo, events = setup()
    preview = await service.preview('alice', b'synthetic')
    assert await repo.list_fields('alice') == []
    assert preview.requires_ownership_confirmation
    confirmation = request(preview)
    receipts = await asyncio.gather(service.confirm('alice', confirmation), service.confirm('alice', confirmation))
    assert receipts[0] == receipts[1]
    fields = await repo.list_fields('alice')
    assert fields and len(events.events) == len(receipts[0].imported)
    assert all(f.verification is ProfileVerification.RECORD for f in fields if f.key != 'study_year')
    row = service.records.records[preview.preview_id]
    assert row['payload'] == {} and '张三' not in json.dumps(row, ensure_ascii=False)
    assert all(f.entry_version == 1 for f in fields)


async def test_ownership_and_protected_fields():
    service, repo, _ = setup()
    await service.profiles.update_field('alice', 'school', '已核验大学', confidence=1, source='record', verification='verified')
    await service.profiles.update_field('alice', 'study_year', '大四', confidence=1, source='user_edit')
    await service.profiles.update_field('alice', 'major', '土木工程', confidence=1, source='user_edit')
    preview = await service.preview('alice', b'synthetic')
    fields = {f.key: f for f in preview.fields}
    assert not fields['school'].selectable and not fields['study_year'].selectable
    assert fields['major'].selectable and not fields['major'].selected
    body = request(preview)
    body.ownership_confirmed = False
    with pytest.raises(InvalidRequest, match='本人'): await service.confirm('alice', body)
    body.ownership_confirmed = True
    body.selected_keys.append('school')
    with pytest.raises(InvalidRequest): await service.confirm('alice', body)
    body.selected_keys.remove('school')
    body.selected_keys.append('major')
    await service.confirm('alice', body)
    actual = {f.key: f for f in await repo.list_fields('alice')}
    assert actual['school'].value == '已核验大学' and actual['study_year'].value == '大四'
    assert actual['major'].value == '计算机科学与技术'
    assert actual['major'].verification is ProfileVerification.RECORD


@pytest.mark.parametrize('enrolled,current,expected,conflict', [
    ('2024-08-22', '大一', '大三', True),
    ('2024-08-22', '大三', '大三', False),
    ('无法识别', '大一', None, False),
])
async def test_preview_separates_derived_year_from_protected_current_year(monkeypatch, enrolled, current, expected, conflict):
    from datetime import date
    from zhiyin_kernel.academic_time import study_year_from_enrollment
    monkeypatch.setattr('zhiyin_business.services.chsi_import.study_year_from_enrollment',
        lambda value: study_year_from_enrollment(value, today=date(2026, 10, 23)))
    service, repo, _ = setup(Reader(enrolled_at=enrolled))
    await service.profiles.update_field('alice', 'study_year', current, confidence=1, source='user_edit')
    before = next(f for f in await repo.list_fields('alice') if f.key == 'study_year')
    preview = await service.preview('alice', b'synthetic')
    field = next(f for f in preview.fields if f.key == 'study_year')
    assert field.value == expected and field.current_value == current
    assert not field.selectable and not field.selected
    assert ('年级不一致' in field.reason) is conflict
    assert any('年级不一致' in w for w in preview.warnings) is conflict
    if expected is None:
        assert '无法' in field.reason
    await service.confirm('alice', request(preview))
    after = next(f for f in await repo.list_fields('alice') if f.key == 'study_year')
    assert after == before


async def test_identity_mismatch_expiry_and_unknown_expiry():
    service, repo, _ = setup()
    await service.profiles.update_field('alice', 'student_name', '李四', confidence=1, source='user_edit')
    preview = await service.preview('alice', b'synthetic')
    assert not preview.can_import
    with pytest.raises(InvalidRequest): await service.confirm('alice', request(preview))
    service, _, _ = setup()
    service.reader.expiry = '2020-01-01'
    assert not (await service.preview('alice', b'synthetic')).can_import
    service.reader.expiry = ''
    preview = await service.preview('alice', b'synthetic')
    assert preview.can_import and any('无法判断有效期' in warning for warning in preview.warnings)


async def test_preview_authorization_expiry_cleanup_and_optimistic_conflict():
    service, repo, _ = setup()
    preview = await service.preview('alice', b'synthetic')
    with pytest.raises(ResourceNotFound): await service.confirm('bob', request(preview))
    await service.profiles.update_field('alice', 'major', '新专业', confidence=1, source='user_edit')
    with pytest.raises(DuplicateResource): await service.confirm('alice', request(preview))
    service.records.records[preview.preview_id]['expires_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    with pytest.raises(InvalidRequest, match='过期'): await service.confirm('alice', request(preview))
    assert await service.records.cleanup() == 1


async def test_mid_write_failure_rolls_back_every_field_and_receipt(monkeypatch):
    service, repo, events = setup()
    preview = await service.preview('alice', b'synthetic')
    original = repo.upsert_field
    count = 0
    async def failing(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2: raise RuntimeError('injected failure')
        return await original(*args, **kwargs)
    monkeypatch.setattr(repo, 'upsert_field', failing)
    with pytest.raises(RuntimeError): await service.confirm('alice', request(preview))
    assert await repo.list_fields('alice') == []
    assert service.records.records[preview.preview_id]['status'] == 'pending'
    assert not events.events


async def test_online_http_403_has_specific_message_without_bearer_code(monkeypatch):
    import httpx
    from zhiyin_infrastructure.chsi import client as module
    from zhiyin_data_sdk.gateways.chsi import ChsiVerifyError
    factory = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: factory(
        **kwargs, transport=httpx.MockTransport(lambda req: httpx.Response(403))))
    with pytest.raises(ChsiVerifyError, match='服务器访问学信网核验页面被拒绝') as error:
        await module.ChsiReportClient().fetch_report_html('A123456789012345')
    assert 'A123456789012345' not in str(error.value)
    assert not error.value.detail
