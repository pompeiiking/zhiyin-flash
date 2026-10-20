"""画像条目词表与用途视图（《个人画像设计-2026-10-20》第 2/4/8 节）。

为什么放在 kernel
-----------------
类别、核实状态、以及「哪类内容可以进哪个用途」是跨层共享的**语义契约**：
业务层按它校验写入，基础设施取数按它选词，界面按它组织展示。放在任何一层
实现里都会逼出「另一层各自再写一份口径」的老问题 —— 而这份口径一旦分成
两份，读取方就会重新开始猜字符串含义（这正是本轮要修掉的根因）。

这里只放受控词表与纯函数，不读写数据库、不构造业务对象。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from zhiyin_kernel.enums import (
    ProfileEntryStatus,
    ProfileEntryType,
    ProfilePurpose,
    ProfileSource,
    ProfileVerification,
)
from zhiyin_kernel.errors import InvalidRequest

#: 类别中文名（界面显示与错误文案共用；不另起第二份）。
ENTRY_TYPE_LABELS: dict[ProfileEntryType, str] = {
    ProfileEntryType.LEARNING_BACKGROUND: "学习背景",
    ProfileEntryType.INTEREST: "兴趣与偏好",
    ProfileEntryType.EXPERIENCE: "经历",
    ProfileEntryType.ABILITY: "能力与技能",
    ProfileEntryType.CAREER_FOCUS: "职业关注",
    ProfileEntryType.VALUES: "价值取向",
    ProfileEntryType.CONDITION: "现实条件",
    ProfileEntryType.SUPPLEMENT: "补充信息",
}

#: 核实状态中文名（界面显示；与来源说明分开，不用“把握度”代替）。
VERIFICATION_LABELS: dict[ProfileVerification, str] = {
    ProfileVerification.SELF_REPORTED: "本人自述",
    ProfileVerification.USER_CONFIRMED: "本人确认",
    ProfileVerification.RECORD: "资料记录",
    ProfileVerification.VERIFIED: "已核验",
    ProfileVerification.PENDING: "待核对",
}

#: 条目状态中文名（界面上区分有效、被更正、冲突、过期与撤回）。
STATUS_LABELS: dict[ProfileEntryStatus, str] = {
    ProfileEntryStatus.ACTIVE: "当前有效",
    ProfileEntryStatus.CORRECTED: "已由本人更正",
    ProfileEntryStatus.CONFLICT: "来源存在冲突",
    ProfileEntryStatus.EXPIRED: "已过期",
    ProfileEntryStatus.WITHDRAWN: "已撤回",
    ProfileEntryStatus.SUPERSEDED: "已被后续版本替代",
}

#: 字段键 → 内容类别。键来自画像字段词表（`profile.field.*`），模型不能自由生成。
#: 认不出的键落到“补充信息”：宁可待归类，也不猜到「兴趣」或「职业目标」上。
KEY_ENTRY_TYPES: dict[str, ProfileEntryType] = {
    # 学习背景
    "school": ProfileEntryType.LEARNING_BACKGROUND,
    "major": ProfileEntryType.LEARNING_BACKGROUND,
    "department": ProfileEntryType.LEARNING_BACKGROUND,
    "study_year": ProfileEntryType.LEARNING_BACKGROUND,
    "degree_level": ProfileEntryType.LEARNING_BACKGROUND,
    "enrollment_status": ProfileEntryType.LEARNING_BACKGROUND,
    "student_name": ProfileEntryType.LEARNING_BACKGROUND,
    "student_no": ProfileEntryType.LEARNING_BACKGROUND,
    "duration": ProfileEntryType.LEARNING_BACKGROUND,
    "study_mode": ProfileEntryType.LEARNING_BACKGROUND,
    "enrolled_at": ProfileEntryType.LEARNING_BACKGROUND,
    "expected_graduation": ProfileEntryType.LEARNING_BACKGROUND,
    "courses": ProfileEntryType.LEARNING_BACKGROUND,
    "scores": ProfileEntryType.LEARNING_BACKGROUND,
    "current_status": ProfileEntryType.LEARNING_BACKGROUND,
    # 兴趣与偏好（多条、可不确定、可变化；不能充职业名称或能力证明）
    "interest": ProfileEntryType.INTEREST,
    "interests": ProfileEntryType.INTEREST,
    "style": ProfileEntryType.INTEREST,
    "preferences": ProfileEntryType.INTEREST,
    # 经历（保存具体事件；同一经历多处引用不复制成多份事实）
    "experience": ProfileEntryType.EXPERIENCE,
    "internship": ProfileEntryType.EXPERIENCE,
    "project": ProfileEntryType.EXPERIENCE,
    # 能力与技能（区分接触、自评与成果）
    "skills": ProfileEntryType.ABILITY,
    "resume_material": ProfileEntryType.ABILITY,
    "award": ProfileEntryType.ABILITY,
    "weakness": ProfileEntryType.ABILITY,
    # 职业关注（关注状态分开；查询/点击/推荐不能自动成为已选目标）
    "target_direction": ProfileEntryType.CAREER_FOCUS,
    "target_direction.job_posting": ProfileEntryType.CAREER_FOCUS,
    "target_job": ProfileEntryType.CAREER_FOCUS,
    "career_interest": ProfileEntryType.CAREER_FOCUS,
    "career_focus": ProfileEntryType.CAREER_FOCUS,
    "direction": ProfileEntryType.CAREER_FOCUS,
    # 价值取向
    "values": ProfileEntryType.VALUES,
    # 现实条件（标明适用范围和时间；本周没空不是长期没有时间）
    "constraints": ProfileEntryType.CONDITION,
    "city": ProfileEntryType.CONDITION,
    "jobtype": ProfileEntryType.CONDITION,
    "salary": ProfileEntryType.CONDITION,
    "family": ProfileEntryType.CONDITION,
    "time": ProfileEntryType.CONDITION,
    "weekly_hours": ProfileEntryType.CONDITION,
    "pipeline": ProfileEntryType.CONDITION,
    "schedule": ProfileEntryType.CONDITION,
    "stuck_point": ProfileEntryType.CONDITION,
    # 明确进入补充信息的键
    "supplement": ProfileEntryType.SUPPLEMENT,
    "supplement_info": ProfileEntryType.SUPPLEMENT,
}

#: 专业检索只认这些键：普通兴趣、价值偏好或补充描述都不能替代专业查询。
MAJOR_KEYS: tuple[str, ...] = ("major", "speciality", "target_major", "field_of_study")

#: 职业检索只认“明确的职业关注”：兴趣、行业、任意描述都不拼成职业名称。
CAREER_FOCUS_KEYS: tuple[str, ...] = (
    "target_job",
    "target_direction",
    "target_direction.job_posting",
    "career_interest",
    "career_focus",
    "direction",
)

#: 每个类别允许的结构化属性（受控键；值类型与上限也在这里定义）。
INTEREST_POLARITIES: tuple[str, ...] = ("like", "dislike", "unsure")
CAREER_FOCUS_STATES: tuple[str, ...] = ("exploring", "considering", "selected")
ABILITY_EVIDENCE_KINDS: tuple[str, ...] = (
    "exposed",       # 接触过
    "self_assessed", # 本人自评
    "completed_once",# 单次完成
    "work_output",   # 有作品/成果
    "verified",      # 外部核验
)

ATTRIBUTE_SPECS: dict[ProfileEntryType, dict[str, tuple[str, ...]]] = {
    ProfileEntryType.INTEREST: {
        "polarity": INTEREST_POLARITIES,
        "context": (),
    },
    ProfileEntryType.CAREER_FOCUS: {
        "state": CAREER_FOCUS_STATES,
        "occupation_id": (),
    },
    ProfileEntryType.ABILITY: {
        "evidence_kind": ABILITY_EVIDENCE_KINDS,
        "context": (),
    },
    ProfileEntryType.EXPERIENCE: {"outcome": ()},
    ProfileEntryType.CONDITION: {"scope": ()},
    ProfileEntryType.SUPPLEMENT: {"title": (), "pending_classification": ()},
}

#: 属性值的长度上限（枚举型不需要，自由文本需要）。
ATTRIBUTE_MAX_CHARS: dict[str, int] = {
    "context": 120,
    "outcome": 2000,
    "scope": 120,
    "title": 120,
    "occupation_id": 64,
}

#: 各键的取值上限（字符）。不在表里的键落到类别上限。
KEY_VALUE_LIMITS: dict[str, int] = {
    "major": 40,
    "school": 40,
    "department": 40,
    "student_name": 40,
    "student_no": 40,
    "study_year": 20,
    "degree_level": 20,
    "enrollment_status": 20,
    "duration": 20,
    "study_mode": 20,
    "enrolled_at": 20,
    "expected_graduation": 20,
    "courses": 12000,
    "scores": 12000,
    "experience": 12000,
}

#: 各类型的默认上限：经历正文与短标签分开，不再用统一的 40 字承载所有记录。
TYPE_VALUE_LIMITS: dict[ProfileEntryType, int] = {
    ProfileEntryType.LEARNING_BACKGROUND: 60,
    ProfileEntryType.INTEREST: 60,
    ProfileEntryType.EXPERIENCE: 12000,
    ProfileEntryType.ABILITY: 60,
    ProfileEntryType.CAREER_FOCUS: 60,
    ProfileEntryType.VALUES: 240,
    ProfileEntryType.CONDITION: 240,
    ProfileEntryType.SUPPLEMENT: 240,
}

#: 允许一条记录里放多项的类别（兴趣与职业关注天然是多条偏好/多个关注对象）。
TYPE_MAX_ITEMS: dict[ProfileEntryType, int] = {
    ProfileEntryType.INTEREST: 8,
    ProfileEntryType.ABILITY: 8,
    ProfileEntryType.CAREER_FOCUS: 6,
}

#: 用途 → 允许进入该用途的内容类别（第 8 节的用途表）。
PURPOSE_TYPES: dict[ProfilePurpose, frozenset[ProfileEntryType]] = {
    ProfilePurpose.MAJOR_RETRIEVAL: frozenset({ProfileEntryType.LEARNING_BACKGROUND}),
    ProfilePurpose.CAREER_RETRIEVAL: frozenset({ProfileEntryType.CAREER_FOCUS}),
    ProfilePurpose.DIRECTION_RECOMMENDATION: frozenset(
        {
            # 专业/学校是“方向推荐与比较”的背景事实（读的是哪个专业、哪一阶段），
            # 不是用它替代兴趣或职业关注；普通兴趣仍然不能进入专业检索。
            ProfileEntryType.LEARNING_BACKGROUND,
            ProfileEntryType.INTEREST,
            ProfileEntryType.EXPERIENCE,
            ProfileEntryType.ABILITY,
            ProfileEntryType.VALUES,
            ProfileEntryType.CONDITION,
            ProfileEntryType.CAREER_FOCUS,
        }
    ),
    ProfilePurpose.PLANNING: frozenset(
        {
            ProfileEntryType.CAREER_FOCUS,
            ProfileEntryType.ABILITY,
            ProfileEntryType.CONDITION,
            ProfileEntryType.LEARNING_BACKGROUND,
        }
    ),
    ProfilePurpose.CONVERSATION: frozenset(ProfileEntryType),
}

#: 不可用于任何业务读取的状态。修正过的记录仍是当前值（CORRECTED 可用），
#: 冲突/过期/撤回必须退出读取，除非用户主动打开“全部记录”。
_UNUSABLE_STATUSES = frozenset(
    {
        ProfileEntryStatus.CONFLICT,
        ProfileEntryStatus.EXPIRED,
        ProfileEntryStatus.WITHDRAWN,
        ProfileEntryStatus.SUPERSEDED,
    }
)


def entry_type_of(key: str) -> ProfileEntryType:
    """字段键 → 内容类别。认不出的键是“补充信息”，不是“兴趣”。"""
    return KEY_ENTRY_TYPES.get((key or "").strip(), ProfileEntryType.SUPPLEMENT)


def entry_type_label(entry_type: ProfileEntryType | str | None) -> str:
    try:
        return ENTRY_TYPE_LABELS[ProfileEntryType(entry_type)]
    except (ValueError, KeyError):
        return ENTRY_TYPE_LABELS[ProfileEntryType.SUPPLEMENT]


def verification_for(source: ProfileSource | str) -> ProfileVerification:
    """来源 → 默认核实状态。

    来源不自动证明能力或职业判断成立：对话里的自述只是自述，客观档案是资料记录，
    外部核验才是核验。这里只做“来源方式”的默认映射，真实核实与否由写入方声明。
    """
    try:
        value = ProfileSource(source)
    except ValueError:
        return ProfileVerification.PENDING
    return {
        ProfileSource.CONVERSATION: ProfileVerification.SELF_REPORTED,
        ProfileSource.ASSESSMENT: ProfileVerification.PENDING,
        ProfileSource.BEHAVIOR_INFERENCE: ProfileVerification.PENDING,
        ProfileSource.MENTOR: ProfileVerification.PENDING,
        ProfileSource.USER_EDIT: ProfileVerification.USER_CONFIRMED,
        ProfileSource.RECORD: ProfileVerification.RECORD,
        ProfileSource.RESUME: ProfileVerification.RECORD,
    }.get(value, ProfileVerification.PENDING)


def is_usable(field: Any) -> bool:
    """这条记录能不能进入业务读取（有效或已更正；冲突/过期/撤回退出）。"""
    status = getattr(field, "status", None) or (
        field.get("status") if isinstance(field, Mapping) else None
    )
    if status in (None, ""):
        # 老数据没有状态列：默认按“当前有效”处理，不因此把它排除在读取之外。
        return True
    try:
        return ProfileEntryStatus(status) not in _UNUSABLE_STATUSES
    except ValueError:
        return False


def value_limit(key: str, entry_type: ProfileEntryType | None = None) -> int:
    """这条记录的取值上限（字符）；按「键优先、类别兜底」。"""
    canonical = entry_type or entry_type_of(key)
    return KEY_VALUE_LIMITS.get((key or "").strip(), TYPE_VALUE_LIMITS[canonical])


def allows_multiple(key: str, entry_type: ProfileEntryType | None = None) -> bool:
    return (entry_type or entry_type_of(key)) in TYPE_MAX_ITEMS


def max_items(key: str, entry_type: ProfileEntryType | None = None) -> int:
    return TYPE_MAX_ITEMS.get(entry_type or entry_type_of(key), 1)


def normalize_value(key: str, value: Any, entry_type: ProfileEntryType | None = None) -> Any:
    """把写入值整理成该类别的合法形状。

    - 多值类别：列表逐项去空白、去重、保序，最多 `max_items` 项；
    - 单值类别：字符串去空白；空值明确拒绝（清空是撤回/删除，不是写空串）。
    """
    canonical = entry_type or entry_type_of(key)
    limit = value_limit(key, canonical)
    if allows_multiple(key, canonical):
        items = value if isinstance(value, (list, tuple)) else [value]
        cleaned: list[str] = []
        for item in items:
            text = "" if item is None else str(item).strip()
            if not text:
                continue
            if len(text) > limit:
                raise InvalidRequest(
                    f"「{ENTRY_TYPE_LABELS[canonical]}」里的一条最多 {limit} 个字，"
                    f"现在有 {len(text)} 个 —— 请直接写那一件事。"
                )
            if text not in cleaned:
                cleaned.append(text)
        if not cleaned:
            raise InvalidRequest(f"「{ENTRY_TYPE_LABELS[canonical]}」不能是空的。")
        if len(cleaned) > max_items(key, canonical):
            raise InvalidRequest(
                f"「{ENTRY_TYPE_LABELS[canonical]}」最多记 {max_items(key, canonical)} 条，"
                f"现在有 {len(cleaned)} 条 —— 请保留最重要的几条。"
            )
        return cleaned
    text = "" if value is None else str(value).strip()
    if not text:
        raise InvalidRequest(f"「{ENTRY_TYPE_LABELS[canonical]}」不能是空的。")
    if len(text) > limit:
        raise InvalidRequest(
            f"「{ENTRY_TYPE_LABELS[canonical]}」最多 {limit} 个字，现在有 {len(text)} 个 —— "
            "请拆成一条读得完的事实。"
        )
    return text


def normalize_attributes(entry_type: ProfileEntryType, attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    """校验并整理类别专属属性；未登记的属性一律拒绝（模型不能自由扩展）。"""
    if not attributes:
        return {}
    specs = ATTRIBUTE_SPECS.get(entry_type, {})
    allowed = set(specs)
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise InvalidRequest(
            f"「{ENTRY_TYPE_LABELS[entry_type]}」不支持这些属性：{'、'.join(unknown)}"
        )
    normalized: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        choices = specs.get(key, ())
        if choices:
            text = str(value).strip()
            if text not in choices:
                raise InvalidRequest(
                    f"「{ENTRY_TYPE_LABELS[entry_type]}」的「{key}」只能是：{'、'.join(choices)}"
                )
            normalized[key] = text
            continue
        if isinstance(value, bool):
            normalized[key] = value
            continue
        text = str(value).strip()
        limit = ATTRIBUTE_MAX_CHARS.get(key, 240)
        if len(text) > limit:
            raise InvalidRequest(f"「{ENTRY_TYPE_LABELS[entry_type]}」的「{key}」最多 {limit} 个字。")
        normalized[key] = text
    return normalized


def validate_window(valid_from: Any, valid_to: Any) -> None:
    """有效范围的起止要能对上；未知时间不补成当前时间。"""
    if valid_from is not None and valid_to is not None and valid_from > valid_to:
        raise InvalidRequest("有效范围的开始时间不能晚于结束时间。")


def records_for_purpose(purpose: ProfilePurpose, fields: Iterable[Any]) -> list[Any]:
    """按用途筛出可读记录（有效状态 + 类别允许）。

    调用方拿到的是**服务端算好的用途视图**，不用再自行扫描整份画像。
    """
    allowed = PURPOSE_TYPES[ProfilePurpose(purpose)]
    selected = [field for field in fields if is_usable(field) and _entry_type(field) in allowed]
    return selected


def major_terms(fields: Iterable[Any]) -> list[str]:
    """专业检索词：只来自明确的学习背景专业字段。"""
    return _terms_from_keys(records_for_purpose(ProfilePurpose.MAJOR_RETRIEVAL, fields), MAJOR_KEYS)


def career_focus_terms(fields: Iterable[Any]) -> list[str]:
    """职业/方向检索词：只来自明确的职业关注字段。"""
    return _terms_from_keys(records_for_purpose(ProfilePurpose.CAREER_RETRIEVAL, fields), CAREER_FOCUS_KEYS)


#: 检索词上限：检索框不是语料库。
TERM_MAX_CHARS = 40


def value_terms(value: Any) -> list[str]:
    """把一个记录的取值摊平成若干检索词（多值条目逐项取）。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw: list[Any] = list(value)
    elif isinstance(value, Mapping):
        raw = [value.get(key) for key in ("activity", "target", "name", "text", "value")]
    else:
        raw = [value]
    terms: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        text = text[:TERM_MAX_CHARS]
        if text not in terms:
            terms.append(text)
    return terms


def scope_terms(fields: Iterable[Any], *, types: Sequence[ProfileEntryType]) -> list[str]:
    """按类别取检索词（供用途视图之外的定向读取使用）。"""
    wanted = set(types)
    return _terms_from_keys(
        [field for field in fields if is_usable(field) and _entry_type(field) in wanted], None
    )


# ---------------------------------------------------------------------------
# 内部：字段对象 / 字典两种形状都认（gateway 上下文进来的是 dict）
# ---------------------------------------------------------------------------


def _entry_type(field: Any) -> ProfileEntryType:
    raw = field.get("entry_type") if isinstance(field, Mapping) else getattr(field, "entry_type", None)
    if raw:
        try:
            return ProfileEntryType(raw)
        except ValueError:
            pass
    key = field.get("key") if isinstance(field, Mapping) else getattr(field, "key", "")
    return entry_type_of(str(key or ""))


def _field_value(field: Any) -> Any:
    return field.get("value") if isinstance(field, Mapping) else getattr(field, "value", None)


def _field_key(field: Any) -> str:
    raw = field.get("key") if isinstance(field, Mapping) else getattr(field, "key", "")
    return str(raw or "")


def _terms_from_keys(fields: Iterable[Any], keys: Sequence[str] | None) -> list[str]:
    wanted = set(keys) if keys else None
    terms: list[str] = []
    for field in fields:
        if wanted is not None and _field_key(field) not in wanted:
            continue
        for term in value_terms(_field_value(field)):
            if term not in terms:
                terms.append(term)
    return terms


__all__ = [
    "ABILITY_EVIDENCE_KINDS",
    "ATTRIBUTE_MAX_CHARS",
    "ATTRIBUTE_SPECS",
    "CAREER_FOCUS_KEYS",
    "CAREER_FOCUS_STATES",
    "ENTRY_TYPE_LABELS",
    "INTEREST_POLARITIES",
    "KEY_ENTRY_TYPES",
    "KEY_VALUE_LIMITS",
    "MAJOR_KEYS",
    "PURPOSE_TYPES",
    "STATUS_LABELS",
    "TERM_MAX_CHARS",
    "TYPE_MAX_ITEMS",
    "TYPE_VALUE_LIMITS",
    "VERIFICATION_LABELS",
    "allows_multiple",
    "career_focus_terms",
    "entry_type_label",
    "entry_type_of",
    "is_usable",
    "major_terms",
    "max_items",
    "normalize_attributes",
    "normalize_value",
    "records_for_purpose",
    "scope_terms",
    "validate_window",
    "value_limit",
    "value_terms",
    "verification_for",
]
