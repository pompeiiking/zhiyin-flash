"""基础设施层表：AI 供应商、模型、路由与运行时配置。"""

DDL = """
CREATE TABLE IF NOT EXISTS infra_ai_provider (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    protocol TEXT NOT NULL,
    base_url TEXT NOT NULL DEFAULT '',
    api_key_env TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS infra_ai_model (
    id TEXT PRIMARY KEY,
    provider_code TEXT NOT NULL REFERENCES infra_ai_provider(code) ON DELETE CASCADE,
    model_code TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    capability TEXT NOT NULL DEFAULT 'chat',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_code, model_code)
);

CREATE TABLE IF NOT EXISTS infra_ai_route (
    id TEXT PRIMARY KEY,
    scene TEXT NOT NULL,
    provider_code TEXT NOT NULL,
    model_code TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (scene, provider_code, model_code)
);

-- 两列删掉的原因各自不同，都不是"暂时没用"：
--   · `infra_ai_model.default_params`：模型级默认参数。温度现在已经跟提示词走
--     （见 `ai_prompt_template.params`），这一列从建起就没被任何一次调用读过，
--     留着只会让"温度到底谁说了算"多出一个候选答案。
--   · `infra_ai_route.fallback_route_id`：降级路由。解析路径里从来没有 fallback
--     逻辑，而且按本项目的口径，配置缺失应当直接报错而不是悄悄换一个模型。
-- 老库里这两列还在，靠下面两条收敛。
ALTER TABLE infra_ai_model DROP COLUMN IF EXISTS default_params;
ALTER TABLE infra_ai_route DROP COLUMN IF EXISTS fallback_route_id;

CREATE TABLE IF NOT EXISTS infra_runtime_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    description TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS infra_feature_flag (
    code TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS infra_auth_credential (
    user_id TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    iterations INTEGER NOT NULL DEFAULT 390000,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS infra_auth_session (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_infra_auth_session_user
    ON infra_auth_session (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS infra_vector_sync_state (
    source_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── AI 区：读者是智能体引擎与编排策略，和"前端要下发的内容"不是一回事 ──
--
-- 分区判据是**谁读它**，不是"是不是配置"：
--   · 前端读（BFF 下发）  → 展示内容区，第一期收容在 biz_registry_item
--   · 引擎读（每次调用）  → 本区，独立成表，因为它的形状要能被数据库约束住
--   · 编排策略读（每次判定）→ 本区
--   · 业务读侧读（口径）  → 产品口径区，第一期同样收容在 biz_registry_item
--
-- 为什么本区不跟着收容进通用表：通用表把一切压成 JSONB payload，
-- 字段没有约束 —— layer 打错、归属写偏、参数键名写错，都要等到读的时候才炸。
-- 提示词与规则是"错了会静默变坏"的东西（模型照样回答，只是答得不对），
-- 所以在写入那一刻就该被拦下来。

CREATE TABLE IF NOT EXISTS ai_prompt_template (
    code TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'enabled',
    sort_order INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_prompt_lookup
    ON ai_prompt_template (status, layer, agent_id, stage, sort_order);

CREATE TABLE IF NOT EXISTS ai_routing_rule (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 100,
    match JSONB NOT NULL DEFAULT '[]'::jsonb,
    intent TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'enabled',
    note TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_routing_kind
    ON ai_routing_rule (kind, status, sort_order);

-- AI 任务的产出：**跨重启、跨实例的缓存**，不是"临时缓存"。
--
-- 8 个生成类任务（报告小结 / 维度解读 / 缺口追问 / 待办建议 / 匹配矩阵……）的正文
-- 此前缓存在进程内存里：重启就重算（模型是按量计费的），多实例各存一份
-- （同一个用户刷新两次可能拿到两份不同的生成）。
-- 形状是原始 JSON：产出本身是 `{data, citations, meta, rationale}` 信封，
-- 拆成列会逼着这张表去认识每个任务的内部形状。
CREATE TABLE IF NOT EXISTS ai_task_result (
    user_id TEXT NOT NULL,
    task_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, task_key)
);
CREATE INDEX IF NOT EXISTS idx_ai_task_result_user
    ON ai_task_result (user_id, updated_at DESC);
"""

__all__ = ["DDL"]
