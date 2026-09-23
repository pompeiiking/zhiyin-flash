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
async def test_writing_profile_fields_counts_as_an_action() -> None:
    """① 采集真的写了画像 → 记一条 `profile_field_updated`。

    这条事件类型一直躺在停滞判定"什么算动作"的清单里，而库里从来没有过一行：
    一个只补画像、不勾任务的人，会被停滞判定当成"好几天没动"。
    """
    container = _container()
    container.orchestrator._agent_engine = _StubEngine(COLLECT_PAYLOAD)  # noqa: SLF001

    session = await container.orchestrator.enter_task("u-collect-log", "confused")
    await container.orchestrator.handle_message(
        TurnRequest(user_id="u-collect-log", task_id=session.id, message="我是学计算机的")
    )

    logged = await container.behavior_service.recent("u-collect-log")
    kinds = [event.event_type for event in logged]
    assert BehaviorEventType.PROFILE_FIELD_UPDATED in kinds, (
        "采集落库了画像却没记行为：干预判定看不见这次动作"
    )


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


@pytest.mark.asyncio
async def test_claiming_a_gap_is_recorded_and_moves_the_loop_forward() -> None:
    """② 点了认领差距的选项 → 记 `gap_claim`，而且**下一轮真的进 ③**。

    这是整条闭环能否走动的关键一步：此前 `gap_claim` 只有枚举和算式，
    没有任何地方写它，于是"认领差距 → 决策"永远触发不了。
    """
    container = _container()
    engine = _StubEngine(COLLECT_PAYLOAD)
    container.orchestrator._agent_engine = engine  # noqa: SLF001
    user = "u-claim"

    # 先造出"② 已经产出过报告"这个前提（报告在手才会被认领推动）
    from zhiyin_kernel.assets import Report, Swot, Verdict

    await container.asset_service.save_report(
        user,
        Report(
            id="rpt-1",
            user_id=user,
            version=0,
            generated_at=datetime.now(timezone.utc),
            verdict=Verdict(title="差在材料", summary="先补一份能打开的文件"),
            swot=Swot(strength=["a", "b"], weakness=["c", "d"], opportunity=["e", "f"], risk=["g", "h"]),
        ),
        depends_on_profile_keys=["major"],
    )
    session = await container.orchestrator.enter_task(user, "confused")

    # 用户点了"我先去抄 3 条岗位职责"这个认领选项
    await container.orchestrator.handle_message(
        TurnRequest(
            user_id=user,
            task_id=session.id,
            message="我先去抄 3 条岗位职责",
            option_id="gap_jd",
        )
    )
    logged = await container.behavior_service.recent(user)
    claims = [e for e in logged if e.event_type is BehaviorEventType.GAP_CLAIM]
    assert claims, "认领了差距却没有留下行为记录"
    assert claims[0].payload.get("gap_id") == "gap_jd"
    assert claims[0].payload.get("label") == "我先去抄 3 条岗位职责", (
        "只记 id 的话，报告与复盘里只剩一串没人看得懂的标识"
    )

    # 下一轮：关键词没命中，但进度说"该做选择了"
    result = await container.orchestrator.handle_message(
        TurnRequest(user_id=user, task_id=session.id, message="那接下来呢")
    )
    assert result.stage is LoopStage.DECIDE, (
        "认领了差距却还在原地：闭环又回到「只能靠关键词推进」了"
    )
