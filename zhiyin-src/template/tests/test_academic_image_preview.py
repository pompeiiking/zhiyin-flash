"""Image decoding, shared preview and real permission/version boundaries (no network)."""
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from agno.run import RunContext

from zhiyin_business.contracts.academic_preview import AcademicPreviewRequest
from zhiyin_business.services.academic import DefaultAcademicService
from zhiyin_business.services.academic_preview import AcademicPreviewService
from zhiyin_business.services.memory import DefaultConversationMemoryService
from zhiyin_infrastructure.academic import ManualAcademicImporter
from zhiyin_infrastructure.imagefile import image_data_url
from zhiyin_infrastructure.local.repository import InMemoryAcademicSnapshotRepository, InMemoryConversationMemoryRepository
from zhiyin_infrastructure.local.object_store import LocalFileStore
from zhiyin_infrastructure.textfile import LocalTextExtractor
from zhiyin_kernel.errors import InvalidRequest
from tests.test_materials import client


def png(size=(40, 40)):
    output = BytesIO()
    Image.new('RGB', size, 'blue').save(output, format='PNG')
    return output.getvalue()


def services(tmp_path, result=None):
    importer = ManualAcademicImporter()
    store = LocalFileStore(str(tmp_path))
    memory = DefaultConversationMemoryService(InMemoryConversationMemoryRepository(), documents=LocalTextExtractor(),
        object_store=store, image_reader=image_data_url)
    academic = DefaultAcademicService(InMemoryAcademicSnapshotRepository(), importer)
    vision = AsyncMock(return_value=result or {'courses': [{'name': '高等数学', 'weekday': 2, 'start_period': 1, 'end_period': 2, 'weeks': '1-16周'}], 'warnings': []})
    return memory, academic, AcademicPreviewService(academic, importer, memory, store, vision), vision


def request(**kwargs):
    return AcademicPreviewRequest(kind='courses', school='测试大学', term='2026-2027-1', **kwargs)


def test_actual_image_decoding_and_dimension_limits():
    assert image_data_url(png()).startswith('data:image/jpeg;base64,')
    for value in (b'text disguised as png', png((8193, 1))):
        with pytest.raises(InvalidRequest):
            image_data_url(value)


@pytest.mark.parametrize('base,model,override,wanted', [
    ('https://api.deepseek.com', 'deepseek-chat', '', 'deepseek-flash'),
    ('https://api.deepseek.com/v1', 'deepseek-v4-pro', '', 'deepseek-flash'),
    ('https://api.deepseek.com', 'deepseek-flash', '', 'deepseek-flash'),
    ('https://compatible.example/v1', 'vision-capable-model', '', 'vision-capable-model'),
    ('https://compatible.example/v1', 'text-model', 'configured-vision', 'configured-vision'),
])
def test_vision_route_is_explicit_and_never_replaces_text_model(base, model, override, wanted):
    from zhiyin_infrastructure.ai.agno_runtime import AgnoModelRuntime
    runtime = AgnoModelRuntime(api_key='test', base_url=base, model=model, vision_model=override)
    assert runtime.create_model().id == model
    assert runtime.create_model(vision=True).id == wanted


async def test_image_storage_has_no_binary_in_receipt_and_is_owner_scoped(tmp_path):
    memory, _, _, _ = services(tmp_path)
    result = await memory.put_material('u1', name='截图.png', data=png())
    body = await memory.material_body('u1', result.material_id)
    assert body.image_data_url.startswith('data:image/jpeg;base64,') and not body.text
    assert 'base64' not in result.model_dump_json() and result.chars == 0
    with pytest.raises(LookupError):
        await memory.material_body('u2', result.material_id)
    with pytest.raises(InvalidRequest):
        await memory.put_material('u1', name='fake.png', data=b'not an image')


async def test_image_preview_is_readonly_and_commit_preserves_grades(tmp_path):
    memory, academic, previews, vision = services(tmp_path)
    await academic.import_('u1', grades_raw='[{"name":"程序设计","score":"0","credit":"3"}]', term='2025-2026-2')
    material = await memory.put_material('u1', name='课表.png', data=png())
    preview = await previews.prepare('u1', request(material_id=material.material_id))
    assert not (await academic.get('u1')).courses
    assert preview.courses[0].weekday == 2 and preview.courses[0].weeks == '1-16周'
    assert vision.call_args.args[0].startswith('data:image/jpeg;base64,')
    await previews.commit('u1', preview.preview_id)
    snapshot = await academic.get('u1')
    assert snapshot.courses == preview.courses and snapshot.grades[0].score == '0'
    assert snapshot.grades[0].term == '2025-2026-2'
    with pytest.raises(InvalidRequest):
        await previews.commit('u1', preview.preview_id)


async def test_preview_is_bound_to_user_and_snapshot(tmp_path):
    _, academic, previews, _ = services(tmp_path)
    preview = await previews.prepare('u1', request(text='[{"name":"高等数学","weekday":2,"start_period":1,"end_period":2}]'))
    with pytest.raises(InvalidRequest):
        await previews.read('u2', preview.preview_id)
    await academic.import_('u1', courses_raw='[{"name":"大学英语"}]')
    with pytest.raises(InvalidRequest, match='已经变化'):
        await previews.commit('u1', preview.preview_id)
    assert (await academic.get('u1')).courses[0].name == '大学英语'


async def test_atomic_expected_version_guard_prevents_racing_import(tmp_path):
    _, academic, previews, _ = services(tmp_path)
    preview = await previews.prepare('u1', request(text='[{"name":"高等数学"}]'))
    await academic.import_('u1', courses_raw='[{"name":"大学英语"}]')
    with pytest.raises(InvalidRequest, match='已经变化'):
        await academic.import_('u1', courses_raw='[{"name":"不应保存"}]', expected_version=preview.expected_version)


@pytest.mark.parametrize('result', [
    {'courses': [{'name': '数学', 'weekday': 8}]},
    {'courses': [{'name': '数学', 'start_period': 3, 'end_period': 1}]},
    {'courses': [{'name': ''}]},
    {'courses': [{'name': '数学', 'unknown': 'x'}]},
    {'courses': []},
])
async def test_unreliable_recognition_never_mutates_records(tmp_path, result):
    memory, academic, previews, _ = services(tmp_path, result)
    material = await memory.put_material('u1', name='表格.png', data=png())
    with pytest.raises(InvalidRequest):
        await previews.prepare('u1', request(material_id=material.material_id))
    assert await academic.get('u1') is None


async def test_grades_zero_deduplication_and_preview_match_written_rows(tmp_path):
    _, academic, previews, _ = services(tmp_path)
    row = {'name': '程序设计', 'score': '0', 'point': '0', 'credit': '3'}
    preview = await previews.prepare('u1', AcademicPreviewRequest(kind='grades', school='测试大学', term='本学期', text=json.dumps([row, row])))
    assert len(preview.grades) == 1 and preview.warnings
    await previews.commit('u1', preview.preview_id)
    assert (await academic.get('u1')).grades == preview.grades
    with pytest.raises(InvalidRequest):
        await previews.prepare('u1', AcademicPreviewRequest(kind='grades', school='测试大学', term='本学期', text='[{"name":"数学","score":""}]'))


async def test_tool_rejects_material_outside_current_turn():
    from zhiyin_boot.module_platform import product_tools
    handlers = {tool.name: tool.handler for module in product_tools(SimpleNamespace(extra={'modules': {}})) for tool in module.tools}
    with pytest.raises(InvalidRequest, match='当前会话'):
        await handlers['academic.preview'](RunContext(user_id='u1', run_id='r', session_id='s', dependencies={'material_ids': []}),
            kind='courses', school='大学', term='学期', material_id='mat_foreign')


@pytest.mark.parametrize('authorization', ['automatic', 'explicit'])
async def test_dialogue_academic_import_always_requires_approval(tmp_path, authorization):
    from tests.test_dialogue_runtime import setup, send, action
    _, academic, previews, _ = services(tmp_path)
    prepared = await previews.prepare('u1', request(text='[{"name":"高等数学","weekday":2,"start_period":1,"end_period":2}]'))
    pending = {}
    async def decide(runtime):
        result = await runtime.action(action('academic.import', {'preview_id': prepared.preview_id}, evidence='保存课表', authorization=authorization))
        pending.update(result)
        assert result['state'] == 'proposed' and not result['executed']
    c, engine, session = await setup(decide)
    c.orchestrator.academic_reader = academic.get
    c.orchestrator.academic_previews = previews
    c.orchestrator.academic_writer = previews.commit
    await send(c, session, '保存课表')
    assert await academic.get('u1') is None
    engine.callback = None
    await send(c, session, '确认', option_id=f"action.{pending['action_id']}.accept")
    assert (await academic.get('u1')).courses == prepared.courses


async def test_native_dialogue_sends_image_parts_and_excludes_binary_from_context(monkeypatch):
    from zhiyin_orchestration.agent import AgentRequest
    from zhiyin_orchestration.impl import dialogue_engine
    seen = {}
    class Agent:
        def __init__(self, **kwargs):
            pass
        async def arun(self, input, **kwargs):
            seen['messages'] = input
            return SimpleNamespace(status='completed', messages=[], content='图中蓝色区域在右边。')
    monkeypatch.setattr(dialogue_engine, 'Agent', Agent)
    registry = SimpleNamespace(get_prompt=AsyncMock(return_value=SimpleNamespace(content='回答用户', code='conversation.main', params={})), get_agent=AsyncMock(return_value=None))
    engine = SimpleNamespace(refresh_model=None, _registry=registry, module_tool_names=None, _tools={},
        _model_factory=lambda **kwargs: SimpleNamespace(id='test-vision'), _run_context_kwargs=lambda r: {'dependencies': {}},
        _compose_input=lambda r, context: r.model_dump_json())
    request_ = AgentRequest(agent_id='career_advisor', conversation=True, images=[image_data_url(png())], prompt_vars={'raw_user_message': '蓝色在哪边？'})
    result = await dialogue_engine.invoke_dialogue(engine, request_)
    assert result.valid
    content = seen['messages'][-1].content
    assert content[1]['type'] == 'image_url' and content[1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert 'base64' not in seen['messages'][-2].content and 'base64' not in request_.model_dump_json()


def test_real_http_upload_preview_and_confirmation_share_one_service(client):
    from zhiyin_api.facade import get_facade
    facade = get_facade()
    facade._academic_previews.vision_reader = AsyncMock(return_value={'grades': [
        {'name': '图像测试课程', 'score': '0', 'credit': '3', 'point': '0'}], 'warnings': []})
    uploaded = client.post('/api/v1/app/conversation/material', files={'file': ('成绩.png', png(), 'image/png')})
    assert uploaded.status_code == 200 and 'base64' not in uploaded.text
    preview = client.post('/api/v1/app/academic/preview', json={'kind': 'grades', 'school': '测试大学', 'term': '2026-2027-1',
        'material_id': uploaded.json()['data']['material_id']})
    assert preview.status_code == 200, preview.text
    data = preview.json()['data']
    assert data['grades'][0]['score'] == '0' and data['replace_count'] == 0
    saved = client.post('/api/v1/app/academic/preview/commit', json={'preview_id': data['preview_id']})
    assert saved.status_code == 200, saved.text
    assert saved.json()['data']['grades'] == 1
    assert saved.json()['data']['courses'] == 0
    forged = client.post('/api/v1/app/academic/preview/commit', json={'preview_id': data['preview_id'], 'grades': []})
    assert forged.status_code == 422


async def test_expired_preview_and_disabled_source_are_rejected(tmp_path):
    from datetime import datetime, timedelta, timezone
    from zhiyin_business.services.analysis_access import AnalysisScope, activate
    _, academic, previews, _ = services(tmp_path)
    preview = await previews.prepare('u1', request(text='[{"name":"高等数学"}]'))
    expired = preview.model_copy(update={'expires_at': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    await previews.store.put(previews._key('u1', preview.preview_id), expired.model_dump_json().encode(), content_type='application/json')
    with pytest.raises(InvalidRequest, match='过期'):
        await previews.commit('u1', preview.preview_id)
    with activate(AnalysisScope('u1', frozenset(), None, {})):
        with pytest.raises(InvalidRequest, match='偏好'):
            await previews.prepare('u1', request(text='[{"name":"高等数学"}]'))
    assert await academic.get('u1') is None


async def test_runtime_loads_real_images_without_persisting_binary(tmp_path):
    from tests.test_dialogue_runtime import setup, send
    memory, _, _, _ = services(tmp_path)
    material = await memory.put_material('u1', name='图.png', data=png())
    c, engine, session = await setup()
    c.orchestrator._memories = memory
    await send(c, session, '这张图片里是什么？', material_ids=[material.material_id])
    assert engine.requests[-1].images[0].startswith('data:image/jpeg;base64,')
    assert 'base64' not in engine.requests[-1].model_dump_json()


@pytest.mark.parametrize('text', [
    '[{"name":"数学","weekday":8}]',
    '[{"name":"数学","start_period":3,"end_period":1}]',
    '[{"name":"数学"},{"name":""}]',
    '[{"name":"数学","place":{"nested":"value"}}]',
])
async def test_canonical_json_is_validated_before_permissive_export_parser(tmp_path, text):
    _, _, previews, _ = services(tmp_path)
    with pytest.raises(InvalidRequest):
        await previews.prepare('u1', request(text=text))
