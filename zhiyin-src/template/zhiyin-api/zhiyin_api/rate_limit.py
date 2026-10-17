"""Apply shared gateway quotas before consuming uploads or starting model streams."""

import hashlib
import math

from starlette.requests import Request
from starlette.responses import JSONResponse

from zhiyin_api.dto.common import ApiResponse
from zhiyin_kernel.errors import AccessDenied


class ApiRateLimitMiddleware:
    def __init__(self, app, *, gateway, auth, prefix, limits=None):
        self.app, self.gateway, self.auth, self.prefix = app, gateway, auth, prefix
        self.limits = {"auth": 30, "write": 120, "conversation": 20, **(limits or {})}
        if any(not isinstance(n, int) or isinstance(n, bool) or n <= 0 for n in self.limits.values()):
            raise ValueError("API rate limits must be positive integers (requests per minute)")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self.app(scope, receive, send)
        path = scope["path"]
        if not path.startswith(self.prefix + "/"):
            return await self.app(scope, receive, send)
        request = Request(scope)
        group = "write"
        subject = "ip:" + (request.client.host if request.client else "unknown")
        if path in {self.prefix + "/app/auth/login", self.prefix + "/app/auth/register"}:
            group = "auth"
        else:
            token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if token:
                try:
                    principal = await self.auth.authenticate({"token": token})
                    subject = "user:" + principal.user_id
                except AccessDenied:
                    pass  # The controller retains the normal 401 response.
            if path.startswith(self.prefix + "/app/conversation/message"):
                group = "conversation"
        key = "api:" + group + ":" + hashlib.sha256(subject.encode()).hexdigest()
        limit = self.limits[group]
        allowed = await self.gateway.allow_async(key, limit=limit, window_s=60)
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content=ApiResponse(code=1009, message="请求过于频繁，请稍后重试。此次操作未执行。").model_dump(mode="json"),
                headers={"Retry-After": str(math.ceil(60 / limit)), "Cache-Control": "no-store"},
            )
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)
