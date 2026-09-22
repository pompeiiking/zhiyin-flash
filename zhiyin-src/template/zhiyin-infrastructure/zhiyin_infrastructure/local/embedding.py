"""本地确定性嵌入（LocalHashEmbedder）—— 骨架实现，显式标记。

**它不是语义嵌入。** 用文本的哈希生成固定维度向量，只保证两件事：
确定性（同样输入同样输出）与形状正确（可被向量库写入 / 检索）。
它的用途是让向量链路在真实嵌入模型接入前可跑、可测，**不得用于评估检索质量**。

`IMPLEMENTATION_STATUS = "skeleton"` 会让 `/healthz` 与 `--check` 如实标注它，
避免"装上了向量检索"的误读。

实现同一份 `EmbedGateway` 契约。
"""

from __future__ import annotations

import hashlib

from zhiyin_data_sdk.gateways.ai import EmbedGateway


class LocalHashEmbedder(EmbedGateway):
    """哈希伪向量。仅用于打通链路与测试，不具备语义区分能力。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self, dim: int = 64, model_id: str = "local-hash-demo") -> None:
        if dim <= 0:
            raise ValueError("dim 必须为正数")
        self._dim = dim
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    async def embed(self, texts: list[str], *, timeout_s: float = 30.0) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # 用摘要字节循环铺满维度，再归一到 [-1, 1]，保证向量非零、可直接算余弦。
        raw = [digest[i % len(digest)] / 255.0 * 2 - 1 for i in range(self._dim)]
        norm = sum(value * value for value in raw) ** 0.5 or 1.0
        return [round(value / norm, 6) for value in raw]


__all__ = ["LocalHashEmbedder"]
