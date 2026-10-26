"""Shared institutional-report identity, whitelist, derivation and write rules."""
from datetime import datetime
from zhiyin_business.contracts.ai_tasks import ProfileLift
from zhiyin_data_sdk.gateways.chsi import ChsiReportKind, ChsiVerifyError, ChsiVerifyErrorKind
from zhiyin_kernel import academic_time, dynamic_config
from zhiyin_kernel.enums import ProfileSource, ProfileVerification

_DERIVED_STUDY_YEAR_REF = "derived://study_year/enrolled_at"

def origin_ref_label(origin_ref: str) -> str:
    """内部追溯引用 → 给学生看的一句话。

    origin_ref 承载的是幂等与溯源键（chsi-pdf://imports/<id>、derived://…），
    给模型或界面原样展示就是一串开发数据。http(s) 链接是真实出处，原样保留。
    """
    text = str(origin_ref or "").strip()
    if not text:
        return ""
    if text.startswith("chsi-pdf://"):
        return "学信网学籍报告（PDF 导入）"
    if text.startswith("derived://"):
        return "按入学日期推算"
    if text.startswith("conversation:"):
        return "对话原话"
    if text.startswith("material:") or text.startswith("material://"):
        return "上传材料"
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if "://" in text:
        return "系统内部记录"
    return text


def _same_identity(left: str, right: str, *, ignore_hyphen: bool = False) -> bool:
    """Compare the report identity with the saved profile identity.

    Whitespace and full/half-width spacing are ignored; student numbers also
    ignore separators. The point is to catch an obviously different report,
    not to create a second normalization standard for names.
    """
    def normalize(value: str) -> str:
        text = "".join(str(value or "").split()).casefold()
        return text.replace("-", "") if ignore_hyphen else text
    return normalize(left) == normalize(right)


def check_report_identity(report, existing):
    # A valid code is a bearer key to *someone's* report. Before writing,
    # reject an obvious identity mismatch instead of merging another
    # person's name/student number into the current profile. If the
    # profile has no identity yet, the user has explicitly chosen to
    # verify this code, so the first import is allowed.
    report_name = report.value_of("student_name")
    current_name = existing.get("student_name")
    if report_name and current_name and not _same_identity(report_name, current_name.value):
        raise ChsiVerifyError(
            "这份报告上的姓名与当前画像中的姓名不一致。请确认是本人的报告，或先在画像中更正姓名后再核验。",
            kind=ChsiVerifyErrorKind.IDENTITY_MISMATCH,
        )
    report_student_no = report.value_of("student_no")
    current_student_no = existing.get("student_no")
    if report_student_no and current_student_no and not _same_identity(
        report_student_no, current_student_no.value, ignore_hyphen=True
    ):
        raise ChsiVerifyError(
            "这份报告上的学号与当前画像中的学号不一致。请确认是本人的报告后再核验。",
            kind=ChsiVerifyErrorKind.IDENTITY_MISMATCH,
        )




class EnrollmentReportService:
    def __init__(self, profiles):
        self._profiles = profiles

    async def apply(self, user_id, report, existing, chsi_specs, *, write=True, origin_ref="", check_identity=True):
        if check_identity:
            check_report_identity(report, existing)
        entries = []
        async def save(user_id, key, value, **kwargs):
            if report.acquisition == "pdf":
                kwargs["origin_ref"] = origin_ref if key != "study_year" else kwargs["origin_ref"]
                # 原始证据只放**给人读的话**；chsi-pdf://imports/<id> 是内部追溯键，
                # 留在 origin_ref 里供幂等与来源核对 —— 卡片、报告引用都会原样
                # 带出 evidence，内部 URI 混进去就是用户眼里的"开发数据"。
                kwargs["evidence"] = ["用户上传学信网报告，待在线核验"]
                if key != "study_year":
                    kwargs["verification"] = ProfileVerification.RECORD.value
            entries.append({"key": key, "value": value, **kwargs})
            if write:
                await self._profiles.update_field(user_id, key, value, **kwargs)
        written: list[ProfileLift] = []
        detail_bits: list[str] = []
        # 学信网字段的"写哪些 / 叫什么 / 什么顺序"在动态资源（`chsi_fields.json`）：
        # 多写一个字段进画像是一个**隐私决定**，不该由代码顺手决定。
        for item in report.fields:
            spec = chsi_specs.get(item.key)
            if spec is None:
                # 不在清单里的字段**不进画像**（比如学信网报告里可能多出的项）。
                # 这是刻意的白名单，不是遗漏。
                continue
            before = existing[item.key].confidence if item.key in existing else 0.0
            await save(
                user_id,
                item.key,
                item.value,
                # 兼容既有材料记录分数；核实程度由 verification 单独表达。
                confidence=1.0,
                source=ProfileSource.RECORD.value,
                evidence=[report.source_url],
                # 学信网在线验证是**外部核验**，不是普通资料记录：核实状态要与来源分开表达。
                verification=ProfileVerification.VERIFIED.value,
                origin_ref=report.source_url,
            )
            written.append(
                ProfileLift(
                    dim=spec.label or item.key,
                    **{"from": round(before, 2), "to": 1.0},
                    because=f"学信网{report.kind.value}在线验证报告 · {item.label}",
                )
            )
            detail_bits.append(f"{spec.label or item.key} {item.value}")

        # 学信网给的是入学日期，不是「现在大几」。这一步只做一次确定性换算，
        # 并且把「这是推算值」写进来源/属性 —— 画像里显示「待核对」，
        # 用户随时可以改成自己确认的年级；用户已经填过的那条永远不被覆盖。
        report_written = len(written)
        # 只有「学籍」报告代表现在仍在读。学历/学位报告是毕业后的证明，
        # 拿它的入学日期推「现在大几」会把毕业生算成在校生。
        enrolled_at = (
            report.value_of("enrolled_at")
            if report.kind is ChsiReportKind.ENROLLMENT
            else ""
        )
        current_study_year = existing.get("study_year")
        can_replace_study_year = current_study_year is None or (
            current_study_year.source is ProfileSource.RECORD
            and str(current_study_year.origin_ref or "").startswith(_DERIVED_STUDY_YEAR_REF)
        )
        derived_study_year = (
            academic_time.study_year_from_enrollment(enrolled_at) if enrolled_at else None
        )
        derived_note = ""
        derived_written = False
        if derived_study_year and can_replace_study_year:
            today = datetime.now(academic_time.CHINA_TZ).date()
            study_year_label = next(
                (
                    spec.label
                    for spec in dynamic_config.snapshot().profile_fields
                    if spec.key == "study_year" and not spec.alias_of and spec.label
                ),
                "当前学习阶段",
            )
            before = current_study_year.confidence if current_study_year else 0.0
            await save(
                user_id,
                "study_year",
                derived_study_year,
                # 0.8 不是「和报告一样权威」：换算本身确定，但它是从入学日推出来的，
                # 不是学信网直接写明的字段，所以核实状态留在「待核对」。
                confidence=0.8,
                source=ProfileSource.RECORD.value,
                label=study_year_label,
                evidence=[report.source_url, f"按入学日期 {enrolled_at} 推算"],
                verification=ProfileVerification.PENDING.value,
                origin_ref=f"{_DERIVED_STUDY_YEAR_REF}={enrolled_at}",
                attributes={
                    "derived_from": f"入学日期 {enrolled_at}",
                    "derived_on": today.isoformat(),
                },
                valid_to=academic_time.study_year_valid_to(enrolled_at),
            )
            written.append(
                ProfileLift(
                    dim="学习阶段",
                    **{"from": round(before, 2), "to": 0.8},
                    because=(
                        f"按学信网入学日期 {enrolled_at} 推算为{derived_study_year}；"
                        "这是推算值，可在画像里修改"
                    ),
                )
            )
            derived_written = True
            derived_note = f"按入学日期 {enrolled_at} 推算为「{derived_study_year}」"
        elif enrolled_at and derived_study_year is None:
            derived_note = (
                f"报告里的入学日期是 {enrolled_at}，但按本科 1–4 年推算不出当前阶段，"
                "请在画像里确认"
            )
        elif enrolled_at and current_study_year is not None:
            derived_note = (
                f"画像里已有你的学习阶段「{current_study_year.value}」，"
                "没有用推算值覆盖"
            )

        return dict(written=written, detail_bits=detail_bits, report_written=report_written,
                    derived_note=derived_note, derived_written=derived_written, entries=entries)
