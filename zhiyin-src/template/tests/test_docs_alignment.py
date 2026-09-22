"""文档对齐守卫（单文档口径）。

本仓只有**一份**设计文档：`docs/职引-完整设计文档.md`。产品与业务口径一律以它为准。
此前那些 PRD / 前端页面设计 / 技术架构 / 评审记录 / 原型说明已整体移除，
本文件同时负责"不让它们借尸还魂"。

为什么值得守：文档漂移的代价是**照错抄**——新人（或 AI）照着文档去改一个不存在的
文件，或者引用一份已经不存在的文档。这类错不会报错，只会把时间浪费在找不到的东西上。

本文件只守五件机械可判的事：

1. 唯一设计文档必须存在，且 `docs/` 下不允许再出现第二份；
2. 入口 README（根 README + 前端 README）必须指向它，且相对链接必须能解析到真实文件；
3. 已移除的文档不得再被引用（文档名 / 仓库路径 / 需求编号 / 章节号）；
4. 入口文档里用代码片段引用的**仓库路径必须存在**；
5. 门禁 JSON 的 `manual` 项里提到的**目录必须存在**。

它不检查文字表述是否正确——那需要人看。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TEMPLATE_ROOT.parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
REGISTRY_DIR = TEMPLATE_ROOT / "data" / "registry"

# 唯一设计文档：全仓产品与业务口径的来源。
DESIGN_DOC = "docs/职引-完整设计文档.md"

# 需要做"链接 / 路径引用存在性"检查的文档：本仓全部 markdown 入口。
CURRENT_DOCS: tuple[str, ...] = (
    "README.md",
    DESIGN_DOC,
    "zhiyin-src/template/zhiyin-web/README.md",
)

# 外部协议：不解析成本地文件
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "codex:", "tel:")

# 已被移除的文档留下的痕迹。加一条之前先问：读者会不会照着它去找一个不存在的东西？
# 会，就加进来；不会（比如普通中文词），就别加。
REMOVED_DOC_MARKERS: tuple[str, ...] = (
    # 需求文档与它的编号体系
    "PRD",
    "FR-",
    # 章节号：本仓只有一份文档，且它不用章节号，出现即是从别处抄来的
    "§",
    # 已移除的文档名（含简称）
    "原型设计说明",
    "移动端原型技术方案",
    "前端页面设计",
    "前端设计文档",
    "开发指南",
    "技术架构文档",
    "职引技术架构",
    "分层详细设计",
    "分层实现与接口设计",
    "目标架构设计",
    "第一期技术架构",
    "第一期数据层设计",
    "业务数据采集与存储来源设计",
    "架构与代码结构评估",
    "架构外壳完整度评估",
    "架构与结构评估",
    "业务口径决策记录",
    # 已移除的路径
    "prototype/",
    "docs/README.md",
    "docs/PRD/",
    "docs/开发指南.md",
    "docs/技术架构文档/",
    "docs/评审/",
    "docs/前端设计/",
)

# 扫描范围：手写文本文件。二进制与锁文件跳过（package-lock 里不会有这些词）。
SCANNED_SUFFIXES = (".md", ".py", ".json", ".ts", ".vue", ".css", ".yml", ".yaml", ".toml")
SCANNED_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "dist",
    # 打包产物：`release/` 里是整仓的一份副本（deploy/package_release.py 生成，
    # 已在 .gitignore 里）。扫它只会让"包里那份旧代码"把本仓判成违规，
    # 而且每加一条标记就要多扫一遍全仓 —— 它不是源码。
    "release",
    "_archive-wireframe-v0",
    # IDE 本地配置（.trae/ 同 .idea/ 一样只在开发者机器上，已进 .gitignore）。
    # 里面装的第三方技能文件自带"§6"这类章节引用，扫它只会误伤。
    ".trae",
}

"""审计 / 评审产物：**必须**引用旧文档名、章节号与"已移除"清单（那正是它们要记录的东西），
所以它们不能进本守卫 —— 否则"把问题记下来"这个动作本身会被判成违规。

这里只放两类：本仓的审计报告目录与报告本体。产品文档（README / 设计文档 / 指南）
一个都不能加进来。
"""
AUDIT_OUTPUT_NAMES = {
    "审计报告.md",
    "codex-audit",
}


def _text_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        parts = path.relative_to(REPO_ROOT).parts
        if any(part in SCANNED_SKIP_DIRS for part in parts):
            continue
        if parts and parts[0] in AUDIT_OUTPUT_NAMES:
            continue
        if path.name == "package-lock.json":
            continue
        files.append(path)
    return sorted(files)


def _relative_links(path: Path) -> list[str]:
    """取出一份 markdown 里的全部相对链接目标（去掉锚点）。"""
    text = path.read_text(encoding="utf-8")
    targets: list[str] = []
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text):
        raw = match.group(1).strip().strip("<>")
        if not raw or raw.startswith(EXTERNAL_PREFIXES) or raw.startswith("#"):
            continue
        target = unquote(raw.split("#")[0].strip())
        if target:
            targets.append(target)
    return targets


# --------------------------------------------------------------------------
# 1. 唯一设计文档
# --------------------------------------------------------------------------


def test_single_design_doc_exists() -> None:
    """`docs/` 下只能有一份 markdown：唯一设计文档。"""
    doc = REPO_ROOT / DESIGN_DOC
    assert doc.is_file(), f"缺少唯一设计文档：{DESIGN_DOC}"

    others = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in DOCS_ROOT.rglob("*")
        if path.is_file()
    )
    assert others == [DESIGN_DOC], (
        "docs/ 下出现了设计文档以外的文件：\n  "
        + "\n  ".join(others)
        + "\n本仓只有一份文档；新增内容请并入唯一设计文档，不要另开文件。"
    )


@pytest.mark.parametrize(
    "relative_doc", [doc for doc in CURRENT_DOCS if doc != DESIGN_DOC]
)
def test_entry_docs_link_to_design_doc(relative_doc: str) -> None:
    """入口 README 必须给出指向唯一设计文档的相对链接。"""
    doc = REPO_ROOT / relative_doc
    depth = len(doc.parent.relative_to(REPO_ROOT).parts)
    expected = "/".join([".."] * depth + DESIGN_DOC.split("/"))

    links = {unquote(link).replace("\\", "/") for link in _relative_links(doc)}
    assert expected in links, (
        f"{relative_doc} 没有指向唯一设计文档 {DESIGN_DOC}；"
        f"相对链接应写成 `{expected}`。"
    )


@pytest.mark.parametrize("relative_doc", CURRENT_DOCS)
def test_relative_links_resolve(relative_doc: str) -> None:
    """文档里的相对链接必须指向真实存在的文件。

    仓外文档（如 BRD / FRD）**不要**写成链接：断链比没有链接更容易误导——
    读者会以为文件在仓库里。
    """
    doc = REPO_ROOT / relative_doc
    broken = [
        target
        for target in _relative_links(doc)
        if not (doc.parent / target).resolve().exists()
    ]
    assert not broken, (
        f"{relative_doc} 存在断链：{broken}。"
        "指向仓外文档时请改为文字引用并标注『仓外文档，未纳入本仓』"
    )


# --------------------------------------------------------------------------
# 2. 已移除的文档不得再被引用
# --------------------------------------------------------------------------


@pytest.mark.parametrize("marker", REMOVED_DOC_MARKERS)
def test_removed_documents_are_not_referenced(marker: str) -> None:
    """全仓不得再出现已移除文档的名字、路径、章节号或需求编号。

    这条守的是"只有一个文档"这个事实本身：留着旧引用，读者就会当成还有那份文档。
    本守卫文件自己当然会出现这些词，因此跳过自己。
    """
    hits: list[str] = []
    for path in _text_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if marker in line:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()[:120]}")

    assert not hits, (
        f"以下位置仍在引用已移除的文档（标记：{marker}）：\n  "
        + "\n  ".join(hits[:20])
        + ("\n  …" if len(hits) > 20 else "")
        + "\n本仓只有一份设计文档；这些引用请删除或改写到真实文件。"
    )


# --------------------------------------------------------------------------
# 3. 文档里引用的仓库路径必须存在
# --------------------------------------------------------------------------

_PATH_EXTENSIONS = (".py", ".json", ".toml", ".md", ".ts", ".vue", ".yml", ".yaml", ".cfg")

# 文档写路径时的简写约定 → 真实位置。
# 例：`services/registry.py` 其实是 `zhiyin-business/zhiyin_business/services/registry.py`，
# `api/dto/mappers.py` 是 `zhiyin-api/zhiyin_api/dto/mappers.py`。
_SHORTHAND_ALIASES: dict[str, str] = {
    "api": "zhiyin-api/zhiyin_api",
    "business": "zhiyin-business/zhiyin_business",
    "kernel": "zhiyin-kernel/zhiyin_kernel",
    "data_sdk": "zhiyin-data-sdk/zhiyin_data_sdk",
    "orchestration": "zhiyin-orchestration/zhiyin_orchestration",
    "infrastructure": "zhiyin-infrastructure/zhiyin_infrastructure",
    "boot": "zhiyin-boot/zhiyin_boot",
    "web": "zhiyin-web",
}


def _package_dirs() -> list[Path]:
    return sorted(
        path
        for path in TEMPLATE_ROOT.iterdir()
        if path.is_dir() and path.name.startswith("zhiyin-")
    )


def _resolves(relative: str, doc_dir: Path) -> bool:
    """把文档里的一个路径片段解析到真实文件（按约定依次尝试）。"""
    candidates: list[Path] = [REPO_ROOT / relative, doc_dir / relative, TEMPLATE_ROOT / relative]

    head, _, rest = relative.partition("/")
    if head in _SHORTHAND_ALIASES and rest:
        candidates.append(TEMPLATE_ROOT / _SHORTHAND_ALIASES[head] / rest)
    if head.startswith("zhiyin-") and rest:
        # `zhiyin-boot/container/` → `zhiyin-boot/zhiyin_boot/container/`
        candidates.append(TEMPLATE_ROOT / head / head.replace("-", "_") / rest)

    for package_dir in _package_dirs():
        candidates.append(package_dir / relative)
        for sub in package_dir.iterdir():
            if sub.is_dir():
                candidates.append(sub / relative)

    for extra in ("data", "tests", "zhiyin-web", "zhiyin-web/src"):
        candidates.append(TEMPLATE_ROOT / extra / relative)

    return any(candidate.exists() for candidate in candidates)


def _looks_like_repo_path(span: str) -> bool:
    """判断一个代码片段是不是"仓库路径引用"，而不是接口路径 / 组件名 / 命令。"""
    if "/" not in span or " " in span:
        return False
    if any(token in span for token in ("*", "{", "}", "<", ">", "|", "…", "...", "=", "@", "::")):
        return False
    if span.startswith(("/", "http", "GET", "POST", "PUT", "DELETE", "PATCH")):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_./\-]+", span):
        return False
    # 只认"能定位"的三种形态，避免把组件名（`home/TaskCardGroup`）与接口段
    # （`task/enter`）当成文件路径：
    #   ① 带文件扩展名；② 至少两段的目录（`data/registry/`）；
    #   ③ 带仓库根前缀的路径（`zhiyin-src/...`）。
    # 单个叶子目录（目录树里的 `local/`）无法判断父目录，不算。
    has_inner_slash = "/" in span.rstrip("/")
    if span.endswith(_PATH_EXTENSIONS):
        return True
    if span.endswith("/") and has_inner_slash:
        return True
    return span.startswith(("docs/", "zhiyin-src/", "tests/", "data/", ".github/"))


def _path_references(text: str) -> set[str]:
    """取出一段文本里的路径引用：行内代码片段 + 围栏代码块（目录树 / 流程图里也可能写路径）。"""
    spans = {match.group(1).strip() for match in re.finditer(r"`([^`]+)`", text)}
    for block in re.findall(r"```[a-zA-Z]*\n([\s\S]*?)```", text):
        # 起始字符带上 `/`：否则 `--in /migration/migration.json` 里的
        # **容器内绝对路径**会被截成 `migration/migration.json`，再被当成
        # 仓库相对路径 —— 于是"部署命令里提到了容器路径"会被判成文档漂移。
        # 带上 `/` 之后，绝对路径仍然以 `/` 开头，由 `_looks_like_repo_path`
        # 的开头判断排除掉（判断口径不变，只是不再误伤）。
        for token in re.findall(r"[/A-Za-z0-9_][A-Za-z0-9_./\-]*", block):
            spans.add(token)
    return {span for span in spans if _looks_like_repo_path(span)}


@pytest.mark.parametrize("relative_doc", CURRENT_DOCS)
def test_documented_repo_paths_exist(relative_doc: str) -> None:
    """文档里用代码片段引用的仓库路径必须真实存在。

    这条守的是最贵的漂移：文档说"改这个文件"，而文件不在那儿。
    """
    doc = REPO_ROOT / relative_doc
    assert doc.is_file(), f"待检查的文档不存在：{relative_doc}"
    missing = sorted(
        span
        for span in _path_references(doc.read_text(encoding="utf-8"))
        if not _resolves(span, doc.parent)
    )
    assert not missing, (
        f"{relative_doc} 引用了不存在的仓库路径（照错抄风险）：\n  "
        + "\n  ".join(missing)
        + "\n请把文档改到真实路径。"
    )


# --------------------------------------------------------------------------
# 4. 门禁里的落点必须真实存在
# --------------------------------------------------------------------------


def test_gate_manual_paths_exist() -> None:
    """门禁 JSON 的 manual 项里提到的目录必须存在。

    此前 `--check --phase=2` 的退出条件写着"`tests/e2e/` 主路径通过"，而该目录不存在——
    门禁引用了一个不存在的验收落点。这里把"门禁提到的目录必须真实"钉住。
    """
    gates = json.loads((REGISTRY_DIR / "assembly_gates.json").read_text(encoding="utf-8"))
    referenced: set[str] = set()
    for gate in gates.get("items", []):
        for text in gate.get("manual", []) or []:
            # manual 是自然语言（可能带反引号也可能不带），因此按"像目录的 token"提取：
            # 只认 ASCII 路径字符且以 `/` 结尾的片段，避免把中文短语当成路径。
            for span in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_./\-]*/", str(text)):
                if "/" in span:
                    referenced.add(span)

    assert referenced, "门禁里应当有可解析的目录引用（如 tests/e2e/）"
    missing = sorted(
        span for span in referenced if not _resolves(span, TEMPLATE_ROOT)
    )
    assert not missing, f"门禁引用了不存在的目录：{missing}"


# --------------------------------------------------------------------------
# 5. 表清单与 DDL 对齐（防重复设计）
# --------------------------------------------------------------------------


def test_table_inventory_matches_schema() -> None:
    """第十一节的表清单必须与 DDL 完全一致：不多、不少、不重名。

    为什么值得守：这份清单是"新东西该放哪张表"的判断依据。
    - 清单里少一张 → 后来的人以为它不存在，于是再建一张同义的表；
    - 清单里多一张 → 他去找一张根本没有的表；
    - 清单里重名 → 同一张表被登记成两种用途，读者不知道该信哪一条。

    三种错都不会报错，只会让人做出重复设计 —— 所以在这里挡住。
    """
    doc = (REPO_ROOT / DESIGN_DOC).read_text(encoding="utf-8")
    assert "## 十一、" in doc, "缺少第十一节（数据库表清单）"
    section = doc.split("## 十一、", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, re.M)

    from zhiyin_infrastructure.postgres.schema import SCHEMA_SQL

    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA_SQL))

    duplicated = sorted({name for name in listed if listed.count(name) > 1})
    assert not duplicated, f"第十一节的表清单里重复登记了：{duplicated}"

    assert set(listed) == declared, (
        "第十一节的表清单与 DDL 不一致：\n"
        f"  清单里有、DDL 里没有：{sorted(set(listed) - declared)}\n"
        f"  DDL 里有、清单没登记：{sorted(declared - set(listed))}\n"
        "新增或删除表时，两处一起改。"
    )
