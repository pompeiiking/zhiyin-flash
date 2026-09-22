"""学职平台数据源 Gateway 实现。"""

from __future__ import annotations

from typing import Any

from zhiyin_data_sdk.gateways.datasource import (
    DataSourceGateway,
    DataSourceRecord,
    DataSourceRequest,
    DataSourceResult,
)
from zhiyin_infrastructure.xuezhi.client import XueZhiClient, fetched_at
from zhiyin_infrastructure.xuezhi.parsing import (
    case_text,
    matched_occupations,
    occupation_text,
    speciality_text,
)

_SOURCE = "xuezhi"
# 画像字段优先级：专业决定"读哪个专业"，目标岗位决定"看哪些职业与案例"。
_MAJOR_KEYS = ("major", "speciality", "target_major", "field_of_study")
_JOB_KEYS = ("target_job", "target_direction", "career_interest", "interest", "industry")


class XueZhiDataSourceGateway(DataSourceGateway):
    """按画像上下文检索学职平台公开数据。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        client: XueZhiClient,
        *,
        max_specialities: int = 3,
        max_occupations: int = 3,
        max_cases: int = 2,
    ) -> None:
        self._client = client
        self._max_specialities = max_specialities
        self._max_occupations = max_occupations
        self._max_cases = max_cases

    async def fetch(self, request: DataSourceRequest) -> DataSourceResult:
        if request.source != _SOURCE:
            return DataSourceResult(
                source=request.source,
                degraded=True,
                errors=[f"未知数据源：{request.source}"],
            )
        records: list[DataSourceRecord] = []
        errors: list[str] = []
        try:
            await self._collect(request, records)
        except Exception as exc:
            # 已经取到的证据照常返回：半份真实数据比整份空缺更有用，
            # 但必须让调用方看见"这次不完整"。
            errors.append(str(exc))
        return DataSourceResult(
            source=request.source,
            records=records[: request.limit],
            degraded=bool(errors),
            errors=errors,
        )

    async def _collect(
        self, request: DataSourceRequest, records: list[DataSourceRecord]
    ) -> None:
        values = _context_values(request.context)
        major_terms = _terms(values, _MAJOR_KEYS)
        job_terms = _terms(values, _JOB_KEYS)
        if not major_terms and not job_terms and request.query.strip():
            # 画像为空（新用户）时才退回原始提问，避免拿整句话当检索词。
            major_terms = [request.query.strip()]
            job_terms = [request.query.strip()]

        # 平台自带的"专业 → 对口职业"映射：比拿专业名去模糊搜职业准得多。
        linked_occupations = await self._collect_specialities(major_terms, records)
        await self._collect_occupations(job_terms, linked_occupations, records)
        await self._collect_cases(job_terms or major_terms, records)

    async def _collect_specialities(
        self, terms: list[str], records: list[DataSourceRecord]
    ) -> list[tuple[str, str]]:
        """按专业名取专业详情，并顺带拿到平台标注的对口职业。"""
        for term in terms[:2]:
            page = await self._client.list_specialities(name=term)
            items = _items(page)[: self._max_specialities]
            if not items:
                continue
            linked: list[tuple[str, str]] = []
            for item in items:
                spec_id = str(item.get("specId") or "")
                if not spec_id:
                    continue
                name = str(item.get("zymc") or "")
                detail = await self._client.get_speciality_detail(spec_id)
                records.append(
                    DataSourceRecord(
                        id=spec_id,
                        kind="speciality",
                        title=name or str(detail.get("zymc") or ""),
                        text=speciality_text(detail, fallback_name=name),
                        source_url=(
                            f"{self._client.base_url}/speciality/detail.action"
                            f"?specId={spec_id}"
                        ),
                        fetched_at=fetched_at(),
                        metadata={
                            "level": item.get("cc"),
                            "category": item.get("mlmc"),
                            "discipline": item.get("xk"),
                            "code": item.get("zydm"),
                        },
                    )
                )
                for linked_name, linked_id in matched_occupations(detail):
                    if (linked_name, linked_id) not in linked:
                        linked.append((linked_name, linked_id))
            return linked
        return []

    async def _collect_occupations(
        self,
        terms: list[str],
        linked: list[tuple[str, str]],
        records: list[DataSourceRecord],
    ) -> None:
        """优先用专业对口职业；专业链条为空时才用职业名模糊检索兜底。"""
        candidates = linked or [("", term) for term in terms]
        seen = {record.id for record in records}
        added = 0
        for name, occupation_id in candidates:
            if added >= self._max_occupations:
                break
            if not occupation_id:
                page = await self._client.search_occupations(name=name or "")
                found = _items(page)[: self._max_occupations]
                if not found:
                    continue
                for item in found:
                    item_id = str(item.get("zhiyId") or "")
                    if not item_id or item_id in seen:
                        continue
                    detail = await self._client.get_occupation_detail(item_id)
                    seen.add(item_id)
                    records.append(
                        _occupation_record(
                            item_id,
                            str(item.get("title") or ""),
                            detail,
                            base_url=self._client.base_url,
                            industry=str(item.get("industrymc") or ""),
                        )
                    )
                    added += 1
                    if added >= self._max_occupations:
                        break
                continue
            if occupation_id in seen:
                continue
            detail = await self._client.get_occupation_detail(occupation_id)
            seen.add(occupation_id)
            records.append(
                _occupation_record(
                    occupation_id,
                    name,
                    detail,
                    base_url=self._client.base_url,
                    industry=str(detail.get("industryName") or ""),
                    matched_from="speciality",
                )
            )
            added += 1
            if added >= self._max_occupations:
                break

    async def _collect_cases(
        self, terms: list[str], records: list[DataSourceRecord]
    ) -> None:
        """用目标岗位/专业名找公开人物案例；案例详情要登录，因此只取公开摘要。"""
        seen = {record.id for record in records}
        for term in terms[:2]:
            page = await self._client.search_occupation_cases(name=term)
            items = _items(page)[: self._max_cases]
            if not items:
                continue
            for item in items:
                case_id = str(item.get("caseId") or item.get("id") or "")
                if not case_id or case_id in seen:
                    continue
                seen.add(case_id)
                records.append(
                    DataSourceRecord(
                        id=case_id,
                        kind="career_case",
                        title=str(item.get("caseDesc") or item.get("caseName") or ""),
                        text=case_text(item),
                        source_url=(
                            f"{self._client.base_url}/occucase/casedetail.action"
                            f"?id={case_id}"
                        ),
                        fetched_at=fetched_at(),
                        metadata={"industry": item.get("industryName")},
                    )
                )
            return


def _occupation_record(
    occupation_id: str,
    name: str,
    detail: dict[str, Any],
    *,
    base_url: str,
    industry: str = "",
    matched_from: str = "search",
) -> DataSourceRecord:
    return DataSourceRecord(
        id=occupation_id,
        kind="occupation",
        title=str(detail.get("zhiyname") or name),
        text=occupation_text(detail, fallback_name=name),
        source_url=(
            f"{base_url}/occupation/occudetail.action"
            f"?id={occupation_id}"
        ),
        fetched_at=fetched_at(),
        metadata={
            "industry": industry or detail.get("industryName") or "",
            "matched_from": matched_from,
        },
    )


def _context_values(context: dict[str, Any]) -> dict[str, list[str]]:
    """把上下文（画像字段快照 / 扁平键值）整理成 键 → 检索词列表。"""
    values: dict[str, Any] = {}
    fields = context.get("fields")
    if isinstance(fields, list):
        for field in fields:
            if isinstance(field, dict) and field.get("key"):
                values[str(field["key"])] = field.get("value")
    for key, value in context.items():
        if key != "fields":
            values.setdefault(str(key), value)

    collected: dict[str, list[str]] = {}
    for key in values:
        value = values[key]
        terms: list[str] = []
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
        elif isinstance(value, (list, tuple)):
            terms.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, dict):
            terms.extend(
                str(item).strip() for item in value.values() if str(item).strip()
            )
        if terms:
            collected[key] = terms
    return collected


def _terms(values: dict[str, list[str]], keys: tuple[str, ...]) -> list[str]:
    """按字段优先级取出检索词，去重保序。"""
    terms: list[str] = []
    for key in keys:
        for term in values.get(key, []):
            if term not in terms:
                terms.append(term)
    return terms


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("pageArray", "zhiyArray", "list", "dataList"):
            items = data.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


__all__ = ["XueZhiDataSourceGateway"]
