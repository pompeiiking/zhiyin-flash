"""外部取数：编排层原语 + 基础设施适配器 + 业务层调用方。

锁住一条依赖方向（这是"取数属于数据层基本操作"的机械保证）：

    业务层 → 编排层 `ExternalDataSource.fetch(DataSourceRequest)`
                                  ↑ 装配层注入
    基础设施层 `DataSourceGateway` 实现（学职平台 / 未来的其它数据源）

因此业务代码里不允许出现任何数据源适配器的名字：换数据源只改装配表一行。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from zhiyin_data_sdk.gateways.datasource import (
    DataSourceGateway,
    DataSourceRecord,
    DataSourceRequest,
    DataSourceResult,
)
from zhiyin_orchestration import (
    AgentEngine,
    AgentRequest,
    AgentResult,
    GatewayDataSource,
)

from zhiyin_boot import Settings, build_container
from zhiyin_boot.container import Container
from zhiyin_infrastructure.xuezhi import XueZhiDataSourceGateway

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
USER_ID = "u-xuezhi"


@pytest.fixture
def container() -> Container:
    return build_container(
        Settings(
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
    )


class _StubGateway(DataSourceGateway):
    """数据源桩：只记录请求，不发网络。"""

    def __init__(self, result: DataSourceResult) -> None:
        self._result = result
        self.requests: list[DataSourceRequest] = []

    async def fetch(self, request: DataSourceRequest) -> DataSourceResult:
        self.requests.append(request)
        return self._result


class _RecordingEngine(AgentEngine):
    """智能体引擎桩：记录下发的提示词变量，不做模型调用。"""

    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def invoke(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.agent_id,
            structured={},
            raw_text="已按当前环节完成分析。",
            valid=True,
        )


def _result() -> DataSourceResult:
    return DataSourceResult(
        source="xuezhi",
        records=[
            DataSourceRecord(
                id="S1",
                kind="speciality",
                title="土木工程",
                text="培养目标：面向工程建设一线的复合型人才。",
                source_url="https://xz.chsi.com.cn/speciality/detail.action?specId=S1",
            )
        ],
    )


# --------------------------------------------------------------------------
# 编排层原语：取数是一个可替换的数据层操作
# --------------------------------------------------------------------------


async def test_gateway_datasource_delegates_and_preserves_request() -> None:
    """原语不做业务判断：请求原样交给 Gateway，结果原样返回。"""
    gateway = _StubGateway(_result())
    data_sources = GatewayDataSource(gateway)

    request = DataSourceRequest(
        source="xuezhi",
        query="结构设计行不行",
        limit=3,
        context={"fields": [{"key": "major", "value": "土木工程"}]},
    )
    result = await data_sources.fetch(request)

    assert gateway.requests == [request]
    assert result.records[0].title == "土木工程"
    assert result.degraded is False


async def test_data_sources_primitives_are_wired(container: Container) -> None:
    """装配层必须把取数原语接上，且它认识的是 Gateway 而不是某个业务适配器。"""
    assert container.data_sources is not None
    assert isinstance(container.data_sources, GatewayDataSource)
    assert isinstance(container.external_data, DataSourceGateway)


# --------------------------------------------------------------------------
# 业务层调用方：只调原语，外部数据进提示词
# --------------------------------------------------------------------------






def test_intel_topic_is_pushed_from_the_profile() -> None:
    """外部情报的主题从画像推，不从用户那句话里猜。

    三条口径，缺一条界面上就会出现"面板里一批、对话里引的是另一批"：

      1. 有专业 → 用专业（这是检索词里最准的一个）；
      2. 多值字段 → 取第一项（不把几个领域拼在一起，越拼越不挨着）；
      3. 一条都认不出 → **空串**，而不是拿"最近很焦虑"当检索词去搜。
    """
    from zhiyin_business.policies import intel_topic

    assert intel_topic(None) == ""
    assert intel_topic([{"key": "state", "value": "最近很焦虑"}]) == ""
    assert (
        intel_topic(
            [
                {"key": "state", "value": "很焦虑"},
                {"key": "major", "label": "专业", "value": "计算机科学与技术"},
            ]
        )
        == "计算机科学与技术"
    )
    # 方向在专业之后：专业优先
    assert (
        intel_topic(
            [
                {"key": "direction", "label": "方向", "value": ["会计学", "金融"]},
            ]
        )
        == "会计学"
    )


class _StubFunctions:
    """功能块服务桩：只记录情报取数请求，不发网络。

    `allow_fetch=False`（只读缓存那一档）时返回空表，模拟"缓存里没有" ——
    真实实现里这一档是不打站点的，用户该看到的是"这一轮没有外部事实"，
    而不是等几秒换来一批他这一轮用不上的东西。
    """

    def __init__(self, items: list[Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._items = items or []

    async def fetch_external_intel(
        self,
        user_id: str | None = None,
        *,
        topic: str = "",
        limit: int = 12,
        refresh: bool = False,
        allow_fetch: bool = True,
    ):
        self.calls.append(
            {
                "user_id": user_id or "",
                "topic": topic,
                "limit": limit,
                "allow_fetch": allow_fetch,
            }
        )
        if not allow_fetch:
            return []
        return list(self._items)

    def drop_intel_cache(self, user_id: str) -> None:  # pragma: no cover - 桩
        return None








# --------------------------------------------------------------------------
# 基础设施适配器：按画像上下文取数，失败如实降级
# --------------------------------------------------------------------------


async def test_intel_topic_follows_the_profile_and_cache_lets_go(
    container: Container,
) -> None:
    """画像决定主题；画像变了，缓存必须让路 —— 这两条是"越用越准"的正循环。

    实测到的两个坑，一并钉住：

    · **主题空着不该乱猜**：没给 topic 时原来直接把空串发下去，
      通用网络检索那一半因此整条不跑（它要求有检索词），而且画像明明有专业；
    · **缓存清不掉**：缓存键是 `f"{user}|{topic}"`，而 `drop_intel_cache`
      写的是 `pop(user_id)` —— 那个键根本不存在。于是补了专业之后，
      9 分钟内看到的还是按旧主题取回的那一批，症状是"我填了专业，情报还是不对"。
    """
    from zhiyin_business.services.function import DefaultFunctionService

    await container.profile_service.update_field(
        USER_ID, "major", "土木工程", confidence=0.9, source="conversation"
    )
    gateway = _StubGateway(_result())
    service = DefaultFunctionService(
        assets=container.asset_service,
        behaviors=container.behavior_service,
        object_store=container.object_store,
        calendar=container.calendar,
        track_events=container.track_events,
        notifications=container.notifications,
        registry=container.registry_service,
        profiles=container.profile_service,
        data_sources=gateway,
        notifier=None,  # 这条用例只关心取数：不推通知
    )

    # ① 不给主题 → 主题从画像推出来，下发到适配器
    items = await service.fetch_external_intel(USER_ID, limit=8)
    assert gateway.requests[0].query == "土木工程"
    assert gateway.requests[0].context["topic"] == "土木工程"
    assert items and items[0].title == "土木工程"

    # ② 再读一次命中缓存（同一个主题不该重复打外部站点）
    await service.fetch_external_intel(USER_ID, limit=8)
    assert len(gateway.requests) == 1, "同一主题第二次读必须走缓存"

    # ③ 画像变了 → 缓存让路 → 按新主题重新取
    await container.profile_service.update_field(
        USER_ID, "major", "会计学", confidence=0.9, source="conversation"
    )
    service.drop_intel_cache(USER_ID)
    await service.fetch_external_intel(USER_ID, limit=8)
    assert len(gateway.requests) == 2, "画像变了之后必须重新取，而不是拿旧主题那一批"
    assert gateway.requests[-1].query == "会计学"


class _StubXueZhiClient:
    """学职平台客户端桩：形状与真实客户端一致，返回精简的真实字段名。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    @property
    def base_url(self) -> str:
        return "https://xz.chsi.com.cn"

    async def list_specialities(self, *, name: str = "", start: int = 0):
        self.calls.append(("speciality", name))
        return {"data": {"pageArray": [{"specId": "S1", "zymc": name or "土木工程"}]}}

    async def get_speciality_detail(self, spec_id: str):
        return {
            "basicVo": {"zymc": "土木工程", "desc": "<p>培养工程建设人才</p>"},
            "byfzVo": {
                "byfzCyfxList": ["建筑业"],
                "expOccList": {
                    "土木/土建/结构工程师": {
                        "specOccProportion": "17",
                        "zhiyId": "O1",
                    },
                    "考研": {"specOccProportion": "30"},
                },
            },
        }

    async def search_occupations(self, *, name: str = "", start: int = 0):
        self.calls.append(("occupation", name))
        return {"data": {"zhiyArray": [{"zhiyId": "O1", "title": "结构工程师"}]}}

    async def get_occupation_detail(self, occ_id: str):
        return {"zhiyId": occ_id, "zhiyname": "结构工程师", "occDesc": "负责结构设计"}

    async def search_occupation_cases(self, *, name: str = "", start: int = 0):
        self.calls.append(("case", name))
        return {
            "data": {
                "list": [
                    {
                        "caseId": "C1",
                        "caseDesc": "从土木到结构设计人",
                        "caseCardDesc": "<p>王同学，结构工程硕士</p>",
                        "industryName": "建筑/工程/房地产服务",
                    }
                ]
            }
        }


async def test_xuezhi_gateway_maps_profile_context_to_records() -> None:
    """适配器把画像上下文翻成检索词，并把详情整理成统一记录形状。

    职业来自平台自带的"专业 → 对口职业"映射，而不是拿专业名去模糊搜职业
    （后者会把"结构工程师"搜成"游戏开发工程师"）。
    """
    client = _StubXueZhiClient()
    gateway = XueZhiDataSourceGateway(client)

    result = await gateway.fetch(
        DataSourceRequest(
            source="xuezhi",
            query="这个方向到底行不行",
            limit=8,
            context={
                "fields": [
                    {"key": "major", "value": "土木工程"},
                    {"key": "skills", "value": ["CAD", "Revit"]},
                ]
            },
        )
    )

    assert result.degraded is False
    assert [record.kind for record in result.records] == [
        "speciality",
        "occupation",
        "career_case",
    ]
    # 画像是检索词的第一来源；原始提问不会当作结构化检索词
    assert client.calls[0] == ("speciality", "土木工程")
    assert ("occupation", "这个方向到底行不行") not in client.calls
    assert all(record.source_url for record in result.records)
    assert "对口职业" in result.records[0].text
    # 案例详情需要登录，因此正文用搜索条目的公开摘要
    assert result.records[-1].title == "从土木到结构设计人"
    assert "结构工程硕士" in result.records[-1].text


async def test_xuezhi_gateway_reports_unknown_source_and_failures() -> None:
    """未知来源与取数异常都必须如实降级，不允许静默返回空结果。"""
    gateway = XueZhiDataSourceGateway(_StubXueZhiClient())

    unknown = await gateway.fetch(DataSourceRequest(source="unknown"))
    assert unknown.degraded is True
    assert unknown.errors and "unknown" in unknown.errors[0]

    broken = await gateway.fetch(DataSourceRequest(source="xuezhi"))
    assert broken.records == [] and broken.degraded is False

    class _BrokenClient(_StubXueZhiClient):
        async def list_specialities(self, *, name: str = "", start: int = 0):
            raise RuntimeError("学职平台不可达")

    failed = await XueZhiDataSourceGateway(_BrokenClient()).fetch(
        DataSourceRequest(source="xuezhi", query="土木工程")
    )
    assert failed.degraded is True
    assert any("学职平台不可达" in item for item in failed.errors)


async def test_xuezhi_gateway_keeps_partial_records_when_a_step_fails() -> None:
    """中途某一步失败时，已取到的证据要保留，同时如实标记不完整。"""

    class _HalfBrokenClient(_StubXueZhiClient):
        async def get_occupation_detail(self, occ_id: str):
            raise RuntimeError("职业详情超时")

    result = await XueZhiDataSourceGateway(_HalfBrokenClient()).fetch(
        DataSourceRequest(
            source="xuezhi",
            limit=8,
            context={"fields": [{"key": "major", "value": "土木工程"}]},
        )
    )

    assert result.degraded is True
    assert any("职业详情超时" in item for item in result.errors)
    assert [record.kind for record in result.records] == ["speciality"]

async def test_intel_explores_by_direction_plan_not_only_profile(container: Container) -> None:
    """方向方案优先于专业：选/生成方向后，探索取词与依据都跟方向走。

    此前的缺陷：方向页说“后端开发”，探索页仍按专业“土木工程”返回
    “结构工程师”，两页方向看起来对不上。
    """
    from zhiyin_business.services.function import DefaultFunctionService
    from zhiyin_kernel.assets import DirectionPlan
    from zhiyin_kernel.enums import PlanRole

    await container.profile_service.update_field(
        USER_ID, "major", "土木工程", confidence=0.9, source="conversation"
    )
    await container.asset_service.save_direction_plans(
        USER_ID,
        [
            DirectionPlan(
                id="dp-main",
                role=PlanRole.MAIN,
                name="后端开发工程师",
                target_desc="后端开发",
                fit_reason="用户明确提出的方向",
                main_risk="需要补项目证据",
            )
        ],
    )
    gateway = _StubGateway(_result())
    service = DefaultFunctionService(
        assets=container.asset_service,
        behaviors=container.behavior_service,
        object_store=container.object_store,
        calendar=container.calendar,
        track_events=container.track_events,
        notifications=container.notifications,
        registry=container.registry_service,
        profiles=container.profile_service,
        data_sources=gateway,
        notifier=None,
    )

    assert await service.intel_basis(USER_ID) == ("后端开发工程师", "direction")
    await service.fetch_external_intel(USER_ID, limit=8)
    assert gateway.requests[0].query == "后端开发工程师"
    assert any(
        field["key"] == "target_direction" and field["value"] == "后端开发工程师"
        for field in gateway.requests[0].context["fields"]
    )

async def test_direction_plan_rejects_reminder_like_name(container: Container) -> None:
    """方向方案不能被日程/提醒内容污染（存量缺陷：主攻叫“明早九点 · 实训材料提醒”）。"""
    from zhiyin_kernel.assets import DirectionPlan
    from zhiyin_kernel.enums import PlanRole
    from zhiyin_kernel.errors import InvalidRequest

    with pytest.raises(InvalidRequest):
        await container.asset_service.save_direction_plans(
            USER_ID,
            [
                DirectionPlan(
                    id="dp-bad",
                    role=PlanRole.MAIN,
                    name="明早九点 · 实训材料提醒",
                    target_desc="提醒",
                    fit_reason="日程",
                    main_risk="污染",
                )
            ],
        )
