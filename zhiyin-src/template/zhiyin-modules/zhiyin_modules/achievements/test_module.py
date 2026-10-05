import pytest
from zhiyin_kernel.modules import ModuleContext


@pytest.mark.asyncio
async def test_achievement_count(module_definition):
    async def read(capability):
        return module_definition.fixture()[capability]
    value = await module_definition.load(ModuleContext("fixture", "fixture", read))
    assert value["data"]["unlocked"] == 1
