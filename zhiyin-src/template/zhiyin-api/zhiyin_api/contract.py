"""接口契约快照：把「代码里的接口」导出成可入库、可校验的 OpenAPI 文档。

为什么需要它
------------
前端 README 本来就写着"字段口径以 `src/api/types.ts` 为准（由后端 OpenAPI
生成，不手写）"，但生成方式只有一条命令：

    openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/api/types.ts

它要求**后端正在本机运行**，于是出现三件事：

1. 前端同学拉不到类型（后端没起 / 端口被占 / 只想改个样式）；
2. CI 无法检查"前端类型是否与后端 DTO 一致"（CI 里没有跑着的后端）；
3. 接口一改，`types.ts` 是否有漂移完全靠人记得重新生成。

现在把链路改成单向、可校验的三段，任何一环漂移都在合入前失败：

```text
后端 DTO / Controller  ──(本模块导出)──▶  contracts/openapi.json（入库快照）
                                             │
                                    (npm run gen:api)
                                             ▼
                                   zhiyin-web/src/api/types.ts

tests/test_api_contract.py  守住「代码 == 快照」
CI 的 npm run check:api      守住「快照 == 前端类型」
```

口径
----
- 唯一事实来源是**代码**（Controller + DTO），快照只是它的导出物，不允许手改；
- 序列化固定为 `sort_keys=True + indent=2 + ensure_ascii=False`，
  因此"重新生成后无 diff"才有意义（否则字典顺序会让 diff 永远非空）；
- 不引入构建系统的运行时依赖：本模块只用 FastAPI 自带的 `app.openapi()`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zhiyin_api.app import create_app


def build_openapi_schema() -> dict[str, Any]:
    """按代码现状构造 OpenAPI（不启动服务、不写文件）。"""
    return create_app().openapi()


def render_openapi(schema: dict[str, Any]) -> str:
    """把 schema 渲染成入库文本。**格式即契约的一部分**：变了就会有 diff。"""
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_contract(path: Path) -> dict[str, Any]:
    """读取已入库的快照。文件不存在时抛 FileNotFoundError（由调用方给指引）。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_contract(path: Path) -> Path:
    """按代码现状覆盖写入快照，返回写入路径。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_openapi(build_openapi_schema()), encoding="utf-8")
    return target


def contract_is_stale(path: Path) -> list[str]:
    """快照与代码不一致时返回差异说明（空列表 = 一致）。

    比较两份 JSON 的**语义**，不比较键顺序：顺序由 `render_openapi` 统一，
    这里只回答"接口形状是否变了"。差异按路径逐条列出，方便直接定位。
    """
    committed = read_contract(path)
    live = build_openapi_schema()
    if committed == live:
        return []

    diffs: list[str] = []
    expected_paths = set(live.get("paths", {}))
    actual_paths = set(committed.get("paths", {}))
    for added in sorted(expected_paths - actual_paths):
        diffs.append(f"快照缺少接口：{added}")
    for removed in sorted(actual_paths - expected_paths):
        diffs.append(f"快照多了接口（代码里已删除）：{removed}")

    for path in sorted(expected_paths & actual_paths):
        if committed["paths"][path] != live["paths"][path]:
            diffs.append(f"接口形状不一致：{path}")

    expected_schemas = set(live.get("components", {}).get("schemas", {}))
    actual_schemas = set(committed.get("components", {}).get("schemas", {}))
    for added in sorted(expected_schemas - actual_schemas):
        diffs.append(f"快照缺少 DTO：{added}")
    for removed in sorted(actual_schemas - expected_schemas):
        diffs.append(f"快照多了 DTO（代码里已删除）：{removed}")

    if not diffs:
        diffs.append("OpenAPI 文本不一致（info / 组件细节变化），请重新生成")
    return diffs


__all__ = [
    "build_openapi_schema",
    "contract_is_stale",
    "read_contract",
    "render_openapi",
    "write_contract",
]
