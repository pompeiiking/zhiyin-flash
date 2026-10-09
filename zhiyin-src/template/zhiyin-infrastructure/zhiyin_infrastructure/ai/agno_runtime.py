"""agno 框架运行时（AI 面向切面的"框架维护"切面，见设计文档第六章 6.5）。

分层口径：
- **本模块（基础设施层）**负责 agno 框架对象的**构建与配置维护**——供应商密钥、
  base_url、模型名、温度、角色映射（agno 默认把 system 映射成 OpenAI 新式
  `developer` 角色，DeepSeek 等兼容服务只认 `system`，必须在这里拉回）。
  框架升级 / 换供应商只改这里，编排层与业务层无感；
- **编排层**（`zhiyin_orchestration`）只做智能体**组装与编排**：它拿到的是
  本运行时产出的模型对象，不接触任何配置。依赖守卫
  （`test_architecture.py`）规定编排层不得 import 基础设施层，
  因此模型对象由装配层（zhiyin-boot）注入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agno.models.openai import OpenAIChat

# DeepSeek / 大多数 OpenAI 兼容服务只认 system 角色
_DEFAULT_ROLE_MAP = {
    "system": "system",
    "user": "user",
    "assistant": "assistant",
    "tool": "tool",
}


@dataclass
class AgnoModelRuntime:
    """agno 模型客户端运行时：配置的持有者与模型对象的工厂。"""

    api_key: str
    base_url: str
    model: str
    temperature: float = 0.2
    role_map: dict[str, str] | None = None
    timeout_s: float | None = None

    def apply(self, *, api_key: str, base_url: str, model: str) -> bool:
        """用**库里的配置**覆盖启动时的种子值。返回是否真的变了。

        为什么是"改字段"而不是"换一个运行时对象"：
        编排层拿到的是 `create_model` 这个绑定方法，一个对象身份换来换去，
        引擎里那份引用就悄悄指向旧配置了 —— 那种 bug 表现为"改了库没生效"，
        而且只在重启后第一次调用时才看得出。原地改字段没有这个缝。
        """
        changed = (api_key, base_url, model) != (self.api_key, self.base_url, self.model)
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        return changed

    def create_model(
        self,
        *,
        temperature: float | None = None,
        timeout_s: float | None = None,
        retries: int | None = None,
    ) -> Any:
        """构造一个 agno 模型客户端。

        温度、超时和重试由调用方按该提示词的 params 传入；未声明的参数
        沿用运行时或框架默认值，避免配置表显示已设置但实际调用没有生效。

        返回类型保持 `Any`（编排层只依赖"能被 agno Agent 接受"这一事实），
        避免基础设施的类型反渗进编排层。
        """
        return OpenAIChat(
            id=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature if temperature is None else temperature,
            role_map=dict(self.role_map or _DEFAULT_ROLE_MAP),
            **({"timeout": timeout_s if timeout_s is not None else self.timeout_s}
               if timeout_s is not None or self.timeout_s else {}),
            **({"retries": retries} if retries is not None else {}),
        )


__all__ = ["AgnoModelRuntime"]
