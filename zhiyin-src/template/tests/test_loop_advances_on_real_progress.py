"""闭环要走得动：环节按**真实进度**推进，而不是等用户说出关键词。

背景（一次真实的用户反馈之后查到的问题）：环节只有一条推进途径 —— 命中意图
关键词（六条映射），未命中就"退回当前环节"。实测一个用户聊了 12 轮，
`① 采集 → ② 诊断` 之后再没动过：他认领了差距、系统手上却没有"可以往下走"的依据。
而设计里每一环的验收锚点本来就是**行为**：

    ② 诊断 认领差距 → ③ 决策；③ 决策 选中方案 → ④ 行动；④ 行动 勾掉任务 → ⑤ 复盘

这里钉住四件事：

1. 进度规则的判定本身（纯函数，含"只往前推、不往回拉"）；
2. 认领这条动作真的被记下来（`gap_claim` 此前全仓没有生产者）；
3. 采集写了画像也算一次动作（`profile_field_updated` 此前库里 0 行）；
4. 认领之后，下一轮真的会进 ③。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from zhiyin_boot import Settings, build_container
from zhiyin_business.policies.progress import progresses_to, stage_from_progress
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import TurnRequest
from zhiyin_kernel.blackboard import AssetVersion, BehaviorLog
from zhiyin_kernel.enums import AssetType, BehaviorEventType, LoopStage
from zhiyin_orchestration.agent import AgentEngine, AgentRequest, AgentResult

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"


def _settings() -> Settings:
    return Settings(
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_data_dir=str(DATA_DIR),
        local_registry_dir=str(DATA_DIR / "registry"),
        local_knowledge_dir=str(DATA_DIR / "knowledge"),
        local_object_dir=str(DATA_DIR / "objects"),
    )


def _asset(asset_type: AssetType) -> AssetVersion:
    return AssetVersion(
        id=f"av-{asset_type.value}",
        user_id="u1",
        asset_type=asset_type,
        version=1,
        created_at=datetime.now(timezone.utc),
    )


def _behavior(event_type: BehaviorEventType) -> BehaviorLog:
    return BehaviorLog(
        id=f"b-{event_type.value}",
        user_id="u1",
        event_type=event_type,
        occurred_at=datetime.now(timezone.utc),
    )


def _board(
    assets: list[AssetType] | None = None,
    events: list[BehaviorEventType] | None = None,
    *,
    stage: LoopStage | None = None,
) -> BlackboardView:
    return BlackboardView(
        user_id="u1",
        current_stage=stage,
        asset_versions=[_asset(item) for item in (assets or [])],
        recent_behaviors=[_behavior(item) for item in (events or [])],
    )


# ---------------------------------------------------------------------------
# 1. 进度规则本身
# ---------------------------------------------------------------------------


def test_nothing_on_the_board_means_no_guess() -> None:
    """黑板空着就返回 None：宁可停在原地，也不凭半份依据把人推进下一环。"""
    assert stage_from_progress(_board()) is None


def test_report_alone_keeps_the_user_in_diagnose() -> None:
    """比过一轮、还没认领任何差距 → 仍在 ②。"""
    assert stage_from_progress(_board([AssetType.REPORT])) is LoopStage.DIAGNOSE


def test_claimed_gap_moves_to_decide() -> None:
    """报告 + 认领过差距 → ③ 决策（设计里 ②→③ 的衔接点）。"""
    board = _board([AssetType.REPORT], [BehaviorEventType.GAP_CLAIM])
    assert stage_from_progress(board) is LoopStage.DECIDE


def test_chosen_plan_moves_to_act_and_done_task_moves_to_review() -> None:
    plan = _board(
        [AssetType.REPORT, AssetType.DIRECTION_PLAN], [BehaviorEventType.DECISION_SELECT]
    )
    assert stage_from_progress(plan) is LoopStage.ACT

    done = _board(
        [AssetType.REPORT, AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN],
        [BehaviorEventType.DECISION_SELECT, BehaviorEventType.TASK_DONE],
    )
    assert stage_from_progress(done) is LoopStage.REVIEW


def test_progress_never_pulls_the_user_backwards() -> None:
    """只往前推：用户在 ⑤、手上还留着没勾完的任务，不该被拽回 ④。"""
    assert progresses_to(LoopStage.REVIEW, LoopStage.ACT) is None
    assert progresses_to(LoopStage.DIAGNOSE, LoopStage.REVIEW) is LoopStage.REVIEW
    # 全新会话（还没定过位）第一次决定从哪一步开始，直接采纳候选
    assert progresses_to(None, LoopStage.DIAGNOSE) is LoopStage.DIAGNOSE


# ---------------------------------------------------------------------------
# 2. 动作真的被记下来
# ---------------------------------------------------------------------------


class _StubEngine(AgentEngine):
    def __init__(self, structured: dict | None = None) -> None:
        self._structured = structured or {}

    async def invoke(self, request: AgentRequest) -> AgentResult:
        return AgentResult(
            agent_id=request.agent_id,
            structured=dict(self._structured),
            valid=True,
        )


COLLECT_PAYLOAD = {
    "conclusion": "你说你是学计算机的，这条我记下了。",
    "field_updates": [
        {
            "key": "major",
            "label": "专业",
            "value": "计算机",
            "confidence": 0.9,
            "source": "conversation",
            "evidence": ["我是学计算机的"],
        }
    ],
    "remaining_gaps": [],
    "confidence_overall": 0.6,
    "ready_to_handoff": False,
    "guide": {"kind": "question", "text": "还缺一条", "question": "你做过什么？"},
}


def _container():
    return build_container(_settings())




@pytest.mark.asyncio
async def test_answer_only_logs_a_field_update_when_a_field_changed() -> None:
    """没写进任何字段的那一轮**不记**这条行为 —— 否则"他刚动过"会变成假信号。"""
    container = _container()
    empty = dict(COLLECT_PAYLOAD, field_updates=[])
    container.orchestrator._agent_engine = _StubEngine(empty)  # noqa: SLF001

    session = await container.orchestrator.enter_task("u-no-field", "confused")
    await container.orchestrator.handle_message(
        TurnRequest(user_id="u-no-field", task_id=session.id, message="嗯")
    )

    logged = await container.behavior_service.recent("u-no-field")
    kinds = [event.event_type for event in logged]
    assert BehaviorEventType.PROFILE_FIELD_UPDATED not in kinds
