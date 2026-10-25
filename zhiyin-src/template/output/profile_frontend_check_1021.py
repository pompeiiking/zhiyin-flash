"""Synthetic records for browser checks; separate in-memory HTTP service."""
import asyncio
from datetime import datetime, timezone
from tests.test_profile_clues import _settings
from zhiyin_boot import build_container, wire_application
from zhiyin_infrastructure.local.auth import DEMO_USER_ID
from zhiyin_kernel.blackboard import ProfileClue

container = build_container(_settings())
app = wire_application(container)

async def seed():
    service = container.profile_service
    for key, value, attributes in [
        ('major', '人工智能', {}),
        ('experience', '独立前端验收：参与课程项目，整理输入数据、复现异常、比较修复方案并记录验证结果。' * 4, {}),
        ('interest', ['重复的业务开发'], {'polarity': 'dislike', 'context': '缺少探索空间的重复劳动'}),
        ('values', '希望工作有探索空间', {}),
    ]:
        await service.update_field(DEMO_USER_ID, key, value, confidence=.9, source='conversation', attributes=attributes)
    await service.record_conflict(DEMO_USER_ID, 'major', '软件工程', label='专业', evidence=['合成冲突资料：另一份资料写软件工程'])
    now = datetime.now(timezone.utc)
    await service.replace_session_clues(DEMO_USER_ID, 'frontend-check-1021', [
        ProfileClue(id='', user_id=DEMO_USER_ID, session_id='frontend-check-1021',
            text='可能更关注弄清问题的原因', evidence=['合成验收原话：我想知道为什么会出错'],
            field_keys=['interest'], created_at=now, updated_at=now),
    ])

asyncio.run(seed())
