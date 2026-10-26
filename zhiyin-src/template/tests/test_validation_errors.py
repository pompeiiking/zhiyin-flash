"""请求校验失败时，用户要能看出是哪一项、该怎么改。

此前 Pydantic 的英文消息和英文 `loc` 会被统一吞成"有填写项不符合要求"：
复盘结果填错时，用户只知道"有一项不对"，但页面上没有任何一项被标出来。
"""

from zhiyin_api.app import _request_field_label, _validation_reason


def test_enum_mismatch_names_the_field_and_translates_allowed_values():
    assert _request_field_label(("body", "result")) == "复盘结果"
    assert _validation_reason("Input should be 'continue', 'adjust' or 'complete'") == "只能是：继续、调整、完成"


def test_length_and_required_errors_are_actionable():
    assert _validation_reason("String should have at most 100 characters") == "最多只能填 100 个字"
    assert _validation_reason("String should have at least 1 character") == "至少需要 1 个字"
    assert _validation_reason("Field required") == "不能为空"


def test_nested_plan_error_points_at_the_right_item_without_english_keys():
    where = _request_field_label(("body", "plans", 1, "role"))
    assert where == "方向方案的方向角色第 2 项"
    assert not any(character.isascii() and character.isalpha() for character in where)


def test_unknown_english_value_is_not_echoed_verbatim():
    assert _validation_reason("Input should be 'main', 'parallel' or 'fallback'") == "取值不在允许范围内"


def test_chinese_custom_validator_message_is_kept():
    assert _validation_reason("Value error, 调整任务时请提供调整内容") == "调整任务时请提供调整内容"


def test_unknown_location_still_says_which_item():
    assert _request_field_label(("body", "items", 2)) == "条目第 3 项"
    assert _request_field_label(("body",)) == "本次填写"
