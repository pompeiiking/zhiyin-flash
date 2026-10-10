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
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import ZipFile

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
    """本地读取文本、带文字的 PDF 和 DOCX（含表格、页眉页脚）。"""

    IMPLEMENTATION_STATUS = "wired"

    def extract_text(self, data: bytes, *, filename: str = "") -> str:
        if len(data) > 10 * 1024 * 1024:
            raise DocumentReadError("文件超过 10 MB，请只保留简历正文后重新上传。")
        suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
        try:
            if suffix == ".pdf" or data.startswith(b"%PDF-"):
                text = self._pdf(data)
            elif suffix == ".docx":
                text = self._docx(data)
            elif suffix == ".doc":
                raise DocumentReadError("请在 Word 中将这份旧版文档另存为 .docx，再上传。")
            else:
                reason = unsupported_reason(filename)
                if reason:
                    raise DocumentReadError(reason, detail=f"suffix={filename}")
                if data.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
                    raise DocumentReadError("文件格式与名称不一致，请按原始格式重新导出后上传。")
                text = decode_text(data)
        except DocumentReadError:
            raise
        except Exception as exc:
            raise DocumentReadError(
                "这份文件未能读取，请重新导出 PDF 或 Word（.docx），也可以粘贴正文。",
                detail=type(exc).__name__,
            ) from exc
        if len(text) > 150_000:
            raise DocumentReadError("正文过长，请只保留需要分析的简历或材料后上传。")
        if not text.strip():
            label = filename or "这个文件"
            raise DocumentReadError(
                f"「{label}」里没有读到文字 —— 确认传的是导出出来的那一份，"
                "或者把里面的内容选中、复制粘贴进来。",
                detail=f"bytes={len(data)}",
            )
        return text

    @staticmethod
    def _pdf(data: bytes) -> str:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentReadError("这份 PDF 有打开密码，请导出不带密码的副本后上传。")
        if len(reader.pages) > 50:
            raise DocumentReadError("PDF 超过 50 页，请只保留需要分析的部分后上传。")
        parts = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(parts)
        if not text.strip():
            raise DocumentReadError("这份 PDF 没有可读取的文字，可能是扫描件；请导出带文字的 PDF 或粘贴正文。")
        return text

    @staticmethod
    def _docx(data: bytes) -> str:
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with ZipFile(BytesIO(data)) as archive:
            names = ["word/document.xml"] + sorted(
                name for name in archive.namelist()
                if name.startswith(("word/header", "word/footer")) and name.endswith(".xml")
            )
            if sum(archive.getinfo(name).file_size for name in names) > 20 * 1024 * 1024:
                raise DocumentReadError("Word 正文过大，请只保留简历内容后上传。")
            paragraphs = []
            for name in names:
                root = ElementTree.fromstring(archive.read(name))
                for paragraph in root.iter(ns + "p"):
                    parts = []
                    for element in paragraph.iter():
                        if element.tag == ns + "t":
                            parts.append(element.text or "")
                        elif element.tag == ns + "tab":
                            parts.append("\t")
                        elif element.tag in (ns + "br", ns + "cr"):
                            parts.append("\n")
                    paragraphs.append("".join(parts))
            return "\n".join(paragraphs)


__all__ = ["LocalTextExtractor", "decode_text", "unsupported_reason"]
