"""Controller 集合。

Controller 只做三件事：接收参数、格式校验（Pydantic 自动完成）、返回结果。
业务判断一律下沉到 Application Facade 与业务层。
"""

from zhiyin_api.controllers.app_controller import router as app_router
from zhiyin_api.controllers.conversation_controller import router as conversation_router
from zhiyin_api.controllers.workspace_controller import router as workspace_router
from zhiyin_api.controllers.asset_controller import router as asset_router
from zhiyin_api.controllers.track_controller import router as track_router
from zhiyin_api.controllers.ai_controller import router as ai_router
from zhiyin_api.controllers.auth_controller import router as auth_router
from zhiyin_api.controllers.config_controller import router as config_router
from zhiyin_api.controllers.note_controller import router as note_router

# 全部路由清单：供 zhiyin-boot 统一挂载
ROUTERS = [
    app_router,
    conversation_router,
    workspace_router,
    asset_router,
    track_router,
    ai_router,
    auth_router,
    config_router,
    note_router,
]

__all__ = [
    "ROUTERS",
    "app_router",
    "conversation_router",
    "workspace_router",
    "asset_router",
    "track_router",
    "ai_router",
    "auth_router",
    "config_router",
    "note_router",
]
