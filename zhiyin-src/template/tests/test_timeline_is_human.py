"""复盘时间线与柱状图：**给用户看的东西必须是人话，而且是真数**。

两条账，都是 issue 证据截图（`docs/issue-assets/2026-09-25/`）里暴露出来的：

1. 复盘时间线把**内部事件码**当标题、把 **Python 字典的 repr** 当说明写给了用户
   （截图 1：`review_warning_show` / `{'has_review': True}`）。它读起来是一串英文下划线，
   而那条记录本该说的是"你当时看了一眼复盘提醒"。
2. 柱状图的点位契约是 0–1 的比值，而生产者从库里直接读的分值量纲并不统一
   （0–1 / 0–100 / 0–10000）。契约一旦被破坏，前端会把它当比值再乘 100 ——
   用户读到"740000 分"，三根柱子还全长一样（截图 3/4/6）。

这里钉住的是**源头**：登记表里每个前端事件都要有人话名字；时间线落库不带原始码与
字典 repr；默认柱状图的点无论上游给什么量纲，出去时一定过得了 `validate_renderables`。
"""

from __future__ import annotations

import json
from pathlib import Path

from zhiyin_business.services.orchestrator import _default_bars, _renderables_for_turn
from zhiyin_kernel.enums import LoopStage

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = TEMPLATE_ROOT / "data" / "registry" / "track_events.json"
FUNCTION_SERVICE = (
    TEMPLATE_ROOT / "zhiyin-business" / "zhiyin_business" / "services" / "function.py"
)


def _registry_items() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["items"]


def test_every_frontend_event_has_a_human_label() -> None:
    """凡是从客户端上报的事件，登记表里必须有人话名字。

    没有名字的后果不是"少一行"，而是**时间线里出现一串英文下划线**
    （`review_warning_show`）—— 那是内部代号，不该出现在给学生看的复盘里。
    """
    missing = [
        item["code"]
        for item in _registry_items()
        if item.get("channel") == "frontend" and not str(item.get("label") or "").strip()
    ]
    assert not missing, (
        "这些前端埋点事件在 data/registry/track_events.json 里没有 label（复盘时间线拿它当标题）：\n  "
        + "\n  ".join(missing)
    )


def test_labels_are_not_codes() -> None:
    """名字不能就是事件码本身，也不能是别的英文下划线串。"""
    bad = [
        item["code"]
        for item in _registry_items()
        if item.get("channel") == "frontend"
        and str(item.get("label") or "").strip() == item["code"]
    ]
    assert not bad, f"这些事件的 label 直接抄了 code：{bad}"


def test_timeline_never_stores_raw_code_or_dict_repr() -> None:
    """落库的那一行不许是"事件码 + 字典 repr"。

    这条读源码而不是跑服务：`record_track_event` 的落库语句就在一个文件里，
    而"把 `event` 当标题、把 `str(payload)` 当说明"正是 issue 截图 1 的成因。
    写成静态断言，是因为它一旦回归，症状只在复盘那一屏出现（没人会天天点开）。
    """
    source = FUNCTION_SERVICE.read_text(encoding="utf-8")
    assert "title=event," not in source, "复盘时间线的标题不该直接用事件码（见 issue 截图 1）"
    assert "detail=str(payload)" not in source, "复盘时间线的说明不该写 payload 的 repr"
    assert "title=title or" in source, "落库应当使用 Facade 传进来的人话标题"


def test_default_bars_refuses_out_of_range_scores() -> None:
    """分值超出 0–1 就**不画图** —— 这是项目已定的口径（宁可没有图，也不画量纲不明的数）。

    我第一版在这里做了"按量级悄悄折算"，撞上了仓库里已有的
    `test_default_chart_rejects_model_score_outside_ratio_range`：契约是
    `contracts/decide.py` 的 `match_score: ge=0.0, le=1.0`，
    上游给 90 这种值应当被拒绝，而不是被服务端猜成 0.9。
    """
    assert _renderables_for_turn(
        [], LoopStage.DECIDE, {"plans": [{"name": "甲", "match_score": 90}, {"name": "乙", "match_score": 60}]}
    ) == []
    # 契约内的分值照常出图
    good = _default_bars(
        LoopStage.DECIDE, {"plans": [{"name": "甲", "match_score": 0.74}, {"name": "乙", "match_score": 0.64}]}
    )
    assert good is not None
    assert [point["value"] for point in good.payload["points"]] == [0.74, 0.64]


def test_charts_coming_from_the_model_are_validated_too() -> None:
    """从"回传盒子"进来的可视件**也要过校验**。

    这是 issue 截图 3/4/6 的真正口子：`_renderables_for_turn` 原先写的是
    `kept = list(from_model)` —— 只要里面已经有一张柱状图就直接返回，
    **连校验都不做**。于是模型侧塞进来的分值（7400 那种）可以绕过
    `validate_renderables` 一路走到前端，前端再当比值乘 100。
    """
    chart = _default_bars(
        LoopStage.DECIDE, {"plans": [{"name": "甲", "match_score": 0.74}, {"name": "乙", "match_score": 0.64}]}
    )
    assert chart is not None
    tampered = chart.model_copy(
        update={
            "payload": {
                "unit": "分",
                "points": [{"label": "甲", "value": 7400}, {"label": "乙", "value": 6400}],
            }
        }
    )
    assert _renderables_for_turn([tampered], LoopStage.DECIDE, {}) == [], (
        "越界的图表点必须被拦下（不能因为是模型给的就直接交给用户）"
    )


APPLICATION = TEMPLATE_ROOT / "zhiyin-api" / "zhiyin_api" / "facade" / "application.py"
REVIEW_OVERLAY = TEMPLATE_ROOT / "zhiyin-web" / "src" / "components" / "console" / "ReviewOverlay.vue"


def test_every_frontend_event_says_whether_it_belongs_on_the_timeline() -> None:
    """登记表必须显式表态：这条事件算不算「发生过的事」。

    留一个默认值是很危险的 —— 新加一条"进了某一屏"的埋点，它会悄悄混进复盘，
    而复盘里每多一条使用痕迹，用户读到"我做过什么"的可信度就少一分。
    实测过的后果：一次核验跑完，复盘里积了 50 行一模一样的文本。
    """
    items = _registry_items()
    missing = [
        item["code"]
        for item in items
        if item.get("channel") == "frontend" and "timeline" not in item
    ]
    assert not missing, (
        "这些前端埋点事件没有写明 timeline（true=发生过的事，false=只是使用痕迹）：\n  "
        + "\n  ".join(missing)
    )
    marked_false = [item["code"] for item in items if item.get("timeline") is False]
    assert marked_false, "一条 false 都没有：说明这张表还没真的分类过"


def test_usage_telemetry_never_reaches_the_review_timeline() -> None:
    """`timeline=false` 的不落时间线（应用层是唯一拿得到登记表的地方）。"""
    source = APPLICATION.read_text(encoding="utf-8")
    assert "if not spec.timeline:" in source, (
        "应用层没有按 timeline 过滤：使用痕迹会一路落进复盘时间线"
    )


def test_review_timeline_collapses_identical_records() -> None:
    """同一条记录合并成一行、次数写在后面（50 行同一个文本就是"在刷屏"）。"""
    source = REVIEW_OVERLAY.read_text(encoding="utf-8")
    assert "const rows = computed" in source, "复盘时间线没有做合并"
    assert "row.n > 1" in source and "次" in source, "合并之后要把次数写出来 —— 不隐藏事实"
