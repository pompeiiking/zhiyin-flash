"""文档正文抽取 Gateway：把「用户带上来的文件」读成文本。

为什么它是一个能力位，而不是几行工具函数
--------------------------------------
用户在两个地方会把文件交给我们：导入课表/成绩（`academic`），
以及在对话里交一份材料（简历、证书、课程说明…）。两处要的是**同一件事**：
一堆字节 → 一段能读的文本。这里面藏着两件必须统一处理的事：

1. **编码**：教务系统导出的 CSV / TXT 有一半是 GBK，按 UTF-8 硬读会得到乱码 ——
   而乱码不是"读不出"，它会一路走到解析或模型那边，变成一句谁也看不懂的东西；
2. **格式**：Excel / PDF / 图片是二进制，本地解不出来。与其让用户看到乱码，
   不如当场说清"另存为 CSV / 导出成 txt 再传"。

收成一个能力位还为了**第二期**：这两件事迟早要换成真正的文档解析服务
（PDF / Word / OCR、甚至带版面的表格识别）。那时换的是这个能力位的实现，
业务代码一行不动 —— 而如果它散在业务层，换解析服务就等于改业务。

边界：不联网、不写任何东西、不落库。它就是"字节 → 文本"。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class DocumentReadError(Exception):
    """这份文件读不出文本。

    `message` 是**给用户看的那句话**（"这是 Excel，先另存为 CSV"），
    不是给排查用的堆栈描述 —— 它会被原样显示在界面上。
    """

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


class DocumentTextGateway(ABC):
    """文本抽取 Port。"""

    @abstractmethod
    def extract_text(self, data: bytes, *, filename: str = "") -> str:
        """把文件字节读成文本。

        读不了时抛 `DocumentReadError`，消息里要写明用户能自己做的那一步
        （另存为 CSV / 重新导出 / 换成 txt）。空文件也算读不了 ——
        返回空串会让上游以为"读到了，只是没有内容"。
        """


__all__ = ["DocumentReadError", "DocumentTextGateway"]
