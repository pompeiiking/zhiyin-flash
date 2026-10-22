"""Evidence assessment scheduling, provenance validation and read-side projection."""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

from zhiyin_data_sdk.gateways.ai import LLMMessage
from zhiyin_kernel.evidence_assessment import EvidenceAssessment
from zhiyin_business.contracts.evidence_assessment import ASSESSMENT_PROMPT, EvidenceJudgment

logger = logging.getLogger(__name__)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class ProfileEvidenceService:
    IMPLEMENTATION_STATUS = 'wired'

    def __init__(self, profiles, repository, llm, registry=None):
        self.profiles, self.repository, self.llm, self.registry = profiles, repository, llm, registry

    async def context(self, user_id):
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
        """Called in the profile transaction, not by display reads or score writes."""
        context = await self.context(user_id)
        previous = await self.repository.list_for_user(user_id)
        targets = set(keys)
        for row in previous:
            if set(keys) & set(row.get('dependency_hashes', {row['field_key']: ''})):
                targets.add(row['field_key'])
        prompt = await self.prompt()
        for key in targets:
            if key not in context:
                await self.repository.remove(user_id, key)
                continue
            version = fingerprint(prompt)
            # Keep all input provenance, but no legacy confidence values.
            inputs = {'target': key, 'fields': context}
            await self.repository.enqueue({'user_id': user_id, 'field_key': key,
                'input_hash': fingerprint({'inputs': inputs, 'prompt_version': version}),
                'inputs': inputs, 'prompt': prompt, 'prompt_version': version,
                'entry_version': context[key]['entry_version'],
                'dependency_hashes': {key: fingerprint(context[key])}})

    async def attach(self, user_id, fields):
        rows = {r['field_key']: r for r in await self.repository.list_for_user(user_id)}
        context = await self.context(user_id) if rows else {}
        projected = []
        for field in fields:
            row = rows.get(field.key)
            assessment = EvidenceAssessment(entry_version=field.entry_version)
            if row:
                valid = all(fingerprint(context.get(k)) == digest
                            for k, digest in row.get('dependency_hashes', {}).items())
                if not valid:
                    assessment = assessment.model_copy(update={'status': 'stale'})
                elif row['status'] in ('evaluated', 'insufficient'):
                    assessment = EvidenceAssessment.model_validate(row['result'])
                else:
                    assessment = assessment.model_copy(update={'status': row['status']})
            projected.append(field.model_copy(update={'evidence_assessment': assessment}))
        return projected

    async def run_once(self):
        job = await self.repository.claim()
        if not job:
            return 0
        try:
            if job['attempts'] > 3:
                await self.repository.finish(job, {'status': 'failed'})
                return 1
            context = await self.context(job['user_id'])
            if context != job['inputs']['fields']:
                await self.repository.discard(job)
                # Coalesce to the newest input; this never scans unassessed legacy users.
                await self.changed(job['user_id'], [job['field_key']])
                return 1
            references = {}
            owners = {}
            for key, item in context.items():
                ref = 'field:' + key
                references[ref] = {'label': item.get('label') or key, 'kind': 'recorded_claim', **item}
                owners[ref] = key
                for index, quote in enumerate(item.get('evidence') or []):
                    ref = f'evidence:{key}:{index}'
                    references[ref] = {'label': item.get('label') or key, 'text': quote,
                                       'source': item['source'], 'origin_ref': item.get('origin_ref', '')}
                    owners[ref] = key
                for conflict in item.get('conflicts', []):
                    ref = 'conflict:' + conflict['id']
                    references[ref] = {'label': item.get('label') or key, **conflict}
                    owners[ref] = key
            result = await asyncio.wait_for(self.llm.chat([
                LLMMessage(role='system', content=job['prompt']),
                LLMMessage(role='user', content=json.dumps({'target': job['field_key'],
                    'as_of': datetime.now(timezone.utc).isoformat(), 'references': references}, ensure_ascii=False)),
            ], json_schema=EvidenceJudgment.model_json_schema(), temperature=0, timeout_s=60), timeout=65)
            if result.degraded:
                raise ValueError('Degraded model response is not an assessment')
            judgment = EvidenceJudgment.model_validate(result.structured if result.structured is not None else json.loads(result.text))
            if not set(judgment.source_refs) <= references.keys():
                raise ValueError('Unknown assessment provenance')
            if judgment.score is not None and not judgment.source_refs:
                raise ValueError('Scored assessment requires references')
            dependencies = {job['field_key']} | {owners[r] for r in judgment.source_refs}
            # Verify *all* model inputs again; a concurrent change cannot become a fresh score.
            if await self.context(job['user_id']) != context:
                await self.repository.discard(job)
                await self.changed(job['user_id'], [job['field_key']])
                return 1
            assessment = EvidenceAssessment(**judgment.model_dump(),
                status='evaluated' if judgment.score is not None else 'insufficient',
                sources={r: self.source_description(references[r]) for r in judgment.source_refs},
                assessed_at=datetime.now(timezone.utc), entry_version=job['entry_version'],
                input_hash=job['input_hash'], prompt_version=job['prompt_version'], model=result.model)
            job['dependency_hashes'] = {key: fingerprint(context[key]) for key in dependencies}
            await self.repository.finish(job, assessment.model_dump(mode='json'))
        except Exception:
            # Do not log model payloads or student data.
            logger.warning('画像把握度评估未完成，将有限重试；attempt=%s', job['attempts'])
            await self.repository.finish(job, {'status': 'failed'}, retry=job['attempts'] < 3)
        return 1

    @staticmethod
    def source_description(reference):
        text = reference.get('text', reference.get('value', ''))
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        origin = reference.get('origin_ref') or ''
        return f"{reference['label']}：{text[:500]}" + (f"（{origin}）" if origin else '')
