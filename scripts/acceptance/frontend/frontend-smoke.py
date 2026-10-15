"""Opt-in local integration: disposable account, real HTTP, no existing user data.

Usage: python scripts/acceptance/frontend/frontend-smoke.py --base http://127.0.0.1:5275
Stores only outcomes, never tokens or credentials. No administrative mutations.
"""
import argparse
import datetime
import json
import uuid
from pathlib import Path
import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--base', default='http://127.0.0.1:5275')
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
ops = json.loads((root/'zhiyin-src/template/zhiyin-web/src/api/operations.json').read_text())
results = {}
client = httpx.Client(base_url=args.base, timeout=120)


def call(key, *, params=None, **kwargs):
    op = ops[key]
    path = op['path']
    for k, v in (params or {}).items():
        path = path.replace('{'+k+'}', str(v))
    resp = client.request(op['method'], '/api/v1'+path, **kwargs)
    body = resp.json()
    entry = {'http':resp.status_code, 'code':body.get('code'), 'message':body.get('message'), 'ok':resp.is_success and body.get('code') == 0}
    results[op['method']+' /api/v1'+op['path']] = entry
    print(key, resp.status_code, body.get('code'), flush=True)
    if not entry['ok']:
        return None
    return body['data']


try:
    credentials = {'account':'integration_'+uuid.uuid4().hex[:12], 'password':uuid.uuid4().hex}
    registered = call('register', json=credentials)
    assert registered and registered['token']
    logged = call('login', json=credentials)
    client.headers['Authorization'] = 'Bearer '+logged['token']
    boot = call('bootstrap')
    call('portal')
    for key in ['sessions','workspace','notes','action','directions','calendar','achievements','trackEvents','notifications','modules','intel','report']:
        call(key)
    note = call('addNote',json={'text':'自动联调：写入、完成、回读、删除', 'kind':'todo'})
    assert note and note['id']
    changed = call('noteDone',params={'note_id':note['id']},json={'done':True})
    assert changed and changed['done']
    assert any(n['id']==note['id'] and n['done'] for n in call('notes'))
    assert call('removeNote',params={'note_id':note['id']})['removed']==note['id']
    assert not any(n['id']==note['id'] for n in call('notes'))
    call('correctProfile',params={'key':'major'},json={'value':'软件工程（联调测试）'})
    assert any(f['key']=='major' and f['value']=='软件工程（联调测试）' for f in call('workspace')['profile_panel']['fields'])
    courses = json.dumps([{'name':'联调课程','weekday':1,'start_period':1,'end_period':2,'weeks':'1-16','place':'测试教室'}],ensure_ascii=False)
    imported = call('academicImport',json={'courses':courses,'grades':'','school':'联调测试学校','term':'2026秋'})
    assert imported and imported['courses']==1
    assert call('workspace')['academic_panel']['courses'][0]['name']=='联调课程'
    call('academicFile',files={'courses_file':('courses.json',courses.encode(),'application/json')},data={'school':'联调测试学校','term':'2026秋'})
    call('academicRevoke')
    assert not call('workspace').get('academic_panel')
    call('material',files={'file':('integration.txt','联调材料：课程项目说明'.encode(),'text/plain')})
    session=call('enterTask',json={'task_code':boot['task_entries'][0]['code']})
    call('sessionTurns',params={'task_id':session['task_id']})
    call('track',json={'event':'diagnosis_view','payload':{},'client_event_id':str(uuid.uuid4())})
    for kind in ['report','direction_plan','action_plan']:
        call('versions',params={'asset_type':kind})
    export=call('export',json={'asset_type':'report','format':'pdf'})
    if export and not export.get('available'):
        results['POST /api/v1/app/assets/export']['limitation']=export.get('reason') or export.get('message') or 'available=false'
    # No real academic verification code is used in automated testing.
    for key in ['brief','portraitAnalysis','noteSuggestions','reportSummary','timetable','careerMatch','dayAdvice']:
        op=ops[key]
        path=op['path'].replace('{day}',datetime.date.today().isoformat())
        with client.stream(op['method'],'/api/v1'+path,json={'arg':480 if key=='dayAdvice' else ''}) as response:
            frames=[]
            for line in response.iter_lines():
                if line.startswith('data:'):
                    frames.append(json.loads(line[5:]))
            result=next((f for f in frames if 'result' in f),None)
            err=next((f['error'] for f in frames if 'error' in f),None)
            results[op['method']+' /api/v1'+op['path']]={'http':response.status_code,'ok':bool(result) and not err,'frames':len(frames),'error':err}
            print(key, 'SSE', bool(result), flush=True)
    call('logout')
    expired=client.get('/api/v1/app/bootstrap')
    assert expired.status_code==401 or expired.json().get('code')==1004
    results['POST /api/v1/app/auth/logout']['revocation_verified']=True
finally:
    out=root/'docs/前端/后端接入/基础联调结果.json'
    out.write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base':args.base,'isolated_test_account':True,'results':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    client.close()

assert results and all(value.get('ok') for value in results.values()), 'Some integration checks failed; inspect 基础联调结果.json'
