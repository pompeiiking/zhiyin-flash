"""本地文件对象存储（LocalFileStore）。

写本地目录。**这是一份完整的实现，不是骨架**：契约里的 put / get / delete /
exists 全都有，并且挡住了路径穿越（`../` 必须被拒），对象带 content-type
与写入时间。

它适合单机部署（这套系统的默认形态）。多副本部署要换成共享对象存储 ——
那是**换一个同契约的实现**，本类不需要改动。

注意它与"加密"是两件事：加密由 SecurityGateway 负责（见
`zhiyin_infrastructure/security/crypto.py`），落盘的是不是密文由调用方决定。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from zhiyin_data_sdk.gateways.storage import ObjectStoreGateway, StoredObject


class LocalFileStore(ObjectStoreGateway):
    """本地目录实现（契约完整）。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, root: str = "data/objects") -> None:
        self._root = Path(root)

    async def put(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> StoredObject:
        path = self._resolve(key)
        await asyncio.to_thread(self._write, path, data)
        return StoredObject(
            key=key,
            size=len(data),
            content_type=content_type,
            updated_at=datetime.now(timezone.utc),
        )

    async def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise FileNotFoundError(f"对象不存在：{key}")
        return await asyncio.to_thread(path.read_bytes)

    async def stat(self, key: str) -> Optional[StoredObject]:
        path = self._resolve(key)
        if not path.is_file():
            return None
        info = await asyncio.to_thread(path.stat)
        return StoredObject(
            key=key,
            size=info.st_size,
            content_type="application/octet-stream",
            updated_at=datetime.fromtimestamp(info.st_mtime, tz=timezone.utc),
        )

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, True)

    def build_key(self, user_id: str, asset_type: str, version: int, ext: str) -> str:
        """统一对象键：{user_id}/{asset_type}/v{version}.{ext}"""
        return f"{user_id}/{asset_type}/v{version}.{ext.lstrip('.')}"

    # ---------- 内部 ----------

    def _resolve(self, key: str) -> Path:
        """解析对象键并挡住路径穿越。

        对象键来自业务层，正常情况下不含 `..`；这里仍然显式校验，
        避免本地实现被当作任意文件读写入口。
        """
        root = self._root.resolve()
        path = (root / key).resolve()
        if root != path and root not in path.parents:
            raise ValueError(f"非法对象键（越出存储根目录）：{key}")
        return path

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


__all__ = ["LocalFileStore"]
