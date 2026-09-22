"""主动干预规则。

产品口径：不允许"系统自嗨式打扰"。是否打扰用户必须由行为日志的真实信号
决定，并受三个参数约束——停滞阈值、冷却期、打扰上限。

**这三个参数是业务规则而非实现细节**，因此：
- 参数取自动态资源（`data/registry/*.json`），
  不得写死在代码里；
- 本模块只给"该不该触发"的判定，真正的触发动作为"交接给教练 + 推一条消息"，
  由编排器与 Worker 完成。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class InterventionPolicy(ABC):
    """停滞干预判定规则。"""

    @abstractmethod
    def should_intervene(
        self,
        *,
        days_inactive: int,
        last_notified_at: datetime | None,
        notifications_in_window: int,
        now: datetime,
    ) -> bool:
        """是否允许触发一次主动干预。

        三个输入分别对应：停滞阈值（`days_inactive`）、冷却期
        （`last_notified_at`）、打扰上限（`notifications_in_window`）。
        任一不满足即返回 False，静默不打扰。
        """
