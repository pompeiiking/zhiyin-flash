"""ASGI 入口（只为 `--reload` 存在）。

为什么需要单独一个模块：uvicorn 的热重载要求把应用传成 **import string**
（`"module:app"`），它才能在改代码后重新导入。而 `__main__` 里是先读库配置、
再装配、最后 `uvicorn.run(实例)` —— 那种传法下 `--reload` 会直接抛
`RuntimeError: You must pass the application as an import string`。

所以本模块把"读库配置 → 装配 → 暴露 app"这三步写在导入期，供
`python -m zhiyin_boot --reload` 使用；生产启动（不带 `--reload`）仍然走
`__main__` 的实例化路径，行为不变。
"""

from __future__ import annotations

import asyncio

from zhiyin_boot.ai_bootstrap import hydrate_ai_config
from zhiyin_boot.container import build_container, wire_application
from zhiyin_boot.logging_setup import configure_logging
from zhiyin_boot.registry_bootstrap import hydrate_registry_content
from zhiyin_boot.runtime_config import hydrate_runtime_config
from zhiyin_boot.settings import Settings


def build_asgi_app():
    """读库配置（AI / 装配口径 / 动态资源）→ 装配 → 返回 ASGI 应用。"""
    configure_logging()
    settings = Settings.from_env()
    asyncio.run(hydrate_ai_config(settings))
    asyncio.run(hydrate_runtime_config(settings))
    asyncio.run(hydrate_registry_content(settings))
    return wire_application(build_container(settings))


app = build_asgi_app()

__all__ = ["app", "build_asgi_app"]
