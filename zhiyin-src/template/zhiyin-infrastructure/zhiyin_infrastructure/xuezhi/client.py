"""学职平台公开数据客户端。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import httpx

_BASE_URL = "https://xz.chsi.com.cn"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    )
}


class XueZhiClient:
    """只访问公开页面与公开查询接口，带基础限速与来源标注。

    公开可取：专业列表 / 专业详情、职业检索 / 职业详情、人物案例检索。
    案例详情页需要学信网登录（未登录返回登录页），因此不提供该方法——
    与其给一个取不到数据的接口，不如让调用方明白地只拿公开摘要。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        base_url: str = _BASE_URL,
        timeout_s: float = 30.0,
        request_interval_s: float = 0.25,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._request_interval_s = request_interval_s
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    @property
    def base_url(self) -> str:
        """站点根地址：取数结果要用它拼可回溯的来源链接。"""
        return self._base_url

    async def list_specialities(
        self, *, name: str = "", start: int = 0
    ) -> dict[str, Any]:
        return await self._get_json(
            "/speciality/list.action",
            {
                "start": start,
                "phbType": "1",
                "cc": "",
                "ml": "",
                "xk": "",
                "zymc": name,
            },
            referer="/speciality/index.action",
        )

    async def get_speciality_detail(self, spec_id: str) -> dict[str, Any]:
        text = await self._get_text(
            "/speciality/detail.action",
            {"specId": spec_id},
            referer="/speciality/index.action",
        )
        return _extract_result_json(text)

    async def search_occupations(
        self, *, name: str = "", start: int = 0
    ) -> dict[str, Any]:
        path = "/occupation/searchbyname.action" if name else "/occupation/searchbyhy.action"
        return await self._get_json(
            path,
            {
                "industryId": "",
                "ktId": "",
                "name": name,
                "start": start,
                "curPage": 1,
                "pageCount": 10,
                "totalCount": 0,
            },
            referer="/occupation/index.action",
        )

    async def get_occupation_detail(self, occupation_id: str) -> dict[str, Any]:
        text = await self._get_text(
            "/occupation/occudetail.action",
            {"id": occupation_id},
            referer="/occupation/index.action",
        )
        return _extract_result_json(text)

    async def search_occupation_cases(
        self, *, name: str = "", start: int = 0
    ) -> dict[str, Any]:
        return await self._get_json(
            "/occucase/search.action",
            {"caseName": name, "start": start},
            referer="/occucase/index.action",
        )

    async def _get_json(
        self, path: str, params: dict[str, Any], *, referer: str
    ) -> dict[str, Any]:
        text = await self._get_text(path, params, referer=referer)
        payload = text.strip()
        if not payload:
            return {}
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"学职接口返回非 JSON：{path}") from exc
        return data if isinstance(data, dict) else {}

    async def _get_text(
        self, path: str, params: dict[str, Any], *, referer: str
    ) -> str:
        await self._throttle()
        headers = {**_HEADERS, "Referer": self._base_url + referer}
        async with httpx.AsyncClient(
            timeout=self._timeout_s, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(self._base_url + path, params=params)
            response.raise_for_status()
            return response.text

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            wait = self._request_interval_s - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = asyncio.get_running_loop().time()


def _extract_result_json(text: str) -> dict[str, Any]:
    marker = "resultJson:"
    index = text.find(marker)
    if index < 0:
        return {}
    start = text.find("{", index + len(marker))
    if start < 0:
        return {}
    end = _find_matching_brace(text, start)
    if end < 0:
        return {}
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _find_matching_brace(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def fetched_at() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["XueZhiClient", "fetched_at"]
