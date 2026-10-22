"""Regressions for the real new-account acceptance failures (synthetic model decisions)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from tests.test_profile_write_path import _setup, _send, _profile_action
from zhiyin_business.services.dialogue_runtime import active_dialogue
from zhiyin_kernel import profile_taxonomy as taxonomy
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_orchestration import AgentResult


def test_independent_negative_interest_preserves_each_objects_polarity():
    old = SimpleNamespace(value=['调试程序'], attributes={'polarity': 'like'})
    values, attrs, conflict = taxonomy.merge_preferences('interest', old, ['重复录入'], {'polarity': 'dislike'})
    # 否定项不是兴趣：它保留逐项极性，但不进入兴趣的取值列表（#40）。
    assert values == ['调试程序'] and not conflict
    assert attrs['items'] == [dict(value='调试程序', polarity='like'), dict(value='重复录入', polarity='dislike')]
    same = SimpleNamespace(value=values, attributes=attrs)
    assert taxonomy.merge_preferences('interest', same, ['调试程序'], {'polarity': 'dislike'})[2]
    candidate, candidate_attrs, _ = taxonomy.merge_preferences('interest', same, ['调试程序'], {'polarity': 'dislike'})
    assert candidate == values and candidate_attrs['items'][0]['polarity'] == 'dislike'
    assert taxonomy.merge_preferences('interest', same, ['重复录入'], {'polarity': 'dislike'})[:2] == (values, attrs)


def test_same_concept_negative_phrases_are_deduplicated_without_entering_interest():
    old = SimpleNamespace(value=['写东西', '研究人为什么买'], attributes={'items': [
        dict(value='写东西', polarity='like'), dict(value='研究人为什么买', polarity='like')]})
    values, attrs, _ = taxonomy.merge_preferences(
        'interest', old, ['天天应酬', '应酬'],
        {'items': [dict(value='天天应酬', polarity='dislike'), dict(value='应酬', polarity='dislike')]},
    )
    assert values == ['写东西', '研究人为什么买']
    dislikes = [item for item in attrs['items'] if item['polarity'] == 'dislike']
    assert [item['value'] for item in dislikes] == ['天天应酬']


def test_per_item_attributes_are_bounded_and_cannot_nest_or_use_unknown_types():
    with pytest.raises(InvalidRequest):
        taxonomy.normalize_attributes(taxonomy.entry_type_of('interest'), {'items': [{'value': '编程', 'state': 'selected'}]})
    with pytest.raises(InvalidRequest):
        taxonomy.normalize_attributes(taxonomy.entry_type_of('interest'), {'items': [{'value': '编程', 'items': []}]})


async def test_runtime_appends_interests_instead_of_generating_false_conflict():
    async def callback(rt):
        message = rt.request.message
        return await rt.action(_profile_action(dict(key='interest', value=message,
            attributes={'polarity': 'like' if message == '调试程序' else 'dislike'}), evidence=message))
    c, s = await _setup(callback)
    await _send(c, s, '调试程序')
    await _send(c, s, '重复录入')
    fields = await c.profile_service.get_fields('u1', ['interest'])
    # 否定项保留在逐项属性里，但不作为兴趣值展示。
    assert fields[0].value == ['调试程序']
    assert fields[0].attributes['items'][1]['polarity'] == 'dislike'
    assert not await c.profile_service.list_conflicts('u1')


async def test_main_writing_one_fact_does_not_discard_remaining_typed_facts():
    c, s = await _setup(lambda rt: None)
    message = '我更看重探索空间，习惯用电子笔记，只是正在了解算法工程师。'
    class Model:
        supports_semantic_memory = True
        async def invoke(self, request):
            if request.prompt_code == 'conversation.memory':
                return AgentResult(agent_id=request.agent_id, valid=True, structured={'policy': {'scope': 'none'}, 'updates': [
                    dict(key='values', value='探索空间', evidence='更看重探索空间', assertion_type='affirmative_self_statement'),
                    dict(key='supplement_info', value='习惯用电子笔记', attributes={'title': '整理习惯'}, evidence='习惯用电子笔记', assertion_type='affirmative_self_statement'),
                    dict(key='career_focus', value=['算法工程师'], attributes={'state': 'exploring'}, evidence='正在了解算法工程师', assertion_type='affirmative_self_statement')]})
            rt = active_dialogue.get()
            await rt.action(_profile_action(dict(key='values', value='探索空间'), evidence='更看重探索空间'))
            return AgentResult(agent_id=request.agent_id, valid=True, raw_text='继续聊。')
    c.orchestrator._agent_engine = Model()
    await _send(c, s, message)
    fields = {f.key: f for f in await c.profile_service.get_fields('u1')}
    assert fields['supplement_info'].attributes['title'] == '整理习惯'
    assert fields['career_focus'].attributes['state'] == 'exploring'
    assert fields['career_focus'].value == ['算法工程师']
    assert not {'skills', 'major'}.intersection(fields)


async def test_explicit_save_retains_typed_value_source_and_expiration():
    end = datetime(2026, 10, 25, 15, 59, 59, tzinfo=timezone.utc)
    async def callback(rt):
        return await rt.action(_profile_action(dict(key='time', value='本周末两小时',
            attributes={'scope': '本周'}, valid_to=end.isoformat()), evidence='本周末两小时', authorization='explicit'))
    c, s = await _setup(callback)
    await _send(c, s, '请保存本周末两小时')
    field = (await c.profile_service.get_fields('u1', ['time']))[0]
    assert field.valid_to == end and field.attributes == {'scope': '本周'}
    assert field.origin_ref.startswith('conversation:') and field.evidence == ['本周末两小时']


async def test_explicit_career_list_is_not_stringified_by_correction_service():
    c, _ = await _setup(lambda rt: None)
    field = await c.profile_service.correct_field('u1', 'career_focus', ['算法工程师'], attributes={'state': 'exploring'})
    assert field.value == ['算法工程师'] and field.attributes['state'] == 'exploring'


async def test_explicit_additional_interest_does_not_replace_unmentioned_preferences():
    async def callback(rt):
        return await rt.action(_profile_action(dict(key='interest', value=[rt.request.message],
            attributes={'polarity': 'like'}), evidence=rt.request.message, authorization='explicit'))
    c, s = await _setup(callback)
    await _send(c, s, '调试程序')
    await _send(c, s, '画星图')
    field = (await c.profile_service.get_fields('u1', ['interest']))[0]
    assert field.value == ['调试程序', '画星图']


async def test_time_actions_and_following_facts_work_with_a_json_only_state_repository(monkeypatch):
    import json
    c, s = await _setup(lambda rt: None)
    original = c.student_state.update
    async def strict_update(user, change):
        def json_change(state):
            changed = change(state)
            json.dumps(changed, ensure_ascii=False)  # PostgreSQL's actual JSON boundary
            return changed
        return await original(user, json_change)
    monkeypatch.setattr(c.student_state, 'update', strict_update)
    async def callback(rt):
        await rt.action(_profile_action(dict(key='time', value='周末两小时', valid_to='2026-10-25T23:59:59+08:00'), evidence='周末两小时'))
        await rt.action(_profile_action(dict(key='values', value='探索空间'), evidence='探索空间'))
    c.orchestrator._agent_engine.callback = callback
    await _send(c, s, '周末两小时，重视探索空间')
    fields = {f.key: f for f in await c.profile_service.get_fields('u1')}
    assert fields['time'].valid_to is not None and fields['values'].value == '探索空间'


def test_attribute_contract_never_stringifies_nested_values():
    for attrs in ({'title': ['学习习惯']}, {'pending_classification': []}, {'context': True}):
        kind = 'supplement_info' if 'context' not in attrs else 'interest'
        with pytest.raises(InvalidRequest):
            taxonomy.normalize_attributes(taxonomy.entry_type_of(kind), attrs)


def test_scalar_values_never_persist_python_container_representations():
    assert taxonomy.normalize_value('values', ['持续学习', '探索空间']) == '持续学习、探索空间'
    with pytest.raises(InvalidRequest):
        taxonomy.normalize_value('experience', ['一次项目'])
    with pytest.raises(InvalidRequest):
        taxonomy.normalize_value('major', {'name': '人工智能'})


async def test_semantic_explicit_correction_uses_the_user_confirmed_write_path():
    c, s = await _setup(lambda rt: None)
    await c.profile_service.correct_field('u1', 'major', '人工智能')
    class Model:
        supports_semantic_memory = True
        async def invoke(self, request):
            if request.prompt_code == 'conversation.memory':
                return AgentResult(agent_id=request.agent_id, valid=True, structured={'policy': {'scope': 'none'},
                    'updates': [dict(key='major', value='软件工程', evidence='更正为软件工程', assertion_type='explicit_correction')]})
            return AgentResult(agent_id=request.agent_id, valid=True, raw_text='已按更正后的信息继续。')
    c.orchestrator._agent_engine = Model()
    await _send(c, s, '专业更正为软件工程')
    field = (await c.profile_service.get_fields('u1', ['major']))[0]
    assert field.value == '软件工程' and field.source.value == 'user_edit'
    assert field.verification.value == 'user_confirmed'


@pytest.mark.parametrize('choice', ['current', 'revision'])
async def test_requested_conflict_candidate_does_not_overwrite_and_adoption_keeps_other_objects(choice):
    c, s = await _setup(lambda rt: None)
    await c.profile_service.update_field('u1', 'interest', ['调试程序', '重复录入'], confidence=.9,
        source='conversation', attributes={'items': [dict(value='调试程序', polarity='like'), dict(value='重复录入', polarity='dislike')]})
    class Model:
        supports_semantic_memory = True
        async def invoke(self, request):
            if request.prompt_code == 'conversation.memory':
                return AgentResult(agent_id=request.agent_id, valid=True, structured={'policy': {'scope': 'none'},
                    'updates': [dict(key='interest', value=['调试程序'], attributes={'polarity': 'dislike'},
                        evidence='不喜欢调试程序，先保留待核对', assertion_type='conflict_candidate')]})
            return AgentResult(agent_id=request.agent_id, valid=True, raw_text='先核对。')
    c.orchestrator._agent_engine = Model()
    result = await _send(c, s, '不喜欢调试程序，先保留待核对')
    assert any('当前记录没有覆盖' in message.text for message in result.messages)
    before = (await c.profile_service.get_fields('u1', ['interest']))[0]
    assert before.attributes['items'][0]['polarity'] == 'like'
    conflict = (await c.profile_service.list_conflicts('u1'))[0]
    from tests.test_profile_clues import _clue
    from zhiyin_business.services.conversation_ledger import ConversationLedger
    await c.profile_service.replace_session_clues('u1', s.id, [_clue('兴趣仍待本人核对').model_copy(update={'session_id': s.id, 'field_keys': []})])
    await ConversationLedger(c.student_state).change('u1', s.id, lambda record: record.update(exploration={'working': {'hypotheses': ['仍待核对']}}))
    await c.profile_service.resolve_conflict('u1', conflict.id, choice=choice)
    after = (await c.profile_service.get_fields('u1', ['interest']))[0]
    assert after.value == ['调试程序', '重复录入']
    assert after.attributes['items'][0]['polarity'] == ('dislike' if choice == 'revision' else 'like')
    assert all(clue.status.value == 'invalid' for clue in await c.profile_service.get_clues('u1'))
    assert 'exploration' not in await ConversationLedger(c.student_state).read('u1', s.id)
