"""agno 智能体引擎适配器（AI 面向切面的"编排"切面，见设计文档第六章 6.5）。

分层口径（与基础设施层的 `ai/agno_runtime.py` 配套）：
- **本模块（编排层）**只做智能体**组装与调用**：agent_id → agno Agent 的惰性
  缓存、指令组合（来自注册表描述）、一次 invoke 的上下文渲染与产出解析；
- 模型对象由装配层注入（`model_factory`）——密钥 / base_url / 角色映射等
  框架配置全部在基础设施层维护，依赖守卫也禁止编排层 import 基础设施层；
- 产出解析后走通用 Schema 校验（R-ORC-001），
  非法结构以 valid=False 返回，降级策略仍由业务层决定。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Mapping, Optional

from agno.agent import Agent
from zhiyin_data_sdk.errors import MissingConfigError
from zhiyin_data_sdk.repositories import RegistryRepository
from zhiyin_orchestration.agent import AgentEngine, AgentRequest, AgentResult
from zhiyin_orchestration.impl._shared import _render_prompt
from zhiyin_orchestration.impl.schema import validate_schema

logger = logging.getLogger(__name__)

ModelFactory = Callable[[], Any]


# 提示词与收尾规范都不在本文件里了。
#
# 这个文件曾经带着三段**写死的产品文案**：对话收尾规范（"要用户回答时必须给
# 可点选项"）、"按给定结构输出 JSON、不要寒暄"这条输出纪律，以及它们的落点。
# 它们对**所有**环节生效，所以当时被放在引擎这一层，理由是"漏一个智能体，
# 用户就会在那个环节突然回到自己想办法组织语言"。理由没错，位置错了：
# 这类文案属于提示词，一经写进代码就只能靠发版修改，而且会与库里的那份漂移。
#
# 现在它们从动态资源读（`ai_prompt_template`，layer 分别为 `core` 与 `guide`）。
# 引擎只负责**取用与拼装**，不再持有任何一句产品文案；少一条配置就抛错，
# 不退回默认温度、也不用兜底句顶上。

_CORE_PROMPT = "core.system"
_GUIDE_PROMPT = "guide.closing"

#: 回传盒子的键名。工具与引擎共用它，**在编排层与工具层各写一遍常量**是刻意的：
#: 编排层不能 import 基础设施层的工具实现（依赖守卫），所以这串名字是两层的约定。
CHART_BOX_KEY = "renderables"


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """从模型文本里解析 JSON 对象：直接解析，失败则剥掉 ```json 围栏再试。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("```")
        if start < 0:
            return None
        body = text[start:]
        body = body[body.find("\n") + 1 :] if "\n" in body else body
        end = body.find("```")
        body = body[:end] if end >= 0 else body
        try:
            parsed = json.loads(body.strip())
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _as_mapping(content: Any) -> dict[str, Any]:
    """把 agno 的结构化产出收敛成 dict。

    走 `output_schema` 时 `content` 不再是字符串：可能是 Pydantic 对象，
    也可能是已经解好的 dict。两种都得认 —— 只看字符串会把整轮产出当成空的。
    """
    if content is None:
        return {}
    if isinstance(content, dict):
        return content
    dump = getattr(content, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    if hasattr(content, "model_fields"):  # 老版本 pydantic 风格
        return {k: getattr(content, k) for k in content.model_fields}
    return {}


class AgnoAgentEngine(AgentEngine):
    """基于 agno 的智能体引擎（组装层）。

    提示词全部来自动态资源：总纲（`core`）、收尾规范（`guide`）、角色（`role`）。
    本类只做**取用、拼装、调用、校验**，不持有任何一句产品文案 ——
    这样改口气、改禁令、改某一步的产出要求都不需要发版，也不会出现
    "两个地方各写了一份提示词、改一处忘一处"。
    """

    IMPLEMENTATION_STATUS = "wired"

    def __init__(
        self,
        *,
        model_factory: ModelFactory,
        registry: Optional[RegistryRepository] = None,
        tools: Optional[Mapping[str, Any]] = None,
        raise_on_violation: bool = False,
    ) -> None:
        self._model_factory = model_factory
        self._registry = registry
        # 工具目录：工具名 → 可调用对象（由装配层从基础设施的工具注册表建好注入）。
        # 引擎只认识名字，不认识实现 —— 它不 import 基础设施层。
        self._tools = dict(tools or {})
        self._raise_on_violation = raise_on_violation
        # 缓存键是 `agent_id@stage`：职业顾问同时负责诊断与决策，
        # 两条提示词不同，按 agent_id 缓存会让后一个环节拿到前一个环节的角色说明。
        self._agents: dict[str, Agent] = {}
        self._model_by_key: dict[str, Any] = {}

    async def invoke(self, request: AgentRequest) -> AgentResult:
        from zhiyin_orchestration.errors import ContractViolationError

        # 取提示词与组装代理**不放进 try**：配置缺失不是模型故障，
        # 不能被下面那段"模型不可用不阻断核心链路"接住 —— 接住就等于
        # 把"少了一条配置"变成"这一轮回答得有点怪"，事后没人查得到。
        bundle = await self._prompt_bundle(
            request.agent_id, request.stage, request.prompt_code
        )
        agent = await self._agent_for(
            request.agent_id,
            request.stage,
            bundle,
            request.prompt_code,
            use_tools=request.use_tools,
        )
        run_kwargs = self._run_context_kwargs(request)
        try:
            input_text = self._compose_input(request, bundle)
            # 契约交给 agno 的 output_schema，而不是我们自己把 JSON Schema
            # 拼进用户消息里。差别很大：
            #   · 自己拼：schema 是"提示词的一部分"，模型可以漏字段，
            #     而我们要到解析时才发现 —— 采集中途就变成"产出不合法"；
            #   · 交给框架：agno 把 schema 放进 system message（use_json_mode），
            #     并按它解析与校验，产出结构与契约对不上时在**调用处**就暴露。
            output = await agent.arun(
                input=input_text,
                output_schema=request.output_schema or None,
                **run_kwargs,
            )
        except Exception as exc:  # 模型不可用不阻断核心链路（R-SDK-008）
            return AgentResult(
                agent_id=request.agent_id,
                valid=False,
                degraded=True,
                errors=[f"agno 调用失败：{exc}"],
            )

        # agno 在模型报错时**不抛异常**：它把错误写进 content，并把 status 置为 error。
        # 不认这个状态的话，一次失败的调用会被当成"成功但内容为空"——
        # 没有 output_schema 时甚至会被判为 valid，于是一句错误信息当成结论流到界面上。
        status = getattr(output, "status", None)
        if str(getattr(status, "value", status)).lower() == "error":
            return AgentResult(
                agent_id=request.agent_id,
                structured={},
                raw_text=str(getattr(output, "content", "") or ""),
                valid=False,
                degraded=True,
                errors=["模型调用失败"],
            )

        structured = _as_mapping(output.content)
        raw_text = (
            output.content
            if isinstance(output.content, str)
            else json.dumps(structured, ensure_ascii=False) if structured else str(output.content or "")
        )
        if not structured:
            structured = _extract_json(raw_text) or {}
        errors: list[str] = []
        if request.output_schema:
            if not structured:
                errors = ["模型未返回可解析的结构化产出"]
            else:
                errors = validate_schema(request.output_schema, structured)
            if errors:
                # 一次自动纠错：模型"答了但没按格式"是这个链路最常见的一种失败，
                # 它几乎总是可修的 —— 把错在哪、要哪些字段再明确说一遍，模型能改对。
                # 不修的话，用户看到的就是一句"我没能按格式产出"，而且**每一轮都是它**：
                # 对话走不动，画像/报告/方案全部生成不出来。
                repaired = await self._repair_once(
                    agent, request, structured, raw_text, errors
                )
                if repaired is not None:
                    structured, raw_text, errors = repaired
        if errors and self._raise_on_violation:
            raise ContractViolationError(
                f"智能体 {request.agent_id} 产出不符合契约",
                detail={"errors": errors, "trace_id": request.trace_id},
            )
        return AgentResult(
            agent_id=request.agent_id,
            structured=structured,
            raw_text=raw_text,
            model=getattr(getattr(agent, "model", None), "id", "") or "",
            valid=not errors,
            errors=errors,
            renderables=_renderables_from_run_context(run_kwargs),
        )

    async def _repair_once(
        self,
        agent: Agent,
        request: AgentRequest,
        structured: dict[str, Any],
        raw_text: str,
        errors: list[str],
    ) -> Optional[tuple[dict[str, Any], str, list[str]]]:
        """把"答了但格式不对"的产出再要一次。成功返回新产出，失败返回 None。

        只重试**一次**：第二次还不行，说明问题不在表述上（多半是模型或 schema
        本身的问题），继续重试只会让用户等更久、还看不到任何区别。
        """
        schema = request.output_schema or {}
        keys = ", ".join(sorted((schema.get("properties") or {}).keys()))
        note = (
            "上一次的产出不符合要求，问题在这里："
            + "；".join(str(item) for item in errors[:5])
            + f"\n请**只输出一个 JSON 对象**，且必须包含这些字段：{keys}。"
            + "不要解释、不要 Markdown 代码块、不要多余字段。"
        )
        previous = (raw_text or json.dumps(structured, ensure_ascii=False))[:2000]
        try:
            output = await agent.arun(
                input=f"{note}\n\n上一次的产出如下（供你改写，不要照抄格式）：\n{previous}",
                output_schema=request.output_schema or None,
            )
        except Exception:  # noqa: BLE001 - 纠错失败就当没发生过，走原来的降级
            logger.warning("结构化产出纠错重试失败：agent=%s", request.agent_id, exc_info=True)
            return None

        retry_structured = _as_mapping(output.content)
        retry_text = (
            output.content
            if isinstance(output.content, str)
            else json.dumps(retry_structured, ensure_ascii=False) if retry_structured else ""
        )
        if not retry_structured:
            retry_structured = _extract_json(retry_text) or {}
        retry_errors = validate_schema(request.output_schema, retry_structured) if retry_structured else [
            "模型未返回可解析的结构化产出"
        ]
        if retry_errors:
            logger.warning(
                "结构化产出纠错重试仍未通过：agent=%s errors=%s",
                request.agent_id,
                retry_errors,
            )
            return None
        logger.info("结构化产出纠错重试成功：agent=%s", request.agent_id)
        return retry_structured, retry_text, []

    # ------------------------------------------------------------------

    async def _agent_for(
        self,
        agent_id: str,
        stage: Optional[str],
        bundle: dict[str, Any],
        prompt_code: Optional[str] = None,
        *,
        use_tools: bool = True,
    ) -> Agent:
        key = _agent_key(agent_id, stage, prompt_code, use_tools)
        cached = self._agents.get(key)
        if cached is not None:
            return cached
        instructions: list[str] = []
        core = bundle.get("core")
        if core is not None:
            instructions.append(core.content)
        role = bundle.get("role")
        if role is not None:
            instructions.append(role.content)
        if self._registry is not None:
            descriptor = await self._registry.get_agent(agent_id)
            if descriptor is not None:
                instructions.append(
                    f"你是「{descriptor.name}」。职责：{descriptor.role_summary or '（见团队分工）'}。"
                )
                if descriptor.call_scenarios:
                    instructions.append("你被调用的场合：" + "；".join(descriptor.call_scenarios))
                if descriptor.not_to_do:
                    instructions.append("明确不做：" + "；".join(descriptor.not_to_do))
        # 挂不挂工具由调用方声明（`use_tools`），不是由"是不是任务"推断：
        # 生成类 AI 任务的上下文由业务层一次备齐，产出要可复现，所以不挂；
        # 而"方向匹配"必须自己去取职业要求，就显式声明要工具。
        tools = await self._tools_for(agent_id) if use_tools else []
        agent = Agent(
            model=self._build_model(key, bundle.get("params") or {}),
            instructions=instructions or None,
            tools=tools or None,
            telemetry=False,
            # 结构化产出交给框架：
            #  · use_json_mode：把 schema 放进 system message（而不是让模型
            #    在对话里"顺便"满足一份它看不清的契约）—— DeepSeek 这类
            #    OpenAI 兼容服务吃这一套，不强依赖 json_schema 严格模式；
            #  · parse_response：框架负责解析与校验，产出结构不对在调用处就暴露。
            use_json_mode=True,
            parse_response=True,
        )
        self._agents[key] = agent
        return agent

    def _build_model(self, key: str, params: dict[str, Any]) -> Any:
        """按提示词行上的参数建模型（一次一条，按 key 缓存）。

        参数与提示词同表，就是为了让"换一条提示词"与"换它的温度"是一次动作；
        工厂不接受参数就直接让它报错：工厂是装配层给的，对不上说明装配错了，
        这时候"悄悄按默认温度跑"只会让调参调不动，而且看不出为什么。
        """
        cached = self._model_by_key.get(key)
        if cached is not None:
            return cached
        temperature = params.get("temperature")
        model = (
            self._model_factory()
            if temperature is None
            else self._model_factory(temperature=float(temperature))
        )
        self._model_by_key[key] = model
        return model

    async def _prompt_bundle(
        self,
        agent_id: str,
        stage: Optional[str],
        prompt_code: Optional[str] = None,
    ) -> dict[str, Any]:
        """一次取齐这个角色这一轮要用的提示词。

        命中顺序：`(agent_id, stage)` → `(agent_id, 无环节)`。
        `guide` 与 `core` 全局各一条。**任一条取不到就抛**：
        缺配置时模型会用通用聊天的方式回答，症状是"这个环节突然不说人话了"，
        而且不报错、不留痕；与其等到有人发现，不如在调用处就炸。

        指定 `prompt_code` 时直接按 code 取那一条（AI 任务走这条），
        不再按角色归属去猜 —— 任务提示词与角色提示词是两回事。
        """
        if self._registry is None:
            raise MissingConfigError("智能体引擎未接入动态资源，取不到任何提示词")
        core = await _required_prompt(self._registry, _CORE_PROMPT)
        guide = await _required_prompt(self._registry, _GUIDE_PROMPT)
        if prompt_code:
            role = await _required_prompt(self._registry, prompt_code)
            return {
                "core": core,
                "guide": guide,
                "role": role,
                "params": dict(role.params or {}),
            }
        roles = [
            item
            for item in await self._registry.list_prompts(agent_id=agent_id)
            if item.layer == "role"
        ]
        exact = [item for item in roles if stage and item.stage == stage]
        generic = [item for item in roles if not item.stage]
        role = (exact or generic or [None])[0]
        if role is None:
            raise MissingConfigError(
                f"智能体 {agent_id} 在环节 {stage or '-'} 没有角色提示词"
            )
        return {
            "core": core,
            "guide": guide,
            "role": role,
            "params": dict(role.params or {}),
        }

    async def _tools_for(self, agent_id: str) -> list[Any]:
        """按智能体注册表里的白名单取工具。

        白名单写在 `agents.json` 的 `tools` 字段（业务口径：某个智能体允许用哪些工具），
        实现侧不得自作主张扩大权限。
        **未注册的工具名：跳过它、记一条 error，但不让这一轮失败。**

        这条口径改过一次，两种做法各有代价，写清楚为什么改成现在这样：

        · 原来的做法是抛错（"静默忽略等于以为给了它一个能力，其实没有"）。
          守住这个意图没错，但它把"这个部署没装某个能力"的代价压到了**用户那一轮**：
          实测一次 —— `.env` 里没配搜索网关，`web.search` 因此没注册，
          而职业顾问的白名单里写着它，于是 ②③④ 每一步都 500：
          用户话说了一半、界面卡住，日志里只有一条配置错误。
        · 现在：缺失**如实记 error**（含智能体名与缺失的工具名，运维在日志里看得见），
          这一轮照常用**已装配**的工具跑完。同类先例见编排器里那句
          "资产落库失败不打断对话" —— 服务端的配置问题不该吃掉用户的话。

        "未注册"与"写错名字"是两件事：这里两种都会落在 missing 里，
        所以日志必须把名字打全，让人一眼看出是"没装配"还是"名字打错了"。
        """
        if not self._tools or self._registry is None:
            return []
        descriptor = await self._registry.get_agent(agent_id)
        if descriptor is None or not descriptor.tools:
            return []
        missing = sorted(name for name in descriptor.tools if name not in self._tools)
        if missing:
            logger.error(
                "智能体 %s 的白名单里有未注册的工具 %s：本次跳过。"
                "未装配就在装配层注册它，写错名字就改 agents.json —— 两者都要处理，"
                "否则这个智能体一直少一条能力而没人知道。",
                agent_id,
                missing,
            )
        return [self._tools[name] for name in descriptor.tools if name in self._tools]

    def _run_context_kwargs(self, request: AgentRequest) -> dict[str, Any]:
        """给这次运行带上用户与会话上下文。

        工具靠 `run_context.user_id` 知道"现在是谁"，**不接受模型传用户标识**。
        带了工具却没有用户上下文时直接抛错 —— 那种情况下工具只能拿到空用户，
        等于让它在错误的账户上取数。
        """
        user_id = str((request.blackboard or {}).get("user_id") or "")
        session_id = str(
            (request.blackboard or {}).get("task_id") or request.trace_id or ""
        )
        if self._tools and not user_id:
            raise MissingConfigError("挂了工具但这次调用没有用户上下文，拒绝执行")
        kwargs: dict[str, Any] = {}
        if user_id:
            kwargs["user_id"] = user_id
        if session_id:
            kwargs["session_id"] = session_id
        # 这一轮的**回传盒子**：工具（如 chart.render）算出来的东西放这儿，
        # 跑完由本引擎取回来交给上层。agno 的 RunContext 有 dependencies 这个
        # 每次运行一份的 dict，正好当这条通道 —— 不必给工具加全局状态，
        # 也不让模型有机会往里塞东西（它只能调工具，碰不到这个 dict）。
        kwargs["dependencies"] = {CHART_BOX_KEY: []}
        return kwargs

    def _compose_input(self, request: AgentRequest, bundle: dict[str, Any]) -> str:
        """拼装用户消息：只有收尾规范与上下文，一个字的产品文案都不在这里。

        "按给定结构输出 JSON、不要 Markdown、不要解释"这条约束在总纲里
        （`core.system` 的输出纪律），不在代码里 —— 两份必然漂移。
        """
        parts: list[str] = [bundle["guide"].content]
        body = _render_prompt(request.prompt_vars, request.blackboard)
        if body:
            parts.append(body)
        return "\n\n".join(parts)


def _renderables_from_run_context(run_kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    """把工具写进回传盒子的可视件取回来。没有就返回空表。

    盒子取不到、里面不是数组、或者根本没放东西，一律按"这一轮没有可视件"处理 ——
    它们是锦上添花，缺了不该让一场对话失败。
    """
    dependencies = run_kwargs.get("dependencies")
    if not isinstance(dependencies, dict):
        return []
    box = dependencies.get(CHART_BOX_KEY)
    if not isinstance(box, list):
        return []
    return [item for item in box if isinstance(item, dict)]


def _agent_key(
    agent_id: str,
    stage: Optional[str],
    prompt_code: Optional[str] = None,
    use_tools: bool = True,
) -> str:
    """缓存键：同一智能体在不同环节／不同任务上是**不同的**代理。

    职业顾问同时负责诊断与决策，AI 任务也用同一个 agent_id —— 不把环节与
    提示词条目编进键里，后一个会拿到前一个的角色说明。
    """
    tools_mark = "tools" if use_tools else "plain"
    return f"{agent_id}@{stage or '-'}@{prompt_code or '-'}@{tools_mark}"


async def _required_prompt(registry: RegistryRepository, code: str) -> Any:
    """取一条必须存在的提示词。取不到直接抛，用一句空提示词顶上比少一条配置更坏。"""
    prompt = await registry.get_prompt(code)
    if prompt is None:
        raise MissingConfigError(f"缺少提示词配置：{code}")
    return prompt


__all__ = ["AgnoAgentEngine"]
