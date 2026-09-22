"""请求上下文（trace id）与它的唯一生产者。

为什么需要这个文件
------------------
`ApiResponse.trace_id`（R-API-006 统一信封）与前端 `client.ts` 的 `ApiError.traceId`
都已经把「链路追踪 id」当成既有字段在用，但**全仓没有任何地方生产它**——
字段恒为空字符串，前端拿到空值、日志里也串不起一次请求。

这与上一轮修掉的 `BootstrapView.app_name` 同类：**契约里有字段，链路上没有出口**。
区别是它更隐蔽（空字符串不会报错，只会让人误以为"这次没产生 trace"）。

本文件的职责（唯一）
--------------------
1. **生成**：请求进来时取上游 `X-Trace-Id`，没有就生成 32 位 hex；
2. **贯穿**：写进 `contextvars`（同进程内任何一层都能 `current_trace_id()` 读到）
   并回写响应头 `X-Trace-Id`；
3. **填充信封**：`ApiResponse.trace_id` 用 `current_trace_id()` 兜底，
   Controller 不需要也不允许自己传 trace id（就地少一处口径）。

口径与边界
----------
- 上游值只在形如 `[A-Za-z0-9_-]{1,64}` 时才沿用，否则重新生成——
  否则一次恶意/超长头会被原样写回响应头与日志。
- 生成点是 BFF：`create_app()` 挂载 `RequestContextMiddleware`，
  它是全站唯一的注入点（和 `/api/v1` 前缀一样，只有一处）。
- 本文件只负责"生成与贯穿"，**不负责落盘**：日志 sink / 采样 / 上报属 M4
  （门禁 manual 项：trace_id 端到端贯通）。届时新增 Gateway 能力位接 sink，
  `current_trace_id()` 这个取值口径不变。
- 将来加 CORS 中间件时，`expose_headers` 必须包含 `X-Trace-Id`，
  否则浏览器侧读不到它。
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token
from typing import Any, MutableMapping

from starlette.datastructures import MutableHeaders

TRACE_HEADER = "X-Trace-Id"
"""请求与响应共用的头名。前端 / 网关 / 压测都靠它把一个请求串起来。"""

TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
"""允许沿用的上游 trace id 形状：够长能唯一、够短不会污染日志。"""

_current_trace_id: ContextVar[str] = ContextVar("zhiyin_trace_id", default="")


def new_trace_id() -> str:
    """生成一个 trace id（32 位 hex，无连字符，便于日志检索与拼接）。"""
    return uuid.uuid4().hex


def current_trace_id() -> str:
    """当前请求的 trace id；不在请求上下文内时返回空字符串。

    这是跨层读取口径：业务 / 编排层写日志时直接调用它即可，
    不需要把 trace_id 一层层当参数传下去。
    """
    return _current_trace_id.get()


def bind_trace_id(trace_id: str) -> Token[str]:
    """绑定当前上下文（供中间件与测试使用）。返回 token，用于还原。"""
    return _current_trace_id.set(trace_id)


def reset_trace_id(token: Token[str]) -> None:
    """还原 `bind_trace_id` 之前的取值。"""
    _current_trace_id.reset(token)


def normalize_trace_id(raw: str | None) -> str:
    """上游值合法则沿用，否则生成新的。"""
    candidate = (raw or "").strip()
    if TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_trace_id()


def _inbound_trace_id(scope: MutableMapping[str, Any]) -> str | None:
    """从 ASGI scope 的原始头里取 `X-Trace-Id`（头名大小写不敏感）。"""
    wanted = TRACE_HEADER.lower().encode("latin-1")
    for name, value in scope.get("headers") or []:
        if name.lower() == wanted:
            return value.decode("latin-1")
    return None


class RequestContextMiddleware:
    """纯 ASGI 中间件：生成/沿用 trace id，回写响应头，并在请求结束后还原上下文。

    为什么不用 `@app.middleware("http")`：那条路走 Starlette 的
    `BaseHTTPMiddleware`，下游在**另一个 task** 里执行，`contextvars` 的可见性
    依赖实现细节。纯 ASGI 中间件与下游同一个 task，取值稳定。
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        trace_id = normalize_trace_id(_inbound_trace_id(scope))
        token = bind_trace_id(trace_id)
        started = False

        async def send_with_trace(message: MutableMapping[str, Any]) -> None:
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers[TRACE_HEADER] = trace_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_trace)
        except Exception as exc:  # noqa: BLE001 - 兜底必须是最宽的
            # 未捕获异常此前会穿透本中间件，由最外层的 ServerErrorMiddleware 返回一条
            # 纯文本 500 —— 既没有统一信封，也没有 X-Trace-Id。于是「日志里那个 id」
            # 恰恰在最需要它的那次请求上不存在。这里补上：响应头与信封用同一个 id。
            if started:
                # 响应已经开始，改不了头也换不了体，只能让它继续失败（交给外层）。
                raise
            await send_with_trace(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": _internal_error_body(exc, trace_id),
                }
            )
        finally:
            reset_trace_id(token)


def _internal_error_body(exc: BaseException, trace_id: str) -> bytes:
    """兜底 500 的响应体：统一信封，且不回显异常细节之外的内部对象。

    延迟 import `dto.common`：它反过来 import 本模块的 `current_trace_id`，
    模块级 import 会成环。
    """
    import json
    import logging

    from zhiyin_api.dto.common import ApiResponse, ErrorCode

    logging.getLogger(__name__).exception("未捕获异常（trace=%s）：%s", trace_id, exc)
    body = ApiResponse[None](
        code=ErrorCode.INTERNAL,
        message=f"服务内部错误（trace_id={trace_id}）",
    ).model_dump(mode="json")
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


__all__ = [
    "TRACE_HEADER",
    "TRACE_ID_PATTERN",
    "RequestContextMiddleware",
    "bind_trace_id",
    "current_trace_id",
    "new_trace_id",
    "normalize_trace_id",
    "reset_trace_id",
]
