"""在线验证报告核验 Gateway：把客户端的原始页面收成一个可靠的结果。"""

from __future__ import annotations

from typing import Any

from zhiyin_data_sdk.gateways.chsi import (
    ChsiReport,
    ChsiVerificationGateway,
    ChsiVerifyError,
    ChsiVerifyErrorKind,
)
from zhiyin_infrastructure.chsi.client import (
    ChsiReportClient,
    classify_error,
    detect_error,
    is_well_formed,
    normalize_code,
    parse_report,
    verified_at_now,
)


class OnlineVerificationGateway(ChsiVerificationGateway):
    """基于学信网"在线验证"服务的核验实现。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, client: ChsiReportClient) -> None:
        self._client = client
        self._last_verify_at = ""

    async def verify(self, code: str) -> ChsiReport:
        normalized = normalize_code(code)
        if not is_well_formed(normalized):
            raise ChsiVerifyError(
                "这串码的格式不对：应为 12 位数字，或以 A / X 开头的 16 位码。",
                kind=ChsiVerifyErrorKind.MALFORMED_CODE,
            )

        page, source_url = await self._client.fetch_report_html(normalized)

        message = detect_error(page)
        if message:
            raise ChsiVerifyError(message, kind=classify_error(message))

        kind, fields, excerpt = parse_report(page, code=normalized)
        if not fields:
            # 拿得到页面却读不出字段：几乎一定是学信网改了版式。
            # 把正文摘录带出去，让人能立刻看出是哪里变了，而不是只看到一个"失败"。
            raise ChsiVerifyError(
                "核验成功，但报告版式与预期不一致，读不出字段。",
                kind=ChsiVerifyErrorKind.UNPARSEABLE,
                detail=excerpt,
            )

        report_no = next(
            (field.value for field in fields if field.key == "chsi_report_no"), ""
        )
        self._last_verify_at = verified_at_now()
        return ChsiReport(
            code=normalized,
            kind=kind,
            report_no=report_no,
            fields=fields,
            verified_at=self._last_verify_at,
            source_url=source_url,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "base_url": self._client.base_url,
            "last_verify_at": self._last_verify_at,
            "mode": "online_verification_code",
        }


__all__ = ["OnlineVerificationGateway"]
