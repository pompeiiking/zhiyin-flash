"""DeepSeek 对话模型适配器。"""

from __future__ import annotations

from zhiyin_infrastructure.ai.openai_compat import OpenAICompatibleLLMGateway


class DeepSeekLLMGateway(OpenAICompatibleLLMGateway):
    """DeepSeek Chat Completions 适配器。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-flash",
    ) -> None:
        normalized = "deepseek-flash" if model in {"ds-flash", "ds_flash"} else model
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=normalized,
            provider_name="deepseek",
        )


__all__ = ["DeepSeekLLMGateway"]
