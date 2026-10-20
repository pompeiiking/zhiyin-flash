"""画像活状态读写（profile_field / profile_gap）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Sequence

from zhiyin_kernel.blackboard import (
    Profile,
    ProfileClue,
    ProfileField,
    ProfileFieldRevision,
    ProfileGap,
)


class ProfileRepository(ABC):
    """画像 Repository。"""

    @abstractmethod
    async def get(self, user_id: str) -> Optional[Profile]:
        """读取画像（含 fields 与 gaps）。不存在返回 None。"""

    @abstractmethod
    async def save(self, profile: Profile) -> Profile:
        """整体保存画像，返回落库后的对象。"""

    @abstractmethod
    async def upsert_field(self, user_id: str, field: ProfileField, *, expected_updated_at: datetime | None = None, check_version: bool = False) -> ProfileField:
        """写入 / 更新单个画像字段。已存在则覆盖并刷新 updated_at。"""

    @abstractmethod
    async def delete_field(self, user_id: str, key: str, *, expected_updated_at: datetime | None = None, check_version: bool = False) -> None:
        """删掉一个画像字段。

        为什么需要它，而不只是"把值改成空"：采集清单判断"这条还需要吗"看的是
        **字段在不在**，不是值空不空。撤销教务系统授权之后，如果只是把摘要清空，
        "课程表 / 成绩单"会永远显示已取到 —— 用户再也回不到取数入口。
        所以撤销要真的把这条抹掉，让它重新变成一件待办。
        """

    @abstractmethod
    async def list_fields(
        self, user_id: str, keys: Optional[Sequence[str]] = None
    ) -> list[ProfileField]:
        """按字段键批量读取画像字段。keys 为空表示全部。"""

    @abstractmethod
    async def list_gaps(self, user_id: str) -> list[ProfileGap]:
        """读取画像缺口清单，用于采集追问与工作台展示。"""

    @abstractmethod
    async def replace_gaps(self, user_id: str, gaps: list[ProfileGap]) -> None:
        """整体替换缺口清单。"""

    @abstractmethod
    async def list_clues(self, user_id: str) -> list[ProfileClue]:
        """读取待验证线索（《个人画像设计-2026-10-20》第 3.2 节）。

        线索与事实字段分开存：它是「AI 对信息的有限理解」，界面要能说清
        「这是系统的理解，不是你说过的事实」，用户也可以否认它。
        """

    @abstractmethod
    async def replace_session_clues(
        self, user_id: str, session_id: str, clues: list[ProfileClue]
    ) -> None:
        """按会话整体替换线索。

        为什么是「整体替换」而不是逐条 upsert：线索来自一次分析，重跑一次分析
        应该得到那一次的结果，而不是把新旧线索堆在一起。逐条追加的后果是同一句
        理解重复出现，看起来像「被反复验证过」—— 设计第 3.2 节明确禁止这种
        用重复次数把推测变成结论的做法。
        """

    @abstractmethod
    async def invalidate_clues(
        self, user_id: str, field_keys: list[str], reason: str
    ) -> int:
        """把依据这些画像字段的线索标记为失效，返回受影响条数。

        依据被更正、撤回或删除后，相关线索失效或等待重新分析（设计第 7 节）。
        只改「待验证」的线索：已失效的不重复改写，已确认的留给重新分析流程。
        """

    @abstractmethod
    async def append_revision(
        self, user_id: str, revision: ProfileFieldRevision
    ) -> ProfileFieldRevision:
        """追加一条历史版本 / 冲突提案；**只追加，不覆盖当前字段**。"""

    @abstractmethod
    async def list_revisions(
        self,
        user_id: str,
        key: Optional[str] = None,
        *,
        status: Optional[Sequence[str]] = None,
    ) -> list[ProfileFieldRevision]:
        """读取版本记录；可按字段键或状态筛选（冲突提案用 status=conflict）。"""

    @abstractmethod
    async def update_revision_status(
        self,
        user_id: str,
        revision_id: str,
        *,
        status: str,
        replaced_at: Optional[datetime] = None,
        change_reason: str = "",
    ) -> None:
        """裁定一条冲突提案：改状态并记录裁定时刻/原因。"""
