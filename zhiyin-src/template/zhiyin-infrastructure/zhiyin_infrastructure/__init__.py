"""zhiyin-infrastructure · 基础设施层。

职责：实现 data-sdk 定义的 Repository 与 Gateway 接口，统一使用自有本地实现，
保证系统能独立跑通、不依赖外部平台。

约束：本层实现接口，不得反向被上层 import；所有实现类必须只依赖接口。
"""

__all__ = [
    "ai",
    "auth",
    "chsi",
    "local",
    "postgres",
    "rag",
    "redis",
    "workers",
    "xuezhi",
]
