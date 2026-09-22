"""编排运行态表：事件、调度、通知、工作流与智能体调用审计。"""

DDL = """
CREATE TABLE IF NOT EXISTS orc_event_outbox (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_orc_event_outbox_status
    ON orc_event_outbox (status, available_at);

CREATE TABLE IF NOT EXISTS orc_schedule_job (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orc_schedule_job_due
    ON orc_schedule_job (status, run_at);

CREATE TABLE IF NOT EXISTS orc_notification (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_orc_notification_user
    ON orc_notification (user_id, created_at DESC);
ALTER TABLE orc_notification
    ADD COLUMN IF NOT EXISTS action JSONB;
ALTER TABLE orc_notification
    ADD COLUMN IF NOT EXISTS related_task_id TEXT;

-- 工作流运行态、智能体调用审计、事件投递明细这三类，第一期**没有实现**，
-- 所以这里没有建表语句。
--
-- 它们原本是"先把表建好、以后要用的时候就有"的写法。代价很实在：
-- 一张 0 行的表看起来像"这个能力已经有了"，于是没人去实现，也没人敢删；
-- 而真正的实现一旦开始，字段几乎一定会改。表跟着实现走，不走在实现前面。
--
-- 已经建过这三张表的库，靠下面三条收敛。
DROP TABLE IF EXISTS orc_workflow_run;
DROP TABLE IF EXISTS orc_agent_call_log;
DROP TABLE IF EXISTS orc_event_delivery;
"""

__all__ = ["DDL"]
