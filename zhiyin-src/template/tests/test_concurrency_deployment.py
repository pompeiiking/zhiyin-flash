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
