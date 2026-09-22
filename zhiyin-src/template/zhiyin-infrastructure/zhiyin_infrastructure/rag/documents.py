"""知识文档源：把本地知识 JSON 转成可嵌入文档。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_NAMESPACES = ("profession", "occupation", "jd", "theory")


class KnowledgeDocument(BaseModel):
    """待同步知识文档。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    title: str = ""
    namespace: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class JsonKnowledgeDocumentSource:
    """从 `data/knowledge/*.json` 读取知识文档。"""

    def __init__(self, data_dir: str, namespaces: Optional[list[str]] = None) -> None:
        self._data_dir = Path(data_dir)
        self._namespaces = namespaces or list(_DEFAULT_NAMESPACES)

    async def list_documents(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        for namespace in self._namespaces:
            path = self._data_dir / f"{namespace}.json"
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("items", []) if isinstance(raw, dict) else raw
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                doc_id = str(item.get("id") or f"{namespace}-{index}")
                text = _document_text(item)
                if not text:
                    continue
                documents.append(
                    KnowledgeDocument(
                        id=doc_id,
                        text=text,
                        title=str(item.get("title") or item.get("name") or ""),
                        namespace=namespace,
                        metadata={**item, "namespace": namespace},
                    )
                )
        return documents


def _document_text(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("title") or item.get("name") or ""),
        str(item.get("summary") or ""),
        str(item.get("content") or ""),
        " ".join(str(tag) for tag in item.get("tags", []) or []),
    ]
    return " ".join(part for part in parts if part).strip()


__all__ = ["JsonKnowledgeDocumentSource", "KnowledgeDocument"]
