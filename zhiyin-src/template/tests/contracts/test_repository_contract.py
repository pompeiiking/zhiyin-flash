"""Repository 语义契约。

这些断言描述的是**任何实现都必须成立的行为**（本地版、未来的其它版）：

- 画像：按 key 幂等覆盖、版本递增、读取是快照；
- 行为日志：只追加、按时间倒序、可按类型取最后发生时间；
- 资产：版本单调递增、影响面只命中依赖字段、只针对最新版本；
- 会话：进行中会话可被续接、推进环节即更新主理、完成后不再算进行中；
- 记忆 / 用户 / 动态资源：读写形状与排序口径。

它们与 `tests/test_infrastructure.py` 的区别：那里的断言偏"这个实现对不对"，
这里偏"契约要求什么"，因此新增实现时会自动被覆盖。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from zhiyin_kernel.assets import ActionPhase, ActionPlan, ActionTask, DirectionPlan
from zhiyin_kernel.blackboard import (
    AssetVersion,
    BehaviorLog,
    ConversationMemory,
    ProfileField,
    TaskSession,
)
from zhiyin_kernel.enums import (
    AssetType,
    BehaviorEventType,
    LoopStage,
    PlanRole,
    ProfileSource,
    TaskStatus,
)
from zhiyin_kernel.identity import UserAccount


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _field(key: str = "major", value: object = "计算机") -> ProfileField:
    return ProfileField(
        key=key,
        value=value,
        confidence=0.9,
        source=ProfileSource.CONVERSATION,
        updated_at=_now(),
    )


async def test_profile_contract(repositories) -> None:
    repo = repositories["profiles"]()

    # upsert 按 key 幂等：同一 key 覆盖而不是追加
    await repo.upsert_field("u1", _field("major", "计算机"))
    await repo.upsert_field("u1", _field("major", "软件工程"))
    fields = await repo.list_fields("u1")
    assert len(fields) == 1
    assert fields[0].value == "软件工程"

    # 版本单调递增
    version_after_first = (await repo.get("u1")).version
    await repo.upsert_field("u1", _field("interest", "数据"))
    assert (await repo.get("u1")).version > version_after_first

    # 读取是快照：改返回值不得影响存储
    snapshot = (await repo.list_fields("u1", ["interest"]))[0]
    snapshot.value = "被改坏了"
    assert (await repo.list_fields("u1", ["interest"]))[0].value == "数据"

    # 缺口整体替换
    await repo.replace_gaps("u1", [])
    assert await repo.list_gaps("u1") == []


async def test_behavior_contract(repositories) -> None:
    repo = repositories["behaviors"]()

    for day in (10, 13, 12):
        await repo.append(
            BehaviorLog(
                id="",
                user_id="u1",
                event_type=BehaviorEventType.TASK_DONE,
                occurred_at=datetime(2026, 9, day, tzinfo=timezone.utc),
            )
        )

    logs = await repo.list_by_user("u1")
    assert [item.occurred_at.day for item in logs] == [13, 12, 10], "必须按时间倒序"

    # 只追加：不得提供任何 UPDATE 路径
    assert not hasattr(repo, "update")
    assert not hasattr(repo, "delete")

    assert await repo.last_occurred_at("u1", BehaviorEventType.TASK_DONE) == datetime(
        2026, 9, 13, tzinfo=timezone.utc
    )
    assert await repo.last_occurred_at("u1", BehaviorEventType.GAP_CLAIM) is None


def _asset(user_id: str, asset_type: AssetType, keys: list[str], version: int = 1):
    return AssetVersion(
        id="",
        user_id=user_id,
        asset_type=asset_type,
        version=version,
        created_at=_now(),
        depends_on_profile_keys=keys,
    )


async def test_asset_contract(repositories) -> None:
    repo = repositories["assets"]()

    first = await repo.save_version(_asset("u1", AssetType.REPORT, ["major"]))
    second = await repo.save_version(
        _asset("u1", AssetType.REPORT, ["major"], version=0)
    )
    assert first.version == 1
    assert second.version == 2, "版本必须单调递增，调用方传小值也不能压低"

    await repo.save_version(_asset("u1", AssetType.ACTION_PLAN, ["target_city"]))
    hit = await repo.list_affected_assets("u1", ["major"])
    assert [item.asset_type for item in hit] == [AssetType.REPORT]
    assert len(hit) == 1, "影响面只针对最新版本"
    assert await repo.list_affected_assets("u1", ["无关字段"]) == []

    # 三套方向方案：整体覆盖 + 可撤回选择
    await repo.save_direction_plans(
        "u1",
        [
            DirectionPlan(
                id="p1",
                role=PlanRole.MAIN,
                name="主攻",
                target_desc="",
                match_score=0.9,
                fit_reason="",
                main_risk="",
            ),
            DirectionPlan(
                id="p2",
                role=PlanRole.FALLBACK,
                name="保底",
                target_desc="",
                match_score=0.5,
                fit_reason="",
                main_risk="",
            ),
        ],
    )
    await repo.select_direction_plan("u1", "p1")
    assert [plan.selected for plan in await repo.list_direction_plans("u1")] == [True, False]
    await repo.select_direction_plan("u1", "p2")
    assert [plan.selected for plan in await repo.list_direction_plans("u1")] == [False, True]

    # 行动计划：勾任务
    await repo.save_action_plan(
        "u1",
        ActionPlan(
            id="ap1",
            phases=[
                ActionPhase(
                    name="阶段一",
                    date_range="9月",
                    tasks=[ActionTask(text="改简历"), ActionTask(text="投 3 家")],
                )
            ],
        ),
    )
    plan = await repo.mark_task_done("u1", "改简历")
    assert plan.phases[0].tasks[0].done is True
    assert plan.phases[0].tasks[0].done_at is not None
    with pytest.raises(LookupError):
        await repo.mark_task_done("u1", "不存在的任务")


async def test_session_contract(repositories) -> None:
    repo = repositories["sessions"]()

    created = await repo.create(
        TaskSession(
            id="s1",
            user_id="u1",
            task_code="confused",
            task_name="迷茫",
            loop_stage=LoopStage.COLLECT,
            lead_agent="profile_analyst",
            created_at=_now(),
            updated_at=_now(),
        )
    )

    # 续接：同一任务的进行中会话必须被找到
    active = await repo.find_active("u1", "confused")
    assert active is not None and active.id == created.id

    # 交接：推进环节同时切换主理
    updated = await repo.update_stage(created.id, LoopStage.DIAGNOSE, "career_advisor")
    assert updated.loop_stage is LoopStage.DIAGNOSE
    assert updated.lead_agent == "career_advisor"
    assert (await repo.get(created.id)).lead_agent == "career_advisor"

    # 完成后不再算进行中
    await repo.update_status(created.id, TaskStatus.COMPLETED)
    assert await repo.find_active("u1", "confused") is None
    assert len(await repo.list_by_user("u1", [TaskStatus.COMPLETED])) == 1


async def test_memory_contract(repositories) -> None:
    repo = repositories["memories"]()

    await repo.upsert(
        ConversationMemory(
            id="",
            user_id="u1",
            task_id="t1",
            loop_stage=LoopStage.COLLECT,
            lead_agent="profile_analyst",
            summary="第一轮",
            last_active_at=_now(),
        )
    )
    stored = await repo.get("u1", "t1")
    assert stored is not None and stored.summary == "第一轮"

    await repo.upsert(
        ConversationMemory(
            id=stored.id,
            user_id="u1",
            task_id="t1",
            loop_stage=LoopStage.DIAGNOSE,
            lead_agent="career_advisor",
            summary="第二轮",
            last_active_at=_now(),
        )
    )
    assert len(await repo.list_by_user("u1")) == 1, "同一 (user, task) 只有一条记忆"
    assert (await repo.get("u1", "t1")).lead_agent == "career_advisor"

    await repo.delete("u1", "t1")
    assert await repo.get("u1", "t1") is None


async def test_user_contract(repositories) -> None:
    repo = repositories["users"]()

    await repo.create(
        UserAccount(
            id="demo-user-0001",
            phone="DEMO-000",
            nickname="演示同学",
            created_at=_now(),
        )
    )
    assert (await repo.get_by_id("demo-user-0001")).nickname == "演示同学"
    assert (await repo.get_by_phone("DEMO-000")).id == "demo-user-0001"
    assert await repo.get_by_id("不存在") is None

    await repo.touch_last_login("demo-user-0001", _now())
    assert (await repo.get_by_id("demo-user-0001")).last_login_at is not None

    with pytest.raises(LookupError):
        await repo.touch_last_login("不存在", _now())


async def test_registry_contract(repositories) -> None:
    """动态资源：读不到不报错（空数据），读到必须按 sort_order 稳定排序。"""
    repo = repositories["registry"]()

    agents = await repo.list_agents()
    assert agents, "种子数据里必须有智能体"
    assert (await repo.get_agent(agents[0].id)) is not None
    assert await repo.get_agent("不存在的智能体") is None

    entries = await repo.list_task_entries()
    assert [entry.sort_order for entry in entries] == sorted(
        entry.sort_order for entry in entries
    )

    # 产出契约按 (agent_id, stage) 查：同一智能体的不同环节必须是两条契约。
    # 任何实现都必须按这个键建立索引，不得按契约 id 查。
    diagnose = await repo.get_output_contract("career_advisor", LoopStage.DIAGNOSE)
    decide = await repo.get_output_contract("career_advisor", LoopStage.DECIDE)
    assert diagnose is not None and decide is not None
    assert diagnose.id != decide.id
    assert await repo.get_output_contract("profile_analyst", LoopStage.REVIEW) is None

    # 规则参数：读不到返回 None（不静默造默认值），读到必须带定稿状态
    params = await repo.get_policy_params("intervention")
    assert params is not None
    assert params.status in {"draft", "confirmed"}
    assert await repo.get_policy_params("不存在的规则") is None

    # 前端页面内容：只下发 enabled、按 sort_order 升序（上下线与排序是数据语义，
    # 不允许每个调用方各写一遍——BFF 与前端都依赖这个口径）。
    for items in (
        await repo.list_menus(),
        await repo.list_routes(),
        await repo.list_banners(),
        await repo.list_trust_blocks(),
        await repo.list_faqs(),
    ):
        assert items, "每类前端动态内容都要有种子数据，否则前端只会看到空页面"
        assert [item.sort_order for item in items] == sorted(
            item.sort_order for item in items
        )
        assert all(item.status == "enabled" for item in items), "停用项不得下发"

    # 停用项：种子数据里刻意留了一条 status=disabled 的运营位，用来验证过滤真的生效
    assert all(banner.code != "prelaunch_notice" for banner in await repo.list_banners())

    # 文案包：按 key 取值、按 bundle 过滤
    bundle = await repo.get_copy_bundle("zh-CN")
    assert bundle.get("app.name"), "文案包必须能按 key 取到应用名"
    assert await repo.get_copy_bundle("en-US") == {}, "未配置的文案包返回空，由调用方决定回落"
