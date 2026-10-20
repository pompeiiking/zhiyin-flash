"""Regressions found by the independent profile review; synthetic data only."""
import importlib.util
from pathlib import Path
from datetime import datetime, timezone
import pytest
from tests.test_profile_write_path import _setup, _send, _profile_action
from tests.test_profile_clues import _profile_service, _clue
from zhiyin_business.services.memory_policy import MemoryPolicyService
from zhiyin_kernel import profile_taxonomy
from zhiyin_kernel.blackboard import ProfileField, Profile
from zhiyin_kernel.enums import ProfilePurpose, ProfileSource
from zhiyin_business.services.ai_tasks import AiTaskService
from zhiyin_orchestration import AgentResult


async def test_denied_clue_stays_invalid_after_next_analysis():
    service = await _profile_service()
    clue = (await service.replace_session_clues('review-only', 's', [_clue('可能喜欢研究原因')]))[0]
    await service.deny_clue('review-only', clue.id)
    await service.replace_session_clues('review-only', 's', [_clue('可能喜欢研究原因')])
    current = await service.get_clues('review-only')
    assert len(current) == 1 and current[0].status.value == 'invalid'
    assert current[0].id == clue.id
    await service.replace_session_clues('review-only', 's', [])
    assert (await service.get_clues('review-only'))[0].status.value == 'invalid'


async def test_temporary_session_does_not_persist_profile_clues():
    calls = 0
    async def callback(runtime):
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        turn_id = next(iter(runtime.exploration_sources))
        await runtime.record_exploration(dict(goal='探索兴趣', mode='explore',
            statements=[dict(turn_id=turn_id, quote='我喜欢调试程序')],
            hypotheses=['可能喜欢研究原因'], explored_topics=[], open_questions=[], next_focus='经历'))
    container, session = await _setup(callback)
    await MemoryPolicyService(container.student_state).set_session_temporary('u1', session.id, True)
    await _send(container, session, '我喜欢调试程序')
    await _send(container, session, '继续')
    assert not await container.profile_service.get_clues('u1')
    assert not await container.profile_service.get_fields('u1')


async def test_ui_delete_prevents_automatic_recreation():
    async def callback(runtime):
        await runtime.action(_profile_action(dict(key='interest', value='调试程序'), evidence='我喜欢调试程序'))
    container, session = await _setup(callback)
    await _send(container, session, '我喜欢调试程序')
    from zhiyin_boot import wire_application
    from zhiyin_api.facade import get_facade
    wire_application(container)
    await get_facade().delete_profile_field('u1', 'interest')
    assert not await container.profile_service.get_fields('u1', ['interest'])
    import pytest
    from zhiyin_kernel.errors import InvalidRequest
    with pytest.raises(InvalidRequest):
        await _send(container, session, '我喜欢调试程序')
    assert not await container.profile_service.get_fields('u1', ['interest'])


async def test_policy_extraction_precedes_main_model_write():
    async def callback(runtime):
        import pytest
        from zhiyin_kernel.errors import InvalidRequest
        with pytest.raises(InvalidRequest):
            await runtime.action(_profile_action(dict(key='major', value='人工智能'), evidence='人工智能'))
    container, session = await _setup(callback)
    invoked = []
    class Model:
        supports_semantic_memory = True
        async def invoke(self, request):
            invoked.append(request.prompt_code)
            if request.prompt_code == 'conversation.memory':
                return AgentResult(agent_id=request.agent_id, valid=True,
                    structured=dict(updates=[], policy=dict(scope='session_temporary')))
            from zhiyin_business.services.dialogue_runtime import active_dialogue
            await callback(active_dialogue.get())
            return AgentResult(agent_id=request.agent_id, valid=True, raw_text='继续聊。')
    container.orchestrator._agent_engine = Model()
    await _send(container, session, '我学人工智能，这次对话不要保存长期记忆')
    assert invoked[0] == 'conversation.memory'
    assert (await MemoryPolicyService(container.student_state).snapshot('u1', session.id))['session_temporary']
    assert not await container.profile_service.get_fields('u1', ['major'])


def test_expired_condition_is_excluded_from_planning():
    field = ProfileField(key='constraints', value='本周只有周末有空', confidence=.9,
        source=ProfileSource.CONVERSATION, updated_at=datetime.now(timezone.utc),
        valid_to=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert not profile_taxonomy.records_for_purpose(ProfilePurpose.PLANNING, [field])
    future = field.model_copy(update={'valid_to': None, 'valid_from': datetime(2099, 1, 1, tzinfo=timezone.utc)})
    assert not profile_taxonomy.records_for_purpose(ProfilePurpose.PLANNING, [future])


def test_negative_interest_attributes_survive_model_context_formatting():
    field = ProfileField(key='interest', value=['写代码'], confidence=.9,
        source=ProfileSource.CONVERSATION, updated_at=datetime.now(timezone.utc),
        attributes=dict(polarity='dislike', context='重复的业务开发'))
    lines = AiTaskService._profile_lines(Profile(id='review-profile', user_id='review-only', fields=[field], updated_at=datetime.now(timezone.utc)), ProfilePurpose.DIRECTION_RECOMMENDATION)
    assert all(value in lines[0] for value in ['写代码', 'dislike', '重复的业务开发'])
    from zhiyin_infrastructure.ai.tools import _describe_profile
    assert 'dislike' in _describe_profile({'fields': [field.model_dump(mode='json')]})


def test_two_legacy_aliases_preserve_both_values_and_original_backup():
    path = Path(__file__).resolve().parents[1] / 'scripts/migrate_profile_aliases.py'
    spec = importlib.util.spec_from_file_location('review_alias', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plans = module.plan_rows([
        dict(user_id='review-only', key='career_goal', value='算法工程师'),
        dict(user_id='review-only', key='career_interest', value='产品经理')])
    assert [p['action'] for p in plans] == ['create', 'conflict']
    assert len({p['target_key'] for p in plans}) == 1
    assert all(plan['target_before'] is None for plan in plans)


async def test_intel_query_excludes_explicitly_expired_fields():
    from zhiyin_business.services.function import DefaultFunctionService
    from zhiyin_data_sdk.gateways.datasource import DataSourceResult
    from zhiyin_kernel.enums import ProfileEntryStatus
    seen = []
    field = ProfileField(key='major', value='人工智能', confidence=.9,
        source=ProfileSource.CONVERSATION, updated_at=datetime.now(timezone.utc),
        status=ProfileEntryStatus.EXPIRED)
    class Profiles:
        async def get_fields(self, user):
            return [field]
    class Data:
        async def fetch(self, request):
            seen.extend(profile_taxonomy.major_terms(request.context['fields']))
            return DataSourceResult(source='xuezhi')
    service = DefaultFunctionService(assets=None, behaviors=None, object_store=None,
        calendar=None, track_events=None, notifications=None, profiles=Profiles(), data_sources=Data())
    assert not profile_taxonomy.major_terms([field])
    await service._collect_intel('review-only', topic='', limit=5)
    assert not seen


@pytest.mark.parametrize('failure', ['invalid_result', 'model_error', 'policy_store_error'])
async def test_failed_memory_preflight_cannot_be_bypassed_by_main_or_fallback(failure, monkeypatch):
    from zhiyin_business.services.dialogue_runtime import active_dialogue
    from zhiyin_kernel.errors import InvalidRequest
    container, session = await _setup(lambda runtime: None)

    async def store_error(*args, **kwargs):
        raise OSError('Synthetic policy-store failure')

    if failure == 'policy_store_error':
        monkeypatch.setattr(MemoryPolicyService, 'set_session_temporary', store_error)

    class Model:
        supports_semantic_memory = True
        async def invoke(self, request):
            if request.prompt_code == 'conversation.memory':
                if failure == 'model_error':
                    raise RuntimeError('Synthetic model failure')
                return AgentResult(agent_id=request.agent_id, valid=failure != 'invalid_result',
                    structured=dict(policy=dict(scope='session_temporary'),
                        updates=[dict(key='major', value='人工智能', evidence='人工智能', assertion_type='affirmative_self_statement')]))
            runtime = active_dialogue.get()
            with pytest.raises(InvalidRequest):
                await runtime.action(_profile_action(dict(key='major', value='人工智能'), evidence='人工智能'))
            return AgentResult(agent_id=request.agent_id, valid=True, raw_text='仍可继续交流。')
    container.orchestrator._agent_engine = Model()
    await _send(container, session, '我学人工智能，这次不要保存长期画像')
    assert not await container.profile_service.get_fields('u1')
