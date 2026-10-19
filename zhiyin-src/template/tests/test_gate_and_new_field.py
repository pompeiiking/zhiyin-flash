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
from zhiyin_kernel.blackboard import AssetVersion
from zhiyin_kernel.enums import AssetType
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
            "evidence": ["家里希望我求稳"],
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
