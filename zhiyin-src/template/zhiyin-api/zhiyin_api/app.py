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
    DuplicateResource,
    InvalidRequest,
    KernelError,
    ResourceNotFound,
)

_log = logging.getLogger(__name__)

DEFAULT_TITLE = "职引 API"


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
    app.add_middleware(RequestContextMiddleware)

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
            location = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
            problems.append(f"{location or 'body'}：{item.get('msg', '格式不正确')}")
        return _envelope(
            ErrorCode.INVALID_PARAM,
            "请求参数不合法 —— " + "；".join(problems[:5]),
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
            "assembly": report.to_dict(),
            # 读缓存自述：哪几片、各多长 TTL、命中/未命中/错误计数。
            # 放在装配报告旁边而不是里面 —— 报告是一次启动的快照，命中率是运行时计数。
            "cache": cache_snapshot(),
        }


__all__ = ["create_app"]
