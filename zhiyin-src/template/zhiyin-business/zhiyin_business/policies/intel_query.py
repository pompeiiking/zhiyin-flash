"""外部情报的**主题口径**：从画像里取出"该去查什么"。

为什么需要单独一条策略
----------------------
外部事实有两条入口，它们必须查同一样东西，否则会出现最难解释的一种不一致：

    用户在情报面板里看到一批（按 A 查的），
    主理在对话里引用的却是另一批（按 B 查的）。

两条入口是：

1. **对话**（② 诊断 / ③ 决策 / ④ 行动 / ① 采集）：编排器取数喂给模型；
2. **面板与推送**（`GET /app/intel`）：用户自己打开看的那一批。

两边都走同一个取数网关，也都把画像字段当检索依据（见
`XueZhiDataSourceGateway._collect`：优先按画像里的专业 / 岗位词检索，
拿不到才退回原始提问）。差的只是"通用网络检索那一路"要一个主题词，
以及情报缓存按 (user, topic) 分桶 —— 主题词给得不一样，两边就是两批数据。

所以这里只做一件事：**把主题词从画像里推出来**，两条入口都用它。

为什么主题词这么取
------------------
- 取**第一个**命中的字段就停：一个人在读的专业只有一个，多取几个拼在一起
  会把检索面摊开（"计算机 会计 汉语言" 查回来的东西谁也不挨着）。
- 认不出的字段一律跳过：宁可没有主题（退回平台通用数据），
  也不拿"最近很焦虑"这种字段去当检索词 —— 那是把用户的状态当成专业名去搜。
- 长度截断到 20 字：网页检索框不是语料库，长句只会把命中率拉低。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

#: 能当"领域主题"的字段特征（键名或中文名命中一个就算）。
#: 顺序即优先级：专业 > 方向 > 岗位/职业 > 行业。
TOPIC_HINTS: tuple[tuple[str, ...], ...] = (
    ("专业", "major", "speciality", "specialty"),
    ("方向", "direction", "track", "target"),
    ("岗位", "职业", "job", "occupation", "career"),
    ("行业", "industry", "sector"),
)

#: 主题词的字符上限：检索框不是语料库。
TOPIC_MAX_CHARS = 20


def _value_of(field: Any) -> str:
    """字段值取成一个短字符串；多值（列表）取第一项。"""
    raw = getattr(field, "value", None)
    if raw is None and isinstance(field, dict):
        raw = field.get("value")
    if isinstance(raw, (list, tuple)):
        raw = next((item for item in raw if str(item).strip()), "")
    if isinstance(raw, dict):
        raw = next((v for v in raw.values() if str(v).strip()), "")
    return str(raw or "").strip()


def _names_of(field: Any) -> str:
    """字段的键与中文名拼一起，用来判断它是不是"领域"字段。"""
    if isinstance(field, dict):
        key, label = field.get("key"), field.get("label")
    else:
        key, label = getattr(field, "key", ""), getattr(field, "label", "")
    return f"{key or ''} {label or ''}".lower()


def intel_topic(fields: Iterable[Any] | None) -> str:
    """从画像字段里推出外部情报的主题词。没有可用的字段时返回空串。

    空串是**合法结果**，也是重要的结果：它表示"还不知道该查什么"，
    取数侧会退回平台通用公开数据，而不是拿一句猜出来的话去查。
    """
    rows: Sequence[Any] = list(fields or [])
    for hints in TOPIC_HINTS:
        for field in rows:
            names = _names_of(field)
            if not any(hint in names for hint in hints):
                continue
            value = _value_of(field)
            if value:
                return value[:TOPIC_MAX_CHARS]
    return ""


__all__ = ["TOPIC_HINTS", "TOPIC_MAX_CHARS", "intel_topic"]
