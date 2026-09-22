"""PostgreSQL 连接池与表结构初始化。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import asyncpg

from zhiyin_infrastructure.postgres.schema import SCHEMA_SQL


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
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()

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
        pool = await self.pool()
        return await pool.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        pool = await self.pool()
        return await pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        pool = await self.pool()
        return await pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        pool = await self.pool()
        return await pool.fetchval(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """获取一个带事务的连接，供跨语句一致性写入使用。"""
        pool = await self.pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                yield connection

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


_DATABASES: dict[str, PostgresDatabase] = {}


def get_database(dsn: str) -> PostgresDatabase:
    """按 DSN 复用连接池，避免同一进程重复建池。"""
    database = _DATABASES.get(dsn)
    if database is None:
        database = PostgresDatabase(dsn)
        _DATABASES[dsn] = database
    return database


__all__ = ["PostgresDatabase", "get_database"]
