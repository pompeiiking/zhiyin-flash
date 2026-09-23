"""文件 → 文本的本地实现（纯函数，不联网）。

它是 `DocumentTextGateway` 的默认实现，也是课表/成绩导入那一侧的解码出口
（`ManualAcademicImporter.read_text` 复用的就是这里）。两处必须一致：
"粘贴能读、上传读不出"这种同一份数据两种结果，看着像两个 bug，其实是
两个各自实现的解码器。

三个必须处理的坑：

1. **编码**。教务系统导出的 CSV / TXT 有一半是 GBK（简体中文 Windows 的默认），
   按 UTF-8 硬读会得到一片乱码 —— 乱码不是"读不出"，它会一路走进解析器或模型，
   最后报"读不出这是课表"，而用户的文件其实完全正确；
2. **二进制文件**。Excel（.xlsx）是个压缩包，解码出来必然是乱码。
   与其让他看乱码，不如当场说清楚"另存为 CSV，或者把表格选中复制粘贴"；
3. **BOM**。带 BOM 的 UTF-8 会在首个字段前多一个看不见的字符，
   表头的"课程名称"就此认不出来 —— 导入失败，错却在看不见的地方。
"""

from __future__ import annotations

import codecs
from pathlib import PurePosixPath

from zhiyin_data_sdk.gateways.documents import DocumentReadError, DocumentTextGateway

"""字节序标记 → 编码。**UTF-32 必须排在 UTF-16 前面**：
它的 BOM（FF FE 00 00）以 UTF-16 的 BOM（FF FE）开头，顺序反了就会读错。"""
_BOM_ENCODINGS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

"""没有 BOM 时按顺序试：UTF-8 优先（现在的导出多是它），再试 GB18030。
GB18030 是 GBK 的超集，且几乎能吃下任意字节 —— 所以它放在最后当兜底。"""
_TRY_ENCODINGS: tuple[str, ...] = ("utf-8", "gb18030")

"""读不了的二进制格式 → 给用户看的名字。

按**后缀**判断（不是看内容里有没有空字节）：内容判断会把某种少见的纯文本编码误判，
而后缀是用户自己知道的、也能自己改的一件事（"另存为 CSV"）。
"""
_BINARY_SUFFIXES: dict[str, str] = {
    ".xlsx": "Excel 工作簿",
    ".xls": "Excel 工作簿",
    ".xlsm": "Excel 工作簿",
    ".docx": "Word 文档",
    ".doc": "Word 文档",
    ".pdf": "PDF",
    ".zip": "压缩包",
    ".rar": "压缩包",
    ".7z": "压缩包",
}


def decode_text(data: bytes) -> str:
    """把文件字节读成文本。空输入返回空串（由上层给出"文件是空的"那句话）。"""
    if not data:
        return ""
    for bom, encoding in _BOM_ENCODINGS:
        if data.startswith(bom):
            # `lstrip`：有些导出会在 BOM 之外再多一个 U+FEFF，留着它表头就认不出来
            return data.decode(encoding, errors="replace").lstrip("\ufeff")
    for encoding in _TRY_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def unsupported_reason(filename: str) -> str:
    """这个文件是不是我们**明确读不了**的二进制格式；是就返回给用户看的一句话。

    读得了（或后缀认不出）返回空串 —— 认不出后缀时按文本试一次，
    真读不出由上层报"读不出这是课表"，那句话本身就是可执行的。
    """
    suffix = PurePosixPath((filename or "").replace("\\", "/")).suffix.lower()
    label = _BINARY_SUFFIXES.get(suffix)
    if not label:
        return ""
    return (
        f"「{label}」（{suffix}）是二进制文件，我读不了 —— "
        "在 Excel 里「另存为 CSV」再传，或者把表格连表头一起选中、复制粘贴进来。"
    )


class LocalTextExtractor(DocumentTextGateway):
    """默认实现：本地解码（编码识别 + 二进制格式当场拒绝）。

    `IMPLEMENTATION_STATUS` 报 wired：它真的把第一版要支持的那几种形态读全了
    （txt / csv / json / html，任意常见编码）。PDF / Word 不是"还没实现"，
    而是**有意不收**：本地解不出正文，收下来只能给用户一段乱码。
    第二期换成带版面解析的实现时，换的就是这个类。
    """

    IMPLEMENTATION_STATUS = "wired"

    def extract_text(self, data: bytes, *, filename: str = "") -> str:
        reason = unsupported_reason(filename)
        if reason:
            raise DocumentReadError(reason, detail=f"suffix={filename}")
        text = decode_text(data)
        if not text.strip():
            label = filename or "这个文件"
            raise DocumentReadError(
                f"「{label}」里没有读到文字 —— 确认传的是导出出来的那一份，"
                "或者把里面的内容选中、复制粘贴进来。",
                detail=f"bytes={len(data)}",
            )
        return text


__all__ = ["LocalTextExtractor", "decode_text", "unsupported_reason"]
