"""两处闭环缝口：用户能回到①，新字段也能让旧结论过期。

这两条都是**深度端到端跑出来的真缺口**（见 CHANGELOG 三十六节），不是推测：

1. 采集门槛过了之后，落到采集的意图被门禁直接顶回诊断 —— 用户**回不到①**。
   实测：他说"家里希望我找个稳定的方向"，这句话只进了诊断的上下文，
   画像里一个字都没落下（诊断契约里没有字段更新），采集清单还挂着"还差 N 条"。
2. 影响面的依赖清单是资产**生成那一刻**的画像快照，所以**新出现**的字段
   （实测：报告生成后才导入的课表）改了也不会让旧结论过期。

这里把两条都钉住：前者钉"明确意图不被顶掉、且真的写进画像"，后者钉"新字段让三本资产都标脏"。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_boot import Settings, build_container
from zhiyin_boot.container import wire_application
from zhiyin_business.policies.routing_rules import RuleStagePolicy
from zhiyin_business.ports.blackboard import BlackboardView
from zhiyin_business.ports.orchestrator import IntentType, TurnRequest
from zhiyin_kernel.blackboard import AssetVersion
from zhiyin_kernel.enums import AssetType, LoopStage
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


# ---------------------------------------------------------------------------
# 1. 环节判定的"来源"必须能被调用方看见
# ---------------------------------------------------------------------------


async def _policy() -> RuleStagePolicy:
    from zhiyin_infrastructure.local.repository import LocalJsonRegistryRepository

    return RuleStagePolicy(LocalJsonRegistryRepository(str(DATA_DIR / "registry")))


@pytest.mark.asyncio
async def test_stage_decision_records_where_it_came_from() -> None:
    """三种来源要分得开：用户明说的（intent）/ 按进度推的（progress）/ 留在原地（fallback）。

    分不开的代价实测过一次：采集门槛无法区分"用户主动说要重新了解自己"与
    "这一轮谁都没命中"，于是把前一种也顶走了。**调用方要靠这个字段做决定**，
    所以它不能靠 confidence 数值去猜。
    """
    policy = await _policy()

    explicit = await policy.decide(
        blackboard=BlackboardView(user_id="u", current_stage=LoopStage.DIAGNOSE),
        intent=IntentType.CONFUSED,
        message="我不知道自己适合什么",
    )
    assert explicit.stage is LoopStage.COLLECT
    assert explicit.source == "intent"

    fallback = await policy.decide(
        blackboard=BlackboardView(user_id="u", current_stage=LoopStage.DIAGNOSE),
        intent=IntentType.FREE_CHAT,
        message="嗯",
    )
    assert fallback.stage is LoopStage.DIAGNOSE
    assert fallback.source == "fallback"


# ---------------------------------------------------------------------------
# 2. 用户明说"想重新了解自己"时，不该被门槛顶走，而且那句话要进画像
# ---------------------------------------------------------------------------


COLLECT_PAYLOAD = {
    "conclusion": "家里希望你求稳，你自己也没那么排斥——这条我先记下了。",
    "field_updates": [
        {
            "key": "constraints",
            "label": "现实约束",
            "value": "家里希望求稳",
            "confidence": 0.8,
            "source": "conversation",
            "evidence": ["家里希望我找个稳定的方向"],
        }
    ],
    "remaining_gaps": [],
    "confidence_overall": 0.8,
    "ready_to_handoff": True,
    "guide": {"kind": "question", "text": "还想补一句吗", "question": "还有别的情况吗？"},
}


class _StubEngine(AgentEngine):
    def __init__(self, structured: dict) -> None:
        self._structured = structured
        self.stages: list[str] = []

    async def invoke(self, request: AgentRequest) -> AgentResult:
        self.stages.append(request.stage)
        return AgentResult(
            agent_id=request.agent_id, structured=dict(self._structured), valid=True
        )


@pytest.mark.asyncio
async def test_saying_i_am_lost_goes_back_to_collect_and_lands_in_the_profile() -> None:
    """门槛早就过了，用户仍能回到①，而且他说的那句真的写进画像。"""
    container = build_container(_settings())
    engine = _StubEngine(COLLECT_PAYLOAD)
    container.orchestrator._agent_engine = engine  # noqa: SLF001
    user = "u-back-to-collect"

    # 先让画像满足采集门槛（关键字段覆盖 + 把握都过线）
    for key, label, value in (
        ("major", "专业", "计算机"),
        ("interest", "兴趣方向", "跟人打交道"),
        ("target_direction", "目标方向", "互联网"),
        ("expected_graduation", "预计毕业", "2028-06"),
    ):
        await container.profile_service.update_field(
            user, key, value, confidence=0.9, source="conversation", label=label
        )
    gate = await container.orchestrator.collection_gate(user)
    assert gate.ready, f"这条用例要的是「门槛已过」的前提：{gate.line}"

    session = await container.orchestrator.enter_task(user, "free_chat")
    result = await container.orchestrator.handle_message(
        TurnRequest(
            user_id=user,
            task_id=session.id,
            message="我有点迷茫，不知道自己适合什么，家里希望我求稳。",
        )
    )

    assert result.stage is LoopStage.COLLECT, (
        "用户明确说要重新了解自己，却还是被门槛顶去了诊断"
    )
    assert engine.stages[-1] == "collect", "这一轮该由①的人来接"
    fields = {item.key for item in await container.profile_service.get_fields(user)}
    assert "constraints" in fields, (
        "他这一轮补充的情况没进画像 —— 这正是「回不到①」的真实代价"
    )


# ---------------------------------------------------------------------------
# 3. 新出现的字段，也要让已有结论过期
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_brand_new_field_marks_every_asset_stale() -> None:
    """画像里冒出一整类新信息（例：刚导入的课表）→ 三本资产都该标成"待重算"。

    旧行为：只有"变更字段 ∩ 资产声明的依赖字段"非空才算命中，而新字段不可能出现在
    生成时那份快照里 —— 于是新信息对已有结论完全不可见（实测过）。
    """
    container = build_container(_settings())
    wire_application(container)  # 让影响面 Worker 订阅上事件
    user = "u-new-field"

    for asset_type in (AssetType.REPORT, AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN):
        await container.asset_service.save_version(
            user,
            __import__(
                "zhiyin_business.contracts.common", fromlist=["AssetUpdateDraft"]
            ).AssetUpdateDraft(
                asset_type=asset_type,
                depends_on_profile_keys=["major"],  # 生成时的画像里只有这一条
            ),
        )

    # 画像里出现一个全新的字段（真实路径：教务导入写 courses）
    await container.profile_service.update_field(
        user, "courses", "课表：4 门课", confidence=1.0, source="record", label="课程表"
    )

    workers = {getattr(worker, "name", ""): worker for worker in container.workers}
    impact = workers.get("impact")
    assert impact is not None, "影响面 Worker 没装配上"
    await impact.run_once()

    marked = []
    for asset_type in (AssetType.REPORT, AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN):
        latest: AssetVersion | None = await container.asset_service.get_latest_version(
            user, asset_type
        )
        if latest is not None and latest.needs_recompute:
            marked.append(asset_type.value)
    assert sorted(marked) == ["action_plan", "direction_plan", "report"], (
        f"新字段没有让三本资产全部过期，只标了 {marked}"
    )

    # 只打标、不升版：三本资产各自还是一版（旧行为会凭空 +1 且正文为空）
    for asset_type in (AssetType.REPORT, AssetType.DIRECTION_PLAN, AssetType.ACTION_PLAN):
        versions = await container.asset_service.list_versions(user, asset_type)
        assert len(versions) == 1, f"{asset_type.value} 被凭空升版了"


# ---------------------------------------------------------------------------
# 4. 手上有数据，就不能因为别处不合格式把它丢掉
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fields_survive_an_otherwise_broken_turn() -> None:
    """整份产出不合契约、但字段能解析 → **仍然落库**。

    口径（用户定的）：这一环的硬指标只有"他说的话有没有被记下来"，
    其余是舒适体验。以前是"缺一个必填字段整轮作废"，于是模型偶尔漏一次，
    用户刚说的那几句就白说了，采集清单还挂着"还差 N 条" —— 而那条正是他刚答的。
    现在能解析的字段照落，解析不了的那条跳过并留日志。
    """
    container = build_container(_settings())
    user = "u-salvage"
    structured = {
        # 没有 conclusion / remaining_gaps / guide：整份 CollectOutput 校验不过
        "field_updates": [
            {
                "key": "major",
                "label": "专业",
                "value": "计算机",
                "confidence": 0.9,
                "source": "conversation",
                "evidence": ["我是学计算机的"],
            },
            {"key": "broken", "label": "坏的", "value": 1},  # 缺 confidence/source
        ]
    }

    await container.orchestrator._apply_collect(user, structured)  # noqa: SLF001

    fields = {item.key for item in await container.profile_service.get_fields(user)}
    assert fields == {"major"}, f"能解析的那条没落库：{fields}"
