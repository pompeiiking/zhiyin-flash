"""AI 模型基础设施实现。

DeepSeek 负责对话生成，豆包 Ark 负责 embedding。
"""

from zhiyin_infrastructure.ai.deepseek import DeepSeekLLMGateway
from zhiyin_infrastructure.ai.doubao import DoubaoEmbeddingGateway

__all__ = ["DeepSeekLLMGateway", "DoubaoEmbeddingGateway"]
