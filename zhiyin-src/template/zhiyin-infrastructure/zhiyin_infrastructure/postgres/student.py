import json
from zhiyin_data_sdk.repositories.student import StudentStateRepository


class PostgresStudentStateRepository(StudentStateRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database):
        self._db = database

    async def get(self, user_id):
        row = await self._db.fetchrow(
            "SELECT payload FROM biz_student_state WHERE user_id=$1", user_id
        )
        value = row["payload"] if row else {}
        return json.loads(value) if isinstance(value, str) else value

    async def update(self, user_id, change):
        async with self._db.transaction() as conn:
            await conn.execute(
                "INSERT INTO biz_student_state(user_id) VALUES($1) ON CONFLICT DO NOTHING", user_id
            )
            row = await conn.fetchrow(
                "SELECT payload FROM biz_student_state WHERE user_id=$1 FOR UPDATE", user_id
            )
            value = row["payload"]
            result = change(json.loads(value) if isinstance(value, str) else value)
            await conn.execute(
                "UPDATE biz_student_state SET payload=$2::jsonb, updated_at=NOW() WHERE user_id=$1",
                user_id,
                json.dumps(result, ensure_ascii=False),
            )
            return result
