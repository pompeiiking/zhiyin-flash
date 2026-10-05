from pathlib import Path
import pytest
from zhiyin_modules import discover


@pytest.fixture
def module_definition(request):
    return discover()[Path(str(request.fspath)).parent.name]
