"""Optional integration tests against a dedicated disposable PostgreSQL database."""
import asyncio
import os
from uuid import uuid4

import pytest

from zhiyin_infrastructure.postgres.database import PostgresDatabase
from zhiyin_infrastructure.postgres.evidence import PostgresEvidenceAssessmentRepository

pytestmark = pytest.mark.skipif(not os.getenv('ZHIYIN_EVIDENCE_TEST_DSN'), reason='Dedicated PostgreSQL test database required')


async def test_durable_coalescing_leases_and_restart():
    db = PostgresDatabase(os.environ['ZHIYIN_EVIDENCE_TEST_DSN'])
    uid = 'assessment_test_' + uuid4().hex
    repo = PostgresEvidenceAssessmentRepository(db)
    record = dict(user_id=uid, field_key='interest', input_hash='v1', inputs={}, prompt='p',
                  prompt_version='p1', entry_version=1, dependency_hashes={'interest': 'a'})
    try:
        await repo.enqueue(record)
        await repo.enqueue(record)
        assert len(await repo.list_for_user(uid)) == 1
        await repo.enqueue({**record, 'input_hash': 'v2', 'entry_version': 2})
        await db.execute('UPDATE biz_profile_evidence_assessment SET next_at=NOW() WHERE user_id=$1', uid)
        # One claim across two simultaneous worker processes/connections.
        claimed = await asyncio.gather(repo.claim(), PostgresEvidenceAssessmentRepository(db).claim())
        old = next(job for job in claimed if job)
        assert sum(job is not None for job in claimed) == 1
        assert old['input_hash'] == 'v2'
        await db.aclose()
        restarted = PostgresDatabase(os.environ['ZHIYIN_EVIDENCE_TEST_DSN'])
        recovered = PostgresEvidenceAssessmentRepository(restarted)
        assert (await recovered.list_for_user(uid))[0]['status'] == 'processing'
        assert await recovered.claim() is None
        await restarted.execute("UPDATE biz_profile_evidence_assessment SET leased_until=NOW()-INTERVAL '1 second' WHERE user_id=$1", uid)
        new = await recovered.claim()
        assert new['attempts'] == 2
        assert not await recovered.finish(old, {'status': 'evaluated', 'score': 1})
        assert await recovered.finish(new, {'status': 'insufficient', 'score': None})
        await recovered.enqueue({**record, 'input_hash': 'v3'})
        # A late result cannot overwrite a newer queued version.
        assert not await recovered.finish(new, {'status': 'evaluated', 'score': .9})
        assert (await recovered.list_for_user(uid))[0]['status'] == 'pending'
        await recovered.remove(uid, 'interest')
        assert await recovered.list_for_user(uid) == []
        await restarted.aclose()
    finally:
        await db.aclose()
