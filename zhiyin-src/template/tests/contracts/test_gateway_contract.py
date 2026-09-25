"""Gateway 语义契约。

覆盖第一期就存在、且第二期一定会被替换的接缝：缓存、向量、嵌入、功能开关、对象存储。
其它 Gateway（事件总线 / 调度 / 通知 / 鉴权 / 安全 / 限流）的行为断言在
`tests/test_infrastructure.py` 与 `tests/test_orchestration.py`。
"""

from __future__ import annotations

import pytest

from zhiyin_data_sdk.gateways.vector import VectorRecord


async def test_cache_contract(gateways) -> None:
    cache = gateways["cache"]()

    assert await cache.get("workspace", "missing") is None, "未命中是 None，不是异常"
    await cache.set("workspace", "u1", "payload")
    assert await cache.get("workspace", "u1") == "payload"

    # 命名空间隔离：同名 key 在不同命名空间互不影响
    assert await cache.get("profile", "u1") is None

    await cache.set("workspace", "u2", "other")
    assert await cache.delete_many("workspace", ["u1", "u2", "u3"]) == 2

    await cache.set("workspace", "u1", "again")
    await cache.clear_namespace("workspace")
    assert await cache.get("workspace", "u1") is None

    # ttl_s=0 表示不过期
    await cache.set("profile", "u1", "forever", ttl_s=0)
    assert await cache.get("profile", "u1") == "forever"


async def test_vector_contract(gateways) -> None:
    store = gateways["vector"]()
    model = "test-model"

    await store.upsert(
        "occupation",
        [
            VectorRecord(id="a", vector=[1.0, 0.0], text="甲", source_id="doc-a"),
            VectorRecord(id="b", vector=[0.0, 1.0], text="乙", source_id="doc-b"),
        ],
        model=model,
    )

    hits = await store.search("occupation", [1.0, 0.0], model=model, top_k=2)
    assert [hit.id for hit in hits] == ["a", "b"], "必须按相似度降序"
    assert hits[0].source_id == "doc-a", "命中必须能回到来源文档"

    # 命名空间隔离
    assert await store.search("profession", [1.0, 0.0], model=model) == []

    # 模型版本路由：换了嵌入模型后，旧向量不参与比较（而不是给一个错的相似度）
    assert await store.search("occupation", [1.0, 0.0], model="another-model") == []

    # 按 metadata 过滤
    await store.upsert(
        "occupation",
        [VectorRecord(id="c", vector=[1.0, 0.0], metadata={"city": "上海"})],
        model=model,
    )
    filtered = await store.search(
        "occupation", [1.0, 0.0], model=model, filters={"city": "上海"}
    )
    assert [hit.id for hit in filtered] == ["c"]

    # 同 id 覆盖（可重复执行的同步任务）
    await store.upsert(
        "occupation", [VectorRecord(id="a", vector=[0.0, 1.0])], model=model
    )
    assert (await store.search("occupation", [0.0, 1.0], model=model, top_k=1))[0].id in {
        "a",
        "b",
    }

    assert await store.delete("occupation", ["a", "不存在"]) == 1
    await store.clear_namespace("occupation")
    assert await store.search("occupation", [1.0, 0.0], model=model) == []


async def test_embedding_contract(gateways) -> None:
    embedder = gateways["embedding"]()

    assert isinstance(embedder.model_id, str) and embedder.model_id

    vectors = await embedder.embed(["甲", "乙", "甲"])
    assert len(vectors) == 3, "返回顺序与条数必须与入参一一对应"
    assert vectors[0] == vectors[2], "同样输入必须得到同样向量（否则索引会漂移）"
    assert len(vectors[0]) == len(vectors[1]), "维度必须一致"
    assert any(value != 0 for value in vectors[0]), "不得返回零向量（无法算余弦）"


async def test_feature_flag_contract(gateways) -> None:
    """功能开关：未知开关必须默认关闭，且返回的是快照。"""
    flags = gateways["feature_flags"]()

    all_flags = await flags.all()
    assert all_flags, "种子数据里必须有开关"
    assert await flags.is_enabled("report_full_text") is True
    assert await flags.is_enabled("export") is False

    # 配置漏了不能反而把功能打开（这是"默认通过层"最容易犯的错）
    assert await flags.is_enabled("not_configured") is False
    assert await flags.is_enabled("not_configured", default=True) is True

    # 快照语义：调用方改返回值不得影响实现内部缓存
    all_flags["report_full_text"] = False
    assert await flags.is_enabled("report_full_text") is True


async def test_object_store_contract(gateways) -> None:
    store = gateways["object_store"]()
    key = store.build_key("u1", "report", 1, ".pdf")

    assert await store.stat(key) is None
    await store.put(key, b"hello", content_type="application/pdf")
    assert await store.get(key) == b"hello"
    stat = await store.stat(key)
    assert stat is not None and stat.size == 5

    await store.delete(key)
    assert await store.stat(key) is None

    with pytest.raises(ValueError):
        await store.put("../escape.txt", b"x")


async def test_object_store_write_failure_is_not_reported_as_success(tmp_path) -> None:
    from zhiyin_infrastructure.local.object_store import LocalFileStore

    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory", encoding="utf-8")
    store = LocalFileStore(str(occupied))
    with pytest.raises(OSError):
        await store.put("u1/report/v1.pdf", b"content")
