"""AI 任务结果的持久化契约。

为什么这份缓存要入库
--------------------
8 个 AI 任务的产出（报告小结、维度解读、缺口追问、待办建议、匹配矩阵……）
此前缓存在 `AiTaskService` 的**进程内存字典**里。两个后果：

- 重启一次，**模型已经花过钱生成的正文全部重来**；
- 多实例部署时各缓存各的，同一个用户刷新两次可能拿到两次不同的生成。

它不是"临时缓存"：`_TASK_SPECS` 里除少数有副作用的任务外，
产出都是可复用的资产级内容（`invalidate` 的语义也是"用户补了信息才作废"）。
所以按 (user_id, task_key) 落一张表，让"算过没有"这件事跨重启、跨实例成立。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class AiTaskResultRepository(ABC):
    """按 (user_id, task_key) 存 AI 任务的产出。"""

    @abstractmethod
    async def get(self, user_id: str, task_key: str) -> Optional[dict[str, Any]]:
        """取一份产出（原始 JSON 形状，由调用方还原成信封）。取不到返回 None。"""

    @abstractmethod
    async def put(self, user_id: str, task_key: str, payload: dict[str, Any]) -> None:
        """写入 / 覆盖一份产出。"""

    @abstractmethod
    async def delete_prefix(self, user_id: str, prefix: str = "") -> int:
        """按前缀作废（如 `dim.` 全部维度解读），返回删除条数。

        对应 `AiTaskService.invalidate`：用户补了信息之后，旧产出必须失效，
        否则界面会拿一份基于旧画像的解读当最新的用。
        """


__all__ = ["AiTaskResultRepository"]
