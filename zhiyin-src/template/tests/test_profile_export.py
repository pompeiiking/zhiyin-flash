"""个人画像导出必须是学生能读的文件，不是接口 JSON。"""

from datetime import datetime, timezone

from zhiyin_business.services.student import _profile_export_lines
from zhiyin_kernel.blackboard import ProfileField
from zhiyin_kernel.enums import ProfileEntryStatus, ProfileSource, ProfileVerification


def field(key, label, value, *, attributes=None, source=ProfileSource.CONVERSATION,
          verification=ProfileVerification.SELF_REPORTED, origin_ref="", evidence=None):
    return ProfileField(
        key=key, label=label, value=value, confidence=0.9, source=source,
        updated_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        attributes=attributes or {}, verification=verification,
        status=ProfileEntryStatus.ACTIVE, origin_ref=origin_ref, evidence=evidence or [],
    )


def test_profile_export_lists_readable_values_and_negative_interests():
    lines = _profile_export_lines([
        field("study_year", "当前学习阶段", "大三", source=ProfileSource.RECORD,
              verification=ProfileVerification.RECORD, origin_ref="chsi-pdf://imports/abc"),
        field("interest", "兴趣", [], attributes={"items": [
            {"value": "天天应酬", "polarity": "dislike"},
            {"value": "写东西", "polarity": "like"},
        ]}, origin_ref="conversation:s1:m1", evidence=["我喜欢写点东西"]),
    ])
    text = "\n".join(lines)
    assert "【学习背景】" in text and "当前学习阶段：大三" in text
    assert "学信网学籍报告（PDF 导入）" in text
    assert "来源：资料记录" in text and "核实：资料记录" in text
    assert "兴趣：天天应酬（不喜欢）；写东西（喜欢）" in text
    assert "出处：对话原话" in text
    # 字段键、内部追溯串不能出现在给用户看的文件里。
    assert "study_year" not in text and "conversation:" not in text and "chsi-pdf://" not in text
