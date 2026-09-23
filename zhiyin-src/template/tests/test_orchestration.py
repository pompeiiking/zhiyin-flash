"""编排层测试：六个原语必须真的能用，而不是只有 ABC。

这组测试的意义：修复前 `zhiyin-orchestration` 全仓 0 处引用、6 个原语只有抽象类，
相当于金字塔上多画的一格。这里逐条锁住它现在具备的行为。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from agno.models.base import Model
from agno.models.response import ModelResponse

from zhiyin_orchestration import (
    AgentEngine,
    AgentRequest,
    AgentResult,
    DomainEvent,
    GatewayEventBus,
    GatewayNotifier,
    GatewayScheduler,
    MemoryStateStore,
    ScheduleSpec,
    SequentialWorkflowEngine,
    StateConflictError,
    WorkflowFailedError,
    WorkflowSpec,
    WorkflowStep,
    validate_schema,
)

from zhiyin_infrastructure.local.messaging import (
    InMemoryEventBus,
    LocalNotify,
    LocalScheduler,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _StubEngine(AgentEngine):
    """引擎替身：返回固定 structured，或标记为失败。

    工作流原语只依赖 AgentEngine 这个端口，所以测它不需要任何真模型 ——
    给一个实现端口的替身即可（原来这里借用了已删除的第二个引擎实现）。
    """

    def __init__(self, structured: dict | None = None, *, raises: bool = False) -> None:
        self._structured = structured
        self._raises = raises

    async def invoke(self, request: AgentRequest) -> AgentResult:
        if self._raises:
            return AgentResult(
                agent_id=request.agent_id,
                valid=False,
                degraded=True,
                errors=["模型不可用"],
            )
        return AgentResult(
            agent_id=request.agent_id,
            structured=dict(self._structured or {}),
            valid=True,
        )


# --------------------------------------------------------------------------
# 事件
# --------------------------------------------------------------------------


async def test_event_bus_delivers_envelope() -> None:
    bus = GatewayEventBus(InMemoryEventBus())
    received: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    bus.subscribe("profile_field_updated", handler)
    await bus.publish(
        DomainEvent(
            event_id="e1",
            event_type="profile_field_updated",
            occurred_at=_now(),
            payload={"field_key": "major"},
        )
    )

    assert len(received) == 1
    # 消费方拿到的是完整信封，不需要回查状态
    assert received[0].payload["field_key"] == "major"
    assert received[0].event_id == "e1"


async def test_event_bus_is_idempotent_by_key() -> None:
    bus = GatewayEventBus(InMemoryEventBus(), dedup_size=4)
    seen: list[str] = []
    bus.subscribe("evt", lambda event: seen.append(event.event_id))

    for _ in range(3):
        await bus.publish(
            DomainEvent(
                event_id="dup",
                event_type="evt",
                occurred_at=_now(),
                idempotency_key="same-key",
            )
        )

    assert seen == ["dup"]


async def test_event_bus_unsubscribe() -> None:
    bus = GatewayEventBus(InMemoryEventBus())
    seen: list[str] = []

    def handler(event: DomainEvent) -> None:
        seen.append(event.event_id)

    bus.subscribe("evt", handler)
    bus.unsubscribe("evt", handler)
    await bus.publish(DomainEvent(event_id="e", event_type="evt", occurred_at=_now()))
    assert seen == []


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------


def test_state_store_version_conflict() -> None:
    store = MemoryStateStore()
    first = store.write("k", {"v": 1})
    assert first.version == 1

    second = store.write("k", {"v": 2}, expected_version=1)
    assert second.version == 2

    with pytest.raises(StateConflictError):
        store.write("k", {"v": 3}, expected_version=1)


def test_state_store_read_returns_snapshot() -> None:
    store = MemoryStateStore()
    store.write("k", {"nested": {"v": 1}})
    snapshot = store.read("k")
    assert snapshot is not None
    snapshot.value["nested"]["v"] = 999
    assert store.read("k").value["nested"]["v"] == 1


# --------------------------------------------------------------------------
# 调度
# --------------------------------------------------------------------------


async def _fire(scheduler: GatewayScheduler, gateway: LocalScheduler, at: datetime) -> None:
    await gateway.tick(at)


class _ScheduledBus:
    """一次完整的调度接线：

    - `LocalScheduler` 拿到的是 **SDK Gateway**（InMemoryEventBus），
      因为它投递的是裸 payload，不是编排层的 DomainEvent 信封；
    - `GatewayEventBus` 包装**同一个** InMemoryEventBus，
      因此 LocalScheduler 投出的 tick 能被 GatewayScheduler 订阅到。

    注意：把 GatewayEventBus 直接交给 LocalScheduler 会炸 ——
    两者 publish 签名不同（信封 vs (event_type, payload)）。这是本项目
    真实踩过的接线错误，保留在此作为回归用例。
    """

    def __init__(self) -> None:
        self.underlying = InMemoryEventBus()
        self.bus = GatewayEventBus(self.underlying)
        self.gateway = LocalScheduler(self.underlying)
        self.scheduler = GatewayScheduler(self.gateway, self.bus)


async def test_scheduler_fires_registered_event() -> None:
    wiring = _ScheduledBus()
    fired: list[DomainEvent] = []
    wiring.bus.subscribe("task_stall_detected", lambda event: fired.append(event))

    base = _now()
    wiring.scheduler.register(
        ScheduleSpec(
            task_id="stall-check",
            event_type="task_stall_detected",
            payload={"user_id": "u1"},
            trigger_at=base,
        )
    )
    await _fire(wiring.scheduler, wiring.gateway, base)

    assert len(fired) == 1
    assert fired[0].payload["user_id"] == "u1"


async def test_scheduler_respects_cooldown() -> None:
    wiring = _ScheduledBus()
    fired: list[DomainEvent] = []
    wiring.bus.subscribe("reminder", lambda event: fired.append(event))

    base = _now()
    wiring.scheduler.register(
        ScheduleSpec(
            task_id="r1",
            event_type="reminder",
            payload={"user_id": "u1"},
            trigger_at=base,
            interval_s=1.0,
            cooldown_s=60.0,
        )
    )

    await _fire(wiring.scheduler, wiring.gateway, base)
    await _fire(wiring.scheduler, wiring.gateway, base + timedelta(seconds=2))

    # 两次到点，但冷却期内只实际触发一次（打扰度控制）
    assert len(fired) == 1


async def test_scheduler_respects_max_triggers() -> None:
    wiring = _ScheduledBus()
    fired: list[DomainEvent] = []
    wiring.bus.subscribe("ping", lambda event: fired.append(event))

    base = _now()
    wiring.scheduler.register(
        ScheduleSpec(
            task_id="p1",
            event_type="ping",
            payload={},
            trigger_at=base,
            interval_s=1.0,
            max_triggers=2,
        )
    )

    for step in range(4):
        await _fire(wiring.scheduler, wiring.gateway, base + timedelta(seconds=step))

    assert len(fired) == 2


def test_scheduler_cancel() -> None:
    wiring = _ScheduledBus()
    wiring.scheduler.register(ScheduleSpec(task_id="x", event_type="e", payload={}))
    assert [spec.task_id for spec in wiring.scheduler.list_registered()] == ["x"]
    wiring.scheduler.cancel("x")
    assert wiring.scheduler.list_registered() == []


# --------------------------------------------------------------------------
# 通知
# --------------------------------------------------------------------------


async def test_notifier_maps_channel() -> None:
    gateway = LocalNotify()
    notifier = GatewayNotifier(gateway)

    from zhiyin_orchestration import NotifyMessage

    result = await notifier.push(
        NotifyMessage(user_id="u1", title="该复盘了", body="3 天没勾任务", channel="in_app")
    )

    assert result.delivered is True
    assert result.channel == "in_app"
    assert len(gateway.list_messages("u1")) == 1


async def test_notifier_falls_back_on_unknown_channel() -> None:
    notifier = GatewayNotifier(LocalNotify())
    from zhiyin_orchestration import NotifyMessage

    result = await notifier.push(
        NotifyMessage(user_id="u1", title="t", channel="sms-not-configured")
    )
    assert result.channel == "in_app"


# --------------------------------------------------------------------------
# 产出契约校验
# --------------------------------------------------------------------------


def test_validate_schema_basics() -> None:
    schema = {
        "type": "object",
        "required": ["name", "score"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "kind": {"enum": ["a", "b"]},
        },
    }

    assert validate_schema(schema, {"name": "x", "score": 0.5}) == []
    assert validate_schema(schema, {"score": 0.5})
    assert validate_schema(schema, {"name": "x", "score": 2})
    assert validate_schema(schema, {"name": "x", "score": 0.5, "extra": 1})
    assert validate_schema(schema, {"name": "x", "score": 0.5, "kind": "c"})


def test_validate_schema_resolves_ref() -> None:
    schema = {
        "type": "object",
        "properties": {"item": {"$ref": "#/$defs/Item"}},
        "$defs": {
            "Item": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "string"}},
            }
        },
    }
    assert validate_schema(schema, {"item": {"id": "x"}}) == []
    assert validate_schema(schema, {"item": {}})


class _StubModel(Model):
    """一个不联网的 agno 模型：把给定 payload 当作模型回复返回。

    用它测引擎的契约校验与降级 —— 这两件事在真模型上很难稳定复现
    （要让模型"恰好"返回一份不合契约的 JSON）。
    """

    def __init__(self, payload: dict | None = None, *, raises: bool = False) -> None:
        super().__init__(id="stub", name="stub")
        self._payload = payload or {}
        self._raises = raises

    def _parse_provider_response(self, response, **kwargs):
        return response

    def _parse_provider_response_delta(self, response):
        return response

    def invoke(self, *args, **kwargs) -> ModelResponse:
        if self._raises:
            raise RuntimeError("模型不可用")
        return ModelResponse(content=json.dumps(self._payload, ensure_ascii=False))

    async def ainvoke(self, *args, **kwargs):
        return self.invoke()

    async def aresponse(self, *args, **kwargs):
        return self.invoke()

    def invoke_stream(self, *args, **kwargs):
        raise NotImplementedError

    async def ainvoke_stream(self, *args, **kwargs):
        raise NotImplementedError


class _PromptRegistry:
    """最小注册表：只提供引擎要的那几条提示词。"""

    async def get_prompt(self, code: str):
        from zhiyin_kernel.registry import PromptSpec

        return PromptSpec(code=code, layer="core", content=f"{code} 的说明")

    async def list_prompts(self, *, layer=None, agent_id=None, stage=None):
        from zhiyin_kernel.registry import PromptSpec

        return [
            PromptSpec(
                code="role.x", layer="role", agent_id=agent_id or "x", content="角色说明"
            )
        ]

    async def get_agent(self, agent_id: str):
        from zhiyin_kernel.registry import AgentDescriptor

        return AgentDescriptor(id=agent_id, name="测试智能体")


def _agno_engine(payload: dict | None = None, *, raises: bool = False):
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine

    return AgnoAgentEngine(
        model_factory=lambda **_: _StubModel(payload, raises=raises),
        registry=_PromptRegistry(),
    )


async def test_agent_engine_validates_contract() -> None:
    """产出不符合契约时必须被标为无效，而不是悄悄放过去。"""
    schema = {
        "type": "object",
        "required": ["text"],
        "properties": {"text": {"type": "string", "minLength": 1}},
    }

    result = await _agno_engine({"text": "结论"}).invoke(_request(schema))
    assert result.valid is True
    assert result.structured == {"text": "结论"}

    bad = await _agno_engine({"text": ""}).invoke(_request(schema))
    assert bad.valid is False
    assert bad.errors


async def test_agent_engine_degrades_when_model_is_unavailable() -> None:
    """模型调不动是运行故障：允许降级，但要如实标出来。"""
    result = await _agno_engine(raises=True).invoke(_request(None))
    assert result.valid is False
    assert result.degraded is True


def _request(schema):
    from zhiyin_orchestration import AgentRequest

    return AgentRequest(agent_id="some_agent", output_schema=schema, prompt_vars={"a": 1})


# --------------------------------------------------------------------------
# 工作流
# --------------------------------------------------------------------------


async def test_workflow_runs_in_topological_order() -> None:
    engine = SequentialWorkflowEngine(_StubEngine({"ok": True}))
    spec = WorkflowSpec(
        workflow_id="wf",
        steps=[
            WorkflowStep(step_id="s2", agent_id="a2", input_map={"x": "out1"}, output_key="out2", depends_on=["s1"]),
            WorkflowStep(step_id="s1", agent_id="a1", output_key="out1"),
        ],
    )

    result = await engine.run(spec, {"seed": 1})

    assert result.status == "succeeded"
    assert result.outputs["out1"] == {"ok": True}
    assert result.outputs["out2"] == {"ok": True}
    assert result.outputs["seed"] == 1


async def test_workflow_pure_step_passes_inputs_through() -> None:
    engine = SequentialWorkflowEngine(_StubEngine({}))
    spec = WorkflowSpec(
        workflow_id="wf",
        steps=[WorkflowStep(step_id="s1", output_key="copy", input_map={"v": "seed"})],
    )

    result = await engine.run(spec, {"seed": "value"})
    assert result.outputs["copy"] == {"v": "value"}


async def test_workflow_abort_policy_raises() -> None:
    """abort 策略下，步骤失败必须让整条流程失败，而不是静默跳过。"""
    engine = SequentialWorkflowEngine(_StubEngine(raises=True))
    spec = WorkflowSpec(
        workflow_id="wf",
        failure_policy="abort",
        steps=[WorkflowStep(step_id="s1", agent_id="a", output_key="o")],
    )
    with pytest.raises(WorkflowFailedError):
        await engine.run(spec)


async def test_workflow_degrade_policy_skips_dependents() -> None:
    """degrade 策略下：失败的智能体步骤不算成功，其下游依赖无法满足也被标记失败，
    但整条流程不抛异常，返回 partially_succeeded 让调用方决定降级动作。"""
    engine = SequentialWorkflowEngine(_StubEngine(raises=True))
    spec = WorkflowSpec(
        workflow_id="wf",
        failure_policy="degrade",
        steps=[
            WorkflowStep(step_id="s1", output_key="seed_copy", input_map={"v": "seed"}),
            WorkflowStep(step_id="s2", agent_id="a", output_key="o", depends_on=["s1"]),
            WorkflowStep(
                step_id="s3",
                output_key="copy",
                input_map={"v": "o"},
                depends_on=["s2"],
            ),
        ],
    )
    result = await engine.run(spec, {"seed": "value"})

    assert result.status == "partially_succeeded"
    assert result.failed_steps == ["s2", "s3"]
    # 上游成功的纯计算步骤产出仍然保留
    assert result.outputs["seed_copy"] == {"v": "value"}


async def test_workflow_all_failed_is_reported_as_failed() -> None:
    engine = SequentialWorkflowEngine(_StubEngine(raises=True))
    spec = WorkflowSpec(
        workflow_id="wf",
        failure_policy="degrade",
        steps=[WorkflowStep(step_id="s1", agent_id="a", output_key="o")],
    )
    result = await engine.run(spec)
    assert result.status == "failed"
    assert result.failed_steps == ["s1"]


async def test_workflow_detects_unresolvable_dependency() -> None:
    engine = SequentialWorkflowEngine(_StubEngine({}))
    spec = WorkflowSpec(
        workflow_id="wf",
        failure_policy="abort",
        steps=[
            WorkflowStep(step_id="s2", output_key="o2", depends_on=["missing"]),
        ],
    )
    with pytest.raises(WorkflowFailedError):
        await engine.run(spec)


# ---------------------------------------------------------------------------
# AI 面向切面：编排层只做智能体组装，模型对象由装配层注入（见设计文档 6.5）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agno_agent_engine_uses_injected_model_factory() -> None:
    """引擎不接触任何供应商配置：模型对象来自注入的工厂，指令来自动态资源。

    这条同时钉住两件事：
    1. 提示词**不在代码里** —— 引擎是从注册表按 code 取出来的；
    2. 提示词行上的 `params` 真的作用到模型上（换提示词与换温度是一次动作）。
    """
    from agno.models.openai import OpenAIChat

    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine
    from zhiyin_kernel.registry import PromptSpec

    class _StubRegistry:
        """只实现引擎用到的那几个读接口。"""

        def __init__(self) -> None:
            self._prompts = [
                PromptSpec(code="core.system", layer="core", content="全局总纲：一次只说一件事。"),
                PromptSpec(code="guide.closing", layer="guide", content="收尾规范：需要用户回答时给可点选项。"),
                PromptSpec(
                    code="role.tester",
                    layer="role",
                    agent_id="tester",
                    content="你是测试智能体。",
                    params={"temperature": 0.35},
                ),
            ]

        async def get_prompt(self, code):
            return next((item for item in self._prompts if item.code == code), None)

        async def list_prompts(self, *, layer=None, agent_id=None, stage=None):
            items = [item for item in self._prompts if item.status == "enabled"]
            if layer is not None:
                items = [item for item in items if item.layer == layer]
            if agent_id is not None:
                items = [item for item in items if item.agent_id == agent_id]
            if stage is not None:
                items = [item for item in items if item.stage == stage]
            return items

        async def get_agent(self, agent_id):
            return None

    calls = {"n": 0}
    temperatures: list[float] = []
    sentinel = OpenAIChat(id="test-model", api_key="sk-test")  # 仅构造，不发请求

    def fake_factory(*, temperature: float | None = None):
        calls["n"] += 1
        if temperature is not None:
            temperatures.append(temperature)
        return sentinel  # 验证"被注入、被使用"，不发真请求

    engine = AgnoAgentEngine(
        model_factory=fake_factory,
        registry=_StubRegistry(),
    )
    assert calls["n"] == 0, "构造时不得构建模型（惰性）"

    bundle = await engine._prompt_bundle("tester", None)
    agent = await engine._agent_for("tester", None, bundle)
    assert calls["n"] == 1
    assert temperatures == [0.35], "提示词行上的温度必须作用到模型上"
    joined = "\n".join(agent.instructions or [])
    assert "测试智能体" in joined
    assert "全局总纲" in joined

    # 同一 (agent_id, stage) 复用缓存的 Agent，不重复构建模型
    await engine._agent_for("tester", None, bundle)
    assert calls["n"] == 1

    # 换一个环节就是另一个代理：职业顾问同时负责诊断与决策，不能共用角色说明
    other = await engine._agent_for("tester", "decide", bundle)
    assert other is not agent
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_engine_attaches_only_whitelisted_tools(caplog) -> None:
    """工具只能按注册表白名单挂上去；未注册的名字**跳过并记 error**，不再让整轮失败。

    口径改过一次，两种做法的代价都写在这里，免得后人再改回去：

    · 静默忽略不行：那等于"以为给了它一个能力，其实没有" —— 模型不会报错，
      只会答得差一点，界面上完全看不出来；
    · 直接抛错也不行：实测过一次 —— 部署里没配搜索网关，`web.search` 因此
      没注册，而职业顾问的白名单里写着它，于是 ②③④ 每一步都 500，
      用户那句话说了一半就没了。配置缺口不该由用户的一轮消息来承担。

    所以现在的口径是：**跳过 + 记一条 error（含智能体与缺失的工具名）**，
    这一条用例同时钉住这两半 —— 已装配的照常挂上，缺失的必须在日志里看得见。
    """
    from agno.models.openai import OpenAIChat

    from zhiyin_kernel.registry import AgentDescriptor
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine

    async def kb_search(run_context, query: str) -> str:
        """查知识库。"""
        return "hit"

    async def unused_tool(run_context) -> str:
        """没人允许用的工具。"""
        return "nope"

    class _Registry:
        def __init__(self, tools: list[str]) -> None:
            self._descriptor = AgentDescriptor(id="tester", name="测试", tools=tools)

        async def get_agent(self, agent_id: str):
            return self._descriptor

    def _engine(tools_in_registry, *, declared):
        return AgnoAgentEngine(
            model_factory=lambda **kw: OpenAIChat(
                id="t", api_key="sk-test", base_url="https://api.deepseek.com"
            ),
            registry=_Registry(declared),
            tools=tools_in_registry,
        )

    engine = _engine(
        {"kb.search": kb_search, "unused.tool": unused_tool}, declared=["kb.search"]
    )
    attached = await engine._tools_for("tester")
    assert attached == [kb_search], "只允许挂白名单里那一个"

    # 白名单写了未注册的工具名 → 跳过它，其余照挂，并且 error 里点名
    broken = _engine({"kb.search": kb_search}, declared=["kb.search", "typo.tool"])
    with caplog.at_level("ERROR"):
        still_attached = await broken._tools_for("tester")
    assert still_attached == [kb_search], "已装配的工具照常挂上，这一轮不该失败"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "typo.tool" in logged, "缺的那条能力必须留在日志里，否则没人会去补"
    assert "tester" in logged

    # 没有白名单 → 一个工具都不挂（只读角色不该拿到取数能力）
    assert await _engine({"kb.search": kb_search}, declared=[])._tools_for("tester") == []


def test_engine_refuses_tool_run_without_user_context() -> None:
    """挂了工具却没有用户上下文时拒绝执行。

    工具靠 `run_context.user_id` 知道"现在是谁"；没有它，工具只能在空账户上取数，
    而那会静默返回空结果 —— 看起来像"这个人就是没数据"。
    """
    from agno.models.openai import OpenAIChat

    from zhiyin_data_sdk.errors import MissingConfigError
    from zhiyin_orchestration.agent import AgentRequest
    from zhiyin_orchestration.impl.agno_engine import AgnoAgentEngine

    engine = AgnoAgentEngine(
        model_factory=lambda **kw: OpenAIChat(
            id="t", api_key="sk-test", base_url="https://api.deepseek.com"
        ),
        tools={"kb.search": lambda run_context: "x"},
    )
    with pytest.raises(MissingConfigError):
        engine._run_context_kwargs(AgentRequest(agent_id="a", blackboard={}))

    kwargs = engine._run_context_kwargs(
        AgentRequest(agent_id="a", blackboard={"user_id": "u-1", "task_id": "t-1"})
    )
    assert kwargs["user_id"] == "u-1"
    assert kwargs["session_id"] == "t-1"
    # 每次运行还带一个**回传盒子**：工具（chart.render）算出来的可视件放这儿，
    # 跑完由引擎取回来交给上层。它的存在本身就是约定，所以这里钉住。
    assert kwargs["dependencies"] == {"renderables": []}


def test_extract_json_handles_fenced_output() -> None:
    from zhiyin_orchestration.impl.agno_engine import _extract_json

    assert _extract_json('{"a": 1}') == {"a": 1}
    fenced = "```json" + chr(10) + '{"a": 1}' + chr(10) + "```"
    assert _extract_json(fenced) == {"a": 1}
    assert _extract_json("不是 JSON") is None
