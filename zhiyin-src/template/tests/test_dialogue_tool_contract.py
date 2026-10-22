"""Validate the actual model-facing tools, not just registration names."""
import json
from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock

from agno.run import RunContext
from agno.tools.function import Function
from jsonschema import Draft202012Validator

from zhiyin_boot.module_platform import product_tools
from zhiyin_business.contracts.dialogue_actions import DialogueOperation, action_contracts
from zhiyin_business.services.dialogue_runtime import ActionInput
from zhiyin_orchestration.impl.dialogue_engine import dialogue_tool_names, traced


def handlers():
    return {t.name: t.handler for m in product_tools(SimpleNamespace(extra={'modules': {}})) for t in m.tools}


def test_actual_wrapped_tool_schema_lists_executor_operations_and_hides_identity():
    tool = Function.from_callable(traced(handlers()['workspace.action'], 'workspace.action'))
    assert set(tool.parameters['properties']['operation']['enum']) == set(get_args(DialogueOperation))
    assert set(ActionInput.model_json_schema()['properties']['operation']['enum']) == set(get_args(DialogueOperation))
    assert not {'user_id', 'run_context', 'task_id'}.intersection(tool.parameters['properties'])
    assert 'draft_saved' in tool.description and 'schemas' in tool.description


async def test_model_receives_memory_tool_and_only_installed_permitted_capabilities():
    registry = SimpleNamespace(get_agent=AsyncMock(return_value=SimpleNamespace(status='enabled', tools=['web.search', 'profile.read'])))
    engine = SimpleNamespace(_registry=registry, _tools={name: object() for name in ['workspace.memory', 'workspace.action', 'workspace.read', 'profile.read']}, module_tool_names=AsyncMock(return_value=['not_installed']))
    names = await dialogue_tool_names(engine, 'career_advisor')
    assert set(names) == {'workspace.memory', 'workspace.action', 'workspace.read'}


async def test_schema_reader_exposes_exact_selected_payload_without_server_owned_identity():
    result = json.loads(await handlers()['workspace.read'](RunContext(user_id='u1', run_id='r1', session_id='s1'), area='schemas', operation='report.save'))
    assert set(result['operations']) == {'report.save'}
    assert not {'id', 'user_id', 'version', 'generated_at'}.intersection(result['report.save']['required'])
    assert result['operations']['report.save']['authorization'] == 'explicit_draft'
    assert 'activate' in result['rules']


def test_all_advertised_payload_schemas_are_valid_and_directions_use_the_actual_list_envelope():
    contracts = action_contracts()
    assert set(contracts) == set(get_args(DialogueOperation))
    for contract in contracts.values():
        Draft202012Validator.check_schema(contract['payload_schema'])
    schema = contracts['directions.save']['payload_schema']
    assert schema['required'] == ['plans'] and schema['properties']['plans']['maxItems'] == 6
    assert all(contracts[k]['authorization'] == 'proposal' for k in ('report.activate', 'plan.activate', 'directions.activate'))


async def test_regenerated_report_remains_draft_until_real_approval_then_creates_new_version():
    from datetime import datetime, timezone
    from tests.test_dialogue_runtime import setup, send, action
    from zhiyin_kernel.assets import Report, Swot, Verdict
    previous = Report(id='original', user_id='u1', version=1, generated_at=datetime.now(timezone.utc), verdict=Verdict(title='原报告', summary='原结论'), swot=Swot())
    pending = {}
    async def callback(rt):
        draft = await rt.action(action('report.save', {'verdict': {'title': '新版报告', 'summary': '根据最新资料形成'}, 'swot': {}}, evidence='重新生成报告'))
        assert draft['executed'] and draft['receipt']['draft_saved']
        activation = await rt.action(action('report.activate', {'draft_id': draft['action_id']}, evidence='重新生成报告', authorization='proposal'))
        pending.update(activation)
    c, engine, session = await setup(callback)
    await c.asset_service.save_report('u1', previous)
    result = await send(c, session, '重新生成报告')
    assert any('报告草稿，正式版本尚未替换' in message.text for message in result.messages)
    assert pending['state'] == 'proposed' and not pending['executed']
    assert (await c.asset_service.get_report('u1')).verdict.title == '原报告'
    engine.callback = None
    await send(c, session, '确认', option_id='action.' + pending['action_id'] + '.accept')
    report = await c.asset_service.get_report('u1')
    assert report.verdict.title == '新版报告' and report.version > 1


def test_report_tool_native_parameters_expose_real_report_structure():
    function = Function.from_callable(traced(handlers()['workspace.report_draft'], 'workspace.report_draft'))
    report = function.parameters['properties']['report']
    assert {'verdict', 'swot'}.issubset(report['properties'])
    assert {'verdict', 'swot'}.issubset(report['required'])
    assert not {'id', 'user_id', 'version', 'generated_at'}.intersection(report['properties'])


async def test_validation_feedback_identifies_fields_without_echoing_input():
    from zhiyin_business.contracts.dialogue_actions import ReportDraftInput
    async def invalid(**kwargs):
        ReportDraftInput.model_validate({'verdict': {'title': 'ok', 'summary': 'ok', 'wrong': 'sample-private-value'}, 'swot': {}})
    result = json.loads(await traced(invalid, 'workspace.action')())
    assert result['state'] == 'validation_failed' and not result['executed']
    assert result['errors'][0]['path'] == ['verdict', 'wrong']
    assert 'sample-private-value' not in json.dumps(result)


async def test_successful_report_automatically_attaches_persisted_evidence_chart():
    from tests.test_dialogue_runtime import setup, send, action

    async def callback(rt):
        return await rt.action(action('report.save', {
            'verdict': {'title': '资料整理', 'summary': '依据仍待核实'}, 'swot': {}},
            evidence='生成诊断报告'))

    c, engine, session = await setup(callback)
    await c.profile_service.correct_field('u1', 'interest', '喜欢写代码')
    result = await send(c, session, '生成诊断报告', client_msg_id='report-with-chart')
    charts = result.messages[-1].renderables
    assert len(charts) == 1 and charts[0].kind == 'profile_evidence_chart'
    assert charts[0].payload['metric'] == 'profile_evidence'
    point = charts[0].payload['points'][0]
    assert point['key'] == 'interest'
    assert point['assessment']['status'] == 'pending'
    assert point['assessment']['score'] is None  # old manual confidence=1 never becomes 100%
    turns = await c.memory_service.list_turns('u1', session.id)
    assert next(t for t in reversed(turns) if t.role == 'agent').renderables[0]['kind'] == 'profile_evidence_chart'
    replay = await send(c, session, '生成诊断报告', client_msg_id='report-with-chart')
    assert replay.messages[-1].renderables == charts and len(engine.requests) == 1


async def test_regular_conversation_does_not_gain_report_chart():
    from tests.test_dialogue_runtime import setup, send
    c, _, session = await setup()
    await c.profile_service.correct_field('u1', 'interest', '喜欢写代码')
    result = await send(c, session, '你好')
    assert not result.messages[-1].renderables
