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

    @abstractmethod
    async def invalidate_for_event(self, user_id: str, event: str) -> int:
        """按"发生了什么"作废受影响的产出，返回作废条数。

        调用点（API 层、编排器、Worker）只报事件，**"这一下影响到哪些产出"
        是实现里的知识**（任务 key 与它依据的事实写在一起）。
        事件码与读缓存同一套，见 `services/ai_tasks.py` 的 `_TASK_INPUTS`。

        为什么必须有这一条：读缓存的失效是**分片**的（`invalidate_for_event`），
        而 AI 产出是**按 key 存库**的，两者不共享机制。少了它，用户补完画像、
        勾完任务，界面上那些"由模型算出来的"内容（日历里那天的建议、
        待办建议、报告小结）会一直停在第一次算出来的样子。
        """


__all__ = ["AiTaskService"]
