"""基础设施层测试：语义必须保持一致。

本文件的自述原则是「行为必须保持一致（含版本 +1、只追加、影响面匹配），
否则切真后会暴露契约之外的差异」。这里把这些语义逐条钉住。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from zhiyin_kernel.assets import ActionPhase, ActionPlan, ActionTask
from zhiyin_kernel.blackboard import (
    AssetVersion,
    BehaviorLog,
    ProfileField,
)
from zhiyin_kernel.enums import (
    AssetType,
    BehaviorEventType,
    LoopStage,
    ProfileSource,
    TaskStatus,
)
from zhiyin_kernel.identity import UserAccount

from zhiyin_infrastructure.local.feature_flag import LocalFeatureFlagStore
from zhiyin_infrastructure.local.knowledge import LocalKnowledgeRepo
from zhiyin_infrastructure.local.object_store import LocalFileStore
from zhiyin_infrastructure.local.repository import (
    InMemoryAssetRepository,
    InMemoryBehaviorRepository,
    InMemoryProfileRepository,
    InMemoryTaskSessionRepository,
    LocalJsonRegistryRepository,
)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# 画像
# --------------------------------------------------------------------------


async def test_profile_upsert_is_idempotent_by_key() -> None:
    repo = InMemoryProfileRepository()
    await repo.upsert_field(
        "u1",
        ProfileField(
            key="major",
            value="计算机",
            confidence=0.9,
            source=ProfileSource.CONVERSATION,
            updated_at=_now(),
        ),
    )
    await repo.upsert_field(
        "u1",
        ProfileField(
            key="major",
            value="软件工程",
            confidence=1.0,
            source=ProfileSource.RESUME,
            updated_at=_now(),
        ),
    )

    fields = await repo.list_fields("u1")
    assert len(fields) == 1
    assert fields[0].value == "软件工程"


async def test_profile_version_increases_on_update() -> None:
    repo = InMemoryProfileRepository()
    field = ProfileField(
        key="interest",
        value="a",
        confidence=1.0,
        source=ProfileSource.CONVERSATION,
        updated_at=_now(),
    )
    await repo.upsert_field("u1", field)
    v1 = (await repo.get("u1")).version
    await repo.upsert_field("u1", field)
    v2 = (await repo.get("u1")).version
    assert v2 > v1


async def test_profile_read_is_a_snapshot() -> None:
    repo = InMemoryProfileRepository()
    await repo.upsert_field(
        "u1",
        ProfileField(
            key="k",
            value={"nested": 1},
            confidence=1.0,
            source=ProfileSource.CONVERSATION,
            updated_at=_now(),
        ),
    )
    snapshot = (await repo.list_fields("u1"))[0]
    snapshot.value["nested"] = 999
    assert (await repo.list_fields("u1"))[0].value["nested"] == 1


# --------------------------------------------------------------------------
# 行为日志
# --------------------------------------------------------------------------


async def test_behavior_log_is_append_only_and_sorted_desc() -> None:
    repo = InMemoryBehaviorRepository()
    for index in range(3):
        await repo.append(
            BehaviorLog(
                id="",
                user_id="u1",
                event_type=BehaviorEventType.ANSWER,
                occurred_at=datetime(2026, 9, 14, index, tzinfo=timezone.utc),
            )
        )

    logs = await repo.list_by_user("u1")
    assert len(logs) == 3
    # 最近的在最前
    assert logs[0].occurred_at > logs[-1].occurred_at
    # 没有提供任何 UPDATE 路径
    assert not hasattr(repo, "update")


async def test_behavior_filters_and_last_occurred() -> None:
    repo = InMemoryBehaviorRepository()
    await repo.append(
        BehaviorLog(
            id="",
            user_id="u1",
            event_type=BehaviorEventType.TASK_DONE,
            occurred_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        )
    )
    await repo.append(
        BehaviorLog(
            id="",
            user_id="u1",
            event_type=BehaviorEventType.TASK_DONE,
            occurred_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
        )
    )

    only_done = await repo.list_by_user("u1", event_types=[BehaviorEventType.TASK_DONE])
    assert len(only_done) == 2
    assert await repo.last_occurred_at("u1", BehaviorEventType.TASK_DONE) == datetime(
        2026, 9, 13, tzinfo=timezone.utc
    )
    # 停滞检测的唯一依据
    assert await repo.last_occurred_at("u1", BehaviorEventType.GAP_CLAIM) is None


# --------------------------------------------------------------------------
# 资产与影响面
# --------------------------------------------------------------------------


def _asset(user_id: str, asset_type: AssetType, keys: list[str], version: int = 1) -> AssetVersion:
    return AssetVersion(
        id="",
        user_id=user_id,
        asset_type=asset_type,
        version=version,
        created_at=_now(),
        depends_on_profile_keys=keys,
    )


async def test_asset_version_is_monotonic() -> None:
    repo = InMemoryAssetRepository()
    first = await repo.save_version(_asset("u1", AssetType.REPORT, ["major"]))
    # 调用方就算传小值，也不会把版本压回去
    second = await repo.save_version(
        _asset("u1", AssetType.REPORT, ["major"], version=0)
    )

    assert first.version == 1
    assert second.version == 2


async def test_affected_assets_only_matches_dependencies() -> None:
    repo = InMemoryAssetRepository()
    await repo.save_version(_asset("u1", AssetType.REPORT, ["major", "interest"]))
    await repo.save_version(_asset("u1", AssetType.ACTION_PLAN, ["target_city"]))

    hit = await repo.list_affected_assets("u1", ["major"])
    assert [item.asset_type for item in hit] == [AssetType.REPORT]

    miss = await repo.list_affected_assets("u1", ["something_else"])
    assert miss == []


async def test_affected_assets_uses_latest_version_only() -> None:
    """只重算最新版本，避免把历史版本也卷进影响面传播。"""
    repo = InMemoryAssetRepository()
    await repo.save_version(_asset("u1", AssetType.REPORT, ["major"]))
    latest = await repo.save_version(_asset("u1", AssetType.REPORT, ["major"]))

    hit = await repo.list_affected_assets("u1", ["major"])
    assert len(hit) == 1
    assert hit[0].version == latest.version


async def test_select_direction_plan_is_revocable() -> None:
    from zhiyin_kernel.assets import DirectionPlan
    from zhiyin_kernel.enums import PlanRole

    repo = InMemoryAssetRepository()
    await repo.save_direction_plans(
        "u1",
        [
            DirectionPlan(
                id="p1",
                role=PlanRole.MAIN,
                name="主攻",
                target_desc="",
                match_score=0.8,
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
    plans = await repo.list_direction_plans("u1")
    assert [plan.selected for plan in plans] == [True, False]

    # 可撤回：改选另一个，前一个必须被取消
    await repo.select_direction_plan("u1", "p2")
    plans = await repo.list_direction_plans("u1")
    assert [plan.selected for plan in plans] == [False, True]


async def test_mark_task_done() -> None:
    repo = InMemoryAssetRepository()
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
    assert plan.phases[0].tasks[1].done is False

    with pytest.raises(LookupError):
        await repo.mark_task_done("u1", "不存在的任务")


# --------------------------------------------------------------------------
# 会话
# --------------------------------------------------------------------------


async def test_task_session_find_active_and_update_stage() -> None:
    from zhiyin_kernel.blackboard import TaskSession

    repo = InMemoryTaskSessionRepository()
    await repo.create(
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

    assert (await repo.find_active("u1", "confused")).id == "s1"

    await repo.update_stage("s1", LoopStage.DIAGNOSE, "career_advisor")
    assert (await repo.get("s1")).loop_stage is LoopStage.DIAGNOSE

    await repo.update_status("s1", TaskStatus.COMPLETED)
    assert await repo.find_active("u1", "confused") is None


async def test_user_repository() -> None:
    from zhiyin_infrastructure.local.repository import InMemoryUserRepository

    repo = InMemoryUserRepository()
    await repo.create(
        UserAccount(id="demo-user-0001", phone="DEMO-000", nickname="演示同学", created_at=_now())
    )
    assert (await repo.get_by_id("demo-user-0001")).nickname == "演示同学"
    assert (await repo.get_by_phone("DEMO-000")).id == "demo-user-0001"
    await repo.touch_last_login("demo-user-0001", _now())
    assert (await repo.get_by_id("demo-user-0001")).last_login_at is not None


# --------------------------------------------------------------------------
# 动态资源
# --------------------------------------------------------------------------


async def test_registry_reads_seed_data() -> None:
    repo = LocalJsonRegistryRepository(str(DATA_DIR / "registry"))

    agents = await repo.list_agents()
    assert len(agents) == 5
    assert (await repo.get_agent("profile_analyst")).name == "建档分析师"

    entries = await repo.list_task_entries()
    assert [entry.code for entry in entries][:2] == ["confused", "verify_direction"]
    # sort_order 必须生效，否则首页任务顺序不稳定
    assert [entry.sort_order for entry in entries] == sorted(
        entry.sort_order for entry in entries
    )
    # 「直接开聊」没有目标环节，由编排器判定
    assert entries[-1].target_stage is None

    assert await repo.get_theory_card("holland_riasec") is not None
    assert len(await repo.list_theory_cards(["casve", "clover"])) == 2


async def test_registry_missing_dir_is_empty_not_crash() -> None:
    repo = LocalJsonRegistryRepository(str(DATA_DIR / "does-not-exist"))
    assert await repo.list_agents() == []
    assert await repo.get_agent("any") is None


async def test_feature_flags_come_from_json() -> None:
    store = LocalFeatureFlagStore(str(DATA_DIR / "registry"))
    flags = await store.all()
    assert flags["report_full_text"] is True
    assert flags["export"] is False
    # 未知开关默认关闭，避免"配置漏了反而打开"
    assert await store.is_enabled("not_configured") is False


# --------------------------------------------------------------------------
# 模型 Mock
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# 对象存储 / 知识库
# --------------------------------------------------------------------------


async def test_local_file_store_roundtrip(tmp_path) -> None:
    store = LocalFileStore(str(tmp_path / "objects"))
    key = store.build_key("u1", "report", 2, ".pdf")

    await store.put(key, b"hello", content_type="application/pdf")
    assert await store.get(key) == b"hello"
    stat = await store.stat(key)
    assert stat.size == 5

    await store.delete(key)
    assert await store.stat(key) is None


async def test_local_file_store_blocks_path_traversal(tmp_path) -> None:
    store = LocalFileStore(str(tmp_path / "objects"))
    with pytest.raises(ValueError):
        await store.put("../escape.txt", b"x")


async def test_knowledge_search_ranks_and_respects_namespace() -> None:
    repo = LocalKnowledgeRepo(str(DATA_DIR / "knowledge"))
    hits = await repo.search("霍兰德", namespace="theory", top_k=3)
    assert hits, "应能在 theory 命名空间命中霍兰德相关条目"
    assert hits[0].metadata["namespace"] == "theory"

    # 公共知识命中必须带来源与抓取时间，供报告溯源（R-CRAWL-006）
    assert "source_url" in hits[0].metadata
    assert "fetched_at" in hits[0].metadata


async def test_knowledge_search_vector_degrades_to_empty() -> None:
    from zhiyin_infrastructure.local.knowledge import LocalKeywordSearch

    search = LocalKeywordSearch(str(DATA_DIR / "knowledge"))
    assert await search.vector([0.1, 0.2]) == []
    assert await search.hybrid("霍兰德", top_k=2) == await search.keyword("霍兰德", top_k=2)


# ---------------------------------------------------------------------------
# AI 面向切面：agno 框架运行时与工具注册表（基础设施层维护，见设计文档 6.5）
# ---------------------------------------------------------------------------


def test_agno_model_runtime_builds_client_with_system_role_map() -> None:
    """框架维护切面：role_map 必须显式把 system 拉回（agno 默认 developer，DeepSeek 不认）。"""
    from agno.models.openai import OpenAIChat

    from zhiyin_infrastructure.ai.agno_runtime import AgnoModelRuntime

    runtime = AgnoModelRuntime(
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        temperature=0.3,
    )
    model = runtime.create_model()
    assert isinstance(model, OpenAIChat)
    assert model.id == "deepseek-flash"
    assert model.role_map["system"] == "system", (
        "system 角色必须显式映射，否则 DeepSeek 拒绝请求"
    )
    assert model.temperature == 0.3


def test_tool_registry_register_lookup_and_whitelist() -> None:
    """工具维护切面：注册 / 查询 / 按业务白名单过滤；MCP server 可登记。"""
    import pytest as _pytest

    from zhiyin_infrastructure.ai.tools import ToolRegistry, ToolSpec

    registry = ToolRegistry()
    registry.register(ToolSpec(name="xuezhi.search", description="学职网取数", handler=lambda: None))
    registry.register_mcp_server("career-radar", {"transport": "stdio", "command": "radar"})

    assert registry.get("xuezhi.search").source == "local"
    assert registry.get("mcp:career-radar").source == "mcp"
    with _pytest.raises(LookupError):
        registry.get("not.registered")
    with _pytest.raises(ValueError):
        registry.register(ToolSpec(name="xuezhi.search"))

    # 业务白名单过滤：信息侦查员的 tools 字段只放行列出的工具
    visible = registry.list(allowed={"mcp:career-radar"})
    assert [t.name for t in visible] == ["mcp:career-radar"]


# --------------------------------------------------------------------------
# 工具目录：真实能力包成工具，且模型拿不到用户标识
# --------------------------------------------------------------------------


class _FakeSearch:
    async def hybrid(self, query: str, *, top_k: int = 10):
        from zhiyin_data_sdk.gateways.ai import SearchHit

        return [SearchHit(id="k1", content=f"关于 {query} 的方法论片段", score=0.9)]


class _FakeExternalData:
    async def fetch(self, request):
        from zhiyin_data_sdk.gateways.datasource import DataSourceRecord, DataSourceResult

        return DataSourceResult(
            source=request.source,
            records=[
                DataSourceRecord(
                    id="o1",
                    kind="occupation",
                    title="结构设计",
                    text=f"要求：{request.query} 相关能力",
                    source_url="https://example.test/o1",
                    fetched_at="2026-09-21",
                )
            ],
        )


class _FakeProfile:
    fields = [type("F", (), {"key": "major", "value": "土木工程", "confidence": 0.9, "source": "record"})()]
    gaps = [type("G", (), {"key": "values", "reason": "决定稳定还是成长"})()]


def _full_catalog():
    from zhiyin_infrastructure.ai.tools import build_tool_catalog

    class _FakeWebSearch:
        async def search(self, query: str, *, count=None):  # noqa: ANN001, ANN202
            return []

    async def read_profile(user_id: str):
        return _FakeProfile()

    async def read_behaviors(user_id: str, limit: int = 10):
        return [type("B", (), {"event_type": "task_done", "occurred_at": None})()]

    async def read_plan(user_id: str):
        return {"plan": None, "nodes": []}

    return build_tool_catalog(
        search=_FakeSearch(),
        external_data=_FakeExternalData(),
        # 通用网络搜索是可配的：测试里给一个假的，好让"白名单里的名字都得注册"
        # 这条断言覆盖到它（真的没配时那个名字本来就不该出现在白名单里）。
        web_search=_FakeWebSearch(),
        profile_reader=read_profile,
        behavior_reader=read_behaviors,
        plan_reader=read_plan,
    )


def test_tool_catalog_exposes_real_capabilities() -> None:
    """能力齐备时，五类只读工具都在，而且都能被 agno 认出来。

    （`web.search` 属于"配了搜索密钥才有"，这里给的是假网关，所以它在。）
    """
    from agno.tools.function import Function

    catalog = _full_catalog()
    assert set(catalog) == {
        "kb.search",
        "xuezhi.search",
        "web.search",
        "profile.read",
        "behavior.recent",
        "plan.read",
        "chart.render",
    }
    for spec in catalog.values():
        assert callable(spec.handler), f"{spec.name} 没有可调用的实现"
        fn = Function.from_callable(spec.handler)
        assert fn.description, f"{spec.name} 缺少给模型看的说明"


def test_tools_never_let_the_model_pass_user_identity() -> None:
    """用户标识由运行上下文注入，**不出现在工具参数表里**。

    让模型自己报 user_id 等于把越权入口摆在它面前：它可以填别人的。
    所以工具的 `run_context` 参数必须被框架排除在参数 schema 之外。
    """
    from agno.tools.function import Function

    for name, spec in _full_catalog().items():
        fn = Function.from_callable(spec.handler)
        params = set((fn.parameters or {}).get("properties", {}).keys())
        assert "run_context" not in params, f"{name} 把运行上下文暴露成了模型参数"
        assert not any("user" in param.lower() for param in params), (
            f"{name} 的参数里有用户标识：{params}"
        )


def test_agent_tool_whitelist_matches_registered_tools() -> None:
    """智能体注册表里写的工具名必须真的注册过。

    写错一个名字，引擎会在调用那一刻抛错（不会静默少挂一个），
    但那时用户已经在等回复了。这里提前在测试阶段挡住。
    """
    import json

    template_root = Path(__file__).resolve().parents[1]
    agents = json.loads(
        (template_root / "data" / "registry" / "agents.json").read_text(encoding="utf-8")
    )["items"]
    registered = set(_full_catalog())
    for agent in agents:
        unknown = sorted(set(agent.get("tools", [])) - registered)
        assert not unknown, f"智能体 {agent['id']} 的白名单里有未注册的工具：{unknown}"


async def test_plan_read_hands_the_model_a_readable_plan() -> None:
    """`plan.read` 真的读得出东西来，没有计划时也说得清"还没有"。

    工具挂了却一调就抛，代价落在用户那一轮（模型拿到的是异常文本，只能说"我没查到"）。
    这里直接调它的实现：有计划时给出阶段/任务/勾选状态，没有时如实说没有。
    """
    from types import SimpleNamespace

    async def reader_with_plan(user_id: str):
        plan = SimpleNamespace(
            phases=[
                SimpleNamespace(
                    name="本周",
                    date_range="9-22 ~ 9-28",
                    tasks=[
                        SimpleNamespace(text="抄 3 条岗位职责", done=True),
                        SimpleNamespace(text="把简历改一版", done=False),
                    ],
                )
            ]
        )
        nodes = [SimpleNamespace(title="秋招投递开始", due_at="2026-10-01")]
        return {"plan": plan, "nodes": nodes}

    async def empty_reader(user_id: str):
        return {"plan": None, "nodes": []}

    from zhiyin_infrastructure.ai.tools import build_tool_catalog

    context = SimpleNamespace(user_id="u1")
    filled = await build_tool_catalog(plan_reader=reader_with_plan)["plan.read"].handler(context)
    assert "抄 3 条岗位职责" in filled and "[已做]" in filled
    assert "秋招投递开始" in filled and "2026-10-01" in filled

    empty = await build_tool_catalog(plan_reader=empty_reader)["plan.read"].handler(context)
    assert "还没有行动计划" in empty


def test_side_effecting_capabilities_are_not_tools() -> None:
    """有副作用的动作不许做成模型随手可调的工具。

    核验学籍、抓课表成绩、写日历都要走业务侧的完整链路（核验 → 解析 → 写画像 → 回执），
    模型看不到那条链路的副作用边界，而写画像的代价是不可逆的。
    """
    catalog = _full_catalog()
    forbidden = ("chsi", "academic", "write", "bind")
    offenders = sorted(
        name for name in catalog if any(word in name for word in forbidden)
    )
    assert not offenders, f"这些有明显副作用的动作被做成了工具：{offenders}"


# ---------------------------------------------------------------------------
# 画图：数字只能来自库里，模型只挑"画哪一类"
# ---------------------------------------------------------------------------


def _chart_context():
    from types import SimpleNamespace

    # 回传盒子里放的是**可视件数组**（一个工具可以一次产出多件）。
    return SimpleNamespace(user_id="u1", dependencies={"renderables": []})


async def test_chart_render_draws_from_real_rows_not_from_the_model() -> None:
    """`chart.render` 的点位来自服务端读出的真实数据；模型只能挑类别。

    这是"防止假数据"的全部机关：工具的参数里**没有**任何位置能传数值
    （只有 kind 与 title）。所以模型编不出一个好看的分去画给用户。
    """
    from zhiyin_infrastructure.ai.tools import build_tool_catalog

    class _Field:
        def __init__(self, key, label, confidence):
            self.key, self.label, self.confidence = key, label, confidence

    class _Profile:
        fields = [_Field("major", "专业", 0.9), _Field("interest", "兴趣方向", 0.6)]

    async def read_profile(user_id: str):
        return _Profile()

    catalog = build_tool_catalog(profile_reader=read_profile)
    context = _chart_context()
    result = await catalog["chart.render"].handler(context, kind="profile_confidence")

    spec = context.dependencies["renderables"][0]
    assert spec["kind"] == "bars_chart"
    assert spec["payload"]["points"] == [
        {"label": "专业", "value": 0.9},
        {"label": "兴趣方向", "value": 0.6},
    ]
    assert "90%" in result  # 说给模型听的是同一批真实数字


async def test_chart_render_refuses_an_unknown_kind() -> None:
    """不认识的类别 → 如实说能画哪几种，**不画**。"""
    from zhiyin_infrastructure.ai.tools import build_tool_catalog

    async def read_profile(user_id: str):
        return None

    catalog = build_tool_catalog(profile_reader=read_profile)
    context = _chart_context()
    result = await catalog["chart.render"].handler(context, kind="我编的图")
    assert "没有" in result and "profile_confidence" in result
    assert context.dependencies["renderables"] == [], "不认识的类别不该产出可视件"


async def test_chart_render_says_so_when_there_is_not_enough_data() -> None:
    """数据不够（只有一个点）→ 明说画不出来，别硬画。"""
    from zhiyin_infrastructure.ai.tools import build_tool_catalog

    class _Field:
        key, label, confidence = "major", "专业", 0.9

    class _Profile:
        fields = [_Field()]

    async def read_profile(user_id: str):
        return _Profile()

    catalog = build_tool_catalog(profile_reader=read_profile)
    context = _chart_context()
    result = await catalog["chart.render"].handler(context, kind="profile_confidence")
    assert "只有一项" in result
    assert context.dependencies["renderables"] == []
