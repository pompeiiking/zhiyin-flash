from copy import deepcopy
import asyncio
from zhiyin_data_sdk.repositories.student import StudentStateRepository


class InMemoryStudentStateRepository(StudentStateRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self):
        self._rows = {}
        self._locks = {}

    async def get(self, user_id):
        return deepcopy(self._rows.get(user_id, {}))

    async def update(self, user_id, change):
        async with self._locks.setdefault(user_id, asyncio.Lock()):
            result = change(await self.get(user_id))
            self._rows[user_id] = deepcopy(result)
            return deepcopy(result)
