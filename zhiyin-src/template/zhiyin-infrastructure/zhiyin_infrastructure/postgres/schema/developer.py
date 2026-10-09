"""Additive developer project/version/acceptance metadata. Packages are immutable."""
DDL = """
CREATE TABLE IF NOT EXISTS biz_developer_project (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 owner TEXT NOT NULL, members JSONB NOT NULL DEFAULT '[]', trusted BOOLEAN NOT NULL DEFAULT false,
 auto_deploy BOOLEAN NOT NULL DEFAULT false, revision INTEGER NOT NULL DEFAULT 1,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS biz_developer_version (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES biz_developer_project(id),
 version TEXT NOT NULL, channel TEXT NOT NULL, base_version_id TEXT,
 base_commit TEXT NOT NULL, digest TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL,
 manifest JSONB NOT NULL, package BYTEA NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', stage TEXT NOT NULL DEFAULT 'queued',
 report JSONB NOT NULL DEFAULT '{}', events JSONB NOT NULL DEFAULT '[]',
 candidate_commit TEXT NOT NULL DEFAULT '', release_job_id TEXT NOT NULL DEFAULT '',
 lease TEXT NOT NULL DEFAULT '', lease_until TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(project_id,version), UNIQUE(actor,request_id)
);
-- Register the self-reference after both sides exist, including on repeat startup.
DO $$
BEGIN
 IF NOT EXISTS (
  SELECT 1 FROM pg_constraint
  WHERE conrelid = 'biz_developer_version'::regclass
    AND conname = 'biz_developer_version_base_version_id_fkey'
 ) THEN
  ALTER TABLE biz_developer_version
   ADD CONSTRAINT biz_developer_version_base_version_id_fkey
   FOREIGN KEY (base_version_id) REFERENCES biz_developer_version(id);
 END IF;
END $$;
CREATE INDEX IF NOT EXISTS developer_versions_queue ON biz_developer_version(status,created_at);
CREATE TABLE IF NOT EXISTS biz_developer_worker (
 id TEXT PRIMARY KEY, payload JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
