"""2026-10-17 新人全流程测试里修掉的三类问题，各留一条回归。

1. 采集门槛不能被"回答式 intent"永久挡住（用户在答问题，不是要求回到采集）；
2. 资产创建提议要在同一会话里保留，不因中间插一句别的话而消失；
3. 图片/二进制材料必须在上传阶段明确拒绝，不能"成功"后给模型一串乱码。
"""


import pytest

from zhiyin_data_sdk.gateways.documents import DocumentReadError
from zhiyin_infrastructure.textfile import LocalTextExtractor






















def test_png_material_is_rejected_at_upload_stage():
    extractor = LocalTextExtractor()
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 64
    with pytest.raises(DocumentReadError) as excinfo:
        extractor.extract_text(png, filename="qa-1x1.png")
    message = str(excinfo.value)
    assert "暂不支持直接读取图片" in message
    assert "TXT" in message or "文字" in message


def test_binary_without_suffix_is_rejected_by_content_sniff():
    extractor = LocalTextExtractor()
    payload = (b"\x00\x01\x02\x03\x04\x05" * 40) + b"tail"
    with pytest.raises(DocumentReadError) as excinfo:
        extractor.extract_text(payload, filename="upload")
    assert "二进制" in str(excinfo.value)


def test_plain_text_still_reads():
    extractor = LocalTextExtractor()
    assert extractor.extract_text("课程名称\t成绩\n数据结构\t90".encode("utf-8"), filename="grades.txt")
