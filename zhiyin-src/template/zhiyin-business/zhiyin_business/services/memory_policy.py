"""记忆策略持久化（《个人画像设计-2026-10-20》5.2 节）。

为什么需要这一层
----------------
原有三档开关只保存“当前值”：

- 账号级 ``preferences.automatic_memory``；
- 会话级 ``conversation_settings[task].temporary``；
- 按字段键的 ``conversation_forgotten_keys``。

它们能拦住写入，却回答不了“这条限制是谁、在什么时候、按什么范围提出的”。
“这条不要记录”目前也只能按键拒绝，不能按内容拒绝；“只保存这一条”没有一次性
的显式授权记录。会话摘要压缩、换题、重启或更正信息都不能让限制失效，所以策略
必须落在账号状态里，并且每次变更都留一条带来源与时间的记录。

本服务只读写 ``biz_student_state.payload``：

- ``record_policies``：策略记录流水（id / scope / target / value / source / note /
  session_id / created_at）；
- 同时同步旧字段，既有读取方（对话运行时、API 响应）行为不变。

范围（scope）
-------------
- ``account``：账号级自动记忆开关，后续会话继承；
- ``session``：单个会话的临时策略，只影响该会话的自动写入；
- ``content``：按内容拒绝（字段键或内容指纹），不扩大成整个账号都不能记录；
- ``single``：对明确对象的一次性授权（“只保存这一条”），不恢复全局自动记忆。

前三种由本服务写入 ``record_policies``；``single`` 先作为合同里的合法范围保留，
供显式写入入口记录一次性授权，不参与“是否允许自动写”的判断 —— 手动保存某条
内容只授权该条，不代表允许恢复其他自动记录。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from zhiyin_kernel.errors import InvalidRequest

#: 策略记录允许的范围。``single`` 是“只保存这一条”的一次性授权，不恢复自动记忆。
POLICY_SCOPES: tuple[str, ...] = ("account", "session", "content", "single")

#: 策略记录在账号状态 payload 里的键。
POLICY_STATE_KEY = "record_policies"

#: 旧字段名（兼容读取方：对话运行时 / 设置接口）。
PREFERENCES_KEY = "preferences"
SETTINGS_KEY = "conversation_settings"
ACCOUNT_PREFERENCE_KEY = "automatic_memory"
SESSION_SETTING_KEY = "temporary"
FORGOTTEN_KEYS_KEY = "conversation_forgotten_keys"
#: “只保存这一条”的会话级一次性授权：single_only 保证其他自动记录不恢复，
#: single_save_keys 只允许明确点名的那几条。
SINGLE_ONLY_KEY = "single_only"
SINGLE_KEYS_KEY = "single_save_keys"

#: 每条策略记录的字段集合：有来源、有时间、可回读。
POLICY_FIELDS: tuple[str, ...] = (
    "id",
    "scope",
    "target",
    "value",
    "source",
    "note",
    "session_id",
    "created_at",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policies(state: dict) -> list[dict]:
    """取出现有的策略记录；坏数据按“没有记录”处理，不因此丢掉其他设置。"""
    raw = state.get(POLICY_STATE_KEY)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _legacy_denied_keys(state: dict) -> list[str]:
    """旧的键级拒绝字段（``conversation_forgotten_keys``）；只认字符串列表。"""
    raw = state.get(FORGOTTEN_KEYS_KEY)
    if not isinstance(raw, (list, tuple, set)):
        return []
    return [str(key) for key in raw if isinstance(key, str) and key]


def _policy_sink(state: dict) -> list[dict]:
    """取出可追加的策略记录列表；坏数据换成空列表，别在写入时抛错。"""
    raw = state.get(POLICY_STATE_KEY)
    if not isinstance(raw, list):
        raw = []
        state[POLICY_STATE_KEY] = raw
    return raw


def _mapping_slot(state: dict, key: str) -> dict:
    """取出一个字典槽位（preferences / conversation_settings）；坏数据换成空字典。"""
    value = state.get(key)
    if not isinstance(value, dict):
        value = {}
        state[key] = value
    return value


def _new_policy(
    *,
    scope: str,
    target: str,
    value: Any,
    source: str,
    note: str = "",
    session_id: str = "",
) -> dict:
    """构造一条策略记录。内部入口，不做用户可见的文案。"""
    if scope not in POLICY_SCOPES:
        raise InvalidRequest("记录范围无效。")
    return {
        "id": f"mp_{uuid4().hex[:12]}",
        "scope": scope,
        "target": target,
        "value": value,
        "source": source,
        "note": note,
        "session_id": session_id,
        "created_at": _now_iso(),
    }


def append_policy(
    state: dict,
    *,
    scope: str,
    target: str,
    value: Any,
    source: str = "user_setting",
    note: str = "",
    session_id: str = "",
) -> dict:
    """向账号状态追加一条策略记录，并同步对应的兼容字段。

    这是**纯函数式**的读改写片段：调用方把它放进 ``StudentState.update`` 的
    change 里，就与原来的设置写入处在同一个原子更新中（不会出现“记录写了、
    开关没写”的半截状态）。

    返回新记录；``state`` 本身被原地更新（与仓库里其他 change 的写法一致）。
    """
    if scope == "session" and not session_id:
        raise InvalidRequest("会话级策略需要指定会话。")
    record = _new_policy(
        scope=scope,
        target=target,
        value=value,
        source=source,
        note=note,
        session_id=session_id,
    )
    _policy_sink(state).append(record)

    if scope == "account":
        _mapping_slot(state, PREFERENCES_KEY)[ACCOUNT_PREFERENCE_KEY] = bool(value)
    elif scope == "session":
        _mapping_slot(state, SETTINGS_KEY).setdefault(session_id, {})[
            SESSION_SETTING_KEY
        ] = bool(value)
    return record


def record_account_policy(
    state: dict,
    enabled: bool,
    *,
    source: str = "user_setting",
    note: str = "",
) -> dict:
    """在保存 ``preferences`` 的同一个 change 里记一条账号级策略。

    ``services/student.py`` 用它接入，不再单独做一次 ``update``：偏好与策略记录
    要么一起写入，要么都不写。
    """
    return append_policy(
        state,
        scope="account",
        target=ACCOUNT_PREFERENCE_KEY,
        value=bool(enabled),
        source=source,
        note=note,
    )


def snapshot_from_state(state: dict, session_id: str = "") -> dict:
    """把账号状态整理成可回读的策略快照（纯函数，便于测试与复用）。"""
    policies = _policies(state)
    denied_keys = _legacy_denied_keys(state)
    # 按内容拒绝的指纹：``content`` 记录里，除去“键级拒绝”（同一字符串已在
    # conversation_forgotten_keys 里）之后的目标。键级与内容级共用一张记录表，
    # 靠旧字段区分，避免再加一个与合同字段无关的内部列。
    denied = set(denied_keys)
    content_denials: list[str] = []
    for item in policies:
        if item.get("scope") != "content":
            continue
        target = str(item.get("target") or "")
        if not target or target in denied or target in content_denials:
            continue
        content_denials.append(target)
    settings = state.get(SETTINGS_KEY, {})
    session_settings = settings.get(session_id, {}) if isinstance(settings, dict) and session_id else {}
    preferences = state.get(PREFERENCES_KEY, {})
    account_automatic = True
    if isinstance(preferences, dict):
        account_automatic = bool(preferences.get(ACCOUNT_PREFERENCE_KEY, True))
    return {
        "account_automatic": account_automatic,
        "session_temporary": bool(
            session_settings.get(SESSION_SETTING_KEY, False)
        )
        if isinstance(session_settings, dict)
        else False,
        "single_only": bool(session_settings.get(SINGLE_ONLY_KEY, False))
        if isinstance(session_settings, dict)
        else False,
        "single_keys": list(
            session_settings.get(SINGLE_KEYS_KEY, []) if isinstance(session_settings, dict) else []
        ),
        "denied_keys": denied_keys,
        "content_denials": content_denials,
        "policies": [dict(item) for item in policies],
    }


class MemoryPolicyService:
    """账号状态的记忆策略读写：持久化记录 + 兼容旧字段。"""

    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, state: Any) -> None:
        # state 是 StudentStateRepository（get / update 两个原子操作）。
        self._state = state

    async def snapshot(self, user_id: str, session_id: str = "") -> dict:
        """当前生效的策略（含历史记录），供写入入口与设置界面回读。"""
        return snapshot_from_state(await self._state.get(user_id), session_id)

    async def set_account_automatic(
        self,
        user_id: str,
        enabled: bool,
        *,
        source: str = "user_setting",
        note: str = "",
    ) -> dict:
        """账号级自动记忆开关（后续会话继承），并记录来源与时间。"""
        box: dict = {}

        def change(state: dict) -> dict:
            box["record"] = record_account_policy(
                state, bool(enabled), source=source, note=note
            )
            return state

        await self._state.update(user_id, change)
        return dict(box["record"])

    async def set_session_temporary(
        self,
        user_id: str,
        session_id: str,
        temporary: bool,
        *,
        source: str = "user_setting",
        note: str = "",
    ) -> dict:
        """会话级临时策略（只影响该会话的自动写入），并记录来源与时间。"""
        if not session_id:
            raise InvalidRequest("会话设置需要指定会话。")
        box: dict = {}

        def change(state: dict) -> dict:
            box["record"] = append_policy(
                state,
                scope="session",
                target=SESSION_SETTING_KEY,
                value=bool(temporary),
                source=source,
                note=note,
                session_id=session_id,
            )
            return state

        await self._state.update(user_id, change)
        return dict(box["record"])

    async def deny_key(
        self,
        user_id: str,
        key: str,
        *,
        source: str = "conversation",
        note: str = "",
    ) -> dict:
        """按字段键拒绝自动记录（“这条不要记录”），不扩大为所有内容都不能记。"""
        key = (key or "").strip()
        if not key:
            raise InvalidRequest("要拒绝记录的字段不能为空。")
        box: dict = {}

        def change(state: dict) -> dict:
            state[FORGOTTEN_KEYS_KEY] = sorted(
                set(_legacy_denied_keys(state)) | {key}
            )
            box["record"] = append_policy(
                state,
                scope="content",
                target=key,
                value=True,
                source=source,
                note=note,
            )
            return state

        await self._state.update(user_id, change)
        return dict(box["record"])

    async def deny_content(
        self,
        user_id: str,
        fingerprint: str,
        *,
        source: str = "conversation",
        note: str = "",
    ) -> dict:
        """按内容拒绝自动记录：同一句话及其派生提取不再自动写，其他内容不受影响。"""
        fingerprint = (fingerprint or "").strip()
        if not fingerprint:
            raise InvalidRequest("要拒绝记录的内容标识不能为空。")
        box: dict = {}

        def change(state: dict) -> dict:
            box["record"] = append_policy(
                state,
                scope="content",
                target=fingerprint,
                value=True,
                source=source,
                note=note,
            )
            return state

        await self._state.update(user_id, change)
        return dict(box["record"])

    async def grant_single(
        self,
        user_id: str,
        session_id: str,
        key: str,
        *,
        source: str = "conversation",
        note: str = "",
    ) -> dict:
        """“只保存这一条”的一次性授权：只放行点名的键，其他自动记录继续关闭。"""
        if not session_id:
            raise InvalidRequest("“只保存这一条”需要指定会话。")
        key = (key or "").strip()
        if not key:
            raise InvalidRequest("要保存的字段不能为空。")
        box: dict = {}

        def change(state: dict) -> dict:
            box["record"] = append_policy(
                state,
                scope="single",
                target=key,
                value=True,
                source=source,
                note=note,
                session_id=session_id,
            )
            slot = _mapping_slot(state, SETTINGS_KEY).setdefault(session_id, {})
            slot[SINGLE_ONLY_KEY] = True
            keys = slot.get(SINGLE_KEYS_KEY)
            if not isinstance(keys, list):
                keys = []
            if key not in keys:
                keys.append(key)
            slot[SINGLE_KEYS_KEY] = keys
            return state

        await self._state.update(user_id, change)
        return dict(box["record"])

    async def consume_single(self, user_id: str, session_id: str, key: str) -> None:
        """一次授权只用于一次写入：写成功后移除点名，其他自动记录仍保持关闭。"""
        if not session_id or not key:
            return

        def change(state: dict) -> dict:
            settings = state.get(SETTINGS_KEY)
            if not isinstance(settings, dict):
                return state
            slot = settings.get(session_id)
            if not isinstance(slot, dict):
                return state
            keys = slot.get(SINGLE_KEYS_KEY)
            if isinstance(keys, list):
                slot[SINGLE_KEYS_KEY] = [item for item in keys if item != key]
            return state

        await self._state.update(user_id, change)

    async def clear_single(self, user_id: str, session_id: str) -> None:
        """用户恢复自动记忆时清掉“只保存这一条”的会话限制。"""
        if not session_id:
            return

        def change(state: dict) -> dict:
            settings = state.get(SETTINGS_KEY)
            if isinstance(settings, dict):
                settings.pop(session_id, None)
            return state

        await self._state.update(user_id, change)

    async def check_auto_write(
        self,
        user_id: str,
        session_id: str,
        key: str,
        fingerprint: str = "",
    ) -> tuple[bool, str]:
        """自动写入前读取有效策略；返回 (是否允许, 给学生看的原因)。

        服务端在每个自动写入入口读取这一份状态，不依赖提示词或最近几条消息；
        会话摘要压缩、换题或重启都不会让拒绝记录失效。原因文案面向用户说明
        “保存范围”，不暴露内部字段名。
        """
        current = snapshot_from_state(
            await self._state.get(user_id), session_id or ""
        )
        if not current["account_automatic"]:
            return False, "你已关闭自动记忆，之后只有你明确要求时才会保存。"
        if session_id and current["session_temporary"]:
            return False, "这是临时会话，交流内容不会自动保存为长期画像。"
        key = (key or "").strip()
        if key and key in current["denied_keys"]:
            return False, "你删除过这条记忆，只有你明确要求时才会重新保存。"
        fingerprint = (fingerprint or "").strip()
        if fingerprint and fingerprint in current["content_denials"]:
            return False, "你说过这条内容不要记录，它不会被自动保存。"
        if session_id and current["single_only"] and key not in current["single_keys"]:
            return False, "你要求这次只保存明确那一条，其他内容不会自动记录。"
        return True, ""


__all__ = [
    "ACCOUNT_PREFERENCE_KEY",
    "FORGOTTEN_KEYS_KEY",
    "MemoryPolicyService",
    "PREFERENCES_KEY",
    "POLICY_FIELDS",
    "POLICY_SCOPES",
    "POLICY_STATE_KEY",
    "SESSION_SETTING_KEY",
    "SETTINGS_KEY",
    "SINGLE_KEYS_KEY",
    "SINGLE_ONLY_KEY",
    "append_policy",
    "record_account_policy",
    "snapshot_from_state",
]
