"""编排层默认实现共用的私有辅助。

这些函数不是契约、也不对外导出：它们只服务 `impl/` 下的各原语实现。
若某个辅助函数开始被业务层需要，应先把它提升为契约或公共纯函数，
而不是让业务层 import 这里。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from zhiyin_kernel.enums import NotifyChannel
from zhiyin_orchestration.event import DomainEvent

SCHEDULE_TICK_EVENT = "__orchestration_schedule_tick__"
"""调度器在 Gateway 上注册的内部事件类型。

SchedulerGateway 只负责「到点投递一个事件」，冷却期与触发次数上限这类**策略**
属于编排层，因此真实调度任务统一投递本事件，由 GatewayScheduler 判定后再发布
业务声明的 event_type。
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_event(event_type: str, payload: dict[str, Any]) -> DomainEvent:
    """把 Gateway 上的 payload 还原成领域事件信封。

    本层发布的事件一定是完整信封；但调度器等其它生产者只投递裸 payload，
    这里统一补信封，保证订阅方拿到的一定是 DomainEvent。

    约定（与 `LocalScheduler` 对齐）：裸 payload 里若带 `occurred_at`，
    以它作为事件发生时刻并把它从业务载荷里摘掉 —— 否则冷却期、幂等窗口这类
    依赖时间语义的策略只能取"接收时刻"，在补偿与重放场景会算错。
    """
    try:
        return DomainEvent.model_validate(payload)
    except Exception:
        pass

    body = dict(payload)
    occurred_at = body.pop("occurred_at", None)
    moment = _utcnow()
    if isinstance(occurred_at, str):
        try:
            moment = datetime.fromisoformat(occurred_at)
        except ValueError:
            pass
    return DomainEvent(
        event_id=f"{event_type}:{moment.timestamp()}",
        event_type=event_type,
        occurred_at=moment,
        payload=body,
    )


def _to_channel(raw: str) -> NotifyChannel:
    try:
        return NotifyChannel(raw)
    except ValueError:
        return NotifyChannel.IN_APP


def _render_prompt(prompt_vars: dict[str, Any], blackboard: dict[str, Any]) -> str:
    """把这一轮的上下文拼成给模型看的一段话。

    两条口径：

    - **`context_text` 存在时，它就是上下文**，直接原样用；此时不再 dump 黑板快照。
      这是给"上下文已经渲染成短行文本"的调用方准备的（AI 任务的调用都是这种）——
      把同一样东西既写成短行又 dump 成 JSON，模型会看到两份说法。
    - 否则维持原样：输入变量与共享状态各一段 JSON。走这条路的只有还没改渲染的调用方。
    """
    blocks = []
    context_text = prompt_vars.get("context_text") if prompt_vars else None
    rendered = isinstance(context_text, str) and bool(context_text.strip())
    if rendered:
        blocks.append(context_text.strip())
        prompt_vars = {
            key: value for key, value in prompt_vars.items() if key != "context_text"
        }
    if prompt_vars:
        blocks.append("【输入变量】\n" + json.dumps(prompt_vars, ensure_ascii=False, indent=2))
    if blackboard and not rendered:
        blocks.append("【共享状态】\n" + json.dumps(blackboard, ensure_ascii=False, indent=2))
    return "\n\n".join(blocks)


__all__ = ["SCHEDULE_TICK_EVENT"]
