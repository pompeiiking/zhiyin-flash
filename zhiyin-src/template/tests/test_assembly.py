"""装配层守卫：清单、报告、门禁三者必须始终对得上。

这三份东西分别是"有哪些能力位"（代码）、"现在装了什么"（报告）、
"到哪个里程碑算过"（动态资源 JSON）。它们一旦漂移，门禁就会失效，
所以用测试把它们钉在一起。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zhiyin_api.runtime import NOT_WIRED, SKELETON, WIRED, AssemblyReport
from zhiyin_boot import (
    Settings,
    build_container,
    describe_assembly,
    evaluate_gate,
    load_gates,
    load_ownership,
)
from zhiyin_boot.container.ports import (
    ALL_PORTS,
    GATEWAY_PORTS,
    ORCHESTRATION_PORTS,
    REPOSITORY_PORTS,
    SERVICE_PORTS,
    WORKER_PORTS,
)

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TEMPLATE_ROOT / "data"
REGISTRY_DIR = DATA_DIR / "registry"

GROUP_PORTS: dict[str, tuple[str, ...]] = {
    "gateways": GATEWAY_PORTS,
    "repositories": REPOSITORY_PORTS,
    "orchestration": ORCHESTRATION_PORTS,
    "services": SERVICE_PORTS,
    "workers": WORKER_PORTS,
}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        # 本项目不提供 mock 产出：没有真模型就没有智能体引擎。
        # 构造真网关不发请求，测试里给一个占位密钥即可。
        use_remote_llm=True,
        llm_api_key="sk-test",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-flash",
        env="test",
        local_data_dir=str(DATA_DIR),
        local_registry_dir=str(REGISTRY_DIR),
        local_knowledge_dir=str(DATA_DIR / "knowledge"),
        local_object_dir=str(DATA_DIR / "objects"),
    )


def test_gates_reference_known_ports() -> None:
    """门禁 JSON 里引用的分组与能力位必须真实存在。

    否则门禁会"看起来在卡口、实际上在检查一个不存在的名字"，静默放行。
    """
    gates = load_gates(str(REGISTRY_DIR))
    assert gates, "必须存在门禁定义"

    for gate in gates:
        assert gate.require, f"里程碑 {gate.phase} 没有定义任何退出条件"
        for group, ports in gate.require.items():
            assert group in GROUP_PORTS, f"里程碑 {gate.phase} 引用了未知分组：{group}"
            for port in ports:
                assert port in GROUP_PORTS[group], (
                    f"里程碑 {gate.phase} 引用了未登记的能力位：{group}.{port}"
                )

    assert [gate.phase for gate in gates] == sorted(gate.phase for gate in gates)


def test_ownership_covers_every_port() -> None:
    """归属清单必须覆盖全部能力位：缺口也要有人认领。"""
    owners = load_ownership(str(REGISTRY_DIR))
    missing = [port for port in ALL_PORTS if port not in owners]
    assert not missing, f"以下能力位在 ownership.json 里没有归属：{missing}"


def test_report_covers_every_port(settings: Settings) -> None:
    """装配报告必须逐个能力位给状态，不允许漏报（漏报=看不见的缺口）。"""
    report = describe_assembly(build_container(settings))

    for group, ports in GROUP_PORTS.items():
        actual = getattr(report, group)
        assert set(actual) == set(ports), f"报告分组 {group} 与装配清单不一致"

    # 每个缺口都必须带归属，不能只报"缺了什么"
    assert report.missing
    assert all("待 " in item for item in report.missing)


def test_skeleton_is_reported_not_hidden(settings: Settings) -> None:
    """骨架实现必须显式暴露。

    第一期存在"形状对、能力占位"的实现（哈希伪嵌入）。若它们被报成 wired，
    就会重演"看起来装好了其实没实现"的问题。
    """
    report = describe_assembly(build_container(settings))
    skeleton = [name for name, status in report.gateways.items() if status == SKELETON]
    assert "embedding" in skeleton
    assert report.healthy is False


def test_gate_passes_only_when_requirements_are_wired() -> None:
    gate = load_gates(str(REGISTRY_DIR))[0]

    all_wired = AssemblyReport(env="test")
    for group in gate.require:
        setattr(all_wired, group, {port: WIRED for port in gate.require[group]})
    assert evaluate_gate(all_wired, gate).passed

    missing_one = AssemblyReport(env="test")
    for group in gate.require:
        setattr(missing_one, group, {port: WIRED for port in gate.require[group]})
    first_group = next(iter(gate.require))
    first_port = gate.require[first_group][0]
    getattr(missing_one, first_group)[first_port] = NOT_WIRED

    result = evaluate_gate(missing_one, gate)
    assert not result.passed
    assert any(first_port in item for item in result.unmet)


def test_phase_one_gate_is_currently_satisfied(settings: Settings) -> None:
    """里程碑 1（框架可验证）必须保持通过：它是本期的退出条件。

    里程碑 2/3/4 未达标是预期（业务主干未接），不在本测试里断言，
    避免"实现推进后测试反而失败"。
    """
    report = describe_assembly(build_container(settings))
    gates = {gate.phase: gate for gate in load_gates(str(REGISTRY_DIR))}
    result = evaluate_gate(report, gates[1])
    assert result.passed, result.unmet


def test_cli_check_is_informational_without_phase(capsys) -> None:
    """`--check` 不带 --phase 时是信息输出，不因为骨架存在而失败。"""
    from zhiyin_boot.__main__ import main

    assert main(["--check"]) == 0
    captured = capsys.readouterr()
    assert "missing" in captured.out


def test_port_groups_are_disjoint() -> None:
    """同一个名字不能出现在两个分组里。

    分组既是报告的行，也是门禁的取值口径（`--check --phase=N`）。重名会让
    "这个能力位装没装"出现两个互相矛盾的答案，而且装配报告里看起来都正常。
    """
    groups: dict[str, str] = {}
    duplicated: list[str] = []
    for group, ports in GROUP_PORTS.items():
        for port in ports:
            if port in groups:
                duplicated.append(f"{port}（{groups[port]} 与 {group}）")
            groups[port] = group
    assert not duplicated, f"能力位重名：{duplicated}"


def test_minimum_viable_is_checked_against_known_ports() -> None:
    """启动前置校验（`MINIMUM_VIABLE`）引用的名字必须是真实能力位。

    `assert_minimum_viable()` 用 `getattr(container, name)` 判空：名字拼错时它拿到
    `None`，于是**每次启动都判定"缺少必需部件"**（或者反过来，与真实能力位无关）。
    这类错字在启动日志里看起来像"配置问题"，排查很贵，因此在这里挡住。
    """
    from zhiyin_boot.container.ports import ALL_PORTS, MINIMUM_VIABLE

    unknown = [name for name in MINIMUM_VIABLE if name not in ALL_PORTS]
    assert not unknown, (
        f"MINIMUM_VIABLE 引用了未登记的能力位：{unknown}。"
        "请检查 zhiyin_boot/container/ports.py 的拼写"
    )
    assert len(set(MINIMUM_VIABLE)) == len(MINIMUM_VIABLE), "MINIMUM_VIABLE 有重复项"


# 能力位名 ↔ Container 字段名：绝大多数能力位就是同名字段（装配报告按名字取值），
# 下面 4 个是**有意**的例外，各自有更强的形状约束。登记在这里等于把这份对照写下来，
# 免得下一个人"顺手"把 workers 拆成三个字段、或把事务管理器加成一个新能力位。
PORT_NOT_A_CONTAINER_FIELD: dict[str, str] = {
    "impact": "container.workers 列表（Worker 按自身的 name 寻址）",
    "active_event": "container.workers 列表（Worker 按自身的 name 寻址）",
    "vector_sync": "container.workers 列表（Worker 按自身的 name 寻址）",
}


def test_port_names_match_container_fields() -> None:
    """每个能力位都必须在容器上有一个可取到状态的落点。

    `describe_assembly` 用 `getattr(container, name)` 逐个取值，名字对不上时它
    永远报 `not_wired`——**报告与门禁会一起说谎**（能力位明明实现了，却一直显示
    "无人认领"）。这条守卫把"名字必须能取到"变成机械可判。
    """
    from zhiyin_boot.container import Container
    from zhiyin_boot.container.ports import ALL_PORTS

    fields = set(Container.__dataclass_fields__)
    unknown = [
        port for port in ALL_PORTS if port not in fields and port not in PORT_NOT_A_CONTAINER_FIELD
    ]
    assert not unknown, (
        f"这些能力位在 Container 上没有同名落点：{unknown}。\n"
        "装配报告用 `getattr(container, <能力位名>)` 取值，取不到就会永远报 not_wired。"
        "请加字段，或在本用例的 PORT_NOT_A_CONTAINER_FIELD 里登记例外与理由"
    )

    stale = sorted(set(PORT_NOT_A_CONTAINER_FIELD) - set(ALL_PORTS))
    assert not stale, f"例外表里的能力位已不存在（能力位改名或删除）：{stale}"
