"""复盘走完 → 本轮有明确的结束边界（实测 ZY-12）。

原本：五阶段都走完了，页面上仍写着「⑤ 复盘校准 进行中」，系统继续生成微任务，
用户得自己判断什么时候可以停。

状态本来就有（`TaskStatus.COMPLETED` + `TaskSessionRepository.update_status`），
缺的只是"复盘完成时把它标上"。反过来，标不上也不该把用户这一轮弄崩 ——
他的话说完了，状态晚一点标上远好过整轮报错。
"""

from __future__ import annotations

import pytest

from zhiyin_business.services.orchestrator import DefaultOrchestrator
from zhiyin_kernel.enums import TaskStatus


class _Sessions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, TaskStatus]] = []
        self.fail = False

    async def update_status(self, session_id: str, status: TaskStatus):
        if self.fail:
            raise RuntimeError("down")
        self.calls.append((session_id, status))
        return session_id


class _Stub:
    """只带 `_sessions` 的最小载体 —— 这一条逻辑与编排器的其余部分无关。"""

    def __init__(self, sessions: _Sessions) -> None:
        self._sessions = sessions


@pytest.mark.asyncio
async def test_review_completion_marks_the_session_completed() -> None:
    sessions = _Sessions()
    await DefaultOrchestrator._complete_round(_Stub(sessions), "t1")  # type: ignore[arg-type]
    assert sessions.calls == [("t1", TaskStatus.COMPLETED)]


@pytest.mark.asyncio
async def test_missing_session_id_is_ignored() -> None:
    sessions = _Sessions()
    await DefaultOrchestrator._complete_round(_Stub(sessions), None)  # type: ignore[arg-type]
    assert sessions.calls == []


@pytest.mark.asyncio
async def test_failure_to_mark_does_not_break_the_turn() -> None:
    sessions = _Sessions()
    sessions.fail = True
    await DefaultOrchestrator._complete_round(_Stub(sessions), "t1")  # type: ignore[arg-type]
    assert sessions.calls == []
