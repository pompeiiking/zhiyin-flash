"""AI 任务产出形状的跨语言守卫：SSE 终帧的 `data` ↔ 前端 interface。

为什么它必须存在
----------------
八个 AI 任务是 **SSE 流**，OpenAPI 生成不到它们的响应体（终帧才是结果），
所以前端 `src/ai/registry.ts` 里那份形状是**手写的**。
这是全仓最后一处"跨语言、没有机械校验"的地方：

  · 后端改了 `DimensionReading` 的字段名 → 前端照旧读旧名字，
    界面上那块静默变成空白或 `undefined`，编译期一声不响；
  · 后端加了一个任务 → 前端不知道，能力做了没人用。

这里把两边对齐成可判的一件事：**前端每个 interface 的字段名集合
必须等于后端对应契约模型的字段名集合**（别名按 aliases 算：后端
`if_you_skip` 的 alias 是 `ifYouSkip`，前端就该写 `ifYouSkip`）。

只比**字段名**，不比嵌套结构与类型：嵌套形状（`list[dict[str, str]]` 这类）
在两边表达方式本来就不同，强行比会写成一个脆弱的解析器；而字段名漂移
恰恰是实际踩到过的那个坑。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import zhiyin_business.contracts.ai_tasks as ai_tasks

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_TS = TEMPLATE_ROOT / "zhiyin-web" / "src" / "ai" / "registry.ts"

#: 前端 interface 名 → 后端契约模型。两边同名是刻意的：改名字要一起改。
CONTRACT_MODELS = (
    "BriefToday",
    "DimensionReading",
    "AnalysisPoint",
    "PortraitAnalysis",
    "DayAdvice",
    "GapClarify",
    "ReportSummary",
    "BindResult",
    "TimetablePlan",
    "TodoSuggestion",
    "MatchResult",
)


def _backend_fields(model_name: str) -> set[str]:
    """后端模型的字段名（有 alias 用 alias —— 前端读到的是它）。"""
    model = getattr(ai_tasks, model_name)
    return {field.alias or name for name, field in model.model_fields.items()}


def _frontend_fields(interface: str) -> set[str]:
    """前端 `export interface X { ... }` 里的字段名。"""
    text = REGISTRY_TS.read_text(encoding="utf-8")
    match = re.search(
        rf"export interface {interface} \{{(.*?)\n\}}", text, re.S
    )
    assert match, f"前端 registry.ts 里没有 interface {interface}"
    body = match.group(1)
    fields: set[str] = set()
    for line in body.splitlines():
        line = line.split("//")[0].strip()
        if not line or line.startswith("/*") or line.startswith("*"):
            continue
        hit = re.match(r"([A-Za-z_]\w*)\??\s*:", line)
        if hit:
            fields.add(hit.group(1))
    assert fields, f"interface {interface} 里没解析到字段——守卫会变成空跑"
    return fields


@pytest.mark.parametrize("model_name", CONTRACT_MODELS)
def test_ai_task_output_shape_matches_frontend(model_name: str) -> None:
    """每个 AI 任务的产出形状，两边字段名必须一致（双向）。"""
    backend = _backend_fields(model_name)
    frontend = _frontend_fields(model_name)

    missing = sorted(backend - frontend)
    extra = sorted(frontend - backend)
    assert not (missing or extra), (
        f"{model_name} 的形状两边对不上：\n"
        f"  后端有、前端没写：{missing}\n"
        f"  前端有、后端没有：{extra}\n"
        "改后端 contracts/ai_tasks.py 的字段时，"
        "要同时改 zhiyin-web/src/ai/registry.ts 的 interface。"
    )


def test_registry_covers_every_stage_contract() -> None:
    """八个任务一个都不能漏：后端加了任务而前端不知道，能力就等于没做。"""
    text = REGISTRY_TS.read_text(encoding="utf-8")
    declared = set(re.findall(r"export interface (\w+)", text))
    missing = sorted(set(CONTRACT_MODELS) - declared)
    assert not missing, f"这些 AI 产出形状在前端 registry.ts 里没有对应 interface：{missing}"
