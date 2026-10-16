"""Regenerate the complete HTTP inventory from controller source and OpenAPI.

Connection status is reviewed evidence, never inferred from a transport wrapper.
"""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "zhiyin-src/template"
OUT = ROOT / "docs/前端/后端接入"
OUT.mkdir(parents=True, exist_ok=True)
schema = json.loads((BASE / "contracts/openapi.json").read_text(encoding="utf-8"))
evidence_file = OUT / "接口接入证据.json"
evidence = (
    json.loads(evidence_file.read_text(encoding="utf-8"))
    if evidence_file.exists()
    else {}
)
rows = []
for file in sorted((BASE / "zhiyin-api/zhiyin_api/controllers").glob("*.py")):
    source = file.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            if (
                not isinstance(d, ast.Call)
                or not isinstance(d.func, ast.Attribute)
                or d.func.attr not in {"get", "post", "put", "patch", "delete"}
                or not d.args
                or not isinstance(d.args[0], ast.Constant)
            ):
                continue
            path = "/api/v1" + d.args[0].value
            method = d.func.attr.upper()
            op = schema.get("paths", {}).get(path, {}).get(method.lower(), {})
            key = method + " " + path
            machine = "/source-worker/" in path or "/executor/" in path
            scope = (
                "服务间调用"
                if machine
                else "管理端"
                if "/developer/" in path or "/config/" in path
                else "学生端"
            )
            doc = (ast.get_docstring(node) or op.get("summary") or node.name).replace(
                "\n", " "
            )
            row = {
                "id": key,
                "method": method,
                "path": path,
                "capability": doc,
                "source": str(file.relative_to(ROOT)).replace("\\", "/")
                + ":"
                + str(node.lineno),
                "scope": scope,
                "stream": file.name == "ai_controller.py",
                "parameters": op.get("parameters", []),
                "request": op.get("requestBody"),
                "responses": op.get("responses", {}),
                "status": "服务间接口，不应从浏览器调用" if machine else "尚未接入",
                "frontend": [],
                "verification": "未联调",
            }
            row.update(evidence.get(key, {}))
            rows.append(row)
rows.sort(key=lambda r: (r["scope"], r["path"], r["method"]))
(OUT / "后端接口与模型.json").write_text(
    json.dumps(
        {"endpoints": rows, "schemas": schema.get("components", {}).get("schemas", {})},
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
lines = [
    "# 后端能力与前端接入清单",
    "",
    "以控制器源码逐条扫描，并附完整 OpenAPI 请求、响应和模型，不能仅以学生端封装数量代表后端能力。",
    "",
    f"控制器 HTTP 接口共 **{len(rows)}** 项。机器专用接口仍列出，但不将部署、执行器凭证放进学生端。",
    "",
    "状态定义：尚未接入；前端已连接（代码可达，尚待联调）；联调通过（当前本机系统）；隔离联调通过（独立数据库、合成账号与业务资料，真实 HTTP）；环境阻塞（缺少真实资料或执行环境）。隔离验收不代表生产发布成功；构建通过不等于服务可用。",
    "",
    "完整参数、请求体、响应体与模型定义见 [后端接口与模型.json](后端接口与模型.json)。接入证据记录于 接口接入证据.json，运行 `python scripts/contracts/frontend-capabilities.py` 更新本表。",
    "",
    "## 公共协议",
    "",
    "学生端使用 Bearer token；普通响应为 `{code,message,data,trace_id}`，仅 code=0 算成功。HTTP 401 或业务码 1004 需要重新登录。AI 任务为 SSE，按进度/错误/最终 result 处理，缺少最终结果不能视为成功。管理端还需后端权限校验；Worker 与 Executor 使用服务端执行凭据，与用户登录令牌隔离，不向浏览器提供。",
    "",
    "## 能力清单",
    "",
    "|能力/接口|归属|前端接入状态|页面与代码证据|联调结果|",
    "|---|---|---|---|---|",
]
for r in rows:
    label = r["capability"].split("。")[0].replace("|", "／")[:120]
    files = "<br>".join("`" + p + "`" for p in r["frontend"]) or "—"
    lines.append(
        f"|{label}<br>`{r['id']}`|{r['scope']}|{r['status']}|{files}|{r['verification']}|"
    )
lines += [
    "",
    "## 非控制器能力与边界",
    "",
    "- `/healthz`：服务装配和依赖状态，属于运维探针；`/api/v1/docs`、`/api/v1/redoc`、`/api/v1/openapi.json` 为接口文档。",
    "- 后台定时调度、影响传播、提醒派发、知识检索、模型调用、数据库/Redis/对象存储由后端运行。前端通过报告、依赖、日历、通知与模块结果使用这些能力，不重复实现 Worker。",
    "- 当前系统已实现 PDF/Word 生成及鉴权下载，并通过容器重建后的文件回读；无对应资产时返回明确错误。兼容未装配导出服务的环境时，前端仍须处理 available=false。",
    "- 无密码重置、账号删除、独立手动日历 CRUD；任务排期、偏好和复盘已增加正式接口，状态以逐项证据为准。",
    "- 模块 manifest、policy、表单 schema 和工作流由发布结果决定；目录为空不能用预置应用代替。",
    "- 学业导入和学信核验是不同能力；导入文件成功不代表学籍核验成功。",
    "",
]
(OUT / "后端能力与接入清单.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Inventory: {len(rows)} controller endpoints")
