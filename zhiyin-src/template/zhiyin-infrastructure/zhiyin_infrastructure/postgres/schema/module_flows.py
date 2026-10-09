"""Workflow definitions and immutable published versions; durable run receipts."""
DDL = """
CREATE TABLE IF NOT EXISTS biz_module_runtime_revision (
    id INTEGER PRIMARY KEY CHECK (id=1), active_revision TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO biz_module_runtime_revision(id,active_revision) VALUES(1,'') ON CONFLICT(id) DO NOTHING;
CREATE TABLE IF NOT EXISTS biz_module_workflow (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, owner TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1, definition JSONB NOT NULL,
    published_revision INTEGER, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS biz_module_workflow_version (
    workflow_id TEXT NOT NULL REFERENCES biz_module_workflow(id), revision INTEGER NOT NULL,
    definition JSONB NOT NULL, published_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(workflow_id,revision)
);
CREATE TABLE IF NOT EXISTS biz_module_workflow_run (
    id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES biz_module_workflow(id),
    revision INTEGER NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL,
    input_digest TEXT NOT NULL, result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workflow_id,actor,request_id)
);
"""
