import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone

from zhiyin_data_sdk.repositories.chsi_imports import ChsiImportRepository


class InMemoryChsiImportRepository(ChsiImportRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, profiles):
        self.profiles = profiles
        self.records = {}
        self._lock = asyncio.Lock()

    async def create(self, record):
        async with self._lock:
            self.records[record["id"]] = deepcopy(record)

    @asynccontextmanager
    async def locked(self, user_id, preview_id):
        async with self._lock:
            before = deepcopy(self.records)
            async with self.profiles.transaction():
                try:
                    row = self.records.get(preview_id)
                    yield deepcopy(row) if row and row["user_id"] == user_id else None
                except BaseException:
                    self.records = before
                    raise

    async def finish(self, user_id, preview_id, receipt):
        row = self.records[preview_id]
        assert row["user_id"] == user_id
        row.update(status="committed", payload={}, receipt=deepcopy(receipt))

    async def cleanup(self):
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            expired = [key for key, row in self.records.items()
                       if row["status"] == "pending" and row["expires_at"] <= now]
            for key in expired:
                del self.records[key]
            return len(expired)
