"""Shared model-facing operation vocabulary and payload contracts.

The executor still owns authorization, ownership and version validation.
"""
from copy import deepcopy
from typing import Literal, get_args
from pydantic import ConfigDict, create_model

from zhiyin_kernel.assets import ActionPlan, ActionTask, DirectionPlan, Report

REPORT_OWNED_FIELDS = {'id', 'user_id', 'version', 'generated_at'}
ReportDraftInput = create_model('ReportDraftInput', __config__=ConfigDict(extra='forbid'),
    **{name: (field.annotation, deepcopy(field)) for name, field in Report.model_fields.items() if name not in REPORT_OWNED_FIELDS})

DialogueOperation = Literal[
    'profile.update', 'task.set_done', 'plan.save', 'report.save', 'directions.save',
    'plan.activate', 'plan.patch', 'report.activate', 'directions.activate',
    'direction.select', 'calendar.write', 'calendar.delete', 'memory.forget',
    'action.undo', 'action.approve', 'action.reject',
]


def _object(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def _input_schema(model, owned):
    schema = deepcopy(model.model_json_schema())
    for key in owned:
        schema['properties'].pop(key, None)
    schema['required'] = [key for key in schema.get('required', []) if key not in owned]
    return schema


def action_contracts():
    """Schemas describe the caller payload, excluding server-owned identity/version fields."""
    text = {'type': 'string'}
    plan = _input_schema(ActionPlan, {'id', 'reminders_synced'})
    report = ReportDraftInput.model_json_schema()
    direction = _input_schema(DirectionPlan, {'id', 'selected', 'match_score'})
    # Keep definitions at the document root so nested $refs resolve correctly.
    definitions = direction.pop('$defs', {})
    directions = _object({'plans': {'type': 'array', 'minItems': 1, 'maxItems': 6, 'items': direction}}, ['plans'])
    if definitions:
        directions['$defs'] = definitions
    specs = {
        'profile.update': ('维护本人明确自述的画像；临时会话不保存。按 profile_record_contract 选择字段、取值与属性。', 'automatic_or_explicit', _object({
            'key': text, 'value': {'anyOf': [text, {'type': 'array', 'items': text}]},
            'attributes': {'type': 'object'}, 'assertion_type': {'enum': ['affirmative_self_statement', 'explicit_correction', 'conflict_candidate']},
            'save_scope': {'enum': ['', 'single']},
            **{key: {'type': ['string', 'null'], 'format': 'date-time'} for key in ('valid_from', 'valid_to', 'event_at')},
        }, ['key', 'value', 'assertion_type'])),
        'task.set_done': ('先读计划定位真实 task_id；用户明确指定完成/未完成时可直接执行。', 'explicit', _object({'task_id': text, 'task_text': text, 'done': {'type': 'boolean'}}, ['task_id', 'done'])),
        'plan.save': ('保存计划草稿，不修改正式计划。', 'explicit_draft', plan),
        'report.save': ('保存新版报告草稿；重新生成需读取最新画像，不能仅重读旧报告。', 'explicit_draft', report),
        'directions.save': ('保存多个方向的草稿，不表示用户已选择。', 'explicit_draft', directions),
        'plan.patch': ('先读计划；1至3项明确任务修改可 explicit，其他先 proposal。', 'bounded_explicit_or_proposal', _object({'updates': {'type': 'array', 'minItems': 1, 'maxItems': 30, 'items': _object({'task_id': text, 'fields': _object({key: ActionTask.model_json_schema()['properties'][key] for key in ('text', 'due_date', 'estimated_minutes', 'scheduled_at')})}, ['task_id', 'fields'])}}, ['updates'])),
        'direction.select': ('先读方向定位 plan_id；必须生成具体审批卡，确认后才能选择。', 'proposal', _object({'plan_id': text}, ['plan_id'])),
        'calendar.write': ('先读日历；修改需带 node_id。时间必须带时区，创建/修改均需审批。', 'proposal', _object({'node_id': text, 'title': text, 'due_at': {'type': 'string', 'format': 'date-time'}}, ['title', 'due_at'])),
        'calendar.delete': ('先读日历定位 node_id，确认后删除。', 'proposal', _object({'node_id': text}, ['node_id'])),
        'memory.forget': ('删除一项长期画像并保留拒绝自动恢复策略；必须审批。单纯不要记录用 workspace.memory。', 'proposal', _object({'key': text}, ['key'])),
        'action.undo': ('引用真实已执行操作的 target_id，版本未变且支持撤销时生成审批。', 'proposal', _object({'target_id': text}, ['target_id'])),
    }
    for kind in ('plan', 'report', 'directions'):
        specs[kind + '.activate'] = ('将本会话已保存草稿设为正式版本；先生成审批卡，确认后才替换。', 'proposal', _object({'draft_id': text}, ['draft_id']))
    for kind in ('approve', 'reject'):
        specs['action.' + kind] = ('仅处理真实未决审批；action_id 和本轮原话 evidence 在工具顶层传入，不能伪造用户确认。', 'user_confirmation', _object({}))
    assert set(specs) == set(get_args(DialogueOperation))
    return {key: {'description': desc, 'authorization': auth, 'payload_schema': schema, **({'preferred_tool': 'save_report_draft'} if key == 'report.save' else {})} for key, (desc, auth, schema) in specs.items()}
