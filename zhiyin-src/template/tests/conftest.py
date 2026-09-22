"""测试隔离夹具。

为什么需要它
------------
装配是**全局注入**：`zhiyin_boot.wire_application()` 会把装配报告写进
`zhiyin_api.runtime`、把 Facade 实现写进 `zhiyin_api.facade`。这是"api 不能反向
依赖 boot"逼出来的设计，但代价是**用例之间会串状态**：

- 某个用例若 wire 过一次，后面的用例就会看到别人的 Facade——
  `test_app.py::test_unimplemented_capability_degrades_instead_of_500` 期望
  "未装配 → 503"，一旦有别的用例先装配了 Facade，它就会变成"看别人脸色"的用例；
- 装配报告同理，`/healthz` 的断言会读到上一个用例留下的快照。

此前只有 `test_app.py` 自己手工调了一次 `reset_runtime()`，属于"谁被坑谁修"。
这里统一成自动夹具：每个用例开始前还原两个全局注入点，用例顺序不再影响结果。
"""

from __future__ import annotations

from typing import Iterator

import pytest


@pytest.fixture(autouse=True)
def _reset_global_wiring() -> Iterator[None]:
    """每个用例前后都还原 api 层的两个全局注入点。"""
    from zhiyin_api.facade import reset_facade
    from zhiyin_api.runtime import reset_runtime

    reset_runtime()
    reset_facade()
    yield
    reset_runtime()
    reset_facade()
