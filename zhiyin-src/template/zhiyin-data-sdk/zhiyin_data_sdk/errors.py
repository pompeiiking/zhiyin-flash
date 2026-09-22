"""SDK 统一异常。

约束（对应 R-SDK-007）：
业务层不感知具体基础设施错误，只感知本模块定义的异常。

与 `zhiyin_kernel.errors` 的分工（**不要建第二套**）：

- **语义错误分类**（资源不存在 / 未授权 / 输入不合法 / 冲突）在 `zhiyin_kernel.errors`。
  它们在所有层都能读到，是 api 层翻译统一信封时唯一认识的类型；
- **本模块只留基础设施自己的失败信号**：`MissingConfigError`（缺配置，故意不兜底）
  与本基类的 `retryable` / `detail` 语义。

此前这里另有 `NotFoundError` / `ConflictError` / `UnavailableError`，但全仓没有任何
raise 与订阅点 —— 它们与内核那套是同一能力的两个名字，已删除。
"""

from __future__ import annotations

from typing import Any, Optional


class SdkError(Exception):
    """SDK 异常基类。"""

    code: str = "SDK_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        detail: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}
        self.cause = cause

    def __str__(self) -> str:  # pragma: no cover - 便于日志排查
        return f"[{self.code}] {self.message}"


class ValidationError(SdkError):
    """数据不满足契约约束。"""

    code = "VALIDATION"


class MissingConfigError(SdkError):
    """动态资源配置缺失。

    为什么不给默认值、不做兜底：配置漏了却静默回落，症状会跑到很远的地方 ——
    提示词缺席时模型只是"变得不太会说话"，交接告知缺一条时用户只看到半句话，
    而没有任何一处会报出来。等有人发现"今天它怎么怪怪的"，已经找不到是哪一天
    少了哪一条了。缺配置就是缺配置，直接抛。
    """

    code = "MISSING_CONFIG"
