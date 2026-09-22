"""AI 任务服务 Port。

八个 AI 任务（今日简报 / 维度解读 / 缺口追问 / 报告结论 / 学信网绑定 /
课表 / 待办建议 / 学职网匹配）的执行端，对应前端 `registry.ts`。
传输约定（SSE 帧协议）见设计文档第六章 6.2；产出契约在
`business/contracts/ai_tasks.py`（同时是 agno output_schema 的落点）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class AiTaskService(ABC):
    """AI 任务执行与缓存。"""

    @abstractmethod
    def stream(self, user_id: str, key: str, arg: str = "") -> AsyncIterator[dict]:
        """执行一个 AI 任务：yield 进度帧 {"pct","note","text"}，最后 yield {"result": ...}。

        同 (user_id, key) 命中缓存时直接 yield 终帧且 meta.cached=true。
        未登记的 key 或画像缺维度 / 缺口时抛 LookupError（Facade 映射为 NOT_FOUND）。
        """

    @abstractmethod
    async def invalidate(self, user_id: str, prefix: str = "") -> int:
        """画像更新后按前缀作废产出，返回作废条数。

        `async` 是必须的：产出存在库里（`ai_task_result`），作废是一次**写操作**，
        不是清一个内存字典。同步签名会逼着实现去阻塞事件循环。
        """


__all__ = ["AiTaskService"]
