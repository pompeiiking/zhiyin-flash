"""PostgreSQL 连接池与表结构初始化。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator, Optional

import asyncpg

from zhiyin_infrastructure.postgres.schema import SCHEMA_SQL


class _ConnectionScope:
    """Serialize parallel tool queries on a pinned connection; transactions are reentrant."""

    def __init__(self, connection):
        self._raw = connection
        self._gate = asyncio.Lock()
        self._owner = None

    @asynccontextmanager
    async def _exclusive(self):
        task = asyncio.current_task()
        if self._owner is task:
            yield
            return
        async with self._gate:
            self._owner = task
            try:
                yield
            finally:
                self._owner = None

    def __getattr__(self, name):
        async def call(*args, **kwargs):
            async with self._exclusive():
                return await getattr(self._raw, name)(*args, **kwargs)
        return call

    @asynccontextmanager
    async def transaction(self):
        async with self._exclusive():
            async with self._raw.transaction():
                yield self


class PostgresDatabase:
    """懒加载的 asyncpg 连接池。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
    ) -> None:
        if min_size < 1:
            raise ValueError("PostgreSQL 连接池 min_size 必须大于等于 1")
        if max_size < min_size:
            raise ValueError("PostgreSQL 连接池 max_size 不能小于 min_size")
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()
        self._connection = ContextVar(f"db_connection_{id(self)}", default=None)

    async def _init_connection(self, connection: asyncpg.Connection) -> None:
        from pgvector.asyncpg import register_vector

        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(connection)

    async def pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is None:
                pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    init=self._init_connection,
                )
                try:
                    async with pool.acquire() as connection:
                        await connection.execute(SCHEMA_SQL)
                except Exception:
                    await pool.close()
                    raise
                self._pool = pool
        return self._pool

    async def execute(self, query: str, *args: Any) -> str:
        if self._connection.get() is not None:
            return await self._connection.get().execute(query, *args)
        pool = await self.pool()
        return await pool.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        if self._connection.get() is not None:
            return await self._connection.get().fetch(query, *args)
        pool = await self.pool()
        return await pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        if self._connection.get() is not None:
            return await self._connection.get().fetchrow(query, *args)
        pool = await self.pool()
        return await pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        if self._connection.get() is not None:
            return await self._connection.get().fetchval(query, *args)
        pool = await self.pool()
        return await pool.fetchval(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """获取一个带事务的连接，供跨语句一致性写入使用。"""
        existing = self._connection.get()
        if existing is not None:
            async with existing.transaction():
                yield existing
            return
        pool = await self.pool()
        async with pool.acquire() as connection:
            scoped = _ConnectionScope(connection)
            async with scoped.transaction():
                token = self._connection.set(scoped)
                try:
                    yield scoped
                finally:
                    self._connection.reset(token)

    @asynccontextmanager
    async def conversation_lock(self, user_id: str):
        """Serialize one account across processes without holding a SQL transaction during inference.

        Pin subsequent repository calls to this connection so even a one-slot pool
        cannot deadlock while an advisory lock is held. Waiters release their slot.
        """
        pool = await self.pool()
        while True:
            async with pool.acquire() as connection:
                locked = await connection.fetchval("SELECT pg_try_advisory_lock(hashtextextended($1, 0))", "conversation:" + user_id)
                if locked:
                    token = self._connection.set(_ConnectionScope(connection))
                    try:
                        yield
                    finally:
                        self._connection.reset(token)
                        await asyncio.shield(connection.execute("SELECT pg_advisory_unlock(hashtextextended($1, 0))", "conversation:" + user_id))
                    return
            await asyncio.sleep(0.05)

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


_DATABASES: dict[str, PostgresDatabase] = {}


def get_database(
    dsn: str,
    *,
    min_size: int | None = None,
    max_size: int | None = None,
) -> PostgresDatabase:
    """按 DSN 复用连接池，避免同一进程重复建池。

    装配入口第一次调用时显式传入池大小；后续仓储和网关只按 DSN
    取回同一个对象。如果同一进程尝试用冲突参数重新配置，立即报错，
    避免“配置写了但未生效”。
    """
    database = _DATABASES.get(dsn)
    if database is None:
        database = PostgresDatabase(
            dsn,
            min_size=1 if min_size is None else min_size,
            max_size=10 if max_size is None else max_size,
        )
        _DATABASES[dsn] = database
    elif min_size is not None or max_size is not None:
        requested_min = database._min_size if min_size is None else min_size
        requested_max = database._max_size if max_size is None else max_size
        if (requested_min, requested_max) != (
            database._min_size,
            database._max_size,
        ):
            raise RuntimeError(
                "同一 PostgreSQL DSN 在单进程内不能使用两组连接池配置"
            )
    return database


__all__ = ["PostgresDatabase", "get_database"]
