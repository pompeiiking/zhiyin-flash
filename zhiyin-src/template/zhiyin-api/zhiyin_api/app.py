"""应用工厂。

第一期约定（R-API-001）：前端启动只请求一次 `/app/bootstrap` 即可渲染首页，
因此这里只做"挂载路由 + 统一错误信封 + 健康检查"，不承载业务装配 ——
具体实现的装配由 `zhiyin-boot.wire_application()` 完成。

⚠️ 接口前缀：**全站唯一收口在 `API_PREFIX`（`/api/v1`）**
-----------------------------------------------------------
版本段只在**这一个地方**拼接：`create_app` 把每个 router 统一挂到 `API_PREFIX` 下。
因此：

1. **Controller 里的路由不要写版本段。** 正确写法是 `@router.get("/app/bootstrap")`，
   最终对外是 `/api/v1/app/bootstrap`；写成 `"/api/v1/app/bootstrap"` 会变成
   `/api/v1/api/v1/app/bootstrap`，前端 404 而 OpenAPI 里看起来"有这条路由"。
2. **不要在别处再拼一次前缀。** 前端 baseURL、vite proxy、反向代理、网关都只做
   "原样转发"，不要再加 `/v1`；需要换版本时只改本文件的 `API_PREFIX` 一处。
3. **OpenAPI 与文档同前缀**（`{prefix}/openapi.json`、`{prefix}/docs`），
   所以 `npm run gen:api` 抓的就是真正对外的地址，不会生成一份对不上的类型。
4. **唯一例外是 `/healthz`**：运维探针不随 API 版本变化，故意留在版本命名空间之外。

该规则由 `tests/test_api_prefix.py` 守卫（路由声明里出现版本段即失败）。

⚠️ 请求上下文：**全站唯一的 trace id 生产者在这里挂载**
--------------------------------------------------------
`RequestContextMiddleware`（`zhiyin_api/context.py`）在此挂载，负责生成/沿用
`X-Trace-Id`、回写响应头、并让 `ApiResponse.trace_id` 有值。
换任何一层都不需要再生成一次 trace id；日志与前端按同一个 id 串联。
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from zhiyin_api.controllers import ROUTERS
from zhiyin_api.context import RequestContextMiddleware, current_trace_id
from zhiyin_api.dto.common import ApiResponse, ErrorCode
from zhiyin_api.runtime import cache_snapshot, get_runtime
from zhiyin_kernel.errors import (
    AccessDenied,
    Forbidden,
    DuplicateResource,
    InvalidRequest,
    KernelError,
    ResourceNotFound,
)

_log = logging.getLogger(__name__)

DEFAULT_TITLE = "职引 API"

#: 请求字段 → 学生看得懂的名字。Pydantic 的 `loc` 是英文变量名，直接回显
#: 等于把开发者词汇丢给用户（实测：复盘结果填错时只看到一句"有填写项不符合
#: 要求"，不知道是哪一项）。这里按领域常用字段建立受控词表；不在表里的字段
#: 只报位置（第几项），不把原始键名漏出去。
_REQUEST_FIELD_LABELS = {
    "task_id": "任务",
    "phase_id": "所属阶段",
    "message": "消息内容",
    "text": "内容",
    "name": "名称",
    "title": "标题",
    "reason": "复盘原因",
    "note": "复盘说明",
    "result": "复盘结果",
    "adjustment": "调整内容",
    "status": "状态",
    "waiting_reason": "等待原因",
    "progress": "完成进度",
    "estimated_minutes": "预计用时",
    "due_date": "截止时间",
    "scheduled_at": "安排时间",
    "starts_at": "开始时间",
    "ends_at": "结束时间",
    "date_range": "阶段时间",
    "depends_on": "前置阶段",
    "blocking_conditions": "阻塞条件",
    "handoff_requirements": "交接要求",
    "tasks": "任务",
    "phases": "阶段",
    "plans": "方向方案",
    "role": "方向角色",
    "target_desc": "目标描述",
    "fit_reason": "契合依据",
    "main_risk": "主要风险",
    "gaps": "差距",
    "requirement": "能力要求",
    "current_state": "目前情况",
    "suggestion": "建议",
    "key": "资料项",
    "value": "填写内容",
    "attributes": "补充属性",
    "assertion_type": "说法类型",
    "save_scope": "保存范围",
    "valid_from": "生效时间",
    "valid_to": "有效至",
    "event_at": "发生时间",
    "expected_updated_at": "资料版本",
    "expected_task": "任务版本",
    "client_request_id": "请求编号",
    "client_msg_id": "消息编号",
    "option_id": "选项",
    "option_value": "选项取值",
    "material_ids": "材料",
    "kind": "类别",
    "school": "学校",
    "term": "学期",
    "courses": "课程",
    "grades": "成绩",
    "score": "成绩",
    "credit": "学分",
    "point": "绩点",
    "category": "课程类别",
    "weekday": "星期",
    "start_period": "开始节次",
    "end_period": "结束节次",
    "weeks": "教学周",
    "place": "上课地点",
    "weekday_text": "星期",
    "period_text": "节次",
    "preview_id": "预览编号",
    "asset_type": "导出内容",
    "format": "文件格式",
    "snoozed_until": "稍后提醒时间",
    "badge_key": "完成记录",
    "items": "条目",
    "measurements": "衡量记录",
    "weights": "权重",
    "minimum": "最小值",
    "maximum": "最大值",
    "threshold": "门槛",
    "source": "来源",
    "sources": "资料来源",
    "version": "版本",
}

#: 枚举取值 → 中文。只翻译认识的；不认识的取值不直接回显英文。
_REQUEST_VALUE_LABELS = {
    "continue": "继续",
    "adjust": "调整",
    "complete": "完成",
    "pending": "待处理",
    "in_progress": "进行中",
    "waiting": "等待中",
    "completed": "已完成",
    "read": "已读",
    "later": "稍后",
    "done": "已完成",
    "pdf": "PDF",
    "docx": "Word",
    "report": "诊断报告",
    "direction_plan": "方向方案",
    "action_plan": "行动计划",
    "profile": "个人画像",
}


def _request_field_label(loc: Iterable[Any]) -> str:
    """从 Pydantic 的 `loc` 里拼出一句可读的位置，不回显英文键名。"""
    labels: list[str] = []
    item_number: int | None = None
    for part in loc:
        if isinstance(part, int):
            item_number = part + 1
            continue
        label = _REQUEST_FIELD_LABELS.get(str(part))
        if label:
            labels.append(label)
    if labels:
        text = "的".join(labels)
        return f"{text}第 {item_number} 项" if item_number else text
    return f"第 {item_number} 项" if item_number else "本次填写"


def _validation_reason(raw: str) -> str:
    """把 Pydantic 的英文默认文案翻成一句可执行的中文。"""
    clean = re.sub(r"^Value error,\s*", "", str(raw or "")).strip()
    if not clean:
        return "格式或取值不符合要求"
    lowered = clean.lower()
    if "field required" in lowered:
        return "不能为空"
    if "string should have at least" in lowered:
        match = re.search(r"at least (\d+) character", lowered)
        return f"至少需要 {match.group(1)} 个字" if match else "内容太短"
    if "string should have at most" in lowered:
        match = re.search(r"at most (\d+) character", lowered)
        return f"最多只能填 {match.group(1)} 个字" if match else "内容太长"
    if "input should be a valid integer" in lowered:
        return "请填写整数"
    if "input should be a valid number" in lowered or "input should be a valid float" in lowered:
        return "请填写数字"
    if "input should be a valid boolean" in lowered:
        return "请选择是或否"
    if "input should be a valid datetime" in lowered or "input should be a valid date" in lowered:
        return "请填写有效日期"
    if "input should be a valid list" in lowered:
        return "请按列表填写"
    if "input should be a valid dictionary or object" in lowered or "input should be a valid dictionary" in lowered:
        return "格式不正确"
    if "extra inputs are not permitted" in lowered:
        return "包含不支持的填写项"
    if "json decode error" in lowered:
        return "内容不是有效的 JSON"
    if re.search(r"[\u4e00-\u9fff]", clean):
        # 自定义校验器写的中文提示：原样保留，它通常已经说清改法。
        return clean
    if "input should be" in lowered:
        # 枚举类错误带有 'a', 'b' or 'c'：只翻译认识的值，避免把英文代号回显。
        choices = re.findall(r"['\"]([^'\"]+)['\"]", clean)
        translated = [_REQUEST_VALUE_LABELS.get(choice) for choice in choices]
        if choices and all(translated):
            return "只能是：" + "、".join(dict.fromkeys(translated))
        return "取值不在允许范围内"
    return "格式或取值不符合要求"


#: 进程内运行指标。只记数量与耗时，不记 URL 参数、用户身份或请求体。
_METRICS: dict[str, object] = {
    "requests": 0,
    "errors": 0,
    "latency_ms": [],
    "by_route": Counter(),
    "by_status": Counter(),
}


def _default_version() -> str:
    """接口文档里显示的版本号 —— **只有一个来源**：`pyproject.toml` 的 `version`。

    为什么不再写死一个字面量：写死就会出现"几处版本号、改一半"的老毛病。这个仓里
    刚发生过一次 —— `pyproject.toml` 与 `package.json` 都是 1.0.0，而这里还留着
    0.1.0，于是 `/api/v1/docs` 页头与契约快照长期显示旧版本，**没有任何东西会报错**。

    顺序：先读仓里的 `pyproject.toml`（源码树与容器里它都在），读不到（装成 wheel
    之后不在仓库里）再退回包元数据。两处都拿不到才给一个显眼的哨兵值 —— 宁可显示
    `0.0.0`，也不要编一个看起来像真的版本号。
    """
    try:
        import tomllib

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.is_file():
            with pyproject.open("rb") as handle:
                return str(tomllib.load(handle)["project"]["version"])
    except Exception:  # noqa: BLE001 - 读不到就往下退，不该因此起不来
        _log.debug("读 pyproject.toml 取版本失败，退回包元数据", exc_info=True)
    try:
        from importlib.metadata import version as _dist_version

        return _dist_version("zhiyin")
    except Exception:  # noqa: BLE001
        return "0.0.0"


DEFAULT_VERSION = _default_version()

API_PREFIX = "/api/v1"
"""唯一接口前缀。改版本只改这里，别在路由或前端里再拼一次。"""


def create_app(
    *,
    title: str = DEFAULT_TITLE,
    version: str = DEFAULT_VERSION,
    api_prefix: str = API_PREFIX,
    routers: Optional[Iterable[Any]] = None,
    lifespan: Optional[Any] = None,
    rate_limit: Optional[Any] = None,
    auth: Optional[Any] = None,
    rate_limits: Optional[dict[str, int]] = None,
    feature_registry: Optional[Any] = None,
) -> FastAPI:
    """构造 ASGI 应用。

    `routers` 可覆盖，便于单测只挂载需要的路由；默认挂载 `controllers.ROUTERS`。
    `api_prefix` 由启动方传入（boot 传 `Settings.api_prefix`），保证"配的值"与
    "实际挂载的值"是同一个；不传时回落到本模块的 `API_PREFIX`。
    """
    app = FastAPI(
        title=title,
        version=version,
        lifespan=lifespan,
        # 文档与 OpenAPI 跟着版本前缀走，前端 gen:api 抓到的就是对外地址。
        docs_url=f"{api_prefix}/docs",
        redoc_url=f"{api_prefix}/redoc",
        openapi_url=f"{api_prefix}/openapi.json",
    )

    for router in routers if routers is not None else ROUTERS:
        app.include_router(router, prefix=api_prefix)

    # trace id 的唯一生成点：任何进入应用的 HTTP 请求都会被包上上下文，
    # 因此信封里的 trace_id 不会是空字符串（守卫见 tests/test_request_context.py）。
    if feature_registry is not None:
        from zhiyin_api.feature_gate import FeatureGateMiddleware

        app.add_middleware(FeatureGateMiddleware, registry=feature_registry, prefix=api_prefix)
    if rate_limit is not None and hasattr(rate_limit, "allow_async"):
        from zhiyin_api.rate_limit import ApiRateLimitMiddleware

        app.add_middleware(ApiRateLimitMiddleware, gateway=rate_limit, auth=auth,
                           prefix=api_prefix, limits=rate_limits)
    app.add_middleware(RequestContextMiddleware)

    @app.middleware("http")
    async def _record_metrics(request: Request, call_next):
        """记录数量/耗时/状态码，供 `/metrics` 排查；不记录业务内容。"""
        started = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            route = request.scope.get("route")
            # 没匹配到路由时不能用完整路径做键：路径扫描/恶意请求会让这个字典
            # 无界增长（内存与 /metrics 序列化都跟着膨胀），而它对排查毫无增量 ——
            # 未匹配统一记成 unmatched，基数与路由表同阶。
            route_path = getattr(route, "path", None) or "unmatched"
            _METRICS["requests"] = int(_METRICS["requests"]) + 1
            status = getattr(response, "status_code", 500)
            if status >= 400:
                _METRICS["errors"] = int(_METRICS["errors"]) + 1
            _METRICS["by_route"][route_path] = _METRICS["by_route"].get(route_path, 0) + 1
            _METRICS["by_status"][str(status)] = _METRICS["by_status"].get(str(status), 0) + 1
            samples = _METRICS["latency_ms"]
            samples.append(round(elapsed, 2))
            if len(samples) > 5000:
                del samples[: len(samples) - 5000]

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> dict[str, Any]:
        """运行指标（JSON，非 Prometheus）；路径已按路由模板聚合，不含用户数据。"""
        samples = sorted(_METRICS["latency_ms"])
        count = len(samples)

        def percentile(p: float) -> float:
            if not samples:
                return 0.0
            index = min(count - 1, max(0, int(round((count - 1) * p))))
            return float(samples[index])

        return {
            "requests_total": int(_METRICS["requests"]),
            "errors_total": int(_METRICS["errors"]),
            "latency_ms": {
                "p50": percentile(0.50),
                "p95": percentile(0.95),
                "max": max(samples) if samples else 0.0,
            },
            "by_status": dict(_METRICS["by_status"]),
            "top_routes": dict(
                sorted(_METRICS["by_route"].items(), key=lambda item: item[1], reverse=True)[:20]
            ),
        }

    _install_error_handlers(app)
    return app


def _install_error_handlers(app: FastAPI) -> None:
    """统一响应信封（R-API-006）。

    三条口径：

    1. **能分类的失败按类映射**：`ResourceNotFound → 404/1002`、
       `AccessDenied → 401/1004`、`InvalidRequest → 422/1001`、
       `DuplicateResource → 409/1003`、未实现能力 → `503/1007`。
    2. **内建异常不再当业务信号**。此前按 `LookupError` / `PermissionError`
       这两个内建基类注册处理器，于是任何 `KeyError`/`IndexError` 都会变成 404、
       任何文件系统 `PermissionError` 都会变成 401 —— 真实缺陷被伪装成正常响应。
       现在只认 `zhiyin_kernel.errors` 里的类型（见该模块 docstring），
       内建异常重新落到兜底处理器。
    3. **兜底一定走信封**。`test_request_context.py` 只钉住了成功路径与 503 路径；
       未捕获异常此前会穿透 `RequestContextMiddleware`，返回一条既没有信封、
       也没有 `X-Trace-Id` 的纯文本 500 —— 排查时最需要 trace 的那一刻它恰好不在。
       这里补上兜底，`context.py` 同时保证响应头不丢。
    """
    from zhiyin_api.facade.facade import FacadeNotConfiguredError

    def _envelope(code: ErrorCode, message: str, status_code: int) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=ApiResponse[None](code=code, message=message).model_dump(mode="json"),
        )

    @app.exception_handler(FacadeNotConfiguredError)
    async def _facade_missing(_: Request, exc: FacadeNotConfiguredError) -> JSONResponse:
        return _envelope(ErrorCode.DEPENDENCY_UNAVAILABLE, str(exc), 503)

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        """还没实现的能力：信封照旧，但对外那句话得是用户能懂的。

        `str(exc)` 是写给我们的（"第一期尚未实现 XXX"），摆到界面上就是开发痕迹。
        细节留在日志里，用户拿到一句"现在还没有这个功能"。
        """
        _log.warning("调用了尚未实现的能力（trace=%s）：%s", current_trace_id(), exc)
        return _envelope(
            ErrorCode.DEPENDENCY_UNAVAILABLE, "这个功能现在还没有，稍后再试。", 503
        )

    @app.exception_handler(ResourceNotFound)
    async def _not_found(_: Request, exc: ResourceNotFound) -> JSONResponse:
        return _envelope(ErrorCode.NOT_FOUND, str(exc), 404)

    @app.exception_handler(Forbidden)
    async def _forbidden(_: Request, exc: Forbidden) -> JSONResponse:
        return _envelope(ErrorCode.FORBIDDEN, str(exc), 403)

    @app.exception_handler(AccessDenied)
    async def _unauthorized(_: Request, exc: AccessDenied) -> JSONResponse:
        return _envelope(ErrorCode.UNAUTHORIZED, str(exc), 401)

    @app.exception_handler(InvalidRequest)
    async def _invalid(_: Request, exc: InvalidRequest) -> JSONResponse:
        return _envelope(ErrorCode.INVALID_PARAM, str(exc), 422)

    @app.exception_handler(DuplicateResource)
    async def _duplicate(_: Request, exc: DuplicateResource) -> JSONResponse:
        return _envelope(ErrorCode.CONFLICT, str(exc), 409)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        """请求体校验失败也要走信封。

        此前返回的是 FastAPI 默认的 `{"detail": [...]}`：既没有 `code` / `trace_id`，
        也没有 `message`，前端只能拿到一句 `Request failed with status code 422`。
        更糟的是 Pydantic 的错误详情里带 `input` —— 密码字段校验失败时会把**用户提交的
        密码原文回显在响应体里**。这里只保留「哪个字段、为什么」，不回显取值。
        """
        problems = []
        for item in exc.errors():
            location = tuple(item.get("loc", ()))
            where = _request_field_label(part for part in location if part != "body")
            raw = str(item.get("msg", "格式不正确") or "格式不正确")
            # 自定义校验器写的中文提示优先：它通常已经说清"为什么、怎么改"。
            cleaned = re.sub(r"^Value error,\s*", "", raw).strip()
            if "安静时段" in cleaned:
                problems.append("安静时段：需要同时填写开始和结束时间")
                continue
            reason = _validation_reason(raw)
            problems.append(f"{where}：{reason}")
        return _envelope(
            ErrorCode.INVALID_PARAM,
            "有几个填写项需要检查：" + "；".join(dict.fromkeys(problems))[:300],
            422,
        )

    @app.exception_handler(KernelError)
    async def _kernel_error(_: Request, exc: KernelError) -> JSONResponse:
        """其余跨层异常：仍然是「可分类的失败」，不是 500。"""
        return _envelope(ErrorCode.INTERNAL, str(exc), 500)

    # 唯一不带版本前缀的端点：运维探针不随 API 版本变化（见模块 docstring 第 4 条）。
    @app.get("/healthz", tags=["ops"], summary="装配健康检查")
    async def healthz() -> dict[str, Any]:
        report = get_runtime()
        return {
            "status": "ok" if report.healthy else "degraded",
            "revision": os.environ.get("ZHIYIN_BUILD_REVISION", "working-tree"),
            "environment": os.environ.get("ZHIYIN_MODULE_ENV", "local"),
            "assembly": report.to_dict(),
            # 读缓存自述：哪几片、各多长 TTL、命中/未命中/错误计数。
            # 放在装配报告旁边而不是里面 —— 报告是一次启动的快照，命中率是运行时计数。
            "cache": cache_snapshot(),
        }


__all__ = ["create_app"]
