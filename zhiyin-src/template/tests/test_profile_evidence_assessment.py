"""Display assessments must remain independent of legacy confidence and business gates."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from zhiyin_business.services.evidence_assessment import ProfileEvidenceService
from zhiyin_business.services.profile import DefaultProfileService
from zhiyin_data_sdk.gateways.ai import LLMResult
from zhiyin_infrastructure.local.evidence import InMemoryEvidenceAssessmentRepository
from zhiyin_infrastructure.local.repository import InMemoryProfileRepository
from zhiyin_kernel.blackboard import ProfileField
from zhiyin_kernel.enums import ProfileSource


def judgment(**changes):
    return dict(score=.713, reasons=['只有本人对具体活动的自述，尚无独立材料。'],
                missing_evidence=['活动记录与他人反馈'], contradictions=[],
                source_refs=['field:interest'], **changes)


@pytest.fixture
async def setup():
    profiles = InMemoryProfileRepository()
    repo = InMemoryEvidenceAssessmentRepository()
    llm = AsyncMock()
    llm.chat.return_value = LLMResult(structured=judgment(), model='test-model')
    service = ProfileEvidenceService(profiles, repo, llm)
    business = DefaultProfileService(profiles, AsyncMock(), evidence_assessments=service)
    await profiles.upsert_field('u', ProfileField(key='interest', value='喜欢写代码', confidence=.9,
        source=ProfileSource.CONVERSATION, updated_at=datetime.now(timezone.utc), evidence=['我喜欢写代码']))
    return profiles, repo, llm, service, business


def due(repo):
    for row in repo.records.values():
        row['next_at'] = 0


async def test_old_fields_are_pending_without_backfill(setup):
    profiles, repo, llm, service, _ = setup
    fields = await service.attach('u', await profiles.list_fields('u'))
    assert fields[0].evidence_assessment.status == 'pending'
    assert fields[0].evidence_assessment.score is None
    assert await service.run_once() == 0
    llm.chat.assert_not_called()


async def test_change_dedup_cached_result_and_legacy_independence(setup):
    profiles, repo, llm, service, _ = setup
    await service.changed('u', ['interest'])
    await service.changed('u', ['interest'])
    assert len(repo.records) == 1
    due(repo)
    await service.run_once()
    before = (await service.attach('u', await profiles.list_fields('u')))[0].evidence_assessment
    assert before.score == .713 and before.model == 'test-model'
    # Alter only the old internal score, without changing any evidence.
    profiles._profiles['u'].fields[0].confidence = .01
    await service.changed('u', ['interest'])
    assert await service.run_once() == 0
    after = (await service.attach('u', await profiles.list_fields('u')))[0].evidence_assessment
    assert after == before
    assert llm.chat.await_count == 1


async def test_concurrent_change_discards_response(setup):
    profiles, repo, llm, service, business = setup
    await service.changed('u', ['interest'])
    old_hash = repo.records['u', 'interest']['input_hash']
    due(repo)
    entered, release = asyncio.Event(), asyncio.Event()
    async def response(*args, **kwargs):
        entered.set()
        await release.wait()
        return LLMResult(structured=judgment(), model='test-model')
    llm.chat.side_effect = response
    running = asyncio.create_task(service.run_once())
    await entered.wait()
    await business.update_field('u', 'interest', '喜欢绘画', confidence=.9, source=ProfileSource.CONVERSATION)
    release.set()
    await running
    row = repo.records['u', 'interest']
    assert row['status'] == 'pending' and row['input_hash'] != old_hash
    assert 'result' not in row
    # The queue stores only the target/version/hashes, never a full profile copy.
    assert 'inputs' not in row and 'prompt' not in row


@pytest.mark.parametrize('patch', [dict(score=1.2), dict(score='0.9'), dict(score=True),
    dict(score=float('nan')), dict(source_refs=['fabricated:123']), dict(source_refs=[])])
async def test_bad_model_results_retry_then_fail_without_old_score(setup, patch):
    profiles, repo, llm, service, _ = setup
    payload = judgment()
    payload.update(patch)
    llm.chat.return_value = LLMResult(structured=payload, model='test-model')
    await service.changed('u', ['interest'])
    for _ in range(3):
        due(repo)
        await service.run_once()
    row = repo.records['u', 'interest']
    assert row['status'] == 'failed' and row['attempts'] == 3
    result = (await service.attach('u', await profiles.list_fields('u')))[0].evidence_assessment
    assert result.status == 'failed' and result.score is None


async def test_timeout_and_null_are_not_fixed_scores(setup):
    profiles, repo, llm, service, _ = setup
    llm.chat.side_effect = TimeoutError()
    await service.changed('u', ['interest'])
    due(repo)
    await service.run_once()
    assert repo.records['u', 'interest']['status'] == 'pending'
    assert 'score' not in repo.records['u', 'interest']['result']
    llm.chat.side_effect = None
    payload = judgment()
    payload.update(score=None, source_refs=[], reasons=['缺乏足够资料，无法评估。'])
    llm.chat.return_value = LLMResult(structured=payload, model='test-model')
    due(repo)
    await service.run_once()
    result = (await service.attach('u', await profiles.list_fields('u')))[0].evidence_assessment
    assert result.status == 'insufficient' and result.score is None


async def test_expired_lease_can_resume_and_old_worker_cannot_finish(setup):
    _, repo, _, service, _ = setup
    await service.changed('u', ['interest'])
    due(repo)
    old = await repo.claim()
    assert await repo.claim() is None
    repo.records['u', 'interest']['lease_until'] = 0
    resumed = await repo.claim()
    assert resumed['lease_token'] != old['lease_token']
    assert not await repo.finish(old, {'status': 'evaluated', 'score': 1})
    assert await repo.finish(resumed, {'status': 'failed'})


async def test_delete_invalidates_cited_dependent_without_creating_deleted_job(setup):
    profiles, repo, llm, service, business = setup
    await business.update_field('u', 'skills', '代码写作', confidence=.9, source=ProfileSource.CONVERSATION)
    payload = judgment()
    payload['source_refs'] = ['field:interest', 'field:skills']
    llm.chat.return_value = LLMResult(structured=payload, model='test-model')
    due(repo)
    while await service.run_once():
        pass
    await service.changed('u', ['interest'])
    due(repo)
    await service.run_once()
    assert repo.records['u', 'interest']['status'] == 'evaluated'
    await business.drop_field('u', 'skills')
    assert ('u', 'skills') not in repo.records
    assert repo.records['u', 'interest']['status'] == 'pending'


async def test_conflict_and_resolution_schedule_new_input(setup):
    _, repo, _, service, business = setup
    await service.changed('u', ['interest'])
    original = repo.records['u', 'interest']['input_hash']
    proposal = await business.record_conflict('u', key='interest', value='不喜欢写代码',
        confidence=.9, source=ProfileSource.CONVERSATION, evidence=['我不喜欢写代码'])
    assert repo.records['u', 'interest']['input_hash'] != original
    context = await service.context('u')
    assert context['interest']['conflicts']
    await business.resolve_conflict('u', proposal.id, choice='current')
    assert not (await service.context('u'))['interest']['conflicts']


async def test_new_user_edits_never_immediately_become_100_or_90(setup):
    _, _, llm, _, business = setup
    manual = await business.update_field('u', 'school', '某学校', confidence=1., source=ProfileSource.USER_EDIT)
    conversation = await business.update_field('u', 'major', '计算机', confidence=.9, source=ProfileSource.CONVERSATION)
    assert manual.evidence_assessment.score is None
    assert conversation.evidence_assessment.score is None
    llm.chat.assert_not_called()


async def test_snapshot_never_changes_after_evidence_mutation(setup):
    profiles, repo, _, service, business = setup
    await service.changed('u', ['interest'])
    due(repo)
    await service.run_once()
    snapshot = deepcopy((await service.attach('u', await profiles.list_fields('u')))[0])
    await business.drop_field('u', 'interest')
    assert snapshot.evidence_assessment.score == .713
    assert not await profiles.list_fields('u')


async def test_failed_same_input_can_recover_after_provider_returns(setup):
    profiles, repo, llm, service, _ = setup
    llm.chat.side_effect = TimeoutError()
    await service.changed('u', ['interest'])
    for _ in range(3):
        due(repo)
        await service.run_once()
    assert repo.records['u', 'interest']['status'] == 'failed'

    llm.chat.side_effect = None
    await service.changed('u', ['interest'])
    assert repo.records['u', 'interest']['status'] == 'pending'
    due(repo)
    await service.run_once()
    result = (await service.attach('u', await profiles.list_fields('u')))[0].evidence_assessment
    assert result.status == 'evaluated' and result.score == .713


async def test_failed_job_retries_after_cooldown_without_profile_change(setup):
    profiles, repo, llm, service, _ = setup
    llm.chat.side_effect = TimeoutError()
    await service.changed('u', ['interest'])
    for _ in range(3):
        due(repo)
        await service.run_once()
    assert repo.records['u', 'interest']['status'] == 'failed'

    llm.chat.side_effect = None
    due(repo)  # simulate the hourly recovery window opening
    await service.run_once()
    result = (await service.attach('u', await profiles.list_fields('u')))[0].evidence_assessment
    assert result.status == 'evaluated' and result.score == .713


async def test_queue_payload_contains_no_profile_copy(setup):
    _, repo, _, service, _ = setup
    await service.changed('u', ['interest'])
    row = repo.records['u', 'interest']
    assert 'inputs' not in row and 'prompt' not in row
    assert set(row) >= {'user_id', 'field_key', 'input_hash', 'entry_version', 'dependency_hashes'}


async def test_one_tick_drains_multiple_fields(setup):
    profiles, repo, _, service, _ = setup
    await profiles.upsert_field('u', ProfileField(key='skills', value='Python', confidence=.8,
        source=ProfileSource.CONVERSATION, updated_at=datetime.now(timezone.utc)))
    await service.changed('u', ['interest', 'skills'])
    for row in repo.records.values():
        row['next_at'] = 0
    assert await service.run_once() == 2
    assert {r['status'] for r in repo.records.values()} == {'evaluated'}


async def test_expired_field_is_not_shown_as_current_evidence(setup):
    profiles, repo, _, service, _ = setup
    await service.changed('u', ['interest'])
    due(repo)
    await service.run_once()
    profiles._profiles['u'].fields[0].valid_to = datetime(2020, 1, 1, tzinfo=timezone.utc)
    result = (await service.attach('u', await profiles.list_fields('u')))[0].evidence_assessment
    assert result.status == 'stale' and result.score is None  # saved score is not promoted to current


async def test_profile_write_survives_projection_outage(setup):
    profiles, repo, _, _, _ = setup

    class BrokenEvidence:
        async def changed(self, user_id, keys):
            raise RuntimeError('assessment queue unavailable')

        async def attach(self, user_id, fields):
            return fields

    business = DefaultProfileService(profiles, AsyncMock(), evidence_assessments=BrokenEvidence())
    saved = await business.update_field('u', 'major', '计算机', confidence=.9,
        source=ProfileSource.CONVERSATION)
    assert saved.value == '计算机'
    assert (await profiles.list_fields('u', ['major']))[0].value == '计算机'
