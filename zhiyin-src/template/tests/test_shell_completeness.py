"""外壳完整度守卫。

本期不是实现期，而是"把外壳铺完整、让团队能在不动别人代码的前提下并行开工"。
因此本文件守的是**外壳**，不是业务行为：

1. 落位表里的每个格子都必须是**真实文件**（此前 8 个服务只写在 docstring 表格里，
   文件不存在——每个人接手都要自己新建文件、自己定类名，必然互相踩）；
2. 每个骨架类必须真的实现它那一层的 Port（签名对不上就等于没冻结）；
3. 骨架必须自报 `IMPLEMENTATION_STATUS="skeleton"`，且**不得**出现在装配表里
   ——否则"文件存在"会被误读成"能力已具备"，重演假装配；
4. 动态资源的交叉引用必须闭合（最容易漏、且一旦漏就是静默回落的一类）。

这些断言与 `test_architecture.py` 的分工不同：那里守"层与层之间不许乱连"，
这里守"层内每个格子都有实体、且不会假装完成"。
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = TEMPLATE_ROOT / "data" / "registry"


# 骨架实现登记表：能力位名 → (模块, 类名)。
#
# ⚠️ 这张表**必须非空**，而且不能再用"清空 = 没有待补骨架"的口径。
# 之前有三张同类的表在联调期被清空（SERVICE_SHELL / WORKER_SHELL / SKELETON_PORTS），
# 结果是 4 个 `@pytest.mark.parametrize` 用例退化成
# `SKIPPED (got empty parameter set)` —— pytest 把空参数集当 skip 而不是 fail，
# 于是"骨架不许装成已完成"这条守卫在清表那一刻静默失效，CI 一片绿。
#
# 现在改为**按实际存在的骨架登记**：仓库里确实还留着骨架实现（下面这几个本地方案），
# 它们就必须被逐个断言，而不是被一句"已交付"盖过去。
SKELETON_GATEWAYS: dict[str, tuple[str, str]] = {
    "embedding": ("zhiyin_infrastructure.local.embedding", "LocalHashEmbedder"),
    "cache": ("zhiyin_infrastructure.local.cache", "InMemoryCache"),
    "security": ("zhiyin_infrastructure.local.security", "NoopSecurity"),
    "rate_limit": ("zhiyin_infrastructure.local.security", "NoopRateLimit"),
}

# 业务服务 / Worker 目前没有待补骨架（都已交付实现，登记在 WIRED_* 里）。
WIRED_SERVICE_PORTS: frozenset[str] = frozenset(
    {
        "orchestrator",
        "profile_service",
        "behavior_service",
        "memory_service",
        "asset_service",
        "registry_service",
        "identity_service",
        "workspace_service",
        "function_service",
        "ai_task_service",
        "note_service",
        "academic_service",
        "facade",
    }
)
WIRED_WORKER_PORTS: frozenset[str] = frozenset({"vector_sync", "impact", "active_event"})


def test_shell_tables_are_not_empty() -> None:
    """守卫表不许空转。

    pytest 把空的 parametrize 集当 skip，所以"表被清空"这件事在 CI 里是**静默**的。
    这条断言把它变成红灯：要么登记真实存在的骨架，要么删掉对应的守卫，
    不允许留一张空表假装还在守。
    """
    assert SKELETON_GATEWAYS, (
        "骨架登记表被清空了 —— 守卫会变成 0 个用例的 skip。"
        "若确实已无骨架实现，请连同依赖它的用例一起删除，而不是留一张空表。"
    )


def _load(module: str, name: str):
    return getattr(importlib.import_module(module), name)


def _read_json(name: str) -> dict:
    return json.loads((REGISTRY_DIR / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. 落位表 ↔ 真实文件
# --------------------------------------------------------------------------


@pytest.mark.parametrize("port", sorted(SKELETON_GATEWAYS))
def test_gateway_shell_has_a_real_file_and_class(port: str) -> None:
    """每个骨架网关都必须有可 import 的真实类，而不是只写在报告里。"""
    module, class_name = SKELETON_GATEWAYS[port]
    assert _load(module, class_name) is not None


@pytest.mark.parametrize("port", sorted(SKELETON_GATEWAYS))
def test_gateway_skeleton_declares_its_status(port: str) -> None:
    """骨架网关必须自报 `IMPLEMENTATION_STATUS="skeleton"`。

    口径：`/healthz` 与 `--check` 的 `skeletons` 列表读的就是这个属性 ——
    报告里报得对不对，取决于实现方有没有老实声明。
    """
    module, class_name = SKELETON_GATEWAYS[port]
    assert getattr(_load(module, class_name), "IMPLEMENTATION_STATUS", None) == "skeleton", (
        f"{class_name} 自称骨架，但没声明 IMPLEMENTATION_STATUS='skeleton' —— "
        "装配报告会把它当成已实现"
    )


@pytest.mark.parametrize("port", sorted(SKELETON_GATEWAYS))
def test_gateway_skeleton_is_reported_as_skeleton(port: str) -> None:
    """骨架网关在装配报告里必须显示为 skeleton / not_wired，绝不许显示 wired。

    这是"文件存在 ≠ 能力具备"的运行时落点：本地方案里这些网关是真装配进去的
    （所以不能像业务骨架那样"不进装配表"），它们靠自述属性如实标注。
    """
    from zhiyin_boot import build_container, describe_assembly

    report = describe_assembly(build_container(_test_settings()))
    listed = sorted(report.skeletons)
    assert any(f"gateways.{port}：" in line for line in listed), (
        f"装配报告没有把 gateways.{port} 标成骨架，实际 skeletons={listed}"
    )


def test_service_placement_table_matches_directory() -> None:
    """`services/__init__.py` docstring 里的落位表不得与目录内容漂移。

    这是对本次实际缺陷的定向守卫：过去 7 个服务只存在于文档表格中，文件并不存在，
    表格与目录不一致却没有任何检查会失败。
    """
    directory = TEMPLATE_ROOT / "zhiyin-business" / "zhiyin_business" / "services"
    docstring = (directory / "__init__.py").read_text(encoding="utf-8")
    # 只比对"裸文件名"形态（`xxx.py`）；带路径的引用（如 policies/impact.py）不属于本目录。
    listed = set(re.findall(r"`([a-z_]+\.py)`", docstring))
    actual = {item.name for item in directory.glob("*.py") if item.name != "__init__.py"}
    assert listed == actual, (
        "services/ 的落位表与真实文件不一致：\n"
        f"  表格里有但文件缺失：{sorted(listed - actual)}\n"
        f"  文件存在但表格没登记：{sorted(actual - listed)}"
    )


def test_infrastructure_drawers_exist() -> None:
    """基础设施侧的替换点目录必须存在（一个目录 = 一套实现）。

    没有目录，数据访问负责人连"实现放哪"都要临时决定，必然与 `local/` 混在一起。
    """
    for module in (
        "zhiyin_infrastructure.local",
        "zhiyin_infrastructure.workers",
    ):
        imported = importlib.import_module(module)
        assert (imported.__doc__ or "").strip(), f"{module} 缺少说明 docstring"


def test_every_capability_slot_is_wired_or_shelled() -> None:
    """每个能力位都必须有落位：要么是骨架格子，要么是已交付实现。

    这条守的是"装配清单与代码实体脱节"：`container/ports.py` 里加一个能力位
    （于是 `--check` 会报它 `not_wired`、门禁会要求它），但如果没人建文件，
    接手的人要自己决定文件名与类名，必然与别人的命名打架。
    """
    from zhiyin_boot.container.ports import SERVICE_PORTS, WORKER_PORTS

    unplanned = [port for port in SERVICE_PORTS if port not in WIRED_SERVICE_PORTS]
    assert not unplanned, (
        f"这些服务能力位没有登记落位：{unplanned}。"
        "请把实现加进 WIRED_SERVICE_PORTS，或为其建立骨架并在本文件登记"
    )

    unplanned_workers = [port for port in WORKER_PORTS if port not in WIRED_WORKER_PORTS]
    assert not unplanned_workers, (
        f"这些 Worker 能力位没有落位文件：{unplanned_workers}"
    )

    # 反向：登记为已实现的能力位必须真的还在装配清单里（改名/删除时不留旧约定）
    stale = sorted(
        (WIRED_SERVICE_PORTS - set(SERVICE_PORTS))
        | (WIRED_WORKER_PORTS - set(WORKER_PORTS))
    )
    assert not stale, (
        f"这些已登记的能力位已不在装配清单里（被删或改名）：{stale}。"
        "请同步 zhiyin_boot/container/ports.py"
    )

# --------------------------------------------------------------------------
# 3. 骨架不许装成"已完成"
# --------------------------------------------------------------------------


def test_worker_contract_stays_minimal() -> None:
    """Worker 契约必须保持最小（只有 `name` + `run_once`）。

    它躺在内核里，而内核的准入规则是"零依赖的最小契约"。一旦有人把
    `run_forever` / `run_until_cancelled` 这类驱动逻辑加回来，内核就持有了行为
    （asyncio 循环），下放的意义就没了。驱动逻辑的正确位置是
    `zhiyin_boot/workers.py`。
    """
    from zhiyin_kernel.worker import Worker

    # 过滤 `__abstractmethods__` 与 ABCMeta 注入的 `_abc_impl`，
    # 只看类自己声明的成员。
    members = {name for name in vars(Worker) if not name.startswith("_")}
    assert members == {"name", "run_once"}, (
        f"Worker 契约的成员变了：{sorted(members)}。"
        "驱动逻辑请放 zhiyin_boot/workers.py，不要加进契约"
    )
    assert Worker.__abstractmethods__ == frozenset({"run_once"})


def _test_settings():
    from zhiyin_boot import Settings

    data_dir = TEMPLATE_ROOT / "data"
    return Settings(
        # 本项目不提供 mock 产出：没有真模型就没有智能体引擎。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_data_dir=str(data_dir),
        local_registry_dir=str(data_dir / "registry"),
        local_knowledge_dir=str(data_dir / "knowledge"),
        local_object_dir=str(data_dir / "objects"),
    )


def test_delivered_services_are_wired_into_the_container() -> None:
    """已交付的服务必须进装配表并自报 wired。

    联调期（2026-09）workspace / function / facade 与两个业务 Worker 交付后，
    装配报告必须如实反映；vector_sync 依赖 PostgreSQL，本地装配仍为 not_wired。
    """
    from zhiyin_boot import build_container, describe_assembly

    report = describe_assembly(build_container(_test_settings()))

    for port in ("workspace_service", "function_service", "facade"):
        assert report.services[port] == "wired", port
    for port in ("impact", "active_event"):
        assert report.workers[port] == "wired", port
    assert report.workers["vector_sync"] == "not_wired"


def test_wired_skeleton_is_reported_as_skeleton() -> None:
    """装配层的自述优先：万一有人把骨架接进装配表，报告必须标 skeleton 而不是 wired。

    这是"文件存在 ≠ 能力具备"这条约定的机械保证。
    """
    from zhiyin_api.runtime import SKELETON
    from zhiyin_boot import describe_assembly
    from zhiyin_boot.container import Container
    from zhiyin_business.services import DefaultOrchestrator

    container = Container(
        settings=_test_settings(),
        llm=None,
        embedding=None,
        knowledge=None,
        search=None,
        vector=None,
        cache=None,
        object_store=None,
        event_bus=None,
        scheduler=None,
        notifier=None,
        auth=None,
        security=None,
        rate_limit=None,
        external_data=None,
        chsi=None,
    )

    # 不实例化骨架（其协作方全是未实现的骨架），挂一个同样自述为 skeleton 的替身，
    # 验证报告读的是 IMPLEMENTATION_STATUS 而不是"对象是否存在"。
    class _WiredSkeleton:
        IMPLEMENTATION_STATUS = "skeleton"

    container.orchestrator = _WiredSkeleton()
    report = describe_assembly(container)

    assert report.services["orchestrator"] == SKELETON
    assert DefaultOrchestrator.IMPLEMENTATION_STATUS == "wired"


# --------------------------------------------------------------------------
# 4. BFF 取数路径闭合（api 拿不到 data_sdk，必须每条数据都有业务侧出口）
# --------------------------------------------------------------------------


# `/app/bootstrap` 的每个字段 → 它的取数出口。
# 这张表就是"api 需要、契约却在 data_sdk"这类缺口的检查清单：新增字段时
# 必须同时给出出口（RegistryService 的方法 / identity），否则前端拿不到数据，
# 而症状是"字段恒为空"——比报错更难查。
BOOTSTRAP_FIELD_SOURCES: dict[str, tuple[str, str]] = {
    "app_name": ("zhiyin_business.ports.registry", "get_copy_bundle"),
    "menus": ("zhiyin_business.ports.registry", "list_menus"),
    "routes": ("zhiyin_business.ports.registry", "list_routes"),
    "task_entries": ("zhiyin_business.ports.registry", "list_task_entries"),
    "copy_bundle": ("zhiyin_business.ports.registry", "get_copy_bundle"),
    "trust_blocks": ("zhiyin_business.ports.registry", "list_trust_blocks"),
    "banners": ("zhiyin_business.ports.registry", "list_banners"),
    "faqs": ("zhiyin_business.ports.registry", "list_faqs"),
    "feature_flags": ("zhiyin_business.ports.registry", "feature_flags"),
    # 身份区不走 Registry：它由 IdentityService 解析当前用户后填入。
    "identity": ("zhiyin_business.ports.identity", "current_user"),
}


def test_every_bootstrap_field_has_a_business_source() -> None:
    """`BootstrapView` 的每个字段都必须能从业务侧取到。

    为什么值得守：api 被禁止 import `zhiyin_data_sdk`，所以任何"数据在动态资源里、
    却没人包成业务 Port"的字段都会恒为空——前端只会看到空菜单 / 空文案，
    而不会收到任何错误。这条守卫把"字段有出口"变成机械可判。
    """
    from zhiyin_api.dto.bootstrap import BootstrapView

    fields = set(BootstrapView.model_fields)
    declared = set(BOOTSTRAP_FIELD_SOURCES)
    assert fields == declared, (
        "BootstrapView 字段与取数出口表不一致：\n"
        f"  字段无出口（前端会拿到恒空值）：{sorted(fields - declared)}\n"
        f"  出口表里有已删除字段：{sorted(declared - fields)}"
    )

    for field, (module, method) in BOOTSTRAP_FIELD_SOURCES.items():
        port = _load(module, module.rsplit(".", 1)[1].capitalize() + "Service")
        assert hasattr(port, method), (
            f"{field} 声明的出口 {module}.{method} 不存在，"
            "请先在业务 Port 上冻结方法再让 BFF 用它"
        )


def test_api_has_a_mapper_layer() -> None:
    """BFF 的字段映射必须集中在 `dto/mappers.py`，不能内联在 Facade 里。

    这条守的是"前端字段口径只有一处"：Mapper 一旦被绕开，同事就会直接在
    Facade 方法体里拼 View，字段口径散开，改一个字段要翻遍整个 facade 包。
    """
    import ast

    from zhiyin_api.dto import mappers

    assert (mappers.__doc__ or "").strip(), "mappers.py 必须写清口径"
    facade = TEMPLATE_ROOT / "zhiyin-api" / "zhiyin_api" / "facade" / "application.py"
    tree = ast.parse(facade.read_text(encoding="utf-8"), filename=str(facade))
    inlined = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id.endswith("View")
    ]
    assert not inlined, (
        f"Facade 里出现了直接构造 View 的代码：{sorted(set(inlined))}。"
        "请改为调用 dto/mappers.py 里的映射函数（字段口径只允许一处）"
    )


def test_dynamic_resource_files_exist() -> None:
    """动态资源的 JSON 种子必须齐全。

    Repository 的 `_load` 在文件缺失时**静默返回空列表**——这是刻意的
    （第一期允许某类资源不配），但代价是"配置漏了"和"这类资源本来就没有"
    看起来一样。这里把"清单里声明要读的文件都必须存在"钉住，
    让漏文件在 CI 失败，而不是在前端看到空菜单。
    """
    from zhiyin_infrastructure.local.feature_flag import LocalFeatureFlagStore
    from zhiyin_infrastructure.local.repository import LocalJsonRegistryRepository

    filenames = set(LocalJsonRegistryRepository.FILES.values())
    filenames.add(LocalFeatureFlagStore.FILENAME)
    missing = sorted(name for name in filenames if not (REGISTRY_DIR / name).is_file())
    assert not missing, f"data/registry/ 下缺少动态资源文件：{missing}"


# --------------------------------------------------------------------------
# 5. 动态资源交叉引用闭合（此前无守卫）
# --------------------------------------------------------------------------


def test_registry_cross_references_are_closed() -> None:
    """agents / theory_cards / output_contracts / task_entries 的引用必须闭合。

    这类隐患最贵：对不上时系统不会报错，
    而是**静默回落**（主理展示名退化成 agent_id、理论标签点不开、契约取不到）。
    静默回落比报错贵得多，所以在这里挡住。
    """
    agents_items = _read_json("agents.json")["items"]
    agents = {item["id"] for item in agents_items}
    theories = {item["id"] for item in _read_json("theory_cards.json")["items"]}
    entries = _read_json("task_entries.json")["items"]
    contracts = _read_json("output_contracts.json")["items"]

    # ① 任务入口的默认主理必须是已登记的智能体
    for entry in entries:
        if entry["lead_agent"] is None:
            continue
        assert entry["lead_agent"] in agents, (
            f"任务入口 {entry['code']} 的 lead_agent={entry['lead_agent']} 不在 agents.json"
        )

    # ② 智能体引用的理论卡必须存在
    for item in agents_items:
        unknown = sorted(set(item.get("theory_packages", [])) - theories)
        assert not unknown, f"智能体 {item['id']} 引用了不存在的理论卡：{unknown}"

    # ③ 产出契约的唯一键是 (agent_id, stage)，必须唯一且指向已登记智能体
    keys: list[tuple[str, str]] = []
    for spec in contracts:
        assert spec["agent_id"] in agents, (
            f"产出契约 {spec['id']} 的 agent_id={spec['agent_id']} 不在 agents.json"
        )
        keys.append((spec["agent_id"], spec["stage"]))
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    assert not duplicated, f"(agent_id, stage) 必须唯一，重复：{duplicated}"

    # ④ 任务入口声明的（主理 × 目标环节）必须能找到对应契约——
    #    这条正是"oc_decide 成为孤儿"那类缺陷的定向守卫。
    for entry in entries:
        if entry["lead_agent"] is None or entry["target_stage"] is None:
            continue
        pair = (entry["lead_agent"], entry["target_stage"])
        assert pair in keys, (
            f"任务入口 {entry['code']} 会进入 {entry['target_stage']} 环节、"
            f"由 {entry['lead_agent']} 主理，但没有对应的产出契约 {pair}。"
            "缺少时 Loop 会回落到模型生成的 Schema（当前不出错），"
            "但一旦 JSON Schema 被填进另一条契约就会拿错契约校验。"
        )


def test_track_events_are_closed() -> None:
    """埋点事件归属表必须闭合（决策 14：后端派生为主 + 前端上报为辅）。

    `/app/track` 只接收 `channel=frontend` 的体验型事件；后端派生事件若被误标成
    frontend，就会出现"同一条事件被记两次/归属错乱"。这里把明确由
    前端触发的 6 个事件钉成 frontend，同时校验 channel 取值与 code 唯一。
    """
    events = _read_json("track_events.json")["items"]
    codes = [item["code"] for item in events]
    assert len(codes) == len(set(codes)), f"track_events.json 的 code 重复：{codes}"

    allowed_channels = {"frontend", "backend"}
    for item in events:
        assert item["channel"] in allowed_channels, (
            f"事件 {item['code']} 的 channel={item['channel']!r} 非法，"
            f"只允许 {sorted(allowed_channels)}"
        )

    frontend = {item["code"] for item in events if item["channel"] == "frontend"}
    expected_frontend = {
        "conv_disclosure_open",
        "collect_gap_show",
        "diagnosis_view",
        "decision_compare",
        "review_warning_show",
        "wb_enter",
    }
    assert expected_frontend <= frontend, (
        f"以下纯前端体验事件没有标成 frontend："
       f"{sorted(expected_frontend - frontend)}"
    )


# --------------------------------------------------------------------------
# 6. 提示词与编排规则的闭合（此前无守卫）
# --------------------------------------------------------------------------


def test_every_agent_has_a_role_prompt() -> None:
    """每个登记在册的智能体都要有角色提示词。

    为什么必须守：提示词缺席时引擎**不会报错**，只会退回通用回复 ——
    症状是"这个环节突然不说人话了"，而配置漏了这件事没有任何一处会报出来。
    静默回落比报错贵得多。
    """
    prompts = _read_json("prompts.json")["items"]
    agents = _read_json("agents.json")["items"]

    role_prompts = [item for item in prompts if item.get("layer") == "role"]
    with_prompt = {item.get("agent_id") for item in role_prompts}
    missing = sorted(item["id"] for item in agents if item["id"] not in with_prompt)
    assert not missing, (
        f"以下智能体没有角色提示词：{missing}。"
        "它们被调用时会退回通用回复，而界面上看不出异常。"
    )

    # 同一智能体在多个环节各有提示词时，环节取值必须是真的环节
    from zhiyin_kernel.enums import LoopStage

    stages = {stage.value for stage in LoopStage}
    unknown = sorted(
        f"{item['code']}:{item['stage']}"
        for item in role_prompts
        if item.get("stage") and item["stage"] not in stages
    )
    assert not unknown, f"角色提示词挂了不存在的环节：{unknown}"


def test_orchestration_prompts_and_disclosure_reasons_are_closed() -> None:
    """编排必需的提示词必须齐全；换主理告知要按环节分条给全。

    换主理告知缺一个环节，那个环节的交接就只剩"谁接手"，用户看不到"为什么" ——
    而产品口径是换主理必须显式告知原因。
    """
    prompts = _read_json("prompts.json")["items"]
    codes = {item["code"] for item in prompts}

    required = {
        "core.system",
        "guide.closing",
        "router.intent",
        "router.stage",
        "router.lead",
        "router.clarify",
        "disclosure.lead_change",
        "flow.proactive",
    }
    missing = sorted(required - codes)
    assert not missing, f"缺少编排必需的提示词：{missing}"

    stage_ids = {item["id"] for item in _read_json("stages.json")}
    missing_reasons = sorted(
        f"disclosure.reason.{stage}"
        for stage in stage_ids
        if f"disclosure.reason.{stage}" not in codes
    )
    assert not missing_reasons, f"缺少按环节的交接原因：{missing_reasons}"

    # 告知模板的占位符必须与编排器渲染时用的一致，否则渲染会抛异常、
    # 交接那一刻用户什么都看不到。
    template = next(item for item in prompts if item["code"] == "disclosure.lead_change")
    assert "{to_name}" in template["content"] and "{reason}" in template["content"], (
        "换主理告知模板缺少 to_name / reason 占位符"
    )


def test_routing_rules_are_closed() -> None:
    """编排规则必须闭合：占位符没写、意图名打错、环节名打错，都算漏。

    这些错在运行时的表现是"某一类话永远走不到该去的那一步"，
    不会报错，只会让人觉得"它有时候不太懂我"。
    """
    from zhiyin_business.ports.orchestrator import IntentType
    from zhiyin_kernel.enums import LoopStage

    rules = _read_json("routing_rules.json")["items"]
    intents = {item.value for item in IntentType}
    stages = {item.value for item in LoopStage}

    for rule in rules:
        assert rule["kind"] in {"intent", "stage"}, f"规则 {rule['id']} 的 kind 非法"
        if rule["kind"] == "intent":
            assert rule["match"], f"意图规则 {rule['id']} 没有命中词，它永远不会生效"
            assert rule["intent"] in intents, (
                f"意图规则 {rule['id']} 的目标意图不存在：{rule['intent']}"
            )
        else:
            assert rule["intent"] in intents, (
                f"环节规则 {rule['id']} 的输入意图不存在：{rule['intent']}"
            )
            assert rule["stage"] in stages, (
                f"环节规则 {rule['id']} 的目标环节不存在：{rule['stage']}"
            )

    # 每个意图都要有去处，否则命中它的用户会停在原地
    mapped = {item["intent"] for item in rules if item["kind"] == "stage"}
    unmapped = sorted(intents - mapped - {"free_chat"})
    assert not unmapped, f"以下意图没有映射到环节：{unmapped}"
