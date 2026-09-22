"""本地知识与检索（LocalKnowledgeRepo / LocalKeywordSearch）。

第一期：知识卡与理论卡从本地 JSON 读取；检索退化为关键词匹配。
TODO：按自有基础设施演进。

对应关系：
- `data/knowledge/{namespace}.json` 是**公共知识库**（专业 / 职业 / 岗位 / 政策），
  只作报告与方案里的 evidence / sources 引用，**不写入 profile_field**；
- 命中结果必须带 `source_url` 与 `fetched_at`（该文档 R-CRAWL-006），
  因此 metadata 透传原始条目字段，不做裁剪。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from zhiyin_data_sdk.gateways.ai import (
    KnowledgeGateway,
    KnowledgeHit,
    SearchGateway,
    SearchHit,
)

_DEFAULT_NAMESPACES = ("profession", "occupation", "jd", "theory")

logger = logging.getLogger(__name__)


class LocalKnowledgeRepo(KnowledgeGateway):
    """本地知识库：按 namespace 读 JSON，做分词包含匹配。"""

    def __init__(self, data_dir: str = "data/knowledge") -> None:
        self._data_dir = Path(data_dir)
        self._cache: dict[str, list[dict[str, Any]]] = {}

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        namespace: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[KnowledgeHit]:
        namespaces = [namespace] if namespace else list(_DEFAULT_NAMESPACES)
        terms = _terms(query)
        scored: list[tuple[float, KnowledgeHit]] = []

        for space in namespaces:
            for index, raw in enumerate(self._load(space)):
                if filters and not _match_filters(raw, filters):
                    continue
                score = _score(raw, terms)
                if score <= 0:
                    continue
                # 条目自述的 namespace 优先：文件只是存放位置，条目自己说清了归属
                # （`occupation.json` 里曾混进一条自称 profession 的专业条目，
                # 被这里统一改写成 occupation —— 自述与实际取值不一致，
                # 按 namespace 过滤的调用方会得到互相矛盾的答案）。
                metadata = {**raw, "namespace": str(raw.get("namespace") or space)}
                scored.append(
                    (
                        score,
                        KnowledgeHit(
                            doc_id=str(raw.get("id") or f"{space}-{index}"),
                            title=str(raw.get("title") or raw.get("name") or ""),
                            snippet=str(raw.get("summary") or raw.get("content") or ""),
                            score=score,
                            metadata=metadata,
                        ),
                    )
                )

        scored.sort(key=lambda item: (-item[0], item[1].doc_id))
        return [hit for _, hit in scored[: max(top_k, 0)]]

    def _load(self, namespace: str) -> list[dict[str, Any]]:
        if namespace in self._cache:
            return self._cache[namespace]
        path = self._data_dir / f"{namespace}.json"
        items: list[dict[str, Any]] = []
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                payload = raw.get("items", []) if isinstance(raw, dict) else raw
                items = [item for item in payload if isinstance(item, dict)]
            except (OSError, json.JSONDecodeError):
                # 读坏一个文件不该让**整类检索**失败。缓存空结果而不是不缓存：
                # 不缓存的话，坏文件会让每一次检索都重新读、重新抛。
                logger.exception("知识库文件读不出来，本次按空处理：%s", path)
                items = []
        self._cache[namespace] = items
        return items

    def reload(self) -> None:
        """清缓存，用于演示"改知识库不重启"。"""
        self._cache.clear()


class LocalKeywordSearch(SearchGateway):
    """本地关键词检索。第一期为包含匹配 + 打分排序。"""

    IMPLEMENTATION_STATUS = "skeleton"

    def __init__(self, data_dir: str = "data/knowledge") -> None:
        self._repo = LocalKnowledgeRepo(data_dir)

    async def keyword(self, query: str, *, top_k: int = 10) -> list[SearchHit]:
        hits = await self._repo.search(query, top_k=top_k)
        return [
            SearchHit(id=hit.doc_id, content=hit.snippet or hit.title, score=hit.score, metadata=hit.metadata)
            for hit in hits
        ]

    async def vector(self, embedding: list[float], *, top_k: int = 10) -> list[SearchHit]:
        """当前固定返回空列表，待自有检索实现补齐。"""
        return []

    async def hybrid(self, query: str, *, top_k: int = 10) -> list[SearchHit]:
        """第一期退化为关键词检索。"""
        return await self.keyword(query, top_k=top_k)


def _terms(query: str) -> list[str]:
    """极简切分：按空白与常见标点断开，保留长度 >= 2 的片段。"""
    normalized = query or ""
    for token in "，。！？、；：（）【】《》,.!?;:()[]\"'\n\t":
        normalized = normalized.replace(token, " ")
    return [part for part in normalized.split(" ") if len(part) >= 2]


def _score(raw: dict[str, Any], terms: list[str]) -> float:
    if not terms:
        return 0.0
    haystack = " ".join(
        str(raw.get(field, "")) for field in ("title", "name", "summary", "content", "tags")
    )
    score = 0.0
    for term in terms:
        if term in haystack:
            score += 1.0
    if score > 0 and str(raw.get("title") or raw.get("name") or "") and any(
        term in str(raw.get("title") or raw.get("name") or "") for term in terms
    ):
        # 标题命中加权，避免正文偶然包含就把结果排到前面。
        score += 0.5
    return score


def _match_filters(raw: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        actual = raw.get(key)
        if isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


__all__ = ["LocalKeywordSearch", "LocalKnowledgeRepo"]
