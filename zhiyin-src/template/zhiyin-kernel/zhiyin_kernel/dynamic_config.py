"""动态配置快照：进程内**唯一**一份可热重载的配置。

为什么要收成一份快照
--------------------
之前每个消费点各自读库、各自缓存：环节名在 api 的 mapper 里读，采集规则在
工作台和 AI 任务里各读一次。于是"重载配置"这件事根本没有落点 ——
要么挨个通知（漏一个就是一个诡异的 bug：改完配置有的模块生效有的没生效），
要么等重启。

统一成：**启动时读一次 → 存进这份快照 → 所有消费点都读快照；
`reload()` 重新读一遍、原地替换。**

这么设计还顺带定死了一件事：配置的生效时机是**可控的时刻**，
不是"下一次请求"。实时读库听起来更灵活，实际会让"刚才还好的行为突然变了"
变得难以解释 —— 排查问题的人不会想到是有人在改配置。

份量很轻：只放"读一次就够、改了要全局一致"的东西。
用户数据（画像、会话、资产）不在这里，它们是活的。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from zhiyin_kernel.registry import (
    CachePolicy,
    CollectionRuleSpec,
    LayoutPolicy,
    ProfileFieldSpec,
    StageSpec,
    UserSignalSpec,
)


@dataclass(frozen=True)
class DynamicConfigSnapshot:
    """一份动态配置。字段为空表示"这一类还没读到"，不是"配置为空"。"""

    stages: tuple[StageSpec, ...] = ()
    layout: Optional[LayoutPolicy] = None
    collection_rules: tuple[CollectionRuleSpec, ...] = ()
    """用户信号：用户自己写下的话里，哪些词让哪个画像字段变成前提"""
    user_signals: tuple[UserSignalSpec, ...] = ()
    #: 读缓存策略：哪片 TTL 多长、什么事件让它失效（改它不发版）
    cache: Optional[CachePolicy] = None
    #: 画像字段词表（键 + 中文名）：写侧按它做门禁，界面按它取名字
    profile_fields: tuple[ProfileFieldSpec, ...] = ()

    #: 上一次装载的时间与来源，用于界面上回答"这份配置是什么时候的"
    loaded_at: str = ""
    source: str = ""


_current: DynamicConfigSnapshot = DynamicConfigSnapshot()


def snapshot() -> DynamicConfigSnapshot:
    """当前生效的那一份。所有读侧都走这里，不要各自去读库。"""
    return _current


def configure(snapshot_: DynamicConfigSnapshot) -> None:
    """替换快照。只在**启动**与**重载**两个时刻调用。"""
    global _current
    _current = snapshot_


__all__ = ["DynamicConfigSnapshot", "configure", "snapshot"]
