import json
from contextlib import asynccontextmanager
from datetime import datetime

from zhiyin_data_sdk.repositories.chsi_imports import ChsiImportRepository


class PostgresChsiImportRepository(ChsiImportRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database):
        self.db = database

    async def create(self, record):
        await self.db.execute('''INSERT INTO biz_chsi_pdf_import
            (id,user_id,file_hash,status,expires_at,payload)
            VALUES($1,$2,$3,'pending',$4::timestamptz,$5::jsonb)''',
            record["id"], record["user_id"], record["file_hash"],
            datetime.fromisoformat(record["expires_at"]),
            json.dumps(record["payload"], ensure_ascii=False))

    @asynccontextmanager
    async def locked(self, user_id, preview_id):
        async with self.db.transaction():
            await self.db.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "profile:" + user_id)
            row = await self.db.fetchrow('''SELECT * FROM biz_chsi_pdf_import
                WHERE id=$1 AND user_id=$2 FOR UPDATE''', preview_id, user_id)
            if row is None:
                yield None
                return
            await self.db.fetch("SELECT key FROM biz_profile_field WHERE user_id=$1 FOR UPDATE", user_id)
            data = dict(row)
            for key in ("payload", "receipt"):
                data[key] = json.loads(data[key]) if isinstance(data[key], str) else data[key]
            data["expires_at"] = data["expires_at"].isoformat()
            yield data

    async def finish(self, user_id, preview_id, receipt):
        await self.db.execute('''UPDATE biz_chsi_pdf_import
            SET status='committed',payload='{}'::jsonb,receipt=$3::jsonb,imported_at=NOW()
            WHERE id=$1 AND user_id=$2''', preview_id, user_id, json.dumps(receipt, ensure_ascii=False))

    async def cleanup(self):
        result = await self.db.execute("DELETE FROM biz_chsi_pdf_import WHERE status='pending' AND expires_at<=NOW()")
        return int(result.split()[-1])
