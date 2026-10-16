"""账号级交互状态。原子更新防止并发保存覆盖其他设置。"""

from abc import ABC, abstractmethod
from typing import Callable


class StudentStateRepository(ABC):
    @abstractmethod
    async def get(self, user_id: str) -> dict: ...

    @abstractmethod
    async def update(self, user_id: str, change: Callable[[dict], dict]) -> dict: ...
