"""成员 B 多副本部署的静态回归守卫。"""

from pathlib import Path

import pytest

from zhiyin_infrastructure.postgres.database import PostgresDatabase, get_database


ROOT = Path(__file__).resolve().parents[3]


def test_postgres_pool_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="min_size"):
        PostgresDatabase("postgresql://invalid/test", min_size=0, max_size=1)
    with pytest.raises(ValueError, match="max_size"):
        PostgresDatabase("postgresql://invalid/test", min_size=3, max_size=2)


def test_process_database_pool_keeps_first_explicit_configuration() -> None:
    dsn = "postgresql://pool-config-guard/test"
    database = get_database(dsn, min_size=1, max_size=5)

    assert get_database(dsn) is database
    with pytest.raises(RuntimeError, match="两组连接池配置"):
        get_database(dsn, min_size=1, max_size=10)


def test_perf_compose_has_scalable_api_and_single_background_service() -> None:
    compose = (ROOT / "docker-compose.perf.yml").read_text(encoding="utf-8")

    assert "zhiyin-flash:${ZHIYIN_IMAGE_TAG:-baseline-20260930}" in compose
    assert "zhiyin-flash-web:${ZHIYIN_WEB_IMAGE_TAG:-latest}" in compose
    assert 'ZHIYIN_RUN_IN_PROCESS_BACKGROUND: "0"' in compose
    assert "ZHIYIN_POSTGRES_POOL_MAX_SIZE" in compose
    assert 'command: ["python", "-m", "zhiyin_boot", "background"]' in compose
    assert "zhiyin-background:" in compose
    api_block = compose.split("  zhiyin-flash:", 1)[1].split(
        "  zhiyin-background:", 1
    )[0]
    assert "container_name:" not in api_block
    assert '"8000:8000"' not in api_block
    assert "expose:" in api_block


def test_nginx_keeps_sse_and_records_actual_upstream() -> None:
    nginx = (
        ROOT / "zhiyin-src" / "template" / "zhiyin-web" / "nginx.conf"
    ).read_text(encoding="utf-8")

    assert "resolver 127.0.0.11" in nginx
    assert "upstream_addr=$upstream_addr" in nginx
    assert "upstream_time=$upstream_response_time" in nginx
    assert "proxy_buffering off" in nginx
    assert "proxy_next_upstream_tries 2" in nginx
    assert "non_idempotent;" not in nginx


def test_litellm_overlay_is_internal_and_required_by_backends() -> None:
    compose = (ROOT / "docker-compose.litellm.yml").read_text(encoding="utf-8")

    assert "ghcr.io/berriai/litellm:v1.98.0" in compose
    assert "./deploy/litellm/.env.keys" in compose
    assert "./deploy/litellm/config.yaml:/app/config.yaml:ro" in compose
    assert "./deploy/litellm/validate-and-start.sh:/app/validate-and-start.sh:ro" in compose
    assert "./deploy/litellm/verify_load_balancing.py:/app/verify_load_balancing.py:ro" in compose
    assert "ZHIYIN_LLM_API_KEY must contain the internal LiteLLM key" in compose
    assert "http://127.0.0.1:4000/health/readiness" in compose
    assert "ports:" not in compose
    assert 'expose:\n      - "4000"' in compose
    assert compose.count("condition: service_healthy") == 2


def test_litellm_config_has_four_key_deployments_and_no_secret() -> None:
    config = (ROOT / "deploy" / "litellm" / "config.yaml").read_text(
        encoding="utf-8"
    )

    assert config.count("model_name: deepseek-flash") == 4
    assert config.count("model: openai/deepseek-flash") == 4
    assert config.count("api_base: https://api.deepseek.com") == 4
    for index in range(1, 5):
        assert f"id: deepseek-key-{index}" in config
        assert f"api_key: os.environ/DEEPSEEK_API_KEY_{index}" in config
    assert "routing_strategy: least-busy" in config
    assert "num_retries: 0" in config
    assert "turn_off_message_logging: true" in config
    assert "master_key: os.environ/LITELLM_MASTER_KEY" in config
    assert "sk-" not in config


def test_litellm_startup_guard_requires_distinct_secrets() -> None:
    guard = (ROOT / "deploy" / "litellm" / "validate-and-start.sh").read_text(
        encoding="utf-8"
    )

    for index in range(1, 5):
        assert f"DEEPSEEK_API_KEY_{index}" in guard
    assert "values must be distinct" in guard
    assert "LITELLM_MASTER_KEY must start with sk-" in guard
    assert 'exec litellm "$@"' in guard


def test_litellm_verifier_checks_all_four_deployments_without_provider_keys() -> None:
    verifier = (
        ROOT / "deploy" / "litellm" / "verify_load_balancing.py"
    ).read_text(encoding="utf-8")

    assert "REQUEST_COUNT = 20" in verifier
    assert "CONCURRENCY = 8" in verifier
    assert 'os.getenv("LITELLM_MASTER_KEY"' in verifier
    assert "x-litellm-model-id" in verifier
    assert "len(deployments) != 4" in verifier
    assert "DEEPSEEK_API_KEY_" not in verifier
