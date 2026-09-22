"""对象存储 Gateway。

第一期默认实现：LocalFileStore（本地目录）。
TODO：按自有基础设施演进。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StoredObject(BaseModel):
    """对象元数据。"""

    model_config = ConfigDict(extra="forbid")

    key: str
    size: int = 0
    content_type: str = "application/octet-stream"
    updated_at: Optional[datetime] = None


class ObjectStoreGateway(ABC):
    """对象存储 Port。承载报告全文导出等非结构化内容。"""

    @abstractmethod
    async def put(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> StoredObject:
        """写入对象，返回元数据。"""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """读取对象内容。"""

    @abstractmethod
    async def stat(self, key: str) -> Optional[StoredObject]:
        """读取对象元数据。不存在返回 None。"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除对象。"""

    @abstractmethod
    def build_key(self, user_id: str, asset_type: str, version: int, ext: str) -> str:
        """生成对象键。统一命名规范，避免各调用方自行拼接。"""
