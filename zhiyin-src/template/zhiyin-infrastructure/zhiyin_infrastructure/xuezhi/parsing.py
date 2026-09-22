"""学职平台原始返回 → 可读事实文本。

平台的返回有两层噪声：正文包在 HTML 片段里，详情又按 `Vo` 嵌套。
本模块只做一件事：把一次取数真正需要的字段整理成短文本，
让它既能进提示词，也能进向量库。

不在这里做检索、不做缓存、不判断画像语义——那些属于 Gateway 与业务规则。
"""

from __future__ import annotations

import re
from typing import Any

_TAG = re.compile(r"<[^>]+>")
_ENTITIES = (
    ("&nbsp;", " "),
    ("&ensp;", " "),
    ("&amp;", "&"),
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&quot;", '"'),
)
# 平台的"对口去向"里混着升学项，不是职业，做职业检索时要滤掉。
_NON_JOB_NAMES = frozenset({"考研", "考公", "出国", "其他"})
_TEXT_LIMIT = 1800


def strip_html(value: Any) -> str:
    """去掉 HTML 标签与常见实体，压平空白。"""
    if not isinstance(value, str):
        return ""
    text = _TAG.sub(" ", value)
    for entity, replacement in _ENTITIES:
        text = text.replace(entity, replacement)
    return " ".join(text.split())


def _joined(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, (int, float)):
        return str(value)
    return strip_html(value)


def _line(label: str, value: Any) -> str:
    text = _joined(value)
    return f"{label}：{text}" if text else ""


def _clip(text: str, *, limit: int = _TEXT_LIMIT) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _section_text(section: dict[str, Any]) -> str:
    """把一层详情（label / sublabels）压成"标签：内容"清单。"""
    parts: list[str] = []
    for label in (section.get("laybels") or []) + (section.get("sublabels") or []):
        if not isinstance(label, dict):
            continue
        content = strip_html(label.get("content"))
        if content:
            parts.append(f"{label.get('labelName') or ''}：{content}".strip("："))
    return " ".join(parts)


def matched_occupations(
    speciality_detail: dict[str, Any], *, limit: int = 3
) -> list[tuple[str, str]]:
    """专业详情里的对口职业（平台自带的 专业→职业 映射），按占比降序。

    返回 [(职业名, zhiyId)]。用平台自己的映射比拿专业名去模糊搜职业准得多：
    后者会把"结构工程师"搜成"游戏开发工程师"。
    """
    entries = (speciality_detail.get("byfzVo") or {}).get("expOccList") or {}
    if not isinstance(entries, dict):
        return []
    scored: list[tuple[float, str, str]] = []
    for name, info in entries.items():
        if not isinstance(info, dict) or str(name) in _NON_JOB_NAMES:
            continue
        occupation_id = str(info.get("zhiyId") or "")
        if not occupation_id:
            continue
        try:
            score = float(info.get("specOccProportion") or 0)
        except (TypeError, ValueError):
            score = 0.0
        scored.append((score, str(name), occupation_id))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [(name, occupation_id) for _, name, occupation_id in scored[:limit]]


def speciality_text(detail: dict[str, Any], *, fallback_name: str = "") -> str:
    """专业详情 → 事实文本：简介、规模、满意度、毕业去向、对口职业。"""
    basic = detail.get("basicVo") or {}
    byfz = detail.get("byfzVo") or {}
    occupation_entries = (byfz.get("expOccList") or {}) if isinstance(byfz, dict) else {}
    occupations = [
        f"{name}（占比 {info.get('specOccProportion')}%）"
        for name, info in occupation_entries.items()
        if isinstance(info, dict) and info.get("zhiyId")
    ]
    advances = [
        item.get("yjsZymc")
        for item in (byfz.get("advances") or [])
        if isinstance(item, dict)
    ]
    overall = basic.get("overAll") or {}
    satisfaction = ""
    if isinstance(overall, dict) and overall.get("avgRank"):
        satisfaction = f"{overall.get('avgRank')}（{overall.get('total')} 人评价）"
    return _clip(
        "\n".join(
            line
            for line in (
                _line("专业", fallback_name or basic.get("zymc")),
                _line("简介", basic.get("desc")),
                _line("年招生规模", basic.get("xsgm")),
                _line("满意度", satisfaction),
                _line("毕业去向行业", byfz.get("byfzCyfxList")),
                _line("对口职业", occupations),
                _line("升学方向", advances),
            )
            if line
        )
    )


def occupation_text(detail: dict[str, Any], *, fallback_name: str = "") -> str:
    """职业详情 → 事实文本：定义、行业、职责、要求、工作环境。"""
    lines = [
        _line("职业", detail.get("zhiyname") or fallback_name),
        _line("所属行业", detail.get("industryName")),
        _line("职业定义", detail.get("zhiydesc")),
    ]
    for section in detail.get("details") or []:
        if not isinstance(section, dict):
            continue
        section_text = _section_text(section)
        if section_text:
            lines.append(_line(str(section.get("mlmc") or "详情"), section_text))
    return _clip("\n".join(line for line in lines if line))


def case_text(item: dict[str, Any]) -> str:
    """人物案例（搜索结果条目）→ 事实文本。

    案例详情页需要登录，公开可取的是搜索条目里的摘要，因此正文就用摘要。
    """
    return _clip(
        "\n".join(
            line
            for line in (
                _line("案例", item.get("caseDesc")),
                _line("摘要", item.get("caseCardDesc")),
                _line("学科门类", item.get("kthzmc")),
                _line("行业", item.get("industryName")),
            )
            if line
        )
    )


__all__ = [
    "case_text",
    "matched_occupations",
    "occupation_text",
    "speciality_text",
    "strip_html",
]
