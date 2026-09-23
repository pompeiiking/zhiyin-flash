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
import threading

from zhiyin_boot.ai_bootstrap import hydrate_ai_config
from zhiyin_boot.container import build_container, wire_application
from zhiyin_boot.logging_setup import configure_logging
from zhiyin_boot.registry_bootstrap import hydrate_registry_content
from zhiyin_boot.runtime_config import hydrate_runtime_config
from zhiyin_boot.settings import Settings


def _run_sync(coro):
    """在**导入期**把一个协程跑完。

    没有事件循环时就是 `asyncio.run`。已经在循环里时不能嵌套调用它 ——
    uvicorn 带 `--reload` 会在它自己的循环中导入本模块，嵌套 `asyncio.run`
    直接抛 `RuntimeError: asyncio.run() cannot be called from a running event loop`，
    表现是容器起来就崩（实测踩到，这正是"`--reload` 一直没人用得了"的原因）。
    这时另起一个线程跑：线程里没有循环，`asyncio.run` 就是合法的。

    异常原样带回主线程，不吞：读取库配置失败必须让启动失败得明明白白。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, object] = {}

    def runner() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - 原样抛回主线程
            box["error"] = exc

    thread = threading.Thread(target=runner, name="asgi-bootstrap")
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box.get("value")


def build_asgi_app():
    """读库配置（AI / 装配口径 / 动态资源）→ 装配 → 返回 ASGI 应用。"""
    configure_logging()
    settings = Settings.from_env()
    _run_sync(hydrate_ai_config(settings))
    _run_sync(hydrate_runtime_config(settings))
    _run_sync(hydrate_registry_content(settings))
    return wire_application(build_container(settings))


app = build_asgi_app()

__all__ = ["app", "build_asgi_app"]
