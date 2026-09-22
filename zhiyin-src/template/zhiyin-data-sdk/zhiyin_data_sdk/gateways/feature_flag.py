"""功能开关契约（FeatureFlagGateway）。

为什么单独成一个 Gateway，而不是并进 `RegistryRepository`：
两者的访问特征不同——`RegistryRepository` 读的是**内容型**动态资源
（智能体 / 理论卡 / 产出契约 / 任务入口 / 菜单 / 文案），调用点在业务服务内部；
功能开关是**配置型**动态资源，特点是"读得极频繁、写入极少、必须可缓存"，
调用点是 BFF 启动装配与是否开放功能块。混进同一个 Repository 会让
"读一次内容"和"读一个布尔值"共用一条取数路径。

口径（系统配置）：
- 开关是动态资源，**不得硬编码在代码或 Settings 里**；
- 未知开关一律按"关闭"处理（`default=False`），配置漏了不能反而把功能打开；
- 第一期读 `data/registry/feature_flags.json`，第二期换 `feature_flag` 表时只替换实现。

IO 口径：与其它 Gateway 一致，**公开方法一律 async**。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class FeatureFlagGateway(ABC):
    """功能开关读取。"""

    @abstractmethod
    async def all(self) -> dict[str, bool]:
        """读取全部开关。返回快照，调用方改它不影响实现内部缓存。"""

    @abstractmethod
    async def is_enabled(self, code: str, default: bool = False) -> bool:
        """读取单个开关。未登记的开关返回 `default`。"""


__all__ = ["FeatureFlagGateway"]
