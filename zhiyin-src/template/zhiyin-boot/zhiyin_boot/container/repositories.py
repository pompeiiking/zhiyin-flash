"""Repository 与动态资源装配表。

业务数据使用 PostgreSQL；动态资源仍读 `data/registry/*.json`。
未启用 PostgreSQL 时保留本地内存实现，便于离线开发与测试。
"""

from __future__ import annotations

from typing import Any

from zhiyin_boot.settings import Settings


def build_repositories(settings: Settings) -> dict[str, Any]:
    """按配置装配 Repository。"""
    from zhiyin_infrastructure.local.repository import (
        InMemoryAiTaskResultRepository,
        InMemoryAssetRepository,
        InMemoryAcademicSnapshotRepository,
        InMemoryBehaviorRepository,
        InMemoryCalendarNodeRepository,
        InMemoryConversationMemoryRepository,
        InMemoryConversationTurnRepository,
        InMemoryNotificationRepository,
        InMemoryProfileRepository,
        InMemoryTaskSessionRepository,
        InMemoryTrackEventRepository,
        InMemoryUserRepository,
        InMemoryUserNoteRepository,
        LocalJsonRegistryRepository,
    )

    if settings.use_postgres:
        from zhiyin_infrastructure.postgres.database import get_database
        from zhiyin_infrastructure.postgres.repository import (
            PostgresAiTaskResultRepository,
            PostgresAssetRepository,
            PostgresAcademicSnapshotRepository,
            PostgresBehaviorRepository,
            PostgresCalendarNodeRepository,
            PostgresConversationMemoryRepository,
            PostgresConversationTurnRepository,
            PostgresNotificationRepository,
            PostgresProfileRepository,
            PostgresTaskSessionRepository,
            PostgresTrackEventRepository,
            PostgresUserRepository,
            PostgresUserNoteRepository,
        )
        from zhiyin_infrastructure.postgres.registry import PostgresRegistryRepository

        database = get_database(settings.postgres_dsn)
        return {
            "profiles": PostgresProfileRepository(database),
            "behaviors": PostgresBehaviorRepository(database),
            "memories": PostgresConversationMemoryRepository(database),
            "turns": PostgresConversationTurnRepository(database),
            "assets": PostgresAssetRepository(database),
            "sessions": PostgresTaskSessionRepository(database),
            "registry": PostgresRegistryRepository(
                database, settings.local_registry_dir
            ),
            "users": PostgresUserRepository(database),
            "notes": PostgresUserNoteRepository(database),
            "academic_records": PostgresAcademicSnapshotRepository(database),
            # 日历 / 跟踪时间线 / 通知读侧 / AI 任务产出：都曾经只活在进程内存里
            "calendar": PostgresCalendarNodeRepository(database),
            "track_events": PostgresTrackEventRepository(database),
            "notifications": PostgresNotificationRepository(database),
            "ai_task_results": PostgresAiTaskResultRepository(database),
        }

    return {
        "profiles": InMemoryProfileRepository(),
        "behaviors": InMemoryBehaviorRepository(),
        "memories": InMemoryConversationMemoryRepository(),
        "turns": InMemoryConversationTurnRepository(),
        "assets": InMemoryAssetRepository(),
        "sessions": InMemoryTaskSessionRepository(),
        "registry": LocalJsonRegistryRepository(settings.local_registry_dir),
        "users": InMemoryUserRepository(),
        "notes": InMemoryUserNoteRepository(),
        "academic_records": InMemoryAcademicSnapshotRepository(),
        "calendar": InMemoryCalendarNodeRepository(),
        "track_events": InMemoryTrackEventRepository(),
        "notifications": InMemoryNotificationRepository(),
        "ai_task_results": InMemoryAiTaskResultRepository(),
    }


def build_feature_flags(settings: Settings) -> Any:
    """功能开关。启用 PostgreSQL 时走数据库，否则读本地 JSON。"""
    if settings.use_postgres:
        from zhiyin_infrastructure.postgres.database import get_database
        from zhiyin_infrastructure.postgres.feature_flag import (
            PostgresFeatureFlagGateway,
        )

        return PostgresFeatureFlagGateway(
            get_database(settings.postgres_dsn), settings.local_registry_dir
        )

    from zhiyin_infrastructure.local.feature_flag import LocalFeatureFlagStore

    return LocalFeatureFlagStore(settings.local_registry_dir)


__all__ = ["build_feature_flags", "build_repositories"]
