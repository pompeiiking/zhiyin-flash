"""采集策略：按画像决定"还缺什么、去哪儿取、为什么是它"。

为什么需要一层策略，而不是一个固定管线
--------------------------------------
旧的做法是"绑定学信网 → 固定取回学籍那一套"。它有两个问题：

1. **不问要不要**。用户已经说过自己是哪个学校哪个专业，系统还会再取一遍、
   再写一遍 —— 每一次多余的采集都在消耗用户的耐心；
2. **不问从哪来**。学信网给的是学籍，课程表和成绩单它根本没有。
   不区分源头，就会出现"课程表也去学信网取"这种根本取不到的动线，
   而用户看到的只是"没反应"。

所以采集必须先算一次账：

    缺不缺（对照画像） → 挡着哪一步判断（决定先后） → 有没有源头（决定能不能做）

三个源头的性质完全不同，界面上说法也必须不同：

- `chsi`：学籍 / 学历 / 学位。官方在线验证码读取，**已接通**；
- `conversation`：兴趣、价值取向、经历这类只有本人知道的，问一句就有；
- `academic`：课程表与成绩单。**学信网没有这两个数据**，它们在学校的教务系统里；
  那条路是**学生自己导出后导入**（我们不替他登录任何学校系统）。
  所以它默认可用，但"可用"指的是"导入一次就有"，不是"系统自动帮你去取"。

本模块是**纯函数**：输入画像与所处阶段，输出一张采集清单。
没有 IO、没有状态，所以采集口径可以被单测钉住 —— 一旦漂了，测试会先红。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

from zhiyin_kernel.blackboard import Profile
from zhiyin_kernel.enums import ProfileSource


class CollectionSource(str, Enum):
    """数据从哪来。取值同时用作界面上的分组口径。"""

    CHSI = "chsi"                  # 学信网在线验证：学籍 / 学历 / 学位
    CONVERSATION = "conversation"  # 问本人一句
    ACADEMIC = "academic"          # 课表与成绩单：学生自己从教务系统导出后导入


@dataclass(frozen=True)
class CollectionStep:
    """采集清单里的一条。"""

    key: str
    label: str
    source: CollectionSource
    why: str
    got: bool
    """已经拿到了吗"""
    available: bool
    """这个源头现在能不能用"""
    heard: str = ""
    """用户自己写下的那句话里，命中的原话片段。空表示这条不是被用户的话顶上来的。"""
    ask: str = ""
    """要问用户的那一句（只有 `conversation` 源有）。

    为什么这一句必须从清单里带出来、不能由界面按字段名拼：
    "补兴趣"这种按钮点进去，用户面对的应该是一个**能一句话答上来**的问题，
    而不是"请填写：兴趣"。问题本身是采集口径的一部分，所以它跟 `why` 一样
    属于策略层输出 —— 改它不发版。
    """


@dataclass(frozen=True)
class UserSignal:
    """从用户自己写的东西里读出来的一条线索。"""

    key: str
    """被顶到前面的画像字段"""
    keyword: str
    """命中的线索词"""
    said: str
    """用户的原话片段（截一小段，太长不便于引用）"""
    why: str
    """你这句话为什么让这条数据变成前提"""


@dataclass(frozen=True)
class CollectionPlan:
    """一次采集决策的结果。"""

    steps: tuple[CollectionStep, ...] = ()
    missing: int = 0
    """还差几条"""
    by_source: dict[str, int] = field(default_factory=dict)
    """每个源还差几条 —— 界面按它分组说"从哪取"""
    blocked: tuple[str, ...] = ()
    """有缺口、但没有源头的项（必须如实告诉用户）"""

    def next_source(self) -> Optional[CollectionSource]:
        """下一步最该走的源头：还缺着、且取得到的那个。

        口径是"一次动作补最多条"：学信网一次核验拿全学籍，所以排在最前；
        其次是问本人一句；最后才是教务系统导入。

        这里踩过一个**静默的坑**：候选源头曾经只有学信网与对话，
        而 `by_source` 是照 `available_sources` 算的 —— 装配层早就把
        `academic` 算成可用了。于是"只剩课表/成绩没补"的账号会得到
        `next_source = None`：前端主 CTA 说"没有可自动补的项了"，
        同一屏里课表那两行却还挂着"去导入"。判断与入口自相矛盾，
        而两处都不报错。候选源头现在由枚举驱动，不再手写一份子集。
        """
        for source in _SOURCE_PRIORITY:
            if self.by_source.get(source.value, 0) > 0:
                return source
        return None


# ------------------------------------------------------------------ 规则表

"""
字段 →（中文名、为什么需要它、去哪儿取、问用户的那一句）。

"为什么"这一列是给用户看的，所以写的必须是**这条数据挡着哪一步判断**，
而不是"这是必填项"。用户凭什么再花一次动作，全看这一列说没说清楚。

"问哪一句"只对 `conversation` 源有意义 —— 它是点"去回答"之后落在输入框上方
的那个问题。要求同样是"一句话答得上来"：问一个还要想半天的问题，
等于把补缺口这件事又推回给用户。
"""
_RULES: tuple[tuple[str, str, CollectionSource, str, str], ...] = (
    # ---- 学信网能给的：都是客观事实，一次核验全拿到 ----
    ("major", "专业", CollectionSource.CHSI, "不知道你学什么，方向推荐就无从谈起", ""),
    ("degree_level", "层次", CollectionSource.CHSI, "本科、专科、硕士对应的窗口期完全不同", ""),
    ("expected_graduation", "预计毕业", CollectionSource.CHSI, "它决定你还有几个秋招窗口 —— 冲刺阶段的第一约束", ""),
    ("school", "学校", CollectionSource.CHSI, "同一份简历，学校会影响哪些岗位值得投", ""),
    ("enrollment_status", "学籍状态", CollectionSource.CHSI, "在读、休学、已毕业，能做的事不一样", ""),
    ("duration", "学制", CollectionSource.CHSI, "排完整的时间安排要用它", ""),
    ("study_mode", "学习形式", CollectionSource.CHSI, "全日制和非全日制，能投入的时间差很多", ""),
    ("enrolled_at", "入学日期", CollectionSource.CHSI, "用来推算你现在几年级", ""),
    # ---- 只有本人知道的：问一句就有 ----
    (
        "values",
        "价值取向",
        CollectionSource.CONVERSATION,
        "决定「稳定优先」还是「成长优先」，别人替不了你",
        "找工作的时候，你更在意稳定，还是更在意能不能长本事？",
    ),
    (
        "interest",
        "兴趣",
        CollectionSource.CONVERSATION,
        "方向里哪些你愿意长期做，只有你说得清",
        "有没有什么事，你愿意反复做、做起来不觉得累？",
    ),
    (
        "experience",
        "经历",
        CollectionSource.CONVERSATION,
        "实习与项目是方向判断里最硬的一条证据",
        "到目前为止，你花时间最多的那件事是什么？实习、项目、社团都算。",
    ),
    (
        "skills",
        "能力自评",
        CollectionSource.CONVERSATION,
        "和专业训练相互印证，避免只看成绩",
        "别人最常夸你的一点是什么？一句话就行。",
    ),
    # ---- 学信网没有、只能靠学生自己导入的：界面上要说清"怎么导" ----
    ("courses", "课程表", CollectionSource.ACADEMIC, "没有课表就算不出这周真正能用的空档", ""),
    ("scores", "成绩单", CollectionSource.ACADEMIC, "把课程成绩折算成能力证据", ""),
)

"""出厂可用的源头。

教务系统那一条**不在**默认里：它需要用户授权一次（填学校的系统地址 + 学号密码），
没接通那套网关时，"课程表 / 成绩单"就该老老实实待在"暂时补不了"那一栏，
而不是排到前面去让用户点一个点不动的按钮。

接通之后由调用方把 `academic` 传进来（见 `plan_collection(available_sources=…)`）——
可用性来自**装配实况**，不是一句写死的常量。
"""
_DEFAULT_AVAILABLE: frozenset[CollectionSource] = frozenset(
    {CollectionSource.CHSI, CollectionSource.CONVERSATION}
)

"""下一步的候选顺序。

三个阶段各是一类动作（核验 / 问一句 / 导入），顺序就是界面上的推荐顺序；
**不得只列一部分** —— 少列一个源头，那个源头就会在"下一步"里永久消失，
而它在清单里仍显示"能取"（见 `next_source` 的说明）。
"""
_SOURCE_PRIORITY: tuple[CollectionSource, ...] = (
    CollectionSource.CHSI,
    CollectionSource.CONVERSATION,
    CollectionSource.ACADEMIC,
)

"""所在阶段最卡的几项 —— 同一条缺口，在冲刺期比在探索期更该先补。"""
_STAGE_FIRST: dict[str, tuple[str, ...]] = {
    "sprint": ("expected_graduation", "courses"),
    "act": ("courses", "expected_graduation"),
    "explore": ("values", "interest", "major"),
    "diagnose": ("major", "degree_level", "experience"),
    "review": ("experience", "skills"),
}


def _rules_from(specs: Sequence[Any]) -> tuple[tuple[str, str, CollectionSource, str, str], ...]:
    """把动态资源里的规则收敛成内部用的五元组。

    认不出的来源直接跳过，并**保持顺序** —— 顺序就是"先取哪一条"，
    换一份配置不该顺带把优先级也打乱。
    """
    table: list[tuple[str, str, CollectionSource, str, str]] = []
    for spec in specs:
        try:
            source = CollectionSource(getattr(spec, "source", "") or "")
        except ValueError:
            continue
        key = str(getattr(spec, "key", "") or "")
        if not key:
            continue
        table.append(
            (
                key,
                str(getattr(spec, "label", "") or key),
                source,
                str(getattr(spec, "why", "") or ""),
                str(getattr(spec, "ask", "") or ""),
            )
        )
    return tuple(table)


def field_labels(rules: Optional[Sequence[Any]] = None) -> dict[str, str]:
    """登记表里的画像字段：**键 → 中文名**（`collection_rules.json`）。

    给"用户手动更正画像"做门禁用：只有登记过的键才允许写进画像。
    为什么用这张表而不是随口收下：画像里出现一个没有中文名、采集清单与报告维度
    也都不认识的键，界面上就是一格没人读得懂的东西（实测出现过
    `interest_direction` / `course_selection_pattern` 这类自由发挥的键）。

    `rules` 读不到时退回内置兜底表 —— 与 `plan_collection` 同一条口径，
    否则"配置没装载"会变成"用户改什么都被拒"。
    """
    table = _rules_from(rules) if rules else _RULES
    return {key: label for key, label, _source, _why, _ask in table}


_SNIPPET_PAD = 6


def _snippet(text: str, keyword: str, pad: int = _SNIPPET_PAD) -> str:
    """把命中的那句话截一小段出来。

    引用用户原话要能读得动：整段待办贴进理由里，"因为你写了…"这半句就淹了。
    截在命中词两侧各几个字，两头截断的地方用省略号交代清楚 ——
    不能让用户以为那就是他写的全部。
    """
    i = text.find(keyword)
    if i < 0:
        return keyword
    start = max(0, i - pad)
    end = min(len(text), i + len(keyword) + pad)
    head = "…" if start > 0 else ""
    tail = "…" if end < len(text) else ""
    return f"{head}{text[start:end].strip()}{tail}"


def signals_from(notes: Sequence[str], specs: Sequence[Any]) -> tuple[UserSignal, ...]:
    """读用户自己写下的东西，找出让某条数据变成前提的线索。

    只做一件事：**在用户的话里找线索词**。不做语义推断，也不猜 ——
    猜出来的"用户画像"是最难解释的一类错误：用户没说过的话被当成他说过，
    后面每一句建议都会跟着可疑。宁可少推一条，也不推一条用户不认的。

    同一条画像字段被多句话命中时只留第一条（按 order）：
    回执里只需要一个理由，多给几个反而像在找借口。
    """
    table: list[tuple[int, str, str, str]] = []
    for spec in specs or ():
        keyword = str(getattr(spec, "keyword", "") or "").strip()
        key = str(getattr(spec, "key", "") or "").strip()
        if not keyword or not key:
            continue
        table.append(
            (
                int(getattr(spec, "order", 0) or 0),
                keyword,
                key,
                str(getattr(spec, "why", "") or ""),
            )
        )
    table.sort(key=lambda row: row[0])

    seen: set[str] = set()
    out: list[UserSignal] = []
    for _order, keyword, key, why in table:
        if key in seen:
            continue
        for note in notes or ():
            text = str(note or "")
            if keyword not in text:
                continue
            seen.add(key)
            out.append(
                UserSignal(key=key, keyword=keyword, said=_snippet(text, keyword), why=why)
            )
            break
    return tuple(out)


def _compose_why(signal: UserSignal, rule_why: str) -> str:
    """把你写的话和系统的账接成一句。

    顺序不能反：先说"因为你写了…"（引用用户），再说为什么（系统的账）。
    反过来就成了"系统需要这个，顺便因为你写过"—— 读起来还是被要东西。
    """
    said = signal.said or signal.keyword
    return f"因为你写了「{said}」：{signal.why or rule_why}"


"""登记来源属于"权威记录类"的字段：它们的值必须由**相称的来源**写进来才算拿到。

为什么必须区分来源
------------------
`major` 这类字段在 `collection_rules.json` 上登记的源头是 `chsi`（学信网核验）。
"拿到了没"如果只看键在不在画像里，用户在对话里随口说的那句"计算机大类"就会被算成
已经拿到 —— 学信网核验从此不再被要求、界面上也不再提示，一句对话就此长得像一条
权威记录。这正是 #26 里"系统直接默认认定"的结构性原因：问题不在提示词怎么写，
而在这道判定把**值在不在**当成了**值由谁出具**。
"""
_AUTHORITATIVE_SOURCES: frozenset[CollectionSource] = frozenset(
    {CollectionSource.CHSI, CollectionSource.ACADEMIC}
)

"""对权威字段来说，落库的 `source` 取到什么才算相称。只有两类：

- `record`（客观档案）：学信网在线验证与教务系统导出的原始记录落库时写的都是它
  （见 `services/ai_tasks.py` 的核验写入与 `services/academic.py` 的导入摘要），
  它就是这个字段登记的权威来源本身；
- `user_edit`（本人填写）：用户一字一句告诉系统的值就是拿到了 —— 把他亲手更正过的那条
  又判成"没拿到"，他会一直看到"还差这一条"，上一轮补的手动更正等于白做。

`conversation` / `behavior_inference` 这类推断来源**不在其中**：它们对权威字段不算拿到。
值仍然可以留在画像里做参考（不清、不覆盖），但这条字段要继续出现在缺口里，
对应的采集动作（学信网核验 / 教务导入）也要保持"该做"的状态。

`resume` / `assessment` / `mentor` 同样不算：它们都是**转述或推断**，不是出具方本身，
"相称"问的是这条值由谁签发，不是它听起来多正式。
"""
_AUTHORITY_MATCHING_SOURCES: frozenset[ProfileSource] = frozenset(
    {ProfileSource.RECORD, ProfileSource.USER_EDIT}
)


def _field_source(field: Any) -> Optional[ProfileSource]:
    """读一个画像字段的来源。

    读不出来（缺失、或是认不出的字符串）返回 `None`，按"不相称"处理：
    来源是一份**声明**，读不懂的声明不能替这条值撑起权威性。
    内存装配里它是枚举、库里回来的是字符串，两种都要认。
    """
    raw = getattr(field, "source", None)
    if isinstance(raw, ProfileSource):
        return raw
    try:
        return ProfileSource(str(raw))
    except ValueError:
        return None


def _counts_as_got(rule_source: CollectionSource, field: Any) -> bool:
    """这一条算不算"已经拿到了"。

    登记来源不是权威类的字段（`chsi` / `academic` 之外的，例如 `conversation` 的兴趣、
    目标方向）口径**完全不变**：键在画像里就算拿到。顺手把它们也收紧会把正常动线卡死 ——
    这类字段本来就该从对话来，问对了就是拿到了。

    权威字段（学信网核验 / 教务导入）才看来源。
    """
    if field is None:
        return False
    if rule_source not in _AUTHORITATIVE_SOURCES:
        return True
    return _field_source(field) in _AUTHORITY_MATCHING_SOURCES


def rule_source_of(
    key: str, rules: Optional[Sequence[Any]] = None
) -> Optional[CollectionSource]:
    """这个画像字段在采集登记表里登记的来源；没登记、或来源认不出时返回 `None`。

    "这条值该由谁出具"写在登记表上（`collection_rules.json`），不在字段自己身上。
    所以别的读侧（画像覆盖度、采集门槛）只拿着一个键来问这里，而不是各自
    再存一份"哪些字段是权威的" —— 抄一份就一定会跟登记表漂开。
    """
    table = _rules_from(rules) if rules else _RULES
    for rule_key, _label, source, _why, _ask in table:
        if rule_key == key:
            return source
    return None


def counts_as_got(
    key: str, field: Any, *, rules: Optional[Sequence[Any]] = None
) -> bool:
    """画像里**这个键的这条值**算不算"已经拿到了"。

    这是"拿到了没"的**唯一实现**，三处读它：采集清单（`plan_collection`）、
    画像覆盖度（`services/workspace.py::_coverage`）、采集门槛
    （`policies/collection_gate.py::evaluate_gate`）。
    为什么必须共用：这三处各写一份的结果真实出现过 —— 采集清单说"还差专业"，
    同一屏的画像面板却显示"覆盖 100%"，用户看到的是两句话互相打脸，
    而两处都不报错。

    没登记的键（模型自由生成的字段、以及后续新增但还没进登记表的字段）
    没有"相称来源"可谈：键在画像里就算拿到 —— 与收紧前完全一致，
    不能因为这里认不出它就把新字段一律算成缺口。
    """
    if field is None:
        return False
    source = rule_source_of(key, rules)
    if source is None:
        return True
    return _counts_as_got(source, field)


def plan_collection(
    profile: Optional[Profile],
    *,
    stage: Optional[str] = None,
    rules: Optional[Sequence[Any]] = None,
    notes: Sequence[str] = (),
    signals: Sequence[Any] = (),
    available_sources: Optional[Sequence[str]] = None,
) -> CollectionPlan:
    """按画像算一次采集清单。

    `rules` 由调用方从**动态资源**读进来（`data/registry/collection_rules.json`
    → `list_collection_rules()`）。不传时退回模块里那份内置表 ——
    内置表是兜底，不是第二份权威：库里改了、这里没改，以库为准。

    **不做截断。** 曾经这里有个 `limit` 参数，看着像是"界面只列前几条"的小优化，
    实际上是个 bug：`filled_by()` 靠前后两份清单比对"这一趟补上了哪几条"，
    清单一旦被截断，被截掉的那几条就永远算不出"补上了" ——
    闭环里最该给用户看的那半句会悄悄变少。
    要少列几条是界面的事，不是策略的事。

    `notes` 是**用户自己写下的东西**（自建待办、写下的话），`signals` 是
    `data/registry/user_signals.json` 里的线索表。自己写的东西优先级高于
    系统按阶段猜的：他既然说了想冲秋招，先去取毕业时间就是他的账，不是系统的账。

    `available_sources` 是**现在真的能用的源头**（默认 学信网 + 对话）。
    接通教务系统之后调用方把 `academic` 加进来，"课程表"才会从
    "暂时补不了"变成"授权一次就能取" —— 可用性跟着装配实况走，
    不跟着代码里的一句注释走。
    """
    table = _rules_from(rules) if rules else _RULES
    # 画像里现存的字段按**整条**留下（键 → 字段），不是一个只有键的集合：
    # 判"拿到了没"要看来源，而来源只在这条字段本身上（见 `_counts_as_got`）。
    have = {field.key: field for field in (profile.fields if profile else [])}
    first = _STAGE_FIRST.get((stage or "").lower(), ())
    usable = (
        frozenset(str(item) for item in available_sources)
        if available_sources is not None
        else frozenset(source.value for source in _DEFAULT_AVAILABLE)
    )
    heard = signals_from(tuple(notes or ()), signals)
    heard_by_key = {signal.key: signal for signal in heard}

    steps: list[CollectionStep] = []
    by_source: dict[str, int] = {}
    blocked: list[str] = []
    missing = 0

    for key, label, source, why, ask in table:
        # 判据是"这条值由谁出具"，不是"这个键出现过没有" ——
        # 只对话里提过一句的权威字段，仍然该去做学信网核验（见 `_counts_as_got`）。
        got = _counts_as_got(source, have.get(key))
        available = source.value in usable
        signal = heard_by_key.get(key)
        if signal is not None:
            why = _compose_why(signal, why)
        if not got:
            missing += 1
            if available:
                by_source[source.value] = by_source.get(source.value, 0) + 1
            else:
                blocked.append(label)
        steps.append(
            CollectionStep(
                key=key,
                label=label,
                source=source,
                why=why,
                got=got,
                available=available,
                heard=signal.said if signal is not None else "",
                # 只有"问一句"那一类才有问题；已经拿到的不再问，所以也不给问题 ——
                # 界面据此不给已完成的条目挂"去回答"。
                ask=ask if (source is CollectionSource.CONVERSATION and not got) else "",
            )
        )

    """
    排序口径 = 界面上从头往下读的顺序，也就是"现在最该做哪一件"：

      ① 缺、且取得到 —— 这才是能动手的；
      ② 缺、但没有源头 —— 必须让用户看见"这里暂时没法自动补"，但不能排在最前面
         挡着那些马上能做的事；
      ③ 已经有了 —— 沉到最后，它是记录，不是待办。

    同一档里，顺序是"谁说的"：**用户自己写下来的排最前**（他最清楚自己在忙什么），
    其次才是本阶段最卡的那几条，最后按规则表顺序（表序本身就是重要度）。
    """
    order_index = {key: i for i, (key, *_rest) in enumerate(table)}
    stage_rank = {key: i for i, key in enumerate(first)}
    heard_rank = {signal.key: i for i, signal in enumerate(heard)}

    def order(step: CollectionStep) -> tuple[int, int, int, int]:
        if step.got:
            bucket = 2
        elif not step.available:
            bucket = 1
        else:
            bucket = 0
        from_user = heard_rank.get(step.key, len(heard_rank))
        # 本阶段最卡的那几条按 `_STAGE_FIRST` 里写的次序排 ——
        # 那个元组本身就是优先级，不按字典序，也不按规则表顺序。
        staged = stage_rank.get(step.key, len(first))
        return (bucket, from_user, staged, order_index.get(step.key, 99))

    steps.sort(key=order)
    return CollectionPlan(
        steps=tuple(steps),
        missing=missing,
        by_source=by_source,
        blocked=tuple(blocked),
    )


def filled_by(plan_before: CollectionPlan, plan_after: CollectionPlan) -> tuple[str, ...]:
    """这一趟采集补上了哪几条 —— 闭环里"取回来的东西"那半句。

    只对比"缺 → 有"的翻转，不看值有没有变：
    用户关心的是"这一趟有没有让还差的东西变少"，不是字段被写了几遍。
    """
    before_missing = {
        step.key for step in plan_before.steps if not step.got
    }
    after_have = {
        step.key for step in plan_after.steps if step.got
    }
    filled = before_missing & after_have
    labels = {step.key: step.label for step in plan_after.steps}
    return tuple(labels[key] for key in sorted(filled))


__all__ = [
    "CollectionPlan",
    "CollectionSource",
    "CollectionStep",
    "UserSignal",
    "counts_as_got",
    "field_labels",
    "filled_by",
    "plan_collection",
    "rule_source_of",
    "signals_from",
]
