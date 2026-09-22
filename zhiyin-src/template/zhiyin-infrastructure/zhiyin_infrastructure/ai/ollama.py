"""Ollama 本地模型适配器（OpenAI 兼容协议）。

为什么用它
----------
云端嵌入（豆包 Ark）要一个能用的接入点，且每次索引与每次检索都要出网。
本机 Ollama 上已经拉好的嵌入模型（如 `qwen3-embedding:4b`，2560 维）是**真模型**：
语义是真算出来的，与云端只差精度与速度，`/healthz` 里同样报 `wired`。

两条容易踩的地方
----------------
1. **地址是"容器视角"的宿主**：docker 里的 `host.docker.internal:11434`；
   直接在宿主机上跑（无容器）时是 `127.0.0.1:11434`。所以 base_url 必须可配，
   不要写死在代码里。
2. **Ollama 不校验密钥**，但基类拒绝空 key。这里给一个占位值 ——
   这不是"绕过校验"，是如实描述：这一家本来就没有密钥这个概念。

注意维度：换嵌入模型必须重建向量库（不同模型的向量不在一个空间里，
pgvector 连维度都对不上）。向量同步 Worker 会因为模型版本变化自动重嵌，
前提是旧向量已经按新模型全量覆盖（见 `infra_vector_sync_state`）。
"""

from __future__ import annotations

from zhiyin_infrastructure.ai.openai_compat import OpenAICompatibleEmbeddingGateway


class OllamaEmbeddingGateway(OpenAICompatibleEmbeddingGateway):
    """Ollama 的 `/v1/embeddings`（OpenAI 兼容）适配器。"""

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "http://host.docker.internal:11434/v1",
        model: str = "qwen3-embedding:4b",
    ) -> None:
        super().__init__(
            api_key=api_key or "ollama",
            base_url=base_url,
            model=model,
            provider_name="ollama",
        )


__all__ = ["OllamaEmbeddingGateway"]
