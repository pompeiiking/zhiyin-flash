"""业务层表：用户、画像、行为、会话与资产。"""

DDL = """
CREATE TABLE IF NOT EXISTS biz_user_account (
    id TEXT PRIMARY KEY,
    phone TEXT UNIQUE,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS biz_profile (
    user_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS biz_profile_field (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    value JSONB NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_biz_profile_field_user
    ON biz_profile_field (user_id);

CREATE TABLE IF NOT EXISTS biz_profile_gap (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    suggested_next_action TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS biz_behavior_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_biz_behavior_user_time
    ON biz_behavior_log (user_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS biz_conversation_memory (
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    last_active_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (user_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_biz_memory_user_time
    ON biz_conversation_memory (user_id, last_active_at DESC);

-- 逐轮对话原文。
--
-- 与 biz_conversation_memory 分开：那张表存的是**累积摘要**（给模型续接用），
-- 答不了"这条会话发生过什么、他当时是怎么说的"。此前用户自己说的话一个字都没落库，
-- 会话列表点进去是空的 —— 那不是界面没做，是数据没存。
CREATE TABLE IF NOT EXISTS biz_conversation_turn (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    loop_stage TEXT NOT NULL DEFAULT 'collect',
    agent_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_biz_conversation_turn_task
    ON biz_conversation_turn (user_id, task_id, created_at ASC);

-- 用户自己写下的东西（自建待办 / 写下的目标）。
-- 单独一张表，不并进会话记忆：记忆里的 loop_stage 参与"现在走到哪一环节"的判断，
-- 掺进用户随手写的一条待办就会把阶段算歪。这里只存他的原话，给采集策略读线索。
CREATE TABLE IF NOT EXISTS biz_user_note (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'todo',
    text TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_biz_user_note_user_time
    ON biz_user_note (user_id, created_at DESC);

-- 学生自己导入的课表与成绩单（一份快照，按用户唯一）。
-- 存的是**导入的原文读出来的结果**：这里没有、也不该有任何凭据字段 ——
-- 数据是他自己带进来的，我们从没碰过他学校的账号。
CREATE TABLE IF NOT EXISTS biz_academic_snapshot (
    user_id TEXT PRIMARY KEY,
    school TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    term TEXT NOT NULL DEFAULT '',
    imported_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS biz_task_session (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_code TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_biz_task_session_user_status
    ON biz_task_session (user_id, task_code, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS biz_asset_version (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_biz_asset_version_user_type
    ON biz_asset_version (user_id, asset_type, version DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_biz_asset_version_user_type_version
    ON biz_asset_version (user_id, asset_type, version);

CREATE TABLE IF NOT EXISTS biz_asset_content (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_biz_asset_content_user_type
    ON biz_asset_content (user_id, asset_type, version DESC);
ALTER TABLE biz_asset_content
    ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;

-- 跟踪时间线与关键节点日历：**已经是持久化数据，不再是进程内登记**。
--
-- 它们此前只活在 `DefaultFunctionService` 的两个 dict 里，理由写在当时的注释里：
-- "表应该等真正要持久化的时候再建"。那一刻到了，因为它们本来就是用户可见的核心数据 ——
-- 重启一次就丢掉学生自己排进来的关键节点与教练的复盘时间线，不是"P0 形态"，是数据丢失。
-- 形态没变（`CalendarNode` / `TrackEvent` 仍是内核形状），变的是它落在哪。
CREATE TABLE IF NOT EXISTS biz_calendar_node (
    node_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    due_at TIMESTAMPTZ,
    source TEXT NOT NULL DEFAULT 'planner',
    related_task_text TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_biz_calendar_node_user_due
    ON biz_calendar_node (user_id, due_at ASC NULLS LAST);

CREATE TABLE IF NOT EXISTS biz_track_event (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    occurred_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ,
    related_task_id TEXT,
    related_stage TEXT
);
CREATE INDEX IF NOT EXISTS idx_biz_track_event_user_time
    ON biz_track_event (user_id, occurred_at DESC);

-- 成就**永久不落表**：设计上就是每次从行为日志实时推导（"只由行为日志驱动，防自嗨"）。
-- 落一张成就表等于给它开了第二个事实来源，越往后越对不上。
-- 早期误建过的库靠这一条收敛。
DROP TABLE IF EXISTS biz_achievement;

CREATE TABLE IF NOT EXISTS biz_registry_item (
    kind TEXT NOT NULL,
    code TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'enabled',
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (kind, code)
);
CREATE INDEX IF NOT EXISTS idx_biz_registry_kind
    ON biz_registry_item (kind, status, sort_order);

-- 收敛：`prompts` 与 `routing_rules` 两个类别一度被收容在这张通用表里，
-- 导入 `ai_prompt_template` / `ai_routing_rule` 之后把那一批清掉，
-- 免得同一份配置留下两份、读的时候不知道以哪份为准。
--
-- 它必须待在这里，不能跟着上面那段 AI 区的注释一起放进 infrastructure 的 DDL：
-- 整份 SCHEMA_SQL 的拼装顺序是 infra → business → orchestration → vector，
-- 而这张表是 business 建的。放在 infra 段里，在**空库**上会先于 CREATE 执行，
-- 报 `relation "biz_registry_item" does not exist` 并中断建表 ——
-- 服务在空库上根本起不来（tests/test_schema_order.py 守着这条）。
DELETE FROM biz_registry_item WHERE kind IN ('prompts', 'routing_rules');
"""

__all__ = ["DDL"]
