"""从固定评测输出生成不含版本标签的 A/B 评审 Markdown。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REVIEW_CASES = (
    "stage.collect.emotional.1",
    "stage.diagnose.normal.1",
    "stage.decide.conflict.2",
    "stage.act.normal.1",
    "stage.review.emotional.1",
    "task.dim.missing",
    "task.brief.today.missing",
    "task.match.careers.missing",
    "extra.citation.invalid.1",
    "extra.material.injection.1",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--extra", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for path in (args.core, args.extra)
        for line in path.open(encoding="utf-8")
    ]
    by_key = {(row["case"], row["variant"]): row for row in rows if row["repeat"] == 1}
    lines = [
        "# 提示词匿名 A/B 样本与评分表",
        "",
        "以下是合成输入与同条件评测输出。A/B 只表示展示顺序；评分前请勿查看评测原始文件或版本映射。",
        "评审者及评审方式须如实记录；AI 自评不能写成独立真人评审。",
        "请分别给 A、B 的相关性、尊重用户、具体可执行性、表达清楚程度各打 0–2 分，",
        "并标记是否出现无依据的用户事实、外部事实、分数或理论引用；出现任一项即为硬门槛失败。",
        "0=不满足，1=部分满足，2=满足。最后填写偏好 A/B/相同及简短理由。",
        "",
        "| 样本 | A：相关/尊重/可执行/清楚 | B：相关/尊重/可执行/清楚 | A/B 事实问题 | 偏好及理由 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, _ in enumerate(REVIEW_CASES, 1):
        lines.append(f"| {index:02d} |  /  /  /  |  /  /  /  |  /  |  |")
    lines.extend(["", "## 匿名样本", ""])
    for index, case in enumerate(REVIEW_CASES, 1):
        pair = [by_key[(case, variant)] for variant in ("R0", "candidate")]
        if not all(row["valid"] for row in pair):
            raise ValueError(f"样本 {case} 存在无效模型输出，不能进入盲评")
        if hashlib.sha256(case.encode()).digest()[0] % 2:
            pair.reverse()
        lines.extend([f"### {index:02d} · {case}", "", "输入：", "", pair[0]["input"], ""])
        for label, row in zip(("A", "B"), pair, strict=True):
            lines.extend([
                f"**输出 {label}**", "", "```json",
                json.dumps(json.loads(row["output"]), ensure_ascii=False, indent=2),
                "```", "",
            ])
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"blind_review_cases={len(REVIEW_CASES)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
