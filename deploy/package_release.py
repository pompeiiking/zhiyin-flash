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

**发布件里不带任何密钥**（这一条比什么都重要）
------------------------------------------------
密钥是你的，不是拿到包的人的：

  · 迁移文件里的 `infra_ai_provider.config.api_key`（模型密钥）—— 打包时**抹掉**；
  · `.env` 里的 `ZHIYIN_AUTH_JWT_SECRET`（谁能伪造登录令牌就靠它）—— **重新生成一条**，
    带来的必然结果是"你的发布件签名的那套，和拿到包的人那一套互不通用"，这正是要的；
  · `.env` 里的 `ZHIYIN_SECURITY_KEY`（加密密钥）—— 同样重新生成；
  · `ZHIYIN_LLM_API_KEY` / `ZHIYIN_SEARCH_API_KEY` —— 留空，由部署方自己填。

所以**不要**在 `.env` 里预先填好自己的模型密钥：那会被清掉（这是刻意的），
部署方要按《部署说明》第一节填自己的那把。打包结束前还有一道**扫描**：
把成品 zip 逐文件找一遍密钥特征与本地已知密钥值，命中就拒绝出包。

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
import json
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

#: 发布件里**一律重新生成**的密钥：名字 → 生成方式。
#: 不区分"是不是占位串"，因为**仓库里的那条就是你自己的密钥** —— 一旦跟着包出去，
#: 谁拿到包就能伪造你那套环境的登录会话、解开你那套库里加密过的内容。
_REGENERATED_SECRETS: tuple[str, ...] = (
    "ZHIYIN_AUTH_JWT_SECRET",
    "ZHIYIN_SECURITY_KEY",
)

#: 发布件里**一律留空**、由部署方自己填的密钥。
_BLANKED_SECRETS: tuple[str, ...] = (
    "ZHIYIN_LLM_API_KEY",
    "ZHIYIN_SEARCH_API_KEY",
)


def _set_env_value(text: str, key: str, value: str, *, comment: str = "") -> tuple[str, bool]:
    """把 `.env` 里某个键改成 `value`（键不存在就追加）。返回（新文本, 是否改过）。"""
    match = re.search(rf"(?m)^(\s*{re.escape(key)}\s*=\s*)(.*?)\s*$", text)
    if match is None:
        block = f"\n{comment}\n{key}={value}\n" if comment else f"\n{key}={value}\n"
        return text + block, True
    current = match.group(2).strip()
    if current == value:
        return text, False
    return text[: match.start(2)] + value + text[match.end(2) :], True


def _sanitize_env(staging: Path) -> list[str]:
    """把发布件里的 `.env` 清一遍。返回逐条说明。

    三条口径（都是"宁可让部署方自己填一次，也不把你的密钥带出去"）：

      · JWT 签名密钥与加密密钥**重新生成** —— 这两条是你的，不能跟着包走；
        代价只是"你的那套与拿到包的那套互不通用"，本来就该这样；
      · 模型密钥与搜索密钥**留空**，并在旁边写一句"填你自己的"；
      · 其余原样（数据库地址、嵌入模型这些不是密钥）。

    清的是 **staging 里那份副本**，仓库里的 `.env` 不动 —— 打包不该改你的开发环境。
    """
    env_path = staging / ".env"
    if not env_path.is_file():
        return []
    text = env_path.read_text(encoding="utf-8")
    notes: list[str] = []
    for key in _REGENERATED_SECRETS:
        generated = secrets.token_hex(32)
        text, changed = _set_env_value(text, key, generated)
        if changed:
            notes.append(f".env：{key} 已为本次发布件重新生成（{len(generated)} 字符，不是你的那条）")
    for key in _BLANKED_SECRETS:
        text, changed = _set_env_value(
            text,
            key,
            "",
            comment=(
                "# ↓ 部署方填自己的密钥（发布件不带任何密钥；不填的话真模型起不来，"
                "启动日志会明说缺哪一条）"
            ),
        )
        if changed:
            notes.append(f".env：{key} 已留空，由部署方填自己的")
    env_path.write_text(text, encoding="utf-8")
    return notes


def _column_names(table: dict) -> list[str]:
    """迁移文件里 `columns` 是**对象数组**（`{"name": ..., "type": ...}`），
    不是字符串数组 —— 按字符串找列名会永远找不到，然后"抹密钥"那一步静默不生效。"""
    names: list[str] = []
    for column in table.get("columns") or []:
        if isinstance(column, dict):
            names.append(str(column.get("name") or ""))
        else:
            names.append(str(column))
    return names


def _redact_migration(staging: Path) -> list[str]:
    """把发布件里的迁移文件抹掉模型密钥。返回逐条说明。

    为什么不要求"导出时加 `--redact-secrets`"就完事：那是**流程约定**，
    而这里要的是**结果保证** —— 无论上游怎么导的，包里的 `api_key` 必须是空的。
    抹的是 staging 里那份副本，`deploy/migration.json` 本体不动
    （你本机"整机搬家"还要用它）。
    """
    path = staging / "deploy" / "migration.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    table = (payload.get("tables") or {}).get("infra_ai_provider")
    if not isinstance(table, dict):
        return []
    columns = _column_names(table)
    if "config" not in columns:
        return []
    index = columns.index("config")
    cleared = 0
    for row in table.get("rows") or []:
        if not isinstance(row, list) or len(row) <= index:
            continue
        config = row[index]
        if isinstance(config, dict) and config.get("api_key"):
            row[index] = {**config, "api_key": ""}
            cleared += 1
    payload["secrets_redacted"] = True
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return [
        f"迁移文件：已抹掉 {cleared} 个供应商的 api_key（部署方用 .env 里的 ZHIYIN_LLM_API_KEY 补）"
        if cleared
        else "迁移文件：api_key 本来就是空的，无需处理"
    ]


def _local_secret_values() -> set[str]:
    """本机现有的密钥值（用来在成品里找有没有漏出去的原值）。

    只取"明显是密钥"的：`.env` 里以 `_KEY` / `_SECRET` 结尾且长度 ≥ 16 的值，
    加上本机迁移文件里的 api_key。短值（`ollama` 这种）不算密钥，也避免误报。
    """
    values: set[str] = set()
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$", line)
            if match and (match.group(1).endswith(("_KEY", "_SECRET"))):
                value = match.group(2).strip()
                if len(value) >= 16:
                    values.add(value)
    migration = REPO_ROOT / "deploy" / "migration.json"
    if migration.is_file():
        try:
            payload = json.loads(migration.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        table = (payload.get("tables") or {}).get("infra_ai_provider") or {}
        columns = _column_names(table)
        if "config" in columns:
            index = columns.index("config")
            for row in table.get("rows") or []:
                if isinstance(row, list) and len(row) > index and isinstance(row[index], dict):
                    key = str(row[index].get("api_key") or "")
                    if len(key) >= 16:
                        values.add(key)
    return values


#: 密钥长得像什么（任何一份成品里出现这些形状都算漏）
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bark-[0-9a-fA-F-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _scan_for_secrets(archive: Path, known: set[str]) -> list[str]:
    """出包前的最后一道：成品里出现密钥特征或本机已知密钥值就拒绝。

    为什么要有它：上面两步是"清理"，这一步是"验证清理真的生效了"。
    少了它，哪天有人加了一个新文件（比如又导了一份 migration 到别的名字），
    清理不会覆盖到，而谁也看不出来。
    """
    hits: list[str] = []
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if name.endswith("/"):
                continue
            if Path(name).suffix.lower() not in {".json", ".env", ".yml", ".yaml", ".md", ".example"}:
                continue
            try:
                text = bundle.read(name).decode("utf-8")
            except (UnicodeDecodeError, KeyError):
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{name} 里有密钥特征：{pattern.pattern}")
            for value in known:
                if value and value in text:
                    hits.append(f"{name} 里有本机密钥原值（{value[:6]}…）")
    return hits


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

    notes = _sanitize_env(staging) + _redact_migration(staging)

    archive = args.out / f"{args.name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(args.out))

    leaks = _scan_for_secrets(archive, _local_secret_values())
    if leaks:
        archive.unlink(missing_ok=True)
        print("发布件里发现密钥，已删掉这份 zip、不交付：", file=sys.stderr)
        for line in leaks:
            print(f"  - {line}", file=sys.stderr)
        print(
            "处理方式：把密钥从源文件里挪走（模型密钥走 deploy/migration.json 的导出流程，"
            ".env 里的那几条由 _sanitize_env 统一清），再重新打包。",
            file=sys.stderr,
        )
        return 1

    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"发布件：{archive}")
    print(f"  文件 {len(files)} 个 · 压缩后 {size_mb:.1f} MB · 解压目录 {staging}")
    for note in notes:
        print(f"  {note}")
    print("  成品扫描：没有发现任何密钥（模式匹配 + 本机已知密钥值）")
    print("  关键文件：")
    for name in REQUIRED_FILES:
        # 用 ASCII 标记：Windows 控制台默认是 GBK，✓/✗ 会直接把打印炸掉
        # （zip 已经写好了，却因为最后一行报错让人以为打包失败）。
        mark = "OK " if (staging / name).is_file() else "缺"
        print(f"    {mark} {name}")
    # 交付方最容易误会的一条：模型密钥要**部署方自己填**（这个包不带任何密钥）。
    # 填了就是一次起好；没填会先报错重启几次、导入迁移后自愈。不写清楚，
    # 部署方会以为这个包是坏的。
    print(
        "  交接提醒：这个包**不含任何密钥**。部署方先在 .env 里填自己的"
        " ZHIYIN_LLM_API_KEY，再按《部署说明》第一节走（填了就一次起好；"
        "不填的话第一次会报错重启几遍，导入迁移后自愈）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
