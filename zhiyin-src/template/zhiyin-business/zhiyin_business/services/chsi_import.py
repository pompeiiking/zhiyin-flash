"""PDF preview and commit, sharing report rules without claiming online verification."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from zhiyin_business.contracts.chsi_import import ChsiPdfPreview, PdfFieldPreview, ChsiPdfReceipt
from zhiyin_business.services.enrollment_report import EnrollmentReportService, check_report_identity
from zhiyin_data_sdk.gateways.chsi import ChsiReport, ChsiVerifyError
from zhiyin_kernel.chsi_dates import parse_chsi_date, is_report_expired
from zhiyin_kernel.academic_time import study_year_from_enrollment
from zhiyin_kernel.enums import ProfileVerification
from zhiyin_kernel.errors import InvalidRequest, ResourceNotFound, DuplicateResource


def now():
    return datetime.now(timezone.utc)


def snapshot(field):
    if field is None:
        return None
    return {"entry_version": field.entry_version, "updated_at": field.updated_at.isoformat()}


class ChsiPdfImportService:
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, profiles, records, reader, registry):
        self.profiles, self.records, self.reader, self.registry = profiles, records, reader, registry
        self.reports = EnrollmentReportService(profiles)

    async def preview(self, user_id, data):
        report = await self.reader.read(data)
        report.acquisition = "pdf"
        report.code = report.raw_excerpt = report.source_url = report.verified_at = ""
        existing = {field.key: field for field in await self.profiles.get_fields(user_id)}
        warnings, allowed = [], True
        try:
            check_report_identity(report, existing)
        except ChsiVerifyError as exc:
            warnings.append(str(exc))
            allowed = False
        expiry = report.valid_until
        if is_report_expired(expiry):
            warnings.append("报告已过有效期，请到学信网延长有效期并重新下载后导入。")
            allowed = False
        elif parse_chsi_date(expiry) is None:
            warnings.append("无法判断有效期；导入仅作为材料记录，不代表当前学籍已核验。")
        matched = any(existing.get(key) and report.value_of(key) for key in ("student_name", "student_no"))
        ownership_required = not matched
        if ownership_required:
            warnings.append("画像缺少可比对的身份信息，请确认这是本人的报告。")
        specs = {item.key: item for item in await self.registry.list_chsi_fields()}
        if not specs:
            raise InvalidRequest("学籍字段清单暂不可用，请稍后再试。")
        preview_id = "chsi-pdf-" + uuid4().hex
        applied = await self.reports.apply(user_id, report, existing, specs, write=False,
            origin_ref="chsi-pdf://imports/" + preview_id, check_identity=False)
        entries, fields = applied["entries"], []
        for entry in entries:
            key, reason = entry["key"], ""
            old = existing.get(key)
            if old and old.value == entry["value"]:
                reason = "与已有资料相同，保留原记录。"
            elif old and old.verification is ProfileVerification.VERIFIED:
                reason = "已有在线核验资料，PDF 不覆盖。"
            selectable = not reason and allowed
            fields.append(PdfFieldPreview(key=key, label=entry.get("label") or (specs[key].label if key in specs else "学习阶段"),
                value=entry["value"], current_value=old.value if old else None,
                selectable=selectable, selected=selectable and old is None, reason=reason))
        if report.value_of("enrolled_at") and existing.get("study_year") and not any(f.key == "study_year" for f in fields):
            derived = study_year_from_enrollment(report.value_of("enrolled_at"))
            current = existing["study_year"].value
            reason = "保留当前学习阶段，不自动覆盖；推算值仅供核对。"
            if derived and derived != current:
                reason = f"年级不一致：按入学日期推算为{derived}，当前填写为{current}。保留当前值，请在个人画像中核对并更正。"
                warnings.append(reason)
            elif derived is None:
                reason = "无法按报告入学日期推算当前学习阶段，保留当前值，请在个人画像中核对。"
            fields.append(PdfFieldPreview(key="study_year", label="学习阶段", value=derived,
                current_value=current, selectable=False, reason=reason))
        expires = (now() + timedelta(minutes=30)).isoformat()
        if allowed and not any(field.selectable for field in fields):
            warnings.append("没有可导入的新字段，已有资料和核实状态均已保留。")
        result = ChsiPdfPreview(preview_id=preview_id, expires_at=expires,
            report_date=report.report_date, valid_until=expiry, fields=fields, warnings=warnings,
            can_import=allowed and any(f.selectable for f in fields), requires_ownership_confirmation=ownership_required)
        involved = {entry["key"] for entry in entries} | {"student_name", "student_no", "study_year"}
        payload = {"report": report.model_dump(mode="json"), "preview": result.model_dump(mode="json"),
                   "snapshots": {key: snapshot(existing.get(key)) for key in involved}}
        await self.records.create({"id": preview_id, "user_id": user_id, "file_hash": sha256(data).hexdigest(),
                                   "status": "pending", "expires_at": expires, "payload": payload})
        return result

    async def confirm(self, user_id, request):
        changed = []
        async with self.records.locked(user_id, request.preview_id) as row:
            if row is None:
                raise ResourceNotFound("预览不存在或已过期，请重新上传报告。")
            if row["status"] == "committed":
                return ChsiPdfReceipt.model_validate(row["receipt"])
            if datetime.fromisoformat(row["expires_at"]) <= now():
                raise InvalidRequest("预览已过期，请重新上传报告。")
            payload = row["payload"]
            preview = ChsiPdfPreview.model_validate(payload["preview"])
            if not preview.can_import:
                raise InvalidRequest("这份报告暂不能导入，请按预览提示处理。")
            if preview.requires_ownership_confirmation and not request.ownership_confirmed:
                raise InvalidRequest("请先确认这是本人的学籍报告。")
            selected = set(request.selected_keys)
            selectable = {field.key for field in preview.fields if field.selectable}
            if not selected or not selected <= selectable:
                raise InvalidRequest("请选择可导入字段；已核验或受保护字段不能覆盖。")
            existing = {field.key: field for field in await self.profiles.get_fields(user_id)}
            for key, before in payload["snapshots"].items():
                if snapshot(existing.get(key)) != before:
                    raise DuplicateResource("画像已发生变化，请重新上传并核对预览。")
            report = ChsiReport.model_validate(payload["report"])
            check_report_identity(report, existing)
            if is_report_expired(report.valid_until):
                raise InvalidRequest("报告已过有效期，请延长有效期后重新下载。")
            specs = {item.key: item for item in await self.registry.list_chsi_fields()}
            applied = await self.reports.apply(user_id, report, existing, specs, write=False,
                origin_ref="chsi-pdf://imports/" + request.preview_id)
            entries = [entry for entry in applied["entries"] if entry["key"] in selected]
            if {entry["key"] for entry in entries} != selected:
                raise DuplicateResource("学籍字段规则已变化，请重新上传并核对。")
            for entry in entries:
                field = existing.get(entry["key"])
                if field and field.verification is ProfileVerification.VERIFIED:
                    raise DuplicateResource("已有在线核验资料，请重新核对。")
                entry["expected_updated_at"] = field.updated_at if field else None
            changed = await self.profiles.write_report_entries(user_id, entries)
            receipt = ChsiPdfReceipt(import_id=request.preview_id, imported_at=now().isoformat(),
                imported=sorted(selected), retained=[f.key for f in preview.fields if f.selectable and f.key not in selected],
                skipped=[f.key for f in preview.fields if not f.selectable])
            await self.records.finish(user_id, request.preview_id, receipt.model_dump(mode="json"))
        for key in changed:
            await self.profiles.refresh_report_assessment(user_id, key)
        return receipt
