"""Real-model continuity checks with synthetic in-memory histories, never student rows.

Semantic quality is reviewed from the saved replies, not inferred from keyword checks.
Only model configuration is read from the local database.
"""
import asyncio
import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

TEMPLATE = Path(__file__).resolve().parents[1]
for package in TEMPLATE.glob('zhiyin-*'):
    if package.is_dir():
        sys.path.insert(0, str(package))
sys.stdout.reconfigure(encoding='utf-8')


def _collect_frame(frames: list, item: dict) -> None:
    # Retain protocol metadata; avoid duplicating full streamed text.
    frames.append({k: v for k, v in item.items() if k not in {'text', 'delta'}})


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', help='Run selected case names only')
    parser.add_argument('--suite', choices=['continuity', 'exploration'], default='continuity')
    parser.add_argument('--output', help='Optional evidence JSON path')
    args = parser.parse_args()
    import asyncpg
    from zhiyin_boot import Settings, build_container
    from zhiyin_business.ports.orchestrator import TurnRequest
    from zhiyin_business.services.dynamic_config import load_snapshot
    from zhiyin_business.services.conversation_ledger import ConversationLedger
    from zhiyin_infrastructure.ai.router import AiModelRouter
    from zhiyin_infrastructure.postgres.ai_config import PostgresAiConfigRepository
    from zhiyin_kernel.streaming import progress_channel

    settings = Settings.from_env()
    parsed = urlsplit(settings.postgres_dsn)
    if parsed.hostname not in {'postgres', 'zhiyin-flash-postgres', 'localhost', '127.0.0.1'}:
        raise RuntimeError('Only local development model configuration may be read')
    credentials = parsed.netloc.rsplit('@', 1)[0] if '@' in parsed.netloc else ''
    dsn = urlunsplit(parsed._replace(netloc=(credentials + '@' if credentials else '') + '127.0.0.1:55432'))
    conn = await asyncpg.connect(dsn, timeout=5)
    try:
        route = await AiModelRouter(PostgresAiConfigRepository(conn,
            llm_base_url=settings.llm_base_url, llm_model=settings.llm_model,
            embedding_base_url=settings.embedding_base_url, embedding_model=settings.embedding_model)).resolve('llm')
    finally:
        await conn.close()
    if route is None:
        raise RuntimeError('No configured model')
    c = build_container(Settings(use_remote_llm=True, llm_api_key=route.api_key,
        llm_base_url=route.base_url, llm_model=route.model_code, env='test',
        local_data_dir=str(TEMPLATE / 'data'), local_registry_dir=str(TEMPLATE / 'data/registry'),
        local_knowledge_dir=str(TEMPLATE / 'data/knowledge'),
        local_object_dir=str(TEMPLATE.parents[1] / 'output/dialogue-continuity-objects')))
    await load_snapshot(c.registry_service)
    output = TEMPLATE.parents[1] / ('output/dialogue-exploration-real.json' if args.suite == 'exploration'
                                   else 'output/dialogue-continuity-real.json')
    if args.output:
        output = Path(args.output).resolve()
    evidence = {'model': route.model_code, 'environment': 'synthetic in-memory; real model',
        'prompt_sha256': sha256((TEMPLATE / 'data/registry/prompts.json').read_bytes()).hexdigest(),
        'cases': [], 'semantic_review': 'pending human/agent review of saved replies'}

    async def run(case, history, questions):
        if args.case and case not in args.case:
            return
        user = 'continuity_synthetic_' + uuid4().hex[:12]
        session = await c.orchestrator.enter_task(user, 'free_chat')
        for role, text in history:
            await c.memory_service.record_turn(user, session.id, role='agent' if role == 'assistant' else role, text=text,
                loop_stage=session.loop_stage, agent_id='career_advisor' if role == 'assistant' else '')
        for index, question in enumerate(questions):
            frames, start = [], time.monotonic()
            with progress_channel(partial(_collect_frame, frames)):
                result = await c.orchestrator.handle_message(TurnRequest(user_id=user, task_id=session.id,
                    message=question, client_msg_id=uuid4().hex))
            evidence['cases'].append({'case': case, 'turn': index + 1, 'history': history,
                'input': question, 'messages': [m.model_dump(mode='json') for m in result.messages],
                'frames': frames, 'elapsed': round(time.monotonic()-start, 2),
                'has_saved_plan': await c.asset_service.get_action_plan(user) is not None,
                'profile_fields': [f.key for f in await c.profile_service.get_fields(user)],
                'exploration_after': (await ConversationLedger(c.student_state).read(user, session.id)).get('exploration')})
            output.parent.mkdir(exist_ok=True)
            output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'case': case, 'turn': index + 1, 'elapsed': evidence['cases'][-1]['elapsed']}, ensure_ascii=False), flush=True)

    if args.suite == 'exploration':
        history = [('user', '我是大一人工智能专业，想聊聊自己的兴趣，先不要保存长期画像或安排任务。'),
            ('assistant', '有没有哪件事做起来觉得时间过得快一点？'), ('user', '调bug'),
            ('assistant', '调通之后你是松一口气，还是想搞清楚它为什么错？')]
        for repeat in range(2):
            await run(f'debug-mechanism-{repeat + 1}', history, ['搞清楚为什么错',
                '有次程序一直算不对，发现列表里的数字其实是字符串。',
                '我会想知道读文件时为什么变成了字符串，查明白之后还挺开心。'])
        await run('low-burden', history, ['不知道，想不起具体例子', '还是想不起来，你先帮我分析一下，不要再问了。'])
        await run('switch-topic', history, ['先不聊代码了，我想聊大学社团怎么选。',
            '想认识朋友，不过不太喜欢一下子面对很多人。'])
        await run('respect-pause', history, ['今天先到这里，不用安排下次任务。'])
        await run('direct-fact', [], ['一句话告诉我什么是bug，不要追问。'])
        await run('correction-and-quote', history, ['刚才说错了，我其实不喜欢调bug。想搞清原因是我同学的想法，不是我。先别问，回应一下就好。'])
        print(json.dumps({'cases': len(evidence['cases']), 'evidence': str(output)}))
        if any(row['has_saved_plan'] or row['profile_fields'] for row in evidence['cases']):
            raise AssertionError('Exploration fixtures declined permanent writes, but a profile/plan was saved')
        return

    history = [('user', '我是大一人工智能专业，想了解自己是否适合算法方向。先聊聊，不要保存画像或计划。'),
        ('assistant', '数学课，比如线性代数和概率，目前学起来感觉怎么样？')]
    await run('short-answer-followed-by-unknown', history, ['还可以', '不知道，没什么项目经历'])
    await run('no-interrogation', history, ['还可以，别一直问问题，给我一个现在能试的小建议，不用保存。'])
    await run('respect-pause', history, ['今天先不聊了，我想休息。'])
    await run('direct-fact', [], ['只解释一下什么是线性代数，一句话就好。'])
    await run('explicit-future-wait', history, ['我想等期末成绩出来再讨论方向，先到这里。'])
    print(json.dumps({'cases': len(evidence['cases']), 'evidence': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
