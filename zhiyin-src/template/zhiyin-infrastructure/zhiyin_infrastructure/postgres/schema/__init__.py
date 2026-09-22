"""PostgreSQL 分层 schema。

层次口径：
- infra_*：基础设施配置，如 AI 供应商 / 模型 / 路由；
- biz_*：用户画像、行为、会话、资产等业务数据；
- orc_*：事件、调度、通知、工作流等编排运行态；
- vec_*：pgvector 向量数据。
"""

from zhiyin_infrastructure.postgres.schema.business import DDL as BUSINESS_DDL
from zhiyin_infrastructure.postgres.schema.infrastructure import (
    DDL as INFRASTRUCTURE_DDL,
)
from zhiyin_infrastructure.postgres.schema.migrations import MIGRATION_SQL
from zhiyin_infrastructure.postgres.schema.orchestration import (
    DDL as ORCHESTRATION_DDL,
)
from zhiyin_infrastructure.postgres.schema.vector import DDL as VECTOR_DDL

# 顺序即语义：**先建表、后补列**。
# 增量补丁拼在最后，所以空库（建表即当前形状）与老库（补上缺的列）跑同一段 SQL，
# 应用启动、迁移导入、测试三条路径也都自动带上它 —— 不会有"某条路径忘了升级库"。
SCHEMA_SQL = "\n".join(
    [
        "CREATE EXTENSION IF NOT EXISTS vector;",
        INFRASTRUCTURE_DDL,
        BUSINESS_DDL,
        ORCHESTRATION_DDL,
        VECTOR_DDL,
        MIGRATION_SQL,
    ]
)

__all__ = ["MIGRATION_SQL", "SCHEMA_SQL"]
