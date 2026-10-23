"""Private subprocess entry point. stdin=PDF, stdout=allowlisted JSON only."""
import io
import json
import re
import sys


class ReportPdfError(ValueError):
    pass


def extract(data):
    from pypdf import PdfReader
    from zhiyin_infrastructure.chsi.client import parse_fields
    from zhiyin_data_sdk.gateways.chsi import ChsiReport, ChsiReportKind
    from zhiyin_kernel.chsi_dates import parse_chsi_date

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ReportPdfError("报告已加密，请重新下载未加密的原版 PDF。")
    if not 1 <= len(reader.pages) <= 3:
        raise ReportPdfError("学籍报告最多支持 3 页，请上传单份原版报告。")
    text = "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)
    if len(text) > 50_000:
        raise ReportPdfError("报告文字过多，请上传单份学籍报告。")
    if not text.strip():
        raise ReportPdfError("没有读取到文字，暂不支持扫描件或截图，请下载原版 PDF。")
    if "教育部学籍在线验证报告" not in re.sub(r"\s+", "", text):
        raise ReportPdfError("请上传中文版《教育部学籍在线验证报告》，不支持学历或学位报告。")
    # Stop before instructions/validation URLs: those are not report values.
    text = re.split(r"注意事项|报告内容验证办法|在线验证方式", text, maxsplit=1)[0]
    # PDF editions use both short and long labels.
    for short, full in [("入学时间", "入学日期"), ("预计毕业时间", "预计毕业日期")]:
        text = text.replace(short, full)
    text = re.sub(r"(?m)(^|\s)形式\s*[:：]?", r"\1学习形式：", text)
    allowed = {"student_name", "student_no", "school", "department", "major", "degree_level",
               "duration", "study_mode", "enrolled_at", "expected_graduation", "enrollment_status"}
    parsed = parse_fields(text, strict_labels=True)
    values = {field.key: field.value for field in parsed}
    if not all(values.get(key) for key in ("student_name", "school", "major")):
        raise ReportPdfError("报告中的姓名、学校或专业未能完整识别，请重新下载原版 PDF。")
    # Keep only canonical allowlisted fields. No codes, ID numbers or full text.
    fields = [field for field in parsed if field.key in allowed]
    expiry = values.get("valid_until", "")
    report_date = values.get("verified_date", "")
    for key in ("更新日期", "报告日期"):
        match = re.search(key + r"\s*[:：]?\s*([^\n]{1,30})", text)
        if match and not report_date:
            report_date = match.group(1).strip()
    return ChsiReport(acquisition="pdf", kind=ChsiReportKind.ENROLLMENT, fields=fields,
                      valid_until=expiry, report_date=report_date).model_dump(mode="json")


def main():
    try:
        if sys.platform != "win32":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        data = sys.stdin.buffer.read(2_000_001)
        if len(data) > 2_000_000:
            raise ReportPdfError("文件超过 2MB。")
        result = extract(data)
    except ReportPdfError as exc:
        result = {"error": str(exc)}
    except Exception:
        result = {"error": "PDF 已损坏或无法读取，请重新下载原版报告。"}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
