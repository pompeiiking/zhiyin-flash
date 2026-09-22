"""Port 契约测试的实现注册表。

用法（新增一个实现时**只改这一处**）：

注册后，`test_repository_contract.py` 里的每一条语义断言都会自动对这个新实现
跑一遍。这就是"换实现只改装配"从口号变成门禁的地方：语义漂移（版本不单调、
行为日志被改、影响面多算）在合入前就会失败，而不是等联调时才暴露。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

RepositoryFactory = Callable[[], Any]
GatewayFactory = Callable[[Any], Any]


def _memory_repositories() -> dict[str, RepositoryFactory]:
    from zhiyin_infrastructure.local.repository import (
        InMemoryAssetRepository,
        InMemoryBehaviorRepository,
        InMemoryConversationMemoryRepository,
        InMemoryProfileRepository,
        InMemoryTaskSessionRepository,
        InMemoryUserRepository,
        LocalJsonRegistryRepository,
    )

    return {
        "profiles": InMemoryProfileRepository,
        "behaviors": InMemoryBehaviorRepository,
        "memories": InMemoryConversationMemoryRepository,
        "assets": InMemoryAssetRepository,
        "sessions": InMemoryTaskSessionRepository,
        "users": InMemoryUserRepository,
        "registry": lambda: LocalJsonRegistryRepository(str(DATA_DIR / "registry")),
    }


def _memory_gateways(tmp_path: Path) -> dict[str, GatewayFactory]:
    from zhiyin_infrastructure.local.cache import InMemoryCache
    from zhiyin_infrastructure.local.embedding import LocalHashEmbedder
    from zhiyin_infrastructure.local.feature_flag import LocalFeatureFlagStore
    from zhiyin_infrastructure.local.object_store import LocalFileStore
    from zhiyin_infrastructure.local.vector_store import LocalVectorStore

    return {
        "cache": InMemoryCache,
        "vector": LocalVectorStore,
        "embedding": LocalHashEmbedder,
        "feature_flags": lambda: LocalFeatureFlagStore(str(DATA_DIR / "registry")),
        "object_store": lambda: LocalFileStore(str(tmp_path / "objects")),
    }


# backend 名 → 该 backend 全部 Repository 构造器
REPOSITORY_FACTORIES: dict[str, Callable[[], dict[str, RepositoryFactory]]] = {
    "in-memory": _memory_repositories,
}

# backend 名 → 该 backend 全部 Gateway 构造器
GATEWAY_FACTORIES: dict[str, Callable[[Path], dict[str, GatewayFactory]]] = {
    "in-memory": _memory_gateways,
}


@pytest.fixture(params=sorted(REPOSITORY_FACTORIES))
def repositories(request: pytest.FixtureRequest) -> dict[str, RepositoryFactory]:
    """当前 backend 的全部 Repository 构造器。"""
    return REPOSITORY_FACTORIES[request.param]()


@pytest.fixture(params=sorted(GATEWAY_FACTORIES))
def gateways(request: pytest.FixtureRequest, tmp_path: Path) -> dict[str, GatewayFactory]:
    """当前 backend 的全部 Gateway 构造器。"""
    return GATEWAY_FACTORIES[request.param](tmp_path)
