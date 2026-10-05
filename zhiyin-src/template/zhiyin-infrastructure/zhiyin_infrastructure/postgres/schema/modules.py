"""Additive tables for module policy and durable release management."""
DDL = """
CREATE TABLE IF NOT EXISTS biz_module_policy (
    module_id TEXT PRIMARY KEY, payload JSONB NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
    updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS biz_module_check (
    id TEXT PRIMARY KEY, actor TEXT NOT NULL, result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS biz_module_release (
    id TEXT PRIMARY KEY, commit_sha TEXT NOT NULL, kind TEXT NOT NULL,
    actor TEXT NOT NULL, request_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'requested',
    stage TEXT NOT NULL DEFAULT '', lease TEXT NOT NULL DEFAULT '', lease_until TIMESTAMPTZ,
    result JSONB NOT NULL DEFAULT '{}', events JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(actor, request_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_module_release
    ON biz_module_release ((true)) WHERE status IN ('queued', 'running');
CREATE TABLE IF NOT EXISTS biz_module_audit (
    id BIGSERIAL PRIMARY KEY, actor TEXT NOT NULL, subject TEXT NOT NULL,
    action TEXT NOT NULL, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
