"""PostgreSQL + pgvector 基础设施实现。

PostgreSQL 承载结构化数据，pgvector 承载向量检索。
"""

from zhiyin_infrastructure.postgres.database import PostgresDatabase, get_database
from zhiyin_infrastructure.postgres.vector import PostgresVectorGateway

__all__ = ["PostgresDatabase", "PostgresVectorGateway", "get_database"]
