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

from zhiyin_kernel import profile_taxonomy

_SOURCE = "xuezhi"
# 画像字段优先级见《个人画像设计-2026-10-20》第 8 节：
#   · 专业检索只认明确的学习背景专业字段（普通兴趣/价值偏好/补充描述不能替代）；
#   · 职业检索只认明确的职业关注字段（兴趣、行业等不能拼成职业名称）。
_MAJOR_KEYS = profile_taxonomy.MAJOR_KEYS
_CAREER_KEYS = profile_taxonomy.CAREER_FOCUS_KEYS


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
            details = await self._collect(request, records, errors)
        except Exception as exc:
            # 已经取到的证据照常返回：半份真实数据比整份空缺更有用，
            # 但必须让调用方看见"这次不完整"。
            errors.append(str(exc))
            details = {}
        return DataSourceResult(
            source=request.source,
            records=records[: request.limit],
            degraded=bool(errors),
            errors=errors,
            details=details,
        )

    async def _collect(
        self, request: DataSourceRequest, records: list[DataSourceRecord], errors: list[str]
    ) -> dict[str, Any]:
        fields = _context_fields(request.context)
        major_terms = profile_taxonomy.major_terms(fields)
        career_terms = profile_taxonomy.career_focus_terms(fields)
        if not major_terms and not career_terms and request.query.strip():
            # 画像为空（新用户）时才退回原始提问，避免拿整句话当检索词。
            major_terms = [request.query.strip()]

        # 平台自带的"专业 → 对口职业"映射：比拿专业名去模糊搜职业准得多。
        async def attempt(operation):
            try:
                return await operation
            except Exception as exc:
                errors.append(str(exc))
                return None

        # 专业检索独立：即使同时有明确的职业关注，也照常按专业取专业详情与
        # 官方对口职业，不用职业关注去替换或覆盖专业查询。
        linked_occupations = await attempt(self._collect_specialities(major_terms, records)) or []
        # 明确的职业关注（已选/考虑中的方向）优先：先把关注对象对应的职业取回来，
        # 再用专业链条补足；否则方向页写着"后端开发"，探索页永远是专业对口职业。
        direction_terms = [term for term in career_terms if term not in major_terms]
        if direction_terms:
            await attempt(self._collect_occupations(direction_terms, [], records, relation="direction"))
            await attempt(self._collect_occupations(major_terms, linked_occupations, records, relation="major"))
            await attempt(self._collect_cases(direction_terms, records, relation="direction"))
        else:
            await attempt(self._collect_occupations(
                major_terms, linked_occupations, records, relation="major"
            ))
            await attempt(self._collect_cases(major_terms, records, relation="major"))
        return _retrieval_details(
            major_terms=major_terms,
            career_terms=career_terms,
            records=records,
        )

    async def _collect_specialities(
        self, terms: list[str], records: list[DataSourceRecord]
    ) -> list[tuple[str, str]]:
        """按专业名取专业详情，并顺带拿到平台标注的对口职业。"""
        for term in terms[:2]:
            page = await self._client.list_specialities(name=term)
            items = _items(page)
            exact = [item for item in items if str(item.get("zymc") or "").strip() == term.strip()]
            items = (exact or items)[: self._max_specialities]
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
                            "relation": "major",
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
        *,
        relation: str = "major",
    ) -> None:
        """优先用专业对口职业；专业链条为空时才用职业名模糊检索兜底。"""
        candidates = linked or [(term, "") for term in terms]
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
                            relation=relation,
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
                    relation=relation,
                )
            )
            added += 1
            if added >= self._max_occupations:
                break

    async def _collect_cases(
        self, terms: list[str], records: list[DataSourceRecord], *, relation: str = "major"
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
                        metadata={
                            "industry": item.get("industryName"),
                            "relation": relation,
                        },
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
    relation: str = "major",
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
            "relation": relation,
        },
    )


def _context_fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    """把上下文（画像字段快照 / 扁平键值）整理成可交给用途视图的字段行。

    `fields` 里的每条字段可以带 `entry_type`；没带就由词表按键推导 ——
    与写侧共用同一份受控词表，不在取数处另判一套类别。
    """
    rows: list[dict[str, Any]] = []
    fields = context.get("fields")
    if isinstance(fields, list):
        for field in fields:
            if isinstance(field, dict) and field.get("key"):
                rows.append(dict(field))
    for key, value in context.items():
        if key in {"fields", "background_fields", "topic"}:
            continue
        rows.append({"key": str(key), "value": value})
    return rows


def _retrieval_details(
    *,
    major_terms: list[str],
    career_terms: list[str],
    records: list[DataSourceRecord],
) -> dict[str, Any]:
    """取数依据与结果状态：专业/职业/案例分别报数，不把“专业取到了”当成整次成功。

    第 8 节要求区分官方专业映射、名称检索和一般案例；这条明细就是那句话的依据。
    """
    counts = {"speciality": 0, "occupation": 0, "career_case": 0}
    official = 0
    name_search = 0
    for record in records:
        kind = str(record.kind or "")
        if kind in counts:
            counts[kind] += 1
        if kind == "occupation":
            matched_from = str(record.metadata.get("matched_from") or "")
            if matched_from == "speciality":
                official += 1
            elif matched_from == "search":
                name_search += 1
    return {
        "query": {"major": list(major_terms), "career": list(career_terms)},
        "counts": counts,
        "occupation_sources": {"official_mapping": official, "name_search": name_search},
    }


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("pageArray", "zhiyArray", "list", "dataList"):
            items = data.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


__all__ = ["XueZhiDataSourceGateway"]
