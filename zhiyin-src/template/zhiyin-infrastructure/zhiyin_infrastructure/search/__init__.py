"""通用网络搜索的适配器（可选能力）。

为什么单独占一个包：它和"爬学职平台 / 学信网公开页面"那条链路是**两件事** ——

* 这边查的是**时效性事实**（政策公告、招聘时间、岗位动态），要一个搜索服务；
* 那边取的是**静态档案**（专业介绍、对口职业、校友案例），爬公开页面即可，
  不需要任何密钥。

所以本包只在配了 `ZHIYIN_SEARCH_API_KEY` 时才被装配（见
`zhiyin_boot/container/gateways.py`），没配就没有这个能力位 —— 不假装能搜。

⚠️ 与 `pyproject.toml` 的约定：**每个包都必须在 `[tool.setuptools] packages` 里
列一笔**。漏掉的后果只在镜像里出现：源码树里跑得通（pytest 的 `pythonpath`
直接指到目录），`pip install .` 装出来的 wheel 里却没有它 —— 于是"配了搜索密钥
的容器"一启动就 `ModuleNotFoundError`，而不配搜索的容器一切正常，很难联想到打包。
"""

from __future__ import annotations

__all__: list[str] = []
