import copy

import pytest

from zhiyin_kernel.modules import ModuleContext


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture,total,completed,empty", [("normal", 2, 1, False), ("empty", 0, 0, True)])
async def test_skill_uses_saved_task_states_without_mutating_inputs(module_definition, fixture, total, completed, empty):
    data = module_definition.fixture(fixture)
    before = copy.deepcopy(data)
    reads = []

    async def read(capability):
        reads.append(capability)
        return data[capability]

    result = await module_definition.load(ModuleContext("fixture", "fixture", read))
    assert result["data"]["total"] == total
    assert result["data"]["completed"] == completed
    assert result["data"]["summary"] == (
        f"你的计划共有 {total} 项任务，目前已完成 {completed} 项。" if fixture == "normal"
        else "你还没有已保存的行动计划。")
    assert result["empty"] is empty
    assert reads == ["plan.read"] and data == before


def test_skill_rejects_invented_completion_counts(module_definition):
    with pytest.raises(ValueError):
        module_definition.validate({"data": {"has_plan": True, "tasks": [], "total": 5, "completed": 3}})


@pytest.mark.parametrize("has_plan,summary", [
    (True, "你的计划共有 0 项任务，目前已完成 0 项。"),
    (False, "你还没有已保存的行动计划。"),
])
def test_skill_summary_is_derived_from_validated_data(module_definition, has_plan, summary):
    result = module_definition.validate({"data": {"has_plan": has_plan, "tasks": [], "total": 0,
        "completed": 0, "summary": "我已经替你新增了 100 项任务。"}})
    assert result["data"]["summary"] == summary


@pytest.mark.asyncio
async def test_skill_preserves_sdk_failure(module_definition):
    async def read(_):
        raise ValueError(module_definition.fixture("error")["error"])

    with pytest.raises(ValueError, match="计划读取失败"):
        await module_definition.load(ModuleContext("fixture", "fixture", read))


@pytest.mark.asyncio
async def test_skill_consumes_controller_input_and_rejects_stale_upstream_data(module_definition):
    async def read(capability):
        return module_definition.fixture("normal")[capability]
    result = await module_definition.load(ModuleContext("fixture", "fixture", read, {"expected_total": 2, "expected_completed": 1}))
    assert result["data"]["completed"] == 1
    with pytest.raises(ValueError, match="上游输入"):
        await module_definition.load(ModuleContext("fixture", "fixture", read, {"expected_total": 100}))
