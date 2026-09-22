"""豆包 Ark embedding 适配器。"""

from __future__ import annotations

from zhiyin_infrastructure.ai.openai_compat import OpenAICompatibleEmbeddingGateway


class DoubaoEmbeddingGateway(OpenAICompatibleEmbeddingGateway):
    """豆包 Ark Embeddings 适配器。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "doubao-embedding-text-240715",
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name="doubao-ark",
        )


__all__ = ["DoubaoEmbeddingGateway"]
