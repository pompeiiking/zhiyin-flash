"""Settings `.env` 自动加载守卫。

行为约定（见 zhiyin_boot/settings.py 的 `_load_dotenv`）：
1. `from_env()` 自动加载就近的 `.env`（cwd → 模板目录 → 仓库根，先找到先用）；
2. **已显式设置的环境变量优先**——容器/CI 用真实环境变量，本地裸跑用 `.env`；
3. 值两侧引号剥掉；`#` 注释与空行忽略。

回归背景：2026-09-21 联调时本地裸跑读不到仓库根 `.env`（那只给 docker-compose 用），
导致 DeepSeek 配置"配了但不生效"。这条守卫防止加载流程再被悄悄破坏。
"""

from __future__ import annotations

from pathlib import Path

from zhiyin_boot.settings import Settings


def _write_env(tmp_path: Path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    return env_file


def test_dotenv_is_loaded_from_cwd(tmp_path: Path, monkeypatch) -> None:
    _write_env(tmp_path, '# 注释\nZHIYIN_LLM_MODEL="deepseek-test"\n\nZHIYIN_USE_REDIS=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ZHIYIN_LLM_MODEL", raising=False)
    monkeypatch.delenv("ZHIYIN_USE_REDIS", raising=False)

    settings = Settings.from_env()

    assert settings.llm_model == "deepseek-test", ".env 的值必须被加载（含引号剥离）"
    assert settings.use_redis is True, ".env 的布尔值必须被加载"


def test_explicit_env_wins_over_dotenv(tmp_path: Path, monkeypatch) -> None:
    _write_env(tmp_path, "ZHIYIN_LLM_MODEL=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ZHIYIN_LLM_MODEL", "from-real-env")

    settings = Settings.from_env()

    assert settings.llm_model == "from-real-env", "显式环境变量必须优先于 .env"
