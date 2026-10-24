"""Evidence assessment scheduling, provenance validation and read-side projection."""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

from zhiyin_data_sdk.gateways.ai import LLMMessage
from zhiyin_kernel.evidence_assessment import EvidenceAssessment
from zhiyin_business.contracts.evidence_assessment import ASSESSMENT_PROMPT, EvidenceJudgment
from zhiyin_business.services.enrollment_report import origin_ref_label
from zhiyin_business.services.unit_of_work import transaction

logger = logging.getLogger(__name__)

#: Finite retry budget per input hash. The queue keeps the row after a failure so
#: a later profile edit or explicit retry can revive it; it is never a permanent
#: "failed" tombstone for unchanged input.
MAX_ATTEMPTS = 3
#: One worker tick drains a bounded batch. With a 60s tick, one field per tick
#: made a 20-field profile take 20 minutes; the batch keeps the queue responsive
#: without letting one tick monopolize the process.
DEFAULT_BATCH = 12


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _as_utc(value):
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class ProfileEvidenceService:
    IMPLEMENTATION_STATUS = 'wired'

    def __init__(self, profiles, repository, llm, registry=None):
        self.profiles, self.repository, self.llm, self.registry = profiles, repository, llm, registry

    async def context(self, user_id):
        """Read fields and conflicts from one snapshot when the store supports it.

        Two unrelated READ COMMITTED queries can observe a mixed state under a
        concurrent profile write. The same transaction matters for both the
        input hash and the stale check.
        """
        async with transaction(self.profiles):
            fields = await self.profiles.list_fields(user_id)
            conflicts = await self.profiles.list_revisions(user_id, status=['conflict'])
        by_key = {}
        for field in fields:
            item = field.model_dump(mode='json', exclude={'confidence', 'evidence_assessment'})
            item['conflicts'] = [c.model_dump(mode='json', exclude={'confidence', 'user_id'})
                                 for c in conflicts if c.key == field.key]
            by_key[field.key] = item
        return by_key

    async def prompt(self):
        if self.registry:
            for item in await self.registry.list_prompts():
                if item.code == 'profile.evidence.assess':
                    return item.content
        return ASSESSMENT_PROMPT

    async def changed(self, user_id, keys):
        """Queue projection work after the profile commit.

        The queue payload intentionally stores only the target, its entry version,
        dependency hashes and prompt version — never a copy of the whole profile.
        The worker rebuilds the current context. This keeps deleted fields out of
        old rows and makes every result traceable to the exact inputs it used.
        """
        context = await self.context(user_id)
        previous = await self.repository.list_for_user(user_id)
        targets = set(keys)
        for row in previous:
            deps = set((row.get('dependency_hashes') or {}).keys())
            if set(keys) & deps:
                targets.add(row['field_key'])
        prompt = await self.prompt()
        prompt_version = fingerprint(prompt)
        for key in targets:
            if key not in context:
                await self.repository.remove(user_id, key)
                continue
            inputs = {'target': key, 'fields': context}
            await self.repository.enqueue({
                'user_id': user_id,
                'field_key': key,
                'input_hash': fingerprint({'inputs': inputs, 'prompt_version': prompt_version}),
                'prompt_version': prompt_version,
                'entry_version': context[key]['entry_version'],
                'dependency_hashes': {key: fingerprint(context[key])},
            })

    @staticmethod
    def _inactive(field, now):
        if field.status is not None and field.status.value in {'expired', 'withdrawn', 'superseded'}:
            return True
        valid_to = _as_utc(field.valid_to)
        return valid_to is not None and valid_to <= now

    async def attach(self, user_id, fields):
        """Project assessments onto fields without ever failing the profile read."""
        try:
            rows = {r['field_key']: r for r in await self.repository.list_for_user(user_id)}
        except Exception:  # noqa: BLE001 - display projection is optional
            logger.warning('读取把握度评估失败，画像按未评估展示', exc_info=True)
            rows = {}
        context = {}
        if rows:
            try:
                context = await self.context(user_id)
            except Exception:  # noqa: BLE001 - display projection is optional
                logger.warning('读取把握度评估上下文失败，画像按未评估展示', exc_info=True)
                rows = {}
        now = datetime.now(timezone.utc)
        projected = []
        for field in fields:
            row = rows.get(field.key)
            assessment = EvidenceAssessment(entry_version=field.entry_version)
            if self._inactive(field, now):
                assessment = assessment.model_copy(update={'status': 'stale'})
            elif row:
                valid = all(
                    key in context and fingerprint(context[key]) == digest
                    for key, digest in (row.get('dependency_hashes') or {}).items()
                )
                if not valid:
                    assessment = assessment.model_copy(update={'status': 'stale'})
                elif row['status'] in ('evaluated', 'insufficient'):
                    try:
                        assessment = EvidenceAssessment.model_validate(row['result'])
                    except Exception:  # noqa: BLE001 - one malformed row cannot break the page
                        logger.warning('把握度评估结果损坏，按失败展示（key=%s）', field.key)
                        assessment = assessment.model_copy(update={'status': 'failed'})
                elif row['status'] in ('pending', 'processing', 'stale', 'failed'):
                    assessment = assessment.model_copy(update={'status': row['status']})
                else:
                    assessment = assessment.model_copy(update={'status': 'failed'})
            projected.append(field.model_copy(update={'evidence_assessment': assessment}))
        return projected

    async def run_once(self, limit=DEFAULT_BATCH):
        """Drain up to ``limit`` jobs from the queue.

        The worker driver calls this once per tick. Returning the processed count
        is both observable and backwards compatible with callers/tests that loop
        until zero.
        """
        processed = 0
        while processed < limit:
            job = await self.repository.claim()
            if not job:
                break
            await self._run_job(job)
            processed += 1
        return processed

    async def _run_job(self, job):
        try:
            context = await self.context(job['user_id'])
            key = job['field_key']
            if key not in context:
                await self.repository.remove(job['user_id'], key)
                return
            prompt = await self.prompt()
            prompt_version = fingerprint(prompt)
            inputs = {'target': key, 'fields': context}
            current_hash = fingerprint({'inputs': inputs, 'prompt_version': prompt_version})
            if current_hash != job['input_hash'] or prompt_version != job['prompt_version']:
                await self.repository.discard(job)
                await self.changed(job['user_id'], [key])
                return

            references = {}
            owners = {}
            for field_key, item in context.items():
                ref = 'field:' + field_key
                references[ref] = {'label': item.get('label') or field_key, 'kind': 'recorded_claim', **item}
                owners[ref] = field_key
                for index, quote in enumerate(item.get('evidence') or []):
                    ref = f'evidence:{field_key}:{index}'
                    references[ref] = {'label': item.get('label') or field_key, 'text': quote,
                                       'source': item['source'], 'origin_ref': item.get('origin_ref', '')}
                    owners[ref] = field_key
                for conflict in item.get('conflicts', []):
                    ref = 'conflict:' + conflict['id']
                    references[ref] = {'label': item.get('label') or field_key, **conflict}
                    owners[ref] = field_key
            result = await asyncio.wait_for(self.llm.chat([
                LLMMessage(role='system', content=prompt),
                LLMMessage(role='user', content=json.dumps({'target': key,
                    'as_of': datetime.now(timezone.utc).isoformat(), 'references': references}, ensure_ascii=False)),
            ], json_schema=EvidenceJudgment.model_json_schema(), temperature=0, timeout_s=60), timeout=65)
            if result.degraded:
                raise ValueError('Degraded model response is not an assessment')
            judgment = EvidenceJudgment.model_validate(result.structured if result.structured is not None else json.loads(result.text))
            if not set(judgment.source_refs) <= references.keys():
                raise ValueError('Unknown assessment provenance')
            if judgment.score is not None and not judgment.source_refs:
                raise ValueError('Scored assessment requires references')
            dependencies = {key} | {owners[r] for r in judgment.source_refs}
            # Verify *all* model inputs again; a concurrent change cannot become a fresh score.
            if await self.context(job['user_id']) != context:
                await self.repository.discard(job)
                await self.changed(job['user_id'], [key])
                return
            assessment = EvidenceAssessment(**judgment.model_dump(),
                status='evaluated' if judgment.score is not None else 'insufficient',
                sources={r: self.source_description(references[r]) for r in judgment.source_refs},
                assessed_at=datetime.now(timezone.utc), entry_version=job['entry_version'],
                input_hash=job['input_hash'], prompt_version=job['prompt_version'], model=result.model)
            job['dependency_hashes'] = {dependency: fingerprint(context[dependency]) for dependency in dependencies}
            await self.repository.finish(job, assessment.model_dump(mode='json'))
        except Exception:
            # Do not log model payloads or student data.
            logger.warning('画像把握度评估未完成，将有限重试；attempt=%s', job['attempts'])
            await self.repository.finish(job, {'status': 'failed'}, retry=job['attempts'] < MAX_ATTEMPTS)

    @staticmethod
    def source_description(reference):
        text = reference.get('text', reference.get('value', ''))
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        origin = origin_ref_label(reference.get('origin_ref') or '')
        return f"{reference['label']}：{text[:500]}" + (f"（来源：{origin}）" if origin else '')
