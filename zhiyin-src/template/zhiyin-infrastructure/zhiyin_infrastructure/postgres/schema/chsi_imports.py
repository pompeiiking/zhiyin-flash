DDL = """
CREATE TABLE IF NOT EXISTS biz_chsi_pdf_import (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','committed')),
    expires_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    receipt JSONB,
    imported_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_chsi_pdf_expiry
    ON biz_chsi_pdf_import(expires_at) WHERE status='pending';
"""
