from copy import deepcopy
import time
from uuid import uuid4


class InMemoryEvidenceAssessmentRepository:
    def __init__(self):
        self.records = {}

    async def list_for_user(self, user_id):
        return deepcopy([r for (u, _), r in self.records.items() if u == user_id])

    async def enqueue(self, record):
        key = (record['user_id'], record['field_key'])
        previous = self.records.get(key)
        if (previous and previous['input_hash'] == record['input_hash']
                and previous.get('status') not in ('failed', 'stale')):
            return
        self.records[key] = {**deepcopy(record), 'status': 'pending', 'attempts': 0,
                             'next_at': time.time() + 2, 'lease_until': 0, 'lease_token': ''}

    async def claim(self):
        now = time.time()
        for row in self.records.values():
            if (row['status'] in ('pending', 'failed', 'stale') and row['next_at'] <= now or
                    row['status'] == 'processing' and row['lease_until'] <= now):
                row.update(status='processing', attempts=row['attempts'] + 1,
                           lease_until=now + 120, lease_token=uuid4().hex)
                return deepcopy(row)
        return None

    async def finish(self, job, result, *, retry=False):
        row = self.records.get((job['user_id'], job['field_key']))
        if not row or row['input_hash'] != job['input_hash'] or row['lease_token'] != job['lease_token']:
            return False
        row.pop('inputs', None)
        row.pop('prompt', None)
        row['result'] = deepcopy(result)
        row['dependency_hashes'] = deepcopy(job.get('dependency_hashes', {}))
        row['status'] = 'pending' if retry else result['status']
        row['next_at'] = time.time() + (10 if retry or result['status'] not in ('failed', 'stale') else 3600)
        row['lease_until'] = 0
        return True

    async def discard(self, job):
        await self.finish(job, {'status': 'stale'})

    async def remove(self, user_id, key):
        self.records.pop((user_id, key), None)
