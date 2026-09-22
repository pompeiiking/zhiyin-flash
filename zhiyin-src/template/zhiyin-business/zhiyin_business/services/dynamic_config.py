"""装载动态配置快照：启动一次，之后只在收到重载指令时再跑。

放在业务层是因为它要用 `RegistryService`（业务 Port）——
api 与 boot 都够得着业务层，所以两边都能触发装载，而读侧只认快照。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from zhiyin_business.ports.registry import RegistryService
from zhiyin_kernel.dynamic_config import DynamicConfigSnapshot, configure
from zhiyin_kernel.registry import ProfileFieldSpec

logger = logging.getLogger(__name__)


async def load_snapshot(registry: RegistryService) -> DynamicConfigSnapshot:
    """从动态资源读一整套配置，替换进程内的快照，并返回它。

    某一类读失败**不影响其它类**：配置是好几份独立的表，
    因为一份读不到就让整屏没名字，是把风险绑在了一起。
    读不到的保持空，下一类照常装 —— 空会被界面暴露出来（标题为空等）。
    """
    stages = await _guard(registry.list_stages, "环节口径")
    layout = await _guard(registry.get_layout_policy, "气泡编排策略")
    rules = await _guard(registry.list_collection_rules, "采集规则")
    signals = await _guard(registry.list_user_signals, "用户信号")
    cache = await _guard(registry.get_cache_policy, "读缓存策略")
    copies = await _guard(registry.get_copy_bundle, "文案包（含画像字段词表）")

    snapshot = DynamicConfigSnapshot(
        stages=tuple(stages or ()),
        layout=layout,
        collection_rules=tuple(rules or ()),
        user_signals=tuple(signals or ()),
        cache=cache,
        profile_fields=tuple(_profile_fields(copies or {})),
        loaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source="biz_registry_item",
    )
    configure(snapshot)
    logger.info(
        "动态配置已装载：环节 %d · 气泡 %d · 采集规则 %d · 用户信号 %d（%s）",
        len(snapshot.stages),
        len(snapshot.layout.blocks) if snapshot.layout else 0,
        len(snapshot.collection_rules),
        len(snapshot.user_signals),
        snapshot.loaded_at,
    )
    return snapshot


#: 文案包里画像字段词表的前缀（`profile.field.<键>` → 中文名）
PROFILE_FIELD_PREFIX = "profile.field."
#: 同义词前缀（`profile.alias.<模型写的键>` → 词表里的规范键）
PROFILE_ALIAS_PREFIX = "profile.alias."


def _profile_fields(copies: dict[str, str]) -> list[ProfileFieldSpec]:
    """从文案包里挑出画像字段词表。

    词表与中文名**同源**：一份数据两处用（写侧门禁 + 界面取名）。
    分开维护的话，迟早出现"词表里有、界面上却是一串英文"。

    同义词（`profile.alias.*`）一并收进来：模型写出来的键五花八门
    （`grade` / `internship` / `interest_direction`…），它们不该各占一格画像，
    而是归到规范键上 —— 否则同一个意思在画像里会出现三条。
    """
    return [
        ProfileFieldSpec(key=code[len(PROFILE_FIELD_PREFIX) :], label=text)
        for code, text in copies.items()
        if code.startswith(PROFILE_FIELD_PREFIX)
    ] + [
        ProfileFieldSpec(
            key=code[len(PROFILE_ALIAS_PREFIX) :],
            label=text,
            alias_of=text.strip(),
        )
        for code, text in copies.items()
        if code.startswith(PROFILE_ALIAS_PREFIX)
    ]


async def _guard(loader, what: str):
    try:
        return await loader()
    except Exception:
        logger.exception("装载「%s」失败，这一类保持为空", what)
        return None


__all__ = ["load_snapshot"]
