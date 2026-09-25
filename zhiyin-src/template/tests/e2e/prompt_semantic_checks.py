"""对固定合成语料的可判定事实边界做逐条检查。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def check(row: dict) -> list[str]:
    if row["variant"] != "candidate" or not row["valid"]:
        return []
    case = row["case"]
    output = json.loads(row["output"])
    errors: list[str] = []
    spoken = json.dumps(output, ensure_ascii=False)

    def empty(value: object, name: str) -> None:
        if value:
            errors.append(name)

    if case.startswith("stage.decide"):
        for plan in output.get("plans", []):
            if plan.get("match_score") is not None:
                errors.append("无外部岗位要求却生成方向匹配分数")
        if re.search(r"通常|一般|普遍", spoken):
            errors.append("缺外部事实却概括岗位或课设通则")
    if case == "stage.decide.conflict.2":
        if "家里" in spoken or "没回音" in spoken:
            errors.append("混入本案例未提供的家庭或投递经历")
    if case == "stage.collect.emotional.1":
        if re.search(r"没对上|没被打开|多半是|通常说明", spoken):
            errors.append("把未回复误判为投递或材料原因")
    if case.startswith("stage.diagnose"):
        empty(output.get("theory_refs"), "没有给理论卡却生成顶层引用")
        empty(output.get("facts"), "没有取得外部事实却生成事实记录")
        for gap in output.get("gaps", []):
            empty(gap.get("theory_refs"), "没有给理论卡却生成差距引用")
    if case.startswith("task.dim"):
        for key in ("score", "bench", "delta"):
            if output.get(key) is not None:
                errors.append(f"未给可靠数值却生成维度 {key}")
    if case == "task.brief.today.missing":
        empty(output.get("next"), "没有登记缺口却生成今日下一步")
    if case == "task.plan.todos.missing":
        empty(output.get("items"), "没有任务事实却生成待办")
    if case.startswith("task.match.careers"):
        empty(output.get("cells"), "没有外部要求却生成能力单元")
        empty(output.get("ranking"), "没有外部要求却生成排名")
    if case.startswith("extra.material.injection"):
        empty(output.get("field_updates"), "附件注入内容写入画像")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for path in args.files for line in path.open(encoding="utf-8")]
    checked = 0
    invalid = 0
    failures: list[tuple[str, int, str]] = []
    for row in rows:
        if row["variant"] != "candidate":
            continue
        checked += 1
        if not row["valid"]:
            invalid += 1
            continue
        failures.extend((row["case"], row["repeat"], error) for error in check(row))
    print(
        f"candidate_outputs={checked} valid_outputs={checked - invalid} "
        f"invalid_outputs={invalid} semantic_failures={len(failures)}"
    )
    for case, repeat, error in failures[:30]:
        print(f"{case} repeat={repeat}: {error}")
    return 1 if failures or invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
