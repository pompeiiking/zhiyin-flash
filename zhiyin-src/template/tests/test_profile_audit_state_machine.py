"""State-machine regressions found by the October 21 profile audit."""
import pytest
from datetime import datetime, timezone
from tests.test_profile_write_path import _setup, _send, _profile_action
from zhiyin_business.services.memory_policy import MemoryPolicyService
from zhiyin_kernel.errors import DuplicateResource, ResourceNotFound, InvalidRequest
from zhiyin_orchestration import AgentResult


async def test_deleting_a_field_withdraws_all_pending_conflicts_and_cannot_resurrect_it():
    c, _ = await _setup(lambda rt: None)
    await c.profile_service.correct_field('u1', 'major', '人工智能')
    revision = await c.profile_service.record_conflict('u1', 'major', '软件工程')
    await c.profile_service.drop_field('u1', 'major')
    assert not await c.profile_service.list_conflicts('u1')
    with pytest.raises(ResourceNotFound):
        await c.profile_service.resolve_conflict('u1', revision.id, choice='revision')
    assert not await c.profile_service.get_fields('u1', ['major'])
    assert 'major' in (await MemoryPolicyService(c.student_state).snapshot('u1'))['denied_keys']
    assert not (await c.student_state.get('u1')).get('conversation_memory_reset_at')


@pytest.mark.parametrize('choice', ['current', 'revision'])
async def test_old_conflict_cannot_override_a_new_personal_correction(choice):
    c, _ = await _setup(lambda rt: None)
    await c.profile_service.correct_field('u1', 'major', '人工智能')
    revision = await c.profile_service.record_conflict('u1', 'major', '软件工程')
    await c.profile_service.correct_field('u1', 'major', '网络工程')
    if choice == 'revision':
        with pytest.raises(DuplicateResource):
            await c.profile_service.resolve_conflict('u1', revision.id, choice=choice)
    else:
        await c.profile_service.resolve_conflict('u1', revision.id, choice=choice)
        assert not await c.profile_service.list_conflicts('u1')
    assert (await c.profile_service.get_fields('u1', ['major']))[0].value == '网络工程'


async def test_identical_proposals_for_the_same_base_version_are_deduplicated():
    c, _ = await _setup(lambda rt: None)
    await c.profile_service.correct_field('u1', 'major', '人工智能')
    ids = [(await c.profile_service.record_conflict('u1', 'major', '软件工程')).id for _ in range(3)]
    assert len(set(ids)) == 1
    assert len(await c.profile_service.list_conflicts('u1')) == 1


@pytest.mark.parametrize('temporary,allowed', [(True, False), (False, True)])
async def test_explicit_save_respects_temporary_but_can_override_automatic_opt_out(temporary, allowed):
    results = []
    async def callback(rt):
        results.append(await rt.action(_profile_action(dict(key='major', value='人工智能'), evidence='人工智能', authorization='explicit')))
    c, s = await _setup(callback)
    m = MemoryPolicyService(c.student_state)
    await m.set_account_automatic('u1', False)
    await m.set_session_temporary('u1', s.id, temporary)
    if allowed:
        await _send(c, s, '请保存人工智能')
    else:
        with pytest.raises(InvalidRequest, match='临时会话'):
            await _send(c, s, '请保存人工智能')
    assert bool(await c.profile_service.get_fields('u1', ['major'])) is allowed
    if allowed:
        assert results[0]['executed'] is True


async def test_main_model_denial_happens_before_fallback_collection_commits():
    c, s = await _setup(lambda rt: None)
    class Model:
        supports_semantic_memory = True
        async def invoke(self, request):
            if request.prompt_code == 'conversation.memory':
                return AgentResult(agent_id=request.agent_id, valid=True, structured={'policy': {'scope': 'none'},
                    'updates': [dict(key='major', value='人工智能', evidence='人工智能', assertion_type='affirmative_self_statement')]})
            assert not await c.profile_service.get_fields('u1', ['major'])
            await MemoryPolicyService(c.student_state).deny_key('u1', 'major')
            return AgentResult(agent_id=request.agent_id, valid=True, raw_text='这条不记录。')
    c.orchestrator._agent_engine = Model()
    await _send(c, s, '我学人工智能，但这条不要记录')
    assert not await c.profile_service.get_fields('u1', ['major'])


async def test_resume_auto_memory_clears_consumed_single_restriction():
    c, s = await _setup(lambda rt: None)
    m = MemoryPolicyService(c.student_state)
    await m.grant_single('u1', s.id, 'major')
    await m.consume_single('u1', s.id, 'major')
    class Model:
        supports_semantic_memory = True
        async def invoke(self, request):
            if request.prompt_code == 'conversation.memory':
                return AgentResult(agent_id=request.agent_id, valid=True, structured={'policy': {'scope': 'account_on'}, 'updates': []})
            return AgentResult(agent_id=request.agent_id, valid=True, raw_text='继续聊。')
    c.orchestrator._agent_engine = Model()
    await _send(c, s, '可以继续自动记录')
    snapshot = await m.snapshot('u1', s.id)
    assert snapshot['account_automatic'] and not snapshot['single_only']
    assert (await m.check_auto_write('u1', s.id, 'interest'))[0]


async def test_rest_correction_without_version_keeps_typed_metadata():
    from zhiyin_boot import wire_application
    from zhiyin_api.facade import get_facade
    from zhiyin_api.dto.workspace import ProfileFieldUpdateRequest
    c, _ = await _setup(lambda rt: None)
    wire_application(c)
    end = datetime(2026, 10, 25, tzinfo=timezone.utc)
    await c.profile_service.correct_field('u1', 'interest', ['编程', '录入'],
        attributes={'items': [dict(value='编程', polarity='like'), dict(value='录入', polarity='dislike')]}, valid_to=end)
    result = await get_facade().update_profile_field('u1', 'interest', ProfileFieldUpdateRequest(value=['编程', '录入', '绘画']))
    assert result.value == ['编程', '录入', '绘画']
    assert result.attributes['items'][1]['polarity'] == 'dislike'
    assert result.valid_to == end


def test_extractor_attributes_are_scoped_and_bounded_to_the_entry_type():
    from zhiyin_kernel import profile_taxonomy as t
    for key in ('interest', 'career_focus', 'major', 'time', 'supplement_info'):
        kind = t.entry_type_of(key)
        schema = t.attributes_schema(kind)
        assert set(schema['properties']) == set(t.ATTRIBUTE_SPECS.get(kind, {}))
        if 'items' in schema['properties']:
            assert schema['properties']['items']['maxItems'] == t.max_items(key)
            assert 'items' not in schema['properties']['items']['items']['properties']


def test_correction_window_rejects_naive_timestamps():
    from pydantic import ValidationError
    from zhiyin_api.dto.workspace import ProfileFieldUpdateRequest
    with pytest.raises(ValidationError):
        ProfileFieldUpdateRequest(value='本周两小时', valid_to='2026-10-25T23:59:59')
