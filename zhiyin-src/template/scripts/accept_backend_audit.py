"""Local PostgreSQL audit: synthetic IDs only; transaction/outbox rollback and concurrency.

No real model calls, real students, credentials or external application writes.
Committed concurrency fixtures are deleted by exact generated ID in finally.
"""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

TEMPLATE = Path(__file__).resolve().parents[1]
for package in TEMPLATE.glob('zhiyin-*'):
    if package.is_dir():
        sys.path.insert(0, str(package))
sys.stdout.reconfigure(encoding='utf-8')


async def main():
    from zhiyin_boot import Settings
    from zhiyin_business.services.academic import DefaultAcademicService
    from zhiyin_business.services.profile import DefaultProfileService
    from zhiyin_infrastructure.academic import ManualAcademicImporter
    from zhiyin_infrastructure.postgres.database import PostgresDatabase
    from zhiyin_infrastructure.postgres.repository import PostgresAcademicSnapshotRepository, PostgresProfileRepository
    from zhiyin_infrastructure.postgres.messaging import PostgresEventBus
    from zhiyin_orchestration.impl.event_bus import GatewayEventBus
    from zhiyin_infrastructure.postgres.scheduler import PostgresScheduler
    from zhiyin_data_sdk.gateways.messaging import ScheduledTask

    parsed = urlsplit(Settings.from_env().postgres_dsn)
    if parsed.hostname not in {'postgres', 'zhiyin-flash-postgres', 'localhost', '127.0.0.1'}:
        raise RuntimeError('Only local development PostgreSQL is allowed')
    credentials = parsed.netloc.rsplit('@', 1)[0] if '@' in parsed.netloc else ''
    dsn = urlunsplit(parsed._replace(netloc=(credentials + '@' if credentials else '') + '127.0.0.1:55432'))
    db = PostgresDatabase(dsn, max_size=4)
    snapshots = PostgresAcademicSnapshotRepository(db)
    profile_repo = PostgresProfileRepository(db)
    profiles = DefaultProfileService(profile_repo, GatewayEventBus(PostgresEventBus(db)))
    service = DefaultAcademicService(snapshots, ManualAcademicImporter(), profiles)
    user = 'audit_backend_' + uuid4().hex
    courses = '课程名称\t星期\t节次\t周次\n高等数学\t星期一\t1-2\t1-16'
    grades = '课程名称\t成绩\t学分\n高等数学\t88\t4'
    results = {'date': datetime.now(timezone.utc).isoformat(), 'user': user, 'checks': {}}

    class RollbackProbe(Exception):
        pass

    try:
        try:
            async with db.transaction():
                term = '2025-2026学年第一学期（联合培养与跨校课程安排）'
                await service.import_(user, courses_raw=courses, grades_raw=grades, term=term)
                assert term in next(f for f in await profiles.get_fields(user) if f.key == 'courses').value
                assert await db.fetchval("SELECT count(*) FROM orc_event_outbox WHERE payload->'payload'->>'user_id'=$1", user) == 2
                results['checks']['valid_long_term_snapshot_summaries_and_outbox'] = True
                raise RollbackProbe()
        except RollbackProbe:
            pass
        assert await snapshots.get(user) is None and not await profiles.get_fields(user)

        class FailingProfiles(DefaultProfileService):
            async def update_field(self, user_id, key, value, **kwargs):
                if key == 'scores':
                    raise RuntimeError('synthetic second-summary failure')
                return await super().update_field(user_id, key, value, **kwargs)

        failing = DefaultAcademicService(snapshots, ManualAcademicImporter(),
            FailingProfiles(profile_repo, GatewayEventBus(PostgresEventBus(db))))
        try:
            await failing.import_(user, courses_raw=courses, grades_raw=grades)
        except RuntimeError as exc:
            assert str(exc) == 'synthetic second-summary failure'
        else:
            raise AssertionError('Failure probe did not fail')
        assert await snapshots.get(user) is None and not await profiles.get_fields(user)
        assert await db.fetchval("SELECT count(*) FROM orc_event_outbox WHERE payload->'payload'->>'user_id'=$1", user) == 0
        results['checks']['second_summary_failure_rolls_back_snapshot_profile_and_outbox'] = True

        # Concurrency fixtures have no event bus, so background workers cannot
        # consume synthetic profile events while this probe runs.
        concurrent = DefaultAcademicService(snapshots, ManualAcademicImporter())
        await asyncio.gather(concurrent.import_(user, courses_raw=courses),
                             concurrent.import_(user, grades_raw=grades))
        saved = await snapshots.get(user)
        assert len(saved.courses) == 1 and len(saved.grades) == 1
        results['checks']['concurrent_independent_imports_preserve_both'] = True
        await asyncio.gather(concurrent.import_(user, courses_raw=courses.replace('高等数学', '新课程')),
                             concurrent.revoke_grades(user))
        saved = await snapshots.get(user)
        assert saved.courses[0].name == '新课程' and not saved.grades
        results['checks']['import_and_revoke_preserve_new_course_without_resurrecting_grades'] = True

        job_id = user + '-scheduler'
        moment = datetime.now(timezone.utc)
        task = ScheduledTask(task_id=job_id, event_type='audit.synthetic.scheduler', payload={})
        await db.execute("INSERT INTO orc_schedule_job(id,job_type,run_at,status,payload) VALUES($1,$2,$3,'pending',$4::jsonb)",
                         job_id, task.event_type, moment, json.dumps({'task': task.model_dump(mode='json')}))

        class ScopedSchedulerDatabase:
            # NEVER select or mutate any real scheduled job during this audit.
            def transaction(self):
                return db.transaction()

            async def fetch(self, query, *args):
                assert 'ORDER BY run_at ASC' in query and len(args) == 1
                query = query.replace('ORDER BY run_at ASC', 'AND id = $2 ORDER BY run_at ASC')
                return await db.fetch(query, *args, job_id)

            async def execute(self, query, *args):
                assert args[0] == job_id
                return await db.execute(query, *args)

        class AuditSink:
            def __init__(self):
                self.events = []

            async def publish(self, event_type, payload):
                assert event_type == 'audit.synthetic.scheduler'
                self.events.append(event_type)
                await asyncio.sleep(0.05)

        sink = AuditSink()
        scheduler_db = ScopedSchedulerDatabase()
        await asyncio.gather(PostgresScheduler(scheduler_db, sink).tick(moment),
                             PostgresScheduler(scheduler_db, sink).tick(moment))
        results['scheduler_publications'] = len(sink.events)
        assert len(sink.events) == 1, 'One due job was published by multiple scheduler workers'
        results['checks']['scheduler_workers_claim_a_due_job_once'] = True
    finally:
        assert user.startswith('audit_backend_')
        async with db.transaction():
            for statement in (
                'DELETE FROM biz_academic_snapshot WHERE user_id=$1',
                'DELETE FROM biz_profile_field WHERE user_id=$1',
                'DELETE FROM biz_profile_gap WHERE user_id=$1',
                'DELETE FROM biz_profile WHERE user_id=$1',
                "DELETE FROM orc_event_outbox WHERE payload->'payload'->>'user_id'=$1",
            ):
                await db.execute(statement, user)
            await db.execute('DELETE FROM orc_schedule_job WHERE id=$1', user + '-scheduler')
        assert await snapshots.get(user) is None and not await profiles.get_fields(user)
        results['checks']['synthetic_rows_cleaned_by_exact_id'] = True
        await db.aclose()
        path = TEMPLATE.parents[1] / 'output/backend-audit-20261020-postgres.json'
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
