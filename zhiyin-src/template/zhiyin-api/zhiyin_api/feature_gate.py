"""Enforce published feature switches at the actual API boundary."""

from starlette.responses import JSONResponse

from zhiyin_api.dto.common import ApiResponse, ErrorCode


class FeatureGateMiddleware:
    def __init__(self, app, *, registry, prefix):
        self.app, self.registry, self.prefix = app, registry, prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"].removeprefix(self.prefix)
            feature = {
                "/app/report/full-text": "report_full_text",
                "/app/assets/export": "export",
                "/app/calendar": "calendar",
                "/app/achievements": "achievements",
            }.get(path)
            if path.startswith("/app/assets/download/"):
                feature = "export"
            if path.startswith("/app/assets/report/versions/") and path.endswith("/content"):
                feature = "report_full_text"
            if path.startswith("/app/schedule/"):
                feature = "calendar"
            if feature and (await self.registry.feature_flags()).get(feature) is False:
                response = JSONResponse(status_code=403, content=ApiResponse(
                    code=ErrorCode.FORBIDDEN, message="此功能当前未开放，请返回其他功能。"
                ).model_dump(mode="json"))
                return await response(scope, receive, send)
        return await self.app(scope, receive, send)
