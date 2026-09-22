"""外部情报的**显示名**：类别与来源都说中文。

为什么单独一个映射表
--------------------
取回来的东西带的是机器读的取值（`career_case` / `speciality` / `occupation`），
来源是站点域名。这两样直接摆到界面上，用户看到的是"speciality"和一行网址 ——
那不是给人看的字。

所以：**机器取值留在数据里，中文名只在这一处映射**。新增一种类别只改这里；
映射不到时**回落到"公开信息"**而不是把英文丢出去 —— 内部字段外显是这个产品
最不该有的样子（用户已经提过两次）。
"""

from __future__ import annotations

import re

#: 情报类别 → 中文名。左边是数据访问层定的机器取值，右边是给人看的。
KIND_LABELS: dict[str, str] = {
    "occupation": "职业",
    "speciality": "专业",
    "career_case": "校友案例",
    "web": "网络公开信息",
    "job_requirement": "岗位要求",
    "industry": "行业情况",
    "window": "时间窗口",
}

#: 来源标识 → 中文名。界面上写"学职平台"，链接另存在 source_url 里。
SOURCE_LABELS: dict[str, str] = {
    "xuezhi": "学职平台 · 学信网",
    "chsi": "学信网",
    "academic": "学校教务系统",
}

#: 认不出来时的兜底：宁可说"公开信息"，也不要露出一串英文取值。
FALLBACK_KIND = "公开信息"
FALLBACK_SOURCE = "公开渠道"

_KNOWN_DOMAIN_LABELS: tuple[tuple[str, str], ...] = (
    ("chsi.com.cn", "学职平台 · 学信网"),
    ("chsi.cn", "学信网"),
)


def kind_label(kind: str) -> str:
    """类别 → 中文名。认不出来时返回兜底，不返回原值。"""
    key = (kind or "").strip()
    return KIND_LABELS.get(key, FALLBACK_KIND if key else "")


def source_label(source: str) -> str:
    """来源标识 → 中文名。"""
    key = (source or "").strip().lower()
    return SOURCE_LABELS.get(key, FALLBACK_SOURCE if key else "")


def source_name_of(url: str, *, source: str = "") -> str:
    """按 URL 的域名认来源的中文名；认不出就退回按来源标识认。"""
    host = ""
    hit = re.match(r"https?://([^/]+)", url or "")
    if hit:
        host = hit.group(1).lower()
    for domain, label in _KNOWN_DOMAIN_LABELS:
        if host.endswith(domain):
            return label
    return source_label(source)


__all__ = [
    "FALLBACK_KIND",
    "FALLBACK_SOURCE",
    "KIND_LABELS",
    "SOURCE_LABELS",
    "kind_label",
    "source_label",
    "source_name_of",
]
