"""Prepare private local configuration and start the isolated developer workbench."""
from __future__ import annotations

import argparse
import json
import http.client
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request

from module_executor import read_env

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    private = ROOT / ".platform"
    private.mkdir(exist_ok=True)
    source = read_env(ROOT / ".env") if (ROOT / ".env").exists() else {}
    if not source.get("DASHSCOPE_API_KEY"):
        raise ValueError("请在根目录 .env 设置 DASHSCOPE_API_KEY")
    for name, api, web in (("workbench", 8014, 5174), ("staging", 8015, 5175)):
        target = private / f"{name}.env"
        if target.exists():
            continue
        values = {"PLATFORM_ENV": name, "PLATFORM_API_PORT": str(api), "PLATFORM_WEB_PORT": str(web),
                  "PLATFORM_REVISION": "workbench", "PLATFORM_DB_PASSWORD": secrets.token_hex(20),
                  "ZHIYIN_AUTH_JWT_SECRET": secrets.token_hex(32), "ZHIYIN_EXECUTOR_TOKEN": secrets.token_hex(32),
                  "DASHSCOPE_API_KEY": source["DASHSCOPE_API_KEY"],
                  "PLATFORM_ACCOUNT_PASSWORD": "123456", "PLATFORM_SMOKE_ACCOUNT": "admin"}
        target.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    config = private / "executor.json"
    if not config.exists():
        config.write_text(json.dumps({"repository": str(ROOT), "state_directory": str(private / "executor"),
            "compose_file": str(ROOT / "deploy" / "compose.platform.yml"),
            "workbench_env_file": str(private / "workbench.env"), "staging_env_file": str(private / "staging.env"),
            "workbench_url": "http://127.0.0.1:8014"}, indent=2), encoding="utf-8")
    return private


def start(private):
    env_file = private / "workbench.env"
    cmd = ["docker", "compose", "--project-directory", str(ROOT), "--env-file", str(env_file),
           "-p", "zhiyin-module-workbench", "-f", str(ROOT / "deploy" / "compose.platform.yml")]
    subprocess.run([*cmd, "up", "-d", "--build"], check=True)
    for _ in range(90):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8014/healthz", timeout=5) as response:
                if json.load(response)["status"] == "ok":
                    break
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError("工作台启动检查失败，请检查独立环境容器日志")
    password = read_env(env_file)["PLATFORM_ACCOUNT_PASSWORD"]
    for account, role in (("admin", "admin"), ("module_developer", "developer"), ("module_student", "student")):
        result = subprocess.run([*cmd, "exec", "-T", "-e", "PLATFORM_ACCOUNT_PASSWORD", "api", "python",
                        "scripts/module_admin.py", account, "--role", role, "--seed"], capture_output=True, text=True,
                        env={**os.environ, "PLATFORM_ACCOUNT_PASSWORD": password})
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr).replace(password, "[REDACTED]"))
        print(result.stdout.strip())
    print("Workbench: http://127.0.0.1:5174/developer ; administrator: admin")
    print(f"Private password: PLATFORM_ACCOUNT_PASSWORD in {env_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    private = prepare()
    if not args.prepare_only:
        start(private)
    print(f"Configuration ready: {private}")
