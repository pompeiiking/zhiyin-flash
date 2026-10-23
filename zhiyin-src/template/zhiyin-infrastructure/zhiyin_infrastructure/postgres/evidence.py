import json
from uuid import uuid4


def decode(row):
    if row is None:
        return None
    data = json.loads(row['payload']) if isinstance(row['payload'], str) else dict(row['payload'])
    return {**data, 'status': row['status'], 'attempts': row['attempts'], 'lease_token': row['lease_token']}


class PostgresEvidenceAssessmentRepository:
    def __init__(self, database):
        self.db = database

    async def list_for_user(self, user_id):
        return [decode(r) for r in await self.db.fetch(
            'SELECT * FROM biz_profile_evidence_assessment WHERE user_id=$1', user_id)]

    async def enqueue(self, record):
        await self.db.execute('''INSERT INTO biz_profile_evidence_assessment
            (user_id,field_key,input_hash,payload,status,next_at)
            VALUES ($1,$2,$3,$4::jsonb,'pending',NOW()+INTERVAL '2 seconds')
            ON CONFLICT (user_id,field_key) DO UPDATE SET input_hash=EXCLUDED.input_hash,
            payload=EXCLUDED.payload,status='pending',attempts=0,lease_token='',leased_until=NULL,
            next_at=EXCLUDED.next_at,updated_at=NOW()
            WHERE biz_profile_evidence_assessment.input_hash <> EXCLUDED.input_hash''',
            record['user_id'], record['field_key'], record['input_hash'], json.dumps(record, ensure_ascii=False))

    async def claim(self):
        row = await self.db.fetchrow('''UPDATE biz_profile_evidence_assessment SET
            status='processing', attempts=attempts+1, lease_token=$1,
            leased_until=NOW()+INTERVAL '120 seconds',updated_at=NOW()
            WHERE (user_id,field_key)=(SELECT user_id,field_key FROM biz_profile_evidence_assessment
            WHERE (status='pending' AND next_at<=NOW()) OR (status='processing' AND leased_until<NOW())
            ORDER BY next_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *''', uuid4().hex)
        return decode(row)

    async def finish(self, job, result, *, retry=False):
        payload = {**job, 'result': result}
        changed = await self.db.fetchrow('''UPDATE biz_profile_evidence_assessment
            SET payload=$1::jsonb,status=$2,leased_until=NULL,next_at=NOW()+INTERVAL '10 seconds',updated_at=NOW()
            WHERE user_id=$3 AND field_key=$4 AND input_hash=$5 AND lease_token=$6 RETURNING user_id''',
            json.dumps(payload, ensure_ascii=False), 'pending' if retry else result['status'],
            job['user_id'], job['field_key'], job['input_hash'], job['lease_token'])
        return changed is not None

    async def discard(self, job):
        await self.finish(job, {'status': 'stale'})

    async def remove(self, user_id, key):
        await self.db.execute('DELETE FROM biz_profile_evidence_assessment WHERE user_id=$1 AND field_key=$2', user_id, key)
