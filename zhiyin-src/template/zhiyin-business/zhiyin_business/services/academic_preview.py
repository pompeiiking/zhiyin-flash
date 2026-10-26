"""Owner-scoped short-lived previews shared by HTTP and dialogue tools."""
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pydantic import ValidationError

from zhiyin_business.contracts.academic_preview import AcademicPreview, AcademicPreviewRequest
from zhiyin_business.services.conversation_ledger import digest
from zhiyin_data_sdk.gateways.academic import CourseEntry, GradeEntry, AcademicImportError
from zhiyin_kernel.errors import InvalidRequest
from zhiyin_kernel.privacy import SENSITIVE


class AcademicPreviewChanged(InvalidRequest):
    """A preview cannot be applied; no academic write has started."""


def academic_version(snapshot):
    return digest(snapshot.model_dump(mode='json') if snapshot else None)


def validate_canonical_json(source, kind):
    """Do not let the permissive school-export parser hide malformed canonical rows."""
    try:
        values = json.loads(source)
    except ValueError:
        return source
    if isinstance(values, dict):
        values = values.get(kind)
    if not isinstance(values, list) or not any(isinstance(v, dict) and 'name' in v for v in values):
        return source
    if not 1 <= len(values) <= 200:
        raise InvalidRequest('每次请导入 1 至 200 条记录。')
    row_type = CourseEntry if kind == 'courses' else GradeEntry
    normalized = []
    for value in values:
        if not isinstance(value, dict):
            raise InvalidRequest('每一条记录都需要课程名称和对应字段，请检查表格。')
        value = dict(value)
        for key, field in row_type.model_fields.items():
            if key in value and field.annotation is str and isinstance(value[key], (int, float)) and not isinstance(value[key], bool):
                value[key] = str(value[key])
        try:
            row = row_type.model_validate(value, strict=True)
        except ValidationError:
            raise InvalidRequest('表格中有字段缺失或格式错误，请检查课程、时间和成绩。') from None
        if not row.name.strip():
            raise InvalidRequest('有课程名称缺失，请修正后预览。')
        if kind == 'courses' and (not 0 <= row.weekday <= 7 or not 0 <= row.start_period <= row.end_period <= 30
                or bool(row.start_period) != bool(row.end_period)):
            raise InvalidRequest('课表的星期或节次无效，请修正后预览。')
        normalized.append(row.model_dump(mode='json'))
    return json.dumps(normalized, ensure_ascii=False)


class AcademicPreviewService:
    def __init__(self, academic, importer, materials, store, vision_reader=None):
        self.academic, self.importer, self.materials, self.store = academic, importer, materials, store
        self.vision_reader = vision_reader

    async def prepare(self, user_id, body: AcademicPreviewRequest):
        from zhiyin_business.services.analysis_access import current_scope
        scope = current_scope(user_id)
        if scope and ('academic' not in scope.sources or (body.material_id and 'material' not in scope.sources)):
            raise InvalidRequest('当前资料偏好未允许使用课表、成绩或材料。')
        if bool(body.material_id) == bool(body.text.strip()):
            raise InvalidRequest('请选择一份材料或一段表格文字，不能同时提交。')
        source = body.text
        warnings = []
        if body.material_id:
            try:
                material = await self.materials.material_body(user_id, body.material_id)
            except LookupError as exc:
                raise InvalidRequest('材料不存在，请重新上传。') from exc
            if material.image_data_url:
                if self.vision_reader is None:
                    raise InvalidRequest('图片识别服务暂不可用，请稍后重试或粘贴表格。')
                recognized = await self.vision_reader(material.image_data_url, body.kind)
                values = recognized.get(body.kind)
                if not isinstance(values, list) or len(values) > 200:
                    raise InvalidRequest('图片未识别出有效表格，请裁剪清晰区域后重试。')
                try:
                    row_type = CourseEntry if body.kind == 'courses' else GradeEntry
                    validated = [row_type.model_validate(value, strict=True) for value in values]
                except ValidationError:
                    raise InvalidRequest('图片识别结果存在缺失或错误字段，请重新识别或粘贴表格修正。') from None
                if any(not row.name.strip() for row in validated):
                    raise InvalidRequest('图片有课程名称无法辨认，请裁剪清晰区域后重试。')
                for row in validated:
                    if body.kind == 'courses' and (not 0 <= row.weekday <= 7 or not 0 <= row.start_period <= row.end_period <= 30
                            or bool(row.start_period) != bool(row.end_period)):
                        raise InvalidRequest('图片识别的星期或节次无效，请重新识别或粘贴表格修正。')
                source = json.dumps(values, ensure_ascii=False)
                notices = recognized.get('warnings', [])
                if not isinstance(notices, list):
                    raise InvalidRequest('图片识别结果格式不完整，请重试。')
                warnings = [str(w)[:300] for w in notices[:20] if not SENSITIVE.search(str(w))]
            else:
                source = material.text
        if not source.strip() or len(source) > 200_000 or SENSITIVE.search(source):
            raise InvalidRequest('表格为空、过长或包含敏感信息，请保留必要的课程数据后重试。')
        source = validate_canonical_json(source, body.kind)
        try:
            parsed = (self.importer.parse_courses(source) if body.kind == 'courses' else self.importer.parse_grades(source))
            rows = getattr(parsed, body.kind)
            if not rows or len(rows) > 200:
                raise InvalidRequest('每次请导入 1 至 200 条记录。')
            # The importer supports heterogeneous exports. Revalidate its normalized result.
            rows = [(CourseEntry if body.kind == 'courses' else GradeEntry).model_validate(row) for row in rows]
        except (AcademicImportError, ValidationError, TypeError) as exc:
            raise InvalidRequest('未能读出完整表格，请检查课程名称、成绩和表头后重试。') from exc
        for row in rows:
            if not row.name.strip() or len(row.name) > 200:
                raise InvalidRequest('有课程名称缺失或过长，请修正后预览。')
            if body.kind == 'courses':
                if not 0 <= row.weekday <= 7 or not 0 <= row.start_period <= 30 or not 0 <= row.end_period <= 30:
                    raise InvalidRequest('课表的星期或节次无效，请修正后预览。')
                if bool(row.start_period) != bool(row.end_period) or row.start_period > row.end_period:
                    raise InvalidRequest('课程开始、结束节次不完整，请修正后预览。')
                if not row.weekday or not row.start_period:
                    # 说清"缺的是哪一半"：只缺星期时，节次其实已经读到了，
                    # 再说"上课时间待补充"会让用户以为整段都没识别出来（实测反馈）。
                    missing = (
                        "星期和节次都没读出来"
                        if not row.weekday and not row.start_period
                        else "没认出星期（节次已读到）"
                        if not row.weekday
                        else "没认出节次（星期已读到）"
                    )
                    warnings.append(f"{row.name}：{missing}，保存后暂不出现在课表网格中。")
            elif not row.score.strip():
                raise InvalidRequest(f'「{row.name}」的成绩无法确认，请补充后重新预览；不会猜测分数。')
        snapshot = await self.academic.get(user_id)
        school, term = body.school.strip(), body.term.strip() or getattr(parsed, 'term', '')
        if not school or not term:
            raise InvalidRequest('请填写学校和学期后预览；无法确认的信息不会自动填写。')
        from zhiyin_business.services.academic import _dedupe_courses, _dedupe_grades
        if body.kind == 'grades':
            rows = [row.model_copy(update={'term': row.term or term}) for row in rows]
        rows, dropped = (_dedupe_courses(rows) if body.kind == 'courses' else _dedupe_grades(rows))
        if dropped:
            warnings.append(f'已合并 {dropped} 条重复记录；以上为实际保存的记录。')
        preview = AcademicPreview(preview_id='ap_' + uuid4().hex, kind=body.kind, school=school, term=term,
            **{body.kind: rows}, warnings=list(dict.fromkeys(warnings)),
            replace_count=len(getattr(snapshot, body.kind)) if snapshot else 0,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            expected_version=academic_version(snapshot))
        await self.store.put(self._key(user_id, preview.preview_id), preview.model_dump_json().encode(), content_type='application/json')
        return preview

    def _key(self, user_id, preview_id):
        if not re.fullmatch(r'ap_[a-f0-9]{32}', preview_id):
            raise InvalidRequest('预览编号无效，请重新预览。')
        return self.store.build_named_key(user_id, 'academic_preview', preview_id, 'json')

    async def read(self, user_id, preview_id):
        try:
            raw = await self.store.get(self._key(user_id, preview_id))
        except FileNotFoundError as exc:
            raise InvalidRequest('预览不存在，请重新识别。') from exc
        preview = AcademicPreview.model_validate_json(raw)
        if datetime.fromisoformat(preview.expires_at) <= datetime.now(timezone.utc):
            raise AcademicPreviewChanged('预览已过期，请重新识别。')
        if academic_version(await self.academic.get(user_id)) != preview.expected_version:
            raise AcademicPreviewChanged('课表或成绩已经变化，请重新预览后确认。')
        return preview

    async def commit(self, user_id, preview_id):
        preview = await self.read(user_id, preview_id)
        rows = getattr(preview, preview.kind)
        return await self.academic.import_(user_id,
            **{preview.kind + '_raw': json.dumps([row.model_dump(mode='json') for row in rows], ensure_ascii=False)},
            school=preview.school, term=preview.term, expected_version=preview.expected_version)
