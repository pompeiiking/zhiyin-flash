"""pgvector 向量表。"""

DDL = """
CREATE TABLE IF NOT EXISTS vec_record (
    namespace TEXT NOT NULL,
    id TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding vector NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (namespace, id)
);
CREATE INDEX IF NOT EXISTS idx_vec_record_namespace_model
    ON vec_record (namespace, model);
"""

__all__ = ["DDL"]
