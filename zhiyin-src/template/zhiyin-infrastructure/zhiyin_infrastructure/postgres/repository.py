"""PostgreSQL Repository 实现。

使用 JSONB 保存领域对象，pgvector 保存向量；返回值始终是内核共享模型。
"""

from __future__ import annotations
from contextlib import asynccontextmanager

import json
import logging
from datetime import datetime, timezone, timedelta
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
    ProfileClue,
    ProfileField,
    ProfileFieldRevision,
    ProfileGap,
    TaskSession,
    UserNote,
)
from zhiyin_kernel.enums import (
    AssetType,
    BehaviorEventType,
    LoopStage,
    ProfileClueStatus,
    ProfileEntryStatus,
    ProfileEntryType,
    ProfileSource,
    ProfileVerification,
    TaskStatus,
)
from zhiyin_kernel.errors import ResourceNotFound, DuplicateResource, InvalidRequest
from zhiyin_kernel.identity import UserAccount
from zhiyin_infrastructure.postgres.database import PostgresDatabase

logger = logging.getLogger(__name__)


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


def _optional_enum(enum_type: Any, value: Any) -> Any:
    """数据库里的可空枚举列 → 内核枚举；不认识的旧值按「未记录」处理。"""
    if value in (None, ""):
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _profile_field_row(row: Any) -> ProfileField:
    """画像字段行 → 内核记录（老库缺列时按默认值兜住）。

    新列对老数据是可空的：缺少类别时读成 None，由词表在展示/取数时按键推导；
    缺少核实状态时读成 None（来源仍然在，界面可以说清“从哪儿来”）。
    """
    values = row
    try:
        attributes = _load_value(values["attributes"]) or {}
    except (KeyError, IndexError):
        attributes = {}
    return ProfileField(
        key=values["key"],
        label=values["label"] or "",
        value=_load_value(values["value"]),
        confidence=values["confidence"],
        source=values["source"],
        evidence=_load_value(values["evidence"]) or [],
        updated_at=values["updated_at"],
        entry_type=_optional_enum(ProfileEntryType, _row_get(values, "entry_type")),
        attributes=attributes if isinstance(attributes, dict) else {},
        verification=_optional_enum(ProfileVerification, _row_get(values, "verification")),
        status=_optional_enum(ProfileEntryStatus, _row_get(values, "status"))
        or ProfileEntryStatus.ACTIVE,
        origin_ref=_row_get(values, "origin_ref") or "",
        valid_from=_row_get(values, "valid_from"),
        valid_to=_row_get(values, "valid_to"),
        event_at=_row_get(values, "event_at"),
        entry_version=int(_row_get(values, "entry_version") or 1),
        superseded_by=_row_get(values, "superseded_by") or "",
    )


def _row_get(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _profile_clue_row(row: Any) -> ProfileClue:
    """线索行 → 内核记录。来源/状态枚举不认识的旧值按「待验证」兜底。"""
    try:
        source = ProfileSource(row["source"])
    except ValueError:
        source = ProfileSource.ASSESSMENT
    return ProfileClue(
        id=row["id"],
        user_id=row["user_id"],
        session_id=row["session_id"] or "",
        text=row["text"],
        evidence=_load_value(row["evidence"]) or [],
        field_keys=_load_value(row["field_keys"]) or [],
        source=source,
        status=_optional_enum(ProfileClueStatus, row["status"]) or ProfileClueStatus.PROPOSED,
        invalidated_reason=row["invalidated_reason"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _profile_revision_row(row: Any) -> ProfileFieldRevision:
    """历史/冲突行 → 内核记录；未知枚举按「历史版本」兜底，不让一行坏数据拖垮画像。"""
    try:
        source = ProfileSource(row["source"])
    except ValueError:
        source = ProfileSource.CONVERSATION
    return ProfileFieldRevision(
        id=row["id"],
        user_id=row["user_id"],
        key=row["key"],
        label=row["label"] or "",
        value=_load_value(row["value"]),
        attributes=_load_value(row["attributes"]) or {},
        confidence=row["confidence"],
        source=source,
        verification=_optional_enum(ProfileVerification, row["verification"]),
        status=_optional_enum(ProfileEntryStatus, row["status"]) or ProfileEntryStatus.SUPERSEDED,
        evidence=_load_value(row["evidence"]) or [],
        origin_ref=row["origin_ref"] or "",
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        event_at=row["event_at"],
        entry_version=row["entry_version"] or 1,
        created_at=row["created_at"],
        replaced_at=row["replaced_at"],
        change_reason=row["change_reason"] or "",
    )


def _assemble_profile(
    user_id: str,
    head_row: Any,
    fields: list[ProfileField],
    gaps: list[ProfileGap],
    clues: list[ProfileClue] | None = None,
    conflicts: list[ProfileFieldRevision] | None = None,
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
        if not fields and not gaps and not clues and not conflicts:
            return None
        stamps = [field.updated_at for field in fields]
        if clues:
            stamps.extend(clue.updated_at for clue in clues)
        if conflicts:
            stamps.extend(item.created_at for item in conflicts)
        return Profile(
            id=f"profile-{user_id}",
            user_id=user_id,
            fields=fields,
            gaps=gaps,
            clues=clues or [],
            conflicts=conflicts or [],
            updated_at=max(stamps) if stamps else _now(),
        )
    return Profile(
        id=head_row["profile_id"],
        user_id=user_id,
        version=head_row["version"],
        updated_at=head_row["updated_at"],
        fields=fields,
        gaps=gaps,
        clues=clues or [],
        conflicts=conflicts or [],
    )


class PostgresProfileRepository(ProfileRepository):
    def transaction(self):
        return self._db.transaction()

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
        try:
            clues = await self.list_clues(user_id)
        except Exception:  # noqa: BLE001 - 老库还没跑迁移建表时，画像主体仍要能读
            # 为什么要吞这一处：线索是画像的旁路信息，读不到它不该让整个画像页
            # 变成 500。表由启动迁移创建，正常路径下这里不会走到。
            logger.warning("读取待验证线索失败，按空列表处理（user=%s）", user_id, exc_info=True)
            clues = []
        try:
            conflicts = await self.list_revisions(user_id, status=["conflict"])
        except Exception:  # noqa: BLE001 - 同上：版本表还没建时主画像仍可读
            logger.warning("读取画像冲突提案失败，按空列表处理（user=%s）", user_id, exc_info=True)
            conflicts = []
        return _assemble_profile(
            user_id,
            profile_row,
            await self.list_fields(user_id),
            await self.list_gaps(user_id),
            clues,
            conflicts,
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
                            (user_id, key, label, value, confidence, source, evidence, updated_at,
                             entry_type, attributes, verification, status, origin_ref,
                             valid_from, valid_to, event_at, entry_version, superseded_by)
                        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb, $8,
                                $9, $10::jsonb, $11, $12, $13, $14, $15, $16, $17, $18)
                        """,
                        stored.user_id,
                        field.key,
                        field.label,
                        _dump_value(field.value),
                        field.confidence,
                        field.source.value,
                        _dump_value(field.evidence),
                        field.updated_at,
                        field.entry_type.value if field.entry_type else None,
                        _dump_value(field.attributes),
                        field.verification.value if field.verification else None,
                        field.status.value,
                        field.origin_ref,
                        field.valid_from,
                        field.valid_to,
                        field.event_at,
                        field.entry_version,
                        field.superseded_by,
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
                # 线索与字段同一次整体保存：内存仓储里 clues 本来就在 Profile 上，
                # 这里漏掉会出现「内存测得通、换 Postgres 就丢」的差异。
                await connection.execute(
                    "DELETE FROM biz_profile_clue WHERE user_id = $1", stored.user_id
                )
                for clue in stored.clues:
                    await connection.execute(
                        """
                        INSERT INTO biz_profile_clue
                            (id, user_id, session_id, text, evidence, field_keys,
                             source, status, invalidated_reason, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb,
                                $7, $8, $9, $10, $11)
                        """,
                        clue.id,
                        stored.user_id,
                        clue.session_id,
                        clue.text,
                        _dump_value(clue.evidence),
                        _dump_value(clue.field_keys),
                        clue.source.value,
                        clue.status.value,
                        clue.invalidated_reason,
                        clue.created_at,
                        clue.updated_at,
                    )
        return stored

    async def upsert_field(self, user_id: str, field: ProfileField, *, expected_updated_at: datetime | None = None, check_version: bool = False) -> ProfileField:
        incoming = field.model_copy(deep=True)
        incoming.updated_at = _now()
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            row = await connection.fetchrow("SELECT * FROM biz_profile_field WHERE user_id=$1 AND key=$2", user_id, field.key)
            parent_stamp = await connection.fetchval("SELECT updated_at FROM biz_profile WHERE user_id=$1", user_id)
            incoming.updated_at = max(incoming.updated_at,
                (row["updated_at"] + timedelta(microseconds=1)) if row else incoming.updated_at,
                parent_stamp + timedelta(microseconds=1) if parent_stamp else incoming.updated_at)
            if check_version:
                if (
                    row
                    and _load_value(row["value"]) == field.value
                    and row["source"] == field.source.value
                    and (_load_value(_row_get(row, "attributes")) or {}) == field.attributes
                ):
                    return _profile_field_row(row)
                if (row["updated_at"] if row else None) != expected_updated_at:
                    raise DuplicateResource("这项画像已更新，你的输入仍保留，请核对最新信息后再保存。")
            await connection.execute(
                """
                INSERT INTO biz_profile (user_id, profile_id, version, updated_at)
                VALUES ($1, $2, 1, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                    version = biz_profile.version + 1,
                    updated_at = GREATEST(biz_profile.updated_at + INTERVAL '1 microsecond', EXCLUDED.updated_at)
                """,
                user_id,
                _new_id("prf"),
                incoming.updated_at,
            )
            await connection.execute(
                """
                INSERT INTO biz_profile_field
                    (user_id, key, label, value, confidence, source, evidence, updated_at,
                     entry_type, attributes, verification, status, origin_ref,
                     valid_from, valid_to, event_at, entry_version, superseded_by)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb, $8,
                        $9, $10::jsonb, $11, $12, $13, $14, $15, $16, $17, $18)
                ON CONFLICT (user_id, key) DO UPDATE SET
                    label = EXCLUDED.label,
                    value = EXCLUDED.value,
                    confidence = EXCLUDED.confidence,
                    source = EXCLUDED.source,
                    evidence = EXCLUDED.evidence,
                    updated_at = EXCLUDED.updated_at,
                    entry_type = EXCLUDED.entry_type,
                    attributes = EXCLUDED.attributes,
                    verification = EXCLUDED.verification,
                    status = EXCLUDED.status,
                    origin_ref = EXCLUDED.origin_ref,
                    valid_from = EXCLUDED.valid_from,
                    valid_to = EXCLUDED.valid_to,
                    event_at = EXCLUDED.event_at,
                    entry_version = EXCLUDED.entry_version,
                    superseded_by = EXCLUDED.superseded_by
                """,
                user_id,
                incoming.key,
                incoming.label,
                _dump_value(incoming.value),
                incoming.confidence,
                incoming.source.value,
                _dump_value(incoming.evidence),
                incoming.updated_at,
                incoming.entry_type.value if incoming.entry_type else None,
                _dump_value(incoming.attributes),
                incoming.verification.value if incoming.verification else None,
                incoming.status.value,
                incoming.origin_ref,
                incoming.valid_from,
                incoming.valid_to,
                incoming.event_at,
                incoming.entry_version,
                incoming.superseded_by,
            )
        return incoming

    async def delete_field(self, user_id: str, key: str, *, expected_updated_at: datetime | None = None, check_version: bool = False) -> None:
        """删掉一个画像字段，并把画像版本 +1。

        版本要动：采集清单与气泡编排都按"画像变过"重算，
        删字段如果不动版本，界面上会继续显示那份已经作废的结论。
        """
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            if check_version:
                current = await connection.fetchrow("SELECT updated_at FROM biz_profile_field WHERE user_id=$1 AND key=$2", user_id, key)
                if (current["updated_at"] if current else None) != expected_updated_at:
                    raise DuplicateResource("这项画像已更新，请核对后再删除。")
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
                    updated_at = GREATEST(biz_profile.updated_at + INTERVAL '1 microsecond', EXCLUDED.updated_at)
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
            SELECT key, label, value, confidence, source, evidence, updated_at,
                   entry_type, attributes, verification, status, origin_ref,
                   valid_from, valid_to, event_at, entry_version, superseded_by
            FROM biz_profile_field
            WHERE user_id = $1
              AND ($2::text[] IS NULL OR key = ANY($2::text[]))
            ORDER BY updated_at ASC
            """,
            user_id,
            list(keys) if keys else None,
        )
        return [_profile_field_row(row) for row in rows]

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
            await connection.execute("DELETE FROM biz_profile_gap WHERE user_id = $1", user_id)
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

    async def list_clues(self, user_id: str) -> list[ProfileClue]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, session_id, text, evidence, field_keys,
                   source, status, invalidated_reason, created_at, updated_at
            FROM biz_profile_clue
            WHERE user_id = $1
            ORDER BY created_at ASC, id ASC
            """,
            user_id,
        )
        return [_profile_clue_row(row) for row in rows]

    async def replace_session_clues(
        self, user_id: str, session_id: str, clues: list[ProfileClue]
    ) -> None:
        """同一 session 的线索整体替换：先删这一次会话的旧线索，再写这一批。

        不逐条 upsert：重跑一次分析应该得到**那一次**的结果，而不是把新旧线索
        叠在一起 —— 重复出现会被误读成「反复验证过」（设计第 3.2 节）。
        """
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            deleted = _affected(
                await connection.execute(
                    "DELETE FROM biz_profile_clue WHERE user_id = $1 AND session_id = $2",
                    user_id,
                    session_id,
                )
            )
            if not clues and not deleted:
                return
            for clue in clues:
                await connection.execute(
                    """
                    INSERT INTO biz_profile_clue
                        (id, user_id, session_id, text, evidence, field_keys,
                         source, status, invalidated_reason, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb,
                            $7, $8, $9, $10, $11)
                    """,
                    clue.id,
                    user_id,
                    session_id,
                    clue.text,
                    _dump_value(clue.evidence),
                    _dump_value(clue.field_keys),
                    clue.source.value,
                    clue.status.value,
                    clue.invalidated_reason,
                    clue.created_at,
                    clue.updated_at,
                )
            await self._touch_profile(connection, user_id)

    async def invalidate_clues(
        self, user_id: str, field_keys: list[str], reason: str
    ) -> int:
        keys = [str(key).strip() for key in field_keys if str(key).strip()]
        if not keys:
            return 0
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            result = await connection.execute(
                """
                UPDATE biz_profile_clue
                SET status = 'invalid',
                    invalidated_reason = $3,
                    updated_at = $4
                WHERE user_id = $1
                  AND status = 'proposed'
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements_text(field_keys) AS k(key)
                      WHERE k.key = ANY($2::text[])
                  )
                """,
                user_id,
                keys,
                reason or "",
                _now(),
            )
            count = _affected(result)
            if count:
                await self._touch_profile(connection, user_id)
            return count

    async def append_revision(
        self, user_id: str, revision: ProfileFieldRevision
    ) -> ProfileFieldRevision:
        """追加历史版本/冲突提案；不触碰 biz_profile_field 的当前值。"""
        stored = revision.model_copy(deep=True)
        if not stored.id:
            stored.id = _new_id("rev")
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            await connection.execute(
                """
                INSERT INTO biz_profile_field_revision
                    (id, user_id, key, label, value, attributes, confidence, source,
                     verification, status, evidence, origin_ref, valid_from, valid_to,
                     event_at, entry_version, created_at, replaced_at, change_reason)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8,
                        $9, $10, $11::jsonb, $12, $13, $14, $15, $16, $17, $18, $19)
                """,
                stored.id,
                user_id,
                stored.key,
                stored.label,
                _dump_value(stored.value),
                _dump_value(stored.attributes),
                stored.confidence,
                stored.source.value,
                stored.verification.value if stored.verification else None,
                stored.status.value,
                _dump_value(stored.evidence),
                stored.origin_ref,
                stored.valid_from,
                stored.valid_to,
                stored.event_at,
                stored.entry_version,
                stored.created_at,
                stored.replaced_at,
                stored.change_reason,
            )
            if stored.status is ProfileEntryStatus.CONFLICT:
                await self._touch_profile(connection, user_id)
        return stored

    async def list_revisions(
        self,
        user_id: str,
        key: Optional[str] = None,
        *,
        status: Optional[Sequence[str]] = None,
    ) -> list[ProfileFieldRevision]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, key, label, value, attributes, confidence, source,
                   verification, status, evidence, origin_ref, valid_from, valid_to,
                   event_at, entry_version, created_at, replaced_at, change_reason
            FROM biz_profile_field_revision
            WHERE user_id = $1
              AND ($2::text IS NULL OR key = $2)
              AND ($3::text[] IS NULL OR status = ANY($3::text[]))
            ORDER BY created_at ASC, id ASC
            """,
            user_id,
            key,
            list(status) if status else None,
        )
        return [_profile_revision_row(row) for row in rows]

    async def update_revision_status(
        self,
        user_id: str,
        revision_id: str,
        *,
        status: str,
        replaced_at: Optional[datetime] = None,
        change_reason: str = "",
    ) -> None:
        async with self._db.transaction() as connection:
            await _lock(connection, f"profile:{user_id}")
            await connection.execute(
                """
                UPDATE biz_profile_field_revision
                SET status = $3, replaced_at = $4,
                    change_reason = CASE WHEN $5 = '' THEN change_reason ELSE $5 END
                WHERE user_id = $1 AND id = $2
                """,
                user_id,
                revision_id,
                status,
                replaced_at or _now(),
                change_reason or "",
            )
            await self._touch_profile(connection, user_id)

    async def _touch_profile(self, connection: Any, user_id: str) -> None:
        """画像版本 +1：线索也是画像的一部分，界面按整体版本判断要不要重读。"""
        await connection.execute(
            """
            INSERT INTO biz_profile (user_id, profile_id, version, updated_at)
            VALUES ($1, $2, 1, $3)
            ON CONFLICT (user_id) DO UPDATE SET
                version = biz_profile.version + 1,
                updated_at = GREATEST(biz_profile.updated_at + INTERVAL '1 microsecond', EXCLUDED.updated_at)
            """,
            user_id,
            _new_id("prf"),
            _now(),
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
                (id, user_id, task_id, role, text, loop_stage, agent_id,
                 client_msg_id, created_at, renderables, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb)
            """,
            stored.id,
            stored.user_id,
            stored.task_id or "",
            stored.role,
            stored.text,
            stored.loop_stage.value,
            stored.agent_id,
            stored.client_msg_id,
            stored.created_at,
            json.dumps(stored.renderables),
            json.dumps(stored.metadata),
        )
        return stored

    async def find_reply_by_client_msg_id(
        self, user_id: str, client_msg_id: str
    ) -> Optional[ConversationTurn]:
        if not client_msg_id:
            return None
        row = await self._db.fetchrow(
            """
            SELECT id, user_id, task_id, role, text, loop_stage, agent_id,
                   client_msg_id, created_at, renderables, metadata
            FROM biz_conversation_turn
            WHERE user_id = $1 AND client_msg_id = $2 AND role = 'agent'
            ORDER BY created_at DESC LIMIT 1
            """,
            user_id,
            client_msg_id,
        )
        return (
            ConversationTurn(
                id=row["id"],
                user_id=row["user_id"],
                task_id=row["task_id"] or None,
                role=row["role"],
                text=row["text"],
                loop_stage=LoopStage(row["loop_stage"]),
                agent_id=row["agent_id"],
                client_msg_id=row["client_msg_id"],
                metadata=json.loads(row["metadata"]) if isinstance(row.get("metadata"), str) else (row.get("metadata") or {}),
                created_at=row["created_at"],
                renderables=json.loads(row["renderables"])
                if isinstance(row["renderables"], str)
                else row["renderables"],
            )
            if row
            else None
        )

    async def list_by_task(
        self, user_id: str, task_id: str, *, limit: int = 200
    ) -> list[ConversationTurn]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, task_id, role, text, loop_stage, agent_id,
                   client_msg_id, created_at, renderables, metadata
            FROM (
                SELECT id, user_id, task_id, role, text, loop_stage, agent_id,
                       client_msg_id, created_at, renderables, metadata
                FROM biz_conversation_turn
                WHERE user_id = $1 AND task_id = $2
                ORDER BY created_at DESC, id DESC
                LIMIT $3
            ) AS recent_turns
            ORDER BY created_at ASC, id ASC
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
                client_msg_id=row["client_msg_id"],
                metadata=json.loads(row["metadata"]) if isinstance(row.get("metadata"), str) else (row.get("metadata") or {}),
                created_at=row["created_at"],
                renderables=json.loads(row["renderables"])
                if isinstance(row["renderables"], str)
                else row["renderables"],
            )
            for row in rows
        ]

    async def delete_by_task(self, user_id: str, task_id: str) -> int:
        result = await self._db.execute(
            "DELETE FROM biz_conversation_turn WHERE user_id = $1 AND task_id = $2",
            user_id,
            task_id or "",
        )
        # asyncpg 返回 "DELETE n"；解析不出来就返回 0（不影响主流程）。
        try:
            return int(str(result).split()[-1])
        except (ValueError, IndexError):
            return 0


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
    @asynccontextmanager
    async def write_lock(self, user_id: str):
        # Snapshot, profile summaries and outbox events share this transaction.
        async with self._db.transaction():
            await self._db.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", "academic:" + user_id)
            yield

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
        await self._db.execute("DELETE FROM biz_academic_snapshot WHERE user_id = $1", user_id)


class PostgresAssetRepository(AssetRepository):
    @asynccontextmanager
    async def write_lock(self, user_id):
        async with self._db.transaction():
            await self._db.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", "asset:" + user_id)
            yield

    def transaction(self):
        return self._db.transaction()

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

    async def mark_needs_recompute(
        self, user_id: str, asset_type: AssetType, *, reason: str
    ) -> Optional[AssetVersion]:
        async with self._db.transaction() as connection:
            await _lock(connection, f"asset_version:{user_id}:{asset_type.value}")
            row = await connection.fetchrow(
                """
                SELECT version, payload FROM biz_asset_version
                WHERE user_id = $1 AND asset_type = $2
                ORDER BY version DESC LIMIT 1
                """,
                user_id,
                asset_type.value,
            )
            if row is None:
                return None
            latest = _load(AssetVersion, row["payload"])
            marker = latest.model_copy(update={"needs_recompute": True, "recompute_reason": reason})
            # 原地更新**这一版**的 payload：不加行、不升版，正文一个字不动。
            await connection.execute(
                """
                UPDATE biz_asset_version SET payload = $3::jsonb
                WHERE user_id = $1 AND asset_type = $2 AND version = $4
                """,
                user_id,
                asset_type.value,
                _dump(marker),
                latest.version,
            )
        return marker

    async def get_report(self, user_id: str, version: Optional[int] = None) -> Optional[Report]:
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
            # Each saved report version owns its own content row. Returning an
            # older body for a missing version made the UI claim "V1" while
            # showing V0/V2; an unavailable historical body must stay unavailable.
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
                stored.version = max(stored.version, _load(Report, latest["payload"]).version + 1)
            # A report keeps one stable business id across versions (approvals
            # reference it), but each version needs its own content row. Using
            # model.id alone made V2 overwrite V1 in place, leaving V1 with a
            # version row and no body.
            await self._put_content(
                stored.user_id, "report", stored.version, stored, connection,
                record_id=f"{stored.id}:v{stored.version}",
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

    async def save_direction_plans(self, user_id: str, plans: list[DirectionPlan]) -> None:
        async with self._db.transaction() as connection:
            await self._delete_content(user_id, "direction_plan", connection)
            for sort_order, plan in enumerate(plans):
                stored = plan.model_copy(deep=True)
                if not stored.id:
                    stored.id = _new_id("plan")
                await self._put_content(
                    user_id,
                    "direction_plan",
                    0,
                    stored,
                    connection,
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
            await _lock(connection, f"action_plan:{user_id}")
            await self._delete_content(user_id, "action_plan", connection)
            await self._put_content(user_id, "action_plan", 0, stored, connection)
        return stored

    async def update_action_plan(self, user_id, change):
        async with self._db.transaction() as connection:
            await _lock(connection, f"action_plan:{user_id}")
            row = await connection.fetchrow(
                "SELECT payload FROM biz_asset_content WHERE user_id=$1 AND asset_type='action_plan' ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                user_id,
            )
            plan = _load(ActionPlan, row["payload"]) if row else None
            stored = change(plan)
            await self._delete_content(user_id, "action_plan", connection)
            await self._put_content(user_id, "action_plan", 0, stored, connection)
            return stored

    async def mark_task_done(self, user_id: str, task_id: str, *, done: bool = True) -> ActionPlan:
        def change(plan):
            if plan is None:
                raise ResourceNotFound("行动计划不存在")
            for phase in plan.phases:
                for task in phase.tasks:
                    if task_id in {task.id, f"{phase.name}:{task.text}", task.text}:
                        task.done = done
                        task.done_at = _now() if done else None
                        task.status = "completed" if done else "pending"
                        task.progress = 100 if done else 0
                        task.waiting_reason = ""
                        return plan
            raise ResourceNotFound("行动任务不存在")

        return await self.update_action_plan(user_id, change)

    async def _put_content(
        self,
        user_id: str,
        asset_type: str,
        version: int,
        model: Any,
        connection: Any = None,
        sort_order: int = 0,
        *,
        record_id: str | None = None,
    ) -> None:
        executor = connection or self._db
        status = await executor.execute(
            """
            INSERT INTO biz_asset_content
                (id, user_id, asset_type, version, sort_order, created_at, payload)
            VALUES ($1, $2, $3, $4, $5, NOW(), $6::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                payload = EXCLUDED.payload,
                version = EXCLUDED.version,
                sort_order = EXCLUDED.sort_order
            WHERE biz_asset_content.user_id = EXCLUDED.user_id AND biz_asset_content.asset_type = EXCLUDED.asset_type
            """,
            record_id or model.id,
            user_id,
            asset_type,
            version,
            sort_order,
            _dump(model),
        )

        if status.endswith(" 0"):
            raise InvalidRequest("资产标识冲突，请重新读取后再操作。")

    async def _delete_content(self, user_id: str, asset_type: str, connection: Any = None) -> None:
        executor = connection or self._db
        await executor.execute(
            "DELETE FROM biz_asset_content WHERE user_id = $1 AND asset_type = $2",
            user_id,
            asset_type,
        )


class PostgresTaskSessionRepository(TaskSessionRepository):
    def transaction(self):
        return self._db.transaction()

    def conversation_lock(self, user_id):
        return self._db.conversation_lock(user_id)

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

    async def update_stage(self, session_id: str, stage: LoopStage, lead_agent: str) -> TaskSession:
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

    async def rename(self, session_id: str, task_name: str) -> TaskSession:
        async with self._db.transaction() as connection:
            await _lock(connection, f"session:{session_id}")
            row = await connection.fetchrow(
                "SELECT payload FROM biz_task_session WHERE id = $1 FOR UPDATE",
                session_id,
            )
            if row is None:
                raise ResourceNotFound(f"任务会话不存在：{session_id}")
            session = _load(TaskSession, row["payload"])
            session.task_name = task_name
            session.updated_at = _now()
            await connection.execute(
                "UPDATE biz_task_session SET updated_at = $2, payload = $3::jsonb WHERE id = $1",
                session.id,
                session.updated_at,
                _dump(session),
            )
        return session

    async def delete(self, session_id: str) -> None:
        await self._db.execute("DELETE FROM biz_task_session WHERE id = $1", session_id)


class PostgresUserRepository(UserRepository):
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, database: PostgresDatabase) -> None:
        self._db = database

    async def get_by_id(self, user_id: str) -> Optional[UserAccount]:
        row = await self._db.fetchrow("SELECT payload FROM biz_user_account WHERE id = $1", user_id)
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
        # A login touch must not write back a stale role while an administrator
        # is revoking permissions. Update only the timestamp atomically.
        updated = await self._db.fetchval(
            "UPDATE biz_user_account SET payload=jsonb_set(payload,'{last_login_at}',$2::jsonb) WHERE id=$1 RETURNING id",
            user_id,
            json.dumps(at.isoformat()),
        )
        if updated is None:
            raise ResourceNotFound(f"用户不存在：{user_id}")


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

    async def list_all(self, user_id):
        rows = await self._db.fetch(
            "SELECT * FROM orc_notification WHERE user_id=$1 ORDER BY created_at DESC", user_id
        )
        result = []
        for row in rows:
            state = row["processing_status"]
            if state == "later" and row["snoozed_until"] and row["snoozed_until"] <= _now():
                state = "pending"
            elif state == "pending" and row["status"] == "read":
                state = "read"
            result.append(
                dict(
                    id=row["id"],
                    title=row["title"],
                    body=row["body"],
                    occurred_at=(row["sent_at"] or row["created_at"]).isoformat(),
                    channel=row["channel"],
                    action=_load_value(row["action"]) if row["action"] else None,
                    related_task_id=row["related_task_id"],
                    status=state,
                    snoozed_until=row["snoozed_until"].isoformat()
                    if row["snoozed_until"]
                    else None,
                )
            )
        return result

    async def set_state(self, user_id, message_id, status, snoozed_until=None):
        result = await self._db.execute(
            "UPDATE orc_notification SET processing_status=$3, snoozed_until=$4, status=$5 WHERE user_id=$1 AND id=$2",
            user_id,
            message_id,
            status,
            snoozed_until if status == "later" else None,
            "read" if status in {"read", "done"} else "sent",
        )
        return _affected(result) > 0

    async def list_pending(self, user_id: str) -> list[dict]:
        rows = await self._db.fetch(
            """
            SELECT id, user_id, channel, status, title, body, action,
                   related_task_id, created_at, sent_at
            FROM orc_notification
            WHERE user_id = $1 AND status <> 'read' AND (processing_status = 'pending' OR (processing_status = 'later' AND snoozed_until <= NOW()))
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
