"""把"自己做好的功能模块"接进来的那条路，要真的走得通。

一个模块 = 后端取数 + 前端一整套渲染，对外表现为"模型能调的一个工具"。
三件事必须在测试里全部走一遍，否则接的时候才发现缺口：

    1. 模块交出的工具进了工具目录（模型看得见、能调）；
    2. 它产出的可视件按注册的 kind 通过服务端校验（前端才有得画）；
    3. 形状不对的产出被丢掉（不能摆到用户眼前），重名的工具在装配时就报错。

还有一条同样重要：**模块不自己决定谁能用**。工具进目录 ≠ 哪个角色都能用 ——
挂给谁仍然写在 `data/registry/agents.json` 的白名单里。
"""

from __future__ import annotations

import pytest

from zhiyin_business.policies.renderers import (
    RendererSpec,
    known_kinds,
    register_renderer,
    renderer_for,
    validate_renderables,
)
from zhiyin_infrastructure.ai.tools import ToolModule, ToolSpec, build_tool_catalog

#: 测试用的 kind 名带后缀，避免与真模块抢名字（注册表是进程级的）。
PROBE_KIND = "probe_matrix_v1"
PROBE_TOOL = "probe.matrix"


def _register_probe_renderer() -> None:
    """注册一种"对比矩阵"可视件：两行两列以上才算数。"""
    if renderer_for(PROBE_KIND) is not None:
        return

    def _validate(payload: dict) -> dict:
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) < 2:
            raise ValueError("至少要两行")
        checked = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                raise ValueError("每行至少两列")
            checked.append([str(cell)[:16] for cell in row])
        return {"columns": [str(c)[:12] for c in payload.get("columns") or []], "rows": checked}

    register_renderer(
        RendererSpec(
            kind=PROBE_KIND,
            label="对比矩阵",
            source="模块自己的取数逻辑（这里只是测试替身）",
            validate=_validate,
        )
    )


def _probe_module() -> ToolModule:
    """一个最小的模块：一个工具，产出上面那种可视件。"""

    async def handler(run_context, rows: list | None = None) -> str:
        """摆一块对比矩阵给他看。

        Args:
            rows: 每一行是一个字符串数组（测试替身里由调用方给）
        """
        box = run_context.dependencies.setdefault("renderables", [])
        box.append(
            {
                "kind": PROBE_KIND,
                "title": "两条路摆一起看",
                "payload": {
                    "columns": ["准备方式", "代价"],
                    "rows": rows or [["刷题", "慢"], ["做项目", "更慢但能讲"]],
                },
            }
        )
        return "矩阵已经摆上了。"

    return ToolModule(
        name="probe",
        tools=[ToolSpec(name=PROBE_TOOL, description="测试模块：摆一块对比矩阵", handler=handler)],
    )


def test_a_module_can_register_a_tool_and_a_renderable_kind() -> None:
    """模块的工具进目录；它产出的可视件通过服务端校验。"""
    _register_probe_renderer()
    assert PROBE_KIND in known_kinds()

    catalog = build_tool_catalog(modules=[_probe_module()])
    assert PROBE_TOOL in catalog, "模块的工具没进目录，模型看不见它"

    from types import SimpleNamespace

    context = SimpleNamespace(user_id="u1", dependencies={"renderables": []})
    import asyncio

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        catalog[PROBE_TOOL].handler(context)
    )

    kept = validate_renderables(context.dependencies["renderables"])
    assert len(kept) == 1
    assert kept[0].kind == PROBE_KIND
    # 校验函数真的跑过：列名被截到 12 字、单元格被截到 16 字
    assert kept[0].payload["columns"] == ["准备方式", "代价"]
    assert len(kept[0].payload["rows"]) == 2


def test_a_module_output_that_breaks_its_own_shape_is_dropped() -> None:
    """模块自己声明了形状，就得自己兜住：一行也算矩阵 → 丢掉。"""
    _register_probe_renderer()
    bad = [
        {
            "kind": PROBE_KIND,
            "title": "只有一行",
            "payload": {"columns": ["a"], "rows": [["只有一列"]]},
        }
    ]
    assert validate_renderables(bad) == []


def test_a_module_cannot_shadow_a_builtin_tool() -> None:
    """模块的工具名不能与内置能力重名 —— 装配时就报错，而不是悄悄顶掉一个。"""
    clash = ToolModule(
        name="bad",
        tools=[ToolSpec(name="profile.read", description="想顶掉内置的读画像")],
    )
    with pytest.raises(ValueError) as err:
        build_tool_catalog(modules=[clash])
    assert "重名" in str(err.value)


def test_a_module_tool_is_not_usable_by_everyone() -> None:
    """工具进目录 ≠ 每个角色都能用：挂给谁仍写在 agents.json 的白名单里。

    这一条守的是分工：模块只管"这个能力存在"，"哪个角色该有它"是产品口径，
    由动态资源决定 —— 两件事混在一起，能力一旦注册就等于全员开放。
    """
    import json
    from pathlib import Path

    _register_probe_renderer()
    catalog = build_tool_catalog(modules=[_probe_module()])
    assert PROBE_TOOL in catalog

    root = Path(__file__).resolve().parents[1]
    agents = json.loads((root / "data" / "registry" / "agents.json").read_text(encoding="utf-8"))
    granted = [
        agent["id"] for agent in agents["items"] if PROBE_TOOL in (agent.get("tools") or [])
    ]
    assert granted == [], "测试模块没有登记在白名单里，却已经挂给了角色"
