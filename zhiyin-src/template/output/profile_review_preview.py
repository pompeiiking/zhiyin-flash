"""Isolated HTTP preview with synthetic profile records, never a production DB."""
import asyncio
from tests.test_profile_clues import _settings
from zhiyin_boot import build_container, wire_application
from zhiyin_infrastructure.local.auth import DEMO_USER_ID

container = build_container(_settings())
app = wire_application(container)

async def seed():
    await container.profile_service.update_field(DEMO_USER_ID, 'experience',
        '隔离验收经历：参与课程项目，整理输入数据、复现问题、比较修复方案并记录验证结果。' * 5,
        confidence=.9, source='conversation', label='项目经历')
    await container.profile_service.update_field(DEMO_USER_ID, 'interest', ['重复的业务开发'],
        confidence=.9, source='conversation', label='兴趣与偏好',
        attributes={'polarity': 'dislike', 'context': '缺少探索空间的重复劳动'})

asyncio.run(seed())
