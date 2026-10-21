"""Apply only the profile dialogue contract additions; never resync unrelated registry data.

Run against the deployment's own environment. Default is read-only preview;
--apply requires a local backup file for the exact rows being changed.
"""
import argparse
import asyncio
import json
from pathlib import Path

import asyncpg
from zhiyin_boot.settings import Settings

PROMPTS = {'conversation.main', 'conversation.memory'}
COPIES = {'profile.field.career_focus', 'profile.field.time', 'profile.field.supplement', 'profile.field.supplement_info'}


async def main(args):
    root = Path(__file__).resolve().parents[1] / 'data' / 'registry'
    prompts = [item for item in json.loads((root / 'prompts.json').read_text(encoding='utf-8'))['items'] if item['code'] in PROMPTS]
    copies = [item for item in json.loads((root / 'copies.json').read_text(encoding='utf-8'))['items'] if item['code'] in COPIES]
    assert {item['code'] for item in prompts} == PROMPTS and {item['code'] for item in copies} == COPIES
    connection = await asyncpg.connect(Settings.from_env().postgres_dsn)
    try:
        async with connection.transaction():
            before = {
                'ai_prompt_template': [dict(row) for row in await connection.fetch('SELECT * FROM ai_prompt_template WHERE code=ANY($1::text[]) FOR UPDATE', sorted(PROMPTS))],
                'biz_registry_item': [dict(row) for row in await connection.fetch("SELECT * FROM biz_registry_item WHERE kind='copies' AND code=ANY($1::text[]) FOR UPDATE", sorted(COPIES))],
            }
            if args.apply:
                if not args.backup:
                    raise ValueError('--apply requires --backup for the previous scoped rows')
                with Path(args.backup).open('x', encoding='utf-8') as stream:
                    json.dump(before, stream, ensure_ascii=False, indent=2, default=str)
                for item in prompts:
                    await connection.execute('''INSERT INTO ai_prompt_template
                        (code,layer,agent_id,stage,name,content,params,status,sort_order,note)
                        VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10)
                        ON CONFLICT(code) DO UPDATE SET content=EXCLUDED.content, params=EXCLUDED.params,
                        note=EXCLUDED.note, updated_at=NOW()''', item['code'], item['layer'], item['agent_id'], item['stage'], item['name'],
                        item['content'], json.dumps(item['params']), item['status'], item['sort_order'], item['note'])
                for item in copies:
                    await connection.execute('''INSERT INTO biz_registry_item(kind,code,payload,status,sort_order)
                        VALUES ('copies',$1,$2::jsonb,$3,$4) ON CONFLICT(kind,code)
                        DO UPDATE SET payload=EXCLUDED.payload,status=EXCLUDED.status,sort_order=EXCLUDED.sort_order,updated_at=NOW()''',
                        item['code'], json.dumps(item, ensure_ascii=False), item['status'], item['sort_order'])
            print(json.dumps({'applied': args.apply, 'prompts': sorted(PROMPTS), 'copies': sorted(COPIES)}, ensure_ascii=False))
    finally:
        await connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup')
    asyncio.run(main(parser.parse_args()))
