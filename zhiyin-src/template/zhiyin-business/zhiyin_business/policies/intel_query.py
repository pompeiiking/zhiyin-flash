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
`XueZhiDataSourceGateway._collect`：优先按画像里的专业 / 职业关注检索，
拿不到才退回原始提问）。差的只是"通用网络检索那一路"要一个主题词，
以及情报缓存按 (user, topic) 分桶 —— 主题词给得不一样，两边就是两批数据。

所以这里只做一件事：**把主题词从画像里推出来**，两条入口都用它。

为什么主题词这么取（2026-10-20 修正）
------------------------------------
- 只认受控的字段：专业（`major` 等）优先，其次才是明确的职业关注
  （`target_direction` / `target_job` 等）。**兴趣、价值取向、现实条件、
  补充信息一律不进来** —— 它们不是职业名称，拿它们当检索词的结果就是
  "把东西真正跑起来的过程"查出 0 个职业和两条无关案例。
- 取**第一个**命中的字段就停：一个人在读的专业只有一个，多取几个拼在一起
  会把检索面摊开（"计算机 会计 汉语言" 查回来的东西谁也不挨着）。
- 认不出的字段一律跳过：宁可没有主题（退回平台通用数据），
  也不拿"最近很焦虑"这种字段去当检索词 —— 那是把用户的状态当成专业名去搜。
- 长度截断到 20 字：网页检索框不是语料库，长句只会把命中率拉低。
"""

from __future__ import annotations

from typing import Any, Iterable

from zhiyin_kernel import profile_taxonomy

#: 主题词的字符上限：检索框不是语料库。
TOPIC_MAX_CHARS = 20

#: 兼容旧接口：仍然导出“专业 > 方向 > 岗位 > 行业”的说明，但真正的取词
#: 由受控词表（`profile_taxonomy.MAJOR_KEYS / CAREER_FOCUS_KEYS`）决定。
TOPIC_HINTS: tuple[tuple[str, ...], ...] = (
    ("专业", "major", "speciality", "specialty"),
    ("方向", "direction", "track", "target"),
    ("岗位", "职业", "job", "occupation", "career"),
    ("行业", "industry", "sector"),
)


def intel_topic(fields: Iterable[Any] | None) -> str:
    """从画像字段里推出外部情报的主题词。没有可用的字段时返回空串。

    空串是**合法结果**，也是重要的结果：它表示"还不知道该查什么"，
    取数侧会退回平台通用公开数据，而不是拿一句猜出来的话去查。
    """
    rows = list(fields or [])
    for terms in (
        profile_taxonomy.major_terms(rows),
        profile_taxonomy.career_focus_terms(rows),
    ):
        if terms:
            return terms[0][:TOPIC_MAX_CHARS]
    return ""


__all__ = ["TOPIC_HINTS", "TOPIC_MAX_CHARS", "intel_topic"]
