import pytest
from zhiyin_kernel.modules import ModuleContext


@pytest.mark.asyncio
async def test_progress_matches_saved_tasks(module_definition):
    async def read(capability):
        return module_definition.fixture()[capability]
    result = await module_definition.load(ModuleContext("fixture", "fixture", read))
    assert result["data"]["total"] == 2
    assert result["data"]["completed"] == 1
