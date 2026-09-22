"""通用网络搜索（可配置的搜索服务）。

为什么它必须"配了才装"
----------------------
通用搜索要一个外部搜索服务的密钥。**没有密钥就没有通道** ——
这时候把它装成一个"能返回结果"的网关，只能靠编，而那正是这个项目
最不能有的东西。所以口径是：

  · 配了 `ZHIYIN_SEARCH_API_KEY` → 装配它，`web.search` 工具对主理可用；
  · 没配 → 这个能力位就不装，模型看到的工具清单里没有它，
    界面上也不会出现"正在联网搜索"这种没有发生的事。

协议：Brave Search Web API（`X-Subscription-Token` + `q`）。
换服务商只需改 `ZHIYIN_SEARCH_ENDPOINT` 与下面这一个解析函数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass(frozen=True)
class WebHit:
    """一条搜索结果。"""

    title: str
    url: str
    snippet: str = ""


class BraveWebSearch:
    """Brave Search 适配器。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.search.brave.com/res/v1/web/search",
        timeout_s: float = 12.0,
        count: int = 5,
    ) -> None:
        if not api_key:
            raise ValueError("通用搜索需要 ZHIYIN_SEARCH_API_KEY")
        self._api_key = api_key
        self._endpoint = endpoint
        self._timeout = timeout_s
        self._count = count

    async def search(self, query: str, *, count: Optional[int] = None) -> list[WebHit]:
        """搜一次。失败时**抛**，由调用方决定怎么对用户说 —— 不返回空表假装没结果。"""
        params = {"q": query, "count": count or self._count}
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.get(self._endpoint, params=params, headers=headers)
            res.raise_for_status()
            payload = res.json()
        return _hits_of(payload)


def _hits_of(payload: dict) -> list[WebHit]:
    """Brave 的响应 → 我们要的三元组（只留能用得上的字段）。"""
    rows = ((payload or {}).get("web") or {}).get("results") or []
    hits: list[WebHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        if not url:
            continue
        hits.append(
            WebHit(
                title=str(row.get("title") or "")[:120],
                url=url,
                snippet=str(row.get("description") or "")[:400],
            )
        )
    return hits


__all__ = ["BraveWebSearch", "WebHit"]
