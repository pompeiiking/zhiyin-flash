"""打包「可重新部署」的发布件。

口径
-----
发布件 = **源码 + 部署配置 + 迁移文件**，不是一堆编译产物。理由是这次的验收动作
就是"换一个干净环境重新部署一遍看整体是否正常"，那种场景下需要的是能整份重建的
东西（`docker compose build` 自己会把镜像做出来），而不是一个已经把构建结果固化的
黑盒。

发布件里**不带文档目录**（`docs/`）：部署要用的东西只有两处 —— `README.md`
说明这套代码怎么跑，`deploy/部署说明.md` 说明怎么上线。设计文档属于研发资产，
会随代码一起变，跟着每个部署包走只会让包越来越大、还容易与线上版本对不上。

迁移文件的**交付口径是不含用户表**：上线包只带策略、配置与向量，
新环境起来是一个干净的站。带 `--include-users` 的那一份只在"整机搬家"时用。

所以这里做三件事：

1. 按**白名单**收集要发的东西 —— 白名单而不是黑名单，因为黑名单漏掉一个目录的代价
   是把 `draft-frontend/`（165 MB）、`.venv/`（156 MB）这类本地垃圾发出去；
2. 顺手挡掉几类**必须随包走但很容易忘**的文件：`.env`、`Dockerfile`、
   `docker-compose.yml`、`deploy/migration.json`。缺任何一样都会让"重新部署"变成
   一次手工排查；
3. 打成 zip 并打印清单（大小 / 文件数 / 关键文件是否在位）。

用法
----
    python deploy/package_release.py                 # 输出到 release/职引-flash-deploy-<时间>.zip
    python deploy/package_release.py --name v1.0
"""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 发布件根目录下必须有的文件（漏一个，"重新部署"就跑不起来）
REQUIRED_FILES: tuple[str, ...] = (
    ".dockerignore",
    ".env",
    "Dockerfile",
    "docker-compose.yml",
    "deploy/migration.json",
)

#: 随包一起走的内容
TOP_FILES: tuple[str, ...] = (
    ".dockerignore",
    ".env.example",
    ".env",
    "Dockerfile",
    "docker-compose.yml",
    "README.md",
)
TOP_DIRS: tuple[str, ...] = (
    "deploy",
    # README 里引用的配图：发布件带 README，就得带它引用的图，否则包里的 README 是断图的。
    "assets",
    "zhiyin-src/template",
)

#: 一律不进包：本地环境、缓存、构建产物、审计产物
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".git",
        ".idea",
        ".vscode",
        "dist",
        "htmlcov",
    }
)
EXCLUDED_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo", ".egg-info", ".log", ".coverage")


def _keep(path: Path) -> bool:
    """单个文件是否进包。"""
    if any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in path.parts):
        return False
    if path.name.startswith(".coverage"):
        return False
    return not any(path.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)


def _files() -> list[Path]:
    collected: list[Path] = []
    for name in TOP_FILES:
        path = REPO_ROOT / name
        if path.is_file():
            collected.append(path)
    for name in TOP_DIRS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and _keep(path.relative_to(REPO_ROOT)):
                collected.append(path)
    return collected


def _preflight() -> list[str]:
    """发布件缺什么就报什么 —— 这些都不是"跑起来才发现"的错误。"""
    problems: list[str] = []

    # 先确认站在仓库根上。发布件解压出来以后结构长得和仓库很像
    # （`.env` / `Dockerfile` / `docker-compose.yml` / `deploy` 都在），
    # 在解压目录里再跑一次会**把发布件打进发布件**，而且一路"成功"。
    # 判据用一个只在仓库里才有的文件，避免靠目录名猜。
    if not (REPO_ROOT / "zhiyin-src" / "template" / "pyproject.toml").is_file():
        problems.append(
            f"{REPO_ROOT} 不像仓库根（找不到 zhiyin-src/template/pyproject.toml）；"
            "请在仓库根执行，不要在解压出来的发布件里执行"
        )
    for name in REQUIRED_FILES:
        if not (REPO_ROOT / name).is_file():
            problems.append(f"缺少 {name}")

    migration = REPO_ROOT / "deploy" / "migration.json"
    if migration.is_file() and migration.stat().st_size < 1024:
        problems.append("deploy/migration.json 只有几百字节，像是空导出，先重新导一次")

    env_file = REPO_ROOT / ".env"
    if env_file.is_file() and "ZHIYIN_AUTH_JWT_SECRET=" not in env_file.read_text(
        encoding="utf-8"
    ):
        problems.append(".env 里没有 ZHIYIN_AUTH_JWT_SECRET，compose 会拒绝启动")
    return problems


#: 出厂占位密钥：所有人都知道它，等于没有密钥。
PLACEHOLDER_SECRET = "change-me-in-production-32bytes-min"


def _harden_env(staging: Path) -> str:
    """给**发布件里的** `.env` 换一条随机 JWT 密钥。返回一行说明（没有改动则为空串）。

    为什么在打包这一步做：这条密钥保护的是库里全部数据（谁能伪造登录令牌），
    而它又是唯一刻意留在 env 里的密钥。发布件如果带着出厂占位串出门，
    就等于把签名密钥公开印在文档里 —— 装上就能被伪造会话，而**界面上看不出来**。

    只在"占位串 / 太短"时替换：部署方自己改过的那条不动（那是他的选择）。
    仓库里的 `.env` 也不动 —— 打包不该改开发环境。
    """
    env_path = staging / ".env"
    if not env_path.is_file():
        return ""
    text = env_path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^(\s*ZHIYIN_AUTH_JWT_SECRET\s*=\s*)(.*?)\s*$", text)
    if not match:
        return ""
    current = match.group(2).strip()
    if current and current != PLACEHOLDER_SECRET and len(current) >= 32:
        return ""  # 部署方/仓库自己给的那条，原样保留
    generated = secrets.token_hex(32)
    env_path.write_text(
        text[: match.start(2)] + generated + text[match.end(2) :], encoding="utf-8"
    )
    return f".env：已为本次发布件生成随机 ZHIYIN_AUTH_JWT_SECRET（{len(generated)} 字符）"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="package_release", description="职引 · 发布件打包")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "release", help="输出目录")
    parser.add_argument(
        "--name",
        default="职引-flash-deploy-" + datetime.now().strftime("%Y%m%d-%H%M"),
        help="发布件目录名（zip 同名）",
    )
    args = parser.parse_args(argv)

    problems = _preflight()
    if problems:
        print("发布件不完整，先补齐再打包：", file=sys.stderr)
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        print(
            "\n迁移文件这样生成：\n"
            "  python zhiyin-src/template/scripts/migrate_db.py export \\\n"
            "    --dsn postgresql://zhiyin:zhiyin@127.0.0.1:5432/zhiyin \\\n"
            "    --out deploy/migration.json --include-vectors",
            file=sys.stderr,
        )
        return 1

    staging = args.out / args.name
    if staging.exists():
        shutil.rmtree(staging)
    args.out.mkdir(parents=True, exist_ok=True)

    files = _files()
    for path in files:
        target = staging / path.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    note = _harden_env(staging)

    archive = args.out / f"{args.name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(args.out))

    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"发布件：{archive}")
    print(f"  文件 {len(files)} 个 · 压缩后 {size_mb:.1f} MB · 解压目录 {staging}")
    if note:
        print(f"  {note}")
    print("  关键文件：")
    for name in REQUIRED_FILES:
        # 用 ASCII 标记：Windows 控制台默认是 GBK，✓/✗ 会直接把打印炸掉
        # （zip 已经写好了，却因为最后一行报错让人以为打包失败）。
        mark = "OK " if (staging / name).is_file() else "缺"
        print(f"    {mark} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
