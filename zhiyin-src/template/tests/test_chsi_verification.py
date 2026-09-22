"""学信网在线验证报告核验：解析与失败分流的守卫（不联网）。

为什么要单独守这一层：报告页是**别人家的 HTML**。
它能变、也不欠我们一个通知。所以这里的用例把三件事钉住：

1. 码的格式（形状不对就不该发请求，白跑一趟还显得我们没校验）；
2. 错误页要读得出人话（"此在线验证码无效。"），并且归类正确 ——
   过期和无效对用户是两种动作；
3. 字段解析按标签走，**换版式也要能取到** ——
   同一份内容分别用 `<td>` 相邻和 `<div>` 跨行两种排法，结果必须一致。

真实网络只在联调时跑（见 `zhiyin_infrastructure.chsi.client`），
不放进单测：CI 不该依赖 chsi.com.cn 的可用性。
"""

from __future__ import annotations

from zhiyin_infrastructure.chsi.client import (
    classify_error,
    detect_error,
    is_well_formed,
    normalize_code,
    parse_report,
)
from zhiyin_data_sdk.gateways.chsi import ChsiReportKind, ChsiVerifyErrorKind

# 版式一：报告最常见的样子 —— 标签与值在相邻的单元格里
REPORT_TABLE_LAYOUT = """
<div class="m_cnt_m">
  <h4 class="main_title">教育部学籍在线验证报告</h4>
  <table>
    <tr><td>姓名</td><td>张某某</td><td>性别</td><td>男</td></tr>
    <tr><td>学号</td><td>2023010234</td></tr>
  </table>
  <table>
    <tr><td>院校名称</td><td colspan="3">某某大学</td></tr>
    <tr><td>院系名称</td><td>土木工程学院</td><td>专业名称</td><td>土木工程</td></tr>
    <tr><td>层次</td><td>本科</td><td>学制</td><td>4</td></tr>
    <tr><td>入学日期</td><td>2023-09-01</td><td>学籍状态</td><td>在学</td></tr>
  </table>
  <p>在线验证码：123456789012</p>
  <p>报告编号：ABC123456789</p>
  <p>验证日期：2026-09-21</p>
</div>
<div class="flex-base"><div class="foot-wrap">学信网</div></div>
"""

# 版式二：标签与值被拆到相邻的块里（跨行）—— 站点改版时很可能变成这样
REPORT_BLOCK_LAYOUT = REPORT_TABLE_LAYOUT.replace(
    '<tr><td>院校名称</td><td colspan="3">某某大学</td></tr>',
    "<div>院校名称</div>\n<div>某某大学</div>",
)

ERROR_PAGE = """
<div class="m_cnt_m">
  <div class="result-error">
    <div class="msg-icon"></div>
    <h2>此在线验证码无效。</h2><a href="/xlcx/bgcx.jsp" class="btn_blue">重新查询</a>
  </div>
</div>
<div class="flex-base"><div class="foot-wrap">学信网</div></div>
"""


def _as_dict(html: str) -> dict[str, str]:
    _, fields, _ = parse_report(html, code="123456789012")
    return {field.key: field.value for field in fields}


def test_code_shape_matches_the_official_rule() -> None:
    """12 位数字，或 A / X 开头的 16 位字母数字 —— 口径来自学信网验证页自身。"""
    assert is_well_formed("123456789012")
    assert is_well_formed("A1B2C3D4E5F6G7H8")
    assert is_well_formed("XABCDEFGHIJKLMNO")
    assert not is_well_formed("12345")
    assert not is_well_formed("B1234567890123456")  # B 开头不在官方口径里
    assert not is_well_formed("A1B2C3D4E5F6G7H")   # 少一位


def test_pasted_code_is_cleaned_before_checking() -> None:
    """用户从报告里复制常常带空格或连字符，不该因此被判成格式错误。"""
    assert normalize_code(" 1234-5678 9012 ") == "123456789012"
    assert is_well_formed(normalize_code("a1b2 c3d4 e5f6 g7h8"))


def test_error_page_yields_the_official_message() -> None:
    assert detect_error(ERROR_PAGE) == "此在线验证码无效。"
    assert detect_error(REPORT_TABLE_LAYOUT) == ""  # 正常报告页不该被误判成错误


def test_error_kind_splits_expired_from_invalid() -> None:
    """过期和无效对用户是两种动作：一个去延长/重申请，一个去对码。"""
    assert classify_error("此在线验证码无效。") is ChsiVerifyErrorKind.INVALID_CODE
    assert classify_error("该报告已过有效期，请重新申请。") is ChsiVerifyErrorKind.EXPIRED


def test_fields_are_parsed_by_label() -> None:
    values = _as_dict(REPORT_TABLE_LAYOUT)
    assert values["student_name"] == "张某某"
    assert values["school"] == "某某大学"
    assert values["major"] == "土木工程"
    assert values["degree_level"] == "本科"
    assert values["enrollment_status"] == "在学"
    assert values["chsi_report_no"] == "ABC123456789"
    # 报告编号后面还有"验证日期"一行，不能被吞进编号里
    assert "验证日期" not in values["chsi_report_no"]


def test_report_kind_is_recognised() -> None:
    kind, _, _ = parse_report(REPORT_TABLE_LAYOUT, code="123456789012")
    assert kind is ChsiReportKind.ENROLLMENT
    kind, _, _ = parse_report(
        REPORT_TABLE_LAYOUT.replace("教育部学籍在线验证报告", "教育部学历证书电子注册备案表"),
        code="123456789012",
    )
    assert kind is ChsiReportKind.EDUCATION


def test_same_content_survives_a_layout_change() -> None:
    """换版式（标签与值跨行）也得取到同样的值 —— 这是"按标签不按 DOM"的兑现。"""
    assert _as_dict(REPORT_BLOCK_LAYOUT)["school"] == "某某大学"


def test_personal_identifiers_are_not_treated_as_profile_fields() -> None:
    """身份证号会被解析出来（它在报告上），但不该进业务层允许写画像的那张表的白名单。

    这里守的是"解析归解析、入库归入库"这条边界：
    解析器不认识画像口径，**白名单**才决定写什么。

    白名单的位置变过一次：原来写在 `ai_tasks.py` 的 `_CHSI_PROFILE_KEYS`，
    现在在动态资源 `data/registry/chsi_fields.json`（多写一个字段进画像是一个
    隐私决定，不该由一段代码顺手决定，改它也不该发版）。
    守卫跟着搬到新位置——**守的东西没变：身份证号与验证码永远不在白名单里。**
    """
    import json
    from pathlib import Path

    registry = Path(__file__).resolve().parents[1] / "data" / "registry"
    items = json.loads((registry / "chsi_fields.json").read_text(encoding="utf-8"))["items"]
    allowed = {item["key"] for item in items}

    assert "id_card" not in allowed
    # 在线验证码等于这份报告的钥匙，同样不写进画像
    assert "chsi_code" not in allowed
    assert "school" in allowed
