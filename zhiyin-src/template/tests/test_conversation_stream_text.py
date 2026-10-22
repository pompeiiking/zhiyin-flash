from tests.test_dialogue_presentation import reply
import unittest
from zhiyin_orchestration.impl.stream_text import partial_root_string

class StreamTextTests(unittest.TestCase):
    def test_never_exposes_other_fields(self):
        raw = '{"private":{"conclusion":"secret"},"conclusion":"回答\\n继续\\u4f60好", "guide":{"text":"later"}}'
        previous = ''
        for i in range(len(raw) + 1):
            value = partial_root_string(raw[:i], 'conclusion')
            self.assertTrue('回答\n继续你好'.startswith(value))
            self.assertTrue(value.startswith(previous))
            previous = value
        self.assertEqual(previous, '回答\n继续你好')
    def test_quotes_and_fences(self):
        self.assertEqual(partial_root_string('```json\n{"conclusion":"a\\"b\\\\c"}', 'conclusion'), 'a"b\\c')
    def test_incomplete_escape(self):
        self.assertEqual(partial_root_string('{"conclusion":"ok\\u4f', 'conclusion'), 'ok')
    def test_no_string(self):
        self.assertEqual(partial_root_string('{"conclusion":null,"private":"secret"}', 'conclusion'), '')

if __name__ == '__main__':
    unittest.main()

async def test_agno_stream_emits_before_model_finishes():
    import json
    from tests.test_orchestration import _StubModel, _PromptRegistry
    from agno.models.response import ModelResponse
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_orchestration.agent import AgentRequest
    from zhiyin_kernel.streaming import progress_channel
    frames = []
    class StreamingModel(_StubModel):
        async def ainvoke_stream(self, *args, **kwargs):
            raw = json.dumps({'conclusion':'真实增量', 'private':'不得展示'}, ensure_ascii=False)
            for ch in raw:
                yield ModelResponse(content=ch)
            assert any(f.get('text') == '真实' for f in frames)
    engine = AgnoAgentEngine(model_factory=lambda **_: StreamingModel(), registry=_PromptRegistry())
    request = AgentRequest(agent_id='test', stream_field='conclusion', output_schema={'type':'object','properties':{'conclusion':{'type':'string'}},'required':['conclusion']})
    with progress_channel(frames.append):
        result = await engine.invoke(request)
    assert result.valid, result.errors
    assert frames[-1]['text'] == '真实增量'
    assert all('不得展示' not in f.get('text', '') for f in frames)

async def test_stream_controller_isolates_concurrent_users(monkeypatch):
    import asyncio
    import json
    from types import SimpleNamespace
    from zhiyin_api.controllers import conversation_controller as controller
    from zhiyin_api.dto.conversation import MessageRequest
    from zhiyin_kernel.streaming import emit_progress
    class Facade:
        async def resolve_user_id(self, request): return request.user
        async def check_analysis_consent(self, user): pass
        async def send_message(self, user, body):
            emit_progress({'text': user + '-partial'})
            await asyncio.sleep(0)
            return SimpleNamespace(model_dump=lambda **_: {'task_id':body.task_id,'text':user + '-complete'})
    monkeypatch.setattr(controller, 'get_facade', lambda: Facade())
    async def read(user):
        response = await controller.stream_message(SimpleNamespace(user=user), MessageRequest(task_id=user,message='test'))
        return [json.loads(frame[6:]) async for frame in response.body_iterator if frame.startswith('data: ')]
    a,b = await asyncio.gather(read('a'),read('b'))
    assert a[1]['text'] == 'a-partial' and b[1]['text'] == 'b-partial'
    assert a[-1]['result']['task_id'] == 'a'

async def test_stream_disconnect_does_not_interrupt_approved_writes(monkeypatch):
    import asyncio
    from zhiyin_api.controllers import conversation_controller as controller
    from zhiyin_api.dto.conversation import MessageRequest
    from zhiyin_kernel.streaming import emit_progress
    cancelled = asyncio.Event()
    finish = asyncio.Event()
    class Facade:
        async def resolve_user_id(self, request): return 'a'
        async def check_analysis_consent(self, user): pass
        async def send_message(self, user, body):
            try:
                emit_progress({'text':'partial'})
                await finish.wait()
                from types import SimpleNamespace
                return SimpleNamespace(model_dump=lambda **kwargs: {"task_id": "a"})
            finally:
                cancelled.set()
    monkeypatch.setattr(controller, 'get_facade', lambda: Facade())
    response = await controller.stream_message(None, MessageRequest(task_id='a',message='test'))
    await anext(response.body_iterator)
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert not cancelled.is_set()
    finish.set()
    await asyncio.wait_for(cancelled.wait(), 1)


async def test_native_conversation_streams_plain_text_before_completion():
    from tests.test_orchestration import _StubModel, _PromptRegistry
    from agno.models.response import ModelResponse
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_orchestration.agent import AgentRequest
    from zhiyin_kernel.streaming import progress_channel
    frames = []
    class StreamingModel(_StubModel):
        async def ainvoke_stream(self, *args, **kwargs):
            for chunk in [reply('')[:-2] + '先解释', '高等数学', '的学习方法。"}']:
                yield ModelResponse(content=chunk)
                if chunk == '高等数学':
                    assert frames and frames[-1]['text'] == '先解释高等数学'
    engine = AgnoAgentEngine(model_factory=lambda **_: StreamingModel(), registry=_PromptRegistry())
    with progress_channel(frames.append):
        result = await engine.invoke(AgentRequest(agent_id='test', conversation=True))
    assert result.valid and result.raw_text == '先解释高等数学的学习方法。'
    assert [f['delta'] for f in frames if f.get('type') == 'message.delta'] == ['先解释', '高等数学', '的学习方法。']


async def test_tool_status_only_completes_after_real_read_and_safe_failure():
    from zhiyin_orchestration.impl.dialogue_engine import traced
    from zhiyin_kernel.streaming import progress_channel
    from zhiyin_kernel.errors import InvalidRequest
    frames = []
    async def read(*, area):
        assert len(frames) == 1 and frames[0]['type'] == 'step.started'
        return '{"data":null}'
    with progress_channel(frames.append):
        value = await traced(read, 'workspace.read')(area='plan')
    assert value == '{"data":null}' and frames[-1]['type'] == 'step.completed'
    assert frames[0]['step_id'] == frames[-1]['step_id']
    async def fail():
        raise InvalidRequest('对象已变化')
    frames.clear()
    with progress_channel(frames.append):
        value = await traced(fail, 'workspace.action')()
    assert '对象已变化' in value and frames[-1]['type'] == 'step.failed'


async def test_read_timeout_does_not_mean_empty_data_or_cancel_committing_writes(monkeypatch):
    import asyncio
    import json
    from zhiyin_orchestration.impl.dialogue_engine import traced
    from zhiyin_kernel.streaming import progress_channel
    timeout = asyncio.timeout
    monkeypatch.setattr(asyncio, 'timeout', lambda _: timeout(0.001))
    async def slow_read():
        await asyncio.sleep(0.02)
        return '{"data":[]}'
    frames = []
    with progress_channel(frames.append):
        failed = json.loads(await traced(slow_read, 'xuezhi.search')())
    assert failed['status'] == 'timeout' and failed['retry'] is False
    assert frames[-1]['type'] == 'step.failed'
    async def write_and_receipt():
        await asyncio.sleep(0.02)
        return '{"executed":true}'
    assert json.loads(await traced(write_and_receipt, 'workspace.action')())['executed']


async def test_stream_keeps_server_assigned_run_id_when_client_omits_it(monkeypatch):
    import json
    from types import SimpleNamespace
    from zhiyin_api.controllers import conversation_controller as controller
    from zhiyin_api.dto.conversation import MessageRequest
    from zhiyin_kernel.streaming import emit_progress
    class Facade:
        async def resolve_user_id(self, request): return 'a'
        async def check_analysis_consent(self, user): pass
        async def send_message(self, user, body):
            emit_progress({'type':'run.started', 'run_id':'server-generated'})
            return SimpleNamespace(model_dump=lambda **_: {'task_id':body.task_id})
    monkeypatch.setattr(controller, 'get_facade', lambda: Facade())
    response = await controller.stream_message(None, MessageRequest(task_id='session', message='test'))
    frames = [json.loads(frame[6:]) async for frame in response.body_iterator if frame.startswith('data: ')]
    assert frames[1]['run_id'] == frames[-1]['run_id'] == 'server-generated'


async def test_native_tool_turn_does_not_duplicate_pretool_answer(monkeypatch):
    from types import SimpleNamespace
    from tests.test_orchestration import _StubModel, _PromptRegistry
    from zhiyin_orchestration.impl import dialogue_engine
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_orchestration.agent import AgentRequest
    from zhiyin_kernel.streaming import progress_channel
    class Agent:
        def __init__(self, **kwargs): pass
        async def arun(self, **kwargs):
            for event, content in [('RunContent',reply('先从一道例题开始。')), ('ToolCallStarted',''),
                                   ('ToolCallCompleted',''), ('RunContent',reply('')[:-2] + '先从'), ('RunContent','一道例题开始。"}')]:
                yield SimpleNamespace(event=event, content=content)
    monkeypatch.setattr(dialogue_engine, 'Agent', Agent)
    engine=AgnoAgentEngine(model_factory=lambda **_: _StubModel(), registry=_PromptRegistry())
    frames=[]
    with progress_channel(frames.append):
        result=await engine.invoke(AgentRequest(agent_id='career_advisor',conversation=True))
    assert result.raw_text == '先从一道例题开始。'
    texts=[f['text'] for f in frames if f.get('type')=='message.delta']
    assert texts == ['先从一道例题开始。','先从','先从一道例题开始。']


async def test_nonstream_prefers_final_assistant_message_over_tool_turn_aggregate(monkeypatch):
    from agno.run.agent import RunOutput
    from agno.models.message import Message
    from tests.test_orchestration import _StubModel, _PromptRegistry
    from zhiyin_orchestration.impl import dialogue_engine
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_orchestration.agent import AgentRequest
    class Agent:
        def __init__(self, **kwargs): pass
        async def arun(self, **kwargs):
            return RunOutput(content='我先核对资料。最终建议。',messages=[
                Message(role='assistant',content='我先核对资料。'),
                Message(role='tool',content='已查到'),Message(role='assistant',content=reply('最终建议。'))])
    monkeypatch.setattr(dialogue_engine, 'Agent', Agent)
    engine=AgnoAgentEngine(model_factory=lambda **_: _StubModel(), registry=_PromptRegistry())
    result=await engine.invoke(AgentRequest(agent_id='career_advisor',conversation=True))
    assert result.raw_text == '最终建议。'
