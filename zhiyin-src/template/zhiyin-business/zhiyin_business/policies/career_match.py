"""用原文核验模型选出的对应关系，不把课程成绩当作职业能力分数。"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict

from zhiyin_business.contracts.ai_tasks import (
    MatchCell, MatchDraft, MatchRanking, MatchRecommend, MatchResult,
)

METHOD = "逐项核对职业要求原文与学生材料；自述和经历是待核验依据，课程只是学习线索。资料缺失不代表没有能力，不计算胜任度或就业概率。"


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def ground_match(draft: MatchDraft, sources: list[dict], evidence: dict[str, dict]) -> MatchResult:
    """每个要求须为来源原文，每个学生依据须来自本次输入并出现该能力词。"""
    source_map = {source["id"]: source for source in sources}
    cells = []
    seen = set()
    for cell in draft.cells:
        source = source_map.get(cell.source_id)
        if not source or not source.get("source_url") or not source.get("fetched_at"):
            continue
        skill = _norm(cell.skill)
        requirement = _norm(cell.requirement)
        key = (cell.source_id, skill)
        if key in seen or skill not in requirement or requirement not in _norm(source["text"]):
            continue
        seen.add(key)
        refs = [evidence[ref] for ref in dict.fromkeys(cell.student_evidence)
                if ref in evidence and skill in _norm(evidence[ref]["text"])]
        status = "reported" if any(ref["kind"] == "reported" for ref in refs) else "studied" if refs else "unknown"
        cells.append(MatchCell(
            track=source["title"], skill=cell.skill.strip(), requirement=cell.requirement,
            source_url=source["source_url"], fetched_at=source["fetched_at"],
            student_evidence=[ref["text"] for ref in refs], status=status,
        ))
    grouped = defaultdict(list)
    for cell in cells:
        grouped[cell.track].append(cell)
    # 顺序只反映本次取得的相关证据条数，不冒充适配度排名。
    ordered = sorted(grouped, key=lambda track: -sum(c.status == "reported" for c in grouped[track]))
    ranking = []
    for track in ordered:
        rows = grouped[track]
        reported = sum(c.status == "reported" for c in rows)
        studied = sum(c.status == "studied" for c in rows)
        missing = [c.skill for c in rows if c.status == "unknown"]
        ranking.append(MatchRanking(
            track=track, gap="待补材料：" + "、".join(missing) if missing else "已有线索仍需用实践结果核验",
            why=f"已核对 {len(rows)} 项要求：{reported} 项有自述或经历，{studied} 项只有课程线索。",
        ))
    if ordered:
        first = ordered[0]
        actions = [
            f"核验「{first}」的「{cell.skill}」要求，整理一份相关项目、经历或实践结果作为证据。"
            for cell in grouped[first][:3]
        ]
        recommend = MatchRecommend(
            title=f"可以先核验「{first}」这个方向",
            body="顺序依据本次已取得的相关材料条数。请结合下面的职业原文和个人材料判断；已有线索仍需核验，不能据此认定胜任。",
            because=[f"{cell.track} · {cell.skill}：{cell.requirement}" for cell in grouped[first][:3]],
        )
    else:
        actions = ["补充目标职业及相关项目或经历，核对职业要求后再比较方向。"]
        recommend = MatchRecommend(
            title="先补齐可核验的职业要求与个人材料",
            body="本次还没有形成可核验的能力对照，暂不排序或评分。请补充目标职业及相关经历；职业原文取得后再核对。",
        )
    result = MatchResult(cells=cells, ranking=ranking, recommend=recommend, method=METHOD, actions=actions)
    fingerprint = result.model_dump(exclude={"recommendation_id"})
    for cell in fingerprint["cells"]:
        cell.pop("fetched_at")
    result.recommendation_id = hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
    return result
