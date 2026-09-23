"""可视件上的每个点都得追得回一条真实数据 —— 模型碰不到数值。

"让智能体自己决定给用户摆一块东西"（图 / 时间线 / 对比矩阵…）有一个天然风险：
它可以把一组好看的分数编出来，而用户没法分辨哪个点是编的。这里的做法是把这条路堵死：

1. **模型只能挑类别**：工具 `chart.render(kind, title)` 的参数里没有位置传数值，
   点位由工具自己从库里读（画像把握度 / 已存方案的匹配度 / 已存计划的完成情况）；
2. **上层再校验一遍**：工具写进回传盒子的东西，编排器还要按注册表逐件验一次
   （kind 没注册过、payload 形状不对、点少于两个……一律丢掉并留日志）。

第 1 条在 `tests/test_infrastructure.py` 里钉（工具侧），这一支钉第 2 条（服务端校验）。
"""

from __future__ import annotations

from zhiyin_business.policies.renderers import known_kinds, renderer_for, validate_renderables


def _bars(points, title="这几项你现在各有多少把握", unit="%"):
    return {"kind": "bars_chart", "title": title, "payload": {"unit": unit, "points": points}}


def test_a_valid_renderable_from_the_tool_passes() -> None:
    """工具按真实数据生成的可视件正常通过。"""
    kept = validate_renderables(
        [_bars([{"label": "专业", "value": 90}, {"label": "兴趣方向", "value": 60}])]
    )
    assert len(kept) == 1
    assert kept[0].kind == "bars_chart"
    assert kept[0].payload["points"] == [
        {"label": "专业", "value": 90.0},
        {"label": "兴趣方向", "value": 60.0},
    ]


def test_one_point_is_not_a_chart() -> None:
    """只有一个点画不成图 —— 丢掉。"""
    assert validate_renderables([_bars([{"label": "专业", "value": 90}])]) == []


def test_points_without_a_name_are_dropped() -> None:
    """有点没名字：用户看不懂那一根是什么，整件丢掉。"""
    got = validate_renderables(
        [_bars([{"label": "  ", "value": 1}, {"label": "兴趣", "value": 2}])]
    )
    assert got == []


def test_garbage_never_reaches_the_user() -> None:
    """结构不对一律丢掉 —— 摆到眼前的东西里没有"看起来像那么回事"的位置。"""
    assert validate_renderables(None) == []
    assert validate_renderables("一件东西") == []
    assert validate_renderables([{"kind": "没注册过的类型", "payload": {}}]) == []
    assert validate_renderables([{"kind": "bars_chart"}]) == []  # 缺 payload
    assert validate_renderables([_bars("不是数组")]) == []
    assert validate_renderables([_bars([{"label": "x"}, {"label": "y"}])]) == []


def test_only_registered_kinds_are_accepted() -> None:
    """没注册过的 kind 一律拒绝：前端没有那个组件，摆出去就是一块空白。"""
    assert "bars_chart" in known_kinds()
    assert renderer_for("bars_chart") is not None
    assert renderer_for("chart") is None  # 老名字不再接受（结构已经变成 renderables）


def test_the_contract_has_no_place_for_the_model_to_pass_numbers() -> None:
    """契约里**没有**让模型传图点位的字段：它只能调工具，而工具只收类别名。

    这一条是上面所有校验的前提。哪天有人在契约里加了个"想摆什么 + 数据点"的字段，
    模型编数字的路就又通了 —— 那时这张守卫会红。
    """
    from zhiyin_business.contracts import STAGE_CONTRACTS

    offenders: list[str] = []
    for stage, contract in STAGE_CONTRACTS.items():
        for name, field in contract.model_fields.items():
            text = f"{name} {field.description or ''}".lower()
            if "chart" in text or "图表" in text or "画图" in text:
                offenders.append(f"{stage.value}.{name}")
    assert not offenders, (
        f"契约里出现了与可视件有关的字段：{offenders}。"
        "可视件只能由工具按真实数据生成，不要给模型一个能填数字的位置。"
    )
