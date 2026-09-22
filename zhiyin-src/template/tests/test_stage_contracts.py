"""五环节产出契约的口径。

这里原来还有一整套 Loop 协调器的行为测试（start / resume / advance / run_stage）。
那个协调器装配了却**没有任何调用方** —— 活的是编排器的单轮骨架，它是第二条并行的
实现。删掉它之后，围绕它的测试也没有了主语；留下来的这三条是仍然成立、且有价值的口径。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_business.contracts import STAGE_CONTRACTS
from zhiyin_kernel.enums import LoopStage
from zhiyin_infrastructure.local.repository import LocalJsonRegistryRepository

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def registry() -> LocalJsonRegistryRepository:
    return LocalJsonRegistryRepository(str(DATA_DIR / "registry"))


def test_every_stage_has_an_output_contract() -> None:
    """五个环节一个都不能少：少一个，那个环节的产出就没有契约可校验。"""
    for stage in LoopStage:
        assert stage in STAGE_CONTRACTS, f"环节 {stage} 缺少产出契约"


def test_stage_contract_schema_is_generated_from_the_business_model() -> None:
    """契约的 Schema 由业务层模型生成，只有一处事实来源。

    为什么盯 `guide`：每轮必须以行为引导收尾是产品硬约束，而它是契约里的必填项。
    去掉它，模型就可能回一句没有下一步的总结 —— 那是本项目最不该出现的一种回复。
    """
    for stage, contract in STAGE_CONTRACTS.items():
        schema = contract.model_json_schema()
        assert schema.get("type") == "object", stage
        assert "guide" in schema.get("properties", {}), stage


@pytest.mark.asyncio
async def test_contract_lookup_is_per_stage_not_per_agent(registry) -> None:
    """同一个智能体在不同环节必须取到不同的契约。

    职业顾问同时负责 ②诊断 与 ③决策。契约按"智能体唯一的契约 id"查时，
    ②③ 会取到同一条，另一条成为无人引用的孤儿 —— 而且不报错。
    这条把 (agent_id, stage) 这个口径钉住。
    """
    diagnose = await registry.get_output_contract("career_advisor", LoopStage.DIAGNOSE)
    decide = await registry.get_output_contract("career_advisor", LoopStage.DECIDE)

    assert diagnose is not None and decide is not None
    assert diagnose.id != decide.id, "② 与 ③ 必须是两条不同的契约"
    assert diagnose.stage is LoopStage.DIAGNOSE
    assert decide.stage is LoopStage.DECIDE

    # 取不到的 (agent_id, stage) 组合返回 None，不抛异常（由调用方决定回落）
    assert await registry.get_output_contract("profile_analyst", LoopStage.REVIEW) is None
