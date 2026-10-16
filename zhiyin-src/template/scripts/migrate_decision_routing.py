"""显式修复旧 Kev 策略；默认只预览，--apply 确认启用并保存备份。"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for package in ROOT.glob('zhiyin-*'):
    sys.path.insert(0, str(package))

from zhiyin_business.policies.decision_routing import DecisionRoutingConfig


def migrate(payload):
    result = dict(payload)
    values = dict(result['value'])
    for old, new in [('min_confidence', 'confidence_threshold'), ('min_probability', 'probability_threshold')]:
        if old in values:
            previous = values.pop(old)
            if new in values and values[new] != previous:
                raise ValueError(f'策略新旧字段冲突：{old}/{new}')
            values[new] = previous
    version = values.pop('prompt_version', None)
    values['mode'] = 'active'
    DecisionRoutingConfig.model_validate(values)
    result.update(status='confirmed', value=values)
    result['note'] = '已按当前契约确认 Kev 意图路由；保留分类规则与阈值。' + (f'原提示版本：{version}。' if version else '')
    return result


async def run(apply, backup):
    from zhiyin_boot.settings import Settings
    from zhiyin_infrastructure.postgres.database import PostgresDatabase
    db = PostgresDatabase(Settings.from_env().postgres_dsn, min_size=1, max_size=1)
    try:
        raw = await db.fetchval("SELECT payload FROM biz_registry_item WHERE kind='policy_params' AND code='decision_routing'")
        if raw is None:
            raise ValueError('未找到 Kev 策略，不能迁移')
        original = json.loads(raw) if isinstance(raw, str) else raw
        updated = migrate(original)
        print(json.dumps(updated, ensure_ascii=False, indent=2))
        if apply:
            # 排他创建，避免覆盖已有回滚备份；更新时拒绝并发配置变动。
            with Path(backup).open('x', encoding='utf-8') as file:
                json.dump({'saved_at': datetime.now(timezone.utc).isoformat(), 'payload': original}, file, ensure_ascii=False, indent=2)
            changed = await db.execute("UPDATE biz_registry_item SET payload=$1::jsonb, updated_at=NOW() WHERE kind='policy_params' AND code='decision_routing' AND payload=$2::jsonb", json.dumps(updated), json.dumps(original))
            if changed != 'UPDATE 1':
                raise RuntimeError('策略已被其他进程修改，本次未覆盖，请重新读取')
            print('已更新一条 Kev 策略；其他动态配置保持原样。')
    finally:
        await db.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', default='decision-routing-before.json')
    args = parser.parse_args()
    asyncio.run(run(args.apply, args.backup))
