import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('decision_migration', ROOT / 'scripts/migrate_decision_routing.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def legacy():
    item = next(x for x in json.loads((ROOT / 'data/registry/policy_params.json').read_text(encoding='utf-8'))['items'] if x['code'] == 'decision_routing')
    item['status'] = 'draft'
    values = item['value']
    values['min_confidence'] = values.pop('confidence_threshold')
    values['min_probability'] = values.pop('probability_threshold')
    values['prompt_version'] = 'test-v1'
    return item


def test_migration_preserves_custom_rules_and_thresholds():
    before = legacy()
    before['value']['min_confidence'] = 0.63
    before['value']['instructions'] = 'custom instructions'
    after = module.migrate(before)
    assert after['status'] == 'confirmed'
    assert after['value']['mode'] == 'active'
    assert after['value']['confidence_threshold'] == 0.63
    assert after['value']['instructions'] == 'custom instructions'
    assert 'min_confidence' in before['value']
    assert module.migrate(after)['value'] == after['value']


def test_migration_rejects_conflicting_thresholds():
    before = legacy()
    before['value']['confidence_threshold'] = 0.2
    with pytest.raises(ValueError, match='冲突'):
        module.migrate(before)


def test_migration_rejects_invalid_candidates():
    before = legacy()
    before['value']['criteria'].pop('unclear')
    with pytest.raises(ValueError):
        module.migrate(before)
