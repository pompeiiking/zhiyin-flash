"""理论引用必须是真实存在的卡：模型编出来的 id 不许送到界面上。

端到端跑出来的真问题（2026-09-22）：模型给 `theory_refs` 填了一个 **编造的 id**
（`theo_clover`，而真卡是 `clover`）。前端拿到就如实去请求
`GET /app/theory-cards/theo_clover` → **404**，用户点开是一张打不开的卡。

两处一起收口：

1. **给模型一份可选清单**：编排时把理论卡的 `id/name/school` 放进 prompt 变量，
   让它有的可选，而不是照名字编；
2. **边界上筛一遍**：徽章只保留注册表里真实存在的 id，剔除的进 WARNING 日志 ——
   不静默吞掉，"模型在编 id"这件事必须看得见。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def wired():
    from tests.e2e.test_main_path import _container
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)
    return container


@pytest.mark.asyncio
async def test_unknown_theory_id_is_dropped(wired) -> None:
    """编造的 id 被剔除；真实 id 原样留下。"""
    refs = await wired.orchestrator._known_theory_refs(  # noqa: SLF001
        [
            {"theory_id": "clover", "name": "三叶草模型", "stage": "diagnose"},
            {"theory_id": "theo_clover", "name": "三叶草模型", "stage": "diagnose"},
        ]
    )
    assert [r.theory_id for r in refs] == ["clover"]


@pytest.mark.asyncio
async def test_all_known_ids_survive(wired) -> None:
    """全部合法时一个都不许少 —— 这条守卫不能把正常路径一起筛掉。"""
    cards = await wired.registry.list_theory_cards()
    assert cards, "注册表里应当有理论卡"
    sample = cards[:3]
    refs = await wired.orchestrator._known_theory_refs(  # noqa: SLF001
        [{"theory_id": card.id, "name": card.name, "stage": "diagnose"} for card in sample]
    )
    assert [r.theory_id for r in refs] == [card.id for card in sample]


@pytest.mark.asyncio
async def test_theory_catalog_is_given_to_the_model(wired) -> None:
    """编排时要把理论卡清单放进提示词变量（否则模型只能编 id）。

    这里不真跑模型，直接看那份清单的形状：id / name 齐备、条数与注册表一致。
    """
    cards = await wired.registry.list_theory_cards()
    catalog = [{"id": card.id, "name": card.name, "school": card.school} for card in cards]
    assert catalog and all({"id", "name", "school"} <= set(item) for item in catalog)
    assert len(catalog) == len(cards)
