"""业务领域事件契约。

规则（并行开发规则）：
- 跨模块通信只使用领域事件，不互相调用对方的私有 Service。
- 事件类型字符串在此集中定义，禁止在业务代码里散写魔法字符串。

**只保留真有生产者与消费者的那几条。** 声明了却没有订阅方的领域事件不是"预留"，
而是误导：接手的人会以为链路已经存在，去订阅一个永远不会到达的事件。
新增事件时同时给出生产点与订阅点，再把它加进来。
"""

from __future__ import annotations

# ---------- 事件类型常量 ----------

PROFILE_FIELD_UPDATED = "profile_field_updated"
"""画像字段更新。订阅方：资产服务（影响面传播）。"""

ASSET_VERSION_CHANGED = "asset_version_changed"
"""资产版本变化。订阅方：工作台刷新、通知。"""

BEHAVIOR_LOGGED = "behavior_logged"
"""行为写入。订阅方：成就体系、复盘停滞检测。"""
