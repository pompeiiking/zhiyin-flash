"""Requires a dedicated disposable database, never the deployed user database."""
import asyncio
import os
from uuid import uuid4

import pytest

from zhiyin_business.contracts.chsi_import import ChsiPdfConfirm
from zhiyin_business.services.chsi_import import ChsiPdfImportService
from zhiyin_business.services.profile import DefaultProfileService
from zhiyin_data_sdk.gateways.chsi import ChsiReport, ChsiField, ChsiReportKind
from zhiyin_infrastructure.postgres.chsi_imports import PostgresChsiImportRepository
from zhiyin_infrastructure.postgres.database import PostgresDatabase
from zhiyin_infrastructure.postgres.repository import PostgresProfileRepository
from zhiyin_kernel.registry import ChsiFieldSpec

pytestmark = pytest.mark.skipif(not os.getenv('ZHIYIN_CHSI_TEST_DSN'), reason='Disposable PostgreSQL database required')


class Reader:
    async def read(self, data):
        return ChsiReport(acquisition='pdf', kind=ChsiReportKind.ENROLLMENT, valid_until='2099-01-01', fields=[
            ChsiField(key=key, label=key, value=value) for key,value in
            [('student_name','测试人'),('school','测试大学'),('major','测试专业')]])


class Registry:
    async def list_chsi_fields(self):
        return [ChsiFieldSpec(key=key, label=key) for key in ('student_name','school','major')]


class Events:
    async def publish(self, event): pass


async def test_two_independent_api_instances_commit_once_and_rollback(monkeypatch):
    dsn = os.environ['ZHIYIN_CHSI_TEST_DSN']
    db1, db2 = PostgresDatabase(dsn), PostgresDatabase(dsn)
    user = 'chsi_test_' + uuid4().hex
    try:
        await db1.pool()
        await db2.pool()
        profiles1, profiles2 = PostgresProfileRepository(db1), PostgresProfileRepository(db2)
        records1, records2 = PostgresChsiImportRepository(db1), PostgresChsiImportRepository(db2)
        service1 = ChsiPdfImportService(DefaultProfileService(profiles1, Events()), records1, Reader(), Registry())
        service2 = ChsiPdfImportService(DefaultProfileService(profiles2, Events()), records2, Reader(), Registry())
        preview = await service1.preview(user, b'synthetic')
        body = ChsiPdfConfirm(preview_id=preview.preview_id, selected_keys=['school','major'], ownership_confirmed=True)
        results = await asyncio.gather(service1.confirm(user, body), service2.confirm(user, body))
        assert results[0] == results[1]
        assert all(f.entry_version == 1 for f in await profiles1.list_fields(user))
        payload = await db1.fetchval('SELECT payload FROM biz_chsi_pdf_import WHERE id=$1', preview.preview_id)
        assert payload in ('{}', {})

        # A later upload has missing student_name and can produce a separate atomic batch.
        second_user = user + '_failure'
        preview = await service1.preview(second_user, b'synthetic')
        body = ChsiPdfConfirm(preview_id=preview.preview_id, selected_keys=['school','major'], ownership_confirmed=True)
        original = profiles1.upsert_field
        writes = 0
        async def fail(*args, **kwargs):
            nonlocal writes
            writes += 1
            if writes == 2: raise RuntimeError('injected')
            return await original(*args, **kwargs)
        monkeypatch.setattr(profiles1, 'upsert_field', fail)
        with pytest.raises(RuntimeError): await service1.confirm(second_user, body)
        assert not await profiles1.list_fields(second_user)
        assert await db1.fetchval('SELECT status FROM biz_chsi_pdf_import WHERE id=$1', preview.preview_id) == 'pending'
    finally:
        for uid in (user, user + '_failure'):
            await db1.execute('DELETE FROM biz_chsi_pdf_import WHERE user_id=$1', uid)
            await db1.execute('DELETE FROM biz_profile_field WHERE user_id=$1', uid)
            await db1.execute('DELETE FROM biz_profile WHERE user_id=$1', uid)
        await db1.aclose()
        await db2.aclose()
