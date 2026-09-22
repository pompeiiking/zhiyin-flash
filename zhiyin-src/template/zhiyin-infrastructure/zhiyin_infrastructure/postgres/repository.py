"""PostgreSQL Repository 实现。

使用 JSONB 保存领域对象，pgvector 保存向量；返回值始终是内核共享模型。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import uuid4

from zhiyin_data_sdk.repositories import (
    AcademicSnapshotRepository,
    AssetRepository,
    BehaviorRepository,
    ConversationMemoryRepository,
    ConversationTurnRepository,
    ProfileRepository,
    TaskSessionRepository,
    UserRepository,
    UserNoteRepository,
)
from zhiyin_data_sdk.repositories import (
    AiTaskResultRepository,
    CalendarNodeRepository,
    NotificationRepository,
    TrackEventRepository,
)
from zhiyin_data_sdk.gateways.academic import AcademicSnapshot
from zhiyin_kernel.assets import ActionPlan, CalendarNode, DirectionPlan, Report, TrackEvent
from zhiyin_kernel.blackboard import (
    AssetVersion,
    BehaviorLog,
    ConversationMemory,
    ConversationTurn,
    Profile,
    ProfileField,
    ProfileGap,
    TaskSession,
    UserNote,
)
from zhiyin_kernel.enums import AssetType, BehaviorEventType, LoopStage, TaskStatus
from zhiyin_kernel.errors import ResourceNotFound
from zhiyin_kernel.identity import UserAccount
from zhiyin_infrastructure.postgres.database import PostgresDatabase


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> Optional[datetime]:
    """导入时刻是从业务层带上来的 ISO 串；解析不了就用当前时间，
    绝不因为一个时间格式把整份导入丢掉。"""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _dump(model: Any) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


def _load(model_type: Any, payload: Any) -> Any:
    if isinstance(payload, str):
        payload = json.loads(payload)
    return model_type.model_validate(payload)


def _affected(result: Any) -> int:
    """把 asyncpg 的 `execute()` 返回值（如 `DELETE 1`）翻成条数。

    `execute()` 不给 rowcount，只给一条状态串；直接 `int(...)` 会在驱动换版本时炸。
    这里只取状态串最后一段，取不到就当 0（调用方按"没删到"处理是安全的）。
    """
    text = str(result or "")
    tail = text.rsplit(" ", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _load_json(payload: Any) -> dict[str, Any]:
    """取原始 JSON（不经过模型），用于 AI 任务产出的信封。"""
    value = json.loads(payload) if isinstance(payload, str) else payload
    return value if isinstance(value, dict) else {}


def _dump_value(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _assemble_profile(
    user_id: str,
    head_row: Any,
    fields: list[ProfileField],
    gaps: list[ProfileGap],
) -> Optional[Profile]:
    """头行 + 字段行 → 画像。**头行缺、字段行在时，按字段把容器补出来。**

    头行（`biz_profile`）只装三样东西：这份画像归谁、整体版本、整体更新时间；
    **字段行才是事实**。所以两种情况必须分开：

      · 什么行都没有 → 真的还没建档，返回 None；
      · 头行不在、字段行在 → 画像是有内容的，把容器按字段补出来
        （迁移只搬了字段行、或早年的写入没建头行，都会长成这样）。

    此前一律返回 None，于是同一个用户的同一份画像，工作台看得见、AI 说
    "画像里没有这一条" —— 画像页正中间那句"这一条现在还没有可看的内容"就是这么来的。
    当时在工作台里就地补过一次（那段补丁已删），但 AI 任务、影响面这些别的读法没补，
    谁补谁不补全凭记性。所以补在仓库这一层，只补一次、所有读法共享。
    """
    if head_row is None:
        if not fields and not gaps:
            return None
        stamps = [field.updated_at for field in fields]
        return Profile(
            id=f"profile-{user_id}",
            user_id=user_id,
            fields=fields,
            gaps=gaps,
            updated_at=max(stamps) if stamps else _now(),
        )
    return Profile(
        id=head_row["profile_id"],
        user_id=user_id,
        version=head_row["version"],
        updated_at=head_row["updated_at"],
        fields=fields,
        gaps=gaps,
    )


class PostgresProfileRepository(ProfileRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get(self, user_id: str) -> Optional[Profile]:
        profile_row = await self._db.fetchrow(
            """
            SELECT profile_id, version, updated_at
            FROM biz_profile
            WHERE user_id = $1
            """,
            user_id,
        )
        return _assemble_profile(
            user_id, profile_row, await self.list_fields(user_id), await self.list_gaps(user_id)
        )

    async def save(self, profile: Profile) -> Profile:
        stored = profile.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("prf")
        stored.updated_at = _now()
        async with (await self._db.pool()).acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO biz_profile (user_id, profile_id, version, updated_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET
                        profile_id = EXCLUDED.profile_id,
                        version = EXCLUDED.version,
                        updated_at = EXCLUDED.updated_at
                    """,
                    stored.user_id,
                    stored.id,
                    stored.version,
                    stored.updated_at,
                )
                await connection.execute(
                    "DELETE FROM biz_profile_field WHERE user_id = $1",
                    stored.user_id,
                )
                for field in stored.fields:
                    await connection.execute(
                        """
                        INSERT INTO biz_profile_field
                            (user_id, key, label, value, confidence, source, evidence, updated_at)
                        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb, $8)
                        """,
                        stored.user_id,
                        field.key,
                        field.label,
                        _dump_value(field.value),
                        field.confidence,
                        field.source.value,
                        _dump_value(field.evidence),
                        field.updated_at,
                    )
                await connection.execute(
                    "DELETE FROM biz_profile_gap WHERE user_id = $1",
                    stored.user_id,
                )
                for gap in stored.gaps:
                    await connection.execute(
                        """
                        INSERT INTO biz_profile_gap
                            (user_id, key, label, reason, suggested_next_action)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        stored.user_id,
                        gap.key,
                        gap.label,
                        gap.reason,
                        gap.suggested_next_action,
                    )
        return stored

    async def upsert_field(self, user_id: str, field: ProfileField) -> ProfileField:
        incoming = field.model_copy(deep=True)
        incoming.updated_at = _now()
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            await connection.execute(
                """
                INSERT INTO biz_profile (user_id, profile_id, version, updated_at)
                VALUES ($1, $2, 1, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    version = biz_profile.version + 1,
                    updated_at = EXCLUDED.updated_at
                """,
                user_id,
                _new_id("prf"),
                incoming.updated_at,
            )
            await connection.execute(
                """
                INSERT INTO biz_profile_field
                    (user_id, key, label, value, confidence, source, evidence, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb, $8)
                ON CONFLICT (user_id, key) DO UPDATE SET
                    label = EXCLUDED.label,
                    value = EXCLUDED.value,
                    confidence = EXCLUDED.confidence,
                    source = EXCLUDED.source,
                    evidence = EXCLUDED.evidence,
                    updated_at = EXCLUDED.updated_at
                """,
                user_id,
                incoming.key,
                incoming.label,
                _dump_value(incoming.value),
                incoming.confidence,
                incoming.source.value,
                _dump_value(incoming.evidence),
                incoming.updated_at,
            )
        return incoming

    async def delete_field(self, user_id: str, key: str) -> None:
        """删掉一个画像字段，并把画像版本 +1。

        版本要动：采集清单与气泡编排都按"画像变过"重算，
        删字段如果不动版本，界面上会继续显示那份已经作废的结论。
        """
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            await connection.execute(
                "DELETE FROM biz_profile_field WHERE user_id = $1 AND key = $2",
                user_id,
                key,
            )
            # 用 INSERT…ON CONFLICT，不用 UPDATE：头行缺失时 UPDATE 会静默改 0 行，
            # 版本号从此永远不动（删了字段，界面上那份结论却还挂着）。
            await connection.execute(
                """
                INSERT INTO biz_profile (user_id, profile_id, version, updated_at)
                VALUES ($1, $2, 1, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    version = biz_profile.version + 1,
                    updated_at = EXCLUDED.updated_at
                """,
                user_id,
                _new_id("prf"),
                _now(),
            )

    async def list_fields(
        self, user_id: str, keys: Optional[Sequence[str]] = None
    ) -> list[ProfileField]:
        rows = await self._db.fetch(
            """
            SELECT key, label, value, confidence, source, evidence, updated_at
            FROM biz_profile_field
            WHERE user_id = $1
              AND ($2::text[] IS NULL OR key = ANY($2::text[]))
            ORDER BY updated_at ASC
            """,
            user_id,
            list(keys) if keys else None,
        )
        return [
            ProfileField(
                key=row["key"],
                label=row["label"] or "",
                value=_load_value(row["value"]),
                confidence=row["confidence"],
                source=row["source"],
                evidence=_load_value(row["evidence"]) or [],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def list_gaps(self, user_id: str) -> list[ProfileGap]:
        rows = await self._db.fetch(
            """
            SELECT key, label, reason, suggested_next_action
            FROM biz_profile_gap
            WHERE user_id = $1
            ORDER BY key ASC
            """,
            user_id,
        )
        return [
            ProfileGap(
                key=row["key"],
                label=row["label"] or "",
                reason=row["reason"],
                suggested_next_action=row["suggested_next_action"],
            )
            for row in rows
        ]

    async def replace_gaps(self, user_id: str, gaps: list[ProfileGap]) -> None:
        now = _now()
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            await connection.execute(
                """
                INSERT INTO biz_profile (user_id, profile_id, version, updated_at)
                VALUES ($1, $2, 1, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    version = biz_profile.version + 1,
                    updated_at = EXCLUDED.updated_at
                """,
                user_id,
                _new_id("prf"),
                now,
            )
            await connection.execute(
                "DELETE FROM biz_profile_gap WHERE user_id = $1", user_id
            )
            for gap in gaps:
                await connection.execute(
                    """
                    INSERT INTO biz_profile_gap
                        (user_id, key, label, reason, suggested_next_action)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    user_id,
                    gap.key,
                    gap.label,
                    gap.reason,
                    gap.suggested_next_action,
                )


class PostgresBehaviorRepository(BehaviorRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def append(self, log: BehaviorLog) -> BehaviorLog:
        stored = log.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("bhv")
        await self._db.execute(
            """
            INSERT INTO biz_behavior_log
                (id, user_id, event_type, occurred_at, payload)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            stored.id,
            stored.user_id,
            stored.event_type.value,
            stored.occurred_at,
            _dump(stored),
        )
        return stored

    async def list_by_user(
        self,
        user_id: str,
        *,
        event_types: Optional[Sequence[BehaviorEventType]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[BehaviorLog]:
        rows = await self._db.fetch(
            """
            SELECT payload FROM biz_behavior_log
            WHERE user_id = $1
              AND ($2::text[] IS NULL OR event_type = ANY($2::text[]))
              AND ($3::timestamptz IS NULL OR occurred_at >= $3)
              AND ($4::timestamptz IS NULL OR occurred_at <= $4)
            ORDER BY occurred_at DESC
            LIMIT $5
            """,
            user_id,
            [item.value for item in event_types] if event_types else None,
            since,
            until,
            limit,
        )
        return [_load(BehaviorLog, row["payload"]) for row in rows]

    async def last_occurred_at(
        self, user_id: str, event_type: BehaviorEventType
    ) -> Optional[datetime]:
        return await self._db.fetchval(
            """
            SELECT MAX(occurred_at) FROM biz_behavior_log
            WHERE user_id = $1 AND event_type = $2
            """,
            user_id,
            event_type.value,
        )


class PostgresConversationMemoryRepository(ConversationMemoryRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get(self, user_id: str, task_id: str) -> Optional[ConversationMemory]:
        row = await self._db.fetchrow(
            """
            SELECT payload FROM biz_conversation_memory
            WHERE user_id = $1 AND task_id = $2
            """,
            user_id,
            task_id or "",
        )
        if not row:
            return None
        memory = _load(ConversationMemory, row["payload"])
        if not memory.task_id:
            memory.task_id = None
        return memory

    async def upsert(self, memory: ConversationMemory) -> ConversationMemory:
        stored = memory.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("mem")
        stored.last_active_at = _now()
        await self._db.execute(
            """
            INSERT INTO biz_conversation_memory
                (user_id, task_id, last_active_at, payload)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (user_id, task_id) DO UPDATE SET
                last_active_at = EXCLUDED.last_active_at,
                payload = EXCLUDED.payload
            """,
            stored.user_id,
            stored.task_id or "",
            stored.last_active_at,
            _dump(stored),
        )
        return stored

    async def list_by_user(self, user_id: str) -> list[ConversationMemory]:
        rows = await self._db.fetch(
            """
            SELECT payload FROM biz_conversation_memory
            WHERE user_id = $1
            ORDER BY last_active_at DESC
            """,
            user_id,
        )
        return [_load(ConversationMemory, row["payload"]) for row in rows]

    async def delete(self, user_id: str, task_id: str) -> None:
        await self._db.execute(
            "DELETE FROM biz_conversation_memory WHERE user_id = $1 AND task_id = $2",
            user_id,
            task_id or "",
        )


class PostgresConversationTurnRepository(ConversationTurnRepository):
    """逐轮对话原文。列式存储：要按会话与时间查，不该埋在 JSON 里。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def append(self, turn: ConversationTurn) -> ConversationTurn:
        stored = turn.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("turn")
        await self._db.execute(
            """
            INSERT INTO biz_conversation_turn
                (id, user_id, task_id, role, text, loop_stage, agent_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            stored.id,
            stored.user_id,
            stored.task_id or "",
            stored.role,
            stored.text,
            stored.loop_stage.value,
            stored.agent_id,
            stored.created_at,
        )
        return stored

    async def list_by_task(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationTurn]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, task_id, role, text, loop_stage, agent_id, created_at
            FROM biz_conversation_turn
            WHERE user_id = $1 AND task_id = $2
            ORDER BY created_at ASC
            LIMIT $3
            """,
            user_id,
            task_id or "",
            limit,
        )
        return [
            ConversationTurn(
                id=row["id"],
                user_id=row["user_id"],
                task_id=row["task_id"] or None,
                role=row["role"],
                text=row["text"],
                loop_stage=LoopStage(row["loop_stage"]),
                agent_id=row["agent_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


class PostgresUserNoteRepository(UserNoteRepository):
    """用户自己写下的东西。列式存储：文本要能被查询与引用，不该埋在 JSON 里。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def list_by_user(self, user_id: str) -> list[UserNote]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, kind, text, done, created_at, updated_at
            FROM biz_user_note
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [_note_from_row(row) for row in rows]

    async def upsert(self, note: UserNote) -> UserNote:
        stored = note.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("note")
        stored.updated_at = _now()
        await self._db.execute(
            """
            INSERT INTO biz_user_note
                (id, user_id, kind, text, done, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET
                kind = EXCLUDED.kind,
                text = EXCLUDED.text,
                done = EXCLUDED.done,
                updated_at = EXCLUDED.updated_at
            """,
            stored.id,
            stored.user_id,
            stored.kind,
            stored.text,
            stored.done,
            stored.created_at,
            stored.updated_at,
        )
        return stored

    async def delete(self, user_id: str, note_id: str) -> None:
        await self._db.execute(
            "DELETE FROM biz_user_note WHERE user_id = $1 AND id = $2",
            user_id,
            note_id,
        )


def _note_from_row(row: Any) -> UserNote:
    return UserNote(
        id=row["id"],
        user_id=row["user_id"],
        kind=row["kind"],
        text=row["text"],
        done=bool(row["done"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresAcademicSnapshotRepository(AcademicSnapshotRepository):
    """教务系统快照：一个用户一行，重新取数整体替换。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get(self, user_id: str) -> Optional[AcademicSnapshot]:
        row = await self._db.fetchrow(
            "SELECT payload FROM biz_academic_snapshot WHERE user_id = $1", user_id
        )
        if not row:
            return None
        return _load(AcademicSnapshot, row["payload"])

    async def upsert(self, user_id: str, snapshot: AcademicSnapshot) -> AcademicSnapshot:
        stored = snapshot.model_copy(deep=True)
        await self._db.execute(
            """
            INSERT INTO biz_academic_snapshot
                (user_id, school, source, term, imported_at, payload)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (user_id) DO UPDATE SET
                school = EXCLUDED.school,
                source = EXCLUDED.source,
                term = EXCLUDED.term,
                imported_at = EXCLUDED.imported_at,
                payload = EXCLUDED.payload
            """,
            user_id,
            stored.school,
            stored.source,
            stored.term,
            _parse_iso(stored.imported_at) or _now(),
            _dump(stored),
        )
        return stored

    async def delete(self, user_id: str) -> None:
        await self._db.execute(
            "DELETE FROM biz_academic_snapshot WHERE user_id = $1", user_id
        )


class PostgresAssetRepository(AssetRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get_latest_version(
        self, user_id: str, asset_type: AssetType
    ) -> Optional[AssetVersion]:
        row = await self._db.fetchrow(
            """
            SELECT payload FROM biz_asset_version
            WHERE user_id = $1 AND asset_type = $2
            ORDER BY version DESC LIMIT 1
            """,
            user_id,
            asset_type.value,
        )
        return _load(AssetVersion, row["payload"]) if row else None

    async def list_versions(self, user_id: str, asset_type: AssetType) -> list[AssetVersion]:
        rows = await self._db.fetch(
            """
            SELECT payload FROM biz_asset_version
            WHERE user_id = $1 AND asset_type = $2
            ORDER BY version ASC
            """,
            user_id,
            asset_type.value,
        )
        return [_load(AssetVersion, row["payload"]) for row in rows]

    async def save_version(self, version: AssetVersion) -> AssetVersion:
        stored = version.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("av")
        async with self._db.transaction() as connection:
            await _lock(
                connection,
                f"asset_version:{stored.user_id}:{stored.asset_type.value}",
            )
            latest = await connection.fetchrow(
                """
                SELECT version FROM biz_asset_version
                WHERE user_id = $1 AND asset_type = $2
                ORDER BY version DESC LIMIT 1
                """,
                stored.user_id,
                stored.asset_type.value,
            )
            floor = int(latest["version"]) if latest else 0
            stored.version = max(stored.version, floor + 1)
            stored.created_at = _now()
            await connection.execute(
                """
                INSERT INTO biz_asset_version
                    (id, user_id, asset_type, version, created_at, payload)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                stored.id,
                stored.user_id,
                stored.asset_type.value,
                stored.version,
                stored.created_at,
                _dump(stored),
            )
        return stored

    async def list_affected_assets(
        self, user_id: str, profile_keys: Sequence[str]
    ) -> list[AssetVersion]:
        rows = await self._db.fetch(
            """
            SELECT DISTINCT ON (asset_type) payload
            FROM biz_asset_version
            WHERE user_id = $1
            ORDER BY asset_type, version DESC
            """,
            user_id,
        )
        changed = set(profile_keys)
        affected = [
            _load(AssetVersion, row["payload"])
            for row in rows
            if changed & set(_load(AssetVersion, row["payload"]).depends_on_profile_keys)
        ]
        affected.sort(key=lambda item: (item.asset_type.value, item.version))
        return affected

    async def get_report(
        self, user_id: str, version: Optional[int] = None
    ) -> Optional[Report]:
        if version is None:
            row = await self._db.fetchrow(
                """
                SELECT payload FROM biz_asset_content
                WHERE user_id = $1 AND asset_type = 'report'
                ORDER BY version DESC LIMIT 1
                """,
                user_id,
            )
        else:
            row = await self._db.fetchrow(
                """
                SELECT payload FROM biz_asset_content
                WHERE user_id = $1 AND asset_type = 'report' AND version = $2
                ORDER BY created_at DESC LIMIT 1
                """,
                user_id,
                version,
            )
        return _load(Report, row["payload"]) if row else None

    async def save_report(self, report: Report) -> Report:
        stored = report.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("rpt")
        async with self._db.transaction() as connection:
            await _lock(connection, f"report:{stored.user_id}")
            latest = await connection.fetchrow(
                """
                SELECT payload FROM biz_asset_content
                WHERE user_id = $1 AND asset_type = 'report'
                ORDER BY version DESC LIMIT 1
                """,
                stored.user_id,
            )
            if latest is not None:
                stored.version = max(
                    stored.version, _load(Report, latest["payload"]).version + 1
                )
            await self._put_content(
                stored.user_id, "report", stored.version, stored, connection
            )
        return stored

    async def list_direction_plans(self, user_id: str) -> list[DirectionPlan]:
        rows = await self._db.fetch(
            """
            SELECT payload FROM biz_asset_content
            WHERE user_id = $1 AND asset_type = 'direction_plan'
            ORDER BY sort_order ASC, id ASC
            """,
            user_id,
        )
        return [_load(DirectionPlan, row["payload"]) for row in rows]

    async def save_direction_plans(
        self, user_id: str, plans: list[DirectionPlan]
    ) -> None:
        async with self._db.transaction() as connection:
            await self._delete_content(user_id, "direction_plan", connection)
            for sort_order, plan in enumerate(plans):
                stored = plan.model_copy(deep=True)
                if not stored.id:
                    stored.id = _new_id("plan")
                await self._put_content(
                    user_id, "direction_plan", 0, stored, connection,
                    sort_order=sort_order,
                )

    async def select_direction_plan(self, user_id: str, plan_id: str) -> DirectionPlan:
        """先确认目标存在，再落状态变更（与本地实现同一顺序，防两种实现漂移）。"""
        plans = await self.list_direction_plans(user_id)
        target = next((plan for plan in plans if plan.id == plan_id), None)
        if target is None:
            raise ResourceNotFound(f"方向方案不存在：{plan_id}")

        now = _now()
        for plan in plans:
            if plan is target:
                plan.selected = True
                plan.selected_at = now
            else:
                plan.selected = False
                plan.selected_at = None
        await self.save_direction_plans(user_id, plans)
        return target

    async def get_action_plan(self, user_id: str) -> Optional[ActionPlan]:
        row = await self._db.fetchrow(
            """
            SELECT payload FROM biz_asset_content
            WHERE user_id = $1 AND asset_type = 'action_plan'
            ORDER BY created_at DESC LIMIT 1
            """,
            user_id,
        )
        return _load(ActionPlan, row["payload"]) if row else None

    async def save_action_plan(self, user_id: str, plan: ActionPlan) -> ActionPlan:
        stored = plan.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("act")
        async with self._db.transaction() as connection:
            await self._delete_content(user_id, "action_plan", connection)
            await self._put_content(user_id, "action_plan", 0, stored, connection)
        return stored

    async def mark_task_done(
        self, user_id: str, task_id: str, *, done: bool = True
    ) -> ActionPlan:
        plan = await self.get_action_plan(user_id)
        if plan is None:
            raise ResourceNotFound(f"行动计划不存在：{user_id}")
        for phase in plan.phases:
            for task in phase.tasks:
                # 优先按任务 id 定位（新数据）；老数据没有 id，回落到
                # 「阶段名:任务文本」与"裸任务文本"两种历史口径。
                if task_id in {task.id, f"{phase.name}:{task.text}", task.text}:
                    task.done = done
                    task.done_at = _now() if done else None
                    await self.save_action_plan(user_id, plan)
                    return plan
        raise ResourceNotFound(f"行动任务不存在：{task_id}")

    async def _put_content(
        self,
        user_id: str,
        asset_type: str,
        version: int,
        model: Any,
        connection: Any = None,
        sort_order: int = 0,
    ) -> None:
        executor = connection or self._db
        await executor.execute(
            """
            INSERT INTO biz_asset_content
                (id, user_id, asset_type, version, sort_order, created_at, payload)
            VALUES ($1, $2, $3, $4, $5, NOW(), $6::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                payload = EXCLUDED.payload,
                version = EXCLUDED.version,
                sort_order = EXCLUDED.sort_order
            """,
            model.id,
            user_id,
            asset_type,
            version,
            sort_order,
            _dump(model),
        )

    async def _delete_content(
        self, user_id: str, asset_type: str, connection: Any = None
    ) -> None:
        executor = connection or self._db
        await executor.execute(
            "DELETE FROM biz_asset_content WHERE user_id = $1 AND asset_type = $2",
            user_id,
            asset_type,
        )


class PostgresTaskSessionRepository(TaskSessionRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get(self, session_id: str) -> Optional[TaskSession]:
        row = await self._db.fetchrow(
            "SELECT payload FROM biz_task_session WHERE id = $1", session_id
        )
        return _load(TaskSession, row["payload"]) if row else None

    async def find_active(self, user_id: str, task_code: str) -> Optional[TaskSession]:
        row = await self._db.fetchrow(
            """
            SELECT payload FROM biz_task_session
            WHERE user_id = $1 AND task_code = $2 AND status = 'active'
            ORDER BY updated_at DESC LIMIT 1
            """,
            user_id,
            task_code,
        )
        return _load(TaskSession, row["payload"]) if row else None

    async def list_by_user(
        self, user_id: str, statuses: Optional[Sequence[TaskStatus]] = None
    ) -> list[TaskSession]:
        rows = await self._db.fetch(
            """
            SELECT payload FROM biz_task_session
            WHERE user_id = $1
              AND ($2::text[] IS NULL OR status = ANY($2::text[]))
            ORDER BY updated_at DESC
            """,
            user_id,
            [item.value for item in statuses] if statuses else None,
        )
        return [_load(TaskSession, row["payload"]) for row in rows]

    async def create(self, session: TaskSession) -> TaskSession:
        stored = session.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("tsk")
        await self._db.execute(
            """
            INSERT INTO biz_task_session
                (id, user_id, task_code, status, updated_at, payload)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at,
                payload = EXCLUDED.payload
            """,
            stored.id,
            stored.user_id,
            stored.task_code,
            stored.status.value,
            stored.updated_at,
            _dump(stored),
        )
        return stored

    async def update_stage(
        self, session_id: str, stage: LoopStage, lead_agent: str
    ) -> TaskSession:
        async with self._db.transaction() as connection:
            await _lock(connection, f"session:{session_id}")
            row = await connection.fetchrow(
                "SELECT payload FROM biz_task_session WHERE id = $1 FOR UPDATE",
                session_id,
            )
            if row is None:
                raise ResourceNotFound(f"任务会话不存在：{session_id}")
            session = _load(TaskSession, row["payload"])
            session.loop_stage = stage
            session.lead_agent = lead_agent
            session.updated_at = _now()
            await connection.execute(
                """
                UPDATE biz_task_session
                SET status = $2, updated_at = $3, payload = $4::jsonb
                WHERE id = $1
                """,
                session.id,
                session.status.value,
                session.updated_at,
                _dump(session),
            )
        return session

    async def update_status(self, session_id: str, status: TaskStatus) -> TaskSession:
        async with self._db.transaction() as connection:
            await _lock(connection, f"session:{session_id}")
            row = await connection.fetchrow(
                "SELECT payload FROM biz_task_session WHERE id = $1 FOR UPDATE",
                session_id,
            )
            if row is None:
                raise ResourceNotFound(f"任务会话不存在：{session_id}")
            session = _load(TaskSession, row["payload"])
            session.status = status
            session.updated_at = _now()
            await connection.execute(
                """
                UPDATE biz_task_session
                SET status = $2, updated_at = $3, payload = $4::jsonb
                WHERE id = $1
                """,
                session.id,
                session.status.value,
                session.updated_at,
                _dump(session),
            )
        return session


class PostgresUserRepository(UserRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get_by_id(self, user_id: str) -> Optional[UserAccount]:
        row = await self._db.fetchrow(
            "SELECT payload FROM biz_user_account WHERE id = $1", user_id
        )
        return _load(UserAccount, row["payload"]) if row else None

    async def get_by_phone(self, phone: str) -> Optional[UserAccount]:
        row = await self._db.fetchrow(
            "SELECT payload FROM biz_user_account WHERE phone = $1", phone
        )
        return _load(UserAccount, row["payload"]) if row else None

    async def create(self, user: UserAccount) -> UserAccount:
        stored = user.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("usr")
        await self._db.execute(
            """
            INSERT INTO biz_user_account (id, phone, payload)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                phone = EXCLUDED.phone,
                payload = EXCLUDED.payload
            """,
            stored.id,
            stored.phone,
            _dump(stored),
        )
        return stored

    async def touch_last_login(self, user_id: str, at: datetime) -> None:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ResourceNotFound(f"用户不存在：{user_id}")
        user.last_login_at = at
        await self.create(user)


class PostgresCalendarNodeRepository(CalendarNodeRepository):
    """关键节点日历：真表存储（`biz_calendar_node`）。

    此前是 `FunctionService` 的进程内 dict —— 重启即丢、多实例不共享。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def list_nodes(self, user_id: str) -> list[CalendarNode]:
        rows = await self._db.fetch(
            """
            SELECT node_id, user_id, title, due_at, source, related_task_text
            FROM biz_calendar_node
            WHERE user_id = $1
            ORDER BY due_at ASC NULLS LAST, node_id ASC
            """,
            user_id,
        )
        return [
            CalendarNode(
                node_id=row["node_id"],
                user_id=row["user_id"],
                title=row["title"],
                due_at=row["due_at"],
                source=row["source"],
                related_task_text=row["related_task_text"],
            )
            for row in rows
        ]

    async def upsert_node(self, user_id: str, node: CalendarNode) -> CalendarNode:
        stored = node.model_copy(update={"user_id": user_id})
        await self._db.execute(
            """
            INSERT INTO biz_calendar_node
                (node_id, user_id, title, due_at, source, related_task_text, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (node_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                title = EXCLUDED.title,
                due_at = EXCLUDED.due_at,
                source = EXCLUDED.source,
                related_task_text = EXCLUDED.related_task_text,
                updated_at = NOW()
            """,
            stored.node_id,
            user_id,
            stored.title,
            stored.due_at,
            stored.source,
            stored.related_task_text,
        )
        return stored

    async def delete_node(self, user_id: str, node_id: str) -> int:
        result = await self._db.execute(
            "DELETE FROM biz_calendar_node WHERE user_id = $1 AND node_id = $2",
            user_id,
            node_id,
        )
        return _affected(result)


class PostgresTrackEventRepository(TrackEventRepository):
    """跟踪时间线：真表存储（`biz_track_event`），只追加。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def list_events(self, user_id: str, *, limit: int = 50) -> list[TrackEvent]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, type, title, detail, occurred_at, due_at,
                   related_task_id, related_stage
            FROM biz_track_event
            WHERE user_id = $1
            ORDER BY occurred_at DESC
            LIMIT $2
            """,
            user_id,
            max(int(limit), 1),
        )
        return [
            TrackEvent(
                id=row["id"],
                user_id=row["user_id"],
                type=row["type"],
                title=row["title"],
                detail=row["detail"],
                occurred_at=row["occurred_at"],
                due_at=row["due_at"],
                related_task_id=row["related_task_id"],
                related_stage=row["related_stage"],
            )
            for row in rows
        ]

    async def append_event(self, user_id: str, event: TrackEvent) -> TrackEvent:
        stored = event.model_copy(
            update={
                "user_id": user_id,
                "id": event.id or f"track_{uuid4().hex[:12]}",
                "occurred_at": event.occurred_at or datetime.now(timezone.utc),
            }
        )
        await self._db.execute(
            """
            INSERT INTO biz_track_event
                (id, user_id, type, title, detail, occurred_at, due_at,
                 related_task_id, related_stage)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            stored.id,
            user_id,
            stored.type,
            stored.title,
            stored.detail,
            stored.occurred_at,
            stored.due_at,
            stored.related_task_id,
            stored.related_stage,
        )
        return stored


class PostgresNotificationRepository(NotificationRepository):
    """通知读侧：读 `orc_notification` —— 与 `PostgresNotifier` 的写侧**同一张表**。

    此前读侧是 `FunctionService` 自己的进程内队列，于是"通知写进库了、前端什么都读不到"。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def list_pending(self, user_id: str) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, channel, status, title, body, action,
                   related_task_id, created_at, sent_at
            FROM orc_notification
            WHERE user_id = $1 AND status <> 'read'
            ORDER BY created_at DESC
            LIMIT 20
            """,
            user_id,
        )
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "body": row["body"],
                "occurred_at": (row["sent_at"] or row["created_at"]).isoformat(),
                "channel": row["channel"],
                # 写侧本来就存了 action（"点开我要去哪"），读侧不取的话，
                # 浮窗就只能显示成一坨文字 —— 用户在通知上点不动任何东西。
                "action": _load_value(row["action"]) if row["action"] else None,
                "related_task_id": row["related_task_id"],
            }
            for row in rows
        ]

    async def mark_read(self, user_id: str, message_id: str) -> int:
        result = await self._db.execute(
            "UPDATE orc_notification SET status = 'read' WHERE user_id = $1 AND id = $2",
            user_id,
            message_id,
        )
        return _affected(result)

    async def last_sent_at(self, user_id: str) -> Optional[datetime]:
        value = await self._db.fetchval(
            """
            SELECT MAX(COALESCE(sent_at, created_at))
            FROM orc_notification
            WHERE user_id = $1
            """,
            user_id,
        )
        return value

    async def count_since(self, user_id: str, since: datetime) -> int:
        value = await self._db.fetchval(
            """
            SELECT COUNT(*)
            FROM orc_notification
            WHERE user_id = $1 AND COALESCE(sent_at, created_at) >= $2
            """,
            user_id,
            since,
        )
        return int(value or 0)


class PostgresAiTaskResultRepository(AiTaskResultRepository):
    """AI 任务产出：真表存储（`ai_task_result`），跨重启、跨实例。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get(self, user_id: str, task_key: str) -> Optional[dict[str, Any]]:
        row = await self._db.fetchrow(
            "SELECT payload FROM ai_task_result WHERE user_id = $1 AND task_key = $2",
            user_id,
            task_key,
        )
        return _load_json(row["payload"]) if row else None

    async def put(self, user_id: str, task_key: str, payload: dict[str, Any]) -> None:
        await self._db.execute(
            """
            INSERT INTO ai_task_result (user_id, task_key, payload, updated_at)
            VALUES ($1, $2, $3::jsonb, NOW())
            ON CONFLICT (user_id, task_key) DO UPDATE SET
                payload = EXCLUDED.payload,
                updated_at = NOW()
            """,
            user_id,
            task_key,
            json.dumps(payload, ensure_ascii=False, default=str),
        )

    async def delete_prefix(self, user_id: str, prefix: str = "") -> int:
        result = await self._db.execute(
            "DELETE FROM ai_task_result WHERE user_id = $1 AND task_key LIKE $2",
            user_id,
            f"{prefix}%",
        )
        return _affected(result)


async def _lock(connection: Any, key: str) -> None:
    """在事务内加 PostgreSQL advisory lock，避免版本号并发竞争。"""
    await connection.execute("SELECT pg_advisory_xact_lock(hashtext($1))", key)


__all__ = [
    "PostgresAiTaskResultRepository",
    "PostgresAssetRepository",
    "PostgresAcademicSnapshotRepository",
    "PostgresBehaviorRepository",
    "PostgresCalendarNodeRepository",
    "PostgresConversationMemoryRepository",
    "PostgresNotificationRepository",
    "PostgresProfileRepository",
    "PostgresTaskSessionRepository",
    "PostgresTrackEventRepository",
    "PostgresUserNoteRepository",
    "PostgresUserRepository",
]
