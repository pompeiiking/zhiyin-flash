"""Typed correction limits replace the obsolete universal 40-character cap."""
import pytest

from tests.test_profile_clues import _profile_service
from zhiyin_kernel.errors import InvalidRequest


async def test_long_experience_can_be_corrected_without_truncation():
    profiles = await _profile_service()
    text = '我在课程项目中复现问题、比较方案并验证结果。' * 20
    saved = await profiles.correct_field('review-length', 'experience', text)
    assert saved.value == text
    assert (await profiles.get_fields('review-length', ['experience']))[0].value == text


async def test_identity_field_keeps_its_own_short_limit():
    profiles = await _profile_service()
    with pytest.raises(InvalidRequest):
        await profiles.correct_field('review-length', 'major', '专' * 41)
    assert not await profiles.get_fields('review-length')


async def test_experience_over_its_own_limit_is_rejected():
    profiles = await _profile_service()
    with pytest.raises(InvalidRequest):
        await profiles.correct_field('review-length', 'experience', '经' * 12001)
    assert not await profiles.get_fields('review-length')
