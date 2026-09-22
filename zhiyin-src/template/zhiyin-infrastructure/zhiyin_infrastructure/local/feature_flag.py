"""本地功能开关（LocalFeatureFlagStore）。

为什么单独成文件：功能开关属于**动态资源**（系统配置），
"文案、开关、规则不允许散落在代码里"。此前 `Settings.feature_flags` 把开关写死在
Python 常量里，等于给后续留了一个硬编码入口，这里改成读 `feature_flags.json`。

文件位置：`{data_dir}/feature_flags.json`，形状 `{"items": [{"code":..., "enabled":...}]}`
或 `{"code": true, ...}`。第二期换 `feature_flag` 表时只替换本类。

契约在 `zhiyin_data_sdk.gateways.feature_flag.FeatureFlagGateway`：
本类实现它，因此 BFF 侧的业务读服务可以在**不认识本地实现**的前提下拿到开关
（api 被禁止 import data_sdk，业务服务只面向 SDK 契约）。公开方法是 async——
与其它 Gateway 一致，换配置实现时调用方一行不改。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from zhiyin_data_sdk.gateways.feature_flag import FeatureFlagGateway


class LocalFeatureFlagStore(FeatureFlagGateway):
    """功能开关读取。默认关闭未知开关，避免"配置漏了反而打开"。"""

    FILENAME = "feature_flags.json"
    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self, data_dir: str = "data/registry") -> None:
        self._path = Path(data_dir) / self.FILENAME
        self._cache: Optional[dict[str, bool]] = None

    async def all(self) -> dict[str, bool]:
        if self._cache is None:
            self._cache = self._read()
        return dict(self._cache)

    async def is_enabled(self, code: str, default: bool = False) -> bool:
        return (await self.all()).get(code, default)

    def reload(self) -> None:
        """清缓存，用于演示"改开关不重启"。"""
        self._cache = None

    def _read(self) -> dict[str, bool]:
        if not self._path.is_file():
            return {}
        raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            items = raw.get("items")
            if isinstance(items, list):
                return {
                    str(item["code"]): bool(item.get("enabled", False))
                    for item in items
                    if isinstance(item, dict) and "code" in item
                }
            return {
                str(key): bool(value)
                for key, value in raw.items()
                if not str(key).startswith("_") and isinstance(value, bool)
            }
        return {}


__all__ = ["LocalFeatureFlagStore"]
