"""启动期日志配置：让装配过程真的被打印出来。

为什么需要单独一个模块
----------------------
启动链路上有几句**只有启动期才会说**的话，全都是 `logging`：

    装配口径已从数据库装载：assembly.gates、assembly.ownership
    AI 配置以数据库为准：deepseek / deepseek-flash
    动态资源已入库并核对通过
    动态资源与 data/registry 不一致：agents：库中内容与文件不一致 [...]

在此之前一句都不会出现 —— 本项目的 logger 没有配 handler，而 uvicorn 只配置它自己
那几个 logger，于是这些消息一路冒泡到根 logger，那里什么也没有。INFO 直接消失，
WARNING 靠 Python 的兜底 handler 打在 stderr 上（带一行 `No handlers could be found`
味道的裸文本，没有时间也没有来源）。

后果很具体：**部署完看不到自己刚才做了什么**。日志里只有 uvicorn 的
`Application startup complete`，而那几句话恰恰是"迁移生效了没有 / 动态资源对没对上"
的唯一证据。用户照着文档去 grep 日志，grep 到的是空的。

口径：只在根 logger 还没有 handler 时装一次（测试与 uvicorn 自己的配置优先），
级别由 `ZHIYIN_LOG_LEVEL` 控制，默认 INFO。
"""

from __future__ import annotations

import logging
import os
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def configure_logging() -> None:
    """配一次根日志。已经有 handler 时只调级别，不覆盖别人的配置。"""
    level_name = os.getenv("ZHIYIN_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return
    logging.basicConfig(level=level, format=_FORMAT, stream=sys.stdout)


__all__ = ["configure_logging"]
