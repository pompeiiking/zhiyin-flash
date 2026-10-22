"""诊断报告正文的内容护栏。

报告的 `verdict` 是给用户看的诊断结论，不是生成过程的备注。模型偶尔会把
「本报告说明」「这轮能更新的是依据」「上一版报告……」这类对自己的评论写进
verdict —— 正文看起来像结论，实际上没有回答用户的问题（#41）。

护栏只做一件事：在**写入资产之前**判定 verdict 是否像一个诊断结论。
判定放在 kernel，是因为业务写入与 api 展示读同一份口径：一处拒绝，另一处
只负责兜住历史存量，不能各自维护一份关键词表。
"""

from __future__ import annotations

from typing import Any, Mapping

#: 这些说法属于「对报告/生成过程的评论」，不是对用户的诊断结论。
META_VERDICT_MARKERS: tuple[str, ...] = (
    "报告里",
    "本报告",
    "这轮",
    "本轮",
    "上一版",
    "上一轮",
    "匹配度最高",
    "没看到算法",
    "情报原文",
    "更新的是依据",
    "先补依据",
    "你转来的那句话",
    "不照做",
    "本轮未取回",
)


def report_verdict_issue(verdict: Mapping[str, Any] | Any) -> str:
    """返回 verdict 不能作为诊断结论的原因；没有问题返回空串。"""
    if hasattr(verdict, "model_dump"):
        verdict = verdict.model_dump(mode="json")
    title = str((verdict or {}).get("title") or "").strip()
    summary = str((verdict or {}).get("summary") or "").strip()
    if not title or not summary:
        return "报告结论的标题和说明都不能为空，请重新生成一份有明确诊断结论的报告。"
    prose = f"{title} {summary}"
    marker = next((item for item in META_VERDICT_MARKERS if item in prose), "")
    if marker:
        return (
            f"报告结论混入了对报告/生成过程的评论（「{marker}」），"
            "这不是对用户的诊断结论。请重新生成 verdict，直接回答用户当前最该确认的方向与依据。"
        )
    return ""
