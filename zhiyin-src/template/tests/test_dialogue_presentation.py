import json

import pytest
from pydantic import ValidationError

from tests.test_orchestration import _PromptRegistry
from zhiyin_kernel.streaming import progress_channel
from zhiyin_orchestration.impl.dialogue_presentation import (
    load_professionals, presentation_instructions, stream_public_reply, finish_public_reply,
    history_content,
)


def reply(text, role='career_advisor', focus='diagnose', collaborators=None):
    return json.dumps({'role_id': role, 'focus': focus, 'collaborators': collaborators or [], 'answer': text}, ensure_ascii=False)


def state():
    return {'lead': 'profile_analyst', 'stage': 'collect', 'roles': []}


def test_history_preserves_text_without_fabricating_legacy_identity():
    content = '写出 "第一步"，再检查换行\n和路径\\。'
    known = json.loads(history_content({'role': 'assistant', 'content': content, 'agent_id': 'path_planner', 'focus': 'act'}))
    assert known['answer'] == content and known['role_id'] == 'path_planner'
    unknown = json.loads(history_content({'role': 'assistant', 'content': content}))
    assert unknown == {'historical': True, 'answer': content}
    assert history_content({'role': 'user', 'content': content}) == content


@pytest.mark.asyncio
async def test_selected_identity_and_only_public_answer_stream_before_final_json():
    roles = await load_professionals(_PromptRegistry())
    s, frames = state(), []
    raw = reply('第一步：读取文件。\n再试 "编码" 与 \\ 路径。你好', 'path_planner', 'act', ['info_scout'])
    previous = ''
    with progress_channel(frames.append):
        for i in range(len(raw) + 1):
            public = stream_public_reply(raw[:i], s, roles)
            assert public.startswith(previous)
            assert 'role_id' not in public and 'collaborators' not in public
            previous = public
        assert finish_public_reply(raw, s, roles) == previous
    assert s['lead'] == 'path_planner' and s['stage'] == 'act'
    assert s['roles'] == ['path_planner', 'info_scout']
    assert len(frames) == 1 and frames[0]['type'] == 'role.selected'
    assert 'path_planner' in presentation_instructions(roles)


@pytest.mark.asyncio
async def test_nested_fields_and_split_identity_never_select_an_unfinished_or_nested_role():
    roles = await load_professionals(_PromptRegistry())
    s = state()
    assert stream_public_reply('{"private":{"role_id":"path_planner","focus":"act","answer":"secret"}', s, roles) == ''
    assert stream_public_reply('{"role_id":"path_planner', s, roles) == ''
    assert s['lead'] == 'profile_analyst'


@pytest.mark.asyncio
async def test_unavailable_mismatched_and_scout_leads_do_not_stream_or_commit():
    roles = await load_professionals(_PromptRegistry())
    for raw in [reply('x', 'path_planner', 'review'), reply('x', 'info_scout', 'collect')]:
        s = state()
        assert stream_public_reply(raw, s, roles) == ''
        assert s['lead'] == 'profile_analyst'
    del roles['path_planner']
    with pytest.raises(ValueError):
        finish_public_reply(reply('x', 'path_planner', 'act'), state(), roles)
    with pytest.raises(ValueError):
        finish_public_reply(reply('x', collaborators=['path_planner']), state(), roles)
    with pytest.raises(ValidationError):
        finish_public_reply(reply('x')[:-1], state(), roles)


@pytest.mark.asyncio
async def test_disabled_professional_prompt_is_not_injected_or_selectable():
    registry = _PromptRegistry()
    original = registry.get_prompt
    async def get_prompt(code):
        prompt = await original(code)
        return prompt.model_copy(update={'status': 'disabled'}) if code.endswith('path_planner') else prompt
    registry.get_prompt = get_prompt
    roles = await load_professionals(registry)
    assert 'path_planner' not in roles
    assert stream_public_reply(reply('x', 'path_planner', 'act'), state(), roles) == ''


@pytest.mark.asyncio
async def test_loading_collaborator_does_not_override_selected_lead():
    from tests.test_dialogue_runtime import setup
    from zhiyin_orchestration.impl.dialogue_specialists import specialist_tools
    c, _, _ = await setup()
    roles = await load_professionals(c.registry_service)
    s = {**state(), 'methods': {}, 'clues': [], 'theories': []}
    finish_public_reply(reply('先比较两种选择。', focus='decide'), s, roles)
    load, _ = specialist_tools(c.registry_service, s)
    for role, focus in [('profile_analyst', 'collect'), ('path_planner', 'act'), ('info_scout', '')]:
        assert (await load(role, focus))['loaded']
    assert (s['lead'], s['stage']) == ('career_advisor', 'decide')


@pytest.mark.asyncio
async def test_one_readonly_repair_can_recover_metadata_without_reexecuting_tools(monkeypatch):
    from types import SimpleNamespace
    from tests.test_orchestration import _StubModel
    from zhiyin_orchestration.impl import dialogue_engine
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_orchestration.agent import AgentRequest
    agents = []
    class Agent:
        def __init__(self, **kwargs):
            self.index = len(agents)
            agents.append(kwargs)
        async def arun(self, **kwargs):
            if self.index:
                assert kwargs['input'][-1].role == 'user'
                assert '传输格式修复' in kwargs['input'][-1].content
            return SimpleNamespace(status='completed', messages=[], content='   ' if self.index == 0 else reply('按已有回执继续。', 'path_planner', 'act'))
    monkeypatch.setattr(dialogue_engine, 'Agent', Agent)
    engine = AgnoAgentEngine(model_factory=lambda **_: _StubModel(), registry=_PromptRegistry())
    result = await engine.invoke(AgentRequest(agent_id='profile_analyst', conversation=True))
    assert result.valid and result.agent_id == 'path_planner'
    assert len(agents) == 2 and agents[1]['tools'] == [] and agents[1]['tool_call_limit'] == 0


@pytest.mark.asyncio
async def test_persistent_invalid_metadata_fails_after_one_repair(monkeypatch):
    from types import SimpleNamespace
    from tests.test_orchestration import _StubModel
    from zhiyin_orchestration.impl import dialogue_engine
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_orchestration.agent import AgentRequest
    calls = []
    class Agent:
        def __init__(self, **kwargs): calls.append(kwargs)
        async def arun(self, **kwargs): return SimpleNamespace(status='completed', messages=[], content='not-json')
    monkeypatch.setattr(dialogue_engine, 'Agent', Agent)
    engine = AgnoAgentEngine(model_factory=lambda **_: _StubModel(), registry=_PromptRegistry())
    result = await engine.invoke(AgentRequest(agent_id='profile_analyst', conversation=True))
    assert not result.valid and len(calls) == 2 and result.raw_text == ''


@pytest.mark.asyncio
async def test_unused_transport_annotations_are_never_public():
    roles = await load_professionals(_PromptRegistry())
    raw = json.loads(reply('只展示这句话。'))
    raw['answer_note'] = 'internal-annotation'
    assert finish_public_reply(json.dumps(raw), state(), roles) == '只展示这句话。'


@pytest.mark.asyncio
async def test_complete_assets_in_the_reply_are_handed_to_the_business_layer():
    """正文里的完整方向/计划要随最终回复一起交给业务层；不靠模型再调保存工具。"""
    roles = await load_professionals(_PromptRegistry())
    raw = json.loads(reply('三套方向已经给出。'))
    raw['directions'] = [
        {'role': 'main', 'name': '主攻：算法', 'target_desc': '算法岗',
         'fit_reason': '基础匹配', 'main_risk': '项目不足'},
        {'role': 'fallback', 'name': '保底：测试', 'target_desc': '测试岗',
         'fit_reason': '门槛较低', 'main_risk': '成长空间'},
    ]
    raw['plan'] = {'phases': [{'name': '第一周', 'date_range': '本周',
                              'tasks': [{'text': '完成一次练习'}]}]}
    s = state()
    assert finish_public_reply(json.dumps(raw), s, roles) == '三套方向已经给出。'
    assets = s['reply_assets']
    assert [item['role'] for item in assets['directions']] == ['main', 'fallback']
    assert assets['plan']['phases'][0]['tasks'][0]['text'] == '完成一次练习'


@pytest.mark.asyncio
async def test_incomplete_assets_are_not_announced_to_the_business_layer():
    roles = await load_professionals(_PromptRegistry())
    raw = json.loads(reply('先聊聊你现在的课程。'))
    raw['directions'] = []
    raw['plan'] = {'phases': [{'name': '第一周', 'date_range': '本周', 'tasks': []}]}
    s = state()
    finish_public_reply(json.dumps(raw), s, roles)
    assert 'reply_assets' not in s


@pytest.mark.asyncio
async def test_cancelled_stream_never_commits_provisional_identity(monkeypatch):
    from types import SimpleNamespace
    from tests.test_orchestration import _StubModel
    from zhiyin_orchestration.impl import dialogue_engine
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_orchestration.agent import AgentRequest
    stopped = False
    async def cancelled(): return stopped
    class Agent:
        def __init__(self, **kwargs): pass
        async def arun(self, **kwargs):
            nonlocal stopped
            yield SimpleNamespace(event='RunContent', content=reply('', 'path_planner', 'act')[:-2] + '第一步')
            stopped = True
            yield SimpleNamespace(event='RunContent', content='不会提交这段"}')
    monkeypatch.setattr(dialogue_engine, 'Agent', Agent)
    monkeypatch.setattr(dialogue_engine, 'cancellation_requested', cancelled)
    engine = AgnoAgentEngine(model_factory=lambda **_: _StubModel(), registry=_PromptRegistry())
    with progress_channel(lambda frame: None):
        result = await engine.invoke(AgentRequest(agent_id='profile_analyst', conversation=True))
    assert not result.valid and result.raw_text == '第一步' and result.agent_id == 'path_planner'
    assert result.structured['dialogue_partial_speaker'] == 'path_planner'
    assert not result.structured.get('dialogue_stage')
