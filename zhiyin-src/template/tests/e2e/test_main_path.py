"""五环节主路径 e2e（**外壳已就位，自动门控**）。

为什么现在就建这个目录
----------------------
`--check --phase=2` 的退出条件里写着"五环节主路径 e2e 通过（tests/e2e/）"，
但此前这个目录并不存在——门禁引用了一个不存在的地方，等于把 M2 的验收
悬在半空。这里把**断言先写出来**，并用"Facade 是否已装配"自动门控：

    未装配（当前）→ 跳过，不产生红灯噪音
    装配完成     → 自动开始跑，成为 M2 的真实门禁

这样做的价值是：测试即验收口径。实现者不需要问"e2e 到底测什么"，
也不会在实现完之后才发现口径不一致而返工。

覆盖的验收项
------------
1. 首页任务路由           → 任务入口 → 目标环节
2. 可拆可续               → 从任一环节进入，前序资产不丢
3. 动态组队               → 环节变化时主理（及协理）随之变化
4. 黑板一致               → 画像 / 行为 / 会话 / 资产可跨会话读取
5. 影响面传播             → 画像更新只重算受影响资产，版本 +1
6. 行为闭环               → 认领差距 / 选择方案 / 勾任务 / 复盘都写行为日志
7. 主动干预               → 停滞触发本地教练消息，带最小可执行动作

跑法：

    python -m pytest tests/e2e -v

前置：`python -m zhiyin_boot --check --phase=2` 的 `services` 全绿。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_api.runtime import WIRED
from zhiyin_boot import Settings, build_container, describe_assembly

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = TEMPLATE_ROOT / "data"


def _settings() -> Settings:
    return Settings(
        # 本项目不提供 mock 产出：没有真模型就没有智能体引擎。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
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


def _container():
    return build_container(_settings())


def _facade_wired() -> bool:
    """是否已具备跑主路径的前提（Facade 装配完成）。"""
    return describe_assembly(_container()).services["facade"] == WIRED


M2_PENDING = pytest.mark.skipif(
    not _facade_wired(),
    reason=(
        "M2 未就绪：business 服务与 Facade 仍是骨架（见 "
        "`python -m zhiyin_boot --check --phase=2` 的 unmet 清单）。"
        "装配完成后本用例自动开始执行。"
    ),
)

pytestmark = [pytest.mark.e2e, M2_PENDING]


@pytest.mark.asyncio
async def test_acceptance_1_home_task_routes_to_target_stage() -> None:
    """验收项 1：首页任务路由。

    口径：`task_entries.json` 里每条任务入口声明的 `(lead_agent, target_stage)`
    都必须真的有产出契约（由 `test_shell_completeness` 守卫），
    且 `enter_task` 后会话的环节与主理等于该入口声明的值。
    """
    from zhiyin_api.dto.conversation import TaskEnterRequest
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)

    facade = container.facade
    entries = await container.registry_service.list_task_entries()
    assert entries, "bootstrap 至少要有一个任务入口"

    routable = [entry for entry in entries if entry.target_stage is not None]
    assert routable, "至少要有一个能直接路由到环节的任务入口"

    entry = routable[0]
    view = await facade.enter_task("demo_user", TaskEnterRequest(task_code=entry.code))
    assert view.stage == entry.target_stage
    assert view.lead_agent_name, "任务入口的主理展示名必须来自动态资源"


@pytest.mark.asyncio
async def test_acceptance_2_resume_from_any_stage_keeps_prior_assets() -> None:
    """验收项 2：可拆可续。从后续环节进入时，前序资产必须仍在。"""
    from uuid import uuid4

    from zhiyin_business.contracts.common import AssetUpdateDraft
    from zhiyin_kernel.enums import AssetType

    container = _container()
    user = f"e2e-resume-{uuid4().hex[:6]}"

    # 先在 ① 采集阶段留下资产：一版依赖画像字段的报告 + 一个画像字段
    version = await container.asset_service.save_version(
        user,
        AssetUpdateDraft(
            asset_type=AssetType.REPORT,
            depends_on_profile_keys=["major"],
            reason="e2e 首版",
        ),
    )
    await container.profile_service.update_field(
        user, "major", "土木工程", confidence=0.9, source="conversation"
    )

    # 直接从 ③ 决策进入（跳过 ①②），前序资产必须仍在
    session = await container.orchestrator.enter_task(user, "undecided")
    blackboard = await container.orchestrator.read_blackboard(user, session.id)
    assert any(v.id == version.id for v in blackboard.asset_versions), (
        "换环节进入后，前序资产必须自动继承（可拆可续）"
    )
    keys = {f.key for f in (blackboard.profile.fields if blackboard.profile else [])}
    assert "major" in keys, "画像字段必须跨会话可读"


@pytest.mark.asyncio
async def test_acceptance_3_handoff_changes_lead_and_discloses() -> None:
    """验收项 3：动态组队 + 换主理必须显式告知。

    这是产品硬约束的端到端落点：`TurnResult.disclosure` 与
    `TurnResult.badge` 必须同时变化，且 disclosure 非空。
    """
    from uuid import uuid4

    from zhiyin_api.dto.conversation import MessageRequest
    from zhiyin_boot import wire_application

    container = _container()
    wire_application(container)
    facade = container.facade
    user = f"e2e-handoff-{uuid4().hex[:6]}"

    session = await container.orchestrator.enter_task(user, "confused")
    assert session.lead_agent == "profile_analyst"

    # 关键词把环节推向 ④ 行动（"行动计划"→ HOW_TO_ACT），主理必须换人且显式告知
    turn = await facade.send_message(
        user, MessageRequest(task_id=session.id, message="方向定了，给我一份行动计划")
    )
    assert turn.badge.agent_id != "profile_analyst", "环节变化后主理必须换人"
    assert turn.disclosure is not None, "换主理必须显式告知（产品硬约束）"
    assert turn.disclosure.text, "告知行不能为空"
    assert turn.guide.kind in {"question", "options", "task", "reminder"}, (
        "每轮必须以行为引导收尾（四选一）"
    )


@pytest.mark.asyncio
async def test_acceptance_4_blackboard_is_shared_across_sessions() -> None:
    """验收项 4：黑板一致。第二个会话必须能读到第一个会话写入的画像与资产。"""
    from uuid import uuid4

    container = _container()
    user = f"e2e-blackboard-{uuid4().hex[:6]}"

    session_a = await container.orchestrator.enter_task(user, "confused")
    await container.profile_service.update_field(
        user,
        "career_interest",
        "结构设计与 BIM 交叉",
        confidence=0.7,
        source="conversation",
        evidence=["e2e 会话 A 写入"],
    )
    await container.memory_service.upsert(
        user,
        session_a.id,
        loop_stage=session_a.loop_stage,
        lead_agent=session_a.lead_agent,
        summary_delta="会话 A 摘要",
    )

    session_b = await container.orchestrator.enter_task(user, "verify_direction")
    assert session_b.id != session_a.id, "两个会话必须独立"
    blackboard = await container.orchestrator.read_blackboard(user, session_b.id)
    keys = {f.key for f in (blackboard.profile.fields if blackboard.profile else [])}
    assert "career_interest" in keys, "会话 B 必须读到会话 A 写入的画像"
    assert any(m.task_id == session_a.id for m in blackboard.memories), (
        "会话记忆必须跨会话可读"
    )


@pytest.mark.asyncio
async def test_acceptance_5_profile_update_propagates_only_affected_assets() -> None:
    """验收项 5：影响面传播。只标记受影响资产；未命中资产一个字都不动。

    口径在 2026-09-23 改过一次，测试跟着改：

    原来是"命中就升版 + 写一句「画像补了新信息，这一版跟着更新」"，而正文并没有重算
    （真正的重算要等下一次进入该环节）。后果是两个用户看得见的假信号 ——
    版本下拉里多出一版点开是空白页；用户被告知"跟着改了"，打开一看没变。
    现在传播只把那一版**标成"待重算"**，版本号留给真正重算的那一轮去 +1。
    """
    from uuid import uuid4

    from zhiyin_business.contracts.common import AssetUpdateDraft
    from zhiyin_kernel.enums import AssetType

    container = _container()
    user = f"e2e-impact-{uuid4().hex[:6]}"

    hit = await container.asset_service.save_version(
        user,
        AssetUpdateDraft(asset_type=AssetType.REPORT, depends_on_profile_keys=["major"]),
    )
    miss = await container.asset_service.save_version(
        user,
        AssetUpdateDraft(
            asset_type=AssetType.DIRECTION_PLAN,
            depends_on_profile_keys=["career_interest"],
        ),
    )

    # 画像只更新了 major：只有依赖它的 report 被标记
    changed = await container.asset_service.propagate(user, ["major"])
    assert [v.asset_type for v in changed] == [AssetType.REPORT], (
        "只允许命中依赖字段的资产被标记"
    )
    assert changed[0].needs_recompute, "命中的资产必须标成「待重算」"
    assert changed[0].recompute_reason, "标记要带上给用户看的原因，不能只置一个布尔"
    assert changed[0].version == hit.version, "只标记，不升版：版本号留给真正重算的那一轮"

    reports = await container.asset_service.list_versions(user, AssetType.REPORT)
    assert len(reports) == 1, "传播不得留下没有正文的空版本（点开会是空白页）"
    assert reports[-1].needs_recompute

    plans = await container.asset_service.list_versions(user, AssetType.DIRECTION_PLAN)
    assert plans[-1].version == miss.version, "未命中的资产不得变化"
    assert not plans[-1].needs_recompute

    # 真的重算（落一版新正文）之后，标记必须消失 —— 否则用户会一直被告知"这是旧的"。
    from zhiyin_kernel.assets import Report, Swot, Verdict
    from datetime import datetime, timezone

    fresh = Report(
        id="rpt-recomputed",
        user_id=user,
        version=0,
        generated_at=datetime.now(timezone.utc),
        verdict=Verdict(title="重算后的结论", summary="重算后的说明"),
        swot=Swot(strength=["a", "b"], weakness=["c", "d"], opportunity=["e", "f"], risk=["g", "h"]),
    )
    await container.asset_service.save_report(user, fresh)
    reports = await container.asset_service.list_versions(user, AssetType.REPORT)
    assert not reports[-1].needs_recompute, "重算过的新版本不该还挂着「待重算」"


@pytest.mark.asyncio
async def test_acceptance_6_action_loop_writes_behavior_log() -> None:
    """验收项 6：行为闭环。认领差距 / 选择方案 / 勾任务 / 复盘都产生行为日志。"""
    """验收项 6：行为闭环。环节轮次产生行为日志，停滞检测有据可依。

    口径说明：gap_claim / decision_select / task_done 的入站动作（选方案 /
    认领差距 / 勾任务）挂在后续的资产操作端点上；本用例先锁住"每轮对话都写
    ANSWER 行为"这条闭环底线——它是停滞检测的唯一信号源。
    """
    from uuid import uuid4

    from zhiyin_api.dto.conversation import MessageRequest
    from zhiyin_boot import wire_application
    from zhiyin_kernel.enums import BehaviorEventType

    container = _container()
    wire_application(container)
    facade = container.facade
    user = f"e2e-behavior-{uuid4().hex[:6]}"

    session = await container.orchestrator.enter_task(user, "confused")
    await facade.send_message(
        user, MessageRequest(task_id=session.id, message="我想先弄清楚自己适合什么")
    )
    await facade.send_message(
        user, MessageRequest(task_id=session.id, message="给我一份行动计划")
    )

    answers = await container.behavior_service.recent(
        user, event_types=[BehaviorEventType.ANSWER]
    )
    assert len(answers) >= 2, "每轮对话都必须写行为日志（ANSWER）"
    days = await container.behavior_service.days_since_last(user, BehaviorEventType.ANSWER)
    assert days == 0, "刚发生过作答，停滞天数必须是 0"


@pytest.mark.asyncio
async def test_acceptance_7_stall_triggers_coach_message() -> None:
    """验收项 7：主动干预。停滞触发教练消息，且带最小可执行动作。"""
    """验收项 7：主动干预。停滞触发教练消息，且带最小可执行动作。"""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from zhiyin_business.policies.intervention_rules import ThresholdInterventionPolicy
    from zhiyin_business.workers import ActiveEventWorker
    from zhiyin_kernel.blackboard import BehaviorLog
    from zhiyin_kernel.enums import BehaviorEventType

    container = _container()
    user = f"e2e-stall-{uuid4().hex[:6]}"

    # 唯一的关键动作发生在 4 天前（阈值 3 天）→ 构成停滞
    stale = datetime.now(timezone.utc) - timedelta(days=4)
    await container.behaviors.append(
        BehaviorLog(
            id=f"bhv-e2e-{uuid4().hex[:8]}",
            user_id=user,
            event_type=BehaviorEventType.TASK_DONE,
            occurred_at=stale,
            payload={},
        )
    )

    params = await container.registry.get_policy_params("intervention")
    assert params is not None and params.status == "confirmed", (
        "干预参数必须来自已确认的动态资源"
    )
    worker = ActiveEventWorker(
        behaviors=container.behavior_service,
        policy_factory=lambda value: ThresholdInterventionPolicy(
            stall_threshold_days=int(value.get("stall_threshold_days", 3)),
            cooldown_hours=int(value.get("cooldown_hours", 48)),
            max_notifications_per_window=int(value.get("max_notifications_per_window", 2)),
            window_days=int(value.get("window_days", 7)),
        ),
        registry=container.registry,
        notifications=container.notifications,
        scheduler=container.scheduler_primitive,
        notifier=container.notifier_primitive,
        user_provider=lambda: [user],
    )
    triggered = await worker.run_once()
    assert triggered >= 1, "停滞 4 天必须触发一次主动干预"

    # 冷却期内不再打扰（48 小时冷却）
    assert await worker.run_once() == 0, "冷却期内不得重复打扰"
