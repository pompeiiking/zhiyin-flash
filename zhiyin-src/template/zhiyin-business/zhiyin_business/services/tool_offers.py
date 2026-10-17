"""Server-owned conversation proposals for installed, permitted tools."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ToolOffer:
    tool: str
    question: str
    instruction: str
    area: str = ""


_AREAS = {
    "profile": ("个人画像", "画像"), "academic": ("成绩和课表", "成绩和课表"),
    "report": ("诊断报告", "诊断报告"), "plan": ("行动计划", "行动计划"),
    "directions": ("方向方案", "方向方案"), "calendar": ("日历安排", "日历安排"),
    "notes": ("成长记录", "成长记录"), "reviews": ("复盘记录", "复盘记录"),
    "achievements": ("完成记录", "完成记录"),
}

TOOL_OFFERS = {
    f"read_{key}": ToolOffer("workspace.read", f"要查看你已有的{label}，再结合当前问题分析吗？",
        f"请调用业务资料工具读取我的{term}，结合上一轮的问题回答。", key)
    for key, (label, term) in _AREAS.items()
}
TOOL_OFFERS.update({
    "web": ToolOffer("web.search", "要联网核实与这个问题相关的信息和来源吗？", "请针对上一轮问题联网检索，并列出实际来源。"),
    "knowledge": ToolOffer("kb.search", "要查找相关的职业知识和方法依据吗？", "请针对上一轮问题检索知识库，并说明实际查到的依据。"),
    "xuezhi": ToolOffer("xuezhi.search", "要查询学职平台的相关职业资料吗？", "请针对上一轮问题查询学职平台的相关资料，说明实际来源。"),
    "behavior": ToolOffer("behavior.recent", "要结合你最近的行动记录一起看看吗？", "请读取我的近期行动记录，结合上一轮问题分析。"),
    "profile_detail": ToolOffer("profile.read", "要核对画像中已收集的信息和缺口吗？", "请读取我的画像和信息缺口，结合上一轮问题分析。"),
    "plan_detail": ToolOffer("plan.read", "要结合现有计划和进度一起分析吗？", "请读取我的行动计划与进度，结合上一轮问题分析。"),
    "chart_profile": ToolOffer("chart.render", "要用图表查看画像信息的把握程度吗？", "请用图表展示我的画像信息把握程度。"),
    "chart_plan": ToolOffer("chart.render", "要用图表查看各阶段的计划进度吗？", "请用图表展示我的计划进度。"),
    "progress_card": ToolOffer("action_progress.read", "要展示当前行动计划进度卡片吗？", "请调用行动计划进度模块并展示卡片。"),
    "progress_detail": ToolOffer("plan_progress_skill.read", "要查询已保存的计划进度详情吗？", "请调用计划进度查询技能并说明结果。"),
})


def proposal_at_end(text: str) -> str | None:
    found = next((key for key, offer in TOOL_OFFERS.items() if text.rstrip().endswith(offer.question)), None)
    if found:
        return found
    if re.search(r"要把「[^\n]+」标记为完成吗？$", text.rstrip()):
        return "task_done"
    return "task_undo" if re.search(r"要取消「[^\n]+」的完成状态吗？$", text.rstrip()) else None


def task_offer(name: str, *, done: bool = True) -> ToolOffer:
    display = re.sub(r"\s+", " ", name).strip()
    display = display[:44] + ("…" if len(display) > 44 else "")
    if done:
        return ToolOffer("workspace.task.set_done", f"要把「{display}」标记为完成吗？",
                         f"请把{name}标记为完成。")
    return ToolOffer("workspace.task.set_done", f"要取消「{display}」的完成状态吗？",
                     f"请把{name}取消完成。")


def mentioned_tasks(plan, message: str):
    """Resolve only an exact full name or an unambiguous, literal task fragment."""
    tasks = [t for p in (plan.phases if plan else []) for t in p.tasks if t.text]
    exact = [t for t in tasks if t.text in message]
    if exact:
        return exact
    match = re.search(r"(?:已经|刚刚|刚)?(?:做完了?|完成了?|弄好了?|搞定了?|没完成|未完成|没有完成|误标了?|标错了?)[：:，,\s]*(.+)", message)
    if not match:
        return []
    fragment = match.group(1).strip(" \t\r\n。！!，,；;：:")
    if len(fragment) < 6:
        return []
    return [t for t in tasks if fragment in t.text]
