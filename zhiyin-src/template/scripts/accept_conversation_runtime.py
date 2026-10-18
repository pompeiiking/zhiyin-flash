"""Isolated DB/real-model smoke checks. Never print credentials or read student data."""
# ruff: noqa: E402
import asyncio
import copy
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from weakref import WeakValueDictionary

root = Path(__file__).resolve().parents[3]
(root / "output/agent-audit-20261019").mkdir(parents=True, exist_ok=True)
template = root / "zhiyin-src/template"
sys.path.insert(0, str(template))
for path in template.glob("zhiyin-*"):
    if path.is_dir():
        sys.path.insert(0, str(path))
sys.stdout.reconfigure(encoding="utf-8")

from zhiyin_boot import Settings, build_container
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_infrastructure.ai.router import AiModelRouter
from zhiyin_infrastructure.postgres.ai_config import PostgresAiConfigRepository
from zhiyin_infrastructure.postgres.database import PostgresDatabase
from zhiyin_infrastructure.postgres.repository import (
    PostgresTaskSessionRepository, PostgresConversationTurnRepository, PostgresConversationMemoryRepository,
    PostgresProfileRepository,
)
from zhiyin_business.services.memory import DefaultConversationMemoryService
from tests.test_conversation_asset_confirmation import setup

results = {}

async def main():
    import asyncpg
    settings = Settings.from_env()
    parsed = urlsplit(settings.postgres_dsn)
    host = parsed.hostname
    if host in {"postgres", "zhiyin-flash-postgres", "127.0.0.1", "localhost"}:
        credentials = parsed.netloc.rsplit("@", 1)[0] if "@" in parsed.netloc else ""
        address = (credentials + "@" if credentials else "") + "127.0.0.1:55432"
        dsn = urlunsplit(parsed._replace(netloc=address))
    else:
        raise RuntimeError("Smoke checks require the local development database")
    connection = await asyncpg.connect(dsn, timeout=5)
    schema = "conversation_audit_" + uuid4().hex[:12]
    databases = []
    try:
        # Resolve only configuration rows. No schema migration on the existing app DB.
        router = AiModelRouter(PostgresAiConfigRepository(connection,
            llm_base_url=settings.llm_base_url, llm_model=settings.llm_model,
            embedding_base_url=settings.embedding_base_url, embedding_model=settings.embedding_model))
        resolved = await router.resolve("llm")
        await connection.execute(f'CREATE SCHEMA "{schema}"')

        class IsolatedDatabase(PostgresDatabase):
            async def pool(self):
                if self._pool is None:
                    from zhiyin_infrastructure.postgres.schema import SCHEMA_SQL
                    self._pool = await asyncpg.create_pool(dsn, min_size=1, max_size=1,
                        server_settings={"search_path": f'"{schema}", public'}, init=self._init_connection)
                    async with self._pool.acquire() as conn:
                        assert await conn.fetchval("SELECT current_schema()") == schema
                        await conn.execute(SCHEMA_SQL)
                return self._pool
            async def _init_connection(self, conn):
                await super()._init_connection(conn)

        db1 = IsolatedDatabase(dsn, min_size=1, max_size=1)
        db2 = IsolatedDatabase(dsn, min_size=1, max_size=1)
        databases.extend([db1, db2])
        await db1.pool()
        # Already migrated by db1; avoid concurrent bootstrap in this smoke test.
        await db2.pool()

        c, engine, session = await setup()
        sessions = PostgresTaskSessionRepository(db1)
        await sessions.create(session)
        memories = DefaultConversationMemoryService(PostgresConversationMemoryRepository(db1), PostgresConversationTurnRepository(db1))
        c.orchestrator._sessions = sessions
        c.orchestrator._memories = memories
        other = copy.copy(c.orchestrator)
        other._sessions = PostgresTaskSessionRepository(db2)
        other._turn_locks = WeakValueDictionary()
        request = TurnRequest(user_id="u1", task_id=session.id, message="继续聊", client_msg_id="cross-worker")
        one, two = await asyncio.wait_for(asyncio.gather(c.orchestrator.handle_message(request), other.handle_message(request)), 20)
        assert one == two and len(engine.requests) == 1
        turns = await memories.list_turns("u1", session.id)
        assert len(turns) == 2 and turns[-1].metadata["result"]
        results["postgres_cross_worker_replay_single_slot_pool"] = "passed"
        async with db1.conversation_lock("parallel-tool-check"):
            values = await asyncio.gather(db1.fetchval("SELECT 1"), db1.fetchval("SELECT 2"))
            assert values == [1, 2]
        results["postgres_parallel_tool_queries"] = "passed"

        from zhiyin_business.services.profile import DefaultProfileService
        class BrokenBus:
            async def publish(self, event):
                raise RuntimeError("synthetic outbox failure")
        repo = PostgresProfileRepository(db1)
        profile = DefaultProfileService(repo, BrokenBus())
        try:
            await profile.update_field("rollback-user", "major", "计算机", confidence=1, source="conversation")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Synthetic failure was not raised")
        assert not await repo.list_fields("rollback-user")
        results["postgres_profile_outbox_rollback"] = "passed"
        await db1.execute("CREATE TABLE audit_calendar_marker (title TEXT)")
        class CalendarWriter:
            async def write_calendar_node(self, user_id, node):
                await db1.execute("INSERT INTO audit_calendar_marker(title) VALUES($1)", node.title)
        class BrokenAssetWriter:
            async def save_action_plan(self, *args, **kwargs):
                raise RuntimeError("synthetic plan failure")
        c.orchestrator._functions = CalendarWriter()
        c.orchestrator._assets = BrokenAssetWriter()
        try:
            await c.orchestrator._save_action_plan("u1", {"phases": [], "reminders": [{"title": "synthetic node"}]})
        except RuntimeError:
            pass
        else:
            raise AssertionError("Synthetic plan failure was not raised")
        assert await db1.fetchval("SELECT count(*) FROM audit_calendar_marker") == 0
        results["postgres_calendar_plan_rollback"] = "passed"

        if resolved is None:
            results["real_model"] = "unavailable: no configured route"
        else:
            real_settings = Settings(
                use_remote_llm=True, llm_api_key=resolved.api_key, llm_base_url=resolved.base_url,
                llm_model=resolved.model_code, env="test", local_data_dir=str(template / "data"),
                local_registry_dir=str(template / "data/registry"), local_knowledge_dir=str(template / "data/knowledge"),
                local_object_dir=str(root / "output/agent-audit-20261019/isolated-objects"),
            )
            # A Docker-only proxy may not be reachable from the host; record that boundary.
            if urlsplit(real_settings.llm_base_url).hostname in {"litellm", "zhiyin-litellm"}:
                results["real_model"] = "unavailable: model gateway is internal to Docker"
            else:
                real = build_container(real_settings)
                user = "audit_synthetic_" + uuid4().hex[:8]
                current = await real.orchestrator.enter_task(user, "free_chat")
                replies = []
                for message in [
                    "我是计算机专业大三，课程里用Python清洗过销售数据。我每周只有两小时，不考虑考研，也不要推荐付费课。先聊聊，给我两个找数据分析实习的准备建议，不要创建计划。",
                    "刚才的时间限制是什么？我说不考虑什么？请直接回答，不要再问我的专业。",
                    "不要把我的专业改为法学。请解释数据清洗和数据分析有什么区别，用两个小段落。",
                ]:
                    output = await real.orchestrator.handle_message(TurnRequest(user_id=user, task_id=current.id, message=message, client_msg_id=uuid4().hex))
                    replies.append({"message": message, "reply": [item.text for item in output.messages]})
                results["real_model"] = {"model": resolved.model_code, "turns": replies}
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        for database in databases:
            await database.aclose()
        # Only the newly generated, isolated schema is removed. No user tables are touched.
        await connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await connection.close()
        (root / "output/agent-audit-20261019/runtime-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

asyncio.run(main())
