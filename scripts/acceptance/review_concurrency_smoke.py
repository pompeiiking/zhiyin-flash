"""本地真实 HTTP 复盘并发验收；创建独立测试账号，不输出凭据。"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default='http://127.0.0.1:8000/api/v1')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    results = []
    with httpx.Client(base_url=args.api, timeout=30) as client:
        def request(method, path, body=None, reject=False):
            response = client.request(method, path, json=body)
            envelope = response.json()
            if reject:
                assert response.is_error or envelope['code'] != 0, path
                return envelope
            assert response.is_success and envelope['code'] == 0, envelope
            return envelope['data']

        suffix = uuid4().hex[:12]
        login = request('POST', '/app/auth/register', {'account': 'audit-' + suffix, 'password': uuid4().hex})
        client.headers['Authorization'] = 'Bearer ' + login['token']
        plan = request('POST', '/app/plan/action/phases', {'name': '源码审查验收'})
        pid = plan['phases'][0]['id']
        original = {'text': '复盘并发验收任务', 'phase_id': pid}
        plan = request('POST', '/app/plan/action/tasks', original)
        tid = plan['phases'][0]['tasks'][0]['task_id']
        body = {'task_id': tid, 'reason': '时间不足', 'note': '第一次', 'result': 'adjust',
                'adjustment': {**original, 'text': '复盘调整'}, 'client_request_id': 'retry-' + suffix}
        review = request('POST', '/app/reviews', body)
        replay = request('POST', '/app/reviews', body)
        assert replay['id'] == review['id']
        assert len(request('GET', '/app/reviews')['items']) == 1
        request('POST', '/app/reviews', {**body, 'note': '修改过的重试'}, reject=True)
        results.append('创建重放只保留一条，修改内容的重放被拒')
        edit = {**body, 'note': '甲的新内容', 'expected_updated_at': review['updated_at']}
        saved = request('PUT', '/app/reviews/' + review['id'], edit)
        assert request('PUT', '/app/reviews/' + review['id'], edit) == saved
        request('PUT', '/app/reviews/' + review['id'], {**edit, 'note': '乙的旧表单'}, reject=True)
        assert request('GET', '/app/reviews')['items'][0]['note'] == '甲的新内容'
        results.append('旧版本修订被拒，重复相同修订不增加历史')
        request('PUT', '/app/plan/action/tasks/' + tid, {**original, 'text': '后来修改的任务'})
        request('POST', '/app/reviews/' + review['id'] + '/apply', reject=True)
        current = request('GET', '/app/plan/action')
        assert current['phases'][0]['tasks'][0]['text'] == '后来修改的任务'
        assert request('GET', '/app/reviews')['items'][0]['applied_at'] is None
        results.append('应用过期调整被拒，任务新内容保留，复盘未误标已应用')
        # 新读取并确认后的复盘允许正常应用，再次应用不重复执行。
        latest = request('GET', '/app/reviews')['items'][0]
        task = current['phases'][0]['tasks'][0]
        snapshot = {k: task.get(k) for k in ('text', 'status', 'progress', 'waiting_reason', 'due_date', 'scheduled_at', 'estimated_minutes', 'parent_task_id')}
        snapshot['phase_id'] = pid
        confirmed = {**edit, 'expected_updated_at': latest['updated_at'], 'expected_task': snapshot}
        request('PUT', '/app/reviews/' + review['id'], confirmed)
        applied = request('POST', '/app/reviews/' + review['id'] + '/apply')
        assert applied['applied_at']
        assert request('POST', '/app/reviews/' + review['id'] + '/apply') == applied
        assert request('GET', '/app/plan/action')['phases'][0]['tasks'][0]['text'] == '复盘调整'
        results.append('重新确认后可应用，重复应用结果不变')
        request('POST', '/app/auth/logout')
    Path(args.output).write_text(json.dumps({'checks': results, 'passed': len(results)}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(results)} real HTTP checks passed')


if __name__ == '__main__':
    main()
