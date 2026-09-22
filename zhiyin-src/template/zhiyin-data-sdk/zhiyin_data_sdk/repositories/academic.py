"""教务系统快照的持久化（课表 / 成绩单）。

存的边界要写清楚：这张表里是**取回来的结果**（课程、成绩、学期、取数时刻），
不是授权凭据。学号密码既没有字段可放，也不该有 ——
一旦有了这个字段，早晚有人会因为"顺手"把它填进去。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from zhiyin_data_sdk.gateways.academic import AcademicSnapshot


class AcademicSnapshotRepository(ABC):
    """一个用户一份快照：重新取数即整体替换，不做增量。"""

    @abstractmethod
    async def get(self, user_id: str) -> Optional[AcademicSnapshot]:
        """读回这份快照；没取过就返回 None（界面据此说"还没授权"）。"""

    @abstractmethod
    async def upsert(self, user_id: str, snapshot: AcademicSnapshot) -> AcademicSnapshot:
        """写入 / 替换。"""

    @abstractmethod
    async def delete(self, user_id: str) -> None:
        """撤销授权时连带删掉取回来的数据。"""
